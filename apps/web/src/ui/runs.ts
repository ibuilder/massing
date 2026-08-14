/**
 * R24-RUNS-INBOX phase 1 — an analysis is a **run**, and a run is worth comparing to the last one.
 *
 * The audit's finding 05: *"analyses are modals, so they have no history"*. The roadmap called this
 * "the most externally validated item in the ring", and it recorded the state as *"no runs concept in
 * the web app"*. **That premise was half wrong, and the wrong half is the expensive one to assume.**
 * `models.py:Job` already stores everything a run needs — `params` (the inputs), `actor` (who),
 * `created_at`/`finished_at` (when), `result` (the artifact) — and `routers/jobs.py` has served them
 * for a long time. There was never a missing table.
 *
 * What is missing splits cleanly in two, and only one half is shipped here:
 *
 * * **This half — history and comparison.** Runs that already go through the queue can be listed per
 *   project, grouped by kind, each compared against the one before it. That is pure computation over
 *   data the server already returns, so it is here, tested, with no endpoint and no migration.
 * * **The other half — routing the analyses through the queue.** Clash, IDS, cost and energy still
 *   run in the request thread behind a modal, so they never become rows here. That is a change to
 *   four call sites and their handlers, it is the larger and riskier half, and it stays open. Saying
 *   so is the point: this module works today for the seven registered kinds and is *empty* for the
 *   four analyses the audit actually named.
 *
 * ## The decision that matters: a missing metric is not zero
 *
 * When a key exists in one run and not the other, its delta is `null`, never the full value. Treating
 * absence as zero manufactures a −412 out of a clash detector that simply stopped reporting `count` —
 * a confident, precise, entirely invented number, which is worse than no number because it reads as a
 * finding. The same reasoning refuses to compare against a **failed** run: a run with no result is not
 * a run whose metrics all went to zero.
 */
import type { Job } from "../api/types";

/** One numeric leaf of a run's result, with its dotted path. */
export interface Metric {
  key: string;
  value: number;
}

/**
 * A metric's movement between two runs. `null` on either side means **absent**, not zero — and when
 * either side is absent, `delta` is `null` too.
 */
export interface MetricDelta {
  key: string;
  prev: number | null;
  next: number | null;
  delta: number | null;
}

/** A run and what changed since the last comparable one. */
export interface Run {
  job: Job;
  /** The previous *successful* run of the same kind, or `null` if this is the first. */
  previous: Job | null;
  deltas: MetricDelta[];
}

/**
 * How deep to walk a result, and how many metrics to keep.
 *
 * Both are guards, not preferences. A result is server JSON and a handler is free to nest; without a
 * depth cap a cyclic or pathologically deep structure recurses until the stack goes, and without a
 * count cap one run of a per-element report produces ten thousand rows nobody reads.
 */
const MAX_DEPTH = 4;
const MAX_METRICS = 200;

/**
 * Numeric leaves of a run result, as dotted paths.
 *
 * An array contributes its **length** (`findings.length`), not its items: the useful comparison
 * between two clash runs is "412 findings became 389", and pairing item 7 of one run against item 7
 * of another compares two unrelated things that merely share an index.
 *
 * `NaN` and `Infinity` are dropped rather than carried. They arrive from a division a handler did not
 * guard, and a delta computed from one is noise dressed as a measurement.
 */
export function resultMetrics(result: unknown, prefix = "", depth = 0): Metric[] {
  const out: Metric[] = [];
  if (depth > MAX_DEPTH || result == null) return out;
  if (Array.isArray(result)) {
    out.push({ key: prefix ? `${prefix}.length` : "length", value: result.length });
    return out;
  }
  if (typeof result !== "object") return out;
  for (const [k, v] of Object.entries(result as Record<string, unknown>)) {
    if (out.length >= MAX_METRICS) break;
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "number") {
      if (Number.isFinite(v)) out.push({ key, value: v });
    } else if (typeof v === "boolean") {
      out.push({ key, value: v ? 1 : 0 });     // a flag that flipped is a real, readable change
    } else {
      out.push(...resultMetrics(v, key, depth + 1));
    }
  }
  return out.slice(0, MAX_METRICS);
}

/**
 * Compare two run results.
 *
 * Sorted by absolute movement, largest first, so the biggest change reads at the top. Metrics that
 * appeared or disappeared sort **after** every real delta: their movement is unknown, not large, and
 * putting an unknown at the top of a list ordered by magnitude is a claim the data does not support.
 */
export function diffRunResults(prev: unknown, next: unknown): MetricDelta[] {
  const p = new Map(resultMetrics(prev).map((m) => [m.key, m.value]));
  const n = new Map(resultMetrics(next).map((m) => [m.key, m.value]));
  const keys = [...new Set([...p.keys(), ...n.keys()])];
  const out: MetricDelta[] = keys.map((key) => {
    const a = p.has(key) ? p.get(key)! : null;
    const b = n.has(key) ? n.get(key)! : null;
    return { key, prev: a, next: b, delta: a !== null && b !== null ? b - a : null };
  });
  return out.sort((x, y) => {
    if ((x.delta === null) !== (y.delta === null)) return x.delta === null ? 1 : -1;
    if (x.delta !== null && y.delta !== null && Math.abs(y.delta) !== Math.abs(x.delta)) {
      return Math.abs(y.delta) - Math.abs(x.delta);
    }
    return x.key.localeCompare(y.key);
  });
}

/** When a run happened, for ordering. Finished time if it has one, else when it was asked for. */
export function runTime(j: Job): string {
  return j.finished_at ?? j.started_at ?? j.created_at ?? "";
}

/** A run worth comparing against: it completed and it produced something. */
export function isComparable(j: Job): boolean {
  return j.state === "done" && j.result != null;
}

/**
 * Group jobs into per-kind run histories, newest first, each paired with its predecessor.
 *
 * The predecessor is the previous **comparable** run, not simply the previous row. A failed run in
 * between is still listed — a failure is part of the history and hiding it is how a queue looks
 * healthier than it is — but it is never used as a baseline, because a run with no result is not a
 * run whose every metric fell to zero.
 */
export function runHistory(jobs: readonly Job[]): Map<string, Run[]> {
  const byKind = new Map<string, Job[]>();
  for (const j of jobs) {
    const list = byKind.get(j.kind) ?? [];
    list.push(j);
    byKind.set(j.kind, list);
  }
  const out = new Map<string, Run[]>();
  for (const [kind, list] of byKind) {
    const newestFirst = [...list].sort((a, b) => runTime(b).localeCompare(runTime(a)));
    const runs: Run[] = newestFirst.map((job, i) => {
      const previous = isComparable(job)
        ? newestFirst.slice(i + 1).find(isComparable) ?? null
        : null;
      return {
        job,
        previous,
        deltas: previous ? diffRunResults(previous.result, job.result) : [],
      };
    });
    out.set(kind, runs);
  }
  return out;
}

/** `-23`, `+4`, `0` — the sign is the whole point, so a rise is never mistaken for a fall. */
export function formatDelta(d: number): string {
  if (d === 0) return "0";
  const n = Number.isInteger(d) ? String(Math.abs(d)) : Math.abs(d).toFixed(2);
  return (d > 0 ? "+" : "−") + n;
}

/** How a metric reads when one side is missing — never a number, because there is not one. */
export const ABSENT = "—";
