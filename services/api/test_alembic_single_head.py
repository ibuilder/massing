"""The migration graph has exactly one head, and every revision is reachable from it.

WRITTEN FROM A LIVE BREAK. On 2026-08-07 main went red with:

    ERROR [alembic.util.messaging] Multiple head revisions are present for given argument 'head'

Two PRs were open at once, both branched from a main whose head was `f4b8d2e17c93`, and both added a
migration naming it as `down_revision` — `b4c1f7d92e08` (R41-FDD-INGEST) and `b6d1c48f2a35`
(R39-VIEWER-OBS). **Each was correct in isolation and each one's Alembic job passed**, because on
either branch there was exactly one head. The fork exists only in the union.

That is the property worth stating plainly: *a check that runs per-branch cannot catch a conflict that
only exists after the merge.* Nothing here changes that — two PRs opened simultaneously will still
both pass this test and still fork on landing. What this buys is the other half:

  * it fails on **main**, in the fast local suite, in milliseconds — not only in the Postgres workflow
    that needs a service container and several minutes;
  * it **names the heads and their common parent**, so the fix is obvious. Alembic's own message says
    only "multiple heads are present" and leaves the reader to diff nineteen files to find which two.

The durable prevention is requiring a branch to be up to date with main before merging. This is the
detector, not the cure, and it is written down that way so nobody mistakes it for the cure.

WHY IT PARSES RATHER THAN IMPORTS. Reading the files with a regex means no database, no alembic
config, no engine — so it runs in the ordinary suite on every PR rather than only where Postgres is
available. The parse has to handle BOTH styles present in this tree, which is exactly the sort of
detail a naive version gets wrong:

    revision = "b6d1c48f2a35"                      # plain
    revision: str = 'b4c1f7d92e08'                 # annotated, single quotes

A first attempt at this analysis missed the annotated form and reported 15 of 18 migrations as having
no parent — which read as "everything is a root" rather than as a broken regex. The self-check below
exists because of that: if the parse degrades, the head count collapses to something absurd and this
test must fail on the parse rather than pass on the emptiness.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_alembic_single_head.py
"""
import pathlib
import re
import sys

VERSIONS = pathlib.Path(__file__).resolve().parent / "migrations" / "versions"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


# Both quote styles, with or without a `: str` / `: str | None` annotation. `down_revision` may also
# be a TUPLE (a merge revision), which is the whole point of the fix this file was written beside.
_REV = re.compile(r"^revision(?:\s*:\s*[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)
_DOWN_STR = re.compile(r"^down_revision(?:\s*:\s*[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)
_DOWN_TUP = re.compile(r"^down_revision(?:\s*:\s*[^=]+)?\s*=\s*\(([^)]*)\)", re.M)

graph: dict[str, tuple[str, ...]] = {}
where: dict[str, str] = {}
for path in sorted(VERSIONS.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    m = _REV.search(text)
    if not m:
        continue
    rev = m.group(1)
    if tup := _DOWN_TUP.search(text):
        parents = tuple(p.strip().strip("\"'") for p in tup.group(1).split(",") if p.strip())
    elif one := _DOWN_STR.search(text):
        parents = (one.group(1),)
    else:
        parents = ()
    graph[rev] = parents
    where[rev] = path.name

files = list(VERSIONS.glob("*.py"))
check("every migration file yielded a revision id — otherwise the parse is what failed",
      len(graph) == len(files), f"parsed {len(graph)} of {len(files)} files")
roots = [r for r, p in graph.items() if not p]
check("exactly one migration is a root", len(roots) == 1,
      f"{len(roots)} roots: {sorted(roots)[:5]} — more than one usually means the `down_revision` "
      f"regex stopped matching a style present in the tree, not that the graph changed")

parents = {p for ps in graph.values() for p in ps}
heads = sorted(r for r in graph if r not in parents)
check("the migration graph has exactly ONE head", len(heads) == 1,
      "heads: " + ", ".join(f"{h} ({where[h]}, down={graph[h]})" for h in heads)
      + ". Common parent(s): "
      + ", ".join(sorted({p for h in heads for p in graph[h]}))
      + ". Fix with an empty merge revision whose down_revision is the tuple of these heads; do NOT "
        "re-point one at the other, which lies to any database that already ran it.")

# A parent naming a revision that does not exist breaks `upgrade head` just as hard, and reads as a
# different error, so it is worth separating.
missing = sorted({p for ps in graph.values() for p in ps if p not in graph})
check("every down_revision names a migration that exists", not missing,
      f"dangling parents: {missing}")

# A duplicate revision id needs no check of its own: `graph` is keyed by revision, so a second file
# claiming an existing id overwrites the first and the parsed count drops below the file count — which
# the first assertion above already catches, and names. Counting duplicates in `graph` itself would be
# vacuous, since dict keys are unique by construction.

# Reachability: walking back from the single head must visit every migration. A revision nobody points
# at and that points at nothing reachable would never run, and would not show up as a second head.
if len(heads) == 1:
    seen: set[str] = set()
    stack = [heads[0]]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(p for p in graph.get(cur, ()) if p in graph)
    orphans = sorted(set(graph) - seen)
    check("every migration is reachable from the head — an unreachable one never runs",
          not orphans, f"unreachable: {[(o, where[o]) for o in orphans][:5]}")

print(f"\ntest_alembic_single_head {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}"
      f"  ({len(graph)} migrations, head={heads[0] if len(heads) == 1 else heads})")
sys.exit(1 if failures else 0)
