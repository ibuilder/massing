"""Search + saved-search alerts. Covers the portable search filter (SQLite LIKE fallback here; the
Postgres full-text path is dialect-gated + smoke-tested separately) and the saved-view alert feed
(total + new-since-last-seen counts, cleared by marking a view seen).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_search_alerts.py"""
import os
import time

os.environ["DATABASE_URL"] = "sqlite:///./test_search_alerts.db"
os.environ["STORAGE_DIR"] = "./test_storage_search_alerts"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_search_alerts.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import modules as me            # noqa: E402
from fastapi.testclient import TestClient    # noqa: E402
from aec_api.main import app                 # noqa: E402

# --- pure: safe prefix tsquery builder --------------------------------------
assert me._pg_tsquery("concrete") == "concrete:*"
assert me._pg_tsquery("conc beam") == "conc:* & beam:*"
assert me._pg_tsquery("03-3000") == "03:* & 3000:*"        # hyphen splits into prefix-matched words
assert me._pg_tsquery("   ") is None

mk = lambda c, pid, code, desc: c.post(f"/projects/{pid}/modules/cost_code",         # noqa: E731
                                       json={"data": {"code": code, "description": desc}})

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "SA"}).json()["id"]
    mk(c, pid, "03-3000", "Cast-in-place concrete")
    mk(c, pid, "05-1200", "Structural steel")

    # search (SQLite LIKE fallback path): matches a data field, case-insensitive
    assert len(c.get(f"/projects/{pid}/modules/cost_code?q=STEEL").json()) == 1

    # --- saved-search alerts -------------------------------------------------
    c.post(f"/projects/{pid}/modules/cost_code/views", json={"name": "Steel watch", "config": {"q": "steel"}})
    al = c.get(f"/projects/{pid}/views/alerts").json()
    steel = next(v for v in al if v["name"] == "Steel watch")
    assert steel["module"] == "cost_code" and steel["total"] == 1 and steel["new"] == 1, steel   # never seen -> all new
    vid = steel["id"]

    # mark seen -> new clears, total stays
    assert c.post(f"/projects/{pid}/modules/cost_code/views/{vid}/seen").json()["ok"] is True
    steel = next(v for v in c.get(f"/projects/{pid}/views/alerts").json() if v["id"] == vid)
    assert steel["new"] == 0 and steel["total"] == 1, steel

    # a new matching record after last-seen -> shows up as new (not counted against non-matching adds)
    time.sleep(0.05)
    mk(c, pid, "05-9000", "Misc steel accessories")
    mk(c, pid, "09-2900", "Gypsum board")                  # does NOT match "steel"
    steel = next(v for v in c.get(f"/projects/{pid}/views/alerts").json() if v["id"] == vid)
    assert steel["total"] == 2 and steel["new"] == 1, steel

    # marking seen again clears it
    c.post(f"/projects/{pid}/modules/cost_code/views/{vid}/seen")
    steel = next(v for v in c.get(f"/projects/{pid}/views/alerts").json() if v["id"] == vid)
    assert steel["new"] == 0, steel

    # --- state_counts: per-state tallies via SQL GROUP BY (dashboards/rollups count without loading
    # the rows). Sum of the tally must equal the total record count; unknown module -> {}.
    from aec_api.db import SessionLocal  # noqa: E402
    with SessionLocal() as _db:
        sc = me.state_counts(_db, "cost_code", pid)
        assert sum(sc.values()) == me.count_records(_db, "cost_code", pid) == 4, (sc, "expected 4 total")
        assert me.state_counts(_db, "cost_code", "no-such-project") == {}, "unknown project -> empty"
        assert me.state_counts(_db, "not_a_module", pid) == {}, "unknown module -> empty"

print("SEARCH+ALERTS OK - prefix tsquery builder; SQLite search fallback matches a data field; saved-"
      "view alerts report total + new-since-last-seen, a never-seen view counts all as new, mark-seen "
      "clears the count, and only matching new records increment it")
