"""R41-GATE-SUBSTANCE — a cited path that resolves may still say nothing.

WHY THIS EXISTS
    ``test_claude_md_gates.py`` asserts that every file the standing docs cite resolves to a tracked
    path. That is a real gate and this does not replace it. But resolving is a weak claim: **a path
    can resolve to a twelve-byte stub.** Truncate ``docs/roadmap.md`` to one line and every citation
    of it still passes, because the question asked was "does this name point at something?" and not
    "does the something still contain anything?".

    This asks the second question for the artefacts that carry real content.

WHY A FLOOR IS NOT A RATCHET, AND MUST NOT BE WRITTEN LIKE ONE
    ``test_file_sizes.py`` sets per-file CEILINGS at the exact current size, so any growth fails
    until someone lowers them deliberately. That is right for a ceiling: the direction of travel is
    down, and slack makes it decorative.

    **A floor is the mirror image and the same reasoning gives the opposite answer.** These artefacts
    legitimately LOSE content — the roadmap sheds items to ``roadmap-completed.md``, the README gets
    tightened, a demo corpus is regenerated smaller. A floor at the current value would fail on every
    honest deletion, and a gate that goes red when you do the right thing is one people switch off.

    So these floors sit clearly below today's values and far above a stub. They catch **truncation**,
    not shrinkage. If one ever fires, the question is "did something delete most of this file?", not
    "has this file been edited?". Raise a floor only when the artefact has grown a new *structural*
    part that must not disappear — never merely because the number went up.

WHAT IS MEASURED, AND WHY NOT BYTES ALONE
    Bytes alone are a poor proxy: a file of repeated whitespace passes. So each artefact is measured
    by the thing that makes it substantive — markdown by its **headings** as well as its size, and
    the two data catalogues by their **entry counts**, which is what a consumer actually reads.

    ``demoData.json`` is minified to a single line, so a line-count floor would read ZERO for a
    perfectly healthy 1.4 MB file. That is why this is its own gate rather than another map inside
    the line-count one: the unit that detects a stub differs per artefact.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: Artefacts whose emptiness would be silent. Each entry says how to tell "full" from "stub".
#:
#: ``min_bytes``     — floor on file size, well under today's value (see the module docstring).
#: ``min_headings``  — markdown only: lines starting ``#``. Whitespace cannot fake these.
#: ``json_list``     — a key holding the catalogue's entries; its length is the substance.
#: ``json_keys``     — the top-level mapping IS the catalogue; its key count is the substance.
SUBSTANCE: dict[str, dict[str, object]] = {
    # today: 226,431 bytes / 61 headings
    "docs/roadmap.md": {"min_bytes": 120_000, "min_headings": 35},
    # today: 23,971 / 18 — the standing directions; a stub here silently removes every rule
    "docs/roadmap-directions.md": {"min_bytes": 12_000, "min_headings": 10},
    # today: 30,399 / 14
    "README.md": {"min_bytes": 15_000, "min_headings": 8},
    # today: 5,887 / 9 — small on purpose, so the floor is proportionally close
    "CLAUDE.md": {"min_bytes": 3_500, "min_headings": 6},
    # today: 1,423 / 1 — the smallest listed artefact; it names our third-party licence obligations
    "LICENSE-NOTES.md": {"min_bytes": 900, "min_headings": 1},
    # today: 351,011 / 146 — the historical record; deliberately NOT citation-gated, so nothing else
    # would notice it emptying
    "docs/roadmap-completed.md": {"min_bytes": 150_000, "min_headings": 60},
    # today: packs = 57 entries — the family shelf catalogue
    "services/data/families/external/manifest.json": {"min_bytes": 100_000, "json_list": "packs", "min_entries": 35},
    # today: 1,249 endpoint keys, minified to ONE line — a line floor would read zero
    "apps/web/src/demo/demoData.json": {"min_bytes": 500_000, "json_keys": True, "min_entries": 800},
}


def tracked() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    return {line.strip().replace("\\", "/") for line in out.stdout.splitlines() if line.strip()}


TRACKED = tracked()
check("git ls-files returned a tree", len(TRACKED) > 100, f"{len(TRACKED)} files")

# Presence BEFORE measurement, per entry rather than in aggregate. A floor keyed by path stops
# measuring the moment the path changes, and an aggregate non-empty check cannot see one dead entry
# beside seven live ones — the same failure the per-file ceiling map was given this guard for.
missing = [p for p in SUBSTANCE if p not in TRACKED]
check(
    "every artefact named here is still a tracked path",
    not missing,
    "; ".join(missing) or f"{len(SUBSTANCE)} artefacts",
)

check(
    "the artefact list is not empty",
    len(SUBSTANCE) >= 5,
    f"{len(SUBSTANCE)} artefacts checked",
)

thin: list[str] = []
for rel, rule in SUBSTANCE.items():
    if rel not in TRACKED:
        continue
    path = os.path.join(ROOT, rel)
    size = os.path.getsize(path)
    min_bytes = int(rule["min_bytes"])  # type: ignore[arg-type]
    if size < min_bytes:
        thin.append(f"{rel}: {size:,} bytes < {min_bytes:,}")
        continue

    if "min_headings" in rule:
        with open(path, encoding="utf-8") as fh:
            headings = sum(1 for line in fh if line.startswith("#"))
        want = int(rule["min_headings"])  # type: ignore[arg-type]
        if headings < want:
            thin.append(f"{rel}: {headings} headings < {want}")
        continue

    if "json_list" in rule or "json_keys" in rule:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        entries = len(data) if "json_keys" in rule else len(data.get(str(rule["json_list"]), []))
        want = int(rule["min_entries"])  # type: ignore[arg-type]
        if entries < want:
            thin.append(f"{rel}: {entries} entries < {want}")

check(
    "no cited artefact has been reduced to a stub",
    not thin,
    "; ".join(thin) or f"all {len(SUBSTANCE)} carry content",
)

print(
    "\n  A citation gate proves a name POINTS somewhere. This proves the somewhere still SAYS\n"
    "  something. The floors catch truncation, not editing — they sit well below today's values\n"
    "  because these artefacts legitimately shed content, which is exactly why they are floors\n"
    "  rather than ratchets. Bytes alone would pass on repeated whitespace, so markdown is also\n"
    "  measured by headings and the catalogues by entry count."
)

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_doc_substance OK")
