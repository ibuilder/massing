"""An item marked OPEN whose own gate reports DONE fails the build.

**This roadmap's most persistent defect is a status line, not a bug.** Its own history says so
repeatedly — "two whole bands read as open and were entirely finished" (2026-08-28), the five stale
status lines counted in the SCALE-SEAM ring, "A pull request is the one staleness clock in this file
with a real timestamp on it, and nothing consulted it." A premise-check on 2026-08-29 found four more
in one pass, including **Band 2's ⭐ — the file's own highest-value marker — pointing at an item whose
closing line already read "R46 IS COMPLETE".**

**Two neighbours already exist, and this is deliberately neither of them.**

* `roadmapLanes.test.ts` checks that every open item is in a lane — bookkeeping *between two lists*,
  neither of which measures anything.
* `roadmapStale.test.ts` is much closer: *"an item the roadmap calls OPEN must not already be
  implemented."* But it works from a **self-declaration** — it looks for a module announcing itself as
  that item's implementation. That catches an item whose work lives in one identifiable place, and it
  is why it did not catch R46 or R37-TRIAGE: neither is implemented BY a module. R46 is a count over a
  vendored package's reachability closure; R37-TRIAGE is a count of unreferenced public functions
  across the whole service. Nothing declares itself as either, so a declaration-based check is blind
  to both by construction — and both sat stale for two weeks with that gate green.

This one asks a third question: **does the item's own gate report the work done?** A measurement, not
a declaration and not a cross-reference. For the items that HAVE a measurement. Each entry pairs a roadmap item code with a
predicate that returns True when the thing the item asks for is done. If the roadmap still marks that
code open, this fails and names it. The predicates call the real gates — the same functions that
answer the question for a human — so the check cannot drift from what those gates report.

**Deliberately small, and it grows only when a measurement exists.** Most items are prose about
product decisions and cannot be measured; inventing a predicate for those would produce a check that
is either vacuous or wrong, which is the failure this file exists to catch. Two items qualify today.
A third that is genuinely open (SCALE-SEAM ㉘) is included as a NEGATIVE control: it asserts the gate
can still say "open", so a bug that made every predicate return False would not pass silently.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
ROADMAP = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + label + (("   " + detail) if detail else ""))
    if not ok:
        FAILED.append(label)


def marked_open(code: str) -> bool:
    """Whether `code` still heads a bullet the roadmap counts as open.

    Mirrors `roadmapLanes.test.ts`: a bullet carrying ✅ is shipped-but-not-yet-archived and is not
    work anyone can pick up. Matched on the item's own heading line, not on every mention — the codes
    are referenced all over the file in prose and in the lane table.
    """
    pat = re.compile(rf"^\s*[-*] (?:(?:✅|◧|🟡|⭐)️? )*\*\*{re.escape(code)}\b", re.M)
    return any("✅" not in m.group(0) for m in pat.finditer(ROADMAP))


def _gate_says(script: str, needle: str) -> bool:
    """Run one of this suite's own gates and look for `needle` in what it printed.

    Running it rather than importing: these gates do their work at import time and print a verdict,
    and the verdict line is the contract a human reads. Asserting on the same line means this file
    and a person reading the gate cannot disagree.
    """
    r = subprocess.run([sys.executable, str(HERE / script)], capture_output=True, text=True,
                       env={**__import__("os").environ,
                            "PYTHONPATH": f"{HERE / 'src'}{__import__('os').pathsep}{HERE.parent / 'data' / 'src'}"})
    return r.returncode == 0 and needle in (r.stdout + r.stderr)


#: code -> (predicate that is True when the item's work is DONE, what the predicate reads)
DONE_WHEN = {
    "R46": (lambda: _gate_says("test_vendor_reachable.py", "0 unreached"),
            "test_vendor_reachable reports 0 unreached vendored modules"),
    "R37-TRIAGE": (lambda: _gate_says("test_dead_code_population.py", "0 unreferenced"),
                   "test_dead_code_population reports 0 unreferenced public functions"),
}

#: Genuinely open, with a measurement that should say so. The negative control: without it, a bug
#: that made every predicate return False would leave this file green and useless.
OPEN_WHEN = {
    #: Was `client.ts` line count > 1200 until SCALE-SEAM (85). That is a PROXY for "the split is
    #: unfinished", and a proxy with a threshold decays: every slice moves the file down, and (85)
    #: took it to 1,173 and broke this control without anything being wrong. Lowering the number
    #: each time would be adjusting the check until it passes — the move this whole item exists to
    #: distrust — and it would need doing again within two slices.
    #:
    #: The direct measurement is whether anything is still UNFILED. `client.ts` carries a map of
    #: the methods that have no home yet, derived and checked by
    #: `apps/web/src/api/unfiledMap.test.ts`. While that banner exists, the split is unfinished by
    #: definition; when the last cluster is placed the banner is deleted, and at that moment this
    #: predicate goes False and correctly demands the roadmap close SCALE-SEAM. So it is both the
    #: negative control this file needs AND a real staleness check, rather than a number to chase.
    "SCALE-SEAM": (lambda: "--- UNFILED —" in (ROOT / "apps/web/src/api/client.ts").read_text(),
                   "client.ts still carries an UNFILED map, so the split is unfinished"),
}

check("the roadmap parsed and the codes are findable — else every check below is vacuous",
      len(ROADMAP) > 50_000 and "SCALE-SEAM" in ROADMAP, f"{len(ROADMAP)} chars")

for code, (done, what) in DONE_WHEN.items():
    if not marked_open(code):
        check(f"{code} is closed in the roadmap and its gate agrees", True, what)
        continue
    check(f"{code} is marked OPEN but its gate says the work is done", not done(),
          f"{what} — close the entry, or the ranking sends a reader at finished work")

for code, (still_open, what) in OPEN_WHEN.items():
    check(f"{code} is open and its measurement still says so", still_open(),
          f"{what} (negative control: proves a False predicate is not how this passes)")

print(("ROADMAP-STATUS OK — every item with a measurement agrees with its marker. "
       "The four found by hand on 2026-08-29 (R46, R37-TRIAGE, R37-TESTED-UNWIRED, QTO-TRADE) are "
       "corrected; the two that HAVE a gate are now held by it.")
      if not FAILED else f"roadmap_status: {len(FAILED)} FAILED — {FAILED}")
sys.exit(1 if FAILED else 0)
