"""distwaterfall.scenario — the investor-allocation wrapper over run_waterfall (the last of the
audit-flagged untested engines; run_waterfall's math itself is pinned in test_waterfall).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_distwaterfall.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_distwf.db"
os.environ["STORAGE_DIR"] = "./test_storage_distwf"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_distwf.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Waterfall"}).json()["id"]

    # empty cap table → clean zeroed scenario with a note, never a phantom split
    z = c.post(f"/projects/{pid}/waterfall", json={"exit_amount": 1_000_000}).json()
    assert z["total_distributable"] == 0.0 and z["per_investor"] == [], z
    assert "No investors" in z["note"], z

    # cap table: two LPs (600k + 300k) + a GP (100k)
    for name, cls, commit in (("Alpha LP", "LP", 600_000), ("Beta LP", "LP", 300_000),
                              ("Sponsor", "GP", 100_000)):
        r = c.post(f"/projects/{pid}/modules/investor",
                   json={"data": {"investor": name, "investor_class": cls, "commitment": commit}})
        assert r.status_code == 201, r.text[:160]

    # a 5-year 2.0M exit through the default american waterfall
    w = c.post(f"/projects/{pid}/waterfall", json={
        "exit_amount": 2_000_000, "contribution_date": "2021-01-15", "exit_date": "2026-01-15"}).json()
    assert w["total_distributable"] == 2_000_000, w["total_distributable"]
    assert w["lp_contrib"] == 900_000 and w["gp_contrib"] == 100_000, w
    # dollar conservation across LP + GP
    assert abs(w["lp_distributions"] + w["gp_distributions"] - 2_000_000) < 0.02, w
    # IRRs/EMs computed and internally consistent (the tier MATH itself is pinned in test_waterfall;
    # here we lock the wrapper: LPs cleared their pref on a 2x deal, capital fully returned)
    assert w["lp_irr"] is not None and w["lp_irr"] > 0.08, w["lp_irr"]
    assert w["gp_irr"] is not None, w["gp_irr"]
    assert abs(w["lp_equity_multiple"] - w["lp_distributions"] / w["lp_contrib"]) < 0.01, w
    assert abs(w["gp_equity_multiple"] - w["gp_distributions"] / w["gp_contrib"]) < 0.01, w
    assert w["lp_unreturned"] == 0.0, w["lp_unreturned"]
    # per-investor allocation is pro-rata within the LP class (Alpha 2× Beta), sorted desc
    per = {x["investor"]: x["distribution"] for x in w["per_investor"]}
    assert abs(per["Alpha LP"] - 2 * per["Beta LP"]) < 0.02, per
    assert abs(sum(per.values()) - 2_000_000) < 0.05, per
    assert [x["distribution"] for x in w["per_investor"]] == sorted(
        (x["distribution"] for x in w["per_investor"]), reverse=True), w["per_investor"]

    # multi-period distributable with SHORT dates → periods synthesized annually from the base date
    m = c.post(f"/projects/{pid}/waterfall", json={
        "distributable": [500_000, 500_000, 1_500_000], "contribution_date": "2022-06-10"}).json()
    assert m["total_distributable"] == 2_500_000 and len(m["periods"]) == 3, m
    assert abs(m["lp_distributions"] + m["gp_distributions"] - 2_500_000) < 0.02, m

    # pref-rate override reaches the engine and is echoed back
    o = c.post(f"/projects/{pid}/waterfall",
               json={"exit_amount": 1_000_000, "pref_rate": 0.10}).json()
    assert o["pref_rate"] == 0.10, o["pref_rate"]

    # --- WF-BASIS: WHICH capital base the whole waterfall ran on ----------------------------------
    #
    # `lp_contrib = sum(contributed) or lp_commit`, so the pref, the return of capital, both IRRs and
    # both equity multiples are computed against either contributed capital or — silently — the
    # commitment. **This file's own fixture above has been exercising the fallback since it was
    # written**: not one of its three investors carries a `contributed` figure, so every assertion
    # above is on the committed basis and nothing said so. *A test fixture that only ever walks the
    # fallback path cannot notice that there are two.*
    assert w["lp_basis"] == "committed" and w["gp_basis"] == "committed", (w["lp_basis"], w["gp_basis"])
    assert w["lp_commitment"] == 900_000 and w["gp_commitment"] == 100_000, w
    assert w["lp_contrib"] == w["lp_commitment"], (w["lp_contrib"], w["lp_commitment"])

    # Fund the cap table and the basis flips, with the SAME figures — which is the finding: a deal
    # nobody has funded and one fully funded are byte-identical except for this one field.
    for rec in c.get(f"/projects/{pid}/modules/investor").json():
        amt = (rec.get("data") or {}).get("commitment")
        assert c.patch(f"/projects/{pid}/modules/investor/{rec['id']}",
                       json={"contributed": amt}).status_code < 300, rec["id"]
    f = c.post(f"/projects/{pid}/waterfall", json={
        "exit_amount": 2_000_000, "contribution_date": "2021-01-15", "exit_date": "2026-01-15"}).json()
    assert f["lp_basis"] == "contributed" and f["gp_basis"] == "contributed", f
    assert f["lp_contrib"] == w["lp_contrib"] and f["gp_contrib"] == w["gp_contrib"], (f, w)
    assert f["lp_distributions"] == w["lp_distributions"], (f["lp_distributions"], w["lp_distributions"])
    assert f["lp_irr"] == w["lp_irr"], (f["lp_irr"], w["lp_irr"])

    # HALF called: the base halves, and the money moves. The promote is bigger and the LP IRR higher
    # on the identical exit — which is why the base belongs on the screen.
    for rec in c.get(f"/projects/{pid}/modules/investor").json():
        amt = (rec.get("data") or {}).get("commitment") or 0
        assert c.patch(f"/projects/{pid}/modules/investor/{rec['id']}",
                       json={"contributed": amt / 2}).status_code < 300
    h = c.post(f"/projects/{pid}/waterfall", json={
        "exit_amount": 2_000_000, "contribution_date": "2021-01-15", "exit_date": "2026-01-15"}).json()
    assert h["lp_basis"] == "contributed" and h["lp_contrib"] == 450_000, h
    assert h["gp_distributions"] > w["gp_distributions"], (h["gp_distributions"], w["gp_distributions"])
    assert h["lp_irr"] > w["lp_irr"], (h["lp_irr"], w["lp_irr"])

    # MIXED: the two sides fall back INDEPENDENTLY, so one waterfall can run on two bases.
    recs = c.get(f"/projects/{pid}/modules/investor").json()
    for rec in recs:
        if ((rec.get("data") or {}).get("investor_class") or "").upper().startswith("GP"):
            assert c.patch(f"/projects/{pid}/modules/investor/{rec['id']}",
                           json={"contributed": 0}).status_code < 300
    mx = c.post(f"/projects/{pid}/waterfall", json={"exit_amount": 2_000_000}).json()
    assert mx["lp_basis"] == "contributed" and mx["gp_basis"] == "committed", mx
    assert mx["gp_contrib"] == mx["gp_commitment"], (mx["gp_contrib"], mx["gp_commitment"])

    # --- the per-investor split runs on a DIFFERENT basis, and says so --------------------------
    #
    # `distribution` is pro-rata to COMMITMENT while the waterfall ran on contributed capital. The
    # allocation is deliberately NOT changed — which share a distribution follows is an operating-
    # agreement term — so both shares are published and the disagreement is named. WF-SPLIT holds
    # the decision.
    assert mx["split_basis"] == "commitment", mx["split_basis"]
    uneven = c.post("/projects", json={"name": "WF uneven"}).json()["id"]
    for name, cls, commit, got in (("LP Big", "LP", 800_000, 100_000),
                                   ("LP Small", "LP", 200_000, 200_000),
                                   ("Sponsor", "GP", 100_000, 100_000)):
        assert c.post(f"/projects/{uneven}/modules/investor", json={"data": {
            "investor": name, "investor_class": cls, "commitment": commit,
            "contributed": got}}).status_code == 201
    u = c.post(f"/projects/{uneven}/waterfall", json={"exit_amount": 2_000_000}).json()
    assert u["lp_basis"] == "contributed" and u["lp_contrib"] == 300_000, u
    big = next(x for x in u["per_investor"] if x["investor"] == "LP Big")
    small = next(x for x in u["per_investor"] if x["investor"] == "LP Small")
    # The measured injustice: LP Big funded a THIRD of the LP capital and takes 80% of the LP money,
    # because the split follows commitments.
    assert big["commitment_share"] == 0.8 and abs(big["contributed_share"] - 1 / 3) < 1e-4, big
    assert big["distribution"] > small["distribution"], (big, small)
    assert small["contributed"] > big["contributed"], (small, big)
    # ...and both of them are NAMED, so a screen can refuse to present the figure as settled.
    assert {m["investor"] for m in u["split_mismatch"]} == {"LP Big", "LP Small"}, u["split_mismatch"]
    # An agreed cap table reports no mismatch — otherwise the warning fires on every deal and
    # stops being read, which is what COMPTIER-DARK's always-on qualifier cost.
    assert f["split_mismatch"] == [], f["split_mismatch"]
    # No cap table: no basis at all, rather than a basis for a waterfall that did not run.
    assert z["lp_basis"] is None and z["gp_basis"] is None and z["split_mismatch"] == [], z

print("DISTWATERFALL OK - empty cap table zeroes with a note; 2.0M exit over 900k LP / 100k GP "
      "conserves every dollar, LP IRR clears the 8% pref with capital fully returned, EMs are "
      "internally consistent, and allocation is pro-rata within the LP class (Alpha=2xBeta, sorted "
      "desc); short dates synthesize annual periods (3 for 3 distributions); pref_rate override "
      "echoed. WF-BASIS: the basis is published per side and this file's own fixture had been "
      "walking the COMMITTED fallback since it was written — funding it flips `lp_basis` with "
      "byte-identical figures, half-funding it moves the promote and the IRR, and the two sides "
      "fall back independently; the per-investor split runs on commitments and names every "
      "investor whose funded share disagrees. (Tier math itself is pinned in test_waterfall.)")
