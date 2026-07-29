"""R22-CARBON-OPTION — the arithmetic, and the cases where the honest answer is no number.

The bug this module exists to prevent is not a wrong total, it is a MISSING figure rendered as a good
one. An option with no area and no building type has no embodied carbon; if that comes back as 0, or
as a mid-range placeholder, it wins the ranking and a scheme gets chosen on a number nobody computed.
So most of what is pinned here is the refusal, not the multiplication.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_option_carbon.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import option_carbon as oc  # noqa: E402
from aec_api import option_score

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def rec(name, **data):
    return {"id": name, "workflow_state": data.pop("state", "proposed"),
            "data": {"name": name, **data}}


# --- 1. the three bases, and that they are distinguishable ---------------------------------------------
d = oc.option_carbon(rec("Declared", embodied_kgco2e=1_000_000, gross_area_sf=50_000,
                         building_type="office"))
check("a declared figure is used as given", d["embodied_kgco2e"] == 1_000_000.0, d["embodied_kgco2e"])
check("  and is labelled 'declared', not silently blended with the benchmark",
      d["basis"] == oc.BASIS_DECLARED, d["basis"])

b = oc.option_carbon(rec("Benchmarked", gross_area_sf=50_000, building_type="office"))
area_m2 = 50_000 / option_score.M2_TO_SF
check("area x intensity is computed from the SHARED table, in m2",
      b["embodied_kgco2e"] == round(area_m2 * option_score.CARBON_KGCO2E_M2["office"], 1),
      b["embodied_kgco2e"])
check("  and is labelled 'benchmark' so it is never mistaken for a takeoff",
      b["basis"] == oc.BASIS_BENCHMARK)

# --- 2. the refusals — the reason this module exists ---------------------------------------------------
no_area = oc.option_carbon(rec("No area", building_type="office"))
check("an option with no area gets NO number, not zero", no_area["embodied_kgco2e"] is None,
      no_area["embodied_kgco2e"])
check("  and it says why", "no gross area" in (no_area["note"] or ""), no_area["note"])

unknown = oc.option_carbon(rec("Unknown type", gross_area_sf=50_000, building_type="pyramid"))
check("an unrecognised building type gets NO number rather than the mid-range placeholder",
      unknown["embodied_kgco2e"] is None, unknown["embodied_kgco2e"])
check("  even though option_score HAS such a placeholder for its own generated variants",
      oc.option_score._DEFAULT_CARBON == 450.0)
check("  and the reason names the type that failed", "pyramid" in (unknown["note"] or ""),
      unknown["note"])

no_type = oc.option_carbon(rec("No type", gross_area_sf=50_000))
check("area alone is not enough — an intensity needs a type", no_type["embodied_kgco2e"] is None)
check("  and that reason is different from the unknown-type one",
      no_type["note"] != unknown["note"])

# --- 3. bad data is absent, not favourable -------------------------------------------------------------
neg = oc.option_carbon(rec("Negative", gross_area_sf=50_000, building_type="office",
                           embodied_kgco2e=-5_000))
check("a negative carbon figure is treated as absent, not as the best option",
      neg["basis"] == oc.BASIS_BENCHMARK and neg["embodied_kgco2e"] > 0, neg["embodied_kgco2e"])
check("a non-numeric area does not crash and does not produce a figure",
      oc.option_carbon(rec("Junk", gross_area_sf="about 50k",
                           building_type="office"))["embodied_kgco2e"] is None)

# --- 4. intensity is what compares options of different SIZES ------------------------------------------
small = oc.option_carbon(rec("Small", gross_area_sf=40_000, building_type="hospital"))
big = oc.option_carbon(rec("Big", gross_area_sf=200_000, building_type="warehouse"))
check("the smaller scheme has the lower TOTAL carbon",
      small["embodied_kgco2e"] < big["embodied_kgco2e"])
check("  while being far worse per m2 — which is why intensity is reported too",
      small["kgco2e_per_m2"] > big["kgco2e_per_m2"],
      (small["kgco2e_per_m2"], big["kgco2e_per_m2"]))
check("intensity in kgCO2e/m2 recovers the table value for a benchmarked option",
      abs(small["kgco2e_per_m2"] - option_score.CARBON_KGCO2E_M2["hospital"]) < 0.5,
      small["kgco2e_per_m2"])
# The sf/m2 conversion is the classic silent 10.76x error: wrong by an order of magnitude, but a
# plausible-looking number either way.
check("the per-sf figure is the per-m2 one divided by M2_TO_SF, not equal to it",
      abs(small["kgco2e_per_sf"] - small["kgco2e_per_m2"] / option_score.M2_TO_SF) < 0.01,
      (small["kgco2e_per_sf"], small["kgco2e_per_m2"]))

# --- 5. the roll-up ranks what it can and names what it cannot ------------------------------------------
rows = [rec("A", gross_area_sf=50_000, building_type="office", state="selected"),
        rec("B", gross_area_sf=50_000, building_type="warehouse"),
        rec("C", gross_area_sf=50_000),                       # no type -> unavailable
        rec("D", embodied_kgco2e=1_000, gross_area_sf=50_000, building_type="office")]


class _FakeDB:
    pass


_orig_list, _orig_tables = oc.me.list_records, oc.me.TABLES
oc.me.list_records = lambda db, key, pid, limit=0: rows
oc.me.TABLES = {"design_option": object()}
try:
    r = oc.compare_carbon(_FakeDB(), "p1")
finally:
    oc.me.list_records, oc.me.TABLES = _orig_list, _orig_tables

check("every option appears, measured or not", r["count"] == 4, r["count"])
check("  three could be measured, one could not",
      (r["measured_count"], r["unavailable_count"]) == (3, 1),
      (r["measured_count"], r["unavailable_count"]))
check("the unmeasurable option is NOT ranked lowest — it is not ranked at all",
      r["lowest_total"] == "D", r["lowest_total"])
check("  and C is absent from the ranking entirely",
      "C" not in [o["name"] for o in r["options"] if o["embodied_kgco2e"] is not None])
check("a mixed declared/benchmark comparison is flagged as mixed", r["mixed_basis"] is True,
      r["basis_mix"])
check("  and the bases present are named", set(r["basis_mix"]) ==
      {oc.BASIS_DECLARED, oc.BASIS_BENCHMARK, oc.BASIS_UNAVAILABLE}, r["basis_mix"])
check("the delta vs the selected option is only computed where both figures exist",
      all("delta_vs_selected_kgco2e" in o for o in r["options"]
          if o["embodied_kgco2e"] is not None)
      and not any("delta_vs_selected_kgco2e" in o for o in r["options"]
                  if o["embodied_kgco2e"] is None))
check("with nothing measurable at all, the roll-up says so rather than returning an empty success",
      True)

oc.me.list_records = lambda db, key, pid, limit=0: [rec("Only", gross_area_sf=0)]
oc.me.TABLES = {"design_option": object()}
try:
    empty = oc.compare_carbon(_FakeDB(), "p1")
finally:
    oc.me.list_records, oc.me.TABLES = _orig_list, _orig_tables
check("  the message names what to record", empty["message"] is not None
      and "embodied_kgco2e" in empty["message"], empty["message"])
check("  and lowest_total is None rather than an arbitrary name", empty["lowest_total"] is None)

# --- 6. ONE table, not two ------------------------------------------------------------------------------
# Two tables encoding one set of intensities drift silently — both keep returning plausible numbers for
# the same building type that no longer agree. This asserts the module has no table of its own.
src = open("src/aec_api/option_carbon.py", encoding="utf-8").read()
check("option_carbon defines no carbon-intensity table of its own",
      "kgco2e_m2" not in src.lower().replace("carbon_kgco2e_m2", ""),
      "a local intensity table appears to have been added")
check("  it reads option_score's", "option_score.CARBON_KGCO2E_M2" in src)
check("  and every benchmarked type in the picker resolves through it",
      all(oc.option_carbon(rec("x", gross_area_sf=1000, building_type=t))["basis"]
          == oc.BASIS_BENCHMARK for t in option_score.CARBON_KGCO2E_M2),
      "a type in the shared table failed to benchmark")

print()
if FAILED:
    print(f"option_carbon: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("option_carbon: all checks passed")
