"""Last Planner pull-planning board — swimlanes, hand-offs, make-ready constraints, PPC + PDF.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_pull_plan.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_pullplan.db"
os.environ["STORAGE_DIR"] = "./test_storage_pullplan"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_pullplan.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient             # noqa: E402
from aec_api.main import app                          # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    r = c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})
    assert r.status_code == 200, f"{action}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    MS = "L3 slab complete"

    # a concrete task made ready then committed then done; a steel task pulled behind it (constrained);
    # an MEP task committed then missed (variance).
    conc = _create(c, pid, "pull_plan_task", {"task": "Form & pour L3 deck", "milestone": MS,
        "trade": "Concrete", "responsible": "J. Rivera", "duration_days": 5, "planned_week": "2026-W28"})
    _act(c, pid, "pull_plan_task", conc["id"], "make_ready")
    _act(c, pid, "pull_plan_task", conc["id"], "commit")
    _act(c, pid, "pull_plan_task", conc["id"], "complete")

    steel = _create(c, pid, "pull_plan_task", {"task": "Set L4 columns", "milestone": MS,
        "trade": "Steel", "responsible": "K. Ito", "duration_days": 3, "planned_week": "2026-W29",
        "predecessor": conc["id"], "constraints": ["Materials", "Prerequisite work"]})  # still constrained

    mep = _create(c, pid, "pull_plan_task", {"task": "Rough-in L3 conduit", "milestone": MS,
        "trade": "MEP", "responsible": "P. Shah", "duration_days": 4, "planned_week": "2026-W28"})
    _act(c, pid, "pull_plan_task", mep["id"], "make_ready")
    _act(c, pid, "pull_plan_task", mep["id"], "commit")
    # miss requires a variance reason
    r = c.post(f"/projects/{pid}/modules/pull_plan_task/{mep['id']}/transition", json={"action": "miss"})
    assert r.status_code == 400 and "Variance" in r.text, r.text[:160]
    c.patch(f"/projects/{pid}/modules/pull_plan_task/{mep['id']}", json={"variance_reason": "Materials"})
    _act(c, pid, "pull_plan_task", mep["id"], "miss")

    b = c.get(f"/projects/{pid}/pull-plan/board").json()
    assert b["total"] == 3, b["total"]
    assert {s["trade"] for s in b["swimlanes"]} == {"Concrete", "Steel", "MEP"}, b["swimlanes"]
    assert "2026-W28" in b["weeks"] and "2026-W29" in b["weeks"], b["weeks"]
    # hand-off: concrete -> steel
    assert any(e["from"] == conc["ref"] and e["to"] == steel["ref"] for e in b["handoffs"]), b["handoffs"]
    # make-ready: the steel task carries 2 open constraints
    assert b["make_ready"]["constrained_tasks"] == 1, b["make_ready"]
    cons = {x["constraint"]: x["count"] for x in b["make_ready"]["by_constraint"]}
    assert cons.get("Materials") == 1 and cons.get("Prerequisite work") == 1, cons
    # PPC: 1 done of 2 committed = 50%
    assert b["commitment"]["done"] == 1 and b["commitment"]["not_done"] == 1, b["commitment"]
    assert b["commitment"]["ppc_pct"] == 50.0, b["commitment"]["ppc_pct"]
    assert b["readiness"]["ready"] == 2, b["readiness"]         # concrete + mep reached made_ready+

    # milestone filter + PDF
    bf = c.get(f"/projects/{pid}/pull-plan/board", params={"milestone": MS}).json()
    assert bf["total"] == 3, bf["total"]
    pdf = c.get(f"/projects/{pid}/pull-plan/board.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", (pdf.status_code, pdf.content[:8])

    # --- M2: reliability metrics (TMR, perfect handoff, PPC trend, variance Pareto) ---
    m = c.get(f"/projects/{pid}/pull-plan/metrics").json()
    assert m["total"] == 3, m["total"]
    # concrete reached done + mep reached not_done → 2 made ready; steel still pulled
    assert m["tasks_made_ready"] == 2 and m["tmr_pct"] == 66.7, (m["tasks_made_ready"], m["tmr_pct"])
    # the concrete->steel hand-off is NOT clean (steel still constrained/pulled)
    assert m["handoffs"] == 1 and m["clean_handoffs"] == 0 and m["perfect_handoff_pct"] == 0.0, m
    assert m["ppc_pct"] == 50.0, m["ppc_pct"]          # 1 done of 2 committed
    # PPC trend: W28 carries both committed tasks, 50%
    w28 = next((r for r in m["ppc_trend"] if r["week"] == "2026-W28"), None)
    assert w28 and w28["committed"] == 2 and w28["ppc_pct"] == 50.0, m["ppc_trend"]
    # variance Pareto: the missed MEP task cites Materials
    assert m["variance_pareto"] and m["variance_pareto"][0]["reason"] == "Materials", m["variance_pareto"]

    # cross-project pull-planning benchmark (this project has 2 committed → need min_committed<=2)
    bm = c.get("/benchmarks/pull-planning", params={"min_committed": 1}).json()
    assert bm["projects"] >= 1 and bm["target_ppc"] == 80.0, bm
    assert any(abs(r["ppc_pct"] - 50.0) < 0.1 for r in bm["per_project"]), bm["per_project"]

print("PULL PLAN OK - board (concrete->steel hand-off, steel constrained, miss gated on variance, PPC "
      "50%, PDF); metrics TMR 66.7% + imperfect hand-off + W28 PPC-trend 50% + Materials variance "
      "Pareto; cross-project benchmark vs 80% target")
