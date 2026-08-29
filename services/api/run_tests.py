"""One-command test gate for the API.

The test_*.py files are self-contained scripts (each spins up a TestClient, runs
assertions, prints a one-line summary, and exits non-zero on failure). This runner
executes each in isolation with its own SQLite db + storage dir, and exits non-zero
if any fail — suitable for CI.

    cd services/api && PYTHONPATH="src;../data/src" PYTHONUTF8=1 ./.venv/Scripts/python.exe run_tests.py
    (deps: pip install -r requirements.txt -r requirements-dev.txt)

**The interpreter and the path are part of the command, not details.** This line said
`PYTHONPATH=src python run_tests.py` until 2026-08-06 and was wrong three ways at once:

  * bare `python` resolves off PATH — on this machine to an unrelated 3.10, not
    `services/api/.venv`, where ifcopenshell and pydantic are pinned;
  * `PYTHONPATH=src` omits `../data/src`, so every `aec_data` import fails;
  * no `PYTHONUTF8=1`, which this suite needs on Windows.

`docs/roadmap-directions.md` §5 has carried the correct invocation all along, and **that is
precisely why nobody noticed**: a reviewer asking "is this documented properly?" finds a yes
and stops. A correct copy elsewhere is what makes the wrong copy invisible.

Two ways it hurts. The obvious one is import errors, which read as broken code and get fixed
in minutes. **The dangerous one is a run that SUCCEEDS against different library versions and
reports a result nobody can reproduce — and reports it as a pass.** That is the failure that
survives.
"""
from __future__ import annotations

