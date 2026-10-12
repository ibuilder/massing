"""ELEMENTS-SILENT — the project browser was STALE and TRUNCATED at once and reported neither.

`/projects/{pid}/elements/freshness` was written to prevent one specific silent wrong answer, says so
in its own docstring — *"a browser can show '5 elements added since this list was built — republish
to see them' instead of quietly looking like a smaller building"* — and **had no client method at
all**. `services/api/test_route_reachability.py` carried it as a frozen unreachable route.

It is wired now (`apps/web/src/api/elements.ts` → `apps/web/src/viewer/tools/indexCoverage.ts` →
`apps/web/src/viewer/tools/projectPanel.ts`), which means three properties of this payload stopped
being internal details and became the things a screen's wording rests on. This gate holds them.

WHAT THE SCREEN NOW DEPENDS ON
------------------------------
**① `stale` is tri-state, and the two `None` reasons are DISTINGUISHABLE.** The route is explicit:
*"Unknown and current are different claims and this endpoint refuses to conflate them."* The browser
gives different advice for each — "no source model can be read, so there is nothing to compare
against" tells a user to find the file; "this index predates publish fingerprinting" tells them to
republish. `built_from_source` and `model_reachable` are what separates them, so collapsing those two
booleans into one would not break any test of this route while silently making the screen give the
wrong instruction for half its cases. Both are asserted, each on its own.

**② `indexed_elements` is the size of the WHOLE index.** It is the denominator the browser compares
an unfiltered `/elements` page against, and `/elements` itself has no total of any kind — it breaks
at `len(out) >= limit` and returns a bare array, so this is the only number in the API that can say a
5,000-row page came out of a 12,000-element model. The signature is therefore pinned to take **no
filter parameter**: adding `ifc_class` here would make `indexed_elements` a filtered count and the
browser's comparison silently wrong, with nothing going red.

**③ `hint` is None when the index is current.** The browser prints it, so a republish instruction
attached to a fresh index is a false alarm on every clean project.

HOW THE MUTATION ARM WORKS
--------------------------
The conflating form — `stale = built_from != current`, which answers False for "unknown" — is
replayed here and the SAME battery is required to reject it. Because that replay is a copy, the
route's real line is pinned by source as well: a copy that cannot drift is the only kind worth
replaying. *Asking the right question and then throwing the answer away are two different failures.*

Run: cd services/api && PYTHONPATH="src:../data/src" ./.venv/bin/python test_elements_freshness.py
"""
import inspect
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_elements_freshness.db"
os.environ["STORAGE_DIR"] = "./test_storage_elements_freshness"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_elements_freshness.db"):
    os.remove("./test_elements_freshness.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import aec_data.ifc_loader as ifc_loader  # noqa: E402
from aec_api import deps as api_deps  # noqa: E402
from aec_api.routers import properties as props  # noqa: E402

FAILED: list[str] = []


def ok(cond, label):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILED.append(label)


PID = "freshness-probe"
_TMP = tempfile.NamedTemporaryFile(suffix=".ifc", delete=False)
_TMP.write(b"ISO-10303-21;\nENDSEC;\nEND-ISO-10303-21;\n")
_TMP.close()


def payload(*, built_from: str | None, current: str | None) -> dict:
    """The REAL route, driven over its two inputs.

    `built_from` is the fingerprint the index was stamped with (None = never stamped);
    `current` is the fingerprint of the source on disk (None = no reachable source).
    """
    props._INDEX[PID] = {f"g{i}": {"ifc_class": "IfcWall", "storey": "L1"} for i in range(7)}
    props._META[PID] = {"source_key": built_from} if built_from else {}

    orig_path, orig_key = api_deps.source_ifc_path, ifc_loader.content_key
    try:
        if current is None:
            def _no_source(db, pid):
                raise RuntimeError("no source file for project")
            api_deps.source_ifc_path = _no_source
        else:
            api_deps.source_ifc_path = lambda db, pid: _TMP.name
            ifc_loader.content_key = lambda path, stat: current
        return props.elements_freshness(PID, db=None, _="viewer")
    finally:
        api_deps.source_ifc_path, ifc_loader.content_key = orig_path, orig_key
        props._INDEX.pop(PID, None)
        props._META.pop(PID, None)


# ── ① the three states, and the two reasons for the third ────────────────────────────────────────
def battery(build) -> list[str]:
    """Every claim the browser's wording rests on, as a reusable list of failures.

    Reusable because the mutation arm below runs it against the conflating payload builder and
    requires it to come back non-empty. A battery that only ever runs against the shipped code
    cannot tell you whether it would notice the defect.
    """
    bad: list[str] = []
    moved = build(built_from="stamp-A", current="stamp-B")
    if moved.get("stale") is not True:
        bad.append(f"a moved model must report stale=True, got {moved.get('stale')!r}")
    if not moved.get("hint"):
        bad.append("a stale index must carry a hint — the browser prints it")

    same = build(built_from="stamp-A", current="stamp-A")
    if same.get("stale") is not False:
        bad.append(f"an unchanged model must report stale=False, got {same.get('stale')!r}")
    if same.get("hint") is not None:
        bad.append("a CURRENT index must carry no hint: a republish instruction on a fresh "
                   "project is a false alarm the browser would render")

    # Unknown, reason A: nothing to compare against at all.
    unreachable = build(built_from="stamp-A", current=None)
    if unreachable.get("stale") is not None:
        bad.append("no reachable source model is UNKNOWN, not a verdict: got "
                   f"{unreachable.get('stale')!r}")
    if unreachable.get("model_reachable") is not False:
        bad.append("the payload must say WHICH reason applies: model_reachable should be False")
    if unreachable.get("built_from_source") is not True:
        bad.append("an index that WAS stamped must still say so when the source is unreachable — "
                   "otherwise the browser cannot tell the two unknown reasons apart")

    # Unknown, reason B: the index was never stamped, and the model is right there.
    unstamped = build(built_from=None, current="stamp-A")
    if unstamped.get("stale") is not None:
        bad.append("an unstamped index is UNKNOWN, not current: got "
                   f"{unstamped.get('stale')!r}")
    if unstamped.get("built_from_source") is not False:
        bad.append("built_from_source must be False for an unstamped index")
    if unstamped.get("model_reachable") is not True:
        bad.append("model_reachable must stay True when the source is readable — the two unknown "
                   "reasons must not collapse into one")

    # ② the denominator
    if same.get("indexed_elements") != 7:
        bad.append(f"indexed_elements must be the whole index (7), got "
                   f"{same.get('indexed_elements')!r}")
    return bad


problems = battery(payload)
ok(not problems, "the shipped route satisfies every claim the browser's wording rests on"
   + ("" if not problems else " — " + " | ".join(problems)))


# ── the mutation arm: the conflating form must be REJECTED by that same battery ──────────────────
#
# `stale = built_from != current` is the shape this route exists not to have. It answers False —
# "current" — for an index nobody could check, which is the original silent wrong answer with a
# field name attached.
def conflating_payload(*, built_from: str | None, current: str | None) -> dict:
    return {
        "indexed_elements": 7,
        "stale": built_from != current,
        "built_from_source": bool(built_from),
        "model_reachable": current is not None,
        "hint": "republish to rebuild the index from the current model" if built_from != current
                else None,
    }


conflated = battery(conflating_payload)
ok(any("UNKNOWN" in p or "not a verdict" in p for p in conflated),
   "the battery REJECTS the conflating form, naming unknown-vs-current "
   f"({len(conflated)} problem(s) found)")


# A second mutation, in the other direction: a payload that reports the unknown state correctly but
# folds the two REASONS into one boolean. Nothing about `stale` is wrong here, and the browser would
# still tell half its users to go looking for a file that is sitting right there.
def one_reason_payload(*, built_from: str | None, current: str | None) -> dict:
    p = payload(built_from=built_from, current=current)
    known = bool(built_from) and current is not None
    return {**p, "built_from_source": known, "model_reachable": known}


folded = battery(one_reason_payload)
ok(any("tell the two unknown reasons apart" in p or "must not collapse into one" in p
       for p in folded),
   "the battery REJECTS a payload that folds the two unknown REASONS into one flag "
   f"({len(folded)} problem(s) found)")


# ── ② the denominator can only stay the denominator if this route takes no filter ────────────────
_PARAMS = set(inspect.signature(props.elements_freshness).parameters)
ok(_PARAMS == {"pid", "db", "_"},
   "the freshness route takes NO filter parameter, so indexed_elements is the whole index and is "
   "comparable with an unfiltered /elements page — "
   f"signature is {sorted(_PARAMS)}")

# ── ③ and the reason the browser has to come here at all: /elements carries no total ─────────────
#
# Not a defect being frozen — a dependency being recorded. `list_elements` breaks at the limit and
# returns a bare list, so a consumer cannot distinguish a whole model from its first page. If a
# total is ever added there, this reds, and the right response is to switch the browser to the
# cheaper in-response number rather than to widen this allowance.
_LIST_SRC = inspect.getsource(props.list_elements)
ok("if len(out) >= limit:" in _LIST_SRC and "return out" in _LIST_SRC,
   "/elements still returns a bare, limit-truncated array with no total — which is WHY the browser "
   "reads indexed_elements from here")

# The staleness FORMULA has its own gate — `services/api/test_index_freshness.py`, which replays it
# as a pure function over the two fingerprints. That replay was unpinned until this change, so it
# was a claim about its own copy; the pin now lives there, beside the copy it holds. Nothing is
# repeated here, because the battery above calls the real route rather than a copy of it. The
# division is: that file asks whether the comparison is right, this one whether the payload a screen
# reads carries it — *a formula nobody emits and a payload nobody computes correctly are different
# defects, and a single file asserting both tends to end up asserting neither.*

os.unlink(_TMP.name)

print()
if FAILED:
    print(f"FAILED: {len(FAILED)}")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print("ELEMENTS-SILENT: the freshness payload holds every claim the project browser now makes.")
