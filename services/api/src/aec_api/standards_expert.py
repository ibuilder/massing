"""Standards-compliance experts — grounded checks against a project's own data, not a generic chatbot.

Rather than answer standards questions from a language model's memory, these run the relevant standard
(ISO 19650, COBie / BS 1192-4, buildingSMART IDS, Uniclass/bSDD) against what the project actually holds
— the CDE, the requirements register, the asset data, the model-quality index — and return findings with
the clause each one references plus a concrete recommendation. Deterministic and offline; when
ANTHROPIC_API_KEY is set the caller may layer a narrative on top, but the findings never come from a
model's imagination."""
from __future__ import annotations

from typing import Any

from . import bim_kpi, cde
from . import modules as me

STANDARDS = ("iso19650", "cobie", "ids", "uniclass")


def _finding(level: str, text: str, reference: str) -> dict:
    return {"level": level, "text": text, "reference": reference}


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def check(db, pid: str, standard: str) -> dict[str, Any]:
    """Run a standard against the project. Returns findings (ok/warn/gap + clause reference) and
    recommendations, plus a 0–100 readiness score."""
    standard = (standard or "").lower()
    if standard == "iso19650":
        return _iso19650(db, pid)
    if standard == "cobie":
        return _cobie(db, pid)
    if standard == "ids":
        return _ids(db, pid)
    if standard == "uniclass":
        return _uniclass(db, pid)
    return {"standard": standard, "error": f"unknown standard {standard!r}",
            "supported": list(STANDARDS)}


def _score(findings: list[dict]) -> int:
    if not findings:
        return 0
    weight = {"ok": 1.0, "warn": 0.5, "gap": 0.0}
    return round(100 * sum(weight[f["level"]] for f in findings) / len(findings))


def _iso19650(db, pid: str) -> dict[str, Any]:
    st = cde.status(db, pid)
    reqs = cde.requirements(db, pid)
    f: list[dict] = []
    # requirements register
    if reqs["core_coverage"]["complete"]:
        f.append(_finding("ok", "Core information requirements (EIR, BEP, AIR) are on file.",
                          "ISO 19650-2 §5.1–5.4 (information requirements & BEP)"))
    else:
        f.append(_finding("gap", f"Missing core requirements: {', '.join(reqs['core_coverage']['missing'])}.",
                          "ISO 19650-2 §5.2 (exchange information requirements)"))
    # CDE existence + discipline
    if st["total"] == 0:
        f.append(_finding("gap", "No information containers in the CDE.",
                          "ISO 19650-1 §12 (common data environment)"))
    else:
        md = st["discipline"]["metadata_completeness_pct"] or 0
        lvl = "ok" if md >= 80 else ("warn" if md >= 50 else "gap")
        f.append(_finding(lvl, f"CDE metadata completeness {md}% (type, discipline, originator, "
                               "suitability, revision).",
                          "ISO 19650-2 §5.1.7 (information container identification)"))
        rc = st["discipline"]["revision_control_pct"] or 0
        f.append(_finding("ok" if rc >= 80 else "warn",
                          f"Revision control on {rc}% of containers.",
                          "ISO 19650-2 §5.1.7 (revision & status codes)"))
        wip = st["by_state"].get("wip", 0)
        if wip and st["total"] and wip == st["total"]:
            f.append(_finding("warn", "All containers are still Work-in-progress — nothing Shared/Published.",
                              "ISO 19650-1 §12.2 (WIP → Shared → Published → Archived)"))
    return {"standard": "iso19650", "label": "ISO 19650 (information management)",
            "score": _score(f), "findings": f,
            "recommendations": [x["text"] for x in f if x["level"] != "ok"],
            "note": "Checked against the CDE container discipline and the requirements register."}


