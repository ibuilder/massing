"""Two publishes cannot land on one version number, and `c9f4a8b2e731` repairs the ones that did.

## What was wrong

`versions.snapshot()` allocates `version = last.version + 1` after reading the maximum, over an index
on `project_id` alone. Two publishes to one project — two uploads, a retried convert — both read 7
and both insert 8, and nothing refused it.

**The consequence is not "the diff picks arbitrarily".** `versions.review` reads
`(project_id, version).first()` and sets `review_status` on whatever comes back, so approving
"version 8" approves one row and leaves its twin a draft, against a rule whose whole purpose is
*issue drawings only from approved versions*. And `turnover.py` stamps `record_model_version` — a
bare integer — into the `data` of a signed substantial-completion certificate, so with two rows
carrying that number **which snapshot the certificate attests to is decided by `.first()`**.

## Why the repair renumbers instead of re-sequencing

That signed integer is also why the tidy fix is wrong. Re-sequencing a project's versions by
`created_at` would make numbering match chronology and would silently change what an already-signed
certificate points at. So every number stays on the row that has it, and only the later members of a
duplicate set move to the end. The checks below assert BOTH halves of that: the survivor keeps its
number, and the mover gets a new one — because "no duplicates remain" is equally true of a migration
that renumbered the wrong row, and that migration would move a signature's target.

## The two halves are tested separately, on purpose

The migration is exercised against a seeded dirty database; the allocator is exercised through
`snapshot()` itself. A test of one is not evidence about the other: the constraint could be present
and the allocator still 500 on a legitimate second publish, which is the failure mode a constraint
added without a retry introduces.

Run: cd services/api && PYTHONPATH=src ./.venv/bin/python test_model_version_collision.py
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["DATABASE_URL"] = "sqlite:///./_model_version_collision.db"
os.environ["STORAGE_DIR"] = "./_storage_model_version_collision"
for _f in ("_model_version_collision.db", "_model_version_collision_mig.db"):
    (HERE / _f).unlink(missing_ok=True)

import sqlalchemy as sa  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

_BEFORE = "b6e1c4d09a37"          # the revision a database still holding duplicates is at
_UNDER_TEST = "c9f4a8b2e731"

FAILED: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# ── 1. the migration, against a database that already collided ───────────────────────────────────
MIG_DB = HERE / "_model_version_collision_mig.db"
cfg = Config(str(HERE / "alembic.ini"))
cfg.set_main_option("script_location", str(HERE / "migrations"))
_live = os.environ["DATABASE_URL"]
os.environ["DATABASE_URL"] = f"sqlite:///./{MIG_DB.name}"
command.upgrade(cfg, _BEFORE)

mig = sa.create_engine(os.environ["DATABASE_URL"])
PID = "p-versions"
with mig.begin() as conn:
    conn.execute(sa.text("INSERT INTO projects (id, name, created_at) VALUES (:i,'Tower','2026-01-01')"),
                 {"i": PID})
    # 1, 2, 2', 3 — the pair is the collision, and 3 exists so the renumber has to go PAST it.
    for vid, version, when in (("v1", 1, "2026-01-01 09:00:00"),
                               ("v2", 2, "2026-01-02 09:00:00"),
                               ("v2b", 2, "2026-01-02 09:00:30"),
                               ("v3", 3, "2026-01-03 09:00:00")):
        conn.execute(sa.text(
            "INSERT INTO model_versions (id, project_id, version, element_count, guids, note, "
            "review_status, created_at) VALUES (:i,:p,:v,0,'[]',:n,'draft',:c)"),
            {"i": vid, "p": PID, "v": version, "n": f"+{version}/-0", "c": when})

command.upgrade(cfg, _UNDER_TEST)

with mig.begin() as conn:
    rows = {r["id"]: dict(r) for r in conn.execute(sa.text(
        "SELECT id, version, note FROM model_versions WHERE project_id = :p"), {"p": PID}).mappings()}
    check("the EARLIEST of the colliding pair keeps the number it was issued",
          rows["v2"]["version"] == 2, rows["v2"]["version"])
    check("...and the later one moves PAST the existing maximum, not into a gap",
          rows["v2b"]["version"] == 4, rows["v2b"]["version"])
    check("an untouched version keeps its number, so nothing was re-sequenced under a signature",
          (rows["v1"]["version"], rows["v3"]["version"]) == (1, 3),
          (rows["v1"]["version"], rows["v3"]["version"]))
    check("the moved row says where it came from, so the history explains its own gap",
          "renumbered from 2" in (rows["v2b"]["note"] or ""), rows["v2b"]["note"])
    check("...and its original note survives rather than being overwritten",
          (rows["v2b"]["note"] or "").startswith("+2/-0"), rows["v2b"]["note"])

# ...and the index the migration exists to create refuses the next collision. Every required column
# is supplied and the message is matched against ITS OWN constraint: a bare IntegrityError is what a
# schema says when anything is wrong, and a probe that dies on NOT NULL would pass a weaker check
# while proving nothing. (That is not hypothetical — it is what `test_bcf_reimport_dedupe.py`'s first
# version did, and it passed.)
def _refusal(sql: str, params: dict) -> str:
    try:
        with mig.begin() as conn:
            conn.execute(sa.text(sql), params)
    except sa.exc.IntegrityError as exc:
        return str(exc.orig)
    return ""


_INSERT = ("INSERT INTO model_versions (id, project_id, version, element_count, guids, "
           "review_status, created_at) VALUES (:i,:p,:v,0,'[]','draft','2026-02-01 09:00:00')")
refusal = _refusal(_INSERT, {"i": "v-dup", "p": PID, "v": 3})
check("a fresh collision is refused, and by uq_model_versions_project_version",
      "UNIQUE" in refusal and "model_versions.project_id" in refusal
      and "model_versions.version" in refusal, refusal or "the index accepted a duplicate")
control = _refusal(_INSERT, {"i": "v-free", "p": PID, "v": 99})
check("the probe is otherwise valid, so the refusal above is the index and not a missing column",
      control == "", control or "the same insert with a free number was accepted")

mig.dispose()
os.environ["DATABASE_URL"] = _live

# ── 2. the allocator: a second publish gets the NEXT number, not a 500 ───────────────────────────
# The constraint alone would make a legitimate second publish fail. `snapshot()` retries against the
# new maximum, which is why it cannot use `auth.get_or_create_by_key`: the key is COMPUTED, so a
# loser must recompute rather than adopt the winner's row — the two publishes are different
# snapshots and both belong in the history.
import sys  # noqa: E402

sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(HERE.parent / "data" / "src"))

from aec_api import versions  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import Base, ModelVersion, Project  # noqa: E402

Base.metadata.create_all(engine)
P2 = "p-alloc"
with SessionLocal() as db:
    db.add(Project(id=P2, name="Alloc"))
    db.commit()


def _idx(guids: list[str]) -> dict:
    """The shape `versions._guids` actually reads: `{"elements": [{"guid": ...}, ...]}`.

    The first draft returned `{guid: {...}}`, which `_guids` reads as zero elements — so every
    snapshot in this file was of an EMPTY model and the delta assertions below were comparing
    nothing to nothing. It surfaced only because the note check demanded a specific number ("+4/-0")
    and got "+0/-0". *A check that asserts a value catches what a check that asserts "it ran" does
    not* — the same lesson as the uniqueness probes above, one layer up.
    """
    return {"elements": [{"guid": g, "name": g, "ifc_class": "IfcWall"} for g in guids]}


first = versions.snapshot(P2, _idx(["A", "B"]))
second = versions.snapshot(P2, _idx(["A", "B", "C"]))
check("consecutive publishes get consecutive numbers", (first["version"], second["version"]) == (1, 2),
      (first["version"], second["version"]))

# The lost race, folded: a competing publish takes number 3 between this caller's read and its
# commit. Reproduced by inserting it from a second session inside the read — the same technique as
# `test_member_role_race.py`, and for the same reason: SQLite serialises writers, so the interleaving
# has to be constructed rather than raced.
_real_query = SessionLocal


class _StealOnce:
    """Commits the number the allocator is about to use, AFTER it has read the maximum.

    **The steal point is the whole test, and the first version got it wrong.** Stealing when the
    session opens puts the competing row in place *before* `snapshot()` reads the maximum, so the
    allocator simply reads 3 and writes 4 — no conflict, no retry, and the check passed with the
    retry deleted. Verified by mutation, which is the only reason it was found.

    So the steal fires on `Session.add`: `snapshot()` reads the maximum, computes its number,
    then calls `add` — and only then does the competitor commit. The outer session has issued
    nothing but a SELECT at that point, so SQLite has no write lock to block on, and the collision
    lands on the outer `commit()` where a real race would put it.
    """

    def __init__(self) -> None:
        self.fired = False

    def __call__(self, *a, **kw):
        db = _real_query(*a, **kw)
        outer_add = db.add

        def add(obj, *aa, **kk):
            if not self.fired:
                self.fired = True
                with _real_query() as other:
                    other.add(ModelVersion(project_id=P2, version=3, element_count=0, guids=[],
                                           note="competing publish"))
                    other.commit()
            return outer_add(obj, *aa, **kk)

        db.add = add
        return db


# `snapshot()` imports SessionLocal from `.db` INSIDE the function, so the patch has to land
# on the module it reads from rather than on `versions` itself — patching
# `versions.SessionLocal` would be a no-op that leaves this test quietly measuring nothing.
import aec_api.db as _db  # noqa: E402

_db.SessionLocal = _StealOnce()
third = versions.snapshot(P2, _idx(["A", "B", "C", "D"]))
_db.SessionLocal = _real_query

check("a publish that loses the number retries and takes the NEXT one, rather than 500-ing",
      third["version"] == 4, third)
with SessionLocal() as db:
    rows2 = db.query(ModelVersion).filter(ModelVersion.project_id == P2).all()
    got = sorted(v.version for v in rows2)
    check("...and every publish survives — a loser is not folded onto the winner, it is a real snapshot",
          got == [1, 2, 3, 4], got)
    # The retry recomputes the DELTA too, not just the number. The first attempt measured against
    # version 2 (A,B,C) and would have written "+1/-0"; the retry measures against the competitor,
    # version 3, which holds no elements, so the right answer is "+4/-0". Asserted because the
    # first draft of the retry reassigned the `note` parameter, which pinned the first attempt's
    # text onto a row computed from a different baseline — a note that lies about its own row.
    note4 = next(v.note for v in rows2 if v.version == 4)
    check("a retried publish's note describes the baseline it actually landed on",
          note4 == "+4/-0", note4)

for _f in ("_model_version_collision.db", "_model_version_collision_mig.db"):
    (HERE / _f).unlink(missing_ok=True)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("\ntest_model_version_collision OK - the migration keeps every issued number on the row that "
      "was issued it and moves only the later duplicate past the maximum (so a signed "
      "record_model_version still resolves), the new index then refuses the next collision, and "
      "snapshot() retries a lost allocation into the next free number instead of failing a "
      "legitimate publish.")
