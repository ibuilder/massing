"""A gap record that cites the RMW sweep and is still marked open, while the sweep has no open site
for it to be about, fails the build.

**Three records described the same finished work as outstanding, at once.** On 2026-09-24
`services/api/test_rmw_sweep.py` printed *"43 ORM sites: 43 reasoned exempt or locked, 0 named
open"*, while `docs/roadmap.md` carried RMW-LOCKGAP and RMW-TOKEN as 🟡 **OPEN** and
`docs/security/threat-model.md` carried G-10 and G-12 as open gaps and summarised *"**Four** sites
remain open"*. The last of those sites had been locked the day before. One of the two roadmap entries
had been HALF wrong on the day it was filed: `realestate.save_appraisal` took its lock in PR #552 on
2026-09-13 and the entry naming it as open was written on 2026-09-14.

**This is not a documentation-tidiness check.** A gap recorded as open is a work item: the roadmap's
own ranking sends the next reader at it, the threat model presents it to a reviewer as a live
exposure, and RMW-TOKEN's entry additionally priced the fix as *"a migration (add the column,
backfill, route both writers through a CAS)"* — work nobody ever did, because both sites closed with
a lock already in the tree. *A stale OPEN costs more than a stale CLOSED: one sends somebody to redo
finished work, the other is merely quiet.*

**Why the gate that exists did not catch it.** `services/api/test_roadmap_status.py` asks exactly the
right question — *does the item's own gate report the work done?* — but only for items somebody
REGISTERED in its `DONE_WHEN` map. Nothing forces a closing pull request to add itself, so the map
covers two items out of a file with hundreds. *A registry reports on what it contains, and its
silence is indistinguishable from a clean bill.* (That file had a second, worse problem, fixed in the
same change: its `marked_open` was itself unasserted, and the loop's shape is
`if not marked_open(code): PASS; continue` — so breaking the bullet regex with one literal made every
registered item report PASS and the file print *"every item with a measurement agrees with its
marker"*. Measured by mutation, not reasoned.)

**So this one needs no registration: it derives both sides.** The subjects come from the sweep
ledgers by AST; the records come from the two documents by structure. The rule is:

    a record that CITES the sweep gate and is marked OPEN must name at least one OPEN sweep site.

**The scoping clause is the load-bearing half, and it was learned rather than designed.** The first
draft ruled on every open record in both files, and reported SCALE-SEAM — an item about
`apps/web/src/api/client.ts` — as a stale concurrency gap, because 894 lines into its body it
mentions `_restore_version` while explaining which mixin the undo stack belongs in. That is the
false positive this file had already predicted in the abstract and then produced anyway. *A rule
applied outside the population it was reasoned about does not degrade gracefully; it produces
confident findings about records it has no view of.* Scoping to records that point AT the gate makes
the check say only what the gate can back: it speaks about records that claim it as their freezer,
and is silent everywhere else.

**And the rule is "must name an open site", not "must not name a closed one".** A genuinely open
record routinely cites its closed siblings for contrast — RMW-LOCKGAP's did exactly that, naming all
six LOCKED routes beside the six it was about. Under the stricter reading that record would have red
the build on the day it was correctly filed. Under this one it stayed green while one subject
remained open and turned red the moment the last one closed, which is the transition worth catching.
The same clause is what makes the check work on G-10, whose pre-fix body named its subjects only as
COLUMNS (`Scenario.shared_with`) and no function at all: a record citing the gate with no open site
named is caught whether it named nothing or named only closed things.

**Fails closed.** A ledger that does not parse, a status token outside the declared set, or a record
heading that cannot be classified stops the run — an analyser that cannot read its inputs must not
report a clean tree.

**And it proves its reach before it reports.** The verdict function is separate from the walk so it
can be mutated on its own (`test_unique_read_guard`'s lesson: *reporting a site and classifying it
are two different questions, and asserting one is not asserting the other*), and the whole analyser
is replayed against both documents AS SHIPPED at `53cfa71a` — the commit before this fix — where it
must re-find all four stale records. A pinned commit, not `HEAD`: replaying against HEAD would stop
proving anything the moment this fix merged.
"""
import ast
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent

