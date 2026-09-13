"""TRANSITION-CAS — is a workflow move a compare-and-swap, or a blind write?

WHY THIS EXISTS
    `modules.transition` read the record, decided the move was legal from the state it read, and
    then wrote `workflow_state` with an UPDATE keyed on `id` ALONE. Nothing held the row still in
    between. Two callers could both read `draft`, both pass `_transition`, and both commit — the
    same read-then-write shape as the job claim and the ref counter, which `test_race_conditions.py`
    already gates. Transitions were not covered by it.

    The reach is the thing. `transition` is the ONLY place a record's `workflow_state` moves after
    creation, so this one write backed **139 modules and 342 declared transitions**: two concurrent
    `award` calls both succeeded, two concurrent `send_rfq` calls minted two ITBs.

WHAT IT ASSERTS, AND WHY EACH IS SEPARATE
    1. BEHAVIOUR through the real `transition`, on a stale read constructed by hand: the loser is
       refused. This is the question the item is about.
    2. The PREDICATE is what refuses it — the pre-fix statement shape is reinstated and must land
       its blind write, so the check cannot pass with the guard removed. *A static check that still
       passes with the guard taken out is not testing the guard.*
    3. The two 409s are DISTINGUISHABLE in text. A caller who cannot tell "not available from this
       state" from "you lost a race" cannot decide whether retrying is sensible — and a test that
       reads only the status code would pass against the bug.
    4. No declared transition is a self-loop, which is what makes `rowcount != 1` mean what the
       code says it means. A future `from == to` must not land unnoticed.
    5. `transition` is still the SOLE post-creation writer of the column — derived, not listed.

HONEST LIMIT
    SQLite serialises writers, so a genuinely parallel collision cannot be reproduced here (the same
    caveat `test_race_conditions.py` states). What IS proven here is the property the fix relies on,
    against the real table and the real function, via the exact losing interleaving built by hand.

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_transition_cas.py
"""
import ast
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))
os.environ.setdefault("AEC_TEST", "1")
os.environ["DATABASE_URL"] = "sqlite:///./test_transition_cas.db"
os.environ["STORAGE_DIR"] = "./test_storage_transition_cas"
for _f in ("./test_transition_cas.db",):
    if os.path.exists(_f):
        os.remove(_f)

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


from fastapi import HTTPException  # noqa: E402
from sqlalchemy import update  # noqa: E402

from aec_api import modules  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.models import Project  # noqa: E402

init_db()
_db = SessionLocal()
_proj = Project(name="cas")
_db.add(_proj)
_db.commit()
PID = _proj.id

KEY = "procurement_package"
ACTION = "send_rfq"
FROM, TO = "draft", "rfq_sent"


def fresh_record():
    """A brand-new package in `draft`, in its own session."""
    s = SessionLocal()
    r = modules.create_record(s, KEY, PID, {"data": {"name": "Steel", "trade": "05"}}, "alice", "GC")
    return s, r["id"]


# ---------------------------------------------------------------- 0. the premise the code rests on
_selfloops = []
_transitions = 0
_mods = 0
for _p in sorted(pathlib.Path(os.path.join(os.path.dirname(__file__), "modules")).glob("*/module.json")):
    _m = json.loads(_p.read_text(encoding="utf-8"))
    _mods += 1
    for _t in (_m.get("workflow") or {}).get("transitions") or []:
        _transitions += 1
        if _t.get("from") == _t.get("to"):
            _selfloops.append((_m["key"], _t.get("action"), _t.get("from")))
check("no declared transition is a self-loop, so `rowcount != 1` is unambiguous",
      not _selfloops,
      f"{_mods} modules, {_transitions} transitions, {len(_selfloops)} self-loops"
      + (f" -- {_selfloops}" if _selfloops else ""))

# ---------------------------------------------------------------- 1. the losing interleaving
# A reads the record (draft). B completes the move and commits. A then proceeds on its stale read.
# `transition` re-reads internally, so the stale read is injected by standing in for `get_record`
# for exactly A's call -- which exercises the REAL transition rather than a reimplementation of it.
sa, RID = fresh_record()
stale = modules.get_record(sa, KEY, PID, RID)
check("the interleaving starts from the state the move is declared from",
      stale["workflow_state"] == FROM, f"read {stale['workflow_state']!r}")

sb = SessionLocal()
moved_b = modules.transition(sb, KEY, PID, RID, ACTION, "bob", "GC")
check("B's move lands", moved_b["workflow_state"] == TO, f"-> {moved_b['workflow_state']!r}")

_real_get_record = modules.get_record
modules.get_record = lambda *_a, **_k: dict(stale)          # A's snapshot, taken before B committed
try:
    sa2 = SessionLocal()
    raced_detail = ""
    try:
        modules.transition(sa2, KEY, PID, RID, ACTION, "carol", "GC")
        raced_refused = False
    except HTTPException as e:
        raced_refused = e.status_code == 409
        raced_detail = str(e.detail)
    finally:
        sa2.close()
