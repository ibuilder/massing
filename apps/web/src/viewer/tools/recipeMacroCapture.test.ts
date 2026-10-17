import { describe, expect, it, vi } from "vitest";

import type { EditMacro, RecipeLogEntry } from "../../api/types";
import type { CaptureDeps, Step } from "./recipeMacroCapture";
import {
  at, buildMacro, capturable, leaves, libraryForSave, renderMacroCapture, replaceAt, stepRows,
  suggestName,
} from "./recipeMacroCapture";

/**
 * MACRO-CAPTURE — the four things the module header says this has to get right, one describe each.
 *
 * `saveMacros` was the last callerless method of RECIPE-MACROS and the last unwritable member of
 * `services/api/test_stored_standard_writable.py`'s register, left with its reason written down when
 * its three siblings were wired. These assertions are what makes closing it safe rather than
 * nominal: three of the four rules below are refusals, and a refusal nobody tests is a refusal that
 * works until somebody simplifies it.
 */

const E = (over: Partial<RecipeLogEntry> = {}): RecipeLogEntry => ({
  recipe: "add_wall",
  params: { start: [0, 0], end: [6, 0], height: 3 },
  params_elided: false,
  actor: "ada@example.com",
  at: "2026-10-12T08:14:03+00:00",
  source_in: "m_1.ifc",
  source_out: "m_2.ifc",
  ...over,
});

const LOG: RecipeLogEntry[] = [
  E(),
  E({ recipe: "add_column", params: { point: [6, 0], height: 3.5 } }),
  E({ recipe: "mesh", params: { v: { __elided__: true, bytes: 90210 } }, params_elided: true }),
  E({ recipe: "set_pset", params: { pset: "Pset_WallCommon", prop: "LoadBearing", value: true } }),
];

describe("① an elided entry cannot become a step", () => {
  it("refuses it BY NAME and keeps the rest of the capture", () => {
    const r = capturable(LOG, 0, 3);
    expect(r.steps.map((s) => s.recipe)).toEqual(["add_wall", "add_column", "set_pset"]);
    expect(r.indices).toEqual([0, 1, 3]);
    expect(r.refused).toHaveLength(1);
    expect(r.refused[0]).toContain("#2 mesh");
    expect(r.refused[0]).toContain("elided");
  });

  it("a range of nothing but elided entries yields no steps, and buildMacro says so", () => {
    const r = capturable(LOG, 2, 2);
    expect(r.steps).toEqual([]);
    expect(buildMacro("x", "", r.steps, [])).toEqual(
      { why: "nothing to capture — every selected entry was refused" });
  });

  it("refuses an unusable range rather than silently clamping it", () => {
    expect(capturable(LOG, 3, 1).why).toContain("from ≤ to");
    expect(capturable(LOG, -1, 2).why).toContain("from ≤ to");
    expect(capturable(LOG, 9, 9).why).toContain("outside the log");
  });

  it("clamps `to` to the log's end, which is a cap and not an error", () => {
    expect(capturable(LOG, 3, 999).steps.map((s) => s.recipe)).toEqual(["set_pset"]);
  });
});

describe("② the starter set is not silently adopted", () => {
  const macro: EditMacro = { id: "", name: "Bay", params: [], steps: [] };
  const starter: EditMacro[] = [
    { id: "bay-frame", name: "Structural bay", params: [], steps: [] },
  ];

  it("a seeded library saves the NEW macro alone — PUT replaces the whole library", () => {
    const { library, note } = libraryForSave(starter, true, macro);
    expect(library).toEqual([macro]);
    expect(note).toContain("only the new macro");
    expect(note).toContain("not adopted");
  });

  it("a real library is appended to, with every existing macro sent back", () => {
    const saved: EditMacro[] = [{ id: "a", name: "A", params: [], steps: [] },
                                { id: "b", name: "B", params: [], steps: [] }];
    const { library, note } = libraryForSave(saved, false, macro);
    expect(library).toEqual([...saved, macro]);
    expect(note).toContain("2 macro(s) already saved");
    expect(note).toContain("replaces the whole library");
  });
});

