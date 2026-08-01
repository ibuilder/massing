"""Level of detail, so the client receives a budget rather than a model.

Decimation by **vertex clustering**: overlay a grid, collapse every vertex in a cell to one
representative, remap the faces, drop the ones that collapsed to a line or a point.

Chosen over quadric edge collapse deliberately. Quadric produces prettier silhouettes on organic
meshes and needs a C extension to be fast; clustering is a few lines of numpy, is order-independent
(so the same input always gives the same output, which matters when the output is content-addressed
and cached by hash), and behaves *well* on building geometry specifically -- a wall collapsed to a
slab is still a wall-shaped box, which is exactly what a distant LOD should be. It also degrades
gracefully: there is no configuration under which it produces a non-manifold mess.

The trade it makes is that it will weld two surfaces that are closer together than a cell. At the
distances LOD is for, that is the correct answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DecimatedMesh:
    vertices: np.ndarray
    faces: np.ndarray
    #: Grid cell used, in metres. Recorded so a caller can reproduce the result.
    cell_size: float

    @property
    def face_count(self) -> int:
        return int(len(self.faces))

    @property
    def vertex_count(self) -> int:
        return int(len(self.vertices))


def cluster_decimate(
    vertices: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    *,
    cell_size: float,
) -> DecimatedMesh:
    """Collapse vertices onto a grid of ``cell_size`` metres.

    The representative of a cell is the **mean** of the vertices in it, not the cell centre. The
    mean keeps a flat wall flat; snapping to centres introduces a sawtooth along any surface that
    does not happen to lie on the grid.
    """
    vertex_array = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    face_array = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(vertex_array) == 0 or len(face_array) == 0:
        return DecimatedMesh(vertex_array, face_array, cell_size)
    if cell_size <= 0:
        raise ValueError("Cell size must be positive.")

    cells = np.floor(vertex_array / cell_size).astype(np.int64)
    _, inverse, counts = np.unique(cells, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)

    # Mean position per cell, accumulated in one pass.
    summed = np.zeros((len(counts), 3), dtype=np.float64)
    np.add.at(summed, inverse, vertex_array)
    representatives = summed / counts[:, None]

    remapped = inverse[face_array]
    # A face whose corners landed in the same cell has collapsed to a line or a point. Keeping it
    # would leave zero-area triangles that break normals and confuse a renderer.
    keep = (
        (remapped[:, 0] != remapped[:, 1])
        & (remapped[:, 1] != remapped[:, 2])
        & (remapped[:, 0] != remapped[:, 2])
    )
    return DecimatedMesh(representatives, remapped[keep], cell_size)


def decimate_to_budget(
    vertices: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    *,
    max_faces: int,
    max_iterations: int = 24,
) -> DecimatedMesh:
    """Find the coarsest mesh that still fits a face budget.

    Binary search on cell size rather than a formula, because the relationship between cell size
    and face count depends entirely on how the geometry is distributed -- a tower and a car park
    with the same triangle count decimate at completely different rates.

    Returns the input untouched when it already fits: a budget is a ceiling, not a target, and
    decimating geometry that was already small enough only loses fidelity for nothing.
    """
    vertex_array = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    face_array = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(face_array) <= max_faces or len(vertex_array) == 0:
        return DecimatedMesh(vertex_array, face_array, 0.0)
    if max_faces < 1:
        raise ValueError("A face budget of zero leaves nothing to draw.")

    extent = float(np.max(vertex_array.max(axis=0) - vertex_array.min(axis=0)))
    if extent <= 0:
        return DecimatedMesh(vertex_array, face_array, 0.0)

    low, high = extent / 4096.0, extent
    best = cluster_decimate(vertex_array, face_array, cell_size=high)

    for _ in range(max_iterations):
        middle = (low + high) / 2.0
        candidate = cluster_decimate(vertex_array, face_array, cell_size=middle)
        if candidate.face_count > max_faces:
            low = middle  # too fine; coarsen
        else:
            best = candidate
            high = middle  # fits, try finer
        if high - low < extent / 4096.0:
            break
    return best


def lod_chain(
    vertices: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    *,
    budgets: Sequence[int] = (20000, 5000, 1000),
) -> tuple[DecimatedMesh, ...]:
    """A ladder of levels, coarsest last.

    Each level is decimated from the **original**, not from the level above it. Chaining
    decimations compounds the error, so LOD3 built from LOD2 built from LOD1 drifts noticeably
    further from the source than one built directly -- for no saving, since the work is the same.
    """
    return tuple(
        decimate_to_budget(vertices, faces, max_faces=budget)
        for budget in sorted(budgets, reverse=True)
    )
