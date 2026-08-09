import { describe, expect, it, vi } from "vitest";

import { makeWaitForPublish } from "./publishWait";

/**
 * Nine lines, 24 call sites, no test until now.
 *
 * The three outcomes are asserted as DISTINCT rather than each on its own, because the defect this
 * would catch is not a wrong value — it is two situations collapsing into one return. "the server
 * failed" and "we stopped watching" are different facts about the user's model, and the whole point
 * of returning a string rather than a boolean is that callers can tell them apart.
 */

function reader(states: string[]) {
  let i = 0;
  return {
    calls: () => i,
    publishStatus: vi.fn(async () => ({ state: states[Math.min(i++, states.length - 1)]! })),
  };
}

const fast = { intervalMs: 0, timeoutMs: 2_000 };

describe("waitForPublish", () => {
  it("returns the terminal state the server reported", async () => {
    const r = reader(["queued", "running", "done"]);
    expect(await makeWaitForPublish(r, fast)("p1")).toBe("done");
    expect(r.calls()).toBe(3);          // it stopped AT the terminal state, not after it
  });

  it("returns 'error' when the server says error", async () => {
    expect(await makeWaitForPublish(reader(["running", "error"]), fast)("p1")).toBe("error");
  });

  it("reports every intermediate state to onTick, terminal one included", async () => {
    const seen: string[] = [];
    await makeWaitForPublish(reader(["queued", "running", "done"]), fast)("p1", (s) => seen.push(s));
    expect(seen).toEqual(["queued", "running", "done"]);
  });

  it("treats an unreachable API as 'error' rather than polling a dead transport", async () => {
    // Twelve minutes of retries against a client that cannot reach the server presents to the user
    // as a hang, which is the one outcome with no message attached to it.
    const api = { publishStatus: vi.fn(async () => { throw new Error("network"); }) };
    expect(await makeWaitForPublish(api, fast)("p1")).toBe("error");
    expect(api.publishStatus).toHaveBeenCalledTimes(1);   // fails fast, does not retry
  });

  it("returns 'running' — NOT 'error' — when it gives up waiting", async () => {
    // The distinction that matters. The job is server-side and outlives this page; reporting a
    // timeout as a failure would tell the user their edit was lost when it is on disk and converting.
    const r = reader(["running"]);
    expect(await makeWaitForPublish(r, { intervalMs: 0, timeoutMs: 5 })("p1")).toBe("running");
    expect(r.calls()).toBeGreaterThan(0);
  });

  it("keeps 'running' and 'error' distinguishable", async () => {
    const timedOut = await makeWaitForPublish(reader(["running"]), { intervalMs: 0, timeoutMs: 5 })("p1");
    const failed = await makeWaitForPublish(reader(["error"]), fast)("p1");
    expect(timedOut).not.toBe(failed);
  });

  it("polls under its own deadline, not the caller's patience", async () => {
    // A zero/negative deadline must not poll at all — the loop is `while (now < deadline)`, and a
    // do/while here would fire one request after the caller had already given up.
    const r = reader(["running"]);
    expect(await makeWaitForPublish(r, { intervalMs: 0, timeoutMs: -1 })("p1")).toBe("running");
    expect(r.calls()).toBe(0);
  });
});
