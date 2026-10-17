"""PORTAL-TXN — the tokenized client-decision surface: public approve/acknowledge/decline through a share
token (whitelisted, length-capped, hard per-token cap), the activity feed on the digest + HTML (escaped),
and the editor-side decision feed.

PORTAL-TXN-DARK closed the loop: every route below was complete and careful for months, and the page a
client opens could reach none of them. The last section drives the controls' paths over HTTP — the
behavioural complement `test_portal_public_reach.py` names, since that gate reads the rendered page and
cannot prove a click works.
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
    # PORTAL-STATUS: both invoices are driven through the REAL transitions, and the two carry
    # DELIBERATELY CONTRADICTORY evidence so the assertions below can tell which field is being
    # believed. Until v0.3.1125 this seeded `"status": "paid"` straight into the data blob — a
    # lowercase value the product cannot produce, since the `status` select's options are
    # capitalised — so it proved the arithmetic on data no UI writes, while an invoice paid through
    # `mark_paid` reported `paid: 0` to the owner.
    #
    # INV-001: paid through the WORKFLOW, with no `status` typed at all -> must count as paid.
    # INV-002: only SUBMITTED, but carrying the select's own "Paid" in the blob -> must NOT count.
    #          The transition is the authority; the typed field is a label somebody may have left
    #          stale, and `modules.transition()` never writes it.
    _paid = c.post(f"/projects/{pid}/modules/owner_invoice",
                   json={"data": {"number": "INV-001", "amount": 250000,
                                  "period": "2026-05"}}).json()["id"]
    for _a in ("submit", "mark_paid"):
        assert c.post(f"/projects/{pid}/modules/owner_invoice/{_paid}/transition",
                      json={"action": _a}).status_code < 300
    _open = c.post(f"/projects/{pid}/modules/owner_invoice",
                   json={"data": {"number": "INV-002", "amount": 300000, "period": "2026-06",
                                  "status": "Paid"}}).json()["id"]
    assert c.post(f"/projects/{pid}/modules/owner_invoice/{_open}/transition",
                  json={"action": "submit"}).status_code < 300
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
    # The two invoices discriminate the sources: the same numbers above are reachable by believing
    # the blob, so without this the totals alone could not tell the fix from the defect.
    _by_num = {i["number"]: i for i in ps["items"]}
    assert _by_num["INV-001"]["status_key"] == "paid", ("a workflow-paid invoice must read paid to "
                                                        "the owner", _by_num["INV-001"])
    assert _by_num["INV-001"]["status"] == "Paid", _by_num["INV-001"]
    assert _by_num["INV-002"]["status_key"] == "submitted", (
        "a merely SUBMITTED invoice must not read as paid just because somebody typed Paid in the "
        "status field — the transition is the authority", _by_num["INV-002"])
    # The FALLBACK branch cannot be reached through the route — every record created through the
    # API gets a `workflow_state`, so only a legacy/imported row with a NULL state would fall back
    # to the blob. Mutation-testing showed no route-level assertion could tell `.strip().lower()`
    # from nothing at all, which is the untestable-guard shape v0.3.1124 deleted. The function is
    # pure, so the branch is asserted DIRECTLY rather than kept as decoration nothing checks.
    from aec_api.client_portal import invoice_status_key
    assert invoice_status_key({"workflow_state": "paid"}, {}) == "paid"
    assert invoice_status_key({"workflow_state": "submitted"}, {"status": "Paid"}) == "submitted", \
        "the transition is the authority; a stale typed field must not override it"
    assert invoice_status_key({}, {"status": "Paid"}) == "paid", \
        "a row with no workflow state falls back to the blob, CASEFOLDED — the select writes " \
        "'Paid' and every comparison in this module is lowercase"
    assert invoice_status_key({}, {"status": "  PAID  "}) == "paid"
    assert invoice_status_key({}, {}) == "draft"

    # ...and the HTML colour keys off the same normalised value, so the page and the totals agree.
    # Scoped to the INV-001 ROW, not the whole page. A page-wide substring check passes today (the
    # mutation `color = "#9a6700"` does fail it, verified), but it is only true as long as nothing
    # else on the page uses that colour — the moment something does, the assertion goes vacuous with
    # nothing to announce it. Raised in review of #382 with the reasoning that an approved decision
    # already renders it; that specific claim is false here, but the fragility it points at is real.
    _page = c.get(f"/shared/{pay_tok['token']}").text
    _row = next((li for li in _page.split("<li") if "INV-001" in li), None)
    assert _row is not None, "the paid invoice must appear as a row on the owner's page"
    # Colour AND label together, in one span. Scoping to the row proves the colour belongs to this
    # invoice; binding it to `>Paid<` proves the owner actually reads "Paid" there. Raised in review
    # as asserting the status span rather than a bare hex — a fair point: the hex alone would still
    # pass if the label regressed to the raw blob value.
    assert 'color:#1a7f37">Paid</span>' in _row, \
        ("the paid invoice must render as a Paid span in the paid colour, on its own row; "
         "this colour never fired at all before v0.3.1125", _row[:300])
    _unpaid = next((li for li in _page.split("<li") if "INV-002" in li), None)
    assert _unpaid is not None and "#1a7f37" not in _unpaid, \
        "an unpaid invoice must NOT render in the paid colour"
    pay_html = c.get(f"/shared/{pay_tok['token']}").text
    assert "Payment schedule" in pay_html and "$300,000" in pay_html and "Outstanding" in pay_html, \
        "the opt-in HTML page renders the schedule"
    assert "Payment schedule" not in c.get(f"/shared/{plain_tok['token']}").text

    # A REJECTED application must not appear on the OWNER's own page. This reader had two faults at
    # once: it added every invoice to `billed`, and it displayed `data.status` rather than the
    # workflow state — so a bill the owner had refused showed up as a "draft" that still counted.
    _rej = c.post(f"/projects/{pid}/modules/owner_invoice",
                  json={"data": {"number": "INV-003", "amount": 900000, "period": "2026-07"}}).json()["id"]
    c.post(f"/projects/{pid}/modules/owner_invoice/{_rej}/transition", json={"action": "submit"})
    c.post(f"/projects/{pid}/modules/owner_invoice/{_rej}/transition", json={"action": "reject"})
    ps2 = c.get(f"/shared/{pay_tok['token']}/digest").json()["payment_schedule"]
    assert ps2["billed"] == 550000, ("a rejected application was billed to the client", ps2["billed"])
    assert "INV-003" not in {i["number"] for i in ps2["items"]}, ps2["items"]

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
    # PORTAL-TXN-DARK: this asserted the opposite — "a token with no comments shows no conversation
    # card" — and that was the defect. The card holds the message box and the sentence promising a
    # message reaches the team, so hiding it until somebody has already written one showed the
    # invitation to exactly the people who did not need it. An EMPTY thread is the state where the
    # invitation is the content.
    empty_page = c.get(f"/shared/{plain_tok['token']}").text
    assert "Conversation" in empty_page and "No messages yet" in empty_page, \
        "a token with no comments must still offer the message box"
    assert 'id="comment-send"' in empty_page and "reach the project team" in empty_page

    # --- PORTAL-TXN-DARK: the page a client opens can now reach both public write routes ----------
    # `test_portal_public_reach.py` derives the population and asserts the controls are THERE; it is
    # a source-level check and says so. This is the behavioural complement: the paths those controls
    # post to answer over HTTP, for a token that has done neither thing before.
    fresh = c.post(f"/projects/{pid}/share-tokens", json={"label": "loop"}).json()["token"]
    fresh_page = c.get(f"/shared/{fresh}").text
    assert 'id="decision-form"' in fresh_page and 'data-item-type="digest"' in fresh_page
    # The ref the page defaults is a SNAPSHOT of what was read, not a constant: a client approving a
    # 62% digest has not approved the 88% one.
    import re as _re
    m = _re.search(r'data-item-ref="([^"]+)"', fresh_page)
    assert m and "Readiness digest" in m.group(1) and "%" in m.group(1), fresh_page[:200]
    ref = m.group(1).replace("&amp;", "&").replace("&#x27;", "'").replace("&quot;", '"')
    lands = c.post(f"/shared/{fresh}/decision",
                   json={"item_type": "digest", "item_ref": ref, "action": "approved",
                         "client_name": "Pat Owner", "note": "Looks right to us."})
    assert lands.status_code == 200, lands.text
    assert lands.json()["item_ref"] == ref, (lands.json()["item_ref"], ref)
    said = c.post(f"/shared/{fresh}/comment", json={"text": "One question on step 4."})
    assert said.status_code == 200, said.text
    # and both come back to the OWNER's feed, which is the other end the panel reads
    feed = c.get(f"/projects/{pid}/client-decisions").json()["decisions"]
    mine = [d for d in feed if d["token"] == fresh]
    assert len(mine) == 1 and mine[0]["action"] == "approved" and mine[0]["note"] == "Looks right to us.", mine

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
      "public page renders every message escaped + PORTAL-TXN-DARK: the page a client actually opens "
      "now carries the controls that reach both of those public write routes, the response it defaults "
      "names the digest that was read, and both halves come back on the owner's feed.")
