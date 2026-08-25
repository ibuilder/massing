"""The shipped version must appear in CHANGELOG.md.

**This rule has now failed twice as prose.** Task #494 records a changelog lapse at v0.3.808. Then a
documentation audit on 2026-08-13 found the changelog had stopped at v0.3.881 and **fifty-two
releases had shipped without an entry**, twenty-two of them tagged. It was reconstructed from the
release commits, which in this repo carry real descriptions — but that reconstruction is explicitly
thinner than a contemporaneous entry, because the per-release reasoning was never written down and
inventing it later would have been worse than the gap.

CLAUDE.md's own instruction is the fix: *"If a rule matters, write it as a test — anything held only
as prose will drift."* A release discipline that depends on someone remembering is one that has
already been forgotten twice.

So: the version in `apps/web/package.json` — the number that actually ships — must be named in
`CHANGELOG.md`. The check fires at the moment it is cheap to fix, which is before the release, and
the entry it demands is the one written while the reasoning is still in someone's head.

**Deliberately narrow.** It asserts the CURRENT version only, not every historical tag. A gate that
demanded an entry for all 900-odd releases would fail forever on the reconstructed range and be
switched off within a day, which is the failure mode of a rule that is technically right and
operationally impossible.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PKG = ROOT / "apps" / "web" / "package.json"
LOG = ROOT / "CHANGELOG.md"

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


check("apps/web/package.json is readable", PKG.is_file(), str(PKG))
check("CHANGELOG.md is readable", LOG.is_file(), str(LOG))
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)

version = json.loads(PKG.read_text(encoding="utf-8"))["version"]
log = LOG.read_text(encoding="utf-8")

# Silence is not a signal: an empty or truncated changelog would satisfy a naive "not in" check in
# the wrong direction, and a mangled version string would make every comparison below meaningless.
check("the version parses as a release number", bool(re.fullmatch(r"\d+\.\d+\.\d+", version)),
      f"version={version!r}")
check("the changelog has real content", len(log) > 5000, f"{len(log)} bytes")

# The entry may name the version alone (`## v0.3.936 — …`) or inside a range (`## v0.3.934–936 —`),
# because this repo legitimately groups a day's releases into one section. Both count: what must not
# happen is a version shipping with no mention anywhere.
major_minor, patch = version.rsplit(".", 1)
explicit = f"v{version}" in log
in_range = bool(re.search(
    rf"v{re.escape(major_minor)}\.(\d+)\s*[–\-—]\s*(\d+)",
    log)) and any(
    int(a) <= int(patch) <= int(b)
    for a, b in re.findall(rf"v{re.escape(major_minor)}\.(\d+)\s*[–\-—]\s*(\d+)", log))

check(f"CHANGELOG.md covers the shipping version v{version}", explicit or in_range,
      "" if (explicit or in_range) else
      "add an entry before releasing. This has lapsed twice — once at v0.3.808 and once for "
      "FIFTY-TWO consecutive releases — which is why it is a test and not a note. Write it now, "
      "while the reasoning is still in your head; a reconstruction from commit messages is "
      "strictly worse and the repo already carries one.")

# The twin. Without it, the check above passes on a changelog that happens to contain the digits for
# an unrelated reason, and — more usefully — it proves the matcher can say NO at all.
#
# The sentinel is DERIVED from the shipping version rather than written as a literal, for two
# reasons. The weaker one: sharing the real `major.minor` prefix makes this a harder test, because it
# forces the matcher to discriminate *within* the namespace it actually operates in — a sentinel from
# some unrelated prefix would pass even if the patch comparison were broken entirely.
#
# The stronger one, learned the expensive way: the first version of this twin used a hardcoded
# `9.9.9`, and it FAILED the moment the release entry was written — because the changelog entry
# explaining the twin quoted the sentinel, so the gate matched its own documentation. That is the
# fourth time this repo has shipped a source-scanning check that reads the prose describing it. A
# sentinel nobody would ever type is one nobody can accidentally document.
absurd_patch = "99999"
absurd = f"{major_minor}.{absurd_patch}"
absurd_hit = f"v{absurd}" in log or any(
    int(a) <= int(absurd_patch) <= int(b)
    for a, b in re.findall(rf"v{re.escape(major_minor)}\.(\d+)\s*[–\-—]\s*(\d+)", log))
check("...and the matcher rejects a version that was never released", not absurd_hit,
      f"v{absurd} appears to match, so the check above proves nothing" if absurd_hit
      else f"sentinel v{absurd} correctly absent")

# ---- the changelog's STRUCTURE, not just its coverage -------------------------------------------
#
# Added 2026-08-25 after an audit found **four orphan release headers** in this file: a `## vX.Y.Z`
# line sitting directly on top of another `## vX.Y.Z` line, with one body between the two of them.
#
#     ## v0.3.1038 (2026-08-20) - `/ai` leaves client.ts     <- no body of its own
#     ## v0.3.1026 (2026-08-20) - `/ai` leaves client.ts     <- the entry
#
# The cause is already written down in `docs/roadmap.md`, about a different file: *"If you are
# editing this file with a script, replace between the section markers - never splice at a matched
# string."* That lesson was learned when scripted edits INSERTED a NOW section instead of replacing
# one, three times over. The same splice then happened here, during the v0.3.1019 nineteen-branch
# integration that renumbered colliding releases - and nothing failed, because the check above asks
# only whether the CURRENT version appears somewhere in the text.
#
# **A lesson recorded as prose about one file does not protect the file next to it.** So the rule
# moves from that paragraph into this gate, where it applies to the structure rather than to whoever
# remembers reading the paragraph.
#
# Three shapes, because the splice produced three distinguishable defects:
HEADERS = [
    (i, m.group(0), tuple(int(x) for x in m.groups()), line.split("\u2014", 1)[-1].strip())
    for i, line in enumerate(log.split("\n"))
    if (m := re.match(r"## v(\d+)\.(\d+)\.(\d+) ", line))
]

# Anti-vacuity FIRST, same argument as `roadmapLanes.test.ts`: every check below is a statement about
# a population, and a population of zero satisfies all of them. If the header format ever changes,
# this is the line that says so instead of three silent OKs.
check("the release headers parse", len(HEADERS) > 900, f"{len(HEADERS)} headers found")

# 1. ORPHANS - a header whose next line is another header. This is the splice's own fingerprint, and
#    the only one of the three that names the mechanism rather than a symptom.
_lines = log.split("\n")
orphans = [h for i, h, _v, _t in HEADERS
           if i + 1 < len(_lines) and re.match(r"## v\d+\.\d+\.\d+ ", _lines[i + 1])]
check("no release header is immediately followed by another release header", not orphans,
      "" if not orphans else
      f"{len(orphans)} orphan header(s), first: {orphans[0]!r}. A header with no body under it is a "
      "splice that inserted where it should have replaced. Delete the stray line - do not give it a "
      "body, and do not renumber a neighbour to make the pair look intentional.")

# 2. ORDER - newest first, and non-increasing rather than strictly decreasing, because v0.3.1019 is
#    genuinely held by two entries (below).
disorder = [(HEADERS[i][1], HEADERS[i - 1][1])
            for i in range(1, len(HEADERS)) if HEADERS[i][2] > HEADERS[i - 1][2]]
check("release headers run newest-first", not disorder,
      "" if not disorder else
      f"{len(disorder)} out of order, first: {disorder[0][0]!r} sits below {disorder[0][1]!r}")

# 3. The SAME entry twice - one version AND one title appearing at two places. Distinct from (1):
#    an orphan is adjacent and bodiless, this is a whole duplicated section anywhere in the file.
_seen: dict[tuple, str] = {}
repeats = []
for _i, _h, _v, _t in HEADERS:
    if (_v, _t) in _seen:
        repeats.append(_h)
    _seen[(_v, _t)] = _h
check("no release entry appears twice", not repeats,
      "" if not repeats else f"{len(repeats)} duplicated, first: {repeats[0]!r}")

# 4. A DOWN-ONLY ratchet on version reuse. Two commits really did both bump to v0.3.1019 - the
#    integration pass and the `/drawing-set` seam - so the collision is history, not a typo, and
#    renumbering a shipped release to tidy the list would be inventing a version that never shipped.
#    It is pinned by exact count instead: a NEW collision fails, and fixing this one fails too,
#    telling you to lower the number. A ratchet allowed to sag is an allowlist in disguise.
_versions = [v for _i, _h, v, _t in HEADERS]
reused = sorted({v for v in _versions if _versions.count(v) > 1}, reverse=True)
check("version reuse stays at the one known historical collision", reused == [(0, 3, 1019)],
      f"reused={['v%d.%d.%d' % v for v in reused]}; expected exactly ['v0.3.1019']. If you removed "
      "the collision, tighten this to [] rather than widening it.")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_changelog_current OK")
