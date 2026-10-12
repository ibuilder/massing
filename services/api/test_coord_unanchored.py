"""COORD-UNANCHORED — a coordination topic with no element anchors cannot be ruled stale, and was
counted as one of the issues that did not go stale.

`coordination_fresh.stale_clashes` tests `topic.element_guids ∩ changed`, so a topic carrying **no
element GUIDs** can never be stale by construction: the intersection is empty however much of the
model moved. It was therefore folded into `open_coordination_issues` and omitted from `stale` — and
a coordinator reading *"2 of 40 open issues are stale"* concludes the other 38 are still valid. For
an unanchored one the truth is **"this check cannot say"**.

Not a hypothetical shape: BCF topics created by hand, imported from another tool, or logged against
a drawing rather than a model element routinely carry no `element_guids`, and the clash engine is
only one of the ways a `clash`/`coordination` topic is created. *A verdict whose own premise is
absent for a row has not been reached on that row.*

WHY THE EXISTING TEST COULD NOT SEE IT
--------------------------------------
`test_coordination_fresh.py` builds three open clash topics and **every one of them carries element
GUIDs**, so the unanchored branch never executes and the change is invisible to it. The pre-fix
engine is replayed below on an unanchored topic and must report it as a non-stale open issue before
this gate may report anything.

THE OTHER HALF: A DIFF THAT FOUND NOTHING
-----------------------------------------
When `changed_elements` is 0 — identical versions, or a fingerprint set missing so `versions.diff`
has nothing to compare — every assessable topic is trivially not stale and a "0 stale" answer says
nothing about any of them. `comparable` is false there too, for the same reason `soft_clash` keeps
`untested` out of `clean`.

Run: cd services/api && PYTHONPATH=src ./.venv/bin/python test_coord_unanchored.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_coord_unanchored.db"
os.environ["STORAGE_DIR"] = "./test_storage_coord_unanchored"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_coord_unanchored.db"):
    os.remove("./test_coord_unanchored.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import ModelVersion, Topic  # noqa: E402

FAILED: list[str] = []


def ok(cond, label):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILED.append(label)


def _fp(name, cls, ph):
    return [name, cls, "T", "L1", ph, "q"]


# ── THE PRE-FIX ENGINE, so the defect is replayed rather than described ───────────────────────────
def stale_shipped(db, pid, a, b):
    """`stale_clashes` as it shipped: no unanchored split, no `comparable`."""
    from aec_api import versions
    from aec_api.coordination_fresh import _CLASH_TYPES, _changed_guids
    diff = versions.diff(db, pid, a, b)
    changed = _changed_guids(diff)
    rows = (db.query(Topic)
            .filter(Topic.project_id == pid, Topic.type.in_(_CLASH_TYPES), Topic.status == "open")
            .all())
    stale = [t for t in rows if set(t.element_guids or []) & changed]
    return {"changed_elements": len(changed), "open_coordination_issues": len(rows),
            "stale_count": len(stale)}


with TestClient(app) as c:
    def project(name, versions_spec):
        pid = c.post("/projects", json={"name": name}).json()["id"]
        with SessionLocal() as db:
            for ver, (guids, fps) in versions_spec.items():
                db.add(ModelVersion(project_id=pid, version=ver, element_count=len(guids),
                                    guids=guids, fingerprints=fps, note=f"v{ver}"))
            db.commit()
        return pid

    def topic(pid, guids, title, ttype="clash", status="open"):
        r = c.post(f"/projects/{pid}/topics", json={
            "type": ttype, "status": status, "title": title, "element_guids": guids})
        assert r.status_code == 201, (ttype, r.status_code, r.text[:200])
        return r.json()

    def bcf_topic(pid, title, topic_type):
        """A topic through the BCF door, which is the ONLY way a `coordination` type exists.

        Found while writing this file: `schemas.TopicType` is
        `Literal["rfi", "punch", "clash", "info"]`, so `POST /projects/{pid}/topics` 422s on
        `coordination` — and `coordination_fresh._CLASH_TYPES` is `("clash", "coordination")`. The
        second half of the engine's declared population is unreachable through the typed route.
        It is NOT dead, though, and the difference matters: `bcf_api`'s importer resolves
        `inv_type.get(topic_type, topic_type.lower())`, and `_TYPE` has no "Coordination", so a BCF
        file carrying that `topic_type` falls through to the literal string. *The engine's filter is
        right about where its rows come from — another tool's export — and the typed door simply
        cannot express it.* Asserted below in both directions so neither drifts silently.
        """
        r = c.post(f"/bcf/3.0/projects/{pid}/topics",
                   json={"title": title, "topic_type": topic_type, "topic_status": "Open"})
        assert r.status_code in (200, 201), (topic_type, r.status_code, r.text[:200])
        return r.json()

    def stale(pid, a=1, b=2):
        r = c.get(f"/projects/{pid}/coordination/stale?a={a}&b={b}")
        assert r.status_code == 200, r.text[:200]
        return r.json()

    # v1 {g1,g2}; v2 modifies g1 and leaves g2 alone.
    SPEC = {
        1: (["g1", "g2"], {"g1": _fp("W1", "IfcWall", "h1"), "g2": _fp("W2", "IfcWall", "h2")}),
        2: (["g1", "g2"], {"g1": _fp("W1", "IfcWall", "h1-CHANGED"),
                           "g2": _fp("W2", "IfcWall", "h2")}),
    }

    # ── ① THE SHIPPED DEFECT: an unanchored topic read as an issue that did not go stale ──────────
    print("\n-- one anchored topic that went stale, one with no anchors at all --")
    p1 = project("Unanchored", SPEC)
    topic(p1, ["g1"], "Duct vs beam @g1")                  # anchored, and g1 moved -> stale
    topic(p1, [], "Clash noted on sheet A-201")            # NO anchors -> cannot be ruled on
    st = stale(p1)
    with SessionLocal() as db:
        shipped = stale_shipped(db, p1, 1, 2)
    # PROOF OF REACH — the pre-fix engine must show the unanchored topic inside the open count and
    # outside the stale count, which is the arithmetic a reader subtracts.
    ok(shipped == {"changed_elements": 1, "open_coordination_issues": 2, "stale_count": 1},
       f"PROOF OF REACH: the pre-fix engine reports 1 of 2 stale — so the unanchored topic reads "
       f"as one that did NOT go stale   {shipped}")
    ok(st["stale_count"] == 1 and st["open_coordination_issues"] == 2,
       f"the fixed engine keeps both numbers   stale={st['stale_count']} "
       f"open={st['open_coordination_issues']}")
    ok(st["assessable"] == 1 and st["unanchored"] == 1,
       f"...and SPLITS the open count   assessable={st['assessable']} "
       f"unanchored={st['unanchored']}")
    ok([t["title"] for t in st["unanchored_topics"]] == ["Clash noted on sheet A-201"],
       f"...naming the topic it could not rule on, so a screen can offer to anchor it   "
       f"{[t['title'] for t in st['unanchored_topics']]}")
    ok(st["assessable"] + st["unanchored"] == st["open_coordination_issues"],
       "the two parts sum to the open count — pinned so a later field cannot drift out of it")
    ok(st["comparable"] is True,
       "it IS comparable: something changed and something could be assessed")
    ok("cannot be ruled on by this check" in st["note"] and "1 of 2 open" in st["note"],
       "and the note says so in words, with the counts")

    # ── ② EVERY OPEN TOPIC UNANCHORED: `0 stale` is not a clean bill ──────────────────────────────
    print("\n-- nothing to rule on at all --")
    p2 = project("All unanchored", SPEC)
    topic(p2, [], "Clash from the consultant's PDF")
    bcf_topic(p2, "Coordination note, no model link", "Coordination")
    st2 = stale(p2)
    with SessionLocal() as db:
        shipped2 = stale_shipped(db, p2, 1, 2)
    ok(shipped2["stale_count"] == 0 and shipped2["open_coordination_issues"] == 2,
       f"PROOF OF REACH: the pre-fix engine reports 0 of 2 stale, i.e. a clean bill   {shipped2}")
    ok(st2["assessable"] == 0 and st2["unanchored"] == 2,
       f"the fixed engine says it assessed NOTHING   assessable={st2['assessable']}")
    ok(st2["comparable"] is False,
       "...and `comparable` is False, so no consumer can read 0 stale as 0 problems")
    ok("ruled on nothing" in st2["note"],
       "...with the reason in the note")
    ok(st2["changed_elements"] == 1,
       f"the model DID change, which is what makes this case distinct from ③   "
       f"changed={st2['changed_elements']}")

    # ── THE TWO DOORS DISAGREE ABOUT WHAT A TOPIC TYPE MAY BE ─────────────────────────
    #
    # Pinned because the engine's population depends on it and neither side knows about the other.
    print("\n-- `coordination` exists through the BCF importer and nowhere else --")
    p_doors = project("Doors", SPEC)
    typed = c.post(f"/projects/{p_doors}/topics",
                   json={"type": "coordination", "status": "open", "title": "x",
                         "element_guids": []})
    ok(typed.status_code == 422,
       f"the typed route REFUSES `coordination` — schemas.TopicType has four literals and this is "
       f"not one   {typed.status_code}")
    # `or True` was in the first draft of this line, which made it unfalsifiable — the exact shape
    # this session keeps flagging. The acceptance is already asserted inside `bcf_topic` (it demands
    # 2xx), so what is left to assert here is the FALL-THROUGH: `_TYPE` has no "Coordination", which
    # is the only reason the literal survives into the column.
    from aec_api.routers.bcf_api import _TYPE
    ok("Coordination" not in set(_TYPE.values()),
       f"the BCF type map has no Coordination, so the importer falls through to the literal   "
       f"{sorted(set(_TYPE.values()))}")
    bcf_topic(p_doors, "From another tool", "Coordination")
    with SessionLocal() as db:
        from aec_api.models import Topic as _T
        kinds = {t.type for t in db.query(_T).filter(_T.project_id == p_doors).all()}
    ok("coordination" in kinds,
       f"...and it lands in the column as `coordination`, which is what the engine filters on   "
       f"{sorted(kinds)}")
    from aec_api.coordination_fresh import _CLASH_TYPES
    ok(set(_CLASH_TYPES) == {"clash", "coordination"},
       f"the engine's population is exactly those two   {_CLASH_TYPES}")
    from aec_api.schemas import TopicType
    import typing
    ok("coordination" not in typing.get_args(TopicType),
       "and the typed route's enum does not contain it, so this is a REAL asymmetry and not a "
       "missing validator — recorded rather than 'fixed' by widening either side, because which "
       "types the authoring API should offer is a product decision")

    # ── ③ A DIFF THAT FOUND NOTHING is its own state, not a clean one ─────────────────────────────
    print("\n-- identical versions: 0 stale says nothing --")
    p3 = project("No change", {
        1: (["g1"], {"g1": _fp("W1", "IfcWall", "h1")}),
        2: (["g1"], {"g1": _fp("W1", "IfcWall", "h1")}),
    })
    topic(p3, ["g1"], "Duct vs beam @g1")
    st3 = stale(p3)
    ok(st3["changed_elements"] == 0 and st3["assessable"] == 1,
       f"an assessable topic, and nothing changed   changed={st3['changed_elements']} "
       f"assessable={st3['assessable']}")
    ok(st3["stale_count"] == 0 and st3["comparable"] is False,
       "0 stale, and NOT comparable — the two reasons for a zero are kept apart")
    ok("No element changed between these versions" in st3["note"],
       "...and the note gives this reason rather than the other one")

    # ── ④ THE ORDINARY CASE still reads as a clean, comparable result ─────────────────────────────
    print("\n-- every topic anchored, one of them stale --")
    p4 = project("Anchored", SPEC)
    topic(p4, ["g2"], "Rebar clash @g2")                   # g2 unchanged -> genuinely not stale
    st4 = stale(p4)
    ok(st4["assessable"] == 1 and st4["unanchored"] == 0,
       f"nothing unanchored   assessable={st4['assessable']} unanchored={st4['unanchored']}")
    ok(st4["stale_count"] == 0 and st4["comparable"] is True,
       "0 stale AND comparable — which is the state that genuinely means 'still valid'")
    ok("cannot be ruled on" in st4["note"] and "1 of 1 open" in st4["note"],
       "the note states the assessable count even when it is all of them, so the reader never has "
       "to infer it from an absence")

    # ── ⑤ THE WRITE still only touches what the read called stale ────────────────────────────────
    #
    # `recheck` runs the same scan and flags its `stale` list, so the split must not widen what it
    # writes to. An unanchored topic must come back with no label and no comment: the check could not
    # rule on it, and labelling it `model-changed` would assert something nobody measured.
    print("\n-- recheck flags the stale, and only the stale --")
    p5 = project("Recheck", SPEC)
    t_anchored = topic(p5, ["g1"], "Duct vs beam @g1")
    t_bare = topic(p5, [], "Clash noted on sheet A-201")
    rc = c.post(f"/projects/{p5}/coordination/stale/recheck", json={"a": 1, "b": 2})
    assert rc.status_code == 200, rc.text[:200]
    rcj = rc.json()
    ok(rcj["flagged"] == 1,
       f"one topic flagged, not two   flagged={rcj['flagged']}")
    ok(rcj["unanchored"] == 1 and rcj["assessable"] == 1,
       "the write's response carries the same split as the read, since it runs the same scan")
    tb = c.get(f"/projects/{p5}/topics/{t_bare['id']}").json()
    ok("model-changed" not in (tb["labels"] or []),
       f"the unanchored topic is NOT labelled model-changed — nothing was measured about it   "
       f"{tb['labels']}")
    cm = c.get(f"/projects/{p5}/topics/{t_bare['id']}/comments").json()
    ok(cm == [] or not any("re-verify" in x["text"] for x in cm),
       "...and gets no re-verify comment either")
    ta = c.get(f"/projects/{p5}/topics/{t_anchored['id']}").json()
    ok("model-changed" in (ta["labels"] or []) and ta["status"] == "open",
       "while the anchored stale one is labelled and still OPEN — never auto-closed")

print()
if FAILED:
    print(f"coord_unanchored: {len(FAILED)} FAILED — {FAILED}")
    raise SystemExit(1)
print("COORD-UNANCHORED OK - a coordination topic with no element GlobalIds cannot be ruled stale by "
      "a check whose whole test is `anchors INTERSECT changed`, and was counted among the open issues "
      "that did not go stale: the pre-fix engine is replayed and must report 1 of 2 (and 0 of 2) "
      "before this gate reports. The open count now SPLITS into assessable + unanchored, which are "
      "pinned to sum to it; `comparable` is false both when nothing changed and when nothing could "
      "be assessed, so the two reasons for a zero stay apart; and `recheck` writes only to the "
      "topics the read ruled stale. Also pinned, found while writing this file: the engine filters "
      "on (clash, coordination) and `schemas.TopicType` has no `coordination`, so the typed route "
      "422s on it - the type is reachable ONLY through the BCF importer, which falls through its "
      "type map to the literal string. A real asymmetry between two doors, recorded rather than "
      "'fixed' by widening either side.")
