/**
 * R24-REPORTS-BY-MOMENT — the Report Center is a list of nouns.
 *
 * 56 reports under **18** group headings, six of which hold a single report. The groups are accurate
 * — `Cost`, `Quality`, `Logs` — and accuracy is not the problem. Nobody arrives at the Report Center
 * wanting *a cost report*. They arrive because the owner's monthly package is due on Friday, or the
 * lender wants a draw supported, or the IC meets Tuesday. The catalog answers *"what kinds of report
 * exist"* and the user asked *"what do I owe, to whom, by when"*.
 *
 * That is the same routing-vs-browsing distinction the room spine settled for modules, arriving one
 * layer down: a taxonomy is a fine way to *hold* 56 things and a poor way to *reach* them.
 *
 * **Nothing is removed.** The moments are a layer above the groups, not a replacement — every report
 * stays under its noun heading, which is still the right structure for the person who genuinely wants
 * to browse the surface area. This is the same shape as "the catalog survives behind All modules".
 *
 * Three rules the table follows:
 *
 * * **A moment names who is asking and when**, never a category. If a name could head a filing
 *   cabinet drawer it is a group, not a moment, and it belongs in the layer below.
 * * **A report may appear in several moments, and most do.** The noun taxonomy has to pick one home
 *   for `verified_progress`; the truth is it is evidence in a lender draw, in a monthly package and
 *   at closeout. Forcing one home is precisely what made the catalog hard to route through.
 * * **A moment that names a report the server does not serve is a defect, reported.** Never silently
 *   dropped — a moment that quietly renders four of its six rows looks complete, and the missing two
 *   are exactly the ones nobody notices are missing. Same rule the spine applies to an unroomed
 *   module. `reportMoments.test.ts` asserts the ids against `reports.py` itself, so a renamed report
 *   fails the build rather than thinning a package on a Friday.
 */

export interface ReportMoment {
  id: string;
  /** What the user would call this occasion. */
  label: string;
  /** Who is asking, and when — the line that makes it a moment rather than a category. */
  occasion: string;
  /** Report ids from `GET /reports`, in the order the package is normally assembled. */
  reports: string[];
}

/**
 * The moments, ordered by how often they come round.
 *
 * Deliberately **seven**. The audit named four; the extra three are the ones the catalog itself
 * revealed once the reports were laid out by occasion — a design issue, a GMP handover and an
 * ownership quarter are all recurring deliverables here with reports already built for them. An
 * eighth would be a filing drawer.
 */
export const REPORT_MOMENTS: ReportMoment[] = [
  {
    id: "owner_monthly",
    label: "Monthly owner package",
    occasion: "Due to the owner each month — progress, money, and what moved",
    reports: [
      "project_health", "executive", "cost", "evm", "resource_loading",
      "change_orders", "rfi", "submittals", "field_log", "safety", "quality",
    ],
  },
  {
    id: "lender_draw",
    label: "Lender draw",
    occasion: "Supporting a construction-loan draw request",
    // verified_progress leads: a draw is an argument that the work is IN PLACE, and this is the only
    // report here that says so from the model rather than from a schedule of values.
    reports: ["verified_progress", "cost", "wip", "evm", "contractor_financials", "change_orders", "tm_log"],
  },
  {
    id: "ic_meeting",
    label: "Investment committee",
    occasion: "Taking a deal to committee for approval",
    reports: ["ic_memo", "investor_pack", "appraisal", "financials", "market_intelligence", "site_feasibility", "cap_table"],
  },
  {
    id: "precon_gmp",
    label: "Preconstruction / GMP handover",
    occasion: "Fixing the price — what was assumed, decided and excluded",
    reports: ["estimate_continuity", "assumptions_register", "decision_log", "precon_alignment", "cost", "site_feasibility"],
  },
  {
    id: "design_issue",
    label: "Design issue / model handover",
    occasion: "Issuing a model or drawing set to the next party",
    reports: ["bep", "model_health", "bim_kpi", "lod", "naming", "design_standards", "document_control", "spec_submittal_log"],
  },
  {
    id: "closeout",
    label: "Closeout & turnover",
    occasion: "Handing the finished building to whoever operates it",
    reports: ["closeout", "verified_progress", "document_control", "quality", "lod", "contracts", "action_tracker"],
  },
  {
    id: "ownership_quarter",
    label: "Ownership quarter",
    occasion: "Reporting on a building you now operate rather than build",
    reports: ["rent_roll", "lease_management", "financials", "fca", "esg", "resilience"],
  },
];

export interface CatalogEntry { id: string; name: string; group: string }

/**
 * Report ids a moment names that the server does not serve.
 *
 * Returned rather than thrown, and surfaced rather than swallowed: the Report Center still opens with
 * the reports that DO exist, and says which ones it could not find. A package that silently loses a
 * row is worse than one that admits to it, because the person assembling it has no other signal.
 */
export function missingReportIds(
  moments: readonly ReportMoment[],
  catalog: readonly CatalogEntry[],
): string[] {
  const have = new Set(catalog.map((r) => r.id));
  const gaps = new Set<string>();
  for (const m of moments) for (const id of m.reports) if (!have.has(id)) gaps.add(id);
  return [...gaps].sort();
}

/** A moment's entries, resolved against the catalog and in the moment's own order. Unknown ids drop
 *  out here — `missingReportIds` is what reports them, so this stays a pure lookup. */
export function resolveMoment(m: ReportMoment, catalog: readonly CatalogEntry[]): CatalogEntry[] {
  const by = new Map(catalog.map((r) => [r.id, r]));
  return m.reports.map((id) => by.get(id)).filter((r): r is CatalogEntry => !!r);
}

/**
 * Reports named by no moment at all.
 *
 * Not a defect — 56 reports and seven occasions means a long tail by design, and the noun groups
 * still hold every one of them. It is worth being able to *ask*, though: a report that no occasion
 * ever calls for is either badly named, or nobody has worked out when it is due.
 */
export function unclaimedReports(
  moments: readonly ReportMoment[],
  catalog: readonly CatalogEntry[],
): string[] {
  const claimed = new Set(moments.flatMap((m) => m.reports));
  return catalog.map((r) => r.id).filter((id) => !claimed.has(id));
}
