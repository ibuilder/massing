"""R22-ITP-NCR ② over HTTP — records attach to real elements through the platform's own column.

The status rules are pinned in `test_quality_chain.py` against synthesised rows. What only a live app
shows is that the attachment path actually closes: an `ncr` record created through the module engine,
linked with `POST .../elements` (the route that already existed), comes back out of the chain
against that GlobalId — and that closeout readiness reflects it.

This is what makes it a *reach* seam rather than a new register: no field was added and no migration
was written. The attachment mechanism was already there and already routed; nothing read it.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_quality_chain_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_quality_chain_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_quality_chain_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_quality_chain_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


G1 = "1a2b3c4d5e6f7g8h9i0jkl"
G2 = "2b3c4d5e6f7g8h9i0jklmn"
G3 = "3c4d5e6f7g8h9i0jklmnop"

with TestClient(app) as c:
    c.headers.update({"X-User": "quality@test"})
    pid = c.post("/projects", json={"name": "Quality Chain"}).json()["id"]

    def mk(key, **data):
        r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), (key, r.status_code, r.text[:200])
        return r.json()["id"]

    def attach(key, rid, guids):
        # POST .../elements — the route that already existed. My first draft invented
        # `PUT .../element-guids`, which 404s; the same invented path was also in the module's
        # user-facing message, so it would have shipped an instruction leading nowhere.
        return c.post(f"/projects/{pid}/modules/{key}/{rid}/elements", json={"guids": guids})

    empty = c.get(f"/projects/{pid}/quality/chain")
    check("GET /quality/chain answers 200 with nothing recorded", empty.status_code == 200,
          empty.text[:200])
    E = empty.json()
    check("  and reports no attachment rather than an empty success",
          E["any_attached"] is False and E["message"] is not None)

    # records exist but name no element — the state the registers have been in all along
    ncr_id = mk("ncr", subject="Honeycombing at column base", severity="Major", disposition="Repair")
    itp_id = mk("itp", activity="Concrete placement", point_type="Hold",
                acceptance_criteria="ACI 318", responsible_party="GC")
    unattached = c.get(f"/projects/{pid}/quality/chain").json()
    check("records with no element are counted, not silently dropped",
          unattached["records_total"] == 2 and unattached["any_attached"] is False,
          (unattached["records_total"], unattached["any_attached"]))
    check("  and readiness is not 'ready' just because nothing is attached",
          c.get(f"/projects/{pid}/quality/turnover-readiness").json()["ready"] is False)

    # attach through the route that already existed — no new field, no migration
    a1 = attach("ncr", ncr_id, [G1])
    check("POST .../elements attaches a quality record to an element",
          a1.status_code in (200, 201), (a1.status_code, a1.text[:160]))
    attach("itp", itp_id, [G1])

    J = c.get(f"/projects/{pid}/quality/chain").json()
    check("the chain now reports that element", J["element_count"] == 1, J["element_count"])
    el = J["elements"][0]
    check("  by its GlobalId", el["guid"] == G1, el["guid"])
    check("  as OUTSTANDING — the NCR is open and the hold point unverified",
          el["status"] == "outstanding", el["status"])
    check("  the open items name their module", {x["module"] for x in el["open_items"]} == {"ncr", "itp"},
          el["open_items"])
    check("  and the unverified HOLD point is called out specifically",
          [h["point_type"] for h in el["unverified_hold_points"]] == ["Hold"],
          el["unverified_hold_points"])

    # A CLEAR element, built on a second GlobalId. Action names are READ from each module's
    # workflow (itp: planned -(release)-> active -(verify)-> verified; inspection: scheduled
    # -(pass)-> passed). My first pass guessed "start" for the ITP; a transition that no-ops looks
    # exactly like one that ran, so only the status assertion caught it.
    itp2 = mk("itp", activity="Rebar placement", point_type="Witness", responsible_party="GC",
                acceptance_criteria="ACI 318 lap length")  # `verify` refuses without it
    insp2 = mk("inspection", subject="Rebar", inspection_type="Structural", inspector="EOR",
                date="2026-03-01")
    attach("itp", itp2, [G3])
    attach("inspection", insp2, [G3])
    for key, rid, actions in (("itp", itp2, ("release", "verify")), ("inspection", insp2, ("pass",))):
        for action in actions:
            r = c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})
            assert r.status_code == 200, (key, action, r.status_code, r.text[:160])

    J2 = c.get(f"/projects/{pid}/quality/chain?guids={G3}").json()
    check("an element whose evidence is all resolved reads CLEAR",
          J2["elements"][0]["status"] == "clear",
          (J2["elements"][0]["status"], J2["elements"][0]["open_items"]))

    # The NCR close gate is a REAL product rule and worth pinning: `close` refuses without attached
    # evidence. That is the evidence chain enforcing itself one level down, and it means an element
    # cannot go clear by someone simply marking the NCR closed.
    gate = c.post(f"/projects/{pid}/modules/ncr/{ncr_id}/transition", json={"action": "disposition"})
    assert gate.status_code == 200, gate.text[:160]
    blocked = c.post(f"/projects/{pid}/modules/ncr/{ncr_id}/transition", json={"action": "close"})
    check("closing an NCR without evidence is refused, so an element cannot be cleared by fiat",
          blocked.status_code == 400 and "attachment" in blocked.text, blocked.status_code)
    check("  and that element therefore stays OUTSTANDING",
          c.get(f"/projects/{pid}/quality/chain?guids={G1}").json()["elements"][0]["status"]
          == "outstanding")

    # THE RULE, over HTTP: an element nobody recorded is not a pass.
    T = c.get(f"/projects/{pid}/quality/turnover-readiness?guids={G1},{G2}").json()
    check("asking about an unrecorded element makes turnover NOT ready",
          T["ready"] is False and T["unrecorded_count"] == 1, T)
    check("  the unrecorded element is named", T["unrecorded_elements"] == [G2],
          T["unrecorded_elements"])
    check("  and coverage says half, not all", T["coverage_pct"] == 50.0, T["coverage_pct"])
    C2 = c.get(f"/projects/{pid}/quality/chain?guids={G2}").json()
    check("  its status is 'unrecorded', never 'clear'",
          C2["elements"][0]["status"] == "unrecorded", C2["elements"][0]["status"])

    # additive — the pre-existing quality dashboard is untouched
    q = c.get(f"/projects/{pid}/quality/summary")
    check("the existing quality summary still answers 200", q.status_code == 200, q.text[:160])

print()
if FAILED:
    print(f"quality_chain_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("quality_chain_route: all checks passed")
