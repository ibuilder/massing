"""R21-SOFT-CLASH — clearance clash, and the matrix that says what was actually tested.

Hard clash asks "do two solids occupy the same space". Soft clash asks the question that actually
stops work: **can a person reach this, service it, or pull it out?** A pump that clears every duct by
5 mm passes hard clash and cannot be maintained.

Two halves, and the second is the one that changes what a report is allowed to claim.

**Clearance rules.** Soft clash is a *rules* problem, not a geometry problem: the required clear zone
comes from a code or a manufacturer, not from the model. Each rule here carries its source, so a
finding can be argued with.

**The discipline-pair matrix.** A coordination report that says "clash-free" without saying which
discipline pairs were tested is overstating what it knows. Structural-vs-plumbing being clean means
nothing if structural-vs-plumbing was never run. So an untested pair is reported as **untested** —
never folded into the clean count. This is the same rule the scan verification follows: absence of
evidence is not evidence of absence.
"""
from __future__ import annotations

from typing import Any

# ── clearance rules ──────────────────────────────────────────────────────────────────────────────
# `distance_m` is the clear zone the element needs. `basis` is what to argue with when someone
# disagrees — a rule with no stated source is an opinion with a number attached.
#
# LIMITATION, stated rather than hidden: these are evaluated against axis-aligned bounding boxes,
# which carry no facing. A working space is *directional* — NEC 110.26 wants the space IN FRONT of
# the panel, and clear space behind it satisfies nothing. With an AABB we can only test "is there a
# clear zone on some approach side", which can pass a panel that is in fact unusable. That makes a
# PASS weaker than a FAIL here: a violation is real, a clean result is "not disproved".
CLEARANCE_RULES: dict[str, dict[str, Any]] = {
    "ifcelectricdistributionboard": {
        "distance_m": 0.9, "label": "Electrical working space",
        "basis": "NEC 110.26(A)(1) Condition 1 — 900 mm depth for equipment 0–150 V to ground",
        "why": "The space an electrician must stand in to work the board live."},
    "ifcelectricflowstoragedevice": {
        "distance_m": 0.9, "label": "Electrical working space",
        "basis": "NEC 110.26(A)(1) — working space applies to equipment likely to require "
                 "examination or servicing while energised",
        "why": "Same working space as any other equipment likely to require examination while energised."},
    "ifcairterminalbox": {
        "distance_m": 0.6, "label": "VAV box service access",
        "basis": "Manufacturer service clearance — typical 600 mm to the control side",
        "why": "Access to the controller and the reheat coil connections."},
    "ifcunitaryequipment": {
        "distance_m": 1.0, "label": "Coil pull space",
        "basis": "Manufacturer coil-withdrawal clearance — typically the coil's own length",
        "why": "A coil that cannot be withdrawn has to be cut out, taking the casing with it."},
    "ifcvalve": {
        "distance_m": 0.45, "label": "Valve access",
        "basis": "Reach clearance for hand-wheel or actuator operation",
        "why": "A valve nobody can turn is a valve that will be left in whatever position it is in."},
    "ifcpump": {
        "distance_m": 0.75, "label": "Pump service access",
        "basis": "Manufacturer service clearance for seal / impeller replacement",
        "why": "Seals are a wear item; the space is needed repeatedly over the asset's life."},
    "ifcdoor": {
        "distance_m": 0.9, "label": "Door swing / approach",
        "basis": "Manoeuvring clearance on the approach side",
        "why": "A door that fouls a duct drop is discovered by the person carrying something."},
}

MAX_ELEMENTS = 200_000          # bound the sweep; a model past this needs the job queue, not a GET


def rule_for(ifc_class: str) -> dict[str, Any] | None:
    """The clearance rule for a class, or None when we have no *stated* rule for it.

    Returning None rather than a default distance is deliberate. A made-up clearance produces
    confident findings nobody can defend, and the whole point of the `basis` field is that every
    number here can be traced to something.
    """
    return CLEARANCE_RULES.get(str(ifc_class or "").lower())


def scoped_classes() -> list[str]:
    return sorted(CLEARANCE_RULES)


# ── the discipline-pair matrix ───────────────────────────────────────────────────────────────────
# Which discipline pairs a coordination run actually tested. Declared, not inferred: inferring
# "we tested it because we found something" means a pair with no findings is indistinguishable from
# a pair that never ran, which is exactly the confusion this exists to remove.
def pair_key(a: str, b: str) -> tuple[str, str]:
    """Order-independent key, so Structural×MEP and MEP×Structural are one pair."""
    x, y = (str(a or "?").strip() or "?"), (str(b or "?").strip() or "?")
    return (x, y) if x <= y else (y, x)


def matrix(disciplines: list[str], tested_pairs: list[tuple[str, str]] | None = None,
           findings: list[dict] | None = None) -> dict[str, Any]:
    """Build the coordination matrix over `disciplines`.

    Every unordered pair lands in exactly one of three states, and the third is the point:

    * ``clashes``  — tested, and something was found
    * ``clean``    — tested, and nothing was found
    * ``untested`` — **not run.** Not clean. A report may not count these as coordinated.
    """
    discs = sorted({str(d or "?").strip() or "?" for d in (disciplines or [])})
    tested = {pair_key(a, b) for a, b in (tested_pairs or [])}

    hits: dict[tuple[str, str], int] = {}
    for f in (findings or []):
        k = pair_key(f.get("discipline_a") or "?", f.get("discipline_b") or "?")
        hits[k] = hits.get(k, 0) + 1

    cells = []
    for i, a in enumerate(discs):
        for b in discs[i:]:
            k = pair_key(a, b)
            n = hits.get(k, 0)
            if k in tested:
                state = "clashes" if n else "clean"
            else:
                # a finding on a pair nobody declared as tested still means it WAS tested — trust the
                # evidence over the declaration, but never the other way round
                state = "clashes" if n else "untested"
            cells.append({"a": a, "b": b, "state": state, "count": n})

    counts = {"clashes": 0, "clean": 0, "untested": 0}
    for c in cells:
        counts[c["state"]] += 1
    total = len(cells)
    return {
        "disciplines": discs,
        "cells": cells,
        "pair_count": total,
        "counts": counts,
        "coverage_pct": round(100.0 * (total - counts["untested"]) / total, 1) if total else 0.0,
        # the single claim a coordination report is entitled to make
        "coordinated": total > 0 and counts["untested"] == 0 and counts["clashes"] == 0,
        "note": ("An untested discipline pair is reported as untested, never as clean — "
                 "'clash-free' over a partial matrix overstates what was checked."),
    }
