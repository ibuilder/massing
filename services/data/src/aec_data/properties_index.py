"""Phase 1 — lightweight properties index.

Extracts per-element GUID, IFC class, name, storey, and Psets to a queryable JSON so the
API and the viewer's spatial tree never re-parse geometry. Geometry streams as .frag;
data comes from here (CLAUDE.md: keep geometry and metadata separate)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, physical_elements, storey_of


@dataclass
class ElementRecord:
    guid: str
    ifc_class: str
    name: str | None
    type_name: str | None
    storey: str | None
    #: GlobalId of the containing storey. The `storey` NAME above stays because a dozen readers want
    #: a label, but it is not an identity — two buildings on one site each having a "Level 2" is the
    #: ordinary case, and every grouping keyed on the string merges them in silence. This is the key
    #: to group on, and the one that joins an element to a node of the spatial tree.
    storey_guid: str | None = None
    # IFC's own subtype discriminator (IfcWall.PredefinedType = SOLIDWALL / PARTITIONING / …). Two
    # IfcWalls with the same class and pset can still be a structural wall and a partition, and the
    # only place that distinction lives is here. Read as a plain string because it is an enum in the
    # schema and a free-text `ObjectType` when the enum says USERDEFINED — a caller that wants one
    # rule for both is better served by the string than by a discriminated union it has to unpick.
    predefined_type: str | None = None
    host: str | None = None   # IFC class of the aggregating parent (e.g. an IfcMember's IfcCurtainWall)
    psets: dict[str, dict[str, Any]] = field(default_factory=dict)
    qtos: dict[str, dict[str, Any]] = field(default_factory=dict)
    # --- GEOMETRY FACTS (LOD-ASPECTS) --------------------------------------------------------
    # Not geometry — FACTS ABOUT it, small enough to belong in a metadata index. They exist
    # because LOD is a claim about how far an element's geometry has been thought through, and
    # until these landed the index carried nothing geometric at all, so `lod.achieved_lod` scored
    # information completeness and reported the answer under a geometry name.
    #
    # `rep_types` is the discriminating one: IFC records how a shape is BUILT
    # (`BoundingBox` / `SweptSolid` / `Brep` / `Clipping` / `Tessellation` / `MappedRepresentation`),
    # and a box standing in for a pump is a different claim from a swept solid, which is a different
    # claim from a clipped Brep. That is exactly the Detail axis, read from the file rather than
    # guessed from how well the element is tagged.
    rep_types: list[str] = field(default_factory=list)
    rep_ids: list[str] = field(default_factory=list)      # Body / Axis / Box / FootPrint …
    has_openings: bool = False                            # IfcRelVoidsElement — voids cut into it
    has_material: bool = False
    placed: bool = False                                  # carries an ObjectPlacement at all


def _shape_facts(el) -> tuple[list[str], list[str], bool]:
    """Representation types + identifiers, and whether anything is voided out of the element.

    Wrapped in a broad except on purpose: this runs over every element of every uploaded file, and a
    malformed representation on one element must not cost the whole index. An element whose shape
    could not be read reports EMPTY lists, which downstream reads as *undecidable* rather than as
    *simple* — failing toward "cannot tell" is the only safe direction for a number that goes into a
    BIM execution plan.
    """
    types: list[str] = []
    ids: list[str] = []
    try:
        rep = getattr(el, "Representation", None)
        for r in (getattr(rep, "Representations", None) or []):
            t = getattr(r, "RepresentationType", None)
            i = getattr(r, "RepresentationIdentifier", None)
            if t:
                types.append(str(t))
            if i:
                ids.append(str(i))
    except Exception:  # noqa: BLE001 — see docstring
        pass
    try:
        voided = bool(getattr(el, "HasOpenings", None))
    except Exception:  # noqa: BLE001
        voided = False
    return types, ids, voided


def _predefined_type(el) -> str | None:
    """`PredefinedType`, resolved through USERDEFINED to `ObjectType` when that is what it means.

    IFC spells "the schema has no name for this" as `PredefinedType = USERDEFINED` plus a free-text
    `ObjectType`, so returning the literal string "USERDEFINED" would answer the question with the
    fact that there was no answer. `NOTDEFINED` is dropped for the same reason: it is IFC's null, and
    passing it through would make "the author did not say" indistinguishable from a real value in
    every downstream `if predefined_type ==` — which is the shape of bug that survives review.

    Not every entity has the attribute at all (it arrived in different schema versions for different
    classes), and reading it off one that does not raises rather than returning None, so this asks
    forgiveness rather than maintaining a per-class table that would be wrong on the next schema.
    """
    try:
        raw = getattr(el, "PredefinedType", None)
    except Exception:  # noqa: BLE001 — attribute absent for this class in this schema
        return None
    val = str(raw) if raw is not None else None
    if val in (None, "", "NOTDEFINED"):
        return None
    if val == "USERDEFINED":
        try:
            obj = getattr(el, "ObjectType", None)
        except Exception:  # noqa: BLE001
            obj = None
        return str(obj) if obj else None
    return val


#: What counts as a spatial node, tested with `is_a(name)` so SUBTYPES match too.
#:
#: The obvious spelling is a tuple of the four concrete classes checked with `el.is_a() in (...)`,
#: and it is wrong in the direction that leaves no trace: `is_a()` with no argument returns the
#: element's own class as a string, so an exact-membership test silently drops every subtype —
#: `IfcSpatialZone` in IFC4, and any vendor subtype of `IfcSpace`. `is_a("IfcSpatialElement")`
#: matches the supertype instead. Both spellings are listed because the supertype was renamed
#: between schemas; `is_a` on a class the loaded schema does not define returns False rather than
#: raising, so trying both costs nothing and covers IFC2X3 and IFC4 with one branch.
_SPATIAL_SUPERTYPES = ("IfcSpatialElement", "IfcSpatialStructureElement")


def _is_spatial(el) -> bool:
    return any(el.is_a(c) for c in _SPATIAL_SUPERTYPES)


def _spatial_node(el, children: list[dict]) -> dict:
    """One node in the shape `SpatialNode` documents: ref + ifcClass + name + children.

    `ref.modelId` is filled in by the API, not here. The indexer does not know what the model will
    be called once it is stored, and inventing an id here that the service then has to override is
    how two ids for one model start disagreeing.
    """
    node = {
        "guid": el.GlobalId,
        "ifcClass": el.is_a(),
        # A name is not required by IFC and plenty of real files omit it on storeys. The class is the
        # honest fallback: "IfcBuildingStorey" beats an empty string in a tree widget, and beats a
        # fabricated "Level 1" outright.
        "name": (getattr(el, "Name", None) or el.is_a()),
        "children": children,
    }
    elev = getattr(el, "Elevation", None) if el.is_a("IfcBuildingStorey") else None
    if elev is not None:
        # Metres above project zero, per the consumer's contract. IFC stores this in the project's
        # length unit, which is very often millimetres — converting it here would need the unit
        # context and would silently produce a 3000x error when the assumption is wrong, so the raw
        # value ships with the unit stated in the payload instead of a guess baked into the number.
        node["elevation"] = float(elev)
    return node


def build_spatial_tree(model: ifcopenshell.file) -> dict | None:
    """The real IFC containment hierarchy — IfcProject → Site → Building → Storey → Space.

    **Derived from the file's own decomposition, never from storey NAMES.** The index already carries
    a `storey` string per element and it is tempting to group on it, which would produce a tree with
    no GUIDs in it at all — and a node a caller cannot address by GlobalId is not a node, it is a
    label. Two storeys legitimately share a name across two buildings, so the name-grouped version is
    also wrong on exactly the models where the tree matters most.

    Returns None when the file has no `IfcProject`, which is not a tree with one missing node — it is
    a file with no spatial structure, and the caller must be able to tell those apart.
    """
    project = (model.by_type("IfcProject") or [None])[0]
    if project is None:
        return None

    # The spatial chain is built by DECOMPOSITION (IfcRelAggregates) the whole way down: a project
    # aggregates sites, a site aggregates buildings, a building aggregates storeys, a storey
    # aggregates spaces. `IfcRelContainedInSpatialStructure` — the relationship that puts a *wall* on
    # a storey — is deliberately not read here, because elements are not nodes of this tree; the
    # consumer's `SpatialNode.children` is spatial-only and elements are fetched per storey from
    # `/elements?storey=`. Mixing the two relationships would put 500 walls under a storey node.
    def _spatial_children(el) -> list:
        out, seen = [], set()
        for rel in (getattr(el, "IsDecomposedBy", None) or []):
            for child in (getattr(rel, "RelatedObjects", None) or []):
                if child.id() not in seen and _is_spatial(child):
                    seen.add(child.id())
                    out.append(child)
        return out

    def walk(el, depth: int = 0) -> dict:
        # A malformed file can aggregate a storey into itself. Bounding the depth is cheaper than
        # tracking the visited set through a recursive build, and 12 is far past any real hierarchy
        # (project/site/building/storey/space is five).
        kids = [walk(c, depth + 1) for c in _spatial_children(el)] if depth < 12 else []
        return _spatial_node(el, kids)

    return walk(project)


def _element_record(el) -> ElementRecord:
    _st = storey_of(el)
    el_type = ue.get_type(el)
    parent = ue.get_aggregate(el)     # the decomposing parent (IfcRelAggregates), not the spatial container
    rep_types, rep_ids, has_openings = _shape_facts(el)
    try:
        has_material = ue.get_material(el) is not None
    except Exception:  # noqa: BLE001 — a broken material association is not an indexing failure
        has_material = False
    return ElementRecord(
        rep_types=rep_types, rep_ids=rep_ids, has_openings=has_openings,
        has_material=has_material, placed=getattr(el, "ObjectPlacement", None) is not None,
        guid=el.GlobalId,
        ifc_class=el.is_a(),
        name=getattr(el, "Name", None),
        type_name=getattr(el_type, "Name", None) if el_type else None,
        storey=_st.Name if _st is not None else None,
        storey_guid=_st.GlobalId if _st is not None else None,
        predefined_type=_predefined_type(el),
        host=parent.is_a() if parent is not None else None,
        psets=ue.get_psets(el, psets_only=True),
        qtos=ue.get_psets(el, qtos_only=True),
    )


def build_index(model: ifcopenshell.file) -> dict[str, Any]:
    project = (model.by_type("IfcProject") or [None])[0]
    elements = [asdict(_element_record(el)) for el in physical_elements(model)]
    # collect distinct facets used by layers/classification filters (guide §3/§6)
    classes = sorted({e["ifc_class"] for e in elements})
    storeys = sorted({e["storey"] for e in elements if e["storey"]})
    return {
        "schema": model.schema,
        # The IFC schema above ("IFC4") and the shape of THIS FILE are two different versions, and
        # the first was standing in for both. `index_schema` is ours: 2 is the first that carries
        # `spatial`. It exists so an index written before this can be told apart from a model that
        # genuinely has no spatial structure — both have no tree, and only one of them can be fixed
        # by re-publishing. Serving a v1 index as "this model has no storeys" is the lie the version
        # number prevents, and it is the same argument `schedule_baselines` makes for its own.
        "index_schema": 2,
        "project": {
            "guid": project.GlobalId if project else None,
            "name": getattr(project, "Name", None) if project else None,
        },
        "counts": {"elements": len(elements), "classes": len(classes), "storeys": len(storeys)},
        "facets": {"classes": classes, "storeys": storeys},
        "spatial": build_spatial_tree(model),
        "elements": elements,
    }


def _is_json_model(path: str) -> bool:
    """IFC5 / IFCX / ifcJSON are JSON documents (first non-space byte is { or [); STEP starts ISO-10303."""
    try:
        with open(path, "rb") as fh:
            return fh.read(4096).lstrip()[:1] in (b"{", b"[")
    except OSError:
        return False


def index_file(ifc_path: str, out_path: str | None = None) -> dict[str, Any]:
    if _is_json_model(ifc_path):
        # IFC5/IFCX/ifcJSON: geometry can't render yet, but the data layer reads now (real read path).
        from .ifc5_reader import index_json_file
        return index_json_file(ifc_path, out_path)
    model = open_model(ifc_path)
    index = build_index(model)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False)
    return index