import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = ["test_provenance_report", "test_provenance_estimate_leg", "test_answers_leg_roundtrip", "test_proforma", "test_renovation", "test_rollover", "test_income_basis", "test_cost", "test_g702_lines", "test_modules", "test_dashboard",
         "test_rbac", "test_auth", "test_condition_checks", "test_connections", "test_presence", "test_collab", "test_serving", "test_api",
         "test_evidence_gate", "test_cpm", "test_estimate", "test_bidding", "test_safety", "test_portfolio", "test_templates", "test_versions", "test_generate", "test_sso", "test_ai", "test_closeout", "test_security", "test_dev_budget", "test_specialty", "test_testfit", "test_structure", "test_research", "test_compute_graph", "test_ratelimit", "test_federated_clash", "test_classification",
         # R22-ENTITLE-RISK — approval odds + entitlement duration in the Monte Carlo:
         "test_approval_risk", "test_entitlement_route",
         "test_contracts", "test_scope_library", "test_qto_trade", "test_scope_docx", "test_reports", "test_esign", "test_publish_status", "test_schedule_alerts",
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
         "test_ask", "test_viewer_load_timing", "test_verification", "test_webhooks", "test_operate_capital", "test_payroll_drawings", "test_assistant_itb", "test_construction_depth", "test_distribution", "test_e57", "test_empty_project", "test_metrics", "test_metrics_auth", "test_licensing", "test_revit_bridge", "test_precon", "test_specs", "test_feasibility", "test_clash_import", "test_clash_intel", "test_clash_reduction_scale", "test_layout", "test_loads", "test_verified_progress", "test_element_records", "test_securities_bridge", "test_imports", "test_search_alerts", "test_attachments",
         # previously not wired into the gate (glob would have caught these) — now covered:
         "test_analytics", "test_discipline", "test_gbxml", "test_review", "test_interop",
         "test_module_config", "test_module_aggregate", "test_view_config", "test_view_sharing", "test_view_alerts_per_viewer", "test_markup_rekey", "test_view_crossmodule", "test_report_catalog", "test_env_documented", "test_module_schema", "test_field_attrs", "test_eticket_tm", "test_ref_backfill", "test_module_tables", "test_revision_comments", "test_module_filters", "test_guid_integrity", "test_pay_application", "test_module_fields", "test_throttle", "test_route_order", "test_mutating_get", "test_bootstrap_admin", "test_licence_allowlist", "test_money_parity", "test_money_spine", "test_plan_transform", "test_massingcapture_vendor", "test_mspdi_xxe", "test_scenario_authz", "test_changelog_current", "test_actions_pinned", "test_container_pr_gate", "test_spatial_tree", "test_output_encoding", "test_massingplan_vendor", "test_vendor_reachable", "test_schedule_health", "test_schedule_locations", "test_schedule_takt", "test_schedule_levelling", "test_schedule_progress", "test_schedule_risk_mc", "test_ppc_divergence", "test_ppc_field_conformance", "test_schedule_compare", "test_schedule_windows", "test_schedule_modelled", "test_schedule_p6xml", "test_schedule_earned", "test_schedule_compression", "test_schedule_portfolio", "test_portfolio_authz", "test_no_exception_relay", "test_vendor_drift",
         # R23-PREFAB-KIT — the kit join + its register routes:
         "test_prefab_kit", "test_prefab_route",
         # Tier-1 competitive upgrades:
         "test_drafting", "test_bid_leveling", "test_benchmarking", "test_unit_rate_memory", "test_unit_rate_route",
         # R22-NOTICE-CLOCK — contractual notice periods + the register routes:
         "test_notice_clock", "test_notices_route",
         # Tier-2/3 competitive upgrades:
         "test_prequal", "test_vendor_memory", "test_payapp", "test_accounting", "test_carbon", "test_codecheck", "test_code_analysis", "test_codes", "test_approval_conditions", "test_agent_packs", "test_mcp_attribution", "test_approvability", "test_rfi_readiness", "test_readiness_bcf", "test_productivity", "test_ebc", "test_element_connections", "test_scene", "test_pricing", "test_cost_db",
         "test_ids_authoring", "test_procurement", "test_conceptual", "test_parcels", "test_net",
         "test_design_phase", "test_family_library", "test_change_instruments", "test_turnover",
         "test_prod_hardening", "test_diligence", "test_deal_funnel", "test_deal_memory", "test_deal_memory_beside", "test_energy_star_bridge", "test_operations", "test_reserves_cam", "test_esg",
         "test_cde", "test_openbim_quality", "test_bim_kpi", "test_mcp_standards", "test_twin",
         "test_procurement_gate", "test_sheet_extract", "test_program", "test_pull_plan",
         "test_approval_cycles",
         "test_dead_code_population",
         "test_workspaces", "test_fca", "test_aps", "test_resilience", "test_pull_realtime", "test_disciplines",
         "test_lod", "test_naming", "test_design_engine", "test_mep", "test_resource_loading",
         "test_envelope", "test_model_query", "test_field_ai", "test_deferred",
         "test_gltf_export", "test_gltf_lod", "test_gltf_compress", "test_ifc5_read", "test_ifcx_write", "test_model_events", "test_docmanager", "test_proforma_provenance", "test_filed_output",
         "test_bim_columns", "test_bfast", "test_step_scan", "test_scan_cache", "test_market",
         "test_grid", "test_propmap", "test_layers", "test_graph", "test_fitout", "test_logistics", "test_types", "test_groups", "test_phasing", "test_lod500", "test_selector", "test_representations", "test_openings", "test_detailing", "test_rules", "test_drawing", "test_sections", "test_section_geometry_kinds", "test_view_range", "test_disc_ssot", "test_dxf", "test_export_formats", "test_specmanual", "test_spec_system", "test_keynote_spec", "test_steel_connections", "test_rebar", "test_mep_systems", "test_mep_sizing", "test_takeoff2d", "test_measure_provenance", "test_takeoff_count", "test_wave11_edges", "test_unit_scale", "test_curtainwall", "test_nlauthor", "test_nl_ai", "test_guards", "test_edit_undo", "test_sandbox_bytes", "test_sandbox_adopt", "test_sandbox_isolated", "test_sandbox", "test_security_audit", "test_preflight_smoke", "test_wall_slope", "test_mesh", "test_annotation", "test_content", "test_content_import", "test_structural", "test_analytical", "test_struct_solve", "test_lateral", "test_struct_loads", "test_wall_analytical", "test_struct_supports", "test_docgraph", "test_routines", "test_routines_run", "test_rfi_qa", "test_nodegraph", "test_drawing_set", "test_project_package", "test_mep_families", "test_architectural", "test_preview", "test_icdd", "test_ifc_cache",
         "test_evm", "test_authoring_props", "test_wip", "test_traceability", "test_scale",
         "test_sheetgen", "test_issuance", "test_drawing_revision", "test_pdfops", "test_stamps", "test_seal_identity", "test_stepup_race", "test_sso_provision_race",
         "test_markup", "test_route_authz", "test_resource_id_authz", "test_route_reachability", "test_resumable_upload", "test_model_align", "test_ifc_parse_gate", "test_plugin_isolation", "test_body_pid_authz", "test_global_authz", "test_protected_prefix_coverage", "test_baseline", "test_global_mutating_authz", "test_ref_counter", "test_audit_coverage", "test_bsdd",
         "test_openbim_registry", "test_waterfall", "test_waterfall_cents", "test_sessions", "test_mfa", "test_stored_ids", "test_cobie", "test_fts_index", "test_scim", "test_scim_provision_race", "test_saml", "test_responsibility", "test_array_live", "test_assemblies",
         "test_dxf_takeoff", "test_qto_class_match", "test_georef", "test_scene_package", "test_clash_bvh", "test_model_qa", "test_model_health", "test_roundtrip_qa", "test_stakeholder", "test_prioritization", "test_ai_readiness",
         "test_scan_deviation", "test_plan_to_bim", "test_errorlog", "test_import_cycles", "test_tenant_scoping", "test_schedule_risk_single", "test_carbon_compliance", "test_permit_check", "test_drawing_qa", "test_element_5d", "test_authoring_matrix", "test_option_missing", "test_option_score", "test_plugin_registry", "test_jobs", "test_clash_federated_job", "test_inbox_jobs", "test_job_kind_labels", "test_worker_split", "test_job_orphan_scope", "test_job_stall", "test_pid_lock_xproc", "test_pid_lock_surface", "test_sheet_layout", "test_dim_component", "test_sheet_recover", "test_firm_standards", "test_site_context", "test_risk_board", "test_env_wind", "test_model_options", "test_doc_text", "test_escalation", "test_query_dsl", "test_rule_library", "test_schedule_baselines", "test_model_ci", "test_xlsx_roundtrip", "test_geometric_rules", "test_rebar_rules", "test_cx", "test_distwaterfall", "test_license_cloud", "test_smart_views", "test_view_delete", "test_version_approve_identity", "test_upload_streaming", "test_lod_aspects", "test_lod_element_table", "test_publish_reconvert", "test_model_cache_seed", "test_model_cache_mutation", "test_mutating_readers", "test_adopt_guid", "test_ifcpatch", "test_bcf_api", "test_coordination_fresh", "test_assemblies_cost", "test_fem_export", "test_subset_export", "test_norm_valid", "test_schema_diag", "test_revision_delta", "test_bep", "test_pm_close", "test_itp", "test_quality_chain", "test_quality_chain_route", "test_meeting_links", "test_est_bands", "test_scope_gap", "test_golden_thread", "test_clash_xml_import", "test_gis_out", "test_cbs", "test_mep_graph", "test_model_warnings", "test_schedule_options", "test_master_builder", "test_master_builder_scope", "test_get_commits", "test_project_pulse", "test_client_portal", "test_selections", "test_margin", "test_model_assets", "test_macros", "test_layout_options", "test_equipment", "test_space_util", "test_design_metrics", "test_mep_fittings", "test_prod_actuals", "test_pipeline_allocate", "test_production", "test_procure_level", "test_adjacency", "test_supply_chain", "test_invisible_unicode", "test_cited_answer", "test_est_confidence", "test_buyout_schedule", "test_scope_register", "test_permit_timeline", "test_absorption", "test_progress_rollup", "test_fill_matrix", "test_parcel_geometry", "test_assembly_thermal", "test_portal_txn", "test_persona_answer", "test_boe_ledger", "test_assumption_provenance", "test_assumption_provenance_route", "test_concept_budget", "test_topic_board", "test_roof_window", "test_topic_lifecycle", "test_calc_fields", "test_constraints", "test_element_lookup", "test_cli", "test_view_templates", "test_type_catalogs", "test_password_policy", "test_stepup_single_verifier", "test_fin_gov", "test_fin_calc", "test_fin_ingest", "test_fin_portfolio", "test_level_move", "test_instance_props", "test_roundtrip", "test_wall_joins", "test_composite_family", "test_shared_params", "test_version_values", "test_ifcpatch_transforms", "test_bcf3", "test_energy_export", "test_net_effective", "test_cre_deal_desk", "test_cre_governance", "test_cre_tier3", "test_family_geometry", "test_demo_seed", "test_cost_spine", "test_commercial_drift", "test_family_shapes", "test_workflow_config", "test_option_takeoff", "test_option_carbon", "test_option_carbon_route", "test_option_economics", "test_option_economics_route", "test_option_object", "test_option_object_route", "test_family_coverage", "test_section_annotation", "test_lod500_readiness", "test_scan_to_lod500", "test_egress_routes", "test_status_workflow_parity", "test_section_hatch", "test_section_keynotes", "test_detail_refs", "test_vg_overrides", "test_revit_export_cfg", "test_soft_clash", "test_sequence_clash", "test_element_tags", "test_cost_ifc", "test_fived", "test_health_consistency", "test_module_rooms", "test_modules_response_complete", "test_lifecycle_strip", "test_family_merge", "test_element_facts", "test_consistency", "test_work_queue", "test_task_bind", "test_qto_wire", "test_estimate_diff", "test_dim_constraints", "test_sov_build", "test_takeoff_scope", "test_r37_wire_routes", "test_r37_consolidate", "test_r37_contract", "test_export_promises", "test_pdf_ingest_gate", "test_roadmap_status", "test_claim_type", "test_risk_calibrate", "test_schedule_status", "test_engine_routes", "test_reachable", "test_money_wire", "test_license_gate", "test_license_lock_gate", "test_lock_advisories", "test_npm_advisories", "test_perf_budget", "test_perf_rate", "test_cache_key", "test_oauth_providers", "test_qto_measured_area", "test_lod_census", "test_lod_proxy", "test_model_ensure", "test_support_graph", "test_export_colour_stable", "test_stair_ramp", "test_profile_dims", "test_eot", "test_eot_methods", "test_eot_sourced", "test_shared_model", "test_plan_identity", "test_axon_view", "test_view_kind_dispatch", "test_photo_cv", "test_photo_detect", "test_photo_duplicate", "test_pipeline_scales", "test_plan_pins", "test_plan_cut_quality", "test_pins_unified", "test_index_freshness", "test_bake_budget", "test_geom_slots", "test_bake_shared", "test_geo_ref", "test_file_sizes", "test_declared_imports", "test_delete_ratchet", "test_doc_substance", "test_claude_md_gates", "test_cors_expose_headers", "test_open_redirect", "test_mp_engine", "test_upload_cap", "test_vitals", "test_samples", "test_bundle_index",
         # R41-TEST-RESIDUE — the residue sweep must never propose a database it does not own:
         "test_sweep_guard",
         # R23-DIGEST — the deterministic model digest and its two routes:
         "test_model_digest", "test_digest_route",
         # observability (error alerting + distributed tracing) — env-gated, no-op when unconfigured:
         "test_sentry", "test_otel", "test_doctext_source", "test_docs_module_schema", "test_schema_stale", "test_schema_strictness",
         # public docs are a shipped surface: competitor names for interop only, never comparison:
         "test_no_comparative_names",
         # this list is itself hand-maintained, so it gets a test of its own:
         "test_no_secrets", "test_rate_shared", "test_race_conditions", "test_lock_satisfies_requirements", "test_manifest", "test_alembic_single_head",
         # 2026-08-02 merge-train repair: the eleven-PR merge dropped these six registrations while
         # landing their files — the packed-line hazard, fifth direction. Registered from a disk diff
         # (manifest_problems named them), each run locally first: four green; preflight_covers_settings
         # and stored_collection_caps red because their companion CODE hunks (preflight guards for
         # AEC_ALLOW_IFC_CODE/AEC_SEAL_ALLOW_PROFILE; codes.MAX_AMENDMENTS) were ALSO dropped —
         # Security restores those from their branches; an unregistered test hides that honest red.
         "test_dispatcher_privilege_coverage", "test_ifc_path_containment", "test_outbound_fetch_guard",
         "test_preflight_covers_settings", "test_storage_key_parity", "test_stored_collection_caps", "test_massing_cloud_sso"]


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


