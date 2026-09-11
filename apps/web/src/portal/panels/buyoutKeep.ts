/** BUYOUT-KEEP — the wording for turning a computed grouping into records somebody can work.
 *
 *  Pure, so the rules can be tested without a DOM.
 *
 *  The buyout screen has always been able to GROUP the model's priced quantities into packages and
 *  render them — `POST …/procurement/buyout-packages` is wired and has been since PROCURE-LEVEL.
 *  **Keeping them was not.** `…/packages/save`, which persists each group as a `procurement_package`
 *  in `draft`, and `…/packages/{rid}/send-rfq`, which mints the Bid Solicitation and advances the
 *  workflow, both had no client caller — so a user could produce a buyout plan and had no way to act
 *  on it, and the whole draft → rfq_sent → quotes_in → awarded workflow was unreachable from the
 *  screen that produces its input. Same transient-to-record shape as the prefab freeze, on money.
 */

/** One package as the grouping returns it, before anything is stored. */
export interface GroupedPackage {
  package: string;
  line_count: number;
  est_cost: number;
}

/** One package as the SAVE returns it — now a record, with a ref somebody can quote. */
export interface SavedPackage {
  id: string | number;
  ref: string;
  name: string;
  est_cost: number | null;
  line_count: number;
}

/** What `sendPackageRfq` answered. `package_state` is the half that can disappoint. */
export interface RfqResult {
  solicitation: { id: string | number; ref: string };
  package: string;
  package_state: string | null;
}

/**
 * Whether the grouping is worth keeping, and the reason when it is not.
 *
 * Saving nothing would create nothing and report a cheerful count of zero, which reads as success.
 */
export function saveGate(packageCount: number): { can: boolean; why: string } {
  if (packageCount <= 0) {
    return { can: false,
             why: "there are no packages to keep — group the quantities first" };
  }
  return { can: true, why: "" };
}

/**
 * The confirmation before writing.
 *
 * Names the blast radius rather than the mechanics: these become records the whole project can see
 * and work, not a private draft in this browser, and the count is stated so a mis-grouping is
 * caught before it becomes twelve records somebody has to delete one at a time.
 */
export function saveConfirm(pkgs: GroupedPackage[], groupedBy: string): string {
  const n = pkgs.length;
  const total = pkgs.reduce((sum, p) => sum + (p.est_cost || 0), 0);
  return `Keep ${n} buyout package${n === 1 ? "" : "s"} (grouped by ${groupedBy}, `
    + `about ${fmtUsd(total)} estimated)?\n\n`
    + "Each one becomes a Buyout Packages RECORD in draft — visible to the whole project, trackable "
    + "through draft → RFQ sent → quotes in → awarded, and quotable by ref. This is not a draft in "
    + "your browser. Re-grouping and keeping again creates a SECOND set; it does not replace this one.";
}

/**
 * What the save actually created.
 *
 * A zero-length `created` is reported as the nothing it is: the server answers 200 with an empty
 * list when the grouping produced no packages, and a client that trusts the resolved promise would
 * print "saved" over an empty write.
 */
export function saveSummary(created: SavedPackage[], expected?: number): string {
  if (!created.length) {
    return "Nothing was kept — the grouping produced no packages, so no record was created.";
  }
  const n = created.length;
  const refs = created.slice(0, 4).map((p) => p.ref).join(", ");
  const more = n > 4 ? ` +${n - 4} more` : "";
  const head = `Kept ${n} buyout package${n === 1 ? "" : "s"}: ${refs}${more}.`;
  // The count the CONFIRMATION named, versus what came back. The server re-groups at write time
  // from the lines it is sent, so these can differ; saying so beats reporting a clean success for a
  // set the reader never agreed to.
  return expected != null && expected !== n
    ? `${head} NOTE: ${expected} package${expected === 1 ? " was" : "s were"} offered and ${n} `
      + `${n === 1 ? "was" : "were"} created — the server re-grouped at write time.`
    : head;
}

/**
 * Whether an RFQ can be sent for this package, and why not when it cannot.
 *
 * Two distinct refusals. A package with no record id was never stored — the route is keyed on the
 * record id and would 404 indistinguishably from a refusal on the merits. A package past `draft`
 * has already had its RFQ sent, and sending again is the double-send trap below.
 */
export function rfqGate(pkg: { id?: string | number | null; state?: string | null }):
    { can: boolean; why: string } {
  if (pkg.id == null || pkg.id === "") {
    return { can: false, why: "this package has not been kept yet, so there is nothing to send" };
  }
  const state = (pkg.state || "draft").toLowerCase();
  // An explicit `unknown` is NOT "already sent": the server answered without a state, so what the
  // package is now is exactly what nobody knows. Saying "its RFQ has gone out" would assert the one
  // thing the response failed to establish, so it gets its own refusal pointing at a reload.
  if (state === "unknown") {
    return { can: false,
             why: "the server did not report this package's state after the last send — reload the "
                  + "register before sending again" };
  }
  if (state !== "draft") {
    return { can: false,
             why: `this package is already ${state.replace(/_/g, " ")} — its RFQ has gone out` };
  }
  return { can: true, why: "" };
}

/** The confirmation before minting a solicitation. Names both writes, because there are two. */
export function rfqConfirm(pkg: SavedPackage, due?: string): string {
  return `Send an RFQ for ${pkg.ref} (${pkg.name})?\n\n`
    + "This mints a Bid Solicitation record carrying the package's name, trade and due date, and "
    + `moves the package from draft to RFQ sent${due ? `, due ${due}` : ""}. Both are records the `
    + "project can see.";
}

/**
 * What the send actually did — and this is the load-bearing rule of this file.
 *
 * **The server mints the solicitation unconditionally and transitions only a `draft` package.** So a
 * second send produces a second ITB and leaves the state exactly where it was, and a client that
 * says "RFQ sent" because the promise resolved would report a clean success for a duplicate
 * solicitation nobody asked for. When the state did not reach `rfq_sent`, say so and say what the
 * state actually is.
 */
export function rfqSummary(r: RfqResult): string {
  const ref = r.solicitation?.ref || "(unnamed)";
  const state = (r.package_state || "").toLowerCase();
  if (state === "rfq_sent") {
    return `RFQ ${ref} created and ${r.package} moved to RFQ sent.`;
  }
  return `RFQ ${ref} was created, but ${r.package} did NOT move to RFQ sent — it is `
    + `${state ? state.replace(/_/g, " ") : "in an unreported state"}. A solicitation has been `
    + "minted anyway, so check whether this package already had one before sending another.";
}

/** Money, in whole dollars — the estimating figures here are never cent-precise. */
function fmtUsd(n: number): string {
  return `$${Math.round(n).toLocaleString("en-US")}`;
}
