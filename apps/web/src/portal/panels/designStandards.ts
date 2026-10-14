import type { DesignStandardCheck, DesignStandardItem } from "../../api/types";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * DESIGN-STD-DARK — the firm's design standards, and the model measured against them.
 *
 * `services/api/src/aec_api/design_standards.py` is the rules layer the generator and in-viewer
 * authoring are meant to honour: approved, preferred and prohibited assemblies, materials and
 * products, matched by keyword against the openBIM property data a model already carries. Both its
 * routes were frozen in `test_route_reachability.UNREACHABLE_ROUTES`.
 *
 * **The input was already authorable, which is what made this a door rather than a feature.**
 * `ruleset()` reads the `design_standard` module register through `modules.list_records`, and
 * `services/api/modules/design_standard` has shipped for as long as the register has — so a firm
 * could record its standards and nothing would ever check a model against them. *A capability whose
 * write half is reachable and whose read half is not fails no gate that asks about one side*, which
 * is `test_stored_standard_writable`'s lesson with the sides swapped.
 *
 * ## Three coverage facts, and not one of them is the verdict
 *
 * The engine reports COUNTS and no boolean, deliberately, so this card invents none either. What it
 * must never do is let a count read as a result:
 *
 * **① `model_scored: false`.** The no-model response carries `prohibited_hits: 0` and
 * `unapproved: 0` beside the ruleset. Two zeros that look exactly like a clean audit, on a project
 * with no model loaded.
 *
 * **② `approved_declared: 0`.** `unapproved` is counted only when an approved set exists, so with
 * none declared it is permanently 0 — correct, and on screen indistinguishable from "every element
 * matched something approved". *A zero meaning "nothing to compare against" and a zero meaning
 * "nothing failed" are different answers to different questions.*
 *
 * **③ `coverage.truncated`.** The violation list is capped while both counts stay complete, and the
 * engine's loop stops appending unapproved rows at the cap *while still counting them* — so the list
 * is short of the total by design and `coverage.flagged` is the only honest total. Printing
 * `violations.length` beside the word "violations" is TRUNC-COUNTED.
 *
 * A fourth, quieter one: a standard row with **no match keyword cannot match anything**. The engine
 * filters prohibited rows on it and counts approved keywords rather than approved rows, so a firm
 * that recorded twenty standards and left the keyword blank gets an audit of nothing — with a
 * register that looks full. The card names that gap from the ruleset it already has.
 */

/** Rows with a status the engine buckets, but no keyword — declared and inert. */
export function keywordlessRows(items: readonly DesignStandardItem[]): DesignStandardItem[] {
  const scored = new Set(["approved", "preferred", "prohibited"]);
  return items.filter((i) => scored.has(i.status) && !(i.match_keyword || "").trim());
}

/** Rows whose status the engine does not bucket at all — also inert, for a different reason. */
export function unscoredStatuses(items: readonly DesignStandardItem[]): string[] {
  const scored = new Set(["approved", "preferred", "prohibited"]);
  return [...new Set(items.map((i) => i.status).filter((s) => !scored.has(s)))].sort();
}

/**
 * The audit, in the states a reader can actually be in. Returns a value so a test can assert it
 * without going looking in a DOM.
 */
export function auditNote(c: DesignStandardCheck): { html: string; kind: "ok" | "warn" | "bad" } {
  const cov = c.coverage;
  if (!c.model_scored) {
    return { html: `<b>NOT AUDITED</b> — ${esc(c.note)} The ruleset below has `
                 + `${c.ruleset.count} standard(s); nothing has been measured against it.`,
             kind: "warn" };
  }
  if (!cov.prohibited_declared && !cov.approved_declared) {
    return { html: "<b>NOTHING TO AUDIT</b> — the model loaded and no standard carries a match "
                 + `keyword, so every count below is 0 of nothing. ${esc(cov.reason)}`,
             kind: "warn" };
  }
  const scope = `${c.elements} element(s) against ${cov.prohibited_declared} prohibited and `
    + `${cov.approved_declared} approved/preferred keyword(s)`;
  if (!cov.flagged) {
    return { html: `<b>No violations</b> — ${scope}.`
                 + (cov.approved_declared ? "" : " <b>No approved set is declared</b>, so the "
                   + "unapproved count is not a measurement: only prohibited matches were looked for."),
             kind: cov.approved_declared ? "ok" : "warn" };
  }
  const shown = cov.truncated
    ? ` Showing ${cov.listed} of ${cov.flagged} — the list is capped at ${cov.cap}.`
    : "";
  return { html: `<b>${cov.flagged} flagged</b> — ${c.prohibited_hits} prohibited match(es) and `
               + `${c.unapproved} matching nothing approved, over ${scope}.${shown}`,
           kind: c.prohibited_hits ? "bad" : "warn" };
}

