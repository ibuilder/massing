"""IFC to scene package, server-side.

Converting in Python rather than in the browser is the arrangement the architecture already assumes:
IFC is converted once, somewhere with time and memory, and clients load the result. Doing it per
session pushes a heavy parse into every user's tab.

This produces the *semantic* half of a package directly from IFC — identity, hierarchy, classes,
property sets, quantities, georeference. Geometry is attached separately by whatever produced the
Fragments binary, because re-tessellating here would invent a parallel format and lose the
per-element addressing Fragments already carries. ``geometry=`` takes those bytes when you have
them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from massingifc_scene import (
    FRAGMENTS_ENCODING,
    GeoReference,
    ScenePackage,
    ScenePackageError,
    SceneNode,
    ScenePayload,
    ScenePropertySet,
    SceneRelationship,
    SceneSource,
    build_scene_package,
    content_hash,
    payload_path,
)

#: SI prefixes the format has a matching linear unit for.
_SI_PREFIXES = {
    "MILLI": "mm",
    "CENTI": "cm",
    None: "m",
}

#: Conversion factors to metres for the non-SI units the format supports, with the tolerance
#: needed to recognise them: ``ft`` and ``us-ft`` are ~2ppm apart, so the match has to be tight
#: enough to tell them apart and loose enough to survive a file that rounds.
_CONVERSION_FACTORS = (("ft", 0.3048, 1e-9), ("us-ft", 1200 / 3937, 1e-9))

#: Product supertypes that are deliberately not scene nodes.
#:
#: A void is a subtraction from a wall, not a thing to draw; a port is a connection point on a
#: pipe, not geometry. Both are `IfcProduct`, both are reachable in a real file, and neither means
#: anything to an engine that is going to instance one actor per node. Stated here so their absence
#: is a decision on the record rather than an accident of which relationships the walk follows.
EXCLUDED_SUPERTYPES = ("IfcFeatureElement", "IfcPort")


def is_excluded(product: Any) -> bool:
    return any(product.is_a(supertype) for supertype in EXCLUDED_SUPERTYPES)


#: Classes whose GlobalId is stamped onto everything beneath them as `levelGlobalId`.
_STOREY = "IfcBuildingStorey"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class UnknownUnitError(ScenePackageError):
    """The file's length unit is not one the scene package format can express."""


def _length_unit(ifc_file: Any, assume: Optional[str] = None) -> str:
    """Read the project's length unit.

    Refuses rather than defaults. Silently assuming metres is how a feet-based model — the norm on
    a US project — ends up scaled by 3.28 with nothing anywhere saying so, and that is exactly the
    failure the format's "metres always, never guess" rule exists to prevent. A caller who knows
    better can say so with ``assume_units``.
    """
    for assignment in ifc_file.by_type("IfcUnitAssignment"):
        for unit in assignment.Units or ():
            if getattr(unit, "UnitType", None) != "LENGTHUNIT":
                continue

            if unit.is_a("IfcSIUnit"):
                if getattr(unit, "Name", None) != "METRE":
                    raise UnknownUnitError(
                        f"Unsupported SI length unit {getattr(unit, 'Name', None)!r}."
                    )
                prefix = getattr(unit, "Prefix", None)
                if prefix not in _SI_PREFIXES:
                    raise UnknownUnitError(
                        f"Length unit is metres with prefix {prefix!r}, which the scene package "
                        "format cannot express. Pass assume_units= if you know the right one."
                    )
                return _SI_PREFIXES[prefix]

            if unit.is_a("IfcConversionBasedUnit"):
                # How imperial files declare length: a name plus a factor onto an SI unit.
                factor = getattr(unit, "ConversionFactor", None)
                value = getattr(getattr(factor, "ValueComponent", None), "wrappedValue", None)
                if isinstance(value, (int, float)):
                    for name, metres, tolerance in _CONVERSION_FACTORS:
                        if abs(float(value) - metres) <= tolerance:
                            return name
                raise UnknownUnitError(
                    f"Length unit {getattr(unit, 'Name', None)!r} converts to metres by "
                    f"{value!r}, which is not a unit the scene package format supports."
                )

            raise UnknownUnitError(f"Unrecognised length unit entity {unit.is_a()}.")

    if assume is not None:
        return assume
    raise UnknownUnitError(
        "This IFC declares no length unit. Pass assume_units= to state one explicitly rather "
        "than have the converter guess."
    )


