"""R22-ENTITLE-RISK — approval probability and entitlement duration in the Monte Carlo.

The ring calls this *"the largest unmodelled uncertainty in any acquisition proforma"*, and in this
codebase it is unmodelled twice over:

* **`Timing` has no pre-construction period at all.** `construction_months`, `leaseup_months`,
  `hold_years` — the deal begins the day the shovel goes in. Nothing represents the 6–30 months
  between buying a site and being allowed to build on it, so nothing charges for them.
* **`monte_carlo` can only sample continuous drivers** — normal, uniform, triangular, each set onto
  a dotted path. Approval is not a number on a path. It is a coin, and the two faces are different
  projects.

**The decision that shapes this whole module: a denied entitlement is not a bad IRR.** The tempting
implementation is to make denial a very poor draw and let it flow through `solve()` with everything
else. It cannot, for a reason that is arithmetic rather than stylistic: if the entitlement is
refused, the building is never built, there is no NOI, no exit, no equity multiple. Pushing that
scenario through a solver that assumes construction proceeds produces a *number*, and that number
then sits inside the P5–P95 of a distribution describing a project that does not exist.

So denial is a **terminal branch with its own economics** — pursuit costs sunk, carry spent to the
date of refusal, land recovered at whatever it fetches — and denied draws are reported as their own
population. The approved distribution is reported too, labelled as conditional on approval, because
that is a real and useful number as long as nobody mistakes it for the deal.

**Probability of clearing a hurdle counts denied draws in the denominator.** A 15% IRR target is not
cleared by an entitlement that was refused. This mirrors the choice already made in
`monte_carlo._summary` for undefined metrics, and for the same reason: dividing by the draws that
happened to work out answers "P[good | it worked]", which flatters a deal exactly when it is at its
riskiest.

**A duration that costs nothing is refused rather than accepted.** Sampling entitlement months and
then charging nothing for them changes no output at all — the run completes, the report shows a
duration distribution, and every metric is identical to the run without it. That is worse than an
error, because it looks modelled. `carry_cost_monthly` is therefore required whenever
`duration_months` is given.

**Known limitation, stated because it moves the answer in a knowable direction.** The model has no
pre-construction period to schedule into, so entitlement carry is capitalised as a month-0 soft cost
rather than time-phased ahead of construction. Real entitlement spend leaves the account earlier than
that, so its interest carry is **understated** — this makes the entitled deal look slightly better
than it is, never worse. Fixing it properly means giving `Timing` a pre-construction period, which is
a schema change and a separate piece of work.
"""
from __future__ import annotations

import copy
from typing import Any

import numpy as np

from .monte_carlo import _sample, _summary
from .sensitivity import _get_metric, _set_path
from .solve import solve

DEFAULT_METRICS = ["returns.equity_irr", "returns.equity_multiple",
                   "returns.project_irr", "returns.npv"]


class EntitlementError(ValueError):
    """The entitlement inputs cannot produce an honest answer."""


def _f(d: dict, key: str, default: float | None = None) -> float:
    v = d.get(key, default)
    if v is None:
        raise EntitlementError(f"entitlement.{key} is required")
    try:
        return float(v)
    except (TypeError, ValueError) as e:
        raise EntitlementError(f"entitlement.{key} must be a number, got {v!r}") from e


def _validate(ent: dict) -> None:
    p = _f(ent, "approval_probability")
    if not 0.0 <= p <= 1.0:
        raise EntitlementError(f"approval_probability must be between 0 and 1, got {p}")
    if "duration_months" in ent and ent["duration_months"] is not None:
        if ent.get("carry_cost_monthly") is None:
            raise EntitlementError(
                "duration_months was given without carry_cost_monthly. Sampling a duration that "
                "costs nothing changes no output — every metric would be identical to a run without "
                "it, while the report showed a duration distribution. That is worse than an error, "
                "because it looks modelled.")
        if _f(ent, "carry_cost_monthly") < 0:
            raise EntitlementError("carry_cost_monthly cannot be negative")
    lr = ent.get("land_recovery_pct")
    if lr is not None and not 0.0 <= float(lr) <= 1.0:
        raise EntitlementError(f"land_recovery_pct must be between 0 and 1, got {lr}")


def denial_outcome(ent: dict, months: float) -> dict[str, Any]:
    """What a refusal actually costs, at the month it is refused.

    Not an IRR. A refused entitlement has no holding period to annualise over in any way a reader
    would trust — the loss is realised whenever the authority says no, and dressing that up as a rate
    of return invites it to be compared with the approved IRRs, which is precisely the comparison
    this module exists to prevent.
    """
    pursuit = float(ent.get("pursuit_cost", 0) or 0)
    carry = float(ent.get("carry_cost_monthly", 0) or 0) * max(0.0, months)
    land = float(ent.get("land_basis", 0) or 0)
    recovery_pct = float(ent.get("land_recovery_pct", 1.0) if ent.get("land_recovery_pct") is not None
                         else 1.0)
    land_recovered = land * recovery_pct
    spent = pursuit + carry + land
    return {
        "months_to_refusal": round(months, 2),
        "pursuit_cost": round(pursuit, 2),
        "carry_cost": round(carry, 2),
        "land_basis": round(land, 2),
        "land_recovered": round(land_recovered, 2),
        "capital_deployed": round(spent, 2),
        # Negative = money lost. Signed so it sums with approved-case equity without a convention
        # anyone has to remember.
        "net_loss": round(land_recovered - spent, 2),
    }


