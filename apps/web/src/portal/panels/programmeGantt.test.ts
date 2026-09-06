import { describe, expect, it } from "vitest";

import { programmeBars } from "./programmeGantt";

const P = (id: string, name = id, activities = 3) => ({ id, name, activities });

describe("programmeBars", () => {
  it("places each project on a shared span, ordered by start", () => {
    const r = programmeBars({
      projects: [P("b", "Fit-out"), P("a", "Enabling")],
      project_starts: { a: "2026-01-01", b: "2026-02-01" },
      project_finishes: { a: "2026-01-31", b: "2026-03-01" },
    });
    expect(r.bars.map((x) => x.name)).toEqual(["Enabling", "Fit-out"]);
    expect(r.span).toEqual({ start: "2026-01-01", finish: "2026-03-01", days: 60 });
    expect(r.bars[0]!.left).toBe(0);
    // Enabling runs 30 of the 59-day span; Fit-out starts 31 days in.
    expect(Math.round(r.bars[0]!.width)).toBe(51);
    expect(Math.round(r.bars[1]!.left)).toBe(53);
    expect(r.bars[0]!.days).toBe(31);
    expect(r.unplotted).toEqual([]);
  });

  it("marks the bar that finishes on the programme finish as driving", () => {
    const r = programmeBars({
      projects: [P("a"), P("b")],
      project_starts: { a: "2026-01-01", b: "2026-01-01" },
      project_finishes: { a: "2026-01-10", b: "2026-02-10" },
    });
    expect(r.bars.find((x) => x.id === "b")!.driving).toBe(true);
    expect(r.bars.find((x) => x.id === "a")!.driving).toBe(false);
  });

  // A HALF-DATED PROJECT GETS NO BAR. Substituting the programme's own start or finish for the
  // missing end would draw a bar that looks measured and is not — the defect this module exists to
  // avoid, so it is asserted rather than left to the renderer.
  it("refuses a bar when either end is missing, and says which", () => {
    const r = programmeBars({
      projects: [P("a"), P("b", "No finish"), P("c", "No start"), P("d", "Nothing")],
      project_starts: { a: "2026-01-01", b: "2026-01-05", d: undefined as unknown as string },
      project_finishes: { a: "2026-01-31", c: "2026-02-01" },
    });
    expect(r.bars.map((x) => x.id)).toEqual(["a"]);
    expect(r.unplotted).toEqual([
      { id: "b", name: "No finish", reason: "no finish date" },
      { id: "c", name: "No start", reason: "no start date" },
      { id: "d", name: "Nothing", reason: "no scheduled dates" },
    ]);
    // and the span is computed from the plotted bar alone, never widened by a half-dated project
    expect(r.span).toEqual({ start: "2026-01-01", finish: "2026-01-31", days: 31 });
  });

  it("refuses a bar whose finish precedes its start", () => {
    const r = programmeBars({
      projects: [P("a")],
      project_starts: { a: "2026-03-01" }, project_finishes: { a: "2026-01-01" },
    });
    expect(r.bars).toEqual([]);
    expect(r.unplotted[0]!.reason).toBe("finish precedes start");
    expect(r.span).toBeNull();
  });

  it("survives a single-day programme without NaN widths", () => {
    const r = programmeBars({
      projects: [P("a")],
      project_starts: { a: "2026-01-01" }, project_finishes: { a: "2026-01-01" },
    });
    expect(r.bars[0]!.left).toBe(0);
    expect(r.bars[0]!.width).toBe(100);
    expect(r.bars[0]!.days).toBe(1);
    expect(r.span!.days).toBe(1);
  });

  it("flags the projects an external link names — their dates are a commitment", () => {
    const r = programmeBars({
      projects: [P("enabling"), P("fitout"), P("infra")],
      project_starts: { enabling: "2026-01-01", fitout: "2026-02-01", infra: "2026-01-15" },
      project_finishes: { enabling: "2026-01-31", fitout: "2026-03-01", infra: "2026-02-15" },
      external_links: [{ predecessor: "enabling::A1", successor: "fitout::B1" }],
    });
    expect(r.bars.find((x) => x.id === "enabling")!.linked).toBe(true);
    expect(r.bars.find((x) => x.id === "fitout")!.linked).toBe(true);
    expect(r.bars.find((x) => x.id === "infra")!.linked).toBe(false);
  });

  // `Date` normalises an out-of-range DAY instead of rejecting it — "2026-02-30" becomes
  // 2026-03-02 — while an out-of-range MONTH is NaN. A normalised date is an invented one, so it
  // must not reach a bar.
  it("rejects a date the Date constructor would silently normalise", () => {
    const r = programmeBars({
      projects: [{ id: "a", name: "Feb 30", activities: 1 }],
      project_starts: { a: "2026-02-30" }, project_finishes: { a: "2026-03-31" },
    });
    expect(r.bars).toEqual([]);
    expect(r.unplotted[0]!.reason).toBe("no start date");
    expect(r.span).toBeNull();
  });

  it("rejects an impossible month outright", () => {
    const r = programmeBars({
      projects: [{ id: "a", name: "Month 13", activities: 1 }],
      project_starts: { a: "2026-01-01" }, project_finishes: { a: "2026-13-01" },
    });
    expect(r.bars).toEqual([]);
    expect(r.unplotted[0]!.reason).toBe("no finish date");
  });

  // A bare `startsWith` matches "p10::A1" against a project "p1", flagging the wrong bar as linked
  // and leaving the right one plain. Ordering matters: `p1` is found first by `find`.
  it("does not let one project id prefix-match another", () => {
    const r = programmeBars({
      projects: [{ id: "p1", name: "One", activities: 1 },
                 { id: "p10", name: "Ten", activities: 1 }],
      project_starts: { p1: "2026-01-01", p10: "2026-01-05" },
      project_finishes: { p1: "2026-01-31", p10: "2026-02-05" },
      external_links: [{ predecessor: "p10::A1", successor: "p10::B1" }],
    });
    expect(r.bars.find((x) => x.id === "p10")!.linked).toBe(true);
    expect(r.bars.find((x) => x.id === "p1")!.linked).toBe(false);
  });

  it("returns an empty, well-formed result when the run carried no dates at all", () => {
    const r = programmeBars({ projects: [P("a"), P("b")] });
    expect(r.bars).toEqual([]);
    expect(r.span).toBeNull();
    expect(r.unplotted).toHaveLength(2);
  });
});
