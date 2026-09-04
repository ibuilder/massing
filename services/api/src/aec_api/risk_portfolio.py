"""RISK-PORTFOLIO — the portfolio **risk heat map**, one of the three items R22-PIPELINE's
premise-check found genuinely missing.

`risk_board` answers "what is threatening THIS project" by re-deriving five engines (Monte-Carlo
schedule risk · predictive alerts · EVM · the pre-flight issuance gate · overdue coordination) into
one ranked register. Above the project workspace nobody has that view: `/portfolio/executive` and
`/portfolio/construction` roll up *performance* (SPI, CPI, variance, incident counts), and neither
can say **which risk ENGINE is hot on which project** — the question a heat map exists to answer.
This grids the same board across the book: projects down, risk sources across, severity-weighted
intensity in the cell.

## An empty cell is not a safe cell

The one design decision worth stating. A heat map made of counts renders "0" for two entirely
different facts: *this engine looked and found nothing* and *this engine could not run*. `board`
already separates them — it returns `lanes: {name: ok | error}` beside its items, because every lane
is fail-open and a broken source drops its lane rather than the board. So every cell here carries a
`state`, and a cell whose lane errored is `state: "error"` with **no counts at all** rather than
zeros. A blank column that reads as "clear" across the whole portfolio is the exact failure a risk
tool must not have: it is the same class of defect as a cap table that read a stamped default state
as a decision, and the same remedy — *do not let an unmeasured value wear the costume of a measured
one.*

`coverage` reports the split at portfolio level, so a reader can see how much of the map is real.

## Weighting

Intensity is `3·high + 2·medium + 1·low`. Deliberately shallow: the severities come from thresholds
the individual engines already chose, and a steeper curve here would re-weight their judgement
invisibly. The raw counts travel beside the score so a UI can colour on either.

## Consistency over speed

Each project's cells come from `risk_board.board` unchanged — same engines, same Monte-Carlo seed —
so a cell here and the project's own risk panel can never disagree. That costs a full board per
project, which is why the sweep is bounded by `limit` and reports `truncated`; the alternative
(cheaper approximations at the portfolio level) is how a dashboard ends up contradicting the panel
it links to.

The truncation that buys is worth naming rather than hiding: `limit` takes a **deterministic prefix
of the caller's project list**, not the riskiest projects — ranking by risk is exactly what the sweep
computes, so it cannot be used to choose what to sweep. On a book larger than `limit`, the map is a
sample and `truncated` says so; raise `limit` to see the rest.
"""
from __future__ import annotations

from typing import Any

from .risk_board import LANES

_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_BANDS = ("critical", "elevated", "watch", "clear")
DEFAULT_LIMIT = 25


def _empty_counts() -> dict[str, Any]:
    return {"high": 0, "medium": 0, "low": 0, "count": 0, "score": 0}


def _score(c: dict[str, Any]) -> int:
    return sum(_WEIGHT[s] * c[s] for s in ("high", "medium", "low"))


def heatmap(db: Any, projects: list[tuple[str, str]], *,
            limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Grid `risk_board.board` across `projects` — a list of `(id, name)` already scoped to the
    caller. `limit` bounds the sweep (each project is a full board); the rest are reported as
    `truncated` rather than silently dropped."""
    from . import risk_board

    scanned = projects[:max(0, int(limit))]
    keys = [k for k, _s, _l in LANES]
    by_source = {s: k for k, s, _l in LANES}

    rows: list[dict[str, Any]] = []
    src_tot = {k: _empty_counts() | {"projects_measured": 0, "projects_error": 0} for k in keys}
    tot = _empty_counts()
    tally = dict.fromkeys(_BANDS, 0)
    hotspots: list[dict[str, Any]] = []
    measured = errored = unknown = 0

    for pid, name in scanned:
        try:
            b = risk_board.board(db, pid)
        except Exception:  # noqa: BLE001 — a project whose board fails outright still gets a row,
            b = None       # entirely unmeasured, rather than disappearing from the portfolio.
        lanes = (b or {}).get("lanes") or {}
        items = (b or {}).get("items") or []

        cells: dict[str, dict[str, Any]] = {}
        worst: dict[str, dict[str, Any]] = {}      # lane -> highest-severity item, for the hotspot label
        for it in items:
            k = by_source.get(it.get("source"))
            if k is None:                          # a source this table does not know: counted at
                continue                           # project level below, never invented as a column
            cells.setdefault(k, _empty_counts())
            sev = it.get("severity")
            if sev in _WEIGHT:
                cells[k][sev] += 1
                cells[k]["count"] += 1
            if k not in worst:
                worst[k] = it                      # board sorts high → low, so the first wins

        row_counts = _empty_counts()
        for k in keys:
            state = lanes.get(k)
            if state == "ok":
                c = cells.get(k) or _empty_counts()
                c["score"] = _score(c)
                c["state"] = "ok"
                measured += 1
                src_tot[k]["projects_measured"] += 1
                for f in ("high", "medium", "low", "count", "score"):
                    src_tot[k][f] += c[f]
                    row_counts[f] += c[f]
                if c["score"]:
                    w = worst.get(k) or {}
                    hotspots.append({"project_id": pid, "project": name, "source": k,
                                     "score": c["score"], "high": c["high"],
                                     "title": w.get("title"), "link": w.get("link")})
            else:
                # error, or absent because the board itself failed. No counts: see the module note.
                c = {"state": "error" if state == "error" else "unknown"}
                if state == "error":
                    errored += 1
                    src_tot[k]["projects_error"] += 1
                else:
                    unknown += 1
            cells[k] = c

        band = (b or {}).get("band")
        if band in tally:
            tally[band] += 1
        for f in ("high", "medium", "low", "count", "score"):
            tot[f] += row_counts[f]
        rows.append({"id": pid, "name": name, "band": band,
                     "measured_sources": sum(1 for k in keys if cells[k].get("state") == "ok"),
                     **row_counts, "cells": cells})

    for k in keys:
        src_tot[k]["score"] = _score(src_tot[k])
    rows.sort(key=lambda r: (-r["score"], -r["high"], r["name"]))
    hotspots.sort(key=lambda h: (-h["score"], -h["high"], h["project"], h["source"]))
    cell_total = measured + errored + unknown
    labels = {k: lbl for k, _s, lbl in LANES}
    return {
        "projects": rows,
        "sources": [{"key": k, "label": labels[k], **src_tot[k]} for k in keys],
        "totals": tot,
        "band_tally": tally,
        "hotspots": hotspots[:8],
        "coverage": {"cells": cell_total, "measured": measured, "errored": errored,
                     "unknown": unknown,
                     "pct": round(100.0 * measured / cell_total, 1) if cell_total else None},
        "weights": dict(_WEIGHT),
        "project_count": len(scanned),
        "projects_available": len(projects),
        "truncated": len(projects) > len(scanned),
        "limit": limit,
        "note": "Projects × risk source, intensity = 3·high + 2·medium + 1·low, every cell from the "
                "same board the project's own risk panel shows. A cell reads `error`/`unknown` when "
                "its engine could not run — never 0, which would render an unmeasured source as a "
                "clear one. `coverage` says how much of the map is measured. When `truncated`, the "
                "scanned set is a deterministic prefix of the caller's projects, not the riskiest "
                "ones — ranking is what the sweep produces, so it cannot select what to sweep.",
    }
