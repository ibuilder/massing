import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import type { ScriptThisDeps } from "./scriptThis";
import { scriptThisTool } from "./scriptThis";

/**
 * BATCH-DARK — three callers looped `editIfc` once per step while the route built for them was dark.
 *
 * `POST /projects/{pid}/edit/batch` applies a step sequence as ONE guard-prechecked, all-or-nothing
 * version with one edit-history entry, and its own docstring names the caller: *"so a multi-step NL
 * command undoes as a single step"*. It had no client method at all. The three loops each paid for
 * that in a different currency:
 *
 *  - **this window** hid the partial write — `catch` said only "apply failed" with k of n steps
 *    already written to the model;
 *  - **the AI command bar** compensated with a republish and reported "stopped after k/n";
 *  - **the dimensional-lock solver** counted and reported "Applied k of n".
 *
 * *A partial write reported as a failure is worse than a failure, because the reader believes
 * nothing happened.*
 *
 * This file drives the window — it is the one of the three that can be driven, since the other two
 * live inside `initViewerApp`, which needs a WebGL context and a Fragments worker. It asserts the
 * one call, the plan mapped into it, and that the failure message says nothing was applied.
 */

type Step = { recipe: string; params: Record<string, unknown>; destructive: boolean };

const PLAN: Step[] = [
  { recipe: "add_wall", params: { length: 3 }, destructive: false },
  { recipe: "add_door", params: { host: "w1" }, destructive: false },
];

function mount(over: Partial<ScriptThisDeps> = {}, plan: Step[] = PLAN) {
  const host = document.createElement("div");
  let body!: HTMLElement;
  const batched: unknown[][] = [];
  const singles: string[] = [];
  const notes: string[] = [];
  const api = {
    aiAuthor: vi.fn(async () => ({ plan, needs_clarification: null, source: "claude" })),
    editBatch: vi.fn(async (_pid: string, steps: unknown[]) => { batched.push(steps); return {}; }),
    editIfc: vi.fn(async (_pid: string, recipe: string) => { singles.push(recipe); return {}; }),
  } as unknown as ScriptThisDeps["api"];
  const deps: ScriptThisDeps = {
    api, projectId: "P-1", container: host,
    notify: (m) => notes.push(m),
    showResult: (_t, render) => { body = document.createElement("div"); host.appendChild(body); render(body); },
    selectedGuid: () => null, activeStorey: () => null,
    waitForPublish: async () => "done",
    loadProjectModel: async () => true,
    reloadModelPins: async () => true,
    ...over,
  };
  scriptThisTool(deps);
  const input = () => body.querySelector("input") as HTMLInputElement;
  const buttons = () => [...body.querySelectorAll("button")] as HTMLButtonElement[];
  const interpret = () => buttons().find((b) => b.textContent?.includes("Interpret"))!;
  const apply = () => buttons().find((b) => b.textContent?.includes("Apply"));
  return { host, body: () => body, api, batched, singles, notes, input, interpret, apply };
}

const settle = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

