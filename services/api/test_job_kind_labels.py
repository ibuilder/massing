"""Every registered job kind has a human label in the job tray — two lists, two languages, one check.

`jobs.KINDS` (Python) and `KIND_LABEL` in `apps/web/src/ui/jobTray.ts` are hand-maintained lists of
the same thing on opposite sides of the wire, and nothing compared them. `jobTray.ts` falls back to
rendering the raw kind, deliberately and correctly — a plugin can register a kind in one line and
inventing a friendly label for something unknown is how a UI starts lying. But that fallback also
means a kind WE ship without a label degrades silently: the tray shows `clash_federated` and no gate
goes red. The fallback is right for plugins and wrong for us, and only a check can tell those apart.

**Direction matters, and only one direction is a defect.**

  * A registered kind with no label is a **failure**: we shipped it, so we can name it.
  * A label with no registered kind is a **failure too**, and the more insidious one: it is a label
    for a kind that was renamed or removed, which will never render again and which the next reader
    will take as evidence the feature still exists. Same shape as the roadmap's "names no item that
    has left the roadmap".

`echo` is excluded from the first rule only — it is the queue's own test kind. It has a label anyway;
the exclusion exists so that deleting the test kind does not require a web change.

**Parsed as text, and that is the weaker half of this check, stated rather than hidden.** The TS side
is read with a regex over the object literal. If someone rewrites `KIND_LABEL` as a `Map` or splits it
across files, the parse finds nothing — which is why the first assertion is that it found a
non-trivial number of labels at all. A vacuous parse would otherwise report perfect agreement between
one list and an empty one.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_job_kind_labels.py
"""
from __future__ import annotations

import os
import pathlib
import re

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_job_kind_labels.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_job_kind_labels")
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_job_kind_labels.db"):
    os.remove("./test_job_kind_labels.db")

from aec_api import jobs  # noqa: E402

TRAY = pathlib.Path(__file__).resolve().parents[2] / "apps" / "web" / "src" / "ui" / "jobTray.ts"

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


src = TRAY.read_text(encoding="utf-8")
block = re.search(r"const KIND_LABEL: Record<string, string> = \{(.*?)\n\};", src, re.S)
labels: set[str] = set()
if block:
    labels = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", block.group(1), re.M))

check("the KIND_LABEL literal parses -- a vacuous parse would agree with anything",
      len(labels) >= 5, f"{len(labels)} label(s): {', '.join(sorted(labels))}")

registered = set(jobs.KINDS)
check("the job registry is non-empty -- likewise", len(registered) >= 5,
      f"{len(registered)} kind(s)")

#: The queue's own test kind. Excluded from the "needs a label" rule so deleting it never forces a
#: web change; it is NOT excluded from the reverse rule, because a stale label is still stale.
TEST_KINDS = {"echo"}

unlabelled = sorted(registered - labels - TEST_KINDS)
check("every registered job kind has a label in the job tray", not unlabelled,
      ", ".join(unlabelled) + " -- add to KIND_LABEL in apps/web/src/ui/jobTray.ts"
      if unlabelled else f"{len(registered)} kind(s) covered")

orphans = sorted(labels - registered)
check("...and every label names a kind that is still registered", not orphans,
      ", ".join(orphans) + " -- a label for a kind nothing can produce reads as a live feature"
      if orphans else "no stale labels")

# The twin. Both assertions above are satisfied by two empty sets, and by two identical WRONG sets.
# Planting a kind that the TS file cannot possibly contain proves the comparison is real.
_planted = sorted(({*registered, "kind_that_does_not_exist"}) - labels - TEST_KINDS)
check("...and the comparison can actually fail -- a planted kind is reported",
      "kind_that_does_not_exist" in _planted, str(_planted))
# Membership, not equality. The first draft asserted `_planted == ["kind_that_does_not_exist"]`,
# which is only true when the real comparison is already clean -- so a genuinely missing label made
# BOTH this and the assertion above go red, reporting one defect twice and burying which was which.
# A control must be independent of the thing it controls for.

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print(f"test_job_kind_labels OK  ({len(registered)} kinds, {len(labels)} labels)")