def _with_entitlement_carry(assumptions: dict, months: float, monthly: float) -> dict:
    """A copy of the assumptions with entitlement carry added as a month-0 soft cost.

    See the module docstring's limitation note: month 0 because there is nowhere earlier to put it,
    and the resulting understatement of interest carry favours the deal.
    """
    a = copy.deepcopy(assumptions)
    amount = round(months * monthly, 2)
    if amount:
        a.setdefault("cost_lines", []).append({
            "category": "soft", "name": "Entitlement carry",
            "amount": amount, "start_month": 0, "end_month": 0,
        })
    return a


def simulate(assumptions: dict, entitlement: dict, *, variables: list[dict] | None = None,
             iterations: int = 1000, seed: int = 42, metrics: list[str] | None = None,
             targets: dict[str, float] | None = None) -> dict[str, Any]:
    """Monte Carlo over the approval coin, the entitlement duration, and any other drivers.

    Each iteration: draw approval. If approved, draw a duration, charge its carry, and solve. If
    refused, do not solve — record the denial's own economics instead.
    """
    _validate(entitlement)
    metrics = list(metrics or DEFAULT_METRICS)
    targets = targets or {}
    variables = list(variables or [])
    n = max(1, int(iterations))
    rng = np.random.default_rng(seed)

    p_approve = _f(entitlement, "approval_probability")
    approved_draws = rng.random(n) < p_approve

    dist = entitlement.get("duration_months")
    monthly = float(entitlement.get("carry_cost_monthly", 0) or 0)
    if dist:
        months = _sample(rng, dist, n)
        months = np.clip(months, 0.0, None)     # a negative entitlement period is not a thing
    else:
        months = np.zeros(n)

    other = {v["path"]: _sample(rng, v["dist"], n) for v in variables}

    collected: dict[str, list[float]] = {m: [] for m in metrics}
    denials: list[dict[str, Any]] = []
    failures = 0

    for i in range(n):
        if not approved_draws[i]:
            denials.append(denial_outcome(entitlement, float(months[i])))
            continue
        a = _with_entitlement_carry(assumptions, float(months[i]), monthly)
        for path, arr in other.items():
            _set_path(a, path, float(arr[i]))
        try:
            res = solve(a)
        except Exception:  # noqa: BLE001 — an unsolvable draw is a failure, counted not hidden
            failures += 1
            continue
        for m in metrics:
            val = _get_metric(res, m)
            collected[m].append(float(val) if val is not None else float("nan"))

    n_denied = len(denials)
    n_approved = n - n_denied
    solved = n_approved - failures

    out: dict[str, Any] = {
        "iterations": n,
        "seed": seed,
        "approval_probability": p_approve,
        "approved": n_approved,
        "denied": n_denied,
        "denied_share": round(n_denied / n, 4),
        "solve_failures": failures,
        "solved": solved,
        "entitlement_months": _months_summary(months, approved_draws),
        "variables": [{"path": v["path"], "dist": v["dist"]} for v in variables],
        # Conditional on approval, and labelled as such at the point of use — this is the number most
        # likely to be quoted without its condition.
        "metrics_given_approval": {
            m: _summary(np.array(vals, dtype=float), targets.get(m))
            for m, vals in collected.items()},
        "metrics_are_conditional": (
            f"the distributions above describe the {solved} solved draw(s) in which the entitlement "
            f"was GRANTED. They say nothing about the {n_denied} draw(s) in which it was refused, "
            "which are reported separately — a refused entitlement has no IRR because there is no "
            "project"),
        "denial": _denial_summary(denials),
    }
    out["probability_of_clearing"] = {
        m: _unconditional_target(collected[m], t, n, n_approved)
        for m, t in targets.items() if m in collected
    }
    out["expected_value"] = _expected_value(collected, denials, n, metrics, failures)
    return out


def _months_summary(months: np.ndarray, approved: np.ndarray) -> dict[str, Any]:
    """Duration stats. Reported for the APPROVED draws, because that is the period actually spent
    reaching an approval; the refused draws carry their own months into the denial economics."""
    vals = months[approved]
    if vals.size == 0:
        return {"n": 0, "note": "no draw was approved"}
    return {
        "n": int(vals.size),
        "mean": round(float(vals.mean()), 2),
        "p10": round(float(np.percentile(vals, 10)), 2),
        "p50": round(float(np.percentile(vals, 50)), 2),
        "p90": round(float(np.percentile(vals, 90)), 2),
        "max": round(float(vals.max()), 2),
    }


