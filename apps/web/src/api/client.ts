/** Typed client for the backend API (guide §7). Geometry comes from .frag; all element
 *  metadata and work artifacts (pins/RFIs/viewpoints) come from here. */
import { withAuth } from "./auth";
import { withAuthoring } from "./authoring";
import { withConnections } from "./connections";
import { withDrawingSet } from "./drawingSet";
import { withDrawingSheets } from "./drawingSheets";
import { withElements } from "./elements";
import { withModels } from "./models";
import { withDocuments } from "./documents";
import { withAccounting } from "./accounting";
import { withMep } from "./mep";
import { withTopics } from "./topics";
import { withAi } from "./ai";
import { withEvm } from "./evm";
import { withCodeCheck } from "./codecheck"; import { withDealMemory } from "./dealMemory";
import { withPdfTools } from "./pdfTools";
import { withIds } from "./ids";
import { withSpecialty } from "./specialty";
import { withPrecon } from "./precon";
import { withEntitlements } from "./entitlements";
import { withRisk } from "./risk";
import { withMarkup } from "./markup";
import { withSync } from "./sync";
import { withCost } from "./cost";
import { withRoutines } from "./routines";
import { withContracts } from "./contracts";
import { withDesignOptions } from "./designOptions";
import { withFinance } from "./finance";
import { withLibrary } from "./library";
import { withAssetRights } from "./assetRights";
import { withDocQa } from "./docqa";
import { HttpCore, type LiveStream } from "./httpCore";
import { withModel } from "./model";
import { withEstimate } from "./estimate";
import { withProcurement } from "./procurement";
import { withProforma } from "./proforma";
import { withModules } from "./modules";
import { withSchedule } from "./schedule";

// DTO types live in ./types (extracted from this file). Re-export them so the many
// `import { … } from "../api/client"` sites across the app keep resolving unchanged.
export * from "./types";
// `liveStream` + its LiveStream handle moved into HttpCore so a MIXIN can reach them: a mixin is a
// BASE of ApiClient and cannot see ApiClient's `private` members, which blocked every SSE method
// from extraction. Re-exported because drawings.ts imports the type as
// `import("../api/client").LiveStream`.
export type { LiveStream } from "./httpCore";
// The module-graph DTOs travelled with the /modules methods in SCALE-SEAM ④; re-exported because
// portal/panels/moduleGraph.ts imports them as `from "../../api/client"`.
export type { ModuleGraph, ModuleGraphEdge, ModuleGraphNode } from "./modules";
export * from "./authoring";
export * from "./library";
import type {
  Appraisal, AuditEntry, Dashboard,
  DisciplineTree, DueFeed, EditMacro, EscalationScan, EscalationRun, EnergyResult, IntegrationGroup, Job, ModelCiReport, WorkQueue, ModulePin, ModuleRecord, RoomAllocation,
  LogisticsResource, NotifItem, OpendataPermit, ProjectMember, ProjectRole, PropLayer, PropMapRule, PreflightGate,
  ResponsibilityMatrix, SmartView,
    BidLevelingDetail,
    SpecManual, Topic, Vec3, WorkItem, VitalsPayload,
    DiligenceReadiness, MasterBuilderBrief } from "./types";


