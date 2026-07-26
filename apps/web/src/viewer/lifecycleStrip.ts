/**
 * R26-INSPECTOR — the six-state lifecycle strip, rendered.
 *
 * **designed · checked · priced · scheduled · installed · verified**, left to right, for the selected
 * element. Every one of those facts is already held against the *same GlobalId*; until now they lived
 * in six panels across different workspaces, so the one genuinely unusual thing about this product —
 * that all of it shares one key — was invisible in the interface.
 *
 * The rendering carries the engine's three rules rather than flattening them:
 *
 * * **`unknown` looks different from `none`.** Not a paler shade of failure — a distinct, neutral
 *   state that says nobody asked. A strip that colours the unexamined as failed is one people learn
 *   to ignore, and then the strip is worse than nothing because it looks like it was checked.
 * * **`reached` is contiguous, and the strip says so.** A later state can be individually true while
 *   the element has only *reached* an earlier one; showing the tick without the distinction would let
 *   the strip overstate progress.
 * * **An inconsistency is shown, not smoothed.** "Verified but never installed" is a real data
 *   defect, and hiding it destroys the only signal that says so.
 */
import type { LifecycleStrip, StripStatus } from "../api/types";

export type { LifecycleStrip, StripState, StripStatus } from "../api/types";

/** Same tiny builder `propsView` uses: pure DOM construction, so there is no injection surface. */
function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

const MARK: Record<StripStatus, string> = { done: "●", none: "○", unknown: "–" };

/** What each status *means*, in the tooltip — the distinction is the whole point of the strip. */
const MEANS: Record<StripStatus, string> = {
  done: "Complete",
  none: "Not done — the platform checked and the answer is no",
  unknown: "Not known — the platform could not check this. Different from 'no'.",
};

export function buildLifecycleStrip(data: LifecycleStrip): HTMLElement {
  const root = el("div", "lcstrip");

  const head = el("div", "lcstrip-head");
  head.append(el("span", "lcstrip-title", "Lifecycle"));
  // `reached` is the honest summary: the furthest CONTIGUOUS state. Reporting `done_count` alone
  // would let five scattered ticks read as near-complete.
  const reached = data.reached
    ? (data.states.find((s) => s.key === data.reached)?.label ?? data.reached)
    : "not in the model";
  head.append(el("span", "lcstrip-reached", `reached ${reached}`));
  if (data.unknown_count > 0) {
    const u = el("span", "lcstrip-unk", `${data.unknown_count} unknown`);
    u.title = "States the platform could not check. Unknown is not the same as no.";
    head.append(u);
  }
  root.append(head);

  const track = el("div", "lcstrip-track");
  const reachedAt = data.reached ? data.states.findIndex((s) => s.key === data.reached) : -1;
  data.states.forEach((s, i) => {
    const pill = el("div", `lcstrip-pill is-${s.status}`);
    // A state that is individually true but sits PAST the contiguous reach is marked, so a tick can
    // never be read as progress the element has not actually made.
    if (s.status === "done" && i > reachedAt) pill.classList.add("is-detached");
    pill.append(el("span", "lcstrip-mark", MARK[s.status]));
    pill.append(el("span", "lcstrip-label", s.label));
    if (s.detail) pill.append(el("span", "lcstrip-detail", s.detail));
    pill.title = [s.means, MEANS[s.status], s.advance ? `→ ${s.advance}` : ""]
      .filter(Boolean).join("\n");
    pill.dataset.state = s.key;
    pill.dataset.status = s.status;
    track.append(pill);
  });
  root.append(track);

  for (const msg of data.inconsistencies) {
    const w = el("div", "lcstrip-bad");
    w.textContent = `⚠ ${msg}`;
    root.append(w);
  }

  if (data.next?.advance) {
    const n = el("div", "lcstrip-next");
    const label = data.states.find((s) => s.key === data.next!.key)?.label ?? data.next.key;
    n.textContent = `Next — ${label}: ${data.next.advance}`;
    root.append(n);
  }
  return root;
}
