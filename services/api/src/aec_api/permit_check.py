"""PERMIT-CHECK — permit-submission readiness: one deficiency report over the code engines + the set.

Cities are rolling out AI plan review (LA/Seattle/Austin live in 2026, 6-month queues → days); the
applicants who win the queue are the ones who arrive **pre-checked**. This composes what the platform
already computes into the report a permit tech would produce at intake:

  · **code engines** — computed occupancy/egress (IBC 1004/1005, cited), the plan-reviewer
    approvability pre-flight, and the G-series code-analysis summary (jurisdiction-adopted edition);
  · **the drawing set** — are the submission's required sheet series actually in the register
    (G code analysis · A plans · S structural · M/E/P · life-safety/egress)?
  · **project data** — the intake fields every jurisdiction asks for (occupancy group, construction
    type, sprinklered, stories, area).

Output: an intake **checklist** (requirement · satisfied · evidence), the **deficiency list** ranked by
severity (code violations first — those are rejections, not comments), a readiness %, and a
READY / NOT-READY verdict. Pre-check assist with cited sections; NOT a certified review — the AHJ rules.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import codecheck
from . import modules as me

# The sheet series a typical building-permit submission must include, matched against the drawing
# register's sheet numbers (NCS discipline designators).
REQUIRED_SERIES: list[tuple[str, str]] = [
    ("G", "G-series — code analysis / general"),
    ("A", "A-series — architectural plans"),
    ("S", "S-series — structural"),
    ("M", "M-series — mechanical"),
    ("E", "E-series — electrical"),
    ("P", "P-series — plumbing"),
]


def _sheet_series(db: Session, pid: str) -> dict[str, int]:
    """Count register sheets per leading discipline designator (A-101 → A)."""
    counts: dict[str, int] = {}
    if "drawing" not in me.TABLES:
        return counts
    for r in me.list_records(db, "drawing", pid, limit=100_000):
        num = str((r.get("data") or {}).get("number") or r.get("ref") or "").strip().upper()
        if not num:
            continue
        series = num.split("-")[0].rstrip("0123456789") or num[:1]
        counts[series] = counts.get(series, 0) + 1
    return counts


def readiness(db: Session, pid: str, model, *, occupancy_group: str = "",
              construction_type: str = "", sprinklered: bool = False,
              jurisdiction: str = "") -> dict[str, Any]:
    """Compose the permit-readiness report. `model` is the opened source IFC (caller 409s without one)."""
    checklist: list[dict[str, Any]] = []
    deficiencies: list[dict[str, Any]] = []

    def item(req: str, ok: bool, evidence: str, severity: str = "major", action: str | None = None):
        checklist.append({"requirement": req, "satisfied": bool(ok), "evidence": evidence})
        if not ok:
            deficiencies.append({"item": req, "severity": severity, "source": evidence,
                                 "action": action or f"resolve before submission: {req}"})

    # --- computed code checks (rejections, not comments) --------------------------------------------
    # egress_from_model takes an EDITION year, not a jurisdiction — code_analysis (below) resolves the
    # jurisdiction's adopted edition; the plain call uses the default factors.
    egress = codecheck.egress_from_model(model)
    violations = [f for f in (egress.get("findings") or egress.get("spaces") or [])
                  if isinstance(f, dict) and (f.get("violation") or f.get("deficient"))]
    # tolerate either shape: a findings list or per-space rows with a pass flag
    if not violations and isinstance(egress.get("doors"), list):
        violations = [d for d in egress["doors"] if isinstance(d, dict) and d.get("deficient")]
    item("Computed egress capacity meets occupant load (IBC 1005)", not violations,
         f"{len(violations)} egress deficiency(ies) computed from the model" if violations
         else "occupancy/egress computed from IfcSpaces + IfcDoors, no deficiencies",
         severity="critical",
         action="fix the flagged doors/exits — an egress shortfall is a plan-review rejection")

    approv = codecheck.approvability(model)
    score = float(approv.get("score") or approv.get("readiness_pct") or 0)
    item("Plan-reviewer pre-flight (egress traced, doors clear-width, occupancy classified) ≥ 80%",
         score >= 80.0, f"approvability score {score:.0f}%",
         action="work the approvability checklist items below 80%")

    analysis = codecheck.code_analysis(model, occupancy_group, construction_type,
                                       sprinklered, jurisdiction)
    edition = analysis.get("edition") or analysis.get("code_edition")
    item("Code-analysis summary complete (occupancy group + construction type declared)",
         bool(occupancy_group and construction_type),
         f"occupancy={occupancy_group or '—'} type={construction_type or '—'} "
         f"edition={edition or 'IBC (default)'}",
         severity="major",
         action="declare occupancy group + construction type (they drive allowable area/height)")

    # --- the set: required sheet series in the drawing register -------------------------------------
    series = _sheet_series(db, pid)
    for code, label in REQUIRED_SERIES:
        n = series.get(code, 0)
        item(f"{label} in the drawing register", n > 0,
             f"{n} sheet(s) numbered {code}-…" if n else "no sheets in this series",
             severity="major" if code in ("G", "A", "S") else "minor",
             action=f"generate/register the {code}-series sheets (sheetgen covers this)")

    # --- rollup --------------------------------------------------------------------------------------
    satisfied = sum(1 for c in checklist if c["satisfied"])
    pct = round(satisfied / len(checklist) * 100, 1) if checklist else 0.0
    sev_rank = {"critical": 0, "major": 1, "minor": 2}
    deficiencies.sort(key=lambda d: sev_rank.get(d["severity"], 3))
    verdict = "READY" if not any(d["severity"] == "critical" for d in deficiencies) and pct >= 80 \
        else "NOT READY"
    return {
        "verdict": verdict, "readiness_pct": pct,
        "checklist": checklist, "deficiencies": deficiencies,
        "sheet_series": series,
        "code_edition": edition,
        "egress": {"summary": {k: v for k, v in egress.items() if not isinstance(v, list)}},
        "approvability_score": score,
        "disclaimer": ("Pre-check assist with cited sections — NOT a certified plan review. The "
                       "authority having jurisdiction rules; use this to arrive at intake pre-checked."),
    }
