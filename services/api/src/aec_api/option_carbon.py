"""R22-CARBON-OPTION — embodied carbon on the design-option card, beside cost and area.

`option_score.py` already scores GENERATED massing variants on cost · carbon · yield · code, and
`option_takeoff.embodied()` computes carbon bottom-up from elemental quantities. Neither reaches the
**design_option records** a project actually keeps: `design_options.compare()` ranks options on area,
units, efficiency, cost/sf, EUI and IRR, and has no carbon at all. `energy_eui` is not a substitute —
it is OPERATIONAL energy, a different quantity with different units measuring a different lifecycle
stage, and treating it as the environmental column is how a scheme gets picked on the wrong number.

So this is the seam, not a new estimator: it turns whatever an option carries into a carbon figure and
**says which of three things that figure is**.

**Every row states its basis, and one of the bases is "no answer".**

- ``declared`` — the option carries `embodied_kgco2e` outright (from a real LCA, an EPD roll-up, or
  `option_takeoff.embodied()` upstream). Used as given; nothing here second-guesses a measured number.
- ``benchmark`` — `gross_area_sf` × a whole-building intensity for the building type. A defensible
  design-stage signal and **not** a computed quantity, so it is labelled on every row that uses it.
- ``unavailable`` — no declared figure and not enough to benchmark. Returns ``None`` with a reason.

That third case is the point of the module. An option with no area and no type is not an option with
zero carbon, and a comparison that silently ranks it best is worse than one that refuses: the missing
value gets chased, the confident wrong one gets presented to a client. The same rule the entitlement
expectation and the unit-rate memory had to be corrected for.

**The benchmark table is imported from `option_score`, never copied.** Two tables encoding one set of
intensities will drift, and the drift is invisible — both files keep returning plausible numbers, for
the same building type, that no longer agree. `option_score.CARBON_KGCO2E_M2` is the one table; if it
gains a building type, this module gains it in the same commit whether anyone remembers or not.

**Intensity is reported per m² GFA, in the unit the benchmark is defined in.** The option records area
in **square feet**, so the conversion happens here, once, against `option_score.M2_TO_SF` — the same
constant the scorer uses. A carbon intensity quoted in the wrong unit is out by 10.76×, which is large
enough to be caught and small enough to be believed.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me
from . import option_score

#: Bases in decreasing order of authority. A caller comparing options should treat a set of rows with
#: mixed bases as exactly that — mixed — and `basis_mix` in the roll-up says so explicitly.
BASIS_DECLARED = "declared"
BASIS_BENCHMARK = "benchmark"
BASIS_UNAVAILABLE = "unavailable"

_WHY = {
    BASIS_DECLARED: "an embodied-carbon figure recorded on the option itself",
    BASIS_BENCHMARK: ("gross area x a whole-building intensity for the building type — a design-stage "
                      "signal, not a takeoff"),
    BASIS_UNAVAILABLE: "not enough recorded to compute or to benchmark",
}


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        f = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    # A negative area or a negative mass of CO2e is a data-entry error, not a very good option. Treat
    # it as absent rather than letting it win every ranking.
    return f if f >= 0 else None


def _norm_type(v: Any) -> str:
    return "_".join(str(v or "").strip().lower().split())


def option_carbon(rec: dict[str, Any]) -> dict[str, Any]:
    """Embodied carbon for ONE design-option record, with the basis it rests on.

    Pure — takes the record, not a session, so the arithmetic is testable without a database.
    """
    d = rec.get("data") or rec
    name = d.get("name", "")
    area_sf = _num(d.get("gross_area_sf"))
    declared = _num(d.get("embodied_kgco2e"))
    btype = _norm_type(d.get("building_type"))
    area_m2 = area_sf / option_score.M2_TO_SF if area_sf else None

    row: dict[str, Any] = {
        "id": rec.get("id"), "name": name, "state": rec.get("workflow_state", ""),
        "gross_area_sf": area_sf, "building_type": btype or None,
    }

    if declared is not None:
        kg = declared
        basis, note = BASIS_DECLARED, None
    elif area_m2 and btype in option_score.CARBON_KGCO2E_M2:
        kg = round(area_m2 * option_score.CARBON_KGCO2E_M2[btype], 1)
        basis, note = BASIS_BENCHMARK, None
    elif area_m2:
        # Area but no recognised type. `option_score` has a `_DEFAULT_CARBON` placeholder for its own
        # generated variants; it is deliberately NOT used here. On a card a client reads, a mid-range
        # guess is indistinguishable from a benchmark and would be compared against real figures.
        kg, basis = None, BASIS_UNAVAILABLE
        note = (f"building type {d.get('building_type')!r} has no published intensity — set a known "
                f"type or record embodied_kgco2e directly"
                if btype else
                "no building type recorded, so no intensity applies — set one or record "
                "embodied_kgco2e directly")
    else:
        kg, basis = None, BASIS_UNAVAILABLE
        note = "no gross area recorded, so there is nothing to apply an intensity to"

    row.update({
        "embodied_kgco2e": kg,
        "embodied_tco2e": round(kg / 1000.0, 1) if kg is not None else None,
        # Intensity is the only figure that compares options of different SIZES. A 40,000 sf scheme
        # will always beat an 80,000 sf one on total carbon while being worse per unit of building.
        "kgco2e_per_m2": round(kg / area_m2, 1) if kg is not None and area_m2 else None,
        "kgco2e_per_sf": round(kg / area_sf, 2) if kg is not None and area_sf else None,
        "basis": basis, "basis_note": _WHY[basis], "note": note,
    })
    return row


def compare_carbon(db: Session, pid: str) -> dict[str, Any]:
    """Embodied carbon across a project's design options, ranked, with the unmeasured ones named."""
    rows = me.list_records(db, "design_option", pid, limit=100_000) \
        if "design_option" in me.TABLES else []
    opts = [option_carbon(r) for r in rows if (r.get("data") or r).get("name")]

    # A REJECTED scheme is listed but not ranked — the same separation this module already makes for
    # an unmeasured one, for a second reason. Without it the lowest-carbon headline can name a scheme
    # the team refused, which is worse here than elsewhere: carbon is the number an option gets
    # promoted on.
    from .design_options import DESIGN_OPTION_NOT_IN_CONTENTION
    contenders = [o for o in opts if o["state"] not in DESIGN_OPTION_NOT_IN_CONTENTION]
    measured = [o for o in contenders if o["embodied_kgco2e"] is not None]
    unavailable = [o for o in contenders if o["embodied_kgco2e"] is None]
    ranked = sorted(measured, key=lambda o: o["embodied_kgco2e"])
    by_intensity = [o for o in measured if o["kgco2e_per_m2"] is not None]
    by_intensity.sort(key=lambda o: o["kgco2e_per_m2"])

    mix = sorted({o["basis"] for o in opts})
    selected = next((o for o in opts if o["state"] == "selected"), None)

    # The delta that answers "what does switching cost us in carbon" — only ever between two figures
    # that exist, and only stated when the selected option HAS one.
    if selected and selected["embodied_kgco2e"] is not None:
        for o in measured:
            o["delta_vs_selected_kgco2e"] = round(
                o["embodied_kgco2e"] - selected["embodied_kgco2e"], 1)

    return {
        # `measured` and `unavailable` describe the RANKED population, so they sum to
        # `in_contention_count`, not to `count`. Returning that explicitly is the difference between
        # a reader who can account for every option and one who sees 1 + 0 against a count of 2 and
        # has to guess. See the note in `option_economics` — same shape, found the same way.
        "count": len(opts),
        "in_contention_count": len(contenders),
        "measured_count": len(measured),
        "unavailable_count": len(unavailable),
        "options": opts,
        "lowest_total": ranked[0]["name"] if ranked else None,
        "lowest_intensity": by_intensity[0]["name"] if by_intensity else None,
        "selected": selected["name"] if selected else None,
        "basis_mix": mix,
        # A comparison across mixed bases is a real comparison and a caveated one. Saying so is the
        # difference between a reader who knows to check and one who does not.
        "mixed_basis": len([b for b in mix if b != BASIS_UNAVAILABLE]) > 1,
        "basis_meanings": _WHY,
        "not_in_contention": [o["name"] for o in opts
                              if o["state"] in DESIGN_OPTION_NOT_IN_CONTENTION],
        "note": ("Options with no basis are listed and NOT ranked — an option that could not be "
                 "measured is not an option with zero carbon. A REJECTED option is listed and not "
                 "ranked for the other reason: it is not in contention. See `not_in_contention`."),
        "message": (None if measured else
                    "No option can be given an embodied-carbon figure yet. Record `embodied_kgco2e` "
                    "on an option, or give it a gross area and a known building type."),
    }
