"""COMPTIER-DARK — does the comp source ladder speak the register's own vocabulary?

`comp_tier.TIERS` classifies a comp's `source` by looking for phrases in it, and its docstring calls
that *"pure string normalization over what users already type"*. **Users do not type it.**
`services/api/modules/comparable/module.json` declares `source` a `select` with seven options and
`modules._validate_values` refuses anything outside them, so the guaranteed population of
`tier_of()` is seven fixed strings — and **four of the seven matched no phrase at all**:

    CoStar -> unknown    Appraisal -> unknown    Owner -> unknown    Other -> unknown

Three of those are demotions to the WEAKEST tier, and demotion is the expensive direction here.
`statistic()` exists to report the weakest tier a band rests on and appends *"Strengthen that source
before the number carries a decision."* A band of owner-confirmed or appraisal comps carried that
sentence on every render, so **the one qualifier this leaf publishes fired on the most ordinary
sources an analyst picks.** It was not missing; it was always on, which is the same as missing by the
time anybody has read it twice.

WHY THIS IS A GATE AND NOT A COMMENT BESIDE THE FIX
---------------------------------------------------
The tier ladder and the register are edited by different people for different reasons — one is a
market-data judgement, the other is a form. Nothing connected them, so adding an eighth option, or
renaming `Owner` to `Principal`, silently returns a source to the weakest tier and **nothing goes
red**: the route still answers 200, the band still has an `n`, and the only visible change is a
sentence that was already there. So the population is DERIVED from `module.json` rather than
restated here, and the agreement is asserted in BOTH directions — a key for an option that no longer
exists is dead weight that reads as coverage, which is the `ROWKEY-SUPERSET` lesson: *a test named
for equality that asserts containment misses exactly the entry added last.*

PROOF OF REACH, because a gate over a table cannot see whether the table is consulted
-------------------------------------------------------------------------------------
Every check below passes against a `tier_of` that reads `REGISTER_SOURCES` and ignores it — the
table would be correct and inert. So this file reinstates the PRE-FIX classifier (the substring pass
alone) and requires it to re-find **exactly** the four unmatched options before any verdict is
printed, and it mutates the live function's lookup away to require the behavioural check to red.
*A static check that still passes with the mechanism removed is not testing the mechanism.*

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_comp_tier_sources.py
"""
import json
import pathlib
import sys
from typing import Any

