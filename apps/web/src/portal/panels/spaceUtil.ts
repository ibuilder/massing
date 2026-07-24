import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * SPACE-UTIL panel — occupancy capacity per IfcSpace at an adjustable area-per-person standard
 * (rolled up by space type), plus a headcount program vs the modelled inventory → the area gap per
 * type. Read-only over /model/space-utilization + /model/space-demand; every model-derived string is
 * escaped (space names/types are free text).
 */
const STATUS_COLOR: Record<string, string> = {
  ok: "#1a7f37", surplus: "#1a7f37", tight: "#9a6700", short: "#b42318", missing: "#b42318",
};

export async function renderSpaceUtil(ctx: PanelContext) {
  const pid = ctx.host.projectId()!;
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("🪑 Space Utilization", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));

  const controls = document.createElement("div");
  controls.className = "dash-card";
  controls.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px";
  controls.innerHTML = `<label class="meta" style="margin:0">Area / person (m²)
      <input id="su-app" type="number" min="1" max="100" step="0.5" value="10" style="width:70px;margin-left:6px"></label>
    <button id="su-apply" class="btn">Recompute</button>
    <span id="su-note" class="meta" style="margin:0"></span>`;
  ctx.root.appendChild(controls);

  const body = document.createElement("div");
  ctx.root.appendChild(body);

  async function load() {
    const app = Number((controls.querySelector("#su-app") as HTMLInputElement).value) || 10;
    body.innerHTML = `<div class="meta">Reading the model's spaces…</div>`;
    try {
      const u = await ctx.host.api.modelSpaceUtilization(pid, app);
      (controls.querySelector("#su-note") as HTMLElement).textContent =
        `${u.space_count} space(s) · ${u.total_area_m2.toLocaleString()} m² · capacity ${u.capacity_total}`;
      body.replaceChildren();

      const cap = document.createElement("div");
      cap.className = "dash-card";
      cap.innerHTML = `<div class="section-title">Capacity by space type</div>`
        + `<table style="width:100%;border-collapse:collapse;font-size:12px">`
        + `<tr class="meta"><th style="text-align:left;padding:3px 6px">Type</th>`
        + `<th style="text-align:right;padding:3px 6px">Spaces</th>`
        + `<th style="text-align:right;padding:3px 6px">Area m²</th>`
        + `<th style="text-align:right;padding:3px 6px">Capacity @ ${esc(String(u.area_per_person))} m²/p</th></tr>`
        + u.by_type.map((r) =>
          `<tr><td style="padding:3px 6px">${esc(r.type)}</td>`
          + `<td style="text-align:right;padding:3px 6px">${r.count}</td>`
          + `<td style="text-align:right;padding:3px 6px;font-variant-numeric:tabular-nums">${r.area_m2.toLocaleString()}</td>`
          + `<td style="text-align:right;padding:3px 6px;font-variant-numeric:tabular-nums">${r.capacity}</td></tr>`).join("")
        + `</table>`;
      body.appendChild(cap);

      // headcount program vs inventory
      const dem = document.createElement("div");
      dem.className = "dash-card"; dem.style.marginTop = "10px";
      dem.innerHTML = `<div class="section-title">Program fit — headcount vs modelled area</div>`
        + `<div class="meta" style="margin:2px 0 6px">One <code>type = headcount</code> per line (e.g. <code>Office = 40</code>); types match the table above.</div>`;
      const ta = document.createElement("textarea");
      ta.style.cssText = "width:100%;min-height:64px;font-size:12px;font-family:inherit";
      ta.placeholder = "Office = 40\nMeeting = 12";
      const runBtn = document.createElement("button"); runBtn.className = "tool-btn on"; runBtn.textContent = "Check fit";
      runBtn.style.marginTop = "6px";
      const out = document.createElement("div"); out.style.marginTop = "8px";
      dem.append(ta, runBtn, out); body.appendChild(dem);
      runBtn.onclick = async () => {
        const program: Record<string, number> = {};
        for (const line of ta.value.split("\n")) {
          const m = /^\s*(.+?)\s*[=:]\s*(\d+)\s*$/.exec(line);
          if (m?.[1] && m[2]) program[m[1]] = Number(m[2]);
        }
        if (!Object.keys(program).length) { out.innerHTML = `<div class="meta">No program lines parsed.</div>`; return; }
        out.innerHTML = `<div class="meta">checking…</div>`;
        try {
          const d = await ctx.host.api.modelSpaceDemand(pid, program, app);
          out.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:12px">`
            + `<tr class="meta"><th style="text-align:left;padding:3px 6px">Type</th>`
            + `<th style="text-align:right;padding:3px 6px">Headcount</th>`
            + `<th style="text-align:right;padding:3px 6px">Required m²</th>`
            + `<th style="text-align:right;padding:3px 6px">Modelled m²</th>`
            + `<th style="text-align:right;padding:3px 6px">Gap m²</th>`
            + `<th style="text-align:left;padding:3px 6px">Status</th></tr>`
            + d.by_type.map((r) =>
              `<tr><td style="padding:3px 6px">${esc(r.type)}</td>`
              + `<td style="text-align:right;padding:3px 6px">${r.headcount}</td>`
              + `<td style="text-align:right;padding:3px 6px;font-variant-numeric:tabular-nums">${r.required_m2.toLocaleString()}</td>`
              + `<td style="text-align:right;padding:3px 6px;font-variant-numeric:tabular-nums">${r.supplied_m2.toLocaleString()}</td>`
              + `<td style="text-align:right;padding:3px 6px;font-variant-numeric:tabular-nums">${r.gap_m2.toLocaleString()}</td>`
              + `<td style="padding:3px 6px;color:${STATUS_COLOR[r.status] || "#57606a"}">${esc(r.status)}</td></tr>`).join("")
            + `</table>`
            + `<div class="meta" style="margin-top:6px">${esc(d.note)}</div>`;
        } catch (e) { out.innerHTML = `<div class="meta">Demand check unavailable: ${esc((e as Error).message)}</div>`; }
      };

      const note = document.createElement("div");
      note.className = "meta"; note.style.cssText = "margin-top:8px;opacity:.8";
      note.textContent = u.note;
      body.appendChild(note);
    } catch (e) {
      body.innerHTML = `<div class="meta">Space utilization unavailable (needs a model with IfcSpaces): ${esc((e as Error).message)}</div>`;
    }
  }

  (controls.querySelector("#su-apply") as HTMLButtonElement).onclick = () => void load();
  await load();
}
