/**
 * LIEN-PLACEHOLDER — the statutory lien waiver was downloadable as a PDF reading `[Claimant]`,
 * `[Customer]`, `[Owner]` and `through [date]`, and the only screen that produced it showed a title
 * and a dollar amount.
 *
 * A lien waiver is not a report. It is a **release of mechanics-lien, stop-payment-notice and
 * payment-bond rights** — in most US states a statutory form whose wording is prescribed — and
 * `cost.lien_waiver` builds it properly: the title, the statutory `notice`, the release `body`, the
 * `exceptions` carve-out, the `through_date` a progress release is bounded by, and a
 * `signature_block`. The route takes `claimant`, `customer` and `through_date` so the body can name
 * them.
 *
 * **The client passed none of the three**, so every waiver this product has ever produced rendered
 * the placeholders literally — measured end to end: a GET with no parameters returns a body reading
 * *"Upon receipt by the undersigned of a check from [Customer] in the sum of $0.00 payable to
 * [Claimant] …"*, and the PDF route, which defaults the same parameters to `""`, puts
 * `[Claimant] [Customer] [Owner] [date]` on the page. **And the screen showed neither.** The button
 * was labelled "Lien waiver (JSON)" and set a status line to `"<title> — $<amount>"`: the amount
 * being waived, with none of the scope of the waiver — not the release language, not the exceptions,
 * not the date the progress release runs through.
 *
 * *The amount is the least legally consequential number in the document.* What binds is what is
 * released, from whom, through when, and what is excepted.
 *
 * **So the guard here is a refusal, not a warning.** `readiness` reports NOT ready while any
 * placeholder survives in the body or the notice, and the card withholds the PDF link until it is.
 * A PDF is an artifact somebody signs; an unfinished one with square brackets in it is worse than
 * no PDF, because it looks like a form rather than a bug. *A document that is not ready must not be
 * downloadable as if it were.*
 *
 * Pure, plain text: every field is free text a user typed or the server composed from it.
 */

export interface LienWaiver {
  kind: string;
  title: string;
  conditional: boolean;
  final: boolean;
  amount: number;
  body: string;
  notice: string;
  project_name: string;
  claimant?: string;
  customer?: string;
  through_date?: string;
  application_no?: number;
  exceptions?: string;
  signature_block?: { claimant_title?: string; date?: string };
}

/** The four the engine substitutes, and the field each one is waiting for. */
export const PLACEHOLDER_FIELDS: { token: string; field: string }[] = [
  { token: "[Claimant]", field: "claimant" },
  { token: "[Customer]", field: "customer" },
  { token: "[Owner]", field: "customer" },
  { token: "[Project]", field: "project name" },
  { token: "[date]", field: "through date" },
];

export const WAIVER_KINDS: { value: string; label: string }[] = [
  { value: "conditional_progress", label: "Conditional — progress payment" },
  { value: "unconditional_progress", label: "Unconditional — progress payment" },
  { value: "conditional_final", label: "Conditional — final payment" },
  { value: "unconditional_final", label: "Unconditional — final payment" },
];

export type WaiverTone = "ok" | "warn";

export const WAIVER_CSS: Record<WaiverTone, string> = {
  ok: "var(--status-good)", warn: "var(--status-warn)",
};

/**
 * Which placeholders are still in the document, and which input each one waits on.
 *
 * Scans `body` AND `notice`: the statutory notice is prescribed text and may name the claimant too,
 * so checking only the body would clear a document that still carries a bracket. Deduplicated by
 * FIELD rather than by token, because `[Customer]` and `[Owner]` are both filled by one input and
 * reporting two missing fields for one empty box is a reader's wild-goose chase.
 */
export function unfilled(w: LienWaiver): { token: string; field: string }[] {
  const text = `${w.body ?? ""}\n${w.notice ?? ""}`;
  const seen = new Set<string>();
  const out: { token: string; field: string }[] = [];
  for (const p of PLACEHOLDER_FIELDS) {
    if (!text.includes(p.token)) continue;
    if (seen.has(p.field)) continue;
    seen.add(p.field);
    out.push(p);
  }
  return out;
}

/**
 * Is this a document somebody could sign?
 *
 * `ready` gates the PDF, and it is deliberately NOT "the user filled the boxes" — it is "no bracket
 * survives in the composed text". The server does the substitution, so only the server's own output
 * can answer, and a client-side check of its own inputs would pass a document whose wording changed.
 */
export function readiness(w: LienWaiver): { ready: boolean; text: string; tone: WaiverTone } {
  const gaps = unfilled(w);
  if (!gaps.length) {
    return { ready: true,
             text: "Every field is filled — this release reads as a complete document.",
             tone: "ok" };
  }
  const fields = [...new Set(gaps.map((g) => g.field))];
  return {
    ready: false,
    text: `⚠ NOT READY TO SIGN — the release still reads ${gaps.map((g) => g.token).join(", ")}. `
      + `Fill ${fields.join(", ")} before producing the PDF: this is a statutory release of `
      + "mechanics-lien rights, and one with unfilled brackets in it looks like a form rather than "
      + "an unfinished document.",
    tone: "warn",
  };
}

/** The document's identifying fields, for display beside the release text. */
export function waiverFields(w: LienWaiver): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [
    { label: "Form", value: w.title },
    { label: "Payment", value: w.conditional ? "Conditional" : "Unconditional" },
    { label: "Stage", value: w.final ? "Final" : "Progress" },
    { label: "Amount released", value: `$${Math.round(w.amount).toLocaleString()}` },
  ];
  if (w.application_no !== undefined) rows.push({ label: "Pay application", value: `#${w.application_no}` });
  rows.push({ label: "Claimant", value: w.claimant || "— not given —" });
  rows.push({ label: "Customer / owner", value: w.customer || "— not given —" });
  // THROUGH DATE IS ONLY MEANINGFUL ON A PROGRESS RELEASE, and on one it is the whole bound: the
  // release covers labour and material furnished through that date and nothing after it. A final
  // release covers everything, so the row would be a blank nobody should try to fill.
  if (!w.final) {
    rows.push({ label: "Covers work through", value: w.through_date || "— not given —" });
  }
  return rows;
}