finally:
    modules.get_record = _real_get_record
sa.close()
sb.close()

check("A -- deciding from a STALE read -- is refused rather than committing a second move",
      raced_refused, raced_detail or "A's transition returned successfully")

# and the record is where B left it, once
_sr = SessionLocal()
_after = _real_get_record(_sr, KEY, PID, RID)
_sr.close()
check("the record holds B's state, not a second application of A's",
      _after["workflow_state"] == TO, f"state is {_after['workflow_state']!r}")

# ---------------------------------------------------------------- 2. the PREDICATE is what refuses
# Reinstate the pre-fix statement shape against the same moved row. If the blind write still lands,
# the guard is load-bearing; if it does not, this gate would pass with the fix removed and is
# measuring nothing. Run on a throwaway record so the assertion does not depend on the row above.
sc, RID2 = fresh_record()
sc.close()
sc2 = SessionLocal()
modules.transition(sc2, KEY, PID, RID2, ACTION, "dave", "GC")
sc2.close()          # now in TO
t = modules.TABLES[KEY]
sd = SessionLocal()
pre = sd.execute(update(t).where(t.c.id == RID2).values(workflow_state=TO))
post = sd.execute(update(t).where(t.c.id == RID2, t.c.workflow_state == FROM).values(workflow_state=TO))
sd.rollback()
sd.close()
check("PRE-FIX shape (keyed on id alone) lands the blind write on a row that has already moved",
      pre.rowcount == 1, f"rowcount={pre.rowcount}")
check("POST-FIX shape (id AND the decided-from state) matches nothing, which is the refusal",
      post.rowcount == 0, f"rowcount={post.rowcount}")

# ---------------------------------------------------------------- 3. the two 409s are different
se, RID3 = fresh_record()
se.close()
se2 = SessionLocal()
modules.transition(se2, KEY, PID, RID3, ACTION, "erin", "GC")
se2.close()
_sq = SessionLocal()
try:
    modules.transition(_sq, KEY, PID, RID3, ACTION, "frank", "GC")
    sequential_detail = ""
except HTTPException as e:
    sequential_detail = str(e.detail)
finally:
    _sq.close()
check("a SEQUENTIAL second move is refused too", sequential_detail.startswith("action "),
      sequential_detail or "not refused")
check("the raced refusal and the sequential refusal do not read the same",
      bool(raced_detail) and bool(sequential_detail) and raced_detail != sequential_detail,
      f"raced={raced_detail!r}  sequential={sequential_detail!r}")

# ---------------------------------------------------------------- 4. still the only writer
# Derived at FUNCTION scope, not from the text inside `.values(...)`. That distinction is the whole
# point: `transition` builds its values as a dict and splats it as `**vals`, so a scan that reads
# only the call's own source finds ZERO of the two writers that matter and reports the tree clean.
# The self-test below proves the derivation reaches `transition` before any verdict is printed.
SRC = pathlib.Path(os.path.join(os.path.dirname(__file__), "src", "aec_api"))


def state_writers() -> list[tuple[str, str]]:
    """Every function that calls `update(...)` AND mentions the column anywhere in its body."""
    out = []
    for p in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for f in ast.walk(tree):
            if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.unparse(f)
            if "update(" in body and "workflow_state" in body:
                out.append((str(p.relative_to(SRC.parent.parent)), f.name))
    return out


WRITERS = state_writers()
check("the derivation REACHES `transition` -- the splat blind spot, asserted before any verdict",
      ("src/aec_api/modules.py", "transition") in WRITERS,
      f"found {len(WRITERS)}: {WRITERS}")

#: Everything the derivation surfaces that does NOT move an existing record's state, with why.
#: `update(` is deliberately a loose sieve, so this list is where the reading is recorded.
NOT_A_STATE_MOVE = {
    ("src/aec_api/modules.py", "revise"): "INSERTs a new row at the workflow's initial state",
    ("src/aec_api/option_carbon.py", "option_carbon"): "`row.update({...})` is a dict merge, not SQL",
    ("src/aec_api/option_economics.py", "option_economics"): "same -- dict merge; reads the column",
    ("src/aec_api/pins.py", "resolve_pins"): "reads `workflow_state` onto the pin envelope",
}
movers = [w for w in WRITERS if w not in NOT_A_STATE_MOVE]
check("`transition` is the SOLE post-creation writer of workflow_state",
      movers == [("src/aec_api/modules.py", "transition")], f"movers={movers}")
stale_exempt = [k for k in NOT_A_STATE_MOVE if k not in WRITERS]
check("no exemption outlives the site it exempts", not stale_exempt, f"stale={stale_exempt}")

print()
print(f"test_transition_cas {'FAILED' if FAILED else 'OK'}"
      f"  ({_mods} modules, {_transitions} transitions, {len(WRITERS)} update-and-state functions,"
      f" 1 mover)")
if FAILED:
    for f_ in FAILED:
        print("   FAILED:", f_)
    sys.exit(1)
