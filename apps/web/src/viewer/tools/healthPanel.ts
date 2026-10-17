import type { ModelHealth } from "../../api/model";
import { escapeHtml } from "../../ui/feedback";
import { healthCoverage, healthLensValue, healthNote, healthThin, healthUnscored,
  healthWeightBasis } from "./healthCoverRead";

/**
 * HEALTH-WEIGHT-COVER — the Model Health result body, out of `qaSection.ts`.
 *
 * **It left because of the extraction ratchet, and that is the right reason.** HEALTH-WEIGHT-COVER
 * added 13 lines to `qaSection.ts`, which sits under a one-way ratchet in
 * `services/api/test_file_sizes.py` at 1,229 — so the build went red and I had pushed it, because I
 * ran that gate earlier in the session and not again after touching the file. *A gate run once is a
 * gate for the state it was run against.* The ratchet's own recorded precedent is that the file
 * gives up lines rather than the pin moving — "this file was exactly on its pin, so the explanation
 * of why would not fit until the window left" — and the Model Health body is the right thing to
 * move, because the readings it renders already live next door in `healthCoverRead.ts`.
 *
 * This file opens no `section("<key>"` of its own, so in `apps/web/src/viewer/toolsSplit.test.ts`'s
 * `SECTION_SOURCES` it is attributed to whichever file precedes it and must stay inside the `qa`
 * run — the same constraint that list already records twice, for `repairPanel.ts` and
 * `projectSetupPanel.ts`. *A list that looks like a set can still be an order.*
 */

const DOT: Record<string, string> = { good: "🟢", warn: "🟡", poor: "🔴", na: "⚪" };

/** The tones `ui/result`'s note helper accepts. Spelled as the union rather than `string` so a
 *  caller passing a tone the helper does not know is a type error here, not a silent no-op. */
type Tone = "" | "ok" | "warn" | "bad";

export interface HealthBodyDeps {
  /** `ui/result`'s note helper. Takes HTML, so every reading is escaped on the way in. */
  resultNote: (html: string, tone?: Tone) => HTMLElement;
  kvTable: (rows: { k: string; v: string }[]) => HTMLElement;
}

/**
 * Render the composite into a `showResult` body.
 *
 * The coverage lines come from `healthCoverRead.ts` rather than from a caption written here: the
 * caption that used to live in this block named FOUR lenses where the engine has five, and reported
 * the scored COUNT where the composite's basis is a weight.
 */
export function renderHealthBody(body: HTMLElement, r: ModelHealth, d: HealthBodyDeps): void {
  const tone: Tone = r.overall_score == null ? "" : r.overall_score >= 80 ? "ok" : r.overall_score < 50 ? "bad" : "";
  body.appendChild(d.resultNote(r.overall_score != null
    ? `Composite <b>${r.overall_score}/100</b> — <b>${r.band}</b>.`
    : "No model-quality inputs yet — load a model and log coordination / verification to score.", tone));
  const thin = healthThin(r);
  if (thin) body.appendChild(d.resultNote(escapeHtml(thin), "bad"));
  body.appendChild(d.kvTable(r.lenses.map((l) => ({
    k: `${DOT[l.status] || "⚪"} ${l.label}`,
    v: escapeHtml(healthLensValue(l)),
  }))));
  // `textContent`, not `innerHTML`: these four are server text and engine sentences, and
  // `apps/web/src/ui/innerHtmlGuard.test.ts` is the ratchet that would refuse the alternative.
  for (const line of [healthCoverage(r), healthUnscored(r), healthNote(r), healthWeightBasis(r)]) {
    if (!line) continue;
    const note = document.createElement("div");
    note.className = "meta";
    note.style.cssText = "margin-top:8px;font-size:11px";
    note.textContent = line;
    body.appendChild(note);
  }
}

/** The one-line status the rail's `out` slot shows beside the button. */
export function healthStatusLine(r: ModelHealth): string {
  return r.overall_score != null ? `health ${r.overall_score} · ${r.band}` : "no model data";
}
