import type { ApiClient } from "../../api/client";
import { escapeHtml as esc } from "../../ui/feedback";

/**
 * TURNOVER-UNGATED — the quality gate built for G704 certification was rendered as a caption.
 *
 * `quality_chain.turnover_readiness` exists, in its own words, as *"the seam `turnover.py` never
 * had"*, and it is careful about the one thing that matters: `ready` requires evidence to **exist**
 * and be resolved, because *"an element with no quality record counts against readiness rather than
 * for it — otherwise a project nobody inspected reads as perfectly clean, which is the failure this
 * exists to prevent."*
 *
 * The Operations turnover tab read it, printed one line from it, and gated nothing on it. The
 * architect's "certify substantial completion" button checked
 * `rd.ready_for_substantial_completion` — the PUNCH-list readiness from a different route — and
 * nothing else. Structurally it could not have done otherwise: the quality answer arrived in a
 * detached `.then()`, so it was not even in scope where the decision is made. *A gate whose verdict
 * reaches the screen as a sentence beside the button, instead of as an input to it, is a caption.*
 *
 * Three defects in about twelve lines, each with the honest field already in the payload:
 *
 *  1. **The certify action consulted the punch gate only.** G704 is certified *with* an outstanding
 *     punch list, so a hard veto would be wrong — the engine deliberately does not assert one. What
 *     was missing is that the architect was never *told*, at the moment of signing, what the quality
 *     evidence does and does not support. It is now an acknowledgement that names each item and
 *     defaults to cancel.
 *  2. **`any_attached: false` rendered as zeros.** With no quality records at all, the caption read
 *     "0 outstanding · 0 never inspected · coverage 0%" — which is what a clean, fully-inspected
 *     project with no findings would also look like at a glance. `message` is the field that says
 *     which it is, and the screen dropped it.
 *  3. **`.catch(() => {})` swallowed a failed read as an empty register**, so an API error removed
 *     the card and left the turnover tab looking like a project with no quality concerns.
 */

export type QualityTurnover = Awaited<ReturnType<ApiClient["qualityTurnoverReadiness"]>>;
export type QualityChain = Awaited<ReturnType<ApiClient["qualityChain"]>>;

