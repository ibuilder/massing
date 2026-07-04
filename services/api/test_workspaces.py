"""Workspace membership — the Design workspace + multi-workspace ("|"-list) tagging.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_workspaces.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_workspaces.db"
os.environ["STORAGE_DIR"] = "./test_storage_workspaces"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_workspaces.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient             # noqa: E402
from aec_api.main import app                          # noqa: E402


def _ws(mod: dict) -> set[str]:
    """A module's workspace membership as a set (default construction; '|'-list = multi)."""
    return set((mod.get("workspace") or "construction").split("|"))


with TestClient(app) as c:
    mods = {m["key"]: m for m in c.get("/modules").json()}

    # design-owned registers live in the Design workspace
    for k in ("space_program", "design_review", "selection", "info_requirement",
              "information_container", "coordination_issue", "document"):
        assert "design" in _ws(mods[k]), (k, mods[k].get("workspace"))

    # shared A/E<->GC registers show in BOTH design and construction (so neither role hunts for them)
    for k in ("rfi", "submittal", "drawing", "transmittal", "meeting", "permit", "spec_section"):
        w = _ws(mods[k])
        assert "design" in w and "construction" in w, (k, mods[k].get("workspace"))

    # project_phase is owned by owner + architect (developer|design)
    assert _ws(mods["project_phase"]) == {"developer", "design"}, mods["project_phase"].get("workspace")

    # the GC keeps its core registers construction-side (not moved to design)
    for k in ("daily_report", "schedule_activity", "owner_invoice", "punchlist"):
        assert "construction" in _ws(mods[k]), (k, mods[k].get("workspace"))

    # every workspace tag is one of the three known values
    known = {"construction", "developer", "design"}
    for k, m in mods.items():
        assert _ws(m) <= known, (k, m.get("workspace"))

print(f"WORKSPACES OK - {len(mods)} modules; design-owned + shared construction|design tags load; "
      "project_phase = developer|design; GC registers stay construction; all tags in the known set")
