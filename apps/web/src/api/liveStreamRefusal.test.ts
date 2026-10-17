import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HttpCore, type LiveStatus } from "./httpCore";

/**
 * FIELD-STREAM-POISON — the THIRD instance of a class two offline queues already closed, and the
 * only one that had no test at all.
 *
 * `EventSource.onerror` carries no status. A fatal close (the server answered with an HTTP error)
 * and a transient drop (the wifi went) arrive through the identical handler, so `liveStream` backed
 * off to its 60-second ceiling and retried **for ever** — including on a 403 for a project the
 * caller has been removed from and a 404 for one that was deleted. The one UI that reads this said
 * *"Live notifications disconnected — reconnecting…"* indefinitely, and the only cure was a reload.
 *
 * **The diagnosis was already in the file.** `HttpCore.setToken`'s docstring says *"without the
 * cookie every live stream … resolves anonymous under RBAC and dies in a reconnect loop."* Nothing
 * acted on it. *A symptom named in a docstring beside the code that produces it is not a fixed
 * defect, and it reads like one.*
 *
 * The asymmetry is the same one `permanentRejection` is built around and it runs the same way here:
 * calling a transient failure permanent leaves somebody watching a dead screen, while calling a
 * permanent one transient costs another request. So the probe fails OPEN — a probe that cannot
 * complete means retry — and every refusal is reversible through `retry()`.
 */

class Probe extends HttpCore {
  open(path: string, onMessage: (d: unknown) => void,
       onStatus?: (s: LiveStatus, why?: string) => void) {
    return this.liveStream(path, onMessage, onStatus);
  }
}

interface FakeES { onmessage: ((e: { data: string }) => void) | null;
                   onerror: (() => void) | null; readyState: number; closed: boolean;
                   close: () => void }

let sources: FakeES[] = [];
let opened: string[] = [];

