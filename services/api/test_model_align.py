"""R41-MODEL-ALIGN — the yaw fit, its acceptance rule, and the route that proposes it.

The geometry is one shapely call; the JUDGEMENT is the work, so most of this file is about when a fit
is refused. A true minimum-area rectangle sat 37° off a real building's walls to buy 14% of area —
arithmetically optimal, visibly broken — so the threshold buys a *wall-parallel* box rather than the
*smallest* one, by refusing the margin where those two answers disagree.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_model_align.py
"""
from __future__ import annotations

import math
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_model_align.db"
os.environ["STORAGE_DIR"] = "./test_storage_model_align"
os.environ["IFC_DIR"] = "./test_ifc_model_align"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_model_align.db"):
    os.remove("./test_model_align.db")

import sys  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, "src")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_data import align, drawings, massing  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


def rect(w: float, d: float, deg: float, n: int = 40) -> np.ndarray:
    """A rectangle sampled along its edges, rotated `deg` about its centre."""
    t = np.linspace(0, 1, n)[:, None]
    c = np.array([[0, 0], [w, 0], [w, d], [0, d]], dtype=float) - [w / 2, d / 2]
    pts = np.vstack([c[i] + (c[(i + 1) % 4] - c[i]) * t for i in range(4)])
    r = math.radians(deg)
    return pts @ np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]]).T


# --- the case the entry was written from ---------------------------------------------------------
# R41-MODEL-ALIGN records a 54 x 78 m building whose axis-aligned box is 90.1 x 94.8 m — "~2x the true
# area". Reproducing those exact numbers is what says this implements the thing that was measured,
# rather than something that merely looks plausible.
f = align.fit_yaw(rect(54, 78, 37))
check("a 54 x 78 m building at 37 deg is ACCEPTED", f is not None and f.accepted, f)
check("  the AABB is the 90.1 x 94.8 box the entry measured",
      abs(f.aabb_area - 90.1 * 94.8) / (90.1 * 94.8) < 0.01, f.aabb_area)
check("  ...which is ~2x the true area, exactly as recorded",
      1.95 < f.aabb_area / f.obb_area < 2.10, f.aabb_area / f.obb_area)
check("  the true extent is recovered, not the bounding box",
      abs(f.extent[0] - 78) < 0.1 and abs(f.extent[1] - 54) < 0.1, f.extent)

# The sign is the part a user sees and the easiest to get backwards: a building sitting AT +37 needs
# -37 applied to it. A fit that returned +37 would rotate it to 74 and look like a bug in the viewer.
check("the yaw to APPLY is the negative of the angle the building sits at",
      abs(f.fitted_deg - 37) < 0.01 and abs(f.yaw_deg + 37) < 0.01, (f.fitted_deg, f.yaw_deg))

# --- the refusals, which are the actual feature ---------------------------------------------------
g = align.fit_yaw(rect(90, 95, 0))
check("an ALREADY-ALIGNED building is refused — there is nothing to fix",
      g is not None and not g.accepted and g.saving < 0.01, g)
check("  ...and the refusal states the margin rather than only saying no",
      "wrong answer" in (g.reason or ""), g.reason)

# The cautionary case from the entry: a marginal saving must NOT be proposed, because at that margin
# the smallest rectangle and the wall-parallel one are different rectangles.
marginal = next((x for x in (align.fit_yaw(rect(80, 84, deg)) for deg in range(1, 45))
                 if x and 0.10 <= x.saving <= 0.19), None)
check("a MARGINAL saving is refused — the 37-deg-for-14% case the entry warns about",
      marginal is not None and not marginal.accepted,
      marginal and (marginal.saving, marginal.accepted))
check("  the threshold is the documented 20%", align.MIN_AREA_SAVING == 0.20)
# The twin: the threshold must be a real dial, not a constant nothing reads.
check("  ...and it is honoured, not hard-coded — a lower bar accepts the same shape",
      marginal is not None and align.fit_yaw(rect(80, 84, 1), min_saving=0.0).accepted)

