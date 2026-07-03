/** Typed client for the backend API (guide §7). Geometry comes from .frag; all element
 *  metadata and work artifacts (pins/RFIs/viewpoints) come from here. */
import { IS_DEMO, demoJson, demoTextOr } from "../demo/demoApi";

export interface ElementProps {
  guid: string;
  ifc_class: string;
  name: string | null;
  type_name: string | null;
  storey: string | null;
  psets: Record<string, Record<string, unknown>>;
  qtos: Record<string, Record<string, unknown>>;
}

/** Project-scoped capability role, least→most privileged. */
export type ProjectRole = "viewer" | "reviewer" | "editor" | "admin";

/** One admin integration setting (AI/email/SSO). Secret values are never sent to the client. */
export interface IntegrationKey {
  key: string; label: string; secret: boolean; configured: boolean; value?: string;
}
export interface IntegrationGroup { group: string; keys: IntegrationKey[] }

/** A markup pin on a 2D sheet (intrinsic sheet coords); topic_id set once promoted to an RFI. */
export interface DrawingMarkupItem {
  id: string; sheet_id: string; x: number; y: number; note: string | null;
  author: string | null; topic_id: string | null; created_at: string;
}

/** A registered data-source connection (local DB / Postgres / Supabase / Procore). */
export interface ConnectionItem {
  id: string; name: string; type: string; builtin?: boolean;
  config: Record<string, unknown>;
  status?: { ok: boolean; detail: string };
}

/** A normalized municipal building-permit filing from a city's open data feed. */
export interface OpendataPermit {
  source: string; city: string; authority: string;
  permit_number: string | null; permit_type: string | null; status: string | null;
  address: string | null; lat: number | null; lon: number | null;
  owner: string | null; applicant: string | null; contractor: string | null;
  units: number | null; floor_area: number | null; est_cost: number | null; fee: number | null;
  filed_date: string | null; issued_date: string | null; expires_date: string | null;
  description: string | null; url: string | null;
}

/** A recurring Procore→modules auto-sync schedule. */
export interface SyncScheduleItem {
  id: string; connection_id: string; procore_project_id: string; kinds: string[];
  interval_minutes: number; enabled: boolean; push: boolean;
  last_run: string | null; last_result: { imported_total?: number; error?: string } | null;
}

/** A user's membership of one project: capability role + optional workflow party + company. */
export interface ProjectMember {
  user: string;
  role: ProjectRole;
  party_role: string | null;
  company: string | null;
}

/** One row of the server audit trail (admin-readable). */
export interface AuditEntry {
  id: string;
  ts: string;
  actor: string | null;
  action: string;
  method: string | null;
  path: string | null;
  topic_id: string | null;
  detail: Record<string, unknown> | null;
}

/** A global account (identity). Per-project authorization lives in project members. */
export interface AccountUser {
  username: string;
  role: "admin" | "user";
  active: boolean;
  email: string | null;
  created_at: string;
}

export interface Topic {
  id: string;
  guid: string;
  project_id: string;
  type: "rfi" | "punch" | "clash" | "info";
  title: string;
  description: string | null;
  status: string;
  priority: string | null;
  assignee: string | null;
  anchor: { x: number; y: number; z: number } | null;
  element_guids: string[] | null;
}

export interface Viewpoint {
  id: string;
  guid: string;
  topic_id: string;
  camera: { type?: string; position?: Vec3; target?: Vec3; fov?: number } | null;
  components: string[] | null;
  visibility: { default_visibility: boolean; exceptions: string[] } | null;
}

export interface Vec3 { x: number; y: number; z: number; }

