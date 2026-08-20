"""Which server routes has no client ever called? — a RATCHET, and an honest one.

Seven of eleven engines once shipped with no route at all; `test_reachable.py` closed that by asking
whether a *module* is reachable from a route. **Nothing asked whether a route is reachable from the
product.** Three sibling proforma endpoints — `renovation`, `rollover`, `income-basis` — are built,
tested, and have no client caller; `test_reachable` passes on all three, correctly, because the route
exists. That is the hole this fills.

WHAT THIS IS NOT
    The obvious version — "every server route must be referenced in apps/web/src" — was measured and
    **rejected**: it flags **362 of 894 paths (40%)**, which is not a gap list, it is proof the
    predicate is wrong. Two independent reasons, both evidenced rather than assumed:

    1. **Much of the API is deliberately not for our client.** `/bcf/2.1/*` and `/bcf/3.0/*` are the
       external BIM-tool surface — round-tripping with other tools is a product non-negotiable, not
       an oversight. `/auth/oauth/{provider}/callback` is a browser redirect; `/attachments/{aid}/
       download` is an href. 97 route groups are entirely uncalled because they are *surfaces*.
    2. **Literal matching is unsound for this client**, which builds URLs from template literals with
       placeholders mid-path: `/projects/${pid}/modules/${key}/${rid}/distribution`. Control:
       `modules/attachments` has ZERO literal hits and is obviously used. A gate on contiguous
       literals reports phantom gaps by construction.

THE RULE HERE
    Flag a route only when the **last static segment of its path appears nowhere** in the web source,
    and only when that segment is distinctive (>= 5 chars). That is 54 of 894 — reviewable, and it
    needs no exemption list, which is the signal the population is right.

**THE KNOWN FALSE NEGATIVE, STATED SO NOBODY OVER-TRUSTS A GREEN RUN.** This rule does **not** catch
`/projects/{pid}/proforma/renovation` — the route that started the whole investigation. The word
"renovation" appears in `viewer/app.ts` in unrelated IEBC scope-of-work prose, so a segment match
sees it as referenced. Any route whose distinctive segment coincides with unrelated text is invisible
here. **Widening the predicate to catch it is how you get back to 40% noise** — the narrow rule plus
this stated blind spot beats a wide rule with an exemption list.

It also cannot see **indirection**: `execute_ifc_code` is reachable only via `editIfc` -> the
edit-recipe registry in `edit.py`, which no reference match can follow.

WHAT A PASS MEANS
    Only that no NEW unreachable route arrived. It does **not** mean the 54 below are fine — they are
    frozen because they exist, not because they were judged acceptable. Same contract as
    `test_protected_prefix_coverage`: a ratchet records "this was looked at", never "this is safe".

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_route_reachability.py
"""
import glob
import os
import re
import sys

sys.path.insert(0, "src")

os.environ.setdefault("DATABASE_URL", "sqlite:///./_route_reach.db")
os.environ.setdefault("STORAGE_DIR", "./_route_reach_store")

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


#: Minimum length for a path segment to count as distinctive. Shorter ones ("id", "pdf", "new") occur
#: in unrelated text constantly and would make the rule noise.
MIN_SEGMENT = 5

