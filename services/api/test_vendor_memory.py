"""R22-PROCURE-DEPTH ③ — a trade partner's record across projects, and the two things it refuses.

The refusals are the substance:

1. a vendor with NO history is `no_history`, never `clear` — an unknown sub that renders as a clean
   record is the prequalification equivalent of "0 open NCRs" on a building nobody inspected;
2. quality and schedule performance are NOT attributable — `ncr` and `inspection` carry no vendor
   field — so a clean scorecard here is silence on that subject, not a pass.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_vendor_memory.py
"""
import sys
from datetime import date

sys.path.insert(0, "src")

from aec_api import vendor_memory as vm  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


TODAY = date(2026, 6, 1)


def entry(name, projects=("p1",), **records):
    recs = {k: list(records.get(k, [])) for k in vm.VENDOR_MODULES}
    return {"vendor": name, "projects": set(projects), "records": recs}


# --- 1. commercial history rolls up across projects -----------------------------------------------------
e = entry("Ace Concrete", projects=("p1", "p2"),
          subcontract=[{"value": 500_000, "trade": "Concrete"},
                       {"value": 300_000, "trade": "Concrete"}],
          sub_invoice=[{"amount": 400_000}], lien_waiver=[{"amount": 400_000}],
          coi=[{"expires": "2027-01-01"}])
r = vm.vendor_record(e, TODAY)
check("subcontract value sums across projects", r["subcontract_value"] == 800_000.0,
      r["subcontract_value"])
check("  and the project count is what makes it a RECORD rather than a row",
      r["project_count"] == 2, r["project_count"])
check("  trades are collected", r["trades"] == ["Concrete"], r["trades"])
check("a fully-waived, insured vendor is CLEAR", r["verdict"] == vm.VERDICT_CLEAR,
      (r["verdict"], r["flags"]))

# --- 2. THE REFUSAL: no history is not a good record ------------------------------------------------------
none = vm.vendor_record(entry("Never Worked Here"), TODAY)
check("a vendor with no records is NO_HISTORY, not clear",
      none["verdict"] == vm.VERDICT_NO_HISTORY, none["verdict"])
check("  and its note says 'an unknown, NOT a clean record'",
      "NOT a clean record" in none["verdict_note"], none["verdict_note"])
check("  no_history and clear are distinct verdicts and must never collapse",
      vm.VERDICT_NO_HISTORY != vm.VERDICT_CLEAR)
check("  it carries no invented figures", none["subcontract_value"] == 0.0 and none["flags"] == [])

# --- 3. lapsed and UNKNOWN insurance are different, and neither reads as cover -----------------------------
lapsed = vm.vendor_record(entry("Lapsed Co", coi=[{"expires": "2025-01-01"}]), TODAY)
check("an expired certificate is flagged", lapsed["coi_expired"] == 1, lapsed["coi_expired"])
check("  and puts the vendor on WATCH", lapsed["verdict"] == vm.VERDICT_WATCH, lapsed["verdict"])
blank = vm.vendor_record(entry("No Date Co", coi=[{"carrier": "X"}]), TODAY)
check("a certificate with NO expiry is not treated as cover",
      blank["coi_missing_expiry"] == 1 and blank["verdict"] == vm.VERDICT_WATCH,
      (blank["coi_missing_expiry"], blank["verdict"]))
check("  and it is counted separately from an expired one — unknown is not lapsed",
      blank["coi_expired"] == 0, blank["coi_expired"])
check("  the flag says cover is unknown rather than missing",
      any("unknown" in f for f in blank["flags"]), blank["flags"])

# --- 4. billing beyond the lien waivers on file is an exposure --------------------------------------------
exposed = vm.vendor_record(entry("Billed More", sub_invoice=[{"amount": 500_000}],
                                 lien_waiver=[{"amount": 200_000}],
                                 coi=[{"expires": "2027-01-01"}]), TODAY)
check("invoicing beyond the waivers on file is flagged",
      any("beyond the lien waivers" in f for f in exposed["flags"]), exposed["flags"])
check("  with the amount, not just the fact", any("300000" in f for f in exposed["flags"]),
      exposed["flags"])
