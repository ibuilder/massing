/**
 * UPLOAD-POISON — the portal's offline attachment queue, and the rule for when to stop retrying.
 *
 * WHAT THIS FIXES. `flushUploads` lived on `RegisterUI` and ended in
 * `catch { /* leave it queued for the next reconnect *\/ }`. Every failure re-queued the entry
 * unchanged, with nothing separating a server that was unreachable from one that had answered "no".
 * A file the server will never accept — a validation refusal, or a worker removed from the project
 * between queueing and reconnecting — was resent on every reconnect for as long as the app stayed
 * installed. Three things followed, and the third is the one that has no equivalent in the field
 * queue this defect was first found in:
 *
 *   1. the record's notice kept promising "will upload when back online", about a file that would
 *      not;
 *   2. the entry sat in front of the good ones on every pass;
 *   3. **the bytes never left the device.** These entries hold real `File` objects in IndexedDB, so
 *      an un-droppable upload is not a queue slot, it is storage held forever — and there was no
 *      per-entry discard anywhere in the UI, so the only cure was clearing site data.
 *
 * WHY IT IS A SEPARATE FILE. `register.ts` carries an extraction ratchet, and that pin's own comment
 * says the remedy is extraction, never headroom. This is a genuine leaf: it moves files to the
 * server and reports what happened, reaching back for exactly three things — the API, a status line
 * and a pins-changed nudge — which arrive as `UploadHost` rather than the whole panel context.
 */
import { permanentRejection } from "../../api/httpCore";
import {
  type QueuedUpload, allQueued, dequeue, enqueueUpload, markRejected, queuedCountForRecord,
  refusedForRecord,
} from "../offlineQueue";

/** The three things moving a queued file needs from the shell. Deliberately not `PanelContext`:
 *  a narrow port is what lets this be tested without standing up a panel. */
export interface UploadHost {
  api: {
    uploadAttachment(pid: string, key: string, rid: string, file: File): Promise<unknown>;
    uploadAttachmentsBulk(pid: string, key: string, rid: string, files: File[]): Promise<unknown>;
  };
  setStatus(msg: string): void;
  onPinsChanged(): void;
}

const plural = (n: number) => (n > 1 ? "s" : "");

export class UploadQueue {
  constructor(private host: UploadHost) {}

  private hooked = false;

  /** Persist an upload that couldn't go out (offline) and flush when the connection returns. */
  async queue(pid: string, key: string, rid: string, files: File[]): Promise<void> {
    await enqueueUpload({ pid, key, rid, files });
    this.host.setStatus(`offline — ${files.length} file${plural(files.length)} queued, will upload on reconnect`);
    this.hookOnline();
  }

  /** Register the reconnect flush once (also called at startup to drain a prior session's queue). */
  hookOnline(): void {
    if (this.hooked) return;
    this.hooked = true;
    window.addEventListener("online", () => void this.flush());
  }

  /**
   * Send what can be sent; mark what never can; keep everything else.
   *
   * Entries already carrying `rejected` are not even read from — the point of the mark is that the
   * request has been answered and asking again cannot change it.
   */
  async flush(): Promise<void> {
    if (!navigator.onLine) return;
    let done = 0;
    let refused = 0;
    for (const q of await allQueued()) {
      if (q.rejected) continue;
      try {
        await this.send(q);
        await dequeue(q.id);
        done += q.files.length;
      } catch (e) {
        const why = permanentRejection(e);
        if (!why) continue;              // transient — stays queued, untouched, for the next pass
        await markRejected(q.id, why);
        refused += q.files.length;
      }
    }
    if (done) {
      this.host.setStatus(`back online — uploaded ${done} queued file${plural(done)}`);
      this.host.onPinsChanged();
    }
    if (refused) {
      this.host.setStatus(`${refused} queued file${plural(refused)} refused — open the record to see why`);
    }
  }

  private send(q: QueuedUpload): Promise<unknown> {
    const one = q.files.length === 1 ? q.files[0] : undefined;
    return one
      ? this.host.api.uploadAttachment(q.pid, q.key, q.rid, one)
      : this.host.api.uploadAttachmentsBulk(q.pid, q.key, q.rid, q.files);
  }
}

/**
 * Fill a record's attachment notice with what is actually queued for it.
 *
 * Pending and refused are counted and worded separately, because they are different promises: one
 * says the upload is coming, the other says it is not and why. Refused entries get a Discard button
 * — the only way, before this, to get a permanently-refused file off the device was to clear the
 * site's storage. Nothing is discarded automatically: the person who took the photo decides.
 */
export async function renderQueueNotice(el: HTMLElement, rid: string): Promise<void> {
  const [pending, refused] = await Promise.all([queuedCountForRecord(rid), refusedForRecord(rid)]);
  el.textContent = "";
  if (pending) {
    const line = document.createElement("div");
    line.textContent = `⏳ ${pending} file${plural(pending)} queued (offline) — will upload when back online`;
    el.appendChild(line);
  }
  for (const q of refused) {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;align-items:center;gap:6px;color:var(--danger,#e5534b)";
    const what = document.createElement("span");
    what.style.flex = "1";
    what.textContent = `⚠ ${q.files.length} file${plural(q.files.length)} refused — ${q.rejected}; retrying will not help`;
    const drop = document.createElement("button");
    drop.className = "tool-btn";
    drop.textContent = "Discard";
    drop.onclick = async () => { await dequeue(q.id); await renderQueueNotice(el, rid); };
    row.append(what, drop);
    el.appendChild(row);
  }
}