describe("③ a parameter is per-OCCURRENCE, not per-value", () => {
  const steps: Step[] = [
    { recipe: "add_wall", params: { start: [0, 0], end: [6, 0], height: 3 } },
    { recipe: "add_column", params: { point: [6, 0], height: 3 } },
  ];

  it("replaces exactly the leaf picked, leaving every other occurrence of the value alone", () => {
    const r = buildMacro("Bay", "", steps, [{ step: 0, path: "end.0", name: "span" }]);
    expect("macro" in r).toBe(true);
    const m = (r as { macro: EditMacro }).macro;
    expect(m.steps[0]!.params).toEqual({ start: [0, 0], end: ["${span}", 0], height: 3 });
    // the OTHER 6 — in step 1's point — is untouched; a per-value rule would have rewritten it
    expect(m.steps[1]!.params).toEqual({ point: [6, 0], height: 3 });
  });

  it("lets two leaves share a name when they hold the same value", () => {
    const r = buildMacro("Bay", "", steps, [{ step: 0, path: "height", name: "h" },
                                            { step: 1, path: "height", name: "h" }]);
    const m = (r as { macro: EditMacro }).macro;
    expect(m.steps[0]!.params.height).toBe("${h}");
    expect(m.steps[1]!.params.height).toBe("${h}");
    expect(m.params).toEqual([{ name: "h", label: "h", default: 3 }]);
  });

  it("REFUSES one name over two different values, because running it would move one of them", () => {
    const r = buildMacro("Bay", "", steps, [{ step: 0, path: "height", name: "z" },
                                            { step: 0, path: "end.0", name: "z" }]);
    expect("why" in r).toBe(true);
    expect((r as { why: string }).why).toContain("two different values");
    expect((r as { why: string }).why).toContain("Use two names");
  });

  it("refuses a name that is not an identifier, and a pick off the end of the capture", () => {
    expect(buildMacro("Bay", "", steps, [{ step: 0, path: "height", name: "2h" }]))
      .toMatchObject({ why: expect.stringContaining("simple identifier") });
    expect(buildMacro("Bay", "", steps, [{ step: 9, path: "height", name: "h" }]))
      .toMatchObject({ why: expect.stringContaining("not in the capture") });
  });

  it("refuses the SAME leaf picked twice — the second would read the first's placeholder", () => {
    // Guarded in `buildMacro` rather than in the screen, which cannot produce it: one checkbox per
    // leaf. A precondition that happens to hold at today's only call site is not a precondition.
    const r = buildMacro("Bay", "", steps, [{ step: 0, path: "height", name: "a" },
                                            { step: 0, path: "height", name: "b" }]);
    expect(r).toMatchObject({ why: expect.stringContaining("picked twice") });
  });

  it("refuses a non-scalar leaf — a list default cannot be prompted as text", () => {
    expect(buildMacro("Bay", "", steps, [{ step: 0, path: "start", name: "p" }]))
      .toMatchObject({ why: expect.stringContaining("not a scalar") });
  });

  it("needs a name", () => {
    expect(buildMacro("  ", "", steps, [])).toEqual({ why: "the macro needs a name" });
  });

  it("does not mutate the captured steps", () => {
    const before = JSON.stringify(steps);
    buildMacro("Bay", "", steps, [{ step: 0, path: "end.0", name: "span" }]);
    expect(JSON.stringify(steps)).toBe(before);
  });
});

describe("④ the captured value becomes the default, which carries the TYPE", () => {
  it("a number stays a number, so macroTool.coerceArg prompts for a number", () => {
    const steps: Step[] = [{ recipe: "add_wall", params: { height: 3.5 } }];
    const m = (buildMacro("W", "", steps, [{ step: 0, path: "height", name: "h" }]) as
      { macro: EditMacro }).macro;
    expect(m.params[0]!.default).toBe(3.5);
    expect(typeof m.params[0]!.default).toBe("number");
  });

  it("a boolean and a string keep their own types too", () => {
    const steps: Step[] = [{ recipe: "set_pset", params: { value: true, pset: "Pset_WallCommon" } }];
    const m = (buildMacro("P", "", steps, [{ step: 0, path: "value", name: "v" },
                                           { step: 0, path: "pset", name: "ps" }]) as
      { macro: EditMacro }).macro;
    expect(m.params).toEqual([{ name: "v", label: "v", default: true },
                              { name: "ps", label: "ps", default: "Pset_WallCommon" }]);
  });
});

describe("the leaf walk and its helpers", () => {
  const steps: Step[] = [{ recipe: "add_wall", params: { start: [0, 1], meta: { tag: "A" }, n: null } }];

  it("finds every scalar with a dotted path, and skips null", () => {
    expect(leaves(steps).list).toEqual([
      { step: 0, path: "start.0", value: 0 },
      { step: 0, path: "start.1", value: 1 },
      { step: 0, path: "meta.tag", value: "A" },
    ]);
  });

  it("REPORTS truncation — an offer list that looks complete is the defect at widget level", () => {
    const big: Step[] = [{ recipe: "mesh", params: { v: Array.from({ length: 50 }, (_, i) => i) } }];
    const r = leaves(big, 10);
    expect(r.list).toHaveLength(10);
    expect(r.truncated).toBe(true);
    expect(leaves(steps, 10).truncated).toBe(false);
  });

  it("reads and replaces at a path without touching its siblings", () => {
    expect(at(steps[0]!.params, "meta.tag")).toBe("A");
    expect(at(steps[0]!.params, "meta.missing")).toBeUndefined();
    expect(at(steps[0]!.params, "start.1")).toBe(1);
    expect(replaceAt(steps[0]!.params, "start.1", "${y}"))
      .toEqual({ start: [0, "${y}"], meta: { tag: "A" }, n: null });
    expect(Array.isArray(replaceAt(steps[0]!.params, "start.1", 9).start)).toBe(true);
  });

  it("suggests a name that is a legal identifier even from a numeric path", () => {
    expect(suggestName(0, "start.0")).toBe("start_0_1");
    expect(suggestName(2, "0")).toBe("p0_3");
    expect(suggestName(0, "")).toBe("value_1");
    expect(/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(suggestName(0, "a.b-c"))).toBe(true);
  });

  it("shows each step's parameters as JSON, so a mistyped capture is visible", () => {
    expect(stepRows(steps)[0]!.k).toBe("1. add_wall");
    expect(stepRows(steps)[0]!.v).toContain('"start":[0,1]');
  });
});

