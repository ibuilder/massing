/** RECIPE-LOG-DARK — the log reader's BODY, split out of `recipeLogTool.ts` so it is not eager.
 *
 * `viewer/tools/*` is the app-shell chunk, and `apps/web/scripts/bundle-budget.mjs` caps that shell
 * at 225 KB Brotli. The reader shipped as one module and took the shell to **226.2 KB** — a CI
 * failure on a gate I had not run, because I had run the budget's TESTS (`src/tooling`, 43 of them,
 * all green) and not the budget. *A test about a budget is not the budget*, and the two are
 * different commands: `npx vitest run src/tooling` versus `npm run budget`.
 *
 * So the eager half is now the BUTTON alone, in `recipeLogTool.ts`, and everything a click needs
 * lives here behind `await import()`. That is the same shape the CLAUDE.md note prescribes for every
 * click-driven card in this directory, and `viewer/tools/macroTool.ts` is the neighbour that did not
 * need it only because it is smaller.
 *
 * Why the SPLIT rather than a bigger budget: the shell is what every visitor downloads before
 * anything renders, and a provenance reader is opened by one user in a hundred. The budget's own
 * failure message offers both ("trim the eager path, or bump BUNDLE_BUDGET_KB deliberately with a
 * note") and the deliberate note here is that bumping it would spend a shared allowance on a rarely
 * opened screen.
 */
import type { ApiClient } from "../../api/client";
import type { RecipeDiff, RecipeLogEntry, RecipeLogExport, RecipeLogPage,
  RecipeReplayPlan } from "../../api/types";
import { escapeHtml } from "../../ui/feedback";
import { kvTable, resultNote } from "../../ui/result";

