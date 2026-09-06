"""`b6e1c4d09a37`'s dedupe, run against a seeded dirty database — because it only ever runs once.

## Why a migration's dedupe needs its own test more than ordinary code does

Every other line in this repository runs on every request, so a mistake shows up. A dedupe runs
**once, on a production database, against rows nobody here has ever seen**, and if it is wrong the
evidence it was wrong is the data it destroyed. The three sibling migrations this week were exercised
by hand against a seeded database and the exercise was thrown away, which means the *record* of them
working is prose. This one is the most complex of the four — it re-parents six tables rather than
deleting a row — so the exercise is committed instead.

## What the migration has to get right, and what this asserts

`import_bcfzip` used to blind-insert a `Topic` for every `<Topic Guid>` in the file, so a database
that has seen a re-import holds two topics with one guid, each carrying its own comments, viewpoints
and attachments, plus audit entries and drawing markups pointing at whichever id they were created
under. Adding `uq_topics_project_guid` on top of that fails outright unless the duplicates are
resolved first.

Resolving them by DELETE would take a real conversation with the losing row and leave three soft
references — `record_comments.topic_id`, `audit_log.topic_id`, `drawing_markups.topic_id`, none of
them foreign keys — pointing at a topic that no longer exists. So the migration re-parents every
child onto the earliest topic and only then removes the empty row, and the checks below follow the
data rather than the code: seed the mess, upgrade, count what survived.

Run: cd services/api && PYTHONPATH=src ./.venv/bin/python test_bcf_reimport_dedupe.py
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
_DB = HERE / "_bcf_reimport_dedupe.db"
os.environ["DATABASE_URL"] = "sqlite:///./_bcf_reimport_dedupe.db"
os.environ["STORAGE_DIR"] = "./_storage_bcf_reimport_dedupe"
_DB.unlink(missing_ok=True)

import sqlalchemy as sa  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

#: The revision immediately before the one under test — the state a database is in when it still
#: holds duplicates. Upgrading only this far is what makes the seeding below possible at all: at
#: `head` the unique index already exists and would refuse the second row.
_BEFORE = "a3c7d9e4f218"
_UNDER_TEST = "b6e1c4d09a37"

FAILED: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


cfg = Config(str(HERE / "alembic.ini"))
cfg.set_main_option("script_location", str(HERE / "migrations"))
command.upgrade(cfg, _BEFORE)

engine = sa.create_engine(os.environ["DATABASE_URL"])
PID = "p-dedupe"
GUID = "2$aBcDeFgHiJkLmNoPqRsT"

with engine.begin() as conn:
    conn.execute(sa.text("INSERT INTO projects (id, name, created_at) VALUES (:i, :n, :c)"),
                 {"i": PID, "n": "Coordination", "c": "2026-01-01 08:00:00"})
    # Two topics, one guid: the first import and a re-import of the same file a week later.
    for tid, when, title in (("t-first", "2026-01-01 09:00:00", "Beam vs duct"),
                             ("t-second", "2026-01-08 09:00:00", "Beam vs duct (still open)")):
        conn.execute(sa.text(
            "INSERT INTO topics (id, guid, project_id, type, title, status, created_at, modified_at) "
            "VALUES (:i, :g, :p, 'clash', :t, 'open', :c, :c)"),
            {"i": tid, "g": GUID, "p": PID, "t": title, "c": when})
    # The same conversation under both, as the old importer left it — plus one comment that exists
    # only under the loser, which must SURVIVE the merge rather than being deduped away with it.
    for cid, tid, when, text in (
            ("c-1a", "t-first", "2026-01-01 09:05:00", "Rerouting above the beam."),
            ("c-1b", "t-second", "2026-01-08 09:05:00", "Rerouting above the beam."),
            ("c-2", "t-second", "2026-01-08 09:06:00", "Confirmed on site.")):
        conn.execute(sa.text(
            "INSERT INTO comments (id, topic_id, text, created_at) VALUES (:i, :t, :x, :c)"),
            {"i": cid, "t": tid, "x": text, "c": when})
    conn.execute(sa.text(
        "INSERT INTO viewpoints (id, topic_id, guid, created_at) "
        "VALUES ('v-2', 't-second', 'vp-guid', '2026-01-08 09:07:00')"))
    conn.execute(sa.text(
        "INSERT INTO attachments (id, topic_id, filename, storage_key, size, kind, created_at) "
        "VALUES ('a-2', 't-second', 'photo.jpg', 'k/photo.jpg', 0, 'photo', '2026-01-08 09:08:00')"))
    # ...and a soft reference with no foreign key behind it, which a plain DELETE would strand.
    conn.execute(sa.text(
        "INSERT INTO audit_log (id, action, topic_id, ts) "
        "VALUES ('au-2', 'topic.update', 't-second', '2026-01-08 09:09:00')"))

command.upgrade(cfg, _UNDER_TEST)

with engine.begin() as conn:
    rows = conn.execute(sa.text(
        "SELECT id, title FROM topics WHERE project_id = :p AND guid = :g"),
        {"p": PID, "g": GUID}).mappings().all()
    check("one topic survives the duplicate pair", len(rows) == 1, [dict(r) for r in rows])
    check("...and it is the EARLIEST row, the id every other record already pointed at",
          bool(rows) and rows[0]["id"] == "t-first", rows[0]["id"] if rows else None)

    comments = conn.execute(sa.text(
        "SELECT id, guid, text FROM comments WHERE topic_id = 't-first' ORDER BY created_at"),
    ).mappings().all()
    # c-1a and c-1b are the same sentence but were inserted under different ids, so they carry
    # DIFFERENT backfilled guids and both survive. That is correct and worth stating: the migration
    # dedupes on identity, not on text, because two people really can say the same thing twice.
    check("every comment is re-parented onto the survivor, including the loser's own",
          len(comments) == 3, [c["text"] for c in comments])
    check("...and each carries a backfilled guid equal to its id, the value already in exported files",
          all(c["guid"] == c["id"] for c in comments), [(c["id"], c["guid"]) for c in comments])

    for table, expect in (("viewpoints", "v-2"), ("attachments", "a-2"), ("audit_log", "au-2")):
        got = conn.execute(sa.text(f"SELECT topic_id FROM {table} WHERE id = :i"),
                           {"i": expect}).scalar()
        check(f"{table} row is re-parented, not stranded on a deleted topic", got == "t-first", got)

    orphans = conn.execute(sa.text(
        "SELECT COUNT(*) FROM audit_log WHERE topic_id IS NOT NULL AND topic_id NOT IN "
        "(SELECT id FROM topics)")).scalar()
    check("no soft reference points at a topic that no longer exists", orphans == 0, orphans)

# ...and the index the migration exists to create actually refuses the next duplicate. Without this
# the whole file would prove only that the dedupe ran, not that it achieved anything.
refused = None
try:
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO topics (id, guid, project_id, type, title, status) "
            "VALUES ('t-third', :g, :p, 'clash', 'again', 'open')"), {"g": GUID, "p": PID})
except sa.exc.IntegrityError as exc:
    refused = exc
check("a fresh duplicate is now refused by uq_topics_project_guid", refused is not None,
      "the index accepted a third row" if refused is None else "UNIQUE constraint held")

# the same for comments, whose index only becomes reachable once the topics collapse
crefused = None
try:
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO comments (id, guid, topic_id, text) VALUES ('c-dup', 'c-1a', 't-first', 'x')"))
except sa.exc.IntegrityError as exc:
    crefused = exc
check("a duplicate comment guid on one topic is refused by uq_comments_topic_guid",
      crefused is not None, "the index accepted it" if crefused is None else "UNIQUE constraint held")

engine.dispose()
_DB.unlink(missing_ok=True)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("\ntest_bcf_reimport_dedupe OK - a duplicate topic pair collapses onto the earliest row with "
      "every comment, viewpoint, attachment and audit entry re-parented rather than deleted, comment "
      "guids are backfilled to the ids already written into exported .bcfzip files, and both new "
      "unique indexes then refuse the next duplicate.")
