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

    # --- PORTAL-TXN phase 2: the payment schedule is OPT-IN per token -----------------------------
    for inv in ({"number": "INV-001", "amount": 250000, "period": "2026-05", "status": "paid"},
                {"number": "INV-002", "amount": 300000, "period": "2026-06", "status": "submitted"}):
        r = c.post(f"/projects/{pid}/modules/owner_invoice", json={"data": inv})
        assert r.status_code in (200, 201), r.text
    plain_tok = c.post(f"/projects/{pid}/share-tokens", json={"label": "no-financials"}).json()
    assert plain_tok["show_payments"] is False
    assert "payment_schedule" not in c.get(f"/shared/{plain_tok['token']}/digest").json(), \
        "the DEFAULT digest must expose no financials"
    pay_tok = c.post(f"/projects/{pid}/share-tokens",
                     json={"label": "owner", "show_payments": True}).json()
    assert pay_tok["show_payments"] is True
    ps = c.get(f"/shared/{pay_tok['token']}/digest").json()["payment_schedule"]
    assert ps["billed"] == 550000 and ps["paid"] == 250000 and ps["outstanding"] == 300000, ps
    assert {i["number"] for i in ps["items"]} == {"INV-001", "INV-002"}, ps["items"]
    pay_html = c.get(f"/shared/{pay_tok['token']}").text
    assert "Payment schedule" in pay_html and "$300,000" in pay_html and "Outstanding" in pay_html, \
        "the opt-in HTML page renders the schedule"
    assert "Payment schedule" not in c.get(f"/shared/{plain_tok['token']}").text

    # --- PORTAL-TXN phase 3: the scoped client comment thread (backed by a real BCF topic) --------
    ct = c.post(f"/shared/{pay_tok['token']}/comment",
                json={"text": "When does tile install start?", "client_name": "Pat Owner"})
    assert ct.status_code == 200, ct.text
    fb_tid = ct.json()["topic_id"]
    # the comment landed on a real project topic the team can answer from the Issue Board
    fb = c.get(f"/projects/{pid}/topics/{fb_tid}").json()
    assert fb["type"] == "info" and "Client feedback" in fb["title"] and "client-portal" in fb["labels"], fb
    c.post(f"/projects/{pid}/topics/{fb_tid}/comments",
           json={"author": "pm", "text": "Tile starts the week of 8/10."})     # the team replies
    conv = c.get(f"/shared/{pay_tok['token']}/digest").json()["conversation"]
    assert [x["text"] for x in conv] == ["When does tile install start?", "Tile starts the week of 8/10."], conv
    # a second comment through the token reuses the SAME feedback topic (one thread per link)
    assert c.post(f"/shared/{pay_tok['token']}/comment",
                  json={"text": "Great, thanks."}).json()["topic_id"] == fb_tid
    # guards: empty text 422 · revoked/unknown token 404 · XSS-escaped on the public page
    assert c.post(f"/shared/{pay_tok['token']}/comment", json={"text": "  "}).status_code == 422
    assert c.post("/shared/nope/comment", json={"text": "x"}).status_code == 404
    c.post(f"/shared/{pay_tok['token']}/comment", json={"text": "<img onerror=alert(1)>"})
    page = c.get(f"/shared/{pay_tok['token']}").text
    assert "Conversation" in page and "<img onerror" not in page and "&lt;img onerror" in page
    assert "Conversation" not in c.get(f"/shared/{plain_tok['token']}").text, \
        "a token with no comments shows no conversation card"

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

print("PORTAL-TXN OK - decisions (whitelisted, capped, escaped, 404-on-revoked, 409-on-cap) + the "
      "phase-2 payment schedule (an explicit per-token show_payments opt-in; the default digest exposes "
      "no financials, asserted both ways) + the phase-3 client comment thread: a token holder's comment "
      "lands on the token's dedicated BCF feedback topic (one thread per link), the team's Issue-Board "
      "reply flows back into the digest conversation, empty text 422s, unknown token 404s, and the "
      "public page renders every message escaped.")
