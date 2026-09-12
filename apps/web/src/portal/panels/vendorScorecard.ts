/**
 * VENDOR-SCORECARD — a trade partner's record with your firm, and the limits of that record.
 *
 * `GET /benchmarks/vendors` (`services/api/src/aec_api/vendor_memory.py`) has reported every
 * vendor's cross-project commercial and compliance history since R22-PROCURE-DEPTH ③ and had no
 * client caller the whole time. Its five `/benchmarks/*` siblings all have one.
 *
 * **It is also the route LEDGER-BROWSE blinded the reachability gate to**, in the commit before this
 * one. That sprint's entity list contains `vendors`, so `/connections/{cid}/erp/vendors` became a
 * URL this client builds and the leaf `vendors` read as called — by something else. Wiring this
 * route removes the blind spot's SUBJECT rather than leaving a record of it; the gate still cannot
 * see this route in either direction, and `test_route_reachability.py` says so.
 *
 * Three rules, and all three are the server's own — stated there in prose, enforced here, because a
 * caveat that lives only in a JSON field nobody renders is a caveat nobody reads.
 *
 * 1. **`no_history` is NOT `clear`.** A sub who has never worked for you is an unknown. The engine
 *    calls a clean-looking record for an unexamined vendor "the single most expensive mistake this
 *    module could make", and it is a RENDERING mistake as much as an engine one: three verdicts that
 *    reach the same pixel are one verdict. `verdictTone` refuses to give `no_history` the tone it
 *    gives `clear`.
 * 2. **A clean record here is silence about quality, not a pass.** `ncr` and `inspection` carry no
 *    vendor field, so nothing in this scorecard has looked at quality or schedule performance. The
 *    server says so in `attributable`; a screen that shows the numbers and drops that sentence
 *    asserts something the data cannot support. `attributionLine` is not optional chrome.
 * 3. **A certificate with no expiry is not cover.** `coi_missing_expiry` is counted separately from
 *    `coi_expired` precisely so a missing date cannot read as insurance in force — the same
 *    absent-vs-negative distinction as rule 1, one field down. `coiLine` keeps them apart, and says
 *    "none recorded" rather than "0 problems" when there is no certificate at all.
 */

export type Verdict = "no_history" | "clear" | "watch";

export interface VendorRow {
  vendor: string;
  verdict: string;
  verdict_note?: string;
  project_count: number;
  subcontract_value: number;
  committed: number;
  spent: number;
  invoiced: number;
  lien_waivers_value: number;
  coi_expired: number;
  coi_missing_expiry: number;
  warranties_live: number;
  record_counts?: Record<string, number>;
  flags?: string[];
  trades?: string[];
}

export interface VendorMemory {
  vendors?: VendorRow[];
  vendor_count?: number;
  repeat_vendors?: number;
  watch_count?: number;
  attributable?: { from?: string[]; not_from?: string[]; note?: string };
  message?: string | null;
}

/**
 * The three verdicts, kept visually distinct.
 *
 * `no_history` gets its own tone — NOT the one `clear` gets, and not a neutral blank either, which
 * would read as "nothing to report". An unknown vendor must look different from a vetted one at a
 * glance, because the glance is all most readers give a table row.
 */
export function verdictTone(verdict: string): { label: string; colour: string } {
  if (verdict === "clear") return { label: "clear", colour: "#33d17a" };
  if (verdict === "watch") return { label: "watch", colour: "#e2554a" };
  if (verdict === "no_history") return { label: "no history", colour: "#f0a400" };
  // An unrecognised verdict is not assumed benign: a fourth state added server-side must not
  // inherit `clear`'s green by falling through.
  return { label: verdict || "unknown", colour: "#9aa0a6" };
}

/** Whether this verdict may be read as a positive finding. Only one of them may. */
export function isReassuring(verdict: string): boolean {
  return verdict === "clear";
}

