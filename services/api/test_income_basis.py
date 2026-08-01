"""PF-INCOME-BASIS — the proforma's income says where it came from.

The load-bearing assertions are the refusals. A proforma that answers with a typed figure while a
contradicting rent roll sits one table away is not missing a number — it is reporting a number whose
provenance nobody can see, which is the shape this repo keeps finding.

1. an empty rent roll is UNAVAILABLE, never 0.0 — every sum over no leases is legitimately zero, so
   the arithmetic succeeds and a deal underwrites zero income as though it had been measured;
2. recoveries are never netted into base rent — once netted, the reimbursement is unrecoverable;
3. declared and derived BOTH survive, with the gap between them;
4. leases the maths cannot use are NAMED, not counted.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_income_basis.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.proforma.income_basis import (  # noqa: E402
    BASIS_BOTH,
    BASIS_DECLARED,
    BASIS_RENT_ROLL,
    BASIS_UNAVAILABLE,
    MATERIAL_DISAGREEMENT_PCT,
    from_rent_roll,
    resolve,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# Shape copied from `rentroll.summarize()`'s actual return, not invented.
RR = {"as_of": "2026-08-01", "lease_count": 3, "total_rentable_sf": 50000, "occupied_sf": 40000,
      "vacant_sf": 10000, "occupancy_pct": 80.0, "base_rent_annual": 1_000_000.0,
      "recoveries_annual": 200_000.0, "in_place_gross_income": 1_200_000.0,
      "avg_rent_psf": 25.0, "walt_years": 4.2, "expirations_by_year": {}, "rows": []}

# Shape from `net_effective.roll_up()`.
NER = {"lease_count": 3, "skipped_count": 1,
       "skipped": [{"tenant": "Acme", "suite": "300", "reason": "no end_date"}],
       "face_gpr_annual": 1_000_000.0, "ner_gpr_annual_discounted": 900_000.0}

# --- 1. the ordinary derivation ---------------------------------------------------------------------
d = from_rent_roll(RR)
check("a rent roll yields usable income", d["available"] is True, d)
check("  base rent is carried through", d["base_rent_annual"] == 1_000_000.0, d["base_rent_annual"])
check("  RECOVERIES ARE A SEPARATE LINE, never folded into base rent",
      d["recovery_income_annual"] == 200_000.0 and d["base_rent_annual"] == 1_000_000.0, d)
check("  potential rent is their sum, and the components remain recoverable from the payload",
      d["potential_rent_annual"] == 1_200_000.0, d["potential_rent_annual"])
check("  occupancy and WALT travel with it", d["occupancy_pct"] == 80.0 and d["walt_years"] == 4.2, d)

# --- 2. THE ZERO TRAP: an empty rent roll is not an income of zero -------------------------------------
empty = {**RR, "lease_count": 0, "base_rent_annual": 0.0, "recoveries_annual": 0.0}
e = from_rent_roll(empty)
check("an empty rent roll is UNAVAILABLE, not an income of 0.0",
      e["available"] is False, e)
check("  and it says why, in terms of the distinction that matters",
      "not zero" in e["reason"].lower(), e["reason"])
check("no rent roll at all is also unavailable rather than zero",
      from_rent_roll(None)["available"] is False)
check("a rent roll with leases but no usable rent is unavailable",
      from_rent_roll({**RR, "base_rent_annual": None})["available"] is False)

# --- 3. concessions are reported, not absorbed ----------------------------------------------------------
c = from_rent_roll(RR, NER)
check("face and net effective GPR are BOTH reported",
      c["face_gpr_annual"] == 1_000_000.0 and c["net_effective_gpr_annual"] == 900_000.0, c)
check("  with the concession load between them", c["concession_load_annual"] == 100_000.0,
      c["concession_load_annual"])
check("  as a percentage an underwriter can act on", c["concession_load_pct"] == 10.0,
      c["concession_load_pct"])
check("leases the maths could not use are NAMED, not counted",
      c["leases_not_computable"][0]["tenant"] == "Acme"
      and c["leases_not_computable"][0]["reason"] == "no end_date", c.get("leases_not_computable"))

# --- 4. resolve(): the basis is always stated -------------------------------------------------------------
only_dec = resolve(declared_annual=900_000.0)
check("a declared figure with no rent roll is `declared`", only_dec["basis"] == BASIS_DECLARED,
      only_dec["basis"])
check("  and it records WHY nothing was derived",
      "no rent roll" in (only_dec.get("derived_unavailable_reason") or ""), only_dec)

only_rr = resolve(rent_roll=RR)
check("a rent roll with no declared figure is `rent_roll`", only_rr["basis"] == BASIS_RENT_ROLL)
check("  and uses the derived number", only_rr["potential_rent_annual"] == 1_200_000.0)

neither = resolve()
check("neither source is UNAVAILABLE, and the income is None — not 0.0",
      neither["basis"] == BASIS_UNAVAILABLE and neither["potential_rent_annual"] is None, neither)
check("  every basis is documented in the payload it appears in",
      "not the same as zero" in neither["basis_meaning"], neither["basis_meaning"])

# --- 5. THE DISAGREEMENT — the reason both are kept ----------------------------------------------------------
both = resolve(declared_annual=1_000_000.0, rent_roll=RR)
check("with both sources the basis says so", both["basis"] == BASIS_BOTH, both["basis"])
check("  the rent roll wins — it is the asset's own record",
      both["potential_rent_annual"] == 1_200_000.0, both["potential_rent_annual"])
check("  the declared figure SURVIVES rather than being overwritten",
      both["declared_annual"] == 1_000_000.0, both["declared_annual"])
dv = both["declared_vs_derived"]
check("  the gap is reported in currency", dv["difference"] == 200_000.0, dv)
check("  and as a percentage", dv["difference_pct"] == 20.0, dv)
check("  a 20% gap is flagged MATERIAL", dv["material"] is True, dv)
check("  and the threshold that produced the flag is stated, so the rule can be argued with",
      dv["threshold_pct"] == MATERIAL_DISAGREEMENT_PCT, dv)

close = resolve(declared_annual=1_190_000.0, rent_roll=RR)
check("a sub-threshold gap is reported but NOT flagged material — drafting noise is not a finding",
      close["declared_vs_derived"]["material"] is False
      and close["declared_vs_derived"]["difference"] == 10_000.0,
      close["declared_vs_derived"])

# --- 6. junk in the declared figure is refused, never coerced -------------------------------------------------
for bad, why in ((True, "JSON true is not an income of 1"),
                 ("lots", "a word is not an income"),
                 (float("inf"), "infinite income is not a measurement"),
                 (float("nan"), "NaN is not a measurement")):
    r = resolve(declared_annual=bad, rent_roll=RR)
    check(f"declared={bad!r} is ignored as a figure — {why}",
          r["basis"] == BASIS_RENT_ROLL and r["declared_annual"] is None, (r["basis"], r.get("declared_annual")))
    r2 = resolve(declared_annual=bad)
    check(f"  and with no rent roll either, {bad!r} is UNAVAILABLE, not accepted",
          r2["basis"] == BASIS_UNAVAILABLE, r2["basis"])

check("a zero declared figure is a real statement and is kept",
      resolve(declared_annual=0.0)["basis"] == BASIS_DECLARED)

print()
if FAILED:
    print(f"income_basis: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("income_basis: all checks passed")
