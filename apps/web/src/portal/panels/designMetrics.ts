import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * DESIGN-METRICS + DAYLIGHT panel — the live design-validation numbers off the model: program efficiency
 * (floors · GFA · net floor area · net-to-gross · unit count · area-by-type) and a deterministic
 * average-daylight-factor ESTIMATE from the model's own windows (CIBSE formula — labelled an estimate,
 * not a ray-trace). Read-only over /model/design-metrics; 409s gracefully without a source IFC.
 */
const BAND_COLOR: Record<string, string> = { good: "#1a7f37", fair: "#9a6700", limited: "#b42318" };

export async function renderDesignMetrics(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("📐 Design metrics", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Computing program efficiency + daylight from the model…</div>`;
  ctx.root.appendChild(body);

  const kpi = (label: string, value: string, sub = "") =>
    `<div style="min-width:104px"><div style="font-size:20px;font-weight:800;font-variant-numeric:tabular-nums">${esc(value)}</div>`
    + `<div class="meta" style="margin:0">${esc(label)}${sub ? ` <span style="opacity:.7">${esc(sub)}</span>` : ""}</div></div>`;

  try {
    const r = await ctx.host.api.modelDesignMetrics(pid);
    body.replaceChildren();

    const head = document.createElement("div"); head.className = "dash-card"; head.style.marginBottom = "10px";
    head.innerHTML = `<div class="section-title" style="margin:0 0 8px">Program efficiency</div>`
      + `<div style="display:flex;gap:20px;flex-wrap:wrap">`
      + kpi("Floors", String(r.floors))
      + kpi("Net floor area", `${r.net_floor_area_m2.toLocaleString()}`, "m²")
      + kpi("Gross floor area", `${r.gross_floor_area_m2.toLocaleString()}`, "m²")
      + kpi("Net-to-gross", r.net_to_gross ? `${(r.net_to_gross * 100).toFixed(0)}%` : "—")
      + kpi("Units", String(r.unit_count))
      + kpi("Avg unit", r.avg_unit_m2 ? `${r.avg_unit_m2}` : "—", r.avg_unit_m2 ? "m²" : "")
      + kpi("Spaces", String(r.space_count))
      + `</div>`;
    body.appendChild(head);

    // --- daylight card -----------------------------------------------------------------------------
    const d = r.daylight;
    const col = BAND_COLOR[d.band] || "#57606a";
    const dl = document.createElement("div"); dl.className = "dash-card"; dl.style.marginBottom = "10px";
    dl.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap">`
      + `<div class="section-title" style="margin:0">Daylight <span style="opacity:.6;font-weight:500;font-size:11px">(estimate)</span></div>`
      + `<div style="font-size:22px;font-weight:800;color:${col};font-variant-numeric:tabular-nums">${d.avg_daylight_factor_pct}%`
      + ` <span style="font-size:12px;text-transform:uppercase;letter-spacing:.04em">${esc(d.band)}</span></div></div>`
      + `<div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:8px">`
      + kpi("Windows", String(d.window_count))
      + kpi("Glazed area", `${d.glazed_area_m2.toLocaleString()}`, "m²")
      + kpi("Window-to-floor", d.window_to_floor_ratio ? `${(d.window_to_floor_ratio * 100).toFixed(1)}%` : "—")
      + `</div>`
      + `<div class="meta" style="margin-top:8px;opacity:.8">${esc(d.note)}</div>`;
    body.appendChild(dl);

    // --- area by space type ------------------------------------------------------------------------
    if (r.by_type.length) {
      const net = r.net_floor_area_m2 || 1;
      const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.overflowX = "auto";
      const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:12px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Space type</th>`
        + `<th scope="col" style="text-align:right">Area (m²)</th><th scope="col" style="text-align:right">% of net</th></tr></thead><tbody>`
        + r.by_type.slice(0, 60).map((x) => `<tr><td style="text-align:left">${esc(x.type)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${x.area_m2.toLocaleString()}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${(x.area_m2 / net * 100).toFixed(1)}%</td></tr>`).join("")
        + `</tbody>`;
      wrap.appendChild(t);
      body.appendChild(wrap);
    }
  } catch (e) {
    const msg = (e as Error).message || "";
    body.innerHTML = /409/.test(msg)
      ? `<div class="meta">Design metrics need a source IFC. Convert or upload a model, then reopen this panel.</div>`
      : `<div class="meta">Design metrics unavailable: ${esc(msg)}</div>`;
  }
}
