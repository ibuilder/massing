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
