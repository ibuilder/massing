import { describe, expect, it, vi } from "vitest";

import { elapsedSince, makeWaitForPublish } from "./publishWait";

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

/**
 * `elapsedSince` subtracts a SERVER timestamp from a BROWSER clock, which is the only way to answer
 * "how long has this convert been running" for a page that reloaded mid-job — and is also the one
 * arithmetic in this file that can produce a confidently wrong answer. Every implausible result is
 * asserted to come back as null rather than as a formatted string.
 */
describe("elapsedSince", () => {
  const NOW = Date.parse("2026-09-11T12:00:00Z");

  it("formats seconds under a minute and minutes above it", () => {
    expect(elapsedSince("2026-09-11T11:59:17Z", NOW)).toBe("43s");
    expect(elapsedSince("2026-09-11T11:57:38Z", NOW)).toBe("2m 22s");
    expect(elapsedSince("2026-09-11T11:59:00Z", NOW)).toBe("1m 00s");   // seconds are zero-padded
  });

  it("parses the stamp the SERVER actually writes, offset and all", () => {
    // `_set_pub_status` writes `datetime.now(timezone.utc).isoformat()`, which is
    // `…+00:00` with microseconds — NOT a `Z` suffix, and not a naive datetime. The distinction is
    // the whole correctness of this function: `Date.parse` reads an offset-less datetime as LOCAL
    // time, so a naive server stamp would be wrong by the viewer's UTC offset — silently right in
    // London and hours out everywhere else, which is exactly the bug no developer reproduces.
    expect(elapsedSince("2026-09-11T11:57:38.123456+00:00", NOW)).toBe("2m 21s");
    expect(elapsedSince("2026-09-11T11:57:38Z", NOW)).toBe("2m 22s");          // Z form too
  });

  it("returns null when there is no stamp, or the stamp is not a date", () => {
    // `{state: "idle"}` carries no `at` at all — the common case, and it must not render "NaNs".
    expect(elapsedSince(undefined, NOW)).toBeNull();
    expect(elapsedSince("", NOW)).toBeNull();
    expect(elapsedSince("not a date", NOW)).toBeNull();
  });

  it("returns null for a FUTURE stamp rather than a negative duration", () => {
    // A browser clock behind the server's. Showing "-4m 00s" is worse than showing nothing, and
    // this is the branch a naive implementation gets wrong because it never fires in development.
    expect(elapsedSince("2026-09-11T12:04:00Z", NOW)).toBeNull();
  });

  it("returns null beyond a day — a stale blob is not a 400-hour convert", () => {
    expect(elapsedSince("2026-09-10T11:00:00Z", NOW)).toBeNull();       // 25h
    expect(elapsedSince("2026-09-10T12:00:01Z", NOW)).toBe("1439m 59s"); // 24h minus 1s: still shown
  });
});

describe("waitForPublish elapsed", () => {
  it("hands onTick the elapsed time beside the state", async () => {
    const at = new Date(Date.now() - 90_000).toISOString();
    const api = { publishStatus: vi.fn(async () => ({ state: "done", at })) };
    const seen: [string, string | null][] = [];
    await makeWaitForPublish(api, fast)("p1", (s, e) => seen.push([s, e]));
    expect(seen).toHaveLength(1);
    expect(seen[0]![0]).toBe("done");
    expect(seen[0]![1]).toMatch(/^1m \d\ds$/);
  });

  it("hands onTick null when the reply carries no timestamp", async () => {
    // Every pre-existing caller is `(s) => …` and ignores the second argument; this asserts the
    // no-stamp path produces a value those callers can also ignore rather than a thrown error.
    const seen: (string | null)[] = [];
    await makeWaitForPublish(reader(["done"]), fast)("p1", (_s, e) => seen.push(e));
    expect(seen).toEqual([null]);
  });
});
