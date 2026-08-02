"""One-command test gate for the API.

The test_*.py files are self-contained scripts (each spins up a TestClient, runs
assertions, prints a one-line summary, and exits non-zero on failure). This runner
executes each in isolation with its own SQLite db + storage dir, and exits non-zero
if any fail — suitable for CI.

    cd services/api && PYTHONPATH=src python run_tests.py
    (deps: pip install -r requirements.txt -r requirements-dev.txt)
"""
from __future__ import annotations

import concurrent.futures
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = ["test_proforma", "test_renovation", "test_rollover", "test_income_basis", "test_cost", "test_g702_lines", "test_modules", "test_dashboard",
         "test_rbac", "test_auth", "test_connections", "test_presence", "test_collab", "test_serving", "test_api",
         "test_evidence_gate", "test_cpm", "test_estimate", "test_bidding", "test_safety", "test_portfolio", "test_templates", "test_versions", "test_generate", "test_sso", "test_ai", "test_closeout", "test_security", "test_dev_budget", "test_specialty", "test_testfit", "test_structure", "test_research", "test_compute_graph", "test_ratelimit", "test_federated_clash", "test_classification",
         # R22-ENTITLE-RISK — approval odds + entitlement duration in the Monte Carlo:
         "test_entitlement_risk", "test_entitlement_route",
         "test_contracts", "test_reports", "test_esign", "test_publish_status", "test_schedule_alerts",
         "test_schedule_optimize",
         # R23-RECIPE-ARTIFACT — the edit-recipe log + its routes:
         "test_recipe_log", "test_recipe_route",
         "test_bundle", "test_bundle_preview", "test_desktop", "test_localmode", "test_project_budget", "test_rvt_bridge",
         # R23-JURISDICTION-PACKS — authority-attributed data requirements:
         "test_jurisdiction_packs", "test_jurisdiction_route", "test_jurisdiction_authz",
         "test_bcf", "test_engines", "test_edge_cases", "test_opendata", "test_financials", "test_money", "test_leasemgmt", "test_changeorders",
         "test_migrate", "test_alembic_migrations", "test_appraisal", "test_marketing", "test_workflow_gate", "test_due_feed", "test_directory",
         # R22-CLASSIFY-AI — classification coverage + code proposals:
         "test_classify_assist", "test_classify_route",
         "test_ask", "test_verification", "test_webhooks", "test_operate_capital", "test_payroll_drawings", "test_assistant_itb", "test_construction_depth", "test_distribution", "test_e57", "test_empty_project", "test_metrics", "test_metrics_auth", "test_licensing", "test_revit_bridge", "test_precon", "test_specs", "test_feasibility", "test_clash_import", "test_clash_intel", "test_layout", "test_loads", "test_verified_progress", "test_element_records", "test_securities_bridge", "test_imports", "test_search_alerts", "test_attachments",
         # previously not wired into the gate (glob would have caught these) — now covered:
         "test_analytics", "test_discipline", "test_gbxml", "test_review", "test_interop",
         "test_module_config", "test_module_schema", "test_field_attrs", "test_eticket_tm", "test_ref_backfill", "test_module_tables", "test_module_filters", "test_guid_integrity", "test_pay_application", "test_module_fields", "test_throttle", "test_route_order",
         # R23-PREFAB-KIT — the kit join + its register routes:
         "test_prefab_kit", "test_prefab_route",
         # Tier-1 competitive upgrades:
         "test_drafting", "test_bid_leveling", "test_benchmarking", "test_unit_rate_memory", "test_unit_rate_route",
         # R22-NOTICE-CLOCK — contractual notice periods + the register routes:
         "test_notice_clock", "test_notices_route",
         # Tier-2/3 competitive upgrades:
         "test_prequal", "test_vendor_memory", "test_payapp", "test_accounting", "test_carbon", "test_codecheck", "test_code_analysis", "test_codes", "test_approvability", "test_rfi_readiness", "test_readiness_bcf", "test_productivity", "test_ebc", "test_element_connections", "test_scene", "test_pricing", "test_cost_db",
         "test_ids_authoring", "test_procurement", "test_conceptual", "test_parcels", "test_net",
         "test_design_phase", "test_family_library", "test_change_instruments", "test_turnover",
         "test_prod_hardening", "test_diligence", "test_operations", "test_reserves_cam", "test_esg",
         "test_cde", "test_openbim_quality", "test_bim_kpi", "test_mcp_standards", "test_twin",
         "test_procurement_gate", "test_sheet_extract", "test_program", "test_pull_plan",
         "test_workspaces", "test_fca", "test_aps", "test_resilience", "test_pull_realtime", "test_disciplines",
         "test_lod", "test_naming", "test_design_engine", "test_mep", "test_resource_loading",
         "test_envelope", "test_model_query", "test_field_ai", "test_deferred",
         "test_gltf_export", "test_gltf_lod", "test_gltf_compress", "test_ifc5_read", "test_ifcx_write", "test_model_events", "test_docmanager", "test_proforma_provenance", "test_filed_output",
         "test_bim_columns", "test_bfast", "test_step_scan", "test_scan_cache", "test_market",
         "test_grid", "test_propmap", "test_layers", "test_graph", "test_fitout", "test_logistics", "test_types", "test_groups", "test_phasing", "test_lod500", "test_selector", "test_representations", "test_openings", "test_detailing", "test_rules", "test_drawing", "test_sections", "test_view_range", "test_disc_ssot", "test_dxf", "test_export_formats", "test_specmanual", "test_steel_connections", "test_rebar", "test_mep_systems", "test_mep_sizing", "test_takeoff2d", "test_measure_provenance", "test_takeoff_count", "test_wave11_edges", "test_unit_scale", "test_curtainwall", "test_nlauthor", "test_nl_ai", "test_guards", "test_edit_undo", "test_sandbox", "test_security_audit", "test_preflight_smoke", "test_wall_slope", "test_mesh", "test_annotation", "test_content", "test_content_import", "test_structural", "test_analytical", "test_struct_solve", "test_lateral", "test_struct_loads", "test_wall_analytical", "test_struct_supports", "test_docgraph", "test_rfi_qa", "test_nodegraph", "test_drawing_set", "test_project_package", "test_mep_families", "test_architectural", "test_preview", "test_ifc_cache",
         "test_evm", "test_authoring_props", "test_wip", "test_traceability", "test_scale",
         "test_sheetgen", "test_issuance", "test_drawing_revision", "test_pdfops", "test_stamps", "test_seal_identity", "test_stepup_race",
         "test_markup", "test_route_authz", "test_global_authz", "test_protected_prefix_coverage", "test_baseline", "test_global_mutating_authz", "test_ref_counter", "test_audit_coverage", "test_bsdd",
         "test_openbim_registry", "test_waterfall", "test_sessions", "test_mfa", "test_stored_ids", "test_cobie", "test_fts_index", "test_scim", "test_saml", "test_responsibility", "test_assemblies",
         "test_dxf_takeoff", "test_qto_class_match", "test_georef", "test_scene_package", "test_clash_bvh", "test_model_qa", "test_model_health", "test_roundtrip_qa", "test_stakeholder", "test_prioritization", "test_ai_readiness",
         "test_scan_deviation", "test_plan_to_bim", "test_errorlog", "test_import_cycles", "test_tenant_scoping", "test_schedule_risk", "test_carbon_compliance", "test_permit_check", "test_drawing_qa", "test_element_5d", "test_authoring_matrix", "test_option_score", "test_plugin_registry", "test_jobs", "test_pid_lock_xproc", "test_sheet_layout", "test_dim_component", "test_sheet_recover", "test_firm_standards", "test_site_context", "test_risk_board", "test_env_wind", "test_model_options", "test_doc_text", "test_escalation", "test_query_dsl", "test_rule_library", "test_schedule_baselines", "test_model_ci", "test_xlsx_roundtrip", "test_geometric_rules", "test_rebar_rules", "test_cx", "test_distwaterfall", "test_license_cloud", "test_smart_views", "test_ifcpatch", "test_bcf_api", "test_coordination_fresh", "test_assemblies_cost", "test_fem_export", "test_subset_export", "test_norm_valid", "test_schema_diag", "test_revision_delta", "test_bep", "test_pm_close", "test_itp", "test_quality_chain", "test_quality_chain_route", "test_meeting_links", "test_est_bands", "test_scope_gap", "test_golden_thread", "test_clash_xml_import", "test_gis_out", "test_cbs", "test_mep_graph", "test_model_warnings", "test_schedule_options", "test_master_builder", "test_client_portal", "test_selections", "test_margin", "test_model_assets", "test_macros", "test_layout_options", "test_equipment", "test_space_util", "test_design_metrics", "test_mep_fittings", "test_prod_actuals", "test_pipeline_allocate", "test_production", "test_procure_level", "test_adjacency", "test_supply_chain", "test_invisible_unicode", "test_cited_answer", "test_est_confidence", "test_buyout_schedule", "test_scope_register", "test_permit_timeline", "test_absorption", "test_progress_rollup", "test_fill_matrix", "test_parcel_geometry", "test_assembly_thermal", "test_portal_txn", "test_persona_answer", "test_boe_ledger", "test_assumption_provenance", "test_assumption_provenance_route", "test_concept_budget", "test_topic_board", "test_roof_window", "test_topic_lifecycle", "test_calc_fields", "test_constraints", "test_cli", "test_view_templates", "test_type_catalogs", "test_password_policy", "test_fin_gov", "test_fin_calc", "test_fin_ingest", "test_fin_portfolio", "test_level_move", "test_instance_props", "test_roundtrip", "test_wall_joins", "test_composite_family", "test_shared_params", "test_version_values", "test_ifcpatch_transforms", "test_bcf3", "test_energy_export", "test_net_effective", "test_cre_deal_desk", "test_cre_governance", "test_cre_tier3", "test_family_geometry", "test_demo_seed", "test_cost_spine", "test_family_shapes", "test_workflow_config", "test_option_takeoff", "test_option_carbon", "test_option_carbon_route", "test_option_economics", "test_option_economics_route", "test_family_coverage", "test_section_annotation", "test_lod500_readiness", "test_scan_to_lod500", "test_egress_routes", "test_status_workflow_parity", "test_section_hatch", "test_section_keynotes", "test_detail_refs", "test_vg_overrides", "test_revit_export_cfg", "test_soft_clash", "test_sequence_clash", "test_element_tags", "test_cost_ifc", "test_fived", "test_health_consistency", "test_module_rooms", "test_modules_response_complete", "test_lifecycle_strip", "test_family_merge", "test_element_facts", "test_consistency", "test_work_queue", "test_task_bind", "test_qto_wire", "test_estimate_diff", "test_dim_constraints", "test_sov_build", "test_takeoff_scope", "test_claim_type", "test_risk_calibrate", "test_schedule_status", "test_engine_routes", "test_reachable", "test_money_wire", "test_license_gate", "test_perf_rate", "test_cache_key", "test_oauth_providers", "test_qto_measured_area", "test_lod_census", "test_lod_proxy", "test_model_ensure", "test_support_graph", "test_export_colour_stable", "test_stair_ramp", "test_profile_dims", "test_plan_pins", "test_pins_unified", "test_index_freshness", "test_bake_budget", "test_geom_slots", "test_bake_shared", "test_geo_ref", "test_file_sizes", "test_claude_md_gates", "test_vitals", "test_samples", "test_bundle_index",
         # R23-DIGEST — the deterministic model digest and its two routes:
         "test_model_digest", "test_digest_route",
         # observability (error alerting + distributed tracing) — env-gated, no-op when unconfigured:
         "test_sentry", "test_otel", "test_docs_module_schema", "test_schema_strictness",
         # public docs are a shipped surface: competitor names for interop only, never comparison:
         "test_no_comparative_names",
         # this list is itself hand-maintained, so it gets a test of its own:
         "test_no_secrets", "test_race_conditions", "test_lock_satisfies_requirements", "test_manifest"]


