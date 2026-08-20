import { describe, expect, it } from "vitest";
import {
  ACROSS_PROJECTS, ALL_DESTS, ANALYSE_HOME, ANALYSE_TASK_KEYS, STAGES_BY_WS,
  destButtonActive, destsForRail, stagesFor,
} from "./destinations";
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

  // The label said "the five that exist" for two releases after the spine reached seven. The
  // assertion was always `ROOM_IDS`, so nothing was wrong except the sentence — but a stale count in
  // a test NAME is read as documentation, which is exactly how prose drifts (R36 audit, 2026-08-02).
  it("rooms only into rooms that exist", () => {
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

  it("Design's Analyse & check is one home, not three overlapping dests", () => {
    const stage = STAGES_BY_WS.design!.find(([name]) => name === "Analyse & check");
    expect(stage, "Analyse & check stage missing").toBeTruthy();
    const keys = stage![1].map((d) => d.key);
    expect(keys[0]).toBe(ANALYSE_HOME);
    for (const k of ANALYSE_TASK_KEYS) {
      expect(keys, `${k} must not be a rail sibling of Analyse`).not.toContain(k);
    }
    expect(ALL_DESTS.map((d) => d.key)).toEqual(expect.arrayContaining([...ANALYSE_TASK_KEYS, ANALYSE_HOME]));
  });

  it("the room rail hides the three tasks wherever Analyse is listed", () => {
    const mixed = [
      { key: ANALYSE_HOME, icon: "🔬", label: "Analyse" },
      { key: "__modelqa__", icon: "✅", label: "Check the model" },
      { key: "__documents__", icon: "📁", label: "Documents" },
    ];
    expect(destsForRail(mixed).map((d) => d.key)).toEqual([ANALYSE_HOME, "__documents__"]);
    expect(destsForRail([{ key: "__modelqa__", icon: "✅", label: "x" }]).map((d) => d.key))
      .toEqual(["__modelqa__"]);
  });

  it("Analyse stays lit when a task dest is open", () => {
    expect(destButtonActive(ANALYSE_HOME, "__modelqa__")).toBe(true);
    expect(destButtonActive(ANALYSE_HOME, ANALYSE_HOME)).toBe(true);
    expect(destButtonActive("__documents__", "__modelqa__")).toBe(false);
  });

  it("uses `goto` only for destinations that genuinely live in another workspace", () => {
    // Two, and both are deliberate: underwriting renders in the finance workspace, and the drawing
    // set is its own full-page surface rather than a portal panel.
    //
    // `goto` has a real cost, which is why this list is pinned and why `spine.test.ts` asserts no
    // room's home appears in it: such a destination CANNOT be a
    // room's landing target. It switches workspace instead of activating a rail item, so nothing can
    // observe it having arrived — Deal lands on Portfolio for exactly this reason.
    expect(ALL_DESTS.filter((d) => d.goto).map((d) => d.key).sort())
      .toEqual(["__drawings__", "__uw__"]);
  });
});
