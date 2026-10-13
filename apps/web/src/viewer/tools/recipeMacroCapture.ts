import type { ApiClient } from "../../api/client";
import type { EditMacro, EditMacroParam, RecipeLogEntry } from "../../api/types";
import { escapeHtml } from "../../ui/feedback";
import { kvTable, resultNote } from "../../ui/result";

/**
 * MACRO-CAPTURE — turn edits that already happened into a macro that can happen again.
 *
 * `saveMacros` was the **last** callerless method of RECIPE-MACROS and the last unwritable member of
 * `services/api/test_stored_standard_writable.py`'s register. MACRO-DARK wired the other three on
 * 2026-10-12 and left this one with the reason written down: *"a macro EDITOR is a separate piece of
 * work, and claiming it here because its three siblings found callers is how an entry goes stale in
 * the flattering direction."* This is that work, and it is a capture rather than an editor because
 * the inputs already exist — RECIPE-LOG-DARK made the edit-recipe log readable, and a log entry is
 * exactly `{recipe, params}`, which is exactly a macro step.
 *
 * ## Four things this has to get right, each of them a test
 *
 * **① An elided entry cannot become a step.** `recipe_log` replaces an over-large parameter value
 * with a descriptor and marks the entry `params_elided`; `replay_plan` refuses such an entry rather
 * than calling the recipe with something that resembles the original argument. A capture that did
 * not refuse would write that descriptor into a SAVED macro, where it outlives the log and gets run
 * by somebody who never saw the log. *The same refusal, moved one step further from the evidence,
 * matters more rather than less.*
 *
 * **② The starter set must not be silently adopted.** `GET /macros` falls back to `STARTER_MACROS`
 * and says so in `seeded`, and `PUT /macros` **replaces the whole library**. So appending to what
 * the list returned and saving it would persist the shipped examples as this firm's standards, with
 * nothing saying so. When `seeded` is true the save carries the new macro ALONE, and the screen says
 * which of the two happened.
 *
 * **③ A parameter is per-OCCURRENCE, not per-value.** The useful version of this feature replaces a
 * captured literal with `${name}` so the macro can run somewhere else — and the coordinate `0`
 * occurs all over a step list. Offering "parameterize the value 0" would rewrite unrelated zeros in
 * unrelated steps, so each offer is one leaf at one path in one step. Two leaves MAY share a name —
 * that is how `"end": ["${x}", 0]` is built — but only when they hold the same value: naming two
 * different values one parameter silently moves one of them, so it is refused with the reason.
 *
 * **④ The default carries the TYPE.** `macros._subst` preserves the raw type when a value is exactly
 * `"${name}"`, and `viewer/tools/macroTool.coerceArg` types the user's answer from the declared
 * `default` — *"a param with no typed default therefore goes as a string"*. So every captured
 * parameter is declared with its captured value as the default, which both keeps the macro runnable
 * unchanged and gives the prompt its type. That is also why only SCALAR leaves are offered: a list
 * default would be prompted as text and arrive as a string.
 */

/** A scalar leaf of one step's parameters — the unit a parameter can be made from. */
export interface Leaf {
  /** Index into the captured step list, 0-based. */
  step: number;
  /** Dotted path within that step's `params`, e.g. `start.0`. */
  path: string;
  value: string | number | boolean;
}

/** One leaf the user chose to parameterize, with the name it takes. */
export interface Pick {
  step: number;
  path: string;
  name: string;
}

export type Step = { recipe: string; params: Record<string, unknown> };

/** Steps for a contiguous slice of the EXPORT (oldest-first) order, and what it refused.
 *
 *  Refusals are returned rather than thrown: a capture of 9 entries where 2 are elided is still a
 *  useful capture of 7, and a thrown error would make it an all-or-nothing choice the user cannot
 *  see the shape of. The caller renders both.
 */
