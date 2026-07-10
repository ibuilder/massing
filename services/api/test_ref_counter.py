"""P0-d: human refs come from an atomic per-(project,module) counter — deleting a record must NOT let a
later create reuse a ref (the old COUNT(*) scheme did). Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ref_counter.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ref_counter.db"
os.environ["STORAGE_DIR"] = "./test_storage_ref_counter"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_ref_counter.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

H = {"X-User": "admin"}
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Refs"}).json()["id"]
    mk = lambda: c.post(f"/projects/{pid}/modules/rfi", headers=H,   # noqa: E731
                        json={"data": {"subject": "x", "question": "y?"}}).json()
    r1, r2, r3 = mk(), mk(), mk()
    refs = [r1["ref"], r2["ref"], r3["ref"]]
    assert refs == ["RFI-001", "RFI-002", "RFI-003"], refs
    # delete the last two, then create again — the new ref must be 004, never a reused 002/003
    for r in (r3, r2):
        c.delete(f"/projects/{pid}/modules/rfi/{r['id']}", headers=H)
    r4 = mk()
    assert r4["ref"] == "RFI-004", f"ref reused after delete: {r4['ref']}"
    # and all refs ever minted are unique
    assert len({*refs, r4["ref"]}) == 4

print("REF-COUNTER OK - refs come from an atomic per-(project,module) counter; deleting records does "
      "not cause a later create to reuse a ref (RFI-004 after deleting 002/003, never a collision).")
