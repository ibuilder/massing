import { describe, expect, it, vi } from "vitest";
import { StateStore } from "./state.js";

interface ViewState {
  selection: string[];
  hidden: number;
}

describe("StateStore", () => {
  it("defines a slice and reads it back", () => {
    const store = new StateStore();
    const slice = store.defineSlice<ViewState>("viewer", { selection: [], hidden: 0 });

    expect(slice.get()).toEqual({ selection: [], hidden: 0 });
    expect(store.hasSlice("viewer")).toBe(true);
  });

  it("rejects a duplicate namespace", () => {
    const store = new StateStore();
    store.defineSlice("viewer", {});
    expect(() => store.defineSlice("viewer", {})).toThrowError();
  });

  it("notifies subscribers with next and previous values", () => {
    const store = new StateStore();
    const slice = store.defineSlice<number>("count", 0);
    const listener = vi.fn();
    slice.subscribe(listener);

    slice.set(1);

    expect(listener).toHaveBeenCalledWith(1, 0);
  });

  it("ignores a write that does not change the value", () => {
    const store = new StateStore();
    const slice = store.defineSlice<number>("count", 5);
    const listener = vi.fn();
    slice.subscribe(listener);

    slice.set(5);

    expect(listener).not.toHaveBeenCalled();
  });

  it("isolates a throwing subscriber", () => {
    const store = new StateStore();
    const slice = store.defineSlice<number>("count", 0);
    const good = vi.fn();
    slice.subscribe(() => {
      throw new Error("subscriber failed");
    });
    slice.subscribe(good);

    expect(() => slice.set(1)).not.toThrow();
    expect(good).toHaveBeenCalledOnce();
  });

  describe("select", () => {
    it("only fires when the projection changes", () => {
      const store = new StateStore();
      const slice = store.defineSlice<ViewState>("viewer", { selection: [], hidden: 0 });
      const listener = vi.fn();
      slice.select((s) => s.hidden, listener);

      slice.set({ selection: ["a"], hidden: 0 }); // unrelated field
      expect(listener).not.toHaveBeenCalled();

      slice.set({ selection: ["a"], hidden: 3 });
      expect(listener).toHaveBeenCalledWith(3, 0);
    });

    it("accepts a custom equality function", () => {
      const store = new StateStore();
      const slice = store.defineSlice<ViewState>("viewer", { selection: ["a"], hidden: 0 });
      const listener = vi.fn();
      slice.select(
        (s) => s.selection,
        listener,
        (a, b) => a.length === b.length,
      );

      slice.set({ selection: ["b"], hidden: 0 }); // same length -> equal under this comparator
      expect(listener).not.toHaveBeenCalled();

      slice.set({ selection: ["b", "c"], hidden: 0 });
      expect(listener).toHaveBeenCalledOnce();
    });
  });

  describe("transactions", () => {
    it("coalesces writes into one notification per slice", () => {
      const store = new StateStore();
      const slice = store.defineSlice<number>("count", 0);
      const listener = vi.fn();
      slice.subscribe(listener);

      store.transaction(() => {
        slice.set(1);
        slice.set(2);
        slice.set(3);
      });

      expect(listener).toHaveBeenCalledOnce();
      // The previous value reported is the one from before the transaction opened — subscribers
      // never observed 1 or 2, so claiming `2` was the previous state would be a lie.
      expect(listener).toHaveBeenCalledWith(3, 0);
    });

    it("flushes only when the outermost transaction closes", () => {
      const store = new StateStore();
      const slice = store.defineSlice<number>("count", 0);
      const listener = vi.fn();
      slice.subscribe(listener);

      store.transaction(() => {
        store.transaction(() => slice.set(1));
        expect(listener).not.toHaveBeenCalled();
        slice.set(2);
      });

      expect(listener).toHaveBeenCalledOnce();
      expect(listener).toHaveBeenCalledWith(2, 0);
    });

    it("still flushes if the body throws", () => {
      const store = new StateStore();
      const slice = store.defineSlice<number>("count", 0);
      const listener = vi.fn();
      slice.subscribe(listener);

      expect(() =>
        store.transaction(() => {
          slice.set(1);
          throw new Error("mid-transaction failure");
        }),
      ).toThrow();

      // The write already happened; suppressing the notification would leave subscribers showing
      // stale data with no event to correct it.
      expect(listener).toHaveBeenCalledWith(1, 0);
    });
  });

  describe("snapshot and restore", () => {
    it("round-trips live slices", () => {
      const store = new StateStore();
      const slice = store.defineSlice<number>("count", 1);
      slice.set(9);

      const snapshot = store.snapshot();
      slice.set(0);
      store.restore(snapshot);

      expect(slice.get()).toBe(9);
    });

    it("parks state for a slice that does not exist yet", () => {
      const store = new StateStore();
      // Persistence loads the whole project before the owning plugin has activated.
      store.restore({ "massing/objects": [{ id: "m1" }] });

      const slice = store.defineSlice<unknown[]>("massing/objects", []);
      expect(slice.get()).toEqual([{ id: "m1" }]);
    });

    it("includes parked state in a later snapshot", () => {
      const store = new StateStore();
      store.restore({ "not-loaded/x": 1 });

      // Saving a project must not silently drop the state of plugins that were never activated
      // during this session.
      expect(store.snapshot()).toEqual({ "not-loaded/x": 1 });
    });
  });

  it("releases a slice and its listeners on removal", () => {
    const store = new StateStore();
    const slice = store.defineSlice<number>("count", 0);
    const listener = vi.fn();
    slice.subscribe(listener);

    store.removeSlice("count");
    slice.set(5);

    expect(listener).not.toHaveBeenCalled();
    expect(store.hasSlice("count")).toBe(false);
  });

  it("reports changes to observers", () => {
    const store = new StateStore();
    const slice = store.defineSlice<number>("count", 0);
    const changes: unknown[] = [];
    store.observe((change) => changes.push(change));

    slice.set(1);

    expect(changes).toEqual([{ namespace: "count", next: 1, previous: 0 }]);
  });
});
