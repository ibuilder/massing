"""The scene package model.

A faithful second implementation of the format defined by ``@massingifc/engine-bridge``. Its
existence is the point: the format claims a consumer needs nothing but a JSON parser and a file
handle, and a claim like that is only worth anything once something outside the original language
reads and writes it. The conformance suite compares the two byte for byte.

Every field name here is the JSON name used on the wire, so the mapping is explicit rather than
inferred from a naming convention that could drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from .geo import GeoReference, _drop_none

#: Bumped only for breaking changes to the manifest shape.
SCENE_FORMAT_VERSION = "1.0"

SCENE_MANIFEST_PATH = "scene.json"
SCENE_PAYLOAD_DIRECTORY = "payloads"

#: Media type for a Fragments 2.0 binary — the geometry a package normally carries.
FRAGMENTS_ENCODING = "application/vnd.thatopen.fragments"


@dataclass(frozen=True)
class ScenePayload:
    id: str
    role: str
    path: str
    encoding: str
    byte_length: int
    hash: Optional[str] = None

    def to_json(self) -> dict:
        return _drop_none(
            {
                "id": self.id,
                "role": self.role,
                "path": self.path,
                "encoding": self.encoding,
                "byteLength": self.byte_length,
                "hash": self.hash,
            }
        )

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "ScenePayload":
        return ScenePayload(
            id=data["id"],
            role=data["role"],
            path=data["path"],
            encoding=data["encoding"],
            byte_length=data["byteLength"],
            hash=data.get("hash"),
        )


@dataclass(frozen=True)
class SceneNode:
    """One addressable thing in the scene.

    ``global_id`` is the identity — the IFC GlobalId. It survives export, re-import, a change of
    viewer and a change of engine. ``transient_local_id`` is a debugging aid and is never a key;
    an importer that indexes on it has reintroduced exactly the bug this format exists to avoid.
    """

    global_id: str
    name: Optional[str] = None
    ifc_class: Optional[str] = None
    parent_global_id: Optional[str] = None
    level_global_id: Optional[str] = None
    transform: Optional[Sequence[float]] = None
    bounds: Optional[Sequence[float]] = None
    payload_id: Optional[str] = None
    geometry_index: Optional[int] = None
    material_id: Optional[str] = None
    transient_local_id: Optional[int] = None

    def to_json(self) -> dict:
        return _drop_none(
            {
                "globalId": self.global_id,
                "name": self.name,
                "ifcClass": self.ifc_class,
                "parentGlobalId": self.parent_global_id,
                "levelGlobalId": self.level_global_id,
                "transform": list(self.transform) if self.transform is not None else None,
                "bounds": list(self.bounds) if self.bounds is not None else None,
                "payloadId": self.payload_id,
                "geometryIndex": self.geometry_index,
                "materialId": self.material_id,
                "transientLocalId": self.transient_local_id,
            }
        )

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "SceneNode":
        return SceneNode(
            global_id=data["globalId"],
            name=data.get("name"),
            ifc_class=data.get("ifcClass"),
            parent_global_id=data.get("parentGlobalId"),
            level_global_id=data.get("levelGlobalId"),
            transform=data.get("transform"),
            bounds=data.get("bounds"),
            payload_id=data.get("payloadId"),
            geometry_index=data.get("geometryIndex"),
            material_id=data.get("materialId"),
            transient_local_id=data.get("transientLocalId"),
        )


@dataclass(frozen=True)
class SceneMaterial:
    """Appearance for a node that references it by ``material_id``.

    Carried even though nothing here produces materials yet: a reader that drops a field it does
    not use turns a round-trip into data loss, and the nodes would keep pointing at ids the
    materials list no longer contains.
    """

    id: str
    name: Optional[str] = None
    base_color: Optional[Sequence[float]] = None
    metallic: Optional[float] = None
    roughness: Optional[float] = None
    opacity: Optional[float] = None
    double_sided: Optional[bool] = None
    texture_payload_id: Optional[str] = None

    def to_json(self) -> dict:
        return _drop_none(
            {
                "id": self.id,
                "name": self.name,
                "baseColor": list(self.base_color) if self.base_color is not None else None,
                "metallic": self.metallic,
                "roughness": self.roughness,
                "opacity": self.opacity,
                "doubleSided": self.double_sided,
                "texturePayloadId": self.texture_payload_id,
            }
        )

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "SceneMaterial":
        return SceneMaterial(
            id=data["id"],
            name=data.get("name"),
            base_color=data.get("baseColor"),
            metallic=data.get("metallic"),
            roughness=data.get("roughness"),
            opacity=data.get("opacity"),
            double_sided=data.get("doubleSided"),
            texture_payload_id=data.get("texturePayloadId"),
        )


@dataclass(frozen=True)
class ScenePropertySet:
    name: str
    properties: Mapping[str, Any]

    def to_json(self) -> dict:
        return {"name": self.name, "properties": dict(self.properties)}

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "ScenePropertySet":
        return ScenePropertySet(name=data["name"], properties=dict(data.get("properties", {})))


@dataclass(frozen=True)
class SceneRelationship:
    type: str
    from_global_id: str
    to_global_id: str

    def to_json(self) -> dict:
        return {
            "type": self.type,
            "fromGlobalId": self.from_global_id,
            "toGlobalId": self.to_global_id,
        }

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "SceneRelationship":
        return SceneRelationship(
            type=data["type"],
            from_global_id=data["fromGlobalId"],
            to_global_id=data["toGlobalId"],
        )


@dataclass(frozen=True)
class SceneRealityLayer:
    """Evidence carried alongside the model.

    ``measurable`` is the flag that stops a downstream tool offering a dimension over a radiance
    field, which renders convincingly and has no surface.
    """

    id: str
    name: str
    kind: str
    measurable: bool
    payload_id: Optional[str] = None
    source_uri: Optional[str] = None
    transform: Optional[Sequence[float]] = None
    geo_reference: Optional[GeoReference] = None

    def to_json(self) -> dict:
        return _drop_none(
            {
                "id": self.id,
                "name": self.name,
                "kind": self.kind,
                "measurable": self.measurable,
                "payloadId": self.payload_id,
                "sourceUri": self.source_uri,
                "transform": list(self.transform) if self.transform is not None else None,
                "geoReference": self.geo_reference.to_json() if self.geo_reference else None,
            }
        )

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "SceneRealityLayer":
        geo = data.get("geoReference")
        return SceneRealityLayer(
            id=data["id"],
            name=data["name"],
            kind=data["kind"],
            measurable=bool(data["measurable"]),
            payload_id=data.get("payloadId"),
            source_uri=data.get("sourceUri"),
            transform=data.get("transform"),
            geo_reference=GeoReference.from_json(geo) if geo else None,
        )


@dataclass(frozen=True)
class SceneSource:
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    revision: Optional[str] = None

    def to_json(self) -> dict:
        return _drop_none(
            {
                "modelId": self.model_id,
                "modelName": self.model_name,
                "revision": self.revision,
            }
        )

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "SceneSource":
        return SceneSource(
            model_id=data.get("modelId"),
            model_name=data.get("modelName"),
            revision=data.get("revision"),
        )


@dataclass(frozen=True)
class SceneIndex:
    """Lookups precomputed by the exporter, which already holds the whole model."""

    by_class: Mapping[str, Sequence[int]] = field(default_factory=dict)
    by_level: Mapping[str, Sequence[int]] = field(default_factory=dict)
    by_global_id: Mapping[str, int] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "byClass": {key: list(value) for key, value in self.by_class.items()},
            "byLevel": {key: list(value) for key, value in self.by_level.items()},
            "byGlobalId": dict(self.by_global_id),
        }

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "SceneIndex":
        return SceneIndex(
            by_class=data.get("byClass", {}),
            by_level=data.get("byLevel", {}),
            by_global_id=data.get("byGlobalId", {}),
        )


@dataclass(frozen=True)
class ScenePackage:
    """The manifest.

    Coordinates are metres throughout; ``source_units`` records what the model was authored in
    because that is provenance and losing it makes a later discrepancy impossible to explain.
    """

    generator: str
    generated_at: str
    format_version: str = SCENE_FORMAT_VERSION
    units: str = "m"
    source_units: Optional[str] = None
    geo_reference: Optional[GeoReference] = None
    sources: Sequence[SceneSource] = field(default_factory=tuple)
    payloads: Sequence[ScenePayload] = field(default_factory=tuple)
    nodes: Sequence[SceneNode] = field(default_factory=tuple)
    materials: Optional[Sequence[SceneMaterial]] = None
    properties: Optional[Mapping[str, Sequence[ScenePropertySet]]] = None
    relationships: Optional[Sequence[SceneRelationship]] = None
    reality_layers: Optional[Sequence[SceneRealityLayer]] = None
    index: SceneIndex = field(default_factory=SceneIndex)

    def to_json(self) -> dict:
        # Key order mirrors the TypeScript object literal so a diff of two manifests shows real
        # differences rather than reordering.
        data: Dict[str, Any] = {
            "formatVersion": self.format_version,
            "generator": self.generator,
            "generatedAt": self.generated_at,
            "sources": [source.to_json() for source in self.sources],
            "units": self.units,
        }
        if self.source_units is not None:
            data["sourceUnits"] = self.source_units
        if self.geo_reference is not None:
            data["geoReference"] = self.geo_reference.to_json()
        data["payloads"] = [payload.to_json() for payload in self.payloads]
        data["nodes"] = [node.to_json() for node in self.nodes]
        if self.materials is not None:
            data["materials"] = [material.to_json() for material in self.materials]
        if self.properties is not None:
            data["properties"] = {
                global_id: [entry.to_json() for entry in sets]
                for global_id, sets in self.properties.items()
            }
        if self.relationships is not None:
            data["relationships"] = [edge.to_json() for edge in self.relationships]
        if self.reality_layers is not None:
            data["realityLayers"] = [layer.to_json() for layer in self.reality_layers]
        data["index"] = self.index.to_json()
        return data

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "ScenePackage":
        geo = data.get("geoReference")
        materials = data.get("materials")
        properties = data.get("properties")
        relationships = data.get("relationships")
        layers = data.get("realityLayers")
        return ScenePackage(
            format_version=data["formatVersion"],
            generator=data.get("generator", ""),
            generated_at=data.get("generatedAt", ""),
            units=data.get("units", "m"),
            source_units=data.get("sourceUnits"),
            geo_reference=GeoReference.from_json(geo) if geo else None,
            sources=[SceneSource.from_json(entry) for entry in data.get("sources", [])],
            payloads=[ScenePayload.from_json(entry) for entry in data.get("payloads", [])],
            nodes=[SceneNode.from_json(entry) for entry in data.get("nodes", [])],
            materials=(
                [SceneMaterial.from_json(entry) for entry in materials]
                if materials is not None
                else None
            ),
            properties=(
                {
                    global_id: [ScenePropertySet.from_json(entry) for entry in sets]
                    for global_id, sets in properties.items()
                }
                if properties is not None
                else None
            ),
            relationships=(
                [SceneRelationship.from_json(entry) for entry in relationships]
                if relationships is not None
                else None
            ),
            reality_layers=(
                [SceneRealityLayer.from_json(entry) for entry in layers]
                if layers is not None
                else None
            ),
            index=SceneIndex.from_json(data.get("index", {})),
        )


class ScenePackageError(Exception):
    """Raised when a package cannot be built or read.

    Python's idiom is an exception where the TypeScript side returns a ``Result``; the boundary is
    the language, not the behaviour, and both refuse rather than guess.
    """
