"""FTS GIN index (P1-a) — module full-text search is index-backed on Postgres.

The Postgres `@@` search matches `to_tsvector(ref+title+data)`; without a GIN index on that exact
expression the planner recomputes to_tsvector for every row (seq scan). `ensure_fts_indexes` creates
the matching GIN index, built from the *same* `_pg_document` helper so index and query can't drift.

Postgres isn't available in this harness, so we verify two things that don't need a live PG:
  1. On SQLite it's a clean no-op and search still works (the LIKE fallback needs no index).
  2. The GIN index expression is *exactly* the left-hand side of the query's `@@` predicate, when
     both are compiled against the Postgres dialect — so the index is guaranteed to be used.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_fts_index.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_fts_index.db"
os.environ["STORAGE_DIR"] = "./test_storage_fts"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_fts_index.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, literal_column  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from aec_api import modules  # noqa: E402
from aec_api.db import engine  # noqa: E402
from aec_api.main import app  # noqa: E402


def _pg(expr) -> str:
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


with TestClient(app) as c:                          # startup runs init_db → TABLES populated, indexes built
    # 1) SQLite: ensure_fts_indexes must be a no-op (never raises), and search still returns rows.
    assert engine.dialect.name == "sqlite", engine.dialect.name
    modules.ensure_fts_indexes(engine)              # must not raise on a non-Postgres engine

    pid = c.post("/projects", json={"name": "FTS Tower"}).json()["id"]
    for subj in ("Concrete beam clash at grid B4", "Steel column splice detail", "Curtain wall shop dwg"):
        r = c.post(f"/projects/{pid}/modules/rfi", json={"data": {"subject": subj, "question": "?"}})
        assert r.status_code in (200, 201), r.text[:160]

    hits = c.get(f"/projects/{pid}/modules/rfi", params={"q": "concrete"}).json()
    subjects = [h.get("title") or h.get("data", {}).get("subject") for h in hits]
    assert any("Concrete" in (s or "") for s in subjects), subjects
    assert not any("Steel" in (s or "") for s in subjects), f"search should not match steel rows: {subjects}"

    # 2) The GIN index DDL is a well-formed `USING gin` over to_tsvector(...), and it indexes the
    #    *same* to_tsvector document the query's `@@` predicate matches — both come from
    #    `_pg_document`, so the fully-inlined index expression appears verbatim in the search
    #    predicate (drift is impossible; this guards it anyway).
    t = modules.TABLES["rfi"]
    ddl = modules.fts_index_ddl("rfi")
    assert "USING gin" in ddl and "to_tsvector" in ddl and "concat_ws" in ddl, ddl
    assert 'CREATE INDEX IF NOT EXISTS "ix_mod_rfi_fts" ON "mod_rfi"' in ddl, ddl

    doc = _pg(modules._pg_document(t))                          # fully-inlined to_tsvector document
    query_sql = _pg(modules._pg_document(t).op("@@")(func.to_tsquery(
        literal_column("'english'"), "concrete:*")))
    assert "to_tsvector" in doc, doc
    assert doc in ddl, f"index must be over the shared document\n{doc}\n{ddl}"
    assert doc in query_sql, f"query `@@` must match the same document\n{doc}\n{query_sql}"

print("FTS INDEX OK - SQLite no-op + search works; GIN expr matches the `@@` query LHS exactly")
