import { describe, expect, it, vi } from "vitest";

import type { DeltaDeps } from "./deltaCommit";
import { DeltaStore, deltaBadge, deltaCommitter, deltaIndicator, deltaStatusText, recipeRefusalNote } from "./deltaCommit";

/**
 * R42-COMMIT-DELTA — the pending-geometry state, and the rule that it must be VISIBLE.
 *
 * The performance half of this feature (keep the converted fragment instead of re-deriving the
 * model) is not what these tests are about — that is measured, not asserted. What is asserted here
 * is the half that can silently rot: **a partial state must render differently from a complete
 * one.** The product decision was explicitly for a visible pending state rather than an automatic
 * background consolidate, so "the user can tell" is a requirement, not a nicety.
 */

describe("recipeRefusalNote", () => {
  it("reads the nested changed.status the /edit route actually returns", () => {
    expect(recipeRefusalNote({
      recipe: "set_array_params",
      changed: { status: "would_delete_authored", note: "keep them" },
    })).toBe("keep them");
    expect(recipeRefusalNote({ recipe: "add_wall", changed: { guid: "x" } })).toBeNull();
  });
});
  it("counts what is pending and keeps authoring order", () => {
    const s = new DeltaStore();
    s.add({ modelId: "d1", label: "Wall" });
    s.add({ modelId: "d2", label: "Door" });
    expect(s.count).toBe(2);
    expect(s.entries().map((e) => e.label)).toEqual(["Wall", "Door"]);
  });

  it("REPLACES a repeated model id instead of appending it", () => {
    // Two records pointing at one loader model would leak: disposing it once leaves the other
    // claiming geometry that is gone. The id is the identity, so re-adding must overwrite.
    const s = new DeltaStore();
    s.add({ modelId: "d1", label: "Wall" });
    s.add({ modelId: "d1", label: "Wall (retried)" });
    expect(s.count).toBe(1);
    expect(s.entries()[0]!.label).toBe("Wall (retried)");
  });

  it("removes by id and reports whether anything went", () => {
    const s = new DeltaStore();
    s.add({ modelId: "d1", label: "Wall" });
    expect(s.remove("d1")).toBe(true);
    expect(s.remove("d1")).toBe(false);   // second remove is a no-op, not a silent success
    expect(s.count).toBe(0);
  });

  it("exposes ids, because disposing geometry is done by id", () => {
    const s = new DeltaStore();
    s.add({ modelId: "d1", label: "Wall" });
    s.add({ modelId: "d2", label: "Door" });
    expect(s.ids()).toEqual(["d1", "d2"]);
  });
});

describe("the status text is the honest-state rule, in words", () => {
  it("says something DEFINITE at zero rather than nothing", () => {
    // The empty string would make "nothing pending" and "this indicator is broken" identical.
    const t = deltaStatusText(0);
    expect(t.length).toBeGreaterThan(0);
    expect(t).toMatch(/up to date/i);
  });

  it("names the count and the consequence when edits are pending", () => {
    const t = deltaStatusText(3);
    expect(t).toContain("3 edits");
    // The consequence is the point. "3 pending" alone tells a reader a number, not what is true of
    // what they are looking at.
    expect(t).toMatch(/not yet rebuilt/i);
    expect(t, "the data being CURRENT is the reassuring half and must be said too")
      .toMatch(/data is current/i);
  });

  it("reads correctly for exactly one", () => {
    expect(deltaStatusText(1)).toContain("1 edit");
    expect(deltaStatusText(1)).not.toContain("1 edits");
  });

  it("zero and non-zero never render the same", () => {
    // The rule stated as a property rather than as three examples of it.
    expect(deltaStatusText(0)).not.toBe(deltaStatusText(1));
    expect(deltaBadge(0)).not.toBe(deltaBadge(1));
    expect(deltaBadge(0)).toMatch(/up to date/i);
    expect(deltaBadge(2)).toContain("2");
  });
});