#: Frozen: routes whose last static segment appears nowhere in the web source, as of 2026-08-06.
#: **Not an allowlist of acceptable routes** — a record of what existed when the gate was written, so
#: the NEXT one cannot arrive unnoticed. Shrinking this set is always allowed and never fails.
KNOWN_UNCALLED: set[str] = {
    #: R39-VIEWER-OBS, added 2026-08-07 with an expiry condition rather than a shrug. The POST that
    #: WRITES load timings has a caller (`reportViewerLoad` in `apps/web/src/api/model.ts`, called
    #: from the viewer's load path) — it is only this read-side aggregate that has none yet.
    #:
    #: Not parked for convenience: a reader for it belongs in an admin/diagnostics screen, and every
    #: candidate screen lives in Lane A or B while this work is Lane E. Adding one here would put two
    #: sessions in the same file for the sake of satisfying a gate, which is the collision the lane
    #: table exists to prevent. The data is queryable over HTTP today; what is missing is a screen.
    #:
    #: **Remove this entry when that screen lands** — the route is finished and tested
    #: (`test_viewer_load_timing.py` covers p50/p95, the survivorship guard and retention), so this
    #: is a UI gap, not an unfinished endpoint.
    "/projects/{pid}/model/load-timings",
    "/bcf/3.0/projects/{pid}/topics/{guid}/document_references",
    "/benchmarks/unit-rates", "/cost/datasets/import-custom", "/portfolio/deal-memory",
    "/proforma/entitlement-risk", "/proforma/provenance/admissibility",
    "/projects/preview-bundle", "/projects/{pid}/5d/element-costs",
    "/projects/{pid}/agent-packs", "/projects/{pid}/clash/clearance-rules",
    "/projects/{pid}/code/amendments", "/projects/{pid}/cost-vintage",
    "/projects/{pid}/cost/pay-application", "/projects/{pid}/dev-budget/sync-from-model",
    "/projects/{pid}/documents/file-model", "/projects/{pid}/documents/model-history",
    # --- 2026-08-20: MASKED BY THE COMMENT BUG, not newly broken ---------------------------------
    # These five were always uncalled. `uncalled_routes` matched against the raw web source, so a
    # route whose name appears in a doc comment read as called; `strip_comments` above ends that.
    # Frozen rather than wired, per this list's own contract: a ratchet records "this was looked at",
    # never "this is safe". Two are worth someone's attention — `/entitlements/conditions` is
    # R22-ENTITLEMENT's own surface, and `/schedule/make-ready` is the Last Planner constraint list.
    "/cost/datasets", "/pipeline/funnel", "/projects/{pid}/entitlements/conditions",
    "/projects/{pid}/schedule/eot/sourced",
    "/projects/{pid}/drawing-set/compiled.pdf", "/projects/{pid}/drawing-set/file-drawing-set",
    "/projects/{pid}/drawings/received-regions", "/projects/{pid}/drawings/schedule.csv",
    "/projects/{pid}/drawings/sheet-regions", "/projects/{pid}/drawings/sheet.dxf",
    "/projects/{pid}/energy/export.gbxml", "/projects/{pid}/energy/export.idf",
    "/projects/{pid}/entitlements/condition-checks", "/projects/{pid}/ffe-bom",
    "/projects/{pid}/golden-thread", "/projects/{pid}/k1-pack",
    "/projects/{pid}/lod/handover-readiness", "/projects/{pid}/mep/pressure-loss",
    "/projects/{pid}/mep/thermal-loads", "/projects/{pid}/mep/tray-fill",
    "/projects/{pid}/model/equipment/budget-lines",
    "/projects/{pid}/model/equipment/starter-requirements",
    "/projects/{pid}/model/equipment/to-submittals", "/projects/{pid}/model/export.ifcx",
    "/projects/{pid}/model/lod/census", "/projects/{pid}/models/export-qa",
    "/projects/{pid}/models/footprint.geojson", "/projects/{pid}/models/schema-diag",
    "/projects/{pid}/modules/backfill-references",
    "/projects/{pid}/procurement/packages/{rid}/send-rfq",
    "/projects/{pid}/project-package.pdf", "/projects/{pid}/provenance/admissibility",
    "/projects/{pid}/quality/turnover-readiness", "/projects/{pid}/recipes/replay-plan",
    "/projects/{pid}/rules/space-pack", "/projects/{pid}/scan/verify-lod500",
    "/projects/{pid}/spec-links", "/projects/{pid}/verified-progress/from-layout",
    "/projects/{pid}/view-templates/{tid}/graphics", "/reference/authoring-matrix",
}

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_WEB = os.path.join(_ROOT, "apps", "web", "src")


def _web_source() -> str:
    """Every non-test, non-demo web source file, concatenated.

    `demo/` is excluded deliberately: `demoData.json` is a *captured* snapshot keyed by request path,
    so including it would make every crawled route look 'called' by its own recording.
    """
    out = []
    for pat in ("**/*.ts", "**/*.tsx"):
        for p in glob.glob(os.path.join(_WEB, pat), recursive=True):
            q = p.replace("\\", "/")
            if ".test." in q or "/src/demo/" in q:
                continue
            out.append(open(p, encoding="utf-8", errors="replace").read())
    return "\n".join(out)


def _leaf(route: str) -> str:
    segs = [s for s in route.strip("/").split("/") if not s.startswith("{")]
    return segs[-1] if segs else ""


