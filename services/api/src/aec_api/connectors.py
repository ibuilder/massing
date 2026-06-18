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


# --- field mapping (admin-customizable Procore field -> our module field) ------
# Default Procore source path for each module field (dotted, with array indexes). Admins can
# override any of these per connection (connection.config["mappings"][kind][field] = path).
DEFAULT_MAPPINGS: dict[str, dict[str, str]] = {
    "rfi": {"subject": "subject", "question": "questions.0.body",
            "discipline": "discipline", "spec_section": "specification_section"},
    "submittal": {"title": "title", "spec_section": "specification_section",
                  "type": "type", "disposition": "status"},
    "change_event": {"subject": "title"},   # rom is computed from line items (not a plain path)
}


def extract_path(payload: Any, path: str) -> Any:
    """Read a dotted path with optional array indexes, e.g. 'questions.0.body'."""
    cur = payload
    for part in (path or "").split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def effective_mapping(kind: str, override: dict | None = None) -> dict[str, str]:
    """Default mapping for `kind`, with non-empty admin overrides applied (known fields only)."""
    m = dict(DEFAULT_MAPPINGS.get(kind, {}))
    for f, p in ((override or {}).get(kind, {}) if override else {}).items():
        if f in m and (p or "").strip():
            m[f] = p
    return m


def _ce_amount(ce: dict) -> float:
    amt = 0.0
    for li in (ce.get("change_event_line_items") or []):
        try:
            amt += float(li.get("amount") or 0)
        except (TypeError, ValueError):
            pass
    if not amt:
        try:
            amt = float(ce.get("rom") or 0)
        except (TypeError, ValueError):
            amt = 0.0
    return amt


def map_procore(kind: str, payload: dict, override: dict | None = None) -> dict[str, Any]:
    """Map a Procore payload to module record data via the effective field mapping, with
    code-level fallbacks for title/subject and the computed change-event ROM."""
    mapping = effective_mapping(kind, override)
    data: dict[str, Any] = {}
    for field, path in mapping.items():
        v = extract_path(payload, path)
        data[field] = v if v is not None else ""
    num = payload.get("number")
    if kind == "rfi":
        if not data.get("subject"):
            data["subject"] = f"RFI {num}" if num else "Imported RFI"
        if not data.get("question"):
            data["question"] = payload.get("body") or ""
    elif kind == "submittal":
        if not data.get("title"):
            data["title"] = f"Submittal {num}" if num else "Imported submittal"
    elif kind == "change_event":
        if not data.get("subject"):
            data["subject"] = f"CE {num}" if num else "Imported change event"
        data["rom"] = _ce_amount(payload)
    return {"procore_id": str(payload.get("id")), "data": data}


# back-compat wrappers (default mapping, no override)
def map_procore_rfi(r: dict) -> dict[str, Any]:
    return map_procore("rfi", r)


def map_procore_submittal(s: dict) -> dict[str, Any]:
    return map_procore("submittal", s)


def map_procore_change_event(ce: dict) -> dict[str, Any]:
    return map_procore("change_event", ce)


def _procore_rfis(token: str, project_id: str) -> list[dict]:
    return _procore_get(f"/rest/v1.0/projects/{project_id}/rfis", token) or []


def _procore_submittals(token: str, project_id: str) -> list[dict]:
    return _procore_get(f"/rest/v1.0/projects/{project_id}/submittals", token) or []


def _procore_change_events(token: str, project_id: str) -> list[dict]:
    return _procore_get(f"/rest/v1.1/projects/{project_id}/change_events", token) or []


def map_rfi_to_procore(record: dict) -> dict[str, Any]:
    """Normalize one of our rfi records into a Procore RFI update payload (status + answer).
    The exact PATCH body shape is applied in procore_update_rfi (Procore API-version specific)."""
    d = record.get("data") or {}
    status = {"answered": "open", "closed": "closed"}.get(record.get("workflow_state"), "open")
    return {"status": status, "answer": d.get("answer") or ""}


def _procore_update_rfi(token: str, project_id: str, rfi_id: str, payload: dict) -> Any:
    body = json.dumps({"rfi": payload}).encode()
    req = urllib.request.Request(
        f"https://api.procore.com/rest/v1.0/projects/{project_id}/rfis/{rfi_id}",
        data=body, method="PATCH",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 — fixed Procore host
        return json.loads(r.read().decode() or "{}")


# overridable seams so tests can drive the sync (read + write) without a live Procore
procore_rfis = _procore_rfis
procore_submittals = _procore_submittals
procore_change_events = _procore_change_events
procore_update_rfi = _procore_update_rfi


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