export interface ModuleField {
  name: string; label: string; type: string; required?: boolean; options?: string[];
  module?: string;   // for type:"reference" — the target module key
  fieldset?: string; // F1 — labeled form section this field groups under
}
export interface ModuleDef {
  key: string; name: string; section: string; icon: string; pinnable: boolean;
  workspace?: "construction" | "developer";
  title_field?: string; ref_prefix?: string;
  fields: ModuleField[];
  workflow: { initial: string; states: string[]; transitions: WorkflowTransition[] };
  relations?: { label: string; module: string }[];
  list_columns?: string[];
  revisable?: boolean;
}
export interface WorkflowTransition { from: string; to: string; action: string; party: string[] }
export interface RecordBrief {
  module: string; module_name: string; id: string; ref: string; title: string | null; state: string;
}
export interface ModuleRecord {
  id: string; ref: string; title: string | null; workflow_state: string;
  party_owner: string | null; assignee?: string | null; created_by: string | null; created_at: string;
  anchor: Vec3 | null; element_guids: string[] | null;
  links: { module: string; id: string; ref: string }[];
  data: Record<string, unknown>;
  data_refs?: Record<string, RecordBrief>;   // resolved reference fields
  revision?: { number: number; revises: RecordBrief | null; superseded_by: RecordBrief | null };
  attachments?: RecordAttachmentMeta[];
  activity?: { ts: string; actor: string; party: string; action: string; detail: unknown }[];
  comments?: { author: string | null; text: string; created_at: string }[];
  available_actions?: { action: string; to: string; party: string[]; requires?: string[] }[];
}
export interface RecordAttachmentMeta {
  id: string; filename: string; size: number; content_type: string | null;
  uploaded_by: string | null; created_at: string | null;
}
export interface RelatedRecords {
  outgoing: (RecordBrief & { label: string })[];
  incoming: RecordBrief[];
}
export interface ModuleBoard {
  states: string[];
  columns: Record<string, { id: string; ref: string; title: string | null; assignee: string | null; party_owner: string | null }[]>;
  transitions: WorkflowTransition[];
}
export interface WorkItem {
  module: string; module_name: string; icon: string; id: string; ref: string;
  title: string | null; state: string; assignee: string | null; reason: string;
}
export interface NotifItem {
  module: string; module_name: string; icon: string; record_id: string; ref: string;
  title: string | null; action: string; actor: string | null; ts: string | null; reason: string;
}
export interface SavedViewDef { id: string; name: string; config: { q?: string; state?: string; sort?: { col: string; dir: 1 | -1 } }; }
export interface DueItem {
  module: string; module_name: string; icon: string; id: string; ref: string;
  title: string | null; state: string; assignee: string | null; due_date: string; days: number;
}
export interface DueFeed {
  overdue: DueItem[]; due_soon: DueItem[];
  counts: { overdue: number; due_soon: number }; as_of: string; horizon_days: number;
}

export interface StatementLine { label: string; amount: number; subtotal?: boolean; total?: boolean }
export interface FinancialStatements {
  scenario?: { id: string; name: string };
  assumptions: { income_tax_rate: number; depreciation_years: number; capital_gains_rate: number; niit_rate: number; recapture_rate: number; land: number; depreciable_basis: number };
  income_statement: {
    lines: StatementLine[];
    by_year: { year: number; noi: number; interest: number; depreciation: number; taxable_income: number; loss_carryforward_used: number; loss_carryforward_end: number; income_tax: number; net_income: number; after_tax_cash_flow: number }[];
    note: string;
  };
  balance_sheet: {
    balanced: boolean;
    by_year: { year: number; assets: { land: number; improvements_net: number; accumulated_depreciation: number; capitalized_financing: number; cash: number; total: number };
      liabilities: { loan: number; total: number }; equity: { paid_in_capital: number; retained_earnings: number; total: number }; balanced: boolean }[];
  };
  cash_flow_statement: {
    operating: { after_tax_operating_cash_flow: number; note: string };
    investing: { development_cost: number; net_sale_proceeds: number; sale_tax: number; total: number };
    financing: { loan_proceeds: number; equity_contributions: number; loan_repayment: number; distributions: number; total: number };
    net_change_in_cash: number;
    by_year: { year: number; operating: number; investing: number; loan_repayment: number; distributions: number; net_change_in_cash: number }[];
  };
  tax: {
    depreciation_by_year: number[];
    suspended_loss_at_sale: number;
    sale: { sale_price: number; selling_costs: number; net_sale: number; adjusted_basis: number; total_gain: number; suspended_loss_used: number; taxable_gain: number; depreciation_recaptured: number; recapture_tax: number; capital_gain: number; capital_gains_tax: number; total_sale_tax: number };
  };
  after_tax_returns: { equity_irr: number | null; equity_multiple: number | null; total_income_tax: number; total_sale_tax: number; suspended_loss_at_sale: number };
  two_sided_budget: { uses: StatementLine[]; sources: StatementLine[]; total_uses: number; total_sources: number; balanced: boolean };
}

export interface Appraisal {
  inputs: { replacement_cost_new: number; land_value: number; depreciation_pct: number;
    stabilized_noi: number; cap_rate: number; subject_sqft: number; subject_units: number | null; has_proforma: boolean };
  cost: { approach: string; replacement_cost_new: number; depreciation_pct: number; depreciation_amount: number;
    depreciated_improvements: number; land_value: number; value: number };
  income: { approach: string; stabilized_noi: number; cap_rate: number; value: number; method: string };
  sales_comparison: { approach: string; comp_count: number; basis: string; median_price_psf: number | null;
    median_price_per_unit: number | null; implied_cap_rate: number | null; value: number };
  reconciliation: { value: number; contributions: { approach: string; value: number; weight: number }[];
    approaches_used: string[]; range: { low: number; high: number; spread_pct: number } };
  comp_count: number;
}

