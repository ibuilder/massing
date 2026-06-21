"""One-command test gate for the API.

The test_*.py files are self-contained scripts (each spins up a TestClient, runs
assertions, prints a one-line summary, and exits non-zero on failure). This runner
executes each in isolation with its own SQLite db + storage dir, and exits non-zero
if any fail — suitable for CI.

    cd services/api && PYTHONPATH=src python run_tests.py
    (deps: pip install -r requirements.txt -r requirements-dev.txt)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = ["test_proforma", "test_cost", "test_modules", "test_dashboard",
         "test_rbac", "test_auth", "test_connections", "test_presence", "test_serving", "test_api",
         "test_evidence_gate", "test_cpm", "test_estimate", "test_bidding", "test_safety", "test_portfolio", "test_templates", "test_versions"]


def main() -> int:
    # api src + the data service src (analysis/export bridge), mirroring the runtime image
    pp = os.pathsep.join([str(HERE / "src"), str(HERE.parent / "data" / "src")])
    base = {**os.environ, "PYTHONPATH": pp}
    results: list[tuple[str, bool, float]] = []
    for t in TESTS:
        if not (HERE / f"{t}.py").exists():
            continue
        env = {**base,
               "DATABASE_URL": f"sqlite:///./_{t}.db",
               "STORAGE_DIR": f"./_storage_{t}",
               "AEC_RBAC": "1" if t in ("test_rbac", "test_modules") else os.environ.get("AEC_RBAC", "0")}
        for stale in (HERE / f"_{t}.db",):
            stale.unlink(missing_ok=True)
        t0 = time.time()
        proc = subprocess.run([sys.executable, f"{t}.py"], cwd=HERE, env=env,
                              capture_output=True, text=True)
        ok = proc.returncode == 0
        results.append((t, ok, time.time() - t0))
        print(f"{'PASS' if ok else 'FAIL'}  {t}  ({time.time() - t0:.1f}s)")
        if not ok:
            print((proc.stdout + proc.stderr).strip()[-1200:])

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} suites passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