describe("the rail control", () => {
  it("is disabled and quiet with nothing pending", () => {
    const s = new DeltaStore();
    const { el } = deltaIndicator(s, () => {});
    const btn = el.querySelector("button")!;
    expect(btn.disabled).toBe(true);
    expect(el.textContent).toMatch(/up to date/i);
  });

  it("enables and states the count once an edit is pending", () => {
    const s = new DeltaStore();
    const { el, refresh } = deltaIndicator(s, () => {});
    s.add({ modelId: "d1", label: "Wall" });
    refresh();
    const btn = el.querySelector("button")!;
    expect(btn.disabled).toBe(false);
    expect(btn.textContent).toContain("1");
    expect(el.textContent).toMatch(/not yet rebuilt/i);
  });

  it("repaints from the STORE after a consolidate, not from the attempt", async () => {
    // The store is the truth. A button that painted itself "done" because the click finished would
    // lie whenever the consolidate failed — which is exactly when the deltas still matter, because
    // they are the only correct geometry on screen.
    const s = new DeltaStore();
    s.add({ modelId: "d1", label: "Wall" });
    const onConsolidate = vi.fn(async () => { throw new Error("publish failed"); });
    const { el, refresh } = deltaIndicator(s, async () => {
      await onConsolidate().catch(() => {});   // the caller swallows; the store is untouched
    });
    refresh();
    el.querySelector("button")!.click();
    await new Promise((r) => setTimeout(r, 0));
    expect(onConsolidate).toHaveBeenCalled();
    // Still pending, still enabled, still saying so.
    expect(s.count).toBe(1);
    expect(el.querySelector("button")!.disabled).toBe(false);
    expect(el.textContent).toMatch(/not yet rebuilt/i);
  });

  it("goes quiet only when the store is actually emptied", async () => {
    const s = new DeltaStore();
    s.add({ modelId: "d1", label: "Wall" });
    const { el, refresh } = deltaIndicator(s, () => { s.clear(); });
    refresh();
    el.querySelector("button")!.click();
    await new Promise((r) => setTimeout(r, 0));
    expect(s.count).toBe(0);
    expect(el.querySelector("button")!.disabled).toBe(true);
    expect(el.textContent).toMatch(/up to date/i);
  });
});

/**
 * The commit DECISION, which is the reason this module exists at all.
 *
 * Inside `authorAndReload` this branch was unreachable by any suite — it wanted a loader, a fragment
 * server, a project and a running convert. As nine named functions it wants none of them, so the one
 * thing that actually matters is three lines to assert: **with a preview fragment, nothing
 * reconverts and nothing reloads.**
 */
function harness(over: Partial<DeltaDeps> = {}) {
  const store = new DeltaStore();
  const notes: string[] = [];
  const d = {
    store,
    refresh: vi.fn(),
    editIfc: vi.fn(async () => ({})),
    publish: vi.fn(async () => ({})),
    awaitPublish: vi.fn(async () => "done"),
    reloadModel: vi.fn(async () => true),
    reloadPins: vi.fn(async () => ({})),
    dispose: vi.fn(async () => ({})),
    clearDraft: vi.fn(),
    markFailed: vi.fn(),
    notify: vi.fn((m: string) => { notes.push(m); }),
    ...over,
  } satisfies DeltaDeps;
  return { d, store, notes, c: deltaCommitter(d) };
}

describe("commit — with a preview fragment", () => {
  it("authors WITHOUT publishing and never reloads the model", async () => {
    const { d, store, c } = harness();
    const out = await c.commit("add_wall", { x: 1 }, "Wall", "pv-1", "GUID000000000000000001");

    expect(out).toEqual({ applied: true, refused: false });
    // publish=false on the edit: the whole saving is not converting here. And the preview's GUID is
    // handed over, so the element that lands in the IFC IS the one this fragment draws — without it
    // the kept geometry carries an id no index has, which is how it shipped for a few hours.
    expect(d.editIfc).toHaveBeenCalledWith("add_wall", { x: 1 }, false, "GUID000000000000000001");
    expect(store.entries()[0]!.guid).toBe("GUID000000000000000001");
    // reconvert=false on the publish: reindex so the DATA is current, without re-deriving geometry.
    expect(d.publish).toHaveBeenCalledWith(false);
    // The call that costs 37 s on a 1,000-element model, not made. `awaitPublish` IS called — but
    // for the reindex, in the background, and `publish` was never asked to reconvert.
    expect(d.reloadModel).not.toHaveBeenCalled();
    expect(d.publish).not.toHaveBeenCalledWith(true);
    // The fragment is kept and recorded, not disposed.
    expect(d.dispose).not.toHaveBeenCalled();
    expect(store.ids()).toEqual(["pv-1"]);
    expect(d.clearDraft).toHaveBeenCalled();   // it is on the record; the amber marker is now a lie
  });

  it("survives a failed reindex — the edit is already durable", async () => {
    // The reindex is fire-and-forget on purpose. Reporting its failure as a failed author would be
    // wrong in the way that costs the most: the edit IS in the IFC, and a user told otherwise redoes
    // it and gets two walls.
    const { store, c } = harness({ publish: vi.fn(async () => { throw new Error("500"); }) });
    const out = await c.commit("add_wall", {}, "Wall", "pv-1");
    expect(out.applied).toBe(true);
    expect(store.count).toBe(1);
  });

  it("takes the delta back off the books when the author itself fails", async () => {
    const { d, store, c } = harness({ editIfc: vi.fn(async () => { throw new Error("refused"); }) });
    const out = await c.commit("add_wall", {}, "Wall", "pv-1");
    expect(out).toEqual({ applied: false, refused: true });
    expect(store.count, "a record with no edit behind it would ask for a rebuild of nothing").toBe(0);
    expect(d.dispose).toHaveBeenCalledWith("pv-1");
    expect(d.markFailed).toHaveBeenCalled();
  });

  it("drops the delta if a LATER step throws, after the promotion", async () => {
    // The promotion happens before `reloadPins`. If the record survived a late throw it would name
    // geometry the catch had just disposed — the rail would keep asking to rebuild something that
    // is no longer on screen.
    const { d, store, c } = harness({ reloadPins: vi.fn(async () => { throw new Error("pins"); }) });
    await c.commit("add_wall", {}, "Wall", "pv-1");
    expect(store.count).toBe(0);
    expect(d.dispose).toHaveBeenCalledWith("pv-1");
  });
});

