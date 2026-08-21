"""The npm advisory gate must be able to fail, and its exemptions must expire.

The sibling of `test_lock_advisories.py`, for the other language — written because the npm half of
`.github/workflows/security.yml` had the identical defect its Python half was fixed for, fifty lines
below it, and nobody had looked.

WHAT WAS MEASURED, 2026-08-21
-----------------------------
    npm audit --omit=dev   ->  "found 0 vulnerabilities", exit 0
    npm audit              ->  5 advisories, 2 of them HIGH

**Every advisory in this tree is dev-only, and the step omitted dev.** So it was neutered three
independent ways at once: `continue-on-error: true`, a trailing `|| true`, and a population that
excluded every finding. Any one alone would have been enough; together they made a step that could
not fail look diligent. Sitting behind it: `brace-expansion` (three copies, two advisories) and
`nanoid`, all HIGH, all fixed by an in-range bump — four packages, a 17-line lockfile diff from
`npm audit fix --package-lock-only`. They were not hard. They were invisible.

WHAT THIS FILE ASSERTS, AND WHY IT IS SEPARATE FROM THE GATE
------------------------------------------------------------
`scripts/audit_npm_gate.py` needs the network and an installed `node_modules`, so it runs in CI. What
runs *here* is everything about it that is a decision rather than a lookup: the classification rules,
that exemptions are dated, that an expired one blocks, that a NEW advisory on an already-exempt
package is not covered by the old exemption, and that a broken audit run is a failure rather than a
clean result.

That last one is the trap the whole item is about, in its new location. `npm audit` exits non-zero
when it FINDS something *and* when it cannot read a lockfile. Reading the exit code conflates them;
reading stdout without checking that it parses turns "the tool broke" into "nothing found".

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_npm_advisories.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from datetime import date

_GATE = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "audit_npm_gate.py")
_WF = os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows", "security.yml")

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def _load():
    spec = importlib.util.spec_from_file_location("audit_npm_gate", _GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load()
TODAY = date.today().isoformat()


# --- the exemption list's shape -----------------------------------------------------------------
problems: list[str] = []
for key, entry in gate.EXEMPT.items():
    if not (isinstance(entry, tuple) and len(entry) == 2):
        problems.append(f"{key}: an exemption is (expiry, reason); got {entry!r}")
        continue
    expiry, why = entry
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(expiry)):
        problems.append(f"{key}: expiry {expiry!r} is not an ISO date — an undated exemption never ends")
    elif expiry < TODAY:
        problems.append(f"{key}: expired {expiry}. Take the fix or re-argue it with a new date — "
                        "silently extending is how an exemption becomes permanent")
    if len(str(why).strip()) < 20:
        problems.append(f"{key}: reason {why!r} is too short to be a reason")
    # The key carries the advisory, not just the package. That is the load-bearing part: an
    # exemption for THIS finding must not silently cover the NEXT one on the same package.
    if ":" not in key:
        problems.append(f"{key}: an exemption key is `package:ADVISORY-ID`. A bare package name "
                        "exempts every future advisory on it too, which is not what anyone decided")
check("every exemption is dated, live, reasoned, and keyed to ONE advisory",
      not problems, "; ".join(problems) or f"{len(gate.EXEMPT)} exemption(s)")


# --- the classification rules, driven with synthetic reports -------------------------------------
def report(**pkgs) -> dict:
    return {"vulnerabilities": pkgs}


def row(sev="high", fix=True, via=None):
    return {"severity": sev, "fixAvailable": fix, "via": via or []}


ADV = [{"url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc", "title": "t"}]

b, e, u = gate.classify(report(pkg=row(fix=True, via=ADV)), TODAY)
check("an in-range fix BLOCKS — it is always actionable", len(b) == 1 and not e and not u,
      "; ".join(b) or "nothing blocked")

b, e, u = gate.classify(
    report(pkg=row(fix={"name": "other", "version": "1.0.0", "isSemVerMajor": True}, via=ADV)), TODAY)
check("a semver-major fix BLOCKS too, rather than being waved through", len(b) == 1,
      "; ".join(b) or "nothing blocked")

b, e, u = gate.classify(report(pkg=row(fix=False, via=ADV)), TODAY)
check("no published fix does NOT block — no bump answers it, so blocking would only manufacture "
      "exemptions", not b and len(u) == 1, "; ".join(u) or "not reported either")

# The twin for the whole gate: it must be able to say yes. A gate that refuses everything is as
# useless as one that refuses nothing, and the assertions above would pass for both.
b, _, _ = gate.classify(report(), TODAY)
check("an empty report blocks nothing", not b)


# --- exemptions, in both directions --------------------------------------------------------------
KEY = "pkg:GHSA-aaaa-bbbb-cccc"
gate.EXEMPT[KEY] = ("2999-01-01", "a live exemption, long enough to be a reason for the shape check")
b, e, _ = gate.classify(report(pkg=row(fix=True, via=ADV)), TODAY)
check("a LIVE exemption suppresses the block", not b and len(e) == 1, "; ".join(b) or "suppressed")

gate.EXEMPT[KEY] = ("2000-01-01", "an expiry in the past, to prove the gate notices rather than ignores")
b, e, _ = gate.classify(report(pkg=row(fix=True, via=ADV)), TODAY)
check("an EXPIRED exemption blocks, and says so", len(b) == 1 and "EXPIRED" in b[0],
      "; ".join(b) or "passed through as still-exempt")

# --- the property the key shape exists for, in the shape npm actually reports -------------------
#
# The first version of this passed `via=OTHER`, which REPLACES the exempt advisory. That only ever
# exercised the case where the old advisory had vanished -- which already worked -- so it was green
# against a `classify()` that suppressed the whole package on any single exempt match. The realistic
# shape is ADDITIVE: an exemption exists because that advisory has no acceptable fix, so it persists,
# and the next advisory lands BESIDE it. Both shapes are asserted below; the additive one is the
# assertion that has teeth.
gate.EXEMPT[KEY] = ("2999-01-01", "a live exemption for ONE advisory, not for the package forever")
OTHER = [{"url": "https://github.com/advisories/GHSA-zzzz-yyyy-xxxx", "title": "a new one"}]

b, e, _ = gate.classify(report(pkg=row(fix=True, via=[*ADV, *OTHER])), TODAY)
check("a new advisory ALONGSIDE an exempt one on the same package still BLOCKS",
      len(b) == 1, "; ".join(b) or "the old exemption silently covered a finding nobody looked at")
check("...and the blocking line names ONLY the unexempted advisory",
      bool(b) and "GHSA-zzzz-yyyy-xxxx" in b[0] and "GHSA-aaaa-bbbb-cccc" not in b[0],
      (b[0] if b else "nothing blocked"))
check("...and says the rest of the row is still exempt, so a reader can tell which half moved",
      bool(b) and "remain exempt" in b[0], (b[0] if b else ""))

# The easy shape, kept: the exempt advisory is gone and only the new one remains.
b, e, _ = gate.classify(report(pkg=row(fix=True, via=OTHER)), TODAY)
check("a NEW advisory replacing an exempt one also BLOCKS", len(b) == 1,
      "; ".join(b) or "nothing blocked")

# Partial expiry: one live, one lapsed. The lapsed one must drag the row into blocking.
gate.EXEMPT["pkg:GHSA-zzzz-yyyy-xxxx"] = ("2000-01-01", "a lapsed exemption sitting beside a live one")
b, e, _ = gate.classify(report(pkg=row(fix=True, via=[*ADV, *OTHER])), TODAY)
check("one EXPIRED exemption blocks even when a sibling advisory is still covered",
      len(b) == 1 and "EXPIRED" in b[0], "; ".join(b) or "passed through as still-exempt")
del gate.EXEMPT["pkg:GHSA-zzzz-yyyy-xxxx"]

# ...and the twin: when EVERY advisory on the row is covered, it is exempt and blocks nothing.
gate.EXEMPT["pkg:GHSA-zzzz-yyyy-xxxx"] = ("2999-01-02", "the sibling, also live")
b, e, _ = gate.classify(report(pkg=row(fix=True, via=[*ADV, *OTHER])), TODAY)
check("a row whose every advisory is covered is exempt, not blocked",
      not b and len(e) == 1, "; ".join(b) or "exempt")
check("...and it quotes the SOONEST expiry, not the most generous one",
      bool(e) and "2999-01-01" in e[0], (e[0] if e else ""))
del gate.EXEMPT["pkg:GHSA-zzzz-yyyy-xxxx"]
del gate.EXEMPT[KEY]


# --- the via chain -------------------------------------------------------------------------------
# npm reports a propagated finding as the NAME of the package it came through, not the advisory.
# Without resolving the chain, every hop looks like a finding with no id and could never be exempted.
chain = {"leaf": {"via": ADV}, "mid": {"via": ["leaf"]}, "top": {"via": ["mid"]}}
check("an advisory id is resolved through npm's `via` chain of package NAMES",
      gate.advisories_for("top", chain) == {"GHSA-aaaa-bbbb-cccc"},
      str(gate.advisories_for("top", chain)))
# A cycle in registry-derived data must not hang a security gate.
cyc = {"a": {"via": ["b"]}, "b": {"via": ["a"]}}
check("a cyclic `via` chain terminates instead of hanging the gate",
      gate.advisories_for("a", cyc) == set())


# --- the EXIT CODE follows the verdict -----------------------------------------------------------
# Everything above drives `classify()`. `main()` is what CI actually runs, and a gate whose
# classification is perfect and whose exit code is always 0 is indistinguishable from no gate --
# which is, precisely, the defect this whole file exists about, one layer in.
_real_audit = gate._audit
for _label, _rep, _want in (
    ("a blocking advisory", {"vulnerabilities": {"p": {"severity": "critical", "fixAvailable": True,
                                                       "via": ADV}}}, 1),
    ("an unfixable one", {"vulnerabilities": {"p": {"severity": "low", "fixAvailable": False,
                                                    "via": ADV}}}, 0),
    ("a clean tree", {"vulnerabilities": {}}, 0),
):
    gate._audit = lambda r=_rep: r
    _got = gate.main()
    check(f"main() exits {_want} for {_label}", _got == _want, f"exit {_got}")
gate._audit = _real_audit


# --- a broken run is a failure, not a pass -------------------------------------------------------
def _fake_run(out: str, err: str = "boom", code: int = 1):
    return lambda *a, **k: type("P", (), {"stdout": out, "stderr": err, "returncode": code})()


_real = subprocess.run
for label, payload in (("unparseable stdout", "npm ERR! code ENOLOCK"),
                       ("valid JSON with no `vulnerabilities` key", '{"auditReportVersion": 2}')):
    try:
        gate.subprocess.run = _fake_run(payload)
        try:
            gate._audit()
        except SystemExit as ex:
            check(f"a broken audit run fails loudly ({label})", ex.code == 2, f"exit {ex.code}")
        else:
            check(f"a broken audit run fails loudly ({label})", False,
                  "treated as an empty result — the gate would report clean for a tree it never read")
    finally:
        gate.subprocess.run = _real


# --- the workflow actually calls it, and can fail -------------------------------------------------
with open(_WF, encoding="utf-8") as fh:
    WF_SRC = fh.read()
at = WF_SRC.find("scripts/audit_npm_gate.py")
check("security.yml invokes the npm-advisory gate", at > -1)
if at > -1:
    start = WF_SRC.rfind("      - name:", 0, at)
    end = WF_SRC.find("      - name:", at)
    step = WF_SRC[start:end if end > -1 else len(WF_SRC)]
    # Comments stripped FIRST. Without this the check reads the step's own comment — which says
    # "DO NOT add continue-on-error" — and fails on the words warning against the thing. That has
    # happened twice in this repo; the sibling test carries the same note for the same reason.
    step = "\n".join(ln for ln in step.splitlines() if not ln.lstrip().startswith("#"))
    check("...with no continue-on-error", "continue-on-error" not in step, step.strip()[:120])
    check("...and no `|| true`", "|| true" not in step)
    check("...and it audits the FULL tree, not --omit=dev — every advisory here is dev-only, so a "
          "production-only scope excludes the entire population", "--omit=dev" not in step)

# A change to the lockfile must be able to TRIGGER the workflow that audits it. The Python sibling
# shipped without this and a lock-only change could not start its own audit for weeks.
block = WF_SRC[WF_SRC.index("    paths:"):WF_SRC.index("  workflow_dispatch:")]
globs = [ln.strip().lstrip("- ").strip('"') for ln in block.splitlines() if ln.strip().startswith("- ")]
check("the trigger globs parse — otherwise this check reads the wrong part of the workflow", bool(globs))
check("a package-lock.json change can trigger the workflow that audits it",
      any(g.endswith("package-lock.json") for g in globs), ", ".join(globs))

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print(f"test_npm_advisories OK  ({len(gate.EXEMPT)} exemption(s))")
