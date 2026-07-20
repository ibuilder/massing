"""REVISION-DELTA (R15) — the conceptual **cost impact of a model revision**: diff two published
versions, then turn "what changed" into "what it costs".

Honest about what the version store can support. Per-version we keep the element GUID set + a
fingerprint (name / class / type / level / property-hash / quantity-hash) — **not** the raw quantities.
So:

  * **added** elements are present in the *current* model, so their real takeoff quantities exist →
    they are priced through the conceptual estimator (``estimate.estimate_from_takeoff``).
  * **removed** elements are gone from the current model and their prior quantities weren't stored →
    they are *counted by IFC class* (from the prior version's fingerprints), not priced.
  * **modified** elements whose **quantity-hash changed** are *flagged for re-estimate* — the quantity
    moved but the before/after magnitudes aren't both known, so a precise net isn't claimed.

The result is a change-management aid ("this revision added ≈ $X of structure; 3 walls removed; 8 beams
re-sized — re-price"), **not** a change order. Pure over the diff + current takeoff + prior fingerprints,
so it unit-tests without a model or a database.
"""
from __future__ import annotations

from typing import Any


def delta(diff_res: dict[str, Any], current_rows: list[dict],
          prev_fingerprints: dict[str, list] | None = None,
          overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Cost the revision described by ``diff_res`` (a ``versions.diff`` result). ``current_rows`` is the
    current model's ``qto.takeoff`` output; ``prev_fingerprints`` the prior version's fingerprint map
    (``guid -> [name, class, …]``) used to classify removed elements. Returns a structured impact."""
    from . import classification as cls
    from . import estimate

    prev_fingerprints = prev_fingerprints or {}
    added = set(diff_res.get("added") or [])
    removed = set(diff_res.get("removed") or [])
    modified = diff_res.get("modified") or []

    # ADDED — present in the current model, so priced from the real takeoff
    added_rows = [r for r in current_rows if r.get("guid") in added]
    priced = estimate.estimate_from_takeoff(added_rows, overrides or {})
    added_block = {
        "count": len(added), "priced_count": priced["element_count"],
        "cost": priced["total"], "lines": priced["lines"],
        "unpriced": priced["unpriced"],
    }

    # REMOVED — gone from the current model; count by class from the prior fingerprints (no prices)
    by_class: dict[str, int] = {}
    for g in removed:
        fp = prev_fingerprints.get(g)
        c = fp[1] if (fp and len(fp) > 1 and fp[1]) else "Unknown"
        by_class[c] = by_class.get(c, 0) + 1
    removed_lines = sorted(
        ({"ifc_class": c, "count": n,
          "discipline": cls.discipline_name(cls.discipline_of_ifc_class(c)) or "General"}
         for c, n in by_class.items()), key=lambda x: (-x["count"], x["ifc_class"]))
    removed_block = {
        "count": len(removed), "by_class": removed_lines,
        "note": "removed elements aren't in the current model — counted by class, not priced "
                "(prior-version quantities aren't stored).",
    }

    # MODIFIED whose quantity-hash moved → re-estimate flags
    requant = [{"guid": m.get("guid"), "name": m.get("name"), "ifc_class": m.get("ifc_class")}
               for m in modified if "quantities changed" in (m.get("changes") or [])]
    requant_block = {
        "count": len(requant), "sample": requant[:20],
        "note": "quantity changed between versions — re-price these (before/after magnitudes not both "
                "stored, so no automatic net).",
    }

    return {
        "from": diff_res.get("from"), "to": diff_res.get("to"),
        "added": added_block, "removed": removed_block, "requantified": requant_block,
        "summary": {"added_count": len(added), "removed_count": len(removed),
                    "requantified_count": len(requant), "added_cost": priced["total"]},
        "note": "Conceptual revision cost impact — ADDED elements priced from the current takeoff, "
                "REMOVED counted by class, quantity-modified elements flagged for re-estimate. A "
                "change-management aid, not a change order.",
    }