/** What the register declares but the audit cannot use. Empty when the ruleset is sound. */
export function inertNote(c: DesignStandardCheck): string | null {
  const blank = keywordlessRows(c.ruleset.items);
  const odd = unscoredStatuses(c.ruleset.items);
  const bits: string[] = [];
  if (blank.length) {
    bits.push(`<b>${blank.length} standard(s) carry no match keyword</b> and can never fire: `
      + blank.slice(0, 8).map((i) => esc(i.name || "(unnamed)")).join(", ")
      + (blank.length > 8 ? ", …" : ""));
  }
  if (odd.length) {
    bits.push(`<b>${odd.length} status value(s) the audit does not bucket</b> — `
      + odd.map(esc).join(", ") + " — so those rows are declared and inert");
  }
  return bits.length ? bits.join("<br>") : null;
}

/** One row per flagged element. */
export function violationRows(c: DesignStandardCheck): { k: string; v: string }[] {
  return c.violations.map((v) => ({ k: v.type || "(untyped)", v: `${v.issue} · ${v.guid}` }));
}

/** The ruleset, by the three statuses the audit uses. */
export function statusRows(c: DesignStandardCheck): { k: string; v: string }[] {
  return ["prohibited", "approved", "preferred"].map((s) => {
    const rows = c.ruleset.by_status[s] ?? [];
    const withKw = rows.filter((r) => (r.match_keyword || "").trim()).length;
    return { k: s, v: rows.length
      ? `${rows.length} declared, ${withKw} with a keyword: `
        + rows.slice(0, 6).map((r) => r.name || "(unnamed)").join(", ") + (rows.length > 6 ? ", …" : "")
      : "none declared" };
  });
}

/** The card, appended to the CDE / Standards panel. */
export async function renderDesignStandards(ctx: PanelContext, host: HTMLElement,
                                            pid: string): Promise<void> {
  host.textContent = "auditing…";
  let c: DesignStandardCheck;
  try { c = await ctx.host.api.designStandardsCheck(pid); }
  catch (e) { host.textContent = `design standards unavailable: ${(e as Error).message}`; return; }
  // The SLOT pattern this panel file already records, and its liveness check with it: `root` is
  // shared by every panel and cleared by whoever renders next, so a late write belongs in a node
  // appended up front — and `isConnected` goes false the moment `root.innerHTML` is cleared, which
  // is the cheapest way to know the reader has moved on. The bug it documents (PR #527) was a late
  // `.then` appending a card into a DIFFERENT screen; writing into a detached slot is merely a
  // no-op, but leaving the guard out would be rebuilding the hazard on purpose.
  if (!host.isConnected) return;
  const note = auditNote(c);
  const inert = inertNote(c);
  // Both interpolations below are in `innerHtmlGuard`'s BASELINE, and reaching that conclusion took
  // a wrong turn worth recording. The first version imported `resultNote` from `ui/result` to make
  // the interpolation disappear rather than be excused — and that **promoted `ui/result` into the
  // shared app-shell chunk**, because a module two lazy chunks import is hoisted out of both. The
  // shell went from 14 bytes over its Brotli cap to 34. *A fix that removes a lint finding by moving
  // code into the eager bundle is not free, and the budget is the only thing that says so.*
  //
  // So: hand-written markup, and the two expressions declared. They are safe by construction —
  // every value inside `note.html` and `inert` goes through `esc` in the functions above, and `kind`
  // is a union of three literals — which is exactly the case the baseline exists for. The guard
  // follows one level of indirection (PR #544), so this is a declaration about reachable values, not
  // a hole: a NEW unescaped interpolation in those functions still reds.
  host.innerHTML = `<div class="result-note ${note.kind}">${note.html}</div>`
    + (inert ? `<div class="result-note warn" style="margin-top:6px">${inert}</div>` : "")
    + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:6px">`
    + statusRows(c).map((r) => `<tr><td style="white-space:nowrap;padding-right:8px"><b>${esc(r.k)}</b></td>`
        + `<td>${esc(r.v)}</td></tr>`).join("")
    + `</table>`
    + (c.violations.length
        ? `<table class="fin-table" style="width:100%;font-size:12px;margin-top:6px">`
          + violationRows(c).map((r) => `<tr><td style="white-space:nowrap;padding-right:8px">${esc(r.k)}</td>`
              + `<td>${esc(r.v)}</td></tr>`).join("")
          + `</table>`
        : "");
}
