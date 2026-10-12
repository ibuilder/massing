import type { ApiClient } from "../../api/client";
import type { EditMacro, EditMacroParam } from "../../api/types";
import { askText } from "../../ui/prompt";
import { escapeHtml } from "../../ui/feedback";
import { kvTable, resultNote, showResult } from "../../ui/result";

/**
 * MACRO-DARK — the door onto RECIPE-MACROS, which shipped complete and unreachable.
 *
 * A macro is a saved, parameterized **chain** of authoring recipes that applies as ONE GUID-stable
 * version: one entry in the edit history, so it undoes as a single step. `services/api/src/aec_api/macros.py`
 * validates every step's recipe name against the edit engine's registry before storing, caps what one
 * save can park, and exposes `expand()` as a **pure, model-free preview** — its docstring says in so
 * many words that it exists *"so a client can preview/validate before it ever touches the model"*.
 * Four routes, a starter macro, an optimistic lock, and `apps/web/src/api/clientCallers.test.ts` froze
 * all four client methods as called by nothing. The reuse multiplier the whole edit-recipe spine was
 * built for had no button.
 *
 * ## Three things this had to get right, and each is a test below
 *
 * **① The starter set is not a saved library.** `GET /macros` falls back to `STARTER_MACROS` and says
 * so in `seeded`. A screen that lists the fallback without naming it tells a firm their standards are
 * captured when nothing has been saved — the empty-versus-absent confusion this branch has now
 * corrected repeatedly, and the API already carried the field that distinguishes them.
 *
 * **② Argument TYPE is load-bearing, and only the declaration can supply it.** `_subst` preserves the
 * raw type when a param value is exactly `"${name}"`, so the starter bay's `"point": ["${x0}",
 * "${y}"]` needs **numbers**: send `"6"` and the recipe receives a string where it wants a coordinate.
 * `askText` returns a string, so every value is coerced against the declared `default`'s type — and
 * **never by guessing from the text**, because the same "looks numeric" rule that correctly types a
 * coordinate would turn the storey name `"2"` into the number 2. A param with no typed default
 * therefore goes as a string; that limit is stated here and visible in the preview.
 *
 * **③ A blank answer OMITS the key rather than sending a blank.** The server's `expand()` fills
 * omitted params from their declarations, so defaulting on the client would be a second answer to one
 * question — and `JSON.stringify` turns an unparseable `Number("")` into `null`, which the engine
 * would read as a supplied value. Refusing NaN is not defensive; it is the difference between an
 * error and a silent `null`.
 *
 * ## The preview is the feature, not a courtesy
 *
 * Nothing is applied until the expanded step list has been rendered and a second button pressed. The
 * steps are shown as JSON **on purpose**: quoting is how a mistyped argument becomes visible —
 * `["6", 0]` and `[6, 0]` are the defect in ② and its absence, and no prose caveat substitutes for
 * seeing it.
 */
export interface MacroDeps {
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  pid: string;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  waitForPublish: (pid: string, onTick?: (s: string, elapsed: string | null) => void) => Promise<string>;
  loadProjectModel: () => Promise<boolean>;
}

/** What the run route answers with — `apply_recipes`' result plus the router's two additions. */
export interface MacroRunResult {
  /** Per step, in order. `changed` is whatever that recipe returns — a count, a GUID, a list — so it
   *  is `unknown` by necessity rather than by erasure: five recipes answer five shapes. The
   *  distinction matters because the erasure this file's sibling `mepTrayFill` carried removed fields
   *  that DID have one shape, and removed them from every audit at the same time. */
  steps: { recipe: string; changed: unknown }[];
  step_count: number;
  /** The new source IFC path the chain was written to. */
  out: string;
  macro: string;
  publish?: string;
}

/**
 * Is this library the project's own, or the starter set standing in for one?
 *
 * Returned rather than appended so the distinction is a value a test can assert, not a side effect
 * to go looking for in a DOM.
 */
