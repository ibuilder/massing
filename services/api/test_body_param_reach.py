"""Does anything SEND what a route accepts? — the mirror of route reachability.

`test_route_reachability.py` asks whether a route is CALLED. This asks whether a route's **required
body parameter is ever named** anywhere in the web source. They are not the same question, and the
difference is what found TM-RATES.

## Why the other gate could not see it

That gate matches a route's last static path segment against the web source and **skips any segment
shorter than `MIN_SEGMENT` (5)**. Its own docstring measures the cost: **113 routes, 12% of the
surface, are never assessed at all**, and it names `/schedule/eot` (leaf `eot`) as an example it
structurally cannot speak for.

`POST /projects/{pid}/cost/tm` is in that 113 — leaf `tm`, two characters. It was uncalled, its
write-back was being silently undone by MOD-TOTALS, and it answered 200 with the correct total in
its body while the record kept the old one. Nothing anywhere could say so. The reachability gate's
docstring claims "of the 113, exactly **two** are genuinely uncalled"; that was measured on
2026-08-20 and `/cost/tm` was already a third.

**A required body parameter is a distinctive identifier, and a two-character path leaf is not.** So
this rule reaches routes the leaf rule cannot, for the same reason the leaf rule reaches routes a
whole-path match cannot: it picks the part of the declaration that survives being written by a
different author on the other side of the wire.

## What is gated, and what is only counted

**Gated: the REQUIRED half.** A `Body(...)` parameter with no default cannot be omitted — so if its
name appears nowhere in the web source, the route is not called from this application at all. That
is a strong claim from a coarse rule, and the population today is **1**, whose route
`test_route_reachability.py` already freezes as uncalled. The check is that cross-agreement: a
required parameter nobody sends must belong to a route the other gate already knows about. When it
does not — as `/cost/tm` did not, and could not, because its leaf is too short — that is a route
that has gone dark inside the other gate's blind spot.

**Counted, not frozen: the OPTIONAL half.** 27 optional parameters are never named, and they are a
weaker signal: an engine running on a default nobody chose is sometimes exactly right (the default
FAR sweep on `/design/options/generate`) and sometimes a capability the UI cannot reach (the
`lot_polygon` on `/generate/massing`, where the client can only send a rectangle). **They have not
been triaged one by one, so they are not frozen** — an allowlist of things nobody has read is a
freeze list, which is the lesson DEAD-FIELD closed on. The count is printed so it is visible; when
someone triages them, this is where the verdicts go.

## What the derivation gets wrong, recorded because each correction cost a run

Five bugs, in order, and two of them were introduced by fixing the previous one:

1. **Shorthand.** `capitalCall(pid, amount, persist)` builds `{ amount, persist }`, so a `"k":`
   pattern misses it. Widened to `["']?\\bkey\\b["']?\\s*[:,}]`.
2. **Scope, too wide.** Matching the whole web tree returned 30 candidates, nearly all noise.
3. **Scope, then too NARROW — and this is the instructive one.** Scoping to `apps/web/src/api`
   (where the typed client builds its bodies) cut 30 to 8 and INVENTED two findings:
   `drawings/layout.svg` and `.pdf` are called by a raw `fetch` in `drawings/layoutEditor.ts`,
   outside that directory, and they do send `viewports`. **Narrowing a search to kill a false
   positive is how you buy a false negative**, and here it bought two false positives instead —
   the narrowing removed evidence of a call, and absent evidence reads as absence. The blob is the
   whole tree, as `test_route_reachability` reads it.
4. **Aliases.** `Body(..., alias="parcels")` means the wire key is `parcels`, not the Python
   parameter name. Reading the OpenAPI schema rather than the function signature fixes this by
   construction — the spec is the wire contract, and it is what the client is written against.
5. **Required vs optional are different findings.** A required parameter that is never sent means
   the route is UNCALLED. An optional one means it runs on a default. Conflating them puts a dark
   route in the same list as a defaulted knob.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_body_param_reach.py
"""
import ast
import os
import re
import sys

sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["DATABASE_URL"] = "sqlite:///./_body_param_reach.db"
os.environ.setdefault("STORAGE_DIR", "./_body_param_reach_store")