#: Engine tests that live beside the data service (services/data/test_*.py) — the massing /
#: family-shelf / analysis characterization suites. They were green but DARK: nothing in CI
#: executed them until 2026-08-02 (ci.yml runs only this file, and the manifest below only
#: mapped services/api). They need no DB/storage; they run with cwd=services/data.
DATA_DIR = HERE.parent / "data"
DATA_TESTS = ["test_analysis", "test_families", "test_massing"]


def manifest_problems(tests: list[str] | None = None,
                      on_disk: set[str] | None = None,
                      data_tests: list[str] | None = None,
                      data_on_disk: set[str] | None = None) -> list[str]:
    """The TESTS manifest must be a faithful 1:1 map of the test_*.py files on disk.

    It is hand-maintained (so it can order/skip and set per-test env), and a hand-maintained list
    drifts in three directions — only one of which used to be caught:

      1. a name registered TWICE      -> the suite runs it twice, quietly burning wall time
      2. a name with NO FILE on disk  -> silently dropped by the runner's .exists() filter
      3. a file with NO REGISTRATION  -> a test nobody runs, which is worse than no test

    (2) was the dangerous one, and it is the same shape as the G-8 RBAC prefix list: the runner
    filtered registered-but-missing entries out without a word, so a typo'd or deleted suite still
    printed "N/N suites passed". A count that shrinks silently reads exactly like a clean run.

    `tests`/`on_disk` are injectable so test_manifest.py can drive each rule with a synthetic
    violation and prove it FIRES. A gate nobody has watched fail is not known to work.

    Returns a list of human-readable problems, empty when the manifest is sound.
    """
    tests = TESTS if tests is None else tests
    if on_disk is None:
        on_disk = {p.stem for p in HERE.glob("test_*.py")}
    data_tests = DATA_TESTS if data_tests is None else data_tests
    if data_on_disk is None:
        data_on_disk = {p.stem for p in DATA_DIR.glob("test_*.py")}
    problems: list[str] = []
    # the same three rules apply to BOTH manifests — DATA_TESTS is how the services/data suites
    # went dark in the first place (files on disk, no registry, nothing ran them)
    for label, registered, disk in (("TESTS", tests, on_disk), ("DATA_TESTS", data_tests, data_on_disk)):
        if dupes := sorted(n for n, c in Counter(registered).items() if c > 1):
            problems.append(f"{label}: registered more than once — each suite must run exactly once: "
                            + ", ".join(dupes))
        if missing := sorted(set(registered) - disk):
            problems.append(f"{label}: registered in {label} but no such file on disk (typo, or the "
                            "file was deleted without being de-registered): " + ", ".join(missing))
        if unregistered := sorted(disk - set(registered)):
            problems.append(f"{label}: test file(s) on disk not registered in {label} "
                            "(add to run_tests.py): " + ", ".join(unregistered))
    return problems


