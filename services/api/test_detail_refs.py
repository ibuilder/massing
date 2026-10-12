"""R21-DETAIL-REF — a drawing set is a graph, and until now nothing could traverse it.

A wall section carries numbered bubbles pointing at enlarged details elsewhere ("12/A-501"), and each
detail carries its own bubble, title and scale. Nothing linked the two, so the set could not be
navigated and — the part that actually costs money — could not be CHECKED.

Two defects, deliberately reported apart because they have different owners and different fixes:
  * dangling — a callout points at a detail that does not exist; the reader follows it and finds
    nothing. This is the one that surfaces in the field.
  * orphan   — a detail nothing points at; drawn, paid for, never reached.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_detail_refs.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_detail_refs.db"
os.environ["STORAGE_DIR"] = "./test_storage_detail_refs"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_detail_refs.db"):
    os.remove("./test_detail_refs.db")

from aec_api import detail_refs as dr  # noqa: E402
from aec_data import drawings as d  # noqa: E402

# ---- parsing: read a reference, or say plainly that it is not one ----------------------------------
assert dr.parse_ref("12/A-501") == {"detail": "12", "sheet": "A501"}
assert dr.parse_ref(" 12 / A-501 ") == {"detail": "12", "sheet": "A501"}
assert dr.parse_ref("3/S200") == {"detail": "3", "sheet": "S200"}
assert dr.parse_ref("12a/A-501")["detail"] == "12A"
# detail-over-sheet is the convention; the inverse must NOT be silently accepted, because guessing the
# order would invert half a set without any signal that it had happened
assert dr.parse_ref("A-501/12") is None
# free text that merely contains a slash is not a broken reference — it is not a reference
for junk in ("see structural", "N/A", "1:10 @ 24x36", "", None, "///", "12/"):
    assert dr.parse_ref(junk) is None, junk

# sheet numbers are written inconsistently across a real set; normalising is what stops the graph
# reporting a dangling reference that is only a punctuation difference
assert dr.norm_sheet("A-501") == dr.norm_sheet("A501") == dr.norm_sheet("a 501") == "A501"

# ---- the two bubble marks are deliberately DIFFERENT -------------------------------------------------
call = d.callout_bubble(100, 100, "12", "A-501")
assert "12" in call and "A-501" in call
assert call.count("<circle") == 1 and "<line" in call, "a callout bubble is split: detail over sheet"
title = d.detail_title_bubble(50, 400, "12", "Bridge Top Detail", "1:10")
assert "BRIDGE TOP DETAIL" in title and "1:10" in title
# a callout points AWAY and must name its destination sheet; a title bubble says "you have arrived"
assert "A-501" not in title, "a title bubble must not look like a callout to somewhere else"
assert call != title
# both escape — titles come from user data
_t = d.detail_title_bubble(0, 0, "1", "<b>", "1:1")      # titles are drawn uppercase, then escaped
assert "&lt;B&gt;" in _t and "<b>" not in _t, _t
_c = d.callout_bubble(0, 0, "1", "<b>")
assert "&lt;b&gt;" in _c and "<b>" not in _c, _c

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

HDR = {"X-User": "engineer"}


def mk(c, P, number, details=None, callouts=None):
    body = {"data": {"number": number, "sheet_number": number, "title": f"Sheet {number}",
                     "details": details or [], "callouts": callouts or []}}
    r = c.post(f"{P}/modules/drawing", json=body, headers=HDR)
    assert r.status_code in (200, 201), r.text
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Ref Graph"}, headers=HDR).json()["id"]
    P = f"/projects/{pid}"

    # AN EMPTY SET IS **NOT** NAVIGABLE, and this assertion is the fix rather than a tightening.
    # It read `navigable is True` with the comment "vacuously, but it must not report phantom
    # defects". Both halves of that sentence were considered; only the second survives.
    #
    # "Vacuously true" is a correct statement about the logic and a wrong answer to the question. A
    # reader asking *is my set navigable?* was told YES by a register with no references in it —
    # indistinguishable from a fully cross-referenced set, on the one field a caller is most likely
    # to read alone. **The empty case was thought about, named as vacuous, and then returned as the
    # same boolean a clean set returns**, and no consumer can read a word in a test comment.
    #
    # The second half stands and is asserted below: nothing is REPORTED as a defect either. The
    # state is `assessed: False` with its reason — not a pass, not a finding.
    g0 = c.get(f"{P}/drawing-set/references", headers=HDR).json()
    assert g0["navigable"] is False and g0["assessed"] is False, g0
    assert g0["reference_count"] == 0 and g0["detail_count"] == 0, g0
    # ...and NO phantom defects, which is what the original comment was right about
    assert g0["dangling"] == [] and g0["orphans"] == [] and g0["unparseable"] == [], g0
    assert "UNCHECKED set, not a clean one" in (g0["unassessed_reason"] or ""), g0

    # A set with sheets but still no callouts or details is the same state, and it is the COMMON
    # one: `details` and `callouts` are optional fields, so an ordinary drawing register that nobody
    # has cross-referenced yet lands here rather than in the clean case.
    pid0 = c.post("/projects", json={"name": "Sheets Only"}, headers=HDR).json()["id"]
    mk(c, f"/projects/{pid0}", "A-101")
    g0b = c.get(f"/projects/{pid0}/drawing-set/references", headers=HDR).json()
    assert g0b["sheet_count"] == 1 and g0b["assessed"] is False, g0b
    assert g0b["navigable"] is False, g0b
    assert "1 sheet(s) are registered" in (g0b["unassessed_reason"] or ""), g0b

    # A-201 is a wall section calling out three details; A-501 carries two of them.
    mk(c, P, "A-201", callouts=[{"ref": "12/A-501"}, {"ref": "13/A-501"}, {"ref": "99/A-501"},
                                {"ref": "4/A-999"}, {"ref": "see arch"}])
    mk(c, P, "A-501", details=[{"number": "12", "title": "Bridge Top Detail", "scale": "1:10"},
                               {"number": "13", "title": "Sill", "scale": "1:10"},
                               {"number": "77", "title": "Nobody Points Here", "scale": "1:5"}])

    g = c.get(f"{P}/drawing-set/references", headers=HDR).json()
    assert g["sheet_count"] == 2 and g["detail_count"] == 3, g
    assert g["resolved"] == 2, g["edges"]

    # DANGLING, split by reason — the fix differs, so collapsing them would hide which
    reasons = sorted((x["label"], x["reason"]) for x in g["dangling"])
    assert reasons == [("4/A999", "sheet_not_in_set"),
                       ("99/A501", "detail_not_on_sheet")], reasons
    # the un-propagated-renumber case says what IS on that sheet, which is the actionable part
    miss = [x for x in g["dangling"] if x["reason"] == "detail_not_on_sheet"][0]
    assert miss["available"] == ["12", "13", "77"], miss

    # ORPHAN — detail 77 exists, is drawn, costs sheet area, and nothing routes a reader to it
    assert [(o["detail"], o["title"]) for o in g["orphans"]] == [("77", "Nobody Points Here")], g["orphans"]

    # "see arch" is neither resolved nor dangling — it never claimed to be a reference
    assert [u["text"] for u in g["unparseable"]] == ["see arch"], g["unparseable"]
    assert g["navigable"] is False

    # punctuation must not manufacture a defect: A501 and A-501 are ONE sheet
    pid2 = c.post("/projects", json={"name": "Punct"}, headers=HDR).json()["id"]
    Q = f"/projects/{pid2}"
    mk(c, Q, "A-201", callouts=[{"ref": "12/A501"}])
    mk(c, Q, "A-501", details=[{"number": "12", "title": "T", "scale": "1:10"}])
    g2 = c.get(f"{Q}/drawing-set/references", headers=HDR).json()
    assert g2["navigable"] is True, g2
    assert g2["resolved"] == 1 and not g2["dangling"] and not g2["orphans"], g2
    # BOTH DIRECTIONS. Asserting only the empty case would pass a `navigable: False` constant, and
    # asserting only this one would pass the pre-fix unguarded conjunction — the two together are
    # what pin the guard.
    assert g2["assessed"] is True and g2["unassessed_reason"] is None, g2

    # (route authorization is owned by test_route_authz, which enumerates every /projects/{pid} route
    #  and fails on any lacking a require_role gate — asserting it here would only test THIS file's
    #  AEC_TRUST_XUSER env, which makes anonymous permissive, and would pass for the wrong reason)

print("R21-DETAIL-REF OK - the drawing set is now a traversable GRAPH rather than a pile of sheets: "
      "callouts parse as detail-over-sheet, resolve against the details each sheet declares, and the "
      "two defects are reported APART because they have different owners - a dangling callout sends a "
      "reader to a detail that does not exist (the one that surfaces in the field), an orphan detail "
      "is drawn and paid for and never reached. Dangling splits again by reason, since an unknown "
      "SHEET is a typo or an unissued sheet while a known sheet missing the detail NUMBER is almost "
      "always a renumber nobody propagated - so the report names what IS on that sheet. The inverse "
      "'A-501/12' is refused rather than guessed, because silently inverting the order would corrupt "
      "half a set with no signal; free text that merely contains a slash is reported as unparseable "
      "rather than counted as broken; and sheet numbers are normalised so A501 and A-501 are one "
      "sheet, which is what stops the check manufacturing defects out of punctuation.")
