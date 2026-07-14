/** Shared API DTO types for the backend client. Extracted from client.ts so the type surface
 *  (imported across the app) lives apart from the ~2.6k-line ApiClient implementation.
 *  client.ts re-exports everything here (`export * from "./types"`) for import-path compatibility. */

export interface ElementProps {
  guid: string;
  ifc_class: string;
  name: string | null;
  type_name: string | null;
  storey: string | null;
  /** Server-computed A/S/M/P/E/FP discipline bucket, when the index provides it. */
  discipline?: string | null;
  psets: Record<string, Record<string, unknown>>;
  qtos: Record<string, Record<string, unknown>>;
}

/** A property-normalization rule (W9-1): remap a source pset/prop onto a target structure. */
export interface PropMapRule {
  from_pset: string; from_prop: string;
  to_pset?: string; to_prop: string;
  cast?: "string" | "number" | "bool";
  keep_source?: boolean;
}

/** A temporary site-logistics resource on the 4D timeline (W9-5). */
export interface LogisticsResource {
  id: string; kind: string; label?: string;
  position?: [number, number, number]; polygon?: [number, number][]; radius?: number;
  start?: string; end?: string;
}

/** One IFC5-style non-destructive property-override layer (W9-3). */
export interface PropLayer {
  name: string;
  enabled: boolean;
  overrides: { guid: string; pset: string; prop: string; value: unknown }[];
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
  kind?: string; data?: { pts?: { x: number; y: number }[]; value?: number; unit?: string; page?: number; text?: string; nx?: number; ny?: number } | null;
}

/** One markup in a bulk save from the 2D editor (pin or a structured takeoff markup). `nx`/`ny` are the
 *  page-normalized (0..1) anchor — the shared coordinate space that lets the SVG sheet viewer place a
 *  PDF-editor markup in its own content box. */
export interface SheetMarkupIn {
  x: number; y: number; note?: string | null; kind?: string;
  data?: { pts: { x: number; y: number }[]; value: number; unit: string; page: number; text?: string; nx?: number; ny?: number };
}

/** An A/E/C stamp template from the server library (review / inspection / status / seal). */
export interface StampTemplate {
  id: string; name: string; category: "review" | "inspection" | "status" | "seal";
  dispositions?: string[]; disclaimer?: boolean; color: string; size: [number, number];
  discipline?: string;
  fields: { key: string; label: string; type: "text" | "multiline" | "date" | "user" }[];
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

/** A folder node in the standard document taxonomy (with per-project counts + gaps). */
export interface DocFolderNode {
  path: string; label: string; depth: number; owner_role: string | null;
  discipline: string | null; cde_default: string; required: boolean;
  count: number; direct_count: number; gap: boolean;
}
/** One filed document (a revision of a document in a folder). */
export interface DocFile {
  id: string; folder: string; name: string; orig_name: string; title: string;
  discipline: string; doc_type: string; revision: string; cde_state: string; status: string;
  owner_role: string | null; size: number; uploaded_by: string; uploaded_at: string;
  superseded?: boolean; superseded_by?: string | null;
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
  // a module can belong to one or more workspaces; multi-membership is a "|"-separated list
  // (e.g. "construction|design") so shared A/E↔GC registers (RFIs, submittals) show in both.
  workspace?: string;
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
  modified_at?: string | null;   // for the optimistic lock (send back as expected_modified_at)
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

export interface RespRow {
  id: string; ref: string | null; activity: string;
  phase: string | null; category: string | null; milestone: string | null; reference: string | null;
  assignments: Record<string, string>;
}
export interface ResponsibilityMatrix {
  mode: "RACI" | "DACI"; letters: string[]; doer: string;
  roles: string[]; rows: RespRow[]; count: number;
  validation: {
    missing_accountable: { ref: string | null; activity: string; count: number }[];
    no_responsible: { ref: string | null; activity: string }[];
    unknown_role: { ref: string | null; role: string }[];
    accountable_load: Record<string, number>; clean: boolean;
  };
  summary: { activities: number; clean: boolean; issues: number };
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
