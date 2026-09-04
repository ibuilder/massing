/** Schedule: CPM, 4D, takt, P6/MSP interchange, the Last-Planner pull board, and site logistics.
 *
 *  SCALE-SEAM ② took `/schedule`. SCALE-SEAM ㉝ adds the six Last-Planner methods that answer
 *  *did this week keep its commitments?* — the pull board, its PDF, PPC/TMR metrics, the
 *  pull-planning benchmark, lean PPC, and the live board stream. They span `/pull-plan` and
 *  `/lean/ppc`. License/integrations sat immediately above the cluster in `client.ts` and did
 *  **not** come (admin, not the board). Permit-city open data sat immediately below and did
 *  **not** come. Clash already rides this mixin so `ApiClient` does not grow another `withX()`.
 *
 *  SCALE-SEAM ㊱ adds the three logistics methods that answer *what resources are on site when?*
 *  They sit on the 4D timeline. The model graph sat immediately below them in `client.ts` and
 *  did **not** come — that is a relational query, not a site resource.
 *
 *  SCALE-SEAM ⓬ adds site-daily ops — *what happened on site this week?* OSHA safety
 *  rollup plus the daily-report field log. E57 sat below and did **not** come.
 */
import { IS_DEMO, demoTextOr } from "../demo/demoApi";
import { withClash } from "./clash";
import { HttpCore, type LiveStream } from "./httpCore";
import type { LogisticsResource, MakeReady } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withSchedule<TBase extends Ctor<HttpCore>>(Base: TBase) {
  // Clash rides here so ApiClient's mixin expression does not grow another
  // `withX()` — one more wrapper there loses HttpCore on the type (TS mixin depth).
  return class Schedule extends withClash(Base) {
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

  /** Schedule optioneering: sweep takt/zone/overlap levers and rank the resulting sequences. */
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
  /** 4D: schedule activities linked to model elements, by trade, with the source it came from. */
  schedule4d(pid: string, source?: "gc" | "takt") {
    return this.json<{ floors: number; duration_days?: number; total_days?: number; element_count: number;
      source: "takt" | "p6" | "gc"; start_date?: string; finish_date?: string; p6_activities?: number;
      activity_count?: number; linked?: number; unlinked?: number; by_trade: Record<string, number>;
      frames: { day: number; new: number; completed_cumulative: number; pct: number; date?: string; new_guids: string[];
        late?: number; early?: number; late_guids?: string[]; early_guids?: string[] }[] }>(
      `/projects/${pid}/schedule/4d${source ? `?source=${source}` : ""}`);
  }
  /** R21-4D-CLASH — space contention (two trades, one place, one window) plus install-before-support. */
  sequenceClash(pid: string, minOverlapDays = 1, crewThreshold = 0) {
    const q = new URLSearchParams({ min_overlap_days: String(minOverlapDays),
                                    crew_threshold: String(crewThreshold) });
    return this.json<{
      analyzed: number; skipped_count: number; locations: number;
      findings: { location: string; overlap_days: number; combined_crew: number;
        a: { id?: string; name: string; trade: string };
        b: { id?: string; name: string; trade: string };
        window: { start: string; finish: string } }[];
      finding_count: number; support_checked: boolean; support_pairs: number;
      support_finding_count: number;
      support_findings: { kind: string; grade: string;
        support: { guid: string; id?: string; name: string; trade: string; start: string; finish: string };
        supported: { guid: string; id?: string; name: string; trade: string; start: string; finish: string } }[];
      support_unscheduled_count: number; clean: boolean; note: string; not_covered: string;
      bound_activities: number;
    }>(`/projects/${pid}/clash/sequence?${q}`);
  }
  /** RESOURCE-LEVEL-2 — APPLY one leveling round: shift over-allocated activities forward within
   *  their CPM float (finish never moves). Mutates the schedule — gate behind an explicit confirm. */
  applyResourceLevel(pid: string, cap: number) {
    return this.json<{ cap: number; moved: number; peak_before: { units: number }; peak_after: { units: number };
      over_weeks_before: number; over_weeks_after: number; note: string;
      moves: { activity: string | null; shifted_days: number; new_start: string; new_finish: string; float_remaining: number }[] }>(
      `/projects/${pid}/schedule/resource-leveling/apply`, { method: "POST", body: JSON.stringify({ cap }) });
  }
  /**
   * RESOURCE-LEVEL — the named-baseline library (metadata, newest first).
   *
   * `has_logic` is false for a baseline captured before v0.3.961: those froze dates but no
   * predecessors, so `scheduleCompare` refuses them. Variance works against every baseline.
   */
  scheduleBaselines(pid: string) {
    return this.json<{ baselines: { id: string; name: string; captured_at: string; count: number;
      schema?: number; has_logic?: boolean }[] }>(
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
  /** READY-AGENT — every activity starting within `days`, its preconditions checked with cited
   *  evidence (incomplete predecessors by ref + % complete, open submittals by ref/state) and a
   *  ready/blocked verdict. Distinct from `scheduleLookahead`, which says what is COMING;
   *  this says whether it can actually START, and what is in the way. */
  scheduleMakeReady(pid: string, days = 14) {
    return this.json<MakeReady>(`/projects/${pid}/schedule/make-ready?days=${days}`);
  }
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
  /** CPM analysis of the schedule activities — duration, critical path, float, cycle detection. */
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
   * DEPRECATED alias for `scheduleMonteCarlo`, kept because retiring the `/schedule/risk` path is a
   * user-facing removal the roadmap records as undecided. Same response as `scheduleMonteCarlo`,
   * plus a `deprecated` note. The SHAPE changed with v0.3.972 — dates rather than day counts —
   * because the old shape was the wrong answer's shape.
   */
  scheduleRisk(pid: string, iterations = 1000) {
    return this.scheduleMonteCarlo(pid, { iterations });
  }

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
      /** P80 minus the programme date, in WORKING days on the schedule's own calendar. */
      buffer_p80_days: number | null;
      /** Spread measured from THIS project's finished work, reported beside the forecast. */
      calibration?: { n_finished: number; in_progress_excluded: number; outliers_excluded: number;
                      by_trade: Record<string, unknown>; note: string };
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

  /**
   * R45-SCHED-REACH — diff the live schedule against a named baseline and attribute the finish move.
   *
   * Not `scheduleVariance`. That one answers "did this activity's dates move"; this re-schedules the
   * baseline through the CPM engine and answers **why the finish moved**, apportioning the move
   * across duration growth, added logic, lag, constraints, progress and levelling. The contributions
   * sum to `finish_move_days` exactly — render that as the check it is, not as decoration.
   *
   * Two things to render carefully:
   * - `available: false` with a reason is the normal answer for a baseline captured before
   *   v0.3.961. Those hold dates but no logic, and the reason says to capture a new one. Show the
   *   sentence; do not fall back to a zero.
   * - an `unexplained` contribution is usually **not** a mystery: the engine's contributions are in
   *   working days and its total is in calendar days, and `calendar_vs_working_gap_days` is how much
   *   of the residual is that arithmetic. Subtract it before telling anyone days are unaccounted for.
   */
  scheduleCompare(pid: string, opts: { baselineId?: string; match?: "id" | "code" } = {}) {
    const q = new URLSearchParams();
    if (opts.baselineId) q.set("baseline_id", opts.baselineId);
    if (opts.match) q.set("match", opts.match);
    return this.json<{
      available: boolean; reason?: string;
      baseline: { id: string; name: string; captured_at: string; count: number;
                  schema: number; has_logic: boolean } | null;
      match_key: string | null;
      baseline_finish: string | null; current_finish: string | null;
      finish_move_days: number | null; finish_move_working_days?: number | null;
      calendar_vs_working_gap_days?: number | null;
      activity_count: number | null; changed_count: number | null;
      changes_by_kind: Record<string, number>; link_changes: number | null;
      criticality_gained: string[]; criticality_lost: string[]; ambiguous_matches: string[];
      driving_path: {
        baseline_path: string[]; current_path: string[]; entered: string[]; left: string[];
        finish_move_days: number; attribution_sums: boolean;
        attribution: { activity_id: string | null; cause: string; days: number;
                       evidence: string }[];
      } | null;
      cycle?: string[];
    }>(`/projects/${pid}/schedule/compare${q.toString() ? `?${q}` : ""}`);
  }

  /**
   * R46 — what finishing `targetDays` earlier would take, and cost.
   *
   * Not `scheduleOptimize`, which is a rule-based advisory that never re-schedules: it reports
   * `duration × 0.25` per long critical activity, which cannot see the path behind it. On a
   * four-activity network with a near-parallel path the advisory says 5 days and the finish moves 3.
   *
   * `days_saved` is what the PROJECT finish moved, not what came off the activity. Render
   * `meets_target: false` plainly — eight of the ten days asked for is the answer, not an error.
   * `costs` are required; there is no default for how far an activity can be shortened.
   */
  scheduleCompress(pid: string, body: {
    target_days: number;
    costs: { activity_id: string; cost_per_day: number; max_days: number }[];
    fast_trackable?: [string, string][];
  }) {
    return this.json<{
      available: boolean; reason?: string; rejected_costs: string[];
      activities_without_costs: number | null; target_days: number | null;
      finish_before: string | null; best_finish: string | null;
      days_available: number | null; meets_target: boolean | null; total_cost: number | null;
      options: { kind: string; activity_id: string; days_shortened?: number; cost?: number;
        days_saved: number; cost_per_day_saved: number | null;
        finish_before: string; finish_after: string }[];
      notes: string[];
    }>(`/projects/${pid}/schedule/compress`, { method: "POST", body: JSON.stringify(body) });
  }

  /**
   * R46 — the weather allowance a programme already carries, made explicit.
   *
   * No allowance is invented: days per month come from the contract or a met-office table, and a
   * request with none is refused rather than defaulted to a "typical year". The days are listed,
   * not just counted — an allowance is argued with.
   */
  scheduleWeather(pid: string, body: { days_by_month: Record<string, number>;
                                       start?: string; finish?: string }) {
    return this.json<{
      available: boolean; reason?: string; allowance_days: number | null;
      by_month: Record<string, number>; days: string[];
      window_start: string | null; window_finish: string | null;
      finish_without_allowance: string | null; rejected_months: string[];
      weather_days_only: boolean | null; distribution: string | null;
    }>(`/projects/${pid}/schedule/weather`, { method: "POST", body: JSON.stringify(body) });
  }

  /**
   * R46 — several projects scheduled together, with the links between them honoured.
   *
   * One pass over one merged network. Scheduling projects in sequence propagates a delay only in
   * whichever order they were listed. **Membership is checked server-side on every id you send**, so
   * a 403 here means the caller is not a member of one of them — surface that, do not retry.
   */
  schedulePortfolio(pid: string, body: {
    project_ids: string[];
    external?: { predecessor_project: string; predecessor_id: string;
                 successor_project: string; successor_id: string;
                 type?: string; lag_days?: number }[];
  }) {
    return this.json<{
      available: boolean; reason?: string;
      projects: { id: string; name: string; activities: number }[];
      external_links: { predecessor: string; successor: string; type: string; lag_days: number }[];
      rejected_links: string[]; projects_without_activities: string[];
      programme_finish: string | null; project_count: number | null;
      external_link_count: number | null;
      // The merged pass returns per-project dates and the activities that cross a boundary. This
      // type declared only the three scalars above until v0.3.1144, so the dates reached the browser
      // and were dropped before anything could draw them — which is why the roadmap recorded the
      // cross-project Gantt as missing an engine it already had. Keyed by project id.
      project_starts?: Record<string, string>;
      project_finishes?: Record<string, string>;
      crossing_activities?: string[];
      issues?: { code?: string; message?: string }[];
    }>(`/projects/${pid}/schedule/portfolio`, { method: "POST", body: JSON.stringify(body) });
  }

  /**
   * R46 — Earned Schedule: how far along in TIME.
   *
   * Not a duplicate of `evm`'s SPI. Classic `SPI = EV/PV` converges on exactly **1.0** at completion
   * whatever the dates did — it arrives at "perfectly on schedule" for a job that finished a year
   * late. `SPI(t) = ES / AT` compares two durations and stays below 1.0. Render both if you show
   * both, and label which is which.
   *
   * `performance_index` is `null` when no time has passed — show an em-dash, never 1.0, which would
   * say a project that has not started is exactly on schedule. Everything is in **working days**.
   *
   * This is the one baseline method that accepts a pre-v0.3.961 snapshot: it needs only dates.
   */
  scheduleEarned(pid: string, baselineId?: string) {
    return this.json<{
      available: boolean; reason?: string;
      baseline: { id: string; name: string; captured_at: string; count: number;
                  schema: number; has_logic: boolean } | null;
      data_date: string | null; planned_duration_days: number | null;
      actual_time_days: number | null; earned_days: number | null;
      earned_duration_days: number | null; baseline_duration_days: number | null;
      schedule_variance_days: number | null; performance_index: number | null;
      unit: string; baseline_undated: number | null; unbaselined_activities: number | null;
    }>(`/projects/${pid}/schedule/earned${baselineId ? `?baseline_id=${baselineId}` : ""}`);
  }

  /**
   * R46 — contemporaneous windows analysis (AACE 29R-03 MIP 3.3): where the time went, period by
   * period.
   *
   * The headline is `worst_window` + `worst_window_slip_days`: *which period lost the time*, which
   * an as-planned-vs-as-built comparison structurally cannot answer. `windows_sum` is the invariant
   * — render it as the check it is. A negative `slip_days` is acceleration and must be shown as
   * such, never dropped: a claim that counts only the slips overstates itself.
   *
   * `skipped_without_logic` lists baselines captured before v0.3.961. Show them — an analysis over
   * 2 of 8 snapshots is answering a question about a different job.
   */
  scheduleWindows(pid: string, match: "id" | "code" = "id") {
    return this.json<{
      available: boolean; reason?: string; hint?: string;
      updates: string[]; skipped_without_logic: string[]; skipped_cyclic: string[];
      method: string | null; window_count: number | null;
      first_finish: string | null; last_finish: string | null;
      total_slip_days: number | null; windows_sum: boolean | null;
      worst_window: number | null; worst_window_slip_days: number | null;
      path_changes: number | null; by_cause: Record<string, number>; issue_count: number | null;
      windows: { index: number; opened: string; closed: string; opening_finish: string;
        closing_finish: string; slip_days: number; driving_path_changed: boolean;
        driving_path: string[];
        attribution: { activity_id: string | null; cause: string; days: number;
                       evidence: string }[] }[];
    }>(`/projects/${pid}/schedule/windows?match=${match}`);
  }

  /**
   * R46 — impacted as-planned (MIP 3.6, additive) and collapsed as-built (MIP 3.9, subtractive).
   *
   * `concurrency_days` is the number worth rendering loudest: how much the individual impacts
   * exceed their combined impact. Two five-day delays running concurrently move the finish five
   * days, not ten, and that overlap is the entitlement nobody gets twice.
   *
   * `days_source` is `"caller"` — say so on the screen. Nothing in the field record says what a
   * delay cost, so the most contested input is typed. `rejected_events` names events that could not
   * be used; a silently dropped event is an entitlement quietly shrinking.
   *
   * Per-event `days` are WORKING days and `calendar_days` sits beside them. Do not add across the
   * two: mixing the axes is what makes concurrency come out negative.
   */
  scheduleImpacted(pid: string, events: Record<string, unknown>[], baselineId?: string) {
    return this.json<ModelledDelay>(`/projects/${pid}/schedule/impacted`,
      { method: "POST", body: JSON.stringify({ events, baseline_id: baselineId }) });
  }

  /** R46 — the subtractive twin. Refuses unless the events are already activities in the as-built. */
  scheduleCollapsed(pid: string, events: Record<string, unknown>[]) {
    return this.json<ModelledDelay>(`/projects/${pid}/schedule/collapsed`,
      { method: "POST", body: JSON.stringify({ events }) });
  }

  /** EST-1: upsert QTO-driven crew-day durations as EST schedule activities (one per trade, FS chain). */
  scheduleFromEstimate(pid: string, body: { loading?: string; rate?: number; crews?: number } = {}) {
    return this.json<{ written: { ref: string; trade: string; crew_days: number; duration_days: number;
      updated: boolean }[]; activities: number; estimate_total_cost: number;
      duration_working_days: number; cpm_project_duration: number; note: string }>(
      `/projects/${pid}/schedule/from-estimate`, { method: "POST", body: JSON.stringify(body) });
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
  /** pullPlanPdfUrl — printable Last-Planner board. */
  pullPlanPdfUrl(pid: string, milestone?: string) {
    const qs = milestone ? `?milestone=${encodeURIComponent(milestone)}` : "";
    return this.url(`/projects/${pid}/pull-plan/board.pdf${qs}`);
  }
  /** pullPlanMetrics — TMR, handoff cleanliness, PPC trend, variance Pareto. */
  pullPlanMetrics(pid: string, milestone?: string) {
    const qs = milestone ? `?milestone=${encodeURIComponent(milestone)}` : "";
    return this.json<{ total: number; tasks_made_ready: number; tmr_pct: number | null;
      make_ready_runway_weeks: number; perfect_handoff_pct: number | null; clean_handoffs: number;
      handoffs: number; ppc_pct: number | null; committed: number; done: number;
      ppc_trend: { week: string; committed: number; done: number; ppc_pct: number | null }[];
      variance_pareto: { reason: string; count: number }[]; note: string }>(
      `/projects/${pid}/pull-plan/metrics${qs}`);
  }
  /** benchmarksPullPlanning — PPC/TMR distribution across the caller's projects. */
  benchmarksPullPlanning() {
    return this.json<{ projects: number; target_ppc?: number; message?: string | null;
      ppc?: { low: number; median: number; high: number; avg: number };
      tmr?: { low: number; median: number; high: number; avg: number };
      per_project?: { project_id: string; ppc_pct: number; tmr_pct: number; committed: number }[] }>(
      `/benchmarks/pull-planning`);
  }
  /** leanPpc — Last-Planner percent complete plus missed-commitment reasons. */
  leanPpc(pid: string) {
    return this.json<{ commitments: number; completed: number; ppc: number; missed: number; rating: string; top_variance_reasons: { reason: string; count: number }[] }>(
      `/projects/${pid}/lean/ppc`);
  }
  /** SSE stream of the pull-board change-signature; fires whenever any trade edits a sticky note so
   *  the board can live-refresh. Returns a resilient handle so callers can close it on teardown. */
  pullPlanStream(pid: string, onMessage: (d: { count: number; latest: string | null }) => void,
                 onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    return this.liveStream(`/projects/${pid}/pull-plan/stream`,
                           onMessage as (d: unknown) => void, onStatus);
  }

  /** getLogistics — site resources placed on the 4D timeline. */
  getLogistics(pid: string) {
    return this.json<{ resources: LogisticsResource[]; summary: { total: number; by_kind: Record<string, number>; start: string | null; end: string | null } }>(`/projects/${pid}/logistics`);
  }
  /** putLogistics — replace the project's site-logistics resource list. */
  putLogistics(pid: string, resources: LogisticsResource[]) {
    return this.json<{ resources: LogisticsResource[] }>(`/projects/${pid}/logistics`, { method: "PUT", body: JSON.stringify({ resources }) });
  }
  /** logisticsState — which site resources are active on a given date. */
  logisticsState(pid: string, date?: string) {
    return this.json<{ date: string | null; active: LogisticsResource[]; active_count: number; total: number }>(`/projects/${pid}/logistics/state${date ? `?date=${encodeURIComponent(date)}` : ""}`);
  }

  /** verifiedProgress — as-built vs claimed progress per schedule activity plus the trust gap. */
  verifiedProgress(pid: string) {
    return this.json<{ elements_total: number; elements_verified: number; elements_deviated: number;
      verified_pct: number; claimed_pct: number; trust_gap: number; coverage_pct: number;
      verification_records: number;
      activities: { ref: string; activity: string; trade: string | null; elements: number; verified: number;
        deviated: number; verified_pct: number; planned_pct: number | null; trust_gap: number }[] }>(
      `/projects/${pid}/verified-progress`);
  }
  /** progressRollup — installed GUIDs rolled up by class, discipline and level. */
  progressRollup(pid: string, installedGuids: string[], elements?: Record<string, unknown>[]) {
    type Grp = { expected: number; installed: number; pct_complete: number; value_total: number; pct_complete_value: number | null };
    return this.json<{
      element_count: number; installed_count: number; pct_complete: number; value_total: number;
      value_installed: number; pct_complete_value: number | null;
      by_class: (Grp & { ifc_class: string })[]; by_discipline: (Grp & { discipline: string })[];
      by_level: (Grp & { level: string })[]; note: string;
    }>(`/projects/${pid}/progress/rollup`, { method: "POST", body: JSON.stringify({ installed_guids: installedGuids, elements }) });
  }
  /** progressCaptureDiff — newly installed and disappeared between two capture timestamps. */
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

  /** safetySummary — OSHA TRIR/DART/LTIFR, observation mix, toolbox coverage, violations. */
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

  // --- The recordable-rate metrics behind that summary ---
  /** Safety analytics — incidents by OSHA class, recordable/lost-time counts, TRIR/DART. */
  safetyMetrics(pid: string) {
    return this.json<{ incident_count: number; recordable_count: number; lost_time_count: number; lost_days: number; hours_worked: number; trir: number | null; dart: number | null; observation_count: number; toolbox_talk_count: number }>(
      `/projects/${pid}/safety/metrics`);
  }
  /** fieldLogSummary — manpower trend, weather-impact lost-days, reporting coverage. */
  fieldLogSummary(pid: string) {
    return this.json<{ report_count: number; submitted_count: number; coverage_pct: number | null;
      total_manpower: number; avg_manpower: number | null;
      peak_manpower: { count: number; date: string | null }; weather_lost_days: number;
      delay_days: number; by_weather: Record<string, number>; by_impact: Record<string, number>;
      rows: Record<string, unknown>[] }>(`/projects/${pid}/daily-reports/summary`);
  }
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

/** R46 — a modelled delay counterfactual, with the AACE method that produced it attached. */
export interface ModelledDelay {
  available: boolean;
  reason?: string;
  baseline: { id: string; name: string; captured_at: string; count: number } | null;
  rejected_events: string[];
  missing_from_as_built?: string[];
  /** Always "caller": nothing in the field record says what a delay cost. */
  days_source: string | null;
  method: string | null;
  mip: string | null;
  unimpacted_finish: string | null;
  impacted_finish: string | null;
  /** Working days. `total_calendar_days` is the same move in elapsed time — never add the two. */
  total_days: number | null;
  total_calendar_days: number | null;
  sum_of_individual_days: number | null;
  /** How much the individual impacts overstate the combined one. The five nobody gets twice. */
  concurrency_days: number | null;
  is_concurrent: boolean | null;
  per_event: { id: string; name: string; duration_days: number; impacts: string;
    onset: string | null; responsibility: string; finish_without: string; finish_with: string;
    days: number; calendar_days: number }[];
  notes: string[];
}
