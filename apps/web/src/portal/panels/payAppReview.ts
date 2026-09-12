/**
 * PAY-APP-SCREEN — the AIA G702 certificate and its G703 continuation sheet, on screen, from data.
 *
 * **Why this exists, and why it is not a nicety.** Until now a pay application could be FROZEN
 * (`POST …/cost/pay-app/invoice`) and DOWNLOADED (`GET …/cost/g702.pdf`), but never *read*. The
 * over-billing defect fixed in PAY-APP lived in line 7 — "less previous certificates for payment" —
 * and survived because line 7 existed only inside a PDF blob. Nobody could look at the nine lines
 * before submitting, so a wrong zero there was invisible until the next draw asked for the whole job
 * again. `GET …/cost/g702` and `GET …/cost/g703` had answered this all along and had no client
 * caller; they sat in `CONFIRMED_DARK_SHORT_LEAF` in `services/api/test_route_reachability.py` with
 * the note that a screen rendering the application from data would use them, and none existed.
 *
 * *A number a person cannot see is a number nothing checks.*
 *
 * Pure rules only — no DOM, no fetch. The panel that renders these is `payAppReviewPanel.ts`.
 */

/** The G702 certificate as `GET /projects/{pid}/cost/g702` returns it. */
export interface Certificate {
  application_no: number;
  period: string | null;
  retainage_released: boolean;
  line1_original_contract_sum: number;
  line2_net_change_orders: number;
  line3_contract_sum_to_date: number;
  line4_total_completed_stored: number;
  line5_retainage: number;
  line6_total_earned_less_retainage: number;
  line7_less_previous_certificates: number;
  line8_current_payment_due: number;
  line9_balance_to_finish_incl_retainage: number;
}

/** One row of the G703 continuation sheet. */
export interface SheetLine {
  item_no: string | null;
  description: string | null;
  cost_code: string | null;
  scheduled_value: number;
  completed_prev: number;
  completed_this: number;
  materials_stored: number;
  total_completed_stored: number;
  percent: number;
  balance_to_finish: number;
  retainage: number;
  retainage_prev: number;
}

export interface Sheet {
  lines: SheetLine[];
  totals: {
    scheduled: number; prev: number; this: number; stored: number;
    completed: number; balance: number; retainage: number; retainage_prev: number;
  };
}

/**
 * The nine lines, in the order the AIA G702 prints them. The order is the form's, not ours — a
 * certificate whose lines are reordered is not a G702, and a GC reading it against a paper copy
 * needs them to correspond one for one.
 */
export const CERT_LINES: { key: keyof Certificate; no: number; label: string }[] = [
  { key: "line1_original_contract_sum", no: 1, label: "Original contract sum" },
  { key: "line2_net_change_orders", no: 2, label: "Net change by change orders" },
  { key: "line3_contract_sum_to_date", no: 3, label: "Contract sum to date" },
  { key: "line4_total_completed_stored", no: 4, label: "Total completed & stored to date" },
  { key: "line5_retainage", no: 5, label: "Retainage" },
  { key: "line6_total_earned_less_retainage", no: 6, label: "Total earned less retainage" },
  { key: "line7_less_previous_certificates", no: 7, label: "Less previous certificates for payment" },
  { key: "line8_current_payment_due", no: 8, label: "Current payment due" },
  { key: "line9_balance_to_finish_incl_retainage", no: 9, label: "Balance to finish, plus retainage" },
];

const cents = (n: number) => Math.round(n * 100);

export interface Check {
  label: string;
  ok: boolean;
  /** The arithmetic as stated, so a failure says which two numbers disagree rather than just "no". */
  detail: string;
}

/**
 * The certificate's internal arithmetic, checked against itself and against the continuation sheet.
 *
 * A G702 is nine numbers with four identities between them, and the sheet totals into line 4. Those
 * identities are exactly what a reviewer would verify by hand, so the screen does it — **this is the
 * point of rendering from data rather than from a PDF.** Compared in integer cents: the engine rounds
 * to 2dp and binary floats do not survive `===` at that scale (0.1 + 0.2 is the standard example, and
 * this codebase has already been bitten by HALF_EVEN vs HALF_UP disagreeing by a penny inside one
 * G702).
 */
