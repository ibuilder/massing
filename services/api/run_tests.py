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
         "test_evidence_gate", "test_cpm", "test_estimate", "test_bidding", "test_safety", "test_portfolio", "test_templates", "test_versions", "test_generate", "test_sso", "test_ai", "test_closeout", "test_security", "test_dev_budget", "test_specialty", "test_testfit", "test_structure", "test_research", "test_compute_graph", "test_ratelimit", "test_federated_clash", "test_classification",
         "test_contracts", "test_reports", "test_esign", "test_publish_status", "test_schedule_alerts",
         "test_schedule_optimize",
         "test_bundle", "test_desktop", "test_localmode", "test_project_budget", "test_rvt_bridge",
         "test_bcf", "test_engines", "test_edge_cases", "test_opendata", "test_financials",
         "test_migrate", "test_appraisal", "test_marketing", "test_workflow_gate", "test_due_feed", "test_directory",
         "test_ask", "test_verification", "test_webhooks", "test_operate_capital", "test_payroll_drawings", "test_assistant_itb", "test_construction_depth", "test_distribution", "test_e57", "test_empty_project", "test_metrics", "test_licensing", "test_revit_bridge", "test_precon", "test_specs", "test_feasibility", "test_clash_import", "test_imports", "test_search_alerts", "test_attachments",
         # previously not wired into the gate (glob would have caught these) — now covered:
         "test_analytics", "test_discipline", "test_gbxml", "test_review", "test_interop",
         "test_module_config", "test_module_schema", "test_throttle", "test_route_order",
         # Tier-1 competitive upgrades:
         "test_drafting", "test_bid_leveling", "test_benchmarking",
         # Tier-2/3 competitive upgrades:
         "test_prequal", "test_payapp", "test_accounting", "test_carbon", "test_codecheck", "test_pricing",
         "test_ids_authoring", "test_procurement", "test_conceptual", "test_parcels", "test_net",
         "test_design_phase", "test_family_library", "test_change_instruments", "test_turnover",
         "test_prod_hardening"]


def main() -> int:
    # api src + the data service src (analysis/export bridge), mirroring the runtime image
    pp = os.pathsep.join([str(HERE / "src"), str(HERE.parent / "data" / "src")])
    base = {**os.environ, "PYTHONPATH": pp, "AEC_TRUST_XUSER": "1"}
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