# --- angle normalisation --------------------------------------------------------------------------
check("88 deg is reported as -2, because a rectangle is symmetric every 90",
      abs(align.fit_yaw(rect(54, 78, 88)).fitted_deg + 2) < 0.01)
check("  _normalise folds into (-45, 45]",
      align._normalise(135) == 45.0 and align._normalise(-53) == 37.0,
      (align._normalise(135), align._normalise(-53)))

# --- degenerate input -----------------------------------------------------------------------------
check("two points cannot bound an area -> None", align.fit_yaw([[0, 0], [1, 1]]) is None)
check("a straight line has no area to save -> None",
      align.fit_yaw([[i, 0.0] for i in range(20)]) is None)
check("NaN vertices are dropped rather than poisoning the box",
      align.fit_yaw(np.vstack([rect(54, 78, 37), [[float("nan"), 0.0]]])) is not None)

# --- against REAL geometry, not a synthetic outline ------------------------------------------------
# A generated massing block has exactly FOUR unique plan vertices. An earlier draft required eight,
# which would have silently refused the commonest shape in the product by returning None.
_m = massing.compute_massing({"lot_width": 30, "lot_depth": 20, "far": 2.0,
                              "floor_to_floor": 3.5, "height_limit": 14})
_ifc = Path(tempfile.gettempdir()) / "test_model_align.ifc"
massing.generate_ifc(_m, str(_ifc), name="Align")
import ifcopenshell  # noqa: E402

_model = ifcopenshell.open(str(_ifc))
pts = drawings.plan_points(_model)
check("plan_points returns the model's plan vertices", pts is not None and len(pts) > 0,
      None if pts is None else len(pts))
check("  a simple extruded block has FOUR unique plan points — the floor must admit it",
      len(np.unique(pts, axis=0)) == 4, len(np.unique(pts, axis=0)))
real = align.fit_yaw(pts)
check("  a square-on block is refused", real is not None and not real.accepted, real)

r = math.radians(37)
rot = pts @ np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]]).T
real_rot = align.fit_yaw(rot)
check("  the SAME block rotated 37 deg is accepted, with the extent preserved",
      real_rot is not None and real_rot.accepted
      and abs(real_rot.extent[0] - real.extent[0]) < 0.05,
      real_rot)

# --- the route ------------------------------------------------------------------------------------
with TestClient(app) as c:
    c.headers.update({"X-User": "aligner@test"})
    pid = c.post("/projects", json={"name": "Align"}).json()["id"]
    ifc_bytes = _ifc.read_bytes()
    mid = c.post(f"/projects/{pid}/models",
                 files={"file": ("STR.ifc", ifc_bytes, "application/octet-stream")},
                 data={"discipline": "STR"}).json()["id"]

    r = c.get(f"/projects/{pid}/models/{mid}/alignment-fit")
    check("the fit route answers", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    body = r.json() if r.status_code == 200 else {}
    check("  it reports a fit for a real model", body.get("fit") is not None, body)
    check("  ...and refuses this one, because it is already square-on",
          body.get("fit", {}).get("accepted") is False, body.get("fit"))
    check("  ...and says why, in words a user can act on",
          "wrong answer" in (body.get("fit", {}).get("reason") or ""), body.get("fit"))
    check("  the source file is untouched — a proposal, never an edit",
          body.get("applied") is False and "propos" in (body.get("note") or "").lower(), body)

    r = c.get(f"/projects/{pid}/models/does-not-exist/alignment-fit")
    check("an unknown model is a 404", r.status_code == 404, r.status_code)
    r = c.get(f"/projects/does-not-exist/models/{mid}/alignment-fit")
    check("an unknown project is a 404", r.status_code == 404, r.status_code)

for _f in ("./test_model_align.db",):
    if os.path.exists(_f):
        try:
            os.remove(_f)
        except OSError:
            pass

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("test_model_align OK")
