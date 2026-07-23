"""PERSONA-ANSWER — Exec/PM/Field lenses + a deterministic {answer, insight, follow_ups} envelope over a
CitedAnswer; claims/citations never dropped, insight/chips template-derived from the data (no LLM).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_persona_answer.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_persona_answer.db"
os.environ["STORAGE_DIR"] = "./test_storage_persona"
os.environ.pop("AEC_RBAC", None)

from aec_api import cited_answer as ca  # noqa: E402
from aec_api import persona_answer as pa

base = ca.build([
    ca.claim("12 walls match.", [ca.cite_ifc("g1"), ca.cite_ifc("g2")]),
    ca.claim("8 carry a 2HR rating.", [ca.cite_ifc("g1")]),
    ca.claim("4 are unrated.", [ca.cite_ifc("g2")]),
])
base["matched"] = 12

# --- exec: 2-sentence prose, risk-first insight, exec chip ------------------------------------------
e = pa.shape(base, "exec")
assert e["persona"] == "exec" and e["answer"] == "12 walls match. 8 carry a 2HR rating.", e["answer"]
assert len(e["claims"]) == 3, "claims are never dropped"
assert e["insight"].startswith("Fully cited"), e["insight"]
assert "What is the cost exposure on these elements?" in e["follow_ups"], e["follow_ups"]

# --- field: one line, field chip --------------------------------------------------------------------
f = pa.shape(base, "field")
assert f["answer"] == "12 walls match." and "Show these on my level" in f["follow_ups"], f

# --- pm default + unknown persona falls back to pm --------------------------------------------------
p = pa.shape(base, "chief-vibes-officer")
assert p["persona"] == "pm" and "Which of these have an open RFI or issue?" in p["follow_ups"], p

# --- insight priority: conflicts > uncited > empty > coverage ---------------------------------------
conf = ca.build([
    ca.claim("Model says 2HR.", [ca.cite_ifc("w")], target="w.FireRating", value="2HR"),
    ca.claim("Code needs 3HR.", [ca.cite_rule("T601")], target="w.FireRating", value="3HR"),
])
s = pa.shape(conf, "pm")
assert "conflict" in s["insight"] and s["follow_ups"][0] == "Show the 1 conflicting source(s)", s

unc = pa.shape(ca.build([ca.claim("A hunch.")]), "pm")
assert "no citation" in unc["insight"] and "List the 1 uncited claim(s)" in unc["follow_ups"], unc

empty = dict(ca.build([ca.claim("0 match.", [ca.cite_ifc("x")])]), matched=0)
assert "Nothing in the model matches" in pa.shape(empty, "pm")["insight"]

assert len(pa.shape(base, "pm")["follow_ups"]) <= 4                       # chips capped

# --- route: persona shapes the cited-query response -------------------------------------------------
if os.path.exists("./test_persona_answer.db"):
    os.remove("./test_persona_answer.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Persona"}).json()["id"]
    rr = c.post(f"/projects/{pid}/answer/cited-query", json={"query": "class=IfcWall", "persona": "exec"})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["persona"] == "exec" and "insight" in j and "follow_ups" in j, j
    # without persona the plain CitedAnswer shape is unchanged
    plain = c.post(f"/projects/{pid}/answer/cited-query", json={"query": "class=IfcWall"}).json()
    assert "persona" not in plain and "insight" not in plain, plain

print("PERSONA-ANSWER OK - the same CitedAnswer shapes per seat: exec gets two sentences + a cost-exposure "
      "chip, field one line + 'show these on my level', pm the breakdown + RFI chip (unknown personas fall "
      "back to pm); claims/citations are never dropped; the deterministic insight prioritizes conflicts > "
      "uncited > no-match > coverage, and follow-up chips (≤4) derive from what the answer contains; the "
      "/answer/cited-query route shapes when persona is passed and stays a plain CitedAnswer when not.")