def _run_one(t: str, base: dict, cwd: Path = HERE,
             before: frozenset[Path] = frozenset()) -> tuple[str, bool, float, str]:
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
    argv = [sys.executable, "-X", "utf8", f"{t}.py"]
    if os.environ.get("COVERAGE") == "1":
        # COVERAGE=1: opt-in coverage mode (~2x wall time — never the default gate). One .coverage.*
        # shard per subprocess via --parallel-mode; main() combines + emits coverage.xml after the
        # pool. rcfile/data-file are api-anchored so DATA_TESTS (cwd=services/data) share them.
        argv = [sys.executable, "-X", "utf8", "-m", "coverage", "run",
                f"--rcfile={HERE / '.coveragerc'}", f"--data-file={HERE / '.coverage'}",
                "--parallel-mode", f"{t}.py"]
    proc = subprocess.run(argv, cwd=cwd, env=env,
                          capture_output=True, encoding="utf-8", errors="replace")
    ok = proc.returncode == 0
    # R41-TEST-RESIDUE: sweep HERE, not after the pool. The disk sat at ~96% while a full run held
    # ~1.4 GB of databases open at once; removing each as it finishes keeps the peak at roughly one
    # test's worth. A FAILED test keeps its database — that file is the evidence for the failure, and
    # sweeping it destroys what someone needs at 3am.
    # KEEP_TEST_DB=1 keeps everything, for diagnosing a test that PASSES and still leaves state
    # behind — the case where the sweep working correctly is what hides the thing you are hunting.
    if ok and os.environ.get("KEEP_TEST_DB") != "1":
        _sweep_owned(t, cwd, before)
        # ...and the STORAGE dir, which this line did not cover until 2026-08-21. The database half
        # above has kept the peak at "roughly one test's worth" since R41-TEST-RESIDUE; the object
        # storage beside it was created per test, cleared only at the START of the NEXT run of the
        # same test, and therefore accumulated across the whole run and then across runs. 93 dirs and
        # 1.42 GB were sitting here when a suite finally ran the disk out mid-run and reported
        # `database or disk is full` across 71 unrelated suites.
        #
        # Same rule as the database, deliberately: a FAILED test keeps its storage, because the
        # sidecar state is as much the evidence as the rows are, and KEEP_TEST_DB=1 keeps both.
        shutil.rmtree(cwd / f"_storage_{t}", ignore_errors=True)
    return t, ok, time.time() - t0, (proc.stdout or "") + (proc.stderr or "")


