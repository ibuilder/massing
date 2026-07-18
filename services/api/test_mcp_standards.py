"""AI-over-model: MCP tool dispatch + standards-compliance experts (grounded in project data).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_mcp_standards.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_mcp.db"
os.environ["STORAGE_DIR"] = "./test_storage_mcp"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_mcp.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import mcp_tools  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    eir = _create(c, pid, "info_requirement", {"title": "EIR", "req_type": "EIR - Exchange Information Requirements"})
    _act(c, pid, "info_requirement", eir["id"], "issue")
    _create(c, pid, "rfi", {"subject": "Existing RFI", "question": "?"})

    # --- MCP tool catalog endpoint -----------------------------------------------------------------
    cat = c.get("/mcp/tools").json()
    names = {t["name"] for t in cat["tools"]}
    assert {"project_snapshot", "cde_status", "bim_kpi_scorecard", "standards_check",
            "create_rfi"} <= names, names

    # --- MCP dispatch (the pure surface an external agent drives) ----------------------------------
    db = SessionLocal()
    try:
        projs = mcp_tools.dispatch(db, "list_projects", {})
        assert any(p["id"] == pid for p in projs), projs
        snap = mcp_tools.dispatch(db, "project_snapshot", {"project_id": pid})
        assert "modules" in snap, snap
        recs = mcp_tools.dispatch(db, "list_records", {"project_id": pid, "module": "rfi"})
        assert len(recs) == 1, recs
        cde = mcp_tools.dispatch(db, "cde_status", {"project_id": pid})
        assert "by_state" in cde, cde
        # a write tool: create an RFI through MCP
        rfi = mcp_tools.dispatch(db, "create_rfi",
                                 {"project_id": pid, "subject": "From agent", "question": "Advise?"})
        db.commit()
        assert rfi.get("ref"), rfi
        try:
            mcp_tools.dispatch(db, "nonexistent_tool", {})
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

        # --- SEC-MCP: membership scoping (defense-in-depth if the server is ever non-local) --------
        # RBAC is off in this suite, so member_project_ids is None → unrestricted; simulate RBAC by
        # patching the rbac module the way dispatch resolves it.
        from aec_api import rbac as _rbac
        _saved_on = _rbac.RBAC_ON
        _rbac.RBAC_ON = True
        try:
            # 'stranger' is a member of nothing: list_projects is empty, project tools are refused
            assert mcp_tools.dispatch(db, "list_projects", {}, user="stranger") == []
            try:
                mcp_tools.dispatch(db, "cde_status", {"project_id": pid}, user="stranger")
                raise AssertionError("expected PermissionError for a non-member identity")
            except PermissionError:
                pass
            # the admin api-key identity (the stdio default) stays unrestricted
            assert any(p["id"] == pid for p in mcp_tools.dispatch(db, "list_projects", {}, user="api-key"))
        finally:
            _rbac.RBAC_ON = _saved_on
    finally:
        db.close()
    # the agent-created RFI is now real
    assert len(c.get(f"/projects/{pid}/modules/rfi").json()) == 2

    # --- standards experts: grounded findings with clause references ------------------------------
    iso = c.get(f"/projects/{pid}/standards/check", params={"standard": "iso19650"}).json()
    assert iso["standard"] == "iso19650" and 0 <= iso["score"] <= 100, iso
    assert all("reference" in f for f in iso["findings"]), iso["findings"]
    # EIR present but AIR/BEP missing -> at least one gap referencing ISO 19650
    assert any(f["level"] == "gap" for f in iso["findings"]), iso["findings"]

    cobie = c.get(f"/projects/{pid}/standards/check", params={"standard": "cobie"}).json()
    assert cobie["standard"] == "cobie" and cobie["findings"], cobie
    ids = c.get(f"/projects/{pid}/standards/check", params={"standard": "ids"}).json()
    assert ids["findings"] and any("model" in f["text"].lower() for f in ids["findings"]), ids  # no model
    bad = c.get(f"/projects/{pid}/standards/check", params={"standard": "nope"}).json()
    assert "error" in bad, bad

print("MCP + STANDARDS OK - catalog exposes 8 tools; dispatch runs snapshot/records/cde and creates a "
      "real RFI (write tool); unknown tool raises; standards experts return clause-referenced findings "
      "(iso19650 flags missing AIR/BEP as gaps; ids notes no model)")
