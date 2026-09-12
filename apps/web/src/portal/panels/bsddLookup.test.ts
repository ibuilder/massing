import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { bsddFailure, bsddFailureText, requestGate } from "./bsddLookup";

/**
 * BSDD-LOOKUP's behavioural half. `api/bsdd.test.ts` proves the client CARRIES the status;
 * this proves the screen SPENDS it — and they are different questions. A client that raised a
 * perfect `HttpError` into a panel that rendered every failure as "no results" would pass the
 * first file and ship the defect this one exists to prevent.
 *
 * The failure being guarded is specific: bSDD is a remote reference service, so "the dictionary
 * is unreachable", "the dictionary has no such class" and "your search matched nothing" are three
 * different answers that a blank list renders identically. One says try again, one says that class
 * does not exist, one says your query was wrong.
 */
describe("classifying a failed bSDD call", () => {
  it("reads 502 as the reference service being unreachable", () => {
    expect(bsddFailure(502)).toBe("unavailable");
  });

  it("reads 404 as the dictionary answering, with no such class", () => {
    // The distinction that matters: 404 is bSDD SUCCEEDING at being asked. Folding it into
    // "unavailable" would tell the reader to wait for a recovery that will never change the answer.
    expect(bsddFailure(404)).toBe("not-found");
  });

  it("refuses to guess on any other status", () => {
    for (const s of [0, 400, 401, 403, 500, 503]) {
      expect(bsddFailure(s), `status ${s}`).toBe("unknown");
    }
  });

  it("does not treat 503 or 500 as the service being down", () => {
    // Deliberate and easy to get wrong the other way: our API converts a bSDD outage to 502
    // SPECIFICALLY so the panel can say so. A 500 is our own bug and a 503 is our own deployment —
    // neither is evidence about buildingSMART, and claiming otherwise misdirects the reader.
    expect(bsddFailure(500)).not.toBe("unavailable");
    expect(bsddFailure(503)).not.toBe("unavailable");
  });
});

describe("what the reader is told", () => {
  it("says the service is unavailable AND that this is not an empty result", () => {
    const t = bsddFailureText("unavailable", "the dictionary");
    expect(t).toContain("unavailable");
    // The load-bearing clause. Without it the sentence still reads like "nothing found".
    expect(t).toContain("not an empty result");
    expect(t).toContain("the dictionary");
  });

  it("says the class does not exist, without inviting a retry", () => {
    const t = bsddFailureText("not-found", "that class");
    expect(t).toContain("no such class");
    expect(t).not.toMatch(/try again/i);
  });

  it("carries the underlying message only when it has nothing better to say", () => {
    expect(bsddFailureText("unknown", "that class", "boom")).toContain("boom");
    // ...and never leaks the transport's words into the two states the product can describe itself.
    expect(bsddFailureText("unavailable", "x", "boom")).not.toContain("boom");
    expect(bsddFailureText("not-found", "x", "boom")).not.toContain("boom");
  });
});

/**
 * The stale-response guard (CodeRabbit review, PR #540). The lookup card's two actions — search,
 * and open a class — both write their result into the SAME element after an await, so before this
 * the slower request won regardless of which was asked for last.
 *
 * Tested here rather than through the DOM because the defect is a SCHEDULING ORDER. A rendering
 * test would have to provoke a specific interleaving to see it, and would pass by accident whenever
 * the responses happened to arrive in request order — which is most of the time, and is exactly why
 * this kind of bug ships.
 */
describe("the shared request gate", () => {
  it("lets the newest request write", () => {
    const g = requestGate();
    const gen = g.start();
    expect(g.isCurrent(gen)).toBe(true);
  });

  it("locks out an earlier request once a later one starts", () => {
    const g = requestGate();
    const first = g.start();
    const second = g.start();
    // The real sequence: search "wall", search "door", then "wall" resolves LAST and must not win.
    expect(g.isCurrent(first)).toBe(false);
    expect(g.isCurrent(second)).toBe(true);
  });

  it("is shared across both actions, so a class detail cannot overwrite a newer search", () => {
    // One gate, not one per endpoint. Two independent counters would each be internally consistent
    // and still let this through, because what is contended is the output element, not the route.
    const g = requestGate();
    const openClass = g.start();     // user clicks a result
    const newSearch = g.start();     // user hits "← results" / searches again before it lands
    expect(g.isCurrent(openClass)).toBe(false);
    expect(g.isCurrent(newSearch)).toBe(true);
  });

  it("gives each request a distinct generation, so none can be mistaken for another", () => {
    const g = requestGate();
    const seen = new Set([g.start(), g.start(), g.start()]);
    expect(seen.size).toBe(3);
  });

  it("starts with nothing current, so a generation never claimed cannot write", () => {
    // Guards the off-by-one: if `current` began at 1 and `start()` returned the pre-increment
    // value, a request holding 0 would read as current and the gate would be open by default.
    const g = requestGate();
    expect(g.isCurrent(0)).toBe(false);
  });
});

/**
 * ...and that the PANEL actually wires ONE gate into both writers.
 *
 * The unit tests above assert a property of a single `requestGate()` instance. They say nothing
 * about how `standards.ts` uses it — giving each action its OWN gate typechecks cleanly, leaves
 * every test above green, and reinstates exactly the bug they exist to forbid, because what is
 * contended is the output element rather than the endpoint.
 *
 * *Asserting an outcome without asserting the path to it ran is vacuous.* So this reads the panel.
 */
describe("the standards panel wires one gate, not one per action", () => {
  //: `__dirname`, not `import.meta.url` — under vitest's transform the module URL is a virtual
  //: path that does not exist on disk (the reason `api/httpStatus.test.ts` gives).
  const src = readFileSync(join(resolve(__dirname), "standards.ts"), "utf8");

  it("is reading the panel it thinks it is", () => {
    // Without this the two assertions below pass forever against an empty string.
    expect(src).toContain("bsddSearch");
    expect(src).toContain("bsddClass");
  });

  it("constructs exactly one request gate", () => {
    const gates = src.match(/requestGate\(\)/g) ?? [];
    expect(gates).toHaveLength(1);
  });

  it("guards every write that follows an await on it", () => {
    // Both async writers must consult the gate before touching the shared element: one `start()`
    // each, and a check in both the success and the failure path (4 checks total).
    expect((src.match(/bdGate\.start\(\)/g) ?? [])).toHaveLength(2);
    expect((src.match(/bdGate\.isCurrent\(/g) ?? []).length).toBeGreaterThanOrEqual(4);
  });
});
