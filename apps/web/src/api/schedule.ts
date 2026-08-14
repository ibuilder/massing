/** Schedule: CPM, 4D, baselines, resource levelling, earned value, takt and P6/MSP interchange.
 *
 *  SCALE-SEAM ② — the second extraction out of `client.ts`. Chosen by measuring, not by reading the
 *  section comments: those label the START of a run and the file then continues with methods from
 *  other domains, so they no longer delimit anything. Classifying all 669 methods by the route each
 *  one calls gives 219 groups, and `/schedule` is the largest clean one at 26 methods / 194 lines.
 *
 *  Worth recording for whoever does ③: there is **no big cut left**. The largest group is 4.5% of the
 *  file and the top six together are 20% — `client.ts` is a long tail, so this is ~25 releases of one
 *  group each, not a big-bang split. The entry claiming SCALE-SEAM complete was measuring ① (a 112-line
 *  reduction, 2%) and closed the item with the god-file intact.
 *
 *  A **mixin**, so `api.scheduleCpm(...)` resolves exactly as before and no call site changes.
 *  `api/surface.test.ts` is what makes that checkable: it captures the runtime method surface and
 *  fails if an extraction drops one — which a typecheck cannot, since deleting a method and deleting
 *  its last caller both compile clean.
 *
 *  Reaches nothing but HttpCore's `json` / `url` / `authHeaders`, same as `withAuthoring`. The takt
 *  result types came along because nothing outside `client.ts` imported them.
 */
