"""SCOPE-GAP (R14) — does every element in the model land in someone's bid package?

Maps the model's quantity takeoff (grouped by NCS discipline) against the project's defined
``bid_package`` records (each claims a discipline + spec sections). Surfaces:

  * **covered** — disciplines the model carries that a package claims (with the element tally the
    bidder is pricing),
  * **gaps** — disciplines present in the model with **no** covering package: their quantities aren't
    in any bid yet, the classic scope-hole a GC discovers at buyout (sample GUIDs cited so you can
    click-to-highlight the uncovered elements),
  * **packages_without_model_scope** — packages whose discipline has no model elements (over-scoped /
    nothing to price).

Pure over the takeoff rows + the package records — conceptual-grade, discipline-level baseline;
spec-section refinement and per-line sheet citation extend it.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

_MAX_SAMPLE = 20


def analyze(db: Session, pid: str, rows: list[dict]) -> dict[str, Any]:
    """Coverage of the model takeoff (``rows`` = ``qto.takeoff`` output) by the project's bid packages."""
    from . import classification as cls
    from . import modules as me

    packages = me.list_records(db, "bid_package", pid, limit=100_000)
    claimed: dict[str, list[str]] = {}          # discipline name -> [package names]
    pkgs: list[dict] = []
    for p in packages:
        d = p.get("data") or {}
        disc = (d.get("discipline") or "").strip()
        specs = [s.strip() for s in (d.get("spec_sections") or "").replace(";", ",").split(",") if s.strip()]
        name = d.get("name") or p.get("ref") or "package"
        pkgs.append({"name": name, "discipline": disc, "spec_sections": specs})
        if disc:
            claimed.setdefault(disc, []).append(name)

    by_disc: dict[str, dict] = {}               # discipline name -> tally
    for r in rows:
        c = r.get("ifc_class")
        if not c:
            continue
        dname = cls.discipline_name(cls.discipline_of_ifc_class(c)) or "General"
        b = by_disc.setdefault(dname, {"count": 0, "classes": {}, "guids": []})
        b["count"] += 1
        b["classes"][c] = b["classes"].get(c, 0) + 1
        g = r.get("guid")
        if g and len(b["guids"]) < 50:
            b["guids"].append(g)

    covered, gaps = [], []
    for dname, b in sorted(by_disc.items()):
        classes = sorted(({"ifc_class": k, "count": v} for k, v in b["classes"].items()),
                         key=lambda x: -x["count"])
        entry = {"discipline": dname, "element_count": b["count"], "classes": classes}
        if dname in claimed:
            entry["packages"] = claimed[dname]
            covered.append(entry)
        else:
            entry["sample_guids"] = b["guids"][:_MAX_SAMPLE]
            gaps.append(entry)

    model_discs = set(by_disc)
    empty_pkgs = sorted({p["name"] for p in pkgs if p["discipline"] and p["discipline"] not in model_discs})

    total = sum(b["count"] for b in by_disc.values())
    covered_ct = sum(e["element_count"] for e in covered)
    return {
        "package_count": len(pkgs), "element_count": total,
        "covered_pct": round(100.0 * covered_ct / total, 1) if total else 0.0,
        "gap_element_count": total - covered_ct,
        "covered": covered, "gaps": gaps,
        "packages_without_model_scope": empty_pkgs,
        "note": "Coverage matches each element's NCS discipline to a bid package that claims that "
                "discipline. Gaps = disciplines present in the model with no covering package — their "
                "quantities aren't in any bid. Spec-section refinement + per-line sheet citation extend "
                "this discipline-level baseline. Conceptual-grade.",
    }