#: Anchored on the ASSIGNMENT, not on any occurrence of the DSN. An unanchored pattern matched
#: `sqlite:///./aec.db` inside a COMMENT in test_stepup_race.py — a comment warning that that file
#: is the developer's dev database — and would have unlinked 5 MB of their data the first time that
#: test passed. A comment is not code; `registerOwnership.test.ts` hit the same trap and its first
#: run failed on the sentence explaining what a door is.
_DB_LITERAL = re.compile(r"""DATABASE_URL["']\]\s*=\s*["']sqlite:///\./([^"']+)["']""")
_COMMENT = re.compile(r"^\s*#.*$", re.M)


def _owned_dbs(t: str, cwd: Path) -> set[Path]:
    """The database files test `t` can create — read from its own source, not guessed.

    **Why source-derived rather than a snapshot diff, which is what a per-test sweep would want.**
    Tests run concurrently in a thread pool, so "everything that appeared while I ran" also contains
    files other tests are still using; diffing per-test would delete a live database out from under a
    parallel run. Every test declares its `DATABASE_URL` as a literal `sqlite:///./NAME.db`, so the
    set is knowable exactly and is concurrency-safe by construction.

    Includes the runner's own `_{t}.db` (used by the 187 tests that do not override it) and SQLite's
    `-wal` / `-shm` siblings, which are separate files and were never being removed either.
    """
    names = {f"_{t}.db"}
    try:
        src = _COMMENT.sub("", (cwd / f"{t}.py").read_text(encoding="utf-8", errors="replace"))
        names |= set(_DB_LITERAL.findall(src))
    except OSError:
        pass                                   # unreadable source: fall back to the runner's own name
    out: set[Path] = set()
    for n in names:
        out |= {(cwd / n).resolve()}
        #: `-journal` is SQLite's default rollback sibling and the only one this suite produces
        #: (measured: journal=2, wal=0, shm=0). `-wal`/`-shm` need WAL mode, which it does not use —
        #: the first set was derived from what SQLite CAN write rather than what it DOES write here.
        out |= {(cwd / f"{n}{sfx}").resolve() for sfx in ("-journal", "-wal", "-shm")}
    return out


