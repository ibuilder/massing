"""Preconstruction estimate continuity — per-milestone totals + $/SF, milestone-to-milestone drift,
and the gap to the project budget/GMP. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_precon.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_precon.db"
os.environ["STORAGE_DIR"] = "./test_storage_precon"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_precon.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()["id"]


def trans(c, pid, key, rid, action):
    return c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Precon"}).json()["id"]

    # the module is registered + catalogued
    assert "estimate_set" in {m["key"] for m in c.get("/modules").json()}

    # create estimate sets OUT of milestone order (engine must order along the design timeline)
    mk(c, pid, "estimate_set", {"title": "DD set", "milestone": "DD", "total": 12_500_000, "gsf": 50000,
                                "basis": "Budget", "estimate_date": "2026-03-01"})
    mk(c, pid, "estimate_set", {"title": "Concept set", "milestone": "Concept", "total": 10_000_000,
                                "gsf": 50000, "basis": "ROM", "estimate_date": "2026-01-01"})
    mk(c, pid, "estimate_set", {"title": "SD set", "milestone": "SD", "total": 11_000_000, "gsf": 50000,
                                "basis": "ROM", "estimate_date": "2026-02-01"})

    s = c.get(f"/projects/{pid}/precon/estimate-continuity?budget=12000000").json()
    assert s["set_count"] == 3, s
    assert s["milestones"] == ["Concept", "SD", "DD"], s["milestones"]      # ordered by milestone rank
    assert s["first_total"] == 10_000_000 and s["first_milestone"] == "Concept", s
    assert s["latest_total"] == 12_500_000 and s["latest_milestone"] == "DD", s
    assert s["latest_psf"] == 250.0, s["latest_psf"]                        # 12.5M / 50k SF
    assert s["total_drift"] == 2_500_000 and s["total_drift_pct"] == 25.0, s
    assert s["budget"] == 12_000_000, s
    assert s["variance_to_budget"] == 500_000 and s["over_budget"] is True, s   # latest 12.5M vs 12M budget
    dd = next(r for r in s["rows"] if r["milestone"] == "DD")
    assert dd["delta_total"] == 1_500_000 and dd["delta_pct"] == round(100 * 1.5 / 11, 1), dd  # SD->DD

    # report renders (PDF + xlsx) and is catalogued
    assert "estimate_continuity" in {x["id"] for x in c.get("/reports").json()["reports"]}
    pdf = c.get(f"/projects/{pid}/reports/estimate_continuity.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code
    xls = c.get(f"/projects/{pid}/reports/estimate_continuity.xlsx")
    assert xls.status_code == 200 and len(xls.content) > 100, xls.status_code

    # --- Phase 2: decision log + assumptions register ------------------------
    d1 = mk(c, pid, "decision", {"subject": "Curtainwall system", "category": "Systems",
                                 "cost_impact": 100000, "schedule_impact_days": 10, "alignment": "Disputed"})
    d2 = mk(c, pid, "decision", {"subject": "Slab on grade thickness", "category": "Design",
                                 "cost_impact": 20000, "alignment": "Aligned"})
    trans(c, pid, "decision", d2, "decide")        # d2 decided; d1 stays open + disputed
    dl = c.get(f"/projects/{pid}/precon/decisions").json()
    assert dl["decision_count"] == 2 and dl["open_count"] == 1, dl
    assert dl["disputed_count"] == 1, dl
    assert dl["open_cost_exposure"] == 100000 and dl["open_schedule_exposure_days"] == 10, dl

    mk(c, pid, "assumption", {"subject": "Unsuitable soils allowance", "category": "Allowance", "cost_impact": 50000})
    a2 = mk(c, pid, "assumption", {"subject": "Owner-furnished FF&E excluded", "category": "Exclusion"})
    trans(c, pid, "assumption", a2, "confirm")
    asm = c.get(f"/projects/{pid}/precon/assumptions").json()
    assert asm["assumption_count"] == 2 and asm["open_count"] == 1 and asm["confirmed_count"] == 1, asm
    assert asm["open_cost_exposure"] == 50000, asm

    # --- Phase 3: VE cycle + alignment ---------------------------------------
    v1 = mk(c, pid, "value_engineering", {"subject": "Switch to PT slabs", "savings": 200000})
    trans(c, pid, "value_engineering", v1, "accept")
    v2 = mk(c, pid, "value_engineering", {"subject": "Value-spec finishes", "savings": 100000})
    trans(c, pid, "value_engineering", v2, "accept")
    mk(c, pid, "value_engineering", {"subject": "Defer site furnishings", "savings": 400000})  # stays proposed
    ve = c.get(f"/projects/{pid}/precon/ve?target=500000").json()
    assert ve["accepted_savings"] == 300000 and ve["proposed_savings"] == 400000, ve
    assert ve["gap_after_accepted"] == 200000 and ve["target_met"] is False, ve   # 500k gap - 300k accepted

    al = c.get(f"/projects/{pid}/precon/alignment").json()
    assert al["overall_status"] == "red", al        # disputed decision -> red
    assert al["open_decisions"] == 1 and al["open_assumptions"] == 1, al
    assert al["ve_accepted"] == 300000 and al["ve_pipeline"] == 700000, al
    assert al["variance_to_budget"] is None, al      # no GMP budget seeded in this minimal project
    assert isinstance(al["alignment_score"], int) and 0 <= al["alignment_score"] <= 100, al
    assert any(d["key"] == "decisions" and d["status"] == "red" for d in al["domains"]), al
    # the three precon reports render
    for rid in ("decision_log", "assumptions_register", "precon_alignment"):
        assert rid in {x["id"] for x in c.get("/reports").json()["reports"]}, rid
        rp = c.get(f"/projects/{pid}/reports/{rid}.pdf")
        assert rp.status_code == 200 and rp.content[:4] == b"%PDF", (rid, rp.status_code)

    # empty project -> clean zeroed structure (no crash)
    pid2 = c.post("/projects", json={"name": "Empty precon"}).json()["id"]
    e = c.get(f"/projects/{pid2}/precon/estimate-continuity").json()
    assert e["set_count"] == 0 and e["latest_total"] == 0.0 and e["variance_to_budget"] is None, e

print("PRECON OK - estimate continuity (Concept->SD->DD, $/SF 250, drift +2.5M/25%, +500k OVER $12M); "
      "decision log (1 open/disputed, $100k+10d exposure); assumptions (1 open, $50k allowance); VE cycle "
      "($300k accepted vs $500k gap -> $200k remaining); alignment RED w/ score; 4 precon reports render; "
      "empty project zeroed")
