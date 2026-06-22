import type { ApiClient, MassingParams, MassingResult, ProformaResult } from "../api/client";

/**
 * Real-estate development finance (Proforma) view — edit the key deal drivers, solve live,
 * and read the capital stack, returns and JV waterfall. Spreadsheet-familiar but live: the
 * pure Python engine solves S&U (with interest-reserve circularity), construction loan,
 * XIRR/NPV/EM and the waterfall server-side in <100ms.
 */
const DEFAULT = {
  timing: { construction_months: 18, leaseup_months: 12, hold_years: 5, start_date: "2026-01-01" },
  cost_lines: [
    { category: "land", name: "Land", amount: 4_000_000, curve: "upfront", start_month: 0, end_month: 0 },
    { category: "hard", name: "Construction", amount: 20_000_000, curve: "scurve", start_month: 1, end_month: 17 },
    { category: "soft", name: "Soft costs", amount: 3_000_000, curve: "linear", start_month: 0, end_month: 17 },
    { category: "contingency", name: "Contingency", amount: 1_000_000, curve: "scurve", start_month: 1, end_month: 17 },
  ],
  debt: { ltc: 0.65, rate: 0.085, points: 0.01, funding: "equity_first", max_ltv: null as number | null, min_dscr: null as number | null },
  equity: { lp_pct: 0.9, gp_pct: 0.1 },
  operations: { potential_rent_annual: 3_600_000, other_income_annual: 120_000, opex_annual: 1_300_000, reserves_annual: 0, stabilized_occ: 0.94, credit_loss_pct: 0.02 },
  exit: { exit_cap: 0.055, selling_cost_pct: 0.02 },
  waterfall: { pref_rate: 0.08, style: "american", clawback: false, tiers: [{ hurdle: 0.12, lp: 0.8, gp: 0.2 }, { hurdle: 0.18, lp: 0.7, gp: 0.3 }, { hurdle: null, lp: 0.6, gp: 0.4 }] },
  discount_rate: 0.1,
};

// editable drivers: [label, path, kind] — kind 'pct' shows/edits as %
type Field = [string, string, "money" | "pct" | "num"];
const FIELDS: Field[] = [
  ["Land $", "cost_lines.0.amount", "money"],
  ["Hard cost $", "cost_lines.1.amount", "money"],
  ["Soft cost $", "cost_lines.2.amount", "money"],
  ["Contingency $", "cost_lines.3.amount", "money"],
  ["LTC", "debt.ltc", "pct"],
  ["Loan rate", "debt.rate", "pct"],
  ["Constr. months", "timing.construction_months", "num"],
  ["Hold years", "timing.hold_years", "num"],
  ["Rent / yr", "operations.potential_rent_annual", "money"],
  ["OpEx / yr", "operations.opex_annual", "money"],
  ["Reserves / yr", "operations.reserves_annual", "money"],
  ["Stab. occ", "operations.stabilized_occ", "pct"],
  ["Exit cap", "exit.exit_cap", "pct"],
  ["LP / GP", "equity.lp_pct", "pct"],
  ["Pref", "waterfall.pref_rate", "pct"],
];

function get(obj: any, path: string): any {
  return path.split(".").reduce((o, k) => o?.[k], obj);
}
function set(obj: any, path: string, val: any): void {
  const ks = path.split("."); const last = ks.pop()!;
  ks.reduce((o, k) => o[k], obj)[last] = val;
}
const money = (n: number) => "$" + Math.round(n).toLocaleString();
const pct = (n: number | null) => (n == null ? "n/a" : (n * 100).toFixed(1) + "%");

export class ProformaUI {
  private a = structuredClone(DEFAULT);
  private timer = 0;

  constructor(private root: HTMLElement, private api: ApiClient,
              private setStatus: (m: string) => void,
              private projectId: () => string | null = () => null) {}

  async init() {
    this.render();
    await this.solve();
  }

  private render() {
    this.root.innerHTML = `<div class="section-title">Proforma — development underwriting</div>`;
    const form = document.createElement("div"); form.className = "pf-form";
    for (const [label, path, kind] of FIELDS) {
      const wrap = document.createElement("label"); wrap.className = "pf-field";
      wrap.innerHTML = `<span>${label}</span>`;
      const inp = document.createElement("input"); inp.type = "number"; inp.step = "any";
      const raw = get(this.a, path);
      inp.value = String(kind === "pct" ? +(raw * 100).toFixed(3) : raw);
      inp.oninput = () => {
        const v = parseFloat(inp.value); if (isNaN(v)) return;
        set(this.a, path, kind === "pct" ? v / 100 : v);
        if (path === "equity.lp_pct") set(this.a, "equity.gp_pct", 1 - v / 100);
        clearTimeout(this.timer);
        this.timer = window.setTimeout(() => this.solve(), 350);  // debounced live solve
      };
      wrap.appendChild(inp); form.appendChild(wrap);
    }
    // optional debt-sizing constraints (blank = off → loan sized by LTC only)
    const sizingField = (label: string, path: string, scale: number, placeholder: string) => {
      const wrap = document.createElement("label"); wrap.className = "pf-field";
      wrap.innerHTML = `<span>${label}</span>`;
      const inp = document.createElement("input"); inp.type = "number"; inp.step = "any"; inp.placeholder = placeholder;
      const raw = get(this.a, path);
      inp.value = raw == null ? "" : String(+(raw * scale).toFixed(3));
      inp.oninput = () => {
        const v = parseFloat(inp.value);
        set(this.a, path, inp.value.trim() === "" || isNaN(v) ? null : v / scale);
        clearTimeout(this.timer);
        this.timer = window.setTimeout(() => this.solve(), 350);
      };
      wrap.appendChild(inp); form.appendChild(wrap);
    };
    sizingField("Max LTV", "debt.max_ltv", 100, "off");
    sizingField("Min DSCR", "debt.min_dscr", 1, "off");
    // sticky returns summary bar — always visible, re-solved live (populated by renderResult)
    const bar = document.createElement("div"); bar.id = "pf-returns-bar"; bar.className = "pf-returns-bar";
    bar.innerHTML = `<span class="meta">Edit assumptions to solve the deal…</span>`;
    this.root.appendChild(bar);

    // sub-tabs group the (now many) panels: Feasibility · Budget & Capital · Underwriting · Deliverables
    const TABS: [string, string][] = [["feas", "Feasibility"], ["cap", "Budget & Capital"],
                                      ["uw", "Underwriting"], ["deliver", "Deliverables"]];
    const tabbar = document.createElement("div"); tabbar.className = "pf-subtabs";
    const sections: Record<string, HTMLElement> = {}; const tabBtns: Record<string, HTMLButtonElement> = {};
    for (const [key, label] of TABS) {
      const b = document.createElement("button"); b.className = "pf-subtab"; b.textContent = label; b.dataset.k = key;
      b.onclick = () => showTab(key); tabbar.appendChild(b); tabBtns[key] = b;
      const s = document.createElement("div"); s.className = "pf-section"; sections[key] = s;
    }
    this.root.appendChild(tabbar);
    for (const [key] of TABS) this.root.appendChild(sections[key]);
    const showTab = (k: string) => {
      for (const [key] of TABS) { sections[key].style.display = key === k ? "block" : "none"; tabBtns[key].classList.toggle("active", key === k); }
      localStorage.setItem("pf-tab", k);
    };
    // route each panel into its section by temporarily pointing this.root at the section
    const self = this as unknown as { root: HTMLElement };
    const into = (el: HTMLElement, fn: () => void) => { const r = self.root; self.root = el; try { fn(); } finally { self.root = r; } };
    into(sections.feas, () => { this.renderMassing(); this.renderTestFit(); this.renderProperty(); });
    into(sections.cap, () => { this.renderBudget(); this.renderSourcesUses(); this.renderSpecialty(); });
    into(sections.uw, () => {
      sections.uw.appendChild(form);
      const out = document.createElement("div"); out.id = "pf-out"; sections.uw.appendChild(out);
      const sens = document.createElement("div"); sens.id = "pf-sens"; sections.uw.appendChild(sens);
      const mc = document.createElement("div"); mc.id = "pf-mc"; sections.uw.appendChild(mc);
      this.renderDraws();
    });
    into(sections.deliver, () => { this.renderDeliverables(); this.renderModelLink(); });
    showTab(localStorage.getItem("pf-tab") || "uw");
  }