def _sweep_owned(t: str, cwd: Path, before: frozenset[Path] = frozenset()) -> None:
    """Remove the databases test `t` owns. Only ever called for a test that PASSED.

    `before` is the pre-run snapshot, and it is the belt to the anchored-regex braces. The two
    halves of this sweep have DIFFERENT safety properties: `_sweep_leftovers` is safe by
    construction because a diff cannot name a pre-existing file, while this one deletes BY NAME and
    so is only as safe as the name. Honouring `before` here makes a bad name inert rather than
    destructive, and makes the protected-file property hold for both halves instead of one.
    """
    for q in _owned_dbs(t, cwd) - set(before):
        try:
            q.unlink(missing_ok=True)
        except OSError:
            pass                               # a live handle — the end-of-run check reports it


def _db_snapshot(dirs: tuple[Path, ...] | None = None) -> set[Path]:
    """Every `*.db` sitting in the two suite homes right now, as RESOLVED paths.

    Resolved on both sides of every set operation below, because `Path("./x.db")` and
    `Path("/abs/x.db")` are unequal even when they name the same file — so an unresolved `keep` set
    would silently match nothing and the sweep would delete the failed test's database anyway. That
    is this file's own defect shape inverted: not a cleanup that removes nothing, but a guard that
    protects nothing, and both look identical from outside.
    """
    return {q.resolve() for d in (dirs or (HERE, DATA_DIR)) for q in d.glob("*.db*")}


