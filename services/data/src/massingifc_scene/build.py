"""Assembling and validating packages on the Python side.

Mirrors ``buildScenePackage`` and ``validateScenePackage``. The refusals are the same refusals:
this exists so a Python producer cannot emit something the TypeScript reader would reject, and
vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence

from .geo import GeoReference, convert_length
from .model import (
    SCENE_FORMAT_VERSION,
    ScenePackage,
    ScenePackageError,
    SceneIndex,
    SceneMaterial,
    SceneNode,
    ScenePayload,
    ScenePropertySet,
    SceneRealityLayer,
    SceneRelationship,
    SceneSource,
)


def _scale_transform(transform: Sequence[float], factor: float) -> List[float]:
    """Scale the translation column of a column-major 4x4. Rotation and scale are unit-free."""
    if factor == 1.0:
        return list(transform)
    return [
        value * factor if 12 <= index <= 14 else value
        for index, value in enumerate(transform)
    ]


def build_scene_package(
    *,
    generator: str,
    generated_at: str,
    nodes: Sequence[SceneNode],
    sources: Sequence[SceneSource] = (),
    payloads: Sequence[ScenePayload] = (),
    materials: Optional[Sequence[SceneMaterial]] = None,
    source_units: Optional[str] = None,
    geo_reference: Optional[GeoReference] = None,
    properties: Optional[Mapping[str, Sequence[ScenePropertySet]]] = None,
    relationships: Optional[Sequence[SceneRelationship]] = None,
    reality_layers: Optional[Sequence[SceneRealityLayer]] = None,
) -> ScenePackage:
    """Assemble a package, converting to metres and building the indexes.

    Refuses duplicate GlobalIds rather than tolerating them: the index is a map, so the second
    entry would silently displace the first and an element would quietly stop being selectable.
    """
    seen = set()
    duplicates = []
    for node in nodes:
        if not node.global_id:
            raise ScenePackageError("A scene node has an empty GlobalId; identity is required.")
        if node.global_id in seen:
            duplicates.append(node.global_id)
        seen.add(node.global_id)
    if duplicates:
        raise ScenePackageError(
            f"Scene contains {len(duplicates)} duplicate GlobalId(s): {duplicates[:10]}"
        )

    factor = convert_length(1.0, source_units or "m", "m")
    placed = [
        SceneNode(
            global_id=node.global_id,
            name=node.name,
            ifc_class=node.ifc_class,
            parent_global_id=node.parent_global_id,
            level_global_id=node.level_global_id,
            # `is not None`, not truthiness: an empty array is a value the TypeScript writer
            # emits, and dropping it here would make the two implementations disagree.
            transform=(
                _scale_transform(node.transform, factor) if node.transform is not None else None
            ),
            bounds=(
                [value * factor for value in node.bounds] if node.bounds is not None else None
            ),
            payload_id=node.payload_id,
            geometry_index=node.geometry_index,
            material_id=node.material_id,
            transient_local_id=node.transient_local_id,
        )
        for node in nodes
    ]

    by_class: Dict[str, List[int]] = {}
    by_level: Dict[str, List[int]] = {}
    by_global_id: Dict[str, int] = {}
    for position, node in enumerate(placed):
        by_global_id[node.global_id] = position
        if node.ifc_class is not None:
            by_class.setdefault(node.ifc_class, []).append(position)
        if node.level_global_id is not None:
            by_level.setdefault(node.level_global_id, []).append(position)

    return ScenePackage(
        format_version=SCENE_FORMAT_VERSION,
        generator=generator,
        generated_at=generated_at,
        sources=list(sources),
        units="m",
        source_units=source_units,
        # Converted by its own units, never the model's: the two are independent.
        geo_reference=geo_reference.to_metres() if geo_reference else None,
        payloads=list(payloads),
        nodes=placed,
        materials=list(materials) if materials is not None else None,
        properties=properties,
        relationships=list(relationships) if relationships is not None else None,
        reality_layers=list(reality_layers) if reality_layers is not None else None,
        index=SceneIndex(by_class=by_class, by_level=by_level, by_global_id=by_global_id),
    )


@dataclass(frozen=True)
class SceneIssue:
    severity: str
    code: str
    message: str
    subject: Optional[str] = None


@dataclass(frozen=True)
class SceneValidationReport:
    valid: bool
    issues: Sequence[SceneIssue]


def validate_scene_package(scene: ScenePackage) -> SceneValidationReport:
    """Check internal references before a package leaves the process.

    Every failure this catches would otherwise surface inside an engine importer as a missing mesh
    or a null lookup, several tools away from the cause.
    """
    issues: List[SceneIssue] = []
    payload_ids = {payload.id for payload in scene.payloads}
    material_ids = {material.id for material in scene.materials or ()}
    global_ids = {node.global_id for node in scene.nodes}

    for node in scene.nodes:
        if node.payload_id is not None and node.payload_id not in payload_ids:
            issues.append(
                SceneIssue(
                    "error",
                    "unknown-payload-reference",
                    f"Node {node.global_id!r} references payload {node.payload_id!r}, "
                    "which is not in the package.",
                    node.global_id,
                )
            )
        if node.material_id is not None and node.material_id not in material_ids:
            issues.append(
                SceneIssue(
                    "warning",
                    "unknown-material",
                    f"Node {node.global_id!r} references material {node.material_id!r}, "
                    "which is not declared.",
                    node.global_id,
                )
            )
        if node.parent_global_id is not None and node.parent_global_id not in global_ids:
            # A warning, not an error: a single-storey export legitimately leaves the parent
            # outside the package, and refusing that would make scoped exports impossible.
            issues.append(
                SceneIssue(
                    "warning",
                    "unknown-parent",
                    f"Node {node.global_id!r} has parent {node.parent_global_id!r}, "
                    "which is outside this package.",
                    node.global_id,
                )
            )
        if node.level_global_id is not None and node.level_global_id not in global_ids:
            issues.append(
                SceneIssue(
                    "warning",
                    "unknown-level",
                    f"Node {node.global_id!r} is on level {node.level_global_id!r}, "
                    "which is outside this package.",
                    node.global_id,
                )
            )

    for edge in scene.relationships or ():
        if edge.from_global_id not in global_ids or edge.to_global_id not in global_ids:
            issues.append(
                SceneIssue(
                    "warning",
                    "dangling-relationship",
                    f"Relationship {edge.type!r} links {edge.from_global_id} to "
                    f"{edge.to_global_id}, at least one of which is outside this package.",
                )
            )

    for global_id in (scene.properties or {}):
        if global_id not in global_ids:
            issues.append(
                SceneIssue(
                    "warning",
                    "properties-without-node",
                    f"Property sets are attached to {global_id!r}, which has no node.",
                    global_id,
                )
            )

    for global_id, position in scene.index.by_global_id.items():
        if not (0 <= position < len(scene.nodes)) or scene.nodes[position].global_id != global_id:
            issues.append(
                SceneIssue(
                    "error",
                    "stale-index",
                    f"Index entry for {global_id!r} points at position {position}, "
                    "which holds a different node.",
                    global_id,
                )
            )

    if scene.nodes and all(node.payload_id is None for node in scene.nodes):
        issues.append(
            SceneIssue(
                "warning",
                "no-geometry",
                "No node references geometry; this package carries semantics only.",
            )
        )

    return SceneValidationReport(
        valid=not any(issue.severity == "error" for issue in issues), issues=issues
    )
