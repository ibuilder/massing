/** Saved views: whose they are, and what may be done to them.
 *
 *  `GET/POST /projects/{pid}/modules/{key}/views` return `scope`, `owner` and `mine` on every row,
 *  and `SavedViewDef` declared none of them. The server's own comment says why `mine` is sent rather
 *  than inferred from `owner == me` — *"the two can disagree the moment a display name is not the
 *  identity key … and the UI uses it to decide whether to offer Delete, which must match what the
 *  server will actually allow"*. The UI could not read it, so it did not match, and the mismatch
 *  compounded three ways:
 *
 *  * the dropdown showed a colleague's shared report identically to your own private filter;
 *  * the delete picker offered every listed view, including ones `DELETE` refuses -- picking one
 *    returned `deleted: false`, which the UI reports as *"was already gone — refreshing the list"*,
 *    after which it is still there, because it was never gone and was never yours;
 *  * the confirmation said *"Saved views are yours alone, so this removes it only for you"*, which
 *    stopped being true the day sharing shipped (R22-REPORT-BUILDER item 4).
 *
 *  And `saveView` sent no `scope` at all, so the server's `default="private"` decided for every view
 *  the web UI has ever created: the sharing half was reachable only from outside this app.
 *
 *  Pure, so all of that is testable without a register on screen.
 */
import type { SavedViewDef } from "../../api/client";

/** How a view reads in the dropdown — its name, plus whose it is when that is not obvious. */
export function viewLabel(v: SavedViewDef): string {
  if (!v.mine) return `${v.name} · shared by ${v.owner}`;
  return v.scope === "project" ? `${v.name} · shared` : v.name;
}

/** The views this user may actually delete — the server refuses the rest, so offering them is how a
 *  refusal gets reported to the user as "already gone". */
export function deletableViews(views: SavedViewDef[]): SavedViewDef[] {
  return views.filter((v) => v.mine);
}

/** What deleting this view really does. A shared view is not "yours alone", and saying so to the one
 *  person who can remove it for the whole project is the wrong moment to be reassuring. */
export function deleteWarning(v: SavedViewDef): string {
  const who = v.scope === "project"
    ? "This view is SHARED with the project, so deleting it removes it for everyone who uses it."
    : "This view is yours alone, so this removes it only for you.";
  return `${who} The records it filters are not touched.\n\nThere is no undo — the filter and sort `
    + "would have to be set up again.";
}

/**
 * The scope a free-text "share with the project?" answer asks for.
 *
 * Anything but an explicit yes stays private. A saved view becoming visible to the whole project is
 * not a good default for an ambiguous answer, an empty one, or a dismissed prompt — the cost of
 * guessing wrong is asymmetric, and only one direction of it is recoverable in private.
 */
export function scopeFromAnswer(answer: string | undefined): "private" | "project" {
  return (answer ?? "").trim().toLowerCase().startsWith("y") ? "project" : "private";
}

/**
 * The view a free-text "which number?" answer names, or `undefined` for an answer that names none.
 *
 * `parseInt` returns NaN for `"abc"` and **3** for `"3abc"`; both have to be refused, rather than
 * deleting the third view because the string happened to start with a digit. `Number` rejects the
 * second outright, and `Number.isInteger` rejects `"2.5"` and the empty string.
 *
 * WHY THE CONTROL IS A PICK-THEN-CONFIRM AND NOT AN ✕ ON THE SELECT (moved here from the register,
 * whose extraction ratchet is what asked for it): applying a view re-renders the whole toolbar, so
 * the select never HOLDS a selection and a "delete the selected one" button would have nothing to
 * read. The confirm step is what turns a number back into a name — agreeing to delete "3" is not
 * consent, agreeing to delete "Overdue — mine" is.
 */
export function pickedView(answer: string | undefined, own: SavedViewDef[]): SavedViewDef | undefined {
  const n = Number((answer ?? "").trim());
  return Number.isInteger(n) ? own[n - 1] : undefined;
}
