import type { ApiClient } from "../../api/client";
import type { ClashResult, FederatedClashResult } from "../../api/clash";
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
  let lastMatrix: { disciplines: string[]; tested_pairs: [string, string][];
    findings: { discipline_a: string; discipline_b: string; count?: number }[] } | null = null;
  /** The list is also capped client-side. Before CLASH-TRUNC the header counted the PAGE while the
   *  summary line above it counted the RUN, so two different numbers sat on one screen under the
   *  same word, and neither said a cap was in play. */
  const LIST_CAP = 300;
  const renderClashes = (clashes: ClashHit[], total = clashes.length) => {
    list.innerHTML = "";
    if (!total) {
      list.innerHTML = `<div class="meta" style="color:var(--status-good)">No hard clashes 🎉</div>`;
      return;
    }
    const shown = Math.min(clashes.length, LIST_CAP);
    const cap = shown < total;
    list.insertAdjacentHTML("beforeend",
      `<div class="section-title" style="margin:4px 0 2px">${cap ? `${shown} of ${total}` : total}`
      + ` clash${total === 1 ? "" : "es"} — click to inspect${cap ? " (list capped)" : ""}</div>`);
    clashes.slice(0, LIST_CAP).forEach((c, i) => {
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
      const r = await enqueueAndWait(d.api, pid, "clash_federated",
        { coordinate: true, create_topics: true }) as unknown as FederatedClashResult;
      const co = r.coordination;
      const bits = [`${r.count} clashes`, `${(r.disciplines ?? []).length} disciplines`];
      if (r.created_topics != null) bits.push(`${r.created_topics} issue(s)`);
      out.textContent = bits.join(" · ")
        + (co ? ` — ${co.new} new · ${co.active} active · ${co.resolved} resolved${co.reduction ? ` · ${Math.round(co.reduction * 100)}% ↓` : ""}` : "");
      renderClashes(r.clashes ?? [], r.count);
      const discs = r.disciplines ?? [];
      const tested: [string, string][] = [];
      for (let i = 0; i < discs.length; i++) {
        for (let j = i; j < discs.length; j++) {
          const a = discs[i], b = discs[j];
          if (a && b) tested.push([a, b]);
        }
      }
      // CLASH-TRUNC — the matrix is built from the server's per-pair tally over the WHOLE run, not
      // from `clashes`, which stops at the run's limit. Built from the page, a discipline pair whose
      // clashes all fall past that limit arrives with no evidence and `soft_clash.matrix` reports it
      // `clean`; with every pair declared tested the matrix then reads 100% coverage, nothing
      // untested — it states that it examined pairs it never saw. The engine keeps `untested` apart
      // from `clean` precisely to refuse that, and its caller made the refusal moot.
      const tally = r.pair_counts ?? [];
      lastMatrix = {
        disciplines: discs,
        // Declaring every pair tested is only honest when the evidence covers every clash. An older
        // server that truncated and sent no tally leaves a pair with no finding UNKNOWN, not clean,
        // so nothing is declared tested and those pairs report `untested` — the degradation the
        // engine already has a third state for.
        tested_pairs: (tally.length || !r.truncated) ? tested : [],
        findings: tally.length
          ? tally.map((t) => ({ discipline_a: t.discipline_a, discipline_b: t.discipline_b,
              count: t.count }))
          : (r.clashes ?? []).map((c) => ({
              discipline_a: c.a_model || c.a_class, discipline_b: c.b_model || c.b_class })),
      };
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
      }) as unknown as ClashResult;
      // CLASH-TRUNC: topics are minted for the first `limit` results only, so on a truncated run
      // "N clashes · M issue(s) created" understates without saying why. The cap is named.
      out.textContent = `${r.count} clashes · ${r.created_topics ?? 0} issue(s) created`
        + (r.truncated ? ` — capped: only the first ${(r.clashes ?? []).length} became issues` : "")
        + `. Open Issues to coordinate.`;
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
  panel.appendChild(cbtn("📐 Clearance rules (with basis)", () => void (async () => {
    try {
      const r = await d.api.clashClearanceRules(pid);
      showResult("Clearance rules (with basis)", (body) => {
        body.appendChild(resultNote(r.note, "ok"));
        for (const [cls, rule] of Object.entries(r.rules)) {
          body.appendChild(resultNote(
            `<b>${rule.label}</b> · ${rule.distance_m} m · <code>${rule.ifc_class || cls}</code> — ${rule.basis}`, ""));
        }
      });
    } catch (e) { toast(`clearance rules: ${(e as Error).message}`, "error"); }
  })()));
  panel.appendChild(cbtn("▦ Discipline-pair matrix", () => void (async () => {
    try {
      const m = await d.api.clashMatrix(pid, lastMatrix ?? {});
      showResult("Coordination matrix", (body) => {
        body.appendChild(resultNote(
          `<b>${m.coverage_pct}%</b> pair coverage · ${m.counts.clashes} clashes · ${m.counts.clean} clean · `
          + `<b>${m.counts.untested} untested</b> · coordinated: ${m.coordinated ? "yes" : "no"}`,
          m.counts.untested || m.counts.clashes ? "bad" : "ok"));
        body.appendChild(resultNote(m.note, ""));
        body.appendChild(kvTable(m.cells.map((c) => (
          { k: `${c.a} × ${c.b}`, v: `${c.state}${c.count ? ` (${c.count})` : ""}` }))));
      });
    } catch (e) { toast(`matrix: ${(e as Error).message}`, "error"); }
  })()));
  panel.appendChild(cbtn("📌 Open in Issues (BCF)", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
  panel.append(out, list);
}
