/** Typed client for the backend API (guide §7). Geometry comes from .frag; all element
 *  metadata and work artifacts (pins/RFIs/viewpoints) come from here. */

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
  available_actions?: { action: string; to: string; party: string[] }[];
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
    return this.json<{ ai: boolean; email: boolean; sso: string[]; local_mode?: boolean }>("/capabilities");
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
  transitionRecord(pid: string, key: string, rid: string, action: string, note?: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/transition`, {
      method: "POST", body: JSON.stringify({ action, note }) });
  }
  linkRecord(pid: string, key: string, rid: string, module: string, id: string) {
    return this.json<ModuleRecord>(`/projects/${pid}/modules/${key}/${rid}/link`, {
      method: "POST", body: JSON.stringify({ module, id }) });
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
  moduleRecordsFiltered(pid: string, key: string, opts: { q?: string; state?: string } = {}) {
    const p = new URLSearchParams();
    if (opts.q) p.set("q", opts.q);
    if (opts.state) p.set("state", opts.state);
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
  attachmentUrl(attId: string) {
    return this.url(`/attachments/${attId}/download`);
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
  /** 4D construction sequence: scrubable frames (cumulative % built per day) over the takt plan.
   *  When a P6 .xer is imported, `source:"p6"` + start_date/finish_date and each frame gains `date`. */
  schedule4d(pid: string) {
    return this.json<{ floors: number; duration_days: number; element_count: number; source: "takt" | "p6";
      start_date?: string; finish_date?: string; p6_activities?: number; by_trade: Record<string, number>;
      frames: { day: number; new: number; completed_cumulative: number; pct: number; date?: string; new_guids: string[] }[] }>(
      `/projects/${pid}/schedule/4d`);
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
  editIfc(pid: string, recipe: string, params: Record<string, unknown>, publish = true) {
    return this.json<{ recipe: string; changed: number | string; published: unknown }>(
      `/projects/${pid}/edit`, { method: "POST", body: JSON.stringify({ recipe, params, publish }) });
  }
  /** Starter IFC family library (furniture / sanitary / appliances / plants) — generated
   *  parametrically, so it's placeable into any model incl. a from-scratch massing model. */
  familyCatalog() {
    return this.json<{ count: number; categories: Record<string, FamilyItem[]> }>("/families/catalog");
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
