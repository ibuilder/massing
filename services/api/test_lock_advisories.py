"""The lock-advisory gate must be able to fail, and its exemptions must expire.

WHY THIS SUITE IS SEPARATE FROM THE GATE
----------------------------------------
`scripts/audit_lock_gate.py` needs the network and a py3.12 interpreter that can resolve the lock, so
it runs in CI and cannot run here. What CAN run here is everything about it that is a decision rather
than a lookup: that exemptions are dated, that an expired one blocks, and that a broken pip-audit run
is treated as a failure rather than as a clean result.

That last one is the point. The defect this whole gate answers was not "we missed a CVE" — CI's
pip-audit found it and printed it. It was that the step could not fail: `continue-on-error: true` AND
a trailing `|| true`, so `Dependency scan` reported success over a HIGH for weeks. A check with no
failure mode is not a check, and the same trap is available to the replacement — pip-audit exits 1
both when it finds an advisory and when it cannot resolve the file at all. Locally it does the
latter (the lock is py3.12, this venv is 3.10) and prints nothing useful. If the gate read the exit
code it would call that a finding; if it read only stdout it would call it clean. It parses stdout
and refuses on unparseable output, and that refusal is asserted below.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
_GATE = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "audit_lock_gate.py")


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit_lock_gate", _GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_exemption_is_dated_and_unexpired() -> None:
    """An undated exemption is a permanent one wearing a temporary label."""
    gate = _load()
    today = date.today().isoformat()
    for vid, entry in gate.EXEMPT.items():
        assert isinstance(entry, tuple) and len(entry) == 2, (
            f"{vid}: an exemption is (expiry, reason); got {entry!r}")
        expiry, why = entry
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry), (
            f"{vid}: expiry {expiry!r} is not an ISO date. An exemption without a date never ends.")
        assert len(why.strip()) >= 20, (
            f"{vid}: reason {why!r} is too short to be a reason. Say why the fix cannot be taken now.")
        assert expiry >= today, (
            f"{vid}: exemption expired {expiry}. Take the fix or re-argue it with a new date — "
            f"silently extending is how an exemption becomes permanent.")
    print(f"PASS  every advisory exemption is dated and live   {len(gate.EXEMPT)} exemption(s)")


def test_an_expired_exemption_blocks() -> None:
    """The twin. Without it, 'the list is empty' would pass the test above forever."""
    gate = _load()
    gate.EXEMPT["FAKE-0000"] = ("2000-01-01", "an expiry in the past, to prove the gate notices")
    gate._audit = lambda _lock: [                     # type: ignore[assignment]
        {"name": "fakepkg", "version": "1.0",
         "vulns": [{"id": "FAKE-0000", "fix_versions": ["2.0"]}]}]
    assert gate.main() == 1, "an expired exemption must block, not pass through as still-exempt"

    # and the same advisory INSIDE its window must not block — otherwise the gate refuses everything
    # and the test above proves nothing.
    gate.EXEMPT["FAKE-0000"] = ("2999-01-01", "a live exemption, to prove the window is honoured")
    assert gate.main() == 0, "a live, dated exemption must pass — a gate that refuses everything is "\
                             "as useless as one that refuses nothing"
    print("PASS  an expired exemption blocks and a live one does not")


def test_a_fixable_advisory_blocks_and_an_unfixable_one_does_not() -> None:
    """The asymmetry the gate is built on, asserted directly rather than left in the docstring."""
    gate = _load()
    gate._audit = lambda _lock: [                     # type: ignore[assignment]
        {"name": "pypdf", "version": "6.14.2",
         "vulns": [{"id": "CVE-2026-71852", "fix_versions": ["6.15.0"]}]}]
    assert gate.main() == 1, "an advisory with a published fix must block — it is always actionable"

    gate._audit = lambda _lock: [                     # type: ignore[assignment]
        {"name": "diskcache", "version": "5.6.3",
         "vulns": [{"id": "CVE-2025-69872", "fix_versions": []}]}]
    assert gate.main() == 0, (
        "an advisory with NO published fix must not block: no version bump answers it, so blocking "
        "would force a permanent exemption or a rushed removal. It stays in the report.")
    print("PASS  fixable blocks, unfixable reports   the asymmetry holds in both directions")


def test_a_broken_audit_run_is_a_failure_not_a_pass() -> None:
    """The trap that produced this whole item, in its new location.

    pip-audit exits 1 when it FINDS something and also when it cannot resolve the file. Reading the
    exit code conflates them; reading stdout without checking it parses turns 'the tool broke' into
    'nothing found'. Neither is acceptable, so unparseable output raises.
    """
    gate = _load()
    real = subprocess.run
    try:
        subprocess.run = lambda *a, **k: type(                     # type: ignore[assignment]
            "P", (), {"stdout": "ERROR: could not resolve", "stderr": "boom", "returncode": 1})()
        try:
            gate._audit("services/api/requirements.lock")
        except SystemExit as e:
            assert e.code == 2, f"a broken audit must exit 2, not {e.code}"
        else:
            raise AssertionError(
                "unparseable pip-audit output was treated as an empty result — the check would "
                "report clean for a lock it never actually read")
    finally:
        subprocess.run = real
    print("PASS  a broken audit run fails loudly instead of reading as clean")


def test_the_workflow_actually_calls_the_gate_and_can_fail() -> None:
    """A gate nothing invokes is the same as no gate — and this repo has shipped that twice.

    Also asserts the invocation carries NEITHER escape hatch. `continue-on-error` and `|| true` are
    each individually sufficient to make the step unable to fail, and the step being replaced had
    both.
    """
    wf = os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows", "security.yml")
    with open(wf, encoding="utf-8") as fh:
        src = fh.read()
    at = src.find("scripts/audit_lock_gate.py")
    assert at > -1, "security.yml does not invoke the lock-advisory gate"

    # the step containing the call: from the preceding "- name:" to the next one
    start = src.rfind("      - name:", 0, at)
    end = src.find("      - name:", at)
    step = src[start:end if end > -1 else len(src)]
    # Strip comment lines first. Without this the check reads the step's OWN comment — which says
    # "DO NOT add continue-on-error here" — and fails on the words warning against the thing. It did,
    # on the first run. A gate that greps prose is measuring the wrong text.
    step = "\n".join(ln for ln in step.splitlines() if not ln.lstrip().startswith("#"))
    assert "continue-on-error" not in step, (
        "the gate step carries continue-on-error — it cannot fail, which is the exact defect it "
        "exists to correct")
    assert "|| true" not in step, "the gate step swallows its exit code with `|| true`"
    print("PASS  security.yml invokes the gate, with no continue-on-error and no `|| true`")


def _triggers() -> dict:
    """security.yml's `on:` block, parsed.

    `yaml.safe_load` reads the bare key `on` as the BOOLEAN True under YAML 1.1, so the block can
    arrive under either key depending on quoting. Checking only one is how a test like this reads
    an empty dict and passes over a workflow it never examined.
    """
    import yaml
    wf = os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows", "security.yml")
    with open(wf, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh.read()) or {}
    on = doc.get("on", doc.get(True))
    assert isinstance(on, dict) and on, (
        "security.yml's `on:` block did not parse — this check would otherwise pass by measuring "
        "nothing, which is the failure it exists to catch")
    return on


def test_the_blocking_gates_can_actually_block_a_merge() -> None:
    """A gate that only runs AFTER the merge does not gate the merge.

    THE DEFECT, 2026-09-03. This workflow hosts two BLOCKING gates -- `audit_lock_gate.py` and
    `audit_npm_gate.py` -- and triggered on `push:` to main, a weekly schedule and manifest paths.
    Never on `pull_request`. So neither gate could refuse a merge; each could only report one that
    had already happened. Four PRs (#393-#396) landed over a red scan carrying three pypdf CVEs and
    two HIGH browserslist advisories, every one already fixed upstream.

    Same shape as `test_container_pr_gate.py` ("a skipped job is not a passed job"), one level up:
    there a JOB could not run on the event that would show a human the break first; here the whole
    WORKFLOW could not. A check that cannot run before the thing it guards is not a weaker check.

    The file's own header had said "Non-blocking by design ... ci.yml stays the hard gate" for as
    long as the gates existed, which is very likely WHY nobody wired the trigger: a reader who
    believed the header had no reason to. That sentence is corrected, and this asserts the trigger
    rather than the sentence -- prose cannot fail.
    """
    on = _triggers()
    assert "pull_request" in on, (
        "security.yml has no `pull_request:` trigger, so its two BLOCKING gates cannot refuse a "
        "merge -- they can only report one that already happened. Add the trigger; do not weaken "
        "the gates.")
    print("PASS  the blocking gates run on pull_request, so they can actually block")


def test_the_push_and_pull_request_globs_stay_identical() -> None:
    """The ratchet on the duplication, because GitHub Actions does not honour YAML anchors.

    Two lists of the same thing drift, and the drift is silent and asymmetric: a glob added to
    `push:` but not `pull_request:` restores the original hole FOR THAT FILE ALONE -- the scan still
    runs after the merge, so nothing looks broken, and every other assertion in this file still
    passes. Derived from both blocks and compared; neither is listed here.

    Division of labour with the check below, established by mutation rather than assumed: this one
    catches DIVERGENCE and runs first, so it shadows the per-event check for that case. The
    per-event check earns its place on the other failure -- both lists identical and both wrong,
    where equality is satisfied and an audited lock still matches nothing.
    """
    on = _triggers()
    push = list((on.get("push") or {}).get("paths") or [])
    pr = list((on.get("pull_request") or {}).get("paths") or [])
    assert push, "no `push: paths:` globs parsed"
    assert pr, "no `pull_request: paths:` globs parsed"
    assert push == pr, (
        "security.yml's push and pull_request path globs have diverged. Any manifest reachable by "
        f"only one of them is audited on only one event.\n  push only:         {sorted(set(push) - set(pr))}"
        f"\n  pull_request only: {sorted(set(pr) - set(push))}")
    print(f"PASS  push and pull_request audit the same manifests   {len(push)} glob(s), identical")


def test_every_audited_path_can_actually_trigger_the_workflow() -> None:
    """A gate that its own subject cannot trigger is not a smaller gate — it is no gate.

    Found 2026-08-09, immediately after shipping the gate above. `security.yml` triggered on
    `**/requirements*.txt`; the file it audits is `services/api/requirements.lock`, which matched
    none of the globs. A lock-only change — the exact change that introduces or removes an advisory
    — could not start the workflow that checks the lock. The CVE-bump commit ran it only because it
    happened to touch `security.yml` in the same push.

    So this asserts the two halves against each other: every path in `audit_lock_gate.LOCKS` must
    match a trigger glob, on BOTH events. Neither list is trusted to remember the other.

    Parsed as YAML now, not sliced out of the text. The original took the first `paths:` and cut to
    `workflow_dispatch:` — which spanned BOTH glob lists the moment the `pull_request:` block landed
    between them, quietly measuring a merged list of twelve. It would still have passed. This file
    already carries the lesson one function up: a gate that greps prose measures the wrong text.
    """
    import fnmatch

    gate = _load()
    on = _triggers()
    for event in ("push", "pull_request"):
        globs = list((on.get(event) or {}).get("paths") or [])
        assert globs, f"no `{event}: paths:` globs parsed"
        for lock in gate.LOCKS:
            matched = [g for g in globs
                       if fnmatch.fnmatch(lock, g) or fnmatch.fnmatch(lock, g.replace("**/", "*"))
                       or fnmatch.fnmatch(os.path.basename(lock), g.removeprefix("**/"))]
            assert matched, (
                f"{lock} is audited by the gate but matches none of security.yml's `{event}` "
                f"globs {globs} — a change to it would not run the workflow that audits it")
    print(f"PASS  every audited lock can trigger the workflow on push AND pull_request   "
          f"{len(gate.LOCKS)} path(s)")


if __name__ == "__main__":
    test_every_exemption_is_dated_and_unexpired()
    test_an_expired_exemption_blocks()
    test_a_fixable_advisory_blocks_and_an_unfixable_one_does_not()
    test_a_broken_audit_run_is_a_failure_not_a_pass()
    test_the_workflow_actually_calls_the_gate_and_can_fail()
    test_the_blocking_gates_can_actually_block_a_merge()
    test_the_push_and_pull_request_globs_stay_identical()
    test_every_audited_path_can_actually_trigger_the_workflow()
    print("test_lock_advisories OK")
