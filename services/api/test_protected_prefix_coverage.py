"""G-8 — a NEW top-level route prefix must not silently opt out of the RBAC middleware.

`main._PROTECTED_PREFIXES` is hand-maintained. When RBAC is on it forces an authenticated identity on
anything under those prefixes, which is the safety net beneath each route's own dependency. It covers
**7 of 66** top-level prefixes, and nothing anywhere notices when a 67th appears — the new prefix is
simply outside the net, and no test fails.

That is not hypothetical; it is how every authorisation hole found in the 2026-07-29/30 pass got in:

    /pdf         7 routes, incl. /pdf/seal — an UNAUTHENTICATED caller received a PDF bearing a
                 rendered PE seal with a name and licence number of their choosing
    /templates   anonymous create + delete of state shared across every project
    /samples     anonymous project creation, no actor recorded
    /firm        any project-admin could replace (hence erase) the firm's standards library

Each route also had its own defective gate — but the middleware would have caught all four, and it
did not get the chance because the prefix was never in the list.

**This is a ratchet, not an allowlist.** The frozen sets below are "prefixes that existed and were
looked at", not "prefixes that are safe". Deliberately no per-entry prose: a 59-line table of reasons
rots faster than it is read, and a stale reason reads exactly like a live one. What the sets buy is
that the NEXT prefix cannot arrive unnoticed.

Three ways to fail, and the second and third are the ones a plain membership check would miss:

1. a prefix appears that is in neither the protected list nor the frozen sets;
2. a frozen prefix has **gained its first mutating route** — `/reports` going from read-only to
   accepting a POST is precisely the silent-opt-out this exists to catch, and set membership alone
   would wave it through;
3. a frozen prefix no longer exists. A stale entry is not tidiness — it **pre-authorises** the next
   prefix that happens to reuse the name, which is the `AUTHORISING`-with-no-referent trap that
   `test_global_authz` records one level up.

Shrinking a set is always allowed and never fails: adding a prefix to `_PROTECTED_PREFIXES`, or
deleting its last mutating route, is the fix this test is asking for.

Complements rather than duplicates `test_global_authz` (which freezes global *mutating routes with no
authorising dependency*, currently 29) — that one measures individual routes, this one measures the
middleware's blast radius. A route can be personally well-gated and still sit outside the net.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_protected_prefix_coverage.py
"""
import collections
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "prefix_cov.db")
os.environ["STORAGE_DIR"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import _PROTECTED_PREFIXES, app  # noqa: E402

MUTATING = {"post", "put", "patch", "delete"}

#: Uncovered prefixes that HAVE mutating routes — the ones that matter. Frozen 2026-07-30.
KNOWN_UNCOVERED_MUTATING = {
    "/admin", "/bcf", "/client-errors", "/compute", "/cost", "/esign", "/estimate", "/firm",
    "/generate", "/ids", "/jurisdiction", "/license", "/massing", "/parcels", "/pdf", "/plugins",
    "/samples", "/schedule", "/scim", "/shared", "/structure", "/templates", "/test-fit",
}

#: Uncovered read-only prefixes. Lower risk (a GET cannot change state) but still outside the net,
#: so a read-only prefix growing a mutating route has to surface — see failure mode 2.
KNOWN_UNCOVERED_READONLY = {
    "/attachments", "/benchmarks", "/bridge", "/bsdd", "/capabilities", "/classifications", "/codes",
    "/content", "/contractor-statements", "/energy", "/families", "/fca", "/health", "/licenses",
    "/lifecycle", "/market", "/mcp", "/metrics", "/module-attachments", "/modules", "/openbim",
    "/opendata", "/payments", "/portfolio", "/pricing", "/procurement", "/re-syndication", "/ready",
    "/reference", "/reports", "/rooms", "/scope-library", "/securities-syndication", "/stamps",
    "/webhooks", "/wip",
}

FAILED: list[str] = []


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    FAILED.append(msg)


# The app must be STARTED: routers are included lazily, so `app.routes` at import time shows 9 of 854
# paths and a static walk reports a confident "no gap". The OpenAPI schema forces materialisation.
with TestClient(app):
    counts: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])   # [mutating, read]
    for path, ops in app.openapi()["paths"].items():
        if not path.startswith("/") or path == "/":
            continue
        top = "/" + path.split("/")[1]
        for method in ops:
            counts[top][0 if method.lower() in MUTATING else 1] += 1

    covered = {p for p in counts
               if any(p.startswith(pp) or pp.startswith(p + "/") for pp in _PROTECTED_PREFIXES)}
    uncovered = set(counts) - covered
    frozen = KNOWN_UNCOVERED_MUTATING | KNOWN_UNCOVERED_READONLY

    # 1 — a prefix nobody classified.
    for p in sorted(uncovered - frozen):
        kind = "MUTATING" if counts[p][0] else "read-only"
        fail(f"NEW top-level prefix {p!r} ({kind}, {counts[p][0]} mutating / {counts[p][1]} read) is "
             f"outside main._PROTECTED_PREFIXES and unclassified. Either add it to "
             f"_PROTECTED_PREFIXES (do this if any route under it touches project or tenant state), "
             f"or add it to the frozen set here to record that it was looked at.")

    # 2 — a read-only prefix grew teeth. Set membership alone would not notice.
    for p in sorted(KNOWN_UNCOVERED_READONLY & uncovered):
        if counts[p][0]:
            fail(f"{p!r} was frozen as READ-ONLY and now has {counts[p][0]} mutating route(s), while "
                 f"still sitting outside _PROTECTED_PREFIXES. A prefix gaining its first mutating "
                 f"route is exactly the silent opt-out this guards. Gate it, or move it to "
                 f"KNOWN_UNCOVERED_MUTATING deliberately.")

    # 3 — a frozen entry with no referent pre-authorises whatever reuses the name.
    for p in sorted(frozen - set(counts)):
        fail(f"{p!r} is frozen here but no longer exists in the app. Delete it: a name with no "
             f"referent silently becomes pre-approved the day something reuses it.")

    n_mut = sum(1 for p in uncovered if counts[p][0])
    print(f"\nprefixes: {len(counts)} total · {len(covered)} covered by _PROTECTED_PREFIXES · "
          f"{len(uncovered)} outside it ({n_mut} with mutating routes)")

if FAILED:
    print(f"\nprotected_prefix_coverage: {len(FAILED)} FAILED")
    sys.exit(1)
print("protected_prefix_coverage OK — no unclassified top-level prefix, no frozen read-only prefix "
      "has grown a mutating route, and no frozen entry has lost its referent. The set can shrink "
      "freely; it cannot grow without someone deciding to let it.")
