"""TRUNC-DISCLOSE — a capped window that reports its slice as the whole.

Axis B of the LIMIT-FILTER sweep. Axis A was a cap applied before a predicate, which returns an
EMPTY answer. This is the milder sibling and a different defect: the predicate is right, the rows
are right, and the COUNT beside them describes the window while being named for the population.
Nobody can tell from the response that there is more.

**The repository already argues against this, in the file that does it.** `pins.resolve_pins` ends
`return out[:_MAX_PINS]` directly beneath a docstring reading *"Silence is the failure mode; an
unplaced pin that says so is not"*, and `pins.located` adds *"a sheet that draws 4 of 7 pins and
says nothing is the bug"*. The principle was written above the line that breaks it — which is why
this is a derived sweep rather than a reading exercise.

**The three fixed here, and why each cap survives:**

  * `equipment.schedule` — an RFQ line-item schedule capped at `_MAX_LINES`. `line_count` was the
    capped figure and `unit_count` summed only the surviving lines, so a large model produced a
    procurement document that was short in both the item list AND the quantity, in the direction
    that under-buys. Now carries `line_total` / `unit_total` / `truncated`.
  * `topic_lifecycle.timeline` — `event_count` was computed AFTER the 500-event cap. The dropped
    events are the OLDEST, which is where a decision's origin lives.
  * `routers/standards.py::load_timings` — `loads` was the capped row count, and every percentile
    beside it was computed from the newest 20,000 while being labelled as the period's.

The caps stay. A schedule is a document, not a dump, and the percentile computation is bounded in
memory on purpose. **What changes is that the cap can be seen** — which is the whole of this axis.

**The analyser's three false positives each came from a DIFFERENT flaw, and all three are kept
below as probes it must stay silent on.** They are the argument for reading every site rather than
trusting a count:

  1. `parcel_geometry.analyze` — `ring[:-1]` strips a polygon's closing point. A negative constant
     upper bound is NORMALISATION, not a cap.
  2. `provenance_report._leg_answers` — `[:120]` truncates a STRING inside a comprehension. Walking
     the whole assigned expression attributed an inner slice to the outer name.
  3. `layout_options.optioneer` — already discloses, as `count` / `shown`. The disclosure
     vocabulary was too narrow, so a correct site was reported as a defect.

All three over-report, which is the safe direction and why reading caught them. **The one flaw that
did NOT over-report is the one worth remembering**: the first predicate matched only `x[:N]` and
therefore missed `x[-N:]` — the keep-newest spelling — silently dropping `topic_lifecycle.timeline`,
a site already known to be real. *A narrowing hides exactly what it excludes.*

Run: PYTHONPATH=src:../data/src ./.venv/bin/python test_truncation_disclosed.py
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys
import textwrap

os.environ["DATABASE_URL"] = "sqlite:///./test_truncation_disclosed.db"
os.environ["STORAGE_DIR"] = "./test_storage_truncation_disclosed"
for _f in ("./test_truncation_disclosed.db",):
    if os.path.exists(_f):
        os.remove(_f)

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILED.append(f"{label}{(' — ' + detail) if detail else ''}")


# --------------------------------------------------------------------------------------------
# The analyser: a name bound to a CAPPED collection whose length is then reported as a dict value,
# in a function that discloses nothing about the cap.
# --------------------------------------------------------------------------------------------
DISCLOSE = ("truncated", "total", "has_more", "next_cursor", "capped", "complete", "shown",
            "count_all", "omitted", "remaining")


def _capped_names(fn: ast.AST) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in ast.walk(fn):
        if not isinstance(n, ast.Assign) or len(n.targets) != 1:
            continue
        tgt = n.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        # FLAW 2: a slice inside a comprehension truncates the ELEMENT, not the collection —
        # `str(x)[:120]` in a list comprehension caps no list. Walking the whole assigned
        # expression attributed it to the outer name. Comprehension bodies are excluded whole.
        inside_comp: set[int] = set()
        for c in ast.walk(n.value):
            if isinstance(c, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                for d in ast.walk(c):
                    inside_comp.add(id(d))
                inside_comp.discard(id(c))
        for sub in ast.walk(n.value):
            if id(sub) in inside_comp:
                continue
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr == "limit":
                out[tgt.id] = "limit()"
            if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Slice):
                sl = sub.slice
                if sl.step is not None:
                    continue
                # FLAW 1: `x[:-1]` is normalisation (strip a polygon's closing point), not a cap.
                neg = isinstance(sl.upper, ast.UnaryOp) and isinstance(sl.upper.op, ast.USub)
                # FLAW 2: a slice on an INNER expression is not a cap on the outer name — a
                # `str(...)[:120]` inside a comprehension does not truncate the list.
                if sl.upper is not None and sl.lower is None and not neg:
                    out.setdefault(tgt.id, "[:N]")
                # Both spellings drop elements. Matching only the first missed a KNOWN site.
                elif sl.lower is not None and sl.upper is None:
                    out.setdefault(tgt.id, "[-N:]")
    return out


def _counted_names(fn: ast.AST) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in ast.walk(fn):
        if not isinstance(n, ast.Dict):
            continue
        for k, v in zip(n.keys, n.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "len" \
                    and len(v.args) == 1 and isinstance(v.args[0], ast.Name):
                out[v.args[0].id] = k.value
    return out


def _discloses(fn: ast.AST) -> list[str]:
    keys: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            for k in n.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return sorted(k for k in keys if any(d in k for d in DISCLOSE))


def undisclosed(source: str) -> list[tuple[str, str, str]]:
    """(function, capped-name, count-key) for every capped-and-counted site saying nothing."""
    out = []
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _discloses(fn):
            continue
        capped, counted = _capped_names(fn), _counted_names(fn)
        for name in capped:
            if name in counted:
                out.append((fn.name, name, counted[name]))
    return out


# --------------------------------------------------------------------------------------------
# Both directions, before believing anything it says about the tree.
# --------------------------------------------------------------------------------------------
_MUST_REPORT = {
    "pre-fix timeline (keep-newest cap)": '''
        def timeline(db, topic):
            events = assemble(db, topic)
            if len(events) > CAP:
                events = events[-CAP:]
            return {"events": events, "event_count": len(events), "status": topic.status}
    ''',
    "pre-fix equipment schedule (keep-first cap)": '''
        def schedule(model):
            lines = sorted(groups.values(), key=rank)[:MAX_LINES]
            return {"line_count": len(lines), "lines": lines, "note": "RFQ"}
    ''',
    "pre-fix load_timings (SQL cap)": '''
        def load_timings(pid, days, db):
            rows = db.scalars(select(T).where(T.project_id == pid).limit(20_000)).all()
            return {"days": days, "loads": len(rows), "buckets": bucketed(rows)}
    ''',
}

_MUST_STAY_SILENT = {
    # FLAW 1 — a negative upper bound removes a closing point; the count is the true vertex count.
    "polygon ring normalisation": '''
        def analyze(geojson):
            ring = parse_boundary(geojson)
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            return {"vertices": len(ring), "area_m2": area(ring)}
    ''',
    # FLAW 2 — the slice truncates a STRING inside the comprehension, not the list.
    "string truncation inside a comprehension": '''
        def _leg_answers(answers):
            uncited = [str(a.get("text") or "answer")[:120]
                       for a in answers if not a.get("citations")]
            return {"leg": "answers", "uncited_count": len(uncited)}
    ''',
    # FLAW 3 — it already discloses, using a vocabulary the first draft did not recognise.
    "discloses as count/shown rather than total/truncated": '''
        def optioneer(base, limit=24):
            ranked = scenarios[: max(1, limit)]
            return {"scenarios": ranked, "count": len(scenarios), "shown": len(ranked)}
    ''',
    # A cap with no count reported at all is a different shape (the CALLER cannot tell), and
    # deliberately out of scope here rather than silently folded in.
    "capped return with no count": '''
        def resolve_pins(db, pid):
            out = gather(db, pid)
            return out[:MAX_PINS]
    ''',
}

for name, src in _MUST_REPORT.items():
    check(f"reports the authoring shape: {name}", bool(undisclosed(textwrap.dedent(src))),
          "silent — an analyser that cannot find a known defect only ever reports good news")
for name, src in _MUST_STAY_SILENT.items():
    got = undisclosed(textwrap.dedent(src))
    check(f"stays silent on the near-miss: {name}", not got, f"reported {got!r}")

# The keep-newest spelling specifically, because dropping it is the one flaw that UNDER-reported.
check("the `x[-N:]` cap spelling is matched, not just `x[:N]`",
      bool(undisclosed(textwrap.dedent(_MUST_REPORT["pre-fix timeline (keep-newest cap)"]))),
      "matching only `[:N]` silently drops every keep-newest cap in the tree")

# --------------------------------------------------------------------------------------------
# The tree. Fails closed: an unclassified site reds the build.
# --------------------------------------------------------------------------------------------
EXEMPT: dict[tuple[str, str], str] = {
    # NOT truncation. `analyze` normalises a polygon ring twice, and both spellings look like a
    # cap to a syntactic analyser: `ring = ring[:-1]` strips the closing point (GeoJSON repeats
    # the first vertex as the last), and `... or ring[:1]` is the degenerate fallback for a ring
    # that dedupes to nothing. `vertices` is the true vertex count in both cases.
    #
    # Exempted rather than taught to the analyser on purpose. Recognising "a slice that keeps
    # everything but one" and "a one-element fallback after an `or`" means teaching the predicate
    # which slices are *meant* as caps, and a predicate that decides what to LOOK at hides
    # everything it excludes from its own output. A written exemption is visible; a cleverer
    # predicate is not.
    ("parcel_geometry.py", "analyze"): "polygon-ring normalisation, not a cap",
}

ROOT = pathlib.Path(__file__).resolve().parent / "src" / "aec_api"
found: set[tuple[str, str]] = set()
scanned = 0
for path in sorted(ROOT.rglob("*.py")):
    rel = path.relative_to(ROOT).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        FAILED.append(f"could not read {rel}: {exc}")
        continue
    try:
        hits = undisclosed(text)
    except SyntaxError as exc:            # a file we cannot parse is not a pass
        FAILED.append(f"could not parse {rel}: {exc}")
        continue
    scanned += 1
    for fn, _name, _key in hits:
        found.add((rel, fn))

check("the analyser actually reached the tree", scanned >= 100,
      f"parsed only {scanned} files under {ROOT} — a sweep with an empty population passes for "
      f"the same reason a correct one does")
check("every capped-and-counted site discloses its cap", not (found - set(EXEMPT)),
      f"undisclosed: {sorted(found - set(EXEMPT))} — each reports the size of its window under a "
      f"name that reads like the population. Add `<thing>_total` and `truncated` beside the count, "
      f"or record an exemption here with the reason")

# --------------------------------------------------------------------------------------------
# Behaviour. The structural gate cannot tell whether the numbers are RIGHT.
# --------------------------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402

from aec_api import equipment, topic_lifecycle  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import AuditLog, Comment, Topic  # noqa: E402

Base.metadata.create_all(bind=engine)
NOW = datetime.now(timezone.utc)

# --- equipment.schedule: the cap is lowered rather than 4,000 groups built, because the assertion
# is about the ARITHMETIC of the disclosure, not about the constant's value.
_real_cap = equipment._MAX_LINES
try:
    equipment._MAX_LINES = 3

    class _Unit:
        """A minimal element the schedule can group: distinct type per unit forces distinct lines."""

        def __init__(self, i: int) -> None:
            self.GlobalId, self._i = f"guid-{i}", i

        def is_a(self, *a: object) -> bool:
            return True

    class _Model:
        def __init__(self, n: int) -> None:
            self._n = n

        def by_type(self, t: str) -> list[_Unit]:
            return [_Unit(i) for i in range(self._n)] if t == "IfcProduct" else []

    got = equipment.schedule(_Model(10))
    if "line_total" not in got:
        FAILED.append(f"equipment.schedule lost its disclosure keys: {sorted(got)}")
    else:
        check("equipment.schedule: the RFQ says how many lines it is not showing",
              got["line_count"] <= got["line_total"], f"{got['line_count']} of {got['line_total']}")
        check("equipment.schedule: `truncated` agrees with the two counts",
              got["truncated"] == (got["line_total"] > got["line_count"]),
              f"truncated={got['truncated']} on {got['line_count']}/{got['line_total']}")
        check("equipment.schedule: the QUANTITY total is over every line, not the shown ones",
              got["unit_total"] >= got["unit_count"],
              f"unit_count={got['unit_count']} unit_total={got['unit_total']} — a short quantity on "
              f"a procurement document under-buys, which the old code did silently")
finally:
    equipment._MAX_LINES = _real_cap

# --- topic_lifecycle.timeline: real rows, past the real cap.
with SessionLocal() as db:
    db.query(AuditLog).delete()
    db.query(Comment).delete()
    db.query(Topic).delete()
    topic = Topic(id="t-trunc", project_id="p1", guid="G-trunc", type="issue",
                  title="Long-running", status="open")
    db.add(topic)
    over = topic_lifecycle._TIMELINE_CAP + 120
    for i in range(over):
        db.add(AuditLog(action="topic.update", actor="bob", topic_id=topic.id,
                        ts=NOW - timedelta(minutes=over - i), detail={"status": f"s{i}"}))
    db.commit()

    tl = topic_lifecycle.timeline(db, topic)
    check("timeline: `event_count` is the window and `event_total` the history",
          tl.get("event_total", 0) > tl["event_count"],
          f"count={tl['event_count']} total={tl.get('event_total')} — these were the same name for "
          f"two different numbers, and the dropped events are the OLDEST")
    check("timeline: it says it truncated", tl.get("truncated") is True, repr(tl.get("truncated")))
    check("timeline: the window is really capped", tl["event_count"] <= topic_lifecycle._TIMELINE_CAP,
          f"{tl['event_count']} > {topic_lifecycle._TIMELINE_CAP}")

    # And the honest negative: a short topic must NOT claim truncation.
    db.query(AuditLog).delete()
    db.add(AuditLog(action="topic.create", actor="ann", topic_id=topic.id, ts=NOW,
                    detail={"type": "issue", "title": "Long-running"}))
    db.commit()
    short = topic_lifecycle.timeline(db, topic)
    check("timeline: a short history does not claim to be truncated",
          short.get("truncated") is False and short["event_count"] == short.get("event_total"),
          f"count={short['event_count']} total={short.get('event_total')} "
          f"truncated={short.get('truncated')} — a flag that is always on says nothing")

# --- load_timings: the one whose cap is 20,000, so the arithmetic is asserted against a lowered
# window rather than by inserting twenty thousand rows. The route reads `limit(20_000)` inline, so
# what is checked here is the CONTRACT — that `loads`, `load_total` and `truncated` agree — plus the
# honest negative. Only the structural gate above knew about this site until now.
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.models import ViewerLoadTiming  # noqa: E402

with TestClient(app) as client:
    pid = client.post("/projects", headers={"X-User": "gc"},
                      json={"name": "Timings"}).json()["id"]
    with SessionLocal() as db:
        for i in range(7):
            db.add(ViewerLoadTiming(project_id=pid, outcome="ok", bucket="1-10MB",
                                    total_ms=100 + i, ts=NOW - timedelta(minutes=i)))
        db.commit()

    lt = client.get(f"/projects/{pid}/model/load-timings").json()
    check("load_timings: `load_total` is reported beside `loads`",
          "load_total" in lt and "truncated" in lt, f"got keys {sorted(lt)}")
    check("load_timings: an uncapped period reports the same two numbers",
          lt.get("loads") == lt.get("load_total") == 7,
          f"loads={lt.get('loads')} load_total={lt.get('load_total')} — 7 rows were written")
    check("load_timings: an uncapped period does NOT claim truncation",
          lt.get("truncated") is False,
          f"truncated={lt.get('truncated')} — a flag that is always on says nothing, which is the "
          f"opposite failure to the one this axis is about and just as useless")

if FAILED:
    print("FAIL test_truncation_disclosed")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_truncation_disclosed OK  ({scanned} files scanned, 0 undisclosed caps; analyser "
      f"probed in both directions — {len(_MUST_REPORT)} shapes it must report, "
      f"{len(_MUST_STAY_SILENT)} it must not)")
