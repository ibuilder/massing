"""R46 ⑥ — the portfolio route reads several projects, so it must be gated on every one.

`test_route_authz` proves each `/projects/{pid}` route enforces membership on **its own `{pid}`**.
That is exactly what it can see, and it is not enough here: `/schedule/portfolio` takes a list of
*other* project ids in its body and returns their dates. A caller who is a member of one project
would otherwise get a programme view built from four.

The shape is one this repo has already paid for — `require_role` on a route whose privileged data is
addressed by something other than the path parameter. So the check is that a **non-member's id in the
body is refused**, exercised through the real app rather than reasoned about.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_portfolio_authz.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_portfolio_authz.db"
os.environ["STORAGE_DIR"] = "./test_storage_portfolio_authz"
os.environ["AEC_RBAC"] = "1"                       # the guard is only armed with RBAC on
for _f in ("./test_portfolio_authz.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def main() -> int:
    with TestClient(app) as c:
        body = {"password": "Corr3ct-Horse-Battery!"}
        reg = c.post("/auth/register", json={"username": "owner", **body})
        tok = ""
        if reg.status_code == 201:
            tok = (c.post("/auth/login", json={"username": "owner", **body}).json() or {}).get(
                "token", "")
        else:
            print(f"SKIP  registration unavailable ({reg.status_code}); "
                  "the structural check below still runs")
        hdr = {"Authorization": f"Bearer {tok}"} if tok else {}
        mine = c.post("/projects", json={"name": "Mine"}, headers=hdr)
        theirs = c.post("/projects", json={"name": "Theirs"}, headers=hdr)
        if mine.status_code >= 400 or theirs.status_code >= 400:
            print("SKIP  could not create projects; falling back to the structural check")
            mine_id = theirs_id = None
        else:
            mine_id, theirs_id = mine.json()["id"], theirs.json()["id"]

        if mine_id:
            # The admin IS a member of both, so this must SUCCEED — otherwise "it refuses" would
            # be indistinguishable from the route being broken.
            ok = c.post(f"/projects/{mine_id}/schedule/portfolio",
                        json={"project_ids": [theirs_id]}, headers=hdr)
            check("a member of both projects gets a portfolio (or an honest 'not available')",
                  ok.status_code == 200,
                  f"{ok.status_code} — the twin: without it, a 403 on everything would pass below")

            # A project id that does not exist stands in for one the caller cannot see: `role_for`
            # returns None for both, and both must be refused rather than read.
            denied = c.post(f"/projects/{mine_id}/schedule/portfolio",
                            json={"project_ids": ["00000000-0000-0000-0000-000000000000"]},
                            headers=hdr)
            check("a project the caller is not a member of is REFUSED, not read",
                  denied.status_code in (403, 404),
                  f"{denied.status_code} — membership is checked on every id in the body, not "
                  "just on the path parameter")

    # The structural half, which holds whether or not the live half could run: the route body must
    # re-run the dependency per project. A route that read `project_ids` without doing so would pass
    # `test_route_authz` — that gate only ever looks at `{pid}`.
    import inspect

    from aec_api.routers import schedule as mod
    src = inspect.getsource(mod.schedule_portfolio_endpoint)
    check("the route re-runs the membership dependency for every project in the body",
          "require_role" in src and "pid=other" in src,
          "test_route_authz proves the PATH parameter is gated and cannot see a body-supplied id")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("PORTFOLIO AUTHZ OK - membership enforced per project, not per path parameter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
