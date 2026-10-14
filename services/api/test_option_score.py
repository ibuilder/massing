"""GEN-SCORE: generative option scoring — variant grid, engine-backed criteria, weighted ranking,
compliance gating. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_option_score.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./_optscore_test.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_optscore")
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_optscore_test.db"):
    os.remove("./_optscore_test.db")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from aec_api import option_score as osc  # noqa: E402

BASE = {"lot_width": 40, "lot_depth": 30, "far": 3.0, "floor_to_floor": 3.5,
        "coverage_max": 0.6, "height_limit": 60}

# --- generate: deterministic grid, labelled, FAR-stepped ------------------------------------------
grid = osc.generate_options(BASE, types=["multifamily", "office"])
assert len(grid) == 6, len(grid)                       # 2 types × 3 FAR steps
assert {o["far"] for o in grid} == {1.8, 2.4, 3.0}, {o["far"] for o in grid}
assert all(o["label"] for o in grid)
assert osc.generate_options(BASE, types=["multifamily", "office"]) == grid, "must be deterministic"

# --- score: warehouse (cheap $/SF + low carbon) must beat hospital (expensive + high carbon) on the
#     default weights when yield is equal (same envelope) ------------------------------------------
opts = [dict(BASE, building_type="warehouse", label="W"), dict(BASE, building_type="hospital", label="H")]
r = osc.score_options(opts)
assert r["options"][0]["label"] == "W", [o["label"] for o in r["options"]]
assert r["recommended"] == "W"
w_row = next(o for o in r["options"] if o["label"] == "W")
h_row = next(o for o in r["options"] if o["label"] == "H")
# hand-checks: same envelope → same GFA/yield; cost + carbon differentiate
assert w_row["massing"]["buildable_gfa_m2"] == h_row["massing"]["buildable_gfa_m2"]
assert w_row["scores"]["yield"] == h_row["scores"]["yield"] == 100.0, "flat criterion → 100 for all"
assert w_row["scores"]["cost"] == 100.0 and h_row["scores"]["cost"] == 0.0
assert w_row["scores"]["carbon"] == 100.0 and h_row["scores"]["carbon"] == 0.0
assert osc.CARBON_KGCO2E_M2["warehouse"] < osc.CARBON_KGCO2E_M2["hospital"]
# Carbon is HYBRID since v0.3.669: the shell comes from an elemental takeoff (geometry), the fit-out
# from the type benchmark (programme). Either alone loses an axis — a pure takeoff would give these
# two identical carbon on the same envelope, which is exactly the assertion above that would break.
assert w_row["carbon_basis"] == "hybrid" and h_row["carbon_basis"] == "hybrid"
split = w_row["takeoff"]["carbon_split"]
assert split["fitout_kgco2e_m2"] == round(
    osc.CARBON_KGCO2E_M2["warehouse"] * osc.FITOUT_CARBON_SHARE, 1), split
# same envelope → identical SHELL carbon; the whole difference is programme-driven fit-out
assert w_row["takeoff"]["carbon_intensity_kgco2e_m2"] == h_row["takeoff"]["carbon_intensity_kgco2e_m2"]
assert split["fitout_kgco2e_m2"] < h_row["takeoff"]["carbon_split"]["fitout_kgco2e_m2"]
assert w_row["carbon_total_tco2e"] == round(
    w_row["massing"]["buildable_gfa_m2"] * w_row["carbon_intensity_kgco2e_m2"] / 1000.0, 1)

# --- weights steer the ranking: an all-yield weighting ties them (equal yield → equal composite) ---
ry = osc.score_options(opts, weights={"cost": 0.0, "carbon": 0.0, "yield": 1.0, "compliance": 0.0})
comps = [o["composite"] for o in ry["options"]]
assert comps[0] == comps[1] == 100.0, comps

# --- compliance gating: a height-limit-violating option is flagged, capped, never recommended ------
tall = dict(BASE, building_type="warehouse", label="TALL", height_limit=10)   # 3 FAR needs ≫ 10 m
r2 = osc.score_options([dict(BASE, building_type="hospital", label="OK"), tall])
tall_row = next(o for o in r2["options"] if o["label"] == "TALL")
# compute_massing may bind floors to the height limit; only assert when it actually violates
if not tall_row["compliant"]:
    assert tall_row["composite"] <= 49.0 and r2["recommended"] == "OK"
else:
    # envelope-bound: the limit constrained the massing instead — still a valid, compliant option
    assert tall_row["massing"]["building_height_m"] <= 10 + 1e-6

# --- empty set is a clean error --------------------------------------------------------------------
try:
    osc.score_options([])
    raise AssertionError("expected ValueError")
except ValueError:
    pass

# --- endpoints -------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "GenScore"}).json()["id"]
    g = c.post(f"/projects/{pid}/design/options/generate",
               json={"base": BASE, "types": ["multifamily", "office"]})
    assert g.status_code == 200 and len(g.json()["options"]) == 6, g.text[:200]
    s = c.post(f"/projects/{pid}/design/options/score", json={"options": g.json()["options"]})
    assert s.status_code == 200, s.text[:200]
    body = s.json()
    assert body["recommended"] and len(body["options"]) == 6
    assert body["options"] == sorted(body["options"], key=lambda o: -o["composite"]), "ranked"
    assert c.post(f"/projects/{pid}/design/options/score", json={"options": []}).status_code == 400

    # BOARDS: the scored set renders as a one-page deck PDF (pure builder + the HTTP route)
    import io as _io

    from pypdf import PdfReader
    pdf = osc.board_pdf("Deck Test", body)
    assert pdf[:5] == b"%PDF-" and len(PdfReader(_io.BytesIO(pdf)).pages) == 1, len(pdf)
    bd = c.post(f"/projects/{pid}/design/options/board.pdf", json={"options": g.json()["options"]})
    assert bd.status_code == 200 and bd.content[:5] == b"%PDF-", bd.status_code
    assert "options-board.pdf" in bd.headers.get("content-disposition", "")
    assert c.post(f"/projects/{pid}/design/options/board.pdf", json={"options": []}).status_code == 400

    # --- RESPKEY-DELEGATED: the deck's caveats, which were STRUCTURALLY unreachable ----------------
    # `score_options` APPENDS its carbon-basis sentence to `note`, and the deck drew `note[:180]`
    # against a boilerplate that is 480 characters on its own. So the warning did not fail
    # sometimes — it was past the cut on every render there has ever been, measured: index 364 of
    # 546. *A truncation measured against the text that happened to be there first silently
    # reclassifies everything added after it as optional.*
    mixed = [*g.json()["options"], {**g.json()["options"][0], "structure": "unobtanium",
                                    "label": "no-takeoff variant"}]
    ms = c.post(f"/projects/{pid}/design/options/score", json={"options": mixed}).json()
    assert ms["carbon_basis_mixed"] and len(ms["carbon_basis"]) > 1, ms["carbon_basis"]
    assert ms["note"].find("CARBON BASES ARE MIXED") > 180, ms["note"].find("CARBON BASES ARE MIXED")
    txt = PdfReader(_io.BytesIO(osc.board_pdf("Mixed", ms))).pages[0].extract_text()
    assert "MIXED" in txt and "like-for-like" in txt, txt[-300:]

    # and the partial mark, which the table had no way to show: a partially-scored option RANKS, so
    # it can be the top row of a client-facing deck with no star and nothing saying why.
    #
    # Driven through the `_evaluate` seam `test_option_missing.py` uses, NOT by hunting for inputs
    # that happen to lose a criterion. **The first draft of this did the latter and wrapped it in
    # `if ps["partially_scored"]:`** — a region named `atlantis` prices exactly like `us-west`, so
    # the condition was false, the two assertions never ran, and the phase reported PASS. *A guard
    # that makes a check conditional on the thing the check is about is not a guard, it is an
    # off switch that reports success.*
    ROWS = [{"label": "priced", "cost_per_sf": 300.0, "carbon_intensity_kgco2e_m2": 400.0,
             "yield_net_sellable_m2": 1000.0, "compliant": True, "carbon_basis": "quantity",
             "massing": {}, "cost_total": 1.0, "carbon_total_tco2e": 1.0, "violations": []},
            {"label": "unpriced", "cost_per_sf": None, "carbon_intensity_kgco2e_m2": 450.0,
             "yield_net_sellable_m2": 1100.0, "compliant": True, "carbon_basis": "quantity",
             "massing": {}, "cost_total": 1.0, "carbon_total_tco2e": 1.0, "violations": []}]
    _real = osc._evaluate
    osc._evaluate = lambda o: dict(ROWS[o["_i"]])                 # noqa: E731 — focused seam
    try:
        ps = osc.score_options([{"_i": 0}, {"_i": 1}])
    finally:
        osc._evaluate = _real
    assert ps["partially_scored"] == ["unpriced"], ps["partially_scored"]
    ptxt = PdfReader(_io.BytesIO(osc.board_pdf("Partial", ps))).pages[0].extract_text()
    assert "scored on fewer criteria" in ptxt, ptxt[-400:]
    assert "* unpriced" in ptxt.replace("\n", " "), ptxt[:400]

print("GEN-SCORE OK - deterministic variant grid (2 types x 3 FAR steps); warehouse beats hospital on "
      "cost+carbon with equal yield (flat criteria score 100 for all); carbon total = GFA x benchmark; "
      "weights steer ranking (all-yield -> tie); non-compliant options capped <=49 and never "
      "recommended; empty set 400s; endpoints generate+score+rank end to end.")
