import { describe, expect, it, vi } from "vitest";

import type { RecipeLogEntry, RecipeLogExport, RecipeLogPage } from "../../api/types";
import type { RecipeLogDeps } from "./recipeLogTool";
import {
  diffNote, elidedParams, entryRows, logNote, paramsCell, planHtml, recipeLogButton, replayNote,
} from "./recipeLogTool";

/**
 * RECIPE-LOG-DARK — the door onto the edit-recipe log, and the two unsound claims wiring it exposed.
 *
 * The verdict tests below are the ones that matter, because `replayable` was **`all(not elided)`**
 * over a list that can be empty AND is a ring. Both halves are asserted here in the form a reader
 * would meet them: an untouched project and a project past the 500-entry cap. A test that only
 * exercised a short, complete log would have passed on the defect and on its fix alike.
 */

const ENTRY = (over: Partial<RecipeLogEntry> = {}): RecipeLogEntry => ({
  recipe: "add_wall",
  params: { start: [0, 0], end: [5, 0], height: 3 },
  params_elided: false,
  actor: "ada@example.com",
  at: "2026-10-12T08:14:03.221000+00:00",
  source_in: "m_1.ifc",
  source_out: "m_2.ifc",
  outputs: { changed: "2bKf" },
  ...over,
});

const PAGE = (over: Partial<RecipeLogPage> = {}): RecipeLogPage => ({
  version: 1, total: 2, returned: 2, offset: 0,
  entries: [ENTRY(), ENTRY({ recipe: "set_pset" })],
  recipes: ["add_wall", "set_pset"], elided: 0, bounded_at: 500, note: null,
  ...over,
});

const EXPORT = (over: Partial<RecipeLogExport> = {}): RecipeLogExport => ({
  version: 1, project: "p1", order: "oldest_first", count: 2, entries: [ENTRY(), ENTRY()],
  elided: 0, replayable: true, bounded_at: 500,
  replay_coverage: { entries: 2, elided: 0, replayable_entries: 2, dropped: 0, history: "complete",
                     reason: "every entry kept its parameters and none have been dropped" },
  ...over,
});

describe("the page's three caveats, which are independent", () => {
  it("an empty log is NOT a clean one, and does not read like one", () => {
    const n = logNote(PAGE({ total: 0, returned: 0, entries: [], recipes: [] }));
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("Nothing recorded");
    expect(n.html).toContain("not a clean one");
  });

  it("a page says it is a page — TRUNC-COUNTED is printing its length as the total", () => {
    const n = logNote(PAGE({ total: 940, returned: 200, offset: 0 }));
    expect(n.html).toContain("940 logged edit(s)");
    expect(n.html).toContain("this is a page, not the total");
  });

  it("a complete, un-elided page is the only one that reads ok", () => {
    expect(logNote(PAGE()).kind).toBe("ok");
    expect(logNote(PAGE({ elided: 1 })).kind).toBe("warn");
    expect(logNote(PAGE({ note: "the log keeps the most recent 500 entries" })).kind).toBe("warn");
  });

  it("renders the engine's ring note VERBATIM rather than paraphrasing it", () => {
    const note = "the log keeps the most recent 500 entries; older edits have been dropped";
    expect(logNote(PAGE({ note })).html).toContain(note);
  });

  it("escapes the note — it reaches innerHTML", () => {
    expect(logNote(PAGE({ note: "<img src=x>" })).html).not.toContain("<img");
  });
});