export function macroLibraryNote(seeded: boolean, count: number): { html: string; kind: "ok" | "warn" | "" } {
  if (!count) {
    return { html: "<b>No macros</b> — this project's library is empty and the starter set is not "
                 + "available either, which should not happen; check the API.", kind: "warn" };
  }
  if (seeded) {
    return { html: `<b>Starter set</b> — ${count} template(s). <b>Nothing has been saved for this `
                 + "project</b>, so these are the shipped examples, not your firm's standards. "
                 + "Running one is safe; editing the library is a separate step.", kind: "warn" };
  }
  return { html: `<b>${count} saved macro(s)</b> for this project.`, kind: "ok" };
}

/**
 * One parameter's value, typed from its DECLARATION.
 *
 * `raw` is what the user typed, or `null` if they cancelled (which the caller handles before here).
 * An empty answer returns `{ omit: true }` so the server's own default applies — see ③ above.
 */
export function coerceArg(raw: string, decl: EditMacroParam):
  { omit: true } | { value: unknown } | { why: string } {
  const txt = raw.trim();
  const dflt = decl.default;
  if (!txt) {
    if (decl.required) return { why: `${decl.label || decl.name} is required` };
    return { omit: true };
  }
  if (typeof dflt === "number") {
    const n = Number(txt);
    // NOT a stylistic guard: `JSON.stringify({x: NaN})` emits `{"x":null}`, so an unparseable
    // number does not fail — it arrives at the engine as a supplied null.
    if (!Number.isFinite(n)) return { why: `${decl.label || decl.name}: "${txt}" is not a number` };
    return { value: n };
  }
  if (typeof dflt === "boolean") {
    const t = txt.toLowerCase();
    if (["true", "1", "yes", "y"].includes(t)) return { value: true };
    if (["false", "0", "no", "n"].includes(t)) return { value: false };
    return { why: `${decl.label || decl.name}: expected true or false, got "${txt}"` };
  }
  // No typed default — the declaration cannot say what this should be, so it goes as typed. A macro
  // author who needs a number declares a numeric default; guessing from the text would turn the
  // storey name "2" into the number 2.
  return { value: txt };
}

/** Collect the answers into the args body, or the first reason it cannot be built. */
export function macroArgs(params: readonly EditMacroParam[], answers: readonly string[]):
  { args: Record<string, unknown> } | { why: string } {
  const args: Record<string, unknown> = {};
  for (let i = 0; i < params.length; i++) {
    const r = coerceArg(answers[i] ?? "", params[i]!);
    if ("why" in r) return { why: r.why };
    if ("value" in r) args[params[i]!.name] = r.value;
  }
  return { args };
}

/** One row per macro for the library table. */
export function macroRows(macros: readonly EditMacro[]): { k: string; v: string }[] {
  return macros.map((m) => ({
    k: m.name,
    v: `${m.steps.length} step(s): ${m.steps.map((s) => s.recipe).join(" → ")}`
      + (m.params.length ? ` · ${m.params.length} parameter(s)` : " · no parameters"),
  }));
}

/** The expansion, as JSON — see "the preview is the feature". */
export function stepPreviewHtml(steps: readonly { recipe: string; params: Record<string, unknown> }[]): string {
  const lines = steps.map((s, i) =>
    `${i + 1}. <b>${escapeHtml(s.recipe)}</b> ${escapeHtml(JSON.stringify(s.params))}`);
  return `<b>${steps.length} step(s)</b> — nothing has been applied yet:<br>${lines.join("<br>")}`;
}

/** What came back from the run. */
export function runNoteHtml(res: MacroRunResult, publishState: string, reloaded: boolean): string {
  const per = res.steps.map((s) => `${escapeHtml(s.recipe)} → ${escapeHtml(String(s.changed))}`).join(" · ");
  return `<b>Applied ${res.step_count} step(s)</b> as one version — undoes as a single step. ${per}.`
    + `<br>publish: ${escapeHtml(publishState)}`
    + (publishState === "done" && !reloaded
        ? " — <b>the viewer could not reload; reopen the model</b>, what you are looking at is the "
          + "pre-edit geometry"
        : "");
}

