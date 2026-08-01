"""Public docs name competitor products for INTEROP, never for COMPARISON.

The standing directive: no competitor product names in README / CHANGELOG / docs. The repo is
public, so every one of these files is a shipped surface. But the directive has an edge that a blunt
"ban the word" gate gets wrong, and getting it wrong is worse than the violation — it would delete
things the product genuinely does:

  ALLOWED (interop — the name is load-bearing, it identifies a real integration)
    * "Sign in with Autodesk / Procore / Google / Microsoft"  — SSO providers
    * "Navisworks XML import", the `smart:` namespace `<clashresult>` export — a file FORMAT we read
    * "Navisworks, Solibri, BIMcollab, usBIM — connect and sync issues" — connectors
    * Autodesk APS / Model Derivative — a real, paid RVT->IFC bridge

  BANNED (comparative — the name is decoration, standing in for a capability we could just name)
    * "Bluebeam-parity markup"            -> "PDF markup parity"
    * "the Bluebeam Tool Chest idea"      -> "a reusable tool set"
    * "the Navisworks / Bluebeam 'search set' pattern" -> "the saved-search-set pattern"

Seven comparative mentions of one product accumulated before anyone noticed, which is the whole
argument for this file: **the directive existed only as prose, and prose has no way to fail.**

Three checks, because the failure has three shapes:

  1. HARD BAN on names with no interop role here. Zero tolerance, no baseline — there is no
     legitimate sentence in this repo containing them.

  2. A RATCHET on comparative PHRASING around names that DO have an interop role. The shape is the
     signal, not the name: `X-style`, `X-parity`, `the way X does it`. 29 such uses predate this
     gate (mostly `Revit-style`, several in version HEADINGS and commit subjects, where a rewrite
     would rename shipped releases) so they are grandfathered by exact count. The count may only go
     DOWN. A new phrase fails; a lower count also fails, telling you to tighten the number — a
     ratchet that is allowed to sag is an allowlist wearing a ratchet's clothes.

  3. The INVERSE: the allowed interop mentions must still EXIST. Without this, the cheapest way to
     make checks 1-2 green is to delete the SSO buttons and the clash-import docs from the README,
     and the suite would applaud. This is the mutation check on the gate itself.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_no_comparative_names.py
"""
import collections
import os
import re
import subprocess

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

# README + CHANGELOG + EVERY doc. `docs/` is the Pages web root — it is copied wholesale to the
# public site — so scoping this gate to a hand-listed file or three would be the same mistake it
# exists to catch. The first version of this file did exactly that and missed four hard-ban hits in
# docs/esign-options.md and docs/deploy.md.
FILES = ["README.md", "CHANGELOG.md"]
for _root, _dirs, _names in os.walk(os.path.join(_ROOT, "docs")):
    for _n in sorted(_names):
        if _n.endswith((".md", ".html")):
            FILES.append(os.path.relpath(os.path.join(_root, _n), _ROOT).replace(os.sep, "/"))

# A discovery walk that silently returns nothing turns this whole gate into a no-op that prints OK.
assert len(FILES) > 50, f"only found {len(FILES)} docs — the discovery walk is broken, not the docs"
assert "docs/roadmap.md" in FILES, "docs/roadmap.md not discovered — the walk is not reaching docs/"

TEXT = {}
for rel in FILES:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        TEXT[rel] = fh.read()
assert len(TEXT["README.md"]) > 2000, "README.md is suspiciously short — did it move?"
assert len(TEXT["CHANGELOG.md"]) > 2000, "CHANGELOG.md is suspiciously short — did it move?"

# The HARD BAN (check 1) runs wider than the ratchet: every TRACKED markdown/html file in a public
# repo, not just the docs surface. Scoping it to docs/ would have missed the one in
# apps/web/src-tauri/README.md. `git ls-files` rather than a walk, so the population is exactly what
# a stranger cloning the repo receives — untracked scratch files are not published and not our
# problem (see the sample-fixture lesson: if a test reads a repo path, check it is in the archive).
_tracked = subprocess.run(
    ["git", "ls-files", "*.md", "*.html"],
    cwd=_ROOT, capture_output=True, text=True, check=True,
).stdout.split()
assert len(_tracked) > 60, f"git ls-files returned only {len(_tracked)} docs — the scan is broken"

# ---- 1. hard ban -------------------------------------------------------------------------------
# Names with no connector, no import format, no SSO provider and no paid bridge in this product.
# `revu` is separate from `bluebeam` on purpose: the product has been referred to by either half.
BANNED = ("bluebeam", "revu")

_banned_hits = []
for rel in _tracked:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        body = fh.read()
    for i, ln in enumerate(body.splitlines(), 1):
        for name in BANNED:
            if re.search(rf"\b{name}\b", ln, re.I):
                _banned_hits.append(f"{rel}:{i}: {ln.strip()[:100]}")
                break

