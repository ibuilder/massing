"""W10-9 / R23-CONSTRAINTS — dimensional locks: keep a wall 3000 from a grid, and say so when you can't.

A BIM dimensional constraint is not a general geometric constraint solver. It is a **linear** system
over scalar positions — an axis distance, an alignment, an offset, equal spacing along a run of grids
or mullions, a level-height chain, a minimum clearance — plus a notion of which constraint yields
when two of them disagree.

**No new dependency.** The roadmap unblocked this by taking `kiwisolver` (Cassowary, BSD-3), on the
reasoning that its inequalities-and-strengths model fits BIM locks. That reasoning is right about the
*shape* and wrong about the *need*: `numpy` and `scipy` are already here, and this shape is a linear
least-squares problem with priority tiers. `lstsq`'s **rank** is the degrees of freedom, and its
**residual** is whether the tier is satisfiable — the two numbers the UX actually needs. Checking that
before adding a package is the same habit that has been paying all session; the dependency was
reversible, but the best version of a reversible decision is not having to make it.

**Three properties decide whether this is worth having.**

*An over-constrained system NAMES the conflict.* Two constraints that cannot both hold are a modelling
error, and the only useful response is to say which pair. Silently satisfying one — whichever the
solver reached first — produces geometry that looks deliberate and is not, and the author has no way
to find out.

*Strength is a tier, not a weight.* A `required` constraint is not "a very heavy soft constraint".
Blending them lets a strong preference bend a hard lock by a millimetre, which is exactly the failure
that makes people stop trusting locks. Tiers are solved in order: each one is satisfied exactly, then
frozen, and the next may only move what is left free.

*Under-constrained is reported, not defaulted.* A system with degrees of freedom left has infinitely
many solutions, and picking one quietly is how a "solved" sketch drifts on the next edit. The DOF
count is in the result.
"""
from __future__ import annotations

from typing import Any

import numpy as np

#: Strength tiers, strongest first. `required` must hold exactly or the system is over-constrained;
#: the rest are preferences honoured in order, each within the freedom the stronger ones left.
STRENGTHS = ("required", "strong", "medium", "weak")

#: What each constraint kind asserts. Every kind is linear in the variables — that is the whole reason
#: this is tractable without a geometric solver.
KINDS = {
    "fix": "This variable equals a value",
    "equal": "Two variables are equal (alignment)",
    "distance": "b - a equals a distance (a dimensional lock)",
    "offset": "b equals a plus an offset (signed; the sign is the direction)",
    "equal_spacing": "Three or more variables are evenly spaced (grids, mullions, level chains)",
    "min_clearance": "b - a is at least a minimum (code clearance, and the reason ≥ exists here)",
}

#: Residual (in model units) below which a tier counts as satisfied. Millimetres are the working unit
#: in this codebase, so this is a micron — far below any real tolerance, and above float noise.
TOL = 1e-6

MAX_VARS = 5000
MAX_CONSTRAINTS = 20_000


class ConstraintError(ValueError):
    """A malformed constraint. Refused rather than dropped: a lock nobody applied is worse than an
    error, because the model looks constrained and is not."""


def _rows(c: dict[str, Any], index: dict[str, int], n: int) -> list[tuple[np.ndarray, float]]:
    """The linear rows a constraint contributes: each is (coefficients, target)."""
    kind = str(c.get("kind") or "").strip().lower()
    if kind not in KINDS:
        raise ConstraintError(f"unknown kind {kind!r}; expected one of {sorted(KINDS)}")

    def var(name: str) -> int:
        if name not in index:
            raise ConstraintError(f"constraint {c.get('id') or kind!r} references unknown variable {name!r}")
        return index[name]

    def row(pairs: list[tuple[str, float]], target: float) -> tuple[np.ndarray, float]:
        r = np.zeros(n)
        for name, coef in pairs:
            r[var(name)] += coef
        return r, float(target)

    if kind == "fix":
        return [row([(c["a"], 1.0)], c.get("value", 0.0))]
    if kind == "equal":
        return [row([(c["b"], 1.0), (c["a"], -1.0)], 0.0)]
    if kind in ("distance", "offset"):
        key = "distance" if kind == "distance" else "offset"
        if c.get(key) is None:
            raise ConstraintError(f"{kind} needs a {key}")
        return [row([(c["b"], 1.0), (c["a"], -1.0)], float(c[key]))]
    if kind == "equal_spacing":
        names = list(c.get("vars") or [])
        if len(names) < 3:
            raise ConstraintError("equal_spacing needs at least three variables")
        # Even spacing is (v[i+1] - v[i]) - (v[i+2] - v[i+1]) = 0 across the run. It deliberately does
        # NOT pin the spacing itself — that is what a separate distance lock is for, and conflating
        # them would make "evenly spaced" silently also mean "at this pitch".
        return [row([(names[i + 1], 2.0), (names[i], -1.0), (names[i + 2], -1.0)], 0.0)
                for i in range(len(names) - 2)]
    return []                                  # min_clearance is an inequality, handled separately