describe("which parameters were elided, and not merely that some were", () => {
  it("names the keys whose value became a descriptor", () => {
    const e = ENTRY({ params_elided: true,
      params: { height: 3, points: { __elided__: true, type: "list", bytes: 90210 } } });
    expect(elidedParams(e)).toEqual(["points"]);
  });

  it("reports the wholesale substitution rather than missing it", () => {
    // `_fit` replaces `params` ITSELF when the bulk is in the key names — a shape a per-key scan
    // reads as "nothing elided" while `params_elided` is true.
    const e = ENTRY({ params_elided: true,
      params: { __elided__: true, reason: "entry too large to store", keys: 4000 } as never });
    expect(elidedParams(e)).toEqual(["(all parameters)"]);
  });

  it("an ordinary entry has none", () => {
    expect(elidedParams(ENTRY())).toEqual([]);
  });

  it("the row says NOT replayable beside the named key", () => {
    const rows = entryRows([ENTRY({ params_elided: true,
      params: { mesh: { __elided__: true, bytes: 1 } } })]);
    expect(rows[0]!.v).toContain("ELIDED: mesh");
    expect(rows[0]!.v).toContain("NOT replayable");
  });

  it("a row carries what ran, who ran it, when, and between which sources", () => {
    const [row] = entryRows([ENTRY()], 40);
    expect(row!.k).toBe("#41 add_wall");
    expect(row!.v).toContain("2026-10-12 08:14:03");
    expect(row!.v).toContain("ada@example.com");
    expect(row!.v).toContain("m_1.ifc → m_2.ifc");
  });

  it("says a field was not recorded rather than printing an empty one", () => {
    const [row] = entryRows([ENTRY({ actor: null, at: null, source_in: null, source_out: null })]);
    expect(row!.v).toContain("actor not recorded");
    expect(row!.v).toContain("time not recorded");
    expect(row!.v).toContain("sources not recorded");
  });

  it("marks a cut parameter list — a silently cut JSON object reads as a complete one", () => {
    const long = { pts: Array.from({ length: 200 }, (_, i) => i) };
    const cell = paramsCell(long);
    expect(cell).toContain("(cut,");
    expect(paramsCell({ a: 1 })).toBe('{"a":1}');
    expect(paramsCell({ a: 1 })).not.toContain("cut");
  });
});

describe("the replay verdict, which was unsound in two independent ways", () => {
  it("DEFECT 1 — an empty log is not replayable, it has nothing to replay", () => {
    // `all(<empty>)` is True. A project that has never been authored reported *replayable*.
    const n = replayNote(EXPORT({ count: 0, entries: [], replayable: false,
      replay_coverage: { entries: 0, elided: 0, replayable_entries: 0, dropped: 0,
                         history: "complete", reason: "nothing has been logged" } }));
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("Nothing to replay");
    expect(n.html).not.toContain("<b>Replayable</b>");
  });

  it("DEFECT 2 — a truncated history is not replayable even with nothing elided", () => {
    // The worse of the two: wrong about a real project. The ring dropped the edits needed to
    // rebuild the model, and every entry it kept is individually faithful.
    const n = replayNote(EXPORT({ count: 500, elided: 0, replayable: false,
      replay_coverage: { entries: 500, elided: 0, replayable_entries: 500, dropped: 213,
                         history: "truncated", reason: "213 older entries have been dropped" } }));
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("dropped 213 older");
    expect(n.html).toContain("not the model");
    // The field is the END-TO-END claim. All 500 held entries are individually faithful — that
    // fact is `replayable_entries` — and the model still cannot be rebuilt from them.
    expect(n.html).toContain("Not replayable");
  });

  it("an unrecorded drop count is a THIRD state, not folded into either answer", () => {
    const n = replayNote(EXPORT({ count: 500, replayable: false,
      replay_coverage: { entries: 500, elided: 0, replayable_entries: 500, dropped: 0,
                         history: "unknown", reason: "written before the drop counter existed" } }));
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("not recorded");
  });

  it("elision is reported as NOT replayable, with the count", () => {
    const n = replayNote(EXPORT({ count: 9, elided: 2, replayable: false,
      replay_coverage: { entries: 9, elided: 2, replayable_entries: 7, dropped: 0,
                         history: "complete", reason: "2 entries had a parameter elided" } }));
    expect(n.kind).toBe("bad");
    expect(n.html).toContain("NOT replayable");
    expect(n.html).toContain("2 of 9");
  });

  it("only a populated, un-elided, complete log reads ok", () => {
    const n = replayNote(EXPORT());
    expect(n.kind).toBe("ok");
    expect(n.html).toContain("whole edit history");
  });
});

