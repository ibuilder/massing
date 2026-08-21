import type { ApiClient } from "../../api/client";
import { enqueueAndWait, isJobStillRunning } from "../../api/waitForJob";
import { kvTable, resultNote, showResult } from "../../ui/result";
import { toast, withLoading } from "../../ui/feedback";

/**
 * R24-RUNS-INBOX — the Clash rail panel, out of `app.ts`.
 *
 * The panel used to `await api.clashFederated(...)` on the request thread, so a coordination run
 * never became a Job row and the Runs inbox stayed empty. The kind has existed since v0.3.1057;
 * this is the call site.
 *
 * Lifted out of `app.ts` because that file is pinned at its measured size: wiring the queue in
 * place would have grown it, and the ratchet exists to force this extraction.
 */
export interface ClashPanelDeps {
  api: ApiClient;
  projectId: () => string | null;
  selectByGuid: (guid: string, fit?: boolean) => Promise<void | boolean>;
  setStatus: (m: string) => void;
  refreshIssues: () => Promise<void>;
  reloadModelPins: () => Promise<unknown>;
}

type ClashHit = {
  a_class: string; b_class: string; a_guid: string; b_guid: string;
  a_model: string; b_model: string; volume: number;
};

export async function buildClashPanel(d: ClashPanelDeps): Promise<void> {
  const panel = document.getElementById("panel-clash");
  if (!panel) return;
  const pid = d.projectId();
  panel.innerHTML = `<div class="section-title">Clash &amp; coordination</div>`;
  if (!pid) {
    panel.insertAdjacentHTML("beforeend",
      `<div class="meta">Open a project to run clash coordination.</div>`);
    return;
  }
  const intro = document.createElement("div");
  intro.className = "meta";
  intro.style.cssText = "font-size:11px;margin-bottom:8px;line-height:1.4";
  intro.textContent = "Detect cross-discipline interferences, click a clash to fly to it in 3D, and promote to a tracked issue (BCF).";
  panel.appendChild(intro);
  const cbtn = (label: string, on: () => void, cap?: "edit" | "review") => {
    const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label;
    b.style.cssText = "display:block;width:100%;text-align:left;margin:3px 0"; if (cap) b.dataset.cap = cap;
    b.onclick = on; return b;
  };
  const out = document.createElement("div");
  out.className = "meta"; out.style.cssText = "margin:6px 0;font-size:11.5px;line-height:1.45";
  const list = document.createElement("div");
  list.style.cssText = "display:flex;flex-direction:column;gap:2px;max-height:44vh;overflow:auto;margin-top:4px";
  const renderClashes = (clashes: ClashHit[]) => {
    list.innerHTML = "";
    if (!clashes.length) {
      list.innerHTML = `<div class="meta" style="color:var(--status-good)">No hard clashes 🎉</div>`;
      return;
    }
    list.insertAdjacentHTML("beforeend",
      `<div class="section-title" style="margin:4px 0 2px">${clashes.length} clash${clashes.length === 1 ? "" : "es"} — click to inspect</div>`);
    clashes.slice(0, 300).forEach((c, i) => {
      const row = document.createElement("button"); row.className = "tool-btn";
      row.style.cssText = "display:flex;justify-content:space-between;gap:8px;width:100%;text-align:left;font-size:11px;padding:4px 7px";
      row.innerHTML = `<span>${i + 1}. ${c.a_class.replace("Ifc", "")} <span style="color:var(--status-crit)">✕</span> ${c.b_class.replace("Ifc", "")}</span>`
        + `<span class="meta">${c.volume.toFixed(3)} m³</span>`;
      row.title = `${c.a_model} vs ${c.b_model} — click to select + zoom to the clash`;
      row.onclick = () => void d.selectByGuid(c.a_guid || c.b_guid, true)
        .then(() => d.setStatus(`clash ${i + 1}: ${c.a_class} ✕ ${c.b_class}`));
      list.appendChild(row);
    });
  };
  panel.appendChild(cbtn("💥 Run clash — all disciplines", () => void withLoading(panel, "Queueing federated clash", async () => {
    try {
      const r = await enqueueAndWait(d.api, pid, "clash_federated", { coordinate: true, create_topics: true }) as {
        count: number; disciplines: string[]; created_topics?: number; clashes: ClashHit[];
        coordination: { new: number; active: number; resolved: number; reduction?: number } | null;
      };
      const co = r.coordination;
      const bits = [`${r.count} clashes`, `${(r.disciplines ?? []).length} disciplines`];
      if (r.created_topics != null) bits.push(`${r.created_topics} issue(s)`);
      out.textContent = bits.join(" · ")
        + (co ? ` — ${co.new} new · ${co.active} active · ${co.resolved} resolved${co.reduction ? ` · ${Math.round(co.reduction * 100)}% ↓` : ""}` : "");
      renderClashes(r.clashes ?? []);
      await d.refreshIssues(); await d.reloadModelPins();
    } catch (e) {
      if (isJobStillRunning(e)) throw e;
      out.textContent = `${(e as Error).message}. Add a discipline IFC (Tools → Models federation), or run the single-model check below.`;
      list.replaceChildren();
    }
  }), "edit"));
  panel.appendChild(cbtn("⚡ Single-model check (structure ✕ MEP/walls)", () => void withLoading(panel, "Queueing clash", async () => {
    try {
      const r = await enqueueAndWait(d.api, pid, "clash_detect", {
        a: "IfcBeam,IfcSlab,IfcColumn,IfcStair", b: "IfcDuctSegment,IfcPipeSegment,IfcWall",
        min_volume: 0.02, create_topics: true,
      }) as { count: number; created_topics?: number };
      out.textContent = `${r.count} clashes · ${r.created_topics ?? 0} issue(s) created. Open Issues to coordinate.`;
      list.replaceChildren();
      await d.refreshIssues(); await d.reloadModelPins();
    } catch (e) {
      if (isJobStillRunning(e)) throw e;
      out.textContent = `failed: ${(e as Error).message}`;
    }
  }), "edit"));
  panel.appendChild(cbtn("📊 Coordination metrics", () => void (async () => {
    try {
      const m = await d.api.clashMetrics(pid);
      showResult("Clash coordination metrics", (body) => {
        body.appendChild(resultNote(`<b>${m.open}</b> open · <b>${m.closed}</b> closed · ${Math.round(m.resolution_rate * 100)}% resolved · ${m.runs} run(s)`, m.open ? "bad" : "ok"));
        body.appendChild(kvTable([
          { k: "By discipline pair", v: Object.entries(m.by_discipline).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—" },
          { k: "By severity", v: Object.entries(m.by_severity).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—" },
          { k: "Reappearance rate", v: `${Math.round(m.reappearance_rate * 100)}%` },
        ]));
      });
    } catch (e) { toast(`metrics: ${(e as Error).message}`, "error"); }
  })()));
  panel.appendChild(cbtn("📌 Open in Issues (BCF)", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
  panel.append(out, list);
}
