"""R25-QTO-WIRE — the estimate measures the MODEL, not the caller.

`fived.estimate` took its quantities from whatever the caller passed in. Every rule, every rate and
every roll-up could be right while the numbers described a different building — an estimate that is
internally consistent and externally wrong, which is the worst kind because nothing in it looks off.

The wire is `qto.measure()`: every element's quantities keyed by GlobalId, straight from the model.
That alone is not the interesting part. The interesting part is that quantities arrive with different
**provenance**, and an estimate that cannot say which it rests on cannot be checked:

* **declared** — the model's own `IfcElementQuantity`. Somebody's authoring tool asserted this wall
  is 12.4 m².
* **computed** — we meshed the solid and measured it here. Our approximation of the same thing.
* **override** — the caller supplied it, replacing the model's number.
* **unknown** — quantities arrived with no provenance at all.

They are usually close. They are not the same claim, and the difference is exactly what an estimator
wants to know before signing.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_qto_wire.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_qto_wire.db"
os.environ["STORAGE_DIR"] = "./test_storage_qto_wire"
if os.path.exists("./test_qto_wire.db"):
    os.remove("./test_qto_wire.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import fived  # noqa: E402

IDX = {
    "g-wall-1": {"ifc_class": "IfcWall", "name": "W1", "storey": "L1"},
    "g-wall-2": {"ifc_class": "IfcWall", "name": "W2", "storey": "L1"},
    "g-slab-1": {"ifc_class": "IfcSlab", "name": "S1", "storey": "L1"},
}
RULES = [
    {"selector": "class=IfcWall", "code": "09 21 16", "description": "Partitions",
     "basis": "area", "unit_cost": 90.0},
    {"selector": "class=IfcSlab", "code": "03 30 00", "description": "Slab on grade",
     "basis": "volume", "unit_cost": 220.0},
]

# ---- a line says how its quantity was obtained ----------------------------------------------------
qty = {"g-wall-1": {"area": 10.0}, "g-wall-2": {"area": 20.0}, "g-slab-1": {"volume": 4.0}}
src = {"g-wall-1": {"area": "declared"}, "g-wall-2": {"area": "declared"},
       "g-slab-1": {"volume": "computed"}}
est = fived.estimate(IDX, RULES, qty, sources=src)
by_code = {ln["code"]: ln for ln in est["lines"]}
assert by_code["09 21 16"]["quantity_source"] == "declared", by_code["09 21 16"]
assert by_code["03 30 00"]["quantity_source"] == "computed", by_code["03 30 00"]
assert by_code["09 21 16"]["quantity"] == 30.0
assert est["computed_quantity_lines"] == 1, est
assert est["computed_quantity_amount"] == by_code["03 30 00"]["amount"], est

# ---- ONE measured element in a line makes the whole line `mixed` -----------------------------------
# Rounding a part-measured line to "declared" is the small lie an estimate cannot afford: the reader
# would believe the model asserted a number that we, in part, made up.
src_mixed = {"g-wall-1": {"area": "declared"}, "g-wall-2": {"area": "computed"},
             "g-slab-1": {"volume": "declared"}}
mixed = fived.estimate(IDX, RULES, qty, sources=src_mixed)
walls = next(ln for ln in mixed["lines"] if ln["code"] == "09 21 16")
assert walls["quantity_source"] == "mixed", walls
assert mixed["computed_quantity_lines"] == 1, mixed          # `mixed` counts as not-declared

# ---- an ABSENT provenance is `unknown`, never `declared` -------------------------------------------
# A caller who sends quantities with no provenance has said nothing about where they came from.
# Answering "the model declared these" on their behalf is the exact overclaim this field prevents.
bare = fived.estimate(IDX, RULES, qty)                        # no sources at all
for ln in bare["lines"]:
    assert ln["quantity_source"] == "unknown", ln
assert bare["computed_quantity_lines"] == len(bare["lines"]), bare

# an override is its own answer too — neither the model's nor our measurement
over = fived.estimate(IDX, RULES, qty, sources={**src, "g-wall-1": {"area": "override"}})
w = next(ln for ln in over["lines"] if ln["code"] == "09 21 16")
assert w["quantity_source"] == "mixed", w

# ---- the totals are unchanged by provenance -------------------------------------------------------
# Provenance annotates; it must not move a number. If labelling a quantity changed the estimate, the
# label would be doing arithmetic instead of reporting.
assert est["total"] == bare["total"] == mixed["total"], (est["total"], bare["total"], mixed["total"])
assert est["total"] == round(30.0 * 90.0 + 4.0 * 220.0, 2), est["total"]

# ---- and the pre-existing guarantees still hold ---------------------------------------------------
# An element with no quantity for its basis is REPORTED, not billed as zero.
short = fived.estimate(IDX, RULES, {"g-wall-1": {"area": 10.0}}, sources=src)
assert short["missing_quantity_count"] == 2, short["missing_quantity"]
assert not short["complete"], short
assert short["total"] == round(10.0 * 90.0, 2)

# ---- R25-COST-VINTAGE: the RATE says where it came from too ----------------------------------------
# An estimate is a rate times a quantity. v0.3.697 made the quantity say what it rests on; a line that
# can answer for one half and not the other is only half checkable.
V_RULES = [
    {"selector": "class=IfcWall", "code": "09 21 16", "basis": "area", "rate_from": "vintage"},
    {"selector": "class=IfcSlab", "code": "03 30 00", "basis": "volume", "unit_cost": 220.0},
]
V_RATES = {"IfcWall": 75.0}                       # the vintage knows walls, and not slabs

v = fived.estimate(IDX, V_RULES, qty, sources=src, vintage_rates=V_RATES)
v_by = {ln["code"]: ln for ln in v["lines"]}
assert v_by["09 21 16"]["rate_source"] == "vintage", v_by["09 21 16"]
assert v_by["09 21 16"]["unit_cost"] == 75.0, v_by["09 21 16"]
assert v_by["03 30 00"]["rate_source"] == "quoted", v_by["03 30 00"]
assert v["vintage_rate_lines"] == 1, v

# a `vintage` rule whose class the database does not price is its OWN state — not unpriced (a rule
# DID match it) and not priced (there is no number). Folding it into either would make the estimate
# silently short or silently free.
V2 = [{"selector": "class=IfcSlab", "code": "03 30 00", "basis": "volume", "rate_from": "vintage"}]
v2 = fived.estimate(IDX, V2, qty, sources=src, vintage_rates=V_RATES)
assert v2["no_rate_count"] == 1, v2["no_rate"]
assert v2["no_rate"][0]["ifc_class"] == "IfcSlab", v2["no_rate"]
assert "g-slab-1" not in v2["unpriced"], v2["unpriced"]      # matched, so NOT unpriced
assert not v2["complete"], v2                                 # ...and the estimate is not complete
assert v2["total"] == 0.0, v2["total"]                        # nothing was billed for it

# LAYERING: a later rule that can price it clears the flag. Reporting a gap a subsequent rule already
# closed sends an estimator to look at something that is fine.
V3 = [*V2, {"selector": "class=IfcSlab", "code": "03 30 00", "basis": "volume", "unit_cost": 200.0}]
v3 = fived.estimate(IDX, V3, qty, sources=src, vintage_rates=V_RATES)
assert v3["no_rate_count"] == 0, v3["no_rate"]
assert v3["total"] == round(4.0 * 200.0, 2), v3["total"]

# a rule asking for a vintage needs no unit_cost, and an unknown rate_from is REFUSED
fived.validate_rules([{"selector": "class=IfcWall", "code": "X", "basis": "area",
                       "rate_from": "vintage"}])
for bad in ("market", "", "guess"):
    try:
        fived.validate_rules([{"selector": "class=IfcWall", "code": "X", "basis": "area",
                               "rate_from": bad, "unit_cost": 1.0}])
        raise AssertionError(f"accepted rate_from {bad!r}")
    except Exception as e:                     # noqa: BLE001 — QueryError
        assert "rate_from" in str(e), (bad, e)

# ---- qto.measure: the model's own quantities, with their provenance --------------------------------
try:
    import ifcopenshell

    from aec_data import qto

    m = ifcopenshell.file(schema="IFC4")
    m.create_entity("IfcOwnerHistory")
    wall = m.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Measured wall")
    out = qto.measure(m, force_geometry=False)

    gid = wall.GlobalId
    assert gid in out["quantities"], out
    # `count` needs no measurement — one of a thing is one of a thing — so it is declared, always
    assert out["quantities"][gid]["count"] == 1.0
    assert out["sources"][gid]["count"] == "declared"
    # ...and a wall with no Qto pset and no geometry pass is UNMEASURED, not zero. Zero is a
    # measurement; "we could not measure it" is not, and billing the second as the first is how an
    # estimate ends up confidently missing a floor.
    assert any(u["guid"] == gid for u in out["unmeasured"]), out["unmeasured"]
    assert out["unmeasured_count"] == 1, out
    assert "area" not in out["quantities"][gid], out["quantities"][gid]
    assert set(qto.QUANTITY_SOURCES) == {"declared", "computed"}

    # HARDEN — the geometry pass is CAPPED, and the cap is REPORTED. Meshing is the expensive part,
    # and `measure` is reachable from a request-serving estimate route that previously did no
    # geometry work at all; an uncapped pass on a large tower is minutes of a stalled worker. A
    # quantity nobody measured because the budget ran out looks exactly like one the model never
    # carried, and only one of those is worth chasing — so the count is in the payload.
    m2 = ifcopenshell.file(schema="IFC4")
    m2.create_entity("IfcOwnerHistory")
    for i in range(5):
        m2.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name=f"W{i}")
    capped = qto.measure(m2, force_geometry=True, max_geometry=2)
    assert capped["meshed"] + capped["geometry_capped"] == 5, capped
    assert capped["geometry_capped"] == 3, capped
    # every element is still PRESENT — the cap bounds the measuring, not the reporting
    assert capped["measured"] == 5, capped
    # and with no cap in play nothing is reported as capped
    assert qto.measure(m2, force_geometry=False)["geometry_capped"] == 0
    assert qto.MAX_GEOMETRY >= 1000, "a cap this low would silently degrade real models"
    measured_ok = True
except ImportError:                    # pragma: no cover — ifcopenshell absent in a lean env
    measured_ok = False

print("R25-QTO-WIRE OK - the estimate now prices the MODEL's own quantities rather than numbers a "
      "caller passed in, which is the actual content of 'the model IS the estimate': every rule, "
      "rate and roll-up could be right while the numbers described a different building, and nothing "
      "in such an estimate looks wrong. `qto.measure` returns each element's quantities by GlobalId, "
      "and the part that matters is that they carry PROVENANCE - `declared` is the model's own "
      "IfcElementQuantity, `computed` is our measurement off the meshed solid, `override` is the "
      "caller replacing both. They are usually close and they are not the same claim. A line is only "
      "`declared` when EVERY element in it was; one measured element in fifty makes it `mixed`, "
      "because rounding that away would have the reader believe the model asserted a number we partly "
      "made up. An ABSENT provenance reads `unknown`, never `declared` - a caller who sends quantities "
      "with no provenance has said nothing about where they came from. Provenance annotates and never "
      "moves a number: the totals are asserted identical across all four labellings, so the label "
      "cannot quietly start doing arithmetic. The geometry pass is CAPPED and the cap is "
      "REPORTED (`geometry_capped`), because measure() is reachable from a request-serving route and a "
      "quantity nobody measured for want of budget looks exactly like one the model never carried."
      + ("" if measured_ok else " (qto.measure assertions skipped: ifcopenshell unavailable)"))
