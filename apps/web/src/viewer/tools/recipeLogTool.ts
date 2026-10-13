/** RECIPE-LOG-DARK — the eager half of the log reader: the button, and nothing else.
 *
 * The reader's body is `./recipeLogView`, behind `await import()`, and that module's header carries
 * the narrative — what was dark, why four routes were silent in four different ways, and the two
 * unsound claims in `replayable` that wiring it exposed.
 *
 * **What is left here is the part that cannot be lazy**: the button is appended when the tools panel
 * is BUILT, so it must exist before any click. `viewer/tools/*` is the app-shell chunk and
 * `apps/web/scripts/bundle-budget.mjs` caps that shell at 225 KB Brotli; shipping the reader whole
 * in it took the shell to **226.2 KB**, which CI caught and I had not, because I ran the budget's
 * TESTS (`npx vitest run src/tooling`, 43 of them, green) and not the budget (`npm run budget`).
 * *A test about a budget is not the budget.*
 *
 * This file also makes the one decision the view cannot: whether to open an overlay at all. An
 * unreadable log is a 409 — `recipe_log.LogUnreadable`, the file exists and does not parse, which is
 * deliberately distinct from "no log yet" — and that is a toast, not an empty reader with an error
 * inside it.
 */
import type { RecipeLogPage } from "../../api/types";
import { showResult } from "../../ui/result";
import type { RecipeLogDeps } from "./recipeLogView";

export type { RecipeLogDeps };

/**
 * Named `recipeLogButton` and INLINED into its caller's `append`, for the reason `macroButton`
 * records: `sectionButtonsWired.test.ts` derives its population from `export function <name>Button(`
 * and asks that the call appear inside an `append`, because a control built into a local and never
 * appended is the silent-inert failure that gate is named for.
 */
export function recipeLogButton(d: RecipeLogDeps): HTMLButtonElement {
  const btn = d.toolBtn2("⟲ Edit-recipe log (provenance & replay)", async () => {
    let page: RecipeLogPage;
    try { page = await d.api.recipeLog(d.pid); }
    catch (e) { d.notify(`recipe log unavailable: ${(e as Error).message}`, "error"); return; }
    // Imported AFTER the fetch succeeds, so a 409 costs no chunk download; and awaited before
    // `showResult` so the overlay is never opened around a module that failed to load.
    const view = await import("./recipeLogView");
    showResult("Edit-recipe log", (body) => { view.renderRecipeLog(body, d, page); });
  });
  btn.title = "Read the edit-recipe log — recipe, parameters, actor and time per edit — export it as "
    + "a provenance artifact, diff two runs of a recipe, and build a replay plan. Entries whose "
    + "parameters were elided for size are marked, and a replay of one is refused rather than faked.";
  return btn;
}
