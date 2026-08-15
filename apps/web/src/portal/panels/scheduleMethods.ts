/**
 * R45 — the four scheduling methods, on a screen.
 *
 * Each of these took three gates to ship honestly, and the sequence is worth recording because it is
 * the same question asked at four depths:
 *
 * 1. `test_vendor_reachable` — is the vendored *module* reached from the API at all?
 * 2. `test_reachable` — is that module behind a *route*?
 * 3. `test_route_reachability` — does a *client method* call that route?
 * 4. `clientCallers.test.ts` — does a *screen* call that client method?
 *
 * Every one of them caught something. A module behind no route, a route no client calls and a client
 * method no screen calls are all indistinguishable from a shipped feature when read from the inside,
 * and each layer only sees its own hop. This file is the fourth hop.
 *
 * **The rendering rule, shared by all four: read `available` before reading any number.** Every one of
 * these engines can be asked a question it cannot answer — a project with no locations, a schedule
 * with a logic loop, a levelling run with no crew caps — and every one returns `available: false` with
 * a reason rather than a zero. Rendering the zero is how "we could not measure" becomes "this is
 * terrible" on somebody's screen.
 */
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

type Row = { label: string; value: string; hint?: string };

function card(title: string, sub: string): HTMLElement {
  const c = document.createElement("div");
  c.className = "dash-card";
  c.style.cssText = "margin:6px 0";
  c.innerHTML = `<div class="section-title">${esc(title)}</div><div class="meta">${esc(sub)}</div>`;
  return c;
}

/** A result block. `available: false` renders the reason and NO numbers — never a plausible zero. */
function render(host: HTMLElement, out: { available: boolean; reason?: string }, rows: Row[]): void {
  host.innerHTML = "";
  if (!out.available) {
    const why = document.createElement("div");
    why.className = "meta";
    why.dataset.unavailable = "1";
    why.style.cssText = "padding:6px 0;line-height:1.45";
    // textContent: the reason is composed server-side and names user data (a location, a trade).
    why.textContent = out.reason || "Not available for this project.";
    host.appendChild(why);
    return;
  }
  const grid = document.createElement("div");
  grid.style.cssText = "display:flex;flex-wrap:wrap;gap:14px;margin:4px 0";
  for (const r of rows) {
    const cell = document.createElement("div");
    cell.style.cssText = "min-width:120px";
    const v = document.createElement("div");
    v.style.cssText = "font-size:18px;font-weight:700;font-variant-numeric:tabular-nums";
    v.textContent = r.value;
    const l = document.createElement("div");
    l.className = "meta"; l.style.fontSize = "11px";
    l.textContent = r.label;
    cell.append(v, l);
    if (r.hint) { const h = document.createElement("div"); h.className = "meta"; h.style.fontSize = "10.5px"; h.textContent = r.hint; cell.appendChild(h); }
    grid.appendChild(cell);
  }
  host.appendChild(grid);
}

function runner(host: HTMLElement, label: string, go: () => Promise<void>): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = "tool-btn";
  b.textContent = label;
  b.onclick = async () => {
    b.disabled = true; host.textContent = "Running…";
    try { await go(); } catch (e) { host.textContent = `failed: ${(e as Error).message}`; }
    finally { b.disabled = false; }
  };
  return b;
}

