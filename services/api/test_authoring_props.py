"""Authoring P2: structured property editing (set_element_pset) + classification tagging
(set_classification — Uniclass/OmniClass/Uniformat) via the recipe registry. These back the
element property/classify editor in the viewer's props panel.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_authoring_props.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell                                       # noqa: E402
import ifcopenshell.api                                   # noqa: E402
import ifcopenshell.util.classification as ucls           # noqa: E402
import ifcopenshell.util.element as ue                    # noqa: E402
from aec_data import edit                                 # noqa: E402
from aec_data.ifc_loader import open_model                # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_authp.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_authp_out.ifc")


def _build() -> tuple[str, str]:
    m = ifcopenshell.api.run("project.create_file")
    proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="P")
    metre = m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    ifcopenshell.api.run("unit.assign_unit", m, units=[metre])
    ifcopenshell.api.run("context.add_context", m, context_type="Model")
    site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="S")
    bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="B")
    col = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcColumn", name="C1")
    ifcopenshell.api.run("aggregate.assign_object", m, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[bldg], relating_object=site)
    m.write(TMP)
    return TMP, col.GlobalId


def main() -> None:
    src, guid = _build()

    # --- set_element_pset: a structured property edit (replaces the old prompt) ---------------
    edit.apply_recipe(src, "set_element_pset",
                      {"guid": guid, "pset": "Pset_Custom", "prop": "Manufacturer", "value": "Acme"}, OUT)
    edit.apply_recipe(OUT, "set_element_pset",
                      {"guid": guid, "pset": "Pset_Custom", "prop": "LoadRating",
                       "value": "1500", "dtype": "float"}, OUT)
    m = open_model(OUT)
    el = m.by_guid(guid)
    assert ue.get_pset(el, "Pset_Custom", "Manufacturer") == "Acme", "string prop round-trip"
    assert ue.get_pset(el, "Pset_Custom", "LoadRating") == 1500.0, "float prop coerced + round-trip"

    # --- set_classification: Uniclass + a second system, reusing the source (no dupes) --------
    edit.apply_recipe(OUT, "set_classification",
                      {"guid": guid, "system": "Uniclass 2015", "code": "Pr_20_93_52",
                       "name": "Steel column", "edition": "2015"}, OUT)
    edit.apply_recipe(OUT, "set_classification",
                      {"guid": guid, "system": "Uniclass 2015", "code": "Pr_20_93_52_50",
                       "name": "UB column"}, OUT)
    edit.apply_recipe(OUT, "set_classification",
                      {"guid": guid, "system": "Uniformat II", "code": "B1010", "name": "Floor Construction"}, OUT)
    m2 = open_model(OUT)
    el2 = m2.by_guid(guid)
    refs = ucls.get_references(el2)
    by_sys: dict[str, list[str]] = {}
    for r in refs:
        sys_name = r.ReferencedSource.Name if r.ReferencedSource else "?"
        by_sys.setdefault(sys_name, []).append(r.Identification)
    assert "Pr_20_93_52" in by_sys.get("Uniclass 2015", []), by_sys
    assert "Pr_20_93_52_50" in by_sys.get("Uniclass 2015", []), by_sys
    assert "B1010" in by_sys.get("Uniformat II", []), by_sys
    # two Uniclass tags must share ONE IfcClassification source (reuse, not duplicate)
    uniclass_sources = [s for s in m2.by_type("IfcClassification")
                        if (s.Name or "").strip() == "Uniclass 2015"]
    assert len(uniclass_sources) == 1, f"expected 1 Uniclass source, got {len(uniclass_sources)}"

    for f in (TMP, OUT):
        if os.path.exists(f):
            os.remove(f)
    print("AUTHORING PROPS OK - set_element_pset (str + coerced float) + set_classification "
          "(Uniclass 2015 x2 sharing one source, Uniformat II) round-trip through the recipe registry.")


if __name__ == "__main__":
    main()
