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

/** The unified discipline tree (served on `GET /reference/disciplines`, `tree` key) — the single
 *  vocabulary the viewer, model browser, plan poché, and sheet generator all color/group by. */
export interface DisciplineNode {
  code: string; name: string; color: string;
  divisions: { code: string; title: string }[];
  uniformat: { code: string; title: string }[];
  sheet_series: string[];
  ifc_classes: string[];
}
export interface DisciplineTree {
  disciplines: DisciplineNode[];
  series: { code: string; name: string; color: string }[];
  /** IFC class → NCS discipline code (e.g. "IfcSprinkler" → "F"). */
  ifc_class_discipline: Record<string, string>;
  /** discipline code → hex color. */
  colors: Record<string, string>;
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

/** RECIPE-MACROS: a named, parameterized chain of authoring-recipe steps runnable as one version. */
export interface EditMacroParam { name: string; label?: string; default?: unknown; required?: boolean }
export interface EditMacro {
  id: string;
  name: string;
  description?: string;
  params: EditMacroParam[];
  steps: { recipe: string; params: Record<string, unknown> }[];
}

/** UX-ACT: a one-click resolve-action descriptor paired with a computed diagnostic (over-budget code, etc). */
export interface ResolveAction {
  kind: "open_module" | "navigate" | "open_record" | "select_elements";
  label: string;
  module?: string;   // open_module | open_record
  q?: string;        // open_module free-text filter
  target?: string;   // navigate destination key
  ref?: string;      // open_record record id
  guids?: string[];  // select_elements — capped; see `total` / `truncated`
  total?: number;    // select_elements — the TRUE count, which may exceed guids.length
  truncated?: boolean;
  selector?: string; // select_elements — the QUERY-DSL the guids came from, for re-evaluation
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
  kind?: string; data?: { pts?: { x: number; y: number }[]; value?: number; unit?: string; page?: number; text?: string; nx?: number; ny?: number;
    /** MARKUP-2a slip-sheet: the register revision the markup was made against, and (after a sheet
     *  revise) the superseded revision it was carried forward from — "verify against current". */
    rev?: string; carried_from?: string } | null;
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

/** A PE/RA licence held by the signed-in user. The seal is derived from one of these server-side —
 *  the UI offers a choice among the caller's own licences instead of a free-text name/number, because
 *  a seal attests that a specific licensed person was in responsible charge. */
export interface ProfessionalLicense {
  id: string; user: string; name_on_seal: string; license_no: string; state: string;
  discipline?: string | null; expiration?: string | null;
  verified_by?: string | null; verified_at?: string | null;
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
  /** R17 BCF-VIEWPOINT: active section planes captured at issue creation (restored on reopen). */
  clipping_planes?: { normal: Vec3; point: Vec3 }[] | null;
  snapshot?: string | null;
}

export interface Vec3 { x: number; y: number; z: number; }

/** MOD-FILTER — the operators a per-field register filter may use. Mirrors `modules_query.FILTER_OPS`;
 *  the server rejects anything else with a 400 rather than ignoring it. */
export type ModuleFilterOp = "eq" | "ne" | "gte" | "lte" | "contains" | "in" | "empty" | "nonempty";

export interface ModuleField {
  name: string; label: string; type: string; required?: boolean; options?: string[];
  module?: string;   // for type:"reference" — the target module key
  fieldset?: string; // F1 — labeled form section this field groups under
  /** MOD-SWEEP — the unit a numeric value is measured in ("ft", "yr", "days", "kWh").
   *
   *  The sweep found 170 numeric fields with no unit anywhere in the config, most of them encoding it
   *  in the field NAME instead — `elevation_ft`, `expected_life_years`, `ld_per_day`. A unit in a name
   *  is a unit only a human can read: it cannot be shown next to an input, appended in a table cell,
   *  converted, or checked. Declaring it makes the number self-describing, which is most of the
   *  difference between a form and a tool. */
  unit?: string;
  /** MOD-FIELDATTRS — numeric bounds. Rendered as input attributes AND enforced server-side; the
   *  HTML attribute is advice to one browser and nothing to a CSV import or an integration. */
  min?: number;
  max?: number;
  /** Hint text inside an empty input. Only on types that HAVE a text box to put it in. */
  placeholder?: string;
  /** Pre-filled on a NEW record only — re-filling on update would make "empty" unreachable. */
  default?: string | number | boolean;
  /** MOD-TABLE — the columns of a `table` field (line items). Absent on every other type. */
  columns?: ModuleColumn[];
  /** Numeric column summed into a footer total. Validated server-side to name a numeric column. */
  total_column?: string;
}

/** MOD-TABLE — one column of a `table` field. A row is not a record: no workflow, no ref, no
 *  attachments, no id, so a column carries only what is needed to render and read a cell.
 *  Allowed types mirror `module_schema.TABLE_COLUMN_TYPES`. */
export interface ModuleColumn {
  name: string; label?: string; required?: boolean;
  type: "text" | "number" | "currency" | "percent" | "date" | "select" | "checkbox" | "reference";
  options?: string[]; unit?: string; width?: string;
  /** MOD-TABLEREF — the register a `reference` column points at. Required for that type, and
   *  `validate_module` rejects it on any other, so the two can never disagree about what a column is. */
  module?: string;
}

export interface ModuleDef {
  key: string; name: string; section: string; icon: string; pinnable: boolean;
  // a module can belong to one or more workspaces; multi-membership is a "|"-separated list
  // (e.g. "construction|design") so shared A/E↔GC registers (RFIs, submittals) show in both.
  workspace?: string;
  title_field?: string; ref_prefix?: string;
  fields: ModuleField[];
  workflow: { initial: string; states: string[]; transitions: WorkflowTransition[] };
  // MOD-COMPLETE ③: `relations` removed 2026-08-01. The API served it as `[]` to every client since
  // Modules Phase 1 — no `module.json` declared it, no schema defined it, nothing populated it, and
  // nothing here read it. Cross-module links are `"type": "reference"` FIELDS, used by 85 modules.
  list_columns?: string[];
  /** MOD-COMPLETE ② — workflow states that REQUIRE at least one attachment before a record may enter
   *  them. This is **enforced server-side** (`modules.py`, the evidence gate: entering one of these
   *  states with zero attachments is a 400). It is declared here so the UI can say so in advance —
   *  #151 made the API serve it, but nothing read it, so a user still learned the rule by having their
   *  transition rejected. Serving a key is step one of two. */
  close_requires_attachment?: string[];
  /** The module's own explanatory text, authored in `module.json`. Surfaced as the register's
   *  description rather than left to each panel to invent one. */
  help?: string;
  revisable?: boolean;
  /** R30-TOOLS — first-class destinations that operate on this register. The inverse of `Dest.needs`:
   *  `needs` lets a panel say which register it requires, `tools` lets a register say which panels
   *  can act on it. Both directions are needed, and only one existed. `moduleTools.test.ts` asserts
   *  every `dest` here resolves against `ALL_DESTS`. */
  tools?: { dest: string; label: string; scope?: "register" | "record" }[];
  /** R26 — the ONE canonical room this module lives in ("model" | "cost" | "schedule" | "deal").
   *  Served by the API from a single section→room table, so no shell has to invent its own
   *  taxonomy — inventing one per workspace is how four different rails came to exist. */
  room?: string | null;
}
/** R26 — the room spine. Constant for every role; a workspace weights it, never replaces it. */
/** R26-INSPECTOR — one state of the six-state element lifecycle strip.
 *  `unknown` means the platform could not consult that state. It is NOT `none`: an element nobody
 *  priced and an element priced at zero are different facts, and so are "no" and "we did not ask". */
export type StripStatus = "done" | "none" | "unknown";
export interface StripState {
  key: string; label: string; status: StripStatus;
  means: string; detail: string; advance: string | null;
}
export interface LifecycleStrip {
  guid: string | null;
  states: StripState[];
  /** The furthest CONTIGUOUS state — a later state cannot flatter an incomplete earlier one. */
  reached: string | null;
  done_count: number; unknown_count: number;
  next: { key: string; advance: string | null } | null;
  /** Out-of-order combinations ("verified but never installed") — real data defects, reported. */
  inconsistencies: string[];
  note?: string;
  evidence?: Record<string, unknown>;
}

/** R31-DESIGN-GROUPS: `groups` is the room's second navigation level, keyed on the same `section`
 *  that decides the room — one table, refined, never a parallel one. Largest group first. */
export interface RoomGroup { section: string; count: number; modules: string[] }
export interface RoomDef { id: string; label: string; job: string; count: number; modules: string[]; groups?: RoomGroup[] }
export interface RoomAllocation {
  rooms: RoomDef[]; placed: number;
  /** Must always be empty — a module with no room is one nobody can reach. */
  unplaced: { key: string; section: string }[]; unplaced_count: number;
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
  //: R41-SCHEMA-STALE. Sent on EVERY read, not only when something is wrong — a key that appears
  //: only on failure is indistinguishable from a key the server forgot to send. `stale` means this
  //: record's payload no longer means what the current schema says: `orphaned` values belong to
  //: fields that were renamed or removed (unreachable from the form), `mistyped` ones no longer
  //: match their declared type. `changed` alone is NOT stale — an added field leaves old records
  //: correct, and flagging those would train everyone to ignore the badge.
  schema?: {
    version: string; stored: string | null; changed: boolean; epoch_behind: boolean;
    orphaned: string[]; mistyped: string[]; stale: boolean;
  };
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
/** R26-WORK-QUEUE — a work item with its due date, urgency bucket and the actions this caller can run. */
export interface QueueItem extends WorkItem {
  due: string | null;
  bucket: string;
  actions: string[];
  /** Actions the module gates behind required fields — they need the record, not one click. */
  blocked_actions: string[];
}
export interface WorkQueue {
  buckets: { key: string; label: string; means: string; count: number; items: QueueItem[] }[];
  total: number;
  /** Items you can move. `no_action` is the rest — in your court but waiting on someone else. */
  actionable: number;
  no_action: number;
  note?: string;
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
export interface EscalationItem {
  module: string; module_name: string | null; icon: string | null; id: string; ref: string | null;
  title: string | null; state: string | null; assignee: string | null; due_date: string | null;
  days_overdue: number; level: number; applied_level: number; court: string | null; needs_escalation: boolean;
}
export interface EscalationScan {
  as_of: string | null; count: number; pending: number;
  by_level: Record<string, number>; items: EscalationItem[];
}
export interface SmartView {
  id?: string;
  name: string;
  selector: string;
  mode: "isolate" | "color" | "hide";
  color?: string | null;
}
export interface ModelCiReport {
  overall: string; badge: string; ran_at?: string; note?: string;
  total_checks?: number; passed?: number; failed?: number; warned?: number; created_topics?: number;
  checks: { key: string; label: string; status: string; summary: string; metrics?: Record<string, unknown> }[];
}
export interface EscalationRun {
  as_of: string | null; escalated: number; by_level: Record<string, number>;
  items: { module: string; id: string; ref: string | null; title: string | null; level: number; days_overdue: number; court: string | null }[];
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

/** One check row in the pre-flight issuance gate. */
export interface PreflightCheck {
  key: string;
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
  score?: number;
  count?: number;
  guids?: string[];
  link?: string | null;
}

/** The pre-flight issuance gate — PASS/HOLD verdict + deep-linked checklist. */
export interface PreflightGate {
  ready: boolean;
  verdict: string;
  overall_score: number | null;
  band: string | null;
  blocking: number;
  warnings: number;
  checks: PreflightCheck[];
  disclaimer: string;
}

/** The compact gate stamp an issuance record carries. */
export interface PreflightSummary {
  ready: boolean;
  verdict: string;
  overall_score: number | null;
  blocking: number;
  warnings: number;
  blocking_checks: string[];
}

/**
 * R26-VITALS — the six numbers the bottom strip renders.
 *
 * `value: null` is a first-class result meaning "this project has not got there yet", and `note`
 * says what it is waiting on. It must never be rendered as 0 — a zero float reads as "no slack" and
 * a zero IRR as "worthless", which are claims about a project, not about missing data.
 */
export interface Vital {
  value: number | string | null;
  unit: string;
  note?: string | null;
  band?: string | null;
}
export interface VitalsPayload {
  order: string[];
  [key: string]: Vital | string[] | undefined;
}

/**
 * R24-JOB-TRAY — one background job, exactly as `jobs.job_dict` returns it.
 *
 * The queue has existed server-side for a long while (`routers/jobs.py`: enqueue, poll, list,
 * artifact; seven registered kinds; crash recovery resets orphaned `running` rows). Until v0.3.779
 * **no client had ever called it** — `grep -rn "/jobs" apps/web/src` returned nothing. So the
 * findings that heavy work has "background work with foreground UI" and that COBie exports and
 * compiled sets block the user were never a missing engine; they were a missing path to one.
 *
 * `state` is the whole contract: `queued → running → done | error`. There is no cancel, because the
 * server has none — a tray that offers one would be lying about what it can do.
 */
export type JobState = "queued" | "running" | "done" | "error";

export interface Job {
  id: string;
  kind: string;
  project_id: string | null;
  state: JobState;
  params: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string | null;
  actor: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

/**
 * R22-OPTION-OBJECT — a design option as ONE comparable record across the five axes.
 *
 * `axes` values are `null` when the axis is ABSENT, never 0. That distinction is the whole point of
 * the record: `option_score` once coerced a missing `cost_per_sf` to 0.0 and, on a lower-is-better
 * axis, scored it 100 — the best possible mark, awarded for having no data. Render an absent axis as
 * absent; do not fall back to `?? 0`, and do not sort on an axis without checking `axis_status`.
 *
 * There is no rank, score or recommendation here, deliberately — `option_score` owns ranking and
 * does it honestly. `comparable_count` below the option count means some massing is being evaluated
 * without its returns, and `incomparable` says which.
 */
export type OptionAxis = "geometry" | "unit_mix" | "cost" | "carbon" | "returns";
export type OptionAxisStatus = "present" | "absent";

export interface OptionRecord {
  id: string;
  name: string;
  state: string | null;
  axes: Record<OptionAxis, number | null>;
  axis_status: Record<OptionAxis, OptionAxisStatus>;
  /** How each engine got its number: declared / benchmark / derived / unlinked / unavailable. */
  carbon_basis: string | null;
  economics_basis: string | null;
  missing_axes: OptionAxis[];
  comparable: boolean;
  note: string;
}

export interface OptionRecordSet {
  options: OptionRecord[];
  option_count: number;
  /** Options comparable on ALL five axes. Below `option_count` is the number worth surfacing. */
  comparable_count: number;
  incomparable: { id: string; name: string; missing_axes: OptionAxis[] }[];
  axes: OptionAxis[];
  project_id?: string;
  note: string;
}
