/**
 * Wait for a publish to reach a terminal state.
 *
 * This was a nine-line loop inside `app.ts` with **24 call sites** and no test — one of the most
 * reused pieces of behaviour in the viewer, and one of the least examined. It decides three things
 * that are easy to get wrong and impossible to see from a call site: what a transport error means,
 * what a timeout returns, and how often it asks.
 *
 * Extracted rather than left in place because the per-file size ratchet asked the question it is
 * there to ask — should this live in a domain module? — and for a polling loop over a job state the
 * answer is plainly yes. The interval and deadline become parameters purely so a test can run it in
 * milliseconds; the defaults are the shipped ones.
 */

export type PublishStatusReader = {
  publishStatus: (pid: string) => Promise<{ state: string; at?: string }>;
};

/**
 * How long the server has been in this state, from the `at` stamp it writes beside it.
 *
 * Measured against the SERVER's stamp rather than against when this loop started, because the case
 * that needs it most is the one where the loop did not see the beginning: a reload mid-convert
 * leaves a fresh poller watching a job that is already minutes old, and elapsed-since-we-started
 * would confidently report 3 s.
 *
 * That means subtracting a server clock from a browser clock, so the answer is only trusted when it
 * is plausible: a negative figure (browser behind the server) or one beyond a day (a bad stamp, a
 * misconfigured timezone) returns null and the caller simply says nothing. **Showing no elapsed
 * time is honest; showing "-4m" is worse than the silence it replaced.**
 */
export function elapsedSince(at: string | undefined, now: number): string | null {
  if (!at) return null;
  const t = Date.parse(at);
  if (!Number.isFinite(t)) return null;
  const ms = now - t;
  if (ms < 0 || ms > 24 * 60 * 60 * 1000) return null;
  const s = Math.floor(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export type WaitOptions = {
  /** Gap between polls. 1.5 s in the app — fast enough to feel live, slow enough not to hammer. */
  intervalMs?: number;
  /**
   * Give-up point. 12 minutes because a large-model convert legitimately takes minutes, and a
   * caller that stopped watching is not the same as a publish that failed — hence "running" below.
   */
  timeoutMs?: number;
};

/**
 * Bind the poller to a client.
 *
 * The three returns are deliberately distinct and callers branch on all three:
 *
 * - `"done"` / `"error"` — the server said so. Terminal.
 * - `"error"` — ALSO what a failed status request returns. A client that cannot reach the API cannot
 *   tell a running job from a dead one, and continuing to poll a broken transport for twelve
 *   minutes would present as a hang. Failing fast is the honest reading, and the caller shows the
 *   same message either way.
 * - `"running"` — we stopped watching; the publish may well still finish. NOT an error, and callers
 *   must not report it as one: the edit is on disk and the convert is a server-side job that
 *   outlives this page.
 */
export function makeWaitForPublish(api: PublishStatusReader, opts: WaitOptions = {}) {
  const intervalMs = opts.intervalMs ?? 1500;
  const timeoutMs = opts.timeoutMs ?? 12 * 60 * 1000;

  return async function waitForPublish(
    pid: string, onTick?: (s: string, elapsed: string | null) => void): Promise<string> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      let s: { state: string; at?: string };
      try { s = await api.publishStatus(pid); } catch { return "error"; }
      // Second argument, not a changed first one: every existing `(s) => …` caller keeps working
      // untouched, and the ones that want to show progress opt in. A convert legitimately runs for
      // minutes, so "running" on its own is indistinguishable from a stuck job.
      onTick?.(s.state, elapsedSince(s.at, Date.now()));
      if (s.state === "done" || s.state === "error") return s.state;
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    return "running";
  };
}
