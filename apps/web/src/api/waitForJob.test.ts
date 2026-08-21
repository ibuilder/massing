import { describe, expect, it, vi } from "vitest";

import type { Job, JobState } from "./types";
import { enqueueAndWait, JobStillRunning, makeWaitForJob } from "./waitForJob";

function job(partial: Partial<Job> & { state: JobState }): Job {
  return {
    id: "j1", kind: "clash_federated", project_id: "p1", params: null, result: null,
    error: null, actor: null, created_at: null, started_at: null, finished_at: null, ...partial,
  };
}

function reader(states: Job[]) {
  let i = 0;
  return {
    calls: () => i,
    job: vi.fn(async () => states[Math.min(i++, states.length - 1)]!),
  };
}

const fast = { intervalMs: 0, timeoutMs: 2_000 };

describe("waitForJob", () => {
  it("returns the terminal row and stops polling there", async () => {
    const done = job({ state: "done", result: { count: 3 } });
    const r = reader([job({ state: "queued" }), job({ state: "running" }), done]);
    const got = await makeWaitForJob(r, fast)("p1", "j1");
    expect(got.result).toEqual({ count: 3 });
    expect(r.calls()).toBe(3);
  });

  it("returns an error row rather than throwing — the caller names it", async () => {
    const got = await makeWaitForJob(
      reader([job({ state: "error", error: "need >=2 models" })]), fast,
    )("p1", "j1");
    expect(got.state).toBe("error");
    expect(got.error).toBe("need >=2 models");
  });

  it("treats an unreachable API as a thrown error, failing fast", async () => {
    const api = { job: vi.fn(async () => { throw new Error("network"); }) };
    await expect(makeWaitForJob(api, fast)("p1", "j1")).rejects.toThrow(/could not reach/);
    expect(api.job).toHaveBeenCalledTimes(1);
  });

  it("returns the last running row on timeout, not an invented failure", async () => {
    const r = reader([job({ state: "running" })]);
    const got = await makeWaitForJob(r, { intervalMs: 0, timeoutMs: 5 })("p1", "j1");
    expect(got.state).toBe("running");
  });
});

describe("enqueueAndWait", () => {
  it("returns the result of a done job", async () => {
    const api = {
      enqueueJob: vi.fn(async () => job({ state: "queued" })),
      job: vi.fn(async () => job({ state: "done", result: { count: 12 } })),
    };
    await expect(enqueueAndWait(api, "p1", "clash_federated", { coordinate: true }, undefined, fast))
      .resolves.toEqual({ count: 12 });
  });

  it("throws the job's own error sentence, not a generic failure", async () => {
    const api = {
      enqueueJob: vi.fn(async () => job({ state: "queued" })),
      job: vi.fn(async () => job({ state: "error", error: "need >=2 accessible discipline models" })),
    };
    await expect(enqueueAndWait(api, "p1", "clash_federated", {}, undefined, fast))
      .rejects.toThrow(/need >=2 accessible/);
  });

  it("does not invent a failure when the wait timed out while still running", async () => {
    const api = {
      enqueueJob: vi.fn(async () => job({ state: "queued" })),
      job: vi.fn(async () => job({ state: "running" })),
    };
    await expect(enqueueAndWait(api, "p1", "ids_validate", {}, undefined, { intervalMs: 0, timeoutMs: 5 }))
      .rejects.toBeInstanceOf(JobStillRunning);
  });
});
