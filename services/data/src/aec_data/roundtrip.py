"""INTEROP-RT — the round-trip fidelity gauntlet (R19).

The openBIM promise is only real if what we author SURVIVES serialization: write the model to
disk, read it back, and prove nothing drifted. This leaf makes that a first-class, automatable
check:

- `snapshot(model)` — a deterministic per-element fingerprint: IFC class, name, spatial
  container, related type (GUID), and the full occurrence property sets. GUID-keyed, so identity
  is the GlobalId — never an index or a viewer id.
- `compare(before, after)` — missing / added / changed (with the exact aspects that moved:
  class · name · container · type · psets), plus counts and a single `fidelity_ok` verdict.
  Unmatched is reported BOTH ways, never netted.
- `roundtrip(model)` — write to a temp file → fresh parse → compare. The gauntlet itself.

Used by `test_roundtrip` as a suite gate and by the `massing roundtrip` CLI (CI-friendly:
`--gate` exits 1 on any fidelity loss).
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

_SKIP = ("id",)


def _psets(el) -> dict[str, dict[str, Any]]:
    out = {}
    try:
        raw = ue.get_psets(el, should_inherit=False) or {}
    except Exception:                                  # noqa: BLE001 — schema oddity → no psets
        return {}
    for name, props in raw.items():
        if isinstance(props, dict):
            out[name] = {k: v for k, v in props.items() if k not in _SKIP}
    return out


def snapshot(model: ifcopenshell.file) -> dict[str, dict[str, Any]]:
    """GUID → fingerprint for every IfcProduct and IfcTypeProduct in the model."""
    snap: dict[str, dict[str, Any]] = {}
    for el in list(model.by_type("IfcProduct")) + list(model.by_type("IfcTypeProduct")):
        guid = getattr(el, "GlobalId", None)
        if not guid:
            continue
        typ = None
        try:
            t = ue.get_type(el)
            typ = t.GlobalId if t is not None and t is not el else None
        except Exception:                              # noqa: BLE001
            typ = None
        container = None
        try:
            c = ue.get_container(el)
            container = getattr(c, "Name", None)
        except Exception:                              # noqa: BLE001
            container = None
        snap[guid] = {
            "class": el.is_a(),
            "name": getattr(el, "Name", None),
            "container": container,
            "type": typ,
            "psets": _psets(el),
        }
    return snap


def compare(before: dict[str, dict], after: dict[str, dict]) -> dict[str, Any]:
    missing = sorted(g for g in before if g not in after)
    added = sorted(g for g in after if g not in before)
    changed: list[dict[str, Any]] = []
    for g in sorted(set(before) & set(after)):
        aspects = [k for k in ("class", "name", "container", "type", "psets")
                   if before[g].get(k) != after[g].get(k)]
        if aspects:
            detail: dict[str, Any] = {"guid": g, "class": before[g]["class"], "aspects": aspects}
            if "psets" in aspects:
                b, a = before[g]["psets"], after[g]["psets"]
                detail["pset_diff"] = {
                    "missing_psets": sorted(set(b) - set(a)),
                    "added_psets": sorted(set(a) - set(b)),
                    "changed_psets": sorted(p for p in set(b) & set(a) if b[p] != a[p]),
                }
            changed.append(detail)
    return {
        "fidelity_ok": not missing and not added and not changed,
        "element_count": len(before),
        "missing": missing[:200], "added": added[:200], "changed": changed[:200],
        "counts": {"missing": len(missing), "added": len(added), "changed": len(changed)},
    }


def roundtrip(model: ifcopenshell.file) -> dict[str, Any]:
    """Write → fresh parse → compare. The temp file is always cleaned up."""
    before = snapshot(model)
    fd, path = tempfile.mkstemp(suffix=".ifc")
    os.close(fd)
    try:
        model.write(path)
        reread = ifcopenshell.open(path)
        after = snapshot(reread)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    report = compare(before, after)
    report["note"] = "authored model vs its own serialized+reparsed copy"
    return report


def roundtrip_file(path: str) -> dict[str, Any]:
    """The CLI entry: parse → write a copy → reparse → compare (proves OUR reserialization of an
    arbitrary IFC is lossless on the fingerprinted aspects)."""
    return roundtrip(ifcopenshell.open(str(path)))
