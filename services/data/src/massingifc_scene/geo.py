"""Georeferencing, mirroring ``@massingifc/project-schema``.

A transform is not georeferencing: it places geometry relative to a project origin nobody outside
the project knows. Kept here rather than folded into the scene model because a reference model, a
scan and a site boundary all have to say where on Earth they are, and they have to say it the same
way in both implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

#: Metres per unit. ``ft`` and ``us-ft`` differ by ~2ppm, which is metres across a large site.
METRES_PER_UNIT: Mapping[str, float] = {
    "m": 1.0,
    "mm": 0.001,
    "cm": 0.01,
    "ft": 0.3048,
    "us-ft": 1200 / 3937,
}


def convert_length(value: float, source: str, target: str) -> float:
    """Convert a length between linear units, via metres."""
    if source == target:
        return value
    try:
        return (value * METRES_PER_UNIT[source]) / METRES_PER_UNIT[target]
    except KeyError as exc:  # pragma: no cover - guarded by validation upstream
        raise ValueError(f"Unknown linear unit: {exc.args[0]!r}") from exc


def parse_crs_code(code: str) -> Optional[Tuple[str, str]]:
    """Split ``"EPSG:27700"`` into authority and code, or ``None`` if not authority-qualified."""
    text = code.strip()
    authority, separator, identifier = text.partition(":")
    if not separator or not authority or not identifier:
        return None
    if not authority[0].isalpha():
        return None
    if not all(character.isalnum() or character in "_-" for character in authority):
        return None
    if not all(character.isalnum() or character in "._-" for character in identifier):
        return None
    return authority.upper(), identifier


@dataclass(frozen=True)
class GeoAccuracy:
    """Metres, 1-sigma. Deliberately *not* rescaled with ``units`` — it is always metres."""

    horizontal: Optional[float] = None
    vertical: Optional[float] = None

    def to_json(self) -> dict:
        return _drop_none({"horizontal": self.horizontal, "vertical": self.vertical})

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "GeoAccuracy":
        return GeoAccuracy(horizontal=data.get("horizontal"), vertical=data.get("vertical"))


@dataclass(frozen=True)
class GeoReference:
    """Where something sits on Earth.

    ``origin_offset`` exists for float precision: a British National Grid easting is around 530000,
    a 32-bit float carries about seven significant digits, so geometry rendered at true coordinates
    jitters and z-fights. Recording the offset makes the renderer's local frame reversible instead
    of a lossy fudge.
    """

    source_crs: str
    units: str = "m"
    target_crs: Optional[str] = None
    vertical_datum: Optional[str] = None
    origin_offset: Optional[Sequence[float]] = None
    local_to_global: Optional[Sequence[float]] = None
    true_north_angle: Optional[float] = None
    method: Optional[str] = None
    accuracy: Optional[GeoAccuracy] = None
    established_at: Optional[str] = None

    def to_json(self) -> dict:
        return _drop_none(
            {
                "sourceCrs": self.source_crs,
                "units": self.units,
                "targetCrs": self.target_crs,
                "verticalDatum": self.vertical_datum,
                "originOffset": (
                    list(self.origin_offset) if self.origin_offset is not None else None
                ),
                "localToGlobal": (
                    list(self.local_to_global) if self.local_to_global is not None else None
                ),
                "trueNorthAngle": self.true_north_angle,
                "method": self.method,
                "accuracy": self.accuracy.to_json() if self.accuracy else None,
                "establishedAt": self.established_at,
            }
        )

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> "GeoReference":
        accuracy = data.get("accuracy")
        return GeoReference(
            source_crs=data["sourceCrs"],
            units=data.get("units", "m"),
            target_crs=data.get("targetCrs"),
            vertical_datum=data.get("verticalDatum"),
            origin_offset=data.get("originOffset"),
            local_to_global=data.get("localToGlobal"),
            true_north_angle=data.get("trueNorthAngle"),
            method=data.get("method"),
            accuracy=GeoAccuracy.from_json(accuracy) if accuracy else None,
            established_at=data.get("establishedAt"),
        )

    def to_metres(self) -> "GeoReference":
        """Restate in metres.

        Converted by the georeference's *own* units, never the model's: the two are independent, and
        a package that declares metres while carrying a millimetre origin offset puts a consumer a
        factor of a thousand from where it belongs.
        """
        factor = convert_length(1.0, self.units, "m")
        if factor == 1.0:
            return self

        offset = (
            [value * factor for value in self.origin_offset]
            if self.origin_offset is not None
            else None
        )
        local = None
        if self.local_to_global is not None:
            local = [
                value * factor if 12 <= index <= 14 else value
                for index, value in enumerate(self.local_to_global)
            ]

        return GeoReference(
            source_crs=self.source_crs,
            units="m",
            target_crs=self.target_crs,
            vertical_datum=self.vertical_datum,
            origin_offset=offset,
            local_to_global=local,
            true_north_angle=self.true_north_angle,
            method=self.method,
            accuracy=self.accuracy,
            established_at=self.established_at,
        )


def _drop_none(data: Mapping[str, Any]) -> dict:
    """Omit absent keys entirely.

    The TypeScript side uses optional properties, and ``{"targetCrs": null}`` is a different
    document from one without the key. Matching matters: the two implementations are compared
    byte-for-byte by the conformance suite.
    """
    return {key: value for key, value in data.items() if value is not None}
