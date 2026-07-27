import { describe, expect, it } from "vitest";

import { identityScope } from "../api/identity";
import { allQueued, enqueueUpload, queuedCountForRecord } from "./offlineQueue";

/**
 * These run against the in-memory fallback: the module drops to it when IndexedDB is unavailable,
 * which is the case under vitest. That is the same path a locked-down browser takes, so it is worth
 * asserting on rather than mocking around.
 *
 * The fallback is module-level state that outlives a test, so each test uses its own `rid` and reads
 * back through that — no shared-state cleanup to forget.
 */
const signInAs = (t: string) => localStorage.setItem("aec-token", t);
const file = (n: string) => new File(["x"], n);
const mine = async (rid: string) => (await allQueued()).filter((q) => q.rid === rid);

describe("an upload queue on a shared device", () => {
  it("stamps the queuing session onto the entry", async () => {
    signInAs("token-A");
    await enqueueUpload({ pid: "p1", key: "rfi", rid: "stamp", files: [file("a.pdf")] });
    expect((await mine("stamp"))[0]?.owner).toBe(identityScope("token-A"));
  });

  it("the next person does not see the previous person's pending uploads", async () => {
    signInAs("token-A");
    await enqueueUpload({ pid: "p1", key: "rfi", rid: "hidden", files: [file("A-private.pdf")] });

    signInAs("token-B");
    expect(await mine("hidden")).toEqual([]);
    expect(await queuedCountForRecord("hidden")).toBe(0);   // the badge must not leak a count either
  });

  it("...and CRUCIALLY the work is not destroyed — it is waiting when they come back", async () => {
    // Filtering, not deleting. This is unsent work; losing it would be a worse bug than showing it.
    signInAs("token-A");
    await enqueueUpload({ pid: "p1", key: "rfi", rid: "returns", files: [file("A-private.pdf")] });
    signInAs("token-B");
    expect(await mine("returns")).toEqual([]);

    signInAs("token-A");
    const back = await mine("returns");
    expect(back).toHaveLength(1);
    expect(back[0]?.files[0]?.name).toBe("A-private.pdf");
  });

  it("each session sees only its own, with both queued against the same record", async () => {
    signInAs("token-A");
    await enqueueUpload({ pid: "p1", key: "rfi", rid: "both", files: [file("a.pdf")] });
    signInAs("token-B");
    await enqueueUpload({ pid: "p1", key: "rfi", rid: "both", files: [file("b.pdf")] });

    expect((await mine("both")).map((q) => q.files[0]?.name)).toEqual(["b.pdf"]);
    expect(await queuedCountForRecord("both")).toBe(1);
    signInAs("token-A");
    expect((await mine("both")).map((q) => q.files[0]?.name)).toEqual(["a.pdf"]);
  });
});
