"""TRUNC-COUNTED — does a response that returns a PAGE also say how big the population was?

Three engines returned a truncated list and no total, and three screens printed the page's length as
if it were the total. The sharpest is `roundtrip_diff`, because a screen does not merely misreport
it — it ACTS on it:

  * `rows[1:5001]`  — the sheet itself is capped. Undisclosed.
  * `changes[:1000]` — disclosed, via `truncated`, which `apps/web/src/api/model.ts` did not DECLARE,
    so `qaSection.ts` could not read it even though the same file reads the identical flag on another
    response whose type does declare it. *A field absent from the declaration is invisible to every
    audit over declarations* — the CLASH-TRUNC hole, in a second place.
  * `unknown_guids[:100]` — undisclosed.

The Apply button posts `d.changes`, the PAGE. A sheet with more changes than the cap was therefore
applied in part and reported as whole: the model ends up differing from the spreadsheet the operator
believes they applied, with no error anywhere. The cap is reachable by construction and not only in
principle — `_diff_row` emits one change per changed CELL against a 5,000-row bound, so a single
property column overflows a 1,000 cap fivefold.

WHY THERE IS NO SWEEP GATE HERE, recorded so nobody rebuilds it and believes the number.
The class was derived: 43 list truncations inside returned dicts, of which **26 already carry a
sibling `len()`** — the good pattern is this codebase's own convention, which is what makes the rest
anomalous. Of the 17 without, 11 carry the count under another NAME (`total - compliant`,
`unapproved`, `count`) or are top-N by design, leaving 6 fields in 3 files.

Joining those names to `.length` reads in the web tree reports **35 sites**, and it is not a finding:
`guids` alone accounts for 12, matched against engines their callers never call. Two were read in
full — `qaSection.ts:205` reads an assembly-thermal result's `guids` (it slices to 200 itself), and
`repairPanel.ts:184` reads `sample.length` only to decide whether to print an ellipsis, with the
authoritative `removable` count rendered beside it. *A leaf name is not a response*, and a number with
a list attached reads as evidence. Even a checker-resolved join would still have to separate
"`.length` shown to a user as a count" from "`.length` used for an ellipsis" — a judgement call, and a
rule needing judgement calls needs an exemption list, which is where the next instance hides.

So this file gates the three fixed sites behaviourally and stops there.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_trunc_counted.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_trunc_counted")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import ast  # noqa: E402
import inspect  # noqa: E402
from pathlib import Path  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('   ' + detail) if detail else ''}")
    if not ok:
        FAILURES.append(name)


def returned_keys(fn) -> set[str]:
    """The literal string keys of the dict this function RETURNS, by AST rather than by regex — a
    regex over the source also matches keys of dicts built along the way."""
    tree = ast.parse(inspect.getsource(fn).lstrip())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    out.add(k.value)
    return out


# ------------------------------------------------------------------------------------------------
# 1) roundtrip_diff — every bound reports itself
# ------------------------------------------------------------------------------------------------
from aec_api.routers import standards  # noqa: E402

rt = returned_keys(standards.roundtrip_diff)
check("PRECONDITION: roundtrip_diff's return dict was parsed", len(rt) >= 5, f"{len(rt)} keys")
for pair, why in ((("changes", "change_count"), "the changes page"),
                  (("unknown_guids", "unknown_count"), "the unknown-GUID page")):
    page, total = pair
    check(f"{why} is returned with its total", page in rt and total in rt,
          f"{page}={page in rt} {total}={total in rt}")
check("the SHEET bound reports itself too — it was the one nothing mentioned",
      {"rows_read", "rows_cap", "rows_truncated"} <= rt,
      f"missing {sorted({'rows_read', 'rows_cap', 'rows_truncated'} - rt)}")
check("the pre-existing `truncated` flag is still returned",
      "truncated" in rt)

# The sheet bound must be the one the loop actually applies, not a number written twice.
src = inspect.getsource(standards.roundtrip_diff)
check("`rows_cap` agrees with the slice the loop really takes",
      "rows[1:5001]" in src and "\"rows_cap\": 5000" in src,
      "a cap reported from a different literal than the one applied is worse than none")

# ------------------------------------------------------------------------------------------------
# 2) spine traceability — the counts beside the pages
# ------------------------------------------------------------------------------------------------
from aec_api import spine  # noqa: E402

sp = inspect.getsource(spine.traceability)
check("spine gaps carry a `counts` block", '"counts": {"specs_without_bid_package"' in sp)
check("...with a `total`, which is what the screen prints", '"total": len(specs_no_pkg)' in sp)
check("...and `chain` carries its count", '"chain_count": len(chain)' in sp)
# The percentages were always right; that is the whole reason the screen contradicted itself.
check("the percentages are still taken over the FULL lists, not the pages",
      "len(specs) - len(specs_no_pkg)" in sp and "specs_no_pkg[:100]" in sp,
      "if these ever read from the page, the pct and the count would agree by both being wrong")

# ------------------------------------------------------------------------------------------------
# 3) dashboard — a worklist page with no total
# ------------------------------------------------------------------------------------------------
from aec_api import dashboard  # noqa: E402

db = returned_keys(dashboard.build)
check("dashboard returns action_item_count beside the page",
      {"action_items", "action_item_count"} <= db,
      f"missing {sorted({'action_items', 'action_item_count'} - db)}")

# ------------------------------------------------------------------------------------------------
# 4) THE CLIENT MUST DECLARE THEM — an undeclared field is unreadable, which is the whole cause here.
#    `truncated` shipped on the wire for months and `model.ts` never declared it, so no type error,
#    lint, or audit over declarations could reach `qaSection.ts:699`.
# ------------------------------------------------------------------------------------------------
#: `parents[2]`, not `[1]` — `[1]` is `services/`. The first draft used it and died with a
#: FileNotFoundError, which is the right DIRECTION to fail but the wrong shape: a check that
#: tracebacks blames Python rather than naming the path it wanted. `read()` below turns a bad
#: anchor into a named failure, and the byte floors turn an empty read into one too.
WEB = Path(__file__).resolve().parents[2] / "apps" / "web" / "src"


def read(*parts: str) -> str:
    p = WEB.joinpath(*parts)
    if not p.is_file():
        check(f"PRECONDITION: {'/'.join(parts)} exists", False, f"looked in {p}")
        return ""
    return p.read_text(encoding="utf-8")


model_ts = read("api", "model.ts")
check("PRECONDITION: model.ts was read", len(model_ts) > 2000, f"{len(model_ts)} bytes")
#: SCOPED TO `roundtripDiff`'s OWN DECLARATION, and word-boundary matched. Two drafts were wrong
#: here, in the two ways this repo keeps re-learning:
#:
#:   1. `f"{f}:" in model_ts` — `rows_truncated:` CONTAINS `truncated:`, so deleting the field
#:      under test still passed. A suffix match, the mirror of the prefix match `test_gap_records`
#:      paid for.
#:   2. Word-boundary matching over the WHOLE FILE — still passed, because `truncated: boolean`
#:      is declared on four other, unrelated endpoints in this 66 KB file (lines 271, 330, 555,
#:      711). *A leaf name is not a response* — the sentence in this file's own docstring, about
#:      the 35-site name join, committed one screen later in the check itself.
#:
#: So the subject is the text of roundtripDiff's return type, nothing else.
import re as _re  # noqa: E402


def declaration_of(src: str, method: str) -> str:
    """The source of one client method, from its name to the start of the next member."""
    m = _re.search(rf"^  (?:async )?{_re.escape(method)}\s*\(", src, _re.M)
    if not m:
        return ""
    rest = src[m.end():]
    nxt = _re.search(r"^  (?:async )?[a-zA-Z_]\w*\s*\(|^  /\*\*", rest, _re.M)
    return rest[:nxt.start()] if nxt else rest


rt_decl = declaration_of(model_ts, "roundtripDiff")
check("PRECONDITION: roundtripDiff's own declaration was located and is not the whole file",
      500 < len(rt_decl) < 3000, f"{len(rt_decl)} bytes of {len(model_ts)}")
check("PRECONDITION: …and it is the right method", "roundtrip/diff" in rt_decl)

for f in ("truncated", "change_count", "unknown_count", "rows_read", "rows_cap", "rows_truncated"):
    check(f"roundtripDiff declares `{f}`",
          _re.search(rf"(?<![\w$]){_re.escape(f)}\s*:", rt_decl) is not None)

types_ts = read("api", "types.ts")
check("PRECONDITION: types.ts was read", len(types_ts) > 10000, f"{len(types_ts)} bytes")
check("types.ts declares the spine gap counts", "counts: { specs_without_bid_package: number" in types_ts)
check("types.ts declares action_item_count", "action_item_count: number" in types_ts)
check("types.ts declares chain_count", "chain_count: number" in types_ts)

# ------------------------------------------------------------------------------------------------
# 5) AND THE CONSUMERS MUST READ THEM RATHER THAN THE PAGE LENGTH. Declaring a total that nobody
#    reads is the same screen with more JSON behind it.
# ------------------------------------------------------------------------------------------------
ops = read("portal", "panels", "operations.ts")
check("operations.ts counts broken links from the server's total",
      "const gapCount = g.counts.total;" in ops)
check("...and no longer sums the three page lengths",
      "g.specs_without_bid_package.length + g.bid_packages_without_cost_code.length" not in ops)

qa = read("viewer", "tools", "qaSection.ts")
check("qaSection headline uses change_count, not changes.length",
      "<b>${d.change_count}</b> change(s)" in qa and "<b>${d.changes.length}</b> change(s)" not in qa)
check("...and unknown_count, not unknown_guids.length",
      "d.unknown_count" in qa and "d.unknown_guids.length" not in qa)
check("the Apply button says it applies only the PAGE when the sheet overflows",
      "Apply the first ${d.changes.length} of ${d.change_count}" in qa,
      "this is the one that ACTS on the number rather than just printing it")
check("...and warns that the rest are left unwritten",
      "leaves the rest" in qa)

portal = read("portal", "portal.ts")
check("the dashboard worklist says how many it is showing of how many",
      "showing 20 of ${d.action_item_count}" in portal)

print()
if FAILURES:
    print(f"trunc_counted: {len(FAILURES)} FAILED — {FAILURES}")
    sys.exit(1)
print("trunc_counted: all checks passed — the three truncated responses report their populations, "
      "the client declares them, and the three screens read them instead of the page length.")