def solve(variables: dict[str, float], constraints: list[dict[str, Any]]) -> dict[str, Any]:
    """Solve the locks, tier by tier, and report what could not be satisfied.

    `variables` maps name → current value (the starting point, and the fallback for anything the
    constraints leave free). Returns the solved values plus `dof`, `conflicts` and `violations`.
    """
    if len(variables) > MAX_VARS or len(constraints) > MAX_CONSTRAINTS:
        raise ConstraintError(f"too large (max {MAX_VARS} variables, {MAX_CONSTRAINTS} constraints)")
    names = list(variables)
    index = {nm: i for i, nm in enumerate(names)}
    n = len(names)
    if n == 0:
        return {"values": {}, "dof": 0, "solved": True, "conflicts": [], "violations": [],
                "tiers": [], "note": "no variables"}

    x = np.array([float(variables[nm]) for nm in names])
    clearances: list[dict[str, Any]] = []
    by_tier: dict[str, list[dict[str, Any]]] = {s: [] for s in STRENGTHS}
    for c in constraints:
        if not isinstance(c, dict):
            raise ConstraintError("each constraint must be an object")
        strength = str(c.get("strength") or "required").strip().lower()
        if strength not in STRENGTHS:
            raise ConstraintError(f"unknown strength {strength!r}; expected one of {list(STRENGTHS)}")
        if str(c.get("kind") or "").lower() == "min_clearance":
            clearances.append(c)
            continue
        by_tier[strength].append(c)

    # Each tier is solved INSIDE THE NULL SPACE of everything already fixed. That is what makes
    # strength a tier rather than a weight, and the first version got it wrong in exactly the way this
    # module's docstring warns about: it stacked the frozen rows into the same least-squares problem,
    # so a `strong` preference could trade against a `required` lock and did — a hard 3000 lock came
    # out at 7666 because the preference pulled both variables. Least squares has no notion of "this
    # row is not negotiable"; the only way to say it is to remove those directions from the search.
    #
    # `xp` is a particular solution satisfying every tier so far; `basis` spans the directions still
    # free. A weaker tier may only move within `basis`, so it is arithmetically incapable of
    # disturbing a stronger one.
    xp = x.copy()
    basis = np.eye(n)
    conflicts: list[dict[str, Any]] = []
    tiers: list[dict[str, Any]] = []

    for strength in STRENGTHS:
        rows: list[np.ndarray] = []
        targets: list[float] = []
        owners: list[dict[str, Any]] = []
        for c in by_tier[strength]:
            for r, t in _rows(c, index, n):
                rows.append(r)
                targets.append(t)
                owners.append(c)
        if not rows:
            continue
        A = np.vstack(rows)
        b = np.array(targets)
        if basis.shape[1] == 0:
            # Nothing left to move. Every row of this tier either already holds or cannot.
            resid = A @ xp - b
        else:
            M = A @ basis
            rhs = b - A @ xp
            z, *_ = np.linalg.lstsq(M, rhs, rcond=None)
            xp = xp + basis @ z
            resid = A @ xp - b

        satisfied = [i for i in range(len(rows)) if abs(resid[i]) <= TOL]
        for i in range(len(rows)):
            if abs(resid[i]) > TOL:
                c = owners[i]
                conflicts.append({"strength": strength, "kind": c.get("kind"),
                                  "id": c.get("id"), "residual": round(float(resid[i]), 6),
                                  "detail": "cannot hold given the stronger constraints already fixed"})
        tiers.append({"strength": strength, "rows": len(rows),
                      "satisfied": len(satisfied), "conflicted": len(rows) - len(satisfied)})

        # Only the rows this tier actually SATISFIED remove freedom. Freezing a conflicted row would
        # propagate one modelling error into every weaker tier as a phantom constraint.
        if satisfied and basis.shape[1] > 0:
            from scipy.linalg import null_space
            inner = null_space(A[satisfied] @ basis)
            basis = basis @ inner if inner.size else np.zeros((n, 0))

    x = xp
    # Degrees of freedom ARE the remaining free directions — no separate rank computation
    # that could disagree with the solve that just happened.
    dof = int(basis.shape[1])

    # Inequalities are CHECKED, not enforced. A clearance that fails is a finding for the author, and
    # silently sliding geometry to satisfy a code minimum would move a wall somebody placed on purpose
    # — the opposite of what a lock is for.
    violations = []
    for c in clearances:
        a, bnm = c.get("a"), c.get("b")
        if a not in index or bnm not in index:
            raise ConstraintError(f"min_clearance references an unknown variable ({a!r}, {bnm!r})")
        need = float(c.get("min", 0.0))
        got = float(x[index[bnm]] - x[index[a]])
        if got < need - TOL:
            violations.append({"id": c.get("id"), "a": a, "b": bnm, "min": need,
                               "actual": round(got, 6), "short_by": round(need - got, 6)})

    return {
        "values": {nm: round(float(x[i]), 6) for i, nm in enumerate(names)},
        "dof": int(dof),
        # `solved` means every REQUIRED row holds and no clearance is violated. A weaker tier yielding
        # is the system working as designed, not a failure.
        "solved": not any(c["strength"] == "required" for c in conflicts) and not violations,
        "conflicts": conflicts,
        "violations": violations,
        "tiers": tiers,
        "note": ("`dof` > 0 means the system is under-constrained and this is ONE of infinitely many "
                 "solutions — reported rather than defaulted. A conflict names the constraint that "
                 "could not hold; strengths are tiers, not weights, so a preference can never bend a "
                 "`required` lock. Clearances are checked, never enforced: sliding geometry to satisfy "
                 "a minimum would move something somebody placed on purpose."),
    }
