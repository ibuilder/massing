"""Pay-app <-> lien-waiver reconciliation + payments bridge (money-safe stub).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_payapp.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_payapp.db"
os.environ["STORAGE_DIR"] = "./test_storage_payapp"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("PAYMENTS_PROVIDER", None)
for _f in ("./test_payapp.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import payments_bridge  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- payments bridge: off by default, never fabricates a transfer, enforces the waiver gate ---
assert payments_bridge.is_enabled() is False
st = payments_bridge.status()
assert st["enabled"] is False and "not configured" in st["message"], st
# release gate fires regardless of provider config
try:
    payments_bridge.send_payment("Ace", 1000, lien_exposure=500)
    raise AssertionError("expected refusal on lien exposure")
except ValueError as e:
    assert "lien exposure" in str(e), e
# no exposure but unconfigured -> RuntimeError (not a fake transfer)
try:
    payments_bridge.send_payment("Ace", 1000, lien_exposure=0)
    raise AssertionError("expected not-configured error")
except RuntimeError as e:
    assert "not configured" in str(e), e

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    # Ace: paid $100k, only a conditional waiver -> exposure remains
    inv = c.post(f"/projects/{pid}/modules/sub_invoice",
                 json={"data": {"vendor": "Ace", "amount": 100000, "retainage_pct": 10}}).json()
    for a in ("approve", "pay"):        # starts at 'submitted'
        c.post(f"/projects/{pid}/modules/sub_invoice/{inv['id']}/transition", json={"action": a})
    w = c.post(f"/projects/{pid}/modules/lien_waiver",
               json={"data": {"vendor": "Ace", "amount": 100000, "waiver_type": "Conditional Progress"}}).json()
    c.post(f"/projects/{pid}/modules/lien_waiver/{w['id']}/transition", json={"action": "receive"})

    # Best: paid $50k with an unconditional waiver -> clear
    inv2 = c.post(f"/projects/{pid}/modules/sub_invoice",
                  json={"data": {"vendor": "Best", "amount": 50000}}).json()
    for a in ("approve", "pay"):
        c.post(f"/projects/{pid}/modules/sub_invoice/{inv2['id']}/transition", json={"action": a})
    w2 = c.post(f"/projects/{pid}/modules/lien_waiver",
                json={"data": {"vendor": "Best", "amount": 50000, "waiver_type": "Unconditional Final"}}).json()
    c.post(f"/projects/{pid}/modules/lien_waiver/{w2['id']}/transition", json={"action": "receive"})

    r = c.get(f"/projects/{pid}/payapp/lien-exposure").json()
    ace = next(v for v in r["vendors"] if v["vendor"] == "Ace")
    best = next(v for v in r["vendors"] if v["vendor"] == "Best")
    assert ace["paid"] == 100000 and ace["exposure"] == 100000 and ace["status"] == "conditional_only", ace
    assert ace["retainage"] == 10000, ace
    assert best["exposure"] == 0 and best["status"] == "clear", best
    assert r["total_lien_exposure"] == 100000 and r["vendors_at_risk"] == ["Ace"], r
    assert c.get("/payments/status").json()["enabled"] is False

    # --- WAIVER-FLAT: the three security states, all three in ONE response ------------------------
    #
    # The two assertions above are the whole reason this needs a third vendor. They proved the
    # engine reports `conditional_only`, and there was no `no_waiver` vendor beside it — so the
    # pair that the exposure card rendered IDENTICALLY was never both present in anything this
    # suite looked at. `status` and `waived_conditional` were declared on the client type and read
    # by nothing, which no gate here could see: 562 of 706 `this.json<{…}>` call sites declare
    # their response inline, outside `deadFieldTyped`'s population (DEADFIELD-INLINE).
    inv3 = c.post(f"/projects/{pid}/modules/sub_invoice",
                  json={"data": {"vendor": "Cole", "amount": 100000}}).json()
    for a in ("approve", "pay"):
        c.post(f"/projects/{pid}/modules/sub_invoice/{inv3['id']}/transition", json={"action": a})

    r2 = c.get(f"/projects/{pid}/payapp/lien-exposure").json()
    by = {v["vendor"]: v for v in r2["vendors"]}
    assert {v["status"] for v in r2["vendors"]} == {"clear", "conditional_only", "no_waiver"}, \
        [(v["vendor"], v["status"]) for v in r2["vendors"]]
    cole = by["Cole"]
    assert cole["status"] == "no_waiver" and cole["waived_conditional"] == 0, cole

    # THE DEFECT, as the four cells the card actually rendered. Ace holds a signed conditional
    # release for the whole balance; Cole holds nothing. Every column on the screen agreed.
    shipped = ("paid", "waived_unconditional", "exposure")
    assert [by["Ace"][k] for k in shipped] == [cole[k] for k in shipped], (by["Ace"], cole)
    # ...and the two fields that tell them apart disagree, which is what the screen now reads.
    assert by["Ace"]["status"] != cole["status"]
    assert by["Ace"]["waived_conditional"] == 100000 and cole["waived_conditional"] == 0

    # `vendors_at_risk` is derived from the STATUS, so it lumps them — which is exactly why the
    # distinction has to reach the screen rather than being recoverable from the rollup.
    assert sorted(r2["vendors_at_risk"]) == ["Ace", "Cole"], r2["vendors_at_risk"]
    # The population the card prints a denominator from. Equal to the row count in every response
    # this route has served; read from the rollup anyway, because a denominator taken from the page
    # is TRUNC-COUNTED waiting to happen.
    assert r2["vendor_count"] == len(r2["vendors"]) == 3, r2["vendor_count"]
    # The engine's own instruction, which the card never rendered.
    assert r2["message"] and "collect waivers" in r2["message"], r2["message"]

print("PAYAPP OK - lien-waiver reconciliation: paid-with-conditional-only -> full exposure + retainage; "
      "paid-with-unconditional -> clear; project rollup flags at-risk vendor; payments bridge off + "
      "release gate refuses payment while exposure remains (never fabricates a transfer)")
print("WAIVER-FLAT OK - all three security states reachable in one response (clear / "
      "conditional_only / no_waiver); the three columns the card rendered are EQUAL for the "
      "conditional_only and no_waiver vendors while status and waived_conditional disagree; "
      "vendors_at_risk lumps both; vendor_count == len(vendors) == 3; the engine's collect-waivers "
      "instruction is sent")
