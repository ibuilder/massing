"""PORTAL-TXN — the tokenized client-decision surface: public approve/acknowledge/decline through a share
token (whitelisted, length-capped, hard per-token cap), the activity feed on the digest + HTML (escaped),
and the editor-side decision feed.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_portal_txn.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_portal_txn.db"
os.environ["STORAGE_DIR"] = "./test_storage_portaltxn"
os.environ.pop("AEC_RBAC", None)

if os.path.exists("./test_portal_txn.db"):
    os.remove("./test_portal_txn.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Portal"}).json()["id"]
    tok = c.post(f"/projects/{pid}/share-tokens", json={"label": "Owner link"}).json()["token"]

    # --- public decision: approve an estimate version ---------------------------------------------
    r = c.post(f"/shared/{tok}/decision", json={
        "item_type": "estimate", "item_ref": "Estimate v3", "action": "approved", "client_name": "Pat Owner"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["action"] == "approved" and d["item_ref"] == "Estimate v3" and d["created_at"], d

    # acknowledge a CO with a note; decline a selection
    assert c.post(f"/shared/{tok}/decision", json={
        "item_type": "change_order", "item_ref": "CO-004", "action": "acknowledged",
        "note": "Understood the schedule impact."}).status_code == 200
    assert c.post(f"/shared/{tok}/decision", json={
        "item_type": "selection", "item_ref": "Kitchen tile B", "action": "declined"}).status_code == 200

    # --- guards: whitelist 422 · bad action 422 · missing ref 422 · unknown token 404 -------------
    assert c.post(f"/shared/{tok}/decision", json={"item_type": "wire_transfer", "item_ref": "x",
                                                   "action": "approved"}).status_code == 422
    assert c.post(f"/shared/{tok}/decision", json={"item_type": "estimate", "item_ref": "x",
                                                   "action": "paid"}).status_code == 422
    assert c.post(f"/shared/{tok}/decision", json={"item_type": "estimate", "item_ref": "",
                                                   "action": "approved"}).status_code == 422
    assert c.post("/shared/nope/decision", json={"item_type": "estimate", "item_ref": "x",
                                                 "action": "approved"}).status_code == 404

    # length caps applied (item_ref 120 · note 500)
    long = c.post(f"/shared/{tok}/decision", json={"item_type": "document", "item_ref": "A" * 999,
                                                   "action": "acknowledged", "note": "B" * 999}).json()
    assert len(long["item_ref"]) == 120 and len(long["note"]) == 500, (len(long["item_ref"]), len(long["note"]))

    # --- digest carries the activity feed, newest first -------------------------------------------
    dig = c.get(f"/shared/{tok}/digest").json()
    assert len(dig["activity"]) == 4, dig["activity"]
    assert dig["activity"][0]["item_type"] == "document", dig["activity"][0]     # newest first

    # --- the HTML page renders the feed ESCAPED (public page, XSS is the risk) --------------------
    c.post(f"/shared/{tok}/decision", json={"item_type": "digest", "item_ref": "<script>alert(1)</script>",
                                            "action": "acknowledged"})
    html = c.get(f"/shared/{tok}").text
    assert "Your activity" in html and "<script>alert(1)</script>" not in html, "raw script must not render"
    assert "&lt;script&gt;" in html, "the ref must appear escaped"

    # --- editor-side decision feed, newest first; revoked token stops decisions -------------------
    feed = c.get(f"/projects/{pid}/client-decisions").json()["decisions"]
    assert len(feed) == 5 and feed[0]["item_ref"].startswith("<script>"), feed[0]
    c.delete(f"/projects/{pid}/share-tokens/{tok}")
    assert c.post(f"/shared/{tok}/decision", json={"item_type": "estimate", "item_ref": "x",
                                                   "action": "approved"}).status_code == 404

    # --- the hard per-token cap (200) fires 409 ---------------------------------------------------
    tok2 = c.post(f"/projects/{pid}/share-tokens", json={"label": "cap"}).json()["token"]
    from aec_api.client_portal import _MAX_DECISIONS_PER_TOKEN
    from aec_api.db import SessionLocal
    from aec_api.models import ClientDecision
    with SessionLocal() as db:                       # seed to the cap directly (fast), then hit the route
        for i in range(_MAX_DECISIONS_PER_TOKEN):
            db.add(ClientDecision(token=tok2, project_id=pid, item_type="digest",
                                  item_ref=f"n{i}", action="acknowledged"))
        db.commit()
    over = c.post(f"/shared/{tok2}/decision", json={"item_type": "estimate", "item_ref": "one more",
                                                    "action": "approved"})
    assert over.status_code == 409 and "limit" in over.json()["detail"], over.text

print("PORTAL-TXN OK - a share-token holder can approve an estimate, acknowledge a CO (with a note), and "
      "decline a selection through the PUBLIC /shared/{token}/decision endpoint; item types + actions are "
      "whitelisted (wire_transfer/paid → 422), refs/notes are length-capped (120/500), an unknown or revoked "
      "token 404s, and the hard 200-decision-per-token cap 409s; the digest carries the newest-first activity "
      "feed, the public HTML page renders it fully escaped (an injected <script> appears only as "
      "&lt;script&gt;), and editors read the project-wide decision feed newest-first.")
