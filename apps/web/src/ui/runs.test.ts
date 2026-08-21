import { describe, expect, it } from "vitest";
import {
  ABSENT, diffRunResults, formatDelta, isComparable, resultMetrics, runHistory, runTime,
} from "./runs";
import { renderRun, renderRunsInbox, shortTime } from "./runsInbox";
import type { Job } from "../api/types";

const job = (p: Partial<Job> & { id: string }): Job => ({
  kind: "clash_detect", project_id: "p1", state: "done", params: null, result: null, error: null,
  actor: "sam", created_at: "2026-08-14T01:00:00Z", started_at: null, finished_at: "2026-08-14T01:01:00Z",
  ...p,
});

describe("resultMetrics — numeric leaves of a run result", () => {
  it("flattens nested numbers to dotted keys", () => {
    expect(resultMetrics({ count: 412, by: { hard: 300, soft: 112 } })).toEqual([
      { key: "count", value: 412 },
      { key: "by.hard", value: 300 },
      { key: "by.soft", value: 112 },
    ]);
  });

  it("takes an array's LENGTH, not its items", () => {
    // Pairing item 7 of one run against item 7 of another compares two unrelated things that happen
    // to share an index. "412 findings became 389" is the comparison that means something.
    expect(resultMetrics({ findings: [1, 2, 3] })).toEqual([{ key: "findings.length", value: 3 }]);
  });

  it("reads a boolean as a flag that can flip", () => {
    expect(resultMetrics({ passed: true, sealed: false })).toEqual([
      { key: "passed", value: 1 }, { key: "sealed", value: 0 },
    ]);
  });

  it("drops NaN and Infinity rather than carrying them into a delta", () => {
    // They come from an unguarded division. A delta computed from one is noise dressed as a number.
    expect(resultMetrics({ ok: 5, bad: NaN, worse: Infinity })).toEqual([{ key: "ok", value: 5 }]);
  });

  it("ignores strings, nulls and undefined", () => {
    expect(resultMetrics({ name: "x", none: null, n: 1 })).toEqual([{ key: "n", value: 1 }]);
  });

  it("stops at a depth cap — a cyclic result must not take the stack", () => {
    const cyclic: Record<string, unknown> = { n: 1 };
    cyclic.self = cyclic;
    expect(() => resultMetrics(cyclic)).not.toThrow();
    expect(resultMetrics(cyclic).some((m) => m.key === "n")).toBe(true);
  });

  it("handles a non-object result without inventing metrics", () => {
    expect(resultMetrics(null)).toEqual([]);
    expect(resultMetrics(42)).toEqual([]);
    expect(resultMetrics("done")).toEqual([]);
  });
});

describe("diffRunResults — a missing metric is NOT zero", () => {
  it("computes signed deltas for shared metrics", () => {
    const d = diffRunResults({ count: 412 }, { count: 389 });
    expect(d).toEqual([{ key: "count", prev: 412, next: 389, delta: -23 }]);
  });

  /**
   * The decision this module exists to get right. Treating absence as zero turns a detector that
   * stopped reporting `count` into a confident, precise, entirely invented −412 — worse than no
   * number, because it reads as a finding.
   */
  it("reports an appeared metric as prev=null, delta=null — never as a rise from zero", () => {
    const d = diffRunResults({}, { count: 412 });
    expect(d).toEqual([{ key: "count", prev: null, next: 412, delta: null }]);
    expect(d[0]!.delta).not.toBe(412);
  });

  it("reports a disappeared metric as next=null, delta=null — never as a fall to zero", () => {
    const d = diffRunResults({ count: 412 }, {});
    expect(d).toEqual([{ key: "count", prev: 412, next: null, delta: null }]);
    expect(d[0]!.delta).not.toBe(-412);
  });

  it("sorts by absolute movement, largest first", () => {
    const d = diffRunResults({ a: 0, b: 0, c: 0 }, { a: 1, b: 50, c: -9 });
    expect(d.map((x) => x.key)).toEqual(["b", "c", "a"]);
  });

  it("...and sorts UNKNOWN movement after every real delta", () => {
    // An unknown is not a large movement. Putting it at the top of a list ordered by magnitude is a
    // claim the data does not support.
    const d = diffRunResults({ small: 0 }, { small: 1, appeared: 9999 });
    expect(d.map((x) => x.key)).toEqual(["small", "appeared"]);
  });

  it("a zero delta is a real answer, distinct from an absent one", () => {
    const d = diffRunResults({ count: 5 }, { count: 5 });
    expect(d[0]!.delta).toBe(0);
    expect(d[0]!.delta).not.toBeNull();
  });
});