/**
 * What the scorecard did NOT look at, in the server's own words where it supplies them.
 *
 * Never returns an empty string. If the payload omits `attributable` the sentence is still stated
 * from what this module knows, because the silence is a property of the ROUTE, not of one response —
 * and a missing caveat reads as no caveat.
 */
export function attributionLine(mem: VendorMemory): string {
  const note = mem.attributable?.note?.trim();
  if (note) return `Commercial and compliance only — ${note.replace(/^commercial and compliance history only\.\s*/i, "")}`;
  return "Commercial and compliance history only. Quality and schedule performance are not "
    + "attributable to a vendor here, so a clean record below is silence on that subject, not a pass.";
}

/**
 * Insurance, with "expired", "unknown" and "none recorded" kept apart.
 *
 * A vendor with no certificate at all is not compliant and not lapsed — they are unrecorded, and
 * printing "0 expired" for them is the `no_history` error one field down.
 */
export function coiLine(row: VendorRow): string {
  const certs = row.record_counts?.coi ?? 0;
  if (!certs) return "No certificate of insurance recorded — cover is unknown, not absent of problems.";
  const bits: string[] = [];
  if (row.coi_expired) bits.push(`${row.coi_expired} expired`);
  if (row.coi_missing_expiry) bits.push(`${row.coi_missing_expiry} with no expiry recorded (cover unknown)`);
  if (!bits.length) return `${certs} certificate(s) on file, none expired and all carrying an expiry date.`;
  return `${certs} certificate(s) on file — ${bits.join(", ")}.`;
}

/** Money invoiced beyond the lien waivers on file, or null when they have not billed. */
export function lienExposure(row: VendorRow): number | null {
  if (row.invoiced <= 0) return null;
  const gap = row.invoiced - row.lien_waivers_value;
  return gap > 0.01 ? Math.round(gap * 100) / 100 : 0;
}

/**
 * The headline, which must not imply a verdict the set does not support.
 *
 * `watch_count` alone would read as "everything else is fine"; the count with no history is stated
 * beside it so the reader can see how much of the portfolio was actually examined.
 */
export function summaryLine(mem: VendorMemory): string {
  const rows = mem.vendors ?? [];
  if (!rows.length) return mem.message || "No vendor history yet.";
  const unknown = rows.filter((r) => r.verdict === "no_history").length;
  const watch = rows.filter((r) => r.verdict === "watch").length;
  const repeat = mem.repeat_vendors ?? rows.filter((r) => r.project_count > 1).length;
  const parts = [`${rows.length} vendor(s)`, `${repeat} used on more than one project`, `${watch} on watch`];
  if (unknown) parts.push(`${unknown} with NO recorded history — unknown, not clear`);
  return `${parts.join(" · ")}.`;
}

/**
 * Worst first: watch, then unknown, then by EXPOSURE — the money at risk, not the contract size.
 *
 * **The first draft said "by exposure" and sorted by `subcontract_value`**, which a review bot
 * caught. They are not the same thing and the difference is the point of the column: a fully waived
 * $9M subcontract carries no lien exposure, while a $50k sub with unwaived invoices does. Sorting by
 * size would have pushed the second below the first — and with the table capped at 25 rows, off the
 * screen entirely. *A docstring that names the right key does not make the code use it.*
 *
 * `lienExposure` is null for a vendor who has not billed; `?? 0` ranks them with the fully-waived,
 * which is correct here — neither has money at risk. Size stays as the next tiebreak so a large
 * contract still outranks a small one at equal exposure.
 */
export function ordered(rows: VendorRow[]): VendorRow[] {
  const rank = (v: string) => (v === "watch" ? 0 : v === "no_history" ? 1 : 2);
  return [...rows].sort((a, b) =>
    rank(a.verdict) - rank(b.verdict)
    || (lienExposure(b) ?? 0) - (lienExposure(a) ?? 0)
    || (b.subcontract_value || 0) - (a.subcontract_value || 0)
    || a.vendor.localeCompare(b.vendor));
}