export interface QualityReading {
  /** `unread` — the read failed. `no-evidence` — nothing is attached at all. */
  kind: "unread" | "no-evidence" | "outstanding" | "unrecorded" | "ready";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * What the quality evidence says about closeout.
 *
 * `null` means the read failed, and that is its own state: *a question that could not be asked is
 * not an answer of "nothing".* It is reported, not swallowed, because the previous behaviour —
 * dropping the card — made an API error indistinguishable from a project with no quality concerns.
 */
export function qualityReading(qt: QualityTurnover | null): QualityReading {
  if (!qt) {
    return {
      kind: "unread", tone: "warn",
      headline: "The quality evidence could not be read.",
      detail: "This is not a statement that there is nothing to report — nothing is known either "
        + "way. Certifying over it means certifying without having looked.",
    };
  }
  if (!qt.any_attached) {
    return {
      kind: "no-evidence", tone: "bad",
      headline: "No quality record is attached to any element on this project.",
      detail: (qt.message || "")
        + " Coverage is 0%: this is the ABSENCE of evidence, not evidence of conformance, and it "
        + "reads identically to a clean project unless somebody says so.",
    };
  }
  if (qt.outstanding_count) {
    return {
      kind: "outstanding", tone: "bad",
      headline: `${qt.outstanding_count} element(s) carry unresolved quality evidence`
        + (qt.unrecorded_count ? `, and ${qt.unrecorded_count} have no record at all.` : "."),
      detail: `Coverage ${qt.coverage_pct}%. An unresolved NCR, a failed inspection or an `
        + "unverified hold point is a finding the certificate cannot currently speak to. "
        + qt.basis,
    };
  }
  if (qt.unrecorded_count) {
    return {
      kind: "unrecorded", tone: "warn",
      headline: `${qt.unrecorded_count} element(s) have no quality record at all.`,
      detail: `Coverage ${qt.coverage_pct}%. Nothing is outstanding, because nothing was `
        + "inspected on these — which is not the same as nothing being wrong. " + qt.basis,
    };
  }
  return {
    kind: "ready", tone: "ok",
    headline: "Quality evidence exists for every element and nothing is outstanding.",
    detail: `Coverage ${qt.coverage_pct}%.`,
  };
}

/**
 * What the architect must acknowledge before certifying, one line each — empty when the quality
 * evidence supports closeout.
 *
 * **Deliberately not a veto.** G704 substantial completion is certified with an outstanding punch
 * list, and `turnover_readiness`'s own docstring says an open NCR "does not by itself block
 * certification". Turning this into a hard refusal would assert a rule the engine declined to
 * assert, and would make the certificate unissuable on any project with one uninspected element.
 * What was actually missing is that the signatory was never told. *A decision made without the
 * information is not the same decision as one made over it.*
 */
export function certifyAcknowledgements(qt: QualityTurnover | null): string[] {
  const r = qualityReading(qt);
  switch (r.kind) {
    case "ready":
      return [];
    case "unread":
      return ["The quality evidence could not be read, so nothing is known about it."];
    case "no-evidence":
      return ["No quality record is attached to ANY element — coverage 0%. The absence of "
              + "evidence is not evidence of conformance."];
    default: {
      const out: string[] = [];
      if (qt!.outstanding_count) {
        out.push(`${qt!.outstanding_count} element(s) carry unresolved quality evidence `
                 + "(an open NCR, a failed inspection, or an unverified hold point).");
      }
      if (qt!.unrecorded_count) {
        out.push(`${qt!.unrecorded_count} element(s) have no quality record at all.`);
      }
      out.push(`Quality coverage is ${qt!.coverage_pct}%.`);
      return out;
    }
  }
}

/** The confirm body: the acknowledgements, then what signing means. */
export function certifyConfirmBody(acks: string[]): string {
  return "The quality evidence does not support closeout on every element:\n\n"
    + acks.map((a) => `• ${a}`).join("\n")
    + "\n\nCertifying substantial completion now records that you certified with this known. "
    + "G704 is routinely certified with an outstanding punch list, so this is a judgement rather "
    + "than a bar — but it is yours to make, not the form's.";
}

/**
 * The per-element evidence chain — `/projects/{pid}/quality/chain`, which had no client method and
 * no screen.
 *
 * It is what makes the count above actionable: a user told "42 element(s) have no quality record"
 * could not see WHICH, and an unverified hold point — the specific thing an ITP exists to stop being
 * skipped — is named by the engine and appeared nowhere.
 */
export function chainRowsHtml(chain: QualityChain): string {
  if (!chain.elements.length) {
    return `<div class="meta">${esc(chain.message || "no quality records name any element yet")}`
      + `</div>`;
  }
  // Worst first, and `unrecorded` ranks above `clear` rather than below it: the whole point is that
  // an element nobody inspected is not a pass.
  const rank: Record<string, number> = { outstanding: 0, unrecorded: 1, clear: 2 };
  const rows = [...chain.elements].sort((a, b) =>
    (rank[a.status] ?? 9) - (rank[b.status] ?? 9) || a.guid.localeCompare(b.guid));
  const icon: Record<string, string> = { outstanding: "🔴", unrecorded: "❓", clear: "✅" };
  return rows.slice(0, 200).map((e) => `<div class="meta" style="margin:2px 0">`
    + `${icon[e.status] ?? "•"} <code>${esc(e.guid)}</code> — ${esc(e.status)} · `
    + `${esc(String(e.record_count))} record(s)`
    + (e.open_count ? ` · <b>${esc(String(e.open_count))}</b> open` : "")
    + (e.unverified_hold_points?.length
        ? ` · <b>${esc(String(e.unverified_hold_points.length))}</b> unverified hold/witness point(s)`
        : "")
    + `<br><span style="opacity:.7">${esc(e.status_note)}</span></div>`).join("")
    + (rows.length > 200 ? `<div class="meta">…and ${esc(String(rows.length - 200))} more `
       + `element(s) not listed here</div>` : "");
}
