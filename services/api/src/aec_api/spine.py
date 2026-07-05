"""Discipline Spine traceability — trace the delivery chain end to end:
**discipline → sheets → specifications → bid packages → cost codes → budget**, and flag where the chain
is broken (specs with no bid package, packages with no cost code, sheets with no governing spec). Uses
the D1 classification vocabulary to resolve discipline consistently across the model, the documents and
the money. Deterministic, read-only over the config modules."""
from __future__ import annotations

from typing import Any

from . import classification as cls
from . import drawingset
from . import modules as me


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _spec_discipline(s: dict) -> str | None:
    """A spec section's discipline — explicit field, else derived from its MasterFormat division/section."""
    d = _d(s)
    return (cls.discipline_code(d.get("discipline"))
            or cls.discipline_of_division(cls.division_of(d.get("division") or d.get("section_number"))))


def _drawing_discipline(x: dict) -> str | None:
    """A sheet's discipline — explicit field, else parsed from the NCS sheet number."""
    d = _d(x)
    if d.get("discipline"):
        return cls.discipline_code(d.get("discipline"))
    sid = drawingset.parse_sheet_id(d.get("sheet_number") or d.get("number"))
    return sid["discipline_code"] if sid else None


def traceability(db, pid: str) -> dict[str, Any]:
    specs = me.list_records(db, "spec_section", pid, limit=100000)
    packages = me.list_records(db, "bid_package", pid, limit=100000)
    codes = me.list_records(db, "cost_code", pid, limit=100000)
    drawings = me.list_records(db, "drawing", pid, limit=100000)
    pkg_by_id = {p.get("id"): p for p in packages}
    code_by_id = {c.get("id"): c for c in codes}

    # per-discipline rollup across the whole chain, in NCS sheet order
    disc: dict[str, dict] = {d["name"]: {"discipline": d["name"], "code": d["code"], "sheets": 0,
                                         "specs": 0, "packages": 0, "cost_codes": 0, "budget": 0.0}
                             for d in cls.disciplines()}

    def bucket(code: str | None):
        name = cls.discipline_name(code)
        return disc.get(name) if name else None

    for x in drawings:
        b = bucket(_drawing_discipline(x))
        if b:
            b["sheets"] += 1
    for s in specs:
        b = bucket(_spec_discipline(s))
        if b:
            b["specs"] += 1
    for p in packages:
        b = bucket(cls.discipline_code(_d(p).get("discipline")))
        if b:
            b["packages"] += 1
            b["budget"] += _f(_d(p).get("budget"))
    for c in codes:
        b = bucket(cls.discipline_of_division(cls.division_of(_d(c).get("division"))))
        if b:
            b["cost_codes"] += 1

    # the spec → package → cost-code → budget chain, per spec section
    chain = []
    for s in specs:
        sd = _d(s)
        p = pkg_by_id.get(sd.get("bid_package"))
        cc = code_by_id.get(_d(p).get("cost_code")) if p else None
        chain.append({
            "spec": s.get("ref"), "section": sd.get("section_number"), "title": sd.get("title"),
            "discipline": cls.discipline_name(_spec_discipline(s)),
            "bid_package": p.get("ref") if p else None,
            "bid_package_name": _d(p).get("name") if p else None,
            "cost_code": cc.get("ref") if cc else None,
            "cost_code_value": _d(cc).get("code") if cc else None,
            "linked": bool(p and cc),
        })

    # coverage gaps — where the chain breaks
    specs_no_pkg = [{"ref": s.get("ref"), "section": _d(s).get("section_number"), "title": _d(s).get("title")}
                    for s in specs if not _d(s).get("bid_package")]
    pkgs_no_code = [{"ref": p.get("ref"), "name": _d(p).get("name")}
                    for p in packages if not _d(p).get("cost_code")]
    dwgs_no_spec = [{"ref": x.get("ref"), "sheet": _d(x).get("sheet_number") or _d(x).get("number")}
                    for x in drawings if not _d(x).get("spec_section")]
    fully_linked = sum(1 for c in chain if c["linked"])

    return {
        "disciplines": [d for d in disc.values()
                        if d["sheets"] or d["specs"] or d["packages"] or d["cost_codes"]],
        "coverage": {
            "specs": len(specs), "bid_packages": len(packages), "cost_codes": len(codes),
            "sheets": len(drawings),
            "specs_packaged_pct": round(100 * (len(specs) - len(specs_no_pkg)) / len(specs), 1) if specs else None,
            "packages_costed_pct": round(100 * (len(packages) - len(pkgs_no_code)) / len(packages), 1) if packages else None,
            "sheets_specced_pct": round(100 * (len(drawings) - len(dwgs_no_spec)) / len(drawings), 1) if drawings else None,
            "spec_to_budget_pct": round(100 * fully_linked / len(specs), 1) if specs else None,
        },
        "gaps": {
            "specs_without_bid_package": specs_no_pkg[:100],
            "bid_packages_without_cost_code": pkgs_no_code[:100],
            "sheets_without_spec": dwgs_no_spec[:100],
        },
        "chain": chain[:300],
        "note": "Traces discipline → sheets → specs → bid packages → cost codes → budget. A spec is "
                "fully traceable when it reaches a bid package and a cost code; the gaps list the broken "
                "links so scope can't fall between the model, the documents and the money.",
    }