export function renderScheduleMethods(ctx: PanelContext): HTMLElement {
  const pid = ctx.host.projectId()!;
  const api = ctx.host.api;
  const wrap = document.createElement("div");

  // ── DCMA 14-point ────────────────────────────────────────────────────────────────────────────
  const hc = card("Schedule quality — DCMA 14-point",
    "The industry's shared definition of whether a schedule is trustworthy. Checks that could not "
    + "run are excluded from the score, so a clean schedule reads 100 over its runnable checks.");
  const hOut = document.createElement("div");
  hc.appendChild(runner(hOut, "▶ Assess", async () => {
    const r = await api.scheduleHealth(pid);
    render(hOut, r, r.available ? [
      { label: "grade", value: r.grade ?? "—" },
      { label: "score", value: r.score === null ? "—" : `${r.score}` , hint: `${r.assessed} checks run` },
      { label: "failed", value: `${r.failed}` },
      { label: "skipped", value: `${r.skipped}`, hint: "excluded from the score" },
    ] : []);
    if (r.available) {
      const fails = r.checks.filter((c) => c.status === "fail");
      if (fails.length) {
        const ul = document.createElement("div"); ul.className = "meta"; ul.style.marginTop = "4px";
        for (const c of fails) {
          const li = document.createElement("div");
          li.textContent = `${c.number}. ${c.name} — ${c.detail}`;
          ul.appendChild(li);
        }
        hOut.appendChild(ul);
      }
    }
  }));
  hc.appendChild(hOut); wrap.appendChild(hc);

  // ── Line of balance ──────────────────────────────────────────────────────────────────────────
  const fc = card("Flowline — line of balance",
    "Where each crew is, and whether anyone is in anyone's way. CPM cannot express crew continuity: "
    + "its earliest-start pass is exactly what fragments a gang into work-a-floor-then-wait.");
  const fOut = document.createElement("div");
  fc.appendChild(runner(fOut, "▶ Compute flowline", async () => {
    const r = await api.scheduleFlowline(pid);
    const cost = Object.entries(r.continuity_cost_days ?? {});
    const worst = cost.sort((a, b) => b[1] - a[1])[0];
    render(fOut, r, r.available ? [
      { label: "duration", value: `${r.duration_days}d` },
      { label: "locations", value: `${r.locations.length}` },
      { label: "trades", value: `${r.trades.length}` },
      { label: "continuity cost", value: worst ? `${worst[1]}d` : "0d",
        hint: worst ? `worst: ${worst[0]}` : "no crew was pushed" },
    ] : []);
  }));
  fc.appendChild(fOut); wrap.appendChild(fc);

  // ── Takt ─────────────────────────────────────────────────────────────────────────────────────
  const tc = card("Takt train — a fixed rhythm",
    "Not the same method as the flowline. Every wagon occupies one zone for exactly one takt, so "
    + "(wagons + zones − 1) takts is knowable before the work is estimated. Paid for in idle capacity.");
  const tOut = document.createElement("div");
  tc.appendChild(runner(tOut, "▶ Build train", async () => {
    const r = await api.scheduleTaktTrain(pid);
    const u = Object.values(r.utilisation ?? {});
    const lowest = u.length ? Math.min(...u) : null;
    render(tOut, r, r.available ? [
      { label: "takt", value: `${r.takt_days}d`, hint: `min ${r.minimum_takt_days}d — set by ${r.minimum_takt_set_by}` },
      { label: "duration", value: `${r.duration_days}d`, hint: `${r.takt_count} takts` },
      { label: "lowest utilisation", value: lowest === null ? "—" : `${Math.round(lowest * 100)}%`,
        hint: "capacity paid for and not worked" },
      { label: "overloaded", value: `${r.overloaded.length}` },
    ] : []);
  }));
  tc.appendChild(tOut); wrap.appendChild(tc);

  // ── Progress vs baseline ─────────────────────────────────────────────────────────────────────
  const pc = card("Progress vs baseline — BEI, variance, slippage",
    "How the SCHEDULE is standing, not how much of the building is up. A tower can be 60% erected "
    + "and four weeks late. Needs a captured baseline; without one there is nothing to measure against.");
  const pOut = document.createElement("div");
  pc.appendChild(runner(pOut, "▶ Measure progress", async () => {
    const r = await api.scheduleProgressReport(pid);
    render(pOut, r, r.available ? [
      // null, not 0 — nothing was due yet. Rendering "0" here would read as a project doing no work.
      { label: "BEI", value: r.baseline_execution_index === null ? "—" : r.baseline_execution_index.toFixed(2),
        hint: r.baseline_execution_index === null ? "nothing was due yet" : "completed / should-have" },
      { label: "behind", value: `${r.behind}`,
        hint: `${r.not_started_but_due} due but never started` },
      { label: "complete", value: `${r.complete}`, hint: `of ${r.activity_count}` },
      { label: "worst slip", value: r.worst_slippage_days === null ? "—" : `${r.worst_slippage_days}d`,
        hint: r.worst_slippage_activity ?? "" },
    ] : []);
    if (r.available && r.invalid_actuals.length) {
      const w = document.createElement("div");
      w.className = "meta"; w.style.marginTop = "4px";
      w.textContent = `${r.invalid_actuals.length} actual date(s) could not be used: `
        + r.invalid_actuals.slice(0, 6).join(", ");
      pOut.appendChild(w);
    }
  }));
  pc.appendChild(pOut); wrap.appendChild(pc);

  // ── Monte Carlo ──────────────────────────────────────────────────────────────────────────────
  const mc = card("Monte Carlo — how likely is the programme date?",
    "Runs the real network, so it honours relation types, lags and work calendars. Confidence is the "
    + "share of runs that met the CPM date; sensitivity says whether an activity's duration actually "
    + "moves the finish, not just how often it sits on the critical path.");
  const mOut = document.createElement("div");
  mc.appendChild(runner(mOut, "▶ Simulate", async () => {
    const r = await api.scheduleMonteCarlo(pid, { iterations: 2000 });
    render(mOut, r, r.available ? [
      { label: "P50", value: r.p50 ?? "—" },
      { label: "P80", value: r.p80 ?? "—", hint: "80% of runs finished by here" },
      { label: "confidence in CPM date",
        value: r.confidence_in_deterministic === null ? "—"
          : `${Math.round(r.confidence_in_deterministic * 100)}%`,
        hint: r.deterministic_finish ?? "" },
      { label: "iterations", value: `${r.iterations}`, hint: r.distribution ?? "" },
    ] : []);
    if (r.available && r.most_critical.length) {
      const t = document.createElement("div");
      t.className = "meta"; t.style.marginTop = "4px";
      t.textContent = "drives the finish: " + r.most_critical.slice(0, 3)
        .map((a) => `${a.name || a.id} (${Math.round(a.criticality_index * 100)}% critical, `
                  + `sensitivity ${a.duration_sensitivity.toFixed(2)})`).join(" · ");
      mOut.appendChild(t);
    }
  }));
  mc.appendChild(mOut); wrap.appendChild(mc);

  // ── Last Planner reliability ─────────────────────────────────────────────────────────────────
  const rc = card("Last Planner reliability — PPC by week",
    "A week whose commitments are not all answered reads as unmeasurable, not as a score. The other "
    + "PPC numbers in this app divide by everything (low mid-week) or by the assessed only (high).");
  const rOut = document.createElement("div");
  rc.appendChild(runner(rOut, "▶ Score reliability", async () => {
    const r = await api.scheduleReliability(pid);
    render(rOut, r, r.available ? [
      { label: "mean PPC", value: r.mean_ppc === null ? "—" : `${Math.round(r.mean_ppc * 100)}%`,
        hint: `over ${r.measurable_weeks} measurable week(s)` },
      { label: "weeks", value: `${r.weeks}` },
      { label: "top reason", value: r.top_reasons[0]?.reason ?? "—",
        hint: r.top_reasons[0] ? `${r.top_reasons[0].count}x` : "no misses recorded" },
      { label: "not counted", value: `${r.undated_tasks + r.unusable_tasks}`,
        hint: "undated or unusable tasks" },
    ] : []);
    if (r.available && r.trend.length) {
      const t = document.createElement("div");
      t.className = "meta"; t.style.marginTop = "4px";
      // `null` renders as "—", never as 0 — an unmeasurable week is not a failed one.
      t.textContent = r.trend.map((w) => `${w.week}: `
        + (w.ppc === null ? `— (${w.unassessed} unanswered)` : `${Math.round(w.ppc * 100)}%`)).join("  ·  ");
      rOut.appendChild(t);
    }
  }));
  rc.appendChild(rOut); wrap.appendChild(rc);

  // ── Earned Schedule ──────────────────────────────────────────────────────────────────────────
  const esc2 = card("Earned Schedule — how far along in time",
    "Classic SPI is a cost ratio used as a time signal, and it returns to exactly 1.0 at completion "
    + "however late the job was. SPI(t) compares two durations and stays below 1.0. Works on any "
    + "captured baseline — this one needs only dates.");
  const eOut = document.createElement("div");
  esc2.appendChild(runner(eOut, "▶ Measure", async () => {
    const r = await api.scheduleEarned(pid);
    render(eOut, r, r.available ? [
      // null renders as an em-dash, never 1.0 — "exactly on schedule" is the worst value to invent.
      { label: "SPI(t)", value: r.performance_index == null ? "—" : r.performance_index.toFixed(3),
        hint: r.performance_index == null ? "no time elapsed"
          : r.performance_index < 1 ? "behind" : "at or ahead of plan" },
      { label: "SV(t)", value: r.schedule_variance_days == null ? "—"
          : `${r.schedule_variance_days > 0 ? "+" : ""}${r.schedule_variance_days}d`,
        hint: "working days" },
      { label: "elapsed / earned", value: `${r.actual_time_days ?? "—"} / ${r.earned_days ?? "—"}`,
        hint: `of ${r.planned_duration_days ?? "—"}d planned` },
      { label: "vs baseline", value: r.baseline?.name ?? "—",
        hint: r.baseline?.has_logic === false ? "dates-only baseline — fine for this method" : "" },
    ] : []);
    if (r.available && ((r.unbaselined_activities ?? 0) || (r.baseline_undated ?? 0))) {
      const n = document.createElement("div");
      n.className = "meta"; n.style.cssText = "margin-top:4px;font-size:10.5px";
      n.textContent = `excluded: ${r.unbaselined_activities ?? 0} activity(ies) not in the baseline`
        + `, ${r.baseline_undated ?? 0} baseline row(s) undated — counting work the plan never `
        + "contained would inflate the index";
      eOut.appendChild(n);
    }
  }));
  esc2.appendChild(eOut); wrap.appendChild(esc2);

  // ── Windows analysis ─────────────────────────────────────────────────────────────────────────
  const wc = card("Windows analysis — where the time went, period by period",
    "AACE 29R-03 MIP 3.3, over the captured baseline library. As-planned-vs-as-built compares two "
    + "end states; a project eighty days late did not lose them in one step, and a claim has to say "
    + "which period lost which.");
  const wOut = document.createElement("div");
  wc.appendChild(runner(wOut, "▶ Analyse windows", async () => {
    const r = await api.scheduleWindows(pid);
    render(wOut, r, r.available ? [
      { label: "total slip", value: r.total_slip_days == null ? "—" : `${r.total_slip_days}d`,
        hint: `${r.first_finish} → ${r.last_finish}` },
      { label: "worst window", value: r.worst_window == null ? "—" : `#${r.worst_window + 1}`,
        hint: r.worst_window_slip_days == null ? "" : `lost ${r.worst_window_slip_days}d` },
      { label: "windows", value: `${r.window_count}`,
        hint: `${r.path_changes ?? 0} driving-path change(s)` },
      { label: "sums", value: r.windows_sum ? "✓" : "✗",
        hint: "the periods add to the whole" },
    ] : []);
    if (!r.available) {
      if (r.hint) {
        const h = document.createElement("div");
        h.className = "meta"; h.style.marginTop = "4px"; h.textContent = r.hint;
        wOut.appendChild(h);
      }
      return;
    }
    const t = document.createElement("div");
    t.className = "meta"; t.style.cssText = "margin-top:4px;line-height:1.5";
    // Acceleration renders as a negative, deliberately — a series that showed only the slips would
    // not sum to the total, and the sum is the invariant this method rests on.
    t.textContent = r.windows.map((w) => `${w.opened}→${w.closed}: `
      + `${w.slip_days > 0 ? "+" : ""}${w.slip_days}d`
      + (w.driving_path_changed ? " (path changed)" : "")).join("  ·  ");
    wOut.appendChild(t);
    const causes = Object.entries(r.by_cause);
    if (causes.length) {
      const c = document.createElement("div");
      c.className = "meta"; c.style.cssText = "margin-top:2px;font-size:10.5px";
      c.textContent = "by cause: " + causes.map(([k, v]) => `${v}d ${k.replace(/_/g, " ")}`).join(", ");
      wOut.appendChild(c);
    }
    // Named, because an analysis over 2 of 8 snapshots answers a question about a different job.
    if (r.skipped_without_logic.length || r.skipped_cyclic.length) {
      const sk = document.createElement("div");
      sk.className = "meta"; sk.style.cssText = "margin-top:2px;font-size:10.5px";
      sk.textContent = [
        r.skipped_without_logic.length
          ? `not analysed (captured before logic was stored): ${r.skipped_without_logic.join(", ")}` : "",
        r.skipped_cyclic.length ? `skipped (logic loop): ${r.skipped_cyclic.join(", ")}` : "",
      ].filter(Boolean).join(" · ");
      wOut.appendChild(sk);
    }
  }));
  wc.appendChild(wOut); wrap.appendChild(wc);

  // ── Modelled delay ───────────────────────────────────────────────────────────────────────────
  const mdc = card("Modelled delay — impacted as-planned / collapsed as-built",
    "The two methods that ALTER the network rather than observing it (AACE MIP 3.6 / 3.9). Enter "
    + "the delays as 'activity:days' — the duration is yours, because nothing in the field record "
    + "says what an event cost.");
  const evIn = document.createElement("input");
  evIn.type = "text"; evIn.placeholder = "delays, e.g. A20=10, A30=6";
  evIn.className = "tool-btn";
  evIn.style.cssText = "min-width:240px;text-align:left;cursor:text";
  const mdOut = document.createElement("div");
  // Parsed client-side so a malformed entry is a visible error here, not a silent empty list there.
  const parseEvents = () => {
    const out: Record<string, unknown>[] = [];
    for (const [i, part] of evIn.value.split(",").entries()) {
      const [k, v] = part.split("=");
      const days = Number((v ?? "").trim());
      if (k?.trim() && Number.isFinite(days) && days > 0) {
        out.push({ id: `E${i + 1}`, name: `Delay to ${k.trim()}`, impacts: k.trim(), days });
      }
    }
    return out;
  };
  const showModelled = (r: Awaited<ReturnType<typeof api.scheduleImpacted>>) => {
    render(mdOut, r, r.available ? [
      { label: "delay", value: r.total_days == null ? "—" : `${r.total_days}d`,
        hint: `working days · ${r.total_calendar_days}d elapsed` },
      { label: "concurrency", value: r.concurrency_days == null ? "—" : `${r.concurrency_days}d`,
        hint: r.is_concurrent ? "counted once, not twice" : "events were independent" },
      { label: "finish moves", value: r.impacted_finish ?? "—", hint: `from ${r.unimpacted_finish}` },
      { label: "method", value: r.mip?.split(" ").slice(2, 4).join(" ") ?? "—",
        hint: r.baseline ? `vs ${r.baseline.name}` : "" },
    ] : []);
    if (!r.available) {
      if (r.missing_from_as_built?.length) {
        const m = document.createElement("div");
        m.className = "meta"; m.style.marginTop = "4px";
        m.textContent = `not in the as-built network: ${r.missing_from_as_built.join(", ")}`;
        mdOut.appendChild(m);
      }
      return;
    }
    const per = document.createElement("div");
    per.className = "meta"; per.style.cssText = "margin-top:4px;line-height:1.5";
    per.textContent = r.per_event.map((e) => `${e.impacts}: ${e.days}d`).join("  ·  ")
      + `  —  individually ${r.sum_of_individual_days}d, together ${r.total_days}d`;
    mdOut.appendChild(per);
    const src = document.createElement("div");
    src.className = "meta"; src.style.cssText = "margin-top:2px;font-size:10.5px";
    src.textContent = `Durations are ${r.days_source === "caller" ? "yours, not derived" : r.days_source}`
      + " — detection records that an event happened, never what it cost."
      + (r.rejected_events.length ? ` Not used: ${r.rejected_events.join("; ")}` : "");
    mdOut.appendChild(src);
  };
  const mdRow = document.createElement("div");
  mdRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
  mdRow.append(evIn,
    runner(mdOut, "▶ Impact the baseline", async () => {
      showModelled(await api.scheduleImpacted(pid, parseEvents()));
    }),
    runner(mdOut, "▶ Collapse the as-built", async () => {
      showModelled(await api.scheduleCollapsed(pid, parseEvents()));
    }));
  mdc.appendChild(mdRow); mdc.appendChild(mdOut); wrap.appendChild(mdc);

  // ── Delay attribution ────────────────────────────────────────────────────────────────────────
  const cc = card("Delay attribution — why the finish moved",
    "Not variance. The baseline is re-scheduled through the CPM engine and the finish move is "
    + "apportioned across duration growth, added logic, lag, constraints and progress — summing to "
    + "the move exactly, because parts that do not sum to the whole are not evidence.");
  const cOut = document.createElement("div");
  cc.appendChild(runner(cOut, "▶ Attribute the slip", async () => {
    const r = await api.scheduleCompare(pid);
    render(cOut, r, r.available ? [
      { label: "finish move", value: r.finish_move_days === null ? "—" : `${r.finish_move_days}d`,
        hint: r.finish_move_working_days == null ? ""
          : `${r.finish_move_working_days} working days` },
      { label: "vs baseline", value: r.baseline?.name ?? "—",
        hint: r.baseline ? `captured ${r.baseline.captured_at}` : "" },
      { label: "changed", value: `${r.changed_count ?? "—"}`,
        hint: `of ${r.activity_count ?? "—"} activities` },
      { label: "logic changes", value: `${r.link_changes ?? "—"}`,
        hint: r.criticality_gained.length ? `${r.criticality_gained.length} newly critical` : "" },
    ] : []);
    if (!r.available || !r.driving_path) return;
    const d = r.driving_path;
    const t = document.createElement("div");
    t.className = "meta"; t.style.cssText = "margin-top:4px;line-height:1.5";
    t.textContent = d.attribution
      .map((c) => `${c.days}d ${c.cause.replace(/_/g, " ")}`
        + (c.activity_id ? ` (${c.activity_id})` : "")).join("  ·  ");
    cOut.appendChild(t);
    // The residual is usually arithmetic, not a mystery: the engine's contributions are working days
    // and its total is calendar days. Saying so beats letting a planner hunt for the missing four.
    const gap = r.calendar_vs_working_gap_days ?? 0;
    if (gap) {
      const n = document.createElement("div");
      n.className = "meta"; n.style.cssText = "margin-top:2px;font-size:10.5px";
      n.textContent = `${gap}d of any "unexplained" residual is weekend — the contributions above `
        + "are working days, the total is calendar days.";
      cOut.appendChild(n);
    }
    if (!d.attribution_sums) {
      const w = document.createElement("div");
      w.className = "meta"; w.style.cssText = "margin-top:2px;color:var(--bad,#c0392b)";
      w.textContent = "the contributions do not sum to the finish move — do not rely on this";
      cOut.appendChild(w);
    }
  }));
  cc.appendChild(cOut); wrap.appendChild(cc);

  // ── Levelling ────────────────────────────────────────────────────────────────────────────────
  const lc = card("Resource levelling",
    "Deterministic: the same input always gives the same answer, so a planner can follow the "
    + "placements by hand and defend them. Advisory — nothing is written.");
  const capIn = document.createElement("input");
  capIn.type = "text"; capIn.placeholder = 'crew caps, e.g. Carpentry=8, Electrical=4';
  capIn.className = "tool-btn";
  capIn.style.cssText = "min-width:260px;text-align:left;cursor:text";
  const horizon = document.createElement("select");
  horizon.className = "tool-btn";
  const HORIZONS: ReadonlyArray<readonly [string, string]> = [
    ["within_float", "keep the finish"], ["extend_finish", "allow a later finish"]];
  for (const [v, t] of HORIZONS) {
    const o = document.createElement("option"); o.value = v; o.textContent = t; horizon.appendChild(o);
  }
  const lOut = document.createElement("div");
  const lRow = document.createElement("div");
  lRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
  lRow.append(capIn, horizon, runner(lOut, "▶ Level", async () => {
    // `Trade=8, Other=4` -> {Trade: 8, Other: 4}. Parsed here rather than server-side because a
    // malformed cap should be a visible client error, not a silent empty object the API refuses.
    const caps: Record<string, number> = {};
    for (const part of capIn.value.split(",")) {
      const [k, v] = part.split("=");
      const n = Number((v ?? "").trim());
      if (k?.trim() && Number.isFinite(n) && n > 0) caps[k.trim()] = n;
    }
    const r = await api.scheduleLevel(pid, caps,
      horizon.value as "within_float" | "extend_finish");
    render(lOut, r, r.available ? [
      { label: "moves", value: `${r.move_count}` },
      { label: "unresolved", value: `${r.unresolved_count}`,
        hint: r.horizon === "within_float" ? "the horizon would not allow a fix" : "" },
      { label: "finish moves", value: `${r.finish_moved_days}d` },
    ] : []);
  }));
  lc.append(lRow, lOut); wrap.appendChild(lc);

  return wrap;
}