assert not _banned_hits, (
    "a hard-banned product name appears in a tracked doc. It has no connector, import format, SSO "
    "role or paid bridge here, so every use is comparative — rewrite it as the capability itself "
    "(e.g. 'a PDF markup/manipulation stack'):\n  " + "\n  ".join(_banned_hits)
)

# ---- 2. comparative-phrasing ratchet ------------------------------------------------------------
# Names that ARE legitimate as connectors / formats / SSO / bridges — banned only in a comparative
# construction. Matching the CONSTRUCTION rather than the name is what lets check 3 coexist.
INTEROP_NAMES = (
    r"(?:navisworks|solibri|bimcollab|usbim|revit|revizto|archicad|tekla|procore|sketchup"
    r"|rhino|vectorworks|allplan|bentley|trimble|plangrid|speckle|autodesk)"
)
COMPARATIVE = (
    # "Revit-style", "Bluebeam-parity", "Navisworks-like"
    re.compile(INTEROP_NAMES + r"[a-z]*[-‑ ](?:style|parity|like|esque)", re.I),
    # "the way Revit does it", "beats Navisworks", "unlike Solibri"
    re.compile(
        r"(?:like|unlike|than|beats|versus|vs\.?|compared to|the way|how|similar to)\s+"
        + INTEROP_NAMES,
        re.I,
    ),
)

# Grandfathered as of 2026-07-31. DOWN ONLY. Do not add a key to make a new entry pass — rewrite the
# entry instead; that is the point of the file.
BASELINE = {
    "navisworks-style": 1,
    "procore parity": 1,
    "procore-style": 1,
    "revit-parity": 1,
    "revit-style": 14,
    "sketchup-style": 5,
    "solibri-style": 1,
    "the way navisworks": 2,
    "the way revit": 2,
    "vs revit": 1,
}

found = collections.Counter()
for text in TEXT.values():
    for pat in COMPARATIVE:
        for m in pat.findall(text):
            found[" ".join(m.lower().split())] += 1

new = sorted(set(found) - set(BASELINE))
assert not new, (
    "new comparative use of a competitor product name in a public doc: "
    + ", ".join(repr(k) for k in new)
    + ". Name the capability, not the product — e.g. 'Revit-style shortcuts' -> '2-letter draw-tool "
    "shortcuts'. These names are allowed ONLY for connectors, import formats, SSO providers and the "
    "paid Autodesk APS bridge."
)

grew = {k: (found[k], n) for k, n in BASELINE.items() if found[k] > n}
assert not grew, "comparative uses INCREASED (found, baseline): " + repr(grew)

shrank = {k: (found[k], n) for k, n in BASELINE.items() if found[k] < n}
assert not shrank, (
    "comparative uses were removed — good; now tighten BASELINE in this file so the ratchet cannot "
    "sag back. (found, baseline): " + repr(shrank)
)

# ---- 3. the inverse: interop mentions must survive ----------------------------------------------
# Deleting these would make checks 1-2 greener. They are the product, not a violation.
REQUIRED = (
    ("README.md", "Google / Microsoft / Procore", "the SSO provider list"),
    ("README.md", "Autodesk APS", "the paid RVT->IFC bridge"),
    ("CHANGELOG.md", "Navisworks XML", "the native clash-report import format"),
    ("CHANGELOG.md", "clashresult", "the `smart:` namespace export we parse"),
    ("CHANGELOG.md", "Navisworks, Solibri, BIMcollab, usBIM", "the issue-sync connector list"),
    ("CHANGELOG.md", "Autodesk APS", "the paid conversion bridge, in Settings > Integrations"),
)
for rel, phrase, why in REQUIRED:
    assert phrase in TEXT[rel], (
        f"{rel} no longer contains {phrase!r} ({why}). Interop names are ALLOWED — this gate bans "
        "comparative uses only. Do not blanket-remove competitor names to make it pass."
    )

print(
    f"NO COMPARATIVE NAMES OK - {len(_tracked)} tracked docs scanned for the hard ban, "
    f"{len(FILES)} public docs (README + CHANGELOG + all of docs/) read from disk for the ratchet. "
    f"{len(BANNED)} names hard-banned (no interop role, zero tolerance); comparative PHRASING "
    f"({sum(found.values())} grandfathered uses across {len(BASELINE)} phrases) ratcheted DOWN-ONLY, "
    "so a new 'X-style' or 'the way X does it' fails and a removal forces the baseline to tighten; "
    f"and {len(REQUIRED)} legitimate interop mentions (SSO providers, the Navisworks XML clash "
    "format, the connector list, Autodesk APS) asserted PRESENT so the gate cannot be satisfied by "
    "deleting the integrations it exists to protect."
)
