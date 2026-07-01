"""Generic Excel/CSV module import: template download, preview (auto column->field mapping + coerced
sample + unmapped-required flag), and the two-step import (type coercion, required validation, one bad
row never aborts the batch). Exercises cost_code (the 'how do I create a cost code' path) + a currency
module. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_imports.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_imports.db"
os.environ["STORAGE_DIR"] = "./test_storage_imports"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_imports.db",):
    if os.path.exists(_f):
        os.remove(_f)

from openpyxl import Workbook                 # noqa: E402
from aec_api import imports                   # noqa: E402
from fastapi.testclient import TestClient     # noqa: E402
from aec_api.main import app                  # noqa: E402

# --- pure engine (parser + coercion need no module registry) ----------------
csv_bytes = b"Code,Description,Division\n03-3000,Concrete,03\n05-1200,Steel,05\n"
headers, body = imports.parse_table(csv_bytes, "codes.csv")
assert headers == ["Code", "Description", "Division"] and len(body) == 2, (headers, body)
assert imports._coerce("$1,250.50", "currency") == 1250.5
assert imports._coerce("03/14/2026", "date") == "2026-03-14"
assert imports._coerce("a;b, c", "multiselect") == ["a", "b", "c"]

with TestClient(app) as c:                                    # startup registers the module tables
    pid = c.post("/projects", json={"name": "Imp"}).json()["id"]

    # importable fields exclude rollups; auto-mapping matches by label
    fields = imports.importable_fields("cost_code")
    assert "code" in {f["name"] for f in fields} and "rollup" not in {f["type"] for f in fields}, fields
    mp = imports.suggest_mapping(headers, fields)
    assert mp["Code"] == "code" and mp["Division"] == "division", mp
    pv = imports.preview("cost_code", csv_bytes, "codes.csv")
    assert pv["row_count"] == 2 and pv["unmapped_required"] == [], pv
    assert pv["sample"][0] == {"code": "03-3000", "description": "Concrete", "division": "03"}, pv["sample"]

    # template download lists the field labels + marks required with *
    tpl = c.get(f"/projects/{pid}/modules/cost_code/import-template.csv")
    assert tpl.status_code == 200 and "Code *" in tpl.text, tpl.text[:120]

    # preview endpoint
    pr = c.post(f"/projects/{pid}/modules/cost_code/import/preview",
                files={"file": ("codes.csv", csv_bytes, "text/csv")}).json()
    assert pr["suggested_mapping"]["Code"] == "code" and pr["row_count"] == 2, pr

    # import with the suggested mapping -> 2 cost codes created
    import json as _json
    res = c.post(f"/projects/{pid}/modules/cost_code/import",
                 files={"file": ("codes.csv", csv_bytes, "text/csv")},
                 data={"mapping": _json.dumps(pr["suggested_mapping"])}).json()
    assert res["imported"] == 2 and res["error_count"] == 0, res
    recs = c.get(f"/projects/{pid}/modules/cost_code").json()
    assert len(recs) == 2, len(recs)
    assert {(r.get("data") or {}).get("code") for r in recs} == {"03-3000", "05-1200"}, recs

    # pagination: limit/offset page through the list server-side (2 records imported so far)
    assert len(c.get(f"/projects/{pid}/modules/cost_code?limit=1&offset=0").json()) == 1
    assert len(c.get(f"/projects/{pid}/modules/cost_code?limit=1&offset=1").json()) == 1
    assert len(c.get(f"/projects/{pid}/modules/cost_code?limit=10&offset=5").json()) == 0   # past the end

    # server-side search (SQL filter, not a Python post-scan): matches a `data` field value + ref/title
    assert len(c.get(f"/projects/{pid}/modules/cost_code?q=steel").json()) == 1        # data.description
    assert len(c.get(f"/projects/{pid}/modules/cost_code?q=03-3000").json()) == 1      # data.code
    assert len(c.get(f"/projects/{pid}/modules/cost_code?q=zzz-nomatch").json()) == 0

    # a row missing the required 'code' is reported, not created; good rows still import
    bad = b"Code,Description\n,Orphan desc\n09-2900,Gypsum\n"
    res2 = c.post(f"/projects/{pid}/modules/cost_code/import",
                  files={"file": ("bad.csv", bad, "text/csv")},
                  data={"mapping": _json.dumps({"Code": "code", "Description": "description"})}).json()
    assert res2["imported"] == 1 and res2["error_count"] == 1, res2
    assert "missing required: code" in res2["errors"][0]["error"], res2["errors"]

    # XLSX round-trips too (owner_invoice has a currency 'amount' + required 'number')
    wb = Workbook(); ws = wb.active
    ws.append(["Invoice No", "Amount", "Period"])
    ws.append(["INV-001", "$2,400,000", "2026-03-01"])
    buf = io.BytesIO(); wb.save(buf)
    prx = c.post(f"/projects/{pid}/modules/owner_invoice/import/preview",
                 files={"file": ("inv.xlsx", buf.getvalue(),
                                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}).json()
    assert prx["row_count"] == 1, prx
    assert prx["sample"][0].get("amount") == 2_400_000.0, prx["sample"]      # currency coerced from XLSX

print("IMPORTS OK - importable-fields excludes rollups; CSV+XLSX parse; auto column->field mapping by "
      "name/label; type coercion (currency/date/multiselect); template download; preview + two-step "
      "import create records (cost_code); a missing-required row is reported (not created) without "
      "aborting the batch")
