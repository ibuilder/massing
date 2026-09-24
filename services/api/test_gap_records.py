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
is replayed against the four records AS SHIPPED at `53cfa71a`, frozen under
`services/api/tests/fixtures/gap_records/`, where it must re-find all four and nothing else.

**That fixture is a COPY, and the first draft got it wrong in a way CI caught and no local run
could.** The replay read the commit with `git show 53cfa71a:docs/roadmap.md`. Locally that works;
in CI the checkout is shallow, the object is not in the clone, and the gate failed closed on every
build with *"fatal: invalid object name"*. Failing closed was correct — an analyser that cannot read
its inputs must not report a clean tree — but *a proof-of-reach that depends on the depth of
somebody's clone is not a proof, it is a dependency on an environment nobody here controls*, and the
same break would hit any contributor's shallow clone. Every neighbouring gate in this tree embeds
its pre-fix subject rather than fetching it (`test_seeding_sweep` runs against the shipped pre-fix
SAML door; `test_system_columns` reinstates the pre-fix `_system_field`); reaching into history was
the novel choice and the worse one.
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent

#: The commit the frozen fixtures were taken from -- named so a reader can diff them against
#: history where history is available, never read by this file.
PRE_FIX = "53cfa71a"
#: The four stale records as they shipped, copied rather than fetched -- see the docstring.
FIXTURES = pathlib.Path(__file__).resolve().parent / "tests" / "fixtures" / "gap_records"

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

#: The status markers a roadmap heading may carry. `⛔` (closed unbuilt), `❌` (considered and
#: rejected) and a `~~struck~~` code are as closed as `✅`; `◧`, `🟡`, `⭐` and a bare heading are
#: open.
#:
#: **`⛔`, `❌` and `~~` were all missing until the parity check below was written, and they were not
#: a cosmetic omission: the population was 78 items and is 90.** Twelve were invisible -- None of them
#: needed flagging -- every one is closed or withdrawn -- so nothing was wrong today, and nothing
#: would have said so tomorrow either. *A population smaller than it looks reports a clean tree in
#: exactly the same words as a clean tree.* Raised in review on PR #577, which asked what happens
#: when a heading leaves the parsed set; the answer was that twelve already had. **The parity
#: check found `❌` on its own first run**, after `⛔` and `~~` had been added by hand from the
#: same measurement -- *a hand-widened list is a list somebody stopped widening.*
_MARKERS = "✅◧🟡⭐⛔❌"
_CLOSED = "✅⛔❌"
_ROADMAP_HEAD = re.compile(rf"^[-*] ((?:(?:[{_MARKERS}])️? )*(?:~~)?)\*\*([A-Z][A-Z0-9-]{{2,}})\b")
#: A threat-model gap: a numbered entry bolding a G-number.
_TM_HEAD = re.compile(r"^(\d+)\. \*\*(G-\d+)\b")

#: The same two shapes read LOOSELY -- any non-letter prefix, any numbering punctuation. Nothing is
#: parsed with these; they exist so that a heading the strict regexes stop recognising is REPORTED
#: rather than quietly dropped. *A checker that narrows its own population answers a smaller
#: question and prints the same verdict.*
_LOOSE_ROADMAP = re.compile(r"^[-*] ([^A-Za-z]{0,20})\*\*~{0,2}([A-Z][A-Z0-9-]{2,})\b")
_LOOSE_TM = re.compile(r"^\s*\d+[.)]\s*\*{0,2}~{0,2}(G-\d+)\b")


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
        pre = m.group(1)
        is_open = (not any(c in pre for c in _CLOSED) and "~~" not in pre) \
            if kind == "roadmap" else ("CLOSED" not in lines[i])
        out.append((m.group(2), is_open, "\n".join(lines[i:end])))
    return out


def unparsed_headings(text: str, kind: str) -> list[str]:
    """Lines a LOOSE reading calls a heading and the strict one does not — drift, reported."""
    loose = _LOOSE_ROADMAP if kind == "roadmap" else _LOOSE_TM
    strict = _ROADMAP_HEAD if kind == "roadmap" else _TM_HEAD
    return [ln for ln in text.split("\n") if loose.match(ln) and not strict.match(ln)]


def stale(text: str, kind: str, status_by_fn: dict[str, str]) -> list[tuple[str, list[str]]]:
    """In-scope records marked OPEN that name no open sweep site."""
    return [(code, named)
            for code, is_open, body in records(text, kind) if is_open
            for how, named in [verdict(body, status_by_fn)] if how == NO_OPEN]