def _cobie(db, pid: str) -> dict[str, Any]:
    sc = bim_kpi.scorecard(db, pid)
    cat = {c["key"]: c for c in sc["categories"]}
    assets = me.list_records(db, "asset_register", pid, limit=100000)
    f: list[dict] = []
    if not assets:
        f.append(_finding("gap", "No asset register — nothing to hand over to the CMMS/CAFM.",
                          "BS 1192-4 (COBie) / NBIMS-US v3 Components"))
    else:
        tag = cat["asset_data_readiness"]["metrics"].get("tagged_pct") or 0
        f.append(_finding("ok" if tag >= 90 else ("warn" if tag >= 50 else "gap"),
                          f"{tag}% of assets carry a maintainable tag.",
                          "COBie Component sheet (maintainable asset tag)"))
        prod = cat["construction_data_readiness"]["metrics"].get("product_data_pct") or 0
        f.append(_finding("ok" if prod >= 80 else ("warn" if prod >= 40 else "gap"),
                          f"{prod}% of assets carry manufacturer/model product data.",
                          "COBie Type sheet (manufacturer, model)"))
    ha = cat["handover_assurance"]
    f.append(_finding("ok" if ha["grade"] == "good" else "warn",
                      ha["headline"], "COBie Documents/Jobs (O&M, as-built at handover)"))
    return {"standard": "cobie", "label": "COBie / BS 1192-4 (asset handover)",
            "score": _score(f), "findings": f,
            "recommendations": [x["text"] for x in f if x["level"] != "ok"],
            "note": "Checked against the asset register and the handover package."}


def _ids(db, pid: str) -> dict[str, Any]:
    from .bim_kpi import _openbim
    oq = _openbim(pid)
    f: list[dict] = []
    if not oq:
        f.append(_finding("warn", "No model loaded — IDS compliance can't be scored.",
                          "buildingSMART IDS 1.0 (2024)"))
    else:
        if oq.get("ids"):
            pct = oq["ids"]["compliance_pct"]
            f.append(_finding("ok" if (pct or 0) >= 90 else ("warn" if (pct or 0) >= 60 else "gap"),
                              f"IDS rule compliance {pct}% (handover use case).",
                              "buildingSMART IDS 1.0 — automated model validation"))
        lo = oq["loin"]["coordinated_pct"] or 0
        f.append(_finding("ok" if lo >= 80 else ("warn" if lo >= 50 else "gap"),
                          f"{lo}% of elements reach a coordinated LOIN (≥4/5 facets).",
                          "ISO 19650 Level of Information Need (LOIN)"))
        eh = oq["export_health"]["overall"]
        f.append(_finding({"pass": "ok", "warn": "warn", "fail": "gap"}.get(eh, "warn"),
                          f"IFC export health: {eh} ({oq['export_health']['proxy_count']} proxy elements).",
                          "buildingSMART IFC — export integrity"))
    return {"standard": "ids", "label": "buildingSMART IDS / openBIM quality",
            "score": _score(f), "findings": f,
            "recommendations": [x["text"] for x in f if x["level"] != "ok"],
            "note": "Checked against the loaded model's quality index."}


def _uniclass(db, pid: str) -> dict[str, Any]:
    from .bim_kpi import _openbim
    oq = _openbim(pid)
    f: list[dict] = []
    if not oq:
        f.append(_finding("warn", "No model loaded — classification coverage can't be measured.",
                          "Uniclass 2015 / bSDD"))
    else:
        pct = oq["bsdd"]["alignment_pct"] or 0
        f.append(_finding("ok" if pct >= 90 else ("warn" if pct >= 60 else "gap"),
                          f"{pct}% of elements carry a type/classification.",
                          "Uniclass 2015 tables / bSDD dictionary reference"))
        f.append(_finding("warn", "Full bSDD alignment requires classifications to reference a "
                                  "buildingSMART Data Dictionary URI, not just a local type.",
                          "buildingSMART Data Dictionary (bSDD)"))
    return {"standard": "uniclass", "label": "Uniclass / bSDD classification",
            "score": _score(f), "findings": f,
            "recommendations": [x["text"] for x in f if x["level"] != "ok"],
            "note": "Checked against the loaded model's classification coverage."}