def strip_comments(src: str) -> str:
    """Comments removed, so a route NAMED in prose does not read as a route CALLED.

    Measured 2026-08-20: six routes appeared nowhere but in comments — `/cost/datasets`,
    `/pipeline/funnel`, `/drawings/sheet.dxf`, `/entitlements/conditions`,
    `/schedule/eot/sourced`, `/schedule/make-ready`. Every one was counted as reachable because
    its name occurs in a doc comment. **The gate's central assertion could be satisfied by writing
    the route's name in a sentence**, which is the failure mode it exists to prevent, one level up.
    `sheet.dxf`'s only appearance is `/** Exactly the query parameters `sheet.svg` / `sheet.pdf` /
    `sheet.dxf` declare. */`.

    DELIBERATELY CONSERVATIVE, and the reason is recorded because the obvious version is wrong:
    a greedy `/\*.*?\*/` corrupts this source. There are **3,500** `/*` occurrences inside quoted
    glob strings (`"src/**/*.ts"`, `"../**/*.ts"`), each of which opens a false comment that runs
    to the next `*/` and eats real call sites in between — the same over-strip that once ate a
    Python file's imports when a TypeScript pattern was applied to it. Over-stripping is not the
    safe direction here: it produces *false* unreachable routes, i.e. work invented for someone.

    So: block comments only where they START a line (a glob inside a string never does), plus lines
    whose trimmed form begins `//` or `*`. Trailing `// …` after code is left alone, because
    removing it needs string-awareness and a naive pass truncates `https://` inside a literal.
    That under-strips, which can only make this gate *miss* a comment-only mention — never invent one.
    """
    src = re.sub(r"(?m)^[ 	]*/\*.*?\*/", " ", src, flags=re.S)
    return "\n".join(line for line in src.split("\n")
                      if not (line.lstrip().startswith("//") or line.lstrip().startswith("*")))


def uncalled_routes(paths, blob: str) -> set[str]:
    """Routes whose distinctive last static segment appears nowhere in the web source's CODE."""
    code = strip_comments(blob)
    out = set()
    for r in paths:
        leaf = _leaf(r)
        if len(leaf) >= MIN_SEGMENT and leaf not in code:
            out.add(r)
    return out


PATHS = set(app.openapi().get("paths", {}))
BLOB = _web_source()
FOUND = uncalled_routes(PATHS, BLOB)

check("the OpenAPI surface is readable and non-trivial", len(PATHS) > 500, len(PATHS))
check("the web source was actually read", len(BLOB) > 100_000, len(BLOB))
print(f"  routes {len(PATHS)} · web source {len(BLOB):,} chars · uncalled by this rule {len(FOUND)}")

new = sorted(FOUND - KNOWN_UNCALLED)
check("NO NEW UNREACHABLE ROUTE — a route the product cannot call is a feature nobody can use",
      not new,
      f"{len(new)} new: {new[:6]} — either give it a client caller, or add it to KNOWN_UNCALLED "
      f"with a reason. NOTE: a passing run does NOT mean the {len(KNOWN_UNCALLED)} frozen routes are "
      "fine; they are frozen because they existed when this gate was written, not because anyone "
      "judged them acceptable.")

# The OTHER direction, and it was a bare `print` until 2026-08-20 — so the allowlist could rot
# indefinitely while the run stayed green. Its sibling `test_reachable.py` states the principle this
# file was missing: "a KNOWN_UNREACHABLE that becomes reachable ALSO fails — so the list cannot
# quietly rot into a fiction". A frozen entry that nothing matches any more is either a route that
# gained a caller (good news the list should record) or one that was renamed or deleted (a stale
# name pre-authorising whatever reuses it). Both need a human; neither should print and pass.
gone = sorted(KNOWN_UNCALLED - FOUND)
check("no frozen route has quietly become called or vanished — the allowlist cannot rot",
      not gone,
      f"{len(gone)}: {gone[:6]} — if it now has a caller, delete the entry; if the path changed, "
      "update it. Leaving it freezes a name that no longer refers to anything.")

# The stated blind spot, asserted so it cannot be quietly forgotten.
check("the rule's known FALSE NEGATIVE still holds: /proforma/renovation is NOT flagged",
      "/projects/{pid}/proforma/renovation" not in FOUND,
      "renovation is now flagged — if the IEBC prose in viewer/app.ts changed, update the docstring")
# Its siblings WERE flagged when this gate was written — that is how the family was found. Both
# gained client methods in SCALE-SEAM ⑧ (`apps/web/src/api/proforma.ts`), so the rule no longer
# flags them and they have been removed from KNOWN_UNCALLED. **A ratchet that only ever comes down
# is the point**, so this now asserts they stay reachable rather than that they stay broken —
# otherwise the gate would demand the defect it exists to remove.
check("  the siblings that motivated this gate are STILL reachable — the fix must not regress",
      not ({"/projects/{pid}/proforma/rollover", "/projects/{pid}/proforma/income-basis"} & FOUND),
      "a /proforma sibling lost its client caller again; see api/proforma.ts")

print()
if FAILED:
    print(f"route_reachability: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("route_reachability: all checks passed")
