"""CLIENT-PORTAL (SPRINT D phase-1) — tokenized read-only project digest. Mint a share token (editor),
read the curated digest via the PUBLIC /shared/{token}/digest route (no auth), confirm it exposes only
high-level readiness (no record-level data / GUIDs / findings detail), that views are counted, and that
revoking or an unknown token 404s.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_client_portal.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_client_portal.db"
os.environ["STORAGE_DIR"] = "./test_storage_clientportal"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_client_portal.db"):
    os.remove("./test_client_portal.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import client_portal  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Harbour Point"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).jurisdiction = "CA"
        db.commit()

    # --- mint a share token (editor) ------------------------------------------------------------------
    mk = c.post(f"/projects/{pid}/share-tokens", json={"label": "Owner review"})
    assert mk.status_code == 200, mk.text[:200]
    tok = mk.json()["token"]
    assert len(tok) >= 24 and mk.json()["label"] == "Owner review" and mk.json()["revoked"] is False, mk.json()
    assert mk.json()["share_path"] == f"/shared/{tok}/digest", mk.json()

    lst = c.get(f"/projects/{pid}/share-tokens").json()["tokens"]
    assert len(lst) == 1 and lst[0]["token"] == tok, lst

    # --- PUBLIC digest: no auth header, curated fields only -------------------------------------------
    d = c.get(f"/shared/{tok}/digest")
    assert d.status_code == 200, d.text[:200]
    j = d.json()
    assert j["project"] == "Harbour Point" and j["jurisdiction"] == "CA", j
    assert {"readiness_pct", "ready_steps", "gap_steps", "step_count", "steps"} <= set(j), list(j)
    assert len(j["steps"]) == 8, j["steps"]
    # SAFETY: each step exposes ONLY n/title/status — no findings, gaps, links, or record-level data leak
    for s in j["steps"]:
        assert set(s) == {"n", "title", "status"}, s
    # the whole digest must not leak record-ish keys
    assert not any(k in j for k in ("disclaimer_findings", "guids", "records", "budget", "financials")), list(j)
    assert "no record-level data" in j["note"].lower(), j["note"]

    # a second view increments the counter (audited on the token)
    c.get(f"/shared/{tok}/digest")
    assert c.get(f"/projects/{pid}/share-tokens").json()["tokens"][0]["view_count"] == 2, "view not counted"

    # --- revoke → immediate 404; unknown token → 404 (no enumeration signal) --------------------------
    assert c.delete(f"/projects/{pid}/share-tokens/{tok}").status_code == 200
    assert c.get(f"/shared/{tok}/digest").status_code == 404, "revoked token still readable!"
    assert c.delete(f"/projects/{pid}/share-tokens/{tok}").status_code == 404   # already revoked
    assert c.get("/shared/totally-made-up-token/digest").status_code == 404

    # tokens are strong + unique across mints
    toks = {c.post(f"/projects/{pid}/share-tokens", json={}).json()["token"] for _ in range(5)}
    assert len(toks) == 5, "tokens not unique"

    # --- engine: the per-project live-token cap is enforced -------------------------------------------
    with SessionLocal() as db:
        # 5 live already; drive to the cap and assert it raises rather than minting unbounded tokens
        try:
            for _ in range(client_portal._MAX_TOKENS):
                client_portal.create_token(db, pid, None, "system")
            raised = False
        except ValueError:
            raised = True
    assert raised, "live-token cap not enforced"

print("CLIENT-PORTAL OK - an editor mints a revocable read-only share token; the PUBLIC /shared/{token}/"
      "digest route (no auth) returns a curated readiness digest (project + jurisdiction + per-step "
      "title/status ONLY — no findings, GUIDs, financials, or record-level data), counts each view on the "
      "token, and 404s the moment the token is revoked or when the token is unknown; tokens are strong + "
      "unique and the per-project live-token cap is enforced.")
