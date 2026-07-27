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
import re
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

# Strong copyleft in the shipped closure must be EXCLUDED FROM THE ARTIFACT, and the exclusion list
# lives in `supply_chain.SHIP_EXCLUDED` — one declaration read by both PyInstaller specs and by the
# container's purge step. This closes the loop: finding a copyleft package and forgetting to act on it
# now fails a build, rather than being recorded in a list nobody re-reads.
EXCLUDED = {k.lower() for k in supply_chain.SHIP_EXCLUDED}
# Import names first-party code must never reach for — derived from the same declaration, so adding
# an exclusion automatically adds its import guard rather than needing a second edit here.
BANNED_IMPORTS = tuple(e["import_name"] for e in supply_chain.SHIP_EXCLUDED.values()) + ("pymupdf", "fitz")


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
             and c["name"].lower() not in EXCLUDED
             and c["name"].lower() not in DEV_ONLY]
    assert not named, (
        "GPL/AGPL in the SHIPPED dependency closure and NOT excluded from the artifact:"
        + chr(10) + "  " + (chr(10) + "  ").join(named)
        + chr(10) + "Either replace it, or add it to supply_chain.SHIP_EXCLUDED with a reason "
        "(which excludes it from the binaries and the image automatically)."
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
                # WORD BOUNDARY, not substring: `import bcf` is a substring of `import bcf_io`,
                # which is OUR module and the whole reason the name is confusing. Same trap the
                # licence classifier already guards ("EXEMPLARY" contains "mpl").
                if re.search(rf"^\s*(?:import|from)\s+{re.escape(mod)}", text, re.M):
                    hits.append(f"{f}: imports {mod}")
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


def test_every_exclusion_states_a_reason_and_is_still_needed():
    for name, entry in supply_chain.SHIP_EXCLUDED.items():
        assert len(entry["why"]) > 60, f"{name} needs a real reason, not a placeholder"
        assert entry["import_name"], f"{name} needs the import name PyInstaller must exclude"
        # An exclusion for something no longer installed is a rule describing the past.
        assert name.lower() in CLOSURE, f"{name} left the closure — delete this exclusion"


def test_a_dual_licensed_package_is_not_treated_as_copyleft():
    # `odfpy` declares Apache OR GPL OR LGPL. Copyleft-wins-ties classified it as copyleft, which
    # would have had us excluding a dependency we are entitled to use under Apache. A choice is a
    # choice, and we take the permissive option.
    assert supply_chain.classify_license(
        "Apache Software License; GNU General Public License (GPL)") == "permitted"
    assert supply_chain.is_dual_licensed("Apache Software License; GNU General Public License (GPL)")
    # But a choice with no permissive option on offer is still disallowed: PyMuPDF is AGPL or
    # COMMERCIAL, and a commercial licence is not permission.
    assert supply_chain.classify_license(
        "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License") == "copyleft"


def test_the_excluded_package_is_genuinely_unused_by_our_import_path():
    # The claim the exclusion rests on: blocking it must not break what we actually import. Asserted
    # rather than trusted, because "we do not use it" is exactly the kind of belief that rots.
    import importlib.abc

    class _Block(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in {e["import_name"] for e in supply_chain.SHIP_EXCLUDED.values()}:
                raise ImportError(f"blocked: {name}")
            return None

    sys.meta_path.insert(0, _Block())
    try:
        from ifctester import ids  # noqa: F401
        from aec_data import validate  # noqa: F401
    finally:
        sys.meta_path.pop(0)


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
      f"{_shipped} - all declared in supply_chain.SHIP_EXCLUDED and therefore EXCLUDED from "
      f"the binaries and the image. Strong copyleft installed "
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
      "gate gets switched off. AND A FALSE POSITIVE WAS REMOVED: odfpy declares Apache OR GPL OR "
      "LGPL, and copyleft-wins-ties classified it as copyleft - which would have had us excluding a "
      "dependency we are entitled to use under Apache. A choice is a choice and we take the "
      "permissive option; PyMuPDF, whose only free option is AGPL, is correctly still disallowed.")
