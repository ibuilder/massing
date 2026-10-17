import { afterEach, describe, expect, it, vi } from "vitest";

import type { EditMacro } from "../../api/types";
import type { MacroDeps } from "./macroTool";
import {
  coerceArg, macroArgs, macroButton, macroLibraryNote, macroRows, runNoteHtml, stepPreviewHtml,
} from "./macroTool";

/**
 * MACRO-DARK — RECIPE-MACROS shipped complete and reachable by nothing; this is the door, and these
 * are the three things it had to get right (see the module header for why each is load-bearing).
 *
 * The expand-before-apply flow is driven through the real `macroButton` into the DOM, because the
 * decision this tool makes is *what reaches the server* and a helper test cannot see a button that
 * was never appended. `askText` is stubbed at the module boundary rather than typed into — a prompt
 * modal driven by dispatching events at its own input proves the handler runs when the event
 * arrives, never that a person can make it arrive, which is the failure `roomTabs.ts` records for
 * its refusal control.
 */

vi.mock("../../ui/prompt", () => ({
  askText: vi.fn(),
}));
import { askText } from "../../ui/prompt";

const STARTER: EditMacro = {
  id: "bay-frame",
  name: "Structural bay (2 columns + beam)",
  description: "Two columns joined by a beam at their tops.",
  params: [
    { name: "x0", label: "Column 1 X", default: 0.0 },
    { name: "x1", label: "Column 2 X", default: 6.0 },
    { name: "y", label: "Y", default: 0.0 },
    { name: "height", label: "Column height (m)", default: 3.5 },
    { name: "storey", label: "Storey", default: null },
  ],
  steps: [
    { recipe: "add_column", params: { point: ["${x0}", "${y}"], height: "${height}" } },
    { recipe: "add_column", params: { point: ["${x1}", "${y}"], height: "${height}" } },
    { recipe: "add_beam", params: { start: ["${x0}", "${y}", "${height}"] } },
  ],
};

describe("① the starter set is not a saved library", () => {
  it("says so, and not in a passing tone", () => {
    const n = macroLibraryNote(true, 1);
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("Starter set");
    expect(n.html).toContain("Nothing has been saved for this project");
  });

  it("a saved library reads as one", () => {
    const n = macroLibraryNote(false, 4);
    expect(n.kind).toBe("ok");
    expect(n.html).toContain("4 saved macro(s)");
    expect(n.html).not.toContain("Starter set");
  });

  it("an empty list is neither — it should not be reachable, and says that", () => {
    const n = macroLibraryNote(true, 0);
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("No macros");
  });
});

describe("② an argument is typed from its DECLARATION, never from the text", () => {
  it("a numeric default makes a NUMBER — the defect is a coordinate arriving as a string", () => {
    const r = coerceArg("6", { name: "x1", default: 6.0 });
    expect(r).toEqual({ value: 6 });
    expect(typeof (r as { value: unknown }).value).toBe("number");
  });

  it("refuses an unparseable number instead of sending JSON `null`", () => {
    // `JSON.stringify({x: NaN})` is `{"x":null}`, so this is the difference between an error and a
    // value the engine reads as supplied.
    const r = coerceArg("six", { name: "x1", label: "Column 2 X", default: 6.0 });
    expect(r).toEqual({ why: 'Column 2 X: "six" is not a number' });
    expect(JSON.stringify({ x: Number("six") })).toBe('{"x":null}');   // the reason, pinned
  });

  it("does NOT guess a number from text when the declaration has no type", () => {
    // The storey name "2" is a string. The same "looks numeric" rule that correctly types a
    // coordinate destroys this, which is why the rule keys on the default and not the input.
    expect(coerceArg("2", { name: "storey", default: null })).toEqual({ value: "2" });
    expect(coerceArg("Level 1", { name: "storey", default: null })).toEqual({ value: "Level 1" });
  });

  it("types a boolean default both ways and refuses the rest", () => {
    expect(coerceArg("yes", { name: "lb", default: false })).toEqual({ value: true });
    expect(coerceArg("0", { name: "lb", default: false })).toEqual({ value: false });
    expect(coerceArg("maybe", { name: "lb", default: false })).toMatchObject({ why: expect.any(String) });
  });
});

