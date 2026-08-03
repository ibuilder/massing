import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiClient, ModuleDef, ModuleRecord } from "../api/client";
import type { ModuleFilterOp } from "../api/types";
import { type PortalHost, PortalUI } from "./portal";

/**
 * R36-EMPTY-STATE — the register renderer reaches all three empty states.
 *
 * `ui/empty.test.ts` proves the three states differ. This file proves the renderer can actually
 * *decide* between them, which is where the item's premise-check landed: the copy was never the hard
 * part, the plumbing was.
 *
 * Two things were structurally impossible before this change, and each is asserted here:
 *
 *   1. **A filtered-to-nothing register could not be told from a never-used one.** The branch tested
 *      `filter.q || filter.state` and knew nothing about `filter.fields` — the ⧧ Filter panel, which
 *      is the filter UI most likely to empty a register. So "amount ≥ 1M" produced "No change events
 *      yet" *plus* curated guidance about where change events come from: a confident wrong answer in
 *      the one place a reader has no way to check it.
 *   2. **A failed fetch had no state at all.** The records `await` was the only unguarded one in
 *      `openModule`, so a rejection escaped through the `void openModule(...)` call sites and left
 *      the "Loading …" skeleton up permanently.
 *
 * **Why drive the real renderer rather than assert on the source.** A regex over `portal.ts` would
 * pass on a branch that is present and unreachable, and the defect being fixed *is* an unreachable
 * branch. So this mounts `PortalUI` against a stub API and reads `data-empty` off the DOM it
 * produced — the same attribute a person reads in the live app.
 */

const MOD: ModuleDef = {
  key: "spec_section",
  name: "Specifications",
  section: "Design",
  icon: "§",
  pinnable: false,
  fields: [
    { name: "code", label: "Code", type: "text" },
    { name: "system", label: "System", type: "select", options: ["Concrete", "Masonry"] },
  ],
  workflow: { initial: "draft", states: ["draft", "issued"], transitions: [] },
};

type Filter = {
  q?: string; state?: string; offset?: number;
  fields?: Record<string, { op: ModuleFilterOp; value: string }>;
};

/** `openModule` is private — this is the renderer under test, reached the way the app reaches it. */
type Renderer = { openModule: (m: ModuleDef, filter?: Filter) => Promise<void> };

/** What the renderer asked the server for — the half of "clear filters" a DOM check cannot see. */
type Asked = { q?: string; state?: string; filters: unknown[] };

function mount(records: () => ModuleRecord[] | Promise<ModuleRecord[]>) {
  const root = document.createElement("div");
  document.body.appendChild(root);
  const asked: Asked[] = [];
  const moduleRecordsFiltered = vi.fn(async (_pid: string, _key: string, opts: Asked) => {
    asked.push(opts);
    return records();
  });
  const api = {
    moduleRecordsFiltered,
    listViews: async () => [],
    url: (p: string) => p,
  } as unknown as ApiClient;
  const host: PortalHost = {
    api,
    projectId: () => "p1",
    anchorPoint: () => null,
    selectedGuid: () => null,
    onSelectGuids: () => {},
    onPinsChanged: () => {},
    setStatus: () => {},
  };
  const ui = new PortalUI(root, host);
  return { root, ui, render: (ui as unknown as Renderer).openModule.bind(ui), moduleRecordsFiltered, asked };
}

const state = (root: HTMLElement) => root.querySelector<HTMLElement>(".empty-state")?.dataset.empty ?? null;
const button = (root: HTMLElement) => root.querySelector<HTMLButtonElement>(".empty-state button");

beforeEach(() => { document.body.innerHTML = ""; localStorage.clear(); });

