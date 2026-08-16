"""An engine that cannot read its own register, and the check that sees it.

`schedule_lastplanner.reliability` reads `pull_plan_task` records. Until v0.3.974 it looked for a
field called **`week`**. That is `weekly_plan`'s field name. `pull_plan_task/module.json` declares
**`planned_week`**.

So on every real project the engine grouped zero commitments and answered *"none of the N pull-plan
tasks carry a week"* — routed, reachable, tested, and structurally unable to read the register it
exists to read. Its only test supplied `week` in a hand-written fixture, so it passed.

**A fixture cannot catch this by construction.** The fixture is written by the same person as the
reader, from the same wrong belief about the field name, so it agrees with the reader and disagrees
with the database. The check that works reads the **register's own schema** and asserts the engine's
field names against it — a reader neither of them wrote.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_ppc_field_conformance.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from aec_api import schedule_lastplanner as lp  # noqa: E402

_FAILURES: list[str] = []
MODULES = Path(__file__).resolve().parent / "modules"


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def declared(register: str) -> set[str]:
    """Every field name the register declares, read from its module.json."""
    cfg = json.loads((MODULES / register / "module.json").read_text(encoding="utf-8"))
    names = {f["name"] for f in cfg.get("fields", []) if f.get("name")}
    # `workflow_state` is the workflow column, not a declared field, but it is genuinely on the row.
    names.add("workflow_state")
    return names


def main() -> int:
    pull = declared("pull_plan_task")

    # ================= THE ASSERTION =================
    #
    # At least one of the week-field candidates must actually exist on the register. Written as an
    # intersection rather than `"planned_week" in WEEK_FIELDS` so that renaming the field in
    # module.json fails here, which is the direction the drift actually ran.
    usable = sorted(set(lp.WEEK_FIELDS) & pull)
    check("the week field the engine reads EXISTS on pull_plan_task",
          bool(usable),
          f"engine reads {list(lp.WEEK_FIELDS)}; register declares the week as "
          f"{sorted(n for n in pull if 'week' in n)} -> usable: {usable}")

    check("...and `planned_week` is the one the register actually declares",
          "planned_week" in pull and "planned_week" in lp.WEEK_FIELDS,
          "the engine read a bare `week` until v0.3.974 — which is `weekly_plan`'s field name, a "
          "DIFFERENT register. Same word, different table")

    # The twin: the check must be able to FAIL. A conformance test whose candidate list happens to
    # contain every string would pass against any register at all.
    check("...and a field the register does NOT declare is seen as absent — the twin",
          "week" not in pull and "sprint_week" not in pull,
          "`week` is accepted as an alias by the engine and is genuinely NOT on this register; if "
          "this ever passes vacuously the assertion above proves nothing")

    # ================= every field the engine reads =================
    #
    # Enumerated from the engine's own behaviour, not from reading its source: each of these is a key
    # `_commitment` looks up on `data`. Fallbacks are grouped, because only the GROUP has to resolve.
    reads: list[tuple[str, tuple[str, ...]]] = [
        ("the week", tuple(lp.WEEK_FIELDS)),
        ("the completion state", ("workflow_state",)),
        ("the variance reason", ("variance_reason",)),
        ("the crew", ("trade", "crew")),
        ("the constraints", ("constraints",)),
    ]
    for label, keys in reads:
        hit = sorted(set(keys) & pull)
        check(f"{label} resolves on pull_plan_task",
              bool(hit),
              f"{list(keys)} -> {hit}" if hit else
              f"NONE of {list(keys)} is declared by the register; declared: {sorted(pull)}")

    # ================= and it produces a real report on register-shaped rows =================
    #
    # The point of the fix, exercised on rows shaped like the REGISTER rather than like the old
    # fixture. Two answered, one open: the week is deliberately unmeasurable.
    rows = [
        {"id": "t1", "ref": "T1", "title": "pour slab",
         "data": {"planned_week": "2026-03-02", "workflow_state": "done", "trade": "Concrete"}},
        {"id": "t2", "ref": "T2", "title": "strip forms",
         "data": {"planned_week": "2026-03-02", "workflow_state": "not_done", "trade": "Concrete",
                  "variance_reason": "materials"}},
        {"id": "t3", "ref": "T3", "title": "cure",
         "data": {"planned_week": "2026-03-02", "workflow_state": "planned", "trade": "Concrete"}},
    ]
    real = lp.list_records_override(rows) if hasattr(lp, "list_records_override") else None
    if real is None:
        from aec_api import modules as me
        keep = me.list_records
        me.list_records = lambda db, mod, pid, limit=0: rows      # type: ignore[assignment]
        try:
            out = lp.reliability(None, "p1")
        finally:
            me.list_records = keep                                # type: ignore[assignment]
    else:
        out = real

    check("the engine now GROUPS register-shaped rows instead of refusing them",
          out.get("available") is True and out.get("weeks") == 1,
          f"available={out.get('available')} weeks={out.get('weeks')} — before v0.3.974 this was "
          f"available=False with {out.get('reason', '')[:60]!r}")

    check("...and the week reads as unmeasurable, not as a score",
          out["trend"][0]["ppc"] is None and out["trend"][0]["unassessed"] == 1,
          f"{out['trend'][0]} — one commitment still open, so nobody knows how the week went")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("ppc_field_conformance: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
