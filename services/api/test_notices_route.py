"""R22-NOTICE-CLOCK over HTTP — the register is reachable, and it reads the real field record.

The engine's arithmetic and its refusals are tested in `test_notice_clock.py`. This asserts the
three things only a live app can show: that the endpoints answer, that the register is assembled
from records created through the ordinary module API (not from a fixture handed to the engine), and
that the adopted contract family is read off the project's own prime-contract record rather than
from a server default.

The last one is the point of the feature. A register that quietly falls back to a default contract
form produces dates that look exactly like correct ones.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_notices_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_notices_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_notices_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_notices_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


TODAY = "2026-03-30"

with TestClient(app) as c:
    c.headers.update({"X-User": "notices@test"})
    pid = c.post("/projects", json={"name": "Notice Tower"}).json()["id"]

    # --- the library is reachable and self-describing ------------------------------------------
    lib = c.get(f"/projects/{pid}/notices/clauses")
    check("GET /notices/clauses answers 200", lib.status_code == 200, lib.text[:200])
    L = lib.json()
    check("  it lists the families", len(L["families"]) >= 7)
    check("  every clause carries its citation", all(cl["citation"] for cl in L["clauses"]))
    check("  and the verify warning is on the response, not just in the docs",
          "executed contract" in L["verify"])
    one = c.get(f"/projects/{pid}/notices/clauses?family=fidic_red_2017").json()
    check("  filtering by family works",
          {cl["family"] for cl in one["clauses"]} == {"fidic_red_2017"})
    check("  an unknown family is a 422",
          c.get(f"/projects/{pid}/notices/clauses?family=aia_1997").status_code == 422)
    check("  an unknown event type is a 422",
          c.get(f"/projects/{pid}/notices/clauses?event_type=meteor").status_code == 422)

    # --- an empty project: no events, and crucially no adopted family --------------------------
    empty = c.get(f"/projects/{pid}/notices?as_of={TODAY}")
    check("GET /notices answers 200 on an empty project", empty.status_code == 200, empty.text[:200])
    E = empty.json()
    check("  nothing is adopted yet", E["adopted"] is False and E["adopted_family"] is None)
    check("  and it says so rather than picking a default", "cannot be inferred" in E["why"])

    # --- real records, created the ordinary way ------------------------------------------------
    def create(key, data):
        # POST-create wraps the field map in {"data": ...}; PATCH takes it bare. Two shapes, one
        # engine — see the `module-patch-shape` note.
        r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), (key, r.status_code, r.text[:200])
        return r.json()

    create("daily_report", {"report_date": "2026-03-02", "weather": "Snow",
                            "weather_impact": "Full-Day Lost"})
    create("daily_report", {"report_date": "2026-03-25", "weather": "Rain",
                            "weather_impact": "Minor Delay"})
    create("change_event", {"reason": "Unforeseen Condition", "subject": "Rock at footing F-3"})

    still = c.get(f"/projects/{pid}/notices?as_of={TODAY}").json()
    check("events are found even before a family is adopted", still["events_found"] >= 2,
          still["events_found"])
    check("  but the register stays empty until one is", still["items"] == [])

    # --- adopt a family on the prime contract ---------------------------------------------------
    create("prime_contract", {"name": "Prime", "owner": "Owner LLC",
                              "notice_family": "FIDIC Red Book 2017"})
    reg = c.get(f"/projects/{pid}/notices?as_of={TODAY}")
    check("after adoption the register computes", reg.status_code == 200, reg.text[:200])
    R = reg.json()
    check("  the family came off the prime contract record",
          R["adopted_family"] == "fidic_red_2017" and R["adopted_raw"] == "FIDIC Red Book 2017")
    check("  and the label the UI shows resolved to it", R["adopted"] is True)
    check("  there are items now", len(R["items"]) > 0)
    check("  every item names the clause it was computed from",
          all(i.get("clause") for i in R["items"]), [i.get("status") for i in R["items"]])
    check("  FIDIC runs from awareness, which nothing recorded → indeterminate, not a guess",
          all(i["status"] == "indeterminate" for i in R["items"]),
          {i["status"] for i in R["items"]})
    check("  and each says which field is missing",
          all(i.get("missing") == ["became_aware_on"] for i in R["items"]))

    # --- record the awareness date and the clock starts ------------------------------------------
    ce = c.get(f"/projects/{pid}/modules/change_event").json()
    rid = (ce["records"] if isinstance(ce, dict) else ce)[0]["id"]
    patched = c.patch(f"/projects/{pid}/modules/change_event/{rid}",
                      json={"became_aware_on": "2026-03-20"})
    check("the change event accepts an awareness date", patched.status_code == 200,
          patched.text[:200])
    R2 = c.get(f"/projects/{pid}/notices?as_of={TODAY}").json()
    dsc = [i for i in R2["items"]
           if i["event"]["type"] == "differing_site_condition" and i.get("due_date")]
    check("with awareness recorded, the FIDIC clock computes", bool(dsc),
          [i["status"] for i in R2["items"]])
    if dsc:
        c281 = next((i for i in dsc if i["clause"] == "fidic_red_2017.20.2.1"), None)
        check("  28 days from awareness", c281 and c281["due_date"] == "2026-04-17",
              c281 and c281["due_date"])
        check("  and it is an express time bar", c281["consequence"] == "express_time_bar")

    # --- the what-if override is labelled as one -------------------------------------------------
    ov = c.get(f"/projects/{pid}/notices?as_of={TODAY}&family=aia_a201_2017").json()
    check("a family override is honoured", ov["family"] == "aia_a201_2017")
    check("  and reported as a what-if, not as the project's position",
          ov.get("override", {}).get("family") == "aia_a201_2017"
          and "what-if" in ov["override"]["note"])
    check("  while the adopted family is still reported alongside it",
          ov["adopted_family"] == "fidic_red_2017")
    check("an unknown override is a 422",
          c.get(f"/projects/{pid}/notices?family=nec2").status_code == 422)

    # --- the calendar inputs reach the engine ----------------------------------------------------
    check("a bad weekend is a 422, not a silent default",
          c.get(f"/projects/{pid}/notices?weekend=Funday").status_code == 422)
    check("a bad holiday date is a 422",
          c.get(f"/projects/{pid}/notices?holidays=2026-13-45").status_code == 422)
    gulf = c.get(f"/projects/{pid}/notices?as_of={TODAY}&weekend=Fri,Sat&holidays=2026-04-01").json()
    check("the calendar used is reported back",
          gulf["calendar"]["weekend"] == ["Fri", "Sat"]
          and gulf["calendar"]["holidays_supplied"] == 1, gulf["calendar"])

    # --- drafting --------------------------------------------------------------------------------
    if dsc:
        dr = c.post(f"/projects/{pid}/notices/draft?from_party=Acme%20Construction", json=dsc[0])
        check("POST /notices/draft answers 200", dr.status_code == 200, dr.text[:200])
        letter = dr.json()["letter"]
        check("  the letter names the project", "Notice Tower" in letter)
        check("  quotes the clause", dsc[0]["citation"][:40] in letter)
        check("  and carries the due date through", dr.json()["due_date"] == dsc[0]["due_date"])
    check("drafting from a non-item is a 422, not a 500",
          c.post(f"/projects/{pid}/notices/draft", json={"nope": 1}).status_code == 422)
    check("drafting from an event with no date is a 422",
          c.post(f"/projects/{pid}/notices/draft", json={"event": {}}).status_code == 422)

print()
if FAILED:
    print(f"notices_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("notices_route: all checks passed")