describe("commit — with no preview fragment", () => {
  it("still does the FULL publish, because there is no geometry to keep", async () => {
    const { d, store, c } = harness();
    const out = await c.commit("add_wall", {}, "Wall", null);

    expect(out.applied).toBe(true);
    expect(d.editIfc).toHaveBeenCalledWith("add_wall", {}, true);
    expect(d.awaitPublish).toHaveBeenCalled();
    expect(d.reloadModel).toHaveBeenCalled();
    expect(store.count, "nothing was promoted, so nothing is pending").toBe(0);
  });

  it("marks the draft failed when the publish does not finish", async () => {
    const { d, c } = harness({ awaitPublish: vi.fn(async () => "error") });
    const out = await c.commit("add_wall", {}, "Wall", null);
    expect(out.applied).toBe(false);
    expect(d.markFailed).toHaveBeenCalled();
    expect(d.reloadModel).not.toHaveBeenCalled();
  });

  it("does not silently become the delta path — the two are told apart by the fragment alone", async () => {
    // Stated as a pair so a regression that sent BOTH cases down one branch is visible. Asserting
    // only the delta case would pass on a commit() that had lost its `else` entirely.
    const withPv = harness();
    const without = harness();
    await withPv.c.commit("r", {}, "L", "pv-1", "GUID000000000000000002");
    await without.c.commit("r", {}, "L", null);
    expect(withPv.d.editIfc).toHaveBeenCalledWith("r", {}, false, "GUID000000000000000002");
    // No preview means no GUID to adopt: the server mints one, which is the pre-existing behaviour.
    // Asserted on the raw call so "passed undefined" and "passed nothing" stay distinguishable —
    // toHaveBeenCalledWith(..., undefined) would demand a 4th argument that is never sent.
    const call = vi.mocked(without.d.editIfc).mock.calls[0]!;
    expect(call.slice(0, 3)).toEqual(["r", {}, true]);
    expect(call[3]).toBeUndefined();
    expect(withPv.d.reloadModel).not.toHaveBeenCalled();
    expect(without.d.reloadModel).toHaveBeenCalled();
  });

  it("a would_delete_authored recipe is a refusal, not a successful publish", async () => {
    const { d, c, notes } = harness({
      editIfc: vi.fn(async () => ({
        recipe: "set_array_params",
        changed: { status: "would_delete_authored", changed: false, note: "moved members kept" },
      })),
    });
    const out = await c.commit("set_array_params", { guid: "g" }, "array 1×1", null);
    expect(out).toEqual({ applied: false, refused: true });
    expect(d.awaitPublish).not.toHaveBeenCalled();
    expect(d.reloadModel).not.toHaveBeenCalled();
    expect(notes.some((n) => /refused/.test(n))).toBe(true);
  });
});

