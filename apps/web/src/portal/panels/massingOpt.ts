import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * MASSING-OPT panel — the layout/massing optioneer: enter a zoning envelope + acquisition assumptions,
 * sweep the massing levers (floor-to-floor · core efficiency · coverage strategy · unit size) over the
 * deterministic program engine, and rank the options by developer yield with a Pareto cost-vs-profit
 * frontier. Stateless — no IFC is written; this ranks the program so you pick a massing to author.
 */
interface Field { key: string; label: string; def: number; step?: number }
const FIELDS: Field[] = [
  { key: "lot_width", label: "Lot width (m)", def: 40 },
  { key: "lot_depth", label: "Lot depth (m)", def: 60 },
  { key: "far", label: "FAR", def: 3, step: 0.1 },
  { key: "coverage_max", label: "Coverage max", def: 0.6, step: 0.05 },
  { key: "height_limit", label: "Height limit (m)", def: 40 },
  { key: "floor_to_floor", label: "Floor-to-floor (m)", def: 3.5, step: 0.1 },
  { key: "efficiency", label: "Efficiency", def: 0.82, step: 0.01 },
  { key: "avg_unit_m2", label: "Avg unit (m²)", def: 75 },
  { key: "land_cost", label: "Land cost ($)", def: 3_000_000, step: 100_000 },
  { key: "hard_cost_psf", label: "Hard $/sf", def: 225 },
  { key: "rent_per_unit_month", label: "Rent $/unit/mo", def: 3000 },
  { key: "exit_cap", label: "Exit cap", def: 0.05, step: 0.005 },
];

export async function renderMassingOpt(ctx: PanelContext) {
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("🧮 Massing optioneer", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  ctx.root.appendChild(body);

  // --- the envelope form -----------------------------------------------------------------------------
  const form = document.createElement("div"); form.className = "dash-card"; form.style.marginBottom = "10px";
  form.innerHTML = `<div class="section-title" style="margin:0 0 6px">Zoning envelope + acquisition</div>`;
  const grid = document.createElement("div");
  grid.style.cssText = "display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px";
  const inputs: Record<string, HTMLInputElement> = {};
  for (const f of FIELDS) {
    const cell = document.createElement("label"); cell.style.cssText = "display:flex;flex-direction:column;gap:2px;font-size:11px";
    cell.append(Object.assign(document.createElement("span"), { textContent: f.label, className: "meta" }));
    const inp = document.createElement("input"); inp.type = "number"; inp.value = String(f.def);
    inp.step = String(f.step ?? 1); inp.style.cssText = "font-size:16px;padding:3px 6px;width:100%;box-sizing:border-box";
    inputs[f.key] = inp; cell.appendChild(inp); grid.appendChild(cell);
  }
  form.appendChild(grid);

  const controls = document.createElement("div"); controls.style.cssText = "display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap";
  const useSel = document.createElement("select"); useSel.style.cssText = "font-size:13px;padding:3px";
  useSel.innerHTML = `<option value="residential">Residential</option><option value="commercial">Commercial</option>`;
  const objSel = document.createElement("select"); objSel.style.cssText = "font-size:13px;padding:3px";
  objSel.innerHTML = `<option value="yield_on_cost">Rank: yield-on-cost</option><option value="profit">Rank: profit</option>`
    + `<option value="units">Rank: units</option><option value="net_sellable">Rank: net sellable</option>`;
  const run = document.createElement("button"); run.className = "btn"; run.textContent = "Run optioneer";
  controls.append(useSel, objSel, run);
  form.appendChild(controls);
  body.appendChild(form);

  const out = document.createElement("div");
  body.appendChild(out);

  const usd = (n: number) => (n < 0 ? "−$" : "$") + Math.round(Math.abs(n)).toLocaleString();

  run.onclick = async () => {
    run.disabled = true; run.textContent = "Running…";
    out.innerHTML = `<div class="meta">Sweeping massing options…</div>`;
    const envelope: Record<string, unknown> = { use_type: useSel.value };
    for (const f of FIELDS) envelope[f.key] = Number(inputs[f.key]!.value);
    try {
      const r = await ctx.host.api.massingOptioneer(envelope, { objective: objSel.value, limit: 20 });
      out.replaceChildren();
      if (!r.scenarios.length) { out.innerHTML = `<div class="meta">${esc(r.note)}</div>`; return; }

      const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.overflowX = "auto";
      const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:11px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">#</th>`
        + `<th scope="col" style="text-align:right">Floors</th><th scope="col" style="text-align:right">Units</th>`
        + `<th scope="col" style="text-align:right">GFA (sf)</th><th scope="col" style="text-align:right">Yield</th>`
        + `<th scope="col" style="text-align:right">Profit</th><th scope="col" style="text-align:left">Levers (f2f · eff · cov · unit)</th></tr></thead><tbody>`
        + r.scenarios.map((s, i) => {
          const lev = s.levers;
          const badge = s.on_frontier ? ` <span title="on the cost-vs-profit frontier" style="color:var(--accent,#5b9)">✦</span>` : "";
          return `<tr${s.id === r.best ? ' style="font-weight:700"' : ""}><td style="text-align:left">${i + 1}${badge}</td>`
            + `<td style="text-align:right;font-variant-numeric:tabular-nums">${s.floors}</td>`
            + `<td style="text-align:right;font-variant-numeric:tabular-nums">${s.units}</td>`
            + `<td style="text-align:right;font-variant-numeric:tabular-nums">${Math.round(s.gfa_sf).toLocaleString()}</td>`
            + `<td style="text-align:right;font-variant-numeric:tabular-nums">${(s.proforma.yield_on_cost * 100).toFixed(1)}%</td>`
            + `<td style="text-align:right;font-variant-numeric:tabular-nums;color:${s.proforma.profit < 0 ? "var(--status-crit)" : "var(--status-good)"}">${usd(s.proforma.profit)}</td>`
            + `<td style="text-align:left;opacity:.85">${esc(String(lev.floor_to_floor))} · ${esc(String(lev.efficiency))} · ${esc(String(lev.coverage_max))} · ${esc(String(lev.avg_unit_m2))}</td></tr>`;
        }).join("") + `</tbody>`;
      wrap.appendChild(t);
      out.appendChild(wrap);
      out.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:6px;opacity:.8">✦ = on the cost-vs-profit frontier. ${esc(String(r.count))} feasible options evaluated; ranked by ${esc(r.objective)}.</div>`);
    } catch (e) {
      out.innerHTML = `<div class="meta">Optioneer failed: ${esc((e as Error).message)}</div>`;
    } finally {
      run.disabled = false; run.textContent = "Run optioneer";
    }
  };
}
