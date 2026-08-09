"""
A size budget on the files that are edited most.

This exists because of a question the user asked on 2026-07-28: is this codebase heading somewhere it
can no longer be worked on? The honest answer needed a measurement rather than a reassurance, and the
measurement found one file:

    api/client.ts   4,956 lines   152 commits/14d   631 methods on one class

Length alone is not the problem — `schema.d.ts` is 32k lines and nobody suffers, because it is
generated and nobody reads it. The problem is **length x churn**: a file that must be opened to add
any endpoint, is opened ~11 times a day, and only ever grows. Every change to it competes with every
other change for the same window of attention.

So the budget is not "files should be small". It is: **the files we edit constantly must stay small
enough to hold in your head at once.** Generated files and vendored copies are exempt by name, not by
size, because exemption-by-size is how a budget dies.

The threshold is deliberately set ABOVE today's worst offender. This test is a ratchet that stops the
problem getting worse while SCALE-SEAM brings it down; tightening the number is part of that work.
Setting it below the current state would have shipped a red test, and a red test that everyone learns
to ignore protects nothing.
"""
import os
import subprocess
import sys

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: Hand-written source we own. A file over this is a file nobody can review in one sitting.
CEILING = 5_200

#: Per-file ceilings for the files SCALE-SEAM is actively splitting. **Only ever revised DOWN.**
#:
#: WHY THIS EXISTS, and it is a correction to how the ratchet was understood. `CEILING` above is a
#: single GLOBAL number, so it is pinned by whichever file is worst — today `viewer/app.ts` at 5,106
#: (5,064 when this was written; AUTH-SNAP-OVERRIDE added 42 lines the same day, which is exactly how
#: a number embedded in prose goes stale — the assertion below reads the file, this sentence does not).
#: That means an extraction out of any OTHER file cannot move it: SCALE-SEAM ⑦ took 96 lines out of
#: `client.ts` and the global ceiling was as true at 5,200 afterwards as before. The instruction
#: "lower the ceiling as each extraction lands" is right about the intent and cannot be carried out
#: by this number — lowering it to that figure would ratchet a slack belonging to `viewer/app.ts`, a file
#: in a different lane, and leave it with zero headroom so the next edit there fails the build.
#:
#: **A ratchet has to be per-subject when the work is per-subject.** One global number measures the
#: worst file and is silent about every other, which is the same shape as a gate whose scope is
#: narrower than its claim.
#:
#: A new endpoint added straight to `client.ts` will fail this, and that friction is the point rather
#: 2026-08-07: raised by ONE line, and the exception is stated rather than quietly taken. The
#: line is `import { withRoutines } from "./routines";` — the *mechanism* of an extraction,
#: not an endpoint. The endpoint itself went into `api/routines.ts`, which is what this ratchet
#: asks for. A mixin cannot be composed without one import line, so a file sitting exactly on
#: its pin can never gain one otherwise. If this climbs again for the same reason, the pin is
#: measuring the wrong thing and should count endpoints.
#: than a side effect: the question it forces is "should this live in a domain module instead?", and
#: post-⑦ the answer is usually yes. Raising an entry is therefore a deliberate act that should be
#: argued for in the commit message — the direction of travel is down.
PER_FILE = {
    #: ⑨ contracts/scope-library/esign -> contracts.ts. This entry had ZERO headroom — the file
    #: measured exactly its 3,780 cap and the check is `measured > cap`, so a single added line
    #: failed the build. Three lanes hit that wall the same day; two routed their new methods into
    #: other modules and one got a field in only by appending to an existing line. That is the
    #: friction this ratchet is for, and it asked the intended question — the contract documents had
    #: a whole domain to leave with, so the number goes DOWN by 32 instead of up by one.
    "apps/web/src/api/client.ts": 3_703,   # + cost group -> cost.ts;   # +1 = the withRoutines IMPORT, not an endpoint:   # ⑨ contracts -> contracts.ts; ⑧ 3,796; ⑦ 3,871; before ⑦ 3,967   # + ⑩ finance -> finance.ts (both extractions are in the merged file)
    #: R39-DECOMP-VIEWER. Pinned at its CURRENT size before any extraction, deliberately.
    #:
    #: `app.ts` had no per-file entry, so it lived under the 5,200 global — which it also *set*, being
    #: the worst file. That is a ceiling it cannot ratchet against: every extraction from any other
    #: file left the global exactly as true as before, and every feature added here drifted it up
    #: with nothing to notice. Two Lane E features in a row had to route logic into new modules to
    #: fit under it, which is a good outcome reached by an accidental mechanism.
    #:
    #: Pinned BEFORE the split rather than after, so the number the extraction has to beat is the
    #: unimproved one. Pinning afterwards would freeze the improved figure and lose the evidence that
    #: it moved — the history in the line above (3,967 → 3,871 → 3,796) is the thing worth having.
    #: R39-DECOMP-VIEWER, one entry per slice so the movement is the record:
    #:   ① Exports (51)   5,160 -> 5,114
    #:   ② clash/QA (851) 5,114 -> 4,272
    #:   ③ analyse (238) + ④ authoring (91)  4,272 -> 3,953
    #:   ⑤ project-browser panel (216)      3,953 -> 3,751
    #:   ⑥ loadProjectModel (37)            3,751 -> 3,715
    #: The whole `builders` map is now out of app.ts. Ratcheted each time, never reset.
    #:
    #: ⑥ is worth recording because the ratchet CAUSED it rather than merely permitting it.
    #: R39-VIEWER-OBS needed ~5 lines of instrumentation inside `loadProjectModel`, and this entry had
    #: zero headroom, so the choice was to raise the pin or move the routine. The comment above says
    #: the friction is the point and that the question it should force is "should this live in a
    #: domain module instead?" — for a self-contained fetch/parse/show sequence the answer was plainly
    #: yes. The instrumentation went into the new module and app.ts came DOWN 36 lines instead of up.
    #: 3_715 -> 3_717 (v0.3.916). RAISED, which the comment above says must be argued for, so:
    #: R36 slice 3 added one user-facing rail control ("Place this view on a sheet"). The extraction
    #: the ratchet asks for HAPPENED — `sheetSpecs.ts` is 133 lines of new logic that never entered
    #: this file, and it also absorbed the three inline `URLSearchParams` builders that were here
    #: (which were sending `number`/`title`/`scale`, none of which the route accepts). What is left is
    #: two lines of WIRING for a new button, and wiring is what this file is for. The alternative was
    #: to push DOM construction into `sheetSpecs.ts`, whose freedom from the DOM is exactly why its
    #: eleven tests need no browser — that would be trading a real property for a number.
    "apps/web/src/viewer/app.ts": 3_717,
    # Pinned at its EXACT measured size, not above it. qaSection.ts became the file every reach fix
    # lands in and reached 1,373 lines while unpinned - the same accumulation app.ts and client.ts
    # already have entries for. Pinned before it needs splitting rather than after: a ratchet added
    # at the point of pain only ratifies the pain.
    # 1_373 -> 1_360: the shared-parameter read + retire moved out to sharedParamsPanel.ts. The pin
    # fired on the commit that added the retire flow (1,439 > 1,373) and the answer was to extract,
    # not to raise - the same call the /finance extraction made earlier the same day. Re-tightened
    # to the new exact count rather than left at 1_373, because 13 lines of slack is 13 lines the
    # next addition spends without anyone deciding to.
    "apps/web/src/viewer/tools/qaSection.ts": 1_350,
    # Pinned at its EXACT measured size on 2026-08-09, BEFORE it needs splitting — the third-largest
    # hand-written file in the tree and the only one of that size with no ratchet. The qaSection entry
    # above records why the timing matters: "a ratchet added at the point of pain only ratifies the
    # pain." Nothing is wrong with this file today; that is precisely when the pin is free.
    "apps/web/src/portal/register/register.ts": 2_546,
}