  /** Deliverables tab: the investor outputs (investment memo + pitch deck PDFs). */
  private renderDeliverables() {
    const pid = this.projectId();
    const host = document.createElement("div");
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">📑 Investor deliverables</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to generate the memo / deck.</div>`); this.root.appendChild(host); return; }
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;flex-wrap:wrap";
    const memo = document.createElement("button"); memo.className = "file-btn"; memo.textContent = "📄 Investment memo (PDF)";
    memo.onclick = () => window.open(this.api.url(`/projects/${pid}/investment-memo.pdf`), "_blank");
    const deck = document.createElement("button"); deck.className = "file-btn"; deck.textContent = "📊 Pitch deck (PDF)";
    deck.onclick = () => window.open(this.api.url(`/projects/${pid}/investment-deck.pdf`), "_blank");
    row.append(memo, deck); host.appendChild(row); this.root.appendChild(host);
  }

  /** Zoning → model: enter a lot + zoning envelope (FAR, setbacks, height) and generate a real IFC
   *  massing model + a starter acquisition proforma in one click. The IFC-native answer to TestFit/
   *  Forma feasibility — the generated model flows into the viewer, drawings, QTO and this proforma. */
  private renderMassing() {
    const host = document.createElement("div"); host.id = "pf-massing";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🏗️ Generate from zoning</div>` +
      `<div class="meta" style="margin-bottom:6px">Lot + zoning envelope → buildable program, an IFC massing model, and an acquisition proforma.</div>`;
    // [label, key, default, step]
    const fields: [string, keyof MassingParams, number, string][] = [
      ["Lot width (m)", "lot_width", 50, "any"], ["Lot depth (m)", "lot_depth", 40, "any"],
      ["FAR", "far", 3.0, "0.1"], ["Coverage max", "coverage_max", 0.6, "0.05"],
      ["Front setback (m)", "front_setback", 6, "any"], ["Rear setback (m)", "rear_setback", 6, "any"],
      ["Side setback (m)", "side_setback", 3, "any"], ["Height limit (m)", "height_limit", 0, "any"],
      ["Floor-to-floor (m)", "floor_to_floor", 3.5, "0.1"], ["Avg unit (m²)", "avg_unit_m2", 75, "any"],
      ["Land cost $", "land_cost", 2_500_000, "any"], ["Hard $/sf", "hard_cost_psf", 225, "any"],
      ["Rent $/unit·mo", "rent_per_unit_month", 3000, "any"], ["Exit cap", "exit_cap", 0.05, "0.005"],
    ];
    const grid = document.createElement("div"); grid.className = "pf-form";
    // use type selector
    const useWrap = document.createElement("label"); useWrap.className = "pf-field";
    useWrap.innerHTML = `<span>Use type</span>`;
    const useSel = document.createElement("select");
    useSel.innerHTML = `<option value="residential">Residential</option><option value="commercial">Commercial</option>`;
    useWrap.appendChild(useSel); grid.appendChild(useWrap);
    const inputs: Record<string, HTMLInputElement> = {};
    for (const [label, key, def, step] of fields) {
      const wrap = document.createElement("label"); wrap.className = "pf-field";
      wrap.innerHTML = `<span>${label}</span>`;
      const inp = document.createElement("input"); inp.type = "number"; inp.step = step; inp.value = String(def);
      if (key === "height_limit") inp.placeholder = "none";
      inputs[key] = inp; wrap.appendChild(inp); grid.appendChild(wrap);
    }
    host.appendChild(grid);

    // structural frame option — turns the massing into a real concrete frame (columns + beams)
    const frameWrap = document.createElement("label");
    frameWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const frameChk = document.createElement("input"); frameChk.type = "checkbox";
    frameWrap.append(frameChk, document.createTextNode("Generate concrete structural frame (columns + beams on a 7.5 m grid)"));
    host.appendChild(frameWrap);
    const unitWrap = document.createElement("label");
    unitWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const unitChk = document.createElement("input"); unitChk.type = "checkbox";
    unitWrap.append(unitChk, document.createTextNode("Subdivide floors into units (per-apartment spaces)"));
    host.appendChild(unitWrap);
    const envWrap = document.createElement("label");
    envWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const envChk = document.createElement("input"); envChk.type = "checkbox";
    envWrap.append(envChk, document.createTextNode("Wrap in facade + windows (envelope @ 40% WWR)"));
    host.appendChild(envWrap);
    const coreWrap = document.createElement("label");
    coreWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const coreChk = document.createElement("input"); coreChk.type = "checkbox";
    coreWrap.append(coreChk, document.createTextNode("Add service core (elevator + stair + MEP risers)"));
    host.appendChild(coreWrap);
    const corrWrap = document.createElement("label");
    corrWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
    const corrChk = document.createElement("input"); corrChk.type = "checkbox";
    corrWrap.append(corrChk, document.createTextNode("Double-loaded corridor unit layout (test-fit)"));
    host.appendChild(corrWrap);

    const params = (): MassingParams => {
      const p: MassingParams = { use_type: useSel.value as "residential" | "commercial", name: "Massing Study" };
      for (const [, key] of fields) {
        const v = parseFloat(inputs[key].value);
        if (key === "height_limit") { p.height_limit = isNaN(v) || v <= 0 ? null : v; }
        else if (!isNaN(v)) (p as Record<string, unknown>)[key] = v;
      }
      p.frame = frameChk.checked;
      p.units = unitChk.checked;
      p.envelope = envChk.checked;
      p.core = coreChk.checked;
      if (corrChk.checked) { p.units = true; p.unit_layout = "corridor"; }
      return p;
    };
    const out = document.createElement("div"); out.style.marginTop = "6px";
    const showResult = (r: MassingResult, generated: boolean) => {
      const m = r.metrics, ret = r.proforma.returns, su = r.proforma.sources_uses;
      out.innerHTML =
        `<div class="meta" style="margin-bottom:4px"><b>${m.floors} floors</b> · ${Math.round(m.building_height_m)} m · ` +
        `<b>${m.buildable_gfa_sf.toLocaleString()} sf</b> GFA · ${m.units} units · ${m.footprint_m2.toLocaleString()} m² plate ` +
        `<span class="meta">(bound by ${m.binding_constraint}, ${m.far_achieved} FAR)</span></div>` +
        (su ? `<div class="meta">Total cost ${money(su.total_uses ?? 0)} · equity ${money(su.equity ?? 0)} · ` +
              `IRR <b>${pct(ret?.equity_irr ?? null)}</b> · ${ret?.equity_multiple ?? "—"}× EM</div>` : "") +
        (r.proforma.solve_error ? `<div class="meta" style="color:#e2554a">proforma: ${r.proforma.solve_error}</div>` : "") +
        (m.structure ? `<div class="meta">🏛 Structure: <b>${m.structure.system}</b> · ${m.structure.lateral_system}` +
              ` · cols ${m.structure.members_mm.column} mm</div>` : "") +
        (generated ? `<div class="meta" style="color:var(--accent)">✓ IFC model generated & publishing — open the Model workspace to view.</div>` : "");
    };

    const btnRow = document.createElement("div"); btnRow.style.cssText = "display:flex;gap:6px;margin-top:6px";
    const estBtn = document.createElement("button"); estBtn.className = "tool-btn"; estBtn.textContent = "Estimate yield";
    estBtn.onclick = async () => {
      out.innerHTML = `<span class="meta">computing…</span>`;
      try { showResult(await this.api.previewMassing(params()), false); }
      catch (e) { out.innerHTML = `<div class="meta" style="color:#e2554a">${(e as Error).message}</div>`; }
    };
    const genBtn = document.createElement("button"); genBtn.className = "file-btn"; genBtn.textContent = "Generate IFC model + apply";
    genBtn.onclick = async () => {
      const pid = this.projectId();
      if (!pid) { out.innerHTML = `<div class="meta">Open or create a project first (＋ New), then generate its model.</div>`; return; }
      out.innerHTML = `<span class="meta">generating model + proforma…</span>`;
      try {
        const r = await this.api.generateMassing(pid, params());
        showResult(r, true);
        // adopt the generated acquisition assumptions as the live proforma
        this.a = structuredClone(r.proforma.assumptions) as typeof this.a;
        this.render(); void this.solve();
        this.setStatus(`generated ${r.metrics.floors}-floor massing (${r.metrics.buildable_gfa_sf.toLocaleString()} sf) → proforma seeded`);
      } catch (e) { out.innerHTML = `<div class="meta" style="color:#e2554a">${(e as Error).message}</div>`; }
    };
    btnRow.append(estBtn, genBtn); host.append(btnRow, out);
    this.root.appendChild(host);
  }

  /** Test Fit: compare unit-mix schemes on a floor plate — yield (units, efficiency, NSF) + parking,
   *  ranked. The TestFit-style "explore scenarios, find the deal that pencils" surface. */
  private renderTestFit() {
    const host = document.createElement("div"); host.id = "pf-testfit";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">📐 Test Fit — compare unit-mix schemes</div>`
      + `<div class="meta" style="margin-bottom:6px">Fit a unit mix to a floor plate; compare yield + parking across schemes.</div>`;
    const grid = document.createElement("div"); grid.className = "pf-form";
    const inp = (label: string, val: number) => {
      const w = document.createElement("label"); w.className = "pf-field"; w.innerHTML = `<span>${label}</span>`;
      const i = document.createElement("input"); i.type = "number"; i.step = "any"; i.value = String(val); w.appendChild(i); grid.appendChild(w); return i;
    };
    const wi = inp("Plate width (m)", 40), di = inp("Plate depth (m)", 18), fi = inp("Floors", 6);
    host.appendChild(grid);
    const out = document.createElement("div"); out.style.marginTop = "6px";
    const opt = document.createElement("button"); opt.className = "tool-btn"; opt.style.marginLeft = "6px";
    opt.textContent = "⚡ Optimize (find the deal that pencils)";
    opt.onclick = async () => {
      out.innerHTML = `<span class="meta">sweeping schemes…</span>`;
      try {
        const r = await this.api.testFitOptimize({ plate_w: +wi.value, plate_d: +di.value, floors: +fi.value, targets: { min_units: 1 } });
        if (!r.best) { out.innerHTML = `<div class="meta">no feasible scheme for these targets</div>`; return; }
        const rows = r.ranked.map((s, n) => `<tr${n === 0 ? ' style="font-weight:700"' : ""}>`
          + `<th style="text-align:left">${s.name}${n === 0 ? " ★" : ""}</th>`
          + `<td style="text-align:right">${s.total_units}</td><td style="text-align:right">${(s.efficiency * 100).toFixed(0)}%</td>`
          + `<td style="text-align:right">${s.parking_stalls}</td><td style="text-align:right">${(s.yield_on_cost * 100).toFixed(1)}%</td></tr>`).join("");
        out.innerHTML = `<div class="meta" style="margin-bottom:2px">Swept ${r.considered} schemes · ${r.feasible} feasible · ranked by ${r.objective.replace(/_/g, " ")}</div>`
          + `<table class="sens-table" style="font-size:12px"><tr><th style="text-align:left">Scheme</th><th>Units</th><th>Eff.</th><th>Stalls</th><th>YoC</th></tr>${rows}</table>`;
      } catch { out.innerHTML = `<div class="meta">optimize unavailable (API offline)</div>`; }
    };
    const run = document.createElement("button"); run.className = "file-btn"; run.textContent = "Compare schemes";
    run.onclick = async () => {
      out.innerHTML = `<span class="meta">fitting…</span>`;
      try {
        const r = await this.api.testFitCompare({ plate_w: +wi.value, plate_d: +di.value, floors: +fi.value });
        const rows = r.schemes.map((s) => `<tr${s.name === r.best ? ' style="font-weight:700"' : ""}>`
          + `<th style="text-align:left">${s.name}${s.name === r.best ? " ★" : ""}</th>`
          + `<td style="text-align:right">${s.total_units}</td>`
          + `<td style="text-align:right"${s.daylight_limited ? ' title="deep plate — dark interior earns no rent"' : ""}>${(s.daylight_efficiency * 100).toFixed(0)}%${s.daylight_limited ? " ⚠" : ""}</td>`
          + `<td style="text-align:right">${s.avg_unit_sf.toLocaleString()}</td><td style="text-align:right">${s.total_nsf.toLocaleString()}</td>`
          + `<td style="text-align:right">${s.parking_stalls}</td></tr>`).join("");
        out.innerHTML = `<table class="sens-table" style="font-size:12px"><tr><th style="text-align:left">Scheme</th>`
          + `<th>Units</th><th title="rentable ÷ gross, daylight-limited">Daylight</th><th>Avg SF</th><th>Rent. SF</th><th>Stalls</th></tr>${rows}</table>`
          + `<div class="meta" style="margin-top:4px">Best by units: <b>${r.best}</b> · daylight efficiency = rentable area within ~9 m of a window ÷ gross</div>`;
      } catch { out.innerHTML = `<div class="meta">test-fit unavailable (API offline)</div>`; }
    };
    host.append(run, opt, out); this.root.appendChild(host);
  }