def _sweep_leftovers(before: set[Path], keep: set[Path],
                     dirs: tuple[Path, ...] | None = None) -> tuple[int, int]:
    """Backstop after the pool: remove run-created databases nobody claimed, return (removed, left).

    **Snapshot-and-diff here, deliberately, where per-test naming is not available.** The obvious
    alternative is `glob("test_*.db")`, and its safety depends on *what filenames happen to exist* —
    which changes when someone adds a test, with no edit to this sweep. `preview.db`, the dev API's
    live database, sits in this directory today; tomorrow it could be something else. A diff against a
    pre-run snapshot can only ever remove files that appeared **during** the run, so it stays correct
    when the filenames change and cannot be broken by a file that arrives later.

    `keep` holds the databases of tests that FAILED. That file is the evidence for the failure, and
    sweeping it destroys the thing someone needs at 3am — so a red suite leaves its state on disk.
    """
    removed = 0
    for q in sorted(_db_snapshot(dirs) - before - keep):
        try:
            q.unlink()
            removed += 1
        except OSError:
            pass
    return removed, len(_db_snapshot(dirs) - before - keep)


#: Disk-full signatures. SQLite reports SQLITE_FULL as "database or disk is full"; the OS layer says
#: "No space left on device". Either one means the machine ran out of room, not that the code is
#: wrong -- and the failure lands on whichever suites happened to be writing at that moment, which is
#: why it reads as a scatter of unrelated defects.
_DISK_FULL = ("database or disk is full", "no space left on device", "disk i/o error")