describe("consolidate", () => {
  it("reconverts, reloads, and only THEN forgets the deltas", async () => {
    const { d, store, c } = harness();
    store.add({ modelId: "pv-1", label: "Wall" });
    await c.consolidate();
    expect(d.publish).toHaveBeenCalledWith(true);
    expect(d.reloadModel).toHaveBeenCalled();
    expect(store.count).toBe(0);
    expect(d.refresh).toHaveBeenCalled();
  });

  it("KEEPS the deltas when the rebuild does not finish", async () => {
    // The state in which the deltas matter most: the base geometry is unchanged, so they are the
    // only correct shapes on screen. Clearing them here would blank the user's work on a flake.
    const { store, c } = harness({ awaitPublish: vi.fn(async () => "error") });
    store.add({ modelId: "pv-1", label: "Wall" });
    await c.consolidate();
    expect(store.count).toBe(1);
  });

  it("KEEPS the deltas when the publish request itself throws", async () => {
    const { d, store, c } = harness({ publish: vi.fn(async () => { throw new Error("network"); }) });
    store.add({ modelId: "pv-1", label: "Wall" });
    await c.consolidate();
    expect(store.count).toBe(1);
    expect(d.reloadModel).not.toHaveBeenCalled();
  });
});

describe("the two paths meeting", () => {
  it("a successful full publish retires the deltas it also rebuilt", async () => {
    // Draw one element with a preview (delta pending), then run an edit with no preview. That second
    // path reconverts the IFC — which already contains the first edit — so the base geometry is now
    // complete, and `reloadModel`'s disposeAll has reclaimed the delta model. A record that outlived
    // that would name disposed geometry AND keep the rail demanding a rebuild that already happened.
    const { d, store, c } = harness();
    await c.commit("add_wall", {}, "Wall", "pv-1");
    expect(store.count).toBe(1);

    await c.commit("add_door", {}, "Door", null);
    expect(store.count, "the reconvert covered the pending edit too").toBe(0);
    expect(d.reloadModel).toHaveBeenCalled();
  });

  it("a FAILED full publish leaves them alone", async () => {
    // Nothing was rebuilt, so the deltas are still the only geometry those elements have.
    const { store, c } = harness({ awaitPublish: vi.fn(async () => "error") });
    store.add({ modelId: "pv-1", label: "Wall" });
    await c.commit("add_door", {}, "Door", null);
    expect(store.count).toBe(1);
  });
});

describe("the reindex window is stated, not glossed", () => {
  it("says the data is still updating while the reindex is in flight", async () => {
    // The roadmap's second hazard for this feature, made visible. `publish` resolves on ACCEPT, so
    // the window that matters runs until the poll reaches a terminal state — and for that whole
    // window "the data is current" would be a false claim about searches and quantities.
    let release: (s: string) => void = () => {};
    const { d, store, c } = harness({
      awaitPublish: vi.fn(() => new Promise<string>((r) => { release = r; })),
    });
    await c.commit("add_wall", {}, "Wall", "pv-1");

    expect(store.reindexing).toBe(true);
    expect(deltaStatusText(store.count, store.reindexing)).toMatch(/still updating/i);
    expect(deltaStatusText(store.count, store.reindexing)).not.toMatch(/data is current/i);

    release("done");
    await c.settled();
    expect(store.reindexing).toBe(false);
    expect(deltaStatusText(store.count, store.reindexing)).toMatch(/data is current/i);
    expect(d.refresh).toHaveBeenCalled();
  });

  it("clears the window even when the reindex fails", async () => {
    // A stuck "still updating" would be its own lie — permanently warning about a catch-up that is
    // never coming. The claim has to end when the attempt ends, whichever way it ended.
    const { store, c } = harness({ publish: vi.fn(async () => { throw new Error("500"); }) });
    await c.commit("add_wall", {}, "Wall", "pv-1");
    await c.settled();
    expect(store.reindexing).toBe(false);
    expect(store.count, "and the edit still stands").toBe(1);
  });

  it("counts overlapping reindexes so the first to return does not clear the second", async () => {
    const releases: ((s: string) => void)[] = [];
    const { store, c } = harness({
      awaitPublish: vi.fn(() => new Promise<string>((r) => releases.push(r))),
    });
    await c.commit("add_wall", {}, "Wall", "pv-1");
    await c.commit("add_door", {}, "Door", "pv-2");
    expect(releases).toHaveLength(2);

    releases[0]!("done");
    await new Promise((r) => setTimeout(r, 0));
    expect(store.reindexing, "one is still running").toBe(true);

    releases[1]!("done");
    await c.settled();
    expect(store.reindexing).toBe(false);
  });

  it("settled() resolves immediately when nothing is running", async () => {
    // Otherwise a caller that awaits it before any edit would hang — and a helper that only works
    // after the fact is a trap for the export/takeoff callers it exists for.
    const { c } = harness();
    await expect(c.settled()).resolves.toBeUndefined();
  });
});