describe("③ a blank answer omits the key, so the server's own default applies", () => {
  it("omits rather than sending a blank", () => {
    expect(coerceArg("", { name: "storey", default: null })).toEqual({ omit: true });
    expect(coerceArg("   ", { name: "x0", default: 0.0 })).toEqual({ omit: true });
  });

  it("but a REQUIRED param with no answer is refused here, not at the engine", () => {
    expect(coerceArg("", { name: "span", label: "Span", required: true }))
      .toEqual({ why: "Span is required" });
  });

  it("builds the args body with only the answered keys", () => {
    const built = macroArgs(STARTER.params, ["1.5", "", "0", "3", ""]);
    expect(built).toEqual({ args: { x0: 1.5, y: 0, height: 3 } });
    expect(Object.keys((built as { args: object }).args)).not.toContain("storey");
    expect(Object.keys((built as { args: object }).args)).not.toContain("x1");
  });

  it("stops at the first reason it cannot be built", () => {
    expect(macroArgs(STARTER.params, ["1", "nope", "0", "3", ""]))
      .toMatchObject({ why: expect.stringContaining("Column 2 X") });
  });
});

describe("the library table and the previews", () => {
  it("names each macro's chain and parameter count", () => {
    const [row] = macroRows([STARTER]);
    expect(row!.k).toBe(STARTER.name);
    expect(row!.v).toBe("3 step(s): add_column → add_column → add_beam · 5 parameter(s)");
  });

  it("says 'no parameters' rather than '0 parameter(s)'", () => {
    expect(macroRows([{ ...STARTER, params: [] }])[0]!.v).toContain("no parameters");
  });

  it("shows the expansion as JSON, so a mistyped argument is VISIBLE", () => {
    const html = stepPreviewHtml([{ recipe: "add_column", params: { point: ["6", 0] } }]);
    expect(html).toContain("nothing has been applied yet");
    expect(html).toContain("&quot;point&quot;:[&quot;6&quot;,0]");   // the quotes ARE the signal
  });

  it("escapes a recipe name — the step list is server text in innerHTML", () => {
    expect(stepPreviewHtml([{ recipe: "<img src=x>", params: {} }])).not.toContain("<img");
  });

  it("the run note says the chain undoes as ONE step, and warns when the viewer is stale", () => {
    const res = { steps: [{ recipe: "add_column", changed: "0aB" }], step_count: 1, out: "m_2.ifc",
                  macro: "bay-frame" };
    expect(runNoteHtml(res, "done", true)).toContain("undoes as a single step");
    expect(runNoteHtml(res, "done", true)).not.toContain("could not reload");
    expect(runNoteHtml(res, "done", false)).toContain("the viewer could not reload");
  });
});

/** ---- the flow, driven through the real tool ------------------------------------------------- */

function harness(opts: { seeded?: boolean; source?: string | null; collabFails?: boolean } = {}) {
  const calls: { expand: unknown[]; run: unknown[] } = { expand: [], run: [] };
  const api = {
    listMacros: vi.fn(async () => ({ macros: [STARTER], seeded: opts.seeded ?? true })),
    expandMacro: vi.fn(async (_pid: string, id: string, args: Record<string, unknown>) => {
      calls.expand.push({ id, args });
      return { macro: id, name: STARTER.name, step_count: 2,
               steps: [{ recipe: "add_column", params: { point: [1.5, 0] } },
                       { recipe: "add_beam", params: { start: [1.5, 0, 3] } }] };
    }),
    runMacro: vi.fn(async (_pid: string, id: string, args: Record<string, unknown>,
                           o?: { publish?: boolean; baseSource?: string }) => {
      calls.run.push({ id, args, o });
      return { steps: [{ recipe: "add_column", changed: 1 }, { recipe: "add_beam", changed: 1 }],
               step_count: 2, out: "m_2.ifc", macro: id, publish: "running" };
    }),
    collabSnapshot: vi.fn(async () => {
      if (opts.collabFails) throw new Error("offline");
      return { model: { source: opts.source === undefined ? "m_1.ifc" : opts.source, version: 3,
                        element_count: 10, has_model: true },
               editors: [], editor_count: 0 };
    }),
  };
  const deps = {
    toolBtn2: (label: string, onClick: () => void) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = onClick;
      return b;
    },
    api: api as unknown as MacroDeps["api"],
    pid: "p1",
    notify: vi.fn(),
    waitForPublish: vi.fn(async () => "done"),
    loadProjectModel: vi.fn(async () => true),
  } satisfies MacroDeps;
  return { deps, api, calls };
}

