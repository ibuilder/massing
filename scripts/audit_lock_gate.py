"""Fail CI when the shipped lock carries an advisory that a version bump would fix.

WHY THIS EXISTS
---------------
`.github/workflows/security.yml` already ran `pip-audit -r services/api/requirements.lock` on the
production interpreter. It audited the right file, in the right Python, and found a HIGH — and the
job reported **success**, because the step carries both `continue-on-error: true` and a trailing
`|| true`. The advisory was written into a step summary that nothing reads and nothing fails on.

Measured 2026-08-09, against a lock that had been green in CI for weeks:

    cryptography 49.0.0   CVE-2026-69247   HIGH       fixed in 50.0.0
    pypdf        6.14.2   CVE-2026-71852   MODERATE   fixed in 6.15.0
    pypdf        6.14.2   CVE-2026-71870   MODERATE   fixed in 6.15.0
    diskcache    5.6.3    CVE-2025-69872   MODERATE   NO FIX PUBLISHED

The bandit step directly below it in the same workflow has exactly the right shape — medium+ is
report-only, HIGH is a separate blocking gate. pip-audit had only the first half. This is the
missing half, written to the same pattern.

THE ASYMMETRY THIS GATE IS BUILT ON
-----------------------------------
It blocks on **advisories with a published fix**, not on all advisories. That distinction is the
whole design:

- An advisory WITH a fix is always actionable — raise the floor in `requirements.in`, regenerate.
  There is no honest reason to carry one, so blocking costs nothing and catches everything.
- An advisory with NO fix cannot be answered by a version bump. Blocking on it would force either a
  permanent exemption (which trains everyone to add exemptions) or removing a dependency under time
  pressure. It stays in the report, and it is a judgement call recorded in prose — see
  `docs/internal/dependency-advisories.md`.

The nice property is that the no-fix case needs no allowlist entry at all, so the exemption list
stays near-empty by construction. And the day upstream publishes a fix, the gate starts firing on
its own — which is the correct moment to be told.

EXEMPTIONS
----------
`EXEMPT` is for the case a fix exists but taking it is a real project: a major bump with breaking
changes. Every entry needs a reason and an EXPIRY, and an expired entry fails the gate rather than
being ignored — an undated exemption is a permanent one wearing a temporary label.
`test_lock_advisories.py` checks that shape offline, in the normal suite, so a malformed or expired
exemption goes red without needing the network.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date

# id -> (expiry ISO date, reason). Empty is the target state, not an oversight.
EXEMPT: dict[str, tuple[str, str]] = {}

LOCKS = ("services/api/requirements.lock",)


def _audit(lock: str) -> list[dict]:
    """Run pip-audit and return its dependency records. A crash here must NOT read as clean."""
    proc = subprocess.run(
        [sys.executable, "-m", "pip_audit", "-r", lock, "--format", "json",
         "--progress-spinner", "off"],
        capture_output=True, text=True,
    )
    # pip-audit exits 1 when it FINDS something, which is not an error. It exits 1 with no parseable
    # JSON when it fails to resolve — the case that made the local run useless. Distinguish them by
    # whether stdout parses, never by the exit code.
    try:
        return json.loads(proc.stdout)["dependencies"]
    except (json.JSONDecodeError, KeyError):
        print(f"::error::pip-audit produced no parseable report for {lock}. This is a BROKEN CHECK, "
              f"not a clean one — treating it as a failure.\n{proc.stderr[-2000:]}")
        raise SystemExit(2)


def main() -> int:
    today = date.today().isoformat()
    blocking: list[str] = []
    unfixed: list[str] = []
    exempted: list[str] = []

    for lock in LOCKS:
        for dep in _audit(lock):
            for v in dep.get("vulns", []) or []:
                fixes = v.get("fix_versions") or []
                line = f"{dep['name']}=={dep['version']}  {v['id']}"
                if not fixes:
                    unfixed.append(f"{line}  (no fix published)")
                elif v["id"] in EXEMPT:
                    expiry, why = EXEMPT[v["id"]]
                    if expiry < today:
                        blocking.append(f"{line} -> {', '.join(fixes)}  [EXEMPTION EXPIRED {expiry}]")
                    else:
                        exempted.append(f"{line}  [exempt until {expiry}: {why}]")
                else:
                    blocking.append(f"{line} -> fixed in {', '.join(fixes)}")

    for title, rows in (("Blocking (a fix exists)", blocking),
                        ("Exempt", exempted),
                        ("No fix published — reported, not blocking", unfixed)):
        if rows:
            print(f"\n{title}:")
            for r in rows:
                print(f"  {r}")

    if blocking:
        print(f"\n::error::{len(blocking)} advisory(ies) in the lock have a published fix. Raise the "
              f"floor in services/api/requirements.in and regenerate the lock via the "
              f"'Lockfile (pip-compile)' workflow.")
        return 1
    print(f"\nOK — no fixable advisory in the lock ({len(unfixed)} unfixed, {len(exempted)} exempt).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
