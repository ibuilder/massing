"""A bounding-volume hierarchy, so the *server* can answer spatial questions.

This is the layer that moves work off the browser. With a BVH held server-side, picking, frustum
culling and broad-phase clash are all one tree descent on the machine that already holds the model
-- rather than three problems the client has to solve after downloading enough geometry to solve
them. The eventual JS layer sends a ray or a frustum and receives ids.

Built with a median split on the longest axis. Not a full surface-area heuristic: SAH buys perhaps
10-20% on query time for several times the build cost and considerably more code, and a building's
elements are far more evenly distributed than the scattered triangle soups SAH was designed for.

This is the first module in the codebase allowed to import numpy. Everything below
``massingviser.geometry`` stays dependency-free so it can run anywhere; this layer is explicitly
server-side compute, and vectorising it is the entire point.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

#: Leaves below this size stop splitting. Small enough that a leaf test is cheap, large enough that
#: the tree does not degenerate into one node per element.
LEAF_SIZE = 4


@dataclass(frozen=True)
class Aabb:
    """An axis-aligned box in metres."""

    min: tuple[float, float, float]
    max: tuple[float, float, float]

    @staticmethod
    def of_points(points: Sequence[Sequence[float]]) -> Aabb:
        array = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        return Aabb(tuple(array.min(axis=0)), tuple(array.max(axis=0)))

    @staticmethod
    def union(boxes: Iterable[Aabb]) -> Aabb:
        # Materialised once: the parameter is an Iterable, and reading it twice consumed a
        # generator on the first pass and reduced over an empty array on the second.
        collected = list(boxes)
        lows = np.array([box.min for box in collected], dtype=np.float64)
        highs = np.array([box.max for box in collected], dtype=np.float64)
        return Aabb(tuple(lows.min(axis=0)), tuple(highs.max(axis=0)))

    @property
    def centre(self) -> tuple[float, float, float]:
        return tuple((np.asarray(self.min) + np.asarray(self.max)) / 2.0)

    def expanded(self, margin: float) -> Aabb:
        return Aabb(
            tuple(value - margin for value in self.min),
            tuple(value + margin for value in self.max),
        )

    def overlaps(self, other: Aabb, tolerance: float = 0.0) -> bool:
        for axis in range(3):
            if self.min[axis] - tolerance > other.max[axis]:
                return False
            if self.max[axis] + tolerance < other.min[axis]:
                return False
        return True

    def penetration(self, other: Aabb) -> float:
        """Depth of the overlap along its shallowest axis; negative when separated.

        The shallowest axis is the right one: it is the distance you would have to move the two
        apart to stop them touching, which is what a clash report means by "overlap".
        """
        return min(
            min(self.max[axis], other.max[axis]) - max(self.min[axis], other.min[axis])
            for axis in range(3)
        )


@dataclass
class _Node:
    box: Aabb
    start: int = 0
    count: int = 0
    left: _Node | None = None
    right: _Node | None = None

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


class Bvh:
    """Spatial index over labelled boxes.

    Labels are opaque strings, which in this platform means IFC GlobalIds -- so every answer this
    index gives is already in the identity the rest of the system keys on.
    """

    __slots__ = ("_labels", "_boxes", "_order", "_root", "_lows", "_highs")

    def __init__(self, labels: Sequence[str], boxes: Sequence[Aabb]) -> None:
        if len(labels) != len(boxes):
            raise ValueError("Every box needs exactly one label.")
        self._labels = list(labels)
        self._boxes = list(boxes)
        self._order = list(range(len(boxes)))
        self._lows = np.array([box.min for box in boxes], dtype=np.float64).reshape(-1, 3)
        self._highs = np.array([box.max for box in boxes], dtype=np.float64).reshape(-1, 3)
        self._root = self._build(0, len(boxes)) if boxes else None

    def __len__(self) -> int:
        return len(self._boxes)

    @staticmethod
    def of_meshes(meshes: dict[str, Sequence[Sequence[float]]]) -> Bvh:
        """Build from vertex arrays, one per label."""
        labels = list(meshes)
        return Bvh(labels, [Aabb.of_points(meshes[label]) for label in labels])

    # -- construction ------------------------------------------------------------------------

    def _bounds(self, start: int, end: int) -> Aabb:
        indices = self._order[start:end]
        return Aabb(tuple(self._lows[indices].min(axis=0)), tuple(self._highs[indices].max(axis=0)))

    def _build(self, start: int, end: int) -> _Node:
        box = self._bounds(start, end)
        node = _Node(box=box, start=start, count=end - start)
        if end - start <= LEAF_SIZE:
            return node

        extent = np.asarray(box.max) - np.asarray(box.min)
        axis = int(np.argmax(extent))
        if extent[axis] <= 0:
            return node  # every element sits at the same place; splitting achieves nothing

        centres = (
            self._lows[self._order[start:end], axis] + self._highs[self._order[start:end], axis]
        ) / 2.0
        middle = start + (end - start) // 2
        # Partial sort: only the median position has to be correct, not the whole slice.
        local = np.argsort(centres, kind="stable")
        self._order[start:end] = [self._order[start:end][i] for i in local]

        node.left = self._build(start, middle)
        node.right = self._build(middle, end)
        node.count = 0
        return node

    # -- queries -----------------------------------------------------------------------------

    def query_aabb(self, box: Aabb, *, tolerance: float = 0.0) -> tuple[str, ...]:
        """Everything whose bounds meet this box."""
        found: list[str] = []
        self._descend_box(self._root, box, tolerance, found)
        return tuple(found)

    def _descend_box(
        self, node: _Node | None, box: Aabb, tolerance: float, found: list[str]
    ) -> None:
        if node is None or not node.box.overlaps(box, tolerance):
            return
        if node.is_leaf:
            for index in self._order[node.start : node.start + node.count]:
                if self._boxes[index].overlaps(box, tolerance):
                    found.append(self._labels[index])
            return
        self._descend_box(node.left, box, tolerance, found)
        self._descend_box(node.right, box, tolerance, found)

    def raycast(
        self, origin: Sequence[float], direction: Sequence[float], *, max_distance: float = math.inf
    ) -> tuple[tuple[str, float], ...]:
        """Every hit along a ray, nearest first.

        Returns all hits rather than only the first, because a picker usually wants "what is under
        the cursor, in order" -- selecting through a facade to the column behind it is an ordinary
        request, and re-running the query with a moved origin to get there is wasteful.
        """
        origin_array = np.asarray(origin, dtype=np.float64)
        direction_array = np.asarray(direction, dtype=np.float64)
        norm = float(np.linalg.norm(direction_array))
        # Not just zero: a NaN or infinite component gives a norm that is not zero either, and
        # every downstream comparison against NaN is False -- so an unusable direction came back
        # as a hit on everything, at a distance of NaN.
        if norm == 0.0 or not np.isfinite(norm):
            return ()
        direction_array = direction_array / norm

        # Reciprocals once, and infinities handled rather than avoided: a ray exactly parallel to
        # an axis is the common case when a camera is orthographic.
        with np.errstate(divide="ignore", invalid="ignore"):
            inverse = 1.0 / direction_array

        hits: list[tuple[str, float]] = []
        self._descend_ray(self._root, origin_array, inverse, max_distance, hits)
        return tuple(sorted(hits, key=lambda hit: hit[1]))

    def _slab(
        self, box: Aabb, origin: np.ndarray, inverse: np.ndarray, max_distance: float
    ) -> float | None:
        """Distance to the first intersection with ``box``, or ``None``.

        The axes the ray does not travel along are handled separately rather than through the
        arithmetic. On such an axis ``1/0`` is an infinity, and where the origin sits *exactly* on
        one of the box's faces the bound is ``0 * inf`` -- NaN. Letting `nanmin`/`nanmax` drop that
        substitutes the opposite face's bound, which reads as ``t_near = +inf > t_far`` and the box
        is missed: a horizontal pick ray at a slab's own base elevation, or any ray from the model
        origin, silently hit nothing. Such an axis in fact constrains no distance at all -- the ray
        is inside that slab along its whole length, or outside it along its whole length.
        """
        low_bound = np.asarray(box.min, dtype=np.float64)
        high_bound = np.asarray(box.max, dtype=np.float64)

        parallel = ~np.isfinite(inverse)
        if np.any(parallel & ((origin < low_bound) | (origin > high_bound))):
            return None

        with np.errstate(invalid="ignore"):
            low = (low_bound - origin) * inverse
            high = (high_bound - origin) * inverse
        near = np.where(parallel, -np.inf, np.minimum(low, high))
        far = np.where(parallel, np.inf, np.maximum(low, high))

        t_near = float(near.max())
        t_far = float(far.min())
        if t_far < 0 or t_near > t_far or t_near > max_distance:
            return None
        return max(t_near, 0.0)

    def _descend_ray(
        self,
        node: _Node | None,
        origin: np.ndarray,
        inverse: np.ndarray,
        max_distance: float,
        hits: list[tuple[str, float]],
    ) -> None:
        if node is None:
            return
        if self._slab(node.box, origin, inverse, max_distance) is None:
            return
        if node.is_leaf:
            for index in self._order[node.start : node.start + node.count]:
                distance = self._slab(self._boxes[index], origin, inverse, max_distance)
                if distance is not None:
                    hits.append((self._labels[index], distance))
            return
        self._descend_ray(node.left, origin, inverse, max_distance, hits)
        self._descend_ray(node.right, origin, inverse, max_distance, hits)

    def query_frustum(self, planes: Sequence[Sequence[float]]) -> tuple[str, ...]:
        """Everything inside or straddling six planes, each ``(a, b, c, d)`` with inward normals.

        Server-side culling. The client sends its camera; it receives the ids it would have had to
        download the whole model to work out for itself.
        """
        found: list[str] = []
        plane_array = np.asarray(planes, dtype=np.float64).reshape(-1, 4)
        self._descend_frustum(self._root, plane_array, found)
        return tuple(found)

    @staticmethod
    def _outside(box: Aabb, planes: np.ndarray) -> bool:
        low = np.asarray(box.min)
        high = np.asarray(box.max)
        normals = planes[:, :3]
        # The box corner furthest along each plane's normal. If even that corner is behind the
        # plane, nothing in the box is in front of it.
        positive = np.where(normals > 0, high, low)
        return bool(np.any((positive * normals).sum(axis=1) + planes[:, 3] < 0))

    def _descend_frustum(self, node: _Node | None, planes: np.ndarray, found: list[str]) -> None:
        if node is None or self._outside(node.box, planes):
            return
        if node.is_leaf:
            for index in self._order[node.start : node.start + node.count]:
                if not self._outside(self._boxes[index], planes):
                    found.append(self._labels[index])
            return
        self._descend_frustum(node.left, planes, found)
        self._descend_frustum(node.right, planes, found)

    def overlapping_pairs(
        self, other: Bvh, *, tolerance: float = 0.0
    ) -> tuple[tuple[str, str, float], ...]:
        """Broad-phase clash between two sets, as ``(left, right, penetration)``.

        Descends both trees together, so a pair of subtrees that cannot meet is rejected once
        rather than element by element. This is what makes a clash test over two full disciplines
        finish, instead of being 10^10 box comparisons.
        """
        pairs: list[tuple[str, str, float]] = []
        if self._root is None or other._root is None:
            return ()
        self._descend_pairs(self._root, other, other._root, tolerance, pairs)
        return tuple(pairs)

    def _descend_pairs(
        self,
        left: _Node,
        other: Bvh,
        right: _Node,
        tolerance: float,
        pairs: list[tuple[str, str, float]],
    ) -> None:
        if not left.box.overlaps(right.box, tolerance):
            return
        if left.is_leaf and right.is_leaf:
            for i in self._order[left.start : left.start + left.count]:
                for j in other._order[right.start : right.start + right.count]:
                    a = self._boxes[i]
                    b = other._boxes[j]
                    if a.overlaps(b, tolerance):
                        pairs.append((self._labels[i], other._labels[j], a.penetration(b)))
            return
        # Descend whichever side is still internal, and the larger one first when both are, so the
        # tree that actually discriminates does the work.
        if left.is_leaf:
            self._descend_pairs(left, other, right.left, tolerance, pairs)
            self._descend_pairs(left, other, right.right, tolerance, pairs)
        elif right.is_leaf:
            self._descend_pairs(left.left, other, right, tolerance, pairs)
            self._descend_pairs(left.right, other, right, tolerance, pairs)
        else:
            for a in (left.left, left.right):
                for b in (right.left, right.right):
                    if a is not None and b is not None:
                        self._descend_pairs(a, other, b, tolerance, pairs)

    def bounds(self) -> Aabb | None:
        return self._root.box if self._root else None
