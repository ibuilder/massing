"""FIN-TEST: the lease-management money math (rent escalation compounding, CAM/expense recovery, renewal
at-risk rent) — pure read-side aggregation, so a compounding/rounding/recovery bug would be silent and
consequential. Hand-computed expectations. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_leasemgmt.py"""
import os
import sys
from datetime import date, timedelta

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import leasemgmt as L  # noqa: E402


def lease(**k):
    """A flat lease record (leasemgmt._d returns the dict itself when there's no 'data' wrapper)."""
    return k


# --- escalation_schedule: base·(1+esc)^y compounding, portfolio per year ------------------------------
leases = [
    lease(ref="L1", tenant="Acme", workflow_state="active", base_rent_annual=100000, escalation_pct=3.0),
    lease(ref="L2", tenant="Beta", workflow_state="active", base_rent_annual=50000, escalation_pct=0.0),
    lease(ref="L3", tenant="Draft", workflow_state="draft", base_rent_annual=999999, escalation_pct=5.0),
]
esc = L.escalation_schedule(leases, years=5)
assert esc["years"] == 5
# L1 compounded at 3%: 1.03^5 = 1.1592740743 → 115927.41; L2 flat 50000; L3 (draft) excluded
l1 = next(r for r in esc["rows"] if r["ref"] == "L1")
assert l1["projected"] == [100000.0, 103000.0, 106090.0, 109272.7, 112550.88, 115927.41], l1["projected"]
assert len(esc["rows"]) == 2, "draft lease excluded from the active projection"
assert esc["current_base_rent"] == 150000.0, esc["current_base_rent"]          # year 0: 100000 + 50000
assert esc["projected_base_rent"] == round(115927.41 + 50000, 2), esc["projected_base_rent"]  # year 5
assert esc["portfolio_by_year"][0] == 150000.0 and esc["portfolio_by_year"][5] == 165927.41, esc["portfolio_by_year"]

# --- cam_reconciliation: recovery_psf × rentable_sf, ratio + over/under recovery ----------------------
cam_leases = [
    lease(ref="C1", tenant="NNN-tenant", workflow_state="active", lease_type="NNN",
          rentable_sf=10000, recovery_psf=12.0),
    lease(ref="C2", tenant="Gross-tenant", workflow_state="active", lease_type="Gross",   # not a recovery type
          rentable_sf=8000, recovery_psf=15.0),
    lease(ref="C3", tenant="ModGross", workflow_state="active", lease_type="Modified Gross",
          rentable_sf=5000, recovery_psf=8.0),
    lease(ref="C4", tenant="ExpiredNNN", workflow_state="expired", lease_type="NNN",       # not active
          rentable_sf=9000, recovery_psf=20.0),
]
cam = L.cam_reconciliation(cam_leases)
# recoverable = psf×sf: C1 120000, C3 40000; C2 (Gross) + C4 (expired) excluded
assert cam["recoverable_income"] == 160000.0, cam["recoverable_income"]
assert cam["recoverable_sf"] == 15000.0, cam["recoverable_sf"]
assert cam["by_lease_type"] == {"NNN": 120000.0, "Modified Gross": 40000.0}, cam["by_lease_type"]

# under-recovery (opex pool bigger than billed → leakage)
under = L.cam_reconciliation(cam_leases, recoverable_opex=200000)
assert under["recovery_ratio"] == 0.8 and under["under_recovery"] == 40000.0 and under["over_recovery"] == 0.0, under
# over-recovery (billed more than the pool)
over = L.cam_reconciliation(cam_leases, recoverable_opex=140000)
assert over["over_recovery"] == 20000.0 and over["under_recovery"] == 0.0, over
assert over["recovery_ratio"] == round(160000 / 140000, 3), over["recovery_ratio"]
# a zero opex pool must not divide-by-zero
assert L.cam_reconciliation(cam_leases, recoverable_opex=0)["recovery_ratio"] is None

# --- renewal_pipeline: expiry bucketing + at-risk rent (as-of fixed for determinism) ------------------
today = date(2026, 7, 17)
ren_leases = [
    lease(ref="R1", tenant="Soon", workflow_state="active", base_rent_annual=60000,
          end_date=str(today + timedelta(days=60)), renewal_options="1×5yr"),        # <=90d + at-risk + option
    lease(ref="R2", tenant="Mid", workflow_state="active", base_rent_annual=80000,
          end_date=str(today + timedelta(days=200))),                                # <=365d + at-risk
    lease(ref="R3", tenant="Holdover", workflow_state="holdover", base_rent_annual=40000),   # holdover + at-risk
    lease(ref="R4", tenant="Far", workflow_state="active", base_rent_annual=90000,
          end_date=str(today + timedelta(days=500))),                                # >365d → not at risk
    lease(ref="R5", tenant="Done", workflow_state="expired", base_rent_annual=30000),        # expired
]
ren = L.renewal_pipeline(ren_leases, as_of=today)
assert ren["expiring"]["<=90d"] == {"count": 1, "rent": 60000.0}, ren["expiring"]
assert ren["expiring"]["<=365d"] == {"count": 1, "rent": 80000.0}, ren["expiring"]
assert ren["holdover_count"] == 1 and ren["expired_count"] == 1, ren
assert ren["options_outstanding"] == 1, ren
# at-risk = holdover (40000) + expiring ≤365d (60000 + 80000) = 180000; the 500-day and expired leases excluded
assert ren["at_risk_rent"] == 180000.0, ren["at_risk_rent"]
assert {r["ref"] for r in ren["rows"]} == {"R1", "R2", "R3", "R5"}, [r["ref"] for r in ren["rows"]]

# --- robustness: empty + malformed inputs don't crash -------------------------------------------------
assert L.escalation_schedule([])["portfolio_by_year"][0] == 0.0
assert L.cam_reconciliation([])["recoverable_income"] == 0.0
assert L.renewal_pipeline([])["at_risk_rent"] == 0.0
bad = [lease(workflow_state="active", base_rent_annual="not-a-number", escalation_pct="x", end_date="bogus")]
assert L.escalation_schedule(bad)["current_base_rent"] == 0.0, "non-numeric rent coerces to 0, no crash"
assert L.renewal_pipeline(bad, as_of=today)["at_risk_rent"] == 0.0, "unparseable end_date → not bucketed"

print("LEASEMGMT OK - escalation compounds base·(1+esc)^y (L1 @3% → 115,927.41 at year 5), portfolio per "
      "year sums active leases (draft excluded); CAM recovery = psf×sf over recovery-type active leases "
      "(NNN 120k + ModGross 40k = 160k), recovery ratio + over/under-recovery vs the opex pool (0.8 → 40k "
      "leakage; 140k pool → 20k over), zero pool → ratio None; renewal buckets by days-to-expiry with "
      "at-risk rent = holdover + expiring≤365 (180k), options counted; empty/malformed inputs never crash.")
