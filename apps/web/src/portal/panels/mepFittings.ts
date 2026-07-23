import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * MEP-FITTINGS panel — the implied fittings over the MEP port graph: tee/cross at branch nodes, reducer
 * at a segment-to-segment size step, elbow at a direction change (deterministic, no CV). The counts roll
 * into QTO as EA lines. Read-only over /mep/fittings; 409s gracefully without a source IFC.
 */
export async function renderMepFittings(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("🔩 MEP fittings", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const body = document.createElement("div");
  body.innerHTML = `<div class="meta">Inferring implied fittings from the MEP port graph…</div>`;
  ctx.root.appendChild(body);

  try {
    const r = await ctx.host.api.mepFittings(pid);
    body.replaceChildren();

    const head = document.createElement("div"); head.className = "dash-card"; head.style.marginBottom = "10px";
    const chip = (label: string, n: number) =>
      `<span style="white-space:nowrap;margin-right:14px">${esc(label)} <b style="font-variant-numeric:tabular-nums">${n}</b></span>`;
    head.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap">`
      + `<div class="section-title" style="margin:0">Implied fittings</div>`
      + `<div style="font-size:22px;font-weight:800;font-variant-numeric:tabular-nums">${r.total_fittings} <span style="font-size:12px;font-weight:500;opacity:.7">EA · ${r.element_count} MEP elements</span></div></div>`
      + (r.total_fittings ? `<div class="meta" style="margin-top:6px">`
        + chip("Elbow", r.fittings.elbow) + chip("Tee", r.fittings.tee) + chip("Cross", r.fittings.cross) + chip("Reducer", r.fittings.reducer)
        + `</div>` : "");
    body.appendChild(head);

    if (!r.total_fittings) {
      body.appendChild(Object.assign(document.createElement("div"), { className: "meta",
        textContent: "No fittings implied — the model has no connected MEP runs yet (author segments + connect their ports)." }));
      body.appendChild(Object.assign(document.createElement("div"), { className: "meta", textContent: r.note }));
      return;
    }

    // --- QTO lines ---------------------------------------------------------------------------------
    const qwrap = document.createElement("div"); qwrap.className = "dash-card"; qwrap.style.cssText = "overflow-x:auto;margin-bottom:10px";
    qwrap.innerHTML = `<div class="section-title" style="margin:0 0 6px">QTO lines</div>`;
    const qt = document.createElement("table"); qt.className = "portal-table"; qt.style.cssText = "width:100%;font-size:12px";
    qt.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Item</th>`
      + `<th scope="col" style="text-align:right">Qty</th><th scope="col" style="text-align:left">Unit</th></tr></thead><tbody>`
      + r.qto_lines.map((l) => `<tr><td style="text-align:left">${esc(l.item)}</td>`
        + `<td style="text-align:right;font-variant-numeric:tabular-nums"><b>${l.qty}</b></td>`
        + `<td style="text-align:left">${esc(l.unit)}</td></tr>`).join("")
      + `</tbody>`;
    qwrap.appendChild(qt);
    body.appendChild(qwrap);

    // --- detail (where each fitting was inferred) --------------------------------------------------
    if (r.details.length) {
      const dwrap = document.createElement("div"); dwrap.className = "dash-card"; dwrap.style.overflowX = "auto";
      dwrap.innerHTML = `<div class="section-title" style="margin:0 0 6px">Inferred at</div>`;
      const dt = document.createElement("table"); dt.className = "portal-table"; dt.style.cssText = "width:100%;font-size:11px";
      dt.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Fitting</th><th scope="col" style="text-align:left">Class</th>`
        + `<th scope="col" style="text-align:right">Qty</th><th scope="col" style="text-align:left">Reason</th></tr></thead><tbody>`
        + r.details.slice(0, 200).map((x) => `<tr><td style="text-align:left">${esc(x.fitting)}</td>`
          + `<td style="text-align:left">${esc(x.ifc_class.replace("Ifc", ""))}</td>`
          + `<td style="text-align:right;font-variant-numeric:tabular-nums">${x.count}</td>`
          + `<td style="text-align:left;opacity:.85">${esc(x.reason)}</td></tr>`).join("")
        + `</tbody>`;
      dwrap.appendChild(dt);
      if (r.details.length > 200) dwrap.insertAdjacentHTML("beforeend", `<div class="meta" style="opacity:.7">Showing first 200.</div>`);
      body.appendChild(dwrap);
    }

    const note = document.createElement("div"); note.className = "meta"; note.style.marginTop = "8px"; note.style.opacity = ".8";
    note.textContent = r.note;
    body.appendChild(note);
  } catch (e) {
    const msg = (e as Error).message || "";
    body.innerHTML = /409/.test(msg)
      ? `<div class="meta">MEP fittings need a source IFC with a connected MEP system. Convert or upload a model, then reopen this panel.</div>`
      : `<div class="meta">MEP fittings unavailable: ${esc(msg)}</div>`;
  }
}
