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

/** A user's membership of one project: capability role + optional workflow party + company. */
export interface ProjectMember {
  user: string;
  role: ProjectRole;
  party_role: string | null;
  company: string | null;
}

/** A global account (identity). Per-project authorization lives in project members. */
export interface AccountUser {
  username: string;
  role: "admin" | "user";
  active: boolean;
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
}
export interface ModuleDef {
  key: string; name: string; section: string; icon: string; pinnable: boolean;
  fields: ModuleField[];
  workflow: { initial: string; states: string[]; transitions: WorkflowTransition[] };
  relations?: { label: string; module: string }[];
  list_columns?: string[];
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
  sources_uses: { total_uses: number; loan_amount: number; loan_fees: number; interest_reserve: number; equity: number; ltc: number; lp_contribution: number; gp_contribution: number };
  operations: { stabilized_noi_annual: number; reversion: Record<string, number> };
  returns: { project_irr: number | null; equity_irr: number | null; equity_multiple: number; npv: number; yield_on_cost: number; dev_spread: number; total_contributions: number; total_distributions: number };
  waterfall: { lp_irr: number | null; gp_irr: number | null; lp_equity_multiple: number; gp_equity_multiple: number; lp_distributions: number; gp_distributions: number; style: string };
  cash_flow: { dates: string[]; equity: number[]; project: number[]; noi_monthly: number[] };
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
  login(username: string, password: string) {
    return this.json<{ token: string; username: string; role: string }>(
      "/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
  }
  register(username: string, password: string) {
    return this.json<{ username: string; role: string }>(
      "/auth/register", { method: "POST", body: JSON.stringify({ username, password }) });
  }
  me() {
    return this.json<{ username: string; role: string | null; authenticated: boolean }>("/auth/me");
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
  createUser(username: string, password: string, role: "admin" | "user" = "user") {
    return this.json<AccountUser>(
      "/auth/users", { method: "POST", body: JSON.stringify({ username, password, role }) });
  }
  updateUser(username: string, patch: { role?: "admin" | "user"; active?: boolean }) {
    return this.json<AccountUser>(
      `/auth/users/${encodeURIComponent(username)}`, { method: "PATCH", body: JSON.stringify(patch) });
  }
  resetUserPassword(username: string, password: string) {
    return this.json<{ ok: boolean }>(
      `/auth/users/${encodeURIComponent(username)}/password`,
      { method: "POST", body: JSON.stringify({ password }) });
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
    return this.json<{ id: string; name: string }[]>(`/projects`);
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
  editIfc(pid: string, recipe: string, params: Record<string, unknown>, publish = true) {
    return this.json<{ recipe: string; changed: number | string; published: unknown }>(
      `/projects/${pid}/edit`, { method: "POST", body: JSON.stringify({ recipe, params, publish }) });
  }
  publish(pid: string) {
    return this.json<{ state: string }>(
      `/projects/${pid}/publish`, { method: "POST", body: JSON.stringify({ reconvert: true }) });
  }
  publishStatus(pid: string) {
    return this.json<{ state: "idle" | "running" | "done" | "error"; detail?: Record<string, unknown> }>(
      `/projects/${pid}/publish/status`);
  }
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
