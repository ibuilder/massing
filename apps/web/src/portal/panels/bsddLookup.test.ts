import { describe, expect, it } from "vitest";

import { bsddFailure, bsddFailureText } from "./bsddLookup";

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