import { IS_DEMO, demoTextOr } from "../demo/demoApi";
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withSchedule<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Schedule extends Base {
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
  scheduleRisk(pid: string, iterations = 800) {
    return this.json<{
      iterations: number; activity_count?: number; message?: string; has_cycle?: boolean;
      deterministic_days?: number; p10_days?: number; p50_days?: number; p80_days?: number; p90_days?: number;
      p50_vs_deterministic_days?: number; buffer_p80_days?: number; on_time_probability_pct?: number;
      ppc_calibration_pct?: number | null; start_date?: string;
      deterministic_finish?: string; p50_finish?: string; p80_finish?: string;
      delay_drivers?: { ref: string | null; name: string | null; criticality_pct: number; mean_slip_days: number }[];
    }>(`/projects/${pid}/schedule/risk?iterations=${iterations}`);
  }
  /** CARBON-EC3: per-element A1–A3 + Buy Clean limit check + LEED-style inventory (404 until a model loads). */
  scheduleOptioneer(pid: string, body: {
    floors?: number; trades?: { name: string; takt_days: number; reorderable?: boolean }[];
    crew_day_rate?: number; max_crew_trades?: number; zone_options?: number[];
    overlap_options?: number[]; permute_sequence?: boolean; weight_time?: number; weight_cost?: number;
    /** Trade names on the critical path, or "auto" to derive them from the project's own CPM —
     *  crew doubling is then only offered on trades that actually govern the finish. */
    critical_path?: string[] | "auto";
  } = {}) {
    type Scenario = { zones: number; crews: number[]; crews_doubled: string[]; overlap: number;
      sequence: string[]; resequenced: boolean; duration_days: number;
      duration_weeks: number; crew_peak: number; labor_crew_days: number; cost: number;
      score: number; pareto: boolean; rank: number; is_baseline: boolean;
      trades: { name: string; takt_days: number; crews: number }[] };
    return this.json<{
      floors: number; trade_count: number; crew_day_rate: number; scenario_count: number;
      weights: { time: number; cost: number }; crew_candidates: string[]; pareto_count: number;
      levers: { zones: number[]; overlaps: number[]; sequence_variants: number; crew_candidates: string[] };
      trade_source: "body" | "schedule" | "default";
      crew_selection: { rule: string; critical_path: string[]; off_path_excluded: string[];
        unmatched_critical_path: string[]; note: string; source?: "body" | "cpm" };
      recommended: Scenario; baseline: Scenario | null; truncated: boolean;
      recommended_vs_baseline: { days: number; cost: number; pct_faster: number } | null;
      scenarios: Scenario[]; note: string;
    }>(`/projects/${pid}/schedule/optioneer`, { method: "POST", body: JSON.stringify(body) });
  }
  /** MASSING-OPT — sweep massing levers over a zoning envelope → ranked options + Pareto frontier (stateless). */
  schedule4d(pid: string, source?: "gc" | "takt") {
    return this.json<{ floors: number; duration_days?: number; total_days?: number; element_count: number;
      source: "takt" | "p6" | "gc"; start_date?: string; finish_date?: string; p6_activities?: number;
      activity_count?: number; linked?: number; unlinked?: number; by_trade: Record<string, number>;
      frames: { day: number; new: number; completed_cumulative: number; pct: number; date?: string; new_guids: string[];
        late?: number; early?: number; late_guids?: string[]; early_guids?: string[] }[] }>(
      `/projects/${pid}/schedule/4d${source ? `?source=${source}` : ""}`);
  }
  /** RESOURCE-LEVEL-2 — APPLY one leveling round: shift over-allocated activities forward within
   *  their CPM float (finish never moves). Mutates the schedule — gate behind an explicit confirm. */
  applyResourceLevel(pid: string, cap: number) {
    return this.json<{ cap: number; moved: number; peak_before: { units: number }; peak_after: { units: number };
      over_weeks_before: number; over_weeks_after: number; note: string;
      moves: { activity: string | null; shifted_days: number; new_start: string; new_finish: string; float_remaining: number }[] }>(
      `/projects/${pid}/schedule/resource-leveling/apply`, { method: "POST", body: JSON.stringify({ cap }) });
  }
  /** RESOURCE-LEVEL — the named-baseline library (metadata, newest first). */
  scheduleBaselines(pid: string) {
    return this.json<{ baselines: { id: string; name: string; captured_at: string; count: number }[] }>(
      `/projects/${pid}/schedule/baselines`);
  }
  /** Capture the current schedule as a new named baseline. */
  captureBaseline(pid: string, name: string) {
    return this.json<{ id: string; name: string; captured_at: string; count: number }>(
      `/projects/${pid}/schedule/baselines`, { method: "POST", body: JSON.stringify({ name }) });
  }
  deleteBaseline(pid: string, bid: string) {
    return this.json<{ deleted: boolean }>(`/projects/${pid}/schedule/baselines/${bid}`, { method: "DELETE" });
  }
  /** Per-activity slip of the live schedule vs a named baseline (`bid` or "latest"). */
  baselineVariance(pid: string, bid: string) {
    return this.json<{ baseline: { id: string; name: string; captured_at: string; count: number };
      summary: { slipped: number; improved: number; on_baseline: number; added: number; removed: number;
        max_slip_days: number; avg_finish_var: number };
      activities: { ref: string | null; name: string | null; start_var: number | null; finish_var: number | null; status: string }[] }>(
      `/projects/${pid}/schedule/baselines/${bid}/variance`);
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
  async importXer(pid: string, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const res = await fetch(this.url(`/projects/${pid}/schedule/import-xer`), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `import -> ${res.status}`); }
    return res.json() as Promise<{ count: number; start: string | null; finish: string | null; preview: { activity_id: string; name: string; start: string; finish: string }[] }>;
  }
  clearXer(pid: string) {
    return this.json<{ cleared: boolean }>(`/projects/${pid}/schedule/import-xer`, { method: "DELETE" });
  }
  /** SCHED-P6 — export the live schedule for round-trip into a scheduler's tool: Primavera P6 `.xer`
   *  or MS-Project XML (MSPDI). Reflects the current edited state, keyed by the P6 activity code. */
  async exportSchedule(pid: string, fmt: "xer" | "msp") {
    const res = await fetch(this.url(`/projects/${pid}/schedule/export?fmt=${fmt}`), { headers: this.authHeaders() });
    if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail || `export -> ${res.status}`); }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = fmt === "msp" ? "schedule.xml" : "schedule.xer"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }
  /** PROFORMA-LIVE: the model's takeoff-priced cost + GFA + budget delta — refresh on each publish. */
  scheduleCpm(pid: string) {
    return this.json<{ project_duration: number; activity_count: number; critical_count: number; has_cycle: boolean; critical_path: string[]; activities: { ref: string | null; name: string; duration: number; es: number; ef: number; total_float: number; critical: boolean }[] }>(
      `/projects/${pid}/schedule/cpm`);
  }
  /**
   * R45-SCHED-REACH — DCMA 14-point schedule quality.
   *
   * Read `available` before `grade`: a project with no activities and one with a logic loop both come
   * back `available: false` with `grade: null`, because neither is a *failing* schedule. Checks the
   * engine could not run are excluded from the score's denominator, so a clean schedule reads 100 over
   * its runnable checks rather than a diluted number over all fourteen.
   */
  scheduleHealth(pid: string) {
    return this.json<{
      available: boolean; reason?: string; grade: string | null; score: number | null;
      optimisable: boolean | null; assessed: number; skipped: number; failed: number;
      checks: { number: number; name: string; status: "pass" | "fail" | "skipped"; value: number | null;
                threshold: string; detail: string; offenders: string[]; offender_count: number }[];
    }>(`/projects/${pid}/schedule/health`);
  }

  /**
   * R45-SCHED-REACH — location-based (linear) scheduling: line of balance.
   *
   * `continuity_cost_days` is the point: per trade, what keeping that crew whole costs in days. CPM
   * cannot express crew continuity at all, so this is the number that says whether the method is
   * worth using on this job.
   */
  scheduleFlowline(pid: string) {
    return this.json<{
      available: boolean; reason?: string;
      locations: { id: string; name: string; sequence: number }[]; trades: string[];
      duration_days: number | null; continuity_cost_days: Record<string, number>;
      segments: { task_id: string; location_id: string; start_offset: number; finish_offset: number;
                  duration_days: number }[];
      interference_count: number;
    }>(`/projects/${pid}/schedule/flowline`);
  }

  /**
   * R45-SCHED-DEDUPE — takt planning. **Not the same method as the flowline**, and the difference is a
   * decision: every wagon occupies one zone for exactly one takt, so `(W + Z - 1)` takts is knowable
   * before the work is estimated. Paid for in idle capacity — `utilisation` is per wagon per zone and
   * unrounded. Omit `taktDays` for the shortest feasible rhythm plus the wagon that sets it.
   */
  scheduleTaktTrain(pid: string, taktDays?: number) {
    const q = taktDays ? `?takt_days=${taktDays}` : "";
    return this.json<{
      available: boolean; reason?: string; zones: string[]; wagons: string[];
      takt_days: number | null; duration_days: number | null; takt_count: number | null;
      minimum_takt_days: number | null; minimum_takt_set_by: string | null;
      crews: Record<string, number>; utilisation: Record<string, number>; overloaded: string[];
      slots: { wagon_id: string; zone_id: string; takt_index: number; crews: number;
               work_content: number }[];
    }>(`/projects/${pid}/schedule/takt-train${q}`);
  }

  /**
   * R45-SCHED-DEDUPE — deterministic resource levelling against per-trade crew caps.
   *
   * `horizon` has no safe default and is therefore explicit: `within_float` never moves the finish and
   * **reports** what it could not solve; `extend_finish` solves everything and accepts a later finish.
   * A job with liquidated damages wants the first; one that has blown its float wants the second.
   * Advisory — the server returns moves and never writes them.
   */
  scheduleLevel(pid: string, caps: Record<string, number>,
                horizon: "within_float" | "extend_finish" = "within_float") {
    return this.json<{
      available: boolean; reason?: string; horizon: string | null;
      finish_before: string | null; finish_after: string | null; finish_moved_days: number | null;
      moves: { activity_id: string; from_start: string; to_start: string; shifted_working_days: number;
               blocked_by: string[]; float_remaining_days: number }[];
      move_count: number | null; unresolved_count: number | null;
      peak_before: Record<string, number>; peak_after: Record<string, number>;
    }>(`/projects/${pid}/schedule/level`,
       { method: "POST", body: JSON.stringify({ caps, horizon }) });
  }

  /**
   * R45-SCHED-DEDUPE — progress of the **schedule** against a baseline: BEI, variance, slippage.
   *
   * Distinct from percent-complete of the *building*: a tower can be 60% erected and four weeks late.
   * `baseline_execution_index` is `null` when nothing was due, never `1.0` — an empty ratio is no
   * information, and a green tile on a project that has not started is worse than a blank one.
   */
  scheduleProgressReport(pid: string, baselineId?: string) {
    const q = baselineId ? `?baseline_id=${encodeURIComponent(baselineId)}` : "";
    return this.json<{
      available: boolean; reason?: string;
      baseline: { id: string; name: string; captured_at: string; count: number } | null;
      data_date: string | null; activity_count: number | null;
      complete: number | null; behind: number | null; not_started_but_due: number | null;
      baseline_execution_index: number | null; average_finish_variance_days: number | null;
      worst_slippage_days: number | null; worst_slippage_activity: string | null;
      invalid_actuals: string[];
    }>(`/projects/${pid}/schedule/progress-report${q}`);
  }

  /**
   * R45-SCHED-DEDUPE — Monte Carlo schedule risk on the **real** network.
   *
   * Distinct from `scheduleRisk`, which simulates an FS-only, calendar-free graph and converts
   * durations with plain calendar arithmetic. On a 100-working-day chain the two sit ~5 weeks apart,
   * and this is the one that does not count Saturdays. `confidence_in_deterministic` answers "how
   * likely is the programme date, really?"; `duration_sensitivity` says whether an activity's duration
   * actually moves the finish rather than merely sitting on the critical path often.
   */
  scheduleMonteCarlo(pid: string, opts: { iterations?: number; ppcPct?: number;
                                          distribution?: "pert" | "triangular" } = {}) {
    const q = new URLSearchParams();
    if (opts.iterations) q.set("iterations", String(opts.iterations));
    if (opts.ppcPct !== undefined) q.set("ppc_pct", String(opts.ppcPct));
    if (opts.distribution) q.set("distribution", opts.distribution);
    const qs = q.toString();
    return this.json<{
      available: boolean; reason?: string; iterations: number | null; distribution: string | null;
      seed: number | null; ppc_pct: number | null; pessimistic_factor: number | null;
      deterministic_finish: string | null; confidence_in_deterministic: number | null;
      p10: string | null; p50: string | null; p80: string | null; p90: string | null;
      most_critical: { id: string; name: string; criticality_index: number;
                       mean_duration: number; duration_sensitivity: number }[];
    }>(`/projects/${pid}/schedule/montecarlo${qs ? `?${qs}` : ""}`);
  }

  /**
   * R45-SCHED-DEDUPE — Last Planner reliability: PPC by week, with the reasons.
   *
   * **A third PPC on purpose.** `ppc` is `null` for a week whose commitments are not all answered — a
   * week in progress is unmeasurable, not perfect and not failing. The other two numbers in this app
   * divide by everything (reads low mid-week) and by the assessed only (reads high); this one freezes
   * the denominator at commit. Render `null` as an em-dash, never as 0.
   */
  scheduleReliability(pid: string) {
    return this.json<{
      available: boolean; reason?: string; weeks: number | null;
      trend: { week: string; committed: number; completed: number; unassessed: number;
               ppc: number | null }[];
      measurable_weeks: number | null; mean_ppc: number | null;
      top_reasons: { reason: string; count: number }[];
      undated_tasks: number; unusable_tasks: number; weeks_refused_at_commit: string[];
    }>(`/projects/${pid}/schedule/reliability`);
  }

  /** EST-1: upsert QTO-driven crew-day durations as EST schedule activities (one per trade, FS chain). */
  scheduleFromEstimate(pid: string, body: { loading?: string; rate?: number; crews?: number } = {}) {
    return this.json<{ written: { ref: string; trade: string; crew_days: number; duration_days: number;
      updated: boolean }[]; activities: number; estimate_total_cost: number;
      duration_working_days: number; cpm_project_duration: number; note: string }>(
      `/projects/${pid}/schedule/from-estimate`, { method: "POST", body: JSON.stringify(body) });
  }
  /** Developer cost budget (line-item hard/soft/acquisition + contingencies) + computed summary. */
  };
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