def _unconditional_target(vals: list[float], target: float, n_total: int,
                          n_approved: int) -> dict[str, Any]:
    """P[metric ≥ target] over EVERY iteration, denied ones included.

    A refused entitlement does not clear an IRR hurdle. Dividing by the approved draws instead
    answers "P[clears | it was approved]", which is a different and much friendlier question.

    **The conditional denominator is `n_approved`, not the number of draws we managed to solve.**
    `vals` only receives a value when `solve()` succeeded, so dividing by `len(vals)` silently drops
    every approved-but-unsolvable draw out of the denominator and *raises* the reported probability —
    the friendlier number again, arrived at by a different route. An approved draw that could not be
    solved did not clear the hurdle; it is a non-hit, not an absentee.

    The numerator is counted over the NaN-stripped array while the denominator is a draw count, so
    the two describe the same population deliberately: a draw with an undefined metric is likewise a
    non-hit rather than a row removed from the bottom of the fraction.
    """
    arr = np.array(vals, dtype=float)
    defined = arr[~np.isnan(arr)]
    hits = int((defined >= target).sum()) if defined.size else 0
    return {
        "target": target,
        "probability": round(hits / n_total, 4),
        "hits": hits,
        "of_iterations": n_total,
        "probability_given_approval": (round(hits / n_approved, 4) if n_approved else None),
        "given_approval_denominator": n_approved,
        "note": "the headline probability counts every iteration; a refused entitlement cannot clear "
                "a return hurdle. The conditional figure is shown beside it, not instead of it, and "
                "its denominator is every APPROVED draw — an approved draw that failed to solve "
                "counts as not clearing, rather than being dropped from the denominator",
    }


def _denial_summary(denials: list[dict[str, Any]]) -> dict[str, Any]:
    if not denials:
        return {"n": 0, "note": "no draw was refused"}
    losses = np.array([d["net_loss"] for d in denials], dtype=float)
    return {
        "n": len(denials),
        "mean_net_loss": round(float(losses.mean()), 2),
        "worst_net_loss": round(float(losses.min()), 2),
        "best_net_loss": round(float(losses.max()), 2),
        "mean_capital_deployed": round(float(np.mean([d["capital_deployed"] for d in denials])), 2),
        "note": "net_loss is signed — negative is money lost. No IRR is reported: a refused "
                "entitlement has no holding period a reader would trust, and quoting a rate would "
                "invite comparison with the approved returns",
    }


def _expected_value(collected: dict[str, list[float]], denials: list[dict[str, Any]],
                    n_total: int, metrics: list[str], failures: int = 0) -> dict[str, Any]:
    """Probability-weighted NPV across both branches — the one number that spans them.

    Only NPV is blended, and only NPV can be: it is a value in currency, so a denial's loss and an
    approval's gain are the same unit and adding them means something. IRR and equity multiple are
    ratios over a project that, in the denied branch, does not exist — there is nothing to average
    them against, and an "expected IRR" built by treating a refusal as a 0% return would be a
    fabrication with a plausible shape.
    """
    npvs = np.array(collected.get("returns.npv", []), dtype=float)
    defined = npvs[~np.isnan(npvs)] if npvs.size else npvs
    if not n_total:
        return {"available": False, "reason": "no iterations"}
    if defined.size == 0 and not denials:
        return {"available": False, "reason": "no solved draws and no denials"}
    approved_total = float(defined.sum()) if defined.size else 0.0
    denied_total = float(sum(d["net_loss"] for d in denials))
    # THE DENOMINATOR IS THE POPULATION WE ACTUALLY VALUED, not every iteration.
    #
    # A draw that failed to solve contributes nothing to the numerator, so dividing by `n_total`
    # silently prices it at **zero NPV** — a number nobody computed, quietly averaged in with ones
    # somebody did. With failures present that biases `expected_npv` toward zero by exactly the
    # failure fraction, and the payload gave no sign of it.
    #
    # A failed solve is not a project worth nothing; it is a project we could not value. Same rule
    # the vitals strip follows: state the basis, and never let an absent value masquerade as a zero.
    valued = len(defined) + len(denials)
    if not valued:
        return {"available": False, "reason": "no draw could be valued"}
    ev = (approved_total + denied_total) / valued
    return {
        "available": True,
        "metric": "returns.npv",
        "expected_npv": round(ev, 2),
        "basis": "solved approvals and denials",
        "valued_draws": valued,
        "excluded_solve_failures": failures,
        "excluded_note": (
            f"{failures} approved draw(s) could not be solved and are EXCLUDED from the expectation "
            "rather than counted as zero. Pricing an unsolvable draw at zero would drag the "
            "expectation toward it by the failure share, which is a fabrication with a plausible "
            "shape" if failures else
            "every drawn iteration was either valued or denied; nothing was excluded"),
        "approved_mean_npv": round(float(defined.mean()), 2) if defined.size else None,
        "denied_mean_loss": round(denied_total / len(denials), 2) if denials else None,
        "blended": "npv only",
        "why_only_npv": (
            "NPV is a currency amount, so an approval's gain and a refusal's loss are the same unit "
            "and adding them means something. IRR and equity multiple are ratios over a project that "
            "does not exist in the denied branch; an 'expected IRR' that treated a refusal as a 0% "
            "return would be a fabrication with a plausible shape"),
        "excluded_metrics": [m for m in metrics if m != "returns.npv"],
    }
