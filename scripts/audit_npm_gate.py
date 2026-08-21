"""Fail CI when the npm tree carries an advisory that a version bump would fix.

WHY THIS EXISTS — and it is the same defect as `audit_lock_gate.py`, on the other language
--------------------------------------------------------------------------------------------
That file was written because `pip-audit` ran, found a HIGH, and the job reported **success**: the
step carried both `continue-on-error: true` and a trailing `|| true`. The npm step sitting fifty
lines below it in the same workflow had exactly the same two, and nobody looked.

It was worse than that. Measured 2026-08-21:

    npm audit --omit=dev   ->  "found 0 vulnerabilities", exit 0
    npm audit              ->  5 advisories, 2 of them HIGH

**Every advisory in this repo's tree is dev-only, and the CI step omitted dev.** So the step was
neutered three independent ways at once — it could not fail, its output was discarded, and its
population excluded the only packages that had findings. Any one of the three would have been enough
to make it useless; all three together made it look diligent.

What was actually sitting there, green, for as long as anyone had been looking at that summary:

    brace-expansion  2.1.2 / 5.0.7   GHSA-mh99-v99m-4gvg + GHSA-rgw5-rvv9-x895   HIGH   fix in range
    nanoid           3.3.16          GHSA-2v37-7h3g-55p8                          HIGH   fix in range
    uuid             7.0.3           GHSA-w5hq-g745-h8pq                          MODERATE

The two HIGHs were fixed by `npm audit fix --package-lock-only` — a four-line lockfile diff. They
were not hard. They were invisible.

**"dev-only" is not "harmless" here.** This tree builds and signs the desktop and mobile artifacts.
A build tool that can be made to hang or exhaust memory is a supply-chain problem even though not one
byte of it reaches a browser. That is precisely why this gate audits the WHOLE tree and the
report-only step beside it may keep its `--omit=dev` production view.

THE ASYMMETRY THIS GATE IS BUILT ON
-----------------------------------
Same as its Python sibling: it blocks on advisories **with a published fix**, not on all advisories.
An advisory with a fix is always actionable and there is no honest reason to carry one. An advisory
with no fix cannot be answered by a bump, so blocking would only train everyone to add exemptions.

`npm audit --json` states this directly per package:

    fixAvailable: true                     an in-range bump fixes it   -> BLOCKING
    fixAvailable: {isSemVerMajor: true}    needs a major change        -> BLOCKING, exemptible
    fixAvailable: false                    nothing published           -> reported, never blocking

Note the middle case is blocking rather than waved through. npm's "semver-major fix" is sometimes a
**downgrade** — today it proposes rolling `@capacitor/cli` back from 8.5.x to 8.4.2 — and a rule that
quietly excused those would excuse a genuine major fix too. It is exemptible instead, which forces
the analysis to be written down and dated.

EXEMPTIONS
----------
Keyed `package:GHSA-id`, so a NEW advisory on an already-exempt package produces a key nobody has
exempted and blocks. Every entry needs a reason and an EXPIRY, and an expired entry fails the gate
rather than being ignored — an undated exemption is a permanent one wearing a temporary label.
`services/api/test_npm_advisories.py` checks all of that offline, in the normal suite, so a malformed
or expired exemption goes red without needing the network.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date

#: "package:GHSA-id" -> (expiry ISO date, reason). Near-empty is the target state.
EXEMPT: dict[str, tuple[str, str]] = {
    "uuid:GHSA-w5hq-g745-h8pq": (
        "2026-11-21",
        "Dev-only, and the vulnerable functions are never called. The advisory is a missing buffer "
        "bounds check in uuid's v3/v5/v6 WHEN A BUFFER IS PASSED; the only consumer here is "
        "node_modules/xcode (pulled by @capacitor/cli, dev:true), and it calls `uuid.v4()` with no "
        "arguments at pbxProject.js:90 and nowhere else - checked by reading it, not inferred from "
        "the version. npm's proposed fix is a semver-major DOWNGRADE of @capacitor/cli to 8.4.2, "
        "which would undo the 8.5.x line we are on. Re-check when @capacitor/cli ships an xcode "
        "that does not pin uuid ^7."),
    "xcode:GHSA-w5hq-g745-h8pq": (
        "2026-11-21",
        "The same finding propagated up the chain - xcode's only offence is depending on uuid ^7. "
        "See the uuid entry; it carries the reading of the call site."),
    "@capacitor/cli:GHSA-w5hq-g745-h8pq": (
        "2026-11-21",
        "The same finding propagated one level further - @capacitor/cli depends on xcode. Exempted "
        "here as well because npm reports each hop as its own row, and leaving the hops unexempted "
        "would block on one finding three times. See the uuid entry."),
}


def _audit() -> dict:
    """Run `npm audit --json` over the WHOLE tree. A crash here must NOT read as clean."""
    npm = shutil.which("npm") or "npm"
    proc = subprocess.run([npm, "audit", "--json"], capture_output=True, text=True, shell=False)
    # npm exits non-zero when it FINDS something, which is not an error. It also exits non-zero with
    # no parseable JSON when there is no lockfile or the registry is unreachable. Distinguish them by
    # whether stdout parses, never by the exit code — that conflation is what made the pip-audit
    # version of this check useless in both directions at once.
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("::error::npm audit produced no parseable report. This is a BROKEN CHECK, not a clean "
              f"one — treating it as a failure.\n{(proc.stderr or proc.stdout)[-2000:]}")
        raise SystemExit(2) from None
    if "vulnerabilities" not in report:
        print("::error::npm audit returned JSON with no `vulnerabilities` key — the report format "
              f"changed. Treating as a failure rather than as zero findings.\n{proc.stdout[:1000]}")
        raise SystemExit(2)
    return report


def advisories_for(name: str, vulns: dict, _seen: frozenset[str] = frozenset()) -> set[str]:
    """The GHSA ids behind one package's row, resolved through npm's `via` chain.

    npm reports a propagated finding as `via: ["xcode"]` — the NAME of the package it came through,
    not the advisory. Only the row where the advisory originates carries an object with a `url`. So
    an exemption keyed on the advisory id has to walk the chain, or every propagated hop would look
    like a finding with no id and could never be exempted precisely.

    `_seen` guards a cycle. npm should not produce one, but this walks attacker-adjacent data from a
    registry and an infinite loop in a security gate is a broken security gate.
    """
    out: set[str] = set()
    for via in (vulns.get(name, {}).get("via") or []):
        if isinstance(via, dict):
            if url := via.get("url"):
                out.add(url.rsplit("/", 1)[-1])
        elif isinstance(via, str) and via not in _seen and via != name:
            out |= advisories_for(via, vulns, _seen | {name})
    return out


def classify(report: dict, today: str) -> tuple[list[str], list[str], list[str]]:
    """(blocking, exempted, unfixed) — pure, so the test can drive it with a synthetic report."""
    vulns = report.get("vulnerabilities") or {}
    blocking: list[str] = []
    exempted: list[str] = []
    unfixed: list[str] = []
    for name, v in sorted(vulns.items()):
        fix = v.get("fixAvailable")
        sev = str(v.get("severity", "?")).upper()
        ids = sorted(advisories_for(name, vulns)) or ["(no advisory id in report)"]
        how = ("in-range bump" if fix is True
               else f"semver-major -> {fix.get('name')}@{fix.get('version')}" if isinstance(fix, dict)
               else None)
        line = f"{sev:<8} {name}  {', '.join(ids)}"
        if how is None:
            unfixed.append(f"{line}  (no fix published)")
            continue
        keys = [f"{name}:{i}" for i in ids]
        hit = next((k for k in keys if k in EXEMPT), None)
        if hit is None:
            blocking.append(f"{line}  -> {how}")
        else:
            expiry, why = EXEMPT[hit]
            if expiry < today:
                blocking.append(f"{line}  -> {how}  [EXEMPTION EXPIRED {expiry}]")
            else:
                exempted.append(f"{line}  [exempt until {expiry}: {why[:70]}...]")
    return blocking, exempted, unfixed


def main() -> int:
    blocking, exempted, unfixed = classify(_audit(), date.today().isoformat())
    for title, rows in (("Blocking (a fix exists)", blocking),
                        ("Exempt", exempted),
                        ("No fix published — reported, not blocking", unfixed)):
        if rows:
            print(f"\n{title}:")
            for r in rows:
                print(f"  {r}")
    if blocking:
        print(f"\n::error::{len(blocking)} npm advisory(ies) have a published fix. For an in-range "
              f"one, `npm audit fix --package-lock-only` at the repo root and commit the lock. For a "
              f"semver-major one, take the bump or add a dated EXEMPT entry in "
              f"scripts/audit_npm_gate.py saying why not.")
        return 1
    print(f"\nOK — no fixable npm advisory outside the exemption list "
          f"({len(unfixed)} unfixed, {len(exempted)} exempt).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