/**
 * RECIPE-LOG-DARK — the door onto R23-RECIPE-ARTIFACT, which records everything and could be read
 * by nothing.
 *
 * `services/api/src/aec_api/recipe_log.py` is the only place in this product that keeps an edit's
 * **inputs**. Its own header says why that mattered: the audit log records an edit's *outputs* and
 * the undo stack records *file paths*, so before it existed "you cannot replay an operation you did
 * not record the arguments to, cannot diff two edits whose arguments you never kept, and cannot
 * export a provenance trail that says only 'something called add_wall happened'". It is wired at
 * four capture sites in `services/api/src/aec_api/routers/authoring.py` and has run on every edit
 * since. **All four of its read routes had no client method at all.**
 *
 * ## Four routes, four different silences — and none of them a gate being wrong
 *
 * Measured with `test_route_reachability.py`'s own helpers rather than assumed:
 *
 * | route | why nothing flagged it |
 * |---|---|
 * | `GET …/recipes/log` | leaf `log` is 3 chars, under that gate's `MIN_SEGMENT` — honestly **unjudged**, not judged clean |
 * | `GET …/recipes/diff` | leaf `diff` is 4 chars, same bucket |
 * | `GET …/recipes/export` | frozen in `LEAF_COLLISION_BLIND` — `export` collides with web-tree vocabulary |
 * | `POST …/recipes/replay-plan` | frozen in `UNREACHABLE_ROUTES`, which records "this was looked at", never "this is safe" |
 *
 * And `apps/web/src/api/clientCallers.test.ts` was structurally unable to see any of the four,
 * because **no client method was ever declared** — that gate asks whether a declared method has a
 * caller, so a capability with no method is not in its population. *A gate for each side of a seam
 * is not a gate for the seam*: one asks "is the route called", the other "is the method called", and
 * neither asks "is the capability reachable".
 *
 * ## The log's own top-line verdict was unsound, in two independent ways
 *
 * Found while wiring this panel, which is the argument for wiring it. `export()` answered
 * `"replayable": all(not r["params_elided"] for r in entries)`, and:
 *
 * 1. **`all()` over an empty sequence is `True`.** A project that has never been edited reported
 *    *replayable*. That is NEGATED-VERDICT's class arriving in a shape no gate covered — the
 *    vacuity gate's population is `BoolOp`/`And`, and a bare `all(…)` Call is in neither shape.
 * 2. **The log is a RING.** `record()` keeps `[-500:]` and said so in no payload, so a project past
 *    the cap reported *replayable* while the edits needed to rebuild it had already been dropped —
 *    **the worse of the two**, because it is wrong about a real, populated project rather than an
 *    empty one, and the file could not even say whether it had forgotten anything.
 *
 * Both are fixed at the engine, and `replayable` is now `bool(entries) and not elided` beside a
 * `history` of `complete | truncated | unknown`. The third state is not decoration: a log written
 * before the drop counter existed cannot distinguish "exactly 500 edits, none lost" from "500 kept,
 * an unknown number dropped", and folding that into either answer would be a guess. This panel
 * renders `elided` and `history` on **every** answer, which is what `test_verdict_coverage.py`
 * demands of a consumer and what the `# COVERAGE:` declarations beside the verdict point at.
 *
 * ## It is also the door onto `saveMacros`
 *
 * `./recipeMacroCapture` turns a contiguous slice of the log into a saved macro, which closes the
 * last callerless method of RECIPE-MACROS and the last unwritable member of
 * `services/api/test_stored_standard_writable.py`'s register. A log entry is already a macro step:
 * `{recipe, params}`, and the parameters are the half nothing else in this product kept. Its four
 * rules are in its own header; the one that belongs here is that an **elided** entry is refused
 * there too, because a saved macro outlives the log it came from.
 *
 * ## Where it is mounted, which took three tries
 *
 * Not the authoring section, which is where the capability belongs by SUBJECT: that section sets
 * `dataset.cap = "edit"` on its whole group and `/recipes/log` is **viewer**-gated, so mounting it
 * there makes a read reachable for everyone who does not need it and nobody who does. Not
 * `qaSection.ts` either, which has the right gate and sits at its extraction ratchet in
 * `services/api/test_file_sizes.py` — *a ratchet is not raised to accommodate a mount.* So
 * `analyseSection.ts`, which renders under the same "Analyze & Coordinate" heading as the QA
 * section, making the user-visible home the same one either way.
 *
 * ## Why this reads and does not apply
 *
 * `replay_plan()` returns a **plan**, by design — its docstring: *"Re-running edits is exactly the
 * kind of thing that should have one author and one audit row, and a log that could re-run itself
 * would have neither."* So the plan is shown, and this panel does not apply it. That is a real
 * decision rather than an unfinished one: applying a project's own log back onto that project
 * re-runs the edits, which **duplicates** everything they created. The plan's intended target is a
 * different model, and `POST /projects/{pid}/edit/batch` is where it goes — which the engine's own
 * `note` says, and which is rendered verbatim rather than paraphrased.
 */
export interface RecipeLogDeps {
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  pid: string;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
}

/** The parameter names whose VALUE was replaced by a descriptor, in order.
 *
 *  Derived from the stored values rather than read off `params_elided`, because the flag says
 *  *something* was elided and the reader needs to know *what* — an elided `points` array is a
 *  different problem from an elided `name`. The wholesale substitution `_fit` falls back to (the
 *  entry whose bulk is in its KEY names) replaces `params` itself with a descriptor, so that case
 *  reports the dict rather than a key list; it is named `(all parameters)` rather than being missed.
 */
export function elidedParams(e: RecipeLogEntry): string[] {
  const p = e.params as unknown;
  if (p && typeof p === "object" && (p as Record<string, unknown>).__elided__) return ["(all parameters)"];
  if (!p || typeof p !== "object") return [];
  return Object.entries(p as Record<string, unknown>)
    .filter(([, v]) => !!v && typeof v === "object" && (v as Record<string, unknown>).__elided__)
    .map(([k]) => k);
}

/**
 * The page's caveats, as a value a test can assert.
 *
 * Three facts, and they are independent — a page can be truncated, elided, both or neither, so they
 * are stated separately rather than collapsed into one "incomplete" word:
 *
 * * `returned < total` — this is a PAGE. `TRUNC-COUNTED` is the defect of printing the length of a
 *   page as if it were a total, and three screens on this branch had it.
 * * `elided` — entries whose parameters cannot reproduce the edit.
 * * `note` — the engine's own ring warning, rendered **verbatim**: it is the one sentence that says
 *   history has been dropped, and a paraphrase of a caveat is a caveat somebody re-worded.
 */
