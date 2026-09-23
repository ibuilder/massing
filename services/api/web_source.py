"""The web source the reachability gates read, and the comment stripping they read it through.

Shared by `test_route_reachability.py` (does anything CALL this route?) and
`test_body_param_reach.py` (does anything SEND what this route accepts). They ask opposite halves of
one question and must read the SAME text to be comparable: if one counted a comment as a call site
and the other did not, "required parameter nobody sends, on a route something calls" would be an
artefact of the two blobs disagreeing rather than a finding.

Extracted from `test_route_reachability.py` on 2026-09-09, unchanged — the docstrings below are that
file's, including the measurements that justify each exclusion. A second copy of this rule is
exactly the drift CLAUDE.md warns about, and it would drift in the direction that INVENTS work:
whichever copy strips less reports more routes as unreachable.
"""
import glob
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

    **THE VENDORED TREE is excluded for the third time in the same argument, since 2026-09-23.**
    `apps/web/src/vendor/massingifc` and `apps/web/src/vendor/massingpdf` are verbatim copies of two
    other repositories — `VENDOR.md` in each says so, and says the copies carry **no local edits** —
    so a word appearing there is evidence about somebody else's product, not about what this client
    calls. That is the same sentence as the generated types above with a different subject: the blob
    is meant to answer "does OUR app do this", and both exclusions remove text that answers a
    different question while looking like an answer to that one.

    **It was not a theory — this file's consumer had already written the defect down without naming
    the cause.** `test_route_reachability.py` records `/projects/{pid}/cost/calibration` as vouched by
    "85 hits of PDF-takeoff SCALE calibration under `vendor/massingpdf/`, a different trade entirely",
    and its own deterministic backtick fixture is a line copied out of
    `vendor/massingifc/project-schema/coordination.ts`. Two of the five entries in its
    LEAF-COLLISION list were vendor collisions; the diagnosis stopped at "a leaf that is also a common
    domain noun".

    **Measured: 83 of 399 files and 708,650 of 4,597,236 characters, and it moves exactly 2 routes**
    — `/projects/{pid}/workflow/{key}` and `/projects/{pid}/project-package/contents`, uncalled 57 ->
    59. Both were already frozen as invisible in `LEAF_COLLISION_BLIND`, so this does not find new
    debt; it converts two routes the gate could not see into two the gate reports, which is the
    direction the ratchet PUNISHES and therefore the direction nothing was going to drift into on its
    own.

    **SORTED, since 2026-09-23.** `glob.glob` returns filesystem order, so this blob was a different
    string on every machine and the gates reading it could disagree with themselves between runs. A
    stable order does not make any single verdict correct — it makes a failure REPRODUCIBLE, which is
    the property an intermittent takes away. The defect it was hiding is written up at the
    `LEAF_COLLISION_DARK` vouch check in `services/api/test_route_reachability.py`.
    """
    return "\n".join(open(p, encoding="utf-8", errors="replace").read() for p in web_files())


def web_files() -> list[str]:
    """The files `_web_source()` concatenates, in the order it concatenates them.

    Split out so the order-invariance check in `services/api/test_route_reachability.py` can rebuild
    the blob in a DIFFERENT order without restating which files are in it. A second copy of the
    inclusion rule is the drift this module's own docstring warns about, and it would drift in the
    direction that invents work.
    """
    out = []
    for pat in ("**/*.ts", "**/*.tsx"):
        for p in glob.glob(os.path.join(_WEB, pat), recursive=True):
            q = p.replace("\\", "/")
            if ".test." in q or "/src/demo/" in q:
                continue
            if q.endswith("/api/schema.d.ts") or q.endswith("/api/openapiTypes.ts"):
                continue          # generated FROM the spec: lists every route, calls none
            if "/src/vendor/" in q:
                continue          # somebody else's repo, copied verbatim: names routes, calls none
            out.append(p)
    #: ONE sort over the WHOLE list, not one per glob pattern. Sorting inside the loop yields
    #: `[every .ts sorted] + [every .tsx sorted]`, which is deterministic but is not sorted — and the
    #: assertion in `test_route_reachability` that this is sorted CANNOT TELL THE TWO APART TODAY,
    #: because the tree holds 0 `.tsx` files against 658 `.ts`. So the first draft of the fix was
    #: accidentally right and its check was accidentally green; the day somebody adds a `.tsx` the
    #: check would have red with a message blaming the glob. *A check that passes because its
    #: population is empty is the same shape as one that passes because the code is correct.*
    #: Found in review. The probe beside that assertion feeds a synthetic `.tsx` through this
    #: function so the contract is tested on an input the tree cannot supply.
    return sorted(out)


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