#: The commit immediately before the four records were corrected. Pinned on purpose -- see above.
PRE_FIX = "53cfa71a"

#: A record is in this gate's scope only if it cites the gate that owns the ledger.
OWNER_GATE = "test_rmw_sweep.py"

#: Ledger names inside `test_rmw_sweep.py`. Read by AST rather than imported: that module does its
#: work at import time and calls `sys.exit`, so importing it would end this process.
LEDGERS = ("ORM_LEDGER", "BAND_2", "IFC_PIPELINE", "CROSS_FIELD")
STATUSES = {"EXEMPT", "OPEN", "LOCKED"}

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + label + (("   " + detail) if detail else ""))
    if not ok:
        FAILED.append(label)


def die(why: str) -> None:
    """Fail closed. An analyser that cannot read its inputs must not report a clean tree."""
    print(f"FAIL  gap-records could not read its own inputs: {why}")
    print(f"test_gap_records: 1 FAILED — {why}")
    sys.exit(1)


# ---------------------------------------------------------------- subjects (derived from the gate)

def ledger_status_by_function(sweep_src: str) -> dict[str, str]:
    """`{function name: worst status}` over every sweep ledger entry.

    Keyed by FUNCTION although the ledgers are keyed by `(path, function, attribute)`: a document
    names a function, not an attribute of it. Where one function's attributes disagree, OPEN wins --
    a record naming a function with any open attribute still has an open subject.
    """
    tree = ast.parse(sweep_src)
    found: dict[str, dict] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        if name in LEDGERS:
            try:
                found[name] = ast.literal_eval(node.value)
            except (ValueError, SyntaxError) as e:
                die(f"{name} in {OWNER_GATE} is not a literal dict ({e})")
    missing = [n for n in LEDGERS if n not in found]
    if missing:
        die(f"ledgers not found in {OWNER_GATE}: {missing}")

    out: dict[str, str] = {}
    for ledger in found.values():
        for key, value in ledger.items():
            if not (isinstance(key, tuple) and len(key) == 3):
                die(f"ledger key is not a (path, function, attribute) triple: {key!r}")
            status = value[0] if isinstance(value, tuple) else None
            if status not in STATUSES:
                die(f"ledger entry {key!r} carries status {status!r}, outside {sorted(STATUSES)}")
            fn = key[1]
            if out.get(fn) != "OPEN":
                out[fn] = status
    if not out:
        die("the sweep ledgers parsed to zero entries")
    return out


# ---------------------------------------------------------------------------- the verdict function

#: A COMPLETE backticked span, then required to be nothing BUT a dotted/slashed identifier chain,
#: optionally called: `place_family`, `drawingset.revise_sheet`, `routers/proforma.share_scenario`,
#: `_project(db, pid)`.
#:
#: **Two spellings broke the first draft, in opposite directions.** Without `/` in the chain the
#: match stopped at `routers`, so RMW-TOKEN -- whose subjects are written
#: `routers/proforma.share_scenario` and `routers/realestate.save_appraisal` -- came back clean from
#: the replay: *a record that names its subjects only in a spelling the analyser cannot read is
#: invisible to it, and reads identically to a record with no subjects.* And matching a PREFIX of the
#: span made `edit-mep` -- a recipe category, not a route -- match the ledger function `edit`, which
#: is how an unrelated item was first reported stale. *A prefix match answers a question nobody
#: asked, and answers it confidently.* Hence the whole span must be consumed.
_TICKED = re.compile(r"`([^`\n]+)`")
_CHAIN = re.compile(r"[A-Za-z_][\w./]*(?:\(.*\))?")

OUT_OF_SCOPE = "OUT-OF-SCOPE"
HAS_OPEN = "NAMES-AN-OPEN-SITE"
NO_OPEN = "NAMES-NO-OPEN-SITE"


def verdict(body: str, status_by_fn: dict[str, str]) -> tuple[str, list[str]]:
    """Classify one record body against the ledger. Separate from the walk so it can be mutated.

    Only BACKTICKED identifiers count. Prose uses these words in their ordinary sense -- "an edit",
    "the content import" -- and matching those would make every record name every subject.
    """
    if OWNER_GATE not in body:
        return OUT_OF_SCOPE, []
    named = sorted({
        tail
        for m in _TICKED.finditer(body)
        if _CHAIN.fullmatch(m.group(1))
        for tail in [re.split(r"[./]", m.group(1).split("(")[0])[-1]]
        if tail in status_by_fn
    })
    if any(status_by_fn[n] == "OPEN" for n in named):
        return HAS_OPEN, named
    return NO_OPEN, named


