"""Data-source connectors — treat external systems as connectable sources alongside the app's
own database. Each type exposes test() (validate credentials/reachability) and info() (a small
status payload). The adapter pattern is the seam for later mapping external data into the app.

Types:
  local      the app's own database (status only)
  postgres   any PostgreSQL DSN
  supabase   a Supabase project's PostgreSQL DSN (Supabase's DB is Postgres)
  procore    Procore REST API via an access token (a data source, not a SQL DB)
  acc        Autodesk Construction Cloud (APS) via a 3-legged OAuth token

Secrets in a connection's config (DSN password, Procore/ACC access token) are masked on read."""
from __future__ import annotations

import re
from typing import Any

# REL-3 façade: the pure Procore⇄record field-mapping half now lives in connectors_mappings.py.
# Re-exported so callers of connectors.map_procore / connectors.DEFAULT_MAPPINGS are unaffected.
from .connectors_mappings import (  # noqa: F401
    DEFAULT_MAPPINGS,
    _ce_amount,
    effective_mapping,
    extract_path,
    map_procore,
    map_procore_change_event,
    map_procore_rfi,
    map_procore_submittal,
    map_rfi_to_procore,
)

# REL-3 façade: the raw vendor HTTP clients (Procore/ACC/QuickBooks/ERP) live in connectors_vendors.py.
# The overridable seams below (procore_rfis = …, acc_projects = …) stay on THIS module — tests
# monkeypatch them here (connectors.acc_projects = fake) and the test/info dispatchers resolve them here.
from .connectors_vendors import (  # noqa: F401
    _acc_issues,
    _acc_projects,
    _aps_get,
    _erp_read,
    _procore_change_events,
    _procore_get,
    _procore_rfis,
    _procore_submittals,
    _procore_update_rfi,
    _qb_accounts,
    _qb_bills,
    _qb_get,
    _qb_vendors,
)

TYPES = ("local", "postgres", "supabase", "procore", "acc", "quickbooks", "sage", "viewpoint")


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


# overridable seams so tests can drive the sync (read + write) without a live Procore
procore_rfis = _procore_rfis
procore_submittals = _procore_submittals
procore_change_events = _procore_change_events
procore_update_rfi = _procore_update_rfi


# overridable seams so tests can drive ACC reads without a live Autodesk tenant
acc_projects = _acc_projects
acc_issues = _acc_issues


def _test_acc(config: dict) -> dict[str, Any]:
    token = (config or {}).get("access_token")
    if not token:
        return {"ok": False, "detail": "no access token"}
    try:
        me = _aps_get("/userprofile/v1/users/@me", token)
        who = me.get("userName") or me.get("emailId") or me.get("userId") or "connected"
        return {"ok": True, "detail": f"Autodesk · {who}"}
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": str(e)[:140]}


def _info_acc(config: dict) -> dict[str, Any]:
    token, account = config.get("access_token"), (config.get("account_id") or "").strip()
    if not (token and account):
        return {"hint": "set account_id to list projects"} if token else {}
    try:
        projects = acc_projects(token, account)
        names = [p.get("name") for p in projects[:5] if isinstance(p, dict)]
        return {"projects": names, "project_count": len(projects)}
    except Exception:                            # noqa: BLE001
        return {}


# overridable seams so tests can drive QuickBooks reads without a live Intuit tenant
qb_accounts = _qb_accounts
qb_vendors = _qb_vendors
qb_bills = _qb_bills


def _test_quickbooks(config: dict) -> dict[str, Any]:
    token, realm = (config or {}).get("access_token"), (config.get("realm_id") or "").strip()
    if not token:
        return {"ok": False, "detail": "no access token"}
    if not realm:
        return {"ok": False, "detail": "no realm_id (QuickBooks company id)"}
    try:
        ci = _qb_get(f"/v3/company/{realm}/companyinfo/{realm}?minorversion=70", token)
        name = ((ci.get("CompanyInfo") or {}).get("CompanyName")) or "connected"
        return {"ok": True, "detail": f"QuickBooks · {name}"}
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": str(e)[:140]}


def _info_quickbooks(config: dict) -> dict[str, Any]:
    token, realm = config.get("access_token"), (config.get("realm_id") or "").strip()
    if not (token and realm):
        return {"hint": "set realm_id (company id) to read the books"} if token else {}
    try:
        accts = qb_accounts(token, realm)
        return {"account_count": len(accts),
                "accounts": [a.get("Name") for a in accts[:5] if isinstance(a, dict)]}
    except Exception:                            # noqa: BLE001
        return {}


# overridable seam so tests can drive Sage/Viewpoint reads without a live ERP tenant
erp_read = _erp_read


def _test_erp(config: dict) -> dict[str, Any]:
    token, base = (config or {}).get("access_token"), (config.get("base_url") or "").strip()
    if not token:
        return {"ok": False, "detail": "no access token"}
    if not base:
        return {"ok": False, "detail": "no base_url (your ERP tenant API root)"}
    try:
        return {"ok": True, "detail": f"connected · {len(erp_read(config, 'accounts'))} accounts"}
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "detail": str(e)[:140]}


def _info_erp(config: dict) -> dict[str, Any]:
    if not (config.get("access_token") and config.get("base_url")):
        return {"hint": "set base_url + access token"} if config.get("access_token") else {}
    try:
        accts = erp_read(config, "accounts")
        return {"account_count": len(accts),
                "accounts": [(a.get("name") or a.get("Name")) for a in accts[:5] if isinstance(a, dict)]}
    except Exception:                            # noqa: BLE001
        return {}


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
    if ctype == "acc":
        return _test_acc(config)
    if ctype == "quickbooks":
        return _test_quickbooks(config)
    if ctype in ("sage", "viewpoint"):
        return _test_erp(config)
    return {"ok": False, "detail": f"unknown connection type {ctype!r}"}


def info(ctype: str, config: dict | None) -> dict[str, Any]:
    """A small status payload for the connection card. For Procore/ACC, lists a few projects."""
    config = config or {}
    if ctype == "procore" and config.get("access_token"):
        try:
            projects = _procore_get("/rest/v1.0/projects", config["access_token"])
            names = [p.get("name") for p in (projects or [])[:5] if isinstance(p, dict)]
            return {"projects": names, "project_count": len(projects or [])}
        except Exception:                        # noqa: BLE001
            return {}
    if ctype == "acc":
        return _info_acc(config)
    if ctype == "quickbooks":
        return _info_quickbooks(config)
    if ctype in ("sage", "viewpoint"):
        return _info_erp(config)
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
    if ctype == "acc":
        return {"kind": "acc", **info("acc", config)}
    if ctype == "quickbooks":
        return {"kind": "quickbooks", **info("quickbooks", config)}
    if ctype in ("sage", "viewpoint"):
        return {"kind": ctype, **info(ctype, config)}
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