export function logNote(p: RecipeLogPage): { html: string; kind: "ok" | "warn" | "bad" | "" } {
  if (!p.total) {
    return { html: "<b>Nothing recorded.</b> No edit on this project has been logged — either it has "
                 + "never been authored, or every edit predates the recipe log. An empty log is not a "
                 + "clean one; it is a log with nothing to say.", kind: "warn" };
  }
  const bits: string[] = [];
  bits.push(`<b>${p.total} logged edit(s)</b>`);
  if (p.returned < p.total) {
    bits.push(`showing ${p.returned} from #${p.offset + 1} — <b>this is a page, not the total</b>`);
  }
  if (p.elided) {
    bits.push(`<b>${p.elided} of the ${p.total} had parameters elided for size</b> and cannot be `
            + "replayed faithfully");
  }
  const html = bits.join(" · ") + (p.note ? `<br><b>${escapeHtml(p.note)}</b>` : "");
  return { html, kind: p.elided || p.note ? "warn" : "ok" };
}

/** The parameters as text, cut at `max` with the cut MARKED.
 *
 *  A silently-cut JSON object is TRUNC-COUNTED at field level: `{"a":1,"b":2` reads as a complete
 *  object that happens to be malformed, and the reader cannot tell a short parameter list from a cut
 *  one. The marker is the whole point of the helper. */
export function paramsCell(params: unknown, max = 220): string {
  const text = JSON.stringify(params ?? {});
  return text.length <= max ? text : `${text.slice(0, max)}… (cut, ${text.length} chars)`;
}

/** One row per entry: what ran, who ran it, when, and what it ran between. */
export function entryRows(entries: readonly RecipeLogEntry[], offset = 0): { k: string; v: string }[] {
  return entries.map((e, i) => {
    const gone = elidedParams(e);
    const when = (e.at || "").replace("T", " ").slice(0, 19) || "time not recorded";
    const who = e.actor || "actor not recorded";
    const between = e.source_in || e.source_out
      ? `${e.source_in || "?"} → ${e.source_out || "?"}`
      : "sources not recorded";
    return {
      k: `#${offset + i + 1} ${e.recipe}`,
      v: `${when} · ${who} · ${between}`
        + (e.batch ? ` · batch ${e.batch}` : "")
        + ` · params: ${paramsCell(e.params)}`
        + (gone.length ? ` · ELIDED: ${gone.join(", ")} — NOT replayable` : ""),
    };
  });
}

/**
 * The export's replay verdict, with its coverage — never the bare boolean.
 *
 * `replayable` is a claim about the entries the log HOLDS. `history` is a separate claim about
 * whether it holds all of them. Rendering the first without the second is the defect CLASH-TRUNC
 * paid to learn: *a guard is only as sound as the evidence it is handed*, and a ring buffer hands a
 * complete-looking set that is a window.
 */
export function replayNote(x: RecipeLogExport): { html: string; kind: "ok" | "warn" | "bad" | "" } {
  const { history, dropped } = x.replay_coverage;
  const histLine = history === "complete"
    ? "The log holds this project's whole edit history"
    : history === "truncated"
      ? `<b>The log is a ring and has dropped ${dropped} older entr(ies)</b> — a replay reproduces `
        + `the last ${x.bounded_at}, not the model`
      : `<b>Whether anything was dropped is not recorded</b> — this log was written before the drop `
        + `counter existed and holds ${x.count} of a maximum ${x.bounded_at}`;
  if (!x.count) {
    return { html: "<b>Nothing to replay</b> — the log is empty. Note this is NOT the same answer as "
                 + "\"replayable\": an empty sequence satisfies every claim made about its members.",
             kind: "warn" };
  }
  if (x.elided) {
    return { html: `<b>NOT replayable</b> — ${x.elided} of ${x.count} entr(ies) had a parameter `
                 + "replaced by a descriptor (too large to store), and replaying one would call the "
                 + `recipe with something that resembles the original argument and is not it. ${histLine}.`,
             kind: "bad" };
  }
  return { html: `<b>${x.replayable ? "Replayable" : "Not replayable"}</b> — all ${x.count} entr(ies) `
               + `kept their parameters. ${histLine}.`,
           kind: x.replayable && history === "complete" ? "ok" : "warn" };
}

