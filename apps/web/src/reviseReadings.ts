/** REVISE-DARK — a drawing revision could be read and never issued, and the one number that came
 *  back over-reported a failure the engine swallows on purpose.
 *
 *  ## The capability had no door
 *
 *  `POST /projects/{pid}/drawings/{id}/revise` records an AIA revision delta on a sheet, bumps its
 *  revision, and slip-sheets the markups. `apps/web/src/api/clientCallers.test.ts` held
 *  `reviseDrawing` in its frozen callerless set, and a tree-wide grep found no call site outside
 *  `api/`. The register was readable — the drawing-set tool renders `Revisions (N)` from
 *  `drawingRevisions` — so a revision could be *seen* and never *issued*. *A read-only half of a
 *  write capability reads as a feature rather than as a missing one.*
 *
 *  ## And `markups_carried` counted intentions, not writes
 *
 *  `drawingset.revise_sheet` tags every existing markup on the sheet `carried_from` so a reviewer
 *  re-checks it against the revised sheet. That tagging sits inside `except Exception: pass`
 *  **deliberately** — the comment says *"tagging must never block a revision"*, and that is right.
 *  But the counter was incremented in the loop and `db.commit()` sat inside the same `try`, so a
 *  failed commit returned the loop's count over nothing persisted. Measured by injecting a failure
 *  on that commit:
 *
 *  | | response | markups actually tagged |
 *  |---|---|---|
 *  | before | `{"revision":"1","delta_count":1,"markups_carried":3}` | **0 of 3** |
 *  | after | `{"markups_carried":0,"markups_to_carry":3,"markups_carry_failed":"RuntimeError"}` | 0 of 3 |
 *
 *  The revision landing anyway is the deliberate half and is asserted in
 *  `services/api/test_drawing_revision.py`. The claim that the re-check flags are in place is the
 *  defect, and it runs in the reassuring direction on the one operation where a stale markup is
 *  the hazard: a reviewer looking at a revised sheet cannot tell a markup was made against the old
 *  one unless the tag is there. *A count computed before the write that persists it is a count of
 *  intentions.*
 */
import type { RevisionResult } from "./api/drawingSheets";

export type Tone = "" | "good" | "warn" | "crit";

/** Literal, not `var(--status-${tone})` — a custom property built at runtime resolves to nothing
 *  and is dropped in silence (`apps/web/src/shell/cssVars.test.ts` holds that line). */
export const TONE_CSS: Record<Tone, string> = {
  "": "",
  good: "var(--status-good)",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** The change instruments a revision can cite, from `drawing_issuance`'s own `purpose` options —
 *  the register's vocabulary rather than a second list invented here. `""` is "no instrument",
 *  which is a legitimate revision (a drafting correction cites nothing). */
export const INSTRUMENTS = ["", "Addendum", "ASI", "Bulletin", "CCD", "RFI"] as const;

/** Did this revision actually record? The route 422s without a `rev`, so this is about the sheet. */
export function revisionLine(r: RevisionResult): string {
  return `Rev ${r.revision} recorded — ${r.delta_count} delta(s) now on this sheet.`;
}

/** The slip-sheet verdict, with the coverage the number alone cannot carry.
 *
 *  Four states. The third is the one this item exists for: the tagging failed, the revision stands,
 *  and the markups on the sheet still read as current when they are not. */
export function carryVerdict(r: RevisionResult): { text: string; tone: Tone } {
  if (r.markups_carry_failed) {
    const n = r.markups_to_carry;
    return {
      tone: "crit",
      text: `⚠ ${n} markup(s) could NOT be tagged carried-forward (${r.markups_carry_failed}). `
        + `The revision is recorded, but those markups were made against the previous revision and `
        + `carry no re-check flag — a reviewer cannot tell they are stale. Re-issue the revision or `
        + `re-check them by hand.`,
    };
  }
  if (r.markups_to_carry === 0) {
    return { tone: "", text: "No markups on this sheet needed carrying forward." };
  }
  return {
    tone: "good",
    text: `${r.markups_carried} markup(s) tagged carried-forward — each now asks a reviewer to `
      + `re-check it against this revision.`,
  };
}

/** The relation the two counts are supposed to satisfy, checked rather than assumed.
 *
 *  `markups_carried === markups_to_carry` unless the tagging failed. Returns a sentence only when
 *  they disagree WITHOUT a failure being reported, which is a shape neither this client nor the
 *  engine should be able to produce — so saying so is better than rendering a number that cannot
 *  be true. *A consumer that can only report good news is the thing this whole class of defect
 *  needed in order to survive.* */
export function carryReconciles(r: RevisionResult): string | null {
  if (r.markups_carry_failed) return null;
  if (r.markups_carried === r.markups_to_carry) return null;
  return `Markup carry-forward does not reconcile: ${r.markups_carried} tagged of `
    + `${r.markups_to_carry} attempted, with no failure reported. Treat every markup on this sheet `
    + `as unverified against the new revision.`;
}

/** One option per drawing record, newest-revision-last so the picker reads like a sheet index.
 *
 *  Takes the module records rather than the drawing-set register on purpose: `drawingset.register`
 *  carries `ref` and `sheet_number` and **no record id**, and the route is keyed by the record id.
 *  *A screen cannot act through a read that omits the identifier the write needs.* */
export function sheetOptions(
  records: { id: string; ref?: string | null; data?: unknown }[],
): { id: string; label: string; revision: string }[] {
  return records
    .map((rec) => {
      const d = (rec.data ?? {}) as { sheet_number?: string; number?: string; title?: string;
                                      revision?: string };
      const sheet = (d.sheet_number || d.number || rec.ref || "").trim();
      const rev = (d.revision ?? "").toString().trim();
      return {
        id: rec.id,
        revision: rev,
        label: [sheet || "(unnumbered)", d.title, rev ? `rev ${rev}` : "no revision"]
          .filter(Boolean).join(" · "),
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

/** The next revision to propose, from the sheet's current one. Numeric revisions increment; an
 *  alphabetic one (A → B) advances a letter; anything else is left for the user to type.
 *
 *  A SUGGESTION, never a silent default — `_rev_key` in the engine ranks alpha and numeric
 *  revisions separately, so guessing wrong would reorder the set. Returns `""` when it cannot tell. */
export function nextRev(current: string): string {
  const c = (current ?? "").trim();
  if (!c) return "1";
  if (/^\d+$/.test(c)) return String(Number(c) + 1);
  if (/^[A-Y]$/.test(c)) return String.fromCharCode(c.charCodeAt(0) + 1);
  return "";
}