export function capturable(entries: readonly RecipeLogEntry[], from: number, to: number):
  { steps: Step[]; refused: string[]; indices: number[]; why?: string } {
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to < from) {
    return { steps: [], refused: [], indices: [],
             why: "give a from/to range of entry indices in export order (oldest first), from ≤ to" };
  }
  if (from >= entries.length) {
    return { steps: [], refused: [], indices: [],
             why: `entry ${from} is outside the log (${entries.length} entr(ies))` };
  }
  const steps: Step[] = [];
  const refused: string[] = [];
  const indices: number[] = [];
  for (let i = from; i <= Math.min(to, entries.length - 1); i++) {
    const e = entries[i]!;
    if (e.params_elided) {
      refused.push(`#${i} ${e.recipe} — parameters were elided for size, so the step cannot be `
                 + "reproduced faithfully");
      continue;
    }
    steps.push({ recipe: e.recipe, params: { ...(e.params || {}) } });
    indices.push(i);
  }
  return { steps, refused, indices };
}

/** Every scalar leaf of every step, bounded.
 *
 *  `max` exists because a mesh recipe's parameters are thousands of numbers and a checkbox each is
 *  not a screen. Truncation is REPORTED, never silent — a list of 200 offers that looks complete is
 *  the TRUNC-COUNTED defect at widget level.
 */
export function leaves(steps: readonly Step[], max = 120): { list: Leaf[]; truncated: boolean } {
  const list: Leaf[] = [];
  let total = 0;
  const walk = (step: number, prefix: string, v: unknown): void => {
    if (v === null || v === undefined) return;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      total++;
      if (list.length < max) list.push({ step, path: prefix, value: v });
      return;
    }
    if (Array.isArray(v)) {
      v.forEach((x, i) => walk(step, prefix ? `${prefix}.${i}` : String(i), x));
      return;
    }
    if (typeof v === "object") {
      for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
        walk(step, prefix ? `${prefix}.${k}` : k, x);
      }
    }
  };
  steps.forEach((s, i) => walk(i, "", s.params));
  return { list, truncated: total > list.length };
}

/** The value at a dotted path, or `undefined`. */
export function at(params: Record<string, unknown>, path: string): unknown {
  let node: unknown = params;
  for (const seg of path.split(".")) {
    if (node === null || typeof node !== "object") return undefined;
    node = Array.isArray(node) ? node[Number(seg)] : (node as Record<string, unknown>)[seg];
  }
  return node;
}

/** A copy of `params` with the leaf at `path` replaced. Pure — the captured steps are not mutated. */
export function replaceAt(params: Record<string, unknown>, path: string, value: unknown):
  Record<string, unknown> {
  const segs = path.split(".");
  const clone = (node: unknown, depth: number): unknown => {
    if (depth === segs.length) return value;
    const seg = segs[depth]!;
    if (Array.isArray(node)) {
      const out = [...node];
      out[Number(seg)] = clone(node[Number(seg)], depth + 1);
      return out;
    }
    if (node && typeof node === "object") {
      const src = node as Record<string, unknown>;
      return { ...src, [seg]: clone(src[seg], depth + 1) };
    }
    return node;
  };
  return clone(params, 0) as Record<string, unknown>;
}

/** The macro, or the first reason it cannot be built. See ③ and ④ above. */
export function buildMacro(name: string, description: string, steps: readonly Step[],
                           picks: readonly Pick[]): { macro: EditMacro } | { why: string } {
  if (!name.trim()) return { why: "the macro needs a name" };
  if (!steps.length) return { why: "nothing to capture — every selected entry was refused" };
  const ident = /^[a-zA-Z_][a-zA-Z0-9_]*$/;
  const defaults = new Map<string, string | number | boolean>();
  const taken = new Set<string>();
  let out = steps.map((s) => ({ recipe: s.recipe, params: { ...s.params } }));
  for (const p of picks) {
    // The picks are applied in order to a list the previous ones have already rewritten, so a
    // second pick on the SAME leaf would read `"${first}"` as its value and declare a parameter
    // whose default is that placeholder text. The screen cannot produce it — one checkbox per leaf
    // — which is exactly why it is guarded here rather than there: this function is exported, and
    // *a precondition that happens to hold at today's only call site is not a precondition.*
    const site = `${p.step}:${p.path}`;
    if (taken.has(site)) {
      return { why: `step ${p.step + 1}'s ${p.path} was picked twice; one leaf carries one parameter` };
    }
    taken.add(site);
    if (!ident.test(p.name)) {
      return { why: `parameter name "${p.name}" must be a simple identifier (letters, digits, `
                  + "underscore; not starting with a digit)" };
    }
    const step = out[p.step];
    if (!step) return { why: `pick refers to step ${p.step}, which is not in the capture` };
    const value = at(step.params, p.path);
    if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") {
      return { why: `${p.path} in step ${p.step + 1} is not a scalar, so it cannot carry a typed `
                  + "parameter default" };
    }
    const seen = defaults.get(p.name);
    if (seen !== undefined && seen !== value) {
      // ③: one name, two different values. Running the macro would substitute ONE of them into
      // both places — a silent change of behaviour, so it is a refusal rather than a warning.
      return { why: `parameter "${p.name}" would stand for two different values (${JSON.stringify(seen)} `
                  + `and ${JSON.stringify(value)}); running the macro would put one of them where the `
                  + "other was. Use two names, or pick only the occurrences that agree" };
    }
    defaults.set(p.name, value);
    out = out.map((s, i) => (i === p.step
      ? { recipe: s.recipe, params: replaceAt(s.params, p.path, `\${${p.name}}`) }
      : s));
  }
  const params: EditMacroParam[] = [...defaults.entries()].map(([pname, dflt]) => ({
    name: pname, label: pname, default: dflt }));
  return { macro: { id: "", name: name.trim(), description: description.trim(), params, steps: out } };
}