def _scalar(value: Any) -> Optional[Any]:
    """Reduce an IFC value to something JSON can hold, or ``None`` if it cannot.

    Non-scalars are dropped rather than stringified: a consumer reading ``"[object Object]"`` or
    a Python ``repr`` cannot tell it from a real value, but an absent key it can.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    wrapped = getattr(value, "wrappedValue", None)
    if wrapped is not None and isinstance(wrapped, (str, int, float, bool)):
        return wrapped
    return None


def _property_sets(element: Any) -> List[ScenePropertySet]:
    """Property sets and element quantities, kept unflattened as the model has them."""
    sets: List[ScenePropertySet] = []
    quantities: Dict[str, Any] = {}

    for relation in getattr(element, "IsDefinedBy", None) or ():
        definition = getattr(relation, "RelatingPropertyDefinition", None)
        if definition is None:
            continue

        name = getattr(definition, "Name", None) or "Unnamed"

        values: Dict[str, Any] = {}
        for prop in getattr(definition, "HasProperties", None) or ():
            scalar = _scalar(getattr(prop, "NominalValue", None))
            if scalar is not None and getattr(prop, "Name", None):
                values[prop.Name] = scalar

        for quantity in getattr(definition, "Quantities", None) or ():
            label = getattr(quantity, "Name", None)
            if not label:
                continue
            for attribute in (
                "AreaValue",
                "VolumeValue",
                "LengthValue",
                "CountValue",
                "WeightValue",
                "TimeValue",
            ):
                measured = getattr(quantity, attribute, None)
                if measured is not None:
                    values[label] = measured
                    if isinstance(measured, (int, float)):
                        quantities[label] = measured
                    break

        if values:
            sets.append(ScenePropertySet(name=name, properties=values))

    if quantities:
        # Hoisted as well as left in place: takeoff wants them by name as numbers, a property
        # panel wants them where IFC put them. Merged into an existing set of the same name rather
        # than appended beside it — a file may legitimately contain a pset called "Quantities", and
        # two sets sharing a name means any consumer keying a dictionary by it loses one.
        existing = next((index for index, s in enumerate(sets) if s.name == "Quantities"), None)
        if existing is None:
            sets.append(ScenePropertySet(name="Quantities", properties=quantities))
        else:
            merged = {**sets[existing].properties, **quantities}
            sets[existing] = ScenePropertySet(name="Quantities", properties=merged)

    return sets


def _contained(structure: Any) -> List[Any]:
    """Elements a spatial structure contains, plus the structures nested inside it."""
    children: List[Any] = []
    for relation in getattr(structure, "ContainsElements", None) or ():
        children.extend(relation.RelatedElements or ())
    for relation in getattr(structure, "IsDecomposedBy", None) or ():
        children.extend(relation.RelatedObjects or ())
    return children


def convert_ifc(
    path: Path | str,
    *,
    model_id: Optional[str] = None,
    generated_at: Optional[str] = None,
    include_properties: bool = True,
    include_relationships: bool = True,
    geometry: Optional[bytes] = None,
    geo_reference: Optional[GeoReference] = None,
    assume_units: Optional[str] = None,
    on_warning: Optional[Callable[[str], None]] = None,
) -> Tuple[ScenePackage, Mapping[str, bytes]]:
    """Convert an IFC file into a package and its payload bytes.

    Returns both together, because a manifest naming payloads nobody can supply is a promise rather
    than a package.
    """
    try:
        import ifcopenshell  # noqa: PLC0415 - optional, and only this function needs it
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ScenePackageError(
            "Converting IFC needs ifcopenshell; the reader half of this library does not."
        ) from exc

    source = Path(path)
    if not source.is_file():
        raise ScenePackageError(f"No IFC file at {source}")

    ifc_file = ifcopenshell.open(str(source))
    identifier = model_id or source.stem

    nodes: List[SceneNode] = []
    relationships: List[SceneRelationship] = []
    properties: Dict[str, List[ScenePropertySet]] = {}
    seen: set[str] = set()

    def visit(entity: Any, parent: Optional[str], level: Optional[str]) -> None:
        global_id = getattr(entity, "GlobalId", None)
        ifc_class = entity.is_a()
        next_level = level

        if global_id and is_excluded(entity):
            # Reachable but deliberately not a node. Its children, if any, still are.
            for child in _contained(entity):
                visit(child, parent, next_level)
            return

        if global_id:
            if ifc_class == _STOREY:
                next_level = global_id

            if global_id not in seen:
                seen.add(global_id)
                nodes.append(
                    SceneNode(
                        global_id=global_id,
                        name=getattr(entity, "Name", None) or None,
                        ifc_class=ifc_class.upper(),
                        parent_global_id=parent,
                        # A storey is not on its own level.
                        level_global_id=next_level if next_level != global_id else None,
                    )
                )
                if parent is not None and include_relationships:
                    relationships.append(
                        SceneRelationship(
                            type="IFCRELCONTAINEDINSPATIALSTRUCTURE",
                            from_global_id=parent,
                            to_global_id=global_id,
                        )
                    )
                if include_properties:
                    sets = _property_sets(entity)
                    if sets:
                        properties[global_id] = sets

            parent = global_id

        for child in _contained(entity):
            visit(child, parent, next_level)

    roots = ifc_file.by_type("IfcProject")
    if not roots:
        raise ScenePackageError("This IFC file declares no IfcProject, so it has no spatial root.")
    for root in roots:
        visit(root, None, None)

    # Anything the spatial walk did not reach is absent from the package. That happens for real
    # reasons — an element aggregated under another element, or simply orphaned — but an element
    # that silently fails to arrive is the same class of problem as a silently assumed unit, so it
    # is counted and reported rather than left to be discovered downstream.
    unreached = [
        product
        for product in ifc_file.by_type("IfcProduct")
        if getattr(product, "GlobalId", None)
        and product.GlobalId not in seen
        and not is_excluded(product)
    ]
    if on_warning is not None and not any(
        node.global_id != root.GlobalId for node in nodes for root in roots
    ):
        # A file of type definitions with no instances converts to an empty package, which is
        # correct and looks broken. Real family libraries are exactly this shape, so say so rather
        # than hand back an empty package and let the reader guess which of the two it is.
        type_count = len(ifc_file.by_type("IfcTypeProduct"))
        if type_count:
            on_warning(
                f"This file declares {type_count} type definition(s) and no placed products: it is "
                "a type library rather than a model, so the package has no elements."
            )

    if unreached and on_warning is not None:
        sample = ", ".join(f"{p.is_a()} {p.GlobalId}" for p in unreached[:5])
        on_warning(
            f"{len(unreached)} product(s) are not reachable through the spatial hierarchy and are "
            f"not in the package: {sample}"
            + (" ..." if len(unreached) > 5 else "")
        )

    payloads: List[ScenePayload] = []
    payload_bytes: Dict[str, bytes] = {}
    if geometry is not None:
        payload_id = f"geometry-{identifier}"
        payloads.append(
            ScenePayload(
                id=payload_id,
                role="geometry",
                path=payload_path(payload_id, "frag"),
                encoding=FRAGMENTS_ENCODING,
                byte_length=len(geometry),
                hash=content_hash(geometry),
            )
        )
        payload_bytes[payload_id] = geometry
        nodes = [
            SceneNode(**{**node.__dict__, "payload_id": payload_id}) for node in nodes
        ]

    scene = build_scene_package(
        generator=f"massingifc-ifc/{ifcopenshell.version}",
        generated_at=generated_at or _now(),
        sources=[
            SceneSource(
                model_id=identifier,
                model_name=source.name,
                revision=getattr(ifc_file, "schema", None),
            )
        ],
        source_units=_length_unit(ifc_file, assume_units),
        geo_reference=geo_reference,
        nodes=nodes,
        payloads=payloads,
        properties=properties or None,
        relationships=relationships if include_relationships else None,
    )
    return scene, payload_bytes
