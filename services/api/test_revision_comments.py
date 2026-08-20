"""A revision must carry the comments that caused it — R22-ENTITLEMENT ④, comment round-tripping.

THE DEFECT. `modules.revise()` creates a **new record with a new id**, linked to its source by
`data.revises`, and marks the source `data.superseded_by`. Comments live in the shared
`record_comments` table keyed by `(module, record_id)`, and `get_record` fetches them with
`RecordComment.record_id == rid` — the current record only.

So the reviewer who wrote *"Revise & Resubmit — the anchor spacing does not match detail 5/A-501"*
on submittal SUB-001 opens SUB-001.1 and sees **an empty comment list**. The one thing they need in
order to check whether the resubmittal addressed anything is the thing the revision drops. On a
construction project that is not a missing convenience, it is how "we told you this last time"
becomes an argument nobody can settle from the record.

**This is not a submittal problem.** Fifteen modules are `revisable: true` — `rfi`, `asi`,
`bulletin`, `change_event`, `cor`, `design_review`, `document`, `drawing`, `entitlement`,
`information_container`, `market_assumption`, `proposal`, `sketch`, `submittal`, `transmittal`. An
RFI reissued as rev 2 loses the discussion that caused the reissue, in exactly the same way.

WHAT THE FIX MUST NOT DO. It must not merge the history flat. A comment written against rev 0 is
evidence about rev 0; presenting it as though it were written about the revision in hand is the
confident-wrong shape this repo keeps finding — worse than the omission, because it reads as
current. Inherited comments are therefore carried **labelled**: `inherited` says the comment came
from an earlier revision and `on_ref` says which one.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_revision_comments.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_rev_comments.db"
os.environ["STORAGE_DIR"] = "./test_storage_rev_comments"
os.environ["AEC_TRUST_XUSER"] = "1"

for _f in ("./test_rev_comments.db",):
    if os.path.exists(_f):
        os.remove(_f)

import sys  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

H = {"X-User": "gc"}
FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Rev Comments"}, headers=H).json()["id"]

    # --- a submittal, reviewed, returned for revision --------------------------------------------
    made = c.post(f"/projects/{pid}/modules/submittal",
                  json={"data": {"title": "Anchor bolts — shop drawings",
                                 "spec_section": "05 12 00", "type": "Shop Drawing", "rev": 0,
                                 "disposition": "Revise & Resubmit"}}, headers=H)
    assert made.status_code in (200, 201), (made.status_code, made.text)
    rec = made.json()
    rid, ref0 = rec["id"], rec["ref"]

    REVIEW = "Revise & Resubmit — anchor spacing does not match detail 5/A-501."
    SECOND = "Also confirm the embedment depth against the structural notes."
    for text in (REVIEW, SECOND):
        r = c.post(f"/projects/{pid}/modules/submittal/{rid}/comments",
                   json={"text": text}, headers=H)
        assert r.status_code in (200, 201), (r.status_code, r.text)

    before = c.get(f"/projects/{pid}/modules/submittal/{rid}", headers=H).json()
    check("the source revision carries the reviewer's comments", len(before["comments"]) == 2,
          f"{len(before['comments'])} comment(s) on {ref0}")

    # --- the contractor resubmits ---------------------------------------------------------------
    rev = c.post(f"/projects/{pid}/modules/submittal/{rid}/revise", headers=H)
    assert rev.status_code in (200, 201), (rev.status_code, rev.text)
    new_id, ref1 = rev.json()["id"], rev.json()["ref"]
    check("the revision is a NEW record — which is why its comments do not follow by themselves",
          new_id != rid, f"{ref0} -> {ref1}")

    got = c.get(f"/projects/{pid}/modules/submittal/{new_id}", headers=H).json()
    texts = [cm["text"] for cm in got["comments"]]

    check("THE FIX: the resubmittal shows the review that asked for it",
          REVIEW in texts, f"{len(texts)} comment(s) on {ref1}: {texts}")
    check("...and every comment from the source, not just the last one", SECOND in texts)

    # --- carried, but never disguised as current -------------------------------------------------
    inherited = [cm for cm in got["comments"] if cm.get("inherited")]
    check("inherited comments are LABELLED, not merged flat into this revision's own",
          len(inherited) == 2, f"{len(inherited)} of {len(texts)} marked inherited")
    check("...and each names the revision it was actually written against",
          all(cm.get("on_ref") == ref0 for cm in inherited),
          str([cm.get("on_ref") for cm in inherited]))

    # A comment written on the revision itself must NOT be labelled inherited — otherwise the flag
    # means nothing and a reader cannot tell current review from history.
    c.post(f"/projects/{pid}/modules/submittal/{new_id}/comments",
           json={"text": "Resubmitted with spacing corrected."}, headers=H)
    got2 = c.get(f"/projects/{pid}/modules/submittal/{new_id}", headers=H).json()
    own = [cm for cm in got2["comments"] if not cm.get("inherited")]
    check("a comment made ON this revision is not marked inherited",
          [cm["text"] for cm in own] == ["Resubmitted with spacing corrected."], str(own))

    # --- order is chronological across the whole chain, or the thread reads backwards -------------
    stamps = [cm.get("created_at") for cm in got2["comments"]]
    check("the thread reads oldest-first across revisions, not per-record",
          stamps == sorted(s for s in stamps if s), str(stamps))

    # --- two revisions deep: the chain is walked, not just one hop --------------------------------
    rev2 = c.post(f"/projects/{pid}/modules/submittal/{new_id}/revise", headers=H)
    assert rev2.status_code in (200, 201), (rev2.status_code, rev2.text)
    third = c.get(f"/projects/{pid}/modules/submittal/{rev2.json()['id']}",
                  headers=H).json()
    t3 = [cm["text"] for cm in third["comments"]]
    check("rev 2 sees BOTH earlier revisions — a single hop would lose the original review",
          REVIEW in t3 and "Resubmitted with spacing corrected." in t3, f"{len(t3)} comment(s)")
    check("...and each is attributed to the revision it was written on, not to the newest",
          {cm.get("on_ref") for cm in third["comments"] if cm.get("inherited")} == {ref0, ref1},
          str({cm.get("on_ref") for cm in third["comments"] if cm.get("inherited")}))

    # --- an unrevised record is unchanged: no inherited key, no extra comments --------------------
    solo = c.post(f"/projects/{pid}/modules/submittal",
                  json={"data": {"title": "Grout — product data", "spec_section": "03 60 00",
                                 "type": "Product Data", "rev": 0}}, headers=H).json()
    c.post(f"/projects/{pid}/modules/submittal/{solo['id']}/comments",
           json={"text": "Approved as noted."}, headers=H)
    plain = c.get(f"/projects/{pid}/modules/submittal/{solo['id']}", headers=H).json()
    check("a record with no revision history is untouched — one comment, none inherited",
          len(plain["comments"]) == 1 and not any(cm.get("inherited") for cm in plain["comments"]),
          str(plain["comments"]))

    # --- and it is generic, not a submittal special case ------------------------------------------
    rfi = c.post(f"/projects/{pid}/modules/rfi",
                 json={"data": {"subject": "Slab edge condition at grid F",
                               "question": "Confirm the edge detail at grid F."}}, headers=H).json()
    c.post(f"/projects/{pid}/modules/rfi/{rfi['id']}/comments",
           json={"text": "Answered verbally; reissue with the sketch attached."}, headers=H)
    rfi_rev = c.post(f"/projects/{pid}/modules/rfi/{rfi['id']}/revise", headers=H)
    assert rfi_rev.status_code in (200, 201), (rfi_rev.status_code, rfi_rev.text)
    rfi2 = c.get(f"/projects/{pid}/modules/rfi/{rfi_rev.json()['id']}", headers=H).json()
    check("a reissued RFI carries its discussion too — 15 modules are revisable, not one",
          any("reissue with the sketch" in cm["text"] for cm in rfi2["comments"]),
          f"{len(rfi2['comments'])} comment(s) on the reissued RFI")

print()
if FAILED:
    print(f"FAILED: {'; '.join(FAILED)}")
    sys.exit(1)
print("revision comments OK — a resubmittal carries the review that asked for it, labelled with "
      "the revision it was written against, chronological across the chain, and generic to every "
      "revisable module")