export interface ProformaResult {
  sources_uses: { total_uses: number; loan_amount: number; loan_fees: number; interest_reserve: number; equity: number; ltc: number; effective_ltc: number; lp_contribution: number; gp_contribution: number };
  debt_sizing?: { binding_constraint: string; stabilized_value: number; actual_dscr: number | null; actual_debt_yield: number | null; actual_ltv: number | null; caps: Record<string, number> };
  operations: { stabilized_noi_annual: number; reversion: Record<string, number> };
  returns: { project_irr: number | null; equity_irr: number | null; equity_multiple: number; npv: number; yield_on_cost: number; dev_spread: number; total_contributions: number; total_distributions: number };
  waterfall: { lp_irr: number | null; gp_irr: number | null; lp_equity_multiple: number; gp_equity_multiple: number; lp_distributions: number; gp_distributions: number; style: string };
  cash_flow: { dates: string[]; equity: number[]; project: number[]; noi_monthly: number[] };
  guardrails?: { ok: boolean; flags: { level: "high" | "med" | "info"; metric: string; message: string }[] };
}

export interface ProformaForecast {
  as_of_month: number;
  lines: { name: string; category: string; budget: number; committed: number; actual_to_date: number; budget_to_date: number; forecast_at_completion: number; variance_to_budget: number; pct_drawn: number }[];
  totals: { budget: number; committed: number; actual_to_date: number; forecast_at_completion: number; variance_to_budget: number };
  underwritten_returns: { equity_irr: number | null; equity_multiple: number };
  forecast_returns: { equity_irr: number | null; equity_multiple: number };
  irr_delta: number | null;
}

/** One metric's sampled distribution from a Monte Carlo run. */
export interface MonteCarloMetric {
  mean: number; std: number; min: number; max: number; n: number;
  p5: number; p10: number; p25: number; p50: number; p75: number; p90: number; p95: number;
  target?: number; prob_at_least?: number;
  histogram: { counts: number[]; edges: number[] };
}
export interface MonteCarloResult {
  iterations: number; solved: number; failures: number; seed: number;
  variables: { path: string; dist: Record<string, unknown> }[];
  metrics: Record<string, MonteCarloMetric>;
}

export interface EnergyResult {
  areas_m2: Record<string, number>;
  ua_w_per_k: Record<string, number>;
  loads: { design_heating_kw: number; design_cooling_kw: number };
  annual_kwh: { heating: number; cooling: number; total: number };
  eui_kwh_m2_yr: number;
  element_counts: Record<string, number>;
}

export interface Dashboard {
  party: string;
  kpis: Record<string, number>;
  cost: { budget: number; committed: number; actual: number; projected_over_under: number } | null;
  action_items: { module: string; module_name: string; id: string; ref: string; title: string | null; state: string; actions: string[] }[];
  by_module: { key: string; name: string; section: string; count: number; by_state: Record<string, number> }[];
}

export interface ModulePin {
  module: string;
  module_name: string;
  icon: string;
  id: string;
  ref: string;
  title: string | null;
  status: string;
  anchor: Vec3;
  element_guids: string[] | null;
}

// dev (Vite @ :5173): hit the API directly (CORS allows :5173).
// prod build: relative "/api" so nginx reverse-proxies same-origin (no CORS needed).
// VITE_API_URL overrides either, baked at build time.
const DEFAULT_API = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "/api");

export class ApiClient {
  private token = localStorage.getItem("aec-token") || "";
  constructor(private baseUrl = DEFAULT_API) {}