/** A diff between two entries. Both refusals the engine can return are rendered VERBATIM. */
export function diffNote(d: RecipeDiff): { html: string; kind: "ok" | "warn" | "bad" | "" } {
  if (!d.comparable) {
    return { html: `<b>Not comparable</b> — ${escapeHtml(d.reason || "no reason given")}`, kind: "warn" };
  }
  const changed = d.changed ?? [];
  const head = d.identical
    ? `<b>Identical</b> — both runs of <b>${escapeHtml(d.recipe || "?")}</b> were asked for the same thing.`
    : `<b>${changed.length} parameter(s) differ</b> on <b>${escapeHtml(d.recipe || "?")}</b>:<br>`
      + changed.map((c) => `${escapeHtml(c.param)}: ${escapeHtml(JSON.stringify(c.before))} → `
                         + `${escapeHtml(JSON.stringify(c.after))}`).join("<br>");
  return { html: head + (d.elided_warning ? `<br><b>${escapeHtml(d.elided_warning)}</b>` : ""),
           kind: d.elided ? "warn" : "ok" };
}

/**
 * The plan, as JSON, plus the engine's own note.
 *
 * Shown as JSON for the reason `macroTool.stepPreviewHtml` gives: quoting is how a mistyped argument
 * becomes visible, and `["6", 0]` versus `[6, 0]` is a defect no prose caveat substitutes for seeing.
 */
export function planHtml(p: RecipeReplayPlan): string {
  const lines = p.steps.map((s, i) =>
    `${i + 1}. <b>${escapeHtml(s.recipe)}</b> ${escapeHtml(JSON.stringify(s.params))}`);
  return `<b>${p.count} step(s)</b> — <b>nothing has been applied</b>, and this panel does not apply `
       + "it: replaying a project's own log back onto that project re-runs the edits and duplicates "
       + `everything they created. The target is another model.<br>${lines.join("<br>")}`
       + `<br><br>${escapeHtml(p.note)}`;
}

/**
 * The reader itself, rendered into the result-overlay body the button opens.
 *
 * Takes the page it was opened with rather than fetching it, because the button has to know whether
 * the log is readable BEFORE it opens an overlay: an unreadable log is a 409 the reader cannot
 * render, and an empty overlay with an error inside it is worse than a toast.
 */