describe("the diff, and the two refusals it can carry", () => {
  it("renders the incomparable reason verbatim instead of a verdict", () => {
    const reason = "different recipes ('add_wall' vs 'set_pset') — their parameters are not the "
      + "same vocabulary";
    const n = diffNote({ comparable: false, reason });
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("not the");          // the engine's sentence, escaped
    expect(n.html).toContain("Not comparable");
  });

  it("lists the changed parameters with before and after", () => {
    const n = diffNote({ comparable: true, recipe: "add_wall", identical: false,
      changed: [{ param: "height", before: 3, after: 4.2 }], unchanged: ["start"], elided: false,
      elided_warning: null });
    expect(n.html).toContain("height: 3 → 4.2");
    expect(n.kind).toBe("ok");
  });

  it("carries the elided-hash caveat verbatim, because a changed descriptor means LESS than it looks", () => {
    const warning = "one or both entries have elided parameters; a value replaced by a descriptor "
      + "compares by hash";
    const n = diffNote({ comparable: true, recipe: "add_wall", identical: true, changed: [],
      unchanged: ["height"], elided: true, elided_warning: warning });
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("compares by hash");
  });

  it("escapes a recipe name and a parameter name — both are stored text in innerHTML", () => {
    const n = diffNote({ comparable: true, recipe: "<img src=x>", identical: false,
      changed: [{ param: "<svg onload=1>", before: 1, after: 2 }] });
    expect(n.html).not.toContain("<img");
    expect(n.html).not.toContain("<svg");
  });
});

describe("the plan is a plan", () => {
  it("says nothing was applied, says this panel will not apply it, and why", () => {
    const html = planHtml({ steps: [{ recipe: "add_wall", params: { height: 3 } }], count: 1,
      note: "apply with POST /projects/{pid}/edit/batch — one version, one audit row, one author." });
    expect(html).toContain("nothing has been applied");
    expect(html).toContain("duplicates");
    expect(html).toContain("edit/batch");        // the engine's own note, carried
  });

  it("shows the steps as JSON, so a mistyped argument is visible", () => {
    const html = planHtml({ steps: [{ recipe: "add_column", params: { point: ["6", 0] } }], count: 1,
      note: "" });
    expect(html).toContain("&quot;point&quot;:[&quot;6&quot;,0]");
  });
});

/** ---- the flow, driven through the real button ----------------------------------------------- */

const flush = () => new Promise((r) => setTimeout(r, 0));
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text));
const noteTexts = () => [...document.querySelectorAll(".result-note")].map((n) => n.textContent ?? "");

function harness(opts: { page?: RecipeLogPage; exp?: RecipeLogExport; planThrows?: string } = {}) {
  const seen: { log: unknown[] } = { log: [] };
  const api = {
    recipeLog: vi.fn(async (_pid: string, o?: { recipe?: string }) => {
      seen.log.push(o ?? null);
      return opts.page ?? PAGE();
    }),
    recipeLogExport: vi.fn(async () => opts.exp ?? EXPORT()),
    recipeDiff: vi.fn(async () => ({ comparable: true, recipe: "add_wall", identical: true,
      changed: [], unchanged: ["height"], elided: false, elided_warning: null })),
    recipeReplayPlan: vi.fn(async () => {
      if (opts.planThrows) throw new Error(opts.planThrows);
      return { steps: [{ recipe: "add_wall", params: { height: 3 } }], count: 1, note: "apply with POST" };
    }),
  };
  const deps = {
    toolBtn2: (label: string, onClick: () => void) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = onClick;
      return b;
    },
    api: api as unknown as RecipeLogDeps["api"],
    pid: "p1",
    notify: vi.fn(),
  } satisfies RecipeLogDeps;
  return { deps, api, seen };
}