  /** Bearer token for authenticated requests (persisted). Empty string clears it. */
  setToken(t: string) {
    this.token = t;
    if (t) localStorage.setItem("aec-token", t); else localStorage.removeItem("aec-token");
  }
  get authed() { return !!this.token; }
  /** Auth header to merge into any raw fetch (uploads, etc.). */
  authHeaders(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    if (IS_DEMO) return demoJson<T>(path, init);   // viewer-only build: serve the bundled snapshot
    const res = await fetch(this.baseUrl + path, {
      ...init,
      headers: { "Content-Type": "application/json", ...this.authHeaders(), ...(init?.headers || {}) },
    });
    if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}`);
    return res.json() as Promise<T>;
  }

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
  login(username: string, password: string) {
    return this.json<{ token: string; username: string; role: string }>(
      "/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
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
  /** Change your own password (requires the current one). */
  changePassword(current: string, next: string) {
    return this.json<{ ok: boolean }>(
      "/auth/password", { method: "POST", body: JSON.stringify({ current, new: next }) });
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
  url(path: string): string {
    return this.baseUrl + path;
  }

  async health(): Promise<boolean> {
    try {
      const res = await fetch(this.baseUrl + "/health");
      return res.ok;
    } catch {
      return false;
    }
  }

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
  /** Placeable types ("families") in the project's source IFC, for the place-family picker. */
  types(pid: string) {
    return this.json<{ types: { guid: string; name: string; ifc_class: string; has_geometry: boolean }[] }>(
      `/projects/${pid}/types`);
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
  clashFederated(pid: string, opts: { create_topics?: boolean; min_volume?: number; limit?: number } = {}) {
    const q = new URLSearchParams({ create_topics: String(opts.create_topics ?? true),
      ...(opts.min_volume != null ? { min_volume: String(opts.min_volume) } : {}),
      ...(opts.limit != null ? { limit: String(opts.limit) } : {}) }).toString();
    return this.json<{ disciplines: string[]; count: number; created_topics: number; truncated: boolean;
      clashes: { a_model: string; a_class: string; a_guid: string; b_model: string; b_class: string;
        b_guid: string; volume: number; method: "mesh" | "aabb"; point: Vec3 }[] }>(
      `/projects/${pid}/clash/federated?${q}`, { method: "POST" });
  }
  /** Discipline quantity roll-up — reinforcement tonnage, MEP linear runs, structural volume. */
  disciplineQuantities(pid: string) {
    return this.json<{ rebar: { count: number; weight_kg: number; tonnes: number; estimated: boolean };
      mep: { duct_m: number; pipe_m: number; cable_m: number; counts: Record<string, number> };
      structure: { element_volume_m3: number } }>(`/projects/${pid}/quantities/disciplines`);
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
    return this.json<{ name: string; elevation: number }[]>(`/projects/${pid}/drawings/storeys`);
  }

  // real-estate development finance (Proforma)
  solveProforma(assumptions: unknown) {
    return this.json<ProformaResult>(`/proforma/solve`, { method: "POST", body: JSON.stringify(assumptions) });
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
  forecast(assumptions: unknown, actuals: unknown[], as_of_month: number) {
    return this.json<ProformaForecast>(`/proforma/forecast`, {
      method: "POST", body: JSON.stringify({ assumptions, actuals, as_of_month }) });
  }
  portfolio() {
    return this.json<{ deal_count: number; totals: Record<string, number | null>; deals: { id: string; name: string; total_uses: number; equity: number; loan: number; equity_irr: number | null; equity_multiple: number | null }[] }>(`/proforma/portfolio`);
  }
  createScenario(name: string, project_id: string | null, assumptions: unknown) {
    return this.json<{ id: string }>(`/proforma/scenarios`, {
      method: "POST", body: JSON.stringify({ name, project_id, assumptions }) });
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
  updateModuleRecord(pid: string, key: string, rid: string, data: Record<string, unknown>) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}`, {
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
  addDrawingMarkup(pid: string, sheet_id: string, x: number, y: number, note: string) {
    return this.json<DrawingMarkupItem>(`/projects/${pid}/drawings/markup`, { method: "POST", body: JSON.stringify({ sheet_id, x, y, note }) });
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
  /** Schedule earned value: BAC / EV / PV / SPI + per-activity schedule variance. */
  scheduleEarnedValue(pid: string) {
    return this.json<{ bac: number; ev: number; pv: number; sv: number; spi: number | null;
      percent_complete: number; status: string; activity_count: number;
      activities: { ref: string; name: string; budget: number; percent: number; ev: number; pv: number; sv: number }[] }>(
      `/projects/${pid}/schedule/earned-value`);
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
  /** Import a Primavera P6 .xer so the 4D scrub reports real calendar dates. */
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
        pct_complete: number; lookahead_3wk: number; milestones_late: number; gmp: number; eac: number;
        variance_at_completion: number; committed_pct: number; equity_irr: number | null; equity_multiple: number | null }[];
      totals: { gmp: number; eac: number; variance_at_completion: number; committed: number; equity: number; blended_equity_irr: number | null };
      status_tally: { on_track: number; at_risk: number; behind: number }; project_count: number }>(
      `/portfolio/executive`);
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
  /** Generative design: sweep schemes, filter by targets, rank by yield-on-cost. */
  testFitOptimize(params: { plate_w: number; plate_d: number; floors: number; targets?: Record<string, number | string>; econ?: Record<string, number> }) {
    return this.json<{ considered: number; feasible: number; objective: string; best: OptScheme | null; ranked: OptScheme[] }>(
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
  /** Starter IFC family library (furniture / sanitary / appliances / plants) — generated
   *  parametrically, so it's placeable into any model incl. a from-scratch massing model. */
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
export interface FamilyItem {
  key: string; label: string; ifc_class: string; category: string; dims: [number, number, number];
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
    slenderness: number; members_mm: { slab: number; beam_depth: number; column: number; uses_beams: boolean }; flags: string[] };
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