# ------------------------------------------------------------------------------ record delimitation

#: A roadmap item: a column-0 bullet whose heading bolds an ITEM CODE in caps. Status emoji optional
#: -- `test_roadmap_status.marked_open` treats a bullet with no emoji as open and so does this.
_ROADMAP_HEAD = re.compile(r"^[-*] ((?:(?:✅|◧|🟡|⭐)️? )*)\*\*([A-Z][A-Z0-9-]{2,})\b")
#: A threat-model gap: a numbered entry bolding a G-number.
_TM_HEAD = re.compile(r"^(\d+)\. \*\*(G-\d+)\b")


def records(text: str, kind: str) -> list[tuple[str, bool, str]]:
    """`[(code, is_open, body)]`, delimited by indentation."""
    lines = text.split("\n")
    head = _ROADMAP_HEAD if kind == "roadmap" else _TM_HEAD
    starts = [i for i, ln in enumerate(lines) if head.match(ln)]
    out = []
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        #: **A record ends at the first line back at column 0.** Both documents indent a record's
        #: body under its heading, so an unindented line is the next thing, whatever shape it has --
        #: the next item, the band's closing prose, a table, a section rule.
        #:
        #: The first draft ran each record to the next matching HEADING instead, which made one
        #: record 894 lines long and swept in four hundred lines of unrelated prose. *An
        #: over-inclusive delimiter does not lose findings, it manufactures them* -- and a
        #: manufactured one arrives with a list of identifiers attached, which reads as evidence.
        #: The second draft ended at the next column-0 BULLET, which is most of the way there and
        #: still wrong: a band's closing paragraph is not a bullet.
        for j in range(i + 1, end):
            if lines[j].strip() and not lines[j][0].isspace():
                end = j
                break
        m = head.match(lines[i])
        is_open = ("✅" not in m.group(1)) if kind == "roadmap" else ("CLOSED" not in lines[i])
        out.append((m.group(2), is_open, "\n".join(lines[i:end])))
    return out


def stale(text: str, kind: str, status_by_fn: dict[str, str]) -> list[tuple[str, list[str]]]:
    """In-scope records marked OPEN that name no open sweep site."""
    return [(code, named)
            for code, is_open, body in records(text, kind) if is_open
            for how, named in [verdict(body, status_by_fn)] if how == NO_OPEN]


def at(rev: str, path: str) -> str:
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        die(f"cannot read {path} at {rev}: {r.stderr.strip()}")
    return r.stdout


ROADMAP = ROOT / "docs" / "roadmap.md"
THREAT = ROOT / "docs" / "security" / "threat-model.md"

# ------------------------------------------------------------------------------------------- run it

STATUS_BY_FN = ledger_status_by_function((HERE / OWNER_GATE).read_text(encoding="utf-8"))

check("the sweep ledgers parsed and yielded subjects — else every check below is about an empty set",
      len(STATUS_BY_FN) >= 25,
      f"{len(STATUS_BY_FN)} functions; "
      f"{sum(1 for s in STATUS_BY_FN.values() if s == 'OPEN')} carry an open attribute")

# --- self-tests on the verdict function, mutated directly ---------------------------------------
_SYNTH = {"place_family": "LOCKED", "share_scenario": "LOCKED", "widget_save": "OPEN"}
_CITE = f"frozen in `services/api/{OWNER_GATE}`. "

check("SELF-TEST: an in-scope record naming an OPEN site is NOT stale — the contrast citation is "
      "why the rule is 'names an open site' and not 'names no closed one'",
      verdict(_CITE + "wraps `place_family`, unlike `widget_save`", _SYNTH)[0] == HAS_OPEN,
      str(verdict(_CITE + "wraps `place_family`, unlike `widget_save`", _SYNTH)))