  /** Property & tax assumptions: parcel/areas/purchase/taxes; taxes → OPEX, price → acquisition. */
  private renderProperty() {
    const host = document.createElement("div"); host.id = "pf-property";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🏢 Property & tax assumptions</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to set property facts.</div>`); this.root.appendChild(host); return; }
    const body = document.createElement("div"); body.innerHTML = `<div class="meta">loading…</div>`; host.appendChild(body); this.root.appendChild(host);
    void this.api.property(pid).then((resp) => {
      const prop = resp.property as Record<string, number> & { taxes?: Record<string, number> };
      let timer = 0; const save = () => { clearTimeout(timer); timer = window.setTimeout(() => void this.api.saveProperty(pid, prop).then((r) => { sumEl.textContent = summary(r.summary.total_taxes, r.summary.purchase_price); }), 500); };
      const grid = document.createElement("div"); grid.className = "pf-form";
      const field = (label: string, key: string, taxes = false) => {
        const w = document.createElement("label"); w.className = "pf-field"; w.innerHTML = `<span>${label}</span>`;
        const i = document.createElement("input"); i.type = "number"; i.step = "any";
        i.value = String(taxes ? (prop.taxes?.[key] ?? 0) : (prop[key] ?? 0));
        i.oninput = () => { const v = parseFloat(i.value) || 0; if (taxes) { prop.taxes = prop.taxes || {}; prop.taxes[key] = v; } else prop[key] = v; save(); };
        w.appendChild(i); grid.appendChild(w);
      };
      field("Purchase price $", "purchase_price"); field("Building SF", "building_sf"); field("Land SF", "land_sf");
      field("School tax $", "school", true); field("County tax $", "county", true); field("Town tax $", "town", true); field("Fire tax $", "fire", true);
      const summary = (tax: number, price: number) => `Total taxes ${money(tax)}/yr → OPEX · purchase ${money(price)} → acquisition`;
      const sumEl = document.createElement("div"); sumEl.className = "meta"; sumEl.style.marginTop = "4px";
      sumEl.textContent = summary(resp.summary.total_taxes, resp.summary.purchase_price);
      const apply = document.createElement("button"); apply.className = "file-btn"; apply.style.marginTop = "6px"; apply.textContent = "Apply to proforma";
      apply.onclick = async () => {
        const r = await this.api.saveProperty(pid, prop); const d = r.summary.deltas;
        const a = this.a as { cost_lines: { name: string; amount: number }[]; operations: { opex_annual: number } };
        if (d.acquisition_amount) { const land = a.cost_lines.find((c) => /acquisition|land/i.test(c.name)); if (land) land.amount = d.acquisition_amount; }
        a.operations.opex_annual = (a.operations.opex_annual || 0) + d.opex_annual_add;
        this.render(); void this.solve(); this.setStatus(`applied property: ${money(d.acquisition_amount)} acquisition, ${money(d.opex_annual_add)}/yr taxes`);
      };
      body.innerHTML = ""; body.append(grid, sumEl, apply);
    }).catch(() => { body.innerHTML = `<div class="meta">property unavailable (API offline)</div>`; });
  }

  /** Sources & Uses: the capital plan from the cost budget — grouped uses vs sized debt + equity. */
  private renderSourcesUses() {
    const host = document.createElement("div"); host.id = "pf-su";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🏦 Sources &amp; Uses</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to see the capital plan.</div>`); this.root.appendChild(host); return; }
    const body = document.createElement("div"); body.innerHTML = `<div class="meta">loading…</div>`;
    host.appendChild(body); this.root.appendChild(host);
    void this.api.sourcesUses(pid).then((su) => {
      const rows = (items: { label: string; amount: number }[]) =>
        items.map((i) => `<tr><th style="text-align:left;font-weight:400">${i.label}</th><td style="text-align:right">${money(i.amount)}</td></tr>`).join("");
      body.innerHTML =
        `<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">`
        + `<div><div class="section-title" style="font-size:12px;margin:0 0 2px">Uses</div>`
        + `<table class="sens-table" style="font-size:12px">${rows(su.uses)}`
        + `<tr style="font-weight:700"><th style="text-align:left">Total uses</th><td style="text-align:right">${money(su.total_uses)}</td></tr></table></div>`
        + `<div><div class="section-title" style="font-size:12px;margin:0 0 2px">Sources</div>`
        + `<table class="sens-table" style="font-size:12px">${rows(su.sources)}`
        + `<tr style="font-weight:700"><th style="text-align:left">Total sources</th><td style="text-align:right">${money(su.total_sources)}</td></tr></table></div>`
        + `</div>`
        + `<div class="meta" style="margin-top:6px">${(su.ltc * 100).toFixed(0)}% LTC · debt sized by ${su.binding_constraint} · ${su.balanced ? "✓ balanced" : "⚠ unbalanced"}</div>`;
    }).catch(() => { body.innerHTML = `<div class="meta">Sources &amp; Uses unavailable — build a cost budget first.</div>`; });
  }

  /** Specialty assets: on-site energy (solar/wind/battery/rainwater) + vertical-farm (PFAL) tower
   *  revenue. Capex + annual revenue/opex/energy-offset flow into the proforma — the thesis-grounded
   *  differentiator tying the physical program to the deal economics. */
  private renderSpecialty() {
    const host = document.createElement("div"); host.id = "pf-specialty";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">⚡ Specialty: energy & vertical farm</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to model on-site energy + farm revenue.</div>`); this.root.appendChild(host); return; }
    const bodyEl = document.createElement("div"); host.appendChild(bodyEl); this.root.appendChild(host);
    bodyEl.innerHTML = `<div class="meta">loading…</div>`;

    void this.api.specialty(pid).then((resp) => {
      const params = resp.params as Record<string, Record<string, number> & { [k: string]: unknown }> & { energy_enabled?: boolean; pfal_enabled?: boolean };
      let timer = 0;
      const save = () => { clearTimeout(timer); timer = window.setTimeout(() => void this.api.saveSpecialty(pid, params).then((r) => paint(r.summary)), 500); };
      // [label, group, key]
      const FIELDS: [string, "energy" | "pfal", string][] = [
        ["Solar SF", "energy", "solar_sf"], ["$/panel", "energy", "cost_per_panel"],
        ["Battery units", "energy", "battery_units"], ["Rainwater $", "energy", "rainwater_capex"],
        ["PFAL SF", "pfal", "pfal_sf"], ["Greens $/lb", "pfal", "green_price_lb"], ["Herbs $/lb", "pfal", "herb_price_lb"],
      ];
      const paint = (sum?: import("../api/client").SpecialtySummary) => {
        bodyEl.innerHTML = "";
        // enable toggles
        const tog = document.createElement("div"); tog.style.cssText = "display:flex;gap:14px;margin-bottom:6px";
        for (const [k, lbl] of [["energy_enabled", "On-site energy"], ["pfal_enabled", "Vertical farm (PFAL)"]] as const) {
          const w = document.createElement("label"); w.style.cssText = "display:flex;align-items:center;gap:5px;font-size:12px";
          const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = params[k] !== false;
          cb.onchange = () => { (params as Record<string, unknown>)[k] = cb.checked; save(); paint(); };
          w.append(cb, document.createTextNode(lbl)); tog.appendChild(w);
        }
        bodyEl.appendChild(tog);
        const grid = document.createElement("div"); grid.className = "pf-form";
        for (const [label, group, key] of FIELDS) {
          params[group] = params[group] || {};
          const wrap = document.createElement("label"); wrap.className = "pf-field"; wrap.innerHTML = `<span>${label}</span>`;
          const inp = document.createElement("input"); inp.type = "number"; inp.step = "any";
          inp.value = String((params[group] as Record<string, number>)[key] ?? 0);
          inp.oninput = () => { (params[group] as Record<string, number>)[key] = parseFloat(inp.value) || 0; save(); };
          wrap.appendChild(inp); grid.appendChild(wrap);
        }
        bodyEl.appendChild(grid);
        if (sum) {
          const s = document.createElement("div"); s.className = "meta"; s.style.marginTop = "6px";
          s.innerHTML = `Capex <b>${money(sum.capex_total)}</b>`
            + (sum.energy ? ` · ${sum.energy.solar_panels.toLocaleString()} panels` : "")
            + (sum.pfal ? ` · ${sum.pfal.towers.toLocaleString()} towers` : "")
            + `<br>Produce revenue <b>${money(sum.annual_revenue)}</b>/yr · energy offset ${money(sum.annual_energy_offset)}/yr · farm opex ${money(sum.annual_opex)}/yr`
            + `<br>Net operating contribution <b>${money(sum.annual_net_contribution)}</b>/yr`;
          bodyEl.appendChild(s);
        }
        const apply = document.createElement("button"); apply.className = "file-btn"; apply.style.marginTop = "6px";
        apply.textContent = "Apply to proforma";
        apply.onclick = async () => {
          const r = await this.api.saveSpecialty(pid, params);
          const d = r.deltas;
          const a = this.a as { cost_lines: { category: string; name: string; amount: number }[]; operations: { other_income_annual: number; opex_annual: number } };
          if (d.cost_line) {
            const ex = a.cost_lines.find((c) => c.name === d.cost_line!.name);
            if (ex) ex.amount = d.cost_line.amount; else a.cost_lines.push({ ...d.cost_line, start_month: 0, end_month: 0 } as never);
          }
          a.operations.other_income_annual = (a.operations.other_income_annual || 0) + d.other_income_annual_add;
          a.operations.opex_annual = (a.operations.opex_annual || 0) + d.opex_annual_add;
          this.render(); void this.solve();
          this.setStatus(`applied specialty assets: ${money(r.summary.capex_total)} capex, ${money(r.summary.annual_net_contribution)}/yr net`);
        };
        bodyEl.appendChild(apply);
      };
      paint(resp.summary);
    }).catch(() => { bodyEl.innerHTML = `<div class="meta">specialty assets unavailable (API offline)</div>`; });
  }

  /** Developer cost budget: line-item hard/soft/acquisition costs (description × $/unit × qty) with
   *  per-category contingency, that roll into the proforma's cost_lines. The institutional gap the
   *  flat cost drivers don't cover. */
  private renderBudget() {
    const host = document.createElement("div"); host.id = "pf-budget";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">🧱 Cost budget (hard / soft)</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to build a line-item cost budget.</div>`); this.root.appendChild(host); return; }
    const body = document.createElement("div"); host.appendChild(body); this.root.appendChild(host);
    body.innerHTML = `<div class="meta">loading…</div>`;

    const CATS: [string, string][] = [["acquisition", "Acquisition"], ["hard", "Hard costs"], ["soft", "Soft costs"]];
    void this.api.devBudget(pid).then((resp) => {
      const lines = resp.budget.lines.slice();
      const contingency: Record<string, number> = { hard: 0.1, soft: 0.1, acquisition: 0, ...resp.budget.contingency };
      let timer = 0;
      const save = () => { clearTimeout(timer); timer = window.setTimeout(() => void this.api.saveDevBudget(pid, { lines, contingency }).then(paint), 500); };
      const num = (v: string) => { const n = parseFloat(v); return isNaN(n) ? 0 : n; };

      const paint = (r?: import("../api/client").DevBudgetResponse) => {
        const sum = r?.summary;
        body.innerHTML = "";
        for (const [cat, label] of CATS) {
          const head = document.createElement("div"); head.className = "section-title"; head.style.cssText = "margin:8px 0 2px;font-size:12px";
          const subtotal = sum?.categories[cat];
          head.innerHTML = `${label} <span class="meta" style="font-weight:400">${subtotal ? "· " + money(subtotal.subtotal) + (subtotal.contingency ? " + " + money(subtotal.contingency) + " contingency" : "") : ""}</span>`;
          body.appendChild(head);
          const tbl = document.createElement("table"); tbl.className = "sens-table"; tbl.style.fontSize = "12px";
          tbl.innerHTML = `<tr><th style="text-align:left">Description</th><th>$/unit</th><th>Qty</th><th>Total</th><th></th></tr>`;
          lines.forEach((ln, i) => {
            if (ln.category !== cat) return;
            const tr = document.createElement("tr");
            const tot = (ln.unit_cost || 0) * (ln.quantity || 1);
            tr.innerHTML = `<td><input data-i="${i}" data-k="description" value="${(ln.description || "").replace(/"/g, "&quot;")}" style="width:150px"></td>`
              + `<td><input data-i="${i}" data-k="unit_cost" type="number" step="any" value="${ln.unit_cost || 0}" style="width:90px"></td>`
              + `<td><input data-i="${i}" data-k="quantity" type="number" step="any" value="${ln.quantity ?? 1}" style="width:60px"></td>`
              + `<td style="text-align:right">${money(tot)}</td><td><button class="tool-btn" data-rm="${i}" title="Remove">✕</button></td>`;
            tbl.appendChild(tr);
          });
          body.appendChild(tbl);
          const addRow = document.createElement("div"); addRow.style.cssText = "display:flex;gap:8px;align-items:center;margin:3px 0 2px";
          const add = document.createElement("button"); add.className = "tool-btn"; add.textContent = "+ line";
          add.onclick = () => { lines.push({ category: cat as "hard", description: "New line", unit_cost: 0, quantity: 1 }); save(); paint(); };
          const cw = document.createElement("label"); cw.className = "meta"; cw.style.fontSize = "11px";
          cw.innerHTML = `contingency % <input type="number" step="any" value="${+(contingency[cat] * 100).toFixed(2)}" style="width:56px">`;
          (cw.querySelector("input") as HTMLInputElement).oninput = (e) => { contingency[cat] = num((e.target as HTMLInputElement).value) / 100; save(); };
          addRow.append(add, cw); body.appendChild(addRow);
        }
        body.querySelectorAll<HTMLInputElement>("input[data-i]").forEach((inp) => {
          inp.oninput = () => {
            const i = +inp.dataset.i!, k = inp.dataset.k!;
            (lines[i] as unknown as Record<string, unknown>)[k] = k === "description" ? inp.value : num(inp.value);
            save();
            if (k !== "description") paint();   // refresh totals
          };
        });
        body.querySelectorAll<HTMLButtonElement>("button[data-rm]").forEach((b) => {
          b.onclick = () => { lines.splice(+b.dataset.rm!, 1); save(); paint(); };
        });
        const foot = document.createElement("div"); foot.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-top:8px";
        foot.innerHTML = `<b>Total uses ${money(sum?.grand_total ?? 0)}</b>`
          + `<span class="meta" style="font-size:11px">${sum ? `hard ${(sum.hard_pct * 100).toFixed(0)}% / soft ${(sum.soft_pct * 100).toFixed(0)}%` : ""}</span>`;
        const apply = document.createElement("button"); apply.className = "file-btn"; apply.textContent = "Apply to proforma";
        apply.onclick = async () => {
          const r = await this.api.devBudgetCostLines(pid);
          (this.a as { cost_lines: unknown[] }).cost_lines = r.cost_lines.map((c) => ({ ...c, start_month: 0, end_month: 0 }));
          this.render(); void this.solve();
          this.setStatus(`applied cost budget: ${money(r.summary.grand_total)} total uses`);
        };
        const fwrap = document.createElement("div"); fwrap.style.marginTop = "6px"; fwrap.append(apply);
        body.append(foot, fwrap);
      };
      paint(resp);
    }).catch(() => { body.innerHTML = `<div class="meta">cost budget unavailable (API offline)</div>`; });
  }

  /** Model → proforma: pull GFA from the project's source IFC and seed hard cost + rent from it,
   *  so the deal underwrites against the real model instead of hand-keyed numbers. */
  private renderModelLink() {
    const host = document.createElement("div"); host.id = "pf-model";
    host.style.cssText = "margin:8px 0;padding:8px 10px;border:1px dashed var(--line);border-radius:8px";
    const pid = this.projectId();
    host.innerHTML = `<div class="section-title" style="margin:0 0 6px">📐 From model</div>`;
    if (!pid) { host.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to seed the proforma from its IFC.</div>`); this.root.appendChild(host); return; }
    const btn = document.createElement("button"); btn.className = "tool-btn"; btn.textContent = "Pull model metrics";
    const body = document.createElement("div"); body.style.marginTop = "6px";
    btn.onclick = async () => {
      body.innerHTML = `<span class="meta">reading model…</span>`;
      let m;
      try { m = await this.api.proformaModelMetrics(pid); }
      catch { body.innerHTML = `<div class="meta">No source IFC yet — open an IFC in the Model workspace, then retry.</div>`; return; }
      const sf = m.net_floor_area_sf;
      body.innerHTML =
        `<div class="meta" style="margin-bottom:6px"><b>${sf.toLocaleString()} sf</b> net floor area · ${m.space_count} spaces · ${m.storey_count} storeys</div>` +
        `<div class="pf-form">` +
        `<label class="pf-field"><span>Hard cost $/sf</span><input id="pf-hard-rate" type="number" step="any" value="250"></label>` +
        `<label class="pf-field"><span>Rent $/sf·yr</span><input id="pf-rent-rate" type="number" step="any" value="36"></label>` +
        `</div><button class="file-btn" id="pf-apply-model" style="margin-top:6px">Apply to proforma</button>`;
      (body.querySelector("#pf-apply-model") as HTMLButtonElement).onclick = () => {
        const hard = parseFloat((body.querySelector("#pf-hard-rate") as HTMLInputElement).value) || 0;
        const rent = parseFloat((body.querySelector("#pf-rent-rate") as HTMLInputElement).value) || 0;
        set(this.a, "cost_lines.1.amount", Math.round(sf * hard));      // hard cost line
        set(this.a, "operations.potential_rent_annual", Math.round(sf * rent));
        this.render();                                                   // refresh the driver inputs
        void this.solve();
        this.setStatus(`seeded from model: ${sf.toLocaleString()} sf → hard ${money(sf * hard)}, rent ${money(sf * rent)}/yr`);
      };
    };
    host.append(btn, body);
    this.root.appendChild(host);
  }

  /** Actuals / draw bridge — enter actual-to-date per cost line, re-forecast IRR vs underwritten. */
  private renderDraws() {
    const host = document.createElement("div"); host.id = "pf-draws";
    const lines = this.a.cost_lines as any[];
    let html = `<div class="section-title">Actuals / Draw — re-forecast vs underwritten</div>` +
      `<table class="sens-table"><tr><th>Cost line</th><th>Budget</th><th>Actual to date</th></tr>`;
    lines.forEach((ln, i) => {
      html += `<tr><th style="text-align:left">${ln.name}</th><td>${money(ln.amount)}</td>` +
        `<td><input class="pf-actual" data-i="${i}" type="number" step="any" value="0" style="width:90px"></td></tr>`;
    });
    html += `</table><button class="file-btn" id="pf-reforecast" style="margin-top:6px">Re-forecast</button>` +
      `<div id="pf-fc-out"></div>`;
    host.innerHTML = html;
    this.root.appendChild(host);
    (host.querySelector("#pf-reforecast") as HTMLButtonElement).onclick = () => this.reforecast();
  }

  private async reforecast() {
    const inputs = [...document.querySelectorAll<HTMLInputElement>(".pf-actual")];
    const actuals = (this.a.cost_lines as any[]).map((_, i) => {
      const v = parseFloat(inputs.find((x) => +x.dataset.i! === i)?.value || "0") || 0;
      return { actual_to_date: v, committed: 0 };
    });
    this.setStatus("re-forecasting against actuals…");
    let f;
    try { f = await this.api.forecast(this.a, actuals, 9); }
    catch (e) { this.setStatus(`forecast error: ${(e as Error).message}`); return; }
    const uw = f.underwritten_returns.equity_irr, fc = f.forecast_returns.equity_irr;
    const delta = f.irr_delta == null ? "" : `${f.irr_delta >= 0 ? "+" : ""}${(f.irr_delta * 100).toFixed(1)}pp`;
    const dColor = (f.irr_delta ?? 0) >= 0 ? "#2ecc71" : "#e74c3c";
    const rows = f.lines.map((L) =>
      `<tr><th style="text-align:left">${L.name}</th><td>${money(L.budget)}</td>` +
      `<td>${money(L.actual_to_date)}</td><td>${money(L.forecast_at_completion)}</td>` +
      `<td style="color:${L.variance_to_budget > 0 ? "#e74c3c" : "#2ecc71"}">${L.variance_to_budget >= 0 ? "+" : ""}${money(L.variance_to_budget)}</td></tr>`).join("");
    document.getElementById("pf-fc-out")!.innerHTML =
      `<div class="kpi-grid" style="grid-template-columns:1fr 1fr 1fr">` +
      `<div class="kpi"><div class="kpi-v">${pct(uw)}</div><div class="kpi-l">Underwritten IRR</div></div>` +
      `<div class="kpi"><div class="kpi-v">${pct(fc)}</div><div class="kpi-l">Re-forecast IRR</div></div>` +
      `<div class="kpi"><div class="kpi-v" style="color:${dColor}">${delta}</div><div class="kpi-l">Δ IRR</div></div></div>` +
      `<table class="sens-table"><tr><th>Line</th><th>Budget</th><th>Actual</th><th>Forecast</th><th>Var</th></tr>${rows}` +
      `<tr><th style="text-align:left">TOTAL</th><td>${money(f.totals.budget)}</td><td>${money(f.totals.actual_to_date)}</td>` +
      `<td>${money(f.totals.forecast_at_completion)}</td><td style="color:${f.totals.variance_to_budget > 0 ? "#e74c3c" : "#2ecc71"}">${money(f.totals.variance_to_budget)}</td></tr></table>`;
    this.setStatus(`re-forecast IRR ${pct(fc)} (was ${pct(uw)})`);

    // bridge to the GC portal: turn this cost tree + draws into an AIA G702/G703 pay app
    const pid = this.projectId();
    if (pid) {
      const btn = document.createElement("button");
      btn.className = "file-btn"; btn.textContent = "↓ Generate G702 draw package"; btn.style.marginTop = "8px";
      btn.onclick = async () => {
        this.setStatus("generating lender draw package…");
        try {
          const actuals = [...document.querySelectorAll<HTMLInputElement>(".pf-actual")]
            .sort((a, b) => +a.dataset.i! - +b.dataset.i!)
            .map((x) => ({ actual_to_date: parseFloat(x.value) || 0 }));
          const sc = await this.api.createScenario("Draw package", pid, this.a);
          const dp = await this.api.drawPackage(sc.id, { project_id: pid, actuals, as_of_month: 9, app_no: 1 });
          this.setStatus(`SOV (${dp.sov_lines_created} lines) → G702 due $${Math.round(dp.g702.line8_current_payment_due).toLocaleString()}`);
          window.open(this.api.url(dp.g702_pdf), "_blank");
        } catch (e) { this.setStatus(`draw package error: ${(e as Error).message}`); }
      };
      document.getElementById("pf-fc-out")!.appendChild(btn);
    }
  }

  private async solve() {
    this.setStatus("solving proforma…");
    let r: ProformaResult | undefined;
    try { r = await this.api.solveProforma(this.a); }
    catch (e) { this.setStatus(`proforma error: ${(e as Error).message}`); return; }
    this.renderResult(r);
    this.setStatus(`equity IRR ${pct(r.returns.equity_irr)} · EM ${r.returns.equity_multiple}`);
    void this.renderSensitivity();
    this.renderMonteCarloPrompt();   // on-demand: a 1000-solve run shouldn't fire on every edit
  }

  /** Sticky returns bar: the headline KPIs + underwriting guardrail badges, always visible. */
  private updateReturnsBar(r: ProformaResult) {
    const bar = document.getElementById("pf-returns-bar"); if (!bar) return;
    const ret = r.returns;
    const kpi = (v: string, l: string) => `<div class="pf-rk"><b>${v}</b><span>${l}</span></div>`;
    let html = kpi(pct(ret.equity_irr), "Equity IRR") + kpi(`${ret.equity_multiple}×`, "Equity mult.")
      + kpi(pct(ret.yield_on_cost), "Yield on cost") + kpi(money(ret.npv), "NPV");
    const g = r.guardrails;
    if (g && g.flags.length) {
      const worst = g.flags.find((f) => f.level === "high") || g.flags.find((f) => f.level === "med") || g.flags[0];
      html += `<span class="pf-guard ${worst.level === "info" ? "ok" : worst.level}" title="${g.flags.map((f) => f.message).join(" · ").replace(/"/g, "'")}">`
        + `${worst.level === "info" ? "✓ within market bands" : (worst.level === "high" ? "⚠ check assumptions" : "△ review") + ` · ${worst.message.slice(0, 60)}…`}</span>`;
    }
    bar.innerHTML = html;
  }

  /** Cheap placeholder with a Run button — Monte Carlo (~1000 solves) runs only when asked,
   *  so editing assumptions stays snappy (solve + sensitivity are the live-updating views). */
  private renderMonteCarloPrompt() {
    const host = document.getElementById("pf-mc");
    if (!host) return;
    host.innerHTML = `<div class="section-title">Monte Carlo — Equity IRR risk</div>`
      + `<div class="meta">Probabilistic downside on exit cap × hard cost × rent.</div>`;
    const btn = document.createElement("button");
    btn.className = "tool-btn"; btn.textContent = "▶ Run risk simulation (1000 draws)";
    btn.style.cssText = "display:block;margin:6px 0;width:100%;text-align:left";
    btn.onclick = () => void this.renderMonteCarlo();
    host.appendChild(btn);
  }

  /** Monte Carlo risk: sample exit cap, hard cost, and rent; show the equity-IRR distribution. */
  private async renderMonteCarlo() {
    const host = document.getElementById("pf-mc");
    if (!host) return;
    host.innerHTML = `<div class="section-title">Monte Carlo — Equity IRR risk</div>`
      + `<div class="meta">running 1000 draws…</div>`;
    const cap = get(this.a, "exit.exit_cap") as number;
    const hard = get(this.a, "cost_lines.1.amount") as number;
    const rent = get(this.a, "operations.potential_rent_annual") as number;
    const target = 0.15;
    let mc;
    try {
      mc = await this.api.monteCarlo({
        assumptions: this.a,
        iterations: 1000,
        variables: [
          // exit cap & cost skew worse than base; rent is symmetric — a realistic downside tilt
          { path: "exit.exit_cap", dist: { kind: "triangular", low: cap - 0.005, mode: cap, high: cap + 0.012 } },
          { path: "cost_lines.1.amount", dist: { kind: "triangular", low: hard * 0.95, mode: hard, high: hard * 1.2 } },
          { path: "operations.potential_rent_annual", dist: { kind: "normal", mean: rent, std: rent * 0.06, min: rent * 0.8 } },
        ],
        metrics: ["returns.equity_irr"],
        targets: { "returns.equity_irr": target },
      });
    } catch { this.renderMonteCarloPrompt(); return; }
    const m = mc.metrics["returns.equity_irr"];
    if (!m || !m.n) { this.renderMonteCarloPrompt(); return; }
    const hmax = Math.max(...m.histogram.counts, 1);
    const bars = m.histogram.counts.map((c, i) => {
      const lo = m.histogram.edges[i];
      return `<span class="pf-bar" title="${(lo * 100).toFixed(1)}%: ${c}" style="height:${Math.round((c / hmax) * 48) + 1}px"></span>`;
    }).join("");
    const prob = Math.round((m.prob_at_least ?? 0) * 100);
    host.innerHTML =
      `<div class="section-title">Monte Carlo — Equity IRR (${mc.solved} draws: exit cap × hard cost × rent)</div>` +
      `<div class="kpi-grid">` +
      [["P10", pct(m.p10)], ["P50 (median)", pct(m.p50)], ["P90", pct(m.p90)], [`P(IRR ≥ ${target * 100}%)`, `${prob}%`]]
        .map(([l, v]) => `<div class="kpi"><div class="kpi-v">${v}</div><div class="kpi-l">${l}</div></div>`).join("") +
      `</div>` +
      `<div class="pf-hist" title="equity IRR distribution (P10 → P90)">${bars}</div>` +
      `<div class="meta">downside-tilted: exit cap and hard cost skew worse than base; rent ±6%.</div>`;
  }

  /** Two-variable data table: Equity IRR vs exit cap × hard cost (around the base case). */
  private async renderSensitivity() {
    const host = document.getElementById("pf-sens");
    if (!host) return;
    const baseCap = get(this.a, "exit.exit_cap") as number;
    const baseHard = get(this.a, "cost_lines.1.amount") as number;
    const xs = [-0.01, -0.005, 0, 0.005, 0.01].map((d) => +(baseCap + d).toFixed(4));
    const ys = [-0.1, -0.05, 0, 0.05, 0.1].map((d) => Math.round(baseHard * (1 + d)));
    let s;
    try {
      s = await this.api.sensitivity({
        assumptions: this.a,
        x: { path: "exit.exit_cap", values: xs },
        y: { path: "cost_lines.1.amount", values: ys },
        metric: "returns.equity_irr",
      });
    } catch { return; }
    const flat = s.matrix.flat().filter((v): v is number => v != null);
    const lo = Math.min(...flat), hi = Math.max(...flat);
    const color = (v: number | null) => {
      if (v == null) return "#333";
      const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;          // red→green
      return `hsl(${Math.round(t * 120)} 55% 32%)`;
    };
    const head = `<tr><th>IRR</th>${s.x_values.map((x) => `<th>${(x * 100).toFixed(1)}%</th>`).join("")}</tr>`;
    const rows = s.matrix.map((row, j) =>
      `<tr><th>$${(s.y_values[j] / 1e6).toFixed(1)}M</th>` +
      row.map((v) => `<td style="background:${color(v)}">${v == null ? "—" : (v * 100).toFixed(1)}</td>`).join("") +
      `</tr>`).join("");
    host.innerHTML =
      `<div class="section-title">Sensitivity — Equity IRR (exit cap × hard cost)</div>` +
      `<table class="sens-table">${head}${rows}</table>`;
  }

  private renderResult(r: ProformaResult) {
    const su = r.sources_uses, ret = r.returns, wf = r.waterfall;
    this.updateReturnsBar(r);
    const kpis: [string, string][] = [
      ["Project IRR", pct(ret.project_irr)], ["Equity IRR", pct(ret.equity_irr)],
      ["Equity Mult.", `${ret.equity_multiple}×`], ["NPV", money(ret.npv)],
      ["Yield on Cost", pct(ret.yield_on_cost)], ["Dev Spread", `${Math.round(ret.dev_spread * 1e4)} bps`],
    ];
    const out = document.getElementById("pf-out")!;
    out.innerHTML =
      `<div class="kpi-grid">` +
      kpis.map(([l, v]) => `<div class="kpi"><div class="kpi-v">${v}</div><div class="kpi-l">${l}</div></div>`).join("") +
      `</div>` +
      `<div class="section-title">Sources & Uses</div>` +
      `<div class="portal-kv">` +
      `<div class="k">Total uses</div><div class="v">${money(su.total_uses)}</div>` +
      `<div class="k">Senior loan (${pct(su.effective_ltc ?? su.ltc)} LTC)</div><div class="v">${money(su.loan_amount)}</div>` +
      this.sizingRow(r) +
      `<div class="k">Interest reserve</div><div class="v">${money(su.interest_reserve)}</div>` +
      `<div class="k">Equity</div><div class="v">${money(su.equity)}</div>` +
      `<div class="k">LP / GP</div><div class="v">${money(su.lp_contribution)} / ${money(su.gp_contribution)}</div>` +
      `</div>` +
      `<div class="section-title">JV Waterfall (${wf.style})</div>` +
      `<div class="portal-kv">` +
      `<div class="k">LP</div><div class="v">IRR ${pct(wf.lp_irr)} · ${wf.lp_equity_multiple}× · ${money(wf.lp_distributions)}</div>` +
      `<div class="k">GP</div><div class="v">IRR ${pct(wf.gp_irr)} · ${wf.gp_equity_multiple}× · ${money(wf.gp_distributions)}</div>` +
      `</div>` +
      this.cashflowChart(r.cash_flow.equity);
  }

  /** "Loan sizing" row: which constraint bound the loan + the resulting DSCR/LTV. */
  private sizingRow(r: ProformaResult): string {
    const ds = r.debt_sizing;
    if (!ds) return "";
    const label: Record<string, string> = { ltc: "LTC", ltv: "LTV", dscr: "DSCR", debt_yield: "Debt yield" };
    const metrics = [
      ds.actual_dscr != null ? `DSCR ${ds.actual_dscr.toFixed(2)}×` : "",
      ds.actual_ltv != null ? `LTV ${(ds.actual_ltv * 100).toFixed(0)}%` : "",
      ds.actual_debt_yield != null ? `DY ${(ds.actual_debt_yield * 100).toFixed(1)}%` : "",
    ].filter(Boolean).join(" · ");
    const bound = ds.binding_constraint === "ltc" ? "" : ` <span class="meta">(binds)</span>`;
    return `<div class="k">Loan sizing</div><div class="v">${label[ds.binding_constraint] ?? ds.binding_constraint}${bound} — ${metrics}</div>`;
  }

  /** inline SVG bar chart of equity cash flow (outflows during construction, inflows in ops). */
  private cashflowChart(cf: number[]): string {
    const w = 252, h = 70, pad = 4;
    const max = Math.max(1, ...cf.map((v) => Math.abs(v)));
    const bw = (w - 2 * pad) / cf.length;
    const mid = h / 2;
    const bars = cf.map((v, i) => {
      const bh = (Math.abs(v) / max) * (mid - pad);
      const x = pad + i * bw;
      const y = v >= 0 ? mid - bh : mid;
      const col = v >= 0 ? "#2ecc71" : "#e74c3c";
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(bw - 0.5, 1).toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}"/>`;
    }).join("");
    return `<div class="section-title">Equity cash flow</div>` +
      `<svg viewBox="0 0 ${w} ${h}" style="width:100%;background:#1e1f22;border:1px solid var(--line);border-radius:4px">` +
      `<line x1="${pad}" y1="${mid}" x2="${w - pad}" y2="${mid}" stroke="#444" stroke-width="0.5"/>${bars}</svg>`;
  }
}