describe("R36-EMPTY-STATE — an empty register names its reason", () => {
  it("an untouched register invites: `none`, with the curated upstream guidance", async () => {
    const { root, render } = mount(() => []);
    await render(MOD);
    expect(state(root)).toBe("none");
    expect(root.textContent).toContain("No specifications yet");
    // the R24-EMPTY-GUIDE line for this module, still carried through
    expect(root.textContent).toContain("Import a specification");
    expect(button(root)!.textContent).toContain("New");
  });

  it("a register emptied by the ⧧ Filter panel says so — the case that was invisible", async () => {
    const { root, render } = mount(() => []);
    await render(MOD, { fields: { code: { op: "eq", value: "09 91 00" } } });
    expect(state(root)).toBe("filtered");
    expect(root.textContent).toContain("1 filter is");
    expect(root.textContent).toContain("hidden, not missing");
    // and it must NOT offer the "where do these come from" guidance — records may well exist
    expect(root.textContent).not.toContain("Import a specification");
  });

  it("counts every clause narrowing the view — search, state and fields together", async () => {
    const { root, render } = mount(() => []);
    await render(MOD, { q: "concrete", state: "draft", fields: { code: { op: "eq", value: "03" } } });
    expect(state(root)).toBe("filtered");
    expect(root.textContent).toContain("3 filters are");
  });

  it("clearing the filters re-fetches with none of them — not just the search box", async () => {
    const { root, render, moduleRecordsFiltered, asked } = mount(() => []);
    await render(MOD, { q: "concrete", state: "draft", fields: { code: { op: "eq", value: "03" } } });
    button(root)!.click();
    await vi.waitFor(() => expect(moduleRecordsFiltered).toHaveBeenCalledTimes(2));
    const last = asked.at(-1)!;
    expect(last.q).toBeUndefined();
    expect(last.state).toBeUndefined();
    expect(last.filters).toEqual([]);
    await vi.waitFor(() => expect(state(root)).toBe("none"));
  });

  it("a failed fetch renders `failed` with the reason — not a permanent Loading skeleton", async () => {
    const { root, render } = mount(() => { throw new Error("HTTP 503 — register unavailable"); });
    await render(MOD);
    expect(state(root)).toBe("failed");
    expect(root.textContent).toContain("Couldn't load specifications");
    expect(root.textContent).toContain("HTTP 503");
    expect(root.textContent).not.toContain("Loading");
    // the twin: the outage screen must not offer the create/import surface that made a working
    // register look broken. A back link, a reason and a retry — nothing that pretends to work.
    expect(root.querySelectorAll("input").length).toBe(0);
    expect(button(root)!.textContent).toContain("Retry");
  });

  it("retry re-runs the same request, and a register that comes back renders rows", async () => {
    let fail = true;
    const rows = [{ id: "r1", ref: "SPEC-1", title: "Concrete", workflow_state: "draft", data: {} }];
    const { root, render, moduleRecordsFiltered, asked } = mount(() => {
      if (fail) throw new Error("HTTP 503");
      return rows as unknown as ModuleRecord[];
    });
    await render(MOD, { q: "concrete" });
    expect(state(root)).toBe("failed");
    fail = false;
    button(root)!.click();
    // wait for the ROWS, not for the empty state to vanish: `openModule` clears the root before it
    // renders, so "no `.empty-state` yet" is also true of a half-drawn screen
    await vi.waitFor(() => expect(root.textContent).toContain("SPEC-1"));
    expect(state(root)).toBeNull();
    expect(moduleRecordsFiltered).toHaveBeenCalledTimes(2);
    // retry keeps the filter the reader had — dropping it would silently change what they asked for
    expect(asked.at(-1)!.q).toBe("concrete");
  });

  it("a register with rows shows no empty state at all", async () => {
    const rows = [{ id: "r1", ref: "SPEC-1", title: "Concrete", workflow_state: "draft", data: {} }];
    const { root, render } = mount(() => rows as unknown as ModuleRecord[]);
    await render(MOD);
    expect(state(root)).toBeNull();
    expect(root.textContent).toContain("SPEC-1");
  });

  it("the three states are decided distinctly by the SAME renderer on the same module", async () => {
    const seen: (string | null)[] = [];
    for (const [rows, filter] of [
      [() => [], undefined],
      [() => [], { fields: { code: { op: "eq" as ModuleFilterOp, value: "03" } } }],
      [() => { throw new Error("boom"); }, undefined],
    ] as [() => ModuleRecord[], Filter | undefined][]) {
      document.body.innerHTML = "";
      const { root, render } = mount(rows);
      await render(MOD, filter);
      seen.push(state(root));
    }
    expect(seen).toEqual(["none", "filtered", "failed"]);
  });
});