export function renderRecipeLog(body: HTMLElement, d: RecipeLogDeps, page: RecipeLogPage): void {
  const note = logNote(page);
  body.appendChild(resultNote(note.html, note.kind));
  body.appendChild(kvTable(entryRows(page.entries, page.offset)));

  const out = document.createElement("div");
  out.className = "meta";
  out.style.marginTop = "6px";

  // The filter is a real narrowing of the same page, so it refetches rather than filtering the
  // page in hand: `total` and the ring note are answers about the FILTERED set and the server is
  // the only thing that can compute them. Filtering client-side would print the unfiltered total
  // beside a filtered list, which is TRUNC-COUNTED wearing a filter.
  if (page.recipes.length > 1) {
    const sel = document.createElement("select");
    sel.className = "portal-filter";
    sel.style.cssText = "font-size:12px;margin:2px";
    for (const r of ["(all recipes)", ...page.recipes]) {
      const o = document.createElement("option");
      o.value = r === "(all recipes)" ? "" : r;
      o.textContent = r;
      sel.appendChild(o);
    }
    sel.value = "";
    sel.onchange = async () => {
      out.textContent = "reading…";
      try {
        const p = await d.api.recipeLog(d.pid, { recipe: sel.value || undefined });
        const n = logNote(p);
        out.innerHTML = "";
        out.appendChild(resultNote(n.html, n.kind));
        out.appendChild(kvTable(entryRows(p.entries, p.offset)));
      } catch (e) { out.textContent = `could not read: ${(e as Error).message}`; }
    };
    body.appendChild(sel);
  }

  const exportBtn = d.toolBtn2("⇣ Provenance export (whole log, oldest first)", async () => {
    out.textContent = "exporting…";
    try {
      const x = await d.api.recipeLogExport(d.pid);
      const n = replayNote(x);
      out.innerHTML = "";
      out.appendChild(resultNote(n.html, n.kind));
      const blob = new Blob([JSON.stringify(x, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${d.pid}-recipe-log.json`;
      a.textContent = `⇣ download ${x.count} entr(ies) as JSON`;
      out.appendChild(a);
    } catch (e) { out.textContent = `export failed: ${(e as Error).message}`; }
  });

  const planBtn = d.toolBtn2("▶ Build a replay plan (not an execution)", async () => {
    out.textContent = "building…";
    try {
      const p = await d.api.recipeReplayPlan(d.pid);
      out.innerHTML = "";
      out.appendChild(resultNote(planHtml(p), ""));
    } catch (e) {
      // The 422 names which entries cannot be reproduced and why. Rendered verbatim: it is the
      // refusal the whole feature exists to be able to make.
      out.innerHTML = "";
      out.appendChild(resultNote(`<b>Refused</b> — ${escapeHtml((e as Error).message)}`, "bad"));
    }
  });

  const diffWrap = document.createElement("div");
  diffWrap.className = "meta";
  const ia = document.createElement("input");
  const ib = document.createElement("input");
  for (const [inp, ph] of [[ia, "a"], [ib, "b"]] as const) {
    inp.type = "number"; inp.min = "0"; inp.className = "portal-filter";
    inp.placeholder = `entry ${ph}`; inp.style.cssText = "font-size:12px;margin:2px;width:90px";
  }
  const diffBtn = d.toolBtn2("⇄ Diff two runs", async () => {
    // `Number("")` is 0, not NaN — so an EMPTY box passes every numeric check and silently
    // diffs entry 0 against itself. The blank has to be refused before the parse, which is the
    // empty-versus-absent confusion this branch keeps paying for, in its arithmetic form.
    const blank = !ia.value.trim() || !ib.value.trim();
    const a = Number(ia.value), b = Number(ib.value);
    if (blank || !Number.isInteger(a) || !Number.isInteger(b) || a < 0 || b < 0) {
      out.textContent = "give two entry indices (0-based, in export order — oldest first)";
      return;
    }
    out.textContent = "comparing…";
    try {
      const r = await d.api.recipeDiff(d.pid, a, b);
      const n = diffNote(r);
      out.innerHTML = "";
      out.appendChild(resultNote(n.html, n.kind));
    } catch (e) { out.textContent = `diff failed: ${(e as Error).message}`; }
  });
  diffWrap.append(ia, ib, diffBtn);

  // MACRO-CAPTURE — this reader is the door onto `saveMacros`, the last callerless method of
  // RECIPE-MACROS, because a log entry IS a macro step: `{recipe, params}`, and the parameters are
  // the half nothing else in this product kept. Dynamically imported for the same reason this whole
  // file is: the shell sits at its Brotli cap, and a capture screen is opened by a fraction of the
  // people who open the reader.
  const captureBtn = d.toolBtn2("\u29c9 Capture a macro from these edits", async () => {
    out.textContent = "reading\u2026";
    try {
      // The EXPORT, not this page: a macro is a sequence, and the page is newest-first and may be
      // filtered to one recipe. The library comes too, because `PUT /macros` replaces it WHOLE and
      // `seeded` is what says whether the list in hand is the firm's or the shipped starter set —
      // appending to the second and saving it would adopt the shipped examples as their standards.
      const [x, lib] = await Promise.all([d.api.recipeLogExport(d.pid), d.api.listMacros(d.pid)]);
      const mod = await import("./recipeMacroCapture");
      mod.renderMacroCapture(out, { api: d.api, pid: d.pid, toolBtn2: d.toolBtn2, notify: d.notify },
                             x.entries, { macros: lib.macros, seeded: lib.seeded });
    } catch (e) { out.textContent = `could not start a capture: ${(e as Error).message}`; }
  });

  body.append(exportBtn, planBtn, captureBtn, diffWrap, out);
}
