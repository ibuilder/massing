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
#:
#: **WHAT THIS COSTS, measured 2026-08-20: 113 routes are never assessed at all** — a limit stated
#: without its size reads as a minor caveat, and this one is 12% of the surface. `/schedule/eot` is
#: in it (leaf `eot`), and a direct grep confirms **no client code references any EOT endpoint** —
#: so that whole R40-EOT surface is dark and this gate structurally cannot say so.
#:
#: **A longer needle was tried and rejected, with numbers.** Matching the last TWO static segments
#: ("prefab/kits") would cover short leaves — and flags **50** of the 113 as dark, almost all false:
#: the client builds URLs as template literals, `` `/projects/${pid}/ask` ``, so "projects/ask"
#: never appears contiguously. The `${pid}` interpolation is precisely why the leaf alone is the
#: only part that survives, and why this rule cannot be sharpened by lengthening the needle.
#:
#: Of the 113, exactly **two** are genuinely uncalled: `/projects/{pid}/prefab/kits` and its
#: `/{rid}` sibling. Listing them here rather than in KNOWN_UNCALLED, because the rule never
#: evaluates them — an entry there would claim a check that does not run.
MIN_SEGMENT = 5

#: Frozen: routes whose last static segment appears nowhere in the web source, as of 2026-08-06.
#: **Not an allowlist of acceptable routes** — a record of what existed when the gate was written, so
#: the NEXT one cannot arrive unnoticed. Shrinking this set is always allowed and never fails.
KNOWN_UNCALLED: set[str] = {
    #: CLOUD-SSO, added 2026-08-24. `/auth/cloud/callback` has no web caller and **must not have
    #: one**: it is the OAuth redirect target. massing.cloud sends the user's browser here with the
    #: authorization code after they sign in on the site, so the caller is the *broker*, not this
    #: app. `/auth/cloud/login` — the route the app does navigate to — has a caller
    #: (`cloudLoginUrl` in `apps/web/src/api/cloud.ts`), which is the pair that proves the flow is
    #: wired; a grep of the web source structurally cannot see the other half of a redirect.
    #: Expiry condition: none. This is not parked work — a client caller here would mean the app was
    #: forging its own callback, which is the thing PKCE exists to prevent.
    "/auth/cloud/callback",
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
    "/benchmarks/unit-rates", "/cost/datasets/import-custom",
    # "/portfolio/deal-memory" REMOVED v0.3.1112 — it gained a real caller, `portfolioDealMemory` in
    # apps/web/src/api/dealMemory.ts, behind the "which projects?" disclosure on the proforma's cost
    # budget. Recorded because the route it should have been removed for is NOT the route that flagged
    # it: adding `/projects/{pid}/deal-memory/beside` put the substring `deal-memory` into the web
    # source, and this rule matches a leaf against the whole blob, so the frozen entry read as called
    # while nothing called it. **A substring test cannot tell which route a string belongs to** — the
    # same coarseness `MIN_SEGMENT` documents from the other end, met from this one.
    #
    # It was tempting to answer that by sharpening the needle or by shadowing the entry. Both were
    # measured and rejected: a two-segment needle is already rejected above with numbers, and 328 of
    # 941 routes share a leaf with another route, so "a shared leaf decides nothing" would take a
    # third of the surface out of this gate's reach. The real fix was to stop half-wiring the item —
    # R35-DEAL-MEMORY asks for realised outcomes *by vintage*, and only the summary comparison had
    # been built. The gate collision is what made the missing half visible.
    "/proforma/entitlement-risk", "/proforma/provenance/admissibility",
    # "/projects/preview-bundle" REMOVED v0.3.1061 — it gained a real caller in
    # apps/web/src/api/library.ts (the `.mass` preview from PR #336), so freezing it as
    # uncalled had become a false claim. This gate caught it on the merge, which is the
    # direction that matters: an allowlist entry that outlives its reason reads as a
    # deliberate exemption forever.
    "/projects/{pid}/5d/element-costs",
    "/projects/{pid}/agent-packs", "/projects/{pid}/clash/clearance-rules",
    "/projects/{pid}/code/amendments", "/projects/{pid}/cost-vintage",
    "/projects/{pid}/cost/pay-application", "/projects/{pid}/dev-budget/sync-from-model",
    "/projects/{pid}/documents/file-model", "/projects/{pid}/documents/model-history",
    # --- 2026-08-20: MASKED BY THE GENERATED TYPES, not newly broken -----------------------------
    # `api/schema.d.ts` and `api/openapiTypes.ts` are emitted FROM the OpenAPI spec and list every
    # route by construction, so their presence in the blob vouched for these 29. Excluding them took
    # the uncalled count 56 -> 85. Grouped by WHY, because "frozen" without a reason is how an
    # allowlist becomes a fiction:
    #
    #   NOT FOR OUR CLIENT — an external caller or a browser redirect owns these, and a client
    #   caller would be the wrong thing to add:
    "/auth/oauth/{provider}/callback", "/esign/webhook",
    "/scim/v2/ResourceTypes", "/scim/v2/ServiceProviderConfig",
    "/projects/{pid}/listings/{lid}/public",
    "/projects/{pid}/investors/{iid}/statement.public.pdf",
    #
    #   SIGNED-URL HANDOFFS — fetched by a redirect or an <a href>, not by the typed client:
    "/attachments/{aid}/signed-url", "/projects/{pid}/model.frag/signed-url",
    #
    #   EXPORT / DOWNLOAD ENDPOINTS — a user reaches these by clicking a link the server builds, so
    #   "no client caller" is expected. Listed rather than excluded by pattern: a download nobody
    #   links to is still unreachable, and only a person can tell the two apart.
    # `/exports/{cobie,qto,schedule,spaces}.xlsx` were frozen HERE and are now seen as called
    # (v0.3.1132). They never lacked a caller: `viewer/tools/exportsSection.ts:57` opens
    # `/projects/${projectId}/exports/${file}.xlsx` over a literal four-entry list. The leaf rule
    # could not see it because the STEM is templated, which is the one shape the header's
    # template-literal argument did not cover. Recorded rather than silently deleted: four entries
    # under a heading that says "no client caller is expected" were four false claims, and the
    # heading is what made them look considered.
    # `/model/export.{jsonld,parquet}` left this list in v0.3.1132 — `standards.ts:488-489` links
    # both. They moved to `CALLED_VIA_TEMPLATED_EXT`, which carries their call-site evidence and
    # asserts it still exists.
    "/projects/{pid}/estimate/gaeb.x83", "/projects/{pid}/modules/{key}/log.pdf",
    "/projects/{pid}/cost/lien-waiver.pdf", "/projects/{pid}/opendata/permits.geojson",
    # `/schedule/{gantt,lob}.svg` left here in v0.3.1132 for the same reason: `api/schedule.ts:193-4`
    # builds `/projects/${pid}/schedule/${kind}.svg`, and `portal/panels/schedule.ts:731` enumerates
    # both kinds. Two call sites, one blind spot.
    #
    #   GENUINELY UNREACHED CAPABILITIES — these are the ones worth someone's attention, and the
    #   reason this exclusion was worth making. Each is a working engine behind a route the product
    #   never calls:
    "/procurement/rfq-status", "/projects/{pid}/accounting/chart-of-accounts",
    "/projects/{pid}/budget/two-sided", 
    "/projects/{pid}/cost/lien-waiver", "/projects/{pid}/cv-progress/ingest-batch",
    "/projects/{pid}/elements/by-discipline", "/projects/{pid}/naming/conventions",
    

    # --- 2026-08-20: MASKED BY THE COMMENT BUG, not newly broken ---------------------------------
    # These five were always uncalled. `uncalled_routes` matched against the raw web source, so a
    # route whose name appears in a doc comment read as called; `strip_comments` above ends that.
    # Frozen rather than wired, per this list's own contract: a ratchet records "this was looked at",
    # never "this is safe". Two are worth someone's attention — `/entitlements/conditions` is
    # R22-ENTITLEMENT's own surface, and `/schedule/make-ready` is the Last Planner constraint list.
    "/cost/datasets", "/pipeline/funnel",
    "/projects/{pid}/schedule/eot/sourced",
    "/projects/{pid}/drawing-set/compiled.pdf", "/projects/{pid}/drawing-set/file-drawing-set",
    "/projects/{pid}/drawings/received-regions", "/projects/{pid}/drawings/schedule.csv",
    # `/drawings/sheet-regions` was frozen here and is now WIRED (v0.3.1119): it is the producer for
    # the `layout` that `POST /takeoff/2d` consumes, called via `api.sheetRegions` from the 2D takeoff
    # tool. Its entry is deleted rather than kept, which is this list's own contract working — the
    # freeze recorded "this was looked at", and a frozen route that gains a caller must leave.
    "/projects/{pid}/drawings/sheet.dxf",
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

    **GENERATED TYPES are excluded for exactly the same reason, and were not until 2026-08-20.**
    `api/schema.d.ts` and `api/openapiTypes.ts` are emitted FROM the OpenAPI spec, so every route in
    the API appears in them by construction — a route's presence there is a restatement of the
    server's own route table, not evidence that anything calls it. Measured: including them vouched
    for **29 routes**, taking the uncalled count from 85 down to 56. The docstring above had the
    principle right and applied it to one file; this is the same file's rule finishing its sentence.
    """
    out = []
    for pat in ("**/*.ts", "**/*.tsx"):
        for p in glob.glob(os.path.join(_WEB, pat), recursive=True):
            q = p.replace("\\", "/")
            if ".test." in q or "/src/demo/" in q:
                continue
            if q.endswith("/api/schema.d.ts") or q.endswith("/api/openapiTypes.ts"):
                continue          # generated FROM the spec: lists every route, calls none
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


#: Routes reached through a TEMPLATED EXTENSION — `<dir>/<stem>.${fmt}` — with the value verified at
#: the call site that passes it. **Named, not matched, and that is the whole point.**
#:
#: `api/model.ts:185` builds `/projects/${pid}/model/export.${fmt}`, so a pattern that allowed a
#: templated extension would vouch for every `model/export.*` route at once. Measured: it vouches for
#: six, and only two of them are called. The other four are frozen below and each is frozen
#: CORRECTLY, because **a signature that accepts a value is not a call site that passes one**:
#:
#:     model/export.ifcx    `modelExportUrl` is typed "csv" | "jsonld" | "parquet" — no caller passes it
#:     drawings/sheet.dxf   `sheetPath` accepts "dxf"; its only caller `openSheet` is ("svg" | "pdf")
#:     energy/export.gbxml  `energyExportUrl` HAS NO CALLER AT ALL — an unwired client method
#:     energy/export.idf    (same method; both formats it offers are unreachable)
#:
#: So the extension case cannot be a pattern in either direction: matching it would call four
#: unreachable routes reachable, and refusing it leaves two called routes frozen as callerless. A
#: two-entry list whose evidence is asserted below is the honest instrument.
#:
#: `model/export.csv` is absent because it is not flagged at all — it shares its leaf with
#: `/projects/{pid}/modules/{key}/export.csv`, which IS called literally. That is the shared-leaf
#: coarseness `MIN_SEGMENT` documents, working in the forgiving direction for once.
CALLED_VIA_TEMPLATED_EXT: dict[str, str] = {
    #: route -> the call-site text that must still exist for this entry to be true
    "/projects/{pid}/model/export.jsonld": 'modelExportUrl(pid, "jsonld")',
    "/projects/{pid}/model/export.parquet": 'modelExportUrl(pid, "parquet")',
}


def _templated_stem(route: str) -> "re.Pattern[str] | None":
    """`<parent>/${…}.<ext>` for a route whose leaf is a FILENAME — or None when that shape cannot apply.

    The docstring at the top of this file already knew literal matching is unsound against a client
    that builds URLs from template literals, and answered it with the last-static-segment rule. That
    rule assumes the LAST segment is written out. Six routes are built with the last segment templated
    too, so their leaf appears nowhere and they were frozen as callerless while the UI calls them:

        exportsSection.ts:57   `/projects/${projectId}/exports/${file}.xlsx`   qto · cobie · spaces · schedule
        api/schedule.ts:193-4  `/projects/${pid}/schedule/${kind}.svg`         gantt · lob

    Both call sites enumerate their values as literals in the line above, so all six are genuinely
    reachable. Checked by reading the enumeration, not by matching harder.

    **DELIBERATELY THE STEM ONLY, NEVER THE EXTENSION — and there is a live counterexample.**
    `sheetSpecs.ts:149` builds `/projects/${pid}/drawings/sheet.${fmt}` with `fmt: "svg" | "pdf" |
    "dxf"`, so an extension-templating rule would vouch for `/projects/{pid}/drawings/sheet.dxf`.
    Its only caller is `openSheet`, typed `(fmt: "svg" | "pdf")` — **nothing ever passes "dxf"**.
    That route is correctly frozen, and it is the reason this leniency stops where it does: a
    signature that ACCEPTS a value is not a call site that PASSES one.

    The parent segment must still match literally, so this cannot drift toward the 40% noise the
    header rejects: it widens only for a filename leaf, and only inside the route's own directory.
    Measured: dropping that anchor vouches for **six** further routes, none of which is called.

    **THIS IS NOT THE MATCHER-SHARPENING THIS FILE HAS REJECTED TWICE.** That proposal went the other
    way — replace the substring test with `/leaf`, which was measured at 81 -> 124 frozen, 43 newly
    unreachable, and turned down again during ASSET-VERIFY. This is a narrow *widening* on one shape,
    bounded by a differential below that names every route it vouches for. The two are opposite
    changes to the same rule and the earlier decision does not speak to this one.
    """
    segs = [s for s in route.strip("/").split("/") if not s.startswith("{")]
    if len(segs) < 2 or "." not in segs[-1]:
        return None
    stem, _, ext = segs[-1].rpartition(".")
    if not stem or not ext:
        return None
    return re.compile(rf"{re.escape(segs[-2])}/\$\{{[^}}]*\}}\.{re.escape(ext)}")


def uncalled_routes(paths, blob: str) -> set[str]:
    """Routes whose distinctive last static segment appears nowhere in the web source's CODE.

    A filename leaf may also be reached through a templated stem — see `_templated_stem`, which
    carries the evidence and the counterexample that bounds it.
    """
    code = strip_comments(blob)
    out = set()
    for r in paths:
        leaf = _leaf(r)
        if len(leaf) < MIN_SEGMENT or leaf in code:
            continue
        if r in CALLED_VIA_TEMPLATED_EXT:
            continue
        pat = _templated_stem(r)
        if pat is not None and pat.search(code):
            continue
        out.add(r)
    return out


PATHS = set(app.openapi().get("paths", {}))
BLOB = _web_source()
FOUND = uncalled_routes(PATHS, BLOB)

check("the OpenAPI surface is readable and non-trivial", len(PATHS) > 500, len(PATHS))
check("the web source was actually read", len(BLOB) > 100_000, len(BLOB))

# --- the generated-types exclusion is LOAD-BEARING, and until now it was held by nothing ----------
#
# `_web_source()` skips `api/schema.d.ts` and `api/openapiTypes.ts` because they are emitted FROM the
# OpenAPI spec: every route appears in them by construction, so their presence restates the server's
# route table rather than evidencing a caller. That correction landed 2026-08-20 after measuring that
# including them vouched for **29 routes**, dropping the uncalled count 85 -> 56.
#
# It was two `continue` lines and one docstring. **Delete them and this gate gets quietly BETTER** —
# 28 more routes look called and the uncalled count falls by a third, in the direction the ratchet
# rewards, which is the direction nobody investigates.
#
# **The first draft of this comment said every other assertion would still pass. That was wrong, and
# the mutation that was supposed to confirm it disproved it instead.** The frozen-allowlist check
# does fire — 28 entries at once. But read what it *says*: "if it now has a caller, delete the
# entry". Following that instruction is precisely how the regression becomes permanent, because it
# empties the allowlist to match a blob that is vouching for itself. So the pre-existing protection
# is real and points the reader at the wrong remedy, which is worth less than it looks and is the
# actual argument for the two checks below: they name the cause rather than a symptom.
#
# So the exclusion is now asserted two ways, and the second is the one that matters:
#   1. the generated files are genuinely out of the blob (a marker unique to them is absent), and
#   2. putting them BACK changes the answer — proving the exclusion still does work rather than
#      having become decorative because the generator's output shape drifted.
# (2) is the self-test: if the generated types ever stop naming routes, (1) keeps passing while the
# exclusion protects nothing, and only a differential measurement can tell those apart.
_GENERATED = [os.path.join(_WEB, "api", "schema.d.ts"), os.path.join(_WEB, "api", "openapiTypes.ts")]
_gen_present = [p for p in _GENERATED if os.path.exists(p)]
check("the generated type files are on disk, so this comparison is measuring something",
      len(_gen_present) == len(_GENERATED),
      f"missing: {[p for p in _GENERATED if not os.path.exists(p)]}")

#: PER FILE, not over the concatenation. The first version of this check tested `_gen_blob[:2000]`
#: — the prefix of the two files joined — which is the prefix of `schema.d.ts` alone. If
#: `openapiTypes.ts` stopped being excluded while `schema.d.ts` stayed out, the assertion still
#: passed, because the file that regressed was never inside the window being tested. Caught in
#: review; recorded because it is the same defect this whole block exists to fix, one level down: a
#: check whose SCOPE is narrower than its CLAIM.
_gen_contents = {p: open(p, encoding="utf-8", errors="replace").read() for p in _gen_present}
_leaked = [os.path.basename(p) for p, text in _gen_contents.items() if text[:2000] in BLOB]
check("  generated types are EXCLUDED from the web source the rule reads — each file checked alone",
      _gen_contents and not _leaked,
      f"inside the blob: {_leaked} — the exclusion in _web_source() is not taking effect for these")

#: THE TWO FILES ARE NOT IN THE SAME POSITION, and the differential below only speaks for one of
#: them. Measured 2026-08-29, and the numbers decide the shape of this assertion:
#:
#:     schema.d.ts      961,864 chars   would hide 28 routes
#:     openapiTypes.ts    1,777 chars   would hide  0 routes
#:
#: So the exclusion's whole value today is `schema.d.ts`; `openapiTypes.ts` names no route at all and
#: excluding it is PRECAUTIONARY. That is why this is an aggregate check and not a per-file one — a
#: per-file load-bearing assertion would be **false** for `openapiTypes.ts` and would fail on a
#: correct tree, which is how a gate gets switched off. The per-file assertion that IS true (absence
#: from the blob) is the one above, and it is what covers the smaller file.
_with_generated = uncalled_routes(PATHS, BLOB + "\n" + "\n".join(_gen_contents.values()))
check("  and the exclusion is LOAD-BEARING: including them would vouch for routes nothing calls",
      len(_with_generated) < len(FOUND),
      f"uncalled {len(FOUND)} excluded vs {len(_with_generated)} included — no difference means the "
      f"exclusion protects nothing today; find out why before trusting this gate's number")
print(f"  generated-types exclusion worth {len(FOUND) - len(_with_generated)} routes "
      f"({len(FOUND)} uncalled, {len(_with_generated)} if the generated types were counted)")
print(f"  routes {len(PATHS)} · web source {len(BLOB):,} chars · uncalled by this rule {len(FOUND)}")

# --- the templated-stem leniency is PINNED, because it moves the number the wrong way ------------
#
# Every other correction in this file made the gate stricter. This one makes it more permissive, and
# the block above says why that is the dangerous direction: a change that lowers the uncalled count
# is rewarded by the ratchet and therefore not investigated. So the leniency is not trusted to be
# small — it is measured, and the routes it vouches for are named.
#
# `_STRICT` is what the rule said before `_templated_stem` existed. The difference must be exactly
# the six whose call sites were read, one line at a time, in `_templated_stem`'s docstring.
#: Stripped ONCE. The first draft called `strip_comments(BLOB)` inside the comprehension below, so a
#: 3.9 MB blob was re-stripped per candidate route — 943 times — and this gate became the slowest in
#: the suite at 72 s. One variable also guarantees all four checks below compare against the same
#: text as `uncalled_routes` did, which a repeated call only happens to do.
_CODE = strip_comments(BLOB)
_STRICT = {r for r in PATHS
           if len(_leaf(r)) >= MIN_SEGMENT and _leaf(r) not in _CODE}
_GAINED = sorted(_STRICT - FOUND)
_STEM_GAIN = [
    "/projects/{pid}/exports/cobie.xlsx", "/projects/{pid}/exports/qto.xlsx",
    "/projects/{pid}/exports/schedule.xlsx", "/projects/{pid}/exports/spaces.xlsx",
    "/projects/{pid}/schedule/gantt.svg", "/projects/{pid}/schedule/lob.svg",
]
check("the two leniencies together vouch for EXACTLY the eight routes whose callers were read",
      _GAINED == sorted(_STEM_GAIN + list(CALLED_VIA_TEMPLATED_EXT)),
      f"gained {_GAINED}, expected {sorted(_STEM_GAIN + list(CALLED_VIA_TEMPLATED_EXT))} — a NINTH "
      f"route is not a smaller number, it is a route nobody has looked at being called reachable")

#: ATTRIBUTED, because two mechanisms summing to the right total is not the same as each being right.
#: The pattern must account for the six and the named list for the two; swap them and the aggregate
#: above still passes while both instruments are wrong.
_BY_PATTERN = sorted(r for r in _GAINED
                     if r not in CALLED_VIA_TEMPLATED_EXT
                     and (_p := _templated_stem(r)) is not None and _p.search(_CODE))
check("  ...six of them through the STEM pattern, and the other two only through the named list",
      _BY_PATTERN == sorted(_STEM_GAIN),
      f"the pattern accounts for {_BY_PATTERN}, expected {sorted(_STEM_GAIN)}")

#: THE NAMED LIST'S OWN ROT CHECK. `KNOWN_UNCALLED` has one (a frozen route must still exist);
#: an allowlist asserting the OPPOSITE polarity — "this IS called" — needs the mirror of it, or it
#: outlives its caller exactly the way the six frozen entries outlived theirs. Each entry names the
#: call-site text that makes it true, and that text must still be in the source.
_stale = sorted(r for r, ev in CALLED_VIA_TEMPLATED_EXT.items() if ev not in _CODE)
check("  ...and every named entry's CALL SITE is still there — this list can rot too",
      not _stale,
      f"no longer called: {_stale} — the evidence string is gone, so either the caller moved (update "
      f"the evidence) or the route is genuinely uncalled now (move it to KNOWN_UNCALLED)")

#: THE COUNTEREXAMPLE, AS AN ASSERTION RATHER THAN A SENTENCE.
#: `sheetSpecs.ts:149` builds `/projects/${pid}/drawings/sheet.${fmt}` and its type admits "dxf", so
#: a leniency that also allowed a templated EXTENSION would call this route reachable. Its only
#: caller `openSheet` is typed `(fmt: "svg" | "pdf")` and never passes "dxf". **A signature that
#: accepts a value is not a call site that passes one** — which is exactly the confusion the six
#: above were the other half of, and the reason this rule stops at the stem.
check("  ...and NOT for sheet.dxf, whose EXTENSION is templated but whose caller never passes 'dxf'",
      "/projects/{pid}/drawings/sheet.dxf" in FOUND,
      "sheet.dxf is being read as called — the leniency has reached the extension, and the route it "
      "now vouches for has no caller. Narrow it back to the stem.")
print(f"  templated-URL leniencies worth {len(_STRICT) - len(FOUND)} routes "
      f"({len(_BY_PATTERN)} by the stem pattern, {len(CALLED_VIA_TEMPLATED_EXT)} named; "
      f"{len(_STRICT)} uncalled under the literal-leaf rule alone)")

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

# A SECOND blind spot, measured 2026-08-31 while wiring ASSET-VERIFY, and recorded here rather than
# worked around. `/asset-rights/verify` has NO web caller and is invisible to this gate in **both**
# directions: the leaf `verify` occurs in 25 unrelated web files, so the rule reads it as called —
# and for the same reason it cannot be added to `KNOWN_UNCALLED` either, because the frozen check
# would immediately report it as "quietly become called". A route this rule can neither flag nor
# freeze is one it has no opinion about, and saying so is better than a green tick that means
# nothing.
#
# It has no client caller **by design**: the party who verifies a release is whoever received the
# `.mass`, using their own tooling — the same shape as `/auth/cloud/callback`, whose entry above
# records that it must not have one. A `verifyRelease()` method was written for the client and then
# deleted: nothing in the UI called it, so it would have been an unwired client method added to
# satisfy a reachability check — the exact defect ASSET-VERIFY exists to remove, introduced while
# removing it.
#
# The underlying coarseness is `leaf not in code`, a bare substring test. Measured alternatives, if
# anyone takes this on: matching `/leaf` flags **43** further routes, and a word-boundary match
# flags **5** (`/pipeline/allocate`, `/projects/{pid}/coordination/stale/recheck`,
# `/projects/{pid}/model/columnar/aggregate`, `/projects/{pid}/modules/{key}/aggregate`,
# `/structure/recommend`). Both are more accurate than what runs today; neither belongs in a release
# about signed manifests, and each needs those routes triaged rather than bulk-frozen.
check("the ASSET-VERIFY blind spot is still a blind spot, not silent coverage",
      "/asset-rights/verify" not in FOUND and "/asset-rights/verify" not in KNOWN_UNCALLED,
      "if this now fails, the matcher changed — re-triage /asset-rights/verify rather than "
      "assuming the green tick above ever meant it was reachable")

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
