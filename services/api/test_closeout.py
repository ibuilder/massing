"""Turnover/closeout deliverables: the closeout package ZIP + module-log PDF.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_closeout.py"""
import io
import os
import zipfile

os.environ["DATABASE_URL"] = "sqlite:///./test_closeout.db"
os.environ["STORAGE_DIR"] = "./test_storage_closeout"
os.environ["IFC_DIR"] = "./test_ifc_closeout"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_closeout.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

H = {"X-User": "gc"}

with TestClient(app) as c:
    # em-dash in the name: regression for the closeout-package 500 — a non-latin-1 char in the
    # Content-Disposition filename used to crash the download (HTTP headers are latin-1).
    pid = c.post("/projects", json={"name": "Turnover Tower — Ünit 5"}, headers=H).json()["id"]
    # a generated model so the package has an as-built IFC + COBie/QTO/spaces
    g = c.post(f"/projects/{pid}/generate/massing",
               json={"lot_width": 30, "lot_depth": 20, "far": 2.0, "units": True}, headers=H)
    assert g.status_code == 200, g.text

    # closeout records (subject alias fills each module's title field)
    for mod, subj in [("commissioning", "HVAC Cx"), ("om_manual", "O&M"), ("warranty", "Roof 10yr"),
                      ("as_built", "Structural"), ("asset_register", "AHU-1"),
                      ("completion_certificate", "Substantial completion")]:
        r = c.post(f"/projects/{pid}/modules/{mod}", json={"data": {"subject": subj}}, headers=H)
        assert r.status_code == 201, (mod, r.text)
    # a couple RFIs for the log
    for s in ("Beam clash", "Door mismatch"):
        c.post(f"/projects/{pid}/modules/rfi", json={"data": {"subject": s, "question": "?"}}, headers=H)

    # --- closeout package ZIP -------------------------------------------------
    z = c.get(f"/projects/{pid}/closeout/package.zip", headers=H)
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip", z.status_code
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    names = zf.namelist()
    assert "as-built/model.ifc" in names, names
    assert "data/cobie.xlsx" in names and "data/qto.xlsx" in names and "data/spaces.xlsx" in names, names
    assert "report/status.pdf" in names, names
    assert "closeout/manifest.json" in names, names
    import json
    manifest = json.loads(zf.read("closeout/manifest.json"))
    assert manifest["closeout"]["warranty"][0]["title"] == "Roof 10yr", manifest["closeout"]["warranty"]
    assert len(manifest["closeout"]["completion_certificate"]) == 1

    # --- module log PDF -------------------------------------------------------
    log = c.get(f"/projects/{pid}/modules/rfi/log.pdf", headers=H)
    assert log.status_code == 200 and log.content[:4] == b"%PDF", log.status_code
    assert len(log.content) > 800, len(log.content)

    # --- COBie enrichment: closeout records fold into the workbook ------------
    import io as _io

    import openpyxl  # ships with the xlsx writer
    cobie = c.get(f"/projects/{pid}/exports/cobie.xlsx", headers=H)
    assert cobie.status_code == 200, cobie.text
    wb = openpyxl.load_workbook(_io.BytesIO(cobie.content))
    assert "Warranty" in wb.sheetnames and "System" in wb.sheetnames, wb.sheetnames
    assert "Asset" in wb.sheetnames and "Document" in wb.sheetnames, wb.sheetnames
    # model-derived COBie tabs incl. the new Contact / Zone / System spatial-and-functional groupings
    assert {"Contact", "Facility", "Floor", "Space", "Zone", "Type", "Component", "System"} <= set(wb.sheetnames), wb.sheetnames
    # the commissioning-derived System row survives the merge with the (model-derived) System tab
    sysvals = [str(cell.value) for row in wb["System"].iter_rows() for cell in row if cell.value]
    assert any("HVAC Cx" in v for v in sysvals), sysvals

    # --- warranty expiry tracking ---------------------------------------------
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=30)).isoformat()
    past = (date.today() - timedelta(days=5)).isoformat()
    c.post(f"/projects/{pid}/modules/warranty", json={"data": {"name": "HVAC 1yr", "vendor": "Acme", "expires": soon}}, headers=H)
    c.post(f"/projects/{pid}/modules/warranty", json={"data": {"name": "Sealant", "vendor": "Bo", "expires": past}}, headers=H)
    w = c.get(f"/projects/{pid}/warranties/expiring?within_days=90", headers=H).json()
    assert any(x["name"] == "HVAC 1yr" for x in w["expiring"]), w["expiring"]
    assert any(x["name"] == "Sealant" for x in w["expired"]), w["expired"]

    # --- compliance expiry: COI + permit on the canonical `expires` date ------
    c.post(f"/projects/{pid}/modules/coi", json={"data": {"vendor": "SubGuard Ins", "expires": soon}}, headers=H)
    c.post(f"/projects/{pid}/modules/permit", json={"data": {"name": "Building Permit", "expires": past, "status": "Issued"}}, headers=H)
    # a CLOSED permit is ignored even if its expires date is past
    c.post(f"/projects/{pid}/modules/permit", json={"data": {"name": "Old Demo Permit", "expires": past, "status": "Closed"}}, headers=H)
    comp = c.get(f"/projects/{pid}/compliance/expiring?within_days=30", headers=H).json()
    assert any(x["name"] == "SubGuard Ins" and x["module"] == "coi" for x in comp["expiring"]), comp["expiring"]
    assert any(x["name"] == "Building Permit" and x["module"] == "permit" for x in comp["expired"]), comp["expired"]
    assert not any(x["name"] == "Old Demo Permit" for x in comp["expired"] + comp["expiring"]), "closed permit must be ignored"
    assert comp["count"] == len(comp["expired"]) + len(comp["expiring"])

    # --- EXPIRY-UNDATED ----------------------------------------------------------------------
    # Every assertion above supplies a well-formed ISO date, which is why this shipped: *every
    # test of the engine supplied its own inputs.*
    #
    # ① THE WRITE IS NOW REFUSED, and that is the primary fix. `12/31/2026` is the ordinary way a
    # US contractor writes a date; it was accepted into `coi.expires`, a field the module marks
    # REQUIRED, across 136 `date` fields in 87 of 139 modules read by ~70 `fromisoformat` call
    # sites. A field whose declared type is `date` and whose validation was nothing is a field the
    # whole tree reads as optional.
    bad = c.post(f"/projects/{pid}/modules/coi",
                 json={"data": {"vendor": "US Format Ins", "expires": "12/31/2026"}}, headers=H)
    assert bad.status_code == 422 and "ISO-8601" in bad.text, (bad.status_code, bad.text)
    # ...and it accepts EXACTLY what the readers accept, a full timestamp included, because
    # `fromisoformat(str(v)[:10])` is what every consumer does. A validator stricter than its
    # readers refuses data that works; one looser leaves the defect in place.
    ok_ts = c.post(f"/projects/{pid}/modules/coi",
                   json={"data": {"vendor": "Timestamp Ins", "expires": "2026-11-02T00:00:00Z"}},
                   headers=H)
    assert ok_ts.status_code in (200, 201), ok_ts.text

    # ② THE READER STILL HAS TO COPE, because rows stored before this rule hold bad dates. The
    # fixture rewrites a stored blob rather than posting, which is exactly what a legacy row or a
    # CSV import looks like from the window's side — and is the only way to get one now.
    from sqlalchemy import select as _sel
    from sqlalchemy import update as _upd

    from aec_api.db import SessionLocal as _SL
    from aec_api.modules import TABLES as _T

    def _store_expires(key: str, rid: str, value) -> None:
        t = _T[key]
        with _SL() as _db:
            cur = _db.execute(_sel(t.c.data).where(t.c.id == rid)).scalar() or {}
            _db.execute(_upd(t).where(t.c.id == rid).values(data={**cur, "expires": value}))
            _db.commit()

    legacy = c.post(f"/projects/{pid}/modules/permit",
                    json={"data": {"name": "Legacy US Permit", "status": "Issued",
                                   "expires": "2026-12-31"}}, headers=H).json()
    blankp = c.post(f"/projects/{pid}/modules/permit",
                    json={"data": {"name": "Blank Date Permit", "status": "Issued",
                                   "expires": "2026-12-31"}}, headers=H).json()
    _store_expires("permit", legacy["id"], "12/31/2026")     # present and unreadable
    _store_expires("permit", blankp["id"], "")               # required, yet blank on an old row

    comp2 = c.get(f"/projects/{pid}/compliance/expiring?within_days=30", headers=H).json()
    cov = comp2["coverage"]
    assert cov["missing_date"] == 1 and cov["unreadable_date"] == 1, cov
    assert cov["unevaluated"] == 2, cov
    # THE RECONCILIATION IS THE DESIGN: coverage that adds up to the population is checkable, and
    # coverage that does not is just another number somebody prints.
    assert (cov["considered"] + cov["missing_date"] + cov["unreadable_date"] + cov["skipped"]
            == cov["population"]), cov
    assert cov["skipped"] == 1 and "closed permit" in cov["skipped_reason"], cov
    # the two causes are NAMED rather than summed — they ask different things of whoever reads it
    assert "no expiry date" in cov["reason"] and "cannot read" in cov["reason"], cov
    assert "ISO-8601" in cov["reason"], cov
    # and neither leaked into a window
    assert not any(x.get("expires") in ("12/31/2026", "") for x in comp2["expired"] + comp2["expiring"])

    # the same question on the warranty window. `warranty.expires` is NOT required, so a warranty
    # with no date is ordinary rather than legacy — which is why `closeout.warranty_rollup` has
    # always counted `no_expiry` while this window counted nothing.
    # Measured as a DELTA, because this file's own closeout fixture at the top already contains an
    # undated warranty and nothing had ever reported it — which is the finding in miniature. An
    # absolute would also pin somebody else's fixture, and the next person to add a record there
    # would be told their change broke an expiry window.
    w_before = c.get(f"/projects/{pid}/warranties/expiring?within_days=90", headers=H).json()["coverage"]
    c.post(f"/projects/{pid}/modules/warranty", json={"data": {"name": "No date at all"}}, headers=H)
    wlegacy = c.post(f"/projects/{pid}/modules/warranty",
                     json={"data": {"name": "Legacy US warranty", "expires": "2027-01-05"}},
                     headers=H).json()
    _store_expires("warranty", wlegacy["id"], "1/5/2027")
    w2 = c.get(f"/projects/{pid}/warranties/expiring?within_days=90", headers=H).json()
    wcov = w2["coverage"]
    assert wcov["missing_date"] - w_before["missing_date"] == 1, (w_before, wcov)
    assert wcov["unreadable_date"] - w_before["unreadable_date"] == 1, (w_before, wcov)
    assert w_before["missing_date"] >= 1, ("the fixture above lost its undated warranty, so the "
                                           "delta below is no longer measuring a pre-existing one",
                                           w_before)
    assert wcov["considered"] + wcov["unevaluated"] == wcov["population"], wcov
    # `total_warranties` was the ONLY number here, and it made the omission worse rather than
    # visible: two empty lists beside a count of 40 reads as "40 on file, none lapsing".
    assert wcov["population"] == w2["total_warranties"], (wcov, w2["total_warranties"])
    assert "skipped" not in wcov, wcov          # no exclusion of its own, so no phantom bucket

    # EVERY-OF-NOTHING: an empty register must not read as "every record carries a date"
    empty = c.post("/projects", json={"name": "No records yet"}, headers=H).json()["id"]
    ecov = c.get(f"/projects/{empty}/compliance/expiring", headers=H).json()["coverage"]
    assert ecov["population"] == 0 and ecov["unevaluated"] == 0, ecov
    assert ecov["reason"] == "no records of this kind exist", ecov

    # --- multi-period pay app + lien waiver (realistic flow: bill -> waiver -> advance) ---
    c.post(f"/projects/{pid}/modules/sov", json={"data": {"item_no": "01", "description": "Concrete",
           "scheduled_value": 1_000_000, "completed_this": 250_000, "retainage_pct": 5}}, headers=H)
    # period 1 lien waiver = current payment due (completed - retainage)
    lw = c.post(f"/projects/{pid}/cost/lien-waiver", json={"app_no": 1, "vendor": "Concrete Co"}, headers=H)
    assert lw.status_code == 201 and lw.json()["amount"] == 237_500, lw.text
    # advance the period: this -> prev, ready for application no. 2.
    #
    # PAY-APP retired `/cost/pay-app/advance`, a SECOND implementation of this roll that this test
    # used to call, and the two did not agree: the retired one advanced every SOV row and counted
    # them all (`advanced_lines`), while this one touches only rows with work billed this period and
    # counts those (`lines_advanced`). It also returned a `next_application_no` derived from an
    # `application_no` field on the SOV lines, which nothing sets — the real next number comes from
    # `cost.build_application`, which counts the applications that exist. *Two implementations of one
    # money operation, disagreeing on both the count and the number, one of them dark.*
    adv = c.post(f"/projects/{pid}/cost/advance-period", headers=H).json()
    assert adv["lines_advanced"] == 1, adv
    g703 = c.get(f"/projects/{pid}/cost/g703", headers=H).json()
    assert g703["totals"]["prev"] == 250_000 and g703["totals"]["this"] == 0, g703["totals"]

print("CLOSEOUT OK - package.zip + log.pdf; COBie folds Warranty/System/Asset/Document tabs; "
      "warranty expiry tracking (expiring + expired); pay-app advance rolls this->prev; lien waiver")
