"""Structural-system advisor (R3) — system tiers by height/span, rough sizing, load path, flags.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_structure.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_structure.db"
os.environ["STORAGE_DIR"] = "./test_storage_structure"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_structure.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api import structure as st  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- system tiers by height --------------------------------------------------
low = st.recommend(12, 4, 7.5)
mid = st.recommend(40, 12, 7.5)
high = st.recommend(120, 34, 9)
supertall = st.recommend(300, 80, 9)
assert "flat-plate" in low["system"], low["system"]
assert "shear" in mid["system"].lower(), mid["system"]
assert "core" in high["system"].lower(), high["system"]
assert "outrigger" in supertall["system"].lower() or "tube" in supertall["system"].lower(), supertall["system"]

# --- member sizing grows with scale ------------------------------------------
assert supertall["members_mm"]["column"] >= low["members_mm"]["column"], "columns grow with floors"
assert supertall["members_mm"]["column"] <= 1200, "column capped"
# slab/beam scale with span
assert st.recommend(40, 12, 12)["members_mm"]["slab"] > st.recommend(40, 12, 6)["members_mm"]["slab"]

# --- flags: long span on flat-plate, slenderness -----------------------------
longspan = st.recommend(12, 4, 11)        # flat-plate + 11 m span
assert any("Long span" in f or "long" in f.lower() for f in longspan["flags"]), longspan["flags"]
slender = st.recommend(300, 80, 9)        # tall + narrow span → slender
assert slender["slenderness"] > 7 and any("lender" in f for f in slender["flags"]), slender

# --- load path present -------------------------------------------------------
assert "slab" in high["load_path"] and "foundation" in high["load_path"], high["load_path"]
assert high["members_mm"]["uses_beams"] is True and low["members_mm"]["uses_beams"] is False

# --- per-floor column taper --------------------------------------------------
sched = high["column_schedule"]
assert len(sched) == high["floors"], "one entry per floor"
assert sched[0]["floor"] == 0 and sched[0]["floors_carried"] == high["floors"], sched[0]
assert sched[-1]["floors_carried"] == 1, sched[-1]
# base column is the widest, top is the narrowest — the frame tapers upward
assert sched[0]["side_mm"] == high["base_column_mm"], (sched[0], high["base_column_mm"])
assert sched[-1]["side_mm"] == high["top_column_mm"] <= sched[0]["side_mm"], sched
assert high["top_column_mm"] >= 400, "top column floored at 400 mm"
# monotonic non-increasing base→top (√load taper, rounded to 50 mm zones)
sides = [s["side_mm"] for s in sched]
assert all(sides[k] >= sides[k + 1] for k in range(len(sides) - 1)), sides
# side ∝ √(floors carried): the actual mid-height column is meaningfully smaller than the base
assert sched[len(sched) // 2]["side_mm"] < sched[0]["side_mm"], "columns narrow with height"

# --- lateral core sizing -----------------------------------------------------
lc_hi = high["lateral_core"]
assert lc_hi["provided"] is True, "high-rise uses a central core"
assert lc_hi["plan_w_m"] >= 6.0 and lc_hi["wall_mm"] >= 250, lc_hi
# taller building → thicker core walls (drift control)
assert supertall["lateral_core"]["wall_mm"] >= lc_hi["wall_mm"], "walls thicken with height"
assert low["lateral_core"]["provided"] is False, "low-rise: distributed shear walls, no central core"

# 1-storey edge case: schedule still valid, no divide-by-zero
one = st.recommend(4, 1, 7.5)
assert len(one["column_schedule"]) == 1 and one["column_schedule"][0]["floors_carried"] == 1

# --- endpoint ----------------------------------------------------------------
with TestClient(app) as c:
    r = c.post("/structure/recommend", json={"height_m": 120, "floors": 34, "span_m": 9})
    assert r.status_code == 200 and "core" in r.json()["system"].lower(), r.text

print(f"STRUCTURE OK - low '{low['system']}' / mid '{mid['system']}' / high '{high['system']}' / "
      f"supertall '{supertall['system']}'; columns {low['members_mm']['column']}-{supertall['members_mm']['column']} mm; "
      f"span+slenderness flags; load path + endpoint verified")
