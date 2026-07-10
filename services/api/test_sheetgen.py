"""Discipline sheet-set generation — every discipline gets its own NCS-numbered series (S-/A-/M-/E-/
P-/FP-/FA-/T-…), Fire Alarm (FA) is a distinct series from Fire Protection (FP), the sheets become
`drawing` records that feed the drawing-set register, and re-running is idempotent.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sheetgen.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_sheetgen.db"
os.environ["STORAGE_DIR"] = "./test_storage_sheetgen"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_sheetgen.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient                 # noqa: E402
from aec_api import drawingset, sheetgen                  # noqa: E402
from aec_api import classification as cls                 # noqa: E402
from aec_api.main import app                              # noqa: E402

HDR = {"X-User": "drafter"}

# --- pure engine: multi-level plan, per-discipline prefixes, FA distinct from FP -----------------
sheets = sheetgen.plan_set(["Level 1", "Level 2", "Level 3"], sheetgen.DEFAULT_CODES)
prefixes = {n.split("-")[0] for n in (s["number"] for s in sheets)}
for p in ("G", "S", "A", "M", "E", "P", "FP", "FA", "T"):
    assert p in prefixes, f"missing series prefix {p}: {sorted(prefixes)}"
# per-level plans present for each level (Mechanical M-101/102/103)
assert {"M-101", "M-102", "M-103"} <= {s["number"] for s in sheets}, "per-level HVAC plans missing"
# FA and FP are DIFFERENT disciplines on their own series
fa = [s for s in sheets if s["number"].startswith("FA-")]
fp = [s for s in sheets if s["number"].startswith("FP-")]
assert fa and fp, "need both fire alarm + fire protection series"
assert all(s["discipline"] == "Fire Alarm" for s in fa), "FA sheets not tagged Fire Alarm"
assert all(s["discipline"] == "Fire Protection" for s in fp), "FP sheets not tagged Fire Protection"

# --- parse round-trip: the generated numbers parse back to the right discipline ------------------
assert drawingset.parse_sheet_id("FA-101")["discipline"] == "Fire Alarm"
assert drawingset.parse_sheet_id("FP-101")["discipline"] == "Fire Protection"
assert drawingset.parse_sheet_id("M-101")["discipline"] == "Mechanical"
assert drawingset.parse_sheet_id("S-301")["sheet_type_name"] == "Sections"
assert cls.sheet_series("FA") == "Fire Alarm" and cls.sheet_series("FP") == "Fire Protection"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Sheet Set Tower"}, headers=HDR).json()["id"]
    P = f"/projects/{pid}"

    # --- preview (no records created) ------------------------------------------------------------
    prev = c.get(f"{P}/drawing-set/plan?all=true", headers=HDR).json()
    assert prev["sheet_count"] > 0 and "Fire Alarm" in prev["by_discipline"], prev["by_discipline"]
    assert c.get(f"{P}/drawing-set", headers=HDR).json()["sheet_count"] == 0, "preview must not create"

    # --- generate the full set (thin model → 1 level fallback, all disciplines) -------------------
    g = c.post(f"{P}/drawing-set/generate", json={"all": True}, headers=HDR)
    assert g.status_code == 201, g.text
    gen = g.json()
    assert gen["created"] > 0 and gen["created"] == gen["sheet_count"], gen
    assert "Fire Alarm" in gen["by_discipline"] and "Mechanical" in gen["by_discipline"], gen["by_discipline"]

    # the register now groups the created sheets by discipline, with FA and FP separate
    reg = c.get(f"{P}/drawing-set", headers=HDR).json()
    disc = reg["by_discipline"]
    assert disc.get("Fire Alarm", 0) >= 1 and disc.get("Fire Protection", 0) >= 1, disc
    nums = {s["sheet_number"] for s in reg["sheet_index"]}
    assert any(n.startswith("FA-") for n in nums) and any(n.startswith("M-") for n in nums), sorted(nums)[:20]

    # --- idempotent: re-generating creates nothing new -------------------------------------------
    g2 = c.post(f"{P}/drawing-set/generate", json={"all": True}, headers=HDR).json()
    assert g2["created"] == 0 and g2["skipped_existing"] == g2["planned"], g2

    # --- targeted subset: only mechanical + fire alarm -------------------------------------------
    pid2 = c.post("/projects", json={"name": "MEP only"}, headers=HDR).json()["id"]
    g3 = c.post(f"/projects/{pid2}/drawing-set/generate",
                json={"disciplines": ["Mechanical", "FA"]}, headers=HDR).json()
    assert set(g3["by_discipline"]) == {"Mechanical", "Fire Alarm"}, g3["by_discipline"]

print(f"SHEETGEN OK - {len(sheets)} sheets across {len(prev['by_discipline'])} disciplines; each has its "
      "own NCS series (S-/A-/M-/E-/P-/FP-/FA-/T-); Fire Alarm (FA) is a distinct series from Fire "
      "Protection (FP); sheets become drawing records in the register; generation is idempotent; "
      "targeted discipline subset works.")
