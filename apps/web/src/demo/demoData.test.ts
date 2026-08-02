/**
 * The public demo must answer every request the shell makes before a visitor clicks anything.
 *
 * WHY THIS EXISTS
 *   `demoData.json` is the whole backend for the GitHub Pages demo — a captured
 *   `{ "GET <path>": <body> }` map. When the shell asks for a path the capture lacks, nothing
 *   errors: the client falls back, the panel renders its empty state, and the page still looks
 *   fine. That is the failure mode, not a broken one.
 *
 *   Measured 2026-08-01 against a live browser session: FOUR endpoints the shell requests on every
 *   page load had never been in the crawl — `/vitals`, `/work-queue`, `/jobs`, `/presence`. The
 *   vitals strip is the walkthrough's own headline claim ("the same six numbers follow you into
 *   every room"); on the public demo those six numbers were not there, and had not been for 25
 *   releases. The module registry was meanwhile perfectly in sync (133 = 133), which is exactly why
 *   nobody noticed: the dimension that was checked was fine.
 *
 *   `build_demo_data.py` already carried this lesson in a comment about `/rooms`, which rotted the
 *   same way and was fixed the same way. A lesson recorded as a comment protects one endpoint; this
 *   test protects the set.
 *
 * WHAT IS ASSERTED
 *   Presence AND substance. A captured endpoint whose body is `{}` or `[]` renders the same empty
 *   panel as a missing one, so each critical fixture must also carry the shape the UI reads.
 */
import { describe, expect, it } from "vitest";
import demoData from "./demoData.json";

const KEYS = Object.keys(demoData as Record<string, unknown>);

/** Find the captured body for a path fragment (the capture keys carry a project uuid). */
function captured(fragment: string): unknown {
  const k = KEYS.find((key) => key.includes(fragment));
  return k === undefined ? undefined : (demoData as Record<string, unknown>)[k];
}

describe("the demo capture is a working backend, not a plausible one", () => {
  it("has a realistic number of fixtures — a truncated capture is not a demo", () => {
    // Guards the whole file: a crawl that failed halfway would otherwise pass every check below
    // that happens to hit an early endpoint.
    expect(KEYS.length).toBeGreaterThan(900);
  });

  /*
   * Every entry is an endpoint the shell requests BEFORE any user interaction, so a missing one is
   * visible on first paint. Verified against the network log of a real session rather than read off
   * the client source — what the app asks for is a runtime fact.
   */
  const STARTUP: [string, string][] = [
    ["/modules", "the module registry — the whole register surface"],
    ["/rooms", "the room rail (fell back to FALLBACK_ROOMS before v0.3.786)"],
    ["/reference/disciplines", "discipline colours + IFC-class map"],
    ["/vitals", "the six numbers along the bottom of every room"],
    ["/work-queue", "the ball-in-court queue: NEXT BEST ACTION + the Work room"],
    ["/jobs", "the runs inbox"],
    ["/presence", "who else is here"],
  ];

  for (const [path, why] of STARTUP) {
    it(`serves ${path} — ${why}`, () => {
      expect(captured(path), `demoData.json has no fixture for ${path}; the demo renders this `
        + "panel empty and nothing errors. Add it to build_demo_data.py's crawl and re-run it.")
        .toBeDefined();
    });
  }

  it("the vitals fixture carries the six numbers the walkthrough promises", () => {
    // Presence is not enough: an empty object is captured, present, and useless. The walkthrough
    // names these six explicitly, so they are the contract.
    const v = captured("/vitals") as Record<string, unknown> | undefined;
    expect(v).toBeDefined();
    for (const k of ["lod", "area", "cost_sf", "float", "irr", "health"]) {
      expect(Object.keys(v!), `vitals fixture is missing ${k}`).toContain(k);
    }
  });

  it("the work-queue fixture actually has work in it", () => {
    // An empty queue is a legitimate runtime state and a useless demo: the room whose whole point
    // is "what is in your court" would open blank for every visitor.
    //
    // The shape is the server's, read from the fixture rather than guessed — the first draft of
    // this test asserted `items[]` and failed against a real, correct capture. The endpoint returns
    // `{ buckets, total, actionable, no_action, note }`, where `buckets` is the due-window grouping
    // (`undated` is deliberately its own bucket, not the bottom of `later`).
    const w = captured("/work-queue") as
      { buckets?: unknown[]; total?: number; actionable?: number } | undefined;
    expect(w, "no work-queue fixture").toBeDefined();
    expect(Array.isArray(w!.buckets) && w!.buckets.length > 0,
      "the demo's work queue has no buckets — the Work room would render nothing").toBe(true);
    expect((w!.total ?? 0) > 0,
      `the demo's work queue holds ${w!.total} items; the NEXT BEST ACTION card needs at least one`)
      .toBe(true);
  });

  it("the module registry fixture matches the room rail's expectations", () => {
    const mods = captured("/modules") as { key: string }[] | undefined;
    expect(Array.isArray(mods) && mods.length > 100,
      `demo /modules has ${Array.isArray(mods) ? mods.length : "no"} modules`).toBe(true);
  });
});
