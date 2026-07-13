"""Takt / line-of-balance planning (R2) — model construction as a vertical assembly line, the way
the Empire State Building was built: each trade flows floor-to-floor at a steady **takt** (a fixed
days-per-floor production rate), trades chase each other up the building, and material is delivered
**just in time** for each floor. Pure functions over a trade list.

Classic LOB recurrence: a trade can't start floor f until it finished floor f-1 *and* the preceding
trade finished floor f. `plan()` returns per-trade per-floor start/finish, total duration, the JIT
delivery plan, and the peak simultaneous crew count."""
from __future__ import annotations

from typing import Any

# default trade sequence with a production rate (days per floor) — a residential tower takt train
DEFAULT_TRADES = [
    {"name": "Structure", "takt_days": 5},
    {"name": "Envelope", "takt_days": 5},
    {"name": "MEP rough-in", "takt_days": 6},
    {"name": "Interiors", "takt_days": 8},
    {"name": "Finishes", "takt_days": 6},
]


def plan(floors: int, trades: list[dict] | None = None, start_day: int = 0,
         jit_lead_days: int = 1) -> dict[str, Any]:
    """Line-of-balance schedule for `floors` floors through the trade train. Returns each trade's
    floor-by-floor start/finish, total duration, a JIT delivery plan (deliver `jit_lead_days` before
    each floor's trade starts), production rate (floors/week), and the peak concurrent crew count."""
    floors = max(1, int(floors))
    trades = trades or DEFAULT_TRADES
    nt = len(trades)
    # finish[i][f] grid; iterate trades (i) then floors (f) honoring both predecessors
    finish: list[list[float]] = [[0.0] * floors for _ in range(nt)]
    start: list[list[float]] = [[0.0] * floors for _ in range(nt)]
    for i, tr in enumerate(trades):
        td = max(1, int(tr.get("takt_days", 5)))
        for f in range(floors):
            prev_floor_done = finish[i][f - 1] if f > 0 else start_day
            prev_trade_done = finish[i - 1][f] if i > 0 else start_day
            s = max(prev_floor_done, prev_trade_done)
            start[i][f] = s
            finish[i][f] = s + td

    duration = max(finish[i][floors - 1] for i in range(nt))
    trade_out, delivery = [], []
    for i, tr in enumerate(trades):
        trade_out.append({
            "name": tr["name"], "takt_days": int(tr.get("takt_days", 5)),
            "start_day": round(start[i][0]), "finish_day": round(finish[i][floors - 1]),
            "floor_starts": [round(start[i][f]) for f in range(floors)],
        })
        for f in range(floors):
            delivery.append({"floor": f + 1, "trade": tr["name"],
                             "deliver_by_day": round(max(0, start[i][f] - jit_lead_days))})
    delivery.sort(key=lambda d: d["deliver_by_day"])
    # floors/week of the lead trade (structure) sets the pace of ascent
    lead_takt = max(1, int(trades[0].get("takt_days", 5)))
    return {
        "floors": floors, "trades": trade_out,
        "duration_days": round(duration),
        "duration_weeks": round(duration / 7, 1),
        "floors_per_week": round(7 / lead_takt, 2),
        "crew_peak": min(floors, nt),               # up to one crew per trade once the train ramps
        "delivery_plan": delivery,
    }


def progress(p: dict, actuals: list[dict], as_of_day: int | None = None) -> dict[str, Any]:
    """Actual-vs-takt tracking. `p` is a `plan()` result; `actuals` is [{trade, floors_done,
    as_of_day?}, …] — how many floors each trade has actually completed as of a reporting day (rolled
    up from daily reports). For each trade we compare **planned floors complete by that day** (from the
    LOB finishes) with the actual, giving a floor variance (+ahead / −behind) and an achieved production
    rate (floors/week). The lead trade's achieved rate vs the planned `floors_per_week` is the headline:
    is the train ascending at takt? Returns per-trade rows + an overall on/ahead/behind read, and the
    actual-ascent overlay points the LOB chart draws as dashed lines against the plan."""
    floors = int(p["floors"])
    by_name = {t["name"]: t for t in p["trades"]}
    default_day = as_of_day if as_of_day is not None else max(
        [int(a.get("as_of_day", 0)) for a in actuals] or [0])
    rows: list[dict[str, Any]] = []
    overlay: list[dict[str, Any]] = []
    for a in actuals:
        name = a.get("trade")
        tr = by_name.get(name)
        if not tr:
            continue
        day = int(a.get("as_of_day", default_day) or default_day)
        actual_done = max(0, min(floors, int(a.get("floors_done", 0) or 0)))
        # planned floors complete by `day` = count of floor finishes at/under day.
        # finish[f] = floor_starts[f] + takt_days (each floor takes one takt to complete)
        td = int(tr.get("takt_days", 5))
        planned_done = sum(1 for s in tr["floor_starts"] if s + td <= day)
        var = actual_done - planned_done                    # + ahead of plan, − behind
        weeks = day / 7 if day > 0 else 0
        rate = round(actual_done / weeks, 2) if weeks > 0 else 0.0
        planned_rate = round(planned_done / weeks, 2) if weeks > 0 else 0.0
        rows.append({
            "trade": name, "as_of_day": day, "floors_done": actual_done,
            "planned_done": planned_done, "variance_floors": var,
            "actual_floors_per_week": rate, "planned_floors_per_week": planned_rate,
            "status": ("ahead" if var > 0 else "behind" if var < 0 else "on-takt"),
        })
        overlay.append({"trade": name, "as_of_day": day, "floors_done": actual_done})
    # headline: the lead (first) trade paces the build
    lead = rows[0] if rows else None
    total_var = sum(r["variance_floors"] for r in rows)
    return {
        "as_of_day": default_day, "rows": rows, "overlay": overlay,
        "lead_trade": lead["trade"] if lead else None,
        "lead_actual_floors_per_week": lead["actual_floors_per_week"] if lead else 0.0,
        "planned_floors_per_week": p.get("floors_per_week", 0.0),
        "total_variance_floors": total_var,
        "overall_status": ("ahead" if total_var > 0 else "behind" if total_var < 0 else "on-takt"),
    }


