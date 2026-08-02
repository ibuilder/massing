/** The "Generate from zoning" feasibility tab — extracted from the ProformaUI god class along its
 *  LCOM4 seam (Repowise health 1.65). The tab talks back to the coordinator only through
 *  `MassingTabCtx`; behavior is pinned by proforma.render.test.ts, which moved here with it. */
import type { ApiClient, MassingParams, MassingResult } from "../api/client";
import { escapeHtml } from "../ui/feedback";

import { money, pct } from "./format";

export interface MassingTabCtx {
  api: ApiClient;
  projectId: () => string | null;
  setStatus: (m: string) => void;
  /** Adopt the generated acquisition assumptions as the live proforma and re-render/solve. */
  adoptAssumptions: (assumptions: unknown) => void;
}

export function renderMassingTab(root: HTMLElement, ctx: MassingTabCtx): void {
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

  // shape: box (zoning massing) or a monolithic / earth dome (hemisphere by radius)
  const domeWrap = document.createElement("label");
  domeWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
  const domeChk = document.createElement("input"); domeChk.type = "checkbox";
  const domeR = document.createElement("input"); domeR.type = "number"; domeR.step = "0.5"; domeR.value = "8";
  domeR.style.cssText = "width:60px"; domeR.title = "Dome radius (m)";
  domeWrap.append(domeChk, document.createTextNode("Earth / monolithic dome (hemisphere, radius m:"), domeR, document.createTextNode(")"));
  host.appendChild(domeWrap);

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
  const pkWrap = document.createElement("label");
  pkWrap.style.cssText = "display:flex;align-items:center;gap:6px;margin:4px 0;font-size:13px";
  const pkInput = document.createElement("input");
  pkInput.type = "number"; pkInput.min = "0"; pkInput.max = "2000"; pkInput.value = "0"; pkInput.style.width = "70px";
  pkWrap.append(document.createTextNode("Surface parking stalls (real IfcSpaces)"), pkInput);
  host.appendChild(pkWrap);

  const params = (): MassingParams => {
    const p: MassingParams = { use_type: useSel.value as "residential" | "commercial", name: "Massing Study" };
    for (const [, key] of fields) {
      const inp = inputs[key]; if (!inp) continue;
      const v = parseFloat(inp.value);
      if (key === "height_limit") { p.height_limit = isNaN(v) || v <= 0 ? null : v; }
      else if (!isNaN(v)) (p as Record<string, unknown>)[key] = v;
    }
    p.frame = frameChk.checked;
    p.units = unitChk.checked;
    p.envelope = envChk.checked;
    p.core = coreChk.checked;
    if (corrChk.checked) { p.units = true; p.unit_layout = "corridor"; }
    const pk = parseInt(pkInput.value, 10); if (pk > 0) p.parking = pk;
    if (domeChk.checked) { p.shape = "dome"; p.dome_radius = parseFloat(domeR.value) || 8; }
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
      (r.proforma.solve_error ? `<div class="meta" style="color:var(--status-crit)">proforma: ${r.proforma.solve_error}</div>` : "") +
      (m.structure ? `<div class="meta">🏛 Structure: <b>${m.structure.system}</b> · ${m.structure.lateral_system}` +
            ((m.structure.base_column_mm && m.structure.top_column_mm && m.structure.top_column_mm < m.structure.base_column_mm)
              ? ` · cols taper ${m.structure.base_column_mm}→${m.structure.top_column_mm} mm (base→top)`
              : ` · cols ${m.structure.members_mm.column} mm`) +
            (m.structure.lateral_core?.provided
              ? ` · ${m.structure.lateral_core.plan_w_m}×${m.structure.lateral_core.plan_d_m} m core, ${m.structure.lateral_core.wall_mm} mm walls` : "") +
            `</div>` : "") +
      (generated ? `<div class="meta" style="color:var(--accent)">✓ IFC model generated & publishing — open the Model workspace to view.</div>` : "");
  };

  const btnRow = document.createElement("div"); btnRow.style.cssText = "display:flex;gap:6px;margin-top:6px";
  const estBtn = document.createElement("button"); estBtn.className = "tool-btn"; estBtn.textContent = "Estimate yield";
  estBtn.onclick = async () => {
    out.innerHTML = `<span class="meta">computing…</span>`;
    try { showResult(await ctx.api.previewMassing(params()), false); }
    catch (e) { out.innerHTML = `<div class="meta" style="color:var(--status-crit)">${escapeHtml((e as Error).message)}</div>`; }
  };
  const genBtn = document.createElement("button"); genBtn.className = "file-btn"; genBtn.textContent = "Generate IFC model + apply";
  genBtn.onclick = async () => {
    const pid = ctx.projectId();
    if (!pid) { out.innerHTML = `<div class="meta">Open or create a project first (＋ New), then generate its model.</div>`; return; }
    out.innerHTML = `<span class="meta">generating model + proforma…</span>`;
    try {
      const r = await ctx.api.generateMassing(pid, params());
      showResult(r, true);
      // adopt the generated acquisition assumptions as the live proforma
      ctx.adoptAssumptions(r.proforma.assumptions);
      ctx.setStatus(`generated ${r.metrics.floors}-floor massing (${r.metrics.buildable_gfa_sf.toLocaleString()} sf) → proforma seeded`);
    } catch (e) { out.innerHTML = `<div class="meta" style="color:var(--status-crit)">${escapeHtml((e as Error).message)}</div>`; }
  };
  btnRow.append(estBtn, genBtn); host.append(btnRow, out);
  root.appendChild(host);
}
