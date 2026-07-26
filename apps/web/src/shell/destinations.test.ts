import { describe, expect, it } from "vitest";
import { ACROSS_PROJECTS, ALL_DESTS, STAGES_BY_WS, stagesFor } from "./destinations";
import { DEST_ROOM, ROOM_IDS, destRoom, unroomedDests } from "./spine";

/**
 * R26-SHELL. The destination catalog left `buildNav()` so it could be checked. These are the checks
 * that were impossible while it was a literal inside a render function — and the first one below is
 * the load-bearing property of the whole spine: **every destination has exactly one room**.
 */
const ALL_KEYS = ALL_DESTS.map((d) => d.key);

describe("every destination is placed, exactly once", () => {
  it("has a room for every destination that exists", () => {
    // Not "most of them". A destination with no room is one the spine silently drops — and an IA
    // restructure's characteristic failure is making something unreachable in a way that looks fine.
    expect(unroomedDests(ALL_KEYS)).toEqual([]);
  });

  it("rooms only into the five that exist", () => {
    for (const [key, room] of Object.entries(DEST_ROOM)) {
      expect(ROOM_IDS, `${key} → ${room}`).toContain(room);
    }
  });

  it("maps nothing that is not a destination — a stale row is a rail entry nobody can reach", () => {
    expect(Object.keys(DEST_ROOM).filter((k) => !ALL_KEYS.includes(k))).toEqual([]);
  });

  it("reports an unknown key rather than defaulting it somewhere plausible", () => {
    expect(destRoom("__does_not_exist__")).toBeNull();
    expect(destRoom("")).toBeNull();
    expect(unroomedDests(["__budget__", "__nope__"])).toEqual(["__nope__"]);
  });

  it("keys are unique across workspaces — the union is deduped, not concatenated", () => {
    expect(new Set(ALL_KEYS).size).toBe(ALL_KEYS.length);
  });
});

describe("stagesFor resolves `needs` instead of the caller remembering to", () => {
  const none = () => false;
  const all = () => true;

  it("drops a destination whose module is not installed", () => {
    const keys = stagesFor("construction", none).flatMap(([, i]) => i.map((d) => d.key));
    expect(keys).not.toContain("__schedule__");     // needs schedule_activity
    expect(keys).not.toContain("__margin__");       // needs cost_code
    expect(keys).toContain("__budget__");           // unconditional
  });

  it("keeps it when the module is there", () => {
    const keys = stagesFor("construction", all).flatMap(([, i]) => i.map((d) => d.key));
    expect(keys).toContain("__schedule__");
    expect(keys).toContain("__assets__");
  });

  it("drops a stage left empty rather than rendering an empty drawer", () => {
    for (const ws of ["construction", "design", "developer"]) {
      for (const [stage, items] of stagesFor(ws, none)) expect(items.length, `${ws}/${stage}`).toBeGreaterThan(0);
    }
  });

  it("appends the cross-project roll-ups to every workspace", () => {
    for (const ws of ["construction", "design", "developer", "nonsense"]) {
      expect(stagesFor(ws, all).at(-1)![0]).toBe(ACROSS_PROJECTS[0]);
    }
  });

  it("falls back to the builder rail for an unknown workspace, not to nothing", () => {
    const unknown = stagesFor("nonsense", all).map(([s]) => s);
    const builder = stagesFor("construction", all).map(([s]) => s);
    expect(unknown).toEqual(builder);
  });

  it("does not mutate the catalog it filters", () => {
    const before = STAGES_BY_WS.construction!.map(([, i]) => i.length);
    stagesFor("construction", none);
    expect(STAGES_BY_WS.construction!.map(([, i]) => i.length)).toEqual(before);
  });
});

describe("the catalog itself", () => {
  it("gives every destination an icon and a label", () => {
    for (const d of ALL_DESTS) {
      expect(d.icon.length, d.key).toBeGreaterThan(0);
      expect(d.label.trim().length, d.key).toBeGreaterThan(0);
    }
  });

  it("uses `goto` only for the one destination that hops workspaces", () => {
    expect(ALL_DESTS.filter((d) => d.goto).map((d) => d.key)).toEqual(["__uw__"]);
  });
});