async function open(h: ReturnType<typeof harness>) {
  document.body.replaceChildren();
  recipeLogButton(h.deps).click();
  await flush();
}

describe("the door", () => {
  it("reads the log and renders an entry per logged edit", async () => {
    const h = harness();
    await open(h);
    expect(h.api.recipeLog).toHaveBeenCalledWith("p1");
    expect(document.body.textContent).toContain("add_wall");
    expect(document.body.textContent).toContain("ada@example.com");
  });

  it("the recipe filter REFETCHES — filtering the page in hand would print the unfiltered total", async () => {
    const h = harness();
    await open(h);
    const sel = document.querySelector("select") as HTMLSelectElement;
    expect(sel).toBeTruthy();
    sel.value = "set_pset";
    sel.dispatchEvent(new Event("change"));
    await flush();
    expect(h.seen.log).toEqual([null, { recipe: "set_pset" }]);
  });

  it("the export renders the coverage, not the bare boolean, and offers the artifact", async () => {
    const h = harness({ exp: EXPORT({ count: 500, replayable: false,
      replay_coverage: { entries: 500, elided: 0, replayable_entries: 500, dropped: 7,
                         history: "truncated", reason: "7 dropped" } }) });
    await open(h);
    btn("⇣ Provenance export")!.click();
    await flush();
    expect(noteTexts().some((t) => t.includes("dropped 7 older"))).toBe(true);
    expect([...document.querySelectorAll("a")].some((a) => a.textContent?.includes("download")))
      .toBe(true);
  });

  it("a refused replay shows the engine's refusal VERBATIM, naming the entries", async () => {
    const refusal = "2 entry(ies) have elided parameters and cannot be replayed faithfully: "
      + "#3 add_wall, #4 map_properties";
    const h = harness({ planThrows: refusal });
    await open(h);
    btn("▶ Build a replay plan")!.click();
    await flush();
    expect(noteTexts().some((t) => t.includes("#4 map_properties"))).toBe(true);
    expect(noteTexts().some((t) => t.includes("Refused"))).toBe(true);
  });

  it("a built plan is shown and nothing is applied", async () => {
    const h = harness();
    await open(h);
    btn("▶ Build a replay plan")!.click();
    await flush();
    expect(noteTexts().some((t) => t.includes("nothing has been applied"))).toBe(true);
  });

  it("refuses a non-integer diff index at the client rather than sending it", async () => {
    const h = harness();
    await open(h);
    const [a, b] = [...document.querySelectorAll("input")] as HTMLInputElement[];
    // `Number("")` is 0, so a blank box passes `Number.isInteger` — this asserts the BLANK is
    // refused, not merely that a non-numeric string is.
    a!.value = ""; b!.value = "1";
    btn("⇄ Diff two runs")!.click();
    await flush();
    expect(h.api.recipeDiff).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain("two entry indices");
    expect(Number("")).toBe(0);                       // the reason, pinned
  });

  it("sends both indices once they are given", async () => {
    const h = harness();
    await open(h);
    const [a, b] = [...document.querySelectorAll("input")] as HTMLInputElement[];
    a!.value = "0"; b!.value = "1";
    btn("⇄ Diff two runs")!.click();
    await flush();
    expect(h.api.recipeDiff).toHaveBeenCalledWith("p1", 0, 1);
  });

  it("reports an unreadable log instead of opening an empty panel", async () => {
    const h = harness();
    h.api.recipeLog = vi.fn(async () => { throw new Error("log exists but could not be parsed"); });
    document.body.replaceChildren();
    recipeLogButton(h.deps).click();
    await flush();
    expect(h.deps.notify).toHaveBeenCalledWith(
      expect.stringContaining("could not be parsed"), "error");
    expect(document.querySelector(".result-overlay")).toBeNull();
  });
});
