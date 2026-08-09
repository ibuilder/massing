/**
 * R36-DRAWINGS-RETURN — when a control moves you to another workspace, leave a way back.
 *
 * ── WHAT WAS ACTUALLY WRONG, MEASURED 2026-08-09 ──────────────────────────────────────────────
 * The roadmap entry said neither Drawings nor Specs had a return affordance or visible room tabs.
 * Checked in the running app, three of those four claims were already false:
 *
 *   Drawings : room tabs 622×37 visible · Design tab present · "← Back to Model" present (111×23)
 *   Specs    : room tabs 510×37 visible · Design tab present · NO return control
 *
 * So the real defect was an ASYMMETRY, not an absence. And the reason Specs missed out is worth
 * writing down, because it is not an oversight anyone could have spotted by reading the code: the
 * trigger was `DEAD_END_WS`, a set of *workspaces*, and **Specs is not a workspace**. `openSpecs()`
 * calls `setWorkspace("design")` and then opens a module inside it. Design is a perfectly normal
 * workspace with tabs, so it is not a dead end — but a user who pressed **Specs** on the model rail
 * still lands somewhere with no route back to the model they were just in. Measured: of the seven
 * visible controls there mentioning "model" or "3D", one is the Design tab they are already on, two
 * are analysis modules, and four are project-home onboarding cards — *start over*, not *go back*.
 *
 * The rule is therefore about the JOURNEY, not the destination: **a control that carries you out of
 * your workspace owes you a return.** That covers Drawings (rail → its own workspace) and Specs
 * (rail → a module inside another workspace) with one idea instead of a list to keep up to date.
 *
 * ── WHY THIS IS A MODULE AND NOT SIX LINES IN main.ts ────────────────────────────────────────
 * `wsReturn.test.ts` has existed since the original item shipped, with **no `wsReturn.ts` beside
 * it.** It reproduced `main.ts`'s logic in the test file — including its own hand-written
 * `DEAD_END_WS = new Set(["drawings"])` — and said so, reasoning that importing `main.ts` boots the
 * whole shell. That reasoning was sound and the consequence was not: the test asserted a COPY, so it
 * passed while the real set was missing the case its own docstring described as broken
 * (*"and Specs behaves the same"*). A suite that cannot reach the failure is not covering it —
 * see the standing note on tests that assert against a reproduction.
 *
 * Everything here is pure and DOM-free so both the app and the test can use the same functions.
 */

/**
 * Workspaces that own no rail and no tabs of their own, so arriving is always a trap.
 *
 * Kept — a workspace can be a dead end however you reach it, including from the workspace bar, and
 * that is independent of the journey rule below.
 */
export const DEAD_END_WS: ReadonlySet<string> = new Set(["drawings"]);

/** How the user got to this workspace. `jump` = a control elsewhere sent them (a rail launch). */
export type Arrival = "jump" | "nav";

/**
 * Should this workspace show a return control?
 *
 * True when the destination is a dead end, OR when a control carried the user here from a different
 * workspace. The second clause is what Specs needed and what no set of destination names could have
 * expressed.
 */
export function offersReturn(dest: string, origin: string | null, arrival: Arrival): boolean {
  if (DEAD_END_WS.has(dest)) return true;
  return arrival === "jump" && !!origin && origin !== dest;
}

/**
 * Where "back" goes: the workspace actually left, else the model.
 *
 * Not a hard-coded home. Someone who reached Drawings from Design should land in Design; sending
 * everyone to one destination is the wrong-but-plausible behaviour that teaches people to stop
 * trusting a control — landing somewhere unexpected is a second trap, not an escape.
 */
export function returnTarget(origin: string | null, dest: string): string {
  return origin && origin !== dest ? origin : "model";
}

/**
 * The control's text. Reads the label from the tab strip that already names the workspace rather
 * than a second lookup table — a duplicated label list is how the rail once rendered `undefinedView`.
 * Falls back to a capitalised key so an unlabelled workspace still reads as a place, not a slug.
 */
export function returnLabel(target: string, lookup: (ws: string) => string | null): string {
  const named = (lookup(target) || "").trim();
  const label = named || target.charAt(0).toUpperCase() + target.slice(1);
  return `← Back to ${label}`;
}

/** Hover text: says where it goes AND why it is there, so the control explains its own presence. */
export function returnTitle(target: string, dest: string, lookup: (ws: string) => string | null): string {
  const name = (t: string) => (lookup(t) || "").trim() || t.charAt(0).toUpperCase() + t.slice(1);
  return `Return to ${name(target)} — where you opened ${name(dest)} from`;
}
