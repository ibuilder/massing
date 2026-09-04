/**
 * The comment thread on a register record — render it, add to it, and promote an entry out of it.
 *
 * Lived inline in `register.ts` until R22-ENTITLEMENT ⑤ added the promote control and the file's
 * extraction ratchet went red. The pin's question is whether the block is a leaf, and this one is:
 * it touches the record's `comments`, the API, and a reload callback, and nothing else on the class.
 *
 * **R22-ENTITLEMENT ⑤ — why a comment needs a way out.** An agency's review comment is the one input
 * that must LEAVE the thread: somebody has to be assigned it and it has to close. Promoting mints an
 * RFI carrying the comment text, the source record's ref and its element ties. Once promoted the
 * control is replaced by its outcome, because the second press would 409 and a button whose only
 * remaining result is an error is worse than no button at all.
 */
import type { ModuleDef, ModuleRecord } from "../../api/client";

export interface RecordCommentsDeps {
  root: HTMLElement;
  api: {
    addComment(pid: string, key: string, rid: string, text: string): Promise<unknown>;
    promoteComment(pid: string, key: string, rid: string, cid: string,
                   kind?: "rfi" | "issue"): Promise<unknown>;
  };
  setStatus(msg: string): void;
  reload(): void;
}

/** Render the thread + composer for one record. */
export function mountRecordComments(d: RecordCommentsDeps, pid: string, m: ModuleDef,
                                    rid: string, r: ModuleRecord): void {
  const cd = document.createElement("div");
  cd.className = "section-title"; cd.textContent = "Comments";
  d.root.appendChild(cd);

  for (const cm of r.comments ?? []) {
    const e = document.createElement("div"); e.className = "portal-act";
    e.textContent = `${cm.author ?? ""}: ${cm.text}`;
    if (cm.topic_id) {
      const done = document.createElement("span");
      done.className = "meta"; done.textContent = "  → RFI raised";
      e.appendChild(done);
    } else if (cm.id) {
      const cid = cm.id;
      const pb = document.createElement("button");
      pb.className = "mini-btn"; pb.textContent = "→ RFI"; pb.style.marginLeft = "6px";
      pb.title = "Raise an RFI from this comment";
      pb.onclick = async () => {
        pb.disabled = true;
        try { await d.api.promoteComment(pid, m.key, rid, cid); d.reload(); }
        catch (err) { pb.disabled = false; d.setStatus(`promote failed: ${(err as Error).message}`); }
      };
      e.appendChild(pb);
    }
    d.root.appendChild(e);
  }

  const ta = document.createElement("textarea");
  ta.className = "portal-field"; ta.placeholder = "Add a comment…"; ta.style.width = "100%";
  const addBtn = document.createElement("button");
  addBtn.className = "tool-btn"; addBtn.textContent = "Comment"; addBtn.style.margin = "4px 0";
  addBtn.onclick = async () => {
    if (!ta.value.trim()) return;
    await d.api.addComment(pid, m.key, rid, ta.value.trim());
    d.reload();
  };
  d.root.append(ta, addBtn);
}
