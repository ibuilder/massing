"""``massingifc_scene`` — the scene package format, in Python.

A second implementation of what ``@massingifc/engine-bridge`` defines. The format claims a consumer
needs nothing but a JSON parser and a file handle; this package is what turns that from a claim
into a fact, and the conformance suite checks the two agree byte for byte.

Dependency-free on purpose — stdlib only. An importer that drags a dependency tree behind it is
not one you can drop into a Blender addon, a CI check or an engine build step.
"""

from .build import (
    SceneIssue,
    SceneValidationReport,
    build_scene_package,
    validate_scene_package,
)
from .codec import (
    DirectoryArchive,
    MemoryArchive,
    SceneArchive,
    ZipArchive,
    content_hash,
    payload_path,
    read_payload,
    read_scene_package,
    safe_payload_path,
    write_scene_package,
)
from .geo import METRES_PER_UNIT, GeoAccuracy, GeoReference, convert_length, parse_crs_code
from .importer import ImportedElement, SceneImporter
from .model import (
    FRAGMENTS_ENCODING,
    SCENE_FORMAT_VERSION,
    SCENE_MANIFEST_PATH,
    SCENE_PAYLOAD_DIRECTORY,
    SceneIndex,
    SceneMaterial,
    SceneNode,
    ScenePackage,
    ScenePackageError,
    ScenePayload,
    ScenePropertySet,
    SceneRealityLayer,
    SceneRelationship,
    SceneSource,
)

__all__ = [
    "FRAGMENTS_ENCODING",
    "METRES_PER_UNIT",
    "SCENE_FORMAT_VERSION",
    "SCENE_MANIFEST_PATH",
    "SCENE_PAYLOAD_DIRECTORY",
    "DirectoryArchive",
    "GeoAccuracy",
    "GeoReference",
    "ImportedElement",
    "MemoryArchive",
    "SceneArchive",
    "SceneImporter",
    "SceneIndex",
    "SceneIssue",
    "SceneMaterial",
    "SceneNode",
    "ScenePackage",
    "ScenePackageError",
    "ScenePayload",
    "ScenePropertySet",
    "SceneRealityLayer",
    "SceneRelationship",
    "SceneSource",
    "SceneValidationReport",
    "ZipArchive",
    "build_scene_package",
    "content_hash",
    "convert_length",
    "parse_crs_code",
    "payload_path",
    "read_payload",
    "read_scene_package",
    "safe_payload_path",
    "validate_scene_package",
    "write_scene_package",
]
