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

    # --- BASIS-UNREAD: `checked` is a SUBSET of `total`, and the response says which ------------
    #
    # `element_type` and `climate_zone` are both optional fields on the module, so registering an
    # assembly before dimensioning it is the normal order of work. The audit above has them equal,
    # which is why the divergence went unasserted for as long as it did and why the only consumer
    # could print `4/4 assemblies compliant (100.0%)` over a register of forty.
    mk({"name": "Party wall", "element_type": "Wall", "r_value": 19})            # no climate zone
    mk({"name": "Lobby storefront", "element_type": "Window", "climate_zone": "4"})  # no U or R
    mk({"name": "Mystery", "element_type": "Trellis", "climate_zone": "4"})      # not an envelope type

    a = c.get(f"/projects/{pid}/envelope/audit").json()
    assert a["total"] == 6 and a["checked"] == 3, a
    assert a["compliant"] == 2 and a["compliance_pct"] == round(200 / 3, 1), a
    # The population the percentage is over is RECOVERABLE from the response — a consumer that reads
    # `checked` and not `total` cannot tell this apart from a fully dimensioned register.
    assert a["total"] - a["checked"] == 3, a
    # The sharpest form of the defect: the register DOUBLED and the shipped headline is unchanged.
    assert f"{a['compliant']}/{a['checked']} assemblies compliant ({a['compliance_pct']}%)" \
        == "2/3 assemblies compliant (66.7%)", a

    unruled = [r for r in a["results"] if r["compliant"] is None]
    assert len(unruled) == 3, unruled
    # Each one NAMES what is missing, rather than arriving as an indistinguishable blank. The three
    # reasons are different kinds of problem: a data-entry gap, a missing submittal value, and a
    # type the IECC tables do not cover at all.
    assert {r["issue"] for r in unruled} == {
        "no valid climate zone (1–8)", "no U-factor or R-value given",
        "unknown element type 'Trellis'"}, [r["issue"] for r in unruled]

    # A row with no verdict can still carry the REQUIREMENT: the zone is readable, so the engine
    # knows what the assembly needs and only not what it has. That half is the number somebody has
    # to go and find, and it is why the card shows `U-0.38 max / —` rather than a bare dash.
    lobby = next(r for r in unruled if r["name"] == "Lobby storefront")
    assert lobby["required_max_u"] == 0.38 and lobby["provided_u"] is None, lobby
    # And the mirror case: an unreadable zone returns BEFORE a requirement is looked up, so there is
    # no minimum to show — the raw `r_value` is all there is.
    party = next(r for r in unruled if r["name"] == "Party wall")
    assert "required_min_r" not in party and party["r_value"] == 19.0, party

    # The per-assembly numbers that make a FAIL actionable. `margin` is signed as HEADROOM in both
    # families — positive is compliant by that much — which is what lets one column carry both.
    roof = next(r for r in a["results"] if r["name"] == "Low roof")
    assert roof["required_min_r"] == 30 and roof["provided_r"] == 25.0 and roof["margin"] == -5.0, roof
    glz = next(r for r in a["results"] if r["name"] == "Curtain wall glazing")
    assert glz["required_max_u"] == 0.38 and glz["provided_u"] == 0.3 and glz["margin"] == 0.08, glz

    # Nothing evaluable is NOT an empty register, and the response distinguishes them. The card read
    # `checked` alone and fell to an empty-state branch here, reporting "no envelope assemblies
    # registered" over every row in the project.
    pid2 = c.post("/projects", json={"name": "Undimensioned"}).json()["id"]
    for _i in range(4):
        r = c.post(f"/projects/{pid2}/modules/envelope_assembly",
                   json={"data": {"name": f"W{_i}", "element_type": "Wall"}})
        assert r.status_code == 201, r.text[:160]
    b = c.get(f"/projects/{pid2}/envelope/audit").json()
    assert b["total"] == 4 and b["checked"] == 0 and b["compliance_pct"] is None, b
    empty = c.get(f"/projects/{c.post('/projects', json={'name': 'Empty'}).json()['id']}"
                  f"/envelope/audit").json()
    assert empty["total"] == 0 and empty["checked"] == 0, empty
    assert b["total"] != empty["total"], "a register with rows and nothing evaluable must not " \
                                         "report the same population as one with no rows"

    # The engine states its own basis, on every response. A screen that renders a compliance
    # percentage without it is showing a first-pass screen as though it were an energy model.
    assert "IECC 2021" in a["note"] and "not a stamped energy model" in a["note"], a["note"]

    chk = c.get(f"/projects/{pid}/envelope/check",
                params={"element_type": "Wall", "climate_zone": "7", "r_value": 30}).json()
    assert chk["compliant"] is True and chk["required_min_r"] == 29, chk       # zone 7 wall min R29

    assert "envelope" in {x["id"] for x in reports.catalog()}, "envelope missing from catalog"
    rep = c.get(f"/projects/{pid}/reports/envelope.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

print("ENVELOPE OK - IECC 2021 checks: wall R20@z4 pass / R15 fail; roof R25@z6 fail (min R30); window "
      "U0.30@z5 pass (max U0.38) / U0.45 fail; invalid zone -> None; register audit = 2/3 compliant "
      "(66.7%); single-check endpoint (zone-7 wall min R29); report PDF served")
print("BASIS-UNREAD OK - checked (3) is a subset of total (6) and the gap is recoverable; all 3 "
      "unruled assemblies name their issue; a readable zone keeps the requirement with no provided "
      "value; margin is signed as headroom both ways (roof -5.0 R, glazing +0.08 U); 4 rows with "
      "nothing evaluable does not report as 0 rows; the note states IECC 2021 and 'not a stamped "
      "energy model'")
