/** Typed client for the backend API (guide §7). Geometry comes from .frag; all element
 *  metadata and work artifacts (pins/RFIs/viewpoints) come from here. */
import { IS_DEMO, demoTextOr } from "../demo/demoApi";
import { HttpCore } from "./httpCore";

// DTO types live in ./types (extracted from this file). Re-export them so the many
// `import { … } from "../api/client"` sites across the app keep resolving unchanged.
export * from "./types";
import type {
  AccountUser, Appraisal, AuditEntry, ConnectionItem, Dashboard, DocFile,
  DisciplineTree, DocFolderNode, DrawingMarkupItem, DueFeed, ElementProps, EnergyResult, FinancialStatements,
  IntegrationGroup, ModuleBoard, ModuleDef, ModulePin, ModuleRecord, MonteCarloMetric, MonteCarloResult,
  LogisticsResource, NotifItem, OpendataPermit, ProformaForecast, ProformaResult, ProjectMember, ProjectRole, PropLayer, PropMapRule,
  RecordAttachmentMeta, RelatedRecords, ResponsibilityMatrix, SavedViewDef, SheetMarkupIn, StampTemplate, SyncScheduleItem,
  Topic, Vec3, Viewpoint, WorkItem,
} from "./types";

// Transport (baseUrl, token, json/_pdfPost/url/health) lives in HttpCore; ApiClient adds the typed
// domain methods below. Every `api.method()` call site is unchanged by the split.
export class ApiClient extends HttpCore {
  // --- auth ---------------------------------------------------------------
  /** Enabled SSO providers (Google/Microsoft/Procore) for the login UI. */
  authProviders() {
    return this.json<{ providers: { id: string; label: string }[] }>("/auth/providers");
  }
  /** Admin: integration settings (AI / email / SSO). Secret values are never returned. */
  integrations() {
    return this.json<{ groups: IntegrationGroup[] }>("/settings/integrations");
  }
  saveIntegrations(values: Record<string, string>) {
    return this.json<{ groups: IntegrationGroup[] }>(
      "/settings/integrations", { method: "PUT", body: JSON.stringify({ values }) });
  }
  /** Live "Test connection" for one integration group (by its catalog name) → {ok, message}. */
  testIntegration(group: string) {
    return this.json<{ ok: boolean; message: string }>(
      "/settings/integrations/test", { method: "POST", body: JSON.stringify({ group }) });
  }

  // --- data-source connections (admin) -----------------------------------
  connections() {
    return this.json<{ types: string[]; connections: ConnectionItem[] }>("/connections");
  }
  createConnection(name: string, type: string, config: Record<string, unknown>) {
    return this.json<ConnectionItem>("/connections", { method: "POST", body: JSON.stringify({ name, type, config }) });
  }
  updateConnection(id: string, name: string, type: string, config: Record<string, unknown>) {
    return this.json<ConnectionItem>(`/connections/${id}`, { method: "PUT", body: JSON.stringify({ name, type, config }) });
  }
  deleteConnection(id: string) {
    return this.json<{ ok: boolean }>(`/connections/${id}`, { method: "DELETE" });
  }
  testConnectionConfig(type: string, config: Record<string, unknown>) {
    return this.json<{ ok: boolean; detail: string }>("/connections/test", { method: "POST", body: JSON.stringify({ type, config }) });
  }
  testConnection(id: string) {
    return this.json<{ status: { ok: boolean; detail: string }; info: Record<string, unknown> }>(
      `/connections/${id}/test`, { method: "POST" });
  }
  /** Browse a connection: tables (SQL) or projects (Procore). */
  connectionTables(id: string) {
    return this.json<{ kind?: string; tables?: string[]; projects?: string[]; error?: string }>(
      `/connections/${id}/tables`);
  }
  /** Run a read-only SELECT against a SQL connection. */
  connectionQuery(id: string, sql: string, limit = 200) {
    return this.json<{ columns?: string[]; rows?: unknown[][]; row_count?: number; error?: string }>(
      `/connections/${id}/query`, { method: "POST", body: JSON.stringify({ sql, limit }) });
  }
  /** Read an ACC (Autodesk Construction Cloud) project's issues. */
  accIssues(id: string, projectId: string) {
    return this.json<{ kind?: string; count?: number; issues?: Record<string, unknown>[]; error?: string }>(
      `/connections/${id}/acc/projects/${projectId}/issues`);
  }
  /** Editable Procore->module field mapping for a connection (admin). */
  connectionMappings(id: string) {
    return this.json<{ mappings: Record<string, { module: string; fields: { field: string; label: string; default: string; path: string }[] }> }>(
      `/connections/${id}/mappings`);
  }
  /** Save per-field Procore source-path overrides ({kind: {field: path}}). */
  saveConnectionMappings(id: string, mappings: Record<string, Record<string, string>>) {
    return this.json<{ ok: boolean }>(`/connections/${id}/mappings`, { method: "PUT", body: JSON.stringify({ mappings }) });
  }
  /** Import a Procore project's RFIs / submittals / change events into the matching modules. */
  syncProcore(pid: string, connectionId: string, procoreProjectId: string, kinds?: string[]) {
    return this.json<{ source: string; imported_total: number; results: Record<string, { module: string; fetched: number; imported: number; skipped: number }> }>(
      `/projects/${pid}/sync/procore`,
      { method: "POST", body: JSON.stringify({ connection_id: connectionId, procore_project_id: procoreProjectId, ...(kinds ? { kinds } : {}) }) });
  }
  /** Two-way: push locally-resolved records (RFI status + answer) back to Procore. */
  pushProcore(pid: string, connectionId: string, procoreProjectId: string, kinds: string[] = ["rfi"]) {
    return this.json<{ pushed_total: number; results: Record<string, { pushed: number; skipped: number; errors: string[] }> }>(
      `/projects/${pid}/sync/procore/push`,
      { method: "POST", body: JSON.stringify({ connection_id: connectionId, procore_project_id: procoreProjectId, kinds }) });
  }
  // --- auto-sync schedules (project admin) ---
  syncSchedules(pid: string) {
    return this.json<SyncScheduleItem[]>(`/projects/${pid}/sync/schedules`);
  }
  createSyncSchedule(pid: string, body: { connection_id: string; procore_project_id: string; kinds?: string[]; interval_minutes?: number; push?: boolean }) {
    return this.json<SyncScheduleItem>(`/projects/${pid}/sync/schedules`, { method: "POST", body: JSON.stringify(body) });
  }
  updateSyncSchedule(pid: string, sid: string, patch: { enabled?: boolean; interval_minutes?: number; kinds?: string[]; push?: boolean }) {
    return this.json<SyncScheduleItem>(`/projects/${pid}/sync/schedules/${sid}`, { method: "PUT", body: JSON.stringify(patch) });
  }
  deleteSyncSchedule(pid: string, sid: string) {
    return this.json<{ ok: boolean }>(`/projects/${pid}/sync/schedules/${sid}`, { method: "DELETE" });
  }
  runSyncSchedule(pid: string, sid: string) {
    return this.json<{ imported_total?: number; error?: string }>(`/projects/${pid}/sync/schedules/${sid}/run-now`, { method: "POST" });
  }
  /** Which optional integrations are wired (AI / email / SSO) — for status badges. */
  capabilities() {
    return this.json<{ ai: boolean; email: boolean; sso: string[]; local_mode?: boolean;
      license_tier?: string }>("/capabilities");
  }
  /** Massing licence state — plan tier, per-tier features, masked key. Drives the Settings licence panel. */
  license() {
    return this.json<{ tier: string; tier_label: string; enforced: boolean;
      features: { exports: string[]; api_access: boolean; sso: boolean; navisworks: boolean };
      tiers: { id: string; label: string; features: Record<string, unknown> }[];
      key_configured: boolean; key_masked: string; key_format_valid: boolean | null;
      message: string; manage_url: string }>("/license");
  }
  /** AI/rules risk summary over a project's dashboard. */
  riskSummary(pid: string) {
    return this.json<{ headline: string; risks: { level: string; text: string }[]; source: string; ai_enabled: boolean }>(
      `/projects/${pid}/ai/risk-summary`);
  }
  /** Last-Planner Plan Percent Complete + reasons for non-completion (lean, R4). */
  pullPlanBoard(pid: string, milestone?: string) {
    const qs = milestone ? `?milestone=${encodeURIComponent(milestone)}` : "";
    return this.json<{ total: number; milestones: string[]; milestone_filter: string | null;
      weeks: string[];
      swimlanes: { trade: string; tasks: { ref: string; task: string; trade: string; week: string;
        state: string; responsible: string; duration_days: number | null; constraints: string[];
        milestone: string }[] }[];
      handoffs: { from: string; to: string }[];
      make_ready: { constrained_tasks: number; open_constraints: number;
        by_constraint: { constraint: string; count: number }[] };
      readiness: { ready: number; constrained: number; ready_pct: number | null };
      commitment: { committed: number; done: number; not_done: number; ppc_pct: number | null };
      note: string }>(`/projects/${pid}/pull-plan/board${qs}`);
  }
  pullPlanPdfUrl(pid: string, milestone?: string) {
    const qs = milestone ? `?milestone=${encodeURIComponent(milestone)}` : "";
    return this.url(`/projects/${pid}/pull-plan/board.pdf${qs}`);
  }
  pullPlanMetrics(pid: string, milestone?: string) {
    const qs = milestone ? `?milestone=${encodeURIComponent(milestone)}` : "";
    return this.json<{ total: number; tasks_made_ready: number; tmr_pct: number | null;
      make_ready_runway_weeks: number; perfect_handoff_pct: number | null; clean_handoffs: number;
      handoffs: number; ppc_pct: number | null; committed: number; done: number;
      ppc_trend: { week: string; committed: number; done: number; ppc_pct: number | null }[];
      variance_pareto: { reason: string; count: number }[]; note: string }>(
      `/projects/${pid}/pull-plan/metrics${qs}`);
  }
  benchmarksPullPlanning() {
    return this.json<{ projects: number; target_ppc?: number; message?: string | null;
      ppc?: { low: number; median: number; high: number; avg: number };
      tmr?: { low: number; median: number; high: number; avg: number };
      per_project?: { project_id: string; ppc_pct: number; tmr_pct: number; committed: number }[] }>(
      `/benchmarks/pull-planning`);
  }
  leanPpc(pid: string) {
    return this.json<{ commitments: number; completed: number; ppc: number; missed: number; rating: string; top_variance_reasons: { reason: string; count: number }[] }>(
      `/projects/${pid}/lean/ppc`);
  }
  /** Ask a natural-language question about the project; grounded on a live snapshot. */
  aiAsk(pid: string, question: string) {
    return this.json<{ answer: string; source: string; ai_enabled: boolean; snapshot?: unknown }>(
      `/projects/${pid}/ai/ask`, { method: "POST", body: JSON.stringify({ question }) });
  }
  /** Predictive schedule alerts (overdue / late-start / at-risk predecessor / SPI / procurement). */
  scheduleAlerts(pid: string) {
    return this.json<{ alerts: { level: string; type: string; title: string; detail: string; ref?: string }[];
      counts: { high: number; medium: number; low: number } }>(`/projects/${pid}/schedule/alerts`);
  }
  /** Schedule-acceleration advisory off the CPM critical path (crash / fast-track / near-critical). */
  scheduleOptimize(pid: string) {
    return this.json<{
      project_duration: number; critical_count: number; has_cycle: boolean; headline: string;
      best_single_lever_days: number; source: string; ai_enabled: boolean; narrative: string;
      crash: { ref?: string; name: string; duration: number; days_potential: number; detail: string }[];
      fast_track: { ref?: string; name: string; predecessor: string; days_potential: number; detail: string }[];
      near_critical: { ref?: string; name: string; total_float: number; detail: string }[];
    }>(`/projects/${pid}/schedule/optimize`);
  }

  // --- municipal permit open data (multi-city) -------------------------------
  /** Cities whose building-permit open data is readable (id, label, region, authority, geo support). */
  permitCities() {
    return this.json<{ cities: { id: string; label: string; region: string; authority: string; geo: boolean }[] }>(
      "/opendata/permit-cities");
  }
  /** Query a city's filings near a point / by text. */
  opendataPermits(pid: string, opts: { city: string; lat?: number; lon?: number; radius?: number; address?: string; q?: string; limit?: number }) {
    const qs = new URLSearchParams({ city: opts.city });
    for (const k of ["lat", "lon", "radius", "address", "q", "limit"] as const)
      if (opts[k] !== undefined && opts[k] !== "") qs.set(k, String(opts[k]));
    return this.json<{ city: string; count: number; permits: OpendataPermit[] }>(
      `/projects/${pid}/opendata/permits?${qs}`);
  }
  /** Import a city's filings into the GC `permit` module (source-tagged, deduped). */
  importOpendataPermits(pid: string, body: { city: string; lat?: number; lon?: number; radius?: number; address?: string; q?: string; max?: number }) {
    return this.json<{ imported: number; skipped: number; found: number; refs: string[] }>(
      `/projects/${pid}/opendata/permits/import`, { method: "POST", body: JSON.stringify(body) });
  }

  // --- report center ---------------------------------------------------------
  /** Catalog of available reports (id, name, group). */
  reports() {
    return this.json<{ reports: { id: string; name: string; group: string }[] }>(`/reports`);
  }
  /** URL of a generated report — fmt = pdf | xlsx. */
  reportUrl(pid: string, report: string, fmt: "pdf" | "xlsx") {
    return this.url(`/projects/${pid}/reports/${report}.${fmt}`);
  }

  // --- disposition & valuation (real-estate marketing) ----------------------
  /** Tri-approach valuation for a project (cost + income + sales-comparison + reconciliation). */
  appraisal(pid: string) {
    return this.json<Appraisal>(`/projects/${pid}/appraisal`);
  }
  /** Persist appraisal overrides (weights, depreciation, land value, …) and recompute. */
  saveAppraisal(pid: string, overrides: Record<string, unknown>) {
    return this.json<Appraisal>(`/projects/${pid}/appraisal`, {
      method: "POST", body: JSON.stringify(overrides) });
  }
  /** Re-run the appraisal with the income approach valued off the actual rent roll's in-place income. */
  appraisalFromRentRoll(pid: string) {
    return this.json<Appraisal>(`/projects/${pid}/appraisal?rentroll=1`);
  }
  /** Listing fields pre-populated from the project's proforma + model (off-plan auto-fill). */
  listingAutofill(pid: string) {
    return this.json<{ data: Record<string, unknown> }>(`/projects/${pid}/listings/autofill`);
  }
  /** Mint a signed, expiring public link to a listing (for a QR / shared deep link). */
  shareListing(pid: string, lid: string, ttl?: number) {
    const q = ttl ? `?ttl=${ttl}` : "";
    return this.json<{ url: string; sig: string; exp: number; expires_in: number }>(
      `/projects/${pid}/listings/${lid}/share${q}`, { method: "POST" });
  }
  /** Bulk-import comparables from CSV or a RESO array into the `comparable` module (feeds appraisal). */
  importComparables(pid: string, body: { csv?: string; reso?: Record<string, unknown>[] }) {
    return this.json<{ imported: number; rows: { id: string; ref: string; address: string }[] }>(
      `/projects/${pid}/comparables/import`, { method: "POST", body: JSON.stringify(body) });
  }
  /** The RESO Data Dictionary payload for a listing (the bridge seam to WPRealWise / MLS). */
  listingReso(pid: string, lid: string) {
    return this.json<{ reso: Record<string, unknown> }>(`/projects/${pid}/listings/${lid}/reso`);
  }
  /** Whether the WPRealWise / MLS syndication bridge is configured (off unless REALWISE_URL+key set). */
  reSyndicationStatus() {
    return this.json<{ enabled: boolean; target: string; implemented: boolean;
      targets_supported: string[]; message: string }>(`/re-syndication/status`);
  }
  /** Push a listing (RESO-serialized) to WPRealWise / an MLS. 422 if the bridge isn't configured. */
  syndicateListing(pid: string, lid: string) {
    return this.json<{ target: string; remote_id: string | null; url: string | null;
      fields_pushed: number; status: string }>(
      `/projects/${pid}/listings/${lid}/syndicate`, { method: "POST" });
  }

  // --- model intelligence + field verification ------------------------------
  /** Ask a plain-English question about the model; grounded in the property-index snapshot. */
  askModel(pid: string, question: string) {
    return this.json<{ answer?: string; snapshot?: unknown; source: string }>(
      `/projects/${pid}/ask`, { method: "POST", body: JSON.stringify({ question }) });
  }
  /** Install-coverage summary (verified/installed % vs the model total, deviation count). */
  verificationCoverage(pid: string) {
    return this.json<{ total_elements: number; tracked: number; verified: number; installed: number;
      deviations: number; verified_pct: number; installed_pct: number; by_status: Record<string, number> }>(
      `/projects/${pid}/verification/coverage`);
  }
  /** Set an element's field-verification status (installed | verified | deviation | pending). */
  setVerification(pid: string, guid: string, body: { status: string; note?: string }) {
    return this.json<{ guid: string; status: string; ifc_class?: string }>(
      `/projects/${pid}/verification/${guid}`, { method: "PUT", body: JSON.stringify(body) });
  }
  /** The deviation log (elements flagged as not matching design). */
  verificationDeviations(pid: string) {
    return this.json<{ guid: string; ifc_class?: string; storey?: string; note?: string }[]>(
      `/projects/${pid}/verification/deviations`);
  }

  // --- operate (rent roll) + capital (investors) ----------------------------
  /** Operating rent roll — occupancy, WALT, expiration schedule, in-place income. */
  rentRoll(pid: string) {
    return this.json<{ occupancy_pct: number; lease_count: number; base_rent_annual: number;
      in_place_gross_income: number; walt_years: number; expirations_by_year: Record<string, unknown>;
      rows: Record<string, unknown>[] }>(`/projects/${pid}/rent-roll`);
  }
  /** Lease-management depth — renewal pipeline, rent-escalation schedule, CAM/recovery reconciliation. */
  leaseManagement(pid: string, years?: number, recoverableOpex?: number) {
    const q = new URLSearchParams();
    if (years != null) q.set("years", String(years));
    if (recoverableOpex != null) q.set("recoverable_opex", String(recoverableOpex));
    const qs = q.toString() ? `?${q}` : "";
    return this.json<{
      lease_count: number;
      renewals: { holdover_count: number; expired_count: number; options_outstanding: number;
        at_risk_rent: number; expiring: Record<string, { count: number; rent: number }>;
        rows: Record<string, unknown>[] };
      escalations: { years: number; portfolio_by_year: number[]; current_base_rent: number;
        projected_base_rent: number; rows: Record<string, unknown>[] };
      cam: { recoverable_income: number; recoverable_sf: number; by_lease_type: Record<string, number>;
        recovery_ratio?: number | null; over_recovery?: number; under_recovery?: number;
        rows: Record<string, unknown>[] };
    }>(`/projects/${pid}/leases/management${qs}`);
  }
  /** Investor cap table — ownership by commitment + contributed/distributed totals. */
  capTable(pid: string) {
    return this.json<{ investor_count: number; total_commitment: number; total_contributed: number;
      total_distributed: number; total_unreturned: number; by_class: Record<string, number>;
      rows: Record<string, unknown>[] }>(`/projects/${pid}/cap-table`);
  }
  /** The syndication package — the cap table serialized to a neutral investor-platform schema. Always
   * available offline; this is the payload the capital-markets connector pushes. */
  securitiesPackage(pid: string) {
    return this.json<{ schema: string; project: string; fund: Record<string, unknown>;
      positions: Record<string, unknown>[]; disclosures: Record<string, unknown>; disclaimer: string }>(
      `/projects/${pid}/securities/package`);
  }
  /** Whether the capital-markets syndication bridge is configured. Ledger sync only — never moves money. */
  securitiesSyndicationStatus() {
    return this.json<{ enabled: boolean; target: string; implemented: boolean; moves_money: boolean;
      targets_supported: string[]; message: string }>(`/securities-syndication/status`);
  }
  /** Sync the cap table into the configured investor / digital-securities platform (positions only —
   * no funds move). 422 with an actionable message if the bridge isn't configured. */
  syndicateSecurities(pid: string) {
    return this.json<{ target: string; remote_id: string | null; positions_pushed: number;
      moves_money: boolean; status: string }>(
      `/projects/${pid}/securities/syndicate`, { method: "POST" });
  }
  /** Run a distribution / equity-waterfall scenario over the cap table (pref → RoC → promote tiers). */
  waterfallScenario(pid: string, body: { exit_amount?: number; contribution_date?: string;
    exit_date?: string; distributable?: number[]; dates?: string[]; pref_rate?: number;
    style?: string; clawback?: boolean } = {}) {
    return this.json<{ total_distributable: number; lp_distributions: number; gp_distributions: number;
      lp_irr: number | null; gp_irr: number | null; lp_equity_multiple: number; gp_equity_multiple: number;
      lp_unreturned: number; pref_rate: number; style: string; note?: string;
      periods: Record<string, unknown>[]; per_investor: Record<string, unknown>[] }>(
      `/projects/${pid}/waterfall`, { method: "POST", body: JSON.stringify(body) });
  }
  /** Allocate a capital call (pro-rata by commitment). persist=true posts it to investor totals. */
  capitalCall(pid: string, amount: number, persist = false) {
    return this.json<{ kind: string; amount: number; persisted?: boolean; allocations: { investor: string; amount: number }[] }>(
      `/projects/${pid}/capital-call`, { method: "POST", body: JSON.stringify({ amount, persist }) });
  }
  /** Allocate a distribution (pro-rata by commitment). persist=true posts it to investor totals. */
  distribution(pid: string, amount: number, persist = false) {
    return this.json<{ kind: string; amount: number; persisted?: boolean; allocations: { investor: string; amount: number }[] }>(
      `/projects/${pid}/distribution`, { method: "POST", body: JSON.stringify({ amount, persist }) });
  }
  /** URL of a one-page investor capital-account statement PDF. */
  investorStatementUrl(pid: string, iid: string) {
    return this.url(`/projects/${pid}/investors/${iid}/statement.pdf`);
  }
  /** Mint a signed, expiring link to an investor's statement PDF (the no-login LP-portal share). */
  shareInvestorStatement(pid: string, iid: string, ttl?: number) {
    const q = ttl ? `?ttl=${ttl}` : "";
    return this.json<{ url: string; sig: string; exp: number; expires_in: number }>(
      `/projects/${pid}/investors/${iid}/share${q}`, { method: "POST" });
  }

