import type { ModuleBoard } from "../../api/types";

/**
 * BOARD-SHIPPED — the readings the kanban board had no fields for.
 *
 * All three were measured against a live route on the `rfi` register before a line of this existed.
 *
 * ## 1. The column head printed a page length
 *
 * 205 records in `draft`: the column serves the capped **200** cards and `counts.draft` is **205**.
 * The head rendered `(columns[state] ?? []).length`, so it said 200 with nothing to say five were
 * missing — and `counts` was undeclared on the client, so it *could not*. TRUNC-COUNTED again, on
 * the board shared across ~139 modules, and the engine's docstring had already written down the
 * consequence for its consumer: *"A column deeper than the cap shows count > len(cards)."*
 *
 * ## 2. A record in an undeclared state was invisible
 *
 * `columns` was keyed over the union of declared states and states the data actually holds, while
 * `states` was the declared list alone — so a board iterating `states` rendered no column for the
 * rest. Measured on three records with one moved to `retired`: **2 of 3** drawn, and the third was
 * invisible rather than merely uncounted. Reachable because workflows became configurable: drop a
 * state from a firm's workflow and the records sitting in it keep it.
 *
 * ## 3. The board offered the SHIPPED workflow, and the engine honours the CONFIGURED one
 *
 * `board()` called `get_module` where every other workflow consumer routes through
 * `workflow_config.effective`. With RFI overridden to `draft → answered (fast_answer)`:
 * dragging `draft → open` — which the board offered — posted `submit` and got **409 "action
 * 'submit' not allowed from state 'draft'"**, while `fast_answer` returned **200** and the board
 * offered no drag for it. *Every drag it offered failed and the only one that worked it refused
 * client-side.* The single-record route one screen over carries the rule verbatim: *"the actions
 * offered must be the ones the ENGINE will honour, or the UI shows a button that 409s."*
 *
 * Every function here returns PLAIN TEXT: `register.ts` interpolates into `innerHTML`.
 */

/**
 * The count for a column head: the TRUE total, with the page size when the column is deeper.
 *
 * Falls back to the card count when `counts` is absent, so a response from a server that predates
 * the field still renders — but it is the page length then, which is the defect, so the caller
 * shows `columnDepthNote` beside it.
 */
export function columnCount(b: ModuleBoard, state: string): string {
  const cards = (b.columns[state] ?? []).length;
  const total = b.counts?.[state];
  if (total == null) return String(cards);
  return total > cards ? `${cards} of ${total}` : String(total);
}

/** `title` for that head — says which number is which, since `200 of 205` is terse. */
export function columnCountTitle(b: ModuleBoard, state: string): string {
  const cards = (b.columns[state] ?? []).length;
  const total = b.counts?.[state] ?? cards;
  if (total <= cards) return `${total} record(s) in ${state}, all shown.`;
  return `${total} record(s) in ${state}; this column shows the newest ${cards}. The server caps `
    + `each column at ${b.per_state_cap ?? cards} cards — open the register to see them all.`;
}

/** One line when any column is deeper than its cap, naming which. `null` when none is. */
export function boardDepthNote(b: ModuleBoard): string | null {
  if (!b.counts) return null;
  const deep = b.states
    .map((s) => ({ s, cards: (b.columns[s] ?? []).length, total: b.counts![s] ?? 0 }))
    .filter((x) => x.total > x.cards)
    .sort((a, b2) => (b2.total - b2.cards) - (a.total - a.cards));
  if (!deep.length) return null;
  const named = deep.slice(0, 3).map((x) => `${x.s} (${x.cards} of ${x.total})`).join(", ");
  const more = deep.length > 3 ? ` and ${deep.length - 3} more` : "";
  return `Some columns are deeper than the board shows: ${named}${more}. The counts in the heads `
    + "are the true totals; the cards are the newest page.";
}

/**
 * The states the module does not declare but the data holds, or `null` when there are none.
 *
 * Named rather than silently rendered: a column outside the firm's workflow is a data-quality
 * finding — usually a state that was removed from the workflow while records still sat in it.
 */
export function extraStatesNote(b: ModuleBoard): string | null {
  const extra = b.extra_states ?? [];
  if (!extra.length) return null;
  return `${extra.length} state(s) hold records but are not in this module's workflow: `
    + `${extra.join(", ")}. They get a column so nothing is hidden, but no transition leads out of `
    + "them — move those records from the register, or restore the state to the workflow.";
}

/** Says when the drag targets come from this project's own workflow rather than the shipped one. */
export function workflowBasisNote(b: ModuleBoard): string | null {
  if (!b.workflow_overridden) return null;
  return "This project overrides the shipped workflow, so the drags offered here are its own "
    + "transitions — the same ones the server will honour.";
}

/** Why a drag was refused, said in terms of the workflow actually in force. */
export function noTransitionNote(b: ModuleBoard, from: string, to: string): string {
  const base = `No direct transition ${from} → ${to}`;
  const out = b.transitions.filter((t) => t.from === from).map((t) => t.to);
  const where = b.workflow_overridden ? "this project's workflow" : "the module's workflow";
  if (!out.length) return `${base}: ${where} leads nowhere out of ${from}.`;
  return `${base}. From ${from}, ${where} allows: ${[...new Set(out)].join(", ")}.`;
}