check("a vendor who has not billed at all is not flagged for unwaived billing",
      not any("lien waiver" in f for f in
              vm.vendor_record(entry("No Billing", subcontract=[{"value": 100}],
                                     coi=[{"expires": "2027-01-01"}]), TODAY)["flags"]))

# --- 5. malformed money and dates are absent, not favourable ----------------------------------------------
junk = vm.vendor_record(entry("Junk", subcontract=[{"value": "about $500k"}],
                              coi=[{"expires": "not a date"}]), TODAY)
check("a non-numeric value does not crash and contributes nothing",
      junk["subcontract_value"] == 0.0, junk["subcontract_value"])
check("  an unparseable expiry counts as UNKNOWN cover, not as valid cover",
      junk["coi_missing_expiry"] == 1 and junk["verdict"] == vm.VERDICT_WATCH,
      (junk["coi_missing_expiry"], junk["verdict"]))
check("currency formatting is parsed where it is real",
      vm.vendor_record(entry("Fmt", subcontract=[{"value": "$1,250,000"}]),
                       TODAY)["subcontract_value"] == 1_250_000.0)


# --- 6. the roll-up, and the stated limit ------------------------------------------------------------------
class _FakeDB:
    def execute(self, stmt):
        raise AssertionError("gather() should read through the patched _rows")


ROWS = {
    "subcontract": [("p1", {"vendor": "Ace Concrete", "value": 500_000, "trade": "Concrete"}),
                    ("p2", {"vendor": "ace concrete", "value": 300_000, "trade": "Concrete"}),
                    ("p1", {"vendor": "Solo Steel", "value": 90_000, "trade": "Steel"})],
    "coi": [("p1", {"vendor": "Solo Steel", "expires": "2025-01-01"})],
}
_orig = vm._rows
vm._rows = lambda db, key, pids: ROWS.get(key, [])
try:
    R = vm.vendor_memory(_FakeDB(), project_ids=None, today=TODAY)
finally:
    vm._rows = _orig

names = [v["vendor"] for v in R["vendors"]]
check("vendors are bucketed case-insensitively — one partner, not two",
      names == ["Ace Concrete", "Solo Steel"], names)
check("  the repeat partner's two projects are recognised",
      R["vendors"][0]["project_count"] == 2 and R["repeat_vendors"] == 1,
      (R["vendors"][0]["project_count"], R["repeat_vendors"]))
check("  and its value spans both", R["vendors"][0]["subcontract_value"] == 800_000.0)
check("the vendor with a lapsed COI is on watch and counted",
      R["watch_count"] == 1 and R["vendors"][1]["verdict"] == vm.VERDICT_WATCH,
      (R["watch_count"], R["vendors"][1]["verdict"]))
check("the roll-up STATES what it cannot attribute",
      set(R["attributable"]["not_from"]) == {"ncr", "inspection"}, R["attributable"])
check("  and says a clean record here is silence on quality, not a pass",
      "silence on the subject" in R["attributable"]["note"], R["attributable"]["note"])
check("  the six attributable registers are named",
      set(R["attributable"]["from"]) == set(vm.VENDOR_MODULES), R["attributable"]["from"])

# The limit is a FACT about the schema, so assert it against the schema rather than trusting the prose.
import json  # noqa: E402
import os  # noqa: E402

for k in vm.NOT_ATTRIBUTABLE:
    fields = [f["name"] for f in json.load(open(os.path.join("modules", k, "module.json"),
                                                encoding="utf-8"))["fields"]]
    check(f"{k} genuinely carries no vendor field (so the stated limit is true)",
          not any("vendor" in f for f in fields), fields)
for k in vm.VENDOR_MODULES:
    fields = [f["name"] for f in json.load(open(os.path.join("modules", k, "module.json"),
                                                encoding="utf-8"))["fields"]]
    check(f"{k} does carry a vendor field (so it is attributable)", "vendor" in fields, fields)

vm._rows = lambda db, key, pids: []
try:
    empty = vm.vendor_memory(_FakeDB(), project_ids=None, today=TODAY)
finally:
    vm._rows = _orig
check("with no vendors at all it says so rather than returning an empty success",
      empty["vendor_count"] == 0 and empty["message"] is not None, empty["message"])

print()
if FAILED:
    print(f"vendor_memory: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("vendor_memory: all checks passed")