def _owned_dirs(t: str, cwd: Path) -> set[Path]:
    """The per-test object-storage dir this runner CREATED for `t`.

    Derived, never globbed. `_run_one` sets `STORAGE_DIR=./_storage_{t}`, so the runner knows these
    names exactly -- the same argument `_owned_dbs` makes, and the reason neither needs a pattern.
    A glob would be the tempting simplification and it is the dangerous one: `test_storage_*` matches
    the TRACKED source file `test_storage_key_parity.py`, and `test_ifc_*` matches
    `test_ifc_cache.py` and `test_ifc_path_containment.py`. Confirmed by running that glob and
    checking `git ls-files` on every hit before deleting anything.
    """
    return {(cwd / f"_storage_{t}").resolve()}


def _sweep_owned_dirs(results: list[tuple[str, bool, float]]) -> tuple[int, int]:
    """Remove the per-test storage dirs the run created; keep the ones belonging to FAILED tests.

    **Why a snapshot diff does NOT work here, unlike the database half.** `_run_one` clears
    `_storage_{t}` at test START, not at run end -- so the directory from the PREVIOUS run is already
    present when the pre-run snapshot is taken, the diff comes back empty, and nothing is ever swept.
    That is exactly how 93 directories and 1.42 GB accumulated: the sweep everyone assumed covered
    this could not see it by construction.

    Failed tests keep their storage, for the same reason they keep their database: it is the evidence.
    """
    removed = kept = 0
    for t, ok, _ in results:
        home = DATA_DIR if t in DATA_TESTS else HERE
        for d in _owned_dirs(t, home):
            if not d.is_dir():
                continue
            if not ok:
                kept += 1
                continue
            shutil.rmtree(d, ignore_errors=True)
            if not d.exists():
                removed += 1
    return removed, kept


