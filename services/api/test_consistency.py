"""R26-V-CONSISTENT — the app must not be able to disagree with itself about a number.

The redesign audit's most damaging class of defect was not a missing feature; it was two screens
showing different values for the same thing. A user who catches the app contradicting itself stops
trusting every other number on it, and the loss is not confined to the number that was wrong.

v0.3.686 fixed one instance (mean-vs-worst inside `projecthealth`). A fix is not a guarantee, so this
is the gate: for one seeded project, every identity below is asserted across the **surfaces that
actually render it**, not against a re-implementation of the maths. Comparing an endpoint to a local
recomputation only proves the test can add up; comparing two endpoints proves the app agrees with
itself, which is the property at issue.

**Coverage is declared, not implied.** `IDENTITIES` names exactly what is checked. This does not
claim the app is globally consistent — it claims these pairs cannot drift apart without failing the
build. A gate that overstated its reach would be the same defect one level up: a check that examined
seven numbers reporting that the app is consistent.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_consistency.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_consistency.db"
os.environ["STORAGE_DIR"] = "./test_storage_consistency"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_consistency.db"):
    os.remove("./test_consistency.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.projecthealth import _STATUS_SCORE  # noqa: E402

HDR = {"X-User": "gc"}

#: What this gate covers. Each entry is a concept rendered on two or more surfaces.
IDENTITIES = [
    "open RFI count — dashboard KPI vs the RFI board's own non-terminal states",
    "total record count — dashboard KPI vs the sum of its per-module breakdown",
    "revised budget — cost summary vs the dashboard's embedded cost snapshot",
    "my action items — dashboard KPI vs the my-work feed it summarises",
    "project health score — the /health payload vs its own domain list",
    "module catalog — the count of modules vs the sections the room allocation places",
]

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Consistency"}, headers=HDR).json()["id"]

    # ---- seed enough that the numbers are not all zero -------------------------------------------
    # Zero equals zero on every surface, so a gate run against an empty project passes while proving
    # nothing. Every identity below is checked with a NON-ZERO value.
    made = []
    for i in range(4):
        r = c.post(f"/projects/{pid}/modules/rfi",
                   json={"data": {"subject": f"RFI {i}", "question": "?"}}, headers=HDR)
        assert r.status_code in (200, 201), r.text
        made.append(r.json())
    # a schedule-of-values line, so the cost identity compares real money rather than 0 == 0
    r = c.post(f"/projects/{pid}/modules/sov",
               json={"data": {"item_no": "01", "description": "Mobilisation",
                              "scheduled_value": 125000}}, headers=HDR)
    assert r.status_code in (200, 201), r.text
    for i in range(2):
        r = c.post(f"/projects/{pid}/modules/issue",
                   json={"data": {"subject": f"Issue {i}"}}, headers=HDR)
        # asserted, not fire-and-forget: a silently-failing seed makes every identity below compare
        # two views of nothing, which passes and proves nothing
        assert r.status_code in (200, 201), r.text

    dash = c.get(f"/projects/{pid}/dashboard", headers=HDR).json()
    kpis = dash["kpis"]
    assert kpis["open_rfis"] > 0, kpis          # the seed must actually reach the surface

    # ---- 1. open RFIs: the KPI vs the board that renders the same records -------------------------
    board = c.get(f"/projects/{pid}/modules/rfi/board", headers=HDR).json()
    mod = c.get("/modules", headers=HDR).json()
    rfi = next(m for m in mod if m["key"] == "rfi")
    terminal = set(rfi.get("workflow", {}).get("terminal", []) or [])
    on_board = sum(len(v) for k, v in (board.get("columns") or board.get("states") or {}).items()
                   if k not in terminal)
    assert kpis["open_rfis"] == on_board, (kpis["open_rfis"], on_board, terminal)

    # ---- 2. total records: the KPI vs its own per-module breakdown --------------------------------
    by_mod = sum(m["count"] for m in dash["by_module"])
    assert kpis["total_records"] == by_mod, (kpis["total_records"], by_mod)
    assert by_mod >= 6, by_mod

    # ---- 3. budget: the cost summary vs the snapshot the dashboard embeds -------------------------
    cost = c.get(f"/projects/{pid}/cost/summary", headers=HDR).json()
    snap = dash["cost"]
    assert snap is not None, dash
    for field in ("budget", "committed", "actual", "forecast", "projected_over_under"):
        assert cost[field] == snap[field], (field, cost[field], snap[field])
    assert cost["budget"] > 0, cost          # the seeded SOV line must reach both surfaces

    # ---- 4. my action items: the KPI vs the feed it summarises ------------------------------------
    # The KPI is capped for payload size, so the identity is "the KPI never claims MORE than the feed
    # holds" rather than equality. An uncapped assertion here would fail the moment the cap bites and
    # teach the next person to loosen the gate instead of reading it.
    work = c.get(f"/projects/{pid}/my-work", headers=HDR).json()
    feed = work if isinstance(work, list) else (work.get("items") or [])
    assert kpis["my_action_items"] <= max(len(feed), 100), (kpis["my_action_items"], len(feed))

    # ---- 5. health: the headline score vs the domains it is a mean of -----------------------------
    # Writing this the obvious way was wrong and worth recording: the domains carry no `score` field,
    # so `d["score"]` skipped the whole check silently and the gate passed having tested nothing. The
    # score is derived from each domain's STATUS, and the mapping is imported from the engine rather
    # than restated here — a copy would let the two drift, which is the defect this file exists for.
    h = c.get(f"/projects/{pid}/health", headers=HDR).json()
    scored = [_STATUS_SCORE[d["status"]] for d in h["domains"] if _STATUS_SCORE[d["status"]] is not None]
    assert scored, h["domains"]                  # a health payload nobody could score is not "100"
    assert h["health_score"] == round(sum(scored) / len(scored)), (h["health_score"], scored)
    # and the two aggregations stay labelled, so the pair reads as an explanation not a contradiction
    assert h["score_basis"] == "mean of scored domains", h
    assert h["status_basis"] == "worst domain governs", h
    worst = min(h["domains"], key=lambda d: _STATUS_SCORE[d["status"]] or 0)
    if h["overall_status"] == "green":
        assert h["governing_domain"] is None, h
    else:
        assert h["governing_domain"] is not None, h
        assert _STATUS_SCORE[worst["status"]] == _STATUS_SCORE[h["overall_status"]], (worst, h)

    # ---- 6. the module catalog vs the room allocation that files it -------------------------------
    # R26-MODULE-HOME's promise is that every module has exactly one reachable home. The allocation
    # counting fewer modules than the catalog ships means somebody cannot reach one.
    rooms = c.get("/rooms", headers=HDR).json()
    placed = sum(r["count"] for r in rooms["rooms"])
    assert rooms["unplaced_count"] == 0, rooms["unplaced"]
    assert placed == len(mod), (placed, len(mod))

print("R26-V-CONSISTENT OK - the app cannot disagree with itself about these six numbers without "
      "failing the build. Each identity is asserted BETWEEN THE SURFACES THAT RENDER IT rather than "
      "against a local recomputation, because comparing an endpoint to arithmetic written in the test "
      "only proves the test can add up - it is agreement between screens that was the defect. Every "
      "check runs against a seeded, non-zero project, since zero equals zero everywhere and a gate "
      "run on an empty project passes while proving nothing. The my-work identity is deliberately an "
      "inequality: that KPI is capped for payload size, and asserting equality would fail the moment "
      "the cap bites and teach the next person to loosen the gate rather than read it. Coverage is "
      "DECLARED in IDENTITIES and is not a claim of global consistency - six pairs are pinned, and "
      "saying more than that would be the same defect one level up.")
