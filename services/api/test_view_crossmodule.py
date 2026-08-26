"""A report can span two modules, along an edge the schema declares.

R22-REPORT-BUILDER item 2. `SavedView.module` was one string and nothing spanned modules, so — in the
entry's words — *"RFIs against change orders by trade" is not expressible, and that is most of what a
report is.*

## The join comes from the schema, never from the request

`reference_fields` already lists the edges a module declares, and a reference field stores the
target's **id** in `data.<field>` — the same shape `related_records` reads. `_join_target` resolves a
requested join against that list and refuses anything else, for two reasons that are different:

* `_json_text` interpolates the field name into a JSON path, so an arbitrary name is an **injection
  site** — the one `_resolve_field` exists to close, one level further out;
* an arbitrary *module* would let a report join two tables no schema says are related, producing a
  number that cannot be traced back to the data. That is worse than an error, because it looks like
  an answer.

## The join is LEFT, and that is a correctness choice

A base record with no related record still counts, under a `None` group. An inner join would drop it
silently: "RFIs by change-order trade" that omits every RFI *without* a change order answers a
narrower question than the one asked — while looking complete. The test below asserts the unmatched
row survives, because that is the assertion an inner join fails.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_view_crossmodule.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_view_crossmodule.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_view_crossmodule")
for _f in ("./_view_crossmodule.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import HTTPException  # noqa: E402

from aec_api import modules as mod  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import Base  # noqa: E402
from aec_api.modules_query import aggregate, validate_view_config  # noqa: E402
from aec_api.modules_registry import (  # noqa: E402
    REGISTRY,
    load_registry,
    reference_fields,
)

load_registry()
Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def _pick_edge() -> tuple[str, str, str, str]:
    """A real (base, ref_field, target, target_group_field) from the live registry.

    Chosen by resolution rather than hardcoded: a fixture naming two modules by hand would keep
    passing after the schema that connects them changed.
    """
    for base, m in sorted(REGISTRY.items()):
        req_base = [f["name"] for f in m.get("fields", []) if f.get("required")]
        for f in reference_fields(m):
            tgt = REGISTRY.get(f["module"]) or {}
            # a plain text/select field on the target to group by, and both sides creatable
            gf = next((t["name"] for t in tgt.get("fields", [])
                       if t.get("type") in ("text", "select") and not t.get("required")), None)
            req_tgt = [t["name"] for t in tgt.get("fields", []) if t.get("required")]
            if gf and len(req_base) <= 3 and len(req_tgt) <= 3:
                return base, f["name"], f["module"], gf
    raise SystemExit("no usable declared edge in the registry")


BASE, REF, TARGET, GROUP_FIELD = _pick_edge()
check("the registry offers a real declared edge to test",
      bool(BASE and REF and TARGET), f"{BASE}.{REF} -> {TARGET}, grouping on {TARGET}.{GROUP_FIELD}")

# ---- the join is resolved, not accepted ----------------------------------------------------------
for bad, why in [("not_a_field", "an undeclared field"),
                 (GROUP_FIELD, "a declared field that is not a reference")]:
    try:
        aggregate(SessionLocal(), BASE, "P", group_by="id", join=bad)
        check(f"refuses {why} as a join", False, "ACCEPTED")
    except HTTPException as e:
        check(f"refuses {why} as a join", "reference field" in str(e.detail), str(e.detail)[:70])
    except Exception as e:  # noqa: BLE001
        check(f"refuses {why} as a join", False, f"{type(e).__name__}: {e}")

db = SessionLocal()
try:
    PID = "P-cross"
    req_t = [f for f in (REGISTRY[TARGET].get("fields") or []) if f.get("required")]
    req_b = [f for f in (REGISTRY[BASE].get("fields") or []) if f.get("required")]

    def body(mod_key: str, extra: dict) -> dict:
        req = [f for f in (REGISTRY[mod_key].get("fields") or []) if f.get("required")]
        return {"data": {**{f["name"]: "x" for f in req}, **extra}}

    t1 = mod.create_record(db, TARGET, PID, body(TARGET, {GROUP_FIELD: "Alpha"}), "u1", None)
    t2 = mod.create_record(db, TARGET, PID, body(TARGET, {GROUP_FIELD: "Beta"}), "u1", None)
    db.commit()
    # two pointing at Alpha, one at Beta, and one pointing at NOTHING — the left-join case
    for tgt in (t1["id"], t1["id"], t2["id"], None):
        mod.create_record(db, BASE, PID, body(BASE, {REF: tgt} if tgt else {}), "u1", None)
    db.commit()

    res = aggregate(db, BASE, PID, group_by=f"{TARGET}.{GROUP_FIELD}", join=REF)
    groups = {(g["key"] if g["key"] is not None else "<none>"): g["count"] for g in res["groups"]}
    check("the report groups the BASE module by a field on the JOINED module",
          groups.get("Alpha") == 2 and groups.get("Beta") == 1, f"{groups}")
    check("...and reports which module it joined", res.get("join_module") == TARGET,
          f"join_module={res.get('join_module')!r}")
    check("a base record with no related record still counts (LEFT join, not inner)",
          groups.get("<none>") == 1,
          f"{groups} — an inner join drops it and the total silently becomes 3 of 4")
    check("...so every base record is accounted for", sum(groups.values()) == 4, f"{sum(groups.values())} of 4")

    # ---- a saved view is validated exactly as the query it replays ----------------------------
    ok = validate_view_config(BASE, {"join": REF, "group_by": f"{TARGET}.{GROUP_FIELD}", "agg": "count"})
    check("a cross-module config validates", ok.get("join") == REF, str(ok))
    try:
        validate_view_config(BASE, {"join": REF, "group_by": f"{TARGET}.not_a_field"})
        check("...and an undeclared field on the JOINED side is refused", False, "ACCEPTED")
    except HTTPException as e:
        check("...and an undeclared field on the JOINED side is refused",
              "unknown filter/sort field" in str(e.detail), str(e.detail)[:60])
    try:
        validate_view_config(BASE, {"group_by": f"{TARGET}.{GROUP_FIELD}"})
        check("...and a joined-side field WITHOUT a join is refused", False, "ACCEPTED")
    except HTTPException as e:
        check("...and a joined-side field WITHOUT a join is refused", True, str(e.detail)[:50])
finally:
    db.close()

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(
    f"CROSS-MODULE OK - {BASE} grouped by {TARGET}.{GROUP_FIELD} along the declared reference "
    f"{BASE}.{REF}, joins refused unless the schema declares them, and the unmatched base record "
    "still counts because the join is LEFT."
)
