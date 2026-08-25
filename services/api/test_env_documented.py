"""Every environment flag the services read is either documented for an operator, or declared internal.

## The gap this was written from

83 `AEC_*` / `MASSING_*` variables are read under `services/`. **32 of them appeared nowhere** — not in
`.env.example`, not in `docs/`, not in `README.md`, not in `docker-compose.yml`. Two of those are
sign-in restrictions:

    AEC_OAUTH_ALLOWED_DOMAINS    unset ⇒ any domain the IdP will authenticate may sign in
    AEC_OAUTH_NO_AUTOPROVISION   unset ⇒ an unknown identity mints a local account

Neither has a restrictive default, so a deployment with OAuth on and these unset is open by
configuration — and an operator who cannot discover them cannot close it. **A hardening control that
exists in code and in no document is a control nobody can use.** The same argument applies, less
sharply, to `AEC_GRID_KGCO2E_PER_KWH`: its default is a US-average grid factor, so carbon figures are
wrong for any other region and are reported confidently anyway.

## Why this is a gate and not a one-time edit

Documenting them once fixes today. The list drifts the moment someone adds a flag — and this
codebase has already been bitten by a hand-maintained list of names that rotted into fiction:
`clearCache.ts`'s `KEEP_KEYS` named six keys the app never wrote, and shipped a button that deleted
the session it promised to keep.

So this checks **both directions**, and the second is the one that would have caught that:

  * a flag read by the code must be documented or declared INTERNAL — a new flag cannot appear
    unaccounted for;
  * a name in `INTERNAL` must actually be read somewhere — an entry that matches nothing is exactly
    how a list becomes decorative while reading as authoritative.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_env_documented.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


#: Flags an OPERATOR would never set — performance and internal plumbing. Each carries the reason,
#: because "internal" is a judgement and the next reader deserves the argument rather than the verdict.
#:
#: The bar: would a person deploying this need to set it to run safely, legally or correctly? If yes it
#: belongs in `.env.example`, however obscure. If it only exists so a developer can tune a pool or a
#: cache, it belongs here. When unsure, DOCUMENT it — an operator-facing file with one line too many
#: costs a moment's reading; a missing one costs a control nobody knows exists.
INTERNAL: dict[str, str] = {
    "AEC_DB_POOL_SIZE": "SQLAlchemy pool tuning; the defaults carry the compose deployment",
    "AEC_DB_MAX_OVERFLOW": "as above",
    "AEC_DB_POOL_RECYCLE": "as above",
    "AEC_DB_POOL_TIMEOUT": "as above",
    "AEC_DB_CONNECT_TIMEOUT": "as above",
    "AEC_GEOM_SLOTS": "concurrency cap for geometry work; tuned against a machine, not a policy",
    "AEC_GEOM_WAIT_S": "as above",
    "AEC_BAKE_CACHE_MB": "in-process bake cache size",
    "AEC_SCAN_CACHE_TTL": "model-index scan cache TTL",
    "AEC_JOB_HEARTBEAT_SECONDS": "worker liveness cadence; a deployment does not choose this",
    "AEC_JOB_ORPHAN_AFTER_SECONDS": "as above — the reaper's threshold",
    "AEC_WEBHOOK_TIMEOUT": "outbound webhook timeout; the webhook URLS are documented, the dial is not",
    "AEC_WEBHOOK_LOG_MAX": "webhook delivery-log ring size",
    "AEC_WEBHOOK_SYNC": "send webhooks inline instead of in the background — a test seam",
    "AEC_ALEMBIC_NO_BATCH": "migration internal: skip SQLite batch mode, used by the migration tests",
    "AEC_SCALE_PID_FILE": "the load-test harness's own pid file, not part of a deployment",
    "AEC_PLUGINS_DIR": "plugin discovery path; AEC_PLUGINS_ENABLED is the documented switch",
    # AEC_PIDFILE / AEC_ENVFILE / AEC_PLUGIN_CHILD were listed here on the first draft and the
    # reverse check below rejected all three on its first run: the first two are set and read
    # entirely inside test_plugin_isolation, and the third is WRITTEN by `plugin_registry._child_env`
    # and read by nobody in `src/`. None is a deployment surface, so none belongs in a list of flags
    # an operator might have wanted documented. This gate caught its own author's list rotting before
    # it shipped, which is the whole argument for checking both directions.
    "AEC_IFC_PARSE_SLOTS": "concurrent-parse cap; a machine-shaped number (PERF-THREADS)",
}

ENV_RE = re.compile(r'environ(?:\.get)?\(\s*["\']((?:AEC|MASSING)_[A-Z0-9_]+)')


def flags_read() -> dict[str, str]:
    """Every AEC_/MASSING_ flag read under `services/`, with a file that reads it.

    Test files are excluded: a flag only a test sets is not a deployment surface, and including them
    would fill the operator's file with probes. `test_plugin_isolation`'s probes are the exception and
    are declared INTERNAL above, because the code under test reads them from `src/`.
    """
    out: dict[str, str] = {}
    for py in (ROOT / "services").rglob("*.py"):
        parts = py.parts
        if ".venv" in parts or "__pycache__" in parts or py.name.startswith("test_"):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in ENV_RE.finditer(text):
            out.setdefault(m.group(1), str(py.relative_to(ROOT)).replace("\\", "/"))
    return out


def documented_text() -> str:
    """Everything an operator could reasonably read to discover a flag."""
    chunks = [(ROOT / ".env.example").read_text(encoding="utf-8", errors="replace")]
    for name in ("README.md", "docker-compose.yml"):
        p = ROOT / name
        if p.is_file():
            chunks.append(p.read_text(encoding="utf-8", errors="replace"))
    for md in (ROOT / "docs").rglob("*.md"):
        chunks.append(md.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


READ = flags_read()
DOCS = documented_text()

check("found the services' env flags — a short list would make every check below vacuous",
      len(READ) >= 70, f"only {len(READ)} flags found")
# The two that motivated this file, named so that renaming either fails HERE rather than silently
# leaving a sign-in restriction undiscoverable.
for must in ("AEC_OAUTH_ALLOWED_DOMAINS", "AEC_OAUTH_NO_AUTOPROVISION"):
    check(f"  ...including {must}, which is why this gate exists", must in READ,
          "renamed or removed — update this test and .env.example together")

undocumented = sorted(f for f in READ if f not in DOCS and f not in INTERNAL)
check("EVERY flag the services read is documented for an operator, or declared internal",
      not undocumented,
      "\n".join(f"      {f}  ({READ[f]})" for f in undocumented))

# The direction that catches a list rotting into fiction — see the header on KEEP_KEYS.
stale = sorted(f for f in INTERNAL if f not in READ)
check("every INTERNAL entry is a flag something actually reads", not stale,
      f"nothing reads: {stale} — delete the entry, or fix its spelling")

# Anti-vacuity: INTERNAL must not have swallowed the population. If nearly everything is 'internal',
# this file is a rubber stamp with extra steps.
documented_count = sum(1 for f in READ if f in DOCS)
check("a substantial share of flags is DOCUMENTED rather than declared internal",
      documented_count >= 2 * len(INTERNAL),
      f"{documented_count} documented vs {len(INTERNAL)} internal — the exemption is doing too much work")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print(f"test_env_documented OK — {len(READ)} flags: {documented_count} documented, "
      f"{len(INTERNAL)} declared internal")
