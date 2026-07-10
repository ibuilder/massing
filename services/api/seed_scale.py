"""Mega-project scale seeder — bulk-fills EVERY registered module with realistic large volumes so
the API can be load-tested the way a $500M+ job would exercise it (research: ~17 RFIs/$1M →
thousands of RFIs, 5k+ submittals, tens of thousands of cost lines, multi-year daily logs).

Bulk-inserts straight into each `mod_<key>` table (not slow per-record HTTP POST) with a realistic
spread of workflow_state and created_at, and type-aware `data` values generated from each module's
field schema — so state_counts / dashboards / search / cost roll-ups all see real distributions.

    # SQLite (fast, default): seed a scale db then point tests/loadtest at it
    DATABASE_URL=sqlite:///./_scale.db PYTHONPATH=src ./.venv/Scripts/python.exe seed_scale.py
    # Postgres (real query planner + tsvector):
    DATABASE_URL=postgresql://... PYTHONPATH=src ./.venv/Scripts/python.exe seed_scale.py --scale 1.0

Env/flags: --scale <f> multiplies every per-module target (default 1.0). --project <name>.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

random.seed(42)  # deterministic volumes/values across runs

# Per-module target row counts for a mega project (multiplied by --scale). Anything not listed gets
# DEFAULT_N. The heavy hitters mirror the research: coordination/rfi/cost/daily dominate.
TARGETS = {
    "rfi": 10000, "submittal": 5000, "coordination_issue": 8000, "punchlist": 12000,
    "daily_report": 4000, "daily_log": 4000, "inspection": 6000, "direct_cost": 20000,
    "commitment": 4000, "budget": 3000, "sov": 3000, "cor": 2500, "change_event": 2500,
    "pco": 2500, "owner_invoice": 1500, "sub_invoice": 8000, "timesheet": 15000,
    "manpower_log": 6000, "incident": 1500, "safety_observation": 4000, "material_delivery": 5000,
    "schedule_activity": 8000, "resource_assignment": 6000, "pull_plan_task": 6000,
    "meeting_minutes": 2000, "transmittal": 3000, "cost_code": 800, "photo": 8000,
}
DEFAULT_N = 800  # every other module still gets a healthy volume so nothing is empty


def _states(mod: dict) -> list[str]:
    """Distinct workflow states for a module (initial + every from/to on its transitions)."""
    wf = mod.get("workflow", {})
    st = {wf.get("initial", "open")}
    for t in wf.get("transitions", []):
        st.add(t.get("from")); st.add(t.get("to"))
    st.discard(None)
    return sorted(st) or ["open"]


def _value(field: dict, i: int):
    """A plausible value for one field given its type — enough variety that numeric roll-ups,
    select facets, date ranges and text search all get realistic data."""
    ftype = (field.get("type") or "text").lower()
    name = field.get("name", "")
    if ftype in ("number", "currency", "money", "integer", "float", "percent"):
        if any(k in name for k in ("amount", "value", "cost", "budget", "revised", "scheduled",
                                   "total", "price", "sum", "committed", "paid")):
            return round(random.uniform(1_000, 500_000), 2)
        if "pct" in name or "percent" in name:
            return round(random.uniform(0, 100), 1)
        if "hours" in name or "count" in name or "qty" in name or "quantity" in name:
            return random.randint(1, 400)
        return round(random.uniform(0, 10_000), 2)
    if ftype in ("select", "status", "enum"):
        opts = field.get("options") or field.get("select") or []
        opts = [o["value"] if isinstance(o, dict) else o for o in opts]
        return random.choice(opts) if opts else f"opt{i % 5}"
    if ftype in ("date", "datetime"):
        return (datetime(2024, 1, 1) + timedelta(days=random.randint(0, 900))).strftime("%Y-%m-%d")
    if ftype in ("bool", "boolean", "checkbox"):
        return random.choice([True, False])
    if ftype in ("reference", "ref"):
        return None  # left null — bulk seed doesn't wire cross-refs (kept fast + FK-free)
    # text / textarea / string / anything else — varied words so full-text search has signal
    words = ["concrete", "steel", "MEP", "facade", "core", "podium", "tower", "slab", "beam",
             "column", "rebar", "curtainwall", "elevator", "chiller", "riser", "penetration"]
    return f"{random.choice(words)} {random.choice(words)} #{i}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--project", default="Mega Tower (scale test)")
    args = ap.parse_args()

    os.environ.setdefault("DATABASE_URL", "sqlite:///./_scale.db")
    from aec_api import modules as me
    from aec_api.db import SessionLocal, init_db
    from aec_api.models import Project

    init_db()
    me.load_registry()
    t0 = time.time()
    with SessionLocal() as db:
        pid = str(uuid.uuid4())
        db.add(Project(id=pid, name=args.project)); db.commit()
        print(f"project {pid}  ({args.project})")
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        grand = 0
        for key in sorted(me.REGISTRY):
            mod = me.REGISTRY[key]
            table = me.TABLES.get(key)
            if table is None:
                continue
            n = int(TARGETS.get(key, DEFAULT_N) * args.scale)
            if n <= 0:
                continue
            fields = mod.get("fields", [])
            states = _states(mod)
            title_field = mod.get("title_field") or (fields[0]["name"] if fields else None)
            prefix = mod.get("ref_prefix", key.upper())
            rows = []
            for i in range(1, n + 1):
                data = {f["name"]: _value(f, i) for f in fields}
                ca = base + timedelta(minutes=i)  # monotonic-ish spread for ORDER BY created_at
                rows.append({
                    "id": str(uuid.uuid4()), "project_id": pid, "ref": f"{prefix}-{i:05d}",
                    "title": str(data.get(title_field) or f"{key} {i}")[:120],
                    "workflow_state": random.choice(states),
                    "party_owner": random.choice(["gc", "owner", "arch", "sub"]),
                    "assignee": random.choice(["alice", "bob", "carol", "dave", None]),
                    "created_by": "seed", "created_at": ca, "modified_at": ca,
                    "anchor": None,
                    "element_guids": ([f"{uuid.uuid4().hex[:22]}"] if random.random() < 0.3 else None),
                    "links": [], "data": data,
                })
                if len(rows) >= 2000:                      # batch to bound memory
                    db.execute(table.insert(), rows); rows = []
            if rows:
                db.execute(table.insert(), rows)
            db.commit()
            grand += n
            print(f"  {key:28s} {n:>7,}  states={len(states)}")
        print(f"\nseeded {grand:,} records across {len(me.REGISTRY)} modules "
              f"in {time.time() - t0:.1f}s  -> project {pid}")
        # stash the pid so the load harness can find it without parsing stdout
        with open(os.environ.get("AEC_SCALE_PID_FILE", "_scale_pid.txt"), "w") as fh:
            fh.write(pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