def _unowned_residue() -> tuple[int, float]:
    """(count, MB) of storage/IFC dirs this runner did NOT create -- reported, never deleted.

    Tests are free to set their own `STORAGE_DIR` / `IFC_DIR`, and many do. Those names are the
    test's business, not the runner's, so the runner reports them and leaves them alone: *the sweep
    must never propose something it does not own* is the rule the database half already follows.
    """
    n = 0
    total = 0
    owned = {d for t in TESTS for d in _owned_dirs(t, HERE)} | {
        d for t in DATA_TESTS for d in _owned_dirs(t, DATA_DIR)}
    for home in (HERE, DATA_DIR):
        for d in home.iterdir() if home.is_dir() else []:
            if not d.is_dir() or d.resolve() in owned:
                continue
            if not (d.name.startswith(("_storage_", "test_storage_", "_ifc_", "test_ifc_"))):
                continue
            n += 1
            total += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
    return n, total / (1024 * 1024)


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
    outputs: list[tuple[str, bool, str]] = []
    dbs_before = _db_snapshot()
    # Free space is MEASURED, before and after, rather than predicted from a per-worker constant that
    # would drift the moment a fixture changes. What it buys is the ability to SAY "the disk filled"
    # instead of leaving a scatter of unrelated tracebacks -- see the _DISK_FULL scan below.
    free_before = shutil.disk_usage(HERE).free
    t_start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        for t, ok, dt, out in ex.map(lambda tc: _run_one(tc[0], base, tc[1], frozenset(dbs_before)), tests):
            results.append((t, ok, dt))
            outputs.append((t, ok, out))
            print(f"{'PASS' if ok else 'FAIL'}  {t}  ({dt:.1f}s)", flush=True)
            if not ok:
                print(out.strip()[-1200:], flush=True)

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} suites passed  ({jobs} parallel, {time.time() - t_start:.0f}s wall)")

    # A full disk does not fail one suite; it fails whichever suites happened to be writing, with
    # tracebacks that name everything except the cause. Two runs here were diagnosed as contention
    # and as a code regression before anyone read far enough down to find `database or disk is full`.
    # An environment failure that looks like 71 defects costs far more than one that announces itself.
    disk_hits = sorted(n for n, ok, out in outputs
                       if not ok and any(s in out.lower() for s in _DISK_FULL))
    if disk_hits:
        shown = ", ".join(disk_hits[:6]) + (f" (+{len(disk_hits) - 6} more)"
                                            if len(disk_hits) > 6 else "")
        print(f"FAIL  DISK FULL, not a code defect: {len(disk_hits)} suite(s) hit a disk-full error"
              f" -- {shown}")
        print(f"      free space {free_before / 2**30:.1f} GB before the run, "
              f"{shutil.disk_usage(HERE).free / 2**30:.1f} GB now (TEST_JOBS={jobs}).")
        # MEASURED, and it retracts the first thing written here. "Lower TEST_JOBS, the peak scales
        # with the worker count" was the obvious explanation and it is FALSE: 8 workers peaked at
        # ~11.6 GB consumed, 3 workers at ~12.5 GB. The footprint is CUMULATIVE over tests completed,
        # not concurrent over workers, so fewer workers only reach the same total more slowly. The
        # space is reclaimed once the run ends, with a lag of a minute or two.
        print("      NOTE: lowering TEST_JOBS does NOT help -- measured at both 3 and 8 workers, the "
              "peak was the same ~12 GB. The footprint is cumulative over tests, not concurrent "
              "over workers. Free disk space; this suite needs roughly 12 GB of headroom.")

    # R41-TEST-RESIDUE. Sweep, then ASSERT the sweep worked — two different checks, and this very
    # defect is why: a sweep that removes nothing looks exactly like a clean tree. Reporting the
    # count is what makes a regression visible instead of silent.
    kept = {q for t, ok, _ in results if not ok
            for q in _owned_dbs(t, DATA_DIR if t in DATA_TESTS else HERE)}
    removed, leftover = _sweep_leftovers(dbs_before, kept)
    held = sum(1 for q in kept if q.exists())
    print(f"test databases: {removed} swept after the pool, {held} kept for failed tests, "
          f"{leftover} unaccounted for")

    # The storage half of the same sweep. It was missing, and the omission is why 93 directories and
    # 1.42 GB survived seven runs and eventually filled the disk mid-suite.
    dirs_removed, dirs_kept = _sweep_owned_dirs(results)
    unowned_n, unowned_mb = _unowned_residue()
    print(f"test storage:   {dirs_removed} swept after the pool, {dirs_kept} kept for failed tests, "
          f"{unowned_n} dir(s) this runner does not own ({unowned_mb:.0f} MB)")
    if unowned_mb > 2048:
        # Reported, never deleted: a test that sets its own STORAGE_DIR owns that name, and "the
        # sweep must never propose something it does not own" is the rule the database half follows.
        # Naming the size is what makes it actionable without the runner taking the decision.
        print(f"      NOTE {unowned_mb / 1024:.1f} GB of test-chosen storage/IFC dirs are lingering. "
              f"They belong to the tests that named them, so this runner leaves them alone -- clear "
              f"them by hand if the disk is tight. Directories only: `test_storage_*` and "
              f"`test_ifc_*` also match TRACKED source files.")
    if leftover:
        print(f"FAIL  run_tests residue: {leftover} test database(s) nobody claimed survived the "
              f"sweep — each full run leaked ~1.4 GB when this regressed before")
        return 1
    if os.environ.get("COVERAGE") == "1":
        # merge the per-subprocess shards and emit coverage.xml (Repowise / CI-artifact upload).
        # Runs even on a red suite: partial coverage of a failing run is still real data.
        subprocess.run([sys.executable, "-m", "coverage", "combine"], cwd=HERE)
        subprocess.run([sys.executable, "-m", "coverage", "xml", f"--rcfile={HERE / '.coveragerc'}"], cwd=HERE)
        print(f"coverage.xml written to {HERE} — upload to Repowise / attach as a CI artifact")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
