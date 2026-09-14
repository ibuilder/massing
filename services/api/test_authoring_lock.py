"""RMW-LOCKGAP: six authoring routes derived a new IFC version outside the per-project lock the
other five in the same file take, so two concurrent authoring operations each wrote their own
version off the same base and the second commit orphaned the first user's work -- silently, because
each caller's response is true of its own run.

This asserts the property that actually matters, which is NOT "a lock is present": it is that the
SECOND writer derives from the FIRST writer's output rather than from the same base. A test that
only looked for `pid_lock` in the source would pass on a lock that spans the assignment alone -- the
exact defect review caught on PR #552 -- so the recipe is stubbed and the INPUT PATH each call sees
is recorded. Chaining is observable; lock presence is not.

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_authoring_lock.py
"""
import os
import sys
import threading

os.environ["DATABASE_URL"] = "sqlite:///./_authlock_test.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_authlock")
os.environ.setdefault("AEC_TRUST_XUSER", "1")
os.environ.setdefault("IFC_DIR", os.path.join(os.path.dirname(__file__), "_ifc_authlock"))

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import contextlib  # noqa: E402
from pathlib import Path  # noqa: E402

from aec_api import pid_lock as _pl  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_api.routers import authoring  # noqa: E402
from aec_data import edit as _ed  # noqa: E402

Base.metadata.create_all(engine)

PID = "proj-authlock"
IFC_DIR = Path(os.environ["IFC_DIR"])
IFC_DIR.mkdir(parents=True, exist_ok=True)
BASE = IFC_DIR / "model.ifc"
BASE.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")

_db = SessionLocal()
_db.query(Project).filter(Project.id == PID).delete()
_db.add(Project(id=PID, name="authlock", source_ifc=str(BASE),
                prop_layers={"layers": [{"name": "L", "enabled": True,
                                         "overrides": [{"guid": "G", "pset": "P", "prop": "x",
                                                        "value": "1"}]}]}))
_db.commit()
_db.close()

FAILED: list[str] = []


def check(label: str, ok, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}   {detail}")
    if not ok:
        FAILED.append(label)


def run_two_bakes() -> list[str]:
    """Two concurrent `bake_layers`; returns the source path each one read, in completion order."""
    seen: list[str] = []
    seen_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def fake_recipe(src, recipe, params, out, **kw):
        with seen_lock:
            seen.append(src)
        Path(out).write_text(Path(src).read_text())
        return {"changed": 1}

    real = _ed.apply_recipe
    _ed.apply_recipe = fake_recipe
    try:
        def worker():
            db = SessionLocal()
            try:
                barrier.wait(timeout=10)
                authoring.bake_layers(PID, publish=False, db=db, actor="t")
            finally:
                db.close()

        ts = [threading.Thread(target=worker) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=30)
    finally:
        _ed.apply_recipe = real
    return seen


def reset() -> None:
    db = SessionLocal()
    p = db.get(Project, PID)
    p.source_ifc = str(BASE)
    db.commit()
    db.close()


# --- the fix ---------------------------------------------------------------------------------
reset()
seen = run_two_bakes()
check("two concurrent bakes see DIFFERENT source versions -- the second derives from the first's "
      "output, so neither user's work is orphaned",
      len(seen) == 2 and seen[0] != seen[1], f"read: {[Path(s).name for s in seen]}")

db = SessionLocal()
final = db.get(Project, PID).source_ifc
db.close()
check("...and the project points at the LAST of the chain, not at a version derived from the base",
      final not in (str(BASE),) and Path(final).name != Path(BASE).name,
      f"final={Path(final).name}")

# --- MUTATION: the lock removed, the same interleaving loses a version -------------------------
_real_fn = _pl.mutating


@contextlib.contextmanager
def _no_lock(_pid):
    yield


_pl.mutating = _no_lock
try:
    reset()
    seen_m = run_two_bakes()
finally:
    _pl.mutating = _real_fn

check("MUTATION: with `pid_lock.mutating` neutered, both bakes read the SAME base -- so the test "
      "is measuring the lock and not the wall clock",
      len(seen_m) == 2 and seen_m[0] == seen_m[1],
      f"read: {[Path(s).name for s in seen_m]}")

print()
print(f"test_authoring_lock {'FAILED' if FAILED else 'OK'}")
for f in FAILED:
    print(f"  - {f}")
sys.exit(1 if FAILED else 0)
