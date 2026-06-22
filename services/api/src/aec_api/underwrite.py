"""Underwriting guardrails (U5) — sanity-check a solved proforma against market bands and flag
returns that look too good (or too thin) to be real, so the IRR is credible rather than just
arithmetically correct. Pure over the solve() result. Bands reflect typical institutional ranges
(equity IRR ~8–25%, equity multiple ~1.5–3x, positive development spread, DSCR ≥ ~1.2)."""
from __future__ import annotations

from typing import Any


def guardrails(result: dict[str, Any]) -> dict[str, Any]:
    """Return {flags:[{level, metric, message}], ok: bool} for a solved proforma result.
    level ∈ high|med|info. `high` = likely-unrealistic input; `med` = thin/marginal; `info` = note."""
    ret = result.get("returns") or {}
    flags: list[dict[str, str]] = []

    def flag(level: str, metric: str, message: str):
        flags.append({"level": level, "metric": metric, "message": message})

    irr = ret.get("equity_irr")
    if isinstance(irr, (int, float)):
        if irr > 0.35:
            flag("high", "equity_irr", f"Equity IRR {irr * 100:.0f}% is implausibly high — check that "
                 "operating/specialty revenue is risk-adjusted (not gross) and opex is fully built.")
        elif irr > 0.25:
            flag("med", "equity_irr", f"Equity IRR {irr * 100:.0f}% is above typical stabilized range "
                 "(8–25%) — confirm the upside is defensible.")
        elif irr < 0.08:
            flag("med", "equity_irr", f"Equity IRR {irr * 100:.0f}% is below the ~8% equity threshold "
                 "most LPs require.")

    em = ret.get("equity_multiple")
    if isinstance(em, (int, float)) and em > 4:
        flag("high", "equity_multiple", f"Equity multiple {em:.1f}x is far above the typical 1.5–3x — "
             "usually a sign revenue is overstated.")

    spread = ret.get("dev_spread")           # bps of yield-on-cost over exit cap
    if isinstance(spread, (int, float)):
        if spread < 0:
            flag("high", "dev_spread", "Negative development spread — building to a yield below the "
                 "exit cap destroys value. Lower cost or raise NOI.")
        elif spread < 100:
            flag("med", "dev_spread", f"Thin development spread ({spread:.0f} bps) — under the ~150 bps "
                 "developers target over the exit cap.")

    dsizing = result.get("debt_sizing") or {}
    dscr = dsizing.get("actual_dscr")
    if isinstance(dscr, (int, float)) and dscr < 1.2:
        flag("med", "dscr", f"DSCR {dscr:.2f} is below the ~1.20 lenders typically require.")

    if not flags:
        flag("info", "ok", "Returns are within typical market bands.")
    return {"flags": flags, "ok": not any(f["level"] == "high" for f in flags)}
