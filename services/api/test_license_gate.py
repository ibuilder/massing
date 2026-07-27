"""SEC-SUPPLY gate — the no-GPL/AGPL rule is enforced by a build, not by review.

"MIT/BSD/Apache only, no GPL/AGPL" is one of this project's standing constraints, and until now it
was held by prose and by whoever remembered to check a new dependency's licence. `supply_chain`
already had the classifier and the audit — with its own suite and **nothing invoking it**, which is
the same shape as `money`: a mechanism written to enforce something, enforcing nothing.

This is that mechanism wired to a gate. A dependency whose metadata declares GPL or AGPL now fails
the suite, on the run that introduces it, naming the package.

Weak copyleft (LGPL/MPL) is REPORTED, not failed — `ifcopenshell` and `certifi` sit there and are
accepted for our distribution model. Collapsing "disallowed" into "worth a look" would make the gate
either useless or permanently red, and a permanently red gate gets switched off.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_license_gate.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_license_gate.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_license_gate")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import supply_chain  # noqa: E402

AUDIT = supply_chain.license_audit()

# What binds our licensing is what we SHIP, not what happens to sit in a developer's venv. Gating on
# "everything installed" makes the result depend on whose machine ran it and goes permanently red the
# first time anyone runs `pip install ezdxf[draw]` — and a permanently red gate gets switched off,
# which is worse than no gate. So the hard failure is scoped to the DECLARED runtime set, and
# everything else is reported.
_HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME_REQS = [os.path.join(_HERE, "..", "data", "requirements.txt")]
DEV_ONLY = {"pyinstaller", "pyinstaller-hooks-contrib"}   # build the desktop binary; never shipped inside it

# Strong copyleft that IS in the shipped closure and has not been ruled on. Listed, dated and
# reasoned rather than quietly permitted: an allowlist without a reason is how a constraint stops
# being one. These are NOT approved — they are known, and the decision belongs to the project owner.
AWAITING_DECISION = {
    "bcf-client": (
        "2026-07-27 — GPLv3, an unconditional requirement of `ifctester`. INVESTIGATED: we do not need "
        "it. `ifctester` itself is LGPLv3 (same as ifcopenshell, already accepted), we import only "
        "`ifctester.ids`, and importing that loads ZERO bcf modules — bcf-client backs ifctester's BCF "
        "*reporter*, which we never call. Our own BCF handling is `bcf_io.py`. RECOMMENDED: exclude it "
        "from the distributed artifact (PyInstaller `--exclude-module`, or uninstall after pip in the "
        "image) rather than ship GPLv3 we never execute. `test_first_party_never_imports_bcf_client` "
        "below holds the 'never executed' half; the packaging half is a build change awaiting the "
        "owner's call."
    ),
    "odfpy": (
        "2026-07-27 — same route (unconditional requirement of `ifctester`). Classified copyleft from "
        "its metadata, which declares no explicit License field — the classifier read a classifier "
        "line. Worth confirming the actual licence before treating it as a finding."
    ),
}
BANNED_IMPORTS = ("fitz", "pymupdf")                       # PyMuPDF is AGPL — see docs/pdf stack notes


def _declared() -> set[str]:
    names: set[str] = set()
    for path in RUNTIME_REQS:
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            for sep in ("==", ">=", "<=", "~=", ">", "<", "["):
                line = line.split(sep)[0]
            names.add(line.strip().lower())
    return names


DECLARED = _declared()


def _closure() -> set[str]:
    """Declared runtime deps AND everything they require, transitively.

    The first version of this gate checked declared names only, and would have missed the one real
    finding in this repo: GPLv3 arriving as an unconditional requirement of a permissive dependency.
    What binds a distribution is the whole closure it ships, not the names someone typed.
    """
    import importlib.metadata as im
    reqs: dict[str, list[str]] = {}
    for d in im.distributions():
        n = (d.metadata.get("Name") or "").strip().lower()
        if n:
            reqs[n] = [r for r in (d.requires or []) if "extra ==" not in r]
    seen, stack = set(), list(DECLARED)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for r in reqs.get(name, []):
            dep = r.split(";")[0].strip()
            for sep in ("==", ">=", "<=", "~=", ">", "<", "[", " "):
                dep = dep.split(sep)[0]
            dep = dep.strip().lower()
            if dep and dep not in seen:
                stack.append(dep)
    return seen


CLOSURE = _closure()


def test_no_UNKNOWN_strong_copyleft_in_the_shipped_closure():
    # THE GATE. GPL/AGPL anywhere in what we ship changes the licensing of what we distribute —
    # including when it arrives transitively, which is how the one real finding here got in.
    # Anything already recorded in AWAITING_DECISION is excluded so the suite is not permanently red
    # over a judgement call, but a NEW one fails on the commit that introduces it.
    named = [f"{c['name']} {c['version']} ({c['license']})" for c in AUDIT["strong_copyleft"]
             if c["name"].lower() in CLOSURE
             and c["name"].lower() not in AWAITING_DECISION
             and c["name"].lower() not in DEV_ONLY]
    assert not named, (
        "GPL/AGPL in the SHIPPED dependency closure — disallowed by a standing project "
        "constraint:" + chr(10) + "  " + (chr(10) + "  ").join(named)
    )


def test_our_SOURCE_never_imports_a_banned_module():
    # The environment-independent half, and the one that actually matters. PyMuPDF is present in this
    # venv as an OPTIONAL `ezdxf[draw]` extra — undeclared, unused, and harmless while nothing imports
    # it. The day somebody writes `import fitz` it would work locally and ship an AGPL dependency.
    # This catches that on the commit that introduces it rather than at a licence review.
    import pathlib
    hits = []
    for root in ("src", os.path.join("..", "data", "src")):
        base = pathlib.Path(_HERE) / root
        for f in base.rglob("*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for mod in BANNED_IMPORTS:
                if f"import {mod}" in text:
                    hits.append(f"{f}: import {mod}")
    assert not hits, "AGPL module imported by first-party source:" + chr(10) + "  " + (chr(10) + "  ").join(hits)


def test_first_party_never_imports_bcf_client():
    # The half of the bcf-client question that IS a code fact rather than a licensing judgement: we
    # must never take a direct dependency on it. `bcf_io` in this codebase is OUR module — the name
    # collision is close enough to be worth an assertion rather than a comment.
    import pathlib
    hits = []
    for root in ("src", os.path.join("..", "data", "src")):
        for f in (pathlib.Path(_HERE) / root).rglob("*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for bad in ("import bcf" + chr(10), "from bcf ", "from bcf.",
                        "import bcf_client", "from bcf_client"):
                if bad in text:
                    hits.append(f"{f}: {bad.strip()}")
    assert not hits, "first-party code imports the GPLv3 bcf-client package:" + chr(10) + "  " + (chr(10) + "  ").join(hits)


def test_we_only_use_ifctester_s_IDS_surface():
    # Importing `ifctester.ids` pulls in no bcf modules; importing `ifctester.reporter` would. Keeping
    # our usage to `ids` is what makes excluding bcf-client from the artifact viable at all.
    import pathlib
    bad = []
    for root in ("src", os.path.join("..", "data", "src")):
        for f in (pathlib.Path(_HERE) / root).rglob("*.py"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            # Only real IMPORT statements — matching the bare word also hits docstrings and notes
            # strings, and a gate that fires on prose is a gate somebody switches off.
            for line in text.splitlines():
                st = line.strip()
                if not (st.startswith("import ifctester") or st.startswith("from ifctester")):
                    continue
                if st in ("from ifctester import ids",) or st.startswith("import ifctester.ids"):
                    continue
                bad.append(f"{f}: {st}")
    assert not bad, ("ifctester used beyond its `ids` surface — that may pull in bcf-client (GPLv3):"
                     + chr(10) + "  " + (chr(10) + "  ").join(bad))


def test_installed_but_UNDECLARED_copyleft_is_reported_not_failed():
    # Reported so it is visible, not failed so the gate stays usable. `pyinstaller` (GPLv2, with its
    # bundling exception) builds the desktop binary and is not inside it; PyMuPDF arrives as an
    # optional extra of a permissive dependency.
    extra = sorted(c["name"] for c in AUDIT["strong_copyleft"] if c["name"].lower() not in DECLARED)
    for name in extra:
        assert name.lower() in DEV_ONLY or name.lower() not in DECLARED, name
    globals()["_EXTRA"] = extra


def test_the_audit_actually_examined_something():
    # The failure this whole file guards against: a check that inspected nothing reporting clean. An
    # empty distribution list, or an unreadable requirements file, would make the gate vacuous.
    assert AUDIT["total"] > 40, f"only {AUDIT['total']} distributions seen — the audit found nothing"
    assert AUDIT["permitted"] > 0, "no permitted licences classified — the classifier is broken"
    assert len(DECLARED) > 5, f"only {len(DECLARED)} declared deps parsed — requirements path moved"
    assert len(CLOSURE) > len(DECLARED), "the closure is not wider than the declared set — walk broken"


def test_the_awaiting_decision_list_states_a_reason_and_is_still_real():
    for name, why in AWAITING_DECISION.items():
        assert len(why) > 60, f"{name} needs a real reason, not a placeholder"
        assert name in CLOSURE, f"{name} is no longer in the shipped closure — delete this entry"


def test_weak_copyleft_is_surfaced_but_does_NOT_fail():
    # LGPL/MPL is accepted for our dynamic-linking distribution and still reported, so a shift from
    # weak to strong is visible rather than silent.
    weak = [c for c in AUDIT["copyleft"] if not c["strong_copyleft"]]
    assert AUDIT["copyleft_count"] >= len(weak)


def test_unknown_licences_are_counted_not_assumed_permitted():
    # A package whose metadata omits the field is UNKNOWN, and unknown is not permission.
    assert AUDIT["unknown_count"] == len(AUDIT["unknown"])
    for c in AUDIT["unknown"]:
        assert c["classification"] == "unknown", c


def test_the_classifier_is_not_fooled_by_substrings():
    # "EXEMPLARY" appears in BSD text and contains "mpl". Word-boundary matching, not `in`.
    assert supply_chain.classify_license("BSD 3-Clause ... EXEMPLARY damages") == "permitted"
    assert supply_chain.classify_license("GNU Affero General Public License") == "copyleft"
    assert supply_chain.is_strong_copyleft("AGPL-3.0") is True
    assert supply_chain.is_strong_copyleft("LGPL-2.1") is False       # weak, and the distinction matters
    assert supply_chain.classify_license("") == "unknown"


for _n, _f in sorted(list(globals().items())):
    if _n.startswith("test_") and callable(_f):
        _f()

_shipped = sorted(c["name"] for c in AUDIT["strong_copyleft"] if c["name"].lower() in CLOSURE)
_not_shipped = sorted(c["name"] for c in AUDIT["strong_copyleft"] if c["name"].lower() not in CLOSURE)

print(f"SEC-SUPPLY GATE OK - {AUDIT['total']} distributions audited; {len(DECLARED)} declared "
      f"runtime deps expand to a shipped closure of {len(CLOSURE)}. Strong copyleft IN THE CLOSURE: "
      f"{_shipped} (all recorded in AWAITING_DECISION - see this file). Strong copyleft installed "
      f"but NOT shipped: {_not_shipped} - pyinstaller builds the desktop binary and is not inside "
      "it, PyMuPDF is an optional ezdxf[draw] extra that nothing imports. The "
      "'MIT/BSD/Apache only, no GPL/AGPL' constraint was held by prose and by whoever remembered to "
      "check a new dependency; it is now held by this suite, which fails on the commit that "
      "introduces a NEW one and names it. THE FINDING THIS PRODUCED: the first version of this gate "
      "checked declared names only and would have missed the one real case here - GPLv3 arriving as "
      "an UNCONDITIONAL requirement of a permissive declared dependency. What binds a distribution "
      "is the whole closure it ships, not the names somebody typed. `supply_chain` had the "
      "classifier and the audit already, with its own tests and NOTHING invoking it - the same shape "
      "as money.py: a mechanism written to enforce something, enforcing nothing. Weak copyleft "
      "(LGPL/MPL - ifcopenshell, certifi) is REPORTED not failed, because collapsing 'disallowed' "
      "into 'worth a look' makes a gate either useless or permanently red, and a permanently red "
      "gate gets switched off.")
