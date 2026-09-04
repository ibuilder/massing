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
import { usd } from "../../ui/charts";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";
import { programmeBars } from "./programmeGantt";

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

  // -- Compression ------------------------------------------------------------------------------
  const cc2 = card("Compression \u2014 what an earlier finish costs",
    "Not the acceleration advisory, which reports a fixed fraction of each activity's duration and "
    + "never re-schedules. This re-schedules after every day bought, so the days are what the "
    + "PROJECT finish moved. Costs are required \u2014 there is no default for how far work compresses.");
  const tgtIn = document.createElement("input");
  tgtIn.type = "number"; tgtIn.min = "1"; tgtIn.value = "10"; tgtIn.className = "tool-btn";
  tgtIn.style.cssText = "width:78px;text-align:left;cursor:text";
  tgtIn.title = "days to try to recover";
  const cstIn = document.createElement("input");
  cstIn.type = "text"; cstIn.className = "tool-btn";
  cstIn.placeholder = "costs, e.g. A20=1200/10, A30=800/5";
  cstIn.style.cssText = "min-width:250px;text-align:left;cursor:text";
  cstIn.title = "activity = cost per day / max days";
  const cOut2 = document.createElement("div");
  const cRow = document.createElement("div");
  cRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
  cRow.append(tgtIn, cstIn, runner(cOut2, "\u25b6 Price the date", async () => {
    // `A20=1200/10` -> {activity_id:"A20", cost_per_day:1200, max_days:10}. Parsed here so a
    // malformed entry is a visible client error rather than a silent empty list on the server.
    const costs: { activity_id: string; cost_per_day: number; max_days: number }[] = [];
    for (const part of cstIn.value.split(",")) {
      const [k, v] = part.split("=");
      const [rate, cap] = (v ?? "").split("/");
      const r2 = Number((rate ?? "").trim()), m = Number((cap ?? "").trim());
      if (k?.trim() && Number.isFinite(r2) && Number.isFinite(m) && m > 0) {
        costs.push({ activity_id: k.trim(), cost_per_day: r2, max_days: m });
      }
    }
    const r = await api.scheduleCompress(pid, { target_days: Number(tgtIn.value) || 0, costs });
    render(cOut2, r, r.available ? [
      { label: "days bought", value: r.days_available == null ? "\u2014" : `${r.days_available}d`,
        hint: r.meets_target ? "target met" : `of ${r.target_days}d asked` },
      { label: "cost", value: r.total_cost == null ? "\u2014" : usd(r.total_cost) },
      { label: "new finish", value: r.best_finish ?? "\u2014", hint: `from ${r.finish_before}` },
      { label: "not eligible", value: `${r.activities_without_costs ?? "\u2014"}`,
        hint: "activities with no cost entry" },
    ] : []);
    if (!r.available) return;
    const t = document.createElement("div");
    t.className = "meta"; t.style.cssText = "margin-top:4px;line-height:1.5";
    t.textContent = r.options.map((o) => `${o.activity_id}: ${o.days_saved}d`
      + (o.cost_per_day_saved == null ? "" : ` @ ${usd(o.cost_per_day_saved)}/d`)).join("  \u00b7  ")
      + (r.rejected_costs.length ? `  \u2014  not used: ${r.rejected_costs.join("; ")}` : "");
    cOut2.appendChild(t);
  }));
  cc2.appendChild(cRow); cc2.appendChild(cOut2); wrap.appendChild(cc2);

  // -- Weather allowance ------------------------------------------------------------------------
  const wac = card("Weather allowance \u2014 the lost days already in the programme",
    "Usually padded into durations, where a five-day pour becomes seven and nobody can say which "
    + "two days were weather. Modelled here as non-working days. Nothing is invented: the days per "
    + "month come from the contract or a met-office table.");
  const wIn = document.createElement("input");
  wIn.type = "text"; wIn.className = "tool-btn";
  wIn.placeholder = "days per month, e.g. jan=4, feb=3, mar=2";
  wIn.style.cssText = "min-width:250px;text-align:left;cursor:text";
  const waOut = document.createElement("div");
  const waRow = document.createElement("div");
  waRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
  waRow.append(wIn, runner(waOut, "\u25b6 Model the allowance", async () => {
    const days_by_month: Record<string, number> = {};
    for (const part of wIn.value.split(",")) {
      const [k, v] = part.split("=");
      const n = Number((v ?? "").trim());
      if (k?.trim() && Number.isFinite(n)) days_by_month[k.trim()] = n;
    }
    const r = await api.scheduleWeather(pid, { days_by_month });
    render(waOut, r, r.available ? [
      { label: "allowance", value: r.allowance_days == null ? "\u2014" : `${r.allowance_days}d`,
        hint: "non-working days added" },
      { label: "window", value: r.window_start ?? "\u2014", hint: `to ${r.window_finish}` },
      { label: "months", value: `${Object.keys(r.by_month).length}` },
    ] : []);
    if (!r.available) return;
    const t = document.createElement("div");
    t.className = "meta"; t.style.cssText = "margin-top:4px;line-height:1.5";
    // The days themselves, because an allowance is argued with.
    t.textContent = r.days.join("  \u00b7  ")
      + (r.rejected_months.length ? `  \u2014  ignored: ${r.rejected_months.join("; ")}` : "");
    waOut.appendChild(t);
    const d = document.createElement("div");
    d.className = "meta"; d.style.cssText = "margin-top:2px;font-size:10.5px";
    d.textContent = r.distribution ?? "";
    waOut.appendChild(d);
  }));
  wac.appendChild(waRow); wac.appendChild(waOut); wrap.appendChild(wac);

  // -- Portfolio --------------------------------------------------------------------------------
  const pfc = card("Programme \u2014 several projects, scheduled together",
    "A slip in enabling works reaches fit-out only if the two are scheduled in one pass. Doing them "
    + "in sequence propagates a delay only in whichever order they were listed. Membership is "
    + "checked on every project \u2014 a 403 means you are not a member of one of them.");
  const pfIn = document.createElement("input");
  pfIn.type = "text"; pfIn.className = "tool-btn";
  pfIn.placeholder = "other project ids, comma separated";
  pfIn.style.cssText = "min-width:250px;text-align:left;cursor:text";
  const pfOut = document.createElement("div");
  const pfRow = document.createElement("div");
  pfRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
  pfRow.append(pfIn, runner(pfOut, "\u25b6 Schedule the programme", async () => {
    const ids = pfIn.value.split(",").map((x) => x.trim()).filter(Boolean);
    const r = await api.schedulePortfolio(pid, { project_ids: ids });
    render(pfOut, r, r.available ? [
      { label: "programme finish", value: r.programme_finish ?? "\u2014" },
      { label: "projects", value: `${r.project_count ?? "\u2014"}` },
      { label: "external links", value: `${r.external_link_count ?? "\u2014"}`,
        hint: "commitments between parties" },
    ] : []);
    if (!r.available) return;
    const t = document.createElement("div");
    t.className = "meta"; t.style.cssText = "margin-top:4px;line-height:1.5";
    t.textContent = r.projects.map((p) => `${p.name} (${p.activities})`).join("  \u00b7  ")
      + (r.rejected_links.length ? `  \u2014  ignored: ${r.rejected_links.join("; ")}` : "");
    pfOut.appendChild(t);

    // CROSS-PROJECT GANTT — bars from the MERGED pass, not each project's standalone CPM. A project
    // can look comfortable alone and be critical to the programme; a bar drawn from its own run
    // would show the comfortable answer. `programmeBars` holds the geometry and the rule that a
    // half-dated project gets no bar; this only paints what it returns.
    const g = programmeBars(r);
    if (g.span) {
      const gw = document.createElement("div");
      gw.style.cssText = "margin-top:8px";
      const head = document.createElement("div");
      head.className = "meta";
      head.textContent = `Programme ${g.span.start} \u2192 ${g.span.finish} \u00b7 ${g.span.days} days`;
      gw.appendChild(head);
      for (const b of g.bars) {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;align-items:center;gap:8px;margin:3px 0";
        const label = document.createElement("div");
        label.style.cssText = "flex:0 0 150px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
        label.textContent = b.name;
        label.title = `${b.name} \u00b7 ${b.start} \u2192 ${b.finish} \u00b7 ${b.days} days`
          + `${b.linked ? " \u00b7 named by an external link" : ""}`;
        const track = document.createElement("div");
        track.style.cssText = "flex:1;position:relative;height:16px;background:var(--panel2);border-radius:3px";
        const bar = document.createElement("div");
        // Driving = finishes on the programme finish, so the whole span waits on it. Linked = named
        // by a cross-project commitment. Both are facts from the run, not a status guess.
        const col = b.driving ? "var(--status-crit)" : b.linked ? "var(--accent)" : "var(--status-good)";
        bar.style.cssText = `position:absolute;left:${b.left}%;width:${b.width}%;top:2px;bottom:2px;`
          + `background:${col};border-radius:2px`;
        track.appendChild(bar);
        const days = document.createElement("div");
        days.className = "meta";
        days.style.cssText = "flex:0 0 62px;text-align:right;font-variant-numeric:tabular-nums";
        days.textContent = `${b.days}d${b.driving ? " \u25c0" : ""}`;
        row.append(label, track, days);
        gw.appendChild(row);
      }
      const key = document.createElement("div");
      key.className = "meta"; key.style.marginTop = "4px";
      key.textContent = "\u25c0 drives the programme finish \u00b7 blue = named by an external link "
        + "(a commitment between parties) \u00b7 bars come from the merged pass, not each project's "
        + "own schedule.";
      gw.appendChild(key);
      pfOut.appendChild(gw);
    }
    if (g.unplotted.length) {
      // Named, never silently dropped and never drawn with an invented end date.
      const u = document.createElement("div");
      u.className = "meta"; u.style.cssText = "margin-top:4px;color:var(--status-warn)";
      u.textContent = "Not plotted \u2014 " + g.unplotted.map((x) => `${x.name} (${x.reason})`).join("; ");
      pfOut.appendChild(u);
    }
  }));
  pfc.appendChild(pfRow); pfc.appendChild(pfOut); wrap.appendChild(pfc);

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
