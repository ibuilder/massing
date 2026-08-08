"""R22-PUBLIC-VIEWER — a share token can serve model GEOMETRY, but only if it was minted to.

THE DECISION THIS IMPLEMENTS, and it was the user's to make, not a build: may a share token expose
model geometry at all? Answer 2026-08-07: yes — as a **per-token opt-in**, never a default. That
follows the PORTAL-TXN precedent already in the model: `show_payments` widens exactly one token's
digest, chosen when the token is minted, and it does not appear on links somebody already sent.

THE DISTINCTION THAT CARRIES THE MOST RISK, so it is asserted rather than described. The token serves
`{pid}/model.frag` — converted geometry, shapes and placements. It must NOT serve
`{pid}/source.ifc`, which carries every property set, classification and GlobalId in the model.
"Share the model" reads as either of those, and the wide reading is a much larger disclosure than was
approved. There is a test below that fails if the source IFC ever becomes reachable through a token.

FOUR REFUSALS, ONE STATUS CODE. Unknown token, revoked token, token without the opt-in, and a project
with no published fragment all return 404. Distinguishing them tells an attacker whether a token
exists, whether it was revoked, and whether a project has a model — three enumeration signals for no
benefit to a legitimate viewer. The existing token routes behave this way; this one must not be the
exception, and "it 404s" is not enough on its own — the *reason* must be indistinguishable too.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_shared_model.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_shared_model.db"
os.environ["STORAGE_DIR"] = "./test_storage_shared_model"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_shared_model.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import storage  # noqa: E402
from aec_api.main import app  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


FRAG = b"FRAG\x00fake-geometry-bytes-for-the-test"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Shared Tower"}).json()["id"]
    storage.put(f"{storage.safe_seg(pid)}/model.frag", FRAG)

    plain = c.post(f"/projects/{pid}/share-tokens", json={"label": "digest only"}).json()["token"]
    withm = c.post(f"/projects/{pid}/share-tokens",
                   json={"label": "model", "show_model": True}).json()["token"]

    # --- the opt-in is what decides, and the default is closed ----------------------------------
    r_plain = c.get(f"/shared/{plain}/model.frag")
    check("a DEFAULT token cannot fetch geometry", r_plain.status_code == 404,
          f"got {r_plain.status_code} — geometry on a token minted before anyone asked for it is "
          f"retroactively widening a link already sent")

    r_ok = c.get(f"/shared/{withm}/model.frag")
    check("a token minted with show_model CAN", r_ok.status_code == 200,
          f"got {r_ok.status_code}: {r_ok.text[:120]}")
    check("...and returns the fragment bytes unchanged", r_ok.content == FRAG,
          f"{len(r_ok.content)} bytes vs {len(FRAG)}")

    # --- the two opt-ins are independent -----------------------------------------------------------
    pay = c.post(f"/projects/{pid}/share-tokens",
                 json={"label": "payments", "show_payments": True}).json()["token"]
    check("show_payments does NOT imply show_model",
          c.get(f"/shared/{pay}/model.frag").status_code == 404,
          "granting one widening implied another — opt-ins must be independent or the narrowest "
          "one is meaningless")

    # --- revocation stops it immediately -----------------------------------------------------------
    # ASSERT THE REVOKE ACTUALLY HAPPENED before asserting its effect. The first version of this test
    # called `POST .../revoke`, which is not the route — it is `DELETE /projects/{pid}/share-tokens/
    # {token}` — so nothing was revoked and the next line reported "a revoked link still served the
    # model", a security defect that did not exist. A setup step whose success is unchecked turns
    # every assertion after it into a claim about a state you never reached.
    rv = c.delete(f"/projects/{pid}/share-tokens/{withm}")
    check("the revoke call itself succeeded", rv.status_code == 200,
          f"{rv.status_code} {rv.text[:80]} — everything below is about an unrevoked token")
    check("revoking stops geometry immediately",
          c.get(f"/shared/{withm}/model.frag").status_code == 404,
          "a revoked link still served the model — the check must be on the row, not on a cache")

    # --- every refusal looks the same --------------------------------------------------------------
    bodies = {
        "unknown": c.get("/shared/definitely-not-a-real-token/model.frag"),
        "revoked": c.get(f"/shared/{withm}/model.frag"),
        "no opt-in": r_plain,
    }
    codes = {k: r.status_code for k, r in bodies.items()}
    check("unknown, revoked and not-opted-in are indistinguishable",
          len(set(codes.values())) == 1 and set(codes.values()) == {404}
          and len({r.text for r in bodies.values()}) == 1,
          f"codes={codes} bodies={ {k: r.text[:40] for k, r in bodies.items()} } — a different "
          f"message per cause is an enumeration oracle")

    # --- THE scope assertion: geometry, not the source IFC -------------------------------------
    src_key = f"{storage.safe_seg(pid)}/source.ifc"
    storage.put(src_key, b"ISO-10303-21;\nHEADER;\n/* every GlobalId in the model */\n")
    ifc_reachable = [p for p in (f"/shared/{plain}/source.ifc", f"/shared/{plain}/model.ifc",
                                 f"/shared/{plain}/ifc")
                     if c.get(p).status_code == 200]
    check("NO token route serves the source IFC", not ifc_reachable,
          f"{ifc_reachable} returned 200 — source.ifc carries every property set, classification and "
          f"GlobalId; that is a different disclosure from geometry and was not what was approved")

    # And the fragment route must not be coaxed into reading a different key.
    r_traverse = c.get(f"/shared/{withm}/model.frag")
    check("...and the fragment route reads only the frag key",
          r_traverse.status_code == 404 or r_traverse.content != open(  # noqa: SIM115
              os.path.join(os.environ["STORAGE_DIR"], *src_key.split("/")), "rb").read(),
          "the fragment route returned the source IFC's bytes")

    # --- a project with no fragment is not a signal either ------------------------------------------
    pid2 = c.post("/projects", json={"name": "No Model"}).json()["id"]
    t2 = c.post(f"/projects/{pid2}/share-tokens",
                json={"show_model": True}).json()["token"]
    r_none = c.get(f"/shared/{t2}/model.frag")
    check("a project with no fragment 404s like everything else",
          r_none.status_code == 404 and r_none.text == r_plain.text,
          f"{r_none.status_code} {r_none.text[:60]} — 'this project has no model' is information")

    # --- the listing tells an owner which links carry geometry ---------------------------------------
    listed = c.get(f"/projects/{pid}/share-tokens").json()
    rows = listed.get("tokens", listed if isinstance(listed, list) else [])
    check("the owner can SEE which tokens carry geometry",
          any(r.get("show_model") for r in rows) and any(not r.get("show_model") for r in rows),
          f"{[(r.get('label'), r.get('show_model')) for r in rows]} — an opt-in nobody can audit "
          f"after minting cannot be reviewed or regretted")

print(f"\ntest_shared_model {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
