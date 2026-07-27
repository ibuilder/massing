import { beforeEach, describe, expect, it } from "vitest";

import { identityScope } from "../api/identity";
import { type QueuedCapture, loadAll, loadQueue, saveQueue } from "./field";

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