/**
 * Named `macroButton` and not `buildMacroTool`, and INLINED into its caller's `append` — both on
 * purpose. `sectionButtonsWired.test.ts` derives its population from two shapes, `export interface
 * *Buttons` and `export function <name>Button(`, and asks of the second that the call appear inside
 * an `append`. A third spelling would have been outside both populations: the first draft of this
 * file was `buildMacroTool`, assigned to a local and appended, and deleting the append from the
 * section reddened NOTHING. *A control that is built and never appended is the defect that gate
 * exists for, and conforming to the convention it derives from is cheaper than widening it.*
 */
export function macroButton(d: MacroDeps): HTMLButtonElement {
  const btn = d.toolBtn2("⚙ Run a macro (chained recipe)", async () => {
    let lib;
    try { lib = await d.api.listMacros(d.pid); }
    catch (e) { d.notify(`macros unavailable: ${(e as Error).message}`, "error"); return; }
    showResult("Recipe macros", (body) => {
      const note = macroLibraryNote(lib.seeded, lib.macros.length);
      body.appendChild(resultNote(note.html, note.kind));
      body.appendChild(kvTable(macroRows(lib.macros)));
      for (const m of lib.macros) {
        const run = d.toolBtn2(`▶ ${m.name}`, () => { void preview(m, body); });
        run.dataset.cap = "edit";
        run.title = m.description || `${m.steps.length} chained recipe step(s)`;
        body.appendChild(run);
      }
    });
  });
  btn.dataset.cap = "edit";
  btn.title = "Run a saved, parameterized chain of authoring recipes as ONE GUID-stable version — "
    + "the expanded steps are shown for review before anything is applied.";

  /** Ask for the params, expand on the server, and render the concrete steps with an apply button. */
  async function preview(m: EditMacro, body: HTMLElement) {
    const answers: string[] = [];
    for (const p of m.params) {
      const a = await askText(m.name, {
        label: `${p.label || p.name}${p.required ? " (required)" : ""}`,
        value: p.default == null ? "" : String(p.default),
      });
      if (a === null) return;                     // cancelled — nothing asked of the server
      answers.push(a);
    }
    const built = macroArgs(m.params, answers);
    if ("why" in built) { d.notify(built.why, "error"); return; }
    let exp;
    try { exp = await d.api.expandMacro(d.pid, m.id, built.args); }
    catch (e) { d.notify(`cannot expand ${m.name}: ${(e as Error).message}`, "error"); return; }
    body.appendChild(resultNote(stepPreviewHtml(exp.steps), ""));
    const apply = d.toolBtn2(`✔ Apply these ${exp.step_count} step(s)`, () => { void run(m, built.args, body); });
    apply.dataset.cap = "edit";
    body.appendChild(apply);
  }

  async function run(m: EditMacro, args: Record<string, unknown>, body: HTMLElement) {
    // COLLAB-1: the signature of the model this client loaded. The route refuses with 409 if someone
    // published since — but only if we send it, and no caller in this app ever did. When the snapshot
    // itself cannot be read the run still goes ahead and SAYS the lock was not applied: dropping a
    // guard quietly is how it stops being a guard.
    let baseSource: string | undefined;
    try { baseSource = (await d.api.collabSnapshot(d.pid)).model.source ?? undefined; }
    catch { baseSource = undefined; }
    if (!baseSource) {
      body.appendChild(resultNote("The model signature could not be read, so this run is NOT "
        + "protected against a concurrent publish by another editor.", "warn"));
    }
    let res;
    try { res = await d.api.runMacro(d.pid, m.id, args, { publish: true, baseSource }); }
    catch (e) { d.notify(`${m.name} failed: ${(e as Error).message}`, "error"); return; }
    const state = await d.waitForPublish(d.pid);
    const reloaded = state === "done" ? await d.loadProjectModel() : false;
    body.appendChild(resultNote(runNoteHtml(res, state, reloaded), state === "done" && reloaded ? "ok" : "warn"));
    d.notify(`${m.name}: ${res.step_count} step(s) applied`, state === "done" ? "success" : "info");
  }

  return btn;
}