beforeEach(() => {
  sources = [];
  opened = [];
  vi.useFakeTimers();
  class ES {
    static readonly CLOSED = 2;
    static readonly CONNECTING = 0;
    onmessage: ((e: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;
    readyState = 0;
    closed = false;
    constructor(url: string) { opened.push(url); sources.push(this as unknown as FakeES); }
    close() { this.closed = true; }
  }
  (globalThis as unknown as { EventSource: unknown }).EventSource = ES;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** A fatal close on the newest source, then let the classify promise settle. */
const fatal = async () => {
  const es = sources[sources.length - 1]!;
  es.readyState = 2;
  es.onerror?.();
  await vi.advanceTimersByTimeAsync(0);
};

let probeInit: RequestInit | undefined;
const probeStatus = (status: number) => vi.stubGlobal("fetch", vi.fn(async (_u, init) => {
  probeInit = init as RequestInit;
  return { ok: status < 400, status, body: { cancel: async () => {} } } as unknown as Response;
}));

describe("a fatal close is classified, not retried blindly", () => {
  it("THE DEFECT: a 403 used to back off for ever; it now REFUSES, with the reason", async () => {
    probeStatus(403);
    const seen: [LiveStatus, string | undefined][] = [];
    const s = new Probe().open("/p/1/stream", () => {}, (st, why) => seen.push([st, why]));
    await fatal();
    expect(seen).toEqual([["refused", "No longer permitted on this project"]]);
    // and it does NOT come back on the backoff timer — the whole point
    await vi.advanceTimersByTimeAsync(600_000);
    expect(opened).toHaveLength(1);
    expect(s.connected).toBe(false);
  });

  it("a 404 refuses too, naming the record rather than the permission", async () => {
    probeStatus(404);
    const seen: string[] = [];
    new Probe().open("/p/1/stream", () => {}, (_st, why) => { if (why) seen.push(why); });
    await fatal();
    expect(seen).toEqual(["The project or record no longer exists"]);
  });

  it("a 500 is TRANSIENT and still reconnects on the backoff", async () => {
    probeStatus(500);
    new Probe().open("/p/1/stream", () => {}, () => {});
    await fatal();
    expect(opened).toHaveLength(1);              // not yet — the backoff has to elapse
    await vi.advanceTimersByTimeAsync(5000);
    expect(opened).toHaveLength(2);
  });

  it("401 is transient, because signing in again fixes it", async () => {
    // The classifier's own first mistake, in the direction its asymmetry names as costly. Pinned
    // here as well as in the queues' tests: three callers now depend on this one answer.
    probeStatus(401);
    const seen: LiveStatus[] = [];
    new Probe().open("/p/1/stream", () => {}, (st) => seen.push(st));
    await fatal();
    expect(seen).not.toContain("refused");
    await vi.advanceTimersByTimeAsync(5000);
    expect(opened).toHaveLength(2);
  });

  it("A PROBE THAT CANNOT COMPLETE MEANS RETRY — it fails open", async () => {
    // Offline is the single most retryable failure there is, and it is exactly when the probe
    // cannot answer. Refusing here would strand the UI on the one failure that always recovers.
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const seen: LiveStatus[] = [];
    new Probe().open("/p/1/stream", () => {}, (st) => seen.push(st));
    await fatal();
    expect(seen).not.toContain("refused");
    await vi.advanceTimersByTimeAsync(5000);
    expect(opened).toHaveLength(2);
  });

  it("the backoff still doubles to its 60s ceiling across transient closes", async () => {
    probeStatus(503);
    new Probe().open("/p/1/stream", () => {}, () => {});
    for (const wait of [5000, 10_000, 20_000, 40_000, 60_000, 60_000]) {
      await fatal();
      await vi.advanceTimersByTimeAsync(wait - 1);
      const before = opened.length;
      await vi.advanceTimersByTimeAsync(1);
      expect(opened.length, `after ${wait}ms`).toBe(before + 1);
    }
  });

  it("the dead source is RELEASED before a new one opens", async () => {
    // A CLOSED EventSource still holds its slot in the browser's six-per-origin pool, and this
    // helper opens a fresh one on every reconnect. Four live streams reconnecting through a
    // deploy would exhaust it and the next one would simply never connect. Asserted rather than
    // trusted, because deleting the `close()` call changes nothing else observable.
    probeStatus(503);
    new Probe().open("/p/1/stream", () => {}, () => {});
    await fatal();
    expect(sources[0]!.closed).toBe(true);
    await vi.advanceTimersByTimeAsync(5000);
    expect(opened).toHaveLength(2);
    expect(sources[1]!.closed).toBe(false);
  });

  it("a CONNECTING error is the browser's own retry and is not classified", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    new Probe().open("/p/1/stream", () => {}, () => {});
    sources[0]!.readyState = 0;
    sources[0]!.onerror?.();
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("a refusal is REVERSIBLE", () => {
  it("retry() re-subscribes after a refusal, because the verdict can be wrong", async () => {
    probeStatus(403);
    const seen: LiveStatus[] = [];
    const s = new Probe().open("/p/1/stream", () => {}, (st) => seen.push(st));
    await fatal();
    expect(seen).toEqual(["refused"]);
    s.retry();
    expect(seen).toEqual(["refused", "reconnecting"]);
    expect(opened).toHaveLength(2);
  });

  it("retry() on a healthy stream is a no-op, and on a closed one stays closed", async () => {
    probeStatus(403);
    const live = new Probe().open("/p/1/stream", () => {}, () => {});
    live.retry();
    expect(opened).toHaveLength(1);
    await fatal();
    live.close();
    live.retry();
    expect(opened).toHaveLength(1);
  });

  it("a refusal landing while a retry is already scheduled still stops it", async () => {
    // Two fatal closes in flight: the first probe says 503 and schedules a reopen, the second says
    // 403. The timer is already booked by then, so the refusal has to be honoured where `open`
    // runs — not where the verdict arrives. This is what makes the `refused` guard inside `open`
    // load-bearing rather than defence nothing exercises.
    const verdicts = [503, 403];
    vi.stubGlobal("fetch", vi.fn(async () => {
      const status = verdicts.shift() ?? 403;
      return { ok: false, status, body: { cancel: async () => {} } } as unknown as Response;
    }));
    const seen: LiveStatus[] = [];
    new Probe().open("/p/1/stream", () => {}, (st) => seen.push(st));
    await fatal();                 // 503 -> a reopen is scheduled 5s out
    await fatal();                 // 403 -> refused, with that timer still pending
    expect(seen).toContain("refused");
    await vi.advanceTimersByTimeAsync(600_000);
    expect(opened).toHaveLength(1);
  });

  it("close() during a pending probe leaves no timer behind", async () => {
    // The classify step is async, so a close can land between the fatal error and the verdict. The
    // first draft scheduled the reopen from inside the promise without re-checking `closed`.
    let settle: (v: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise((r) => { settle = r; })));
    const live = new Probe().open("/p/1/stream", () => {}, () => {});
    sources[0]!.readyState = 2;
    sources[0]!.onerror?.();
    live.close();
    settle({ ok: false, status: 503, body: { cancel: async () => {} } });
    await vi.advanceTimersByTimeAsync(0);
    // No reopen, AND no orphan timer: scheduling one on a closed stream leaks a firing that does
    // nothing, and `open`'s own guard would hide it from the assertion below.
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(600_000);
    expect(opened).toHaveLength(1);
  });
});

describe("the healthy path is unchanged", () => {
  it("a message marks it connected and resets the backoff", async () => {
    probeStatus(503);
    const seen: LiveStatus[] = [];
    const got: unknown[] = [];
    new Probe().open("/p/1/stream", (d) => got.push(d), (st) => seen.push(st));
    sources[0]!.onmessage?.({ data: '{"count":3}' });
    expect(seen).toEqual(["connected"]);
    expect(got).toEqual([{ count: 3 }]);
    // a malformed frame is skipped and does NOT kill the stream
    sources[0]!.onmessage?.({ data: "not json" });
    expect(got).toHaveLength(1);
  });
});

describe("the probe must authenticate the way the STREAM does", () => {
  it("THE HIGH FINDING: cookie credentials, never an Authorization header", async () => {
    // `EventSource` cannot send an Authorization header and authenticates only with the
    // `aec_token` cookie — the asymmetry `HttpCore.setToken` documents and this method quotes. The
    // first draft of the probe sent `authHeaders()`, so with the cookie missing and the
    // localStorage token present the stream 403s as anonymous while the probe returns 200: the
    // verdict is "transient" and the loop runs for ever, which is the defect being removed.
    probeStatus(403);
    new Probe().open("/p/1/stream", () => {}, () => {});
    await fatal();
    expect(probeInit?.credentials).toBe("include");
    expect(probeInit?.headers).toBeUndefined();
    expect(probeInit?.signal).toBeDefined();
  });

  it("a probe that never settles still ends in a retry, not a limbo", async () => {
    // The reopen is scheduled only inside the probe's `.then`, so a hung probe would leave the
    // stream neither retrying nor refused — "reconnecting…" for ever with `retry()` a no-op, which
    // is worse than either verdict. A 10s abort bounds it and aborting reads as transient.
    vi.stubGlobal("fetch", vi.fn((_u, init: RequestInit) => new Promise((_res, rej) => {
      init.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")));
    })));
    new Probe().open("/p/1/stream", () => {}, () => {});
    sources[0]!.readyState = 2;
    sources[0]!.onerror?.();
    await vi.advanceTimersByTimeAsync(10_000);   // the abort fires
    await vi.advanceTimersByTimeAsync(5000);     // ...then the backoff
    expect(opened).toHaveLength(2);
  });
});

describe("a refusal nobody can see is worse than a retry loop", () => {
  it("a caller with no onStatus keeps RETRYING a permanent refusal", async () => {
    // Three callers hold their handle privately and pass no `onStatus`. Refusing would stop them
    // permanently and SILENTLY, where the old loop at least kept trying — and a stop with nobody
    // to tell has no advocate. Measured rather than assumed: this is the one place the
    // classification is deliberately not acted on.
    probeStatus(403);
    const s = new Probe().open("/p/1/stream", () => {});
    await fatal();
    await vi.advanceTimersByTimeAsync(5000);
    expect(opened).toHaveLength(2);
    expect(s.connected).toBe(false);
  });
});

describe("retry() clears the backoff it is replacing", () => {
  it("THE LEAK: a pending reopen plus a retry used to open TWO sources", async () => {
    const verdicts = [503, 403];
    vi.stubGlobal("fetch", vi.fn(async () => {
      const status = verdicts.shift() ?? 403;
      return { ok: false, status, body: { cancel: async () => {} } } as unknown as Response;
    }));
    const live = new Probe().open("/p/1/stream", () => {}, () => {});
    await fatal();                 // 503 -> reopen booked 5s out
    await fatal();                 // 403 -> refused, timer still pending
    live.retry();
    expect(opened).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(600_000);
    expect(opened, "the stale backoff must not open a third").toHaveLength(2);
  });
});
