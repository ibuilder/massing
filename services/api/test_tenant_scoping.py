"""SEC-TENANT: portfolio roll-ups are scoped to the caller's member projects under RBAC — the
cross-tenant leak fix. Two users, each a member of exactly one of two projects with distinct financials;
each caller's /wip/portfolio, /contractor-statements/portfolio and /benchmarks/* must contain ONLY their
own project's data (the fca_portfolio pattern, now applied everywhere). Also: the /search limit clamp.
Run: AEC_RBAC=1 PYTHONPATH=src ./.venv/Scripts/python.exe test_tenant_scoping.py"""
import os

os.environ["AEC_RBAC"] = "1"
os.environ.setdefault("DATABASE_URL", "sqlite:///./_tenant_scope_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_tenant_scope")
os.environ.setdefault("AEC_TRUST_XUSER", "1")
_f = "./_tenant_scope_test.db"
if os.path.exists(_f):
    os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

ADMIN = {"X-User": "api-key"}
A = {"X-User": "alice"}
B = {"X-User": "bob"}

with TestClient(app) as c:
    # two projects; alice is a member of only P1, bob of only P2 (admin creates + assigns)
    p1 = c.post("/projects", json={"name": "Tenant One Tower"}, headers=ADMIN).json()["id"]
    p2 = c.post("/projects", json={"name": "Tenant Two Plaza"}, headers=ADMIN).json()["id"]
    for pid, user in ((p1, "alice"), (p2, "bob")):
        r = c.post(f"/projects/{pid}/members", json={"user": user, "role": "editor"}, headers=ADMIN)
        assert r.status_code < 300, (r.status_code, r.text[:200])

    # distinct financial fingerprints: a prime contract + direct costs per project
    def seed(pid, user_hdr, contract, cost_code, amounts):
        r = c.post(f"/projects/{pid}/modules/prime_contract",
                   json={"data": {"name": "GMP", "contract_value": contract}}, headers=user_hdr)
        assert r.status_code < 300, (r.status_code, r.text[:200])
        for amt in amounts:
            r = c.post(f"/projects/{pid}/modules/direct_cost",
                       json={"data": {"description": "cost", "cost_code": cost_code, "amount": amt}},
                       headers=user_hdr)
            assert r.status_code < 300, (r.status_code, r.text[:200])

    seed(p1, A, 1_000_000, "03 30 00", [100.0, 200.0, 300.0])   # alice's tenant
    seed(p2, B, 9_000_000, "09 91 00", [5000.0, 6000.0, 7000.0])  # bob's tenant

    # --- WIP portfolio: alice sees only P1; bob only P2; admin sees both ------------------------------
    wa = c.get("/wip/portfolio", headers=A).json()
    ids_a = {r["id"] for r in wa["projects"]} if "projects" in wa else {r["id"] for r in wa.get("rows", [])}
    assert p1 in ids_a and p2 not in ids_a, f"alice's WIP portfolio leaked: {ids_a}"
    wb = c.get("/wip/portfolio", headers=B).json()
    ids_b = {r["id"] for r in (wb.get("projects") or wb.get("rows") or [])}
    assert p2 in ids_b and p1 not in ids_b, f"bob's WIP portfolio leaked: {ids_b}"
    wadm = c.get("/wip/portfolio", headers=ADMIN).json()
    ids_adm = {r["id"] for r in (wadm.get("projects") or wadm.get("rows") or [])}
    assert {p1, p2} <= ids_adm, "admin (api-key) sees the full portfolio"

    # --- contractor statements portfolio: job counts scoped ------------------------------------------
    sa = c.get("/contractor-statements/portfolio", headers=A).json()
    sb = c.get("/contractor-statements/portfolio", headers=B).json()
    assert sa["job_count"] == 1 and sb["job_count"] == 1, (sa.get("job_count"), sb.get("job_count"))
    # alice's revenue basis must not include bob's $9M job (contract values differ by ~9x)
    sadm = c.get("/contractor-statements/portfolio", headers=ADMIN).json()
    assert sadm["job_count"] == 2, sadm.get("job_count")

    # --- cost benchmarks: alice sees only her cost code, never bob's ---------------------------------
    ba = c.get("/benchmarks/costs?min_samples=3", headers=A).json()
    codes_a = {r["cost_code"] for r in ba["cost_codes"]}
    assert "03 30 00" in codes_a and "09 91 00" not in codes_a, f"alice's benchmarks leaked: {codes_a}"
    bb = c.get("/benchmarks/costs?min_samples=3", headers=B).json()
    codes_b = {r["cost_code"] for r in bb["cost_codes"]}
    assert "09 91 00" in codes_b and "03 30 00" not in codes_b, f"bob's benchmarks leaked: {codes_b}"
    badm = c.get("/benchmarks/costs?min_samples=3", headers=ADMIN).json()
    codes_adm = {r["cost_code"] for r in badm["cost_codes"]}
    assert {"03 30 00", "09 91 00"} <= codes_adm

    # response-rates + pull-planning: scoped endpoints respond 200 for a member (shape smoke)
    assert c.get("/benchmarks/response-rates", headers=A).status_code == 200
    assert c.get("/benchmarks/pull-planning", headers=A).status_code == 200

    # --- /search limit clamp: an absurd limit must not 500 and returns a bounded list ----------------
    r = c.get(f"/projects/{p1}/search?q=cost&limit=100000000", headers=A)
    assert r.status_code == 200 and len(r.json()) <= 200, (r.status_code, len(r.json()))

print("TENANT-SCOPING OK - under RBAC, /wip/portfolio, /contractor-statements/portfolio and "
      "/benchmarks/costs each contain ONLY the caller's member projects (alice: P1/03 30 00 only; "
      "bob: P2/09 91 00 only; admin api-key: both); response-rates + pull-planning scoped endpoints "
      "respond; the /search limit is clamped to 200 (no unbounded SQL fan-out).")
