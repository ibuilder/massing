"""SCHED-CALC — deterministic calculated fields: the AST-whitelist evaluator (arithmetic, concat,
conditionals, coercion, and the security rails), schedule columns via /drawings/schedules/calc, and
module-record formulas via /modules/{key}/calc.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_calc_fields.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_calc_fields.db"
os.environ["STORAGE_DIR"] = "./test_storage_calcf"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_calc_fields.db"):
    os.remove("./test_calc_fields.db")

from aec_api import calc_fields as cf  # noqa: E402

# --- the evaluator: arithmetic, coercion, concat, conditionals -------------------------------------
row = {"Width (m)": "0.90", "Height (m)": "2.10", "Mark": "D01", "Level": "Level 1", "Cost": "1,250.50"}
assert cf.evaluate("width_m * height_m", row) == 0.9 * 2.1              # numeric strings auto-coerce
assert cf.evaluate('"DOOR-" + mark', row) == "DOOR-D01"                 # string concat via +
assert cf.evaluate("cost / 2", row) == 625.25                           # $ and , stripped
assert cf.evaluate('"tall" if height_m > 2 else "std"', row) == "tall"  # conditionals
assert cf.evaluate("round(width_m * height_m, 1)", row) == 1.9          # whitelisted functions
assert cf.evaluate("num(mark)", row) is None and cf.evaluate("text(cost)", row) == "1250.5"
assert cf.evaluate("width_m / 0", row) is None                          # divide-by-zero → empty cell
assert cf.evaluate("missing_field + 1", row) is None                    # unknown name → empty cell

# --- the security rails: no attributes/subscripts/lambdas/imports/power, complexity caps -----------
for bad in ("().__class__", "row['x']", "(lambda: 1)()", "__import__('os')", "2 ** 9999",
            "[x for x in y]", "open('x')", "min(1, key=len)"):
    assert cf.validate(bad) is not None, f"{bad!r} must be rejected"
assert cf.validate("a" * 501) is not None                               # length cap
assert cf.validate("1" + " + 1" * 120) is not None                      # node-count cap
assert cf.validate("width_m * height_m") is None                        # the good stuff passes
try:
    cf.check_calcs([{"name": "x", "expr": "().__class__"}])
    raise AssertionError("check_calcs must raise on a rejected expression")
except ValueError as e:
    assert "not allowed" in str(e), e

# --- table extension: {columns, rows} gets the calc columns appended -------------------------------
t = cf.add_calculated({"columns": ["Mark", "Width (m)"], "rows": [["D01", "0.9"], ["D02", "1.2"]]},
                      cf.check_calcs([{"name": "Double", "expr": "width_m * 2"}]))
assert t["columns"] == ["Mark", "Width (m)", "Double"] and t["rows"][1][2] == 2.4, t

# --- routes ----------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_ifc = Path(tempfile.gettempdir()) / "calc_fields_test.ifc"
massing.generate_blank_ifc(str(_ifc), name="Calc", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(str(_ifc))
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, m.by_type("IfcBuildingStorey")[0].Name)
edit.add_opening(m, w, width=0.9, height=2.1, kind="door")
m.write(str(_ifc))

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Calc"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()

    # schedules + a calculated area column on doors
    r = c.post(f"/projects/{pid}/drawings/schedules/calc",
               json={"doors": [{"name": "Area m²", "expr": "round(num(width_m) * num(height_m), 2)"}]})
    assert r.status_code == 200, r.text
    doors = r.json()["doors"]
    assert doors["columns"][-1] == "Area m²" and doors["calculated"] == ["Area m²"], doors["columns"]
    area_col = doors["columns"].index("Area m²")
    assert any(row[area_col] == round(0.9 * 2.1, 2) for row in doors["rows"]), doors["rows"]
    # a bad expression 422s with the field name in the message
    bad = c.post(f"/projects/{pid}/drawings/schedules/calc",
                 json={"doors": [{"name": "Evil", "expr": "().__class__"}]})
    assert bad.status_code == 422 and "Evil" in bad.json()["detail"], bad.text

    # module records + formulas over the field map (ref/title/workflow_state included)
    for inv in ({"number": "INV-1", "amount": 1000, "status": "paid"},
                {"number": "INV-2", "amount": 250, "status": "draft"}):
        assert c.post(f"/projects/{pid}/modules/owner_invoice", json={"data": inv}).status_code in (200, 201)
    mc = c.post(f"/projects/{pid}/modules/owner_invoice/calc", json={"calcs": [
        {"name": "with_tax", "expr": "round(amount * 1.0825, 2)"},
        {"name": "flag", "expr": '"✓ " + number if status == "paid" else number'}]})
    assert mc.status_code == 200, mc.text
    vals = {r["values"]["flag"]: r["values"]["with_tax"] for r in mc.json()["rows"]}
    assert vals["✓ INV-1"] == 1082.5 and vals["INV-2"] == 270.62, vals
    assert c.post(f"/projects/{pid}/modules/owner_invoice/calc",
                  json={"calcs": [{"name": "x", "expr": "open('f')"}]}).status_code == 422
    assert c.post(f"/projects/{pid}/modules/owner_invoice/calc", json={"calcs": []}).status_code == 422

if _ifc.exists():
    _ifc.unlink()

print("SCHED-CALC OK - deterministic calculated fields: numeric strings auto-coerce (width_m*height_m "
      "over a text table), + concatenates strings, conditionals/round/num/text work, divide-by-zero and "
      "unknown fields yield an empty cell; the AST whitelist rejects attribute access, subscripts, "
      "lambdas, __import__, **, comprehensions, open() and keyword args, with length + node-count caps; "
      "/drawings/schedules/calc appends validated formula columns to the computed door schedule (0.9x2.1 "
      "door -> 1.89 m², a bad expr 422s with its field name) and /modules/{key}/calc evaluates formulas "
      "over record field maps (tax + a status-conditional flag; empty or evil calc lists 422).")
