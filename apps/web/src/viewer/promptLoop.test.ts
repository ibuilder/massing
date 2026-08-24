import { describe, expect, it } from "vitest";

import { parseCadCommand } from "./cadCommands";
import { begin, step, toLine, type PromptEvent, type PromptState } from "./promptLoop";

/**
 * The reducer is pure, so every test below drives it with plain values — no DOM, no viewport, no clock.
 * That is the property the module exists for: the interactive CAD flow is normally only testable by
 * driving a renderer, which is why it usually is not tested at all.
 *
 * The load-bearing test is the last group: a collected command must come out as a line the EXISTING
 * parser accepts and turns into the same recipe a typed line would. Two paths, one parser.
 */
const run = (s: PromptState, ...events: PromptEvent[]) => events.reduce(step, s);

describe("begin", () => {
  it("arms a known verb and asks for its first argument", () => {
    const s = begin("WALL")!;
    expect(s.command).toBe("WALL");
    expect(s.status).toBe("collecting");
    expect(s.prompt).toBe("Specify start point");
  });

  it("resolves an alias to the canonical name", () => {
    expect(begin("w")!.command).toBe("WALL");
    expect(begin("COL")!.command).toBe("COLUMN");
  });

  it("returns null for a verb with no interactive spec", () => {
    expect(begin("NOPE")).toBeNull();
  });

  // SPACE's only argument is optional, so it is ready the moment it is armed. A loop that insisted on
  // asking would make `SPACE` require an extra Enter that the typed path does not.
  it("a command whose arguments are all optional is READY immediately", () => {
    const s = begin("SPACE")!;
    expect(s.status).toBe("ready");
    expect(toLine(s)).toBe("SPACE");
  });
});

describe("collecting", () => {
  it("advances through the required arguments and becomes ready", () => {
    const s = run(begin("WALL")!, { t: "token", text: "0,0" }, { t: "token", text: "5,0" });
    expect(s.status).toBe("ready");
    expect(toLine(s)).toBe("WALL 0,0 5,0");
  });

  it("a picked point is formatted as a coordinate token", () => {
    const s = run(begin("WALL")!, { t: "pick", at: [1.5, -2.25] }, { t: "pick", at: [4, 0] });
    expect(toLine(s)).toBe("WALL 1.5,-2.25 4,0");
  });

  // Float noise from a raycast would otherwise render as 2.0000000000000004 in the command line and,
  // worse, in the echo the user is asked to trust.
  it("rounds a picked point to the millimetre", () => {
    const s = run(begin("WALL")!, { t: "pick", at: [2.0000000000000004, 1 / 3] }, { t: "pick", at: [5, 0] });
    expect(toLine(s)).toBe("WALL 2,0.333 5,0");
  });

  it("optional arguments can be supplied", () => {
    const s = run(begin("WALL")!, { t: "token", text: "0,0" }, { t: "token", text: "5,0" },
                  { t: "token", text: "2.7" });
    expect(toLine(s)).toBe("WALL 0,0 5,0 2.7");
  });
});

describe("errors are NON-FATAL — the whole point", () => {
  it("a bad number keeps the collected values and stays on the argument", () => {
    const s = run(begin("WALL")!, { t: "token", text: "0,0" }, { t: "token", text: "5,0" },
                  { t: "token", text: "tall" });
    // `ready` here, because height is optional and both required points are in — the command is
    // committable. It is NOT closed: the typo is reported and the height can still be typed.
    expect(s.status).toBe("ready");
    expect(s.error).toMatch(/not a number/);
    expect(s.tokens).toEqual(["0,0", "5,0"]);          // nothing lost
    // ...and the command can still be completed after the typo.
    expect(toLine(step(s, { t: "token", text: "2.7" }))).toBe("WALL 0,0 5,0 2.7");
  });

  it("a pick offered to a non-point argument is refused by name, not swallowed", () => {
    const s = run(begin("LEVEL")!, { t: "token", text: "Roof" }, { t: "pick", at: [1, 2] });
    expect(s.error).toMatch(/elevation \(m\) is not a point/);
    expect(s.tokens).toEqual(["Roof"]);
  });

  it("accept on a REQUIRED argument refuses rather than skipping it", () => {
    const s = step(begin("WALL")!, { t: "accept" });
    expect(s.status).toBe("collecting");
    expect(s.error).toMatch(/required/);
  });

  it("a cleared error does not linger once a good value arrives", () => {
    const bad = run(begin("WALL")!, { t: "token", text: "0,0" }, { t: "token", text: "5,0" },
                    { t: "token", text: "tall" });
    expect(step(bad, { t: "token", text: "3" }).error).toBeUndefined();
  });
});

describe("variadic outline (SLAB)", () => {
  it("keeps taking points and reports progress toward the minimum", () => {
    let s = begin("SLAB")!;
    expect(s.prompt).toMatch(/\[0 of 3\]/);
    s = run(s, { t: "pick", at: [0, 0] }, { t: "pick", at: [4, 0] });
    expect(s.prompt).toMatch(/\[2 of 3\]/);
    expect(s.status).toBe("collecting");
  });

  it("refuses to close below the minimum, and says how short it is", () => {
    const s = run(begin("SLAB")!, { t: "pick", at: [0, 0] }, { t: "accept" });
    expect(s.status).toBe("collecting");
    expect(s.error).toMatch(/need at least 3, have 1/);
  });

  it("closes on accept once the minimum is met", () => {
    const s = run(begin("SLAB")!, { t: "pick", at: [0, 0] }, { t: "pick", at: [4, 0] },
                  { t: "pick", at: [4, 4] }, { t: "accept" });
    expect(s.status).toBe("ready");
    expect(toLine(s)).toBe("SLAB 0,0 4,0 4,4");
  });

  it("takes a thickness after the outline closes", () => {
    const s = run(begin("SLAB")!, { t: "pick", at: [0, 0] }, { t: "pick", at: [4, 0] },
                  { t: "pick", at: [4, 4] }, { t: "accept" }, { t: "token", text: "0.3" });
    expect(toLine(s)).toBe("SLAB 0,0 4,0 4,4 0.3");
  });
});