_COLORS = ["#4a8cff", "#33d17a", "#ffd479", "#e2554a", "#b083d6", "#6cb6ff", "#f08c5a"]


def takt_svg(p: dict, actuals: list[dict] | None = None) -> str:
    """Line-of-balance chart: floors (Y) vs days (X), one sloped line per trade chasing up the
    building. A flatter/steeper slope = faster/slower ascent; the gap between lines = the buffer.
    When `actuals` (the `progress().overlay` list) is given, each trade's actual ascent is drawn as a
    dashed line from its start to (as_of_day, floors_done) — so plan vs actual reads at a glance."""
    floors = p["floors"]
    dur = max(1, p["duration_days"])
    W, H, ml, mt, mb = 760, 40 + floors * 22 + 70, 50, 30, 40
    plot_w, plot_h = W - ml - 20, H - mt - mb
    def x(day): return ml + plot_w * day / dur
    def y(fl): return mt + plot_h * (1 - fl / floors)
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="system-ui,sans-serif">']
    parts.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    # axes + floor gridlines
    for fl in range(0, floors + 1):
        yy = y(fl)
        parts.append(f'<line x1="{ml}" y1="{yy:.0f}" x2="{ml + plot_w}" y2="{yy:.0f}" stroke="#eee"/>')
        if fl:
            parts.append(f'<text x="{ml - 8}" y="{yy + 3:.0f}" font-size="9" fill="#888" text-anchor="end">L{fl}</text>')
    parts.append(f'<text x="{ml}" y="{H - 8}" font-size="11" fill="#444">Days 0–{dur} · {p["duration_weeks"]} wks · {p["floors_per_week"]} floors/wk</text>')
    # one polyline per trade through its per-floor start points
    for i, tr in enumerate(p["trades"]):
        col = _COLORS[i % len(_COLORS)]
        pts = " ".join(f"{x(s):.0f},{y(fl + 1):.0f}" for fl, s in enumerate(tr["floor_starts"]))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5"/>')
        parts.append(f'<circle cx="{ml + 14 + i * 130}" cy="{mt - 14}" r="4" fill="{col}"/>'
                     f'<text x="{ml + 22 + i * 130}" y="{mt - 10}" font-size="10" fill="#333">{tr["name"]}</text>')
    # actual ascent overlay: dashed line from each trade's start point to (as_of_day, floors_done)
    if actuals:
        name_idx = {tr["name"]: i for i, tr in enumerate(p["trades"])}
        for a in actuals:
            i = name_idx.get(a.get("trade"))
            if i is None:
                continue
            col = _COLORS[i % len(_COLORS)]
            s0 = p["trades"][i]["floor_starts"][0]
            done = max(0, min(floors, int(a.get("floors_done", 0) or 0)))
            day = int(a.get("as_of_day", 0) or 0)
            parts.append(f'<polyline points="{x(s0):.0f},{y(0):.0f} {x(day):.0f},{y(done):.0f}" '
                         f'fill="none" stroke="{col}" stroke-width="2" stroke-dasharray="4 3" opacity="0.85"/>')
            parts.append(f'<circle cx="{x(day):.0f}" cy="{y(done):.0f}" r="3" fill="{col}"/>')
        parts.append(f'<text x="{ml + plot_w}" y="{mt - 10}" font-size="9" fill="#888" '
                     f'text-anchor="end">— plan · ┄ actual</text>')
    parts.append("</svg>")
    return "".join(parts)