/** ---- the flow, driven through the real screen ----------------------------------------------- */

const flush = () => new Promise((r) => setTimeout(r, 0));
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text));
const notes = () => [...document.querySelectorAll(".result-note")].map((n) => n.textContent ?? "");

function harness(opts: { saveThrows?: string; seeded?: boolean } = {}) {
  const sent: unknown[] = [];
  const api = {
    saveMacros: vi.fn(async (_pid: string, macros: EditMacro[]) => {
      sent.push(macros);
      if (opts.saveThrows) throw new Error(opts.saveThrows);
      return { saved: macros.length, macros };
    }),
  };
  const deps = {
    api: api as unknown as CaptureDeps["api"],
    pid: "p1",
    toolBtn2: (label: string, onClick: () => void) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = onClick;
      return b;
    },
    notify: vi.fn(),
  } satisfies CaptureDeps;
  const lib = { macros: [{ id: "bay-frame", name: "Structural bay", params: [], steps: [] }] as EditMacro[],
                seeded: opts.seeded ?? true };
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  renderMacroCapture(host, deps, LOG, lib);
  return { deps, api, sent, lib, host };
}

describe("the capture screen", () => {
  it("builds on open, naming the refused entry and offering every scalar", async () => {
    harness();
    expect(notes().some((t) => t.includes("entr(ies) refused"))).toBe(true);
    expect(notes().some((t) => t.includes("#2 mesh"))).toBe(true);
    expect(notes().some((t) => t.includes("Nothing is saved until"))).toBe(true);
    expect(document.querySelectorAll('input[type="checkbox"]').length).toBeGreaterThan(5);
  });

  it("saves the new macro ALONE when the library is the starter set", async () => {
    const h = harness({ seeded: true });
    (document.querySelector('input[placeholder="macro name"]') as HTMLInputElement).value = "My bay";
    btn("⇣ Save as a macro")!.click();
    await flush();
    expect(h.api.saveMacros).toHaveBeenCalledTimes(1);
    const sent = h.sent[0] as EditMacro[];
    expect(sent).toHaveLength(1);
    expect(sent[0]!.name).toBe("My bay");
    expect(notes().some((t) => t.includes("only the new macro"))).toBe(true);
    expect(notes().some((t) => t.includes("Saved"))).toBe(true);
  });

  it("appends to a real library and sends every existing macro back", async () => {
    const h = harness({ seeded: false });
    (document.querySelector('input[placeholder="macro name"]') as HTMLInputElement).value = "Second";
    btn("⇣ Save as a macro")!.click();
    await flush();
    const sent = h.sent[0] as EditMacro[];
    expect(sent.map((m) => m.name)).toEqual(["Structural bay", "Second"]);
  });

  it("sends the ticked values as parameters, with their captured defaults", async () => {
    const h = harness({ seeded: false });
    (document.querySelector('input[placeholder="macro name"]') as HTMLInputElement).value = "Param";
    const cbs = [...document.querySelectorAll('input[type="checkbox"]')] as HTMLInputElement[];
    cbs[0]!.checked = true;
    btn("⇣ Save as a macro")!.click();
    await flush();
    const sent = h.sent[0] as EditMacro[];
    const made = sent[sent.length - 1]!;
    expect(made.params).toHaveLength(1);
    expect(JSON.stringify(made.steps[0]!.params)).toContain("${");
  });

  it("renders a build refusal and sends NOTHING", async () => {
    const h = harness();
    btn("⇣ Save as a macro")!.click();     // no name given
    await flush();
    expect(h.api.saveMacros).not.toHaveBeenCalled();
    expect(notes().some((t) => t.includes("needs a name"))).toBe(true);
  });

  it("renders the server's 422 VERBATIM — it names the step and the recipe", async () => {
    const refusal = "macro 'My bay' step 2: unknown recipe 'add_colmn'";
    const h = harness({ saveThrows: refusal });
    (document.querySelector('input[placeholder="macro name"]') as HTMLInputElement).value = "My bay";
    btn("⇣ Save as a macro")!.click();
    await flush();
    expect(notes().some((t) => t.includes("unknown recipe 'add_colmn'"))).toBe(true);
    expect(h.deps.notify).not.toHaveBeenCalled();
  });

  it("rebuilding with a narrower range changes the step list", async () => {
    harness();
    (document.querySelector('input[placeholder="from"]') as HTMLInputElement).value = "3";
    (document.querySelector('input[placeholder="to"]') as HTMLInputElement).value = "3";
    btn("⟳ Build the step list")!.click();
    await flush();
    expect(notes().some((t) => t.includes("1 step(s) from entr(ies) 3"))).toBe(true);
    expect(notes().some((t) => t.includes("entr(ies) refused"))).toBe(false);
  });
});
