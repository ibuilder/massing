"""Untrusted XML never reaches a bare ElementTree parse — and the one place it still could.

Found 2026-08-29 by a bandit run (B314, MEDIUM/high-confidence) during a hardening pass. The finding
that mattered was not either flagged line; it was that **the repository's posture here is good and
was held by nothing.** Three independent first-party paths already parse untrusted schedule XML
safely — `massingplan.core.mspdi` and `massingplan.core.p6xml` through `xmlsafe.parse`, and
`aec_data.schedule` through `defusedxml` — and not one assertion anywhere said a fourth had to.

**Why bare ElementTree is not acceptable on untrusted input, measured rather than recalled.** On
CPython 3.12.3, `xml.etree.ElementTree.fromstring` REFUSES an external entity (`undefined entity`,
so no `file:///` read) but happily EXPANDS internal ones: a five-level billion-laughs of ~250 bytes
became 100,000 characters in under 10 ms. Depth is free to the attacker and the growth is
exponential, so the ceiling is memory. `test_expansion_is_still_a_real_risk` below re-measures this
on every run rather than trusting this paragraph — if a future CPython hardens the default parser,
that check goes red and tells us the *reason* for the rule changed, which is the moment to revisit
it. A rule whose justification can silently stop being true is the kind this repo keeps rediscovering.

**The one unguarded parse in the tree is vendored, and deliberately not patched here.**
`src/massingcapture/probe/e57.py:parse_index` reads the E57 XML index with bare
`ElementTree.fromstring`. It is not reachable from the service: nothing in `aec_api` or `aec_data`
imports `massingcapture` at all, and the routed `aec_api/e57.py` is a different module that parses
no XML. Patching it was considered and rejected on two grounds that are recorded in the tree itself:
`VENDOR.md` pins the subset at upstream `1a31e1b` with **"Local deviations: NONE"**, and
`test_massingcapture_vendor.py` asserts the subset is **stdlib-only per file** — so neither
`defusedxml` (undeclared there) nor `massingplan.core.xmlsafe` (a reach into a package the vendor
must not depend on) can be imported from it. The real fix belongs upstream.

**So unreachability IS the control, and that is what is asserted here.** The day someone wires the
capture probes into a route, `test_the_vendored_probe_stays_unreachable` fails and puts the XML
question in front of that commit instead of leaving it to a later audit. That is the difference
between a known risk and a latent one.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_xml_parse_hardening.py
"""
from __future__ import annotations

import pathlib
import re
import sys
import time
from xml.etree import ElementTree

FAILED: list[str] = []
_HERE = pathlib.Path(__file__).parent


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


#: First-party source. `massingcapture` is excluded because it is a pinned verbatim vendor — see the
#: docstring; it gets its own assertion below rather than an exemption that quietly forgives it.
ROOTS = (_HERE / "src", _HERE / ".." / "data" / "src")
VENDOR = (_HERE / "src" / "massingcapture").resolve()

#: A call into the stdlib XML parser that does NOT go through a guard. Matches the attribute forms
#: actually used in this tree; `defusedxml`'s own `_DET.fromstring` is a different receiver and is
#: correctly not matched.
_BARE_PARSE = re.compile(r"\bElementTree\.(?:fromstring|parse)\s*\(")

#: The ONLY file allowed to call it: `xmlsafe.parse` is the guard's own implementation — it refuses
#: entity declarations first, then parses. An allowlist of one is a population, not a loophole; if
#: this ever needs a second entry, that entry is the thing to review.
ALLOWED = {"massingplan/core/xmlsafe.py"}


def _first_party_files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for root in ROOTS:
        if not root.exists():
            continue
        for f in root.rglob("*.py"):
            if VENDOR in f.resolve().parents:
                continue
            out.append(f)
    return sorted(out)


