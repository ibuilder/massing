import type { ApiClient } from "../../api/client";
import { type ChipTone, statusChip } from "../../ui/chips";
import { confirmModal, promptModal } from "../../ui/modal";
import { resultNote, showResult } from "../../ui/result";
import { escapeHtml, toast, withLoading } from "../../ui/feedback";

/**
 * The model's publish history AND its review gate — R41-REACH-WRITES 4/4, the last of the four.
 *
 * TWO THINGS WERE MISSING AND ONLY ONE OF THEM WAS THE WRITE. `versions.history` has returned
 * `review_status`, `reviewed_by`, `reviewed_at` and `review_note` since MODEL-PUBLISH (R18) shipped.
 * `ApiClient.modelVersions` declared four of those eight keys, so the entire review record was
 * dropped at the client boundary — the version picker offered "v3" with no way to tell a draft from
 * an approved snapshot, which is precisely the distinction "issue drawings only from approved
 * versions" rests on. The state was invisible before it was unwritable.
 *
 * WHY `approve` IS TREATED DIFFERENTLY FROM ITS TWO SIBLINGS. The server's transition table is
 * `submit: draft→in_review`, `approve: in_review→approved`, `reject: in_review→draft` — and there is
 * **no transition out of `approved`**. Submit and reject are moves; approve is a one-way door, and
 * `reviewed_by` becomes a permanent answer to "who approved the model this set was issued from".
 * So approve gets a confirmation that says the word irreversible and names the account it will be
 * recorded against, while the other two do not need one.
 *
 * The server refuses `approve` from the api-key identity for the same reason (v0.3.895). This is the
 * caller-side half of that: it explains the rule before the click rather than after the 403.
 *
 * REJECT REQUIRES A NOTE. A rejection with no reason returns the snapshot to draft and tells its
 * author nothing about what to change, which turns a review gate into a stalling mechanism. The
 * server accepts an empty note; this refuses to send one.
 *
 * THE ACTIONS OFFERED COME FROM ONE TABLE, mirrored from `versions.py`. A button the server will
 * 409 is worse than an absent one — it reads as a broken feature rather than an unavailable move.
 */

export type ModelVersionRow = {
  version: number; element_count: number; note: string | null; created_at: string | null;
  review_status: "draft" | "in_review" | "approved";
  reviewed_by: string | null; reviewed_at: string | null; review_note: string | null;
};

export type ModelReviewDeps = {
  api: ApiClient;
  pid: string;
  out: HTMLElement;
  container: HTMLElement;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
};

/** The server's `_REVIEW_ACTIONS`, keyed by the state it moves FROM. Mirrored, not invented — if
 *  these ever disagree the UI offers a move the API refuses, so the table is written once here and
 *  read for both the button set and the legality check. */
const NEXT: Record<ModelVersionRow["review_status"], { action: "submit" | "approve" | "reject"; label: string }[]> = {
  draft: [{ action: "submit", label: "Submit for review" }],
  in_review: [{ action: "approve", label: "Approve" }, { action: "reject", label: "Reject" }],
  approved: [],
};

const TONE: Record<ModelVersionRow["review_status"], ChipTone> = {
  approved: "ok", in_review: "warn", draft: "neutral",
};

const LABEL: Record<ModelVersionRow["review_status"], string> = {
  approved: "approved", in_review: "in review", draft: "draft",
};

/** Who the server will record. Read from the same key `reportCenter.ts` uses; when it is absent the
 *  dialog says so rather than naming a plausible account, because the whole point of the sentence is
 *  that the reader recognises the name as theirs. */
function signedInAs(): string | null {
  try {
    return localStorage.getItem("aec_markup_user") || localStorage.getItem("aec_user") || null;
  } catch { return null; }
}