/** What to PUT, and what to tell the user about it. See ② above. */
export function libraryForSave(existing: readonly EditMacro[], seeded: boolean, macro: EditMacro):
  { library: EditMacro[]; note: string } {
  if (seeded) {
    return { library: [macro],
             note: `This project had no saved macros — the ${existing.length} shown were the shipped `
                 + "starter templates. Saving stores <b>only the new macro</b>; the starter set is "
                 + "not adopted as your firm's standards, and the library will show it alongside "
                 + "them as before." };
  }
  return { library: [...existing, macro],
           note: `Appended to the ${existing.length} macro(s) already saved for this project — `
               + "<code>PUT /macros</code> replaces the whole library, so every existing macro is "
               + "sent back unchanged." };
}

/** One row per captured step, for review before anything is saved. */
export function stepRows(steps: readonly Step[]): { k: string; v: string }[] {
  return steps.map((s, i) => ({ k: `${i + 1}. ${s.recipe}`, v: JSON.stringify(s.params) }));
}

/** A path turned into a parameter-name suggestion: `start.0` → `start_0`. Never starts with a digit. */
export function suggestName(step: number, path: string): string {
  const base = (path || "value").replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "value";
  const safe = /^[0-9]/.test(base) ? `p${base}` : base;
  return `${safe}_${step + 1}`;
}

export interface CaptureDeps {
  api: ApiClient;
  pid: string;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
}