const flush = () => new Promise((r) => setTimeout(r, 0));
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text));
const noteTexts = () => [...document.querySelectorAll(".result-note")].map((n) => n.textContent ?? "");

afterEach(() => { vi.mocked(askText).mockReset(); });

/** The answers for the starter bay's prompts, in declaration order. `null` is a CANCEL.
 *
 *  The first draft wrote `vals[i++] ?? ""`, which collapsed the cancel into a blank answer — so the
 *  cancel test drove the whole flow and failed on the step after the one it was about. The
 *  empty-versus-absent confusion this branch keeps fixing, committed in the harness written to test
 *  a tool that distinguishes them. */
function answer(...vals: (string | null)[]) {
  let i = 0;
  vi.mocked(askText).mockImplementation(async () => (i < vals.length ? vals[i++]! : ""));
}

async function open(h: ReturnType<typeof harness>) {
  document.body.replaceChildren();
  const b = macroButton(h.deps);
  b.click();
  await flush();
}

describe("the expand-before-apply flow", () => {
  it("asks, expands, and applies NOTHING until the second button", async () => {
    const h = harness();
    answer("1.5", "", "0", "3", "");
    await open(h);
    expect(noteTexts().some((t) => t.includes("Starter set"))).toBe(true);
    btn("▶ Structural bay")!.click();
    await flush();
    // the args the server was asked to expand are the coerced, blank-omitted ones
    expect(h.calls.expand).toEqual([{ id: "bay-frame", args: { x0: 1.5, y: 0, height: 3 } }]);
    expect(h.api.runMacro).not.toHaveBeenCalled();
    expect(noteTexts().some((t) => t.includes("nothing has been applied yet"))).toBe(true);
    expect(btn("✔ Apply these 2 step(s)")).toBeDefined();
  });

  it("applies with the SAME args it previewed, under the COLLAB-1 lock", async () => {
    const h = harness();
    answer("1.5", "", "0", "3", "");
    await open(h);
    btn("▶ Structural bay")!.click();
    await flush();
    btn("✔ Apply these")!.click();
    await flush();
    expect(h.calls.run).toEqual([{ id: "bay-frame", args: { x0: 1.5, y: 0, height: 3 },
                                   o: { publish: true, baseSource: "m_1.ifc" } }]);
    expect(h.deps.loadProjectModel).toHaveBeenCalled();
    expect(noteTexts().some((t) => t.includes("Applied 2 step(s)"))).toBe(true);
  });

  it("a cancelled prompt asks the server NOTHING", async () => {
    const h = harness();
    answer("1.5", null);
    await open(h);
    btn("▶ Structural bay")!.click();
    await flush();
    expect(h.api.expandMacro).not.toHaveBeenCalled();
    expect(btn("✔ Apply these")).toBeUndefined();
  });

  it("a bad argument is refused before the server is asked", async () => {
    const h = harness();
    answer("six", "", "", "", "");
    await open(h);
    btn("▶ Structural bay")!.click();
    await flush();
    expect(h.api.expandMacro).not.toHaveBeenCalled();
    expect(h.deps.notify).toHaveBeenCalledWith(expect.stringContaining("is not a number"), "error");
  });

  it("runs WITHOUT the lock when the signature cannot be read, and SAYS so", async () => {
    const h = harness({ collabFails: true });
    answer("1.5", "", "0", "3", "");
    await open(h);
    btn("▶ Structural bay")!.click();
    await flush();
    btn("✔ Apply these")!.click();
    await flush();
    expect(noteTexts().some((t) => t.includes("NOT protected against a concurrent publish"))).toBe(true);
    expect((h.calls.run[0] as { o: { baseSource?: string } }).o.baseSource).toBeUndefined();
  });

  it("treats a NULL signature the same way — a project with no source is not a locked one", async () => {
    const h = harness({ source: null });
    answer("1.5", "", "0", "3", "");
    await open(h);
    btn("▶ Structural bay")!.click();
    await flush();
    btn("✔ Apply these")!.click();
    await flush();
    expect(noteTexts().some((t) => t.includes("NOT protected"))).toBe(true);
  });

  it("a saved library does not claim the starter set", async () => {
    const h = harness({ seeded: false });
    await open(h);
    expect(noteTexts().some((t) => t.includes("1 saved macro(s)"))).toBe(true);
    expect(noteTexts().some((t) => t.includes("Starter set"))).toBe(false);
  });
});
