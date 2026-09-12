/**
 * SCENARIO-SOURCES — renders a scenario's assumption provenance in a dialog.
 *
 * The rules live in `scenarioSources.ts` and are tested there; this file is the DOM and the fetch.
 * Before it existed, `GET /proforma/scenarios/{sid}/provenance` had no client caller: the engine that
 * says which deal assumptions carry a document source, and names the ones that do not, had no way in.
 */
import type { ApiClient } from "../../api/client";
import { esc } from "../../ui/charts";
import { modalShell } from "../../ui/modal";

import {
  type ScenarioProvenance,
  actionNote, actions, headline, headlineNote, staleness, stalenessNote, summary,
} from "./scenarioSources";

const row = (label: string, value: string, muted = false) =>
  `<tr style="border-top:1px solid var(--line)"><td style="padding:3px 8px${muted ? ";color:var(--muted)" : ""}">${label}</td>`
  + `<td style="padding:3px 8px;text-align:right">${value}</td></tr>`;

/**
 * The named list — the part the engine's own docstring says is what gets fixed.
 *
 * Rendered even when long, because a truncated list of gaps is the shape that gets quoted as "only a
 * few" — the same failure as a coverage figure with no gaps named.
 */
function actionList(p: ScenarioProvenance): string {
  const rows = actions(p);
  if (!rows.length) return "";
  const li = rows.map((a) =>
    `<tr style="border-top:1px solid var(--line)">`
    + `<td style="padding:3px 8px;font-family:var(--mono,monospace);font-size:12px">${esc(a.path)}</td>`
    + `<td style="padding:3px 8px;color:var(--muted);font-size:12px">${esc(actionNote(a.kind))}`
    + `${a.alsoMalformed ? " <b>(and the recorded entry is unreadable)</b>" : ""}</td></tr>`).join("");
  return `<div class="section-title" style="margin-top:14px">To fix — ${rows.length} item(s)</div>`
    + `<div style="overflow:auto"><table class="mini-table" style="width:100%"><tbody>${li}</tbody></table></div>`;
}

/**
 * Open the provenance dialog for one saved scenario.
 *
 * **Loads WITHOUT a revision on purpose.** The engine computes citation staleness only when the
 * caller supplies one, and this client has no authoritative "current revision" to invent — so the
 * first render reports currency as *not checked* rather than as zero stale, and offers the reader the
 * input that would actually check it. *A screen that cannot perform a check must say it did not
 * perform it, not report the check's empty result.*
 */
export async function scenarioSourcesModal(api: ApiClient, sid: string, name?: string): Promise<void> {
  const { card, close, ready } = modalShell(`Assumption sources — ${name ?? "scenario"}`, 620);
  const body = document.createElement("div");
  body.className = "meta";
  body.textContent = "Tracing this scenario's assumptions…";
  card.appendChild(body);

  const render = (p: ScenarioProvenance, revision: string) => {
    const s = summary(p);
    const h = headline(p);
    const good = h === "whole";
    body.className = "";
    body.innerHTML =
      `<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:baseline">`
      + `<div style="font-size:20px;font-weight:600">${s.coverage}%</div>`
      + `<div class="meta">${s.cited} of ${s.material} material assumptions carry a source</div></div>`
      // The verdict sits ABOVE the numbers: a coverage figure read without it is the thing the
      // engine's docstring warns gets quoted in a memo.
      + `<div style="margin:10px 0;padding:8px 10px;border-radius:6px;font-size:13px;`
      + `border:1px solid ${good ? "var(--status-good)" : "var(--status-crit)"}">`
      + `${good ? "✓ " : "⚠ "}${esc(headlineNote(h, p))}</div>`
      // Currency is its own line, always, because coverage does not imply it.
      + `<div class="meta" style="font-size:12px">Citation currency: ${esc(stalenessNote(staleness(p), p))}</div>`
      + `<div style="overflow:auto;margin-top:10px"><table class="mini-table" style="width:100%"><tbody>`
      + row("Material assumptions", String(p.material_count))
      + row("Sourced", String(p.cited_count))
      + row("No source recorded", String(p.uncited_count))
      + row("Recorded but unreadable", String(p.malformed_citation_count))
      + row("Citations against a path that is not an assumption", String(p.orphaned_sources.length), true)
      + `</tbody></table></div>`
      + actionList(p)
      + `<div class="meta" style="margin-top:10px;font-size:12px">${esc(p.basis)}</div>`
      + `<div class="meta" style="margin-top:4px;font-size:12px">${esc(p.note)}</div>`
      + `<div style="display:flex;gap:6px;justify-content:flex-end;margin-top:12px;align-items:center">`
      + `<label class="meta" style="font-size:12px">Check citations against revision:</label>`
      + `<input id="sc-prov-rev" class="tool-input" style="width:140px" value="${esc(revision)}" `
      + `placeholder="e.g. rev-7">`
      + `<button id="sc-prov-check" class="tool-btn">Check</button>`
      + `<button id="sc-prov-close" class="tool-btn">Close</button></div>`;

    (document.getElementById("sc-prov-close") as HTMLButtonElement | null)?.addEventListener("click", close);
    const check = document.getElementById("sc-prov-check") as HTMLButtonElement | null;
    check?.addEventListener("click", () => {
      const rev = (document.getElementById("sc-prov-rev") as HTMLInputElement | null)?.value.trim() ?? "";
      if (!rev) return;
      check.disabled = true;
      void api.scenarioProvenance(sid, rev)
        .then((next) => render(next as ScenarioProvenance, rev))
        .catch((e: unknown) => {
          const note = document.createElement("div");
          note.className = "meta";
          note.style.color = "var(--status-crit)";
          note.textContent = `Could not re-check: ${(e as Error).message}`;
          body.appendChild(note);
          check.disabled = false;
        });
    });
  };

  try {
    render(await api.scenarioProvenance(sid) as ScenarioProvenance, "");
  } catch (e) {
    body.className = "meta";
    body.textContent = `Could not trace this scenario: ${(e as Error).message}`;
  } finally {
    ready();
  }
}