describe("runHistory", () => {
  it("groups by kind, newest first", () => {
    const h = runHistory([
      job({ id: "a", kind: "clash_detect", finished_at: "2026-08-14T01:00:00Z" }),
      job({ id: "b", kind: "clash_detect", finished_at: "2026-08-14T03:00:00Z" }),
      job({ id: "c", kind: "cobie_export", finished_at: "2026-08-14T02:00:00Z" }),
    ]);
    expect([...h.keys()].sort()).toEqual(["clash_detect", "cobie_export"]);
    expect(h.get("clash_detect")!.map((r) => r.job.id)).toEqual(["b", "a"]);
  });

  it("pairs each run with the previous one and diffs them", () => {
    const h = runHistory([
      job({ id: "old", result: { count: 412 }, finished_at: "2026-08-14T01:00:00Z" }),
      job({ id: "new", result: { count: 389 }, finished_at: "2026-08-14T03:00:00Z" }),
    ]);
    const runs = h.get("clash_detect")!;
    expect(runs[0]!.previous?.id).toBe("old");
    expect(runs[0]!.deltas).toEqual([{ key: "count", prev: 412, next: 389, delta: -23 }]);
    expect(runs[1]!.previous).toBeNull();          // the oldest has nothing before it
    expect(runs[1]!.deltas).toEqual([]);
  });

  /**
   * A failed run has no result. Using it as a baseline would report every metric as having vanished —
   * a screen full of `—` that looks like the analysis broke, when only one attempt did.
   */
  it("SKIPS a failed run as a baseline, while still listing it", () => {
    const h = runHistory([
      job({ id: "ok1", result: { count: 100 }, finished_at: "2026-08-14T01:00:00Z" }),
      job({ id: "bad", state: "error", result: null, error: "boom", finished_at: "2026-08-14T02:00:00Z" }),
      job({ id: "ok2", result: { count: 90 }, finished_at: "2026-08-14T03:00:00Z" }),
    ]);
    const runs = h.get("clash_detect")!;
    expect(runs.map((r) => r.job.id)).toEqual(["ok2", "bad", "ok1"]);   // the failure is still listed
    expect(runs[0]!.previous?.id).toBe("ok1");                          // ...but never the baseline
    expect(runs[0]!.deltas).toEqual([{ key: "count", prev: 100, next: 90, delta: -10 }]);
  });

  it("a still-running job is neither a baseline nor compared", () => {
    const h = runHistory([
      job({ id: "done1", result: { count: 5 }, finished_at: "2026-08-14T01:00:00Z" }),
      job({ id: "run1", state: "running", result: null, finished_at: null,
            created_at: "2026-08-14T04:00:00Z" }),
    ]);
    const runs = h.get("clash_detect")!;
    expect(runs[0]!.job.id).toBe("run1");
    expect(runs[0]!.previous).toBeNull();
    expect(isComparable(runs[0]!.job)).toBe(false);
  });

  it("orders by finished time, falling back to created", () => {
    expect(runTime(job({ id: "x", finished_at: null, started_at: null, created_at: "C" }))).toBe("C");
    expect(runTime(job({ id: "y", finished_at: "F", created_at: "C" }))).toBe("F");
  });

  it("an empty job list yields an empty history, not a throw", () => {
    expect(runHistory([]).size).toBe(0);
  });
});

describe("formatDelta", () => {
  it("always carries a sign, so a rise is never read as a fall", () => {
    expect(formatDelta(23)).toBe("+23");
    expect(formatDelta(-23)).toBe("−23");
    expect(formatDelta(0)).toBe("0");
    expect(formatDelta(-1.5)).toBe("−1.50");
  });
});

describe("renderRunsInbox", () => {
  const label = (k: string) => k;

  it("renders a section per kind with a run box each", () => {
    const host = document.createElement("div");
    renderRunsInbox(host, [
      job({ id: "a", result: { count: 10 }, finished_at: "2026-08-14T01:00:00Z" }),
      job({ id: "b", result: { count: 7 }, finished_at: "2026-08-14T03:00:00Z" }),
    ], label);
    expect(host.querySelectorAll("[data-kind]")).toHaveLength(1);
    expect(host.querySelectorAll("[data-job]")).toHaveLength(2);
    expect(host.querySelector('[data-job="b"]')!.textContent).toContain("−3");
  });

  it("says which half of the feature is missing when there are no runs", () => {
    // Not "no data" / not "the queue is unused" — an empty inbox is a project that has not run
    // clash, IDS, cost or energy yet, and the copy names those so the reader knows where to start.
    const host = document.createElement("div");
    renderRunsInbox(host, [], label);
    expect(host.querySelector("[data-empty]")?.getAttribute("data-empty")).toBe("none");
    expect(host.textContent).toContain("clash");
  });

  it("a first run says so instead of showing a diff against nothing", () => {
    const box = renderRun({ job: job({ id: "solo", result: { count: 1 } }), previous: null, deltas: [] });
    expect(box.textContent).toContain("First run");
  });

  it("a failed run shows its error and no metrics", () => {
    const box = renderRun({
      job: job({ id: "bad", state: "error", result: null, error: "handler exploded" }),
      previous: null, deltas: [],
    });
    expect(box.dataset.state).toBe("error");
    expect(box.textContent).toContain("handler exploded");
    expect(box.querySelectorAll("[data-metric]")).toHaveLength(0);
  });

  it("an unchanged run says so rather than listing zeroes", () => {
    const box = renderRun({
      job: job({ id: "same", result: { count: 5 } }),
      previous: job({ id: "prev", result: { count: 5 } }),
      deltas: diffRunResults({ count: 5 }, { count: 5 }),
    });
    expect(box.textContent).toContain("No change");
    expect(box.querySelectorAll("[data-metric]")).toHaveLength(0);
  });

  it("an absent metric renders as the absent mark, never as a number", () => {
    const box = renderRun({
      job: job({ id: "j", result: { fresh: 9 } }),
      previous: job({ id: "p", result: {} }),
      deltas: diffRunResults({}, { fresh: 9 }),
    });
    const row = box.querySelector('[data-metric="fresh"]')!;
    expect(row.textContent).toContain(ABSENT);
    expect(row.textContent).not.toContain("+9");
  });

  it("escapes hostile job text — kind, actor and error are all foreign", () => {
    const host = document.createElement("div");
    const nasty = "<img src=x onerror=alert(1)>";
    renderRunsInbox(host, [job({ id: "x", kind: nasty, actor: nasty, state: "error", error: nasty })],
                    (k) => k);
    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toContain(nasty);
  });

  it("shows an unparseable timestamp verbatim rather than 'Invalid Date'", () => {
    expect(shortTime("not-a-date")).toBe("not-a-date");
    expect(shortTime(null)).toBe(ABSENT);
  });
});
