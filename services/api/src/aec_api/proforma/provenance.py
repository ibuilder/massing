"""R24-TRACE-UI ② — the proforma emits its own derivation.

Every headline figure a deal is argued on is a number with no visible parentage: an equity IRR looks
identical whether it rests on ten inputs the sponsor supplied or on three they supplied and seven the
engine defaulted. **That difference is the whole question an IC memo is trying to answer**, and today it
is invisible — `proforma/*.py` contains zero `GlobalId`/`guid` references and no figure records what fed
it. Downstream that becomes a citation problem: a reviewer who cannot see which assumptions were
*assumed* has to re-derive the model to trust it.

## What this does and — more importantly — what it refuses to do

It reports **input provenance**: for each headline figure, which assumption keys fed it, and for each of
those whether the caller **declared** it or the engine **defaulted** it. That is checkable against the
assumptions dict, so every claim here is evidence rather than assertion.

It does **not** invent an element link. `element_link` is `None` on every figure, with a stated reason,
because the proforma genuinely holds no GlobalId today. The tempting version of this feature emits a
trace that *looks* like it walks to a model element while actually asserting one — the fabrication shape
this repo has spent real effort naming. A trace whose terminus is invented is worse than no trace: it is
the same screen, and it is trusted.

`BASIS` is deliberately about the INPUT, not about confidence. "Defaulted" is not a criticism — a
default is often the right choice — it is a fact the reader is entitled to.

## The one thing that makes this correct, and would silently break it

**Provenance MUST be computed on `model_dump(exclude_unset=True)`, never on `model_dump()`.**

The routes call `solve(a.model_dump())`, and by that point pydantic has already substituted every
default — `credit_loss_pct` is `0.0`, `reserves_annual` is `0.0`, and the dict cannot be distinguished
from one where the sponsor typed those zeros. Deriving from it would report **every input as declared**
and produce a provenance record that is confidently, uniformly wrong: the worst possible output, because
it answers the question and the answer is fiction.

`exclude_unset=True` returns only the keys the caller actually sent, which is precisely the "declared"
set. `declared_from()` below is the one supported way to obtain it, and `test_proforma_provenance`
asserts the distinction survives a real `Assumptions` round-trip rather than trusting this note.
"""
from __future__ import annotations

from typing import Any

#: Where a figure's inputs came from. `declared` = the caller supplied it; `defaulted` = the engine
#: substituted its own value because the key was absent. There is no third state today: a figure is
#: built from assumption keys, and a key was either given or it was not.
BASIS = ("declared", "defaulted", "mixed", "none")

#: Why no figure carries a GlobalId. Stated once, returned on every figure, so a consumer that renders a
#: trace cannot quietly present the absence as an unlinked *element* rather than an unlinked *layer*.
NO_ELEMENT_LINK = ("the proforma layer holds no element link — no figure in `proforma/` references a "
                   "GlobalId, so a terminus here would be invented rather than resolved")

#: Headline figure -> the assumption paths that feed it, as `section.key`. Hand-maintained **and
#: completeness-checked**: `test_proforma_provenance` asserts every figure in `solve()`'s headline
#: sections has an entry here, because a hand-maintained map that silently stops covering new figures is
#: the exact rot this repo keeps finding. Paths are the keys `solve()` actually reads — verified by
#: reading the arithmetic, not by guessing from the figure's name.
FIGURE_INPUTS: dict[str, tuple[str, ...]] = {
    # --- operations: NOI is the root of value, debt sizing and the exit -----------------------------
    "operations.stabilized_noi_annual": (
        "operations.potential_rent_annual", "operations.stabilized_occ", "operations.credit_loss_pct",
        "operations.other_income_annual", "operations.opex_annual", "operations.reserves_annual"),
    "operations.reversion": ("exit.exit_cap", "exit.selling_cost_pct"),
    # --- debt sizing --------------------------------------------------------------------------------
    "debt_sizing.stabilized_value": ("operations.potential_rent_annual", "exit.exit_cap"),
    "debt_sizing.binding_constraint": ("debt.max_ltv", "debt.min_dscr", "debt.min_debt_yield", "debt.ltc"),
    "debt_sizing.actual_dscr": ("debt.rate", "debt.min_dscr"),
    "debt_sizing.actual_debt_yield": ("debt.min_debt_yield",),
    "debt_sizing.actual_ltv": ("debt.max_ltv", "exit.exit_cap"),
    # --- sources & uses -----------------------------------------------------------------------------
    "sources_uses.total_uses": ("cost_lines", "timing.construction_months"),
    "sources_uses.loan_amount": ("debt.ltc", "debt.max_ltv", "debt.min_dscr", "debt.min_debt_yield"),
    "sources_uses.loan_fees": ("debt.points",),
    "sources_uses.interest_reserve": ("debt.rate", "timing.construction_months"),
    "sources_uses.equity": ("equity.lp_pct", "equity.gp_pct"),
    # --- returns ------------------------------------------------------------------------------------
    "returns.project_irr": ("timing.start_date", "timing.hold_years", "cost_lines", "exit.exit_cap"),
    "returns.equity_irr": ("equity.lp_pct", "equity.gp_pct", "debt.rate", "timing.hold_years"),
    "returns.equity_multiple": ("equity.lp_pct", "equity.gp_pct"),
    "returns.npv": ("discount_rate", "timing.hold_years"),
    "returns.yield_on_cost": ("operations.opex_annual", "cost_lines"),
    "returns.exit_cap": ("exit.exit_cap",),
    "returns.dev_spread": ("exit.exit_cap", "operations.opex_annual"),
}