def fixture(name: str) -> str:
    """One frozen pre-fix document. Fails closed if it is missing or has been emptied."""
    p = FIXTURES / name
    if not p.is_file():
        die(f"the frozen fixture {p} is missing — the replay below is what proves this analyser "
            f"finds anything, so its absence is not a reason to report a clean tree")
    text = p.read_text(encoding="utf-8")
    if len(text) < 500:
        die(f"the frozen fixture {p} is {len(text)} bytes — too small to hold the four records it "
            f"must, so the replay would pass by having nothing to find")
    return text


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
#: **The replay reads FROZEN statuses, not today's.** The fixtures are historical; the ledger is
#: not. Evaluating one against the other means that the day `place_family` legitimately reopens --
#: and the live RMW-LOCKGAP record correctly reopens with it -- the FROZEN record would name an open
#: site, the replay would stop finding its four, and the build would red with a message blaming the
#: analyser for something the analyser got right. *A replay is a claim about a moment; feeding it a
#: moving input makes it a claim about nothing.* Raised in review on PR #577.
#:
#: Derived rather than listed: at the moment these records were stale the sweep reported `0 named
#: open`, so "every site this sweep knows about is closed" IS the world they were stale against.
#: Taking the names from the live ledger and the statuses from that fact cannot drift into naming a
#: function nobody has, and cannot drift in status at all.
REPLAY_STATUS = dict.fromkeys(STATUS_BY_FN, "LOCKED")

_pre_roadmap = stale(fixture("roadmap.md"), "roadmap", REPLAY_STATUS)
_pre_tm = stale(fixture("threat-model.md"), "threat-model", REPLAY_STATUS)
_pre = {c for c, _ in _pre_roadmap} | {c for c, _ in _pre_tm}

check(f"REPLAY of the {PRE_FIX} records: the analyser re-finds RMW-LOCKGAP and RMW-TOKEN in the roadmap as "
      "shipped — without this, every clean report below is a claim about an analyser that has "
      "never been shown to find anything",
      {"RMW-LOCKGAP", "RMW-TOKEN"} <= _pre, f"roadmap: {_pre_roadmap}")
check(f"REPLAY of the {PRE_FIX} records: ...and BOTH threat-model gaps, found through a second document and a "
      "different record shape, so the delimiter is not tuned to one file",
      {"G-10", "G-12"} <= _pre, f"threat-model: {_pre_tm}")
check(f"REPLAY of the {PRE_FIX} records: ...and nothing else. A replay that also swept in unrelated records "
      "would prove the analyser fires, not that it fires on the right thing",
      _pre == {"RMW-LOCKGAP", "RMW-TOKEN", "G-10", "G-12"}, f"found: {sorted(_pre)}")

#: Without this, `REPLAY_STATUS` could be `{}` and the replay would still find all four -- by
#: classifying every record as naming no open site, which is the same verdict for the opposite
#: reason. *A frozen input that is never read is indistinguishable from a correct one.*
_reopened = {**REPLAY_STATUS, "place_family": "OPEN"}
check("MUTATION: with one of RMW-LOCKGAP's own sites reopened in the frozen ledger, that record is "
      "NOT reported — so the replay above is reading the statuses and not merely the prose",
      "RMW-LOCKGAP" not in {c for c, _ in stale(fixture("roadmap.md"), "roadmap", _reopened)},
      "reinstating one OPEN site must remove the record from the stale set")

# --- the live tree ------------------------------------------------------------------------------
_road = stale(ROADMAP.read_text(encoding="utf-8"), "roadmap", STATUS_BY_FN)
_tm = stale(THREAT.read_text(encoding="utf-8"), "threat-model", STATUS_BY_FN)
_n_road = len(records(ROADMAP.read_text(encoding="utf-8"), "roadmap"))
_n_tm = len(records(THREAT.read_text(encoding="utf-8"), "threat-model"))

_drift_road = unparsed_headings(ROADMAP.read_text(encoding="utf-8"), "roadmap")
_drift_tm = unparsed_headings(THREAT.read_text(encoding="utf-8"), "threat-model")
check("every roadmap heading a loose reading finds, the strict one finds too — a marker this gate "
      "does not know shrinks its population without changing a word of its verdict",
      not _drift_road, f"unparsed: {_drift_road[:5]}" if _drift_road else f"{_n_road} parsed, 0 missed")
check("...and the same for the threat model's numbered gaps",
      not _drift_tm, f"unparsed: {_drift_tm[:5]}" if _drift_tm else f"{_n_tm} parsed, 0 missed")

check("no roadmap item cites the sweep, reads as open, and has no open site left to be about",
      not _road, f"stale: {_road}" if _road else f"{_n_road} items examined")
check("no threat-model gap cites the sweep, reads as open, and has no open site left to be about",
      not _tm, f"stale: {_tm}" if _tm else f"{_n_tm} gaps examined")

print(f"GAP-RECORDS OK — {len(STATUS_BY_FN)} ledger subjects across {_n_road} roadmap items and "
      f"{_n_tm} threat-model gaps; no open record has run out of subject. Proved by replaying "
      f"the frozen {PRE_FIX} records, where all four come back and nothing else does."
      if not FAILED else f"test_gap_records: {len(FAILED)} FAILED — {FAILED}")
sys.exit(1 if FAILED else 0)
