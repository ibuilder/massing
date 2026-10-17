"""R22-OPTION-OBJECT — the option as one comparable record, and the axis it will not invent.

The ring's own sentence is the requirement: geometry + unit mix + cost + carbon + IRR as one record,
**so no massing is ever evaluated without its returns.** All four engines existed and nothing joined
them — three separate routes, so a reader reconciled them by eye, which is the failure the sentence
describes.

1. **a missing axis is `absent`, never zero.** This is the object-level form of a bug already fixed
   one layer down: `option_score` coerced a missing `cost_per_sf` to 0.0 and, on a lower-is-better
   axis, that scored **100** — the best possible mark, awarded for having no data;
2. **this does not rank.** `option_score` owns ranking and does it honestly; a second ordering here
   would be a rival answer to the same question;
3. **the twin**: an option with all five axes must actually come back `comparable`, or the record is
   only a machine for reporting gaps.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_option_object.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.option_object import AXES, STATUS_ABSENT, STATUS_PRESENT, join  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


GEO = {"options": [
    {"id": "a", "name": "Scheme A", "state": "draft", "gross_area_sf": 120000, "unit_count": 140},
    {"id": "b", "name": "Scheme B", "state": "draft", "gross_area_sf": 96000, "unit_count": 110},
    {"id": "c", "name": "Scheme C", "state": "draft", "gross_area_sf": 80000, "unit_count": 90},
]}
CAR = {"options": [
    {"id": "a", "basis": "declared", "kgco2e_per_m2": 420.0, "embodied_kgco2e": 4_684_000},
    {"id": "b", "basis": "benchmark", "kgco2e_per_m2": 380.0, "embodied_kgco2e": 3_389_000},
]}
# OPTION-DISAGREE. The three extra keys are the ones `compare_economics` really emits -- asserted
# against its source at the foot of this file, not remembered. `a` typed nothing; `b` typed 45.0
# against its own solved 16.4, which is the case `option_economics`'s header calls "the single most
# useful thing this module can surface"; `c` has no derived figure to disagree with.
ECO = {"options": [
    {"id": "a", "basis": "derived", "hard_cost": 48_000_000, "irr_pct": 18.1,
     "declared_irr_pct": None, "agrees_with_declared": None,
     "declared_vs_derived_irr_pct": None},
    {"id": "b", "basis": "derived", "hard_cost": 39_000_000, "irr_pct": 16.4,
     "declared_irr_pct": 45.0, "agrees_with_declared": False,
     "declared_vs_derived_irr_pct": 28.6},
    {"id": "c", "basis": "unlinked", "hard_cost": 33_000_000, "irr_pct": None,
     "declared_irr_pct": None, "agrees_with_declared": None,
     "declared_vs_derived_irr_pct": None},
]}

R = join(GEO, CAR, ECO)
by = {r["id"]: r for r in R["options"]}

# --- 3. THE TWIN — a complete option really is comparable ---------------------------------------------
check("all five axes are the ones the ring names",
      list(AXES) == ["geometry", "unit_mix", "cost", "carbon", "returns"], AXES)
check("AN OPTION WITH ALL FIVE AXES IS comparable", by["a"]["comparable"] is True, by["a"])
check("  with every axis marked present",
      set(by["a"]["axis_status"].values()) == {STATUS_PRESENT}, by["a"]["axis_status"])
check("  and the numbers come from the engines that own them",
      by["a"]["axes"]["carbon"] == 420.0 and by["a"]["axes"]["returns"] == 18.1, by["a"]["axes"])
check("two of three options are fully comparable", R["comparable_count"] == 2, R["comparable_count"])

# --- 1. A MISSING AXIS IS ABSENT, NEVER ZERO -----------------------------------------------------------
check("Scheme C is NOT comparable — it has no carbon and no returns",
      by["c"]["comparable"] is False, by["c"])
check("  the missing axes are NAMED", sorted(by["c"]["missing_axes"]) == ["carbon", "returns"],
      by["c"]["missing_axes"])
check("  and they are ABSENT, not 0.0 — the distinction the scorer bug turned on",
      by["c"]["axes"]["carbon"] is None and by["c"]["axes"]["returns"] is None, by["c"]["axes"])
check("  status says absent rather than reporting a value",
      by["c"]["axis_status"]["carbon"] == STATUS_ABSENT, by["c"]["axis_status"])
check("  with a note naming the failure mode it prevents",
      "look like a good one" in by["c"]["note"], by["c"]["note"])
check("  the axes it DOES have are still reported — absence is per-axis, not per-option",
      by["c"]["axes"]["geometry"] == 80000 and by["c"]["axes"]["cost"] == 33_000_000, by["c"]["axes"])
check("the incomparable option is listed for the caller, not silently dropped",
      [x["id"] for x in R["incomparable"]] == ["c"], R["incomparable"])

# --- 2. IT DOES NOT RANK --------------------------------------------------------------------------------
check("NO ranking, score or ordering field is emitted",
      not any(k for k in R if k.lower() in ("rank", "ranked", "score", "scores", "recommended", "best")),
      sorted(R))
check("  option order is input order, not a computed ordering",
      [r["id"] for r in R["options"]] == ["a", "b", "c"], [r["id"] for r in R["options"]])
check("  and the note says why two orderings would be worse than none",
      "worse than no ranking is two" in R["note"], R["note"])

# --- an option present in only ONE engine still appears ------------------------------------------------
only_eco = join({"options": []}, None, {"options": [{"id": "z", "hard_cost": 1}]})
check("an option known to only one engine is still listed, incomparable",
      only_eco["option_count"] == 1 and only_eco["options"][0]["comparable"] is False,
      only_eco["options"])
check("  missing FOUR axes, all named",
      len(only_eco["options"][0]["missing_axes"]) == 4, only_eco["options"][0]["missing_axes"])
check("all engines absent is an empty record, not a crash",
      join(None, None, None)["option_count"] == 0)
check("a zero value is DATA, not absence — 0 carbon is a claim, missing carbon is not",
      join({"options": [{"id": "q", "gross_area_sf": 1, "unit_count": 1}]},
           {"options": [{"id": "q", "kgco2e_per_m2": 0}]},
           {"options": [{"id": "q", "hard_cost": 0, "irr_pct": 0}]}
           )["options"][0]["comparable"] is True)

# --- THE KEY NAMES ARE THE JOIN — and they were wrong ---------------------------------------------
# The first version of `join()` read `total_cost`, `equity_irr` and `carbon_intensity_kgco2e_m2`.
# None of the three is emitted by any engine. Against a real project it returned all five axes
# absent — and every check above still passed, because the fixture was invented next to the code it
# was meant to test. A join's correctness lives entirely in whether both sides use the same names,
# so the names are asserted against the engines' own source rather than against my memory of it.
import pathlib  # noqa: E402

_SRC = pathlib.Path("src/aec_api")
for _mod, _keys in (("design_options.py", ("gross_area_sf", "unit_count", "hard_cost")),
                    ("option_carbon.py", ("kgco2e_per_m2", "embodied_kgco2e", "basis")),
                    ("option_economics.py", ("hard_cost", "irr_pct", "basis",
                                             "declared_irr_pct", "agrees_with_declared",
                                             "declared_vs_derived_irr_pct"))):
    _text = _SRC.joinpath(_mod).read_text(encoding="utf-8")
    for _k in _keys:
        check(f"{_mod} really emits {_k!r} — the key the join reads", f'"{_k}"' in _text,
              f"not found in {_mod}")

check("the basis each engine assigned survives the join — a benchmarked figure is not "
      "silently equal to a measured one",
      by["a"]["carbon_basis"] == "declared" and by["b"]["carbon_basis"] == "benchmark",
      (by["a"]["carbon_basis"], by["b"]["carbon_basis"]))
check("  and an unlinked economics row keeps saying so beside its absent return",
      by["c"]["economics_basis"] == "unlinked" and by["c"]["axes"]["returns"] is None,
      (by["c"]["economics_basis"], by["c"]["axes"]))

# ---- OPTION-DISAGREE -----------------------------------------------------------------------
# The basis above survived the join because dropping it "would turn a benchmarked carbon figure and
# a measured one into the same number". The STRONGER version of that concern did not: a scheme
# typing 45.0% against its own solved 16.4% arrived identical to one that typed nothing -- same
# `returns`, same `economics_basis: derived`. A basis says HOW the number was got; it cannot say
# somebody is quoting a different one.
check("the typed figure survives the join beside the solved one",
      by["b"]["declared_returns"] == 45.0 and by["b"]["axes"]["returns"] == 16.4,
      (by["b"]["declared_returns"], by["b"]["axes"]["returns"]))
check("  and the disagreement is carried as a flag, not left to be re-derived",
      by["b"]["returns_agree"] is False and by["b"]["returns_delta_pct"] == 28.6,
      (by["b"]["returns_agree"], by["b"]["returns_delta_pct"]))
check("  so the two rows that used to render identically no longer do",
      (by["a"]["axes"]["returns"], by["a"]["economics_basis"], by["a"]["returns_agree"])
      != (by["b"]["axes"]["returns"], by["b"]["economics_basis"], by["b"]["returns_agree"]))
check("an option that typed NOTHING reads `None`, never False -- there is no disagreement to claim",
      by["a"]["returns_agree"] is None and by["a"]["declared_returns"] is None, by["a"])
check("  and neither does one with no derived figure to disagree with",
      by["c"]["returns_agree"] is None, by["c"])
check("the set-level list names exactly the disagreeing option",
      [x["name"] for x in R["declared_disagrees"]] == ["Scheme B"], R["declared_disagrees"])
check("  with both figures and the delta, so a reader needs no second call",
      R["declared_disagrees"][0]["declared_returns"] == 45.0
      and R["declared_disagrees"][0]["derived_returns"] == 16.4
      and R["declared_disagrees"][0]["delta_pct"] == 28.6, R["declared_disagrees"])
check("  and the count agrees with the list, because it is DERIVED from the same rows",
      R["declared_disagrees_count"] == len(R["declared_disagrees"]) == 1,
      (R["declared_disagrees_count"], R["declared_disagrees"]))
check("the response says what `returns` is and what the typed figure is for",
      "never promoted or overwritten" in R["returns_basis_note"], R["returns_basis_note"])

# A join with no economics payload at all must not invent a disagreement -- the same refusal the
# absent-axis rule makes one level up.
_bare = join(GEO, None, None)
check("no economics payload -> no disagreement claimed anywhere",
      _bare["declared_disagrees_count"] == 0
      and all(r["returns_agree"] is None and r["declared_returns"] is None
              for r in _bare["options"]), _bare["declared_disagrees"])

print()
if FAILED:
    print(f"option_object: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("option_object: all checks passed — including OPTION-DISAGREE: the typed IRR and the "
      "disagreement flag survive the join, an option that typed nothing reads None rather than "
      "False, the set-level list is derived from the same rows as the flags, and a join with no "
      "economics payload claims no disagreement")
