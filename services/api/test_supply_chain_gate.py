"""`supply_chain --gate` — its EXIT CODE must agree with its printed verdict.

The defect this exists to stop, found 2026-08-29: `--gate` failed on any strong copyleft in the
installed set, with no awareness of `SHIP_EXCLUDED`. `bcf-client` (GPLv3, an unconditional
requirement of the LGPL `ifctester` we do need) is declared there and purged from every artifact by
the container's `--purge`, so the CLI exited **1 on a correct, policy-compliant tree** — every time,
for anyone following the hardening runbook that says to run it before a release. It and
`test_license_gate.py` were two enforcement paths for ONE policy giving opposite answers, and the
test was the one that was right.

**Why this file is separate from `test_license_gate.py`.** That file asks a question about the
dependency closure — *is any strong-copyleft package actually shipped?* This one asks a question
about the TOOL — *does the command that reports on that closure return an exit code matching what it
printed?* They failed independently, which is the argument for testing them independently: the
closure was correct the whole time the CLI was saying otherwise.

**Neither side of this is invented.** The assertions run the real `license_audit()` over the real
installed environment; the only thing manipulated is `SHIP_EXCLUDED`, which is the input whose
handling was wrong. A fixture describing a synthetic package set would agree with itself no matter
which side was broken — the failure mode `docs/roadmap-directions.md` §5 calls "a test that supplies
BOTH SIDES of a seam".

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_supply_chain_gate.py
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from aec_api import supply_chain  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def run_gate() -> tuple[int, str]:
    """Run the real CLI in-process and return (exit code, what it printed)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = supply_chain._main(["--gate"])
    return code, buf.getvalue()


# --- the population has to be real before any verdict over it means anything ----------------------
audit = supply_chain.license_audit()
check("the audit sees a real installed environment", audit["total"] > 50, f"{audit['total']} dists")
check("  and SHIP_EXCLUDED is non-empty, so the exclusion path is actually exercised",
      bool(supply_chain.SHIP_EXCLUDED), str(sorted(supply_chain.SHIP_EXCLUDED)))

# --- 1. THE REGRESSION: a compliant tree must EXIT 0 ----------------------------------------------
code, out = run_gate()
check("--gate exits 0 on a tree whose only strong copyleft is declared in SHIP_EXCLUDED",
      code == 0,
      f"exit={code}; a package purged from every artifact is not a distribution violation, and a "
      f"permanently red gate gets switched off")
check("  and says so in words, not just in the exit code", "GATE OK" in out, out.strip()[-120:])

# --- 2. VERDICT AND EXIT CODE MUST AGREE — the defect was precisely that they did not -------------
check("  the printed verdict matches the exit code",
      ("GATE FAIL" in out) == (code != 0),
      f"printed {'FAIL' if 'GATE FAIL' in out else 'OK'} but exited {code}")

# --- 3. IT CAN STILL FAIL: remove the exclusion and the same tree must be refused -----------------
# Not a synthetic package — the real GPLv3 distribution that is really installed, with only the
# declaration that makes it acceptable taken away. A gate that only ever passes is indistinguishable
# from one that cannot fail.
_saved = dict(supply_chain.SHIP_EXCLUDED)
try:
    supply_chain.SHIP_EXCLUDED.clear()
    code_bad, out_bad = run_gate()
finally:
    supply_chain.SHIP_EXCLUDED.clear()
    supply_chain.SHIP_EXCLUDED.update(_saved)

check("--gate exits 1 when a strong-copyleft package is NOT excluded from the artifact",
      code_bad == 1, f"exit={code_bad}")
check("  and NAMES the offender, so the failure is actionable",
      "GATE FAIL" in out_bad and any(n.split("-")[0] in out_bad for n in _saved),
      out_bad.strip()[-160:])
check("  and its verdict agrees with its exit code too",
      ("GATE FAIL" in out_bad) == (code_bad != 0))

# --- 4. the manipulation was undone, or every later test in this process reads a broken module ----
check("SHIP_EXCLUDED is restored after the mutation", supply_chain.SHIP_EXCLUDED == _saved,
      f"{sorted(supply_chain.SHIP_EXCLUDED)} vs {sorted(_saved)}")
check("  and the gate is green again on the restored state", run_gate()[0] == 0)

# --- 5. an excluded package is still REPORTED, just not counted as blocking -----------------------
# Silence would be the wrong fix: the operator should still see the GPLv3 is installed, with the
# reason it is acceptable, rather than the tool quietly hiding it.
check("an excluded strong-copyleft package is still listed in the report",
      any(n.split("-")[0] in out for n in _saved), out.strip()[:200])
check("  and is marked as excluded rather than shown as a bare violation", "STRONG*" in out)

print()
if FAILED:
    print(f"supply_chain_gate: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"supply_chain_gate: all checks passed (exit 0 clean / exit 1 unexcluded, "
      f"{audit['total']} distributions)")
