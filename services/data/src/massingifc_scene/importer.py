"""The engine-side importer.

This is the consumer half of the format, and it is deliberately written as the reference an engine
integration is ported *from*. An Unreal C++ plugin or a Unity C# importer will not call this code,
but it will have to make the same decisions, and having them written down once — with tests —
means every native implementation has something concrete to agree with instead of prose.

The rules that matter, in the order they bite:

1. **Address by GlobalId, never by array position or runtime id.** Positions shift between
   revisions; a GlobalId does not. ``transient_local_id`` is carried for debugging and is not a key.
2. **Trust the manifest's indexes, but verify them once.** They are precomputed so a consumer does
   not rebuild them on every load, which on a federated model is a visible pause. A stale index is
   worse than none, so ``verify`` exists and ``check_index`` is on by default.
3. **Do not eagerly load geometry.** ``payload_id`` is a reference; the bytes are fetched when the
   consumer wants them. Fragments is designed for models that do not fit in memory at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, List, Mapping, Optional, Sequence

from .codec import SceneArchive, read_payload, read_scene_package
from .model import (
    ScenePackage,
    ScenePackageError,
    SceneNode,
    ScenePropertySet,
    SceneRealityLayer,
    SceneRelationship,
)


@dataclass(frozen=True)
class ImportedElement:
    """What an engine actor or game object needs to carry to stay a BIM object.

    These six fields are the metadata bridge: an element selected in the engine can be traced back
    to the model it came from, and an issue raised against it means something in every other tool.
    """

    global_id: str
    name: Optional[str]
    ifc_class: Optional[str]
    level_global_id: Optional[str]
    payload_id: Optional[str]
    source_system: str = "massingifc"

    @staticmethod
    def of(node: SceneNode, source_system: str = "massingifc") -> "ImportedElement":
        return ImportedElement(
            global_id=node.global_id,
            name=node.name,
            ifc_class=node.ifc_class,
            level_global_id=node.level_global_id,
            payload_id=node.payload_id,
            source_system=source_system,
        )


class SceneImporter:
    """Reads a package and answers the questions an engine runtime asks at interaction time."""

    def __init__(
        self,
        scene: ScenePackage,
        archive: Optional[SceneArchive] = None,
        *,
        check_index: bool = True,
    ) -> None:
        self.scene = scene
        self._archive = archive
        if check_index:
            self.verify()

        # Children and relationship edges are derived once here rather than stored in the manifest:
        # both are exactly recoverable from the parent links and the edge list, and a second copy
        # in the file is a second thing that can disagree with the first.
        self._children: Dict[str, List[SceneNode]] = {}
        for node in scene.nodes:
            if node.parent_global_id is not None:
                self._children.setdefault(node.parent_global_id, []).append(node)

        self._edges: Dict[str, List[SceneRelationship]] = {}
        for edge in scene.relationships or ():
            self._edges.setdefault(edge.from_global_id, []).append(edge)
            self._edges.setdefault(edge.to_global_id, []).append(edge)

    # -- construction ---------------------------------------------------------------------

    @staticmethod
    def open(archive: SceneArchive, *, check_index: bool = True) -> "SceneImporter":
        """Read a package from an archive and prepare it for querying."""
        return SceneImporter(read_scene_package(archive), archive, check_index=check_index)

    # -- integrity ------------------------------------------------------------------------

    def verify(self) -> None:
        """Fail loudly on an index that disagrees with the nodes.

        Consumers trust the index; if it is stale, selection silently picks the wrong element,
        which is far harder to notice than a package that refused to load.
        """
        nodes = self.scene.nodes
        for global_id, position in self.scene.index.by_global_id.items():
            if not isinstance(position, int) or position < 0 or position >= len(nodes):
                raise ScenePackageError(
                    f"Index entry for {global_id!r} points outside the node list."
                )
            if nodes[position].global_id != global_id:
                raise ScenePackageError(
                    f"Index entry for {global_id!r} points at position {position}, "
                    "which holds a different node."
                )

    # -- identity -------------------------------------------------------------------------

    def node(self, global_id: str) -> Optional[SceneNode]:
        position = self.scene.index.by_global_id.get(global_id)
        if position is None:
            return None
        return self.scene.nodes[position]

    def element(self, global_id: str) -> Optional[ImportedElement]:
        node = self.node(global_id)
        return None if node is None else ImportedElement.of(node)

    def elements(self) -> Iterator[ImportedElement]:
        for node in self.scene.nodes:
            yield ImportedElement.of(node)

    def __len__(self) -> int:
        return len(self.scene.nodes)

    def __contains__(self, global_id: object) -> bool:
        return isinstance(global_id, str) and global_id in self.scene.index.by_global_id

    # -- filtering ------------------------------------------------------------------------

    def by_class(self, ifc_class: str) -> List[SceneNode]:
        return self._resolve(self.scene.index.by_class.get(ifc_class))

    def by_level(self, level_global_id: str) -> List[SceneNode]:
        return self._resolve(self.scene.index.by_level.get(level_global_id))

    def classes(self) -> List[str]:
        return sorted(self.scene.index.by_class)

    def levels(self) -> List[str]:
        return sorted(self.scene.index.by_level)

    def _resolve(self, positions: Optional[Sequence[int]]) -> List[SceneNode]:
        nodes = self.scene.nodes
        return [nodes[position] for position in positions or () if 0 <= position < len(nodes)]

    # -- hierarchy ------------------------------------------------------------------------

    def children(self, global_id: str) -> List[SceneNode]:
        return list(self._children.get(global_id, ()))

    def ancestors(self, global_id: str) -> List[SceneNode]:
        """Ancestors nearest-first, stopping at the package boundary."""
        chain: List[SceneNode] = []
        visited = {global_id}
        node = self.node(global_id)
        current = node.parent_global_id if node else None
        while current is not None and current not in visited:
            # A spatial tree should not contain a cycle, but a malformed export must produce a
            # short list rather than hang the importer that trusted it.
            visited.add(current)
            parent = self.node(current)
            if parent is None:
                break
            chain.append(parent)
            current = parent.parent_global_id
        return chain

    def descendants(self, global_id: str) -> Iterator[SceneNode]:
        stack = list(self._children.get(global_id, ()))
        seen = set()
        while stack:
            node = stack.pop()
            if node.global_id in seen:
                continue
            seen.add(node.global_id)
            yield node
            stack.extend(self._children.get(node.global_id, ()))

    # -- semantics ------------------------------------------------------------------------

    def property_sets(self, global_id: str) -> List[ScenePropertySet]:
        return list((self.scene.properties or {}).get(global_id, ()))

    def property(
        self, global_id: str, name: str, set_name: Optional[str] = None
    ) -> Optional[object]:
        """Read one property, searching every set when no set name is given."""
        for entry in self.property_sets(global_id):
            if set_name is not None and entry.name != set_name:
                continue
            if name in entry.properties:
                return entry.properties[name]
        return None

    def relationships(
        self, global_id: str, type: Optional[str] = None
    ) -> List[SceneRelationship]:
        edges = self._edges.get(global_id, ())
        return [edge for edge in edges if type is None or edge.type == type]

    def reality_layers(self, *, measurable_only: bool = False) -> List[SceneRealityLayer]:
        layers = list(self.scene.reality_layers or ())
        # The flag exists so a consumer does not offer a dimension tool over a radiance field.
        return [layer for layer in layers if layer.measurable] if measurable_only else layers

    # -- geometry -------------------------------------------------------------------------

    def payload_bytes(self, payload_id: str) -> Optional[bytes]:
        """Fetch a payload on demand. Never called during import — geometry is not eager."""
        if self._archive is None:
            raise ScenePackageError(
                "This importer was built from a manifest alone and has no archive to read from."
            )
        return read_payload(self._archive, self.scene, payload_id)

    def geometry_for(self, global_id: str) -> Optional[bytes]:
        node = self.node(global_id)
        if node is None or node.payload_id is None:
            return None
        return self.payload_bytes(node.payload_id)

    def payload_ids(self) -> List[str]:
        return [payload.id for payload in self.scene.payloads]

    # -- placement ------------------------------------------------------------------------

    def units(self) -> str:
        """Always metres. Present so a consumer can assert rather than assume.

        A method rather than a ``@property``: this class defines ``property()`` to mirror the
        format's query API, which shadows the builtin decorator inside the class body. Anything
        added here has to be a plain method for the same reason.
        """
        return self.scene.units

    def origin_offset(self) -> Sequence[float]:
        """The offset subtracted from world coordinates, in metres.

        A consumer reconstructs true position as ``local + origin_offset``. Returned as zeros when
        the package is not georeferenced so the arithmetic is uniform either way.
        """
        geo = self.scene.geo_reference
        if geo is None or geo.origin_offset is None:
            return (0.0, 0.0, 0.0)
        return tuple(geo.origin_offset)

    def summary(self) -> Mapping[str, object]:
        """A one-glance description, for logs and for a smoke test after import."""
        return {
            "nodes": len(self.scene.nodes),
            "classes": len(self.scene.index.by_class),
            "levels": len(self.scene.index.by_level),
            "payloads": len(self.scene.payloads),
            "withProperties": len(self.scene.properties or {}),
            "relationships": len(self.scene.relationships or ()),
            "realityLayers": len(self.scene.reality_layers or ()),
            "units": self.scene.units,
            "crs": self.scene.geo_reference.source_crs if self.scene.geo_reference else None,
        }