export function checks(cert: Certificate, sheet: Sheet): Check[] {
  const c = (k: keyof Certificate) => cents(cert[k] as number);
  return [
    { label: "Line 3 = line 1 + line 2",
      ok: c("line3_contract_sum_to_date")
        === c("line1_original_contract_sum") + c("line2_net_change_orders"),
      detail: `${cert.line1_original_contract_sum} + ${cert.line2_net_change_orders} = ${cert.line3_contract_sum_to_date}` },
    { label: "Line 6 = line 4 − line 5",
      ok: c("line6_total_earned_less_retainage")
        === c("line4_total_completed_stored") - c("line5_retainage"),
      detail: `${cert.line4_total_completed_stored} − ${cert.line5_retainage} = ${cert.line6_total_earned_less_retainage}` },
    { label: "Line 8 = line 6 − line 7",
      ok: c("line8_current_payment_due")
        === c("line6_total_earned_less_retainage") - c("line7_less_previous_certificates"),
      detail: `${cert.line6_total_earned_less_retainage} − ${cert.line7_less_previous_certificates} = ${cert.line8_current_payment_due}` },
    { label: "Line 9 = line 3 − line 6",
      ok: c("line9_balance_to_finish_incl_retainage")
        === c("line3_contract_sum_to_date") - c("line6_total_earned_less_retainage"),
      detail: `${cert.line3_contract_sum_to_date} − ${cert.line6_total_earned_less_retainage} = ${cert.line9_balance_to_finish_incl_retainage}` },
    { label: "Line 4 = the continuation sheet's completed total",
      ok: c("line4_total_completed_stored") === cents(sheet.totals.completed),
      detail: `sheet ${sheet.totals.completed} → line 4 ${cert.line4_total_completed_stored}` },
    { label: "Line 5 = the continuation sheet's retainage total",
      // Skipped, not failed, on a final application: `release_retainage` zeroes line 5 deliberately
      // while the sheet still carries the per-line amounts. Asserting equality there would report a
      // correct certificate as broken.
      ok: cert.retainage_released || c("line5_retainage") === cents(sheet.totals.retainage),
      detail: cert.retainage_released
        ? "retainage released on this application — line 5 is zero by design"
        : `sheet ${sheet.totals.retainage} → line 5 ${cert.line5_retainage}` },
  ];
}

export type Line7Basis = "matches-reconstruction" | "differs-from-reconstruction";

/**
 * Whether line 7 equals what it would be if RECONSTRUCTED from the sheet's previous columns.
 *
 * Line 7 is "less previous certificates for payment", and the AIA form says where to get it: line 6
 * of the prior certificate. It is a historical fact. With no stored application the engine can only
 * reconstruct it as `completed_prev − retainage_prev`, which is equal to the truth exactly while
 * nothing about the earlier periods has changed — edit a retainage rate or restate an earlier line
 * and the reconstruction moves while the signed certificate does not.
 *
 * So a DIFFERENCE here is not an error. It is the screen saying "this figure came from a certificate
 * somebody signed, not from re-adding the schedule of values", which is the stronger provenance and
 * is precisely what PAY-APP restored. Reporting it either way keeps the distinction visible instead
 * of letting a reconstruction pass as a fact.
 */
export function line7Basis(cert: Certificate, sheet: Sheet): Line7Basis {
  const reconstructed = cents(sheet.totals.prev) - cents(sheet.totals.retainage_prev);
  return cents(cert.line7_less_previous_certificates) === reconstructed
    ? "matches-reconstruction" : "differs-from-reconstruction";
}

export function line7Note(basis: Line7Basis): string {
  return basis === "differs-from-reconstruction"
    ? "deducted from what a submitted application actually certified — a historical fact, not a re-addition"
    : "equals the schedule of values re-added (no submitted application differs from it)";
}

/** Percent complete for the whole job, from the sheet totals. 0 when nothing is scheduled. */
export function percentComplete(sheet: Sheet): number {
  const scheduled = cents(sheet.totals.scheduled);
  if (!scheduled) return 0;
  return Math.round((cents(sheet.totals.completed) / scheduled) * 1000) / 10;
}

/** The headline: what this application is asking to be paid, and whether the form agrees with itself. */
export function summary(cert: Certificate, sheet: Sheet): {
  due: number; percent: number; failures: Check[]; sound: boolean;
} {
  const failures = checks(cert, sheet).filter((k) => !k.ok);
  return {
    due: cert.line8_current_payment_due,
    percent: percentComplete(sheet),
    failures,
    sound: failures.length === 0,
  };
}