# Anchored on `__file__`, not on `"src"`. `run_tests.py` chdirs to `services/api` and `ci.yml`
# invokes it from the repo root, so a relative entry resolves in one of those and not the other —
# and the comment further down about `Path("modules")` would be advice this file did not take.
_HERE = pathlib.Path(__file__).resolve().parent
for _p in (_HERE / "src", _HERE.parent / "data" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from aec_api import comp_tier  # noqa: E402

FAILED: list[str] = []


def check(label: str, ok: bool, detail: Any = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)
    return ok


def abort(why: str) -> None:
    """A precondition failure is not a pass. Nothing below here may print a verdict."""
    print(f"\nFAIL  precondition — {why}")
    print("comp_tier_sources: ABORTED, no verdict (the gate could not establish its own basis)")
    sys.exit(1)


# --- the population, DERIVED ----------------------------------------------------------------------
# Anchored on __file__, not on the working directory. `run_tests.py` chdirs to `services/api` while
# `ci.yml` invokes it from the repo root, and `Path("modules")` resolves in one of those and not the
# other — `rglob`/`read_text` over a missing path is a confident wrong answer, which is what
# `test_scratch_ignored` and `test_schema_types_agree` each paid for once.
SPEC = _HERE / "modules" / "comparable" / "module.json"
if not SPEC.is_file():
    abort(f"{SPEC} is not readable, so the population cannot be derived")

spec = json.loads(SPEC.read_text(encoding="utf-8"))
_source_fields = [f for f in spec.get("fields", []) if f.get("name") == "source"]
if len(_source_fields) != 1:
    abort(f"`comparable` declares {len(_source_fields)} fields named `source`; expected exactly 1")
SOURCE = _source_fields[0]
OPTIONS: list[str] = list(SOURCE.get("options") or [])
if SOURCE.get("type") != "select":
    abort(f"`comparable.source` is type {SOURCE.get('type')!r}, not `select` — this gate's whole "
          f"premise is that the value space is closed; re-derive it before trusting the table")
if len(OPTIONS) < 2:
    abort(f"`comparable.source` declares {len(OPTIONS)} option(s); the population is empty or "
          f"unparsed, and an empty population reports a clean tree in the same words as a clean one")

print(f"`comparable.source` is a select over {len(OPTIONS)} option(s): {OPTIONS}\n")


# --- proof of reach (1): the PRE-FIX classifier must re-find the four ------------------------------
def _prefix_tier_of(source: Any) -> dict[str, Any]:
    """`comp_tier.tier_of` exactly as it shipped before 2026-10-14 — the substring pass alone.

    Embedded rather than fetched from git history. `test_gap_records` learned that one in CI: a
    replay that reads a commit works locally and fails on a shallow checkout, and *a proof of reach
    that depends on the depth of somebody's clone is not a proof.*
    """
    text = comp_tier._norm(source)
    for key, spec_ in comp_tier._BY_RANK:
        if any(phrase in text for phrase in spec_["match"]):
            return {"tier": key, "matched": True}
    return {"tier": comp_tier.WEAKEST, "matched": False}


_was_broken = sorted(o for o in OPTIONS if not _prefix_tier_of(o)["matched"])
KNOWN_BROKEN = ["Appraisal", "CoStar", "Other", "Owner"]
if _was_broken != KNOWN_BROKEN:
    # THREE causes, and the first one listed is the repair this gate exists to refuse. An earlier
    # draft named only the other two, and under exactly that mutation — `"owner"` added to the
    # `verified` phrase list — this is the message that printed: *a check whose failure message can
    # misdiagnose is worse than one that stays silent, because somebody acts on it.* The replay
    # shares `TIERS` with the live function by design (it must, to be a replay of the pass rather
    # than of a snapshot), so widening a phrase list moves BOTH and lands here rather than on the
    # promotion pins below, which is why those pins cannot be the only thing saying so.
    abort(f"the pre-fix classifier finds {_was_broken} unmatched, not the measured {KNOWN_BROKEN}. "
          f"Three things do this, in the order worth checking: (1) a register option was folded "
          f"into a TIERS phrase list — the cheap repair, and the one the promotion pins below exist "
          f"to refuse, since a phrase reaches text the form can never produce; (2) the register's "
          f"own options changed, in which case re-measure and update this list in the SAME edit; "
          f"(3) the embedded replay no longer matches what shipped. Under all three the checks "
          f"below would be ruling on a population this file cannot vouch for")
print(f"reach (1): the pre-fix classifier re-finds exactly {KNOWN_BROKEN} unmatched — the defect this "
      f"gate is about is reproducible\n")


# --- the rule ------------------------------------------------------------------------------------
TABLE = comp_tier.REGISTER_SOURCES
normalised = {comp_tier._exact(o): o for o in OPTIONS}

check("every key in REGISTER_SOURCES is already in `_exact` normal form",
      all(k == comp_tier._exact(k) for k in TABLE),
      f"a key the lookup can never hit is a silent no-op: "
      f"{[k for k in TABLE if k != comp_tier._exact(k)]}")

_uncovered = sorted(o for n, o in normalised.items() if n not in TABLE)
check("every declared `source` option has an entry in REGISTER_SOURCES",
      not _uncovered,
      f"{_uncovered} fall through to the free-text pass. Three of the four that did so before this "
      f"gate existed landed in the WEAKEST tier, which makes the band's own qualifier fire on an "
      f"ordinary source. Add the option to REGISTER_SOURCES with the tier it means")

_stale = sorted(k for k in TABLE if k not in normalised)
check("every entry in REGISTER_SOURCES names an option the register still declares",
      not _stale,
      f"{_stale} match nothing the form can produce. Asserted in this direction too because "
      f"containment is not equality: a renamed option leaves its old key behind, the count still "
      f"looks complete, and the renamed option is back in the weakest tier")

_bad_tier = sorted(f"{k}->{v}" for k, v in TABLE.items() if v not in comp_tier.TIERS)
check("every entry names a tier that exists", not _bad_tier, _bad_tier)

# Not a style point: a demotion is the direction that defeats this engine, so the gate says out loud
# that only ONE option may resolve to the weakest tier and names which.
_weakest = sorted(normalised[n] for n, v in TABLE.items()
                  if n in normalised and v == comp_tier.WEAKEST)
check("exactly one declared option maps to the weakest tier, and it is the register's own `Other`",
      _weakest == ["Other"],
      f"{_weakest} map to {comp_tier.WEAKEST!r}. `Other` means *no attribution was given*, which is "
      f"honestly the weakest tier. Any other option landing there is a source being told it is "
      f"unattributed when the register knows exactly where it came from")

# `matched` now means THE SOURCE WAS RECOGNISED, which is a different fact from "a phrase hit".
for o in OPTIONS:
    t = comp_tier.tier_of(o)
    check(f"  {o!r} classifies, and says so", t["matched"] is True and t["tier"] in comp_tier.TIERS,
          t)

# Free text must still work — the exact pass is additive, not a replacement.
for text, want in (("County recorder deed", "recorded_sale"), ("Verified with the buyer", "verified"),
                   ("Vendor estimate / AVM", "estimate"), ("Asking price on the MLS", "listing"),
                   ("Broker OM", "broker")):
    check(f"  free text {text!r} still reaches {want}", comp_tier.tier_of(text)["tier"] == want,
          comp_tier.tier_of(text))
check("  and unreadable free text is still the weakest tier, unmatched",
      comp_tier.tier_of("Bob said so") == {"tier": "unknown", "rank": 7, "label": "Unattributed",
                                           "matched": False},
      comp_tier.tier_of("Bob said so"))

# THE REASON IT IS AN EXACT TABLE. Adding `"owner"` to the `verified` phrase list — the obvious fix,
# and the one a reader will try next — promotes a listing to party-verified, and `"appraisal"` in
# `confirmed` promotes a broker package. Pinned so the cheap repair cannot be made quietly.
for text, want in (("listing agent for the owner", "listing"),
                   ("broker OM quoting an appraisal", "broker"),
                   ("owner is asking for this", "listing")):
    got = comp_tier.tier_of(text)["tier"]
    check(f"  {text!r} is NOT promoted by the register entries — still {want}", got == want,
          f"got {got!r}: the register option was folded into the substring list, which reaches text "
          f"the form can never produce")


# --- the behavioural half, with the mutation that makes it mean something -------------------------
def worst_tier_of_owner_band() -> str | None:
    """The band an `Owner`-sourced register actually produces. Separate function so it can be
    mutated directly — `test_unique_read_guard` shipped a self-test that asserted the analyser still
    *reported* a site, which a mutation routing every site to "safe" passed."""
    comps = [{"data": {"address": "1 A St", "price_psf": 300, "source": "Owner"}},
             {"data": {"address": "2 B St", "price_psf": 320, "source": "Owner"}}]
    return comp_tier.statistic(comps, "price_psf")["worst_tier"]


check("a band of Owner-sourced comps does not report itself unattributed",
      worst_tier_of_owner_band() == "verified",
      f"got {worst_tier_of_owner_band()!r} — the band carries 'Strengthen that source before the "
      f"number carries a decision' about two comps confirmed by a principal")

_saved = comp_tier.REGISTER_SOURCES
_real = worst_tier_of_owner_band()
try:
    comp_tier.REGISTER_SOURCES = {}
    _mutated = worst_tier_of_owner_band()
finally:
    comp_tier.REGISTER_SOURCES = _saved

# The claim is DIFFERENCE, not the mutated value. The first draft asserted `_mutated == WEAKEST`,
# which is true of a `tier_of` that never consults the table at all — so the one mutation this arm
# exists to catch (`key = None` in place of the lookup) left it GREEN while the check above went
# red. *Asserting what the mutant returns is not asserting that the mutation changed anything*, and
# a reach arm that passes under its own target mutation is decoration beside a check that was
# already failing. Measured, not reasoned: the mutation was applied and this arm printed PASS.
check("reach (2): emptying REGISTER_SOURCES changes that band's verdict, so the check above is "
      "reading the table rather than agreeing with it by coincidence",
      _real != _mutated,
      f"the band reports {_real!r} with the table and {_mutated!r} without it — `tier_of` is not "
      f"consulting REGISTER_SOURCES, so every static check in this file is ruling on an inert table")
check("  ...and the table object is restored, so later tests in this process see the real one",
      comp_tier.REGISTER_SOURCES is _saved)

print()
if FAILED:
    print(f"comp_tier_sources: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"comp_tier_sources: all checks passed ({len(OPTIONS)} declared options, "
      f"{len(TABLE)} table entries, 0 exemptions)")
