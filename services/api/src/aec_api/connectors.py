"""Data-source connectors — treat external systems as connectable sources alongside the app's
own database. Each type exposes test() (validate credentials/reachability) and info() (a small
status payload). The adapter pattern is the seam for later mapping external data into the app.

Types:
  local      the app's own database (status only)
  postgres   any PostgreSQL DSN
  supabase   a Supabase project's PostgreSQL DSN (Supabase's DB is Postgres)
  procore    Procore REST API via an access token (a data source, not a SQL DB)

Secrets in a connection's config (DSN password, Procore access token) are masked on read."""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

TYPES = ("local", "postgres", "supabase", "procore")


def _mask_dsn(dsn: str) -> str:
    return re.sub(r"(://[^:/@]+:)[^@/]+(@)", r"\1***\2", dsn or "")


def public_config(ctype: str, config: dict | None) -> dict:
    """Config safe to return to the client — secrets redacted."""
    c = dict(config or {})
    if "dsn" in c:
        c["dsn"] = _mask_dsn(c["dsn"])
    if "access_token" in c:
        c["access_token_set"] = bool(c.pop("access_token"))
    return c


def _normalize_dsn(dsn: str) -> str:
    """Use the installed psycopg (v3) driver for plain postgres URLs (incl. Supabase) so a
    pasted `postgresql://…` / `postgres://…` connects without psycopg2."""
    for prefix in ("postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return "postgresql+psycopg://" + dsn[len(prefix):]
    return dsn


def _test_sql(dsn: str) -> dict[str, Any]:
    from sqlalchemy import create_engine
    if not dsn:
        return {"ok": False, "detail": "no connection string"}
    dsn = _normalize_dsn(dsn)
    args = {"connect_timeout": 6} if "postgresql" in dsn else {}
    eng = None
    try:
        eng = create_engine(dsn, connect_args=args, pool_pre_ping=True)
        with eng.connect() as c:
            ver = c.exec_driver_sql("SELECT version()" if "postgres" in dsn else "SELECT sqlite_version()").scalar()
        return {"ok": True, "detail": str(ver)[:90]}
    except ModuleNotFoundError as e:             # postgres driver not installed in this image
        return {"ok": False, "detail": f"{e} — install the PostgreSQL driver (psycopg) on the server"}
    except Exception as e:                       # noqa: BLE001 — surface any connect failure
        return {"ok": False, "detail": str(e).splitlines()[0][:140]}
    finally:
        if eng is not None:
            eng.dispose()


def _test_local(_config: dict) -> dict[str, Any]:
    from sqlalchemy import inspect, text

    from .db import engine
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        n = len(inspect(engine).get_table_names())
        return {"ok": True, "detail": f"{engine.dialect.name} · {n} tables"}
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": str(e)[:140]}


def _procore_get(path: str, token: str) -> Any:
    req = urllib.request.Request(f"https://api.procore.com{path}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 — fixed Procore host
        return json.loads(r.read().decode())


def _test_procore(config: dict) -> dict[str, Any]:
    token = (config or {}).get("access_token")
    if not token:
        return {"ok": False, "detail": "no access token"}
    try:
        me = _procore_get("/rest/v1.0/me", token)
        who = me.get("login") or me.get("name") or me.get("email_address") or "connected"
        return {"ok": True, "detail": f"Procore · {who}"}
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": str(e)[:140]}


def test(ctype: str, config: dict | None) -> dict[str, Any]:
    config = config or {}
    if ctype == "local":
        return _test_local(config)
    if ctype in ("postgres", "supabase"):
        return _test_sql(config.get("dsn", ""))
    if ctype == "procore":
        return _test_procore(config)
    return {"ok": False, "detail": f"unknown connection type {ctype!r}"}


def info(ctype: str, config: dict | None) -> dict[str, Any]:
    """A small status payload for the connection card. For Procore, lists a few projects."""
    config = config or {}
    if ctype == "procore" and config.get("access_token"):
        try:
            projects = _procore_get("/rest/v1.0/projects", config["access_token"])
            names = [p.get("name") for p in (projects or [])[:5] if isinstance(p, dict)]
            return {"projects": names, "project_count": len(projects or [])}
        except Exception:                        # noqa: BLE001
            return {}
    return {}


# --- data plane: read-only browse / query --------------------------------------
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|attach|pragma|vacuum|replace|merge|call|exec|execute|copy)\b",
    re.IGNORECASE)


def _engine_for(ctype: str, config: dict):
    """An engine for a SQL connection, or the app engine for 'local'. Caller disposes non-local."""
    if ctype == "local":
        from .db import engine
        return engine, False
    from sqlalchemy import create_engine
    dsn = _normalize_dsn((config or {}).get("dsn", ""))
    args = {"connect_timeout": 6} if "postgresql" in dsn else {}
    return create_engine(dsn, connect_args=args, pool_pre_ping=True), True


def tables(ctype: str, config: dict | None) -> dict[str, Any]:
    """List tables (SQL) or projects (Procore) available on the connection."""
    config = config or {}
    if ctype == "procore":
        return {"kind": "procore", **info("procore", config)}
    if ctype not in ("local", "postgres", "supabase"):
        return {"error": f"{ctype} is not browsable"}
    from sqlalchemy import inspect
    eng, owned = _engine_for(ctype, config)
    try:
        return {"kind": "sql", "tables": sorted(inspect(eng).get_table_names())}
    except ModuleNotFoundError as e:
        return {"error": f"{e} — install the PostgreSQL driver (psycopg) on the server"}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e).splitlines()[0][:160]}
    finally:
        if owned:
            eng.dispose()


def query(ctype: str, config: dict | None, sql: str, limit: int = 200) -> dict[str, Any]:
    """Run a READ-ONLY SELECT/WITH query and return {columns, rows}. Rejects anything that
    isn't a single SELECT/WITH (no writes/DDL/multiple statements). Result is row-capped."""
    config = config or {}
    if ctype not in ("local", "postgres", "supabase"):
        return {"error": "this connection is not a SQL data source"}
    sql = (sql or "").strip().rstrip(";").strip()
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        return {"error": "only SELECT / WITH queries are allowed"}
    if ";" in sql or _FORBIDDEN.search(sql):
        return {"error": "query rejected: writes, DDL, and multiple statements are not allowed"}
    limit = max(1, min(int(limit or 200), 1000))
    eng, owned = _engine_for(ctype, config)
    try:
        with eng.connect() as c:
            if "postgres" in str(eng.url):
                c.exec_driver_sql("SET TRANSACTION READ ONLY")
            res = c.exec_driver_sql(f"SELECT * FROM ({sql}) AS _q LIMIT {limit}")
            cols = list(res.keys())
            rows = [[(v if isinstance(v, (int, float, str, bool, type(None))) else str(v)) for v in r]
                    for r in res.fetchall()]
        return {"columns": cols, "rows": rows, "row_count": len(rows), "limit": limit}
    except ModuleNotFoundError as e:
        return {"error": f"{e} — install the PostgreSQL driver (psycopg) on the server"}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e).splitlines()[0][:160]}
    finally:
        if owned:
            eng.dispose()
