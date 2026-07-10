"""Model -> cost -> GL traceability by IFC GlobalId. Cost records (budget / direct cost) carry
element_guids; the engine walks element -> cost lines and computes coverage per cost code.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_traceability.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_trace.db"
os.environ["STORAGE_DIR"] = "./test_storage_trace"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_trace.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient                # noqa: E402
from aec_api.main import app                             # noqa: E402

A, B = "3vB2eYHr1ABcDeFgHiJkLm", "0aZzYyXxWw1122334455Aa"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Trace Tower"}).json()["id"]
    cc = c.post(f"/projects/{pid}/modules/cost_code",
                json={"data": {"code": "05-12", "description": "Steel", "division": "05"}}).json()["id"]

    def mk(key, data, guids=None):
        body = {"data": data}
        if guids is not None:
            body["element_guids"] = guids
        r = c.post(f"/projects/{pid}/modules/{key}", json=body)
        assert r.status_code == 201, f"{key}: {r.text[:160]}"
        return r.json()

    # a budget tagged to two elements, a direct cost to one, and an untagged direct cost
    mk("budget", {"cost_code": cc, "description": "Steel", "revised": 100000}, [A, B])
    mk("direct_cost", {"cost_code": cc, "description": "Steel erection", "amount": 40000}, [A])
    mk("direct_cost", {"cost_code": cc, "description": "Misc (untagged)", "amount": 10000})

    # --- coverage summary -------------------------------------------------------------------------
    s = c.get(f"/projects/{pid}/cost/traceability").json()
    assert s["total_cost"] == 150000 and s["traceable_cost"] == 140000, s
    assert s["untraceable_cost"] == 10000 and s["coverage_pct"] == 93.3, s
    assert s["elements_referenced"] == 2 and s["line_count"] == 3, s
    assert s["by_cost_code"][0]["coverage_pct"] == 93.3, s["by_cost_code"]

    # --- element -> cost lines (what did this element cost?) --------------------------------------
    ea = c.get(f"/projects/{pid}/elements/{A}/costs").json()
    assert ea["total"] == 140000 and ea["count"] == 2, ea            # budget 100k + direct 40k
    assert ea["by_kind"] == {"budget": 100000, "direct_cost": 40000}, ea["by_kind"]
    eb = c.get(f"/projects/{pid}/elements/{B}/costs").json()
    assert eb["total"] == 100000 and eb["count"] == 1, eb            # budget only
    ez = c.get(f"/projects/{pid}/elements/NOPE/costs").json()
    assert ez["total"] == 0 and ez["count"] == 0, ez                 # untagged element → nothing

print("TRACEABILITY OK - cost records carry element_guids; coverage 93.3% ($140k of $150k traceable to "
      "2 IFC elements, $10k untagged); element GUID-A -> budget $100k + direct $40k = $140k; the "
      "model->cost->GL-by-GlobalId link no cost-code-only stack can make.")