// Transport (baseUrl, token, json/_pdfPost/url/health) lives in HttpCore; ApiClient adds the typed
// domain methods below. Every `api.method()` call site is unchanged by the split.
export class ApiClient extends withAccounting(withDealMemory(withPdfTools(withCodeCheck(withSpecialty(withIds(withEvm(withRisk(withEntitlements(withPrecon(withAi(withTopics(withMep(withDocuments(withModels(withElements(withDrawingSheets(withDrawingSet(withMarkup(withSync(withConnections(withDocQa(withFinance(withContracts(withAuth(withProforma(withDesignOptions(withRoutines(withCost(withProcurement(withEstimate(withModules(withModel(withSchedule(withLibrary(withAssetRights(withAuthoring(HttpCore))))))))))))))))))))))))))))))))))))) {
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
      message: string; manage_url: string;
      cloud?: { online: boolean; url?: string; secret_configured?: boolean; note?: string } }>("/license");
  }
  /** CLOUD-BRIDGE: validate the recorded key against massing.cloud + apply the returned plan (admin). */
  licenseCloudCheck() {
    return this.json<{ checked_online: boolean; valid?: boolean; tier?: string; reason?: string | null;
      applied: boolean; tier_before: string; tier_after: string; error?: string }>(
      "/license/cloud-check", { method: "POST" });
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
  /** Open-data permit sources: the cities whose permit feeds this deployment can query. */
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
  /**
   * R22-PHOTO-CV — attach a field photo to an element and get the server's read on it back.
   *
   * The endpoint has existed since the verification router shipped and, until now, **had no caller
   * in this app at all** — it appeared only in the generated `schema.d.ts`. So the photo analysis
   * built on top of it (quality gate, change screening, object detection) was reachable by API but
   * not by anyone using the product. This is the front door.
   *
   * The response carries three separately-hedged answers; use `photoVerdict` in `ui/photoVerdict.ts`
   * to render them rather than reading the fields raw, because the qualifiers matter and are easy to
   * drop. `quality` is trustworthy in both directions, `change` is a screening signal only, and
   * `detected` is absent unless the deployment has a model configured.
   */
  async uploadVerificationPhoto(pid: string, guid: string, file: File | Blob, name = "photo.jpg") {
    const fd = new FormData(); fd.append("file", file, name);
    const r = await fetch(this.url(`/projects/${pid}/verification/${encodeURIComponent(guid)}/photo`),
      { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.json() as Promise<import("../ui/photoVerdict").PhotoUploadResult>;
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
  /** The pre-flight issuance gate — PASS/HOLD verdict + checklist, every check deep-linked. */
  preflight(pid: string) {
    return this.json<PreflightGate>(`/projects/${pid}/preflight`);
  }
  /** SITE-1: OSM site context (buildings/roads/land-use) as GeoJSON — fetched once server-side,
   *  cached for offline use afterwards. Omit lat/lon to use the model's IfcSite georeference. */
  siteContext(pid: string, opts: { lat?: number; lon?: number; radius?: number; refresh?: boolean } = {}) {
    const q = new URLSearchParams();
    if (opts.lat !== undefined) q.set("lat", String(opts.lat));
    if (opts.lon !== undefined) q.set("lon", String(opts.lon));
    if (opts.radius !== undefined) q.set("radius", String(opts.radius));
    if (opts.refresh) q.set("refresh", "true");
    const qs = q.toString();
    return this.json<{ lat: number; lon: number; radius: number; attribution: string;
      counts: Record<string, number>; geojson: { features: { properties: Record<string, unknown>;
      geometry: { type: string; coordinates: unknown } }[] } }>(
      `/projects/${pid}/site-context${qs ? "?" + qs : ""}`);
  }
  /** 3D-HERO: pin a captured viewer screenshot as the project's hero image (page 2 of the package PDF). */
  async uploadHero(pid: string, image: Blob) {
    const fd = new FormData(); fd.append("file", image, "hero.png");
    const r = await fetch(this.url(`/projects/${pid}/hero`), { method: "PUT", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.json() as Promise<{ stored: boolean; bytes: number }>;
  }
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
      // the score is a MEAN across domains, the status is WORST-OF — so a high score can carry a red
      // band, and `governing_domain` names the one that set it
      score_basis: string; status_basis: string;
      governing_domain: string | null; governing_detail: string | null;
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
  /** SCOPE-GAP — model-QTO coverage vs bid packages: covered disciplines, gaps (uncovered quantities), over-scoped packages. */
  scopeGap(pid: string) {
    type Disc = { discipline: string; element_count: number; classes: { ifc_class: string; count: number }[] };
    return this.json<{
      package_count: number; element_count: number; covered_pct: number; gap_element_count: number;
      covered: (Disc & { packages: string[] })[];
      gaps: (Disc & { sample_guids: string[] })[];
      packages_without_model_scope: string[]; note: string;
    }>(`/projects/${pid}/bidding/scope-gap`);
  }
  /** Invite companies to bid on a package (records the invitee list). */
  inviteBidders(pid: string, packageId: string, companies: string[]) {
    return this.json<{ bidders_invited: number; invited_companies: string[] }>(
      `/projects/${pid}/bidding/packages/${packageId}/invite`,
      { method: "POST", body: JSON.stringify({ companies }) });
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
  // --- admin: user management --------------------------------------------
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

  /** Every project visible to the caller — id, name, and `model_kind` (which tool a project opens
   *  with). Was documented as "absolute URL for a GET endpoint", a neighbour's comment left behind;
   *  the gate only caught it once `bundleUrl` moved out from under its 14-line lookahead. */
  projects() {
    return this.json<{ id: string; name: string; model_kind?: "frag" | "ifc" | null }[]>(`/projects`);
  }
  /** One project's metadata, incl. model_kind + has_source_ifc (used to gate IFC-only tools). */
  project(pid: string) {
    return this.json<{ id: string; name: string; model_kind?: string | null; has_source_ifc?: boolean }>(
      `/projects/${pid}`);
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
  /** Open a `.mass` container as a new project (fresh id). Legacy `.mmproj` (v1) still works. */
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

  // ── R24-JOB-TRAY — the background queue, finally reachable ──────────────────────────────────────
  //
  // `routers/jobs.py` has offered these four endpoints for a long time and nothing in `apps/web` had
  // ever called one. That is the *what-did-we-build-that-nothing-calls* pattern: every gate measured
  // the queue, none measured the path to it, so "heavy work has a foreground UI" read as a missing
  // engine when the engine was already there.
  //
  // Deliberately no `cancelJob`: the server has no cancel, and a tray with a dead button is worse
  // than one without it.

  /** Queue a background job. 400 on an unregistered kind (a typo fails at submit, not silently). */
  enqueueJob(pid: string, kind: string, params?: Record<string, unknown>) {
    return this.json<Job>(`/projects/${pid}/jobs`,
      { method: "POST", body: JSON.stringify({ kind, params: params ?? {} }) });
  }

  /** One job's state + result/error. 404 when it belongs to another project. */
  job(pid: string, jobId: string) {
    return this.json<Job>(`/projects/${pid}/jobs/${jobId}`);
  }

  /** The project's jobs, newest first. The server bounds `limit` at 200. */
  async jobs(pid: string, limit = 50): Promise<Job[]> {
    const r = await this.json<{ jobs: Job[] }>(`/projects/${pid}/jobs?limit=${limit}`);
    return r.jobs ?? [];
  }

  /** Absolute URL of a finished job's artifact — an href the browser fetches directly, so a big
   *  compiled set never round-trips through JS memory. 409 while queued/running. */
  jobArtifactUrl(pid: string, jobId: string): string {
    return this.url(`/projects/${pid}/jobs/${jobId}/artifact`);
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
  /** The 3-part MasterFormat project manual. See `SpecManual` in `types.ts` for the 50-per-section
   *  cap on `elements` — it matters to every caller. */
  specManual(pid: string) {
    return this.json<SpecManual>(`/projects/${pid}/spec/manual`);
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
  /** PROD-ACTUALS: installed-rate actual vs planned + crew utilization over field productivity actuals. */
  progressActuals(pid: string, actuals: Record<string, unknown>[], planned?: Record<string, unknown>) {
    type Group = {
      group: string; material_class: string; unit: string; entries: number;
      installed_qty: number; productive_hours: number; idle_hours: number;
      installed_rate: number | null; utilization: number | null; planned_rate: number | null;
      variance_pct: number | null; status: "ahead" | "on_track" | "behind" | null;
      planned_qty: number | null; pct_complete: number | null; remaining_qty: number | null;
      projected_hours_at_rate: number | null;
    };
    return this.json<{
      group_count: number; groups: Group[]; overall_utilization: number | null;
      total_productive_hours: number; total_idle_hours: number; planned_compared: number;
      ahead: number; on_track: number; behind: number; worst: string | null; note: string;
    }>(`/projects/${pid}/progress/actuals`, { method: "POST", body: JSON.stringify({ actuals, planned }) });
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
      load_cases: (string | null)[]; load_groups: (string | null)[]; load_actions?: number;
      supports?: number; has_model: boolean;
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

  /** FEM-EXPORT: download URL for the analytical frame as an OpenSees (.tcl) model. */
  openseesTclUrl(pid: string) {
    return this.url(`/projects/${pid}/structure/opensees.tcl`);
  }
  /** SOLVER-OUT — the analytical frame as a Code_Aster mesh (.mail, SI metres). */
  codeAsterMailUrl(pid: string) {
    return this.url(`/projects/${pid}/structure/code-aster.mail`);
  }

  /** SUBSET-EXPORT: download URL for an IFC of just the elements matching a QUERY-DSL selector. */
  subsetIfcUrl(pid: string, query: string) {
    return this.url(`/projects/${pid}/export/subset.ifc?query=${encodeURIComponent(query)}`);
  }

  // STRUCT-LATERAL: ASCE 7 wind + seismic lateral analysis (base shear → story forces)
  structureLateral(pid: string, opts?: {
    sds?: number; sd1?: number; r?: number; ie?: number; system?: string;
    windSpeedMph?: number; exposure?: string; deadPsf?: number; areaSf?: number;
  }) {
    const q = new URLSearchParams();
    const map: Record<string, number | string | undefined> = {
      sds: opts?.sds, sd1: opts?.sd1, r: opts?.r, ie: opts?.ie, system: opts?.system,
      wind_speed_mph: opts?.windSpeedMph, exposure: opts?.exposure,
      dead_psf: opts?.deadPsf, area_sf: opts?.areaSf,
    };
    for (const [k, v] of Object.entries(map)) if (v != null) q.set(k, String(v));
    const qs = q.toString();
    type Story = { level: number; height_ft: number; force_kip: number; shear_kip: number };
    return this.json<{
      story_count: number; area_sf: number | null; dead_psf: number; story_weight_kip: number;
      seismic: { method: string; period_s: number; k: number; Cs: number; seismic_weight_kip: number;
                 base_shear_kip: number; overturning_kipft: number; stories: (Story & { cvx: number; weight_kip: number })[] };
      wind: { method: string; qh_psf: number; base_shear_kip: number; overturning_kipft: number;
              stories: (Story & { trib_ft: number; pressure_psf: number })[] };
      governing: { system: string; base_shear_kip: number };
      disclaimer: string;
    }>(`/projects/${pid}/structure/lateral${qs ? `?${qs}` : ""}`);
  }

  // COLLAB-1: live co-editing snapshot (model signature + presence roster)
  collabSnapshot(pid: string) {
    return this.json<{
      model: { source: string | null; version: number; element_count: number; has_model: boolean };
      editors: { user: string; seconds_ago: number; viewpoint: unknown }[]; editor_count: number;
    }>(`/projects/${pid}/collab`);
  }
  /** Embodied-carbon compliance: element totals, coverage and intensity against the project's limits. */
  carbonComplianceReport(pid: string) {
    return this.json<{
      elements: { total_tco2e: number; coverage_pct: number; intensity_kgco2e_m2?: number;
                  carbon_matched: number; with_quantity: number;
                  hotspots: { guid: string; name: string | null; category: string; kgco2e: number }[] };
      buy_clean: { rows: { category: string; achieved_factor: number; limit: number; unit: string;
                           pass: boolean; headroom_pct: number; action: string | null }[];
                   passing: number; failing: number };
      leed_inventory: { total_tco2e: number; items: { category: string; kgco2e: number; share_pct: number }[] };
    }>(`/projects/${pid}/carbon/compliance`);
  }
  /** PERMIT-CHECK: submission-readiness — checklist + ranked deficiencies + verdict (409 without a model). */
  permitReadiness(pid: string) {
    return this.json<{
      verdict: string; readiness_pct: number; approvability_score: number;
      checklist: { requirement: string; satisfied: boolean; evidence: string }[];
      deficiencies: { item: string; severity: string; action: string }[];
    }>(`/projects/${pid}/permit/readiness`);
  }


  editGraph(pid: string, graph: unknown, opts?: { publish?: boolean; baseSource?: string }) {
    return this.json<{ node_count: number; order: string[]; outputs: Record<string, unknown>; publish?: string }>(
      `/projects/${pid}/edit/graph`,
      { method: "POST", body: JSON.stringify({ graph, publish: opts?.publish ?? false, base_source: opts?.baseSource ?? null }) });
  }

  // RECIPE-MACROS: saved, parameterized chained edit-recipes runnable as one GUID-stable version
  listMacros(pid: string) {
    return this.json<{ macros: EditMacro[]; seeded: boolean }>(`/projects/${pid}/macros`);
  }
  saveMacros(pid: string, macros: EditMacro[]) {
    return this.json<{ saved: number; macros: EditMacro[] }>(
      `/projects/${pid}/macros`, { method: "PUT", body: JSON.stringify({ macros }) });
  }
  expandMacro(pid: string, macroId: string, args: Record<string, unknown>) {
    return this.json<{ macro: string; name: string; steps: { recipe: string; params: Record<string, unknown> }[]; step_count: number }>(
      `/projects/${pid}/macros/${encodeURIComponent(macroId)}/expand`, { method: "POST", body: JSON.stringify({ args }) });
  }
  runMacro(pid: string, macroId: string, args: Record<string, unknown>, opts?: { publish?: boolean; baseSource?: string }) {
    return this.json<Record<string, unknown>>(
      `/projects/${pid}/macros/${encodeURIComponent(macroId)}/run`,
      { method: "POST", body: JSON.stringify({ args, publish: opts?.publish ?? false, base_source: opts?.baseSource ?? null }) });
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
  /** Discipline quantity roll-up — reinforcement tonnage, MEP linear runs, structural volume. */
  disciplineQuantities(pid: string) {
    return this.json<{ rebar: { count: number; weight_kg: number; tonnes: number; estimated: boolean };
      mep: { duct_m: number; pipe_m: number; cable_m: number; counts: Record<string, number> };
      structure: { element_volume_m3: number } }>(`/projects/${pid}/quantities/disciplines`);
  }
  /** SCHED-OPT — deterministic schedule optioneering: ranked crew/zoning scenarios over the Takt LOB model. */
  massingOptioneer(envelope: Record<string, unknown>, opts?: { levers?: Record<string, number[]>; objective?: string; limit?: number }) {
    type Opt = { id: string; levers: Record<string, number>; floors: number; height_m: number;
      gfa_m2: number; gfa_sf: number; net_sellable_m2: number; units: number; far_achieved: number;
      binding_constraint: string; on_frontier: boolean;
      proforma: { total_cost: number; noi: number; stabilized_value: number; profit: number;
        yield_on_cost: number; profit_margin: number } };
    return this.json<{
      scenarios: Opt[]; frontier: string[]; best: string | null; objective: string;
      count: number; shown: number; levers_swept: Record<string, number[]>; note: string;
    }>(`/massing/optioneer`, { method: "POST", body: JSON.stringify({ envelope, levers: opts?.levers ?? null, objective: opts?.objective ?? "yield_on_cost", limit: opts?.limit ?? 24 }) });
  }
  /** MASSING-OPT phase 2 — emit a ranked option as the executable authoring chain: the blank-model
   * bootstrap + GUID-stable edit-recipe steps for /edit/batch. Empty option = the best one. */
  massingOptionRecipes(envelope: Record<string, unknown>, option?: string,
                       opts?: { levers?: Record<string, number[]>; objective?: string; limit?: number }) {
    return this.json<{
      option: string; floors: number; floor_to_floor: number; plate_m2: number; plate_side_m: number;
      core_side_m: number;
      bootstrap: { name: string; storeys: number; storey_height: number; ground_size: number };
      steps: { recipe: string; params: Record<string, unknown> }[]; step_count: number; note: string;
    }>(`/massing/optioneer/recipes`, { method: "POST", body: JSON.stringify({
      envelope, option: option ?? "", levers: opts?.levers ?? null,
      objective: opts?.objective ?? "yield_on_cost", limit: opts?.limit ?? 24 }) });
  }
  /** MASTER-BUILDER brief as a shareable Markdown document (printable one-pager). */
  masterBuilderBriefMdUrl(pid: string) { return this.url(`/projects/${pid}/master-builder/brief.md`); }
  /** SELECTIONS — owner selections & allowances rollup (allowance vs actual → change-order candidates). */
  selectionsSummary(pid: string) {
    type Cat = { category: string; count: number; allowance: number; actual: number; delta: number };
    type Cand = { ref: string; item: string; category: string; allowance: number; actual: number;
      delta: number; state: string; change_subject: string };
    return this.json<{
      count: number; priced: number; approved: number; total_allowance: number; total_actual: number;
      net_delta: number; direction: "over" | "under" | "on-allowance";
      over_count: number; under_count: number; on_count: number;
      by_category: Cat[]; co_candidate_count: number; co_candidates: Cand[]; note: string;
    }>(`/projects/${pid}/selections/summary`);
  }
  /** Push over-allowance selections into change events (reason 'Allowance Reconciliation'); idempotent. */
  pushSelectionChangeEvents(pid: string) {
    return this.json<{ created: number; skipped: number; created_refs: string[]; note: string }>(
      `/projects/${pid}/selections/push-change-events`, { method: "POST", body: "{}" });
  }
  /** CLIENT-PORTAL — read-only share tokens for a public project-readiness digest. */
  shareTokens(pid: string) {
    type Tok = { token: string; label: string | null; revoked: boolean; created_at: string | null;
      created_by: string | null; view_count: number; last_viewed_at: string | null; share_path: string;
      show_payments: boolean };
    return this.json<{ tokens: Tok[] }>(`/projects/${pid}/share-tokens`);
  }
  /** `showPayments` is the explicit opt-in for THIS token's digest to carry the payment schedule. */
  createShareToken(pid: string, label?: string, showPayments?: boolean) {
    return this.json<{ token: string; label: string | null; share_path: string; revoked: boolean }>(
      `/projects/${pid}/share-tokens`,
      { method: "POST", body: JSON.stringify({ label: label ?? "", show_payments: !!showPayments }) });
  }
  revokeShareToken(pid: string, token: string) {
    return this.json<{ revoked: boolean }>(`/projects/${pid}/share-tokens/${encodeURIComponent(token)}`,
      { method: "DELETE" });
  }
  /** PORTAL-TXN phase 3 — post a client comment through a share token (public; lands on the token's
   * BCF feedback topic, so the team answers from the Issue Board). */
  sharedComment(token: string, body: { text: string; client_name?: string }) {
    return this.json<{ topic_id: string; comment_id: string; author: string | null; text: string;
      created_at: string | null }>(
      `/shared/${encodeURIComponent(token)}/comment`, { method: "POST", body: JSON.stringify(body) });
  }
  /** The public digest JSON URL for a share token. */
  sharedDigestUrl(token: string) { return this.url(`/shared/${encodeURIComponent(token)}/digest`); }
  /** The public read-only HTML page for a share token (opens with no login — the human share link). */
  sharedPageUrl(token: string) { return this.url(`/shared/${encodeURIComponent(token)}`); }
  /** VIEW-TEMPLATES — reusable layered view presets (class visibility + isolate + stacked colors). */
  viewTemplates(pid: string) {
    return this.json<{ templates: { id: string; name: string; hide_classes: string[];
      isolate: string | null; rules: { selector: string; color: string }[] }[] }>(
      `/projects/${pid}/view-templates`);
  }
  saveViewTemplates(pid: string, templates: { id?: string; name: string; hide_classes?: string[];
    isolate?: string | null; rules?: { selector: string; color: string }[] }[]) {
    return this.json<{ saved: number }>(`/projects/${pid}/view-templates`,
      { method: "PUT", body: JSON.stringify({ templates }) });
  }
  resolveViewTemplate(pid: string, tid: string) {
    return this.json<{ template: string; name: string | null; visible: string[]; visible_count: number;
      hidden_count: number; colors: Record<string, string>; colored_count: number; note: string }>(
      `/projects/${pid}/view-templates/${encodeURIComponent(tid)}/resolve`);
  }
  /** SPACE-UTIL benchmarking — capacity + m²/space across the portfolio's modelled projects. */
  spaceUtilBenchmarks(areaPerPerson = 10) {
    return this.json<{
      area_per_person: number; projects: number; skipped_over_cap: number; unreadable_models: number;
      rows: { project_id: string; project: string; space_count: number; total_area_m2: number;
        capacity: number; m2_per_space: number; top_type: string | null; top_type_area_m2: number | null }[];
      portfolio: { total_area_m2: number; total_capacity: number; median_m2_per_space: number | null };
      note: string;
    }>(`/benchmarks/space-utilization?area_per_person=${encodeURIComponent(areaPerPerson)}`);
  }
  /** MODEL-PUBLISH — the review gate over model versions: submit | approve | reject (409 on an
   * illegal transition). The file pointer is never touched — this is the QA record. */
  reviewModelVersion(pid: string, version: number, action: "submit" | "approve" | "reject", note?: string) {
    return this.json<{ version: number; review_status: string; reviewed_by: string | null;
      reviewed_at: string; review_note: string | null }>(
      `/projects/${pid}/versions/${version}/review`,
      { method: "POST", body: JSON.stringify({ action, note }) });
  }
  /** PORTAL-TXN — record a client decision through a share token (public; approve/acknowledge/decline). */
  sharedDecision(token: string, body: {
    item_type: string; item_ref: string; action: "approved" | "acknowledged" | "declined";
    client_name?: string; note?: string;
  }) {
    return this.json<{
      id: number; item_type: string; item_ref: string; action: string;
      client_name: string | null; note: string | null; created_at: string | null;
    }>(`/shared/${encodeURIComponent(token)}/decision`, { method: "POST", body: JSON.stringify(body) });
  }
  /** PORTAL-TXN — the project's client-decision feed (editor only), newest first. */
  clientDecisions(pid: string, limit = 500) {
    type D = { id: number; item_type: string; item_ref: string; action: string; client_name: string | null;
      note: string | null; created_at: string | null; token: string };
    return this.json<{ decisions: D[] }>(`/projects/${pid}/client-decisions?limit=${encodeURIComponent(limit)}`);
  }
  parcelAnalyze(body: {
    geojson?: unknown; wkt?: string; parcel_id?: string;
    zoning?: { max_far?: number; max_coverage?: number; max_height_m?: number };
    proposal?: { gfa_m2?: number; footprint_m2?: number; height_m?: number };
  }) {
    type Check = { metric: string; value: number; limit: number | null; ok: boolean | null; slack: number | null; max_gfa_m2?: number | null };
    return this.json<{
      parcel_id: string | null; vertices: number; coordinates_were_lonlat: boolean;
      area_m2: number; area_acres: number; perimeter_m: number;
      centroid: { x: number; y: number }; bbox: { minx: number; miny: number; maxx: number; maxy: number };
      compliance?: { checks: Check[]; ok: boolean | null; violations: string[] }; note: string;
    }>(`/parcels/analyze`, { method: "POST", body: JSON.stringify(body) });
  }
  progressRollup(pid: string, installedGuids: string[], elements?: Record<string, unknown>[]) {
    type Grp = { expected: number; installed: number; pct_complete: number; value_total: number; pct_complete_value: number | null };
    return this.json<{
      element_count: number; installed_count: number; pct_complete: number; value_total: number;
      value_installed: number; pct_complete_value: number | null;
      by_class: (Grp & { ifc_class: string })[]; by_discipline: (Grp & { discipline: string })[];
      by_level: (Grp & { level: string })[]; note: string;
    }>(`/projects/${pid}/progress/rollup`, { method: "POST", body: JSON.stringify({ installed_guids: installedGuids, elements }) });
  }
  /** SCAN-4D — the diff between two capture timestamps: newly installed per class/level, disappeared
   * elements (re-scan/rework flag), progress delta + daily rate. */
  progressCaptureDiff(pid: string, body: {
    installed_t1: string[]; installed_t2: string[]; t1?: string; t2?: string;
    elements?: Record<string, unknown>[];
  }) {
    return this.json<{
      t1: string | null; t2: string | null; days: number | null;
      installed_t1: number; installed_t2: number; newly_installed: number; disappeared: number;
      added_guids: string[]; disappeared_guids: string[];
      added_by_class: { ifc_class: string; count: number }[];
      added_by_level: { storey: string; count: number }[];
      pct_complete_t1: number; pct_complete_t2: number; pct_delta: number;
      elements_per_day: number | null; note: string;
    }>(`/projects/${pid}/progress/capture-diff`, { method: "POST", body: JSON.stringify(body) });
  }
  /** ABSORPTION-SELLOUT — phase revenue by absorption rate → the monthly sell-out curve + months-to-sellout
   * (the carry driver) + total revenue/carry. */
  feasibilitySellout(pid: string, body: {
    units: number; absorption_per_month: number; avg_price: number; monthly_carry?: number; start_month?: number;
  }) {
    type Month = { month: number; units_sold: number; revenue: number; cumulative_units: number; cumulative_revenue: number; remaining_units: number };
    return this.json<{
      units: number; absorption_per_month: number; avg_price: number; months_to_sellout: number | null;
      years_to_sellout: number; total_revenue: number; avg_monthly_revenue: number; total_carry: number;
      monthly_carry: number | null; schedule: Month[]; note: string;
    }>(`/projects/${pid}/feasibility/sellout`, { method: "POST", body: JSON.stringify(body) });
  }
  /** LOT-SUPPLY-INDEX — months of supply = VDL ÷ monthly absorption, indexed to equilibrium (100). */
  feasibilityLotSupply(pid: string, body: { vdl: number; monthly_absorption: number; equilibrium_months?: number }) {
    return this.json<{
      vdl: number; monthly_absorption: number; equilibrium_months: number; months_of_supply: number | null;
      lsi: number | null; band: "oversupplied" | "balanced" | "undersupplied" | "unknown"; note: string;
    }>(`/projects/${pid}/feasibility/lot-supply`, { method: "POST", body: JSON.stringify(body) });
  }
  /** PERMIT-TIMELINE — days-to-issue percentiles (p25/median/p75) by jurisdiction × type × valuation band +
   * a pro-forma estimate (median expected / p75 conservative), over cached permit records. */
  permitsTimeline(pid: string, body: {
    permits?: Record<string, unknown>[]; target?: { jurisdiction?: string; type?: string; valuation?: number };
  } = {}) {
    type Dist = { n: number; p25: number | null; median: number | null; p75: number | null; min: number | null; max: number | null; mean: number | null };
    type Group = Dist & { jurisdiction: string; type: string; band: string };
    return this.json<{
      permit_count: number; measured: number; overall: Dist; groups: Group[];
      seasonal: { month: number; issued: number; median_days: number | null }[];
      estimate?: {
        expected_days: number | null; conservative_days?: number | null; expected_months?: number | null;
        conservative_months?: number | null; sample_size: number; basis: string; note?: string;
      };
      note: string;
    }>(`/projects/${pid}/permits/timeline`, { method: "POST", body: JSON.stringify(body) });
  }
  scopeRegister(pid: string, body: {
    scope_items: Record<string, unknown>[]; qto_lines?: Record<string, unknown>[]; activities?: Record<string, unknown>[];
  }) {
    type Item = {
      id: string | null; name: string; cost_code: string | null; qty: number | null; value: number | null;
      responsible: string | null; package: string | null; start: string | null; finish: string | null;
      quantified: boolean; allocated: boolean; scheduled: boolean; gaps: string[]; status: "complete" | "gap";
    };
    return this.json<{
      item_count: number; complete: number; with_gaps: number; pct_quantified: number; pct_allocated: number;
      pct_scheduled: number; total_value: number; by_owner: { owner: string; value: number }[];
      gap_items: Item[]; items: Item[]; note: string;
    }>(`/projects/${pid}/scope/register`, { method: "POST", body: JSON.stringify(body) });
  }
  citedQuery(pid: string, query: string, property?: string, persona?: "exec" | "pm" | "field") {
    type CitationRef = {
      source_type: "ifc" | "doc" | "record" | "rule"; document_id: string | null; revision: string | null;
      guid: string | null; sheet: string | null; page: number | null; bbox: number[] | null;
      record_ref: string | null; rule_id: string | null; span: number[] | null;
    };
    type Claim = { text: string; citations: CitationRef[]; confidence: number };
    type Conflict = { target: string; values: string[]; claims: { text: string; value: unknown; citations: CitationRef[] }[] };
    return this.json<{
      answer: string; claims: Claim[]; conflicts: Conflict[]; coverage: number; fully_cited: boolean;
      uncited_claims: number[]; citation_count: number; source_types: Record<string, number>;
      note: string; query: string; matched: number; truncated: boolean;
      persona?: string; insight?: string; follow_ups?: string[]; persona_note?: string;
    }>(`/projects/${pid}/answer/cited-query`, { method: "POST", body: JSON.stringify({ query, property, persona }) });
  }
  masterBuilderBrief(pid: string, scope?: { workspace?: string; persona?: string }) {
    const q = new URLSearchParams();
    if (scope?.workspace) q.set("workspace", scope.workspace);
    if (scope?.persona) q.set("persona", scope.persona);
    const qs = q.toString();
    return this.json<MasterBuilderBrief>(
      `/projects/${pid}/master-builder/brief${qs ? `?${qs}` : ""}`);
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
  validate(pid: string) {
    return fetch(this.url(`/projects/${pid}/validate`), { method: "POST" }).then((r) => r.json() as Promise<ValidationResult>);
  }
  energy(pid: string) {
    return this.json<EnergyResult>(`/projects/${pid}/energy`);
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

  /** CRE-HOLDSELL — hold vs sell: incremental hold-year IRRs against the proceeds declined today. */
  holdSell(pid: string, inputs: unknown, hurdleRate = 0.12, maxYears = 10) {
    return this.json<{ computable: boolean; reason?: string;
      sell_now: { gross_sale: number; selling_costs: number; loan_payoff: number;
        net_proceeds: number; exit_cap: number };
      hurdle_rate: number; assumptions: Record<string, number>;
      years: { hold_years: number; exit_cap: number; noi_at_exit: number;
        net_proceeds_at_exit: number; incremental_irr: number | null; beats_hurdle: boolean }[];
      breakeven_hold_years: number | null; recommendation: "hold" | "sell";
      best_year: unknown; note: string }>(
      `/projects/${pid}/hold-sell`,
      { method: "POST", body: JSON.stringify({ inputs, hurdle_rate: hurdleRate,
                                               max_years: maxYears }) });
  }
  /** CRE-CLAUSE — the clause-position playbook (a clause with no red line is not a standard). */
  clausePlaybook(pid: string) {
    return this.json<{ playbook: Record<string, { clause: string; severity: string; accept: string;
      negotiate: string; refuse: string; fallback: string }[]>;
      starter: unknown[]; positions: string[] }>(`/projects/${pid}/contracts/playbook`);
  }
  saveClausePlaybook(pid: string, playbook: unknown) {
    return this.json<{ playbook: unknown }>(`/projects/${pid}/contracts/playbook`,
      { method: "PUT", body: JSON.stringify({ playbook }) });
  }
  /** CRE-CLAUSE — record a review against the PLAYBOOK (distinct from the AI `reviewContract`
   *  above: this one takes findings a human already made and scores them against the standard).
   *  Unreviewed playbook clauses come back as open risk. */
  reviewContractClauses(pid: string, contractType: string, findings: unknown[], document = "") {
    return this.json<{ verdict: string; document: string | null; reason?: string;
      available_types?: string[];
      clauses: { clause: string; severity: string; position: string; deviation: boolean;
        note: string | null; reference: string | null; red_line: string }[];
      deviations: unknown[]; negotiable: unknown[];
      not_reviewed: { clause: string; severity: string }[]; unknown_clauses: string[];
      counts: Record<string, number>; note: string }>(
      `/projects/${pid}/contracts/review`,
      { method: "POST", body: JSON.stringify({ contract_type: contractType, findings, document }) });
  }
  /** CRE-COVENANT — the loan covenant + reporting register (day-count basis, clock start). */
  loanCovenants(pid: string, loan: unknown, actuals?: Record<string, number>) {
    return this.json<{ loan: { name: string; lender: string }; at_risk: boolean;
      summary: Record<string, number>;
      reporting: { obligations: { name: string; computable: boolean; due_date?: string;
        day_basis?: string; clock_start?: string; anchor_source?: string; status?: string;
        risk?: string; days_remaining?: number; clock_start_matters?: boolean;
        alternate_reading?: { due_date: string; days_difference: number; warning: string } }[];
        upcoming: unknown[]; overdue: unknown[]; not_computable: { name: string; reason: string }[];
        counts: Record<string, number> };
      financial: { covenants: { name: string; tested: boolean; passing?: boolean; status?: string;
        headroom?: number; cure_ends?: string | null; reason?: string }[];
        untested: { name: string; reason: string }[]; counts: Record<string, number>;
        clean: boolean } }>(
      `/projects/${pid}/loan/covenants`,
      { method: "POST", body: JSON.stringify({ loan, actuals }) });
  }
  /** CRE-AUTHORITY — the deal-room authority table; required gaps BLOCK downstream analysis. */
  dealAuthority(pid: string) {
    return this.json<{ table: { fact_type: string; label: string; document: string; as_of: string;
      age_days: number | null; freshness_days: number; fresh: boolean; required: boolean }[];
      missing: { fact_type: string; label: string }[];
      stale: { fact_type: string; days_over: number }[];
      superseded_still_active: { fact_type: string; document: string; issue: string }[];
      gate: { passes: boolean; blocking: { fact_type: string; why: string }[]; advisory: unknown[] };
      counts: Record<string, number>; note: string }>(`/projects/${pid}/deal-room/authority`);
  }
  saveDealAuthority(pid: string, entries: unknown[]) {
    return this.json<{ entries: unknown[]; assessment: { gate: { passes: boolean } } }>(
      `/projects/${pid}/deal-room/authority`,
      { method: "PUT", body: JSON.stringify({ entries }) });
  }
  /** CRE-SUPPLY — competitive supply weighted by recorded evidence, not by status label. */
  competitiveSupply(pid: string, body: { projects: unknown[]; window_start?: string;
                                         window_end?: string; product_type?: string;
                                         monthly_absorption?: number }) {
    return this.json<Record<string, unknown>>(
      `/projects/${pid}/supply/competitive`, { method: "POST", body: JSON.stringify(body) });
  }
  /** CRE-DECISION-GATE — the pre-committee gate; a gate without evidence is unknown, and blocks. */
  decisionGate(pid: string, evidence: unknown, requiredExhibits?: string[], minCoverage?: number) {
    return this.json<{ verdict: "ready" | "blocked"; ready: boolean;
      gates: { gate: string; label: string; status: "pass" | "fail" | "unknown"; detail: string;
        action: string }[];
      blocking: { gate: string; status: string; detail: string }[];
      actions: { gate: string; action: string }[];
      counts: Record<string, number>; note: string }>(
      `/projects/${pid}/decision-gate`,
      { method: "POST", body: JSON.stringify({ evidence, required_exhibits: requiredExhibits,
                                               min_coverage: minCoverage ?? 0.9 }) });
  }
  /** CRE-COMP-TIER — comps ranked by source tier; bands report the weakest tier they rest on. */
  tieredComps(pid: string, field = "price_psf") {
    return this.json<{ comp_count: number; conflict_count: number;
      comps: { tier: string; label: string; rank: number; address: string; source: string;
        price_psf: number | null; cap_rate: number | null }[];
      conflicts: { address: string; kept_tier: string;
        outranked: { tier: string; source: string }[];
        value_deltas: { field: string; kept: number; outranked: number }[] }[];
      statistics: Record<string, { n: number; median: number | null; p25?: number; p75?: number;
        worst_tier: string | null; worst_tier_label?: string; best_tier?: string;
        tier_counts?: Record<string, number>; unattributed?: number; note?: string }>;
      note: string }>(`/projects/${pid}/comps/tiered?field=${encodeURIComponent(field)}`);
  }
  /** CRE-T12 — normalize a trailing-twelve to the house chart; the tie-out is a GATE, not a report. */
  normalizeT12(pid: string, t12: unknown, units?: number) {
    return this.json<{ line_count: number; source_totals: Record<string, number>;
      mapped_totals: Record<string, number>;
      tie_out: { reconciles: boolean; deltas: Record<string, number>; tolerance: number };
      stopped?: boolean; adjusted_noi: number | null;
      reconciling_items?: { issue: string; description?: string; amount?: number }[];
      unmapped_count: number; unmapped: { description: string; amount: number }[];
      one_time_items?: { description: string; amount: number; kind: string }[];
      capital_items?: { description: string; amount: number }[];
      by_category?: { category: string; label: string; amount: number; run_rate: number }[];
      run_rate_vs_trailing?: { category: string; trailing: number; run_rate: number; delta: number }[];
      add_back_questions?: { check: string; severity: string; finding: string; question: string }[];
      note: string }>(
      `/projects/${pid}/t12/normalize`, { method: "POST", body: JSON.stringify({ t12, units }) });
  }
  /** CRE-RRSCRUB — rent roll vs income; a check without its inputs reports not-run, never a pass. */
  rentRollScrub(pid: string, income?: unknown, units?: unknown[]) {
    return this.json<{ lease_count: number; excluded_not_active: number; clean: boolean;
      counts: { total: number; ran: number; not_applicable: number; passed: number; failed: number };
      checks: { check: string; applicable: boolean; passed?: boolean; severity?: string;
        finding: string; needs?: string }[];
      findings: { check: string; severity: string; finding: string }[];
      coverage_note: string }>(
      `/projects/${pid}/rent-roll/scrub`, { method: "POST", body: JSON.stringify({ income, units }) });
  }
  /** CRE-NER — net effective rent: the rent roll after concessions (straight-line + discounted). */
  netEffectiveRent(pid: string, opts: { discountRate?: number; lcPct?: number } = {}) {
    const q = new URLSearchParams();
    if (opts.discountRate !== undefined) q.set("discount_rate", String(opts.discountRate));
    if (opts.lcPct !== undefined) q.set("lc_pct", String(opts.lcPct));
    const qs = q.toString();
    return this.json<{ lease_count: number; skipped_count: number; excluded_not_active: number;
      face_gpr_annual: number; ner_gpr_annual_discounted: number;
      ner_gpr_annual_straight_line: number; concession_total_term: number;
      concession_load_pct: number; face_to_ner_delta_annual: number;
      face_to_ner_delta_pct: number; lc_included: boolean; discount_rate: number;
      skipped: { tenant: string; suite: string; reason: string }[];
      leases: { tenant: string; suite: string; face_rent_annual: number;
        ner_annual_discounted: number; ner_psf_discounted: number | null;
        concession_load_pct: number }[]; note: string }>(
      `/projects/${pid}/rent-roll/net-effective${qs ? `?${qs}` : ""}`);
  }
  /** ENERGY phase 1 — the thermal model extracted from the IFC (zones · surfaces · constructions). */
  energyModel(pid: string) {
    return this.json<{ zone_source: string;
      zones: { id: string; name: string; storey: string; area_m2: number; volume_m3: number }[];
      surfaces: { id: string; name: string; ifc_class: string; idf_type: string; zone_id: string;
        construction: string; orientation: string; area_m2: number; geometry: "exact" | "bbox";
        corners: number[][] }[];
      constructions: { name: string; u_value: number | null; source: string }[];
      counts: Record<string, number>; note: string }>(`/projects/${pid}/energy/model`);
  }
  /** ENERGY phase 1 — the gbXML / IDF envelope export URLs (downloads, not JSON). */
  energyExportUrl(pid: string, fmt: "gbxml" | "idf") {
    return `${this.baseUrl}/projects/${pid}/energy/export.${fmt}`;
  }
  sharedParams(pid: string) {
    return this.json<{ params: { name: string; pset: string; ptype: string; applies_to: string[];
      label: string; description: string }[]; max: number }>(`/projects/${pid}/shared-params`);
  }
  saveSharedParams(pid: string, params: unknown[]) {
    return this.json<{ params: unknown[] }>(`/projects/${pid}/shared-params`,
      { method: "PUT", body: JSON.stringify({ params }) });
  }

  rooms() {
    return this.json<RoomAllocation>(`/rooms`);
  }
  /**
   * R26-VITALS — the six numbers along the bottom strip.
   *
   * One request, deliberately: assembling LOD / area / $ft² / float / IRR / health from five engines
   * in the browser is how the same project came to show two different health scores in one session
   * (audit finding 03). The server owns the assembly.
   */
  vitals(pid: string) {
    return this.json<VitalsPayload>(`/projects/${pid}/vitals`);
  }
  modulePins(pid: string) {
    return this.json<ModulePin[]>(`/projects/${pid}/module-pins`);
  }
  dashboard(pid: string, party?: string) {
    const q = party ? `?party=${encodeURIComponent(party)}` : "";
    return this.json<Dashboard>(`/projects/${pid}/dashboard${q}`);
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
    return this.json<BidLevelingDetail>(`/projects/${pid}/bids/leveling/${packageId}`);
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
  projectCarbon(pid: string) {
    return this.json<{ total_kgco2e: number; total_tco2e: number; line_count: number; unmatched: number;
      by_material: Record<string, number>; by_cost_code: Record<string, number>; message?: string | null }>(
      `/projects/${pid}/carbon`);
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
    return this.json<DiligenceReadiness>(`/projects/${pid}/diligence/readiness`);
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
  /** BEP-GEN — the BIM Execution Plan generated from the project's live config (always current). */
  bep(pid: string) {
    return this.json<{
      project: { id: string; name: string; has_model: boolean } | null;
      sections: { id: string; title: string; configured: boolean; summary: string;
        items: { k: string; v: string }[] }[];
      completeness: { configured: number; total: number; pct: number }; note: string;
    }>(`/projects/${pid}/bep`);
  }
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

  async inspectVim(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/convert/vim/inspect`),
      { method: "POST", headers: this.authHeaders(), body: fd });
    if (!res.ok) throw new Error((await res.text()) || `inspect failed (${res.status})`);
    return res.json() as Promise<Record<string, unknown>>;
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
      suggested_level_contribution: number; suggestion_clears_horizon?: boolean; note: string }>(
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

  ifcClassify(pid: string) {
    return this.json<{ suggestions: { guid?: string; name: string; current_class: string;
      suggested_class: string; confidence: string; reason: string }[]; count: number;
      generic_elements: number; by_target_class: Record<string, number>; message?: string | null }>(
      `/projects/${pid}/ifc/classify`, { method: "POST", body: JSON.stringify({}) });
  }

  // --- CX-1 commissioning loop ----------------------------------------------
  /** Seed asset_register from the model's equipment classes (GUID-deduped) + phase-typed
   *  commissioning checklists with MEP FPT expected values. */
  cxSeed(pid: string, checklists = true) {
    return this.json<{ model_scored: boolean; created: number; skipped_existing: number;
      capped?: boolean; note?: string;
      checklists?: { created: number; capped?: boolean } }>(
      `/projects/${pid}/cx/seed${checklists ? "" : "?checklists=false"}`, { method: "POST" });
  }
  /** The system × phase completion matrix. */
  cxMatrix(pid: string) {
    return this.json<{ systems: { system: string; assets: number; tests: number; accepted: number;
      complete_pct: number; phases: Record<string, { total: number; tested: number; accepted: number;
        pass: number; fail: number } | null> }[]; phases: string[]; system_count: number }>(
      `/projects/${pid}/cx/matrix`);
  }
  /** The per-system turnover dossier. */
  cxDossier(pid: string, system: string) {
    return this.json<{ system: string; asset_count: number; test_count: number; accepted: number;
      complete_pct: number; open_punch_mentions: number;
      assets: { ref?: string; name?: string; tag?: string; location?: string; guid?: string }[];
      tests: Record<string, { ref?: string; asset?: string; state?: string; result?: string;
        date?: string; cx_agent?: string; deficiencies?: string }[]>;
      expected_values: Record<string, unknown>; note?: string }>(
      `/projects/${pid}/cx/dossier?system=${encodeURIComponent(system)}`);
  }
  /** REBAR-RULES — the bar bending schedule off the authored IfcReinforcingBar geometry. */
  rebarBbs(pid: string) {
    return this.json<{ rows: { mark: string; size: string | null; diameter_mm: number; shape: string;
      cut_length_m: number; count: number; unit_mass_kg_m: number; total_length_m: number;
      total_kg: number; guids: string[] }[]; marks: number; bars: number; skipped: number;
      total_length_m: number; total_kg: number; total_tonnes: number }>(
      `/projects/${pid}/rebar/bbs`);
  }
  rebarBbsCsvUrl(pid: string) { return this.url(`/projects/${pid}/rebar/bbs.csv`); }
  /** REBAR-RULES — verify a column's authored cage against the ACI envelope (bar count, tie spacing). */
  rebarCheckCage(pid: string, column: string) {
    return this.json<{ checked: boolean; longitudinal_bars?: number; ties?: number;
      violations: string[]; params: { bar_size: string; tie_size: string; tie_spacing: number;
        governing: string; rule: string; min_longitudinal_bars: number } }>(
      `/projects/${pid}/rebar/check?column=${encodeURIComponent(column)}`);
  }


  pricingReconcile(pid: string) {
    return this.json<{ lines: { material: string; quantity: number; unit: string; matched?: string | null;
      unit_price?: number; priced_amount?: number | null; estimated_unit_price?: number; variance?: number;
      variance_pct?: number | null; note?: string }[]; matched: number; priced_total: number;
      estimated_total: number; variance_total: number | null; pricing_source: string }>(
      `/projects/${pid}/pricing/reconcile`);
  }
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
  workQueue(pid: string) {
    return this.json<WorkQueue>(`/projects/${pid}/work-queue`);
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
  /** WORKFLOW-ENGINE — read-only escalation preview: overdue records with their computed level. */
  escalationsScan(pid: string) {
    return this.json<EscalationScan>(`/projects/${pid}/escalations`);
  }
  /** Apply the overdue-escalation pass (admin) — notifies the ball-in-court party + assignee. */
  escalationsRun(pid: string) {
    return this.json<EscalationRun>(`/projects/${pid}/escalations/run`, { method: "POST" });
  }
  /** Admin: send each member with open items a work-queue digest email. */
  sendDigest(pid: string) {
    return this.json<{ smtp_configured: boolean; results: Record<string, string[]>; skipped_no_email: string[] }>(
      `/projects/${pid}/notifications/digest`, { method: "POST" });
  }
  viewAlerts(pid: string) {
    return this.json<{ id: string; name: string; module: string; total: number; new: number;
      config: { q?: string; state?: string; sort?: unknown } }[]>(`/projects/${pid}/views/alerts`);
  }
  notificationStream(pid: string, onMessage: (d: { count: number; items: NotifItem[] }) => void,
                     onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    return this.liveStream(`/projects/${pid}/notifications/stream`,
                           onMessage as (d: unknown) => void, onStatus);
  }
  /** SSE stream of the pull-board change-signature; fires whenever any trade edits a sticky note so
   *  the board can live-refresh. Returns a resilient handle so callers can close it on teardown. */
  pullPlanStream(pid: string, onMessage: (d: { count: number; latest: string | null }) => void,
                 onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    return this.liveStream(`/projects/${pid}/pull-plan/stream`,
                           onMessage as (d: unknown) => void, onStatus);
  }
  searchAll(pid: string, q: string, limit = 50) {
    return this.json<WorkItem[]>(`/projects/${pid}/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  }
  async importClashXlsx(pid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/coordination/import-xlsx`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Clash import -> ${res.status}`);
    return res.json() as Promise<{ imported: number; detected_columns: string[]; sheet: string; rows_parsed: number }>;
  }
  /** CLASH-TRIAGE — import a native Navisworks clash-report XML -> coordination_issue records (GUID-anchored). */
  async importClashXml(pid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/coordination/import-xml`), {
      method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) throw new Error(`Clash XML import -> ${res.status}`);
    return res.json() as Promise<{ imported: number; sheet: string; rows_parsed: number; truncated: boolean }>;
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
  /** Model version history (one snapshot per publish), WITH its review state. The four review keys
   *  are not new server work — this type declared 4 of the 8 keys `versions.history` has returned
   *  since R18, so the record was discarded here (see `viewer/tools/modelReviewPanel.ts`). */
  modelVersions(pid: string) {
    return this.json<{ version: number; element_count: number; note: string | null; created_at: string | null;
      review_status: "draft" | "in_review" | "approved"; reviewed_by: string | null;
      reviewed_at: string | null; review_note: string | null }[]>(`/projects/${pid}/versions`);
  }
  /** Diff two model versions — added/removed/modified elements (with change labels) + unchanged count. */
  versionDiff(pid: string, a: number, b: number) {
    return this.json<{
      from: number; to: number; added: string[]; removed: string[];
      modified: { guid: string; name: string | null; ifc_class: string | null; changes: string[];
        changed_properties?: { property: string; status: "added" | "removed" | "changed" }[] }[];
      modified_available: boolean; property_detail_available?: boolean;
      added_count: number; removed_count: number; modified_count: number; unchanged_count: number;
    }>(`/projects/${pid}/versions/diff?a=${a}&b=${b}`);
  }
  /** REVISION-DELTA — conceptual cost impact of a revision (added priced, removed counted, modified flagged). */
  versionCostDelta(pid: string, a: number, b: number) {
    return this.json<{
      from: number; to: number;
      added: { count: number; priced_count: number; cost: number;
        lines: { ifc_class: string; count: number; unit: string; quantity: number; rate: number; amount: number }[];
        unpriced: { ifc_class: string; count: number }[] };
      removed: { count: number; by_class: { ifc_class: string; count: number; discipline: string }[]; note: string };
      requantified: { count: number; sample: { guid: string; name: string | null; ifc_class: string | null }[]; note: string };
      summary: { added_count: number; removed_count: number; requantified_count: number; added_cost: number };
      note: string;
    }>(`/projects/${pid}/versions/cost-delta?a=${a}&b=${b}`);
  }
  /** Reusable templates for a module (save a project's records → apply to another project). */
  templates(module: string) {
    return this.json<{ id: string; module: string; name: string; item_count: number }[]>(`/templates?module=${encodeURIComponent(module)}`);
  }
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
  /** MODEL-CI — run the model check pack → pass/warn/fail report + badge (persisted). With
   *  `createTopics`, each failing check becomes an open coordination Topic (BCF-model). */
  ciRun(pid: string, createTopics = false) {
    return this.json<ModelCiReport>(
      `/projects/${pid}/ci/run${createTopics ? "?create_topics=true" : ""}`, { method: "POST" });
  }
  /** MODEL-CI — the project's latest check-pack report (the badge source). */
  ciLatest(pid: string) {
    return this.json<ModelCiReport>(`/projects/${pid}/ci/latest`);
  }
  /** RULE-LIB — check the loaded model against the user-authored rule library → per-rule pass/fail
   *  + offending GUIDs + a by-severity rollup. */
  rulesRun(pid: string) {
    return this.json<{ model_scored: boolean; total_rules: number; failing_rules?: number;
      total_violations?: number; by_severity?: Record<string, number>; note?: string;
      rules: { id: string; name: string; severity: string; scope: string; require: string;
        scoped: number; passed: number; failed: number; fail_guids: string[]; status: string }[] }>(
      `/projects/${pid}/rules/run`);
  }
  /** RULE-LIB-2 — geometric rule checks over the model's baked AABBs (clearance / escape-distance /
   *  clear-width). Omit `checks` for the server's starter set. */
  rulesGeometryRun(pid: string, checks?: { kind: string; scope: string; [k: string]: unknown }[]) {
    return this.json<{ violation_total: number; by_severity: Record<string, number>;
      results: { id?: string; kind: string; name: string; severity: string; passed: boolean;
        checked: number; note?: string;
        violations: { guid: string; name?: string; detail: string; distance_m?: number;
          width_m?: number; blocking?: (string | null)[] }[] }[] }>(
      `/projects/${pid}/rules/geometry/run`,
      { method: "POST", body: JSON.stringify(checks?.length ? { checks } : {}) });
  }
  smartViews(pid: string) {
    return this.json<{ views: SmartView[]; count: number }>(`/projects/${pid}/smart-views`);
  }
  /** Replace the saved smart views (editor). Selectors are validated server-side → 422 on a bad one. */
  smartViewsSave(pid: string, views: SmartView[]) {
    return this.json<{ saved: number; views: SmartView[] }>(
      `/projects/${pid}/smart-views`, { method: "PUT", body: JSON.stringify({ views }) });
  }
  /** Resolve a saved view's selector to the matching GUIDs (to isolate / colour / hide in 3D). */
  smartViewRun(pid: string, vid: string) {
    return this.json<{ id: string; name: string; mode: string; color: string | null;
      selector: string; matched: number; truncated: boolean; guids: string[]; error?: string }>(
      `/projects/${pid}/smart-views/${encodeURIComponent(vid)}/run`);
  }
  costTraceability(pid: string) {
    return this.json<{ total_cost: number; traceable_cost: number; untraceable_cost: number;
      coverage_pct: number; elements_referenced: number; line_count: number;
      // `element_count` is the exact total; `guids` is a capped sample (200) — enough to select in
      // the viewer without turning a panel fetch into a megabyte on a large cost code.
      by_cost_code: { cost_code: string; total: number; traceable: number; coverage_pct: number;
        element_count: number; guids: string[] }[];
      note: string }>(`/projects/${pid}/cost/traceability`);
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
  /** The development budget: line items and contingency, as saved for this project. */
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
export interface MaterialEntry {
  name: string; category: string; color: [number, number, number]; transparency: number;
}
export interface MaterialPaletteResult {
  default: Record<string, MaterialEntry>;
  overrides: Record<string, MaterialEntry>;
  effective: Record<string, MaterialEntry>;
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
export interface EgressResult {
  compliant: boolean; flags: string[]; max_travel_m: number; limit_m: number;
  occupant_load_per_floor: number; min_exits_required: number;
  exit_separation_m: number; required_separation_m: number;
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