def _run_one(t: str, base: dict, cwd: Path = HERE) -> tuple[str, bool, float, str]:
    """Run a single test_*.py as an isolated subprocess (own SQLite db + storage dir) and return
    (name, ok, seconds, captured-output). Safe to run concurrently — each test's db/storage is
    unique. `cwd` selects the suite's home dir (services/api for TESTS, services/data for DATA_TESTS);
    the relative db/storage paths resolve against it either way."""
    env = {**base,
           "DATABASE_URL": f"sqlite:///./_{t}.db",
           "STORAGE_DIR": f"./_storage_{t}",
           "AEC_RBAC": "1" if t in ("test_rbac", "test_modules") else os.environ.get("AEC_RBAC", "0")}
    (cwd / f"_{t}.db").unlink(missing_ok=True)
    # also clear the per-test object-storage dir so sidecar state (e.g. docmanager's
    # {pid}/docs/_index.json) can't leak across runs and break count assertions
    shutil.rmtree(cwd / f"_storage_{t}", ignore_errors=True)
    t0 = time.time()
    # -X utf8 + utf-8 capture so a test's unicode output (→, ², °) never crashes on a cp1252 console
    proc = subprocess.run([sys.executable, "-X", "utf8", f"{t}.py"], cwd=cwd, env=env,
                          capture_output=True, encoding="utf-8", errors="replace")
    return t, proc.returncode == 0, time.time() - t0, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    if problems := manifest_problems():
        for p in problems:
            print(f"FAIL  run_tests manifest: {p}")
        return 1
    # api src + the data service src (analysis/export bridge), mirroring the runtime image
    pp = os.pathsep.join([str(HERE / "src"), str(HERE.parent / "data" / "src")])
    # AEC_GEOM_WORKERS=1: each test's ifcopenshell geometry pass runs single-threaded so the outer
    # test-level parallelism owns the cores (no cpu-1 × cpu-1 oversubscription).
    base = {**os.environ, "PYTHONPATH": pp, "AEC_TRUST_XUSER": "1", "PYTHONUTF8": "1",
            "AEC_GEOM_WORKERS": os.environ.get("AEC_GEOM_WORKERS", "1")}
    # every entry, no filtering: manifest_problems() above has already proved each one exists, so a
    # missing file is now a loud failure rather than a silently shorter run.
    tests = [(t, HERE) for t in TESTS] + [(t, DATA_DIR) for t in DATA_TESTS]
    # each test is an isolated subprocess → embarrassingly parallel. TEST_JOBS overrides the worker count
    # (TEST_JOBS=1 forces the old sequential behaviour for debugging a flaky/order-sensitive test).
    jobs = int(os.environ.get("TEST_JOBS") or 0) or max(1, (os.cpu_count() or 2) - 1)
    jobs = max(1, min(jobs, len(tests)))
    results: list[tuple[str, bool, float]] = []
    t_start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for t, ok, dt, out in ex.map(lambda tc: _run_one(tc[0], base, tc[1]), tests):
            results.append((t, ok, dt))
            print(f"{'PASS' if ok else 'FAIL'}  {t}  ({dt:.1f}s)", flush=True)
            if not ok:
                print(out.strip()[-1200:], flush=True)

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} suites passed  ({jobs} parallel, {time.time() - t_start:.0f}s wall)")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
