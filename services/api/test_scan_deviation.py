"""Scan-to-BIM deviation — synthetic points vs a reference surface, plus endpoint 409/400 smokes.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_scan_deviation.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_scan_deviation.db"
os.environ["STORAGE_DIR"] = "./test_storage_scan_deviation"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_scan_deviation.db",):
    if os.path.exists(_f):
        os.remove(_f)

import numpy as np  # noqa: E402

from aec_api import scan_deviation as sd  # noqa: E402

# Reference: a flat 11x11 grid on the z=0 plane spanning [0,1]x[0,1].
gx, gy = np.meshgrid(np.linspace(0, 1, 11), np.linspace(0, 1, 11))
ref = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])

# Scan points: 8 sit ~exactly on the plane (within tol), 2 float far above it (out of tol).
tol = 0.05
on = np.array([[0.1, 0.1, 0.0], [0.2, 0.3, 0.01], [0.5, 0.5, -0.02], [0.7, 0.2, 0.03],
               [0.9, 0.9, 0.0], [0.3, 0.8, 0.04], [0.6, 0.4, -0.01], [0.4, 0.6, 0.02]])
off = np.array([[0.5, 0.5, 0.5], [0.2, 0.2, 0.3]])   # 0.5m and 0.3m off -> >3x tol
pts = np.vstack([on, off])

res = sd.analyze(pts, ref, tolerance=tol)
assert res["point_count"] == 10, res["point_count"]
assert res["within_tolerance"] == 8, res            # the 8 near-plane points
assert res["out_of_tolerance"] == 2, res
assert res["within_pct"] == 80.0, res["within_pct"]
assert res["max_deviation"] >= 0.49, res["max_deviation"]      # the 0.5m outlier
assert abs(res["p95_deviation"]) > tol, res["p95_deviation"]
# histogram bands sum to the point count; the 2 outliers land in >3x tol
assert sum(h["count"] for h in res["histogram"]) == 10, res["histogram"]
assert res["histogram"][-1]["count"] == 2, res["histogram"]
print(f"analyze: within {res['within_pct']}%  mean={res['mean_deviation']}  "
      f"max={res['max_deviation']}  hist={[h['count'] for h in res['histogram']]}")

# empty inputs degrade gracefully
empty = sd.analyze(np.zeros((0, 3)), ref, tolerance=tol)
assert empty["within_pct"] is None and "error" in empty, empty

# parse_point_cloud: XYZ + CSV + comment/blank-line tolerance
text = "# header\n0 0 0\n1.5, 2.5, 3.5\n\n// note\nbad line here\n4 5 6 255 128 0\n"
parsed = sd.parse_point_cloud(text)
assert parsed.shape == (3, 3), parsed.shape          # 3 valid rows; RGB tail on the last is ignored
assert np.allclose(parsed[1], [1.5, 2.5, 3.5]), parsed[1]
print(f"parse_point_cloud: {parsed.shape[0]} points parsed")

# endpoint: no source IFC -> 409
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "P"}).json()["id"]
    r = tc.post(f"/projects/{pid}/scan/deviation",
                files={"file": ("scan.xyz", b"0 0 0\n1 1 1\n", "text/plain")})
    assert r.status_code == 409, (r.status_code, r.text[:160])

print("test_scan_deviation OK")
