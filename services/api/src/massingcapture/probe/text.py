"""Text point formats: PTX, PTS, XYZ, and delimited variants.

Ugly formats, and the ones a scanner operator hands over when the E57 export failed. Worth reading
properly for one reason: **PTX carries the scanner's setup position and orientation in its header**,
one block per setup, and that is the same prize as the E57 index -- scan positions, which become
walkthrough nodes without anybody clicking anything.

PTS declares a count and nothing else. XYZ declares nothing at all. Both are streamed for bounds and
column layout, and the column layout is guessed from the data rather than assumed, because a
seven-column file is XYZ+intensity+RGB and a six-column file could be XYZ+RGB or XYZ+normals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO

#: Beyond this many lines the scan samples rather than reads every point.
DEFAULT_MAX_SAMPLES = 500_000


class TextPointError(ValueError):
    """A text point file did not read as one."""


def _numbers(line: str) -> list[float] | None:
    parts = line.replace(",", " ").split()
    if not parts:
        return None
    try:
        return [float(part) for part in parts]
    except ValueError:
        return None


def _describe_columns(count: int) -> str:
    return {
        3: "x y z",
        4: "x y z intensity",
        6: "x y z r g b",
        7: "x y z intensity r g b",
        9: "x y z r g b nx ny nz",
    }.get(count, f"{count} columns, layout not recognised")


def _scan_bounds(
    stream: TextIO, *, max_samples: int, skip: int = 0
) -> tuple[list[float] | None, int, int, bool]:
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    read = 0
    columns = 0
    for _ in range(skip):
        if not stream.readline():
            break
    for line in stream:
        values = _numbers(line)
        if values is None or len(values) < 3:
            continue
        read += 1
        columns = columns or len(values)
        if read <= max_samples:
            for axis in range(3):
                if values[axis] < lo[axis]:
                    lo[axis] = values[axis]
                if values[axis] > hi[axis]:
                    hi[axis] = values[axis]
    if lo[0] == float("inf"):
        return None, read, columns, False
    return [lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]], read, columns, read > max_samples


def summarise_ptx(path: str | Path, *, max_samples: int = DEFAULT_MAX_SAMPLES) -> dict[str, Any]:
    """Read every PTX setup header, and bound the points.

    A PTX block is: columns, rows, a three-float scanner position, three three-float axis rows, then
    a 4x4 registration matrix in row-major order, then ``rows * columns`` point lines -- including
    the ``0 0 0`` entries for rays that hit nothing, which is why the declared grid size and the
    useful point count differ, often by half.
    """
    path = Path(path)
    setups: list[dict[str, Any]] = []
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    sampled = False
    total_points = 0
    valid_points = 0
    columns_seen = 0

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        while True:
            first = stream.readline()
            if not first.strip():
                break
            try:
                grid_columns = int(first.strip())
                grid_rows = int(stream.readline().strip())
            except ValueError as thrown:
                raise TextPointError(f"PTX header is not a grid size: {thrown}") from thrown

            position = _numbers(stream.readline() or "")
            axes = [_numbers(stream.readline() or "") for _ in range(3)]
            matrix_rows = [_numbers(stream.readline() or "") for _ in range(4)]
            if position is None or len(position) < 3:
                raise TextPointError("PTX setup header is missing its scanner position.")

            setup: dict[str, Any] = {
                "rows": grid_rows,
                "columns": grid_columns,
                "position": position[:3],
                "declared_points": grid_rows * grid_columns,
            }
            if all(row and len(row) >= 4 for row in matrix_rows):
                # PTX writes the transform row-major; everything downstream is column-major.
                flat = [value for row in matrix_rows for value in row[:4]]
                setup["matrix_column_major"] = [flat[(i % 4) * 4 + i // 4] for i in range(16)]
            if all(axis and len(axis) >= 3 for axis in axes):
                setup["axes"] = [axis[:3] for axis in axes]
            setups.append(setup)

            expected = grid_rows * grid_columns
            total_points += expected
            step = max(1, -(-expected // max_samples))
            for index in range(expected):
                line = stream.readline()
                if not line:
                    break
                if index % step:
                    continue
                values = _numbers(line)
                if values is None or len(values) < 3:
                    continue
                columns_seen = columns_seen or len(values)
                if values[0] == 0.0 and values[1] == 0.0 and values[2] == 0.0:
                    continue  # A ray that returned nothing.
                valid_points += 1
                for axis in range(3):
                    if values[axis] < lo[axis]:
                        lo[axis] = values[axis]
                    if values[axis] > hi[axis]:
                        hi[axis] = values[axis]
            if step > 1:
                sampled = True

    summary: dict[str, Any] = {
        "text_format": "ptx",
        "scan_count": len(setups),
        "point_count": total_points,
        "populated_points_sampled": valid_points,
        "structured": True,
        "columns": _describe_columns(columns_seen) if columns_seen else None,
        "has_color": columns_seen >= 7,
        "has_intensity": columns_seen >= 4,
        "scans": setups,
    }
    if lo[0] != float("inf"):
        summary["bounds"] = [lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]]
        summary["bounds_sampled"] = sampled
    return summary


def summarise_pts(path: str | Path, *, max_samples: int = DEFAULT_MAX_SAMPLES) -> dict[str, Any]:
    """PTS: a count on the first line, then points."""
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        first = stream.readline().strip()
        declared: int | None
        try:
            declared = int(first)
            skip = 0
        except ValueError:
            declared = None
            stream.seek(0)
            skip = 0
        bounds, read, columns, sampled = _scan_bounds(stream, max_samples=max_samples, skip=skip)

    summary: dict[str, Any] = {
        "text_format": "pts",
        "point_count": declared if declared is not None else read,
        "columns": _describe_columns(columns) if columns else None,
        "has_color": columns >= 6,
        "has_intensity": columns in (4, 7),
        "structured": False,
    }
    if declared is not None and declared != read:
        summary["warnings"] = [f"Header declares {declared} points; {read} readable lines found."]
    if bounds:
        summary["bounds"] = bounds
        summary["bounds_sampled"] = sampled
    return summary


def summarise_xyz(path: str | Path, *, max_samples: int = DEFAULT_MAX_SAMPLES) -> dict[str, Any]:
    """XYZ and comma-delimited variants: no header, so everything is inferred from the rows."""
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        head = stream.readline()
        # A first line that is not numbers is a column header, not a point.
        skip = 0 if _numbers(head) else 1
        stream.seek(0)
        bounds, read, columns, sampled = _scan_bounds(stream, max_samples=max_samples, skip=skip)

    summary: dict[str, Any] = {
        "text_format": "xyz",
        "point_count": read,
        "columns": _describe_columns(columns) if columns else None,
        "has_color": columns >= 6,
        "has_intensity": columns in (4, 7),
        "structured": False,
        "header_row": bool(skip),
    }
    if bounds:
        summary["bounds"] = bounds
        summary["bounds_sampled"] = sampled
    return summary


def summarise(path: str | Path) -> dict[str, Any]:
    """Dispatch on extension, which for these formats is the only signal available."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".ptx":
        return summarise_ptx(path)
    if suffix == ".pts":
        return summarise_pts(path)
    return summarise_xyz(path)
