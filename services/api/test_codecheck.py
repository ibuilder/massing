"""Code-compliance assistant — offline IBC rules path (no ANTHROPIC_API_KEY).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_codecheck.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_codecheck.db"
os.environ["STORAGE_DIR"] = "./test_storage_codecheck"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)          # force offline rules
for _f in ("./test_codecheck.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import codecheck                         # noqa: E402
from aec_api.main import app                          # noqa: E402

# assembly + large area + multistory -> occupancy A, sprinklers, assembly egress, multistory rules
r = codecheck.check("A 4-story restaurant and assembly hall, 20,000 sf, 400 occupants")
assert r["source"] == "rules", r
assert r["detected"]["occupancy"]["group"] == "A", r["detected"]
assert r["detected"]["area_sf"] == 20000 and r["detected"]["stories"] == 4, r["detected"]
titles = " ".join(t["title"].lower() for t in r["topics"])
assert "occupancy classification" in titles and "egress width" in titles and "accessibility" in titles, titles
assert "sprinkler" in titles, "large assembly should trigger sprinklers"
assert "assembly egress" in titles, "A occupancy should trigger panic hardware/aisles"
assert any("elevator" in t["requirement"].lower() or "fire-resistance" in t["title"].lower() for t in r["topics"]), r["topics"]
# every topic cites a real code + section (no fabricated blanks)
assert all(t["code"] and t["section"] and t["requirement"] for t in r["topics"]), r["topics"]

# small office -> business occupancy, no sprinkler/assembly triggers, still the universal checklist
r2 = codecheck.check("Single-story 2,000 sf professional office")
assert r2["detected"]["occupancy"]["group"] == "B", r2["detected"]
t2 = " ".join(t["title"].lower() for t in r2["topics"])
assert "sprinkler" not in t2 and "assembly egress" not in t2, t2
assert "occupant load" in t2, t2

# empty -> no fabrication
assert codecheck.check("")["source"] == "empty"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    resp = c.post(f"/projects/{pid}/codecheck", json={"description": "5-story apartment building, 60,000 sf"})
    assert resp.status_code == 200, resp.text[:200]
    j = resp.json()
    assert j["detected"]["occupancy"]["group"] == "R" and j["detected"]["stories"] == 5, j["detected"]
    assert any("dwelling" in t["title"].lower() for t in j["topics"]), j["topics"]

print("CODECHECK OK - detects occupancy/area/stories; assembly+large+multistory -> sprinklers + assembly "
      "egress + elevator/fire-resistance; small office omits those; R triggers dwelling separation; all "
      "topics carry a real code+section; empty -> no fabrication; endpoint 200")
