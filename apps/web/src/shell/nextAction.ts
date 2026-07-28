/**
 * NEXT BEST ACTION — the single thing to do now, in the header.
 *
 * The other half of "work comes to you". The room tabs say *how much* is in your court; this says
 * *what to do about it*, as one button with one verb.
 *
 * `nextBestAction()` in `portal/panels/pulse.ts` already does the ranking and is tested. This module
 * is the adapter — queue shape in, header button out — plus the two judgement calls that adapter has
 * to make: which action a caller can actually run, and how a due date becomes urgency.
 */
import { type ActionCandidate, nextBestAction } from "../portal/panels/pulse";
import type { WorkQueue } from "../api/types";

/** Days from today to `due`, negative when overdue. `null` when there is no date to reason about. */
export function daysUntil(due: string | null | undefined, now = new Date()): number | null {
  if (!due) return null;
  const d = new Date(due);
  if (Number.isNaN(d.getTime())) return null;
  // Compare calendar days, not instants: an item due "today" at 09:00 is not overdue at 17:00, and
  // telling somebody they are late for something due today is how a queue loses credibility.
  const a = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const b = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.round((a - b) / 86_400_000);
}

/**
 * Flatten a queue into ranked candidates.
 *
 * **Only items with an action the caller can actually run.** `blocked_actions` are gated behind
 * required fields — offering one as *the* next best action sends somebody to a form and calls it a
 * recommendation. An item you cannot act on is not an action.
 */
export function candidatesFrom(queue: WorkQueue | null | undefined, now = new Date()): ActionCandidate[] {
  const out: ActionCandidate[] = [];
  for (const bucket of queue?.buckets ?? []) {
    for (const it of bucket.items ?? []) {
      const verb = (it.actions ?? [])[0];
      if (!verb) continue;
      const d = daysUntil(it.due, now);
      out.push({
        ref: it.ref,
        title: it.title || it.module_name || it.ref,
        verb,
        overdueDays: d != null && d < 0 ? -d : null,
        dueInDays: d,
      });
    }
  }
  return out;
}

/**
 * The server's action *id* made presentable: `close` → `Close`, `request_info` → `Request info`.
 *
 * The id is an identifier and the label is English; conflating them put "close ACT-001" in the
 * header, which reads like a typo rather than an instruction. Capitalising here rather than in the
 * renderer keeps the id intact for anything that dispatches on it — the display name is a view
 * concern, and the id must stay exactly what the server said.
 */
export function verbLabel(verb: string): string {
  const words = String(verb || "").replace(/[_-]+/g, " ").trim();
  if (!words) return "";
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export interface HeaderAction {
  ref: string;
  /** "Answer RFI-118" — verb first, because the verb is the point. */
  label: string;
  /** "Overdue 1d" / "Due today" / "Due in 3d", or null when there is no date. */
  when: string | null;
  urgent: boolean;
  item: ActionCandidate;
}

/** The one action, or null when there is genuinely nothing to do. */
export function headerAction(queue: WorkQueue | null | undefined, now = new Date()): HeaderAction | null {
  const pick = nextBestAction(candidatesFrom(queue, now));
  if (!pick) return null;
  const d = pick.dueInDays;
  const when = d == null ? null
    : d < 0 ? `Overdue ${-d}d`
    : d === 0 ? "Due today"
    : `Due in ${d}d`;
  return {
    ref: pick.ref,
    label: `${verbLabel(pick.verb)} ${pick.ref}`,
    when,
    urgent: d != null && d <= 0,
    item: pick,
  };
}

/**
 * Render into `host`, or clear it.
 *
 * Renders **nothing** when there is no action — an empty queue should leave the header quiet, not
 * display "Nothing to do", which is a claim that ages badly between polls and trains people to stop
 * reading the one place urgency lives.
 */
export function renderHeaderAction(
  host: HTMLElement,
  action: HeaderAction | null,
  onPick: (a: HeaderAction) => void,
): void {
  host.innerHTML = "";
  host.hidden = !action;
  if (!action) return;

  const cap = document.createElement("span");
  cap.className = "nba-cap";
  cap.textContent = "NEXT BEST ACTION";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "nba-btn" + (action.urgent ? " nba-urgent" : "");
  btn.dataset.ref = action.ref;
  // textContent, not innerHTML: ref and title are record data, and this is a header that renders on
  // every page — exactly the js/xss-through-dom path this repo has a standing rule about.
  btn.textContent = action.when ? `${action.label} — ${action.when} →` : `${action.label} →`;
  btn.title = action.item.title;
  btn.onclick = () => onPick(action);

  host.append(cap, btn);
}