from aec_api.main import app  # noqa: E402
from web_source import _web_source, strip_comments  # noqa: E402

FAILED: list[str] = []


def _frozen_uncalled() -> set[str]:
    """`KNOWN_UNCALLED` as `test_route_reachability.py` declares it, read without running it."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "test_route_reachability.py"), encoding="utf-8").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "KNOWN_UNCALLED":
            return {v for v in ast.literal_eval(node.value) if isinstance(v, str)}
    raise AssertionError("KNOWN_UNCALLED is no longer a literal set assignment in "
                         "test_route_reachability.py — this gate reads it by AST")


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def body_params(spec: dict) -> list[tuple[str, str, str, bool]]:
    """`(path, method, wire key, required)` for every JSON body property the API declares.

    Read off the OpenAPI schema, not the Python signatures: `Body(..., alias="x")` puts `x` on the
    wire under a parameter named something else, and the client is written against the wire.
    """
    out = []
    for path, ops in (spec.get("paths") or {}).items():
        for method, op in ops.items():
            if method.upper() not in ("POST", "PUT", "PATCH"):
                continue
            sch = ((op.get("requestBody") or {}).get("content", {})
                   .get("application/json", {}).get("schema") or {})
            if ref := sch.get("$ref"):
                sch = (spec.get("components", {}).get("schemas", {})
                       .get(ref.rsplit("/", 1)[-1]) or {})
            required = set(sch.get("required") or [])
            for key in (sch.get("properties") or {}):
                out.append((path, method.upper(), key, key in required))
    return out


def names_key(code: str, key: str) -> bool:
    """Does the web source name this wire key — as a JSON property, ES shorthand, or an ASSIGNMENT?

    Deliberately coarse in the LENIENT direction, exactly like the leaf rule it mirrors: a key named
    anywhere counts as sent. Over-matching can only make this gate miss a gap; under-matching would
    invent work for somebody, which is the expensive mistake.

    **And it made exactly that mistake from the day it shipped.** The first draft accepted only
    `key:` / `key,` / `key}` — object-literal syntax. A request body assembled INCREMENTALLY is not
    written that way: `massingTab.params()` builds `p` field by field (`p.dome_radius = ...`,
    `p.parking = ...`) and stringifies it, which is an ordinary way to send an optional only when it
    applies. So `dome_radius` sat on the unsent list while a control on the feasibility tab had been
    sending it all along, and PARCEL-SHAPE's `lot_polygon` joined it the day it was wired. Two false
    positives out of 27, in the direction the paragraph above calls expensive — because the rule was
    written from the shape of the code that happened to be in front of it.

    `=` is admitted, but not `==` / `===` (a comparison is a read, not a send) and not `=>` (an
    arrow parameter that happens to be named for the key is not a send either).
    """
    return re.search(rf'["\']?\b{re.escape(key)}\b["\']?\s*(?:[:,}}]|=(?![=>]))', code) is not None


def unsent(params, code: str, *, required: bool) -> list[tuple[str, str, str]]:
    """The verdict function, separate so a mutation can be aimed at it directly.

    `test_unique_read_guard.py`'s first draft asserted only that its analyser REPORTED a site, so a
    mutation that misclassified every site still passed. Reporting a candidate and judging it are
    two questions; this is the judging one, and the self-test below mutates it.
    """
    return sorted((p, m, k) for p, m, k, r in params if r is required and not names_key(code, k))


# --- the matcher's own blind spot, pinned ---------------------------------------------------------
# Reverting `names_key` to object-literal syntax alone reds this. That matters because the fix is
# invisible to every check below: both counts are printed and neither is frozen, so a silent
# regression would show up as a number nobody was watching. A comparison and an arrow parameter must
# NOT count — they are reads, not sends.
_M = "const p = {}; p.lot_polygon = ring; if (x.foo === 1) {} const f = (bar) => bar;"
assert names_key(_M, "lot_polygon"), "an incrementally assembled body is a SEND"
assert names_key('{"lot_polygon": r}', "lot_polygon"), "...and so is an object literal"
assert not names_key(_M, "foo"), "`foo === 1` is a comparison, not a send"
assert not names_key(_M, "bar"), "`(bar) => bar` is an arrow parameter, not a send"

SPEC = app.openapi()
CODE = strip_comments(_web_source())
PARAMS = body_params(SPEC)
MISSING_REQUIRED = unsent(PARAMS, CODE, required=True)
MISSING_OPTIONAL = unsent(PARAMS, CODE, required=False)

check("the OpenAPI body surface is readable and non-trivial", len(PARAMS) > 300, len(PARAMS))
check("the web source was actually read", len(CODE) > 1_000_000, len(CODE))

# --- the self-test: the derivation must find the defect it was BUILT from ------------------------
#
# `eticket_id` is sent today (TM-RATES wired it), so the live population cannot demonstrate that
# this rule reaches `/projects/{pid}/cost/tm`. Deleting the call site from a COPY of the blob
# restores the world the gate was written for, and the rule must report it. Without this the check
# could have been silently unable to see the very route that motivated it — which is precisely how
# `test_seeding_sweep.py`'s first draft reported a clean tree over four live races.
_PRE_FIX = CODE.replace("eticket_id: eticketId", "REMOVED_BY_SELF_TEST")
check("the call site the self-test removes actually exists", _PRE_FIX != CODE,
      "priceTicket no longer sends `eticket_id` under that name — update this self-test to name "
      "the current call site, do NOT delete the check")
_found = unsent(PARAMS, _PRE_FIX, required=True)
check("run against the PRE-FIX web source, the rule finds /cost/tm's eticket_id",
      ("/projects/{pid}/cost/tm", "POST", "eticket_id") in _found, _found)

# ...and finding it is not the same as JUDGING it. A verdict function that returned everything would
# satisfy the check above, so the negative is asserted too: on the CURRENT source it must be absent.
check("...and on the current source it is NOT reported, because the client now sends it",
      ("/projects/{pid}/cost/tm", "POST", "eticket_id") not in MISSING_REQUIRED,
      MISSING_REQUIRED)

# --- the gate ------------------------------------------------------------------------------------
#
# Every required body parameter nothing sends must belong to a route the reachability gate ALREADY
# knows is uncalled. Anything else is a route that has gone dark where that gate cannot look.
#
# Read out of the other gate's source by AST rather than restated here, and rather than IMPORTED:
# importing would run that whole gate a second time, and a second copy of the list would let this
# check pass while the list it depends on moved underneath it.
KNOWN_UNCALLED = _frozen_uncalled()
check("the frozen-uncalled list was actually parsed out of the other gate",
      len(KNOWN_UNCALLED) > 10, len(KNOWN_UNCALLED))

def unexplained(missing, frozen) -> list[tuple[str, str, str]]:
    """The second verdict: which unsent-required findings are NOT already accounted for."""
    return [(p, m, k) for p, m, k in missing if p not in frozen]


# The gate's own fail-closed check. `KNOWN_UNCALLED` is parsed from another file, so a change there
# — or a mutation here — could make every finding "explained" and this gate silently vacuous. A
# fabricated finding on a route that is NOT frozen must come back unexplained.
_SYNTHETIC = ("/projects/{pid}/cost/tm", "POST", "eticket_id")
check("a finding on a route the other gate does NOT freeze is reported, not absorbed",
      unexplained([_SYNTHETIC], KNOWN_UNCALLED) == [_SYNTHETIC],
      f"{_SYNTHETIC[0]} is not in KNOWN_UNCALLED (its leaf is too short for that gate to assess), "
      f"so it must survive this filter — if it does not, the filter is letting everything through")

_unexplained = unexplained(MISSING_REQUIRED, KNOWN_UNCALLED)
check("no route has a REQUIRED body parameter nothing sends, unless it is already frozen as uncalled",
      not _unexplained,
      "; ".join(f"{m} {p} needs {k!r} and nothing in apps/web names it" for p, m, k in _unexplained)
      + " — either wire a caller, or freeze the route in test_route_reachability.KNOWN_UNCALLED "
        "with the reason")

# --- the live count reached ZERO, and NOT because the surface completed ---------------------------
#
# This check used to be `bool(MISSING_REQUIRED)`: some required parameter must be genuinely unsent,
# or the filter above is vacuous. On 2026-09-11 it went to zero and the honest reading is **not**
# "the surface is complete".
#
# The last finding was `/proforma/entitlement-risk` needing `entitlement`. That route is still dark —
# it is frozen in `test_route_reachability.KNOWN_UNCALLED` and nothing calls it. What changed is that
# R40-EOT added `apps/web/src/api/schedule.ts`, whose `EotEvent` / `EotEventInput` declare
# `entitlement: string | null` — the AACE entitlement CLASS of a delay event, a different domain
# entirely. `names_key` matches `key` followed by `:`, so **a TypeScript type annotation now reads as
# a send.**
#
# That is the third shape of this collision family recorded in this repository within one day, and it
# is the one the others did not predict:
#   * a route leaf inside unrelated PROSE (`/proforma/renovation`);
#   * a route leaf that is another ROUTE's leaf (`/jurisdiction/check`);
#   * and now a body key that is a TYPE DECLARATION rather than a value — *the matcher cannot tell
#     `{foo: bar}` from `foo: string`, because in text they are the same shape.*
#
# **Not sharpened, deliberately.** This file's own docstring says the rule is coarse in the LENIENT
# direction on purpose: "over-matching can only make this gate miss a gap; under-matching would
# invent work for somebody, which is the expensive mistake." Excluding type positions textually would
# reintroduce exactly the false positives `names_key` was widened to remove.
#
# So the assertion is replaced rather than deleted, and it now tests the RULE instead of the
# population — using this file's own self-test idiom. Remove the colliding declaration from a copy of
# the blob and the finding must come back. That cannot go vacuous the way a count can.
COLLIDED = ("/proforma/entitlement-risk", "POST", "entitlement")
_NO_COLLISION = CODE.replace("entitlement?: string | null", "REMOVED_BY_SELF_TEST") \
                    .replace("entitlement: string | null", "REMOVED_BY_SELF_TEST")
check("the colliding declaration this check now depends on still exists",
      _NO_COLLISION != CODE,
      "api/schedule.ts no longer declares `entitlement` on its EOT event types — re-point this at "
      "whatever collides today, or if nothing does, restore `bool(MISSING_REQUIRED)`")
check("with the COLLISION removed, the rule still finds a genuinely unsent required parameter",
      COLLIDED in unsent(PARAMS, _NO_COLLISION, required=True),
      f"{COLLIDED[0]} needs {COLLIDED[2]!r} and is frozen as uncalled, so removing the unrelated "
      "type declaration must expose it again; if it does not, `names_key` or the OpenAPI read broke")
check("...and the live population is zero ONLY by that collision, not by completion",
      not MISSING_REQUIRED,
      f"a required parameter is unsent again: {MISSING_REQUIRED} — good news if it was just wired, "
      "but read it before assuming; this line asserts the state recorded above, so a change here "
      "means the note is now wrong")

print(f"\n  body params {len(PARAMS)} "
      f"({sum(1 for *_, r in PARAMS if r)} required) · web source {len(CODE):,} chars")
print(f"  required and unsent: {len(MISSING_REQUIRED)} — all on routes frozen as uncalled")
for p, m, k in MISSING_REQUIRED:
    print(f"    {m:5} {p} · {k}")
# NOT a ratchet. These are untriaged and a frozen count would be a freeze list; the number is here
# so that a jump in it is visible to whoever next reads this output.
print(f"  optional and unsent: {len(MISSING_OPTIONAL)} — an engine on a default nobody chose."
      "\n    UNTRIAGED, deliberately not frozen. Read one before calling it a defect: "
      "`/design/options/generate`'s\n    `far_steps` default (60/80/100% of base FAR) is right, "
      "and `/generate/massing`'s `lot_area` is a\n    real capability the client cannot reach — it "
      "is how you state a lot whose DIMENSIONS are unknown, and the tab\n    offers only width x depth "
      "or a boundary. Same shape, opposite verdicts. (`lot_polygon` was\n    this line's example until "
      "PARCEL-SHAPE wired it — an exemplar that gets FIXED is the good\n    outcome, and leaving it here "
      "would have made this note a lie.)")

print()
if FAILED:
    print(f"body_param_reach FAILED ({len(FAILED)}): " + "; ".join(FAILED))
    raise SystemExit(1)
print("body_param_reach: all checks passed")