check("SELF-TEST: ...and one naming only CLOSED sites IS stale",
      verdict(_CITE + "`place_family` and `share_scenario` still lose a write", _SYNTH)[0]
      == NO_OPEN)
check("SELF-TEST: ...and one naming NO site at all is stale too — G-10 named its subjects only as "
      "columns, and a record citing the gate with nothing open left is stale either way",
      verdict(_CITE + "`Scenario.shared_with` still loses a grant", _SYNTH)[0] == NO_OPEN)
check("SELF-TEST: a record that does NOT cite the gate is out of scope however many sites it names "
      "— this clause is what stops an item about `client.ts` being called a concurrency gap for "
      "mentioning one backend helper",
      verdict("`place_family` and `share_scenario` in passing", _SYNTH)[0] == OUT_OF_SCOPE)
check("SELF-TEST: an UNBACKTICKED mention does not count — 'place family' and 'an edit' are "
      "ordinary English in these documents",
      verdict(_CITE + "two people place family content at once", _SYNTH)[1] == [])
check("SELF-TEST: a DOTTED, SLASHED or CALLED form does count — the documents write "
      "`routers/proforma.share_scenario` and `place_family(...)` as often as the bare name",
      verdict(_CITE + "`routers/x.share_scenario` and `place_family(db, pid)`", _SYNTH)[1]
      == ["place_family", "share_scenario"])
check("SELF-TEST: a PREFIX of a backticked span does not count — `edit-mep` is a recipe category, "
      "not the route `edit`",
      verdict(_CITE + "the `edit-mep` group", {"edit": "LOCKED"})[1] == [])

# --- the replay: the shipped stale records must come back ----------------------------------------
_pre_roadmap = stale(at(PRE_FIX, "docs/roadmap.md"), "roadmap", STATUS_BY_FN)
_pre_tm = stale(at(PRE_FIX, "docs/security/threat-model.md"), "threat-model", STATUS_BY_FN)
_pre = {c for c, _ in _pre_roadmap} | {c for c, _ in _pre_tm}

check(f"REPLAY at {PRE_FIX}: the analyser re-finds RMW-LOCKGAP and RMW-TOKEN in the roadmap as "
      "shipped — without this, every clean report below is a claim about an analyser that has "
      "never been shown to find anything",
      {"RMW-LOCKGAP", "RMW-TOKEN"} <= _pre, f"roadmap: {_pre_roadmap}")
check(f"REPLAY at {PRE_FIX}: ...and BOTH threat-model gaps, found through a second document and a "
      "different record shape, so the delimiter is not tuned to one file",
      {"G-10", "G-12"} <= _pre, f"threat-model: {_pre_tm}")
check(f"REPLAY at {PRE_FIX}: ...and nothing else. A replay that also swept in unrelated records "
      "would prove the analyser fires, not that it fires on the right thing",
      _pre == {"RMW-LOCKGAP", "RMW-TOKEN", "G-10", "G-12"}, f"found: {sorted(_pre)}")

# --- the live tree ------------------------------------------------------------------------------
_road = stale(ROADMAP.read_text(encoding="utf-8"), "roadmap", STATUS_BY_FN)
_tm = stale(THREAT.read_text(encoding="utf-8"), "threat-model", STATUS_BY_FN)
_n_road = len(records(ROADMAP.read_text(encoding="utf-8"), "roadmap"))
_n_tm = len(records(THREAT.read_text(encoding="utf-8"), "threat-model"))

check("no roadmap item cites the sweep, reads as open, and has no open site left to be about",
      not _road, f"stale: {_road}" if _road else f"{_n_road} items examined")
check("no threat-model gap cites the sweep, reads as open, and has no open site left to be about",
      not _tm, f"stale: {_tm}" if _tm else f"{_n_tm} gaps examined")

print(f"GAP-RECORDS OK — {len(STATUS_BY_FN)} ledger subjects across {_n_road} roadmap items and "
      f"{_n_tm} threat-model gaps; no open record has run out of subject. Proved by replaying "
      f"{PRE_FIX}, where all four shipped stale records come back and nothing else does."
      if not FAILED else f"test_gap_records: {len(FAILED)} FAILED — {FAILED}")
sys.exit(1 if FAILED else 0)
