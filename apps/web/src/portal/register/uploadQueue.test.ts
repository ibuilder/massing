import { beforeEach, describe, expect, it } from "vitest";

import { HttpError } from "../../api/httpCore";
import { allQueued, enqueueUpload, queuedCountForRecord, refusedForRecord } from "../offlineQueue";
import { type UploadHost, UploadQueue, renderQueueNotice } from "./uploadQueue";

/**
 * UPLOAD-POISON — the portal's offline attachment queue could not be emptied.
 *
 * These drive the REAL `offlineQueue`, not a mock of it. The test environment has no `indexedDB`,
 * so every call lands on that module's in-memory fallback — which is the same path a real device
 * takes in private browsing, and which had its own defect: entries carried no id, so `dequeue`
 * fell through to `memFallback.shift()` and removed whichever entry happened to be FIRST. Mocking
 * the store would have hidden that completely, which is the argument for not mocking it.
 */
const file = (name: string) => new File([name], name, { type: "image/jpeg" });

/** Replaces the module-level queue between tests — there is no reset export, and adding one for the
 *  tests' benefit would put a production API in the file for a reason production never has. */
const emptyQueue = async () => {
  const { dequeue } = await import("../offlineQueue");
  for (const q of await allQueued()) await dequeue(q.id);
};

function host(fail: (rid: string) => Error | null) {
  const sent: string[] = [];
  const status: string[] = [];
  let pinsChanged = 0;
  const send = async (_p: string, _k: string, rid: string) => {
    const e = fail(rid);
    if (e) throw e;
    sent.push(rid);
    return {};
  };
  const h: UploadHost & { sent: string[]; status: string[]; pins: () => number } = {
    api: {
      uploadAttachment: (p, k, rid) => send(p, k, rid),
      uploadAttachmentsBulk: (p, k, rid) => send(p, k, rid),
    },
    setStatus: (m) => { status.push(m); },
    onPinsChanged: () => { pinsChanged++; },
    sent,
    status,
    pins: () => pinsChanged,
  };
  return h;
}

describe("UPLOAD-POISON — a queued file the server refuses", () => {
  beforeEach(async () => {
    await emptyQueue();
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
  });

  it("does not hold the good uploads behind it", async () => {
    const h = host((rid) => (rid === "poison" ? new HttpError("upload -> 400", 400) : null));
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "poison", files: [file("a.jpg")] });
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "good", files: [file("b.jpg")] });

    await new UploadQueue(h).flush();

    expect(h.sent).toEqual(["good"]);
    expect(await queuedCountForRecord("good")).toBe(0);          // sent, so gone
    expect(await queuedCountForRecord("poison")).toBe(0);        // refused, so not "pending"
    expect((await refusedForRecord("poison"))[0]?.rejected).toBeTruthy();
  });

  it("keeps the refused file — never discards somebody's work on their behalf", async () => {
    const h = host(() => new HttpError("upload -> 403", 403));
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "r1", files: [file("a.jpg")] });

    await new UploadQueue(h).flush();

    const refused = await refusedForRecord("r1");
    expect(refused).toHaveLength(1);
    expect(refused[0]?.files).toHaveLength(1);                   // the bytes are still here
    expect(refused[0]?.rejected).toBe("No longer permitted on this project");
  });

  it("never asks the server about a refused file again", async () => {
    const h = host(() => new HttpError("upload -> 400", 400));
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "r1", files: [file("a.jpg")] });
    await new UploadQueue(h).flush();

    // second pass, with a server that would now accept anything: the marked entry is not offered
    const h2 = host(() => null);
    await new UploadQueue(h2).flush();
    expect(h2.sent).toEqual([]);
    expect(await refusedForRecord("r1")).toHaveLength(1);
  });

  it("a 5xx stays a retry and lands on the next pass", async () => {
    let attempts = 0;
    const h = host(() => (++attempts === 1 ? new HttpError("upload -> 503", 503) : null));
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "r1", files: [file("a.jpg")] });
    const q = new UploadQueue(h);

    await q.flush();
    expect(await refusedForRecord("r1")).toHaveLength(0);        // NOT marked final
    expect(await queuedCountForRecord("r1")).toBe(1);            // still pending

    await q.flush();
    expect(h.sent).toEqual(["r1"]);
    expect(await allQueued()).toHaveLength(0);
  });

  it("an offline failure — a bare TypeError, no status — is a retry, not a refusal", async () => {
    // The most common failure this queue exists for does not arrive as an HttpError at all.
    const h = host(() => new TypeError("Failed to fetch"));
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "r1", files: [file("a.jpg")] });
    await new UploadQueue(h).flush();
    expect(await refusedForRecord("r1")).toHaveLength(0);
    expect(await queuedCountForRecord("r1")).toBe(1);
  });

  it("dequeues the entry that SUCCEEDED, not whichever one is first", async () => {
    // The in-memory fallback's own defect, which only shows up with two entries and a failure on
    // the earlier one: `shift()` would have dropped the file that never reached the server.
    const h = host((rid) => (rid === "first" ? new HttpError("upload -> 503", 503) : null));
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "first", files: [file("a.jpg")] });
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "second", files: [file("b.jpg")] });

    await new UploadQueue(h).flush();

    const left = await allQueued();
    expect(left.map((q) => q.rid)).toEqual(["first"]);           // the one that failed, still here
    expect(h.sent).toEqual(["second"]);
  });
});

describe("the record's attachment notice", () => {
  beforeEach(async () => {
    await emptyQueue();
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
  });

  it("promises an upload only for work that will actually be attempted", async () => {
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "r1", files: [file("a.jpg")] });
    const el = document.createElement("div");
    await renderQueueNotice(el, "r1");
    expect(el.textContent).toContain("will upload when back online");
  });

  it("says why a refused file is refused, instead of calling it pending", async () => {
    const h = host(() => new HttpError("upload -> 404", 404));
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "r1", files: [file("a.jpg")] });
    await new UploadQueue(h).flush();

    const el = document.createElement("div");
    await renderQueueNotice(el, "r1");
    expect(el.textContent).not.toContain("will upload when back online");
    expect(el.textContent).toContain("The project or record no longer exists");
    expect(el.textContent).toContain("retrying will not help");
  });

  it("offers a discard, which is the only way these bytes ever leave the device", async () => {
    const h = host(() => new HttpError("upload -> 400", 400));
    await enqueueUpload({ pid: "p1", key: "punchlist", rid: "r1", files: [file("a.jpg")] });
    await new UploadQueue(h).flush();

    const el = document.createElement("div");
    await renderQueueNotice(el, "r1");
    const discard = el.querySelector("button");
    expect(discard?.textContent).toBe("Discard");

    discard!.click();
    await new Promise((r) => setTimeout(r, 0));
    expect(await allQueued()).toHaveLength(0);
  });
});