describe("back and cancel", () => {
  it("back gives up one point and stays inside the outline", () => {
    let s = run(begin("SLAB")!, { t: "pick", at: [0, 0] }, { t: "pick", at: [4, 0] });
    s = step(s, { t: "back" });
    expect(s.tokens).toEqual(["0,0"]);
    expect(s.prompt).toMatch(/\[1 of 3\]/);
  });

  it("back returns to the previous fixed argument and re-asks for it", () => {
    let s = run(begin("WALL")!, { t: "token", text: "0,0" });
    expect(s.prompt).toBe("Specify end point");
    s = step(s, { t: "back" });
    expect(s.tokens).toEqual([]);
    expect(s.prompt).toBe("Specify start point");
  });

  it("back on an empty command is a no-op, not an underflow", () => {
    const s = step(begin("WALL")!, { t: "back" });
    expect(s.tokens).toEqual([]);
    expect(s.status).toBe("collecting");
  });

  it("cancel is terminal", () => {
    const s = step(begin("WALL")!, { t: "cancel" });
    expect(s.status).toBe("cancelled");
    expect(() => toLine(s)).toThrow(/cancelled/);
  });

  // `ready` means COMMITTABLE, not closed. The first version of this module froze there and silently
  // dropped the next token, so a typed thickness vanished and the command committed at its default —
  // no error, no value, the worst of the three possible failures.
  it("a READY command still accepts a trailing optional value", () => {
    const done = run(begin("WALL")!, { t: "token", text: "0,0" }, { t: "token", text: "5,0" });
    expect(done.status).toBe("ready");
    expect(toLine(step(done, { t: "token", text: "2.4" }))).toBe("WALL 0,0 5,0 2.4");
  });

  it("...and a pick offered where a number is wanted is refused, not swallowed", () => {
    const done = run(begin("WALL")!, { t: "token", text: "0,0" }, { t: "token", text: "5,0" });
    const after = step(done, { t: "pick", at: [9, 9] });
    expect(after.error).toMatch(/height is not a point/);
    expect(after.tokens).toEqual(["0,0", "5,0"]);      // the stray pick added nothing
  });

  // A pointer-up arriving after the click that finished the command is ordinary, not an error.
  it("events are ignored once every argument is consumed, and after cancel", () => {
    const full = run(begin("WALL")!, { t: "token", text: "0,0" }, { t: "token", text: "5,0" },
                     { t: "token", text: "3" });
    expect(step(full, { t: "pick", at: [9, 9] })).toEqual(full);
    expect(step(step(full, { t: "cancel" }), { t: "token", text: "1,1" }).status).toBe("cancelled");
  });

  it("toLine refuses a half-collected command", () => {
    expect(() => toLine(begin("WALL")!)).toThrow(/collecting/);
  });
});

/**
 * THE LOAD-BEARING GROUP. Collecting tokens instead of typed values is what makes the interactive path
 * and the typed path share one parser; if a collected line did not parse identically, the module would
 * be a second grammar wearing the first one's name.
 */
describe("the collected line is the SAME line the typed path parses", () => {
  it("a clicked wall produces the recipe a typed wall produces", () => {
    const clicked = run(begin("WALL")!, { t: "pick", at: [0, 0] }, { t: "pick", at: [5, 0] },
                        { t: "token", text: "3" });
    const viaLoop = parseCadCommand(toLine(clicked));
    const viaTyped = parseCadCommand("WALL 0,0 5,0 3");
    expect(viaLoop).toEqual(viaTyped);
    expect(viaLoop.kind).toBe("recipe");
  });

  it("relative and polar coordinate forms survive the loop untouched", () => {
    const s = run(begin("WALL")!, { t: "token", text: "0,0" }, { t: "token", text: "@5<0" });
    expect(parseCadCommand(toLine(s))).toEqual(parseCadCommand("WALL 0,0 @5<0"));
  });

  it("a closed slab outline parses as a slab recipe", () => {
    const s = run(begin("SLAB")!, { t: "token", text: "0,0" }, { t: "token", text: "4,0" },
                  { t: "token", text: "4,4" }, { t: "accept" });
    const parsed = parseCadCommand(toLine(s));
    expect(parsed.kind).toBe("recipe");
    expect(parsed).toEqual(parseCadCommand("SLAB 0,0 4,0 4,4"));
  });

  it("every interactively completable command yields a line the parser accepts", () => {
    const cases: Array<[string, PromptEvent[]]> = [
      ["WALL", [{ t: "token", text: "0,0" }, { t: "token", text: "5,0" }]],
      ["COLUMN", [{ t: "token", text: "2,2" }]],
      ["BEAM", [{ t: "token", text: "0,0" }, { t: "token", text: "6,0" }]],
      ["SLAB", [{ t: "token", text: "0,0" }, { t: "token", text: "4,0" }, { t: "token", text: "4,4" },
                { t: "accept" }]],
      ["LEVEL", [{ t: "token", text: "Roof" }, { t: "token", text: "12" }]],
      ["SPACE", []],
    ];
    for (const [verb, events] of cases) {
      const s = run(begin(verb)!, ...events);
      expect(s.status, `${verb} should be ready`).toBe("ready");
      expect(parseCadCommand(toLine(s)).kind, `${verb} -> ${toLine(s)}`).toBe("recipe");
    }
  });
});
