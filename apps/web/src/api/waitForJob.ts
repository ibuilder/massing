/**
 * Poll a queued job until it is terminal.
 *
 * Same shape as `viewer/publishWait.ts` (interval, deadline, transport-fail ≠ timeout) because the
 * defect class is the same: collapsing "the server failed", "we stopped watching", and "it finished"
 * into one boolean. Callers of clash / IDS / cost used to `await api.clashFederated(...)` on the
 * request thread; now they enqueue and wait here, so the Runs inbox gets a row and the UI can still
 * show the result when the worker finishes.
 *
 * `"running"` on timeout is NOT an error — the job is durable and outlives this page. The caller
 * must not toast that as a failure. `"error"` is the job's own `error` string, or a transport miss.
 */
import type { Job, JobState } from "./types";

export type JobReader = {
  job: (pid: string, jobId: string) => Promise<Job>;
};

export type WaitJobOptions = {
  intervalMs?: number;
  timeoutMs?: number;
};

const TERMINAL: ReadonlySet<JobState> = new Set(["done", "error"]);

export function makeWaitForJob(api: JobReader, opts: WaitJobOptions = {}) {
  const intervalMs = opts.intervalMs ?? 1500;
  const timeoutMs = opts.timeoutMs ?? 12 * 60 * 1000;

  return async function waitForJob(
    pid: string, jobId: string, onTick?: (s: JobState) => void,
  ): Promise<Job> {
    const deadline = Date.now() + timeoutMs;
    let last: Job | null = null;
    while (Date.now() < deadline) {
      try { last = await api.job(pid, jobId); } catch {
        throw new Error("could not reach the job queue");
      }
      onTick?.(last.state);
      if (TERMINAL.has(last.state)) return last;
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    // Still moving. The row exists; the worker may finish after we walk away.
    if (last) return last;
    throw new Error("job did not start");
  };
}

export type EnqueueClient = JobReader & {
  enqueueJob: (pid: string, kind: string, params?: Record<string, unknown>) => Promise<Job>;
};

/**
 * Enqueue, wait for `done`, return `result`. Throws on a failed job (named), a transport miss, or
 * a timeout that left the job still moving — timeout is reported as still-running so a caller can
 * send the user to the job tray rather than invent a failure.
 */
export async function enqueueAndWait(
  api: EnqueueClient, pid: string, kind: string,
  params: Record<string, unknown> = {},
  onTick?: (s: JobState) => void,
  waitOpts?: WaitJobOptions,
): Promise<Record<string, unknown>> {
  const queued = await api.enqueueJob(pid, kind, params);
  onTick?.(queued.state);
  const done = await makeWaitForJob(api, waitOpts)(pid, queued.id, onTick);
  if (done.state === "error") throw new Error(done.error || `${kind} failed`);
  if (done.state !== "done") {
    throw new Error(`${kind} is still running — watch the job tray`);
  }
  return (done.result ?? {}) as Record<string, unknown>;
}