  // --- assistant · certified payroll · drawing set · ITB --------------------
  /** Ask about the whole project (modules/schedule/budget/risk); grounded snapshot, AI-optional. */
  askProject(pid: string, question: string) {
    return this.json<{ answer?: string; snapshot?: unknown; source: string }>(
      `/projects/${pid}/assistant`, { method: "POST", body: JSON.stringify({ question }) });
  }
  /** Weekly certified-payroll (WH-347) summary. */
  payroll(pid: string, weekEnding?: string) {
    const q = weekEnding ? `?week_ending=${weekEnding}` : "";
    return this.json<{ week_ending: string; worker_count: number; total_hours: number;
      total_gross: number; rows: Record<string, unknown>[] }>(`/projects/${pid}/payroll${q}`);
  }
  /** URL of the WH-347 certified-payroll PDF for a week. */
  wh347Url(pid: string, weekEnding?: string) {
    return this.url(`/projects/${pid}/payroll/wh347.pdf${weekEnding ? `?week_ending=${weekEnding}` : ""}`);
  }
  /** Controlled drawing-set register (current set, superseded, sheet index, issuance new/revised). */
  drawingSet(pid: string) {
    return this.json<{ sheet_count: number; current_count: number; superseded_count: number;
      new_count: number; revised_count: number; by_discipline: Record<string, number>;
      sheet_index: Record<string, unknown>[] }>(`/projects/${pid}/drawing-set`);
  }
  /** Preview the discipline sheet set that would be generated (one NCS series per discipline: M-/FA-/S-/…). */
  drawingSetPlan(pid: string, opts: { disciplines?: string; all?: boolean } = {}) {
    const q = new URLSearchParams({ ...(opts.disciplines ? { disciplines: opts.disciplines } : {}),
      ...(opts.all ? { all: "true" } : {}) }).toString();
    return this.json<{ levels: number; series: string[]; sheet_count: number;
      by_discipline: Record<string, number>; sheets: Record<string, unknown>[] }>(
      `/projects/${pid}/drawing-set/plan${q ? "?" + q : ""}`);
  }
  /** Generate the discipline sheet set as drawing records (per-discipline NCS numbering, plan per level). */
  generateDrawingSet(pid: string, body: { disciplines?: string[]; all?: boolean; max_levels?: number } = {}) {
    return this.json<{ levels: number; series: string[]; planned: number; created: number;
      skipped_existing: number; by_discipline: Record<string, number>; sheet_count: number }>(
      `/projects/${pid}/drawing-set/generate`, { method: "POST", body: JSON.stringify(body) });
  }
  /** Issue the current drawing set for a purpose (AIA/CD) — snapshots every sheet + its revision. */
  issueDrawingSet(pid: string, body: { purpose: string; date?: string; description?: string; recipients?: string }) {
    return this.json<{ id: string; purpose: string; issue_date: string; sheet_count: number }>(
      `/projects/${pid}/drawing-set/issue`, { method: "POST", body: JSON.stringify(body) });
  }
  /** The issuance history (every release, purpose, date, sheet count, recipients). */
  drawingIssuances(pid: string) {
    return this.json<{ issuance_count: number; by_purpose: Record<string, number>;
      issuances: Record<string, unknown>[] }>(`/projects/${pid}/drawing-set/issuances`);
  }
  /** The sheet-index × issuance matrix (each sheet's revision in each issuance). */
  drawingIssuanceMatrix(pid: string) {
    return this.json<{ issuances: Record<string, unknown>[]; sheet_count: number;
      rows: { sheet_number: string; title: string; discipline: string; cells: (string | null)[] }[] }>(
      `/projects/${pid}/drawing-set/issuance-matrix`);
  }
  /** AIA/CD issuance purposes for the "issue for…" picker. */
  drawingIssuancePurposes(pid: string) {
    return this.json<{ purposes: { name: string; abbr: string }[] }>(
      `/projects/${pid}/drawing-set/issuance-purposes`);
  }
  /** URL of a per-issuance transmittal PDF (stamped with the purpose + date). */
  issuanceTransmittalUrl(pid: string, iid: string) {
    return this.url(`/projects/${pid}/drawing-set/issuances/${iid}/transmittal.pdf`);
  }
  /** URL of the digitally-sealed (PAdES) issuance transmittal, for permit/IFC submittal. */
  issuanceSealedUrl(pid: string, iid: string, name = "") {
    const q = name ? "?name=" + encodeURIComponent(name) : "";
    return this.url(`/projects/${pid}/drawing-set/issuances/${iid}/sealed.pdf${q}`);
  }
  // --- PDF manipulation (server pypdf): merge / split / rotate / extract uploaded PDFs -----------
  /** Page count + flags for an uploaded PDF. */
  async pdfInfo(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(this.url("/pdf/info"), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.json() as Promise<{ pages: number; encrypted: boolean }>;
  }
  /** Merge several uploaded PDFs into one (order = list order). */
  pdfMerge(files: File[]) { return this._pdfPost("/pdf/merge", (fd) => { for (const f of files) fd.append("files", f); }); }
  /** Split a PDF into one PDF per page, returned as a .zip. */
  pdfSplitZip(file: File) { return this._pdfPost("/pdf/split", (fd) => fd.append("file", file)); }
  /** Rotate pages by `angle` (multiple of 90); `pages` (1-based '1,3-5') limits it, blank = all. */
  pdfRotate(file: File, angle: number, pages = "") { return this._pdfPost("/pdf/rotate", (fd) => { fd.append("file", file); fd.append("angle", String(angle)); if (pages) fd.append("pages", pages); }); }
  /** Extract the given pages ('1,3,5-7', 1-based) into a new PDF. */
  pdfExtract(file: File, pages: string) { return this._pdfPost("/pdf/extract", (fd) => { fd.append("file", file); fd.append("pages", pages); }); }
  // --- A/E/C stamps (server: reportlab overlay + pypdf; seals add a PAdES signature) --------------
  /** The stamp template library — review (EJCDC + CSI), inspection, status, and PE/RA seal templates. */
  stampLibrary() { return this.json<{ templates: StampTemplate[] }>("/stamps/library"); }
  /** Composite a review / inspection / status stamp onto a page (1-based). (x,y) = top-left in PDF points. */
  pdfStamp(file: File, o: { template_id: string; page?: number; x?: number; y?: number; disposition?: string; values?: Record<string, string> }) {
    return this._pdfPost("/pdf/stamp", (fd) => {
      fd.append("file", file); fd.append("template_id", o.template_id);
      fd.append("page", String(o.page ?? 1)); fd.append("x", String(o.x ?? 36)); fd.append("y", String(o.y ?? 36));
      if (o.disposition) fd.append("disposition", o.disposition);
      if (o.values) fd.append("values", JSON.stringify(o.values));
    });
  }
  /** Apply a *visible* professional seal, then a tamper-evident PAdES signature LAST. Returns the sealed
   *  PDF plus the compliance note the server reports (demo cert vs configured cert). */
  async pdfSeal(file: File, o: { template_id: string; profile: Record<string, string>; page?: number; x?: number; y?: number; sign?: boolean }) {
    const fd = new FormData();
    fd.append("file", file); fd.append("template_id", o.template_id); fd.append("profile", JSON.stringify(o.profile));
    fd.append("page", String(o.page ?? 1)); fd.append("x", String(o.x ?? 36)); fd.append("y", String(o.y ?? 36));
    fd.append("sign", String(o.sign ?? true));
    const r = await fetch(this.url("/pdf/seal"), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return { blob: await r.blob(), sealed: r.headers.get("X-Seal-Sealed") === "true", compliance: r.headers.get("X-Seal-Compliance") || "" };
  }
  /** Record a revision (delta) on a sheet, optionally citing the driving instrument (ASI/CCD/Addendum). */
  reviseDrawing(pid: string, drawingId: string, body: { rev: string; description?: string; date?: string; instrument_type?: string; instrument_ref?: string }) {
    return this.json<{ drawing_id: string; revision: string; delta_count: number }>(
      `/projects/${pid}/drawings/${drawingId}/revise`, { method: "POST", body: JSON.stringify(body) });
  }
  /** The cross-sheet revision register — every delta on every sheet (newest first) + instrument rollup. */
  drawingRevisions(pid: string) {
    return this.json<{ delta_count: number; by_instrument: Record<string, number>;
      revisions: { sheet_number: string; discipline: string; rev: string; date: string; description: string; instrument: { type: string; ref: string } | null }[] }>(
      `/projects/${pid}/drawing-set/revisions`);
  }
  /** URL of a drawing-transmittal PDF for the current set (recipients comma-separated). */
  drawingTransmittalUrl(pid: string, to = "", note = "") {
    const q = new URLSearchParams({ ...(to ? { to } : {}), ...(note ? { note } : {}) }).toString();
    return this.url(`/projects/${pid}/drawing-set/transmittal.pdf${q ? "?" + q : ""}`);
  }
  /** Resolve a record's distribution (CC) field against the contact directory → recipients + emails. */
  recordDistribution(pid: string, key: string, rid: string) {
    return this.json<{ ref: string; recipients: { name: string; email: string | null; resolved: boolean }[];
      emails: string[] }>(`/projects/${pid}/modules/${key}/${rid}/distribution`);
  }
  /** Time & Material (eTicket) cost rollup — labor/material/equipment, billed vs unbilled. */
  tmSummary(pid: string) {
    return this.json<{ ticket_count: number; labor_total: number; material_total: number;
      equipment_total: number; grand_total: number; unbilled_total: number; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/tm-summary`);
  }
  /** T&M (eTicket) cost rolled up by linked change event. */
  tmByChangeEvent(pid: string) {
    return this.json<{ groups: Record<string, unknown>[]; linked_total: number; unassigned_total: number }>(
      `/projects/${pid}/tm-by-change-event`);
  }
  /** Spec-section submittal register — turnaround, ball-in-court, overdue. */
  submittalRegister(pid: string) {
    return this.json<{ submittal_count: number; open_count: number; overdue_count: number;
      avg_turnaround_days: number | null; by_section: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/submittals/register`);
  }
  /** Change-order log — CO value pipeline (pending/approved/executed), reason mix, schedule exposure. */
  coLog(pid: string) {
    return this.json<{ co_count: number; total_value: number; pending_value: number;
      approved_value: number; executed_value: number; total_schedule_days: number;
      change_events_open: number; change_event_rom_exposure: number;
      by_reason: Record<string, number>; ball_in_court: Record<string, number>;
      rows: Record<string, unknown>[] }>(`/projects/${pid}/change-orders/log`);
  }
  /** Meeting & action-item tracker — open/overdue by assignee, completion, meeting log. */
  actionTracker(pid: string) {
    return this.json<{ action_count: number; open_count: number; done_count: number;
      overdue_count: number; completion_pct: number | null; meeting_count: number;
      last_meeting: string | null; by_assignee: Record<string, number>;
      meetings_by_type: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/action-items/tracker`);
  }
  /** Executive project-health rollup — per-domain status, overall score, ranked attention items. */
  projectHealth(pid: string) {
    return this.json<{
      health_score: number | null; overall_status: string;
      open_items_total: number; overdue_items_total: number;
      domains: { key: string; label: string; status: string; headline: string;
        open_count: number; overdue_count: number }[];
      attention_items: { domain: string; status: string; issue: string }[];
    }>(`/projects/${pid}/health`);
  }
  /** Closeout analytics — punchlist completion/ball-in-court, commissioning, warranties, O&M. */
  closeoutSummary(pid: string) {
    return this.json<{
      punchlist: { punch_count: number; verified_count: number; open_count: number;
        overdue_count: number; complete_pct: number | null; open_cost: number;
        ball_in_court: Record<string, number>; by_trade: Record<string, number>;
        rows: Record<string, unknown>[] };
      commissioning: { cx_count: number; passed: number; failed: number; conditional: number;
        accepted: number; pass_rate: number | null };
      certificates: { cert_count: number; by_type: Record<string, number> };
      warranties: { warranty_count: number; active: number; expired: number; expiring_soon: number };
      om_manuals: { om_count: number; accepted: number; accepted_pct: number | null };
    }>(`/projects/${pid}/closeout/summary`);
  }
  /** Safety analytics — OSHA TRIR/DART/LTIFR, observation mix, toolbox coverage, violations. */
  safetySummary(pid: string, hours?: number) {
    const qs = hours != null ? `?hours=${hours}` : "";
    return this.json<{
      hours_estimated: boolean;
      incidents: { incident_count: number; recordable_count: number; dart_count: number;
        lost_time_count: number; total_lost_days: number; open_count: number; hours_worked: number;
        trir: number | null; dart_rate: number | null; ltifr: number | null;
        severity_rate: number | null; by_classification: Record<string, number>;
        rows: Record<string, unknown>[] };
      observations: { observation_count: number; safe_count: number; at_risk_count: number;
        closed_pct: number | null; safe_to_at_risk: number | null; by_category: Record<string, number> };
      toolbox_talks: { talk_count: number; total_attendees: number; avg_attendees: number | null };
      violations: { violation_count: number; open_count: number; overdue_count: number };
    }>(`/projects/${pid}/safety/summary${qs}`);
  }
  /** Field-log rollup — manpower trend, weather-impact lost-days, reporting coverage. */
  fieldLogSummary(pid: string) {
    return this.json<{ report_count: number; submitted_count: number; coverage_pct: number | null;
      total_manpower: number; avg_manpower: number | null;
      peak_manpower: { count: number; date: string | null }; weather_lost_days: number;
      delay_days: number; by_weather: Record<string, number>; by_impact: Record<string, number>;
      rows: Record<string, unknown>[] }>(`/projects/${pid}/daily-reports/summary`);
  }
  /** RFI register — ball-in-court, overdue, response turnaround, cost/schedule-impact exposure. */
  rfiRegister(pid: string) {
    return this.json<{ rfi_count: number; open_count: number; overdue_count: number;
      cost_impacted_count: number; schedule_impacted_count: number; avg_response_days: number | null;
      ball_in_court: Record<string, number>; by_discipline: Record<string, number>;
      by_priority: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/rfi/register`);
  }
  /** Spec-driven submittal log — required submittals per spec section vs logged, with missing gaps. */
  specSubmittalLog(pid: string) {
    return this.json<{ spec_count: number; required_total: number; logged_total: number;
      missing_total: number; coverage_pct: number | null; by_type: Record<string, number>;
      by_division: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/specs/submittal-log`);
  }
  /** Extract a typed submittal list from pasted spec text (AI when configured; rules fallback). */
  extractSubmittals(pid: string, text: string, create = false) {
    return this.json<{ items: { section_number?: string; title: string; type: string }[];
      source: string; message?: string; created_submittals?: number }>(
      `/projects/${pid}/specs/extract-submittals`, { method: "POST", body: JSON.stringify({ text, create }) });
  }
  /** Site feasibility / zoning envelope — max buildable GFA, unit yield, parking, vs. model GFA. */
  feasibility(pid: string, gfa?: number) {
    const qs = gfa != null ? `?gfa=${gfa}` : "";
    return this.json<{ error?: string; site?: string; jurisdiction?: string; use_type?: string;
      site_area_sf?: number; site_area_acres?: number; buildable_footprint_sf?: number | null;
      max_floors?: number | null; far_gfa_sf?: number | null; envelope_gfa_sf?: number | null;
      allowed_gfa_sf?: number | null; binding_constraint?: string | null; net_buildable_sf?: number | null;
      unit_yield?: number | null; parking_required?: number | null; open_space_required_sf?: number | null;
      constraints?: { constraint: string; limit_gfa_sf: number; basis: string }[];
      model?: { actual_gfa_sf: number; far_used: number; pct_of_allowed: number;
        headroom_gfa_sf: number; status: string } | null; warnings?: string[]; ref?: string }>(
      `/projects/${pid}/feasibility${qs}`);
  }
  /** Compare zoning schemes (one zoning record = one scheme) ranked by buildable yield. */
  feasibilityCompare(pid: string) {
    return this.json<{ count: number; best_ref?: string | null; warnings?: string[];
      scenarios: { ref?: string; site?: string; use_type?: string; far?: number | null;
        max_floors?: number | null; allowed_gfa_sf?: number | null; binding_constraint?: string | null;
        net_buildable_sf?: number | null; unit_yield?: number | null; parking_required?: number | null;
        delta_units?: number; delta_gfa_sf?: number }[] }>(
      `/projects/${pid}/feasibility/compare`);
  }
  /** Preconstruction estimate continuity — per-milestone totals + $/SF, drift, gap vs budget/GMP. */
  estimateContinuity(pid: string, budget?: number) {
    const qs = budget != null ? `?budget=${budget}` : "";
    return this.json<{ set_count: number; latest_total: number; latest_milestone: string | null;
      latest_psf: number | null; total_drift: number; total_drift_pct: number | null;
      budget: number | null; variance_to_budget: number | null; over_budget: boolean;
      milestones: string[]; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/precon/estimate-continuity${qs}`);
  }
  /** One-click: price the current model and save it as an estimate set at the given milestone. */
  preconSnapshot(pid: string, milestone: string) {
    return this.json<{ created: string; ref: string; total: number; milestone: string }>(
      `/projects/${pid}/precon/snapshot?milestone=${encodeURIComponent(milestone)}`, { method: "POST" });
  }
  /** Preconstruction decision log — by status/alignment + open cost & schedule exposure. */
  decisionLog(pid: string) {
    return this.json<{ decision_count: number; open_count: number; disputed_count: number;
      open_cost_exposure: number; open_schedule_exposure_days: number;
      by_alignment: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/precon/decisions`);
  }
  /** Assumptions & clarifications register — by status/category + open allowance exposure. */
  assumptionsRegister(pid: string) {
    return this.json<{ assumption_count: number; open_count: number; confirmed_count: number;
      open_cost_exposure: number; by_category: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/precon/assumptions`);
  }
  /** Value-engineering cycle — proposed/accepted/rejected savings; optional target gap. */
  veLog(pid: string, target?: number) {
    const qs = target != null ? `?target=${target}` : "";
    return this.json<{ ve_count: number; proposed_savings: number; accepted_savings: number;
      rejected_savings: number; pipeline_savings: number; gap_after_accepted?: number;
      target_met?: boolean; by_status: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/precon/ve${qs}`);
  }
  /** Calibrate-style preconstruction alignment — per-domain RAG + alignment score. */
  preconAlignment(pid: string) {
    return this.json<{ alignment_score: number | null; overall_status: string; latest_milestone: string | null;
      latest_total: number; budget: number | null; variance_to_budget: number | null;
      ve_accepted: number; ve_pipeline: number; open_decisions: number; open_assumptions: number;
      domains: { key: string; label: string; status: string; headline: string }[] }>(
      `/projects/${pid}/precon/alignment`);
  }
  /** Quality dashboard — inspection pass-rate KPIs, NCR loop, deficiency ball-in-court. */
  qualitySummary(pid: string) {
    return this.json<{
      inspections: { total: number; passed: number; failed: number; conditional: number;
        pass_rate: number | null; first_pass_yield: number | null;
        by_result: Record<string, number>; by_type: Record<string, number> };
      ncrs: { ncr_count: number; open_count: number; overdue_count: number;
        avg_days_to_close: number | null; by_disposition: Record<string, number>;
        by_severity: Record<string, number>; rows: Record<string, unknown>[] };
      deficiencies: { deficiency_count: number; open_count: number; overdue_count: number;
        ball_in_court: Record<string, number>; by_trade: Record<string, number>;
        rows: Record<string, unknown>[] };
    }>(`/projects/${pid}/quality/summary`);
  }
  /** ITB tracking — invited vs responded vs bonded per package + coverage gaps. */
  itb(pid: string) {
    return this.json<{ package_count: number; total_invited: number; total_responses: number;
      packages_without_bids: number; rows: Record<string, unknown>[] }>(`/projects/${pid}/bidding/itb`);
  }
  /** Invite companies to bid on a package (records the invitee list). */
  inviteBidders(pid: string, packageId: string, companies: string[]) {
    return this.json<{ bidders_invited: number; invited_companies: string[] }>(
      `/projects/${pid}/bidding/packages/${packageId}/invite`,
      { method: "POST", body: JSON.stringify({ companies }) });
  }

  // --- contract documents (generate / scope library / sign) -----------------
  /** URL of a generated contract document — doc = agreement | prime | co | exhibit. */
  contractDocUrl(pid: string, key: string, rid: string, doc: string, clauses?: string, attach = false) {
    const q = new URLSearchParams({ doc, ...(clauses ? { clauses } : {}), ...(attach ? { attach: "1" } : {}) }).toString();
    return this.url(`/projects/${pid}/contracts/${key}/${rid}/document.pdf?${q}`);
  }
  /** Scope-of-work clause library for composing Exhibit A. */
  scopeLibrary() {
    return this.json<{ clauses: { id: string; category: string; title: string; trade?: string | null }[] }>(`/scope-library`);
  }
  /** Record a party's signature (typed name) on a contract / change order. */
  signContract(pid: string, key: string, rid: string, party: string, name: string) {
    return this.json<{ signatures: { party: string; name: string; signed_at: string; method: string }[] }>(
      `/projects/${pid}/contracts/${key}/${rid}/sign`, { method: "POST", body: JSON.stringify({ party, name }) });
  }
  /** Apply a certificate-based PAdES digital signature to the contract document (tamper-evident). */
  digitalSignContract(pid: string, key: string, rid: string) {
    return this.json<{ signed: boolean; fingerprint: string; kind: string }>(
      `/projects/${pid}/contracts/${key}/${rid}/digital-sign`, { method: "POST", body: "{}" });
  }
  /** Whether server-side E57 → .xyz point-cloud conversion is available (needs optional pye57). */
  e57Status() {
    return this.json<{ available: boolean; max_points: number; message: string }>(`/convert/e57/status`);
  }
  /** Convert an uploaded .e57 scan to a decimated .xyz point cloud (server-side). Returns the blob. */
  async convertE57(file: File): Promise<Blob> {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/convert`), { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `convert failed (${res.status})`);
    return res.blob();
  }
  /** Digital-signature capability — built-in PAdES + the optional 3rd-party bridge (DocuSeal etc.). */
  esignStatus() {
    return this.json<{ pades: { available: boolean; kind: string };
      bridge: { enabled: boolean; provider: string | null; implemented: boolean; message: string } }>(
      `/esign/status`);
  }
  /** Route a contract/CO through the configured 3rd-party e-signature provider (DocuSeal etc.). */
  sendForSignature(pid: string, key: string, rid: string, signers: { email: string; name?: string; party?: string }[]) {
    return this.json<{ provider: string; submission_id: number | string | null;
      signers: { email: string; role: string; url: string | null }[]; status: string }>(
      `/projects/${pid}/contracts/${key}/${rid}/send-for-signature`,
      { method: "POST", body: JSON.stringify({ signers }) });
  }
  /** Triage an RFI (AI): category / discipline / urgency / ball-in-court + a draft response. */
  triageRfi(pid: string, rid: string) {
    return this.json<{ ai_enabled: boolean; source: string; discipline: string; category: string;
      urgency: string; ball_in_court: string; draft_response: string }>(
      `/projects/${pid}/ai/triage-rfi`, { method: "POST", body: JSON.stringify({ rid }) });
  }
  /** Draft a Bill of Quantities from a plain-text project description (AI; stub without a key). */
  aiEstimate(pid: string, description: string) {
    return this.json<{ lines: { description: string; quantity: number; unit: string; rate: number; amount?: number; division?: string }[];
      total?: number; source: string; ai_enabled: boolean; message?: string }>(
      `/projects/${pid}/ai/estimate`, { method: "POST", body: JSON.stringify({ description }) });
  }
  /** Password login. If the account has MFA on, the reply is `{ mfa_required, mfa_token }` instead
   *  of a token — complete it with `mfaVerify(mfa_token, code)`. */
  login(username: string, password: string) {
    return this.json<{ token?: string; username: string; role?: string;
      mfa_required?: boolean; mfa_token?: string }>(
      "/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
  }
  /** Login step 2: exchange the challenge ticket + a TOTP or recovery code for a session. */
  mfaVerify(mfaToken: string, code: string) {
    return this.json<{ token: string; username: string; role: string }>(
      "/auth/mfa/verify", { method: "POST", body: JSON.stringify({ mfa_token: mfaToken, code }) });
  }
  mfaStatus() {
    return this.json<{ enabled: boolean; pending: boolean; recovery_remaining: number }>("/auth/mfa/status");
  }
  mfaSetup() {
    return this.json<{ secret: string; otpauth_uri: string }>("/auth/mfa/setup", { method: "POST" });
  }
  mfaEnable(code: string) {
    return this.json<{ enabled: boolean; recovery_codes: string[] }>(
      "/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code }) });
  }
  mfaDisable(password: string, code: string) {
    return this.json<{ enabled: boolean }>(
      "/auth/mfa/disable", { method: "POST", body: JSON.stringify({ password, code }) });
  }
  register(username: string, password: string) {
    return this.json<{ username: string; role: string }>(
      "/auth/register", { method: "POST", body: JSON.stringify({ username, password }) });
  }
  me() {
    return this.json<{ username: string; role: string | null; authenticated: boolean;
      tier?: string; features?: Record<string, boolean>; platform_admin?: boolean }>("/auth/me");
  }
  logout() {
    return this.json<{ ok: boolean }>("/auth/logout", { method: "POST" }).catch(() => ({ ok: false }));
  }
  /** Change your own password (requires the current one). The server revokes all other sessions
   *  and returns a fresh token for this tab; adopt it so the current session keeps working. */
  async changePassword(current: string, next: string) {
    const r = await this.json<{ ok: boolean; token?: string }>(
      "/auth/password", { method: "POST", body: JSON.stringify({ current, new: next }) });
    if (r.token) this.setToken(r.token);
    return r;
  }
  /** Sign out of every other session (revoke all outstanding tokens); keeps this tab signed in
   *  via the fresh token the server returns. Use after a suspected token leak. */
  async logoutAll() {
    const r = await this.json<{ ok: boolean; token?: string }>("/auth/logout-all", { method: "POST" });
    if (r.token) this.setToken(r.token);
    return r;
  }
  /** Admin: force-revoke all of a user's outstanding sessions (offboarding / lost device). */
  revokeUserSessions(username: string) {
    return this.json<{ ok: boolean }>(
      `/auth/users/${encodeURIComponent(username)}/revoke-sessions`, { method: "POST" });
  }

  // --- admin: user management --------------------------------------------
  listUsers() {
    return this.json<AccountUser[]>("/auth/users");
  }
  /** Admin: read the audit trail (newest first), optionally filtered. */
  auditLog(params: { action?: string; actor?: string; since?: string; limit?: number } = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) qs.set(k, String(v));
    return this.json<AuditEntry[]>(`/audit${qs.toString() ? `?${qs}` : ""}`);
  }
  /** Admin: the error-log feed (server 500s + reported client errors), newest first. */
  errorLog(params: { source?: string; level?: string; since_hours?: number; limit?: number } = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v != null && v !== "") qs.set(k, String(v));
    return this.json<{ stats: { total: number; by_source: Record<string, number>; [k: string]: unknown };
      errors: { id: string; ts: string; source: string; level: string; kind: string | null;
        message: string | null; method: string | null; path: string | null; status: number | null;
        actor: string | null; project_id: string | null; request_id: string | null;
        traceback: string | null; detail: Record<string, unknown> | null }[] }>(
      `/admin/errors${qs.toString() ? `?${qs}` : ""}`);
  }
  /** Admin: prune the error log to its retention cap. */
  clearErrorLog() {
    return this.json<{ pruned: number }>("/admin/errors", { method: "DELETE" });
  }
  /** Report a browser-side error to the server feed. Fire-and-forget: never throws into the app. */
  reportClientError(e: { message: string; kind?: string; path?: string; level?: string;
    detail?: Record<string, unknown> }): void {
    void fetch(this.url("/client-errors"),
      { method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json", ...this.authHeaders() },
        body: JSON.stringify(e), keepalive: true }).catch(() => { /* best-effort */ });
  }
  createUser(username: string, password: string, role: "admin" | "user" = "user", email?: string) {
    return this.json<AccountUser>(
      "/auth/users", { method: "POST", body: JSON.stringify({ username, password, role, email }) });
  }
  updateUser(username: string, patch: { role?: "admin" | "user"; active?: boolean; email?: string }) {
    return this.json<AccountUser>(
      `/auth/users/${encodeURIComponent(username)}`, { method: "PATCH", body: JSON.stringify(patch) });
  }
  resetUserPassword(username: string, password: string) {
    return this.json<{ ok: boolean }>(
      `/auth/users/${encodeURIComponent(username)}/password`,
      { method: "POST", body: JSON.stringify({ password }) });
  }
  /** Admin: mint a single-use reset token for a user to set their own password. */
  issueResetToken(username: string) {
    return this.json<{ username: string; reset_token: string; expires_in: number }>(
      `/auth/users/${encodeURIComponent(username)}/reset-token`, { method: "POST" });
  }
  /** Unauthenticated: set a new password using a reset token (the token is the credential). */
  resetWithToken(token: string, next: string) {
    return this.json<{ ok: boolean; username: string }>(
      `/auth/reset`, { method: "POST", body: JSON.stringify({ token, new: next }) });
  }

  /** Absolute URL for a GET endpoint, e.g. an export download. */
  projects() {
    return this.json<{ id: string; name: string; model_kind?: "frag" | "ifc" | null }[]>(`/projects`);
  }
  /** One project's metadata, incl. model_kind + has_source_ifc (used to gate IFC-only tools). */
  project(pid: string) {
    return this.json<{ id: string; name: string; model_kind?: string | null; has_source_ifc?: boolean }>(
      `/projects/${pid}`);
  }
  /** Download URL for a project's portable .mmproj bundle (geometry + all data + blobs). */
  bundleUrl(pid: string) {
    return this.url(`/projects/${pid}/bundle`);
  }
  /** Create a blank project (no IFC needed) — GC portal + proforma work immediately. */
  createProject(name: string) {
    return this.json<{ id: string; name: string }>("/projects", { method: "POST", body: JSON.stringify({ name }) });
  }
  /** Delete a project and everything it owns (rows + geometry + blobs). */
  deleteProject(pid: string) {
    return this.json<{ deleted: boolean; id: string; rows: Record<string, number> }>(
      `/projects/${pid}`, { method: "DELETE" });
  }
  /** Open a .mmproj bundle as a new project (fresh id). */
  async importBundle(file: File, name?: string) {
    const fd = new FormData();
    fd.append("file", file);
    if (name) fd.append("name", name);
    const res = await fetch(this.url(`/projects/import-bundle`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`import -> ${res.status}`);
    return res.json() as Promise<{ id: string; name: string; model_kind?: string | null }>;
  }
  /** Heartbeat presence (optionally sharing the current camera viewpoint) → live peer roster. */
  presence(pid: string, viewpoint?: unknown) {
    return this.json<{ user: string; active: { user: string; seconds_ago: number; viewpoint: { position: Vec3; target: Vec3 } | null }[] }>(
      `/projects/${pid}/presence`, { method: "POST", body: JSON.stringify({ viewpoint }) });
  }
  /** The caller's own effective role on a project (drives UI capability gating). */
  myRole(pid: string) {
    return this.json<{ user: string; role: ProjectRole | null; party_role: string | null; rbac: boolean }>(
      `/projects/${pid}/me`);
  }
  // --- project members (admin) -------------------------------------------
  members(pid: string) {
    return this.json<ProjectMember[]>(`/projects/${pid}/members`);
  }
  addMember(pid: string, body: { user: string; role: ProjectRole; party_role?: string | null; company?: string | null }) {
    return this.json<{ user: string; role: ProjectRole; party_role: string | null }>(
      `/projects/${pid}/members`, { method: "POST", body: JSON.stringify(body) });
  }
  removeMember(pid: string, user: string) {
    return this.json<{ ok: boolean }>(
      `/projects/${pid}/members/${encodeURIComponent(user)}`, { method: "DELETE" });
  }
  meta(pid: string) {
    return this.json<{ schema: string; counts: Record<string, number>; facets: { classes: string[]; storeys: string[] } }>(
      `/projects/${pid}/properties/meta`,
    );
  }

  /** The unified discipline tree (colors + IFC-class→discipline map). Project-independent, so cached
   * for the session — the viewer, model browser, and any legend share one served vocabulary. */
  private _discTree?: Promise<DisciplineTree>;
  disciplineTree(): Promise<DisciplineTree> {
    return (this._discTree ??= this.json<{ tree: DisciplineTree }>(`/reference/disciplines`).then((r) => r.tree));
  }

  // properties index (Phase 1 data)
  element(pid: string, guid: string) {
    return this.json<ElementProps>(`/projects/${pid}/elements/${guid}`);
  }
  /** 5D for an element: its schedule activity (%-complete, dates, hard-tied?) + cost-code budget. */
  element5d(pid: string, guid: string) {
    return this.json<{ guid: string; ifc_class: string | null; storey: string | null; name: string | null;
      schedule: { ref: string; name: string; trade: string | null; percent: number; start: string | null;
        finish: string | null; state: string | null; hard_tied: boolean } | null;
      cost: { code: string | null; ref: string | null; name: string | null; division: string | null;
        budget: number; committed: number; actual: number; eac: number; variance: number } | null }>(
      `/projects/${pid}/elements/${guid}/5d`);
  }
  /** Batch 5D heatmap: bucket every element GUID by schedule %-complete (by=progress) or cost
   *  variance (by=cost), for coloring the whole model. */
  elements5dMap(pid: string, by: "progress" | "cost" = "progress") {
    return this.json<{ by: string; buckets: Record<string, string[]>; counts: Record<string, number>; element_count: number }>(
      `/projects/${pid}/5d/heatmap?by=${by}`);
  }
  /** Placeable types ("families") in the project's source IFC, for the place-family picker and the
   *  type browser. Carries PredefinedType + how many occurrences reference each type. */
  types(pid: string) {
    return this.json<{ types: TypeRow[] }>(`/projects/${pid}/types`);
  }
  /** W10-1 type inspector: class, predefined, box dims, type Psets, material layers, occurrences. */
  typeDetail(pid: string, typeGuid: string) {
    return this.json<TypeDetail>(`/projects/${pid}/types/${encodeURIComponent(typeGuid)}`);
  }
  /** W10-1: author a custom family type (class + optional [w,d,h] box + PredefinedType + type Psets).
   *  Returns the new type GUID in `changed`. Versioned + GUID-stable via the /edit recipe path. */
  createType(pid: string, ifc_class: string, name: string, dims?: [number, number, number] | null,
             predefined?: string | null, psets?: Record<string, Record<string, unknown>> | null,
             publish = true) {
    return this.editIfc(pid, "create_type", { ifc_class, name, dims, predefined, psets }, publish);
  }
  /** W10-1: edit a type's params. Changing `dims` propagates to EVERY placed occurrence at once
   *  (shared RepresentationMap), GUID-stable — no re-placement. */
  editType(pid: string, type_guid: string, patch: { name?: string; dims?: [number, number, number];
             predefined?: string; psets?: Record<string, Record<string, unknown>> }, publish = true) {
    return this.editIfc(pid, "edit_type_params", { type_guid, ...patch }, publish);
  }
  /** W10-1: give a type an ordered IfcMaterialLayerSet ([{material, thickness(m)}]); occurrences inherit. */
  assignMaterialSet(pid: string, type_guid: string,
                    layers: { material: string; thickness: number }[], publish = true) {
    return this.editIfc(pid, "assign_material_set", { type_guid, layers }, publish);
  }
  /** W10-3: every IfcGroup (named set) and IfcElementAssembly (part-of whole) with member counts. */
  groups(pid: string) {
    return this.json<{ groups: GroupRow[]; assemblies: AssemblyRow[] }>(`/projects/${pid}/groups`);
  }
  /** W10-3 inspector: the members/parts of one group or assembly. */
  groupDetail(pid: string, guid: string) {
    return this.json<{ guid: string; kind: "group" | "assembly"; name: string; member_count: number;
      members: { guid: string; name: string; ifc_class: string }[] }>(
      `/projects/${pid}/groups/${encodeURIComponent(guid)}`);
  }
  /** W10-3: author an IfcGroup (named set) over the given element GUIDs (re-using a name adds to it). */
  createGroup(pid: string, name: string, guids: string[], publish = true) {
    return this.editIfc(pid, "create_group", { name, guids }, publish);
  }
  /** W10-3: aggregate the given elements into an IfcElementAssembly (a real part-of whole). */
  createAssembly(pid: string, name: string, guids: string[], predefined?: string | null, publish = true) {
    return this.editIfc(pid, "create_assembly", { name, guids, predefined }, publish);
  }
  /** W10-3: rectangular parametric array — nx×ny copies at pitch (dx,dy) m (dz per column). */
  arrayElement(pid: string, guid: string, nx: number, ny: number, dx: number, dy: number, dz = 0, publish = true) {
    return this.editIfc(pid, "array_element", { guid, nx, ny, dx, dy, dz }, publish);
  }
  /** W11 Track D: one element's attached carriers — classification codes + documents (details/instructions). */
  elementDetailing(pid: string, guid: string) {
    return this.json<{ guid: string; name: string; ifc_class: string;
      classifications: { system: string | null; code: string | null; title: string | null }[];
      documents: { identification: string | null; name: string | null; location: string | null; description: string | null }[] }>(
      `/projects/${pid}/detailing/${encodeURIComponent(guid)}`);
  }
  /** W11 Track D: classify elements with a keynote/spec/element code (UniFormat/MasterFormat/OmniClass). */
  classify(pid: string, guids: string[], system: string, code: string, name?: string, edition?: string, publish = true) {
    return this.editIfc(pid, "classify", { guids, system, code, name, edition }, publish);
  }
  /** W11 D3: auto-detail — run the condition→content rule set (e.g. exterior window → IBC flashing
   *  detail + 08 51 00), writing code/detail bundles to every matching element. */
  applyDetailingRules(pid: string, publish = true) {
    return this.editIfc(pid, "apply_detailing_rules", {}, publish);
  }
  /** W11 D3: IDS-style QA — elements that a rule applies to but are missing their required keynote/spec code. */
  validateDetailing(pid: string) {
    return this.json<{ rules_evaluated: number; gaps: number;
      elements: { rule: string; guid: string; name: string; missing: string }[] }>(
      `/projects/${pid}/detailing/rules/validate`);
  }
  /** W11 Track D: attach a document (detail drawing / installation instruction) to elements. */
  attachDocument(pid: string, guids: string[], name: string,
                 opts: { location?: string; identification?: string; description?: string; purpose?: string } = {}, publish = true) {
    return this.editIfc(pid, "attach_document", { guids, name, ...opts }, publish);
  }
  /** G3: attach an O&M / warranty document reference (purpose-tagged) to elements — turnover paperwork
   *  bound to the physical asset; surfaced in the as-built summary's `with_om_docs`. */
  attachOmDocument(pid: string, guids: string[], name: string,
                   opts: { location?: string; kind?: "om" | "warranty" } = {}, publish = true) {
    return this.editIfc(pid, "attach_om_document", { guids, name, ...opts }, publish);
  }
  /** W11 B6: author a base plate + anchor bolts under a steel column (fabrication assembly). */
  addBasePlate(pid: string, columnGuid: string, opts: { bolts?: number; width?: number; depth?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_base_plate", { column_guid: columnGuid, ...opts }, publish);
  }
  /** W11 B6: author a shear tab + bolts at a steel beam end (fabrication assembly). */
  addShearTab(pid: string, beamGuid: string, opts: { bolts?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_shear_tab", { beam_guid: beamGuid, ...opts }, publish);
  }
  /** W11 B6: author a reinforcement cage (longitudinal bars + stirrups) in a concrete column. */
  addRebarCage(pid: string, columnGuid: string,
               opts: { bar_size?: string; tie_size?: string; cover?: number; tie_spacing?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_rebar_cage", { column_guid: columnGuid, ...opts }, publish);
  }
  /** Natural-language authoring: interpret a plain-English instruction into a validated plan of
   *  {recipe, params} (no execution — apply each step via editIfc after the user confirms). */
  aiAuthor(pid: string, text: string, context: { selected_guids?: string[]; active_storey?: string } = {}) {
    return this.json<{ source: string; needs_clarification: string | null;
      plan: { recipe: string; params: Record<string, unknown>; summary?: string; ok: boolean; destructive: boolean; errors: string[] }[] }>(
      `/projects/${pid}/ai/author`, { method: "POST", body: JSON.stringify({ text, context }) });
  }
  /** W11 D6: the 3-part MasterFormat project manual seeded from the model. */
  specManual(pid: string) {
    return this.json<{ system: string; section_count: number; division_count: number; note: string;
      divisions: { division: string; title: string; sections: { code: string; title: string;
        element_count: number; part1_general: string; part2_products: string[]; part3_execution: string[] }[] }[] }>(
      `/projects/${pid}/spec/manual`);
  }
  /** S4: whether the model can be undone / redone + stack depths. */
  editHistory(pid: string) {
    return this.json<{ can_undo: boolean; can_redo: boolean; undo_depth: number; redo_depth: number }>(
      `/projects/${pid}/edit/history`);
  }
  /** S4: undo the last authoring edit (restore the prior model version + republish). */
  editUndo(pid: string, publish = true) {
    return this.json<{ restored: string; state: { can_undo: boolean; can_redo: boolean } }>(
      `/projects/${pid}/edit/undo`, { method: "POST", body: JSON.stringify({ publish }) });
  }
  /** S4: redo an undone edit. */
  editRedo(pid: string, publish = true) {
    return this.json<{ restored: string; state: { can_undo: boolean; can_redo: boolean } }>(
      `/projects/${pid}/edit/redo`, { method: "POST", body: JSON.stringify({ publish }) });
  }
  /** B3: give a wall a sloped top (start_height → end_height) for parapet/shed/gable walls. */
  setWallSlope(pid: string, guid: string, startHeight: number, endHeight: number, publish = true) {
    return this.editIfc(pid, "set_wall_slope", { guid, start_height: startHeight, end_height: endHeight }, publish);
  }
  /** B4: author an element from a raw triangle mesh (verts [[x,y,z]…], faces [[i,j,k]…] 0-based). */
  addMesh(pid: string, verts: number[][], faces: number[][], name = "Mesh", publish = true) {
    return this.editIfc(pid, "add_mesh_representation", { verts, faces, name }, publish);
  }
  /** UX-2: place a 2D text annotation (note / tag / callout) as an IfcAnnotation at an [E,N] point. */
  addAnnotation(pid: string, point: [number, number], text: string,
                opts: { kind?: "note" | "tag" | "callout"; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_annotation", { point, text, ...opts }, publish);
  }
  /** UX-2: place a dimension annotation (line + measured distance) between two [E,N] points. */
  addDimension(pid: string, start: [number, number], end: [number, number],
               opts: { text?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_dimension", { start, end, ...opts }, publish);
  }
  /** UX-2: place a revision cloud (scalloped outline + optional delta/number tag) around a region —
   *  two opposite [E,N] corners, or >=3 boundary points. Renders on the generated plan. */
  addRevisionCloud(pid: string, points: [number, number][],
                   opts: { tag?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_revision_cloud", { points, ...opts }, publish);
  }
  /** UX-2: place an element-aware tag on a host element — the label is auto-read from the host
   *  (its Name / Pset mark / type), or overridden with `text`; assigned to the element it labels. */
  addTag(pid: string, hostGuid: string,
         opts: { text?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_tag", { host_guid: hostGuid, ...opts }, publish);
  }
  /** A4: a compact scene digest of the model (counts by class, storeys, spaces, MEP, phasing, LOD, hygiene
   * + a one-paragraph prose overview) — grounds the AI command bar and gives a one-glance summary. */
  sceneDigest(pid: string) {
    return this.json<{ totals: { elements: number; storeys: number; spaces: number };
      by_class: Record<string, number>; storeys: string[]; prose: string;
      mep: { systems: number; has_fire_protection: boolean; by_discipline: Record<string, { systems: number; members: number }> };
      phasing: Record<string, number>; lod: Record<string, number>;
      hygiene: { issues: number | null; clean: boolean | null } }>(`/projects/${pid}/scene-digest`);
  }
  /** CONTENT-1: the curated content catalog (logistics / furniture / landscaping → IFC class + phase). */
  contentCatalog() {
    return this.json<{ count: number; note: string; groups: Record<string, { key: string; ifc_class: string;
      phase: string | null; classification: string; default_dims_m: number[] }[]> }>(`/content/catalog`);
  }
  /** CONTENT-1: place a catalogued content item at an [E,N] point (optionally with a supplied mesh). */
  placeContent(pid: string, category: string, point: [number, number], name?: string, publish = true) {
    return this.editIfc(pid, "place_content", { category, point, ...(name ? { name } : {}) }, publish);
  }
  /** CONTENT-1 (import): upload a detailed mesh (glTF/GLB/OBJ/STL/PLY) → auto-classified + placed as the
   *  right IFC via place_content. Category auto-detected from the filename unless given. */
  async importContent(pid: string, file: File, opts: { category?: string; e?: number; n?: number;
      scale?: number; name?: string; storey?: string } = {}) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts)) if (v !== undefined && v !== "") q.set(k, String(v));
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(this.url(`/projects/${pid}/content/import?${q.toString()}`),
      { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.json() as Promise<{ guid: string; ifc_class: string; category: string; faces: number; publish?: string }>;
  }
  /** W11 E8: validate an edit's params against the authoring guardrails without applying it. */
  editPrecheck(pid: string, recipe: string, params: Record<string, unknown>) {
    return this.json<{ ok: boolean; errors: string[]; warnings: string[] }>(
      `/projects/${pid}/edit/precheck`, { method: "POST", body: JSON.stringify({ recipe, params }) });
  }
  /** W11 G1: LOD-500 readiness — share of the model field-verified as-built, by method. */
  lod500(pid: string) {
    return this.json<{ total: number; verified: number; unverified: number; readiness_pct: number;
      by_method: Record<string, number>; methods: string[]; prop: string;
      with_manufacturer: number; with_serial: number; with_dimensions: number; dimensions_out_of_tolerance: number;
      with_om_docs?: number; om_documents?: string[] }>(`/projects/${pid}/lod500`);
  }
  /** W11 G2: record a field-verified as-built dimension (+ variance vs design) on the selection. */
  recordAsbuiltDimension(pid: string, guids: string[], dimension: string, measured: number, design?: number, publish = true) {
    return this.editIfc(pid, "record_asbuilt_dimension", { guids, dimension, measured, ...(design != null ? { design } : {}) }, publish);
  }
  /** W11 G1: stamp elements as field-verified as-built (Massing_AsBuilt) — the LOD-500 reliability layer. */
  verifyAsbuilt(pid: string, guids: string[], opts: { verified_by?: string; method?: string; note?: string } = {}, publish = true) {
    return this.editIfc(pid, "verify_asbuilt", { guids, ...opts }, publish);
  }
  /** W11 G3: stamp manufacturer / serial info (Pset_Manufacturer*) — the LOD-500 / O&M / turnover layer. */
  setManufacturerInfo(pid: string, guids: string[], opts: { manufacturer?: string; model_label?: string; production_year?: string; serial?: string; barcode?: string } = {}, publish = true) {
    return this.editIfc(pid, "set_manufacturer_info", { guids, ...opts }, publish);
  }
  /** W11 B6: author an IfcCurtainWall (mullions + transoms + glazing panels) along a line. */
  addCurtainWall(pid: string, start: [number, number], end: [number, number],
                 opts: { height?: number; cols?: number; rows?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_curtain_wall", { start, end, ...opts }, publish);
  }
  /** W11 B6 + MEP-FP: MEP system browser — systems (with discipline: hvac/plumbing/electrical/fire/comms)
   * with segment/fitting/terminal counts + connectivity signal, and a by-discipline rollup. */
  mepSummary(pid: string) {
    return this.json<{ total_systems: number; unassigned: { segments: number; fittings: number };
      has_fire_protection?: boolean; by_discipline?: Record<string, { systems: number; members: number }>;
      systems: { guid: string; name: string; discipline?: string; predefined_type?: string | null;
        members: number; segments: number; fittings: number;
        terminals: number; other: number; elements_with_open_ports: number }[] }>(`/projects/${pid}/mep`);
  }
  /** W10-4: MEP connectivity validation — ports connected/open, links, dangling (floating) elements. */
  mepConnectivity(pid: string) {
    return this.json<{ elements: number; ports_total: number; ports_connected: number; ports_open: number;
      connections: number; dangling_count: number; connected_pct: number;
      dangling: { guid: string; class: string; name: string | null }[] }>(`/projects/${pid}/mep/connectivity`);
  }
  /** MEP-SIZE: velocity/fill size checks over authored MEP (air/water velocity vs limits), pass/fail. */
  mepSizing(pid: string, opts?: { ductMaxFpm?: number; pipeMaxFps?: number }) {
    const q = new URLSearchParams();
    if (opts?.ductMaxFpm != null) q.set("duct_max_fpm", String(opts.ductMaxFpm));
    if (opts?.pipeMaxFps != null) q.set("pipe_max_fps", String(opts.pipeMaxFps));
    const qs = q.toString();
    return this.json<{
      checked: number; passed: number; failed: number; info: number; all_pass: boolean;
      limits: { duct_max_fpm: number; pipe_max_fps: number; tray_max_fill: number };
      checks: {
        guid: string; class: string; system: string | null; size_mm: number; shape: string;
        flow: number | null; flow_unit: string | null; parameter: string;
        value_fpm?: number; value_fps?: number; value?: number | null;
        limit_fpm?: number; limit_fps?: number; limit?: number;
        status: "pass" | "fail" | "info"; note: string;
      }[];
      disclaimer: string;
    }>(`/projects/${pid}/mep/sizing${qs ? `?${qs}` : ""}`);
  }
  /** MEP-FP: NFPA-13-informed sprinkler coverage pre-check (head count vs area ÷ max coverage per hazard). */
  sprinklerCoverage(pid: string, hazard = "light") {
    return this.json<{ hazard: string; sprinkler_heads: number; protected_area_m2: number; spaces_measured: number;
      max_coverage_m2_per_head: number; required_heads: number; adequate: boolean | null; shortfall: number | null;
      citation: string; note: string; verify: string }>(
      `/projects/${pid}/mep/sprinkler-coverage?hazard=${encodeURIComponent(hazard)}`);
  }
  /** W10-4: connect two MEP elements port-to-port (IfcRelConnectsPorts). */
  connectMep(pid: string, guidA: string, guidB: string, publish = true) {
    return this.editIfc(pid, "connect_mep", { guid_a: guidA, guid_b: guidB }, publish);
  }
  /** B5: record a physical connection between two elements (IfcRelConnectsElements, LOD-350 coordination). */
  connectElements(pid: string, guidA: string, guidB: string, description?: string, publish = true) {
    return this.editIfc(pid, "connect_elements", { guid_a: guidA, guid_b: guidB, ...(description ? { description } : {}) }, publish);
  }
  /** B5: the element-to-element connection graph (IfcRelConnectsElements) — pairs + per-element degree. */
  elementConnections(pid: string) {
    return this.json<{ count: number; elements_connected: number; max_degree: number;
      connections: { a: string; a_class: string; b: string; b_class: string; description: string | null }[] }>(
      `/projects/${pid}/element-connections`);
  }
  /** W11 B6: author a MEP fitting (elbow BEND / tee JUNCTION / TRANSITION) at a point, on a system. */
  addMepFitting(pid: string, ifcClass: string, point: [number, number],
                opts: { predefined?: string; size?: number; system?: string } = {}, publish = true) {
    return this.editIfc(pid, "add_mep_fitting", { ifc_class: ifcClass, point, ...opts }, publish);
  }
  /** W11 C4: computed door / window / room schedules from the model. */
  drawingSchedules(pid: string) {
    return this.json<Record<"doors" | "windows" | "rooms", { columns: string[]; rows: string[][] }>>(
      `/projects/${pid}/drawings/schedules`);
  }
  /** W11 F0: element LOD-stage distribution (100/200/300/350/400/500/unset). */
  lodSummary(pid: string) {
    return this.json<{ total: number; staged: number; prop: string;
      counts: Record<"100" | "200" | "300" | "350" | "400" | "500" | "UNSET", number> }>(
      `/projects/${pid}/lod`);
  }
  /** W11 F0: tag elements with a LOD stage (element maturity 100→500). */
  setLod(pid: string, guids: string[], stage: "100" | "200" | "300" | "350" | "400" | "500", publish = true) {
    return this.editIfc(pid, "set_lod", { guids, stage }, publish);
  }
  /** W11 F0: establish the view-keyed representation contexts (Model+Plan; Body/Axis/Box/Annotation/
   *  FootPrint) the drawing pipeline needs. Idempotent. */
  ensureContexts(pid: string, publish = false) {
    return this.editIfc(pid, "ensure_contexts", {}, publish);
  }
  /** W11: power selection via the IfcOpenShell selector DSL — e.g. `IfcWall`, `IfcWall, IfcDoor`,
   *  `IfcWall, Pset_WallCommon.FireRating=2HR`, `IfcElement, material=concrete`. */
  queryElements(pid: string, q: string, limit = 2000) {
    return this.json<{ query: string; count: number; truncated: boolean;
      elements: { guid: string; name: string; ifc_class: string; storey: string | null }[] }>(
      `/projects/${pid}/query?q=${encodeURIComponent(q)}&limit=${limit}`);
  }
  /** W10-8: element phase/status distribution (new · existing · demolish · temporary · unset). */
  phasing(pid: string) {
    return this.json<{ total: number; phased: number; prop: string;
      counts: Record<"NEW" | "EXISTING" | "DEMOLISH" | "TEMPORARY" | "UNSET", number> }>(
      `/projects/${pid}/phasing`);
  }
  /** W10-8: tag elements with a construction phase (new | existing | demolish | temporary). */
  setPhase(pid: string, guids: string[], phase: "new" | "existing" | "demolish" | "temporary", publish = true) {
    return this.editIfc(pid, "set_phase", { guids, phase }, publish);
  }
  /** AI-draft an RFI from an element's context (Claude when keyed, else a template draft). */
  draftRfi(pid: string, element: unknown, note?: string) {
    return this.json<{ ai_enabled: boolean; subject: string; question: string; discipline: string; suggested_priority: string; source: string }>(
      `/projects/${pid}/ai/draft-rfi`, { method: "POST", body: JSON.stringify({ element, note }) });
  }
  elements(pid: string, params: { ifc_class?: string; storey?: string; limit?: number } = {}) {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return this.json<ElementProps[]>(`/projects/${pid}/elements?${q}`);
  }
  /** Properties you can colour the model by (attributes + pset/qto props), for the picker. */
  colorFacets(pid: string) {
    return this.json<{ attributes: { prop: string; label: string; distinct: number }[];
      properties: { prop: string; label: string; distinct: number }[] }>(
      `/projects/${pid}/elements/facets-list`);
  }
  /** Bucket every element by a property → colour buckets (numeric binned, categorical grouped). */
  colorBy(pid: string, prop: string, bins = 6) {
    return this.json<{ prop: string; kind: "numeric" | "categorical"; total: number; colored: number;
      unset: number; buckets: { label: string; count: number; guids: string[] }[] }>(
      `/projects/${pid}/elements/color-by?prop=${encodeURIComponent(prop)}&bins=${bins}`);
  }
  /** BIM data-completeness check: per-attribute present/missing + non-compliant guids to highlight. */
  dataQa(pid: string) {
    return this.json<{ total: number; compliant: number; noncompliant: number; compliant_pct: number;
      rules: { key: string; label: string; severity: string; present: number; missing: number; missing_guids: string[] }[];
      noncompliant_guids: string[] }>(`/projects/${pid}/elements/qa`);
  }
  /** Speckle interoperability bridge status (open-source, self-hostable; off unless configured). */
  speckleStatus() {
    return this.json<{ enabled: boolean; connected: boolean; server: string | null; server_name?: string;
      message: string }>(`/interop/speckle/status`);
  }
  /** Convert an uploaded CityGML (.gml) to a GeoJSON FeatureCollection of building footprints. */
  async convertCityGml(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/convert/citygml`), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.status }))).detail || `CityGML -> ${res.status}`);
    return res.json() as Promise<{ type: string; features: unknown[]; meta: { buildings: number } }>;
  }
  /** Code-readiness check: does the model carry the data a plan review needs (property-level). */
  codeCheck(pid: string) {
    return this.json<{ code: string; rules: number; checked: number; passed: number; readiness_pct: number;
      checks: { id: string; label: string; code: string; note: string; applies: string; checked: number;
        passed: number; failed: number; below_min: number; fail_guids: string[]; status: string }[];
      fail_guids: string[] }>(`/projects/${pid}/elements/code-check`);
  }
  // W9-2 computed occupancy load (IBC 1004) + egress capacity (IBC 1005) — pre-check assist
  codecheckEgress(pid: string) {
    return this.json<{
      building: { occupant_load: number; area_ft2: number; spaces: number; spaces_missing_area: number };
      egress: { required_width_in: number; provided_width_in: number; adequate: boolean | null; factor_in_per_occ: number; code: string };
      doors: { checked: number; below_min_32in: number; fail_guids: string[]; min_clear_m: number; code: string };
      by_occupancy: { occupancy: string; factor: number; basis: string; spaces: number; area_ft2: number; load: number }[];
      spaces: { guid: string; name: string | null; occupancy: string; area_ft2: number | null; load: number | null; needs_2_exits?: boolean; note?: string }[];
      citations: string[]; disclaimer: string;
    }>(`/projects/${pid}/codecheck/egress`);
  }
  /** W11 D1: the IBC code-analysis summary (occupancy, construction type, area/stories, occupant load,
   *  egress, governing sections) for the G-series code sheet. */
  codeAnalysis(pid: string, opts: { occupancy_group?: string; construction_type?: string; sprinklered?: boolean; jurisdiction?: string } = {}) {
    const q = new URLSearchParams();
    if (opts.occupancy_group) q.set("occupancy_group", opts.occupancy_group);
    if (opts.construction_type) q.set("construction_type", opts.construction_type);
    if (opts.sprinklered) q.set("sprinklered", "true");
    if (opts.jurisdiction) q.set("jurisdiction", opts.jurisdiction);
    return this.json<{ code_context: { jurisdiction: string | null; ibc_edition: number | null; resolved: boolean; as_of: number | null; verify: string };
      occupancy: { group: string; primary: string; mix: string[] };
      construction_type: string; sprinklered: boolean;
      building: { gross_area_ft2: number; stories: number; occupant_load: number };
      occupant_load_by_occupancy: { occupancy: string; load: number; area_ft2: number }[];
      egress: { required_width_in: number; provided_width_in: number; adequate: boolean | null };
      doors: { checked: number; below_min_32in: number };
      allowable: { note: string; sections: string[]; sprinkler_increase: string };
      citations: string[]; disclaimer: string }>(`/projects/${pid}/codecheck/analysis?${q.toString()}`);
  }
  /** CODE-1: resolve a jurisdiction (USPS state code) to its adopted code editions (baseline fallback). */
  codeAdoptions(jurisdiction: string) {
    return this.json<{ jurisdiction: string | null; resolved: boolean; as_of: number | null;
      codes: { family: string; edition: number; name: string; source: string }[];
      primary: { IBC: number | null; IECC: number | null; "A117.1": number | null }; verify: string }>(
      `/codes/adoptions?jurisdiction=${encodeURIComponent(jurisdiction)}`);
  }
  /** CODE-EBC: classify an existing-building scope under the IEBC Work Area Method. `infer` first-guesses
   * the scope from the model's phasing (existing vs new/demolish); explicit flags override the guess. */
  ebcClassify(pid: string, opts: { jurisdiction?: string; infer?: boolean; adds_area?: boolean;
    changes_occupancy?: boolean; reconfigures_space?: boolean; alters_openings?: boolean;
    alters_systems?: boolean; adds_equipment?: boolean; replaces_same_purpose?: boolean;
    repair_only?: boolean; work_area_pct?: number } = {}) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
    return this.json<{ ok: boolean; classification: string | null; classification_key?: string;
      method?: string; method_cite?: string; gist?: string; reason?: string;
      work_area_pct?: number | null; triggers?: string[];
      code: { family: string; edition: number | null; name?: string; jurisdiction: string | null; adoption_resolved?: boolean };
      applies?: { classification: string; section: string; requirements: string }[];
      citations?: { classification: string; section: string; requirements: string }[];
      methods: { key: string; name: string; cite: string; gist: string }[];
      notes?: string[]; inferred?: Record<string, unknown>; basis?: string[];
      phase_counts?: Record<string, number>; verify: string; disclaimer: string }>(
      `/projects/${pid}/codecheck/ebc?${q.toString()}`);
  }
  /** CODE-EBC: the IEBC reference catalog — compliance methods + Work-Area classifications with citations. */
  ebcPathways() {
    return this.json<{ code: { family: string; name: string };
      methods: { key: string; name: string; cite: string; gist: string }[];
      classifications: { key: string; label: string; class_cite: string; req_cite: string; gist: string }[];
      work_area_threshold_pct: number; verify: string; disclaimer: string }>(`/codes/ebc/pathways`);
  }
  /** EST-1: rough cost + duration estimate from the model's quantities (productivity rates). With
   * `full`, adds material + equipment cost lines (labour + material + equipment total). */
  laborEstimate(pid: string, loading = "commercial", rate = 25, full = false) {
    return this.json<{ loading: string; loading_factor: number; hourly_rate: number; line_count: number;
      total_man_hours: number; total_labor_cost: number; note: string; derived_from_model?: boolean;
      has_material_equipment?: boolean; total_material_cost?: number; total_equipment_cost?: number; total_cost?: number;
      lines: { activity: string; group: string; unit: string; quantity: number; man_hours: number;
        crew: number; crew_days: number; labor_cost: number;
        material_cost?: number; equipment_cost?: number; line_total?: number }[] }>(
      `/projects/${pid}/estimate/labor?loading=${encodeURIComponent(loading)}&rate=${rate}${full ? "&full=true" : ""}`);
  }
  /** RFI-0: decision-readiness audit — the information gaps a builder would ask about, ranked. */
  rfiReadiness(pid: string) {
    return this.json<{ ready: boolean; total_gaps: number; high_severity: number; summary: string; disclaimer: string;
      by_category: Record<string, number>;
      gaps: { category: string; severity: string; title: string; detail: string; fix: string; citation?: string;
        count?: number | null; guids?: string[] }[] }>(`/projects/${pid}/rfi/readiness`);
  }
  /** RFI-0: promote the decision-readiness gaps to BCF topics (one per gap, GUID-anchored, priority by severity). */
  rfiReadinessBcf(pid: string) {
    return this.json<{ created: number; topics: string[]; ready: boolean; high_severity: number }>(
      `/projects/${pid}/rfi/readiness/bcf`, { method: "POST", body: "{}" });
  }
  /** W11 D8: plan-reviewer approvability pre-flight (egress, door widths, occupancy, rated assemblies). */
  approvability(pid: string) {
    return this.json<{ checks: { check: string; citation: string; status: string; detail: string; guids?: string[] }[];
      summary: { passed: number; failed: number; gating: number; ready: boolean; score_pct: number | null };
      disclaimer: string }>(`/projects/${pid}/codecheck/approvability`);
  }
  codecheckEgressBcf(pid: string) {
    return this.json<{ created: number; topics: string[] }>(`/projects/${pid}/codecheck/egress/bcf`, { method: "POST", body: "{}" });
  }

  // W9-5 site logistics on the 4D timeline
  getLogistics(pid: string) {
    return this.json<{ resources: LogisticsResource[]; summary: { total: number; by_kind: Record<string, number>; start: string | null; end: string | null } }>(`/projects/${pid}/logistics`);
  }
  putLogistics(pid: string, resources: LogisticsResource[]) {
    return this.json<{ resources: LogisticsResource[] }>(`/projects/${pid}/logistics`, { method: "PUT", body: JSON.stringify({ resources }) });
  }
  logisticsState(pid: string, date?: string) {
    return this.json<{ date: string | null; active: LogisticsResource[]; active_count: number; total: number }>(`/projects/${pid}/logistics/state${date ? `?date=${encodeURIComponent(date)}` : ""}`);
  }

  // W9-4 semantic model graph (IFC relationships) — multi-hop, cited relational queries
  modelGraphStats(pid: string) {
    return this.json<{ nodes: number; edges: number; by_rel: Record<string, number> }>(`/projects/${pid}/graph`);
  }
  graphNeighbors(pid: string, guid: string, depth = 1) {
    return this.json<{
      root: string; found: boolean; depth?: number; neighbor_count?: number;
      nodes: { guid: string; class: string; name: string | null }[];
      edges: { from: string; to: string; rel: string }[];
      paths: { guid: string; class: string; name: string | null; path: { rel: string; dir: string; to: string }[] }[];
    }>(`/projects/${pid}/graph/neighbors?guid=${encodeURIComponent(guid)}&depth=${depth}`);
  }

  // W9-4 (harder half) doc-graph: spec-section + document nodes linked to the elements they govern
  docGraph(pid: string) {
    return this.json<{
      spec_sections: { system: string | null; code: string; title: string; elements: string[] }[];
      documents: { name: string; sheet: string; elements: string[] }[];
      counts: { spec_sections: number; documents: number; edges: number };
      by_rel: Record<string, number>;
    }>(`/projects/${pid}/doc-graph`);
  }
  // the cited provenance of one element (spec sections · documents · location)
  elementSources(pid: string, guid: string) {
    return this.json<{
      guid: string; found: boolean; name?: string | null; class?: string;
      spec_sections?: { system: string | null; code: string; title: string }[];
      documents?: { name: string; sheet: string }[];
      container?: { guid: string | null; name: string | null; class: string } | null;
      citations: { kind: string; ref: string; title?: string; sheet?: string; source: string }[];
    }>(`/projects/${pid}/elements/${encodeURIComponent(guid)}/sources`);
  }
  // RFI-0 NL-QA: a plain-language question -> a cited answer from the model's own data
  rfiQa(pid: string, question: string) {
    return this.json<{
      question: string; intent: string; answer: string;
      citations: { kind: string; ref: string; source?: string; guids?: string[] }[];
      disclaimer: string; found?: boolean; ready?: boolean;
    }>(`/projects/${pid}/rfi/qa`, { method: "POST", body: JSON.stringify({ question }) });
  }

  // W10-7 structural analytical model (IfcStructuralAnalysisModel derived from the physical frame)
  analyticalSummary(pid: string) {
    return this.json<{
      analysis_models: { guid: string; name: string | null; predefined_type: string | null }[];
      curve_members: number; surface_members: number; point_connections: number;
      load_cases: (string | null)[]; load_groups: (string | null)[]; has_model: boolean;
    }>(`/projects/${pid}/analytical`);
  }

  // STRUCT-SOLVE: apply a gravity load case to the analytical members + a determinate statics solve
  structureSolve(pid: string, opts?: {
    liveOccupancy?: string; sdlPsf?: number; slabThicknessIn?: number;
    tributaryFt?: number; grossAreaSf?: number; eKsi?: number; iIn4?: number;
  }) {
    const q = new URLSearchParams();
    if (opts?.liveOccupancy) q.set("live_occupancy", opts.liveOccupancy);
    if (opts?.sdlPsf != null) q.set("sdl_psf", String(opts.sdlPsf));
    if (opts?.slabThicknessIn != null) q.set("slab_thickness_in", String(opts.slabThicknessIn));
    if (opts?.tributaryFt != null) q.set("tributary_ft", String(opts.tributaryFt));
    if (opts?.grossAreaSf != null) q.set("gross_area_sf", String(opts.grossAreaSf));
    if (opts?.eKsi != null) q.set("e_ksi", String(opts.eKsi));
    if (opts?.iIn4 != null) q.set("i_in4", String(opts.iIn4));
    const qs = q.toString();
    type Diagram = { x_ft: number; shear_kip: number; moment_kipft: number; deflection_in: number };
    type Beam = {
      name: string; guid: string; length_ft: number;
      service: {
        reaction_kip: number; shear_max_kip: number; moment_max_kipft: number;
        deflection_in: number; deflection_limit_in: number; deflection_ok: boolean; diagram: Diagram[];
      };
      factored: Beam["service"];
    };
    return this.json<{
      has_analytical: boolean; message?: string;
      load_case?: {
        name: string; dead_klf: number; live_klf: number; service_klf: number;
        factored_lrfd_klf: number; dead_psf: number; live_psf: number; tributary_ft: number;
        governing_combo: string;
      };
      counts?: { beams: number; columns: number; total_beam_length_ft: number };
      governing_beam?: Beam | null; beams?: Beam[];
      columns_axial?: {
        service_total_kip: number; factored_lrfd_kip: number; storeys: number;
        column_count: number; note: string;
      } | null;
      reactions?: { sum_beam_service_kip: number };
      assumptions?: Record<string, unknown>; disclaimer?: string;
    }>(`/projects/${pid}/structure/solve${qs ? `?${qs}` : ""}`);
  }

  // COLLAB-1: live co-editing snapshot (model signature + presence roster)
  collabSnapshot(pid: string) {
    return this.json<{
      model: { source: string | null; version: number; element_count: number; has_model: boolean };
      editors: { user: string; seconds_ago: number; viewpoint: unknown }[]; editor_count: number;
    }>(`/projects/${pid}/collab`);
  }
  /** Subscribe to the model-edit SSE stream; onMessage fires with the collab snapshot on each change. */
  modelStream(pid: string, onMessage: (snap: unknown) => void): EventSource {
    const es = new EventSource(this.url(`/projects/${pid}/model/stream`));
    es.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch { /* ignore */ } };
    return es;
  }

  // AUTH-VS: execute a recipe graph (visual node authoring) as one GUID-stable pass
  editGraph(pid: string, graph: unknown, opts?: { publish?: boolean; baseSource?: string }) {
    return this.json<{ node_count: number; order: string[]; outputs: Record<string, unknown>; publish?: string }>(
      `/projects/${pid}/edit/graph`,
      { method: "POST", body: JSON.stringify({ graph, publish: opts?.publish ?? false, base_source: opts?.baseSource ?? null }) });
  }

  // W9-3 IFC5-style property-override layers (non-destructive composition over the model)
  getLayers(pid: string) {
    return this.json<{ layers: PropLayer[] }>(`/projects/${pid}/layers`);
  }
  putLayers(pid: string, layers: PropLayer[]) {
    return this.json<{ layers: PropLayer[] }>(`/projects/${pid}/layers`, { method: "PUT", body: JSON.stringify({ layers }) });
  }
  resolveLayers(pid: string) {
    return this.json<{
      layers: { name: string; enabled: boolean; overrides: number }[];
      overrides: { guid: string; pset: string; prop: string; base: unknown; effective: unknown; winning_layer: string; setters: string[] }[];
      conflicts: { guid: string; pset: string; prop: string; winning_layer: string; values: { layer: string; value: unknown }[] }[];
      effective_count: number; conflict_count: number;
    }>(`/projects/${pid}/layers/resolve`);
  }
  bakeLayers(pid: string) {
    return this.json<{ baked: number; publish?: string; message?: string }>(`/projects/${pid}/layers/bake`, { method: "POST", body: JSON.stringify({ publish: true }) });
  }

  // pins / topics (Phase 4)
  pins(pid: string) {
    return this.json<Topic[]>(`/projects/${pid}/pins`);
  }
  createTopic(pid: string, body: Partial<Topic>) {
    return this.json<Topic>(`/projects/${pid}/topics`, { method: "POST", body: JSON.stringify(body) });
  }
  viewpoints(pid: string, tid: string) {
    return this.json<Viewpoint[]>(`/projects/${pid}/topics/${tid}/viewpoints`);
  }
  addViewpoint(pid: string, tid: string, body: Partial<Viewpoint>) {
    return this.json<Viewpoint>(`/projects/${pid}/topics/${tid}/viewpoints`, {
      method: "POST", body: JSON.stringify(body),
    });
  }

  // analysis & QA (clash + IDS validation)
  runClash(pid: string, opts: { a?: string; b?: string; min_volume?: number; create_topics?: boolean } = {}) {
    const q = new URLSearchParams({ create_topics: "true", ...(opts as Record<string, string>) }).toString();
    return this.json<ClashResult>(`/projects/${pid}/clash?${q}`, { method: "POST" });
  }
  /** Federated (cross-discipline) clash across the project's layered models — primary source IFC +
   *  any appended discipline models. 409 if fewer than 2 are available. */
  clashFederated(pid: string, opts: { create_topics?: boolean; coordinate?: boolean; min_volume?: number; limit?: number } = {}) {
    const q = new URLSearchParams({ create_topics: String(opts.create_topics ?? true),
      ...(opts.coordinate != null ? { coordinate: String(opts.coordinate) } : {}),
      ...(opts.min_volume != null ? { min_volume: String(opts.min_volume) } : {}),
      ...(opts.limit != null ? { limit: String(opts.limit) } : {}) }).toString();
    return this.json<{ disciplines: string[]; count: number; created_topics: number; truncated: boolean;
      coordination: { run: string; new: number; active: number; resolved: number; reappeared: number;
        clash_count: number; group_count: number; reduction: number;
        by_discipline: Record<string, number>; by_severity: Record<string, number>; note: string } | null;
      clashes: { a_model: string; a_class: string; a_guid: string; b_model: string; b_class: string;
        b_guid: string; volume: number; method: "mesh" | "aabb"; point: Vec3 }[] }>(
      `/projects/${pid}/clash/federated?${q}`, { method: "POST" });
  }
  /** Clash coordination KPIs — status mix, worst discipline pairs, severity, aging, run burn-down. */
  clashMetrics(pid: string) {
    return this.json<{ total_issues: number; open: number; closed: number; resolution_rate: number;
      by_status: Record<string, number>; by_discipline: Record<string, number>;
      by_severity: Record<string, number>; aging: Record<string, number>; runs: number;
      reappearance_rate: number;
      burn_down: { run: string; new: number; resolved: number; reappeared: number; issues: number }[];
      note: string }>(`/projects/${pid}/clash/metrics`);
  }
  /** Model → field layout setout points (georeferenced; grids + column/footing/opening/wall). */
  layoutPoints(pid: string, classes?: string) {
    const q = classes ? `?classes=${encodeURIComponent(classes)}` : "";
    return this.json<{ count: number; by_class: Record<string, number>; truncated: boolean; note: string;
      points: { number: string; e: number; n: number; z: number; description: string; kind: string;
        ifc_class: string; guid: string }[] }>(`/projects/${pid}/layout/points${q}`);
  }
  /** PENZD/PNEZD points-CSV download URL for total stations / marking robots. */
  layoutCsvUrl(pid: string, order: "PENZD" | "PNEZD" = "PENZD", delimiter = ",", classes?: string) {
    const q = new URLSearchParams({ order, delimiter, ...(classes ? { classes } : {}) }).toString();
    return this.url(`/projects/${pid}/layout/points.csv?${q}`);
  }
  /** Layered DXF layout-drawing download URL for floor printers. */
  layoutDxfUrl(pid: string, classes?: string) {
    return this.url(`/projects/${pid}/layout.dxf${classes ? `?classes=${encodeURIComponent(classes)}` : ""}`);
  }
  /** Verify as-installed total-station shots against the design setout (deviation by point number). */
  layoutVerify(pid: string, measured: { number: string; e: number; n: number; z: number }[], toleranceM = 0.02) {
    return this.json<{ tolerance_m: number; checked: number; in_tolerance: number; max_deviation_m: number;
      out_of_tolerance: { number: string; guid: string; ifc_class: string; deviation_m: number }[]; note: string }>(
      `/projects/${pid}/layout/verify`, { method: "POST", body: JSON.stringify({ measured, tolerance_m: toleranceM }) });
  }
  /** Load-takedown defaults from the model — storey names/count + interior-column count. */
  loadsDefaults(pid: string) {
    return this.json<{ storey_names: string[]; storey_count: number; column_count: number }>(
      `/projects/${pid}/loads/defaults`);
  }
  /** Preliminary gravity load takedown → per-column/footing service + factored (ASCE 7) axial. */
  loadsTakedown(pid: string, params: { floor_area_sf?: number; storey_count?: number; occupancy?: string;
      column_count?: number; sdl_psf?: number; slab_thickness_in?: number; storeys?: unknown[] }) {
    return this.json<{ assumptions: Record<string, number>;
      storeys: { name: string; occupancy: string; area_sf: number; col_dead_kip: number; col_live_kip: number }[];
      column: { service_dead_kip: number; service_live_kip: number; service_total_kip: number;
        factored_lrfd_kip: number; factored_asd_kip: number };
      footing: { service_total_kip: number; factored_lrfd_kip: number };
      combinations: { governing_lrfd: { combo: string; kips: number }; governing_asd: { combo: string; kips: number } };
      disclaimer: string }>(`/projects/${pid}/loads/takedown`, { method: "POST", body: JSON.stringify(params) });
  }
  /** Verified-as-built vs claimed progress per schedule activity + the overall trust gap (③b). */
  verifiedProgress(pid: string) {
    return this.json<{ elements_total: number; elements_verified: number; elements_deviated: number;
      verified_pct: number; claimed_pct: number; trust_gap: number; coverage_pct: number;
      verification_records: number;
      activities: { ref: string; activity: string; trade: string | null; elements: number; verified: number;
        deviated: number; verified_pct: number; planned_pct: number | null; trust_gap: number }[] }>(
      `/projects/${pid}/verified-progress`);
  }
  /** Reverse deep-link — every record across pinnable modules tied to this element by GlobalId. */
  elementRecords(pid: string, guid: string) {
    return this.json<{ guid: string; total: number;
      modules: { module: string; module_name: string; icon: string; count: number;
        records: { ref: string | null; title: string; id: number; state: string | null }[] }[] }>(
      `/projects/${pid}/elements/${encodeURIComponent(guid)}/records`);
  }
  /** Composite Model Health scorecard — one score over hygiene + ISO 19650 KPIs + clash + verified. */
  modelHealth(pid: string) {
    return this.json<{ overall_score: number | null; band: string; scored_lenses: number; model_available: boolean;
      lenses: { key: string; label: string; tool: string; score: number | null; status: string; headline: string }[] }>(
      `/projects/${pid}/models/health`);
  }
  /** Discipline quantity roll-up — reinforcement tonnage, MEP linear runs, structural volume. */
  disciplineQuantities(pid: string) {
    return this.json<{ rebar: { count: number; weight_kg: number; tonnes: number; estimated: boolean };
      mep: { duct_m: number; pipe_m: number; cable_m: number; counts: Record<string, number> };
      structure: { element_volume_m3: number } }>(`/projects/${pid}/quantities/disciplines`);
  }
  /** Model integrity scan — duplicate GUIDs, orphaned elements, overlaps, unenclosed spaces, blank names. */
  modelQa(pid: string) {
    type Check = { count: number; [k: string]: unknown };
    return this.json<{ element_count: number; total_issues: number; clean: boolean;
      checks: { duplicate_guids: Check; orphaned_elements: Check; overlapping_duplicates: Check;
        unenclosed_spaces: Check & { total_spaces: number }; blank_names: Check & { of_elements: number } };
      note: string }>(`/projects/${pid}/models/qa`);
  }
  /** Shared-coordinates / setout basis — IfcMapConversion (E/N/height, true-north, scale) + CRS + LoGeoRef. */
  modelGeoreferencing(pid: string) {
    return this.json<{ georeferenced: boolean; level: number; level_label: string; note: string;
      map_conversion: { eastings: number | null; northings: number | null; orthogonal_height: number | null;
        true_north_bearing_deg: number | null; scale: number } | null;
      crs: { name: string | null; geodetic_datum: string | null; vertical_datum: string | null;
        map_projection: string | null; map_zone: string | null } | null;
      site: { ref_latitude: number[] | null; ref_longitude: number[] | null; ref_elevation: number | null } | null }>(
      `/projects/${pid}/models/georeferencing`);
  }
  /** Scan-to-BIM deviation — upload an as-built point cloud (XYZ/CSV) and compare it to the model surface. */
  async scanDeviation(pid: string, file: File, tolerance = 0.05) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/scan/deviation?tolerance=${tolerance}`),
      { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.status }))).detail || `scan -> ${res.status}`);
    return res.json() as Promise<{ point_count: number; reference_count: number; tolerance: number;
      within_tolerance: number; within_pct: number | null; out_of_tolerance: number;
      mean_deviation: number; max_deviation: number; p95_deviation: number;
      histogram: { band: string; count: number }[]; note: string }>;
  }
  /** Federation alignment report — do the discipline models share a storey scheme + georef origin? */
  modelAlignment(pid: string) {
    return this.json<{ models: { name: string; storey_count: number; error?: string;
        storeys: { name: string; elevation: number }[]; georef: Record<string, unknown> | null }[];
      issues: { type: string; severity: string; model: string; detail: string }[];
      aligned: boolean; message: string }>(`/projects/${pid}/models/alignment`);
  }
  /** Discipline models layered on a project (for federated clash). */
  projectModels(pid: string) {
    return this.json<{ id: string; discipline: string; created_at: string | null }[]>(`/projects/${pid}/models`);
  }
  async addProjectModel(pid: string, file: File, discipline: string) {
    const fd = new FormData(); fd.append("file", file); fd.append("discipline", discipline);
    const res = await fetch(this.url(`/projects/${pid}/models`), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `add model -> ${res.status}`); }
    return res.json() as Promise<{ id: string; discipline: string; size: number }>;
  }
  deleteProjectModel(pid: string, mid: string) {
    return this.json<{ deleted: boolean; id: string }>(`/projects/${pid}/models/${mid}`, { method: "DELETE" });
  }
  validate(pid: string) {
    return fetch(this.url(`/projects/${pid}/validate`), { method: "POST" }).then((r) => r.json() as Promise<ValidationResult>);
  }
  energy(pid: string) {
    return this.json<EnergyResult>(`/projects/${pid}/energy`);
  }
  mep(pid: string) {
    return this.json<{ by_class: Record<string, number>; systems: Record<string, string>; total_distribution_elements: number }>(`/projects/${pid}/mep`);
  }

  // 2D documentation
  drawingStoreys(pid: string) {
    return this.json<{ name: string | null; elevation: number; guid: string }[]>(`/projects/${pid}/drawings/storeys`);
  }

  // W9-1 property mapping / normalization — the transform verb between IDS-validate and COBie-export
  propmapDetect(pid: string) {
    return this.json<{ element_count: number; properties: { pset: string; prop: string; count: number; kind: string; sample: string }[] }>(
      `/projects/${pid}/propmap/detect`);
  }
  propmapPlan(pid: string, rules: PropMapRule[]) {
    return this.json<{ dry_run: boolean; changed: number; rules: { from: string; to: string; matched: number; cast: string; keep_source: boolean; samples: { guid: string; from: string; to: string }[] }[] }>(
      `/projects/${pid}/propmap/plan`, { method: "POST", body: JSON.stringify({ rules }) });
  }

  // real-estate development finance (Proforma)
  solveProforma(assumptions: unknown) {
    return this.json<ProformaResult>(`/proforma/solve`, { method: "POST", body: JSON.stringify(assumptions) });
  }
  /** Same solve, but the guardrails also validate the exit cap against the project's sale comps (U3). */
  solveProformaForProject(pid: string, assumptions: unknown) {
    return this.json<ProformaResult>(`/projects/${pid}/proforma/solve`,
      { method: "POST", body: JSON.stringify(assumptions) });
  }
  /** Three financial statements + tax for the current deal (income/balance/cash-flow + two-sided budget). */
  financials(assumptions: unknown) {
    return this.json<FinancialStatements>(`/proforma/financials`, { method: "POST", body: JSON.stringify(assumptions) });
  }
  sensitivity(body: unknown) {
    return this.json<{ metric: string; x_values: number[]; y_values: number[]; matrix: (number | null)[][] }>(
      `/proforma/sensitivity`, { method: "POST", body: JSON.stringify(body) });
  }
  monteCarlo(body: unknown) {
    return this.json<MonteCarloResult>(
      `/proforma/monte-carlo`, { method: "POST", body: JSON.stringify(body) });
  }
  forecast(assumptions: unknown, actuals: unknown[], asOfMonth: number) {
    return this.json<ProformaForecast>(`/proforma/forecast`, {
      method: "POST", body: JSON.stringify({ assumptions, actuals, as_of_month: asOfMonth }) });
  }
  portfolio() {
    return this.json<{ deal_count: number; totals: Record<string, number | null>; deals: { id: string; name: string; total_uses: number; equity: number; loan: number; equity_irr: number | null; equity_multiple: number | null }[] }>(`/proforma/portfolio`);
  }
  createScenario(name: string, projectId: string | null, assumptions: unknown) {
    return this.json<{ id: string }>(`/proforma/scenarios`, {
      method: "POST", body: JSON.stringify({ name, project_id: projectId, assumptions }) });
  }
  /** Saved proforma scenarios for a project (with their solved returns), oldest→newest. */
  listScenarios(projectId: string) {
    return this.json<{ id: string; name: string; project_id: string | null;
      returns: { equity_irr?: number | null; equity_multiple?: number | null; project_irr?: number | null;
        yield_on_cost?: number | null; npv?: number | null } | null }[]>(
      `/proforma/scenarios?project_id=${encodeURIComponent(projectId)}`);
  }
  drawPackage(sid: string, body: unknown) {
    return this.json<{ sov_lines_created: number; g702: Record<string, number>; g702_pdf: string }>(
      `/proforma/scenarios/${sid}/draw-package`, { method: "POST", body: JSON.stringify(body) });
  }

  // GC portal modules + model pins
  modules() {
    return this.json<ModuleDef[]>(`/modules`);
  }
  modulePins(pid: string) {
    return this.json<ModulePin[]>(`/projects/${pid}/module-pins`);
  }
  dashboard(pid: string, party?: string) {
    const q = party ? `?party=${encodeURIComponent(party)}` : "";
    return this.json<Dashboard>(`/projects/${pid}/dashboard${q}`);
  }
  moduleRecords(pid: string, key: string) {
    return this.json<ModuleRecord[]>(`/projects/${pid}/modules/${key}`);
  }
  moduleRecord(pid: string, key: string, rid: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}`);
  }
  createModuleRecord(pid: string, key: string, body: Record<string, unknown>) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}`, {
      method: "POST", body: JSON.stringify(body) });
  }
  /** Preconstruction intelligence — POST a contract/spec (file or text) for review. */
  private async reviewPost<T>(pid: string, kind: string, opts: { file?: File; text?: string; question?: string }) {
    const fd = new FormData();
    if (opts.file) fd.append("file", opts.file);
    if (opts.text != null) fd.append("text", opts.text);
    if (opts.question != null) fd.append("question", opts.question);
    const res = await fetch(this.url(`/projects/${pid}/review/${kind}`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Review ${kind} -> ${res.status}`);
    return res.json() as Promise<T>;
  }
  reviewContract(pid: string, opts: { file?: File; text?: string }) {
    return this.reviewPost<{ findings: { clause: string; severity: "high" | "medium" | "low"; category: string;
      rationale: string; suggested_action: string; snippet: string }[];
      counts: Record<string, number>; source: string; message?: string }>(pid, "contract", opts);
  }
  reviewScope(pid: string, opts: { file?: File; text?: string }) {
    return this.reviewPost<{ gaps: { marker: string; note: string; snippet: string }[]; source: string; message?: string }>(
      pid, "scope", opts);
  }
  reviewAsk(pid: string, question: string, opts: { file?: File; text?: string }) {
    return this.reviewPost<{ answer: string; citations: { page: number; snippet: string }[]; source: string; message?: string }>(
      pid, "ask", { ...opts, question });
  }

  // --- AI drafting (RFI / submittal summary / scope of work) -----------------
  private async draftPost<T>(pid: string, kind: string, fields: Record<string, string | File | undefined>) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(fields)) if (v != null) fd.append(k, v);
    const res = await fetch(this.url(`/projects/${pid}/draft/${kind}`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Draft ${kind} -> ${res.status}`);
    return res.json() as Promise<T>;
  }
  /** Draft an RFI from a short note (+ optional source PDF/text) — editable before you create it. */
  aiDraftRfi(pid: string, opts: { note?: string; file?: File; text?: string }) {
    return this.draftPost<{ subject: string; question: string; discipline: string; spec_section?: string;
      priority: string; suggested_assignee?: string; background?: string;
      citations?: { page: number; snippet?: string }[]; source: string; message?: string }>(
      pid, "rfi", { note: opts.note, file: opts.file, text: opts.text });
  }
  /** Summarize an uploaded submittal package (title / spec / type / key + missing items). */
  draftSubmittalSummary(pid: string, opts: { file?: File; text?: string }) {
    return this.draftPost<{ title: string; spec_section?: string; type?: string; summary: string;
      key_items?: string[]; missing_or_review?: string[];
      citations?: { page: number }[]; source: string; message?: string }>(
      pid, "submittal-summary", { file: opts.file, text: opts.text });
  }
  /** Draft a trade scope of work (inclusions / exclusions / clarifications) from a plan/spec set. */
  draftScope(pid: string, trade: string, opts: { file?: File; text?: string }) {
    return this.draftPost<{ trade: string; inclusions: string[]; exclusions: string[];
      clarifications: string[]; spec_sections?: string[];
      citations?: { page: number }[]; source: string; message?: string }>(
      pid, "scope", { trade, file: opts.file, text: opts.text });
  }

  /** Extract a drawing-sheet index (number/title/discipline) from a PDF or pasted list; optionally create drawing records. */
  async extractSheets(pid: string, opts: { file?: File; text?: string; create?: boolean }) {
    const fd = new FormData();
    if (opts.file) fd.append("file", opts.file);
    if (opts.text) fd.append("text", opts.text);
    fd.append("create", opts.create ? "true" : "false");
    const res = await fetch(this.url(`/projects/${pid}/extract/sheets`),
      { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Extract sheets -> ${res.status}`);
    return res.json() as Promise<{ sheets: { number: string; title: string; discipline: string }[];
      method: string; has_text_layer?: boolean; note?: string; created?: string[] }>;
  }

  /** Deep bid leveling for one package: base stats, scope matrix, gaps, scope-adjusted recommendation. */
  bidLevelingDetail(pid: string, packageId: string) {
    return this.json<{ package: string; vendors: string[];
      base_stats: { count: number; low?: number; high?: number; median?: number; average?: number; spread_pct?: number };
      outliers: string[];
      scope_rows: { item: string; example: string; included_by: string[]; excluded_by: string[]; gap: boolean }[];
      gaps: { item: string; included_by: string[]; excluded_or_silent: string[] }[];
      recommendation: { apparent_low: string; base: number; is_outlier: boolean; missing_scope: string[]; note: string } | null;
      bids: { bidder: string; ref?: string; base?: number; alternates: string[]; bond: boolean; qualifications: string[] }[];
      source: string; message?: string }>(`/projects/${pid}/bids/leveling/${packageId}`);
  }

  // --- portfolio benchmarking (cross-project) --------------------------------
  benchmarkCosts(minSamples = 3) {
    return this.json<{ cost_codes: { cost_code: string; samples: number; low: number; p25: number;
      median: number; p75: number; high: number; total: number }[];
      code_count: number; min_samples: number; codes_below_threshold: number; message?: string | null }>(
      `/benchmarks/costs?min_samples=${minSamples}`);
  }
  benchmarkResponseRates() {
    return this.json<{ rfi: { total: number; open: number; answered_or_closed: number;
      avg_turnaround_days: number | null; overdue: number; overdue_pct: number };
      submittal: { total: number; open: number; returned: number; avg_turnaround_days: number | null;
      overdue: number; overdue_pct: number } }>(`/benchmarks/response-rates`);
  }

  // --- Tier 2/3: prequal, lien exposure, accounting, carbon, code check, pricing ---------------
  prequalScores(pid: string, projectSize?: number) {
    const qs = projectSize ? `?project_size=${projectSize}` : "";
    return this.json<{ subs: { company?: string; trade?: string; score: number; risk_band: string;
      factors: { factor: string; points: number; of: number; note: string }[]; flags: string[] }[];
      count: number; high_risk: number }>(`/projects/${pid}/prequal/scores${qs}`);
  }
  procurementComplianceFeed(pid: string) {
    return this.json<{ within_days: number; vendors_flagged: number;
      vendors: { vendor: string; issues: string[]; can_bid: boolean; can_bill: boolean }[];
      note: string }>(`/projects/${pid}/procurement/compliance-feed`);
  }
  procurementGate(pid: string, vendor: string) {
    return this.json<{ vendor: string; coi: { status: string; expires: string | null };
      prequal: { status: string }; subcontract: { executed: boolean }; waiver_on_file: boolean;
      can_bid: boolean; bid_blockers: string[]; can_bill: boolean; bill_blockers: string[] }>(
      `/projects/${pid}/procurement/gate?vendor=${encodeURIComponent(vendor)}`);
  }
  coiExpiry(pid: string, soonDays = 30) {
    return this.json<{ expired: { vendor?: string; coverage_type?: string; expires: string; days: number }[];
      expiring_soon: { vendor?: string; coverage_type?: string; expires: string; days: number }[];
      expired_count: number; expiring_count: number }>(`/projects/${pid}/prequal/coi-expiry?soon_days=${soonDays}`);
  }
  lienExposure(pid: string) {
    return this.json<{ vendors: { vendor: string; billed: number; paid: number; retainage: number;
      waived_unconditional: number; waived_conditional: number; exposure: number; status: string }[];
      total_lien_exposure: number; vendors_at_risk: string[]; message?: string | null }>(
      `/projects/${pid}/payapp/lien-exposure`);
  }
  accountingGlCsvUrl(pid: string) { return this.url(`/projects/${pid}/accounting/gl.csv`); }
  accountingIifUrl(pid: string) { return this.url(`/projects/${pid}/accounting/bills.iif`); }
  /** Freeze the current books into an approval-gated journal batch (draft → submit → approve → export). */
  createJournalBatch(pid: string, period: string, memo = "") {
    return this.json<{ id: string; ref: string; workflow_state: string; data: Record<string, unknown> }>(
      `/projects/${pid}/accounting/journal-batch`, { method: "POST", body: JSON.stringify({ period, memo }) });
  }
  /** Download URL for an APPROVED batch's frozen GL — fmt "gl" (CSV) or "iif" (QuickBooks). */
  journalBatchExportUrl(pid: string, batchId: string, fmt: "gl" | "iif" = "gl") {
    return this.url(`/projects/${pid}/accounting/journal-batch/${batchId}/export?fmt=${fmt}`);
  }
  projectCarbon(pid: string) {
    return this.json<{ total_kgco2e: number; total_tco2e: number; line_count: number; unmatched: number;
      by_material: Record<string, number>; by_cost_code: Record<string, number>; message?: string | null }>(
      `/projects/${pid}/carbon`);
  }
  codeComplianceCheck(pid: string, description: string, context?: string) {
    return this.json<{ topics: { code: string; section: string; title: string; requirement: string }[];
      detected?: { occupancy?: { group: string; label: string } | null; area_sf?: number | null;
      stories?: number | null }; source: string; message?: string }>(
      `/projects/${pid}/codecheck`, { method: "POST", body: JSON.stringify({ description, context }) });
  }
  // --- land / parcel screening (Acres) ---------------------------------------
  parcelsScreen(parcelList: unknown[], criteria: Record<string, unknown>) {
    return this.json<{ matches: { id: string; acres: number; zoning?: string; flood_zone?: string;
      price?: number | null; buildable: { acres: number; max_gfa_sf?: number | null;
      conceptual_cost?: number; land_cost_per_buildable_sf?: number } }[];
      rejected: { id: string; failed: string[] }[]; match_count: number; screened: number;
      message?: string | null }>(`/parcels/screen`, { method: "POST",
      body: JSON.stringify({ parcels: parcelList, criteria }) });
  }
  parcelsDataStatus() {
    return this.json<{ enabled: boolean; provider: string | null; message: string }>(`/parcels/data-status`);
  }

  // --- design lifecycle (RIBA/AIA phases + itemized soft costs) ---------------
  lifecycle(pid: string) {
    return this.json<{ count: number; seeded: boolean;
      current_stage: { id: string; riba_stage: string; aia_phase: string } | null;
      phases: { id: string; ref: string; order: number; state: string; riba_stage: string;
        aia_phase: string; design_fee_pct: number | string; iso_status: string;
        deliverables: string[]; design_fee_amount: number; signed_by?: string }[];
      hard_cost: number;
      soft_costs: { total: number; lines: { key: string; label: string; pct_of_hard: number; amount: number }[] } | null;
      }>(`/projects/${pid}/lifecycle`);
  }
  lifecycleSeed(pid: string) {
    return this.json<{ seeded: boolean; phases?: number; reason?: string }>(
      `/projects/${pid}/lifecycle/seed`, { method: "POST" });
  }
  diligenceReadiness(pid: string) {
    return this.json<{
      due_diligence: { total: number; cleared: number; flagged: number;
        by_category: Record<string, { total: number; cleared: number; flagged: number; open: number }>;
        high_risk: { ref: string; item: string; risk: string; category: string; state: string }[] };
      entitlements: { total: number; by_state: Record<string, number>; approved: number;
        pending: number; denied: number;
        expiring_within_180d: { ref: string; application: string; expires: string }[] };
      go: boolean }>(`/projects/${pid}/diligence/readiness`);
  }

  // --- operations: CMMS + metered energy ----------------------------------------
  cmmsGeneratePm(pid: string) {
    return this.json<{ generated: number; work_orders: { work_order: string; schedule: string }[];
      as_of: string }>(`/projects/${pid}/cmms/generate-pm`, { method: "POST" });
  }
  cmmsKpis(pid: string) {
    return this.json<{ total: number; open: number; completed: number; overdue: number;
      open_by_priority: Record<string, number>; by_type: Record<string, number>;
      pm_compliance_pct: number | null; mttr_days: number | null }>(`/projects/${pid}/cmms/kpis`);
  }
  energyActual(pid: string, gfaSf?: number) {
    const qs = gfaSf ? `?gfa_sf=${gfaSf}` : "";
    return this.json<{ total_kbtu: number; total_cost: number; water_gallons: number;
      by_utility: Record<string, { consumption: number; unit: string; kbtu: number; cost: number }>;
      monthly: { month: string; kbtu: number }[]; months_covered: number;
      gfa_sf: number | null; eui_kbtu_sf_yr: number | null; note: string }>(
      `/projects/${pid}/energy/actual${qs}`);
  }
  energyBenchmarkStatus() {
    return this.json<{ enabled: boolean; provider: string | null; message: string }>(
      `/energy/benchmark-status`);
  }
  twinReadiness(pid: string) {
    return this.json<{ assets: number; systems: number; systems_by_type: Record<string, number>;
      system_linked_pct: number | null; sensor_mapped_pct: number | null; bms_integrated_systems: number;
      dpp: { complete_pct: number | null; partial: number; complete: number; fields: string[]; note: string };
      twin_readiness_pct: number | null; note: string }>(`/projects/${pid}/twin/readiness`);
  }

  // --- facility condition assessment (FCI) --------------------------------------
  fcaIndex(pid: string) {
    return this.json<{ elements: number; open_deficiencies: number; crv: number; crv_source: string;
      deferred_maintenance: number; capital_renewal: number; fci_pct: number; band: string;
      by_uniformat: { group: string; count: number; deferred: number; renewal: number; crv: number; fci_pct: number | null }[];
      by_condition: Record<string, number>;
      worst_elements: { ref: string; element: string; uniformat: string; condition: string; cost: number }[];
      recommended_by_year: { year: number; cost: number }[];
      bands: Record<string, string>; note: string }>(`/projects/${pid}/fca/index`);
  }
  fcaPortfolio() {
    return this.json<{ count: number; note: string;
      projects: { project_id: string; project: string; fci_pct: number; band: string; crv: number;
        backlog: number; open_deficiencies: number }[] }>(`/fca/portfolio`);
  }

  // --- climate & water resilience (flood + stormwater) --------------------------
  resilienceFlood(pid: string) {
    return this.json<{ count: number; in_special_flood_hazard_area: boolean;
      design_flood_elevation_ft: number | null; assets_checked: number; at_risk_count: number;
      compliant: boolean; note: string;
      assessments: { ref: string; name: string; flood_zone: string; in_sfha: boolean; bfe_ft: number | null;
        flood_design_class: string; freeboard_ft: number; dfe_ft: number | null }[];
      assets_at_risk: { ref: string; asset: string; elevation_ft: number; below_dfe_by_ft: number }[] }>(
      `/projects/${pid}/resilience/flood`);
  }
  resilienceStormwater(pid: string) {
    return this.json<{ count: number; total_area_acres: number; composite_runoff_coefficient: number | null;
      peak_runoff_cfs: number; detention_volume_cf: number; detention_volume_gal: number; note: string;
      catchments: { ref: string; name: string; surface: string; area_sf: number; c: number; i_in_hr: number;
        return_period_years: string; peak_cfs: number }[];
      by_surface: { surface: string; area_sf: number; peak_cfs: number }[] }>(
      `/projects/${pid}/resilience/stormwater`);
  }
  resilienceWeather(pid: string) {
    return this.json<{ sensitive_count: number; by_sensitivity: Record<string, number>;
      site_risk_count: number; open_risk_count: number; high_severity_open: number; risk_score: number;
      weather_delay_days: number; delay_report_count: number;
      by_season: Record<string, number>; by_hazard: Record<string, number>; note: string;
      weather_sensitive_activities: { ref: string; name: string; trade: string; sensitivity: string;
        start: string; finish: string; percent: number }[];
      site_risks: { ref: string; name: string; hazard_type: string; season: string; severity: string;
        location: string; activity_ref: string; open: boolean; state: string }[];
      delay_reports: { ref: string; date: string; weather: string; impact: string; days: number }[] }>(
      `/projects/${pid}/resilience/weather`);
  }
  resilienceClimateRisk(pid: string) {
    return this.json<{ rating: string; score: number; in_special_flood_hazard_area: boolean;
      design_flood_elevation_ft: number | null; assets_at_risk: number; peak_runoff_cfs: number;
      open_site_risks: number; high_severity_open: number; weather_delay_days: number;
      factors: string[]; note: string }>(`/projects/${pid}/resilience/climate-risk`);
  }
  /** Discipline Spine traceability: discipline → sheets → specs → bid packages → cost codes → budget. */
  spineTraceability(pid: string) {
    return this.json<{
      disciplines: { discipline: string; code: string | null; sheets: number; specs: number;
        packages: number; cost_codes: number; budget: number }[];
      coverage: { specs: number; bid_packages: number; cost_codes: number; sheets: number;
        specs_packaged_pct: number | null; packages_costed_pct: number | null;
        sheets_specced_pct: number | null; spec_to_budget_pct: number | null };
      gaps: { specs_without_bid_package: { ref: string; section: string; title: string }[];
        bid_packages_without_cost_code: { ref: string; name: string }[];
        sheets_without_spec: { ref: string; sheet: string }[] };
      chain: { spec: string; section: string; title: string; discipline: string | null;
        bid_package: string | null; bid_package_name: string | null; cost_code: string | null;
        cost_code_value: string | null; linked: boolean }[];
      note: string }>(`/projects/${pid}/spine/traceability`);
  }

  // --- concept space programming: adjacency graph + massing hints ---------------
  programSummary(pid: string) {
    return this.json<{ spaces: number; total_area_sf: number; net_area_sf: number;
      efficiency_pct: number | null;
      by_type: Record<string, { count: number; area: number; pct: number }>;
      graph: { nodes: { id: string; name: string; type: string; area: number; quantity: number; adjacent_to: string[] }[];
        edges: { from: string; from_type: string; to_type: string; satisfiable: boolean }[] };
      adjacency: { total: number; satisfiable: number; unmet: { from_type: string; to_type: string }[] };
      massing_hints: { gross_area_sf: number; net_area_sf: number; mix_pct: Record<string, number> };
      note: string }>(`/projects/${pid}/program/summary`);
  }

  // --- market intelligence & cost escalation (Track M) --------------------------
  marketSnapshot() {
    return this.json<{ base_year: number;
      regions: { key: string; escalation_pct: number; labour_usd_hr: number; location_index: number; label: string }[];
      sectors: { sector: string; temperature: string }[];
      market_signal: { hot: string[]; warm_or_hot: string[]; cold: string[]; headline: string };
      source: string }>(`/market/snapshot`);
  }
  marketContext(pid: string, q: { region?: string; sector?: string; start_year?: number; duration_months?: number } = {}) {
    const p = new URLSearchParams();
    if (q.region) p.set('region', q.region);
    if (q.sector) p.set('sector', q.sector);
    if (q.start_year != null) p.set('start_year', String(q.start_year));
    if (q.duration_months != null) p.set('duration_months', String(q.duration_months));
    const qs = p.toString();
    return this.json<{ region: { region: string; escalation_pct: number; labour_usd_hr: number;
        location_index: number; label: string };
      sector: { sector: string; temperature: string; note: string };
      escalation_factor: number; escalation_basis: string; midpoint_year: number;
      from_assumption: boolean; source: string }>(`/projects/${pid}/market/context${qs ? '?' + qs : ''}`);
  }
  marketEscalate(pid: string, amount: number, q: { region?: string; start_year?: number;
      duration_months?: number; to_year?: number; rate_pct?: number } = {}) {
    const p = new URLSearchParams({ amount: String(amount) });
    if (q.region) p.set('region', q.region);
    if (q.start_year != null) p.set('start_year', String(q.start_year));
    if (q.duration_months != null) p.set('duration_months', String(q.duration_months));
    if (q.to_year != null) p.set('to_year', String(q.to_year));
    if (q.rate_pct != null) p.set('rate_pct', String(q.rate_pct));
    return this.json<{ base_year: number; region: string; annual_rate_pct: number; escalation_basis: string;
      midpoint_year: number; years: number; escalation_factor: number; base_amount: number;
      escalated_amount: number; note: string }>(`/projects/${pid}/market/escalate?${p.toString()}`);
  }

  // --- AI concept-render bridge (Track V; feature-flagged) -----------------------
  conceptRenderStatus(pid: string) {
    return this.json<{ feature: string; enabled: boolean; note: string;
      request_contract: Record<string, string>; ingest_contract: Record<string, string>;
      reference_adapter: string }>(`/projects/${pid}/concept-render/status`);
  }
  conceptRenderRequest(pid: string, payload: { prompt?: string; style?: string; variations?: number;
      program?: unknown; massing?: unknown } = {}) {
    return this.json<{ accepted: boolean; reason?: string; prompt?: string; style?: string;
      variations?: number; note?: string }>(`/projects/${pid}/concept-render/request`,
      { method: 'POST', body: JSON.stringify(payload) });
  }
  conceptRenderIngest(pid: string, payload: { title?: string; prompt?: string; style?: string;
      image_url: string; source?: string }) {
    return this.json<{ accepted: boolean; reason?: string; stored?: boolean; record_id?: string;
      image_url?: string }>(`/projects/${pid}/concept-render/ingest`,
      { method: 'POST', body: JSON.stringify(payload) });
  }

  // --- ISO 19650 standards: CDE container discipline + requirements register ----
  cdeStatus(pid: string) {
    return this.json<{ total: number; by_state: Record<string, number>;
      by_suitability: Record<string, number>;
      discipline: { revision_control_pct: number | null; approval_status_pct: number | null;
        metadata_completeness_pct: number | null; published: number; archived: number };
      note: string }>(`/projects/${pid}/cde/status`);
  }
  infoRequirementsRegister(pid: string) {
    return this.json<{ total: number;
      by_type: Record<string, { total: number; issued: number; draft: number; superseded: number }>;
      core_coverage: { required: string[]; missing: string[]; complete: boolean }; note: string }>(
      `/projects/${pid}/info-requirements/register`);
  }
  /** ISO 19650 requirement flow-down (OIR→PIR/AIR→EIR→MIDP/TIDP) via each record's derives_from,
   *  with cascade health: orphans that don't trace up + links pointing the wrong way. */
  infoRequirementsCascade(pid: string) {
    type Brief = { id: string; ref: string | null; type: string; title: string | null };
    return this.json<{ total: number; linked: number; coverage_pct: number | null;
      roots: Brief[]; orphans: Brief[];
      misdirected: { id: string; ref: string | null; type: string; parent_type: string }[]; note: string }>(
      `/projects/${pid}/info-requirements/cascade`);
  }
  /** MIDP/TIDP delivery plan — requirements vs programme dates, overdue/due-soon, LOIN coverage. */
  infoRequirementsDeliveryPlan(pid: string) {
    type Item = { id: string; ref: string | null; title: string | null; type: string;
      due_date: string | null; status: string; has_loin: boolean };
    return this.json<{ total: number; overdue: number; due_soon: number; loin_coverage_pct: number | null;
      next_deliverable: Item | null;
      by_month: { month: string; total: number; issued: number; overdue: number }[];
      items: Item[]; note: string }>(
      `/projects/${pid}/info-requirements/delivery-plan`);
  }
  /** AI / data-readiness scorecard — single-source / completeness / model-integrity / governance 0-100. */
  aiReadiness(pid: string) {
    type Dim = { score: number; advice: string; [k: string]: unknown };
    return this.json<{ overall: number; verdict: "ready" | "partial" | "not_ready"; note: string;
      dimensions: { single_source_of_truth: Dim; information_completeness: Dim; governance: Dim;
        model_integrity?: Dim } }>(`/projects/${pid}/ai-readiness`);
  }
  /** ISO 19650-6 exchange acceptance — non-WIP containers vs completeness/suitability/auth/traceability. */
  cdeExchangeAcceptance(pid: string) {
    return this.json<{ reviewed: number; accepted: number; nonconforming_count: number; acceptable: boolean;
      criteria_pct: { completeness: number | null; suitability: number | null; authorization: number | null; traceability: number | null };
      nonconforming: { id: string; ref: string | null; title: string | null; state: string; failed: string[] }[]; note: string }>(
      `/projects/${pid}/cde/exchange-acceptance`);
  }
  // --- Responsibility matrix (RACI / DACI) ----------------------------------
  responsibilityMatrix(pid: string) {
    return this.json<ResponsibilityMatrix>(`/projects/${pid}/responsibility`);
  }
  responsibilityTemplates(pid: string) {
    return this.json<{ templates: { key: string; name: string; description: string; rows: number }[] }>(
      `/projects/${pid}/responsibility/templates`);
  }
  setResponsibilityConfig(pid: string, roles: string[], mode: "RACI" | "DACI") {
    return this.json<{ roles: string[]; mode: string }>(`/projects/${pid}/responsibility/config`, {
      method: "PUT", body: JSON.stringify({ roles, mode }) });
  }
  applyResponsibilityTemplate(pid: string, key: string, mode: "RACI" | "DACI") {
    return this.json<{ applied: string; created: number; mode: string }>(
      `/projects/${pid}/responsibility/apply-template`, {
        method: "POST", body: JSON.stringify({ key, mode }) });
  }
  standardsCheck(pid: string, standard: "iso19650" | "cobie" | "ids" | "uniclass") {
    return this.json<{ standard: string; label?: string; score?: number;
      findings?: { level: string; text: string; reference: string }[];
      recommendations?: string[]; error?: string; note?: string }>(
      `/projects/${pid}/standards/check?standard=${standard}`);
  }
  mcpTools() {
    return this.json<{ tools: { name: string; description: string }[]; server: string; note: string }>(
      `/mcp/tools`);
  }
  bimKpiScorecard(pid: string) {
    return this.json<{
      categories: { key: string; label: string; grade: string; headline: string;
        metrics: Record<string, number | null> }[];
      summary: { scored: number; good: number; warn: number; poor: number; na: number; health_pct: number | null };
      model_scored: boolean; note: string }>(`/projects/${pid}/bim-kpi/scorecard`);
  }
  handoverAcceptance(pid: string) {
    return this.json<{ accepted: boolean; checks: { key: string; label: string; ok: boolean }[];
      metrics: Record<string, number>; note: string }>(`/projects/${pid}/handover/acceptance`);
  }
  openbimQuality(pid: string, useCase?: string) {
    const qs = useCase ? `?use_case=${encodeURIComponent(useCase)}` : "";
    return this.json<{
      loin: { total: number; max_score: number; avg_score: number; coordinated_pct: number | null;
        distribution: Record<string, number>; facet_coverage_pct: Record<string, number | null> };
      export_health: { total: number; proxy_count: number; overall: string;
        checks: { key: string; label: string; pct: number | null; grade: string }[] };
      bsdd: { total: number; classified: number; alignment_pct: number | null };
      ids?: { compliance_pct: number | null; applicable_total: number; passing_total: number;
        specs: { name: string; ifc_class: string; applicable: number; passing: number; pct: number | null }[] };
      use_case: string | null }>(`/projects/${pid}/openbim/quality${qs}`);
  }

  // --- model analysis (capabilities / query / LOD / envelope / MEP-extract / naming) --------------
  modelCapabilities(pid: string) {
    return this.json<{ supported_read_schemas: string[];
      loaded_model: { detected: string | null; supported: boolean | null; data_readable?: boolean; note: string };
      ifc5: { status: string; data_read?: boolean; geometry_read?: boolean; note: string } }>(
      `/projects/${pid}/model/capabilities`);
  }
  /** Download URL for the model element table in a columnar/graph format. */
  modelExportUrl(pid: string, fmt: "csv" | "jsonld" | "parquet") {
    return this.url(`/projects/${pid}/model/export.${fmt}`);
  }
  /** Download URL for the model geometry as a self-contained glTF 2.0 file (interchange). */
  modelGltfUrl(pid: string) {
    return this.url(`/projects/${pid}/model/export.gltf`);
  }
  /** Download URL for the model geometry as a binary glTF (.glb) — the compact single-file interchange. */
  modelGlbUrl(pid: string) {
    return this.url(`/projects/${pid}/model/export.glb`);
  }
  /** Download URL for a first-class IFC re-export — the current authored source IFC (GUID-stable). */
  modelIfcUrl(pid: string) {
    return this.url(`/projects/${pid}/model/export.ifc`);
  }
  /** TAKEOFF-2D: measure + price regions traced on a 2D drawing at a calibrated scale (units/px). */
  takeoff2d(pid: string, regions: { category: string; points: [number, number][]; label?: string }[],
            scaleUnitsPerPx: number, unit = "m") {
    return this.json<{
      region_count: number; total_cost: number; unit: string;
      regions: { index: number; category: string; assembly: string; measure: string; quantity: number;
                 unit: string; rate: number; cost: number }[];
      by_assembly: { category: string; assembly: string; unit: string; quantity: number; cost: number; count: number }[];
      assemblies: { category: string; measure: string; rate: number; label: string; unit: string | null }[];
      disclaimer: string;
    }>(`/projects/${pid}/takeoff/2d`, {
      method: "POST",
      body: JSON.stringify({ scale_units_per_px: scaleUnitsPerPx, unit, regions }),
    });
  }
  /** Interning/columnar efficiency stats (dedup ratio + estimated RAM saved) — G1. */
  modelColumnarStats(pid: string) {
    return this.json<{ model_loaded: boolean; elements?: number; param_rows?: number;
      unique_strings?: number; dedup_ratio?: number | null; est_bytes_saved?: number;
      est_reduction_pct?: number | null }>(`/projects/${pid}/model/columnar/stats`);
  }
  /** Download URL for the EAV parameter table as Parquet (analytics) — G1. */
  modelParamsParquetUrl(pid: string) {
    return this.url(`/projects/${pid}/model/export/params.parquet`);
  }
  /** Fast model summary — entity-type histogram from a streaming STEP scan (no full parse) — G3. */
  modelStepSummary(pid: string) {
    return this.json<{ ok: boolean; schema?: string | null; total_entities?: number;
      distinct_types?: number; file_size_bytes?: number;
      histogram?: { ifc_class: string; count: number }[] }>(`/projects/${pid}/model/step-summary`);
  }
  /** Inspect an uploaded VIM / G3D file (schema, buffers, geometry stats) — G2. */
  async inspectVim(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/convert/vim/inspect`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `inspect failed (${res.status})`);
    return res.json() as Promise<Record<string, unknown>>;
  }
  /** Model version/signature for 2D staleness (bumps on publish; /drawings/stream pushes it). */
  drawingsSyncStatus(pid: string) {
    return this.json<{ model_loaded: boolean; version: number; signature: string | null;
      changed_at: number | null }>(`/projects/${pid}/drawings/sync-status`);
  }

  // --- Document control / file manager (F1-F6) ---------------------------------
  documentsTree(pid: string) {
    return this.json<{ project: string; total_files: number; required_gaps: string[];
      nodes: DocFolderNode[] }>(`/projects/${pid}/documents/tree`);
  }
  documentsFolder(pid: string, path: string, superseded = false) {
    const q = `?path=${encodeURIComponent(path)}${superseded ? "&superseded=true" : ""}`;
    return this.json<{ folder: string; owner_role: string | null; valid_folder: boolean;
      count: number; files: DocFile[] }>(`/projects/${pid}/documents/folder${q}`);
  }
  documentsByRole(pid: string, role: string) {
    return this.json<{ role: string; count: number; folders: DocFolderNode[] }>(
      `/projects/${pid}/documents/by-role?role=${encodeURIComponent(role)}`);
  }
  documentsHealth(pid: string) {
    return this.json<{ total_files: number; naming_compliance_pct: number | null;
      required_coverage_pct: number | null; revision_control_pct: number | null;
      required_missing: string[]; by_cde_state: Record<string, number>; superseded_kept: number }>(
      `/projects/${pid}/documents/health`);
  }
  documentsPhaseGaps(pid: string, phase: string) {
    return this.json<{ phase: string; missing: number; complete: boolean;
      items: { folder: string; description: string; present: boolean }[] }>(
      `/projects/${pid}/documents/phase-gaps?phase=${encodeURIComponent(phase)}`);
  }
  async uploadDocument(pid: string, path: string, file: File,
      meta: { title?: string; discipline?: string; doc_type?: string; cde_state?: string } = {}) {
    const fd = new FormData();
    fd.append("path", path); fd.append("file", file);
    for (const [k, v] of Object.entries(meta)) if (v) fd.append(k, v);
    const res = await fetch(this.url(`/projects/${pid}/documents/upload`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `upload failed (${res.status})`);
    return res.json() as Promise<{ entry: DocFile; naming: { valid: boolean; issues: string[] };
      superseded: string | null }>;
  }
  async moveDocument(pid: string, fid: string, path: string) {
    const fd = new FormData(); fd.append("path", path);
    const res = await fetch(this.url(`/projects/${pid}/documents/${fid}/move`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `move failed (${res.status})`);
    return res.json() as Promise<DocFile>;
  }
  deleteDocument(pid: string, fid: string, hard = false) {
    return this.json<{ deleted: string }>(`/projects/${pid}/documents/${fid}${hard ? "?hard=true" : ""}`,
      { method: "DELETE" });
  }
  documentDownloadUrl(pid: string, fid: string) {
    return this.url(`/projects/${pid}/documents/${fid}/download`);
  }
  modelQueryViews(pid: string) {
    return this.json<{ views: { id: string; label: string }[] }>(`/projects/${pid}/model/query/views`);
  }
  modelQuery(pid: string, view?: string, groupBy = "ifc_class") {
    const qs = view ? `?view=${encodeURIComponent(view)}` : `?group_by=${encodeURIComponent(groupBy)}`;
    return this.json<{ model_scored: boolean; matched: number;
      rows: { group: string; value: number; count: number }[] }>(`/projects/${pid}/model/query${qs}`);
  }
  lodAssessment(pid: string) {
    return this.json<{ model_scored: boolean; elements: number; using_default: boolean;
      distribution: Record<string, number>;
      by_discipline: { discipline: string; elements: number; avg_lod: string }[] }>(
      `/projects/${pid}/lod/assessment`);
  }
  envelopeAudit(pid: string) {
    return this.json<{ total: number; checked: number; compliant: number; compliance_pct: number | null;
      results: { name: string; element_type: string; compliant: boolean | null }[] }>(
      `/projects/${pid}/envelope/audit`);
  }
  mepModelExtract(pid: string) {
    return this.json<{ model_scored: boolean; mep_elements: number;
      by_class: { ifc_class: string; label: string; count: number }[] }>(
      `/projects/${pid}/mep/model-extract`);
  }
  namingAudit(pid: string) {
    return this.json<{ containers: { total: number; compliant: number; compliance_pct: number | null };
      sheets: { total: number; compliant: number; compliance_pct: number | null } }>(
      `/projects/${pid}/naming/audit`);
  }

  // --- hold-phase asset management: reserve study + CAM reconciliation ----------
  reserveStudy(pid: string, opts: { horizonYears?: number; openingBalance?: number;
      annualContribution?: number; inflationPct?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.horizonYears) q.set("horizon_years", String(opts.horizonYears));
    if (opts.openingBalance) q.set("opening_balance", String(opts.openingBalance));
    if (opts.annualContribution) q.set("annual_contribution", String(opts.annualContribution));
    if (opts.inflationPct) q.set("inflation_pct", String(opts.inflationPct));
    const qs = q.toString();
    return this.json<{ horizon: { from: number; to: number }; components: number;
      components_missing_data: number;
      events: { year: number; item: string; cost: number; cost_escalated: number; source: string; ref: string }[];
      schedule: { year: number; outflows: number; contribution: number; balance: number }[];
      total_outflows: number; first_underfunded_year: number | null; adequately_funded: boolean;
      suggested_level_contribution: number; note: string }>(
      `/projects/${pid}/reserves/study${qs ? `?${qs}` : ""}`);
  }
  camReconciliation(pid: string, opts: { year?: number; grossUpToPct?: number; buildingSf?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.year) q.set("year", String(opts.year));
    if (opts.grossUpToPct) q.set("gross_up_to_pct", String(opts.grossUpToPct));
    if (opts.buildingSf) q.set("building_sf", String(opts.buildingSf));
    const qs = q.toString();
    return this.json<{ year: number; occupied_sf: number; building_sf: number; occupancy_pct: number;
      gross_up_to_pct: number;
      expense_lines: { ref: string; category: string; budget: number; actual: number;
        variable: boolean; recoverable: boolean; grossed_up: number }[];
      budget_total: number; actual_total: number; recoverable_pool: number;
      tenants: { id: string; ref: string; tenant: string; suite: string; rentable_sf: number;
        share_pct: number; share_of_expenses: number; estimated_paid: number; balance_due: number }[];
      note: string }>(`/projects/${pid}/cam/reconciliation${qs ? `?${qs}` : ""}`);
  }
  esgSummary(pid: string, gfaSf?: number) {
    const qs = gfaSf ? `?gfa_sf=${gfaSf}` : "";
    return this.json<{
      performance: {
        energy: { total_kbtu: number; eui_kbtu_sf_yr: number | null; months_covered: number; gfa_sf: number | null };
        ghg: { scope1_tco2e: number; scope2_tco2e: number; total_tco2e: number;
          intensity_kgco2e_sf: number | null; grid_factor_kgco2e_kwh: number; note: string };
        water: { gallons: number; intensity_gal_sf: number | null };
      };
      certifications: { credits_tracked: number; points_targeted: number; points_achieved: number };
      poe: { count: number; reported: number; latest: { ref: string; level: string | null; state: string;
        survey_date: string | null; satisfaction_score: number | null; design_eui: number | null;
        actual_eui: number | null; eui_gap_pct: number | null } | null };
      data_coverage: { meter_months: number }; as_of: string }>(`/projects/${pid}/esg${qs}`);
  }
  camStatementUrl(pid: string, rid: string, opts: { year?: number; buildingSf?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.year) q.set("year", String(opts.year));
    if (opts.buildingSf) q.set("building_sf", String(opts.buildingSf));
    const qs = q.toString();
    return this.url(`/projects/${pid}/cam/statement/${rid}.pdf${qs ? `?${qs}` : ""}`);
  }

  // --- turnover: substantial completion (G704) + record model ------------------
  turnoverReadiness(pid: string) {
    return this.json<{ punch: { count: number; verified: number; open: number;
      complete_pct: number | null; overdue: number; open_cost: number };
      punch_list_prepared: boolean; latest_model_version: number | null;
      ready_for_substantial_completion: boolean }>(`/projects/${pid}/turnover/readiness`);
  }
  turnoverStatus(pid: string) {
    return this.json<{ readiness: { ready_for_substantial_completion: boolean };
      substantial_completion: { ref: string; record_model_version: number | null; signed_by: string[] } | null;
      record_model_locked: boolean }>(`/projects/${pid}/turnover/status`);
  }
  turnoverCertify(pid: string, certRid: string, architect: string, owner?: string, contractor?: string, occupancyDate?: string) {
    return this.json<{ certificate: ModuleRecord; readiness: unknown }>(
      `/projects/${pid}/turnover/certify`, { method: "POST",
      body: JSON.stringify({ cert_rid: certRid, architect, owner, contractor, occupancy_date: occupancyDate }) });
  }
  g704Url(pid: string, certRid: string) {
    return this.url(`/projects/${pid}/contracts/completion_certificate/${certRid}/document.pdf?doc=g704`);
  }

  // --- conceptual estimating + IFC classification (Ediphi / Qonic) -----------
  conceptualCatalog() {
    return this.json<{ building_types: string[]; regions: string[]; base_year: number;
      annual_escalation: number; current_year: number }>(`/estimate/conceptual/catalog`);
  }
  conceptualEstimate(pid: string, params: Record<string, unknown>) {
    return this.json<{ building_type: string; gfa_sf: number; hard_cost: number; soft_cost: number;
      total_cost: number; range: { low: number; base: number; high: number };
      metrics: Record<string, number>; region_index: number; escalation_factor: number; error?: string }>(
      `/projects/${pid}/estimate/conceptual`, { method: "POST", body: JSON.stringify(params) });
  }
  ifcClassify(pid: string) {
    return this.json<{ suggestions: { guid?: string; name: string; current_class: string;
      suggested_class: string; confidence: string; reason: string }[]; count: number;
      generic_elements: number; by_target_class: Record<string, number>; message?: string | null }>(
      `/projects/${pid}/ifc/classify`, { method: "POST", body: JSON.stringify({}) });
  }

  // --- materials procure-to-pay (FieldMaterials) -----------------------------
  procurementThreeWayMatch(pid: string) {
    return this.json<{ pos: { po: string; vendor: string; cost_code: string; po_amount: number;
      deliveries: number; received: number; invoiced: number; invoice_count: number; variance: number;
      flags: string[]; status: string }[]; po_count: number; flagged: string[];
      message?: string | null }>(`/projects/${pid}/procurement/three-way-match`);
  }
  procurementLevelQuotes(pid: string, quotes: unknown[]) {
    return this.json<{ suppliers: string[]; items: { item: string; low_supplier: string | null;
      low_price: number; prices: Record<string, number | null>; spread_pct: number }[];
      supplier_totals: Record<string, number>; best_all_in_supplier: string | null;
      line_by_line_savings: number; message?: string | null }>(
      `/projects/${pid}/procurement/level-quotes`, { method: "POST", body: JSON.stringify({ quotes }) });
  }

  // --- IDS authoring (BIMIDS) ------------------------------------------------
  idsTemplates() {
    return this.json<{ elements: { key: string; label: string; ifc_class: string;
      requirements: { pset: string; property: string; data_type: string }[] }[];
      use_cases: { key: string; label: string; groups: string[] }[] }>(`/ids/templates`);
  }
  /** POST a use_case (or specs) and download the resulting .ids / EIR.md file. */
  async idsDownload(kind: "build" | "eir", body: Record<string, unknown>, filename: string) {
    const res = await fetch(this.url(`/ids/${kind}`), {
      method: "POST", body: JSON.stringify(body),
      headers: { "Content-Type": "application/json", ...this.authHeaders() } });
    if (!res.ok) throw new Error(`ids ${kind} -> ${res.status}`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }

  /** Build a use-case IDS and return its bytes (for pinning), rather than triggering a download. */
  async idsBuildBlob(useCase: string): Promise<Blob> {
    const res = await fetch(this.url(`/ids/build`), {
      method: "POST", body: JSON.stringify({ use_case: useCase }),
      headers: { "Content-Type": "application/json", ...this.authHeaders() } });
    if (!res.ok) throw new Error(`ids build -> ${res.status}`);
    return res.blob();
  }
  /** Whether a project has a pinned IDS (+ its size). */
  projectIdsStatus(pid: string) {
    return this.json<{ exists: boolean; bytes: number }>(`/projects/${pid}/ids`);
  }
  /** Pin an IDS to the project so /validate runs against it with no re-upload. */
  async pinProjectIds(pid: string, ids: Blob, filename = "project.ids") {
    const fd = new FormData(); fd.append("file", ids, filename);
    const res = await fetch(this.url(`/projects/${pid}/ids`),
      { method: "PUT", body: fd, headers: { ...this.authHeaders() } });
    if (!res.ok) throw new Error(`pin IDS -> ${res.status}`);
    return res.json() as Promise<{ stored: boolean; bytes: number }>;
  }
  unpinProjectIds(pid: string) {
    return this.json<{ deleted: boolean }>(`/projects/${pid}/ids`, { method: "DELETE" });
  }

  pricingReconcile(pid: string) {
    return this.json<{ lines: { material: string; quantity: number; unit: string; matched?: string | null;
      unit_price?: number; priced_amount?: number | null; estimated_unit_price?: number; variance?: number;
      variance_pct?: number | null; note?: string }[]; matched: number; priced_total: number;
      estimated_total: number; variance_total: number | null; pricing_source: string }>(
      `/projects/${pid}/pricing/reconcile`);
  }
  /** Download URL for a module's header-only import template (CSV). */
  importTemplateUrl(pid: string, key: string) {
    return this.url(`/projects/${pid}/modules/${key}/import-template.csv`);
  }
  /** Step 1 of a generic Excel/CSV import: parse + auto-map columns to fields + coerce a sample. */
  async importPreview(pid: string, key: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/import/preview`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Import preview -> ${res.status}`);
    return res.json() as Promise<{ headers: string[]; row_count: number; unmapped_required: string[];
      suggested_mapping: Record<string, string>; sample: Record<string, unknown>[];
      fields: { name: string; label: string; type: string; required: boolean }[] }>;
  }
  /** Step 2: import the sheet with a column->field mapping. */
  async importModuleRecords(pid: string, key: string, file: File, mapping: Record<string, string>) {
    const fd = new FormData(); fd.append("file", file); fd.append("mapping", JSON.stringify(mapping));
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/import`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Import -> ${res.status}`);
    return res.json() as Promise<{ imported: number; error_count: number;
      errors: { row: number; error: string }[]; truncated: boolean }>;
  }
  transitionRecord(pid: string, key: string, rid: string, action: string, note?: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/transition`, {
      method: "POST", body: JSON.stringify({ action, note }) });
  }
  linkRecord(pid: string, key: string, rid: string, module: string, id: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/link`, {
      method: "POST", body: JSON.stringify({ module, id }) });
  }
  // compliance expiry: COI + permit certs expiring soon / already expired
  complianceExpiring(pid: string, withinDays = 30) {
    return this.json<{ within_days: number; count: number;
      expired: { module: string; ref: string; name: string; expires: string; days_left: number }[];
      expiring: { module: string; ref: string; name: string; expires: string; days_left: number }[]; }>(
      `/projects/${pid}/compliance/expiring?within_days=${withinDays}`);
  }
  // E1 — project-level custom select options, nested {module: {field: [values]}}
  enumOptions(pid: string) {
    return this.json<Record<string, Record<string, string[]>>>(`/projects/${pid}/enum-options`);
  }
  addEnumOption(pid: string, key: string, field: string, value: string) {
    return this.json<{ module: string; field: string; value: string; options: string[] }>(
      `/projects/${pid}/modules/${key}/enum/${field}`, { method: "POST", body: JSON.stringify({ value }) });
  }
  addComment(pid: string, key: string, rid: string, text: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/comments`, {
      method: "POST", body: JSON.stringify({ text }) });
  }
  updateModuleRecord(pid: string, key: string, rid: string, data: Record<string, unknown>,
                     expectedModifiedAt?: string | null) {
    // pass the modified_at the editor loaded to opt into the optimistic lock — a concurrent edit
    // returns 409 instead of a silent overwrite (the caller reloads to reconcile).
    const qs = expectedModifiedAt ? `?expected_modified_at=${encodeURIComponent(expectedModifiedAt)}` : "";
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}${qs}`, {
      method: "PATCH", body: JSON.stringify(data) });
  }
  deleteModuleRecord(pid: string, key: string, rid: string) {
    return this.json<{ deleted: boolean; ref: string }>(`/projects/${pid}/modules/${key}/${rid}`, {
      method: "DELETE" });
  }
  relatedRecords(pid: string, key: string, rid: string) {
    return this.json<RelatedRecords>(`/projects/${pid}/modules/${key}/${rid}/related`);
  }
  moduleBoard(pid: string, key: string) {
    return this.json<ModuleBoard>(`/projects/${pid}/modules/${key}/board`);
  }
  myWork(pid: string) {
    return this.json<WorkItem[]>(`/projects/${pid}/my-work`);
  }
  notifications(pid: string) {
    return this.json<NotifItem[]>(`/projects/${pid}/notifications`);
  }
  /** Cross-module SLA feed — open records past or near their due date (overdue / due-soon). */
  dueFeed(pid: string, days = 7) {
    return this.json<DueFeed>(`/projects/${pid}/due-feed?days=${days}`);
  }
  // --- drawing markup (2D sheet pins; promotable to RFIs) ----------------
  drawingMarkup(pid: string, sheet: string) {
    return this.json<DrawingMarkupItem[]>(`/projects/${pid}/drawings/markup?sheet=${encodeURIComponent(sheet)}`);
  }
  addDrawingMarkup(pid: string, sheetId: string, x: number, y: number, note: string) {
    return this.json<DrawingMarkupItem>(`/projects/${pid}/drawings/markup`, { method: "POST", body: JSON.stringify({ sheet_id: sheetId, x, y, note }) });
  }
  /** Persist the 2D editor's whole markup scene for a sheet (structured takeoff markups, promotable to
   *  RFI like pins). `replace` clears the caller's own prior unpromoted markups for that sheet first. */
  saveDrawingMarkups(pid: string, sheetId: string, markups: SheetMarkupIn[], replace = true) {
    return this.json<{ saved: number; sheet_id: string }>(`/projects/${pid}/drawings/markup/bulk`,
      { method: "POST", body: JSON.stringify({ sheet_id: sheetId, replace, markups }) });
  }
  deleteDrawingMarkup(pid: string, id: string) {
    return this.json<{ ok: boolean }>(`/projects/${pid}/drawings/markup/${id}`, { method: "DELETE" });
  }
  promoteDrawingMarkup(pid: string, id: string) {
    return this.json<{ markup: DrawingMarkupItem; topic: { id: string; type: string; title: string; status: string } }>(
      `/projects/${pid}/drawings/markup/${id}/promote`, { method: "POST" });
  }

  /** Admin: send each member with open items a work-queue digest email. */
  sendDigest(pid: string) {
    return this.json<{ smtp_configured: boolean; results: Record<string, string[]>; skipped_no_email: string[] }>(
      `/projects/${pid}/notifications/digest`, { method: "POST" });
  }
  listViews(pid: string, key: string) {
    return this.json<SavedViewDef[]>(`/projects/${pid}/modules/${key}/views`);
  }
  saveView(pid: string, key: string, name: string, config: Record<string, unknown>) {
    return this.json<SavedViewDef>(`/projects/${pid}/modules/${key}/views`, {
      method: "POST", body: JSON.stringify({ name, config }) });
  }
  deleteView(pid: string, key: string, vid: string) {
    return this.json<{ deleted: boolean }>(`/projects/${pid}/modules/${key}/views/${vid}`, { method: "DELETE" });
  }
  /** Saved-search alert feed: each saved view with total + new-since-last-seen match counts. */
  viewAlerts(pid: string) {
    return this.json<{ id: string; name: string; module: string; total: number; new: number;
      config: { q?: string; state?: string; sort?: unknown } }[]>(`/projects/${pid}/views/alerts`);
  }
  /** Mark a saved view as seen (clears its 'new' alert count). */
  markViewSeen(pid: string, key: string, vid: string) {
    return this.json<{ ok: boolean; last_seen_at: string }>(
      `/projects/${pid}/modules/${key}/views/${vid}/seen`, { method: "POST" });
  }
  /** SSE stream of the notification feed; returns the EventSource so callers can close it. */
  notificationStream(pid: string, onMessage: (d: { count: number; items: NotifItem[] }) => void): EventSource {
    const es = new EventSource(this.url(`/projects/${pid}/notifications/stream`));
    es.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch { /* ignore */ } };
    return es;
  }
  /** SSE stream of the pull-board change-signature; fires whenever any trade edits a sticky note so
   *  the board can live-refresh. Returns the EventSource so callers can close it on teardown. */
  pullPlanStream(pid: string, onMessage: (d: { count: number; latest: string | null }) => void): EventSource {
    const es = new EventSource(this.url(`/projects/${pid}/pull-plan/stream`));
    es.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch { /* ignore */ } };
    return es;
  }
  searchAll(pid: string, q: string, limit = 50) {
    return this.json<WorkItem[]>(`/projects/${pid}/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  }
  bulkAction(pid: string, key: string, ids: string[], action: "transition" | "assign" | "delete", value?: string) {
    return this.json<{ ok: number; failed: { id: string; error: string }[] }>(
      `/projects/${pid}/modules/${key}/bulk`, { method: "POST", body: JSON.stringify({ ids, action, value }) });
  }
  moduleRecordsFiltered(pid: string, key: string, opts: { q?: string; state?: string; limit?: number; offset?: number } = {}) {
    const p = new URLSearchParams();
    if (opts.q) p.set("q", opts.q);
    if (opts.state) p.set("state", opts.state);
    if (opts.limit != null) p.set("limit", String(opts.limit));
    if (opts.offset) p.set("offset", String(opts.offset));
    const qs = p.toString();
    return this.json<ModuleRecord[]>(`/projects/${pid}/modules/${key}${qs ? `?${qs}` : ""}`);
  }
  /** Create a tracked revision of a record (revisable modules); re-opens the workflow. */
  reviseRecord(pid: string, key: string, rid: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/revise`, { method: "POST" });
  }
  assignRecord(pid: string, key: string, rid: string, assignee: string | null) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/assign`, {
      method: "POST", body: JSON.stringify({ assignee }) });
  }
  async uploadAttachment(pid: string, key: string, rid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/${rid}/attachments`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`upload -> ${res.status}`);
    return res.json() as Promise<RecordAttachmentMeta>;
  }
  /** Export a module's records as a BCF .bcfzip (auth'd blob, for coordination-issue interop). */
  async downloadModuleBcf(pid: string, key: string) {
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/bcf/export`), { headers: this.authHeaders() });
    if (!res.ok) throw new Error(`BCF export -> ${res.status}`);
    return res.blob();
  }
  /** Import a BCF .bcfzip as records in a module. */
  async importModuleBcf(pid: string, key: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/bcf/import`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`BCF import -> ${res.status}`);
    return res.json() as Promise<{ count: number; ids: string[] }>;
  }
  /** Import a Solibri/Navisworks clash report (XLSX) -> coordination_issue records (GUID-anchored). */
  async importClashXlsx(pid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/coordination/import-xlsx`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Clash import -> ${res.status}`);
    return res.json() as Promise<{ imported: number; detected_columns: string[]; sheet: string; rows_parsed: number }>;
  }
  /** Tie model elements (IFC GlobalIds) to a record. mode: add | remove | set. */
  tagElements(pid: string, key: string, rid: string, guids: string[], mode: "add" | "remove" | "set" = "add") {
    return this.json<{ element_guids: string[]; count: number }>(
      `/projects/${pid}/modules/${key}/${rid}/elements`, { method: "POST", body: JSON.stringify({ guids, mode }) });
  }
  /** Attach many files at once (bulk site-photo upload). */
  async uploadAttachmentsBulk(pid: string, key: string, rid: string, files: File[] | FileList) {
    const fd = new FormData();
    for (const f of Array.from(files)) fd.append("files", f);
    const res = await fetch(this.url(`/projects/${pid}/modules/${key}/${rid}/attachments/bulk`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`bulk upload -> ${res.status}`);
    return res.json() as Promise<{ count: number; attachments: RecordAttachmentMeta[] }>;
  }
  attachmentUrl(attId: string) {
    // module-record attachments live in RecordAttachment; this distinct path avoids bim.py's
    // /attachments/{id}/download route (Attachment table) shadowing it (which 404'd every thumbnail).
    return this.url(`/module-attachments/${attId}/download`);
  }

  // cost / financials (GC portal)
  costSummary(pid: string) {
    return this.json<{ budget: number; committed: number; actual: number; forecast: number; projected_over_under: number; pct_committed: number; pct_spent: number }>(
      `/projects/${pid}/cost/summary`);
  }

  // authoring round-trip (Phase 6)
  /** Model version history (one snapshot per publish). */
  modelVersions(pid: string) {
    return this.json<{ version: number; element_count: number; note: string | null; created_at: string | null }[]>(`/projects/${pid}/versions`);
  }
  /** Diff two model versions — added/removed element GUIDs + unchanged count. */
  versionDiff(pid: string, a: number, b: number) {
    return this.json<{ from: number; to: number; added_count: number; removed_count: number; unchanged_count: number }>(`/projects/${pid}/versions/diff?a=${a}&b=${b}`);
  }
  /** Reusable templates for a module (save a project's records → apply to another project). */
  templates(module: string) {
    return this.json<{ id: string; module: string; name: string; item_count: number }[]>(`/templates?module=${encodeURIComponent(module)}`);
  }
  saveTemplate(pid: string, key: string, name: string) {
    return this.json<{ id: string; item_count: number }>(`/projects/${pid}/modules/${key}/save-template`, { method: "POST", body: JSON.stringify({ name }) });
  }
  applyTemplate(pid: string, key: string, tid: string) {
    return this.json<{ applied: string; created: number }>(`/projects/${pid}/modules/${key}/apply-template/${tid}`, { method: "POST" });
  }
  /** Construction program portfolio — cost over/under + risk + safety across all projects. */
  constructionPortfolio() {
    return this.json<{ project_count: number; totals: { projected_over_under: number; over_budget_count: number; open_risks: number; risk_exposure: number; recordables: number; open_rfis: number }; projects: { id: string; name: string; projected_over_under: number; over_budget: boolean; open_risks: number; risk_exposure: number; recordables: number; open_rfis: number }[] }>(
      "/portfolio/construction");
  }
  /** Safety analytics — incidents by OSHA class, recordable/lost-time counts, TRIR/DART. */
  safetyMetrics(pid: string) {
    return this.json<{ incident_count: number; recordable_count: number; lost_time_count: number; lost_days: number; hours_worked: number; trir: number | null; dart: number | null; observation_count: number; toolbox_talk_count: number }>(
      `/projects/${pid}/safety/metrics`);
  }
  /** Bid leveling — submissions tabulated by package with low/high/avg/spread. */
  bidLeveling(pid: string) {
    return this.json<{ package_count: number; bid_count: number; packages: { package: string; bid_count: number; low: number | null; high: number | null; avg: number | null; spread: number; bids: { bidder: string | null; amount: number | null; is_low: boolean }[] }[] }>(
      `/projects/${pid}/bids/leveling`);
  }
  /** Conceptual estimate from the IFC takeoff × unit rates — priced line items + total. */
  estimateFromModel(pid: string) {
    return this.json<{ total: number; element_count: number; lines: { ifc_class: string; count: number; unit: string; quantity: number; rate: number; amount: number }[]; unpriced: { ifc_class: string; count: number }[] }>(
      `/projects/${pid}/estimate/from-model`);
  }
  /** Resource-based (assembly) estimate — each class priced by building the cost up from labor +
   *  material + equipment, returning the L/M/E split + total crew-hours (not just a blended $/unit). */
  estimateResourceBased(pid: string) {
    type Line = { ifc_class: string; assembly: string; assembly_name: string; count: number; unit: string;
      quantity: number; total: number; unit_cost: number; labor_hours: number; by_kind: { labor: number; material: number; equipment: number } };
    return this.json<{ total: number; element_count: number; labor_hours: number;
      by_kind: { labor: number; material: number; equipment: number };
      by_trade: { resource: string; name: string; hours: number; cost: number }[];
      lines: Line[]; unmapped: { ifc_class: string; count: number }[] }>(
      `/projects/${pid}/estimate/resource-based`);
  }
  /** DXF (2D CAD) quantity takeoff — linear metres, enclosed area and block counts per layer. */
  async takeoffDxf(pid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/takeoff/dxf`), {
      method: "POST", credentials: "include", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `takeoff failed (${res.status})`);
    return res.json() as Promise<{ units: string; unitless: boolean; layer_count: number; entity_count: number;
      total_length_m: number; total_area_m2: number;
      layers: { layer: string; entities: number; length_m: number; area_m2: number; inserts: number }[];
      blocks: { block: string; count: number }[] }>;
  }
  /** 2D -> BIM raise: turn an uploaded DXF floor plan into an IFC model (walls + spaces). `preview`
   *  just parses (returns wall/room counts); otherwise registers a "2D Raise" discipline model. */
  async raisePlan(pid: string, file: File, opts: { wallHeight?: number; wallThickness?: number; preview?: boolean } = {}) {
    const fd = new FormData(); fd.append("file", file);
    if (opts.wallHeight != null) fd.append("wall_height", String(opts.wallHeight));
    if (opts.wallThickness != null) fd.append("wall_thickness", String(opts.wallThickness));
    if (opts.preview) fd.append("preview", "true");
    const res = await fetch(this.url(`/projects/${pid}/raise-plan`), {
      method: "POST", credentials: "include", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `raise failed (${res.status})`);
    return res.json() as Promise<{ id?: string; discipline?: string; units: string;
      wall_count: number; space_count?: number; room_count?: number;
      total_wall_length_m: number; total_floor_area_m2: number;
      wall_height_m?: number; wall_thickness_m?: number }>;
  }
  /** QTO + cost by floor (storey) and discipline (IFC class) — quantities mapped to where they are. */
  qtoByFloor(pid: string) {
    type Line = { ifc_class: string; count: number; unit: string; quantity: number; rate: number; amount: number };
    return this.json<{ grand_total: number; element_count: number;
      storeys: { storey: string; total: number; element_count: number; lines: Line[] }[];
      by_discipline: Line[] }>(`/projects/${pid}/qto/by-floor`);
  }
  /** 4D construction sequence: scrubable frames (cumulative % built per day).
   *  Relational by default — when GC `schedule_activity` records exist they drive it (`source:"gc"`),
   *  each frame carrying a real calendar `date` + `linked`/`unlinked` element counts. Otherwise a takt
   *  plan; a P6 .xer import yields `source:"p6"` with interpolated dates. `?source=gc|takt` forces one. */
  schedule4d(pid: string, source?: "gc" | "takt") {
    return this.json<{ floors: number; duration_days?: number; total_days?: number; element_count: number;
      source: "takt" | "p6" | "gc"; start_date?: string; finish_date?: string; p6_activities?: number;
      activity_count?: number; linked?: number; unlinked?: number; by_trade: Record<string, number>;
      frames: { day: number; new: number; completed_cumulative: number; pct: number; date?: string; new_guids: string[] }[] }>(
      `/projects/${pid}/schedule/4d${source ? `?source=${source}` : ""}`);
  }
  /** Snapshot the current schedule as the baseline (variance is measured against it). */
  setBaseline(pid: string) {
    return this.json<{ captured_at: string; count: number }>(
      `/projects/${pid}/schedule/baseline`, { method: "POST" });
  }
  clearBaseline(pid: string) {
    return this.json<{ cleared: boolean }>(`/projects/${pid}/schedule/baseline`, { method: "DELETE" });
  }
  /** Per-activity slip vs the baseline (finish_var/start_var in days). 409 if no baseline set. */
  scheduleVariance(pid: string) {
    return this.json<{ captured_at: string; baseline_count: number; summary: Record<string, number>;
      activities: { ref: string; name: string; status: string; start_var: number | null; finish_var: number | null }[] }>(
      `/projects/${pid}/schedule/variance`);
  }
  /** Cost traceability coverage — cost tied to IFC elements by GlobalId, per cost code. */
  costTraceability(pid: string) {
    return this.json<{ total_cost: number; traceable_cost: number; untraceable_cost: number;
      coverage_pct: number; elements_referenced: number; line_count: number;
      by_cost_code: { cost_code: string; total: number; traceable: number; coverage_pct: number }[];
      note: string }>(`/projects/${pid}/cost/traceability`);
  }
  /** Every cost line (budget / commitment / direct cost / sub invoice) tagged to one IFC element. */
  elementCosts(pid: string, guid: string) {
    return this.json<{ guid: string; total: number; count: number; by_kind: Record<string, number>;
      lines: { kind: string; ref: string | null; cost_code: string | null; amount: number }[]; note: string }>(
      `/projects/${pid}/elements/${encodeURIComponent(guid)}/costs`);
  }
  /** Balanced double-entry journal from job cost + billing + the WIP POC adjustment. */
  journalEntries(pid: string) {
    return this.json<{ entries: { date: string; ref: string; memo: string; debit_total: number;
      credit_total: number; lines: { account: string; code: string; debit: number; credit: number }[] }[];
      debit_total: number; credit_total: number; balanced: boolean; note: string }>(
      `/projects/${pid}/accounting/journal-entries`);
  }
  /** Trial balance — debits and credits per account (must tie). */
  trialBalance(pid: string) {
    return this.json<{ accounts: { code: string; account: string; type: string; debit: number;
      credit: number; balance: number; balance_side: "debit" | "credit" }[];
      debit_total: number; credit_total: number; balanced: boolean; note: string }>(
      `/projects/${pid}/accounting/trial-balance`);
  }
  /** Contractor statements: POC income statement + contract-position (asset/liability, retainage, AP). */
  contractorStatements(pid: string) {
    return this.json<{ contract_value: number; percent_complete: number; backlog: number; note: string;
      income_statement: { revenue_earned: number; cost_of_revenue: number; gross_profit: number;
        gross_margin_pct: number; basis: string };
      contract_position: { contract_asset_underbillings: number; contract_liability_overbillings: number;
        retainage_receivable: number; accounts_payable: number; net_contract_working_capital: number } }>(
      `/projects/${pid}/contractor-statements`);
  }
  /** WIP schedule: POC → earned vs billed → over/under-billing, retainage, gross profit, backlog.
   *  `method`: "cost-to-cost" (default) or "units-installed" (physical model progress by GlobalId). */
  wip(pid: string, method: "cost-to-cost" | "units-installed" = "cost-to-cost") {
    return this.json<{ contract_value: number; estimated_cost: number; cost_to_date: number;
      cost_to_complete: number; percent_complete: number; pct_method: string; earned_revenue: number;
      billed_to_date: number; over_billing: number; under_billing: number;
      billing_status: "over-billed" | "under-billed" | "even";
      retainage: number; gross_profit: number; gross_margin_pct: number; profit_to_date: number;
      backlog: number; note: string;
      model?: { model_percent_complete: number; cost_percent_complete: number; divergence_pct: number;
        installed_elements: number; total_elements: number;
        flag: "cost-ahead" | "physical-ahead" | "aligned"; note: string };
    }>(`/projects/${pid}/wip?method=${encodeURIComponent(method)}`);
  }
  /** Physical % complete from the model: installed elements ÷ total by IFC GlobalId, optionally
   *  quantity-weighted. The independent "units-installed" signal that cross-checks cost-to-cost POC. */
  wipModelProgress(pid: string, quantity?: string) {
    const q = quantity ? `?quantity=${encodeURIComponent(quantity)}` : "";
    return this.json<{ available: boolean; method?: string; total_elements?: number;
      installed_elements?: number; percent_complete_count?: number; percent_complete?: number;
      quantity?: string; elements_with_quantity?: number; total_quantity?: number;
      installed_quantity?: number; percent_complete_quantity?: number; note: string
    }>(`/projects/${pid}/wip/model-progress${q}`);
  }
  /** Portfolio WIP: one row per project, worst cash position (largest under-billing) first. */
  wipPortfolio() {
    return this.json<{ projects: { id: string; name: string; contract_value: number; earned_revenue: number;
      billed_to_date: number; over_billing: number; under_billing: number; billing_status: string;
      percent_complete: number; gross_profit: number }[];
      totals: Record<string, number>; project_count: number; note: string }>(`/wip/portfolio`);
  }
  /** Cost-loaded resource histogram + unit/cost S-curves + over-allocation (from resource assignments). */
  resourceLoading(pid: string, cap?: number) {
    return this.json<{ source: string; loads: number; weeks_span: number; cap: number | null;
      trades: string[]; types: string[]; peak: { week: string | null; units: number }; total_cost: number;
      histogram: { week: string; total: number; cost: number; by_trade: Record<string, number>;
        by_type: Record<string, number> }[];
      scurve: { week: string; cumulative: number }[]; cost_curve: { week: string; cumulative: number }[];
      over_allocation: { week: string; units: number; cap: number | null }[]; note: string }>(
      `/projects/${pid}/schedule/resource-loading${cap != null ? `?cap=${cap}` : ""}`);
  }
  /** Resource-leveling advisory: over-allocated work with CPM float that can be smoothed within float. */
  resourceLeveling(pid: string, cap: number) {
    return this.json<{ cap: number; peak: { week: string | null; units: number }; over_weeks: number;
      critical_locked: number; suggestions: { assignment: string | null; resource: string | null;
        activity: string; trade: string | null; total_float_days: number; units: number | null;
        action: string }[]; note: string }>(`/projects/${pid}/schedule/resource-leveling?cap=${cap}`);
  }
  /** Schedule earned value: BAC / EV / PV / SPI + per-activity schedule variance. */
  scheduleEarnedValue(pid: string) {
    return this.json<{ bac: number; ev: number; pv: number; sv: number; spi: number | null;
      percent_complete: number; status: string; activity_count: number;
      activities: { ref: string; name: string; budget: number; percent: number; ev: number; pv: number; sv: number }[] }>(
      `/projects/${pid}/schedule/earned-value`);
  }
  /** Full EVM snapshot: PV/EV/AC/BAC, CV/SV/CPI/SPI + bands, the EAC/ETC/VAC/TCPI forecast family,
   *  and a per-control-account (cost code) breakdown — schedule EV joined with cost actuals. */
  evm(pid: string, dataDate?: string) {
    return this.json<{
      totals: { data_date: string; bac: number; pv: number; ev: number; ac: number; cv: number; sv: number;
        cpi: number | null; spi: number | null; cpi_band: string; spi_band: string;
        percent_complete: number; percent_spent: number;
        forecast: { eac: { cpi: number | null; at_plan: number; cpi_spi: number | null };
          eac_working: number | null; etc: number | null; vac: number | null;
          tcpi_bac: number | null; tcpi_eac: number | null; tcpi_warning: boolean;
          recommended: { stage: string; recommended_eac: string; guidance: string } };
        activity_count: number; note: string };
      control_accounts: { cost_code: string; bac: number; pv: number; ev: number; ac: number; cv: number;
        sv: number; cpi: number | null; spi: number | null; percent_complete: number }[];
      activities: { ref: string; name: string; cost_code: string; budget: number; percent: number;
        ev: number; pv: number; sv: number }[];
      earned_schedule: EvmEarnedSchedule | null;
    }>(`/projects/${pid}/evm${dataDate ? `?data_date=${dataDate}` : ""}`);
  }
  /** Earned Schedule (time-based EVM): ES, SV(t), SPI(t), IEAC(t) → forecast finish + PV curve. */
  earnedSchedule(pid: string, period: "week" | "month" = "week") {
    return this.json<EvmEarnedSchedule & { note?: string }>(
      `/projects/${pid}/evm/earned-schedule?period=${period}`);
  }
  /** Model-based EV: EV from physically-installed model elements × BAC, vs schedule EV. */
  evmModelEv(pid: string) {
    return this.json<{ total_elements: number; installed_elements: number; tracked_elements: number;
      model_percent_complete: number; has_field_data: boolean;
      bac: number; ev_model: number; ev_schedule: number; divergence: number; front_loaded_flag: boolean;
      note: string }>(`/projects/${pid}/evm/model-ev`);
  }
  /** EVM S-curve: cumulative PV (full baseline) + EV + AC to the data date, for the 3-line chart. */
  evmScurve(pid: string, period: "week" | "month" = "week") {
    return this.json<{ period: string; labels: string[]; pv: number[]; ev: number[]; ac: number[];
      bac: number; eac: number | null; data_date_period: number; note: string }>(
      `/projects/${pid}/evm/scurve?period=${period}`);
  }
  /** CPI/SPI performance-index trend across captured EVM snapshots (oldest-first). */
  evmTrend(pid: string) {
    return this.json<{ count: number; labels: string[]; cpi: number[]; spi: number[]; spi_t: number[];
      points: { data_date: string; period_label: string; cpi: number | null; spi: number | null;
        spi_t: number | null; eac: number | null; percent_complete: number | null }[]; note: string }>(
      `/projects/${pid}/evm/trend`);
  }
  /** Capture the current EVM state as a dated snapshot baseline (feeds the trend). */
  evmCaptureSnapshot(pid: string, body: { data_date?: string; period_label?: string; notes?: string } = {}) {
    return this.json<{ id: string; ref: string }>(`/projects/${pid}/evm/snapshot`,
      { method: "POST", body: JSON.stringify(body) });
  }
  /** Full GC project budget (GMP): direct + GC/GR + overhead/fee/contingency, each budget vs
   *  committed vs actual vs variance; reconciled to the prime contract + developer proforma. */
  gmpBudget(pid: string) {
    type Cat = { key: string; name: string; budget: number; committed: number; actual: number;
      forecast: number; eac: number; etc: number; variance: number; lines: { name: string; budget: number;
      committed: number; eac?: number; etc?: number; variance: number; is_group?: boolean }[];
      groups?: { name: string; budget: number }[] };
    return this.json<{
      gmp: { contract_value: number; computed: number; reconciliation: number | null; cost_of_work: number;
        approved_changes?: number; unallocated_changes?: number; revised?: number;
        markups: { overhead_pct: number; fee_pct: number; contingency_pct: number } };
      categories: Cat[];
      totals: { budget: number; committed: number; actual: number; forecast: number; eac: number; etc: number; variance: number };
      completion: { bac: number; eac: number; etc: number; actual_to_date: number; projected_over_under: number; pct_spent: number };
      bid_packages: { ref: string; name: string; trade?: string; budget: number; awarded: number;
        bought_out: boolean; savings: number; submissions: number }[];
      buyout: { packages: number; bought_out: number; budget: number; awarded: number; savings: number };
      staffing: { projected: number; headcount_roles: number };
      proforma: { hard_cost: number; gmp_vs_hard: number } | null;
    }>(`/projects/${pid}/budget/gmp`);
  }
  /** PX executive health: on-schedule (SPI, % complete, critical path, lookahead, milestones) next
   *  to on-budget (GMP, EAC, variance-at-completion, buyout, cash flow), with an overall status. */
  pxSummary(pid: string) {
    return this.json<{
      status: "on_track" | "at_risk" | "behind";
      schedule: { spi: number | null; pct_complete: number; activities: number; critical_path_days: number;
        critical_activities: number; lookahead_3wk: number; milestones: { late: number; due_soon: number; upcoming: number } };
      budget: { gmp: number; revised_gmp: number; eac: number; variance_at_completion: number; committed: number;
        committed_pct: number; spent_pct: number; draw_this_month: number;
        buyout: { packages: number; bought_out: number; savings: number } | null; baseline_movement: number | null };
    }>(`/projects/${pid}/px-summary`);
  }
  /** Snapshot the current GMP budget as the baseline (for budget-movement tracking). */
  setBudgetBaseline(pid: string) {
    return this.json<{ captured_at: string; gmp_computed: number; lines: number }>(
      `/projects/${pid}/budget/baseline`, { method: "POST" });
  }
  /** Budget movement vs the baseline (per category + line). Rejects if no baseline set. */
  budgetVariance(pid: string) {
    return this.json<{ captured_at: string; baseline_gmp: number; current_gmp: number; total_delta: number;
      categories: { key: string; baseline: number; current: number; delta: number }[];
      lines: { code: string; baseline: number; current: number; delta: number }[] }>(
      `/projects/${pid}/budget/variance`);
  }
  /** Cost-loaded schedule → monthly cash-flow / draw curve (construction S-curve). */
  budgetCashflow(pid: string) {
    return this.json<{ total: number; months: number; loaded_activities: number; peak_month_cost: number;
      series: { month: string; cost: number; cumulative: number; pct: number }[] }>(
      `/projects/${pid}/budget/cashflow`);
  }
  /** Seed the owner pay-app SOV from the GMP budget lines (idempotent unless replace). */
  sovFromBudget(pid: string, replace = false) {
    return this.json<{ created: number; lines?: number; scheduled_value?: number; skipped?: number; note?: string }>(
      `/projects/${pid}/cost/sov/from-budget?replace=${replace}`, { method: "POST" });
  }
  /** The owner pay application (G702 certificate + G703 continuation) as a signable PDF blob. */
  async payAppPdf(pid: string, appNo = 1) {
    const res = await fetch(this.url(`/projects/${pid}/cost/g702.pdf?app_no=${appNo}`), { headers: this.authHeaders() });
    if (!res.ok) throw new Error(`pay-app PDF -> ${res.status}`);
    return res.blob();
  }
  /** Create an owner-invoice record from the current pay application (amount = current payment due). */
  payAppInvoice(pid: string, appNo = 1) {
    return this.json<{ owner_invoice: ModuleRecord; application_no: number; amount: number }>(
      `/projects/${pid}/cost/pay-app/invoice`, { method: "POST", body: JSON.stringify({ app_no: appNo }) });
  }
  /** Short-interval lookahead: near-term activities grouped by week (the field's 3-/6-week plan). */
  scheduleLookahead(pid: string, weeks = 3) {
    return this.json<{ start: string; finish: string; weeks: number; count: number;
      weeks_detail: { week: string; activities: { ref: string; name: string; trade?: string;
        start?: string; finish?: string; percent: number; status: string }[] }[] }>(
      `/projects/${pid}/schedule/lookahead?weeks=${weeks}`);
  }
  /** Milestone schedule: the key dates with status (met / due_soon / upcoming / late). */
  scheduleMilestones(pid: string) {
    return this.json<{ count: number; summary: Record<string, number>;
      milestones: { ref: string; name: string; date?: string; days_out?: number; percent: number; status: string }[] }>(
      `/projects/${pid}/schedule/milestones`);
  }
  /** Schedule visual (Gantt or Line-of-Balance) as inline SVG text, over the schedule_activity records. */
  async scheduleSvg(pid: string, kind: "gantt" | "lob") {
    if (IS_DEMO) return demoTextOr(`/projects/${pid}/schedule/${kind}.svg`, "");
    const res = await fetch(this.url(`/projects/${pid}/schedule/${kind}.svg`), { headers: this.authHeaders() });
    if (!res.ok) throw new Error(`schedule ${kind}: ${res.status}`);
    return res.text();
  }
  /** The takt line-of-balance chart with the ACTUAL ascent overlaid (dashed) on the plan. */
  async taktSvg(pid: string) {
    if (IS_DEMO) return demoTextOr(`/projects/${pid}/schedule/takt.svg`, "");
    const res = await fetch(this.url(`/projects/${pid}/schedule/takt.svg`), { headers: this.authHeaders() });
    if (!res.ok) throw new Error(`takt svg: ${res.status}`);
    return res.text();
  }
  /** Actual-vs-takt production tracking for the project (per-trade variance + rates) + bundled PPC. */
  taktProgress(pid: string) {
    return this.json<TaktProgressResult>(`/projects/${pid}/schedule/takt/progress`);
  }
  /** The module-relations graph: nodes = modules, edges = reference + rollup links (optional workspace). */
  modulesGraph(workspace?: string) {
    const qs = workspace ? `?workspace=${encodeURIComponent(workspace)}` : "";
    return this.json<ModuleGraph>(`/modules/graph${qs}`);
  }
  /** M1 material palette: default table + saved per-project overrides + the effective (merged) palette. */
  materialPalette(pid: string) {
    return this.json<MaterialPaletteResult>(`/projects/${pid}/materials/palette`);
  }
  saveMaterialPalette(pid: string, overrides: Record<string, MaterialEntry>) {
    return this.json<{ overrides: Record<string, MaterialEntry>; effective: Record<string, MaterialEntry> }>(
      `/projects/${pid}/materials/palette`, { method: "PUT", body: JSON.stringify({ overrides }) });
  }
  applyMaterialPalette(pid: string) {
    return this.json<{ applied: { styled: number; materialed: number; materials: number; classes: number }; publish: string }>(
      `/projects/${pid}/materials/apply`, { method: "POST" });
  }
  /** Import a Primavera P6 export (.xer or .xml/PMXML — auto-detected) so the 4D scrub reports
   *  real calendar dates and the tasks become editable schedule_activity records. */
  async importXer(pid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/schedule/import-xer`), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `import -> ${res.status}`); }
    return res.json() as Promise<{ count: number; start: string | null; finish: string | null; preview: { activity_id: string; name: string; start: string; finish: string }[] }>;
  }
  clearXer(pid: string) {
    return this.json<{ cleared: boolean }>(`/projects/${pid}/schedule/import-xer`, { method: "DELETE" });
  }
  /** CPM analysis of the schedule activities — float + critical path. */
  scheduleCpm(pid: string) {
    return this.json<{ project_duration: number; activity_count: number; critical_count: number; has_cycle: boolean; critical_path: string[]; activities: { ref: string | null; name: string; duration: number; es: number; ef: number; total_float: number; critical: boolean }[] }>(
      `/projects/${pid}/schedule/cpm`);
  }
  /** Developer cost budget (line-item hard/soft/acquisition + contingencies) + computed summary. */
  devBudget(pid: string) {
    return this.json<DevBudgetResponse>(`/projects/${pid}/dev-budget`);
  }
  saveDevBudget(pid: string, budget: { lines: DevBudgetLine[]; contingency: Record<string, number> }) {
    return this.json<DevBudgetResponse>(`/projects/${pid}/dev-budget`, { method: "PUT", body: JSON.stringify(budget) });
  }
  /** Reconcile the developer's construction hard cost against the GC's live GMP. */
  gmpReconciliation(pid: string) {
    return this.json<{ dev_hard_cost: number; gc_gmp: number; delta: number; in_sync: boolean;
      gmp_committed: number; gmp_eac: number; gmp_variance_at_completion: number }>(
      `/projects/${pid}/dev-budget/gmp-reconciliation`);
  }
  /** Developer construction draw schedule sourced from the GC cost-loaded schedule + actual billed. */
  constructionDraws(pid: string) {
    return this.json<{ projected_total: number; months: number; peak_month_cost: number;
      series: { month: string; cost: number; cumulative: number; pct: number }[];
      actual_billed: number; invoice_count: number; pct_billed: number;
      by_cost_code: { code: string; description: string | null; division: string | null; billed: number }[] }>(
      `/projects/${pid}/construction-draws`);
  }
  /** Construction-loan draw status: owner invoices funded equity-first then debt vs the sized stack. */
  loanDraws(pid: string) {
    return this.json<{ loan_amount: number; equity: number; drawn_to_date: number; equity_drawn: number;
      loan_drawn: number; loan_available: number; loan_balance: number; pct_capital_drawn: number;
      interest_rate: number; accrued_interest: number; loan_start: string | null; outstanding_with_interest: number;
      budgeted_interest_reserve: number; forecast_interest: number; interest_variance: number;
      invoice_count: number }>(`/projects/${pid}/loan-draws`);
  }
  /** Lender draw-request PDF (the bank-facing submission) as an auth'd blob. */
  async loanDrawRequestPdf(pid: string, appNo = 1) {
    const res = await fetch(this.url(`/projects/${pid}/loan-draws/request.pdf?app_no=${appNo}`), { headers: this.authHeaders() });
    if (!res.ok) throw new Error(`draw request PDF -> ${res.status}`);
    return res.blob();
  }
  /** Cross-project executive roll-up: each project's on-schedule + on-budget status + portfolio totals. */
  executivePortfolio() {
    return this.json<{
      projects: { id: string; name: string; status: "on_track" | "at_risk" | "behind"; spi: number | null;
        cpi: number | null;
        pct_complete: number; lookahead_3wk: number; milestones_late: number; gmp: number; eac: number;
        variance_at_completion: number; committed_pct: number; equity_irr: number | null; equity_multiple: number | null }[];
      totals: { gmp: number; eac: number; variance_at_completion: number; committed: number; equity: number; blended_equity_irr: number | null };
      status_tally: { on_track: number; at_risk: number; behind: number }; project_count: number }>(
      `/portfolio/executive`);
  }
  /** Portfolio prioritization — projects ranked 0-100 on return / budget / schedule / risk. */
  portfolioPrioritization() {
    type Scores = { return: number; budget: number; schedule: number; risk: number };
    return this.json<{ weights: Scores; criteria: string[];
      projects: { id: string; name: string; status: string; rank: number; composite: number;
        scores: Scores; equity_irr: number | null; gmp: number }[];
      top: { name: string } | null; bottom: { name: string } | null; note: string }>(
      `/portfolio/prioritization`);
  }
  /** Subcontractor billing rollup — each subcontract's pay apps vs contract value (GC-pays-subs). */
  subcontractorBilling(pid: string) {
    return this.json<{ subs: { subcontract_ref: string | null; vendor: string | null; trade: string | null;
      cost_code: string | null; contract_value: number; billed: number; retainage: number; paid: number;
      remaining: number; applications: number }[];
      totals: { contract_value: number; billed: number; retainage: number; paid: number; remaining: number };
      subcontract_count: number; invoice_count: number }>(`/projects/${pid}/subcontractor-billing`);
  }
  /** Set the developer hard cost to the GC's GMP (replaces hard lines with one synced line). */
  syncGmpToHard(pid: string) {
    return this.json<{ synced: boolean; hard_cost: number; budget: { lines: DevBudgetLine[]; contingency: Record<string, number> }; summary: DevBudgetSummary }>(
      `/projects/${pid}/dev-budget/sync-gmp`, { method: "POST" });
  }
  devBudgetCostLines(pid: string) {
    return this.json<{ cost_lines: { category: string; name: string; amount: number; curve: string }[]; summary: DevBudgetSummary }>(
      `/projects/${pid}/dev-budget/cost-lines`);
  }
  /** Property & tax assumptions + computed summary (totals, per-SF ratios, proforma deltas). */
  property(pid: string) {
    return this.json<{ property: Record<string, unknown>; summary: { total_taxes: number; purchase_price: number; price_per_building_sf: number; tax_per_building_sf: number; far_existing: number; deltas: { opex_annual_add: number; acquisition_amount: number } } }>(
      `/projects/${pid}/property`);
  }
  saveProperty(pid: string, body: Record<string, unknown>) {
    return this.json<{ property: Record<string, unknown>; summary: { total_taxes: number; purchase_price: number; deltas: { opex_annual_add: number; acquisition_amount: number } } }>(
      `/projects/${pid}/property`, { method: "PUT", body: JSON.stringify(body) });
  }
  /** Test-fit: compare unit-mix schemes on a floor plate (yield + parking, ranked). */
  testFitCompare(params: { plate_w: number; plate_d: number; floors: number; schemes?: unknown[]; with_defaults?: boolean }) {
    return this.json<{ best: string | null; schemes: { name: string; total_units: number; efficiency: number; daylight_efficiency: number; daylight_limited: boolean; total_nsf: number; total_gsf: number; avg_unit_sf: number; parking_stalls: number; mix: Record<string, number> }[]; egress?: EgressResult }>(
      "/test-fit/compare", { method: "POST", body: JSON.stringify(params) });
  }
  /** Generative design: sweep schemes (× optional plate depths), filter by targets, rank by yield-on-cost.
   * Pass `depths` or `targets.sweep_depth` to make daylight-limited plate depth an optimize dimension. */
  testFitOptimize(params: { plate_w: number; plate_d: number; floors: number;
    targets?: Record<string, number | string | boolean>; econ?: Record<string, number>; depths?: number[] }) {
    return this.json<{ considered: number; feasible: number; objective: string; best: OptScheme | null;
      ranked: OptScheme[]; swept_depths: number[]; depth_curve: DepthPoint[]; best_depth_m: number | null }>(
      "/test-fit/optimize", { method: "POST", body: JSON.stringify(params) });
  }
  /** Sources & Uses built from the project's cost budget (grouped uses vs sized debt + equity). */
  sourcesUses(pid: string) {
    return this.json<{ uses: { label: string; amount: number }[]; sources: { label: string; amount: number }[];
      total_uses: number; total_sources: number; ltc: number; debt: number; equity: number;
      binding_constraint: string; balanced: boolean }>(`/projects/${pid}/sources-uses`);
  }
  /** Specialty assets (on-site energy + vertical-farm/PFAL) params + computed summary + deltas. */
  specialty(pid: string) {
    return this.json<SpecialtyResponse>(`/projects/${pid}/specialty`);
  }
  saveSpecialty(pid: string, params: Record<string, unknown>) {
    return this.json<SpecialtyResponse>(`/projects/${pid}/specialty`, { method: "PUT", body: JSON.stringify(params) });
  }
  /** Multi-year specialty P&L with a production ramp + a specialty-only IRR (U4 depth). */
  specialtyProforma(pid: string, opts?: { years?: number; ramp_years?: number; ramp_start?: number; terminal_cap?: number }) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts || {})) if (v != null) q.set(k, String(v));
    const qs = q.toString();
    return this.json<{ proforma: SpecialtyProforma }>(`/projects/${pid}/specialty/proforma${qs ? "?" + qs : ""}`);
  }
  /** Blend the saved specialty business into the deal's equity cash flows: RE-only vs blended IRR. */
  specialtyBlended(pid: string, assumptions: unknown, opts?: { years?: number; ramp_years?: number; ramp_start?: number; terminal_cap?: number }) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts || {})) if (v != null) q.set(k, String(v));
    const qs = q.toString();
    return this.json<{ blended: SpecialtyBlended }>(`/projects/${pid}/specialty/blended${qs ? "?" + qs : ""}`,
      { method: "POST", body: JSON.stringify(assumptions) });
  }
  /** Monte-Carlo the specialty risk discount → distribution of blended & specialty IRR. */
  specialtyMonteCarlo(pid: string, body: {
    assumptions: unknown; variables: { path: string; dist: Record<string, unknown> }[];
    iterations?: number; seed?: number; targets?: Record<string, number>;
    years?: number; ramp_years?: number; ramp_start?: number; terminal_cap?: number;
  }) {
    return this.json<{ iterations: number; metrics: Record<string, MonteCarloMetric> }>(
      `/projects/${pid}/specialty/monte-carlo`, { method: "POST", body: JSON.stringify(body) });
  }
  /** Proforma seed metrics derived from the project's source IFC (areas / space + storey counts). */
  proformaModelMetrics(pid: string) {
    return this.json<{ space_count: number; spaces_with_area: number; storey_count: number; net_floor_area_m2: number; net_floor_area_sf: number }>(
      `/projects/${pid}/proforma/model-metrics`);
  }
  /** Upload an IFC as the project's source model (sets source_ifc + publishes) — what lights up
   *  drawings, clash/IDS, energy, exports, and authoring for the project. */
  async uploadSourceIfc(pid: string, file: File, publish = true) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/source-ifc?publish=${publish}`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `upload -> ${res.status}`); }
    return res.json() as Promise<{ source_ifc: string; publish?: string }>;
  }
  /** Is the optional paid Revit→IFC bridge configured? (+ cost warning / free alternative text). */
  rvtBridgeStatus() {
    return this.json<{ enabled: boolean; activity_configured: boolean; cost_warning: string;
      free_alternative: string; message: string }>(`/bridge/rvt/status`);
  }
  /** Import a native .rvt via the paid APS bridge (must confirm cost). 501 off · 402 unconfirmed. */
  async importRvt(pid: string, file: File, confirmCost: boolean) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/import/rvt?confirm_cost=${confirmCost}`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `rvt import -> ${res.status}`); }
    return res.json() as Promise<{ source_ifc: string; size: number; source: string; publish?: string }>;
  }
  editIfc(pid: string, recipe: string, params: Record<string, unknown>, publish = true) {
    return this.json<{ recipe: string; changed: number | string; published: unknown }>(
      `/projects/${pid}/edit`, { method: "POST", body: JSON.stringify({ recipe, params, publish }) });
  }
  /** Incremental one-element preview fragment (real geometry, fast) while the full model republishes.
   *  Returns the fragment bytes + new element GUID, or null (fail-open → the viewer keeps its proxy). */
  async editPreview(pid: string, recipe: string, params: Record<string, unknown>):
      Promise<{ frag: ArrayBuffer; guid: string } | null> {
    try {
      const res = await fetch(this.url(`/projects/${pid}/edit-preview`), {
        method: "POST", headers: { "Content-Type": "application/json", ...this.authHeaders() },
        body: JSON.stringify({ recipe, params }),
      });
      if (!res.ok) return null;
      return { frag: await res.arrayBuffer(), guid: res.headers.get("X-Element-Guid") || "" };
    } catch { return null; }
  }
  /** Starter IFC family library (furniture / sanitary / appliances / plants) — generated
   *  parametrically, so it's placeable into any model incl. a from-scratch massing model. */
  /** Drafting grid (real IfcGrid or derived from columns) + snap intersections + storey levels. */
  modelGrid(pid: string) {
    return this.json<{
      grid: { source: string;
        axes: { tag: string; dir: "u" | "v"; start: [number, number]; end: [number, number] }[];
        intersections: { x: number; y: number; label: string }[];
        bounds: { min: [number, number]; max: [number, number] } | null; note?: string };
      levels: { name: string | null; elevation: number }[];
    }>(`/projects/${pid}/model/grid`);
  }
  familyCatalog() {
    return this.json<{ count: number; categories: Record<string, FamilyItem[]> }>("/families/catalog");
  }
  /** The shippable IFC family library: the generated parametric catalog (grouped) plus the
   *  generated `library.ifc` and any curated external `.ifc` files. */
  familyLibrary() {
    return this.json<{ count: number; categories: Record<string, FamilyItem[]>;
      generated_library: { exists: boolean; size_bytes: number };
      external: { name: string; size_bytes: number }[] }>("/families/library");
  }
  /** Place a library family (thin wrapper over the add_family recipe). */
  placeFamily(pid: string, family: string, position?: [number, number] | null) {
    return this.json<{ recipe: string; changed: number | string; publish?: string }>(
      `/projects/${pid}/families/place`, { method: "POST",
      body: JSON.stringify({ family, position: position || undefined, publish: true }) });
  }
  /** Place a starter-library family on a storey (optionally at an [E,N] point in metres), then
   *  publish the round-trip. Reuses the `add_family` edit recipe. */
  addFamily(pid: string, family: string, position?: [number, number] | null, storey?: string | null) {
    const params: Record<string, unknown> = { family };
    if (position) params.position = position;
    if (storey) params.storey = storey;
    return this.editIfc(pid, "add_family", params, true);
  }
  /** Import external IFC type content (manufacturer / 3rd-party families) from an uploaded IFC into
   *  the project; imported types then appear in the place-family picker. */
  async importFamilies(pid: string, file: File, publish = true) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/families/import?publish=${publish}`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `import -> ${res.status}`); }
    return res.json() as Promise<{ imported: { guid: string; name: string; ifc_class: string }[]; count: number; publish?: string }>;
  }
  publish(pid: string) {
    return this.json<{ state: string }>(
      `/projects/${pid}/publish`, { method: "POST", body: JSON.stringify({ reconvert: true }) });
  }
  /** Computational-graph (M4) node palette — each node's input/output ports for the visual editor. */
  computeNodes() {
    return this.json<{ nodes: ComputeNodeSpec[] }>("/compute/nodes");
  }
  /** Run a {nodes, edges} compute graph; returns each node's outputs + the execution order. */
  runGraph(graph: ComputeGraph) {
    return this.json<{ order: string[]; results: Record<string, Record<string, unknown>>; node_count: number }>(
      "/compute/graph", { method: "POST", body: JSON.stringify(graph) });
  }
  publishStatus(pid: string) {
    return this.json<{ state: "idle" | "running" | "done" | "error"; detail?: Record<string, unknown> }>(
      `/projects/${pid}/publish/status`);
  }
  /** Generative massing — zoning envelope → program (+ proforma) WITHOUT writing a model. Instant. */
  previewMassing(params: MassingParams) {
    return this.json<MassingResult>("/generate/massing/preview", { method: "POST", body: JSON.stringify(params) });
  }
  /** Generate an IFC massing model from a zoning envelope, set it as the project's source IFC,
   *  publish it (off-thread), and return the program + a starter acquisition proforma. */
  generateMassing(pid: string, params: MassingParams) {
    return this.json<MassingResult & { source_ifc: string; publish: string }>(
      `/projects/${pid}/generate/massing`, { method: "POST", body: JSON.stringify(params) });
  }
  /** Create a blank authoring model (base IFC + levels + ground datum) — the from-scratch start for
   *  the in-browser modeler; sets it as the project's source IFC + publishes. */
  createBlankModel(pid: string, opts?: { name?: string; storeys?: number; storey_height?: number }) {
    return this.json<{ storeys: number; storey_height: number; source_ifc: string; publish: string }>(
      `/projects/${pid}/model/blank`, { method: "POST", body: JSON.stringify(opts || {}) });
  }
}

export interface DevBudgetLine {
  category: "acquisition" | "hard" | "soft";
  description: string; unit_cost: number; quantity: number; cost_code?: string | null;
}
export interface DevBudgetCategory {
  subtotal: number; contingency: number; contingency_pct: number; total: number;
  lines: { description: string; unit_cost: number; quantity: number; total: number; cost_code?: string | null }[];
}
export interface DevBudgetSummary {
  categories: Record<string, DevBudgetCategory>;
  grand_total: number; hard_pct: number; soft_pct: number; line_count: number;
}
export interface DevBudgetResponse {
  budget: { lines: DevBudgetLine[]; contingency: Record<string, number> };
  summary: DevBudgetSummary;
}
export interface OptScheme {
  name: string; mix_preset: string; parking_ratio: number; total_units: number;
  efficiency: number; total_nsf: number; parking_stalls: number; yield_on_cost: number;
  plate_d?: number; daylight_efficiency?: number; core_efficiency?: number;
  daylight_limited?: boolean; dev_spread_bps?: number;
}
export interface DepthPoint {
  plate_d: number; yield_on_cost: number; daylight_efficiency: number;
  core_efficiency: number; total_units: number; dev_spread_bps: number;
}
export interface SpecialtySummary {
  capex_total: number; annual_revenue: number; annual_opex: number;
  annual_energy_offset: number; annual_net_contribution: number;
  energy: { solar_panels: number; capex: number; generation_kwh_yr: number; annual_energy_offset: number } | null;
  pfal: { towers: number; annual_revenue: number; annual_opex: number; startup_capex: number } | null;
}
export interface SpecialtyResponse {
  params: Record<string, unknown>;
  summary: SpecialtySummary;
  deltas: { cost_line: { category: string; name: string; amount: number; curve: string } | null;
    other_income_annual_add: number; opex_annual_add: number };
}
export interface ModuleGraphNode {
  key: string; label: string; section: string; workspace: string; icon: string;
  in_degree: number; out_degree: number;
}
export interface ModuleGraphEdge {
  source: string; target: string; field: string | null; label: string; kind: "reference" | "rollup";
}
export interface ModuleGraph {
  workspace: string | null; node_count: number; edge_count: number;
  nodes: ModuleGraphNode[]; edges: ModuleGraphEdge[];
  most_referenced: { key: string; label: string; in_degree: number }[]; orphan_count: number;
}
export interface MaterialEntry {
  name: string; category: string; color: [number, number, number]; transparency: number;
}
export interface MaterialPaletteResult {
  default: Record<string, MaterialEntry>;
  overrides: Record<string, MaterialEntry>;
  effective: Record<string, MaterialEntry>;
}
export interface TaktProgressRow {
  trade: string; as_of_day: number; floors_done: number; planned_done: number;
  variance_floors: number; actual_floors_per_week: number; planned_floors_per_week: number;
  status: "ahead" | "behind" | "on-takt";
}
export interface TaktProgressResult {
  floors: number;
  plan: { floors: number; duration_days: number; duration_weeks: number; floors_per_week: number;
    trades: { name: string; takt_days: number; start_day: number; finish_day: number }[] };
  progress: { as_of_day: number; rows: TaktProgressRow[]; lead_trade: string | null;
    lead_actual_floors_per_week: number; planned_floors_per_week: number;
    total_variance_floors: number; overall_status: "ahead" | "behind" | "on-takt" };
  ppc: { commitments: number; completed: number; ppc: number; missed: number; rating: string };
}
export interface SpecialtyProformaRow {
  year: number; op_year: number; ramp: number; revenue: number; energy_offset: number;
  opex: number; net: number; cumulative: number;
}
export interface SpecialtyProforma {
  years: number; ramp_years: number; ramp_start: number; terminal_cap: number;
  capex_total: number; stabilized_net_annual: number; terminal_value: number;
  rows: SpecialtyProformaRow[]; cumulative_net: number;
  specialty_irr: number | null; payback_op_year: number | null;
}
export interface SpecialtyBlended {
  re_only_irr: number | null; blended_irr: number | null; irr_lift: number | null;
  error?: string;
  specialty?: { specialty_irr: number | null; capex_total: number; stabilized_net_annual: number;
    terminal_value: number; payback_op_year: number | null };
}
export interface FamilyItem {
  key: string; label: string; ifc_class: string; category: string; dims: [number, number, number];
}
/** A family type row (W10-1 type browser) — placeable IfcTypeProduct with its occurrence count. */
export interface TypeRow {
  guid: string; name: string; ifc_class: string; predefined: string | null;
  has_geometry: boolean; occurrence_count: number;
}
/** A named set of elements (W10-3) — IfcGroup with its member count. */
export interface GroupRow { guid: string; name: string; kind: string; members: number; }
/** A part-of whole (W10-3) — IfcElementAssembly with its part count. */
export interface AssemblyRow { guid: string; name: string; predefined: string | null; parts: number; }
/** Full type inspector (W10-1) — dims, type Psets, material layers, and placed occurrences. */
export interface TypeDetail {
  guid: string; name: string; ifc_class: string; predefined: string | null;
  dims: [number, number, number] | null; has_geometry: boolean;
  psets: Record<string, Record<string, unknown>>;
  materials: { material: string | null; thickness: number | null }[];
  occurrence_count: number;
  occurrences: { guid: string; name: string; ifc_class: string }[];
}
export interface EvmEarnedSchedule {
  period: string; planned_start: string; planned_finish: string;
  planned_duration_periods: number; actual_time_periods: number; earned_schedule_periods: number;
  sv_t_periods: number; spi_t: number | null; spi_t_band: string;
  ieac_t_periods: number | null; forecast_finish: string | null; days_late: number | null;
  bac: number; ev: number; curve: { period: number; date: string; pv: number }[]; note: string;
}
export interface EgressResult {
  compliant: boolean; flags: string[]; max_travel_m: number; limit_m: number;
  occupant_load_per_floor: number; min_exits_required: number;
  exit_separation_m: number; required_separation_m: number;
}
export interface ComputeNodeSpec {
  key: string; label: string; category: string; doc: string;
  inputs: { name: string; default: number | string | null }[];
  outputs: string[];
}
export interface ComputeGraph {
  nodes: { id: string; type: string; params: Record<string, number | string> }[];
  edges: { from: string; from_port: string; to: string; to_port: string }[];
}
export interface MassingParams {
  name?: string; use_type?: "residential" | "commercial";
  lot_width?: number | null; lot_depth?: number | null; lot_area?: number | null;
  far?: number; coverage_max?: number; front_setback?: number; rear_setback?: number;
  side_setback?: number; height_limit?: number | null; floor_to_floor?: number;
  efficiency?: number; avg_unit_m2?: number;
  frame?: boolean; bay_m?: number; units?: boolean; envelope?: boolean; wwr?: number; core?: boolean;
  unit_layout?: "grid" | "corridor"; parking?: number;
  shape?: "box" | "dome"; dome_radius?: number;
  land_cost?: number; hard_cost_psf?: number; rent_per_unit_month?: number; rent_psf_year?: number;
  exit_cap?: number; ltc?: number; rate?: number;
}
export interface MassingMetrics {
  lot_area_m2: number; far: number; far_achieved: number; footprint_m2: number;
  plate_w: number; plate_d: number; floors: number; floor_to_floor: number;
  building_height_m: number; buildable_gfa_m2: number; buildable_gfa_sf: number;
  net_sellable_m2: number; units: number; binding_constraint: string;
  structure?: { system: string; lateral_system: string; rationale: string; load_path: string;
    slenderness: number; members_mm: { slab: number; beam_depth: number; column: number; uses_beams: boolean };
    column_schedule?: { floor: number; floors_carried: number; side_mm: number }[];
    base_column_mm?: number; top_column_mm?: number;
    lateral_core?: { provided: boolean; plan_w_m: number; plan_d_m: number; wall_mm: number; note: string };
    flags: string[] };
}
export interface MassingResult {
  metrics: MassingMetrics;
  proforma: { assumptions: Record<string, unknown>;
    returns?: { equity_irr?: number; equity_multiple?: number } | null;
    sources_uses?: { total_uses?: number; equity?: number; loan_amount?: number } | null;
    solve_error?: string };
}

export interface ClashResult {
  count: number;
  created_topics: number;
  truncated: boolean;
  clashes: { a_guid: string; a_class: string; b_guid: string; b_class: string; volume: number; method: "mesh" | "aabb"; point: Vec3 }[];
}

export interface ValidationResult {
  title: string;
  status: "pass" | "fail";
  summary: { specifications: number; passed: number; failed: number };
  specifications: { name: string; status: "pass" | "fail"; applicable: number; passed: number; failed: number; failed_guids: string[] }[];
}
