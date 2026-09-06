"""R22-ENTITLEMENT ⑤ — an agency review comment becomes an RFI somebody owns.

`RecordComment` had no outward link of any kind: an agency's comment on an `entitlement` or `permit`
was a text blob at the end of a thread — readable, and impossible to assign, track or close. ④ had
already made comments survive a revision, which is the INBOUND half of "round-tripping"; this is the
outbound half the ring entry still listed as remaining.

Follows `promote_markup` rather than inventing a second idiom, and the back-link is the idempotency:
a second promote 409s instead of minting a duplicate RFI for the same comment — the failure mode a
"promote" button produces on every double-click.

Run: PYTHONPATH=src ./.venv/bin/python test_comment_promote.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_comment_promote.db"
os.environ["STORAGE_DIR"] = "./test_storage_comment_promote"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_comment_promote.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules as mod_engine  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import RecordComment  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Entitlement P"}).json()["id"]
    rec = c.post(f"/projects/{pid}/modules/entitlement",
                 json={"data": {"subject": "Site plan review", "agency": "City Planning",
                                "application_type": "Site Plan"}}).json()
    rid = rec["id"]

    # --- the comment exists and is addressable -------------------------------------------------
    # It was not, before this slice: the serialised comment carried author/text/created_at and no
    # id, so nothing could name one comment out of a thread in order to act on it.
    body = ("Provide a shade study for the north plaza before the hearing.\n"
            "Ref: condition 14.")
    c.post(f"/projects/{pid}/modules/entitlement/{rid}/comments", json={"text": body})
    got = c.get(f"/projects/{pid}/modules/entitlement/{rid}").json()
    assert len(got["comments"]) == 1, got["comments"]
    cid = got["comments"][0]["id"]
    assert cid, "the comment must be addressable or it cannot be promoted"
    assert "topic_id" not in got["comments"][0], "an unpromoted comment must not claim a topic"

    # --- promote → a real RFI carrying the comment and its source ------------------------------
    r = c.post(f"/projects/{pid}/modules/entitlement/{rid}/comments/{cid}/promote",
               json={"kind": "rfi"})
    assert r.status_code == 201, (r.status_code, r.text)
    out = r.json()
    tid = out["topic"]["id"]
    assert out["topic"]["type"] == "rfi", out["topic"]
    assert out["topic"]["status"] == "open", out["topic"]
    # The title is the comment's FIRST LINE, not the whole body: an RFI list is scanned, and a
    # two-paragraph title is unreadable in it.
    assert out["topic"]["title"] == "Provide a shade study for the north plaza before the hearing.", \
        out["topic"]["title"]

    # The description must carry the provenance — which record, and who said it. An RFI that does
    # not name where it came from sends someone back to find the thread by hand.
    topic = c.get(f"/projects/{pid}/topics/{tid}").json()
    assert "entitlement" in topic["description"], topic["description"]
    assert rec["ref"] in topic["description"], (rec["ref"], topic["description"])
    assert "shade study" in topic["description"], topic["description"]

    # --- the back-link is written, and it is what the UI reads ---------------------------------
    got2 = c.get(f"/projects/{pid}/modules/entitlement/{rid}").json()
    assert got2["comments"][0].get("topic_id") == tid, got2["comments"][0]

    # --- promoting the same comment twice is refused, not duplicated ---------------------------
    # Without the back-link this mints a second RFI for one comment every time the button is
    # pressed, and nothing downstream can tell the copies apart.
    again = c.post(f"/projects/{pid}/modules/entitlement/{rid}/comments/{cid}/promote", json={})
    assert again.status_code == 409, (again.status_code, again.text)
    assert len(c.get(f"/projects/{pid}/topics").json()) == 1, "a refused promote must mint nothing"

    # --- the element tie is carried, because an RFI belongs on the model -----------------------
    # GlobalId is the only identity that survives a reload, so the RFI has to reference the element
    # rather than a viewer id; the record's own tie is the honest source for it.
    rec2 = c.post(f"/projects/{pid}/modules/entitlement",
                  json={"data": {"subject": "Height variance", "agency": "City Planning",
                                 "application_type": "Variance"}}).json()
    rid2 = rec2["id"]
    c.post(f"/projects/{pid}/modules/entitlement/{rid2}/elements",
           json={"guids": ["1a2b3c4d5e6f7g8h9i0j1k"]})
    c.post(f"/projects/{pid}/modules/entitlement/{rid2}/comments",
           json={"text": "Parapet exceeds the district limit."})
    cid2 = c.get(f"/projects/{pid}/modules/entitlement/{rid2}").json()["comments"][0]["id"]
    r2 = c.post(f"/projects/{pid}/modules/entitlement/{rid2}/comments/{cid2}/promote", json={})
    assert r2.status_code == 201, (r2.status_code, r2.text)
    assert r2.json()["topic"]["element_guids"] == ["1a2b3c4d5e6f7g8h9i0j1k"], r2.json()["topic"]

    # --- refusals: an unknown comment, and a kind nobody defined -------------------------------
    assert c.post(f"/projects/{pid}/modules/entitlement/{rid}/comments/nope/promote",
                  json={}).status_code == 404
    c.post(f"/projects/{pid}/modules/entitlement/{rid}/comments", json={"text": "Third round."})
    cid3 = [x for x in c.get(f"/projects/{pid}/modules/entitlement/{rid}").json()["comments"]
            if not x.get("topic_id")][0]["id"]
    bad = c.post(f"/projects/{pid}/modules/entitlement/{rid}/comments/{cid3}/promote",
                 json={"kind": "wishlist"})
    assert bad.status_code == 422, (bad.status_code, bad.text)

    # a comment on a DIFFERENT record must not be promotable through this record's path — the
    # engine matches project+module+record, not the comment id alone.
    cross = c.post(f"/projects/{pid}/modules/entitlement/{rid2}/comments/{cid3}/promote", json={})
    assert cross.status_code == 404, (cross.status_code, cross.text)

    # --- a whitespace-only comment promotes to the fallback title, it does not 500 ---------------
    # The comment route takes `text: str = Body(...)` with no min-length, so "   \n  " is a 201.
    # Promoting it ran `.strip().splitlines()[0]` over an empty list — IndexError, 500, and the
    # fallback title written for exactly this case never fired.
    rec3 = c.post(f"/projects/{pid}/modules/entitlement",
                  json={"data": {"subject": "Blank", "agency": "City Planning",
                                 "application_type": "Site Plan"}}).json()
    rid3 = rec3["id"]
    assert c.post(f"/projects/{pid}/modules/entitlement/{rid3}/comments",
                  json={"text": "   \n  "}).status_code == 201
    cid4 = c.get(f"/projects/{pid}/modules/entitlement/{rid3}").json()["comments"][0]["id"]
    blank = c.post(f"/projects/{pid}/modules/entitlement/{rid3}/comments/{cid4}/promote", json={})
    assert blank.status_code == 201, (blank.status_code, blank.text)
    assert blank.json()["topic"]["title"] == f"entitlement {rec3['ref']} review comment", \
        blank.json()["topic"]["title"]

    # --- two sessions that both read a null back-link: exactly one promote survives -------------
    # The `if cm.topic_id` guard reads the SESSION's copy, and `SessionLocal` is
    # `expire_on_commit=False`, so a request that loaded the comment before a concurrent promote
    # committed still sees None however long it holds it. A plain assignment therefore let the later
    # writer overwrite the back-link — minting a duplicate RFI AND orphaning the first, whose Topic
    # no comment pointed at any more. The claim is a conditional UPDATE; this is the loser's path.
    rec4 = c.post(f"/projects/{pid}/modules/entitlement",
                  json={"data": {"subject": "Race", "agency": "City Planning",
                                 "application_type": "Site Plan"}}).json()
    rid4 = rec4["id"]
    c.post(f"/projects/{pid}/modules/entitlement/{rid4}/comments",
           json={"text": "Two reviewers pressed promote at once."})
    cid5 = c.get(f"/projects/{pid}/modules/entitlement/{rid4}").json()["comments"][0]["id"]

    before = len(c.get(f"/projects/{pid}/topics").json())
    loser, winner = SessionLocal(), SessionLocal()
    stale = loser.get(RecordComment, cid5)          # the loser reads first: topic_id is None
    assert stale.topic_id is None
    won = mod_engine.promote_comment(winner, "entitlement", pid, rid4, cid5, "winner", "rfi")
    assert stale.topic_id is None, "the loser's session still holds the pre-promote read"
    try:
        mod_engine.promote_comment(loser, "entitlement", pid, rid4, cid5, "loser", "rfi")
        raise AssertionError("a stale-read promote must be refused, not duplicated")
    except HTTPException as e:
        assert e.status_code == 409, e.status_code
    loser.close()
    winner.close()

    # and the loser left nothing behind: one new Topic, still pointed at by the comment.
    assert len(c.get(f"/projects/{pid}/topics").json()) == before + 1, "the loser minted an orphan"
    linked = [x for x in c.get(f"/projects/{pid}/modules/entitlement/{rid4}").json()["comments"]
              if x["id"] == cid5][0]
    assert linked["topic_id"] == won["topic"]["id"], (linked, won["topic"]["id"])

print("test_comment_promote OK")
