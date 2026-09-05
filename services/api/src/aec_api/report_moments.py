"""R24-REPORTS-BY-MOMENT — the moments, moved server-side so a routine can name one.

The moments were authored in `apps/web/src/ui/reportMoments.ts` and lived only there: a routing layer
over the 56-report catalog, resolved in the browser, turned into `{moment_id, reports[]}` and handed
to the `report_package` job. That works for a person clicking a button and **cannot work for a
schedule**, which is the gap R22-ROUTINES left open.

`routines_run.run_due` enqueues `{routine_id, window_start}` plus the project id. `report_package`
needs a `reports[]` list. Nothing server-side could produce one, because the only table saying which
reports make up an owner's monthly package was in a browser bundle. So "the owner package, every
month, automatically" — the plainest thing anyone would want from a scheduler over a report
catalog — was unreachable, and `modules/routine/module.json` had to say so in its help text.

**Python owns the table now; the TypeScript literal mirrors it.** Two copies of one fact, which is
the thing this repository has scars from, so it is bound the same way `reportMoments.test.ts` already
binds the catalog: that test reads THIS FILE off disk and asserts the two tables are identical — ids,
order, labels, occasions and report lists. A moment edited on one side and not the other fails the
web build.

**Why not one copy.** The single-source alternative is to delete the TS literal and fetch the moments
from an endpoint. It is better and it is not free: `reportCenter.ts` resolves `REPORT_MOMENTS`
synchronously while rendering, so it becomes a second await on a path that already awaits the
catalog, and the seven-way `missingReportIds` gap report changes shape with it. That is a Report
Center change; this is a scheduler change. Recorded rather than done, because the next reader should
know the duplication was chosen and priced, not overlooked.

**The report ids are NOT re-validated here.** `_report_package` already refuses an unknown id rather
than shortening the package, and `reportMoments.test.ts` asserts every id against `reports.py`
itself. A third check in this module would be a copy of a rule that already fails a build twice.
"""
from __future__ import annotations

from typing import Any

#: moment id -> (label, occasion, report ids in assembly order).
#:
#: Ordered by how often the occasion comes round, and identical — including that order — to
#: `REPORT_MOMENTS` in `apps/web/src/ui/reportMoments.ts`.
MOMENTS: dict[str, tuple[str, str, list[str]]] = {
    "owner_monthly": ("Monthly owner package",
                      "Due to the owner each month — progress, money, and what moved",
                      ["project_health", "executive", "cost", "evm", "resource_loading",
                       "change_orders", "rfi", "submittals", "field_log", "safety", "quality"]),
    "lender_draw": ("Lender draw",
                    "Supporting a construction-loan draw request",
                    ["verified_progress", "cost", "wip", "evm", "contractor_financials",
                     "change_orders", "tm_log"]),
    "ic_meeting": ("Investment committee",
                   "Taking a deal to committee for approval",
                   ["ic_memo", "investor_pack", "appraisal", "financials", "market_intelligence",
                    "site_feasibility", "cap_table"]),
    "precon_gmp": ("Preconstruction / GMP handover",
                   "Fixing the price — what was assumed, decided and excluded",
                   ["estimate_continuity", "assumptions_register", "decision_log",
                    "precon_alignment", "cost", "site_feasibility"]),
    "design_issue": ("Design issue / model handover",
                     "Issuing a model or drawing set to the next party",
                     ["bep", "model_health", "bim_kpi", "lod", "naming", "design_standards",
                      "document_control", "spec_submittal_log"]),
    "closeout": ("Closeout & turnover",
                 "Handing the finished building to whoever operates it",
                 ["closeout", "verified_progress", "document_control", "quality", "lod",
                  "contracts", "action_tracker"]),
    "ownership_quarter": ("Ownership quarter",
                          "Reporting on a building you now operate rather than build",
                          ["rent_roll", "lease_management", "financials", "fca", "esg",
                           "resilience"]),
}


def package_params(moment_id: str) -> dict[str, Any]:
    """`report_package` params for a moment, or raise `KeyError` naming the ones that exist.

    Deliberately the same shape `packageJobParams` produces in the browser, so a scheduled package
    and a clicked one are the same job with the same artifact name.
    """
    row = MOMENTS.get(moment_id)
    if row is None:
        raise KeyError(f"unknown report moment {moment_id!r}; known: {sorted(MOMENTS)}")
    return {"moment_id": moment_id, "reports": list(row[2])}