#: The sections of `solve()`'s output whose members are headline figures. `cash_flow` and `waterfall`
#: are excluded on purpose: they are series and schedules, not single arguable numbers, and pretending
#: to derive each period would produce noise nobody reads.
HEADLINE_SECTIONS = ("sources_uses", "debt_sizing", "operations", "returns")

#: Members of those sections that are NOT arguable figures — diagnostics and pass-throughs. Listed so
#: the completeness check can tell "deliberately not derived" from "forgotten".
NOT_FIGURES = frozenset({
    "sources_uses.ltc", "sources_uses.effective_ltc",
    "sources_uses.lp_contribution", "sources_uses.gp_contribution",
    "sources_uses.unscheduled_lines", "sources_uses.unscheduled_amount",
    "debt_sizing.caps",
    "returns.total_contributions", "returns.total_distributions",
})


def _lookup(a: dict, path: str) -> tuple[bool, Any]:
    """(present, value) for a dotted assumption path. Present means the CALLER supplied the key.

    An explicit `None` counts as absent: the engine will substitute, so the number downstream is the
    engine's, and saying otherwise would credit the caller with a value they did not choose.
    """
    node: Any = a
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return (node is not None), node


def declared_from(assumptions: Any) -> dict:
    """The keys the CALLER actually supplied, from a pydantic `Assumptions` (or a plain dict).

    This is the only supported way to build the input to `derive()`. Passing a full `model_dump()`
    instead is not a smaller mistake — it silently reclassifies every default as a sponsor decision, and
    the resulting record looks complete. See the module docstring.
    """
    dump = getattr(assumptions, "model_dump", None)
    if callable(dump):
        return dump(exclude_unset=True)
    return dict(assumptions or {})


def figure_basis(a: dict, inputs: tuple[str, ...]) -> dict[str, Any]:
    """Classify one figure's inputs as declared / defaulted, and summarise."""
    declared, defaulted = [], []
    for path in inputs:
        present, value = _lookup(a, path)
        (declared if present else defaulted).append(
            {"path": path, "value": value if present else None})
    if not inputs:
        basis = "none"
    elif not defaulted:
        basis = "declared"
    elif not declared:
        basis = "defaulted"
    else:
        basis = "mixed"
    return {"basis": basis, "declared": declared, "defaulted": defaulted,
            "declared_count": len(declared), "defaulted_count": len(defaulted)}


def derive(a: dict, solved: dict) -> dict[str, Any]:
    """The derivation record for a solved proforma: one entry per headline figure.

    Pure over the two dicts — no DB, no IO — so it is testable without a project and cannot drift from
    `solve()` by depending on anything `solve()` does not.
    """
    figures: dict[str, Any] = {}
    for key, inputs in FIGURE_INPUTS.items():
        section, name = key.split(".", 1)
        value = (solved.get(section) or {}).get(name)
        figures[key] = {
            "value": value,
            **figure_basis(a, inputs),
            # Never a guessed terminus. See NO_ELEMENT_LINK.
            "element_link": None,
            "element_link_reason": NO_ELEMENT_LINK,
        }
    by_basis: dict[str, int] = {}
    for f in figures.values():
        by_basis[f["basis"]] = by_basis.get(f["basis"], 0) + 1
    # The number a reviewer actually wants: which assumptions nobody supplied. Deduped across figures,
    # sorted so the list is stable enough to diff between two runs of the same deal.
    all_defaulted = sorted({d["path"] for f in figures.values() for d in f["defaulted"]})
    return {
        "figure_count": len(figures),
        "by_basis": by_basis,
        "defaulted_inputs": all_defaulted,
        "defaulted_input_count": len(all_defaulted),
        "figures": figures,
        "note": ("Input provenance only: which assumptions the caller declared and which the engine "
                 "defaulted. No figure carries an element link — see `element_link_reason`."),
    }