#: Exempt because a human never reads them top-to-bottom. Name them, never infer them.
EXEMPT_SUBSTRINGS = (
    "/vendor/",           # vendored upstream copies — re-synced by overwrite, never hand-edited
    "schema.d.ts",        # generated from the OpenAPI schema
    "/node_modules/",
    "/dist/",
    "/.venv/",
    "package-lock.json",
    "demoData.json",      # a captured snapshot, regenerated by build_demo_data.py
    "/migrations/versions/",   # alembic autogenerate output; hand-editing one is already the bug
)


def tracked_source():
    """Files git knows about — not the working tree, so build output can never enter the budget."""
    out = subprocess.run(
        ["git", "ls-files", "*.py", "*.ts", "*.tsx", "*.js"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    for rel in out.stdout.splitlines():
        rel = rel.strip().replace("\\", "/")
        if not rel or any(s in "/" + rel for s in EXEMPT_SUBSTRINGS):
            continue
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                yield rel, sum(1 for _ in fh)
        except OSError:
            continue


sizes = sorted(tracked_source(), key=lambda kv: -kv[1])
check("the source tree is readable at all", len(sizes) > 100, f"{len(sizes)} files measured")

over = [(rel, n) for rel, n in sizes if n > CEILING]
check(
    f"no hand-written file exceeds {CEILING} lines",
    not over,
    "; ".join(f"{rel}={n}" for rel, n in over[:5]) or "",
)

measured = dict(sizes)

# A per-file ratchet keyed by PATH silently stops ratcheting the moment the path changes — a rename,
# a move, or an exemption that starts matching would drop the entry and this check would go green by
# measuring nothing. So assert the subjects are present BEFORE asserting their sizes, individually
# rather than in aggregate: an aggregate non-empty check cannot see a dead entry beside a live one.
missing = [rel for rel in PER_FILE if rel not in measured]
check(
    "every per-file ratchet still names a file that exists",
    not missing,
    "; ".join(missing) or f"{len(PER_FILE)} tracked",
)

grew = [(rel, measured[rel], cap) for rel, cap in PER_FILE.items()
        if rel in measured and measured[rel] > cap]
check(
    "no file under an extraction ratchet has grown",
    not grew,
    "; ".join(f"{rel}={n} > {cap}" for rel, n, cap in grew)
    or "; ".join(f"{rel}={measured[rel]}/{cap}" for rel, cap in PER_FILE.items() if rel in measured),
)

# The ratchet only ratchets if somebody can see the headroom. Print the top of the list every run so
# a file approaching the ceiling is visible BEFORE it crosses and blocks somebody mid-sprint.
print("\n  largest hand-written files:")
for rel, n in sizes[:8]:
    room = CEILING - n
    flag = "  <-- at the ceiling" if room < 400 else ""
    print(f"    {n:>6}  {rel}{flag}")

# A budget nobody can act on is decoration. If the worst file is over the *target*, say what to do —
# the seam is the fix, and the roadmap item that owns it is named so this points somewhere real.
TARGET = 3_000
worst_rel, worst_n = sizes[0]
if worst_n > TARGET:
    print(
        f"\n  NOTE: {worst_rel} is {worst_n} lines, over the {TARGET}-line target.\n"
        f"        Roadmap SCALE-SEAM owns bringing this down by splitting along domain seams.\n"
        f"        Lower CEILING here as each extraction lands — that is what makes it a ratchet."
    )

# --- the public demo snapshot: a BYTE ceiling, because lines are meaningless for captured JSON ----
# `demoData.json` was listed in EXEMPT_SUBSTRINGS above, which read as "deliberately unbounded" and
# was in fact decorative: `tracked_source()` globs *.py *.ts *.tsx *.js, so a .json file was never in
# the population the exemption excludes it from. NOTHING bounded this file's bytes.
#
# It matters because this is a SHIPPED PUBLIC SURFACE — every visitor to the Pages demo downloads it
# on a first impression, much of it on mobile. Widening the register fill loop in build_demo_data.py
# doubles the payload with no signal that anything changed.
#
# A ratchet, in the same spirit as CEILING and PER_FILE above — but deliberately a SEPARATE
# concept, not an entry in PER_FILE: those are LINE counts for hand-written source, this is
# BYTES for a captured artifact. Lines are meaningless for generated JSON. This number comes DOWN
# as the snapshot gets leaner
# and must never be raised to accommodate a bigger capture. If a change needs more bytes, the
# question to answer first is what a reader learns from them.
DEMO_SNAPSHOT = os.path.join(ROOT, "apps", "web", "src", "demo", "demoData.json")
DEMO_MAX_BYTES = 1_500_000
if os.path.exists(DEMO_SNAPSHOT):
    _demo_n = os.path.getsize(DEMO_SNAPSHOT)
    check(f"public demo snapshot is within {DEMO_MAX_BYTES:,} bytes",
          _demo_n <= DEMO_MAX_BYTES,
          f"{_demo_n:,} bytes — regenerate with a smaller `count=` in build_demo_data.py's register "
          f"fill loop rather than raising this ceiling")
    print(f"  demo snapshot: {_demo_n:,} bytes of {DEMO_MAX_BYTES:,} "
          f"({100 * _demo_n // DEMO_MAX_BYTES}% of ceiling)")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_file_sizes OK")