export function modelReviewButton(deps: ModelReviewDeps): HTMLButtonElement {
  const { api, pid, out, container, toolBtn2 } = deps;

  const render = (rows: ModelVersionRow[]) => {
    const approved = rows.filter((r) => r.review_status === "approved").length;
    out.textContent = `${rows.length} version(s) · ${approved} approved`;
    showResult("Model review", (body) => {
      if (!rows.length) {
        body.appendChild(resultNote("No versions yet — publish the model (Authoring) to snapshot one.", ""));
        return;
      }
      const latestApproved = rows.filter((r) => r.review_status === "approved")
        .reduce<number | null>((m, r) => (m === null || r.version > m ? r.version : m), null);
      body.appendChild(resultNote(
        latestApproved === null
          ? `<b>${rows.length}</b> version(s) · <b>none approved yet</b> — nothing here is cleared for issue.`
          : `<b>${rows.length}</b> version(s) · latest approved is <b>v${latestApproved}</b>.`, ""));

      for (const r of rows) {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:8px;align-items:baseline;justify-content:space-between;"
          + "padding:6px 0;border-bottom:1px solid var(--hairline,rgba(128,128,128,.2))";
        const txt = document.createElement("div");
        // Who and when are shown for every reviewed state, not only for approved. `reviewed_by` is
        // set by EVERY transition server-side, so it means "who last moved this" until the terminal
        // state — worded as "last action by" rather than "reviewed by" so it does not overclaim.
        const who = r.reviewed_by
          ? `<div class="meta">last action by ${escapeHtml(r.reviewed_by)}`
            + `${r.reviewed_at ? " · " + escapeHtml(r.reviewed_at.slice(0, 16).replace("T", " ")) : ""}`
            + `${r.review_note ? " — " + escapeHtml(r.review_note) : ""}</div>`
          : "";
        txt.innerHTML = `<b>v${r.version}</b> ${statusChip(LABEL[r.review_status], { tone: TONE[r.review_status] })}`
          + `<div class="meta">${r.element_count} element(s)`
          + `${r.note ? " · " + escapeHtml(r.note) : ""}</div>${who}`;

        const acts = document.createElement("div");
        acts.style.cssText = "display:flex;gap:6px;flex-shrink:0";
        for (const nx of NEXT[r.review_status]) {
          const b = document.createElement("button");
          b.className = "file-btn";
          b.textContent = nx.label;
          b.onclick = async () => {
            let note: string | undefined;
            if (nx.action === "reject") {
              // `required: true` is what actually enforces this — promptModal trims before checking,
              // so a whitespace-only entry keeps the dialog open with "…is required" and never
              // resolves. Verified in the browser rather than assumed: the first version of this
              // comment claimed the opposite (that `required` accepts all-space input and the local
              // check was the real guard) and was simply wrong about a helper in this repo.
              const v = await promptModal(`Reject v${r.version}?`,
                [{ name: "note", label: "What has to change before this can be approved?", required: true }],
                "Reject");
              if (!v) return;
              note = v.note;
              // Kept as a floor, not as the mechanism: this reads a `Record<string, string>` by key,
              // and a future caller renaming the field would otherwise send `undefined` silently.
              if (!note) { toast("A rejection needs a reason — not rejected.", "error"); return; }
            }
            if (nx.action === "approve") {
              const me = signedInAs();
              const ok = await confirmModal(`Approve v${r.version}?`,
                `THIS CANNOT BE UNDONE. There is no transition out of "approved" — no reopen, no `
                + `revoke. The only way past a wrong approval is to publish a new version.\n\n`
                + `${me ? `It will be recorded permanently as approved by "${me}".`
                       : `It will be recorded permanently against the account you are signed in as.`}\n\n`
                + `Approving does not change the model file. It marks this snapshot as the one `
                + `drawings may be issued from.`,
                "Approve permanently", true);
              if (!ok) return;
            }
            b.disabled = true;
            let res;
            try {
              res = await api.reviewModelVersion(pid, r.version, nx.action, note);
            } catch (e) {
              b.disabled = false;
              toast(`v${r.version} not ${nx.action}ed: ${(e as Error).message}`, "error");
              return;
            }
            // Report the state the SERVER returned, not the one requested. The transition can be
            // legal here and refused there — the api-key cannot approve — and echoing the intent
            // would show a green "approved" for a call that did nothing.
            // `res.review_status` is whatever the SERVER said, so it is looked up rather than
            // indexed: a state this build has never heard of must render as itself, not crash or
            // read as one of the three it does know.
            const shown = (LABEL as Record<string, string>)[res.review_status] ?? res.review_status;
            toast(`v${r.version} is now ${shown}`
              + `${res.reviewed_by ? ` (${res.reviewed_by})` : ""}`, "success");
            try {
              render(await api.modelVersions(pid));
            } catch {
              toast("Saved, but the history could not be re-read — reopen to confirm.", "error");
            }
          };
          acts.append(b);
        }
        if (!NEXT[r.review_status].length) {
          const done = document.createElement("span");
          done.className = "meta";
          done.textContent = "final";
          done.title = "Approved is terminal — publish a new version to supersede it.";
          acts.append(done);
        }
        row.append(txt, acts);
        body.appendChild(row);
      }
    });
  };

  return toolBtn2("✅ Model review (issue gate)",
    () => withLoading(container, "Reading version history", async () => {
      let rows: ModelVersionRow[];
      try { rows = await api.modelVersions(pid); }
      catch (e) { toast((e as Error).message, "error"); return; }
      render(rows);
    }));
}