describe("scriptThisTool — one batch, not N applies", () => {
  it("renders the plan it was given", async () => {
    const m = mount();
    m.input().value = "add a wall and a door";
    m.interpret().click();
    await settle();
    expect(m.body().textContent).toContain("add_wall");
    expect(m.body().textContent).toContain("2</b> GUID-safe recipe step(s)".replace("</b>", ""));
  });

  it("applies the whole plan in ONE call and never loops single applies", async () => {
    const m = mount();
    m.input().value = "add a wall and a door";
    m.interpret().click();
    await settle();
    m.apply()!.click();
    await settle();
    expect(m.batched, "the plan must reach the server as one batch").toHaveLength(1);
    expect(m.singles, "a per-step loop is the defect this item removes").toEqual([]);
  });

  it("maps every step, in order, as {recipe, params}", async () => {
    const m = mount();
    m.input().value = "x";
    m.interpret().click();
    await settle();
    m.apply()!.click();
    await settle();
    expect(m.batched[0]).toEqual([
      { recipe: "add_wall", params: { length: 3 } },
      { recipe: "add_door", params: { host: "w1" } },
    ]);
  });

  it("says NOTHING WAS APPLIED when the batch is refused", async () => {
    // The whole user-visible point. The loop's message was "apply failed", which is true and
    // misleading: k-1 steps were already in the model.
    const m = mount({
      api: {
        aiAuthor: vi.fn(async () => ({ plan: [{ recipe: "add_wall", params: {}, destructive: false }],
                                       needs_clarification: null })),
        editBatch: vi.fn(async () => { throw new Error("step 2 (add_door): unknown host"); }),
      } as unknown as ScriptThisDeps["api"],
    });
    m.input().value = "x";
    m.interpret().click();
    await settle();
    m.apply()!.click();
    await settle();
    expect(m.notes.join(" ")).toContain("nothing was applied");
    expect(m.notes.join(" ")).toContain("unknown host");
  });

  it("reads the selection at COMMAND time, not at open time", async () => {
    // The window stays open while the user picks. A value captured at construction would plan every
    // command against whatever was selected when it opened.
    let sel: string | null = null;
    const m = mount({ selectedGuid: () => sel });
    sel = "GUID-AFTER-OPENING";
    m.input().value = "x";
    m.interpret().click();
    await settle();
    expect((m.api.aiAuthor as ReturnType<typeof vi.fn>).mock.calls[0]![2])
      .toMatchObject({ selected_guids: ["GUID-AFTER-OPENING"] });
  });

  it("offers no Apply for a destructive plan", async () => {
    const m = mount({}, [{ recipe: "delete_elements", params: {}, destructive: true }]);
    m.input().value = "delete everything";
    m.interpret().click();
    await settle();
    expect(m.apply()).toBeUndefined();
  });

  it("shows a clarification question instead of a plan", async () => {
    const m = mount({
      api: { aiAuthor: vi.fn(async () => ({ plan: [], needs_clarification: "which storey?" })) } as
        unknown as ScriptThisDeps["api"],
    });
    m.input().value = "add a wall";
    m.interpret().click();
    await settle();
    expect(m.body().textContent).toContain("which storey?");
  });
});

/** The pins: no loop survives at any of the three call sites, and the client posts the right body. */
const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "../../api/authoring.ts"), "utf8");
const app = readFileSync(resolve(here, "../app.ts"), "utf8");
const solver = readFileSync(resolve(here, "authoringSection.ts"), "utf8");

describe("all three call sites batch", () => {
  it("declares editBatch and posts steps with publish", () => {
    expect(client).toMatch(/editBatch\(pid: string, steps:/);
    expect(client).toContain("/edit/batch");
    const b = client.split("editBatch(pid: string")[1]!.slice(0, 600);
    expect(b).toContain('method: "POST"');
    expect(b, "base_source is the optimistic lock and must be omitted, not sent as null")
      .toContain("baseSource\n            ? { steps, publish, base_source: baseSource }");
  });

  it("the AI command bar batches, and its compensating republish is GONE", () => {
    expect(app).toMatch(/await api\.editBatch\(projectId!,/);
    expect(app, "a per-step loop over a plan is the defect")
      .not.toMatch(/for \(let i = 0; i < res\.plan\.length; i\+\+\)/);
    expect(app, "the republish existed only to un-strand a partial write that can no longer happen")
      .not.toContain("republish (deferred to the last step) never fired");
    expect(app).toContain("nothing was applied");
  });

  it("the solver's Apply batches through `planSteps`", () => {
    expect(solver).toMatch(/api\.editBatch\(pid, planSteps\(plan\), false\)/);
    expect(solver, "a per-write loop is the defect")
      .not.toMatch(/for \(const w of plan\.writes\)/);
    expect(solver).toContain("Nothing was applied");
  });

  it("this window left app.ts rather than being copied into it", () => {
    // `app.ts` is on an exact line pin, and the extraction is what paid for the fix. A copy is not
    // a move: two windows for one tool means a change lands in the one nobody is looking at.
    expect(app).toMatch(/scriptThisTool\(\{/);
    expect(app, "the window's own body must be gone from app.ts")
      .not.toContain("Script this — the recipe interface");
  });
});
