"""Underwriting guardrails (U5) — sanity-check a solved proforma against market bands and flag
returns that look too good (or too thin) to be real, so the IRR is credible rather than just
arithmetically correct. Pure over the solve() result. Bands reflect typical institutional ranges
(equity IRR ~8–25%, equity multiple ~1.5–3x, positive development spread, DSCR ≥ ~1.2)."""
from __future__ import annotations

from typing import Any


def _comp_cap_stats(comps: list[dict] | None) -> dict[str, float] | None:
    """Cap-rate band from the deal's sale comps (data.cap_rate on `comparable` records). Rents/land
    comps carry no cap rate and are ignored. Returns {lo, hi, median, n} as fractions, or None."""
    if not comps:
        return None
    caps: list[float] = []
    for c in comps:
        d = c.get("data") or c
        if str(d.get("comp_type") or "Sale").lower() in ("rent", "land"):
            continue
        try:
            v = float(d.get("cap_rate"))
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        caps.append(v / 100 if v > 1 else v)          # accept 5.5 (%) or 0.055 (fraction)
    if not caps:
        return None
    caps.sort()
    mid = caps[len(caps) // 2] if len(caps) % 2 else (caps[len(caps) // 2 - 1] + caps[len(caps) // 2]) / 2
    return {"lo": caps[0], "hi": caps[-1], "median": round(mid, 4), "n": len(caps)}


def guardrails(result: dict[str, Any], comps: list[dict] | None = None) -> dict[str, Any]:
    """Return {flags:[{level, metric, message}], ok: bool} for a solved proforma result.
    level ∈ high|med|info. `high` = likely-unrealistic input; `med` = thin/marginal; `info` = note.
    Bands are sourced from `benchmarks` (R5) so the checks are citable, not magic numbers (U3).
    When `comps` (the project's `comparable` records) are supplied, the deal's **exit cap is validated
    against the sale-comp cap-rate band** (U3) — a going-out cap tighter than the market supports
    silently inflates the reversion and the whole IRR."""
    from . import benchmarks as bm
    irr_lo, irr_hi = bm.BENCHMARKS["equity_irr"]["typical"]   # citable IRR band
    ret = result.get("returns") or {}
    flags: list[dict[str, str]] = []

    def flag(level: str, metric: str, message: str):
        flags.append({"level": level, "metric": metric, "message": message})

    irr = ret.get("equity_irr")
    if isinstance(irr, (int, float)):
        if irr > 0.35:
            flag("high", "equity_irr", f"Equity IRR {irr * 100:.0f}% is implausibly high — check that "
                 "operating/specialty revenue is risk-adjusted (not gross) and opex is fully built.")
        elif irr > irr_hi:
            flag("med", "equity_irr", f"Equity IRR {irr * 100:.0f}% is above the typical "
                 f"{irr_lo * 100:.0f}–{irr_hi * 100:.0f}% band — confirm the upside is defensible.")
        elif irr < irr_lo:
            flag("med", "equity_irr", f"Equity IRR {irr * 100:.0f}% is below the ~{irr_lo * 100:.0f}% "
                 "equity threshold most LPs require.")

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

    # U3 — validate the exit cap against the deal's own sale comps. A going-out cap tighter than the
    # market supports silently inflates the reversion (value = NOI ÷ cap) and the whole IRR.
    cs = _comp_cap_stats(comps)
    exit_cap = ret.get("exit_cap")
    if cs and isinstance(exit_cap, (int, float)) and exit_cap > 0:
        band = f"{cs['lo'] * 100:.2f}–{cs['hi'] * 100:.2f}% ({cs['n']} sale comp{'s' if cs['n'] != 1 else ''}, " \
               f"median {cs['median'] * 100:.2f}%)"
        if exit_cap < cs["lo"] - 0.005:                  # >50 bps tighter than the tightest comp
            flag("high", "exit_cap", f"Exit cap {exit_cap * 100:.2f}% is well below the comp band {band} — "
                 "a tighter going-out cap inflates the reversion and the IRR. Underwrite ≥ the comps.")
        elif exit_cap < cs["lo"]:
            flag("med", "exit_cap", f"Exit cap {exit_cap * 100:.2f}% is below the comp band {band} — "
                 "confirm the exit is defensible; developers usually exit a touch soft of comps.")
        elif exit_cap < cs["median"]:
            flag("info", "exit_cap", f"Exit cap {exit_cap * 100:.2f}% sits inside the comp band {band}.")

    if not flags:
        flag("info", "ok", "Returns are within typical market bands.")
    return {"flags": flags, "ok": not any(f["level"] == "high" for f in flags)}