/** The capture screen. Mounted into the log reader's own output area, so one door serves both. */
export function renderMacroCapture(host: HTMLElement, d: CaptureDeps,
                                   entries: readonly RecipeLogEntry[],
                                   lib: { macros: EditMacro[]; seeded: boolean }): void {
  host.innerHTML = "";
  // `MAX_STEPS` in `services/api/src/aec_api/macros.py` is 60. Defaulting `to` past it would build a
  // step list the server refuses AFTER the user has named parameters for all of it.
  const MAX_STEPS = 60;
  const mk = (ph: string, val = "") => {
    const i = document.createElement("input");
    i.className = "portal-filter"; i.placeholder = ph; i.value = val;
    i.style.cssText = "font-size:12px;margin:2px";
    return i;
  };
  const fromI = mk("from", "0");
  const toI = mk("to", String(Math.min(entries.length - 1, MAX_STEPS - 1)));
  const nameI = mk("macro name");
  const descI = mk("what it does (optional)");
  const body = document.createElement("div");
  body.className = "meta";
  const out = document.createElement("div");
  out.className = "meta";

  let built: Step[] = [];
  const pickRows: { cb: HTMLInputElement; name: HTMLInputElement; leaf: Leaf }[] = [];

  const build = () => {
    const r = capturable(entries, Number(fromI.value), Number(toI.value));
    body.innerHTML = "";
    pickRows.length = 0;
    built = r.steps;
    if (r.why) {
      body.appendChild(resultNote(`<b>Cannot capture</b> — ${escapeHtml(r.why)}`, "warn"));
      return;
    }
    if (r.refused.length) {
      // ①, and the refusal is the engine's own rule carried one step further out.
      body.appendChild(resultNote(
        `<b>${r.refused.length} entr(ies) refused</b> — an elided parameter cannot be reproduced, and `
        + "a saved macro outlives the log it came from, so the descriptor must not be written into "
        + `one:<br>${r.refused.map(escapeHtml).join("<br>")}`, "warn"));
    }
    if (!r.steps.length) {
      body.appendChild(resultNote("<b>Nothing capturable in that range.</b>", "warn"));
      return;
    }
    if (r.steps.length > MAX_STEPS) {
      body.appendChild(resultNote(
        `<b>${r.steps.length} steps</b> — the server caps a macro at ${MAX_STEPS}, so narrow the `
        + "range before naming parameters for all of it.", "warn"));
    }
    body.appendChild(resultNote(
      `<b>${r.steps.length} step(s)</b> from entr(ies) ${r.indices.join(", ")}, in export order. `
      + "Nothing is saved until the button below.", ""));
    body.appendChild(kvTable(stepRows(r.steps)));

    const { list, truncated } = leaves(r.steps);
    if (truncated) {
      body.appendChild(resultNote(
        `<b>Showing the first ${list.length} values</b> — these steps carry more scalars than a `
        + "picker can offer. Capture a narrower range to reach the rest.", "warn"));
    }
    const legend = document.createElement("div");
    legend.className = "meta";
    legend.innerHTML = "<b>Make a value a parameter</b> — tick a value to replace it with "
      + "<code>${name}</code>. The captured value becomes the parameter's default, so the macro runs "
      + "unchanged until somebody answers differently, and the default is what gives the prompt its "
      + "type. Two ticks may share a name only when they hold the same value.";
    body.appendChild(legend);
    for (const leaf of list) {
      const row = document.createElement("div");
      row.className = "meta";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      const nm = mk("parameter name", suggestName(leaf.step, leaf.path));
      const label = document.createElement("span");
      label.textContent = ` step ${leaf.step + 1} · ${leaf.path || "(value)"} = ${JSON.stringify(leaf.value)} `;
      row.append(cb, label, nm);
      body.appendChild(row);
      pickRows.push({ cb, name: nm, leaf });
    }
  };

  const save = async () => {
    const picks: Pick[] = pickRows.filter((r) => r.cb.checked)
      .map((r) => ({ step: r.leaf.step, path: r.leaf.path, name: r.name.value.trim() }));
    const m = buildMacro(nameI.value, descI.value, built, picks);
    if ("why" in m) {
      out.innerHTML = "";
      out.appendChild(resultNote(`<b>Not saved</b> — ${escapeHtml(m.why)}`, "warn"));
      return;
    }
    const plan = libraryForSave(lib.macros, lib.seeded, m.macro);
    out.innerHTML = "";
    out.appendChild(resultNote(plan.note, ""));
    try {
      const res = await d.api.saveMacros(d.pid, plan.library);
      // The server mints the id and echoes the normalized library, so the count comes from IT and
      // not from what we sent: a macro the validator rewrote is still one we should report as it is.
      out.appendChild(resultNote(
        `<b>Saved</b> — the library now holds ${res.saved} macro(s). Run it from `
        + "<b>⚙ Run a macro</b> in the authoring tools.", "ok"));
      lib.macros = res.macros;
      lib.seeded = false;
      d.notify(`macro "${m.macro.name}" saved`, "success");
    } catch (e) {
      // The 422 names which step and which recipe, which is the only thing that tells the user what
      // to change. Verbatim: "save failed" throws away the whole content of the refusal.
      out.appendChild(resultNote(`<b>Refused</b> — ${escapeHtml((e as Error).message)}`, "bad"));
    }
  };

  const head = document.createElement("div");
  head.className = "meta";
  head.innerHTML = "<b>Capture a macro from these edits</b> — entry indices are the EXPORT order "
    + "(oldest first), the same order the diff uses.";
  host.append(head, fromI, toI,
              d.toolBtn2("⟳ Build the step list", build),
              nameI, descI,
              d.toolBtn2("⇣ Save as a macro", () => { void save(); }),
              body, out);
  build();
}
