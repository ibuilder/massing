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

  // The wind screen lives outside the metrics try/catch on purpose: it can run on typed dimensions
  // with no model at all, so a 409 on the metrics must not take it down with them.
  const windHost = document.createElement("div");
  ctx.root.appendChild(windHost);
  let hasModel = false;

  try {
    const r = await ctx.host.api.modelDesignMetrics(pid);
    hasModel = true;
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

  await renderWindScreen(ctx, windHost, pid, hasModel);
}

/**
 * ENV-WIND — the pedestrian wind-comfort screen, drawn under the metrics it shares a stage with.
 *
 * A form, because the screen's three most misreadable inputs are all optional: the dimensions (blank
 * ⇒ taken off the model's bounding box), the site wind (blank ⇒ a default that scales every number),
 * and the gap to a neighbouring mass (blank ⇒ channelling is never checked at all). `envWind.ts`
 * holds the wording for all three; this function only draws it.
 */
async function renderWindScreen(ctx: PanelContext, host: HTMLElement, pid: string, hasModel: boolean) {
  const W = await import("./envWind");
  const card = document.createElement("div"); card.className = "dash-card";
  const num = (id: string, label: string, ph: string) =>
    `<label style="display:flex;flex-direction:column;gap:2px;font-size:11px;color:var(--muted)">${esc(label)}`
    + `<input class="portal-filter" data-w="${id}" type="number" min="0" step="0.1" placeholder="${esc(ph)}" style="width:96px"></label>`;
  card.innerHTML = `<div class="section-title" style="margin:0 0 8px">Pedestrian wind comfort `
    + `<span style="opacity:.6;font-weight:500;font-size:11px">(massing screen — not CFD)</span></div>`
    + `<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">`
    + num("height_m", "Height (m)", hasModel ? "from model" : "required")
    + num("width_m", "Width (m)", hasModel ? "from model" : "required")
    + num("depth_m", "Depth (m)", hasModel ? "from model" : "required")
    + num("wind_ms", "Site wind (m/s)", "default 5")
    + num("gap_m", "Gap to neighbour (m)", "not checked")
    + num("podium_height_m", "Podium height (m)", "none")
    + `<button class="mini-btn" data-w-run type="button">Screen</button></div>`
    + `<div data-w-out style="margin-top:10px"></div>`;
  host.appendChild(card);

  const out = card.querySelector<HTMLElement>("[data-w-out]")!;
  const btn = card.querySelector<HTMLButtonElement>("[data-w-run]")!;
  const read = (): import("./envWind").WindForm => {
    const f: Record<string, number | null> = {};
    card.querySelectorAll<HTMLInputElement>("input[data-w]").forEach((i) => {
      const v = i.value.trim();
      f[i.dataset.w!] = v === "" ? null : Number(v);
    });
    return f as import("./envWind").WindForm;
  };

  btn.addEventListener("click", async () => {
    const form = read();
    const gate = W.screenGate(form, hasModel);
    if (!gate.can) { out.innerHTML = `<div class="meta">Cannot screen — ${esc(gate.why)}.</div>`; return; }
    btn.disabled = true;
    out.innerHTML = `<div class="meta">Screening…</div>`;
    try {
      const r = await ctx.host.api.envWindScreen(pid, form);
      const gaps = W.unassessed(r);
      const bad = !r.acceptable_for_entrances || r.worst.lawson === "S";
      out.innerHTML =
        `<div style="font-weight:700;color:${bad ? "#b42318" : gaps.length ? "#9a6700" : "#1a7f37"}">`
        + `${esc(W.verdict(r))}</div>`
        + gaps.map((g) => `<div class="meta" style="margin-top:6px;color:#9a6700">⚠ ${esc(g)}</div>`).join("")
        + `<div class="meta" style="margin-top:6px">${esc(W.dimensionBasis(r, form))}</div>`
        + `<div class="meta" style="margin-top:2px">${esc(W.windBasis(form.wind_ms, r.inputs.wind_ms))}</div>`
        + `<table class="portal-table" style="margin-top:8px"><thead><tr>`
        + `<th scope="col">Zone</th><th scope="col" style="text-align:right">Factor</th>`
        + `<th scope="col" style="text-align:right">Speed (m/s)</th><th scope="col">Lawson</th></tr></thead><tbody>`
        + r.zones.map((z) => `<tr><td>${esc(z.zone)}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">×${z.factor}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${z.speed_ms}</td>`
          + `<td>${esc(W.comfortLabel(z))}</td></tr>`).join("")
        + `</tbody></table>`
        + `<div class="section-title" style="margin:10px 0 4px">Mitigations</div>`
        + `<ul style="margin:0;padding-left:18px;font-size:12px">`
        + W.mitigationLines(r).map((m) => `<li>${esc(m)}</li>`).join("") + `</ul>`
        + `<div class="meta" style="margin-top:8px;opacity:.8">${esc(r.disclaimer)}</div>`;
    } catch (e) {
      const msg = (e as Error).message || "";
      out.innerHTML = `<div class="meta">Wind screen unavailable: ${esc(msg)}</div>`;
    } finally {
      btn.disabled = false;
    }
  });
}
