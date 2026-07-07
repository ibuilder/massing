"""Envelope code-compliance (D3): assemblies vs IECC 2021 climate-zone minimums.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_envelope.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_envelope.db"
os.environ["STORAGE_DIR"] = "./test_storage_envelope"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_envelope.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import envelope, reports  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- unit: the compliance checks ------------------------------------------------------------------
assert envelope.check_assembly("Wall", "4", r_value=20)["compliant"] is True     # R20 >= min R20 (zone 4)
assert envelope.check_assembly("Wall", "4", r_value=15)["compliant"] is False    # R15 < R20
assert envelope.check_assembly("Roof", "6", r_value=25)["compliant"] is False    # R25 < min R30 (zone 6)
w = envelope.check_assembly("Window", "5", u_factor=0.30)
assert w["compliant"] is True and w["required_max_u"] == 0.38, w                  # U0.30 <= max U0.38
assert envelope.check_assembly("Window", "5", u_factor=0.45)["compliant"] is False
assert envelope.check_assembly("Wall", "bad")["compliant"] is None               # invalid zone

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    def mk(data):
        r = c.post(f"/projects/{pid}/modules/envelope_assembly", json={"data": data})
        assert r.status_code == 201, r.text[:160]

    mk({"name": "Exterior wall", "element_type": "Wall", "climate_zone": "4", "r_value": 21})   # pass
    mk({"name": "Low roof", "element_type": "Roof", "climate_zone": "6", "r_value": 25})        # fail
    mk({"name": "Curtain wall glazing", "element_type": "Window", "climate_zone": "5", "u_factor": 0.30})  # pass

    a = c.get(f"/projects/{pid}/envelope/audit").json()
    assert a["total"] == 3 and a["checked"] == 3, a
    assert a["compliant"] == 2 and a["compliance_pct"] == round(200 / 3, 1), a

    chk = c.get(f"/projects/{pid}/envelope/check",
                params={"element_type": "Wall", "climate_zone": "7", "r_value": 30}).json()
    assert chk["compliant"] is True and chk["required_min_r"] == 29, chk       # zone 7 wall min R29

    assert "envelope" in {x["id"] for x in reports.catalog()}, "envelope missing from catalog"
    rep = c.get(f"/projects/{pid}/reports/envelope.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

print("ENVELOPE OK - IECC 2021 checks: wall R20@z4 pass / R15 fail; roof R25@z6 fail (min R30); window "
      "U0.30@z5 pass (max U0.38) / U0.45 fail; invalid zone -> None; register audit = 2/3 compliant "
      "(66.7%); single-check endpoint (zone-7 wall min R29); report PDF served")
