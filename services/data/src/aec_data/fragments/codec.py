"""Read and write `.frag` — `zlib(flatbuffers)` — against the layout in `schema.py`.

The reader exists for the conformance gate (it is how one file is compared against another) and is
useful on its own for inspecting a converted model without a browser. The writer is the half the
desktop app needs.

**Both directions are here on purpose.** A writer with no reader can only be checked by another
program; a reader beside it means the round trip is testable in one process, and a malformed buffer
is caught where it is produced rather than three layers away in a viewer that just draws nothing.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

import flatbuffers

from . import schema as S


# --------------------------------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------------------------------
class Table:
    """A FlatBuffers table cursor: a buffer plus the position of one table."""

    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes, pos: int):
        self.buf, self.pos = buf, pos

    # -- primitives --------------------------------------------------------------------------------
    def _u16(self, o: int) -> int: return struct.unpack_from("<H", self.buf, o)[0]
    def _i32(self, o: int) -> int: return struct.unpack_from("<i", self.buf, o)[0]
    def _u32(self, o: int) -> int: return struct.unpack_from("<I", self.buf, o)[0]

    def _slot(self, slot: int) -> int:
        """Byte offset of `slot` from this table's start, or 0 when the field is absent.

        A vtable shorter than the slot means the field did not exist when the file was written —
        which is how FlatBuffers stays forward-compatible, and why this returns 0 rather than
        indexing off the end.
        """
        vt = self.pos - self._i32(self.pos)
        return self._u16(vt + slot) if slot < self._u16(vt) else 0

    def _indirect(self, o: int) -> int: return o + self._i32(o)

    # -- typed field access ------------------------------------------------------------------------
    def scalar(self, slot: int, fmt: str, default=0):
        o = self._slot(slot)
        return struct.unpack_from(fmt, self.buf, self.pos + o)[0] if o else default

    def string(self, slot: int) -> str | None:
        o = self._slot(slot)
        if not o:
            return None
        s = self._indirect(self.pos + o)
        return self.buf[s + 4:s + 4 + self._u32(s)].decode("utf8", "replace")

    def table(self, slot: int) -> Table | None:
        o = self._slot(slot)
        return Table(self.buf, self._indirect(self.pos + o)) if o else None

    def _vector(self, slot: int) -> tuple[int, int]:
        """`(first_element_offset, count)` — `(0, 0)` when absent."""
        o = self._slot(slot)
        if not o:
            return 0, 0
        v = self._indirect(self.pos + o)
        return v + 4, self._u32(v)

    def vec_len(self, slot: int) -> int:
        return self._vector(slot)[1]

    def vec_scalar(self, slot: int, fmt: str, stride: int) -> list:
        base, n = self._vector(slot)
        return [struct.unpack_from(fmt, self.buf, base + i * stride)[0] for i in range(n)]

    def vec_string(self, slot: int) -> list[str]:
        base, n = self._vector(slot)
        out = []
        for i in range(n):
            s = self._indirect(base + i * 4)
            out.append(self.buf[s + 4:s + 4 + self._u32(s)].decode("utf8", "replace"))
        return out

    def vec_table(self, slot: int) -> list[Table]:
        base, n = self._vector(slot)
        return [Table(self.buf, self._indirect(base + i * 4)) for i in range(n)]

    def vec_struct(self, slot: int, stride: int) -> list[int]:
        """Byte offsets of each inline struct. Structs have no vtable, so the caller unpacks."""
        base, n = self._vector(slot)
        return [base + i * stride for i in range(n)]


def _triples(buf: bytes, off: int, fmt: str) -> tuple[float, float, float]:
    return struct.unpack_from(fmt, buf, off)


@dataclass
class Mesh:
    """One shell: its vertices and the index loops around each face."""

    points: list[tuple[float, float, float]] = field(default_factory=list)
    profiles: list[list[int]] = field(default_factory=list)
    #: `Representation.representation_class` for this shell. Read back so a writer that misplaces
    #: it is caught HERE rather than by a viewer drawing nothing -- which is what happened: the
    #: first draft put this byte at offset 31 and the round-trip stayed green because this field
    #: did not exist to be compared.
    representation_class: int = 0

    def bbox(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        xs = [p[0] for p in self.points]; ys = [p[1] for p in self.points]; zs = [p[2] for p in self.points]
        if not xs:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


@dataclass
class FragModel:
    """The parts of a `.frag` this codec round-trips. Deliberately a subset, and it says so.

    `attributes`, `relations` and `spatial_structure` are read as COUNTS only: the desktop path
    serves element data from the API's own database, not from the fragment, so re-encoding them
    would be duplicating a store rather than filling a gap. The conformance gate asserts on what is
    here; it must not silently imply the rest was checked.
    """

    guid: str = ""
    metadata: str = ""
    guids: list[str] = field(default_factory=list)
    guids_items: list[int] = field(default_factory=list)
    local_ids: list[int] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    max_local_id: int = 0
    coordinates: tuple[float, float, float] = (0.0, 0.0, 0.0)
    meshes_items: list[int] = field(default_factory=list)
    meshes: list[Mesh] = field(default_factory=list)
    #: counts of the parts this codec does not re-encode — see the class docstring
    attribute_count: int = 0
    relation_count: int = 0


def loads(data: bytes) -> FragModel:
    """Parse `.frag` bytes. Raises on anything that is not a fragment rather than returning empty."""
    if not data:
        raise ValueError("empty .frag")
    try:
        raw = zlib.decompress(data)
    except zlib.error as e:                      # not a fragment, or truncated
        raise ValueError(f"not a zlib-wrapped fragment: {e}") from e
    root = Table(raw, struct.unpack_from("<i", raw, 0)[0])
    m = FragModel(
        guid=root.string(S.MODEL["guid"]) or "",
        metadata=root.string(S.MODEL["metadata"]) or "",
        guids=root.vec_string(S.MODEL["guids"]),
        guids_items=root.vec_scalar(S.MODEL["guids_items"], "<I", 4),
        local_ids=root.vec_scalar(S.MODEL["local_ids"], "<I", 4),
        categories=root.vec_string(S.MODEL["categories"]),
        max_local_id=root.scalar(S.MODEL["max_local_id"], "<I"),
        attribute_count=root.vec_len(S.MODEL["attributes"]),
        relation_count=root.vec_len(S.MODEL["relations"]),
    )
    meshes = root.table(S.MODEL["meshes"])
    if meshes is None:
        return m
    m.meshes_items = meshes.vec_scalar(S.MESHES["meshes_items"], "<I", 4)
    co = meshes.table(S.MESHES["coordinates"])
    if co is not None:
        m.coordinates = _triples(raw, co.pos, "<ddd")
    rep_offsets = meshes.vec_struct(S.MESHES["representations"], S.REPRESENTATION_STRIDE)
    for i, shell in enumerate(meshes.vec_table(S.MESHES["shells"])):
        mesh = Mesh()
        if i < len(rep_offsets):
            mesh.representation_class = struct.unpack_from(
                "<b", raw, rep_offsets[i] + S.REPRESENTATION["representation_class"])[0]
        for off in shell.vec_struct(S.SHELL["points"], S.FLOAT_VECTOR_STRIDE):
            mesh.points.append(_triples(raw, off, "<fff"))
        for prof in shell.vec_table(S.SHELL["profiles"]):
            mesh.profiles.append(prof.vec_scalar(S.SHELL_PROFILE["indices"], "<H", 2))
        m.meshes.append(mesh)
    return m


# --------------------------------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------------------------------
def _prepend_struct_vector(b: flatbuffers.Builder, count: int, stride: int, writer) -> int:
    """Lay out `count` inline structs back-to-front, as FlatBuffers requires, and return the offset.

    The builder grows downwards, so vectors are written last element first. `writer(i)` is called
    with each index in REVERSE order and must emit that struct's bytes, itself back-to-front.
    """
    b.StartVector(stride, count, 4)
    for i in range(count - 1, -1, -1):
        writer(i)
    return b.EndVector()


def dumps(m: FragModel, *, compress: bool = True) -> bytes:
    """Serialise a `FragModel` to `.frag` bytes.

    Field order below is dictated by FlatBuffers, not by taste: every nested object and vector must
    be finished BEFORE the table that references it is started, so this reads inside-out.
    """
    b = flatbuffers.Builder(1024)

    # --- strings and leaf vectors first -----------------------------------------------------------
    guid_off = b.CreateString(m.guid)
    meta_off = b.CreateString(m.metadata)
    guid_strs = [b.CreateString(g) for g in m.guids]
    cat_strs = [b.CreateString(c) for c in m.categories]

    def _offset_vector(offsets: list[int]) -> int:
        b.StartVector(4, len(offsets), 4)
        for o in reversed(offsets):
            b.PrependUOffsetTRelative(o)
        return b.EndVector()

    def _u32_vector(values: list[int]) -> int:
        b.StartVector(4, len(values), 4)
        for v in reversed(values):
            b.PrependUint32(v)
        return b.EndVector()

    guids_vec = _offset_vector(guid_strs)
    cats_vec = _offset_vector(cat_strs)
    guids_items_vec = _u32_vector(m.guids_items)
    local_ids_vec = _u32_vector(m.local_ids)

    # --- shells (tables) --------------------------------------------------------------------------
    shell_offsets = []
    for mesh in m.meshes:
        prof_offsets = []
        for loop in mesh.profiles:
            b.StartVector(2, len(loop), 2)
            for idx in reversed(loop):
                b.PrependUint16(idx)
            idx_vec = b.EndVector()
            b.StartObject(S.SHELL_PROFILE_FIELDS)
            b.PrependUOffsetTRelativeSlot(0, idx_vec, 0)
            prof_offsets.append(b.EndObject())
        profiles_vec = _offset_vector(prof_offsets)

        pts = mesh.points
        def _pt(i: int, pts=pts) -> None:
            x, y, z = pts[i]
            b.PrependFloat32(z); b.PrependFloat32(y); b.PrependFloat32(x)
        points_vec = _prepend_struct_vector(b, len(pts), S.FLOAT_VECTOR_STRIDE, _pt)

        b.StartObject(S.SHELL_FIELDS)
        b.PrependUOffsetTRelativeSlot(0, profiles_vec, 0)   # profiles
        b.PrependUOffsetTRelativeSlot(2, points_vec, 0)     # points
        shell_offsets.append(b.EndObject())
    shells_vec = _offset_vector(shell_offsets)

    # --- the per-instance struct vectors ----------------------------------------------------------
    n = len(m.meshes)

    def _sample(i: int) -> None:
        b.PrependUint32(i)   # local_transform
        b.PrependUint32(i)   # representation
        b.PrependUint32(0)   # material
        b.PrependUint32(i)   # item
    samples_vec = _prepend_struct_vector(b, n, S.SAMPLE_STRIDE, _sample)

    def _representation(i: int) -> None:
        # **Back-to-front, and the padding goes FIRST.** A struct is laid out by prepending, so the
        # highest byte offset is written first: the 3 tail bytes, then `representation_class` at 28,
        # then the bbox, then the id at 0. Writing the class before the padding puts it at offset 31
        # and leaves 28 zero -- the reference reader then reports class 0 (a point cloud) for a
        # shell, and NOTHING here notices, because this file's own reader does not read that field.
        # Caught by parsing the output with the real `@thatopen/fragments` reader; the round-trip
        # through `loads()` was green with the bytes in the wrong place.
        lo, hi = m.meshes[i].bbox()
        b.Pad(3)                                   # tail padding to the 32-byte stride
        b.PrependInt8(S.REPRESENTATION_CLASS_SHELL)
        b.PrependFloat32(hi[2]); b.PrependFloat32(hi[1]); b.PrependFloat32(hi[0])
        b.PrependFloat32(lo[2]); b.PrependFloat32(lo[1]); b.PrependFloat32(lo[0])
        b.PrependUint32(i)                         # id
    reps_vec = _prepend_struct_vector(b, n, S.REPRESENTATION_STRIDE, _representation)

    def _material(_i: int) -> None:
        b.PrependInt8(0)      # stroke
        b.PrependInt8(0)      # rendered_faces
        b.PrependUint8(255); b.PrependUint8(180); b.PrependUint8(180); b.PrependUint8(180)  # a,b,g,r
    materials_vec = _prepend_struct_vector(b, 1, S.MATERIAL_STRIDE, _material)

    def _identity_transform(_i: int) -> None:
        b.PrependFloat32(0.0); b.PrependFloat32(1.0); b.PrependFloat32(0.0)   # y direction
        b.PrependFloat32(0.0); b.PrependFloat32(0.0); b.PrependFloat32(1.0)   # x direction
        b.PrependFloat64(0.0); b.PrependFloat64(0.0); b.PrependFloat64(0.0)   # position
    local_vec = _prepend_struct_vector(b, n, S.TRANSFORM_STRIDE, _identity_transform)
    global_vec = _prepend_struct_vector(b, n, S.TRANSFORM_STRIDE, _identity_transform)

    meshes_items_vec = _u32_vector(m.meshes_items)

    # --- Meshes ------------------------------------------------------------------------------------
    b.StartObject(S.MESHES_FIELDS)
    b.PrependUOffsetTRelativeSlot(1, meshes_items_vec, 0)
    b.PrependUOffsetTRelativeSlot(2, samples_vec, 0)
    b.PrependUOffsetTRelativeSlot(3, reps_vec, 0)
    b.PrependUOffsetTRelativeSlot(4, materials_vec, 0)
    b.PrependUOffsetTRelativeSlot(6, shells_vec, 0)
    b.PrependUOffsetTRelativeSlot(7, local_vec, 0)
    b.PrependUOffsetTRelativeSlot(8, global_vec, 0)
    meshes_off = b.EndObject()

    # --- Model (root) ------------------------------------------------------------------------------
    b.StartObject(S.MODEL_FIELDS)
    b.PrependUOffsetTRelativeSlot(0, meta_off, 0)
    b.PrependUOffsetTRelativeSlot(1, guids_vec, 0)
    b.PrependUOffsetTRelativeSlot(2, guids_items_vec, 0)
    b.PrependUint32Slot(3, m.max_local_id, 0)
    b.PrependUOffsetTRelativeSlot(4, local_ids_vec, 0)
    b.PrependUOffsetTRelativeSlot(5, cats_vec, 0)
    b.PrependUOffsetTRelativeSlot(6, meshes_off, 0)
    b.PrependUOffsetTRelativeSlot(10, guid_off, 0)
    root = b.EndObject()

    b.Finish(root)
    out = bytes(b.Output())
    return zlib.compress(out) if compress else out
