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
  publishStatus: (pid: string) => Promise<{ state: string }>;
};

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

  return async function waitForPublish(pid: string, onTick?: (s: string) => void): Promise<string> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      let s: { state: string };
      try { s = await api.publishStatus(pid); } catch { return "error"; }
      onTick?.(s.state);
      if (s.state === "done" || s.state === "error") return s.state;
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    return "running";
  };
}
