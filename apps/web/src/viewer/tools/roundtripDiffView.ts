/** The XLSX round-trip dry-run diff — and the three bounds it has to be honest about.
 *
 *  `roundtrip_diff` returns a PAGE of changes and a page of unknown GUIDs, from a sheet that is
 *  itself capped:
 *
 *  | bound | what it caps |
 *  |---|---|
 *  | `rows[1:5001]` | how much of the uploaded sheet is read at all |
 *  | `changes[:1000]` | how many changes come back |
 *  | `unknown_guids[:100]` | how many unmatched GUIDs are listed |
 *
 *  **Only the middle one was ever disclosed, and its flag was not DECLARED on the client**, so the
 *  panel could not read it — while `qaSection.ts` reads the identical flag correctly on a different
 *  response whose type does declare it. *A field absent from the declaration is invisible to every
 *  audit over declarations.*
 *
 *  The consequence is not a wrong label, it is a wrong WRITE. Apply posts `changes` verbatim through
 *  `set_props_by_guid`, so a sheet past the cap was applied in part and reported as whole: the model
 *  ends up differing from the spreadsheet the operator believes they applied, with no error
 *  anywhere. Reachable by construction — `_diff_row` emits one change per changed CELL against a
 *  5,000-row bound, so a single property column overflows a 1,000 cap fivefold.
 *
 *  Extracted from `qaSection.ts` rather than added to it: that file is under a down-only extraction
 *  ratchet in `services/api/test_file_sizes.py`, and the repo's guidance is a self-contained module
 *  plus one small mount point. It also makes these three decisions unit-testable, which string
 *  matching over the panel's source was never going to be.
 */
import type { ApiClient } from "../../api/client";
import { escapeHtml } from "../../ui/feedback";

export type RoundtripDiff = Awaited<ReturnType<ApiClient["roundtripDiff"]>>;

/** The headline. Every figure is a COUNT, never the length of the page it arrived in. */
export function statusHtml(d: RoundtripDiff): string {
  return `<b>${d.change_count}</b> change(s) across ${d.checked} rows`
    + (d.unknown_count ? ` · <b>${d.unknown_count}</b> unknown GUID(s) skipped` : "")
    + ` · ${d.unchanged} unchanged`
    + (d.rows_truncated
        ? ` · <b style="color:var(--status-warn)">only the first ${d.rows_cap} rows of `
          + `${d.rows_read} were read</b>`
        : "");
}

/** What the button will ACTUALLY do — it posts the page, so on an overflowing sheet it must not
 *  claim the total. */
export function applyLabel(d: RoundtripDiff): string {
  return d.truncated
    ? `✓ Apply the first ${d.changes.length} of ${d.change_count} change(s) + republish`
    : `✓ Apply ${d.changes.length} change(s) + republish`;
}

/** The warning beside it, or "" when the whole sheet came back. */
export function truncationNote(d: RoundtripDiff): string {
  if (!d.truncated) return "";
  return `<div class="meta" style="color:var(--status-warn);margin-top:4px">`
    + `This sheet has ${d.change_count} changes and the diff returns at most ${d.changes.length}. `
    + `Applying now writes those and leaves the rest — split the sheet and re-upload to apply all `
    + `of them.</div>`;
}

/** The change table, capped at 300 rows for the DOM's sake — a display bound, not a data one, and
 *  the count above it is already the real total. */
export function changeTable(d: RoundtripDiff): HTMLTableElement {
  const tbl = document.createElement("table");
  tbl.className = "result-table";
  for (const c of d.changes.slice(0, 300)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="k">${escapeHtml(c.guid.slice(0, 8))}… ${escapeHtml(c.pset)}.${escapeHtml(c.prop)}</td>`
      + `<td class="v">${escapeHtml(c.old ?? "—")} → <b>${escapeHtml(c.new)}</b></td>`;
    tbl.appendChild(tr);
  }
  return tbl;
}

export interface DiffViewCtx {
  status: HTMLElement;
  diffBox: HTMLElement;
  apply: (changes: RoundtripDiff["changes"], btn: HTMLButtonElement) => void | Promise<void>;
}

/** Render a completed dry run. Returns the Apply button, or null when there is nothing to apply. */
export function renderRoundtripDiff(d: RoundtripDiff, ctx: DiffViewCtx): HTMLButtonElement | null {
  ctx.status.innerHTML = statusHtml(d);
  if (!d.changes.length) return null;
  ctx.diffBox.appendChild(changeTable(d));
  const btn = document.createElement("button");
  btn.className = "mini-btn on";
  btn.style.marginTop = "6px";
  btn.textContent = applyLabel(d);
  const note = truncationNote(d);
  if (note) ctx.diffBox.insertAdjacentHTML("beforeend", note);
  btn.onclick = () => ctx.apply(d.changes, btn);
  ctx.diffBox.appendChild(btn);
  return btn;
}
