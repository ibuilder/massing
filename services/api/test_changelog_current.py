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

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_changelog_current OK")
