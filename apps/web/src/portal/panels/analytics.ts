import { esc, money as cmoney } from "../../ui/charts";
import { noProjectHtml } from "../../ui/empty";
import { toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";
import { renderPlanningBrief } from "./planningBrief";

/**
 * Analytics & benchmarking panels (cross-project benchmarks, subcontractor risk & cost).
 * Extracted from portal.ts as free render*(ctx) functions (portal.ts decomposition).
 */

  // --- Benchmarks: cross-project cost distribution + response rates ------------------------------
export async function renderBenchmarks(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("📈 Benchmarks", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    root.appendChild(await renderPlanningBrief(ctx));
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Your own history across every project: what things actually cost (per cost code) and "
      + "how fast RFIs/submittals turn around. Sanity-check a new estimate or hold the team accountable.";
    root.appendChild(intro);
    const rr = el("div"); const costs = el("div"); costs.style.marginTop = "10px";
    root.append(rr, costs);
    rr.textContent = "loading…"; costs.textContent = "";
    try {
      const resp = await ctx.host.api.benchmarkResponseRates();
      rr.innerHTML = "";
      const card = (title: string, m: { total: number; open: number; avg_turnaround_days: number | null; overdue: number; overdue_pct: number }) => {
        const c = el("div", "kpi-card"); c.style.cssText = "display:inline-block;margin:4px 8px 4px 0;padding:8px 12px;border:1px solid var(--line);border-radius:8px";
        c.innerHTML = `<div class="meta"><b>${title}</b></div>`
          + `<div style="font-size:12px">${m.total} total · ${m.open} open · ${m.overdue} overdue (${m.overdue_pct}%)`
          + ` · avg turnaround ${m.avg_turnaround_days ?? "—"} d</div>`;
        return c;
      };
      rr.append(card("RFIs", resp.rfi), card("Submittals", resp.submittal));
    } catch (e) { rr.textContent = `response rates failed: ${(e as Error).message}`; }
    try {
      const cb = await ctx.host.api.benchmarkCosts();
      if (!cb.cost_codes.length) { costs.innerHTML = `<div class="meta">${cb.message || "No cost history yet."}</div>`; }
      else {
        const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px";
        tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Cost code</th><th scope="col">n</th><th scope="col">low</th><th scope="col">p25</th>`
          + `<th scope="col">median</th><th scope="col">p75</th><th scope="col">high</th></tr></thead><tbody>`
          + cb.cost_codes.map((c) => `<tr><td>${c.cost_code}</td><td style="text-align:center">${c.samples}</td>`
            + `<td style="text-align:right">${cmoney(c.low)}</td><td style="text-align:right">${cmoney(c.p25)}</td>`
            + `<td style="text-align:right"><b>${cmoney(c.median)}</b></td><td style="text-align:right">${cmoney(c.p75)}</td>`
            + `<td style="text-align:right">${cmoney(c.high)}</td></tr>`).join("") + `</tbody>`;
        const h = el("div", "meta"); h.style.margin = "10px 0 4px"; h.innerHTML = `<b>Actual cost by code</b> (${cb.code_count} codes, ≥${cb.min_samples} samples each)`;
        costs.append(h, tbl);
      }
    } catch (e) { costs.textContent = `cost benchmarks failed: ${(e as Error).message}`; }
  }

  // --- Market Intelligence: regional escalation / labour / location + warm-cold sectors ----------
export async function renderMarket(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(ctx.bar("📈 Market Intelligence", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const pid = ctx.host.projectId();
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.innerHTML = "Regional cost escalation, labour rates and a location index, plus the two-speed "
      + "<b>warm/cold</b> demand signal by sector — so an estimate is escalated to the <b>midpoint of "
      + "construction</b> in the region where it will actually be built. Set a project's assumptions under "
      + "Finance → <b>Market Assumptions</b> (region · sector · construction start · duration).";
    root.appendChild(intro);
    const tempTone = (t: string) => t === "hot" ? "var(--status-crit)" : t === "warm" ? "var(--status-warn)"
      : t === "cold" ? "var(--muted)" : "var(--status-good)";
    const editBtn = el("button", "tool-btn"); editBtn.textContent = "✎ Market assumptions";
    editBtn.title = "Set this project's region / sector / construction timeline"; editBtn.style.marginBottom = "8px";
    editBtn.onclick = () => { const m = ctx.mods.find((x) => x.key === "market_assumption"); if (m) { ctx.activeKey = "market_assumption"; void ctx.openModule(m); ctx.buildNav(); } };
    root.appendChild(editBtn);

    // per-project market context (region economics + sector temp + escalation factor to midpoint)
    if (pid) {
      const ctxSlot = el("div", "dash-card"); ctxSlot.style.marginBottom = "8px"; ctxSlot.textContent = "loading project context…";
      root.appendChild(ctxSlot);
      ctx.host.api.marketContext(pid).then((c) => {
        const r = c.region; const s = c.sector;
        ctxSlot.innerHTML = `<b>This project</b> ${c.from_assumption ? "" : `<span class="meta">(defaults — no Market Assumption yet)</span>`}`
          + `<div class="meta" style="margin-top:2px"><b>${r.label}</b> · escalation ${r.escalation_pct}%/yr · `
          + `labour $${r.labour_usd_hr}/hr · location index ${r.location_index}</div>`
          + `<div class="meta">Sector <b>${s.sector}</b> — <span style="color:${tempTone(s.temperature)}">${s.temperature}</span>: ${s.note}</div>`
          + `<div class="meta">Escalation factor <b>${c.escalation_factor}×</b> to ${c.midpoint_year} (${c.escalation_basis})</div>`;
      }).catch((e) => { ctxSlot.textContent = `context failed: ${(e as Error).message}`; });

      // escalation calculator
      const calc = el("div", "dash-card"); calc.style.marginBottom = "8px";
      calc.innerHTML = `<b>Escalate a base cost</b> <span class="meta">to the construction midpoint</span>`;
      const row = el("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:4px";
      const amt = el("input", "portal-filter") as HTMLInputElement; amt.type = "number"; amt.placeholder = "base amount ($)";
      amt.setAttribute("aria-label", "Base amount USD"); amt.style.width = "150px";
      const go = el("button", "file-btn") as HTMLButtonElement; go.textContent = "Escalate";
      const out = el("span", "meta"); out.style.marginLeft = "8px";
      go.onclick = async () => {
        const a = Number(amt.value); if (!a) { out.textContent = "enter an amount"; return; }
        out.textContent = "…";
        try {
          const r = await ctx.host.api.marketEscalate(pid, a);
          out.innerHTML = `<b>${cmoney(r.escalated_amount)}</b> at ${r.midpoint_year} `
            + `(×${r.escalation_factor} · ${r.annual_rate_pct}%/yr · ${r.escalation_basis})`;
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      row.append(amt, go, out); calc.append(row); root.appendChild(calc);
    }

    // the market table (regions + sector board), shared across projects
    const snap = el("div"); snap.textContent = "loading market table…"; root.appendChild(snap);
    ctx.host.api.marketSnapshot().then((m) => {
      snap.innerHTML = "";
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-bottom:8px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Region</th><th scope="col">Escalation %/yr</th>`
        + `<th scope="col">Labour $/hr</th><th scope="col">Location index</th></tr></thead><tbody>`
        + m.regions.map((r) => `<tr><td>${r.label}</td><td style="text-align:center">${r.escalation_pct}</td>`
          + `<td style="text-align:right">$${r.labour_usd_hr}</td><td style="text-align:center">${r.location_index}</td></tr>`).join("")
        + `</tbody>`;
      snap.append(t);
      const sig = el("div", "dash-card"); sig.style.marginBottom = "8px";
      const chips = (list: string[], t2: string) => list.map((s) => `<span class="badge" style="background:${tempTone(t2)};color:#fff;margin:2px">${s}</span>`).join("");
      sig.innerHTML = `<b>Two-speed market</b> <span class="meta">${m.market_signal.headline}</span>`
        + `<div style="margin-top:4px">Warm/hot: ${chips(m.market_signal.warm_or_hot, "warm")}</div>`
        + `<div style="margin-top:4px">Cold: ${chips(m.market_signal.cold, "cold")}</div>`;
      snap.append(sig);
      const src = el("div", "meta"); src.style.fontSize = "11px"; src.textContent = m.source; snap.append(src);
    }).catch((e) => { snap.textContent = `market table failed: ${(e as Error).message}`; });
  }

  // --- Risk & Cost: prequal, COI, lien exposure, carbon, pricing, accounting export -------------
/**
 * A unit price, to the cent.
 *
 * NEITHER SHARED MONEY HELPER CAN EXPRESS ONE: `money` is compact (4.25 -> "$4") and `usd` rounds to
 * whole dollars (4.25 -> "$4"). A supplier comparison built on either renders 4.25 and 4.10
 * IDENTICALLY — a price grid whose prices cannot be compared, with the low-price highlight left as
 * the only thing telling them apart. Found by opening the panel and reading it; every unit test
 * passed on the broken output, because none asserted a rendered number.
 *
 * The price LEDGER card had the same defect and nobody had ever seen it: it was unreachable until
 * quote leveling started writing observations, so it had only ever rendered its empty state.
 *
 * Local to this file rather than a new shared export — cents are load-bearing in a procurement
 * comparison specifically, and promoting a formatter app-wide on the strength of one screen is how
 * the eighteen near-duplicate money helpers documented in `ui/charts.ts` got started.
 */
const cents = (n: number): string =>
  (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString(undefined,
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** One supplier's quote, in exactly the shape `POST /procurement/level-quotes` expects. */
export interface ParsedQuote {
  supplier: string;
  lines: { item: string; qty: number; unit: string; unit_price: number }[];
}

/**
 * Pasted text -> the leveling engine's input shape.
 *
 * Exported and tested directly rather than through the rendered panel, for the reason
 * `budget.test.ts` sets out: asserting on HTML proves two strings are spelled differently, not that
 * the right one is produced for a given input. The mapping is the part that can be wrong — the
 * column order a buyer pastes is `item, qty, unit, unit price`, and `procurement.level_quotes`
 * reads `{item, qty, unit, unit_price}`, so a silent transposition here would price the job off the
 * wrong column and still render a confident grid.
 *
 * A line with fewer than four comma-separated cells starts a new supplier; anything else is a
 * priced line belonging to the supplier above it.
 */
export function parseQuoteText(text: string): ParsedQuote[] {
  const quotes: ParsedQuote[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const cells = line.split(",").map((c) => c.trim());
    if (cells.length < 4) { quotes.push({ supplier: line, lines: [] }); continue; }
    if (!quotes.length) quotes.push({ supplier: "Supplier 1", lines: [] });
    // `noUncheckedIndexedAccess` is on, so every cell is `string | undefined` even after the length
    // check — defaulted rather than asserted, because a `!` here would be a claim about text a user
    // pasted.
    // THE COMMA IS BOTH THE DELIMITER AND A THOUSANDS SEPARATOR, so a pasted `$1,250.00` arrives
    // as TWO cells and a naive `cells[3]` reads it as $1. That is not a parse error anyone would
    // see — it renders a confident, well-formatted grid off a price 1000x wrong, which is the exact
    // failure shape this file's neighbours keep documenting. So the price is everything from the
    // fourth cell onward, rejoined; only `item` is assumed comma-free.
    const [item = "", qty = "", unit = ""] = cells;
    const price = cells.slice(3).join(",");
    const target = quotes[quotes.length - 1];
    if (!target || !item) continue;
    target.lines.push({
      item, unit, qty: Number(qty) || 0, unit_price: Number(price.replace(/[$,]/g, "")) || 0,
    });
  }
  // A supplier header with no priced lines under it is not a quote.
  return quotes.filter((q) => q.lines.length);
}

export async function renderRiskCost(ctx: PanelContext) {
    const root = ctx.root; root.innerHTML = "";
    const pid = ctx.host.projectId();
    if (!pid) { root.innerHTML = noProjectHtml("Risk & Cost"); return; }
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    const api = ctx.host.api;
    root.appendChild(ctx.bar("🛡 Risk & Cost", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
    const tone = (band: string) => band === "high" ? "var(--status-crit)" : band === "medium" ? "var(--status-warn)" : "var(--status-good)";
    const section = (title: string) => { const h = el("div", "meta"); h.style.cssText = "margin:12px 0 4px;font-weight:600"; h.textContent = title; root.appendChild(h); return h; };
    const slot = () => { const d = el("div"); d.textContent = "loading…"; root.appendChild(d); return d; };

    section("Subcontractor prequalification (Q-score, worst first)");
    const pqSlot = slot();
    section("Insurance (COI) expiry");
    const coiSlot = slot();
    section("Procurement compliance gate (can bid / can bill)");
    const gateSlot = slot();
    section("Lien exposure (paid without an unconditional waiver)");
    const lienSlot = slot();
    section("Embodied carbon");
    const carbonSlot = slot();
    section("Carbon compliance — per-element A1–A3 · Buy Clean · LEED inventory");
    const carbonCompSlot = slot();
    section("Permit-submission readiness");
    const permitSlot = slot();
    section("Takeoff pricing vs estimate");
    const priceSlot = slot();
    section("Model classification (improve QTO + carbon)");
    const classifySlot = slot();
    section("Cost assemblies (unit-rate build-ups)");
    const asmWrap = el("div");
    root.appendChild(asmWrap);
    void api.estimateAssemblies().then((r) => {
      asmWrap.innerHTML = "";
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:11px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Assembly</th><th scope="col">CSI</th>`
        + `<th scope="col">Unit</th><th scope="col">Rate</th><th scope="col">Qty</th><th scope="col">Total</th></tr></thead><tbody>`;
      const tb = el("tbody");
      for (const a of r.assemblies) {
        const tr = el("tr");
        tr.innerHTML = `<td>${esc(a.name)}</td><td style="text-align:center">${esc(a.csi || "")}</td>`
          + `<td style="text-align:center">${esc(a.unit)}</td><td style="text-align:right">${cmoney(a.unit_rate)}/${esc(a.unit)}</td>`;
        const qtd = el("td"); const qi = el("input", "portal-filter") as HTMLInputElement;
        qi.type = "number"; qi.min = "0"; qi.placeholder = "qty"; qi.style.cssText = "width:64px;font-size:11px;text-align:right";
        qtd.appendChild(qi); tr.appendChild(qtd);
        const totd = el("td"); totd.style.textAlign = "right"; totd.className = "meta"; tr.appendChild(totd);
        qi.oninput = async () => {
          const q = Number(qi.value); if (!q) { totd.textContent = ""; return; }
          try { const p = await api.estimateAssemblyPrice({ assembly_id: a.id, quantity: q }); totd.textContent = cmoney(p.total || 0); }
          catch { totd.textContent = "—"; }
        };
        tb.appendChild(tr);
      }
      t.appendChild(tb); const w = el("div"); w.style.overflowX = "auto"; w.appendChild(t);
      asmWrap.appendChild(w);
      asmWrap.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:4px">Each rate is built up from labour + material + equipment components (auditable, re-costs when a wage/price moves). Enter a take-off quantity for a line total.</div>`);
    }).catch(() => { asmWrap.innerHTML = `<div class="meta">assemblies unavailable</div>`; });
    section("Conceptual estimate (parametric $/SF)");
    const ceWrap = el("div");
    root.appendChild(ceWrap);
    section("Materials 3-way match (PO ↔ delivery ↔ invoice)");
    const rfqNote = el("div", "meta");
    rfqNote.textContent = "checking RFQ dispatch…";
    root.appendChild(rfqNote);
    void api.rfqStatus().then((st) => { rfqNote.textContent = st.message; })
      .catch(() => { rfqNote.remove(); });
    const matchSlot = slot();
    section("Level material quotes (competing suppliers)");
    const quoteLevelWrap = el("div");
    root.appendChild(quoteLevelWrap);
    section("Price ledger (observed material prices)");
    const priceLedgerSlot = slot();
    section("Material requests from the model (QTO)");
    const mrWrap = el("div");
    root.appendChild(mrWrap);
    section("Accounting export");
    const acct = el("div");
    const glBtn = el("a", "file-btn") as HTMLAnchorElement; glBtn.textContent = "⬇ GL (CSV)";
    glBtn.href = api.accountingGlCsvUrl(pid); glBtn.style.marginRight = "8px";
    const iifBtn = el("a", "file-btn") as HTMLAnchorElement; iifBtn.textContent = "⬇ QuickBooks bills (IIF)";
    iifBtn.href = api.accountingIifUrl(pid);
    acct.append(glBtn, iifBtn); root.appendChild(acct);

    api.prequalScores(pid).then((r) => {
      pqSlot.innerHTML = "";
      if (!r.count) { pqSlot.innerHTML = `<div class="meta">No prequalification records yet.</div>`; return; }
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Company</th><th scope="col">Trade</th><th scope="col">Score</th><th scope="col" style="text-align:left">Flags</th></tr></thead><tbody>`
        + r.subs.map((s) => `<tr><td>${s.company || ""}</td><td style="text-align:center">${s.trade || ""}</td>`
          + `<td style="text-align:center;color:${tone(s.risk_band)}"><b>${s.score}</b> ${s.risk_band}</td>`
          + `<td>${(s.flags || []).join("; ")}</td></tr>`).join("") + `</tbody>`;
      pqSlot.append(t);
    }).catch((e) => { pqSlot.textContent = `failed: ${(e as Error).message}`; });

    api.coiExpiry(pid).then((r) => {
      coiSlot.innerHTML = `<div class="meta">${r.expired_count} expired · ${r.expiring_count} expiring ≤30d</div>`;
      const rows = [...r.expired.map((x) => ({ ...x, k: "EXPIRED" })), ...r.expiring_soon.map((x) => ({ ...x, k: "soon" }))];
      if (rows.length) {
        const ul = el("ul"); ul.style.cssText = "margin:4px 0 0 16px;font-size:12px";
        rows.forEach((x) => { const li = el("li");
          li.innerHTML = `<span style="color:${x.k === "EXPIRED" ? "var(--status-crit)" : "var(--status-warn)"}">${x.k}</span> `
            + `${x.vendor || ""} — ${x.coverage_type || ""} exp ${x.expires} (${x.days}d)`; ul.append(li); });
        coiSlot.append(ul);
      }
    }).catch((e) => { coiSlot.textContent = `failed: ${(e as Error).message}`; });

    api.procurementComplianceFeed(pid).then((r) => {
      gateSlot.innerHTML = `<div class="meta">${r.vendors_flagged} vendor(s) need a compliance nudge before they can bid or bill.</div>`;
      if (r.vendors.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Vendor</th><th scope="col" style="text-align:left">Issues</th>`
          + `<th scope="col">Bid</th><th scope="col">Bill</th></tr></thead><tbody>`
          + r.vendors.map((v) => `<tr><td>${v.vendor}</td><td>${v.issues.map((i) => `<span style="color:var(--status-warn)">${i}</span>`).join("; ")}</td>`
            + `<td style="text-align:center">${v.can_bid ? "✅" : "⛔"}</td>`
            + `<td style="text-align:center">${v.can_bill ? "✅" : "⛔"}</td></tr>`).join("") + `</tbody>`;
        gateSlot.append(t);
      } else {
        gateSlot.insertAdjacentHTML("beforeend", `<div class="meta">✅ All vendors clear on insurance + prequalification.</div>`);
      }
    }).catch((e) => { gateSlot.textContent = `failed: ${(e as Error).message}`; });

    api.lienExposure(pid).then((r) => {
      lienSlot.innerHTML = `<div class="meta">Total exposure <b style="color:${r.total_lien_exposure > 0 ? "var(--status-crit)" : "var(--status-good)"}">${cmoney(r.total_lien_exposure)}</b>`
        + (r.vendors_at_risk.length ? ` · at risk: ${r.vendors_at_risk.join(", ")}` : "") + `</div>`;
      const risky = r.vendors.filter((v) => v.exposure > 0);
      if (risky.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Vendor</th><th scope="col">Paid</th><th scope="col">Unconditional waived</th><th scope="col">Exposure</th></tr></thead><tbody>`
          + risky.map((v) => `<tr><td>${v.vendor}</td><td style="text-align:right">${cmoney(v.paid)}</td>`
            + `<td style="text-align:right">${cmoney(v.waived_unconditional)}</td>`
            + `<td style="text-align:right;color:var(--status-crit)">${cmoney(v.exposure)}</td></tr>`).join("") + `</tbody>`;
        lienSlot.append(t);
      }
    }).catch((e) => { lienSlot.textContent = `failed: ${(e as Error).message}`; });

    api.projectCarbon(pid).then((r) => {
      if (!r.line_count) { carbonSlot.innerHTML = `<div class="meta">${r.message || "No material quantities."}</div>`; return; }
      const mats = Object.entries(r.by_material).slice(0, 6).map(([m, v]) => `${m}: ${(v / 1000).toFixed(1)} t`).join(" · ");
      carbonSlot.innerHTML = `<div><b>${r.total_tco2e.toLocaleString()} tCO₂e</b> embodied (A1-A3)`
        + (r.unmatched ? ` · ${r.unmatched} line(s) unmatched` : "") + `</div><div class="meta">${mats}</div>`;
    }).catch((e) => { carbonSlot.textContent = `failed: ${(e as Error).message}`; });

    api.carbonComplianceReport(pid).then((r) => {
      const e = r.elements;
      const bc = r.buy_clean;
      carbonCompSlot.innerHTML = `<div><b>${e.total_tco2e.toLocaleString()} tCO₂e</b> A1–A3 from the model `
        + `(${e.carbon_matched}/${e.with_quantity} elements matched · ${e.coverage_pct}% coverage`
        + (e.intensity_kgco2e_m2 != null ? ` · ${e.intensity_kgco2e_m2} kg/m²` : "") + `)</div>`
        + `<div class="meta" style="margin-top:2px">Buy Clean: `
        + `<b style="color:var(--status-good)">${bc.passing} pass</b> · `
        + `<b style="color:${bc.failing ? "var(--status-crit)" : "var(--status-good)"}">${bc.failing} need an EPD</b></div>`;
      if (bc.rows.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Category</th><th scope="col">Factor</th>`
          + `<th scope="col">Limit</th><th scope="col">Headroom</th><th scope="col" style="text-align:left">Action</th></tr></thead><tbody>`
          + bc.rows.map((x) => `<tr><td>${x.category}</td>`
            + `<td style="text-align:center">${x.achieved_factor} /${x.unit}</td>`
            + `<td style="text-align:center">${x.limit}</td>`
            + `<td style="text-align:center;color:${x.pass ? "var(--status-good)" : "var(--status-crit)"}">${x.headroom_pct}%</td>`
            + `<td class="meta">${x.action || "✅ within the program limit"}</td></tr>`).join("") + `</tbody>`;
        carbonCompSlot.append(t);
      }
      if (e.hotspots?.length) {
        const tops = e.hotspots.slice(0, 3).map((h) => `${h.name || h.guid} (${h.category}, ${(h.kgco2e / 1000).toFixed(1)} t)`).join(" · ");
        carbonCompSlot.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:2px">Hotspots: ${tops}</div>`);
      }
    }).catch(() => { carbonCompSlot.innerHTML = `<div class="meta">Load a model in the Model workspace to compute per-element carbon.</div>`; });

    api.permitReadiness(pid).then((r) => {
      const good = r.verdict === "READY";
      permitSlot.innerHTML = `<div><b style="color:${good ? "var(--status-good)" : "var(--status-warn)"}">${r.verdict}</b>`
        + ` · readiness ${r.readiness_pct}% · approvability ${Math.round(r.approvability_score)}%</div>`;
      if (r.deficiencies.length) {
        const ul = el("ul"); ul.style.cssText = "margin:4px 0 0 16px;font-size:12px";
        for (const d of r.deficiencies.slice(0, 6)) {
          const li = el("li");
          const col = d.severity === "critical" ? "var(--status-crit)" : d.severity === "major" ? "var(--status-warn)" : "var(--muted)";
          li.innerHTML = `<span style="color:${col}">${d.severity}</span> ${d.item} — <span class="meta">${d.action}</span>`;
          ul.append(li);
        }
        permitSlot.append(ul);
      } else {
        permitSlot.insertAdjacentHTML("beforeend", `<div class="meta">✅ No deficiencies — the intake checklist is clear.</div>`);
      }
    }).catch(() => { permitSlot.innerHTML = `<div class="meta">Load a model to run the permit-submission pre-check (egress + approvability + sheet series).</div>`; });

    api.pricingReconcile(pid).then((r) => {
      if (!r.matched) { priceSlot.innerHTML = `<div class="meta">No priced quantities (${r.pricing_source}).</div>`; return; }
      const v = r.variance_total;
      priceSlot.innerHTML = `<div>Priced <b>${cmoney(r.priced_total)}</b> (${r.pricing_source})`
        + (v != null ? ` vs estimate ${cmoney(r.estimated_total)} — variance <b style="color:${v > 0 ? "var(--status-warn)" : "var(--status-good)"}">${cmoney(v)}</b>` : "")
        + `</div>`;
    }).catch((e) => { priceSlot.textContent = `failed: ${(e as Error).message}`; });

    api.ifcClassify(pid).then((r) => {
      if (!r.count) { classifySlot.innerHTML = `<div class="meta">${r.message || "No reclassification suggestions (load a model in the Model workspace)."}</div>`; return; }
      const tops = Object.entries(r.by_target_class).slice(0, 5).map(([c, n]) => `${c}: ${n}`).join(" · ");
      classifySlot.innerHTML = `<div><b>${r.count}</b> element(s) suggested for reclassification`
        + (r.generic_elements ? ` (${r.generic_elements} generic/proxy)` : "") + `</div><div class="meta">${tops}</div>`;
    }).catch((e) => { classifySlot.textContent = `failed: ${(e as Error).message}`; });

    // conceptual estimate mini-form (developer-side $/SF from building params)
    void api.conceptualCatalog().then((cat) => {
      ceWrap.innerHTML = "";
      const type = el("select", "portal-filter") as HTMLSelectElement; type.style.cssText = "margin:2px 4px 2px 0";
      type.setAttribute("aria-label", "Building type");
      type.innerHTML = cat.building_types.map((t) => `<option value="${t}">${t}</option>`).join("");
      const region = el("select", "portal-filter") as HTMLSelectElement; region.style.cssText = "margin:2px 4px";
      region.setAttribute("aria-label", "Region");
      region.innerHTML = cat.regions.map((rg) => `<option value="${rg}"${rg === "us_average" ? " selected" : ""}>${rg}</option>`).join("");
      const gfa = el("input", "portal-filter") as HTMLInputElement; gfa.type = "number"; gfa.placeholder = "GFA (sf)"; gfa.setAttribute("aria-label", "Gross floor area (sf)"); gfa.style.cssText = "width:110px;margin:2px 4px";
      const go = el("button", "file-btn") as HTMLButtonElement; go.textContent = "Estimate";
      const out = el("div"); out.style.marginTop = "6px";
      go.onclick = async () => {
        if (!Number(gfa.value)) { toast("Enter GFA", "error"); return; }
        out.textContent = "estimating…";
        try {
          const r = await api.conceptualEstimate(pid, { building_type: type.value, region: region.value, gfa_sf: Number(gfa.value) });
          if (r.error) { out.textContent = r.error; return; }
          out.innerHTML = `<div><b>${cmoney(r.total_cost)}</b> total (${cmoney(r.range.low)}–${cmoney(r.range.high)}) `
            + `· ${cmoney(r.metrics.total_per_sf ?? 0)}/sf · hard ${cmoney(r.hard_cost)} + soft ${cmoney(r.soft_cost)}</div>`;
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      ceWrap.append(type, region, gfa, go, out);

      // GEN-SCORE: massing-option comparison — generate FAR variants of a zoning envelope and rank
      // them through cost ($/SF) + embodied carbon + yield + FAR/height compliance in one pass.
      const optRow = el("div"); optRow.style.cssText = "margin-top:8px;border-top:1px solid var(--line);padding-top:6px";
      const mkNum = (ph: string, w = 86) => { const i = el("input", "portal-filter") as HTMLInputElement;
        i.type = "number"; i.placeholder = ph; i.setAttribute("aria-label", ph); i.style.cssText = `width:${w}px;margin:2px 4px 2px 0`; return i; };
      const lotW = mkNum("Lot W (m)"), lotD = mkNum("Lot D (m)"), farIn = mkNum("FAR", 60), hLim = mkNum("Ht limit (m)", 92);
      const scoreBtn = el("button", "file-btn") as HTMLButtonElement; scoreBtn.textContent = "⚖ Score options";
      scoreBtn.title = "Generate FAR variants of this envelope and rank them: cost · carbon · yield · compliance";
      const optOut = el("div"); optOut.style.marginTop = "6px";
      scoreBtn.onclick = async () => {
        if (!Number(lotW.value) || !Number(lotD.value) || !Number(farIn.value)) { toast("Enter lot W/D + FAR", "error"); return; }
        optOut.textContent = "scoring options…";
        try {
          const base: Record<string, unknown> = { lot_width: Number(lotW.value), lot_depth: Number(lotD.value),
            far: Number(farIn.value), building_type: type.value, region: region.value,
            ...(Number(hLim.value) ? { height_limit: Number(hLim.value) } : {}) };
          const g = await api.designOptionsGenerate(pid, base, [type.value]);
          const s = await api.designOptionsScore(pid, g.options);
          const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:11px;margin-top:4px";
          t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Option</th><th scope="col">Score</th><th scope="col">$/sf</th>`
            + `<th scope="col">tCO₂e</th><th scope="col">Floors</th><th scope="col">GFA (sf)</th><th scope="col" style="text-align:left">Code</th></tr></thead><tbody>`
            + s.options.map((o) => `<tr${o.label === s.recommended ? ' style="background:var(--hover)"' : ""}>`
              + `<td>${o.label === s.recommended ? "★ " : ""}${o.label}</td><td style="text-align:center"><b>${o.composite}</b></td>`
              + `<td style="text-align:right">${o.cost_per_sf != null ? "$" + Math.round(o.cost_per_sf) : "—"}</td>`
              + `<td style="text-align:right">${o.carbon_total_tco2e.toLocaleString()}</td>`
              + `<td style="text-align:center">${o.massing.floors}</td>`
              + `<td style="text-align:right">${Math.round(o.massing.buildable_gfa_sf).toLocaleString()}</td>`
              + `<td>${o.compliant ? "✓" : `<span style="color:var(--status-crit)" title="${o.violations.join("; ")}">✗</span>`}</td></tr>`).join("")
            + `</tbody>`;
          optOut.innerHTML = "";
          optOut.append(t);
        } catch (e) { optOut.textContent = `failed: ${(e as Error).message}`; }
      };
      optRow.append(lotW, lotD, farIn, hLim, scoreBtn, optOut);
      ceWrap.append(optRow);
    }).catch(() => { ceWrap.innerHTML = `<div class="meta">conceptual estimator unavailable</div>`; });

    api.procurementThreeWayMatch(pid).then((r) => {
      if (!r.po_count) { matchSlot.innerHTML = `<div class="meta">No purchase orders (commitments) yet.</div>`; return; }
      matchSlot.innerHTML = `<div class="meta">${r.po_count} PO(s)`
        + (r.flagged.length ? ` · <span style="color:var(--status-warn)">${r.flagged.length} need review</span>` : " · all clear") + `</div>`;
      const flagged = r.pos.filter((p) => p.status === "review");
      if (flagged.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:11px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">PO</th><th scope="col">Vendor</th><th scope="col">PO</th><th scope="col">Recd</th><th scope="col">Invoiced</th><th scope="col" style="text-align:left">Issue</th></tr></thead><tbody>`
          + flagged.map((p) => `<tr><td>${esc(p.po)}</td><td>${esc(p.vendor || "")}</td><td style="text-align:right">${cmoney(p.po_amount)}</td>`
            + `<td style="text-align:center">${p.received}</td><td style="text-align:right;color:${p.variance > 0 ? "var(--status-crit)" : "inherit"}">${cmoney(p.invoiced)}</td>`
            + `<td>${esc((p.flags || []).join("; "))}</td></tr>`).join("") + `</tbody>`;
        matchSlot.append(t);
      }
    }).catch((e) => { matchSlot.textContent = `failed: ${(e as Error).message}`; });

    // PROC-LOOP: quote leveling — the tool the ledger's own caption already promised.
    //
    // `procurement.level_quotes` and POST /procurement/level-quotes have existed and been tested for
    // months with NO caller, while the price-ledger card below rendered the sentence "quote leveling
    // with 'record' feeds this ledger" — advertising a feature there was no way to invoke. Wiring it
    // here rather than onto the bid screens is deliberate: `bidLevelingDetail` already levels
    // SUBCONTRACT bids (base totals, scope inclusion/exclusion, non-responsive bidders). This levels
    // MATERIAL quotes line by line and answers a different question — who is cheapest per item, and
    // what does splitting the award save. Same-shaped data, different decision.
    {
      const hint = el("div", "meta");
      hint.textContent = "Paste competing supplier quotes. A line with no commas starts a supplier; "
        + "lines below it are  item, qty, unit, unit price.";
      const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
      ta.style.cssText = "width:100%;min-height:96px;margin:6px 0;font-family:var(--mono);font-size:11px";
      ta.placeholder = `Acme Supply
2x4 stud, 500, EA, 4.25
1/2" drywall, 200, SHT, 12.90

Builders Depot
2x4 stud, 500, EA, 4.10
1/2" drywall, 200, SHT, 13.40`;
      const ctl = el("div"); ctl.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap";
      const runBtn = el("button", "file-btn") as HTMLButtonElement; runBtn.textContent = "Level quotes";
      const recLbl = el("label", "meta"); recLbl.style.cssText = "display:flex;align-items:center;gap:4px";
      const recCb = el("input") as HTMLInputElement; recCb.type = "checkbox";
      recLbl.append(recCb, document.createTextNode("record to the price ledger (editor)"));
      // PROCURE-LEVEL: score AGAINST A PACKAGE SCOPE, which is the step `buyout_packages` own note
      // names and nothing has ever called — *"each carries an RFQ scope (item/qty/unit) to send to
      // suppliers. Feed returned quotes to /procurement/level for a scored comparison."*
      //
      // Price-only leveling (above) cannot see the thing that decides a buyout: a supplier is
      // cheapest per line precisely BECAUSE they left half the scope out. `score_quotes` reads the
      // package's stored `scope_json` and reports coverage and the missing items alongside price.
      // The two are one control on purpose — same pasted quotes, and the scope picker decides which
      // question is being asked.
      const scopeSel = el("select", "portal-filter") as HTMLSelectElement;
      scopeSel.style.cssText = "max-width:260px";
      scopeSel.innerHTML = `<option value="">Compare prices only (no scope)</option>`;
      const out = el("div"); out.style.marginTop = "8px";
      ctl.append(runBtn, scopeSel, recLbl);
      quoteLevelWrap.append(hint, ta, ctl, out);

      // Saved buyout packages carry the scope. Absent (or unreachable) the picker just stays on
      // "prices only" — the panel must not lose its existing tool because this list failed to load.
      const pkgScope = new Map<string, { item: string; qty: number; unit: string }[]>();
      void api.moduleRecords(pid, "procurement_package").then((recs) => {
        for (const r of recs) {
          const raw = (r.data as Record<string, unknown> | undefined)?.["scope_json"];
          if (typeof raw !== "string" || !raw.trim()) continue;
          try {
            const parsed = JSON.parse(raw) as { item?: string; qty?: number; unit?: string }[];
            const scope = parsed.filter((x) => x && x.item)
              .map((x) => ({ item: String(x.item), qty: Number(x.qty) || 0, unit: String(x.unit ?? "") }));
            if (!scope.length) continue;
            pkgScope.set(r.id, scope);
            const o = document.createElement("option");
            o.value = r.id;
            o.textContent = `Score vs ${String(r.title || r.ref || r.id)} (${scope.length} lines)`;
            scopeSel.appendChild(o);
          } catch { /* a hand-edited scope_json is not a reason to break the picker */ }
        }
      }).catch(() => { /* no packages, or offline — "prices only" remains available */ });


      runBtn.onclick = async () => {
        const quotes = parseQuoteText(ta.value);
        // Three outcomes, kept distinct on purpose — "nothing pasted", "pasted but unparseable" and
        // "levelled to nothing" are different problems, and one shared empty state would report the
        // second as the first and send the reader looking in the wrong place.
        if (!ta.value.trim()) { out.innerHTML = `<div class="meta">Paste at least one supplier's quote above.</div>`; return; }
        if (!quotes.length) {
          out.innerHTML = `<div class="meta">Nothing parsed — every priced line needs four comma-separated cells: `
            + `item, qty, unit, unit price.</div>`;
          return;
        }
        out.textContent = "leveling…";

        // SCOPE PICKED -> the scored comparison, which answers a different question: not "who is
        // cheapest per line" but "who is best value once the lines they did NOT price are counted".
        const scope = pkgScope.get(scopeSel.value);
        if (scope) {
          try {
            const r = await api.procurementLevel(pid, scope, quotes);
            if (!r.suppliers.length) {
              out.innerHTML = `<div class="meta">${esc(r.note || "No suppliers to score against this scope.")}</div>`;
              return;
            }
            const t = el("table", "portal-table") as HTMLTableElement;
            t.style.cssText = "width:100%;font-size:11px;margin-top:6px";
            t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Supplier</th>`
              + `<th scope="col" style="text-align:right">Score</th><th scope="col" style="text-align:right">Coverage</th>`
              + `<th scope="col" style="text-align:right">Priced</th><th scope="col" style="text-align:right">Lead</th>`
              + `<th scope="col" style="text-align:left">Scope gaps</th></tr></thead><tbody>`
              + r.suppliers.map((sp) => {
                // A gap list is the reason this view exists — never truncated to "…" alone, because
                // the omitted item IS the finding. Capped for width, with the remainder counted.
                const gaps = sp.scope_gaps.length
                  ? esc(sp.scope_gaps.slice(0, 3).join(", "))
                    + (sp.scope_gaps.length > 3 ? ` <span class="meta">+${sp.scope_gaps.length - 3} more</span>` : "")
                  : `<span style="color:var(--status-good)">complete</span>`;
                // `coverage_pct` IS A FRACTION (0..1), despite the name — `score_quotes` computes
                // `len(covered) / n_scope` and multiplies it straight into the composite. Trusting
                // the name rendered "0.6667%" for a supplier who had priced two thirds of the
                // scope, and made the shortfall warning below fire on every complete bid.
                const cov = sp.coverage_pct * 100;
                return `<tr><td style="text-align:left">${esc(sp.supplier)}</td>`
                  + `<td style="text-align:right;font-weight:700">${sp.score.toFixed(3)}</td>`
                  + `<td style="text-align:right;color:${cov < 100 ? "var(--status-warn)" : "inherit"}">${cov.toFixed(cov % 1 ? 1 : 0)}%</td>`
                  + `<td style="text-align:right">${sp.covered_lines}/${sp.scope_lines}</td>`
                  + `<td style="text-align:right">${sp.lead_time_days == null ? "—" : `${sp.lead_time_days}d`}</td>`
                  + `<td style="text-align:left">${gaps}</td></tr>`;
              }).join("") + `</tbody>`;
            const w = r.weights;
            out.innerHTML = `<div class="meta">Best value: <b>${esc(r.best_value_supplier || "—")}</b>`
              + ` over ${r.scope_lines} scope line(s) · weights price ${w.price} / coverage ${w.coverage}`
              + ` / lead ${w.lead_time}</div>`;
            out.append(t);
            if (r.suppliers.some((sp) => sp.coverage_pct < 1)) {   // fraction, not percent
              out.insertAdjacentHTML("beforeend",
                `<div class="meta" style="color:var(--status-warn);margin-top:4px">⚠️ A supplier priced less `
                + `than the full scope — the low total may not be a like-for-like bid.</div>`);
            }
          } catch (e) { out.innerHTML = `<div class="meta">Scoring failed: ${esc((e as Error).message)}</div>`; }
          return;
        }

        try {
          const r = await api.procurementLevelQuotes(pid, quotes, recCb.checked);
          if (!r.items.length) {
            out.innerHTML = `<div class="meta">${esc(r.message || "No comparable line items across these suppliers.")}</div>`;
            return;
          }
          const sup = r.suppliers;
          const t = el("table", "portal-table") as HTMLTableElement;
          t.style.cssText = "width:100%;font-size:11px;margin-top:6px";
          t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Item</th>`
            + sup.map((x) => `<th scope="col" style="text-align:right">${esc(x)}</th>`).join("")
            + `<th scope="col" style="text-align:right">Spread</th></tr></thead><tbody>`
            + r.items.map((it) => `<tr><td style="text-align:left">${esc(it.item)}</td>`
              + sup.map((x) => {
                const v = it.prices[x];
                if (v == null) return `<td style="text-align:right;opacity:.45">—</td>`;
                const low = x === it.low_supplier;
                return `<td style="text-align:right;font-variant-numeric:tabular-nums`
                  + `${low ? ";font-weight:700;color:var(--status-good)" : ""}">${cents(v)}</td>`;
              }).join("")
              + `<td style="text-align:right">${it.spread_pct}%</td></tr>`).join("")
            + `<tr><td style="text-align:left"><b>Total</b></td>`
            + sup.map((x) => `<td style="text-align:right"><b>${cents(r.supplier_totals[x] ?? 0)}</b></td>`).join("")
            + `<td></td></tr></tbody>`;
          out.innerHTML = `<div class="meta">Best all-in supplier: <b>${esc(r.best_all_in_supplier || "—")}</b>`
            // Worded from the ARITHMETIC, not from the engine's comment, which claimed this was the
            // saving against the cheapest all-in supplier and never was. It is the spread captured
            // by taking the low quote on every line instead of the high one.
            + ` · taking the low quote on every line rather than the high one is worth`
            + ` <b>${cents(r.line_by_line_savings)}</b>`
            + (r.recorded_observations ? ` · <b>${r.recorded_observations}</b> observation(s) recorded` : "")
            + `</div>`;
          out.append(t);
          if (recCb.checked) toast("Quote observations recorded to the price ledger");
        } catch (e) { out.innerHTML = `<div class="meta">Leveling failed: ${esc((e as Error).message)}</div>`; }
      };
    }

    // PROC-LOOP: the price-observation ledger — per-material stats, latest price + drift vs median
    api.procurementPriceHistory(pid).then((r) => {
      if (!r.material_count) { priceLedgerSlot.innerHTML = `<div class="meta">${esc(r.message || "No price observations yet.")}</div>`; return; }
      const top = r.materials.slice().sort((a, b) => b.observations - a.observations).slice(0, 15);
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:11px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Material</th><th scope="col">Obs</th><th scope="col">Min</th>`
        + `<th scope="col">Median</th><th scope="col">Max</th><th scope="col">Latest</th><th scope="col">Drift</th></tr></thead><tbody>`
        + top.map((m) => {
          const drift = m.latest_vs_median_pct;
          const col = Math.abs(drift) >= 10 ? (drift > 0 ? "var(--status-crit)" : "var(--status-good)") : "inherit";
          return `<tr><td>${esc(m.material)}${m.unit ? ` <span class="meta">/${esc(m.unit)}</span>` : ""}</td>`
            + `<td style="text-align:center">${m.observations}</td><td style="text-align:right">${cents(m.min)}</td>`
            + `<td style="text-align:right">${cents(m.median)}</td><td style="text-align:right">${cents(m.max)}</td>`
            + `<td style="text-align:right" title="${esc(m.latest.date)} · ${esc(m.latest.vendor || "")}">${cents(m.latest.unit_price)}</td>`
            + `<td style="text-align:right;color:${col}">${drift > 0 ? "+" : ""}${drift}%</td></tr>`;
        }).join("") + `</tbody>`;
      priceLedgerSlot.innerHTML = `<div class="meta">${r.material_count} material(s) tracked — quote leveling with "record" feeds this ledger</div>`;
      priceLedgerSlot.append(t);
    }).catch((e) => { priceLedgerSlot.textContent = `failed: ${(e as Error).message}`; });

    // PROC-LOOP: model selection → per-class material-request suggestions → create requests
    {
      const row = el("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
      const qIn = el("input", "portal-filter") as HTMLInputElement;
      qIn.placeholder = "QUERY-DSL scope (blank = whole model), e.g. IfcWall & storey=L2";
      qIn.style.cssText = "flex:1 1 260px;min-width:0";
      const sugBtn = el("button", "tool-btn") as HTMLButtonElement; sugBtn.textContent = "📦 Suggest";
      const out = el("div"); out.style.marginTop = "6px";
      row.append(qIn, sugBtn); mrWrap.append(row, out);
      sugBtn.onclick = async () => {
        out.textContent = "computing takeoff…";
        try {
          const q = qIn.value.trim();
          const r = await api.procurementMaterialSuggest(pid, q ? { q } : {});
          if (!r.suggestions.length) { out.textContent = "nothing matched the selection"; return; }
          const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:11px";
          t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Material</th><th scope="col">Qty</th>`
            + `<th scope="col">Unit</th><th scope="col">Elements</th></tr></thead><tbody>`
            + r.suggestions.map((s) => `<tr><td>${esc(s.material)}</td><td style="text-align:right">${s.qty ?? "—"}</td>`
              + `<td style="text-align:center">${esc(s.unit || "")}</td><td style="text-align:center">${s.elements}</td></tr>`).join("")
            + `</tbody>`;
          const mk = el("button", "tool-btn") as HTMLButtonElement;
          mk.textContent = `✚ Create ${r.suggestions.length} request(s)`; mk.style.marginTop = "6px";
          mk.onclick = async () => {
            mk.disabled = true;
            try {
              const cr = await api.procurementMaterialSuggest(pid, { ...(q ? { q } : {}), create: true });
              toast(`${cr.created.length} material request(s) created`, "success");
              mk.textContent = `✓ ${cr.created.length} created`;
            } catch (e) { toast((e as Error).message, "error"); mk.disabled = false; }
          };
          out.innerHTML = ""; out.append(t, mk);
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
    }
  }