def _offenders(files) -> list[str]:
    hits = []
    for f in files:
        rel = f.resolve().as_posix()
        text = f.read_text(encoding="utf-8", errors="ignore")
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue                       # a comment ABOUT the hazard is not the hazard
            if _BARE_PARSE.search(line) and not any(rel.endswith(a) for a in ALLOWED):
                hits.append(f"{rel.split('/services/')[-1]}:{n}")
    return hits


files = _first_party_files()

# Silence is not a signal: an empty population satisfies every "no offender" assertion below.
check("first-party python is actually being read", len(files) > 100, f"{len(files)} files")
check("  and the vendored subset is excluded from it",
      not any(VENDOR in f.resolve().parents for f in files))

# --- THE RATCHET ---------------------------------------------------------------------------------
offenders = _offenders(files)
check("no first-party module parses XML with a bare ElementTree call",
      not offenders,
      "; ".join(offenders) + "  -> route it through massingplan.core.xmlsafe.parse (which refuses "
                             "entity declarations first) or defusedxml, as the three existing "
                             "schedule readers already do")

# --- self-test the reader: a clean bill of health from a blind scanner is worthless ---------------
_PLANT = "    root = ElementTree.fromstring(untrusted)\n"
_probe = _HERE / "src" / "aec_api" / "_xml_hardening_probe_tmp.py"
try:
    _probe.write_text("from xml.etree import ElementTree\n\n\ndef f(untrusted):\n" + _PLANT,
                      encoding="utf-8")
    planted = _offenders(_first_party_files())
    check("  the scanner FINDS a planted bare parse (proves it can see one at all)",
          any("_xml_hardening_probe_tmp" in h for h in planted), str(planted[:3]))
finally:
    _probe.unlink(missing_ok=True)
check("  and the planted file is cleaned up", not _probe.exists())

# --- the justification, re-measured rather than recalled ------------------------------------------
_BOMB = """<?xml version="1.0"?><!DOCTYPE r [
<!ENTITY a "AAAAAAAAAA"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;"><!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">
<!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;">]><r>&e;</r>"""

_started = time.time()
try:
    _grew = len(ElementTree.fromstring(_BOMB).text or "")
except Exception:                                            # noqa: BLE001 — a refusal is the news
    _grew = 0
check("bare ElementTree still EXPANDS internal entities, so the rule above still has a reason",
      _grew >= 10_000,
      f"{_grew:,} chars from {len(_BOMB)} bytes in {(time.time() - _started) * 1000:.0f} ms"
      if _grew else "REFUSED — CPython changed; re-read whether this file's rule is still needed")

sys.path.insert(0, str((_HERE / "src").resolve()))
from massingplan.core import xmlsafe  # noqa: E402

try:
    xmlsafe.parse(_BOMB)
    _refused = False
except ValueError:
    _refused = True
check("  and the guard we route through REFUSES that same document", _refused)
check("  while still parsing an ordinary one",
      xmlsafe.parse("<r><a>1</a></r>").find("a") is not None)

# --- the vendored probe: unreachable is the control, so assert the unreachability ------------------
_imports_vendor = [
    f"{f.resolve().as_posix().split('/services/')[-1]}"
    for f in files
    if re.search(r"^\s*(?:import|from)\s+massingcapture\b",
                 f.read_text(encoding="utf-8", errors="ignore"), re.M)
]
check("the vendored capture probes stay unreachable from first-party source",
      not _imports_vendor,
      "; ".join(_imports_vendor) + "  -> massingcapture/probe/e57.py parses the E57 XML index with "
                                   "a bare ElementTree call. Wiring it means answering the XML "
                                   "question first: sanitise at the caller, or fix it upstream and "
                                   "re-sync the vendor. Do NOT patch the vendored file in place — "
                                   "VENDOR.md records 'Local deviations: NONE'.")

print()
if FAILED:
    print(f"xml_parse_hardening: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"xml_parse_hardening: all checks passed ({len(files)} first-party files scanned, "
      f"{len(ALLOWED)} allowlisted guard implementation)")
