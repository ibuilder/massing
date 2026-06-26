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
