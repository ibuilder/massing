import { beforeEach, describe, expect, it } from "vitest";

import { identityScope } from "../api/identity";
import { HttpError } from "../api/httpCore";
import { FieldCapture, type QueuedCapture, loadAll, loadQueue, saveQueue } from "./field";

const signInAs = (t: string) => localStorage.setItem("aec-token", t);
const capture = (id: string, owner?: string): QueuedCapture =>
  ({ id, pid: "p1", module: "punchlist", data: {}, ...(owner ? { owner } : {}) });

beforeEach(() => localStorage.clear());

describe("field captures on a shared tablet", () => {
  it("a session sees its own captures and not the previous person's", () => {
    localStorage.setItem("aec-field-queue", JSON.stringify([
      capture("a1", identityScope("token-A")),
      capture("b1", identityScope("token-B")),
    ]));
    signInAs("token-A");
    expect(loadQueue().map((c) => c.id)).toEqual(["a1"]);
    signInAs("token-B");
    expect(loadQueue().map((c) => c.id)).toEqual(["b1"]);
  });

  it("SAVING MY QUEUE DOES NOT DELETE THEIRS", () => {
    // The single most important assertion here. `loadQueue` returns a FILTERED view, so writing it
    // straight back would erase every other person's unsent captures — photos taken on a jobsite
    // that exist nowhere else yet. Deleting someone's work would be a far worse bug than the
    // visibility one this scoping closes.
    localStorage.setItem("aec-field-queue", JSON.stringify([
      capture("a1", identityScope("token-A")),
      capture("b1", identityScope("token-B")),
    ]));
    signInAs("token-A");
    saveQueue(loadQueue().filter((c) => c.id !== "a1"));      // A clears their own queue

    const left = loadAll().map((c) => c.id);
    expect(left).toContain("b1");                              // B's capture survived
    expect(left).not.toContain("a1");
    signInAs("token-B");
    expect(loadQueue().map((c) => c.id)).toEqual(["b1"]);      // and B still sees it
  });

  it("untagged legacy captures stay visible to whoever is signed in", () => {
    // They predate scoping; hiding them would strand unsent work with no way to recover it.
    localStorage.setItem("aec-field-queue", JSON.stringify([capture("legacy")]));
    signInAs("token-A");
    expect(loadQueue().map((c) => c.id)).toEqual(["legacy"]);
    signInAs("token-B");
    expect(loadQueue().map((c) => c.id)).toEqual(["legacy"]);
  });

  it("a legacy capture is not silently re-stamped with the current session", () => {
    localStorage.setItem("aec-field-queue", JSON.stringify([capture("legacy")]));
    signInAs("token-A");
    saveQueue(loadQueue());
    expect(loadAll()[0]?.owner).toBeUndefined();
  });

  it("corrupt storage reads as empty rather than throwing", () => {
    localStorage.setItem("aec-field-queue", "{not json");
    expect(loadQueue()).toEqual([]);
  });
});

describe("FIELD-POISON — a capture the server will never accept", () => {
  // The queue used to re-push EVERY failure, so a 400 was retried on every reconnect: the badge
  // never cleared, the review sheet showed it as merely "pending", and the worker's only recourse
  // was a bare ✕ with nothing saying why. Worse, a poisoned item sat in front of the good ones.
  //
  // The asymmetry that decides the design: calling a transient failure permanent LOSES a field
  // worker's capture; calling a permanent one transient costs one more request. So only a 4xx that
  // cannot change on repeat is treated as final — and even then the item is KEPT, marked with a
  // reason, never silently discarded.
  const mkApi = (fail: (item: QueuedCapture) => Error | null) => {
    const created: string[] = [];
    return {
      created,
      createModuleRecord: async (pid: string, module: string, body: { data: Record<string, unknown> }) => {
        const err = fail({ id: String(body.data.subject), pid, module, data: body.data });
        if (err) throw err;
        created.push(String(body.data.subject));
        return { id: `rec-${body.data.subject}` };
      },
      uploadAttachment: async () => ({}),
    };
  };

  const queue = (...subjects: string[]) =>
    subjects.map((s) => ({ id: s, pid: "p1", module: "punchlist", data: { subject: s } }));

  /** `flush()` is only reachable after `mount()` in the app — the badge hangs off the FAB that
   *  mount creates — so the tests drive that lifecycle rather than reaching past it. Mounting on an
   *  empty queue is a no-op flush, so the fixture is queued afterwards. */
  const mounted = (api: unknown) => {
    document.body.innerHTML = "";
    const fc = new FieldCapture(api as never, () => "p1");
    fc.mount();
    return fc;
  };

  it("a 400 does not hold the good captures behind it", async () => {
    const api = mkApi((it) => (it.id === "poison" ? new HttpError("POST -> 400", 400) : null));
    const fc = mounted(api);
    saveQueue(queue("poison", "good") as QueuedCapture[]);
    await fc.flush();

    expect(api.created).toEqual(["good"]);                       // the good one went through
    const left = loadQueue();
    expect(left.map((x) => x.id)).toEqual(["poison"]);           // only the refused one remains
    expect(left[0]?.rejected).toBeTruthy();                      // ...and it says why
  });

  it("a refused capture is not retried again, but is never discarded either", async () => {
    const api = mkApi(() => new HttpError("POST -> 400", 400));
    const fc = mounted(api);
    saveQueue(queue("poison") as QueuedCapture[]);
    await fc.flush();
    const afterFirst = loadQueue();

    // second flush: the server is not asked again, and the capture is still there for the worker
    const api2 = mkApi(() => { throw new Error("must not be called for an already-refused item"); });
    await mounted(api2).flush();
    expect(api2.created).toEqual([]);
    expect(loadQueue()).toEqual(afterFirst);
  });

  it("a 5xx or a network drop stays a plain retry — losing a capture is the worse error", async () => {
    let attempts = 0;
    const api = mkApi(() => { attempts++; return attempts === 1 ? new HttpError("POST -> 503", 503) : null; });
    const fc = mounted(api);
    saveQueue(queue("flaky") as QueuedCapture[]);
    await fc.flush();
    expect(loadQueue()[0]?.rejected).toBeUndefined();            // not marked final
    await fc.flush();
    expect(api.created).toEqual(["flaky"]);                      // and it lands on the retry
    expect(loadQueue()).toEqual([]);
  });

  it("408 and 429 invite a retry and are NOT treated as final", async () => {
    for (const status of [408, 429]) {
      const api = mkApi(() => new HttpError(`POST -> ${status}`, status));
      const fc = mounted(api);
      saveQueue(queue(`s${status}`) as QueuedCapture[]);
      await fc.flush();
      const [only] = loadQueue();
      expect(only, `status ${status}: the fixture must leave exactly one item`).toBeDefined();
      expect(only?.rejected, `status ${status}`).toBeUndefined();
    }
  });
});
