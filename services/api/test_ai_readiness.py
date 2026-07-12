"""AI / data-readiness scorecard — single-source / completeness / integrity / governance grading.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ai_readiness.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ai_readiness.db"
os.environ["STORAGE_DIR"] = "./test_storage_ai_readiness"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_ai_readiness.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _req(c, pid, title, rtype):
    r = c.post(f"/projects/{pid}/modules/info_requirement",
               json={"data": {"title": title, "req_type": rtype}})
    assert r.status_code == 201, r.text[:160]
    c.post(f"/projects/{pid}/modules/info_requirement/{r.json()['id']}/transition", json={"action": "issue"})
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    r0 = c.get(f"/projects/{pid}/ai-readiness").json()
    assert 0 <= r0["overall"] <= 100, r0["overall"]
    assert r0["verdict"] in ("ready", "partial", "not_ready"), r0["verdict"]
    d = r0["dimensions"]
    assert {"single_source_of_truth", "information_completeness", "governance"} <= set(d), list(d)
    assert "model_integrity" not in d, "no IFC → integrity dimension should be skipped"
    assert r0["verdict"] == "not_ready", r0                 # empty project isn't agent-ready
    base_completeness = d["information_completeness"]["score"]

    # add the core requirements (EIR/BEP/AIR) issued → completeness improves
    _req(c, pid, "EIR", "EIR - Exchange Information Requirements")
    _req(c, pid, "BEP", "BEP - BIM Execution Plan")
    _req(c, pid, "AIR", "AIR - Asset Information Requirements")
    r1 = c.get(f"/projects/{pid}/ai-readiness").json()
    assert r1["dimensions"]["information_completeness"]["requirements_core_complete"] is True, r1["dimensions"]
    assert r1["dimensions"]["information_completeness"]["score"] > base_completeness, \
        (base_completeness, r1["dimensions"]["information_completeness"]["score"])
    assert r1["overall"] >= r0["overall"], (r0["overall"], r1["overall"])

print(f"ai_readiness: empty={r0['overall']} ({r0['verdict']}) -> +core-reqs={r1['overall']} ({r1['verdict']})")
print("test_ai_readiness OK")
