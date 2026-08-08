"""A saved view's delete reports what it actually did — and only the owner can do it.

THE DEFECT THIS EXISTS FOR. `delete_view` was:

    v = db.get(SavedView, vid)
    if v and v.user == user:
        db.delete(v); db.commit()
    return {"deleted": bool(v)}

`bool(v)` is truthy whenever the ROW EXISTS, including when it belongs to somebody else and was
therefore not deleted. Asking to remove another user's view returned **"deleted": true** with the
view still there. Confidently wrong, and the exact shape that trains a UI to skip its re-read — the
same family as `available: false` rendered as zero, applied to a write instead of a read.

Nothing caught it because NO TEST COVERED THIS ROUTE AT ALL. `test_smart_views.py` and
`test_search_alerts.py` both create and list views; neither deletes one. That is the gap this file
closes, and it is why the sweep now checks for a test before trusting an endpoint's behaviour.

The route also now scopes to `pid`, which its sibling `mark_view_seen` always did.

WHY BOTH REFUSALS LOOK THE SAME. Not-mine and doesn't-exist both return `deleted: false` rather than
different statuses. Distinguishing them would confirm the existence of another user's view id to
somebody who cannot read it — the same enumeration argument the share-token routes make.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_view_delete.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_view_delete.db"
os.environ["STORAGE_DIR"] = "./test_storage_view_delete"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_view_delete.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


MOD = "rfi"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "View Delete"}).json()["id"]
    other = c.post("/projects", json={"name": "Other Project"}).json()["id"]

    def make(name: str, user: str, project: str = pid) -> str:
        r = c.post(f"/projects/{project}/modules/{MOD}/views",
                   json={"name": name, "config": {"filter": name}},
                   headers={"X-User": user})
        assert r.status_code in (200, 201), (r.status_code, r.text)
        return r.json()["id"]

    def views_of(user: str, project: str = pid) -> list:
        r = c.get(f"/projects/{project}/modules/{MOD}/views", headers={"X-User": user})
        return r.json() if isinstance(r.json(), list) else r.json().get("views", [])

    mine = make("mine", "alice")
    theirs = make("theirs", "bob")

    check("the fixture really made two views owned by different users",
          bool(mine) and bool(theirs) and mine != theirs, f"{mine} {theirs}")

    # ---- the defect: deleting somebody else's view must not claim success --------------------
    r = c.delete(f"/projects/{pid}/modules/{MOD}/views/{theirs}", headers={"X-User": "alice"})
    check("deleting another user's view reports deleted:false",
          r.status_code == 200 and r.json().get("deleted") is False,
          f"{r.status_code} {r.text} — `bool(v)` was truthy for any existing row, so this said true")
    # ...AND THE VIEW IS STILL THERE. The pairing is the point: the old code returned the wrong
    # ANSWER while doing the right THING, so asserting only the flag would have missed half of it,
    # and asserting only survival would have passed on the broken version.
    check("...and bob's view still exists",
          any(v.get("id") == theirs for v in views_of("bob")),
          f"bob's views: {[v.get('id') for v in views_of('bob')]}")

    # ---- the owner CAN delete, and it is reported truthfully ---------------------------------
    r = c.delete(f"/projects/{pid}/modules/{MOD}/views/{mine}", headers={"X-User": "alice"})
    check("the owner's own delete reports deleted:true",
          r.status_code == 200 and r.json().get("deleted") is True, f"{r.status_code} {r.text}")
    check("...and it is gone", not any(v.get("id") == mine for v in views_of("alice")),
          f"alice's views: {[v.get('id') for v in views_of('alice')]}")

    # ---- a second delete of the same id is honest, not a lie ----------------------------------
    r = c.delete(f"/projects/{pid}/modules/{MOD}/views/{mine}", headers={"X-User": "alice"})
    check("deleting it again reports deleted:false", r.json().get("deleted") is False, r.text)

    # ---- an unknown id is indistinguishable from not-mine -------------------------------------
    r_unknown = c.delete(f"/projects/{pid}/modules/{MOD}/views/no-such-view-id",
                         headers={"X-User": "alice"})
    r_notmine = c.delete(f"/projects/{pid}/modules/{MOD}/views/{theirs}",
                         headers={"X-User": "alice"})
    check("unknown and not-mine are indistinguishable",
          r_unknown.status_code == r_notmine.status_code and r_unknown.text == r_notmine.text,
          f"unknown={r_unknown.status_code}/{r_unknown.text} notmine={r_notmine.status_code}/{r_notmine.text}")

    # ---- project scope: the sibling route always checked it, this one did not -----------------
    elsewhere = make("elsewhere", "alice", project=other)
    r = c.delete(f"/projects/{pid}/modules/{MOD}/views/{elsewhere}", headers={"X-User": "alice"})
    check("my own view in ANOTHER project is not deleted through this project's path",
          r.json().get("deleted") is False,
          f"{r.text} — owner matches, so only the project check can refuse this")
    check("...and it survives", any(v.get("id") == elsewhere for v in views_of("alice", other)),
          f"other-project views: {[v.get('id') for v in views_of('alice', other)]}")

    # ---- MODULE scope: the half that was missed when the project half was fixed ----------------
    # The `pid` check above was added by copying `mark_view_seen`, which does not check `key`
    # either — so the copy inherited the gap. Both segments of the path address the row; only one
    # of them was verified. Same user and same project, so nothing crosses a privilege boundary:
    # this asserts that the module segment MEANS something rather than being decorative.
    other_mod = make("in rfi", "alice")
    r = c.delete(f"/projects/{pid}/modules/submittal/views/{other_mod}", headers={"X-User": "alice"})
    check("a view saved under one module is not deleted through ANOTHER module's path",
          r.json().get("deleted") is False,
          f"{r.text} — owner and project both match, so only the module check can refuse this")
    check("...and it is still listed under its own module",
          any(v.get("id") == other_mod for v in views_of("alice")),
          f"{MOD} views: {[v.get('id') for v in views_of('alice')]}")

    # The sibling route had the same gap, and fixing one without the other is how two routes that
    # are meant to agree start disagreeing. `seen` clears a saved-search alert count, so a
    # cross-module hit silently marks the WRONG view as read.
    s = c.post(f"/projects/{pid}/modules/costitem/views/{other_mod}/seen", headers={"X-User": "alice"})
    check("mark_view_seen refuses a view from another module too", s.status_code == 404,
          f"{s.status_code} {s.text}")
    s = c.post(f"/projects/{pid}/modules/{MOD}/views/{other_mod}/seen", headers={"X-User": "alice"})
    # PAIRED WITH ITS TWIN. A 404-only assertion passes just as well on a route that 404s for
    # everything, which is the failure mode a refusal test cannot see on its own.
    check("...and still accepts it through its own module", s.status_code == 200,
          f"{s.status_code} {s.text}")

print(f"\ntest_view_delete {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
