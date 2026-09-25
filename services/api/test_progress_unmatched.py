"""PROGRESS-DARK — does a capture diff say how much of the capture it could not use?

`progress_rollup.capture_diff` builds both of its sets by filtering through the model's element
list:

    added   = sorted(g for g in (s2 - s1) if g in known)
    removed = sorted(g for g in (s1 - s2) if g in known)

and its note promised the opposite of what that does:

    > Elements present at t1 but absent at t2 are surfaced as 'disappeared' — a re-scan or rework
    > flag, **never silently dropped**.

**The promise held only among elements the CURRENT model still contains**, which excludes exactly
the case a rework flag is for: something taken out of the model *and* off the site between captures.
Measured before the fix — 500 capture GUIDs at t2 against a 300-element model:

    installed_t2 300 · newly_installed 300 · pct_complete_t2 1.0 · 200 dropped · no key naming them

*A note that claims more than the code does is worse than no note*, because it is read as a
guarantee and stops the next person looking.

**The filter is kept and only the silence is fixed.** A diff is scoped to the model it is about, and
a GUID with no element carries no class or storey to group by — so `added_by_class` and
`added_by_level` have nothing to put it in. What changed is that the count is reported, so a capture
aimed at a different model version shows up as an unmatched count instead of arriving as a quietly
smaller diff that reads like slower progress.

The caps beside it were ALREADY the good pattern and are left alone: `added_guids[:200]` sits next to
`newly_installed`, which is the true total. `unmatched_guids` follows the same shape.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_progress_unmatched.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_progress_unmatched")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import inspect  # noqa: E402

from aec_api import progress_rollup as pr  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('   ' + detail) if detail else ''}")
    if not ok:
        FAILURES.append(name)


MODEL = [{"guid": f"E{i}", "ifc_class": "IfcWall", "storey": "L1"} for i in range(300)]

# ------------------------------------------------------------------------------------------------
# THE CLAIM, REPRODUCED. A capture naming 500 installed elements against a 300-element model.
# ------------------------------------------------------------------------------------------------
t2 = [f"E{i}" for i in range(300)] + [f"UNKNOWN{i}" for i in range(200)]
r = pr.capture_diff(MODEL, [], t2, "2026-01-01", "2026-02-01")

check("PRECONDITION: the diff ran and counted the known elements",
      r["installed_t2"] == 300 and r["newly_installed"] == 300,
      f"installed_t2={r['installed_t2']} newly_installed={r['newly_installed']}")
check("the 200 capture GUIDs with no element are COUNTED, not dropped",
      r["unmatched_t2"] == 200, f"unmatched_t2={r['unmatched_t2']}")
#: `.get()`, not `[...]`. Deleting the key made this file die with a bare KeyError — which IS a
#: red, but one that names Python instead of the property that broke. A check whose failure message
#: can misdiagnose is worse than one that stays silent, because somebody acts on it.
_listed = r.get("unmatched_guids")
check("...and are listed, capped like every other page here",
      isinstance(_listed, list) and 0 < len(_listed) <= 200,
      f"{len(_listed) if isinstance(_listed, list) else _listed!r} listed of {r['unmatched_t2']}")
check("...and the note says so in numbers rather than in general",
      "200 capture GUID(s) matched no element" in r["note"])

# The t1 side is the half the old note actually named, and it had the same hole.
r_t1 = pr.capture_diff(MODEL, ["E1", "GHOST1", "GHOST2"], ["E1"])
check("an UNMATCHED GUID vanishing between captures is counted on the t1 side too",
      r_t1["unmatched_t1"] == 2, f"unmatched_t1={r_t1['unmatched_t1']}")
check("...while a KNOWN element vanishing is still a 'disappeared', as it always was",
      pr.capture_diff(MODEL, ["E1", "E2"], ["E1"])["disappeared"] == 1)

# ------------------------------------------------------------------------------------------------
# SILENCE MUST MEAN SOMETHING. A sweep that always speaks is a sweep nobody reads.
# ------------------------------------------------------------------------------------------------
clean = pr.capture_diff(MODEL, [], [f"E{i}" for i in range(300)])
check("a capture that matches entirely reports zero unmatched",
      clean["unmatched_t1"] == 0 and clean["unmatched_t2"] == 0)
check("...and the note adds no count sentence at all",
      "matched no element" not in clean["note"])
check("...and lists no unmatched GUIDs",
      clean.get("unmatched_guids") == [])

# ------------------------------------------------------------------------------------------------
# THE NOTE MUST NOT RE-OVERCLAIM. This is the defect that was in the prose rather than the code, so
# the prose is what is pinned: the old sentence promised a property the filter cannot deliver.
# ------------------------------------------------------------------------------------------------
check("the note no longer claims disappearances are NEVER silently dropped",
      "never silently dropped" not in clean["note"],
      "the filter cannot deliver that, and the sentence stopped the next reader looking")
check("...and states the scope it actually has",
      "only GUIDs the model still contains" in clean["note"])

# ------------------------------------------------------------------------------------------------
# THE GOOD PATTERN BESIDE IT IS UNTOUCHED — a page with its true total.
# ------------------------------------------------------------------------------------------------
big = pr.capture_diff(MODEL, [], [f"E{i}" for i in range(300)])
check("added_guids is a page and newly_installed is the total",
      len(big["added_guids"]) == 200 and big["newly_installed"] == 300,
      f"{len(big['added_guids'])} listed of {big['newly_installed']}")

# ------------------------------------------------------------------------------------------------
# PRECONDITION: the filter this file reasons about is still the one in the code. If someone removes
# it, unmatched GUIDs would flow into added_by_class with no class — a different bug, and these
# assertions would be measuring nothing.
# ------------------------------------------------------------------------------------------------
src = inspect.getsource(pr.capture_diff)
check("PRECONDITION: both sets are still filtered through the model's elements",
      src.count("if g in known") == 2, f"{src.count('if g in known')} filter(s)")
check("PRECONDITION: unmatched is derived from the SAME membership test",
      "g not in known" in src)

print()
if FAILURES:
    print(f"progress_unmatched: {len(FAILURES)} FAILED — {FAILURES}")
    sys.exit(1)
print("progress_unmatched: all checks passed — a capture diff reports the GUIDs it could not use, "
      "and its note claims only the scope the filter gives it.")
