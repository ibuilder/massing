"""CITED-ANSWER — the provenance contract: claims cite their source (GUID/record/rule/doc+revision),
deterministic coverage %, uncited-claim guard, source-conflict surfacing, provenance-as-confidence.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cited_answer.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cited_answer.db"
os.environ["STORAGE_DIR"] = "./test_storage_cited"
os.environ.pop("AEC_RBAC", None)

from aec_api import cited_answer as ca  # noqa: E402


def G(label: str) -> str:
    """A syntactically valid IFC GlobalId (22 chars of ``[0-9A-Za-z_$]``) from a readable label.

    These fixtures used to pass ``"g1"`` and ``"wallX"`` straight to `cite_ifc`. That was shorthand,
    and it stopped being harmless once `is_citation` began checking the GlobalId SHAPE and not merely
    its presence — a display name where a GlobalId belongs is exactly the unresolvable citation the
    contract now refuses, and a test that mints one cannot tell the refusal from a regression. The
    labels stay readable; only the padding is new.
    """
    return (label + "$" * 22)[:22]

# --- citation minters ------------------------------------------------------------------------------
assert ca.cite_ifc(G("guid1"), "proj", "rev3")["source_type"] == "ifc" and ca.cite_ifc(G("guid1"))["guid"] == G("guid1")
assert ca.cite_record("budget", 7)["record_ref"] == "module/budget/7"
assert ca.cite_rule("IBC-1006.2")["rule_id"] == "IBC-1006.2" and ca.cite_rule("x")["source_type"] == "rule"
assert ca.cite_doc("A-101", sheet="A-101", page=2)["sheet"] == "A-101"

# --- the identifying field must have the right SHAPE, not merely be present ------------------------
# Before this, `is_citation` asked only "is there a non-empty string here?". Measured then:
# cite_ifc("the north wall") scored 0.733 — the contract's HIGHEST tier, the same as a real GlobalId —
# and {"record_ref": "banana"} scored 0.667, the same as a real module/budget/7. A display name renders
# perfectly and cannot be opened; crediting it is the dead end R31-CITE-HIGHLIGHT fixed for documents.
assert ca.is_citation(ca.cite_ifc(G("wall"))), "a real GlobalId must still be a citation"
assert not ca.is_citation({"source_type": "ifc", "guid": "the north wall"}), "a display name is not a GlobalId"
assert ca.is_citation(ca.cite_record("budget", 7)), "a real record ref must still be a citation"
for junk in ("Budget line 7", "banana", "module/budget/", "module//7", "budget/7"):
    assert not ca.is_citation({"source_type": "record", "record_ref": junk}), junk

# The unresolvable citation must lose its CREDIT, not just its label — the score is what a reader acts on.
assert ca.provenance_confidence([{"source_type": "ifc", "guid": "the north wall"}]) == 0.0
assert ca.provenance_confidence([ca.cite_ifc(G("wall"))]) == 0.733            # positive control: real one unchanged

# POSITIVE CONTROL on the other half: `rule` and `doc` ids have no canonical shape, so they are
# checked for presence only. Without this, tightening every kind would look identical to tightening
# the two that have a knowable format.
assert ca.is_citation(ca.cite_rule("readiness/spec")) and ca.is_citation(ca.cite_rule("anything at all"))
assert ca.is_citation(ca.cite_doc("A-101")) and ca.is_citation(ca.cite_doc("any document name"))
# ...and presence is still required, so "no shape rule" has not become "no rule".
assert not ca.is_citation({"source_type": "rule", "rule_id": "  "})
assert not ca.is_citation({"source_type": "doc", "document_id": ""})

# An UNHASHABLE source_type must be rejected, not raise. `_IDENTIFIES`/`_SHAPES` are dict lookups, so
# a list/dict/set here raised `TypeError: unhashable type` while every other malformed shape returned
# False — and `Assumptions.sources` is typed `dict[str, list[dict]]`, so a client can post exactly
# that and take out the whole scoring call. Pre-dates the shape rule; found in review of it.
for weird in ([ "ifc" ], {"k": 1}, {"ifc"}, 7, None, object()):
    assert ca.is_citation({"source_type": weird, "guid": "x"}) is False, repr(weird)
assert ca.provenance_confidence([{"source_type": ["ifc"], "guid": "x"}]) == 0.0
# positive control: the guard must not swallow well-formed citations on the same path
assert ca.provenance_confidence([ca.cite_ifc(G("wall"))]) == 0.733

# The shape map must be CONSULTED, not merely defined — a rule nothing reads is the defect this fixes.
assert set(ca._SHAPES) == {"ifc", "record"}, ca._SHAPES
assert ca._SHAPES["ifc"] is not ca._SHAPES["record"], "one regex serving both kinds would not be a per-kind check"

# --- provenance-as-confidence (deterministic, no model number) -------------------------------------
assert ca.provenance_confidence([]) == 0.0
one = ca.provenance_confidence([ca.cite_ifc(G("g"))])
assert one == 0.733, one                                   # 0.4 + 0.2·1 + 0.4·(1/3)
three = ca.provenance_confidence([ca.cite_ifc(G("g1")), ca.cite_ifc(G("g2")), ca.cite_ifc(G("g3"))])
assert three == 1.0, three                                  # 3 independent sources → full independence
stale = ca.provenance_confidence([ca.cite_ifc(G("g"), revision="r1")], current_revision="r2")
assert stale == round(one * 0.7, 3), stale                  # every citation on a superseded revision → penalty

# --- build: coverage + uncited guard ---------------------------------------------------------------
ok = ca.build([ca.claim("A.", [ca.cite_ifc(G("g1"))]), ca.claim("B.", [ca.cite_rule("R1")])])
assert ok["coverage"] == 1.0 and ok["fully_cited"] and not ok["uncited_claims"], ok
assert ok["answer"] == "A. B." and ok["citation_count"] == 2 and ok["source_types"] == {"ifc": 1, "rule": 1}
bad = ca.build([ca.claim("cited.", [ca.cite_ifc(G("g1"))]), ca.claim("uncited hunch.")])
assert bad["coverage"] == 0.5 and not bad["fully_cited"] and bad["uncited_claims"] == [1], bad
assert "WARNING" in bad["note"]

# --- conflict surfacing: two sources disagree on the same target -----------------------------------
conf = ca.build([
    ca.claim("Model says the wall is 2HR.", [ca.cite_ifc(G("wallX"), revision="r5")], target=f"{G('wallX')}.FireRating", value="2HR"),
    ca.claim("Code check requires 3HR.", [ca.cite_rule("IBC-T601")], target=f"{G('wallX')}.FireRating", value="3HR"),
])
assert len(conf["conflicts"]) == 1, conf["conflicts"]
c0 = conf["conflicts"][0]
assert c0["target"] == f"{G('wallX')}.FireRating" and c0["values"] == ["2HR", "3HR"] and len(c0["claims"]) == 2, c0

# --- cited_query over a fabricated property index --------------------------------------------------
idx = {
    G("g1"): {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {"FireRating": "2HR"}}},
    G("g2"): {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {"FireRating": "2HR"}}},
    G("g3"): {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {}}},          # missing FireRating
    G("g4"): {"ifc_class": "IfcSlab", "psets": {}},
}
r = ca.cited_query(idx, "class=IfcWall", prop="Pset_WallCommon.FireRating", model_id="p1")
assert r["matched"] == 3 and r["coverage"] == 1.0 and r["fully_cited"], r
# summary claim cites all three matched GUIDs
assert {c["guid"] for c in r["claims"][0]["citations"]} == {G("g1"), G("g2"), G("g3")}, r["claims"][0]
# breakdown by FireRating: 2 = 2HR, 1 = missing
by = {c["text"]: len(c["citations"]) for c in r["claims"][1:]}
assert any("2HR" in t and n == 2 for t, n in by.items()), by
assert any("missing" in t and n == 1 for t, n in by.items()), by
assert all(cit["source_type"] == "ifc" for c in r["claims"] for cit in c["citations"]), r

# an empty index → the single summary claim is uncited (the guard fires)
empty = ca.cited_query(None, "class=IfcWall", model_id="p1")
assert empty["matched"] == 0 and empty["coverage"] == 0.0 and not empty["fully_cited"], empty

# --- route: 422 on a missing query; 200 CitedAnswer otherwise --------------------------------------
if os.path.exists("./test_cited_answer.db"):
    os.remove("./test_cited_answer.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Cited"}).json()["id"]
    assert c.post(f"/projects/{pid}/answer/cited-query", json={}).status_code == 422
    rr = c.post(f"/projects/{pid}/answer/cited-query", json={"query": "class=IfcWall"})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert "coverage" in j and "claims" in j and "conflicts" in j and j["matched"] == 0, j

print("CITED-ANSWER OK - the provenance contract: claims cite their source (GUID/record/rule/doc+revision); "
      "provenance-as-confidence is deterministic (1 ifc source = 0.733, 3 independent = 1.0, a stale revision "
      "applies a 0.7 penalty); build() computes coverage and fires the uncited-claim guard (0.5 coverage + "
      "WARNING when a hunch has no citation) and surfaces a source conflict when the model (2HR) and a code "
      "rule (3HR) disagree on the same wall's fire rating; cited_query answers a model query with every claim "
      "citing the GUIDs it derives from, broken down by property value; the /answer/cited-query route 422s "
      "without a query and returns a CitedAnswer otherwise.")
