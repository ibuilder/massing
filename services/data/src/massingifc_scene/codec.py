"""Reading and writing packages.

The archive is a protocol rather than a concrete type for the same reason as the TypeScript side: a
package is a directory or a ZIP depending on where it is going, and compression belongs to whoever
knows the environment. A directory implementation and a ZIP implementation both ship here because
in Python both are one stdlib call away, and refusing to provide them would be pedantry.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Protocol

from .model import (
    SCENE_FORMAT_VERSION,
    SCENE_MANIFEST_PATH,
    SCENE_PAYLOAD_DIRECTORY,
    ScenePackage,
    ScenePackageError,
)

_SAFE_CHARACTERS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
)


class SceneArchive(Protocol):
    """Path-and-bytes access to a package."""

    def entries(self) -> Iterable[str]: ...

    def read(self, path: str) -> Optional[bytes]: ...

    def write(self, path: str, data: bytes) -> None: ...


class MemoryArchive:
    """An in-memory package. Useful for tests and for streaming straight to a response."""

    def __init__(self, files: Optional[Mapping[str, bytes]] = None) -> None:
        self.files: Dict[str, bytes] = dict(files or {})

    def entries(self) -> Iterable[str]:
        return sorted(self.files)

    def read(self, path: str) -> Optional[bytes]:
        return self.files.get(path)

    def write(self, path: str, data: bytes) -> None:
        self.files[path] = data


class DirectoryArchive:
    """A package as a directory on disk."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def entries(self) -> Iterable[str]:
        if not self.root.exists():
            return []
        return sorted(
            str(path.relative_to(self.root)).replace("\\", "/")
            for path in self.root.rglob("*")
            if path.is_file()
        )

    def read(self, path: str) -> Optional[bytes]:
        target = self._resolve(path)
        return target.read_bytes() if target.is_file() else None

    def write(self, path: str, data: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def _resolve(self, path: str) -> Path:
        safe = safe_payload_path(path)
        if safe is None:
            raise ScenePackageError(f"Refusing a path outside the package: {path!r}")
        # Belt and braces: `safe_payload_path` already rejects traversal, but this archive touches
        # a real filesystem, so the containment is also enforced against the resolved path.
        target = (self.root / safe).resolve()
        root = self.root.resolve()
        if root != target and root not in target.parents:
            raise ScenePackageError(f"Refusing a path outside the package: {path!r}")
        return target


class ZipArchive:
    """A package as a ZIP file. Read-only unless opened for writing."""

    def __init__(self, path: Path, mode: str = "r") -> None:
        self._zip = zipfile.ZipFile(Path(path), mode)

    def entries(self) -> Iterable[str]:
        return sorted(self._zip.namelist())

    def read(self, path: str) -> Optional[bytes]:
        try:
            return self._zip.read(path)
        except KeyError:
            return None

    def write(self, path: str, data: bytes) -> None:
        self._zip.writestr(path, data)

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "ZipArchive":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def safe_payload_path(path: str) -> Optional[str]:
    """Normalise a package-relative path, refusing any that escapes the package.

    Paths in a manifest are file *content*, not caller input, and a package can arrive from
    anywhere. ``../../../.ssh/id_rsa`` handed to a filesystem archive reads — or on write,
    clobbers — a file outside the package.
    """
    normalised = path.replace("\\", "/")
    # Absoluteness is tested before any stripping: removing a leading slash first would quietly
    # turn "/etc/passwd" into a package-relative path and read a different file than was asked for.
    if not normalised or normalised.startswith("/"):
        return None
    if len(normalised) >= 2 and normalised[1] == ":" and normalised[0].isalpha():
        return None
    if normalised.startswith("./"):
        normalised = normalised[2:]
    segments = normalised.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        return None
    return "/".join(segments)


def payload_path(payload_id: str, extension: str = "bin") -> str:
    """Package-relative path for a payload id, percent-encoding anything unsafe in a file name."""
    encoded = []
    for character in payload_id:
        if character in _SAFE_CHARACTERS:
            encoded.append(character)
        else:
            encoded.extend(f"%{byte:02X}" for byte in character.encode("utf-8"))
    safe = "".join(encoded) or "%"
    return f"{SCENE_PAYLOAD_DIRECTORY}/{safe}.{extension}"


def content_hash(data: bytes) -> str:
    """FNV-1a over the bytes, matching the TypeScript implementation exactly.

    An identity key so an incremental sync can skip unchanged payloads — explicitly not a digest,
    and not a security check. It has to agree across implementations or a Python-written package
    would look changed to a TypeScript reader and be needlessly re-fetched.
    """
    value = 0x811C9DC5
    for byte in data:
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return f"fnv1a-{_base36(value)}"


def _base36(value: int) -> str:
    """Match JavaScript's ``Number.prototype.toString(36)`` for a non-negative integer."""
    if value == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while value:
        value, remainder = divmod(value, 36)
        out = digits[remainder] + out
    return out


def write_scene_package(
    archive: SceneArchive,
    scene: ScenePackage,
    payloads: Optional[Mapping[str, bytes]] = None,
) -> None:
    """Write a manifest and its payloads.

    Manifest and payloads stay separate files: a consumer wants to parse a small JSON document and
    then stream or memory-map geometry it may never fully load.
    """
    supplied = dict(payloads or {})

    for payload in scene.payloads:
        data = supplied.get(payload.id)
        if data is None:
            raise ScenePackageError(f"No bytes supplied for payload {payload.id!r}.")
        if len(data) != payload.byte_length:
            # A declared length that disagrees with the bytes means a consumer reading by offset
            # gets garbage, and it will blame the geometry rather than the manifest.
            raise ScenePackageError(
                f"Payload {payload.id!r} declares {payload.byte_length} bytes "
                f"but {len(data)} were supplied."
            )
        safe = safe_payload_path(payload.path)
        if safe is None:
            raise ScenePackageError(
                f"Payload {payload.id!r} declares a path outside the package: {payload.path!r}"
            )
        archive.write(safe, data)

    manifest = json.dumps(scene.to_json(), indent=2, ensure_ascii=False)
    archive.write(SCENE_MANIFEST_PATH, manifest.encode("utf-8"))


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def read_scene_package(archive: SceneArchive) -> ScenePackage:
    """Read and validate a manifest.

    Refuses a major version it does not know rather than reading the parts it recognises: a
    partially understood scene loads looking correct with pieces missing, and nothing says so.
    """
    raw = archive.read(SCENE_MANIFEST_PATH)
    if raw is None:
        raise ScenePackageError(f'Package has no "{SCENE_MANIFEST_PATH}".')

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScenePackageError("Scene manifest is not valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise ScenePackageError("Scene manifest is not an object.")

    version = parsed.get("formatVersion")
    if not isinstance(version, str):
        raise ScenePackageError("Scene manifest declares no format version.")
    if _major(version) != _major(SCENE_FORMAT_VERSION):
        raise ScenePackageError(
            f"Scene format {version} cannot be read by a {SCENE_FORMAT_VERSION} reader."
        )

    if not isinstance(parsed.get("nodes"), list):
        raise ScenePackageError("Scene manifest is missing its nodes.")

    index = parsed.get("index")
    # Checked in full because consumers read `byGlobalId` without guarding: an index that merely
    # exists lets the reader succeed and the first lookup fail.
    if not isinstance(index, dict) or not all(
        isinstance(index.get(key), dict) for key in ("byClass", "byLevel", "byGlobalId")
    ):
        raise ScenePackageError("Scene manifest has no usable index.")

    # Value types too, not just the shape: a string position is accepted by every check above
    # and then fails as a bare TypeError deep inside a consumer that indexed with it.
    if any(
        isinstance(position, bool) or not isinstance(position, int)
        for position in index["byGlobalId"].values()
    ):
        raise ScenePackageError(
            "Scene manifest has a non-integer position in its byGlobalId index."
        )

    return ScenePackage.from_json(parsed)


def read_payload(archive: SceneArchive, scene: ScenePackage, payload_id: str) -> Optional[bytes]:
    """Read one payload's bytes, refusing a path that escapes the package."""
    for payload in scene.payloads:
        if payload.id != payload_id:
            continue
        safe = safe_payload_path(payload.path)
        return None if safe is None else archive.read(safe)
    return None
