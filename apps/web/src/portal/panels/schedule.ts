import type { ModuleDef } from "../../api/client";
import { groupedBar } from "../../ui/charts";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import { confirmModal } from "../../ui/modal";
import type { PanelContext } from "../panelContext";

/**
 * Unified GC schedule visuals — one relational schedule drives all of it: the Last Planner pull-plan
 * board (make-ready, PPC, live collaboration + presence), lookahead, milestones, CPM critical path,
 * earned value, baseline/variance, and the Gantt + Line-of-Balance SVGs. Extracted from portal.ts.
 */
// M3 live-board resources of the CURRENT render. The panel has no dispose hook, so each re-render
// closes its predecessor's SSE stream + presence timer synchronously — rapid Schedule↔Home toggling
// must replace the live subscription, never stack them (the 20s heartbeat probe alone left a window).
let livePull: { close(): void } | null = null;
let livePullTimer = 0;

export async function renderScheduleViews(ctx: PanelContext, m: ModuleDef) {
  const pid = ctx.host.projectId()!;
  livePull?.close(); livePull = null;
  if (livePullTimer) { window.clearInterval(livePullTimer); livePullTimer = 0; }
  ctx.root.innerHTML = "";
  ctx.root.appendChild(ctx.bar("Schedule", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const intro = document.createElement("div"); intro.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:2px 0 8px";
  const listBtn = document.createElement("button"); listBtn.className = "tool-btn"; listBtn.textContent = "✎ Activities (list)";
  listBtn.title = "Open the activity list to add / edit / import tasks";
  listBtn.onclick = () => { ctx.activeKey = "schedule_activity"; void ctx.openModule(m); ctx.buildNav(); };
  // SURF-1: P6/MSP import + predictive alerts + earned-schedule were backed but had no surface.
  const xerLabel = document.createElement("label"); xerLabel.className = "tool-btn";
  xerLabel.style.cssText = "cursor:pointer"; xerLabel.textContent = "⇪ Import P6/MSP (.xer/.xml)";
  xerLabel.title = "Import a Primavera P6 (.xer) or MS-Project (.xml/PMXML) export — tasks become editable activities with real calendar dates";
  const xerInput = document.createElement("input"); xerInput.type = "file"; xerInput.accept = ".xer,.xml"; xerInput.style.display = "none";
  xerLabel.appendChild(xerInput);
  xerInput.onchange = async () => {
    const f = xerInput.files?.[0]; if (!f) return;
    xerLabel.textContent = "⏳ Importing…";
    try {
      const r = await ctx.host.api.importXer(pid, f);
      toast(`Imported ${r.count} activities${r.start ? ` (${r.start} → ${r.finish})` : ""}`, "success");
      void renderScheduleViews(ctx, m);   // re-render the CPM/Gantt off the imported schedule
    } catch (e) { toast(`P6/MSP import failed: ${(e as Error).message}`, "error"); xerLabel.textContent = "⇪ Import P6/MSP (.xer/.xml)"; }
    finally { xerInput.value = ""; }
  };
  const alertBtn = document.createElement("button"); alertBtn.className = "tool-btn"; alertBtn.textContent = "🔔 Alerts";
  alertBtn.title = "Predictive schedule alerts: overdue, late-start, at-risk predecessor, SPI, procurement";
  const esBtn = document.createElement("button"); esBtn.className = "tool-btn"; esBtn.textContent = "⏱ Earned schedule";
  esBtn.title = "Earned Schedule (time-based EVM): ES, SV(t), SPI(t), forecast finish";
  const baseBtn = document.createElement("button"); baseBtn.className = "tool-btn"; baseBtn.textContent = "📌 Baselines";
  baseBtn.title = "Named schedule baselines: capture GMP/Recovery/etc. and measure slip against any of them";
  // SCHED-P6 export — the live schedule (imported + hand-entered, with GC edits) back out to the
  // scheduler's tool, keyed by the P6 activity code so their re-import matches by code (round-trip).
  const xerOut = document.createElement("button"); xerOut.className = "tool-btn"; xerOut.textContent = "⤓ Export .xer";
  xerOut.title = "Export the live schedule as a Primavera P6 .xer (round-trips: re-import matches by activity code)";
  const mspOut = document.createElement("button"); mspOut.className = "tool-btn"; mspOut.textContent = "⤓ Export MSP .xml";
  mspOut.title = "Export the live schedule as MS-Project XML (MSPDI) for Microsoft Project";
  const doExport = (fmt: "xer" | "msp") => async () => {
    try { await ctx.host.api.exportSchedule(pid, fmt); toast(`Exported the schedule as ${fmt === "msp" ? "MS-Project XML" : "P6 .xer"}`, "success"); }
    catch (e) { toast(`Export failed: ${(e as Error).message}`, "error"); }
  };
  xerOut.onclick = doExport("xer"); mspOut.onclick = doExport("msp");
  const note = document.createElement("span"); note.className = "meta";
  note.innerHTML = "One relational schedule — these views + the 3D <b>4D sequence</b> (Model → ⏱ 4D) share the same activities.";
  intro.append(listBtn, xerLabel, xerOut, mspOut, alertBtn, esBtn, baseBtn, note);
  ctx.root.appendChild(intro);

  // a collapsible drawer the alerts / earned-schedule buttons fill on demand (kept out of the way)
  const interopDrawer = document.createElement("div"); interopDrawer.style.cssText = "display:none;margin:0 0 8px";
  ctx.root.appendChild(interopDrawer);
  const showDrawer = (html: string) => { interopDrawer.innerHTML = html; interopDrawer.style.display = ""; };
  alertBtn.onclick = async () => {
    showDrawer(`<div class="dash-card"><div class="meta">Collecting alerts…</div></div>`);
    try {
      const a = await ctx.host.api.scheduleAlerts(pid);
      const dot: Record<string, string> = { high: "⛔", medium: "⚠️", low: "•" };
      const rows = a.alerts.length
        ? a.alerts.map((al) => `<div class="meta" style="margin:2px 0">${dot[al.level] ?? "•"} <b>${esc(al.title)}</b> — ${esc(al.detail)}${al.ref ? ` <span style="opacity:.6">[${esc(al.ref)}]</span>` : ""}</div>`).join("")
        : `<div class="meta">🟢 No schedule alerts.</div>`;
      showDrawer(`<div class="dash-card"><div class="section-title">🔔 Schedule alerts · ${a.counts.high} high · ${a.counts.medium} medium · ${a.counts.low} low</div>${rows}</div>`);
    } catch (e) { showDrawer(`<div class="dash-card"><div class="meta">Alerts unavailable: ${esc((e as Error).message)}</div></div>`); }
  };
  esBtn.onclick = async () => {
    showDrawer(`<div class="dash-card"><div class="meta">Computing earned schedule…</div></div>`);
    try {
      const es = await ctx.host.api.earnedSchedule(pid);
      const spit = es.spi_t == null ? "—" : es.spi_t.toFixed(2);
      const col = es.spi_t == null ? "var(--muted)" : es.spi_t < 1 ? "var(--status-crit)" : "var(--status-good)";
      showDrawer(`<div class="dash-card"><div class="section-title">⏱ Earned Schedule</div>`
        + `<div class="meta">SPI(t) <b style="color:${col}">${spit}</b>`
        + ` · SV(t) ${es.sv_t_periods.toFixed(1)} periods`
        + (es.forecast_finish ? ` · forecast finish <b>${esc(es.forecast_finish)}</b>` : "")
        + (es.note ? `<br><span style="opacity:.7">${esc(es.note)}</span>` : "") + `</div></div>`);
    } catch (e) { showDrawer(`<div class="dash-card"><div class="meta">Earned schedule unavailable: ${esc((e as Error).message)}</div></div>`); }
  };
  const drawBaselines = async () => {
    showDrawer(`<div class="dash-card"><div class="meta">Loading baselines…</div></div>`);
    let list;
    try { list = (await ctx.host.api.scheduleBaselines(pid)).baselines; }
    catch (e) { showDrawer(`<div class="dash-card"><div class="meta">Baselines unavailable: ${esc((e as Error).message)}</div></div>`); return; }
    const card = document.createElement("div"); card.className = "dash-card";
    card.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "📌 Named baselines" }));
    const form = document.createElement("div"); form.style.cssText = "display:flex;gap:6px;margin:4px 0;flex-wrap:wrap";
    const nameI = document.createElement("input"); nameI.className = "portal-filter"; nameI.placeholder = "name (e.g. GMP)"; nameI.style.cssText = "flex:1 1 140px;font-size:12px";
    const cap = document.createElement("button"); cap.className = "mini-btn on"; cap.textContent = "＋ Capture now";
    cap.onclick = async () => { try { await ctx.host.api.captureBaseline(pid, nameI.value.trim()); toast("baseline captured", "success"); void drawBaselines(); } catch (e) { toast((e as Error).message, "error"); } };
    form.append(nameI, cap); card.appendChild(form);
    if (!list.length) card.appendChild(Object.assign(document.createElement("div"), { className: "meta", textContent: "No baselines yet — capture one to track slip against it." }));
    const varBox = document.createElement("div"); varBox.className = "meta"; varBox.style.marginTop = "4px";
    for (const b of list) {
      const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;margin:2px 0";
      const link = document.createElement("a"); link.href = "#";
      link.innerHTML = `<b>${esc(b.name)}</b> <span style="opacity:.6">${esc(b.captured_at)} · ${b.count} acts</span>`;
      link.onclick = async (e) => {
        e.preventDefault();
        try { const v = await ctx.host.api.baselineVariance(pid, b.id); const s = v.summary;
          varBox.innerHTML = `vs <b>${esc(b.name)}</b>: ${s.slipped} slipped · ${s.improved} improved · ${s.on_baseline} on-baseline · ${s.added} added · ${s.removed} removed · max slip <b>${s.max_slip_days}d</b>`;
        } catch (err) { varBox.textContent = (err as Error).message; }
      };
      const del = document.createElement("button"); del.className = "selset-del"; del.textContent = "✕";
      del.onclick = async () => { try { await ctx.host.api.deleteBaseline(pid, b.id); void drawBaselines(); } catch (e) { toast((e as Error).message, "error"); } };
      row.append(link, del); card.appendChild(row);
    }
    card.appendChild(varBox);
    interopDrawer.replaceChildren(card); interopDrawer.style.display = "";
  };
  baseBtn.onclick = () => void drawBaselines();

  // --- Pull planning (Last Planner phase board) — trade swimlanes × weeks, make-ready, PPC -------
  const ppCard = document.createElement("div"); ppCard.className = "dash-card"; ppCard.style.marginBottom = "10px";
  const ppHead = document.createElement("div"); ppHead.className = "section-title";
  ppHead.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap";
  ppHead.append(Object.assign(document.createElement("span"), { textContent: "🧲 Pull Planning (Last Planner)" }));
  const ppRight = document.createElement("div"); ppRight.style.cssText = "display:flex;gap:6px;align-items:center";
  const msSel = document.createElement("select"); msSel.className = "sb-sel";
  const editBtn = document.createElement("button"); editBtn.className = "tool-btn"; editBtn.textContent = "✎ Sticky notes";
  editBtn.title = "Add / edit pull-plan tasks (every trade edits its own)";
  editBtn.onclick = () => { const pm = ctx.mods.find((x) => x.key === "pull_plan_task"); if (pm) { ctx.activeKey = "pull_plan_task"; void ctx.openModule(pm); ctx.buildNav(); } };
  const pdfBtn = document.createElement("a"); pdfBtn.className = "tool-btn"; pdfBtn.textContent = "⬇ PDF"; pdfBtn.target = "_blank"; pdfBtn.rel = "noopener";
  const anBtn = document.createElement("button"); anBtn.className = "tool-btn"; anBtn.textContent = "📊 Analytics";
  anBtn.title = "Reliability metrics: Tasks-Made-Ready, perfect hand-offs, PPC trend, variance reasons";
  ppRight.append(msSel, editBtn, anBtn, pdfBtn); ppHead.append(ppRight); ppCard.appendChild(ppHead);
  const ppBody = document.createElement("div"); ppBody.innerHTML = `<div class="meta">loading…</div>`; ppCard.appendChild(ppBody);
  const ppAnalytics = document.createElement("div"); ppAnalytics.style.display = "none"; ppCard.appendChild(ppAnalytics);
  ctx.root.appendChild(ppCard);

  // --- RISK-BOARD: one register unifying every computed risk signal (deep-linked) -----------------
  const rbCard = document.createElement("div"); rbCard.className = "dash-card"; rbCard.style.marginBottom = "10px";
  rbCard.innerHTML = `<div class="section-title">🚨 Risk board</div>`;
  const rbBody = document.createElement("div"); rbBody.innerHTML = `<div class="meta">Collecting signals…</div>`;
  rbCard.appendChild(rbBody); ctx.root.appendChild(rbCard);
  void ctx.host.api.riskBoard(pid).then((rb) => {
    const bandCol = rb.band === "critical" ? "var(--status-crit)" : rb.band === "elevated" ? "var(--status-warn)" : "var(--status-good)";
    if (!rb.count) { rbBody.innerHTML = `<div class="meta">🟢 Clear — no computed risk signals right now.</div>`; return; }
    const icon: Record<string, string> = { high: "⛔", medium: "⚠️", low: "•" };
    rbBody.innerHTML = `<div class="meta" style="margin-bottom:4px">Band <b style="color:${bandCol}">${esc(rb.band)}</b>`
      + ` · ${rb.by_severity.high} high · ${rb.by_severity.medium} medium · ${rb.by_severity.low} low</div>`;
    for (const it of rb.items.slice(0, 10)) {
      const row = document.createElement("div"); row.className = "meta"; row.style.margin = "2px 0";
      row.innerHTML = `${icon[it.severity] ?? "•"} <b>${esc(it.title)}</b> — ${esc(it.detail)}`
        + ` <span style="opacity:.6">[${esc(it.source)}]</span>`;
      rbBody.appendChild(row);
    }
    if (rb.count > 10) rbBody.insertAdjacentHTML("beforeend", `<div class="meta">…and ${rb.count - 10} more.</div>`);
  }).catch(() => { rbBody.innerHTML = `<div class="meta">Risk board unavailable.</div>`; });

  // --- Schedule risk (Monte Carlo over the CPM network): P50/P80, buffer, delay drivers -----------
  const riskCard = document.createElement("div"); riskCard.className = "dash-card"; riskCard.style.marginBottom = "10px";
  riskCard.innerHTML = `<div class="section-title">🎲 Schedule risk (Monte Carlo)</div>`;
  const riskBody = document.createElement("div"); riskBody.innerHTML = `<div class="meta">simulating…</div>`;
  riskCard.appendChild(riskBody); ctx.root.appendChild(riskCard);
  ctx.host.api.scheduleRisk(pid).then((r) => {
    if (r.message || !r.p80_days) { riskBody.innerHTML = `<div class="meta">${r.message || "Add activities with durations + predecessors to simulate."}</div>`; return; }
    const finish = (d?: string) => (d ? ` <span class="meta">(${d})</span>` : "");
    riskBody.innerHTML =
      `<div style="display:flex;gap:14px;flex-wrap:wrap;margin:2px 0 4px">`
      + `<span>CPM <b>${r.deterministic_days}d</b>${finish(r.deterministic_finish)}</span>`
      + `<span>P50 <b>${r.p50_days}d</b>${finish(r.p50_finish)}</span>`
      + `<span>P80 <b style="color:var(--status-warn)">${r.p80_days}d</b>${finish(r.p80_finish)}</span>`
      + `<span>on-time odds <b>${r.on_time_probability_pct}%</b></span>`
      + `</div>`
      + `<div class="meta">A reliable commitment needs a <b>${r.buffer_p80_days}d</b> buffer on the CPM date`
      + (r.ppc_calibration_pct != null ? ` · tail calibrated by your PPC (${Math.round(r.ppc_calibration_pct)}%)` : "")
      + ` · ${r.iterations} iterations</div>`;
    if (r.delay_drivers?.length) {
      const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Delay driver</th>`
        + `<th scope="col">On critical path</th><th scope="col">Mean slip</th></tr></thead><tbody>`
        + r.delay_drivers.slice(0, 5).map((d) => `<tr><td>${d.name || d.ref || ""}</td>`
          + `<td style="text-align:center">${d.criticality_pct}%</td>`
          + `<td style="text-align:center">${d.mean_slip_days}d</td></tr>`).join("") + `</tbody>`;
      riskBody.append(t);
    }
  }).catch((e) => { riskBody.innerHTML = `<div class="meta">risk simulation failed: ${(e as Error).message}</div>`; });

  // --- Schedule acceleration (advisory): crash + fast-track levers off the critical path ----------
  const accCard = document.createElement("div"); accCard.className = "dash-card"; accCard.style.marginBottom = "10px";
  accCard.innerHTML = `<div class="section-title">🚀 Acceleration levers (advisory)</div>`;
  const accBody = document.createElement("div"); accBody.innerHTML = `<div class="meta">analyzing the critical path…</div>`;
  accCard.appendChild(accBody); ctx.root.appendChild(accCard);
  ctx.host.api.scheduleOptimize(pid).then((r) => {
    if (r.has_cycle || !r.critical_count) { accBody.innerHTML = `<div class="meta">${r.headline || "Add a schedule with predecessors to find acceleration levers."}</div>`; return; }
    accBody.innerHTML = `<div>${r.headline} <span class="meta">· best single lever saves ~<b>${r.best_single_lever_days}d</b></span></div>`;
    const levers = [
      ...r.crash.slice(0, 3).map((x) => ({ kind: "crash", name: x.name, ref: x.ref, days: x.days_potential, detail: x.detail })),
      ...r.fast_track.slice(0, 3).map((x) => ({ kind: "fast-track", name: x.name, ref: x.ref, days: x.days_potential, detail: x.detail })),
    ];
    if (levers.length) {
      const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Lever</th><th scope="col" style="text-align:left">Activity</th>`
        + `<th scope="col">Saves</th></tr></thead><tbody>`
        + levers.map((l) => `<tr><td><span class="meta">${l.kind}</span></td>`
          + `<td>${l.name || l.ref || ""} <span class="meta">— ${l.detail}</span></td>`
          + `<td style="text-align:center;color:var(--status-good)">${l.days}d</td></tr>`).join("") + `</tbody>`;
      accBody.append(t);
    }
    if (r.ai_enabled && r.narrative) {
      const n = document.createElement("div"); n.className = "meta"; n.style.marginTop = "4px"; n.textContent = r.narrative;
      accBody.append(n);
    }
    accBody.insertAdjacentHTML("beforeend", `<div class="meta" style="margin-top:3px">Advisory only — the platform never rewrites your schedule.</div>`);
  }).catch((e) => { accBody.innerHTML = `<div class="meta">acceleration analysis failed: ${(e as Error).message}</div>`; });
  const ppState = (s: string) => s === "done" ? "var(--status-good)" : s === "not_done" ? "var(--status-crit)"
    : s === "committed" ? "var(--accent)" : s === "made_ready" ? "var(--status-warn)" : "var(--muted)";
  const loadPull = (milestone: string) => {
    ppBody.innerHTML = `<div class="meta">loading…</div>`;
    pdfBtn.href = ctx.host.api.pullPlanPdfUrl(pid, milestone || undefined);
    void ctx.host.api.pullPlanBoard(pid, milestone || undefined).then((b) => {
      // milestone options (only rebuild once)
      if (!msSel.options.length) {
        msSel.innerHTML = `<option value="">All phases</option>`
          + b.milestones.map((m) => `<option value="${m.replace(/"/g, "&quot;")}">${m}</option>`).join("");
      }
      if (!b.total) { ppBody.innerHTML = `<div class="meta">No pull-plan tasks yet — click <b>✎ Sticky notes</b> to add them. Work backward from a milestone; each trade posts its tasks and hand-offs, and constraints are cleared to make work ready.</div>`; return; }
      ppBody.innerHTML = "";
      // summary chips
      const chips = document.createElement("div"); chips.className = "meta"; chips.style.marginBottom = "6px";
      chips.innerHTML = `Ready <b>${b.readiness.ready_pct ?? "—"}%</b> · PPC <b style="color:${b.commitment.ppc_pct != null && b.commitment.ppc_pct < 70 ? "var(--status-warn)" : "var(--status-good)"}">${b.commitment.ppc_pct ?? "—"}%</b> · `
        + `<b>${b.make_ready.constrained_tasks}</b> constrained task(s), ${b.make_ready.open_constraints} open constraint(s)`;
      ppBody.appendChild(chips);
      // matrix: trade rows × week columns
      const wrap = document.createElement("div"); wrap.style.cssText = "overflow-x:auto";
      const t = document.createElement("table"); t.className = "portal-table"; t.style.cssText = "font-size:11px;border-collapse:collapse";
      t.innerHTML = `<thead><tr><th style="text-align:left;position:sticky;left:0;background:var(--panel)">Trade</th>`
        + b.weeks.map((w) => `<th style="min-width:120px">${w}</th>`).join("") + `</tr></thead>`;
      const tb = document.createElement("tbody");
      for (const lane of b.swimlanes) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td style="text-align:left;font-weight:600;position:sticky;left:0;background:var(--panel)">${lane.trade}</td>`
          + b.weeks.map((w) => {
            const cell = lane.tasks.filter((x) => x.week === w);
            return `<td style="vertical-align:top">` + cell.map((x) =>
              `<div title="${(x.state + (x.constraints.length ? " · constraints: " + x.constraints.join(", ") : ""))}" `
              + `style="margin:2px 0;padding:2px 5px;border-radius:4px;border-left:3px solid ${ppState(x.state)};background:var(--hover)">`
              + `${x.constraints.length ? "🔒 " : ""}${esc(x.task)}</div>`).join("") + `</td>`;
          }).join("");
        tb.appendChild(tr);
      }
      t.appendChild(tb); wrap.appendChild(t); ppBody.appendChild(wrap);
      // make-ready log
      if (b.make_ready.by_constraint.length) {
        const mr = document.createElement("div"); mr.className = "meta"; mr.style.marginTop = "6px";
        mr.innerHTML = `<b>Make-ready</b> — ` + b.make_ready.by_constraint.map((x) => `${x.constraint}: ${x.count}`).join(" · ");
        ppBody.appendChild(mr);
      }
    }).catch((e) => { ppBody.innerHTML = `<div class="meta">Pull plan unavailable: ${esc((e as Error).message)}</div>`; });
  };
  // --- reliability analytics (M2): TMR, perfect-handoff %, PPC trend, variance Pareto, benchmark ---
  let anShown = false;
  const loadAnalytics = (milestone: string) => {
    ppAnalytics.innerHTML = `<div class="meta">loading analytics…</div>`;
    void ctx.host.api.pullPlanMetrics(pid, milestone || undefined).then(async (m) => {
      if (!m.total) { ppAnalytics.innerHTML = `<div class="meta">No pull-plan tasks yet.</div>`; return; }
      ppAnalytics.innerHTML = "";
      const chipColor = (v: number | null, good = 80) => v == null ? "var(--muted)" : v >= good ? "var(--status-good)" : v >= good - 20 ? "var(--status-warn)" : "var(--status-crit)";
      const chips = document.createElement("div"); chips.className = "meta"; chips.style.cssText = "margin:6px 0;display:flex;gap:14px;flex-wrap:wrap";
      chips.innerHTML = `<span>PPC <b style="color:${chipColor(m.ppc_pct)}">${m.ppc_pct ?? "—"}%</b> <span class="meta">(target ≥80%)</span></span>`
        + `<span>Tasks made ready <b style="color:${chipColor(m.tmr_pct)}">${m.tmr_pct ?? "—"}%</b></span>`
        + `<span>Perfect hand-offs <b style="color:${chipColor(m.perfect_handoff_pct)}">${m.perfect_handoff_pct ?? "—"}%</b> <span class="meta">(${m.clean_handoffs}/${m.handoffs})</span></span>`
        + `<span>Make-ready runway <b>${m.make_ready_runway_weeks}</b> wk</span>`;
      ppAnalytics.appendChild(chips);
      // PPC trend by week
      if (m.ppc_trend.length) {
        const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.margin = "6px 0";
        wrap.innerHTML = groupedBar(m.ppc_trend.map((r) => ({ label: r.week, bars: [{ name: "PPC", value: r.ppc_pct ?? 0 }] })),
          { title: "PPC trend by week (%)", fmt: (n) => `${Math.round(n)}%` });
        ppAnalytics.appendChild(wrap);
      }
      // variance Pareto
      if (m.variance_pareto.length) {
        const wrap = document.createElement("div"); wrap.className = "dash-card"; wrap.style.margin = "6px 0";
        wrap.innerHTML = groupedBar(m.variance_pareto.map((v) => ({ label: v.reason, bars: [{ name: "misses", value: v.count }] })),
          { title: "Why work misses (variance Pareto)", fmt: (n) => String(Math.round(n)) });
        ppAnalytics.appendChild(wrap);
      }
      // cross-project benchmark
      try {
        const bm = await ctx.host.api.benchmarksPullPlanning();
        if (bm.projects && bm.ppc) {
          const b = document.createElement("div"); b.className = "meta"; b.style.marginTop = "4px";
          b.innerHTML = `<b>Portfolio benchmark</b> (${bm.projects} project${bm.projects === 1 ? "" : "s"}) — `
            + `PPC median <b>${bm.ppc.median}%</b> (low ${bm.ppc.low} · high ${bm.ppc.high}) vs the ≥${bm.target_ppc ?? 80}% target`;
          ppAnalytics.appendChild(b);
        }
      } catch { /* benchmark optional */ }
    }).catch((e) => { ppAnalytics.innerHTML = `<div class="meta">Analytics unavailable: ${esc((e as Error).message)}</div>`; });
  };
  anBtn.onclick = () => {
    anShown = !anShown;
    ppAnalytics.style.display = anShown ? "" : "none";
    ppBody.style.display = anShown ? "none" : "";
    anBtn.classList.toggle("on", anShown);
    anBtn.textContent = anShown ? "🧲 Board" : "📊 Analytics";
    if (anShown) loadAnalytics(msSel.value);
  };
  msSel.onchange = () => { loadPull(msSel.value); if (anShown) loadAnalytics(msSel.value); };
  loadPull("");

  // --- M3: real-time collaboration — the board live-refreshes as any trade edits, and presence shows
  //     who else is on it. Reuses the SSE + presence infra; self-cleans when the view is replaced. ---
  const liveEl = document.createElement("span"); liveEl.className = "meta";
  liveEl.title = "Live — the board refreshes automatically as any trade edits its sticky notes";
  liveEl.style.cssText = "display:inline-flex;align-items:center;gap:4px;font-size:11px";
  liveEl.innerHTML = `<span style="width:8px;height:8px;border-radius:50%;background:var(--status-good);display:inline-block"></span>live`;
  ppRight.insertBefore(liveEl, msSel);
  let lastSig = "";
  const es = ctx.host.api.pullPlanStream(pid, (d) => {
    if (!document.body.contains(ppCard)) { es.close(); return; }   // view left → immediate teardown
    const sig = `${d.count}|${d.latest ?? ""}`;
    const first = lastSig === "";
    if (sig === lastSig) return;
    lastSig = sig;
    if (!first) { loadPull(msSel.value); if (anShown) loadAnalytics(msSel.value); }   // someone edited → refresh
  });
  livePull = es;
  const renderPeers = (active: { user: string; viewpoint: unknown }[]) => {
    const peers = active.filter((a) => a.viewpoint && (a.viewpoint as { board?: string }).board === "pull-plan");
    [...ppRight.querySelectorAll(".pp-peer")].forEach((n) => n.remove());
    for (const p of peers.slice(0, 6)) {
      const chip = document.createElement("span"); chip.className = "meta pp-peer";
      chip.style.cssText = "font-size:11px;padding:1px 6px;border-radius:10px;background:var(--hover)";
      chip.title = `${p.user} is viewing this board`; chip.textContent = `👤 ${p.user}`;
      ppRight.insertBefore(chip, liveEl);
    }
  };
  let hbTimer = 0;
  const heartbeat = () => {
    if (!document.body.contains(ppCard)) { es.close(); window.clearInterval(hbTimer); return; }   // view left → teardown
    void ctx.host.api.presence(pid, { board: "pull-plan" }).then((r) => renderPeers(r.active)).catch(() => { /* offline */ });
  };
  hbTimer = window.setInterval(heartbeat, 20000);
  livePullTimer = hbTimer;
  heartbeat();

  const statusColor = (s: string) =>
    s === "late" ? "var(--status-crit)" : s === "complete" || s === "met" ? "var(--status-good)"
      : s === "in_progress" || s === "due_soon" ? "var(--status-warn)" : "var(--muted)";

  // Lookahead (the field's short-interval plan) — 3 / 6 week toggle, grouped by week
  const laCard = document.createElement("div"); laCard.className = "dash-card"; laCard.style.marginBottom = "10px";
  const laHead = document.createElement("div"); laHead.className = "section-title";
  laHead.style.cssText = "display:flex;justify-content:space-between;align-items:center";
  laHead.append(Object.assign(document.createElement("span"), { textContent: "Lookahead" }));
  const laSel = document.createElement("select"); laSel.className = "sb-sel";
  for (const w of [3, 6]) { const o = document.createElement("option"); o.value = String(w); o.textContent = `${w} weeks`; laSel.appendChild(o); }
  laHead.appendChild(laSel); laCard.appendChild(laHead);
  const laBody = document.createElement("div"); laBody.innerHTML = `<div class="meta">loading…</div>`; laCard.appendChild(laBody);
  const loadLookahead = (weeks: number) => {
    laBody.innerHTML = `<div class="meta">loading…</div>`;
    void ctx.host.api.scheduleLookahead(pid, weeks).then((la) => {
      if (!la.count) { laBody.innerHTML = `<div class="meta">No activities in the next ${weeks} weeks.</div>`; return; }
      laBody.innerHTML = "";
      for (const wk of la.weeks_detail) {
        const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "margin-top:6px;font-weight:700"; h.textContent = wk.week;
        laBody.appendChild(h);
        for (const a of wk.activities) {
          const row = document.createElement("div"); row.className = "meta"; row.style.margin = "1px 0";
          row.innerHTML = `<span style="color:${statusColor(a.status)}">●</span> ${a.name}`
            + `${a.trade ? ` · <span class="meta">${a.trade}</span>` : ""}`
            + ` · ${a.percent}% · <span class="meta">${a.status.replace("_", " ")}</span>`;
          laBody.appendChild(row);
        }
      }
    }).catch(() => { laBody.innerHTML = `<div class="meta">Lookahead unavailable.</div>`; });
  };
  laSel.onchange = () => loadLookahead(+laSel.value);
  ctx.root.appendChild(laCard); loadLookahead(3);

  // Milestone schedule — key dates with status
  const msCard = document.createElement("div"); msCard.className = "dash-card"; msCard.style.marginBottom = "10px";
  msCard.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Milestones" }));
  const msBody = document.createElement("div"); msBody.innerHTML = `<div class="meta">loading…</div>`; msCard.appendChild(msBody);
  void ctx.host.api.scheduleMilestones(pid).then((ms) => {
    if (!ms.count) { msBody.innerHTML = `<div class="meta">No milestones — set an activity’s Type to “Milestone”.</div>`; return; }
    const s = ms.summary;
    msBody.innerHTML = `<div class="meta" style="margin-bottom:4px">`
      + `<b style="color:var(--status-crit)">${s.late || 0}</b> late · <b style="color:var(--status-warn)">${s.due_soon || 0}</b> due soon · `
      + `${s.upcoming || 0} upcoming · <b style="color:var(--status-good)">${s.met || 0}</b> met</div>`;
    for (const mi of ms.milestones) {
      const row = document.createElement("div"); row.className = "meta"; row.style.margin = "1px 0";
      const out = mi.days_out == null ? "" : mi.days_out < 0 ? ` (${-mi.days_out}d ago)` : ` (in ${mi.days_out}d)`;
      row.innerHTML = `<span style="color:${statusColor(mi.status)}">◆</span> ${mi.name}`
        + ` · <span class="meta">${mi.date ?? "no date"}${out}</span> · ${mi.status.replace("_", " ")}`;
      msBody.appendChild(row);
    }
  }).catch(() => { msBody.innerHTML = `<div class="meta">Milestones unavailable.</div>`; });
  ctx.root.appendChild(msCard);

  // CPM summary line (critical path + float)
  const cpmBox = document.createElement("div"); cpmBox.className = "meta"; cpmBox.style.margin = "0 0 8px";
  cpmBox.textContent = "Computing critical path…"; ctx.root.appendChild(cpmBox);
  // EST-1: seed/refresh trade durations straight from the model's measured QTO takeoff
  const estBtn = document.createElement("button"); estBtn.className = "file-btn";
  estBtn.textContent = "⚙ Durations from model (QTO)"; estBtn.style.margin = "0 0 8px";
  estBtn.title = "Run the QTO-driven labour estimate and upsert one EST activity per trade "
    + "(crew-day durations, chained FS) into this schedule — re-running refreshes, never duplicates.";
  estBtn.onclick = async () => {
    estBtn.disabled = true; const prev = estBtn.textContent; estBtn.textContent = "Estimating…";
    try {
      const r = await ctx.host.api.scheduleFromEstimate(pid);
      toast(`${r.activities} trade activit${r.activities === 1 ? "y" : "ies"} upserted — `
        + `CPM ${r.cpm_project_duration}d`, "success");
      const c = await ctx.host.api.scheduleCpm(pid);       // refresh the CPM line in place
      cpmBox.innerHTML = `<b>CPM</b>: project ${c.project_duration}d · ${c.critical_count}/${c.activity_count} on the `
        + `<span style="color:var(--status-crit)">critical path</span>`;
    } catch (e) { toast((e as Error).message, "error"); }
    estBtn.disabled = false; estBtn.textContent = prev;
  };
  ctx.root.appendChild(estBtn);
  void ctx.host.api.scheduleCpm(pid).then((c) => {
    if (!c.activity_count) { cpmBox.textContent = "CPM: no activities with durations yet."; return; }
    const cp = c.critical_path.slice(0, 12).join(" → ") || "—";
    cpmBox.innerHTML = `<b>CPM</b>: project ${c.project_duration}d · ${c.critical_count}/${c.activity_count} on the `
      + `<span style="color:var(--status-crit)">critical path</span>${c.has_cycle ? " · ⚠ cycle broken" : ""}<br>`
      + `<span class="meta">Critical: ${cp}</span>`;
  }).catch(() => { cpmBox.textContent = "CPM unavailable."; });

  // Earned value (schedule performance) — SPI + dollar schedule variance
  const evBox = document.createElement("div"); evBox.className = "meta"; evBox.style.margin = "0 0 8px";
  evBox.textContent = "Computing earned value…"; ctx.root.appendChild(evBox);
  void ctx.host.api.scheduleEarnedValue(pid).then((e) => {
    if (!e.activity_count) { evBox.textContent = "Earned value: add a Budgeted Cost + % to activities."; return; }
    const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;
    const col = e.status === "ahead" ? "var(--status-good)" : e.status === "behind" ? "var(--status-crit)" : "var(--status-warn)";
    evBox.innerHTML = `<b>Earned value</b>: ${e.percent_complete}% complete · `
      + `SPI <b style="color:${col}">${e.spi ?? "—"}</b> (${e.status.replace("_", " ")}) · `
      + `schedule variance <span style="color:${e.sv < 0 ? "var(--status-crit)" : "var(--status-good)"}">${usd(e.sv)}</span><br>`
      + `<span class="meta">EV ${usd(e.ev)} · PV ${usd(e.pv)} · BAC ${usd(e.bac)}</span>`;
  }).catch(() => { evBox.textContent = "Earned value unavailable."; });

  // Baseline + variance — snapshot the plan, then track slip against it
  const blCard = document.createElement("div"); blCard.className = "dash-card"; blCard.style.marginBottom = "10px";
  const blHead = document.createElement("div"); blHead.className = "section-title";
  blHead.style.cssText = "display:flex;justify-content:space-between;align-items:center";
  blHead.append(Object.assign(document.createElement("span"), { textContent: "Baseline & variance" }));
  const setBtn = document.createElement("button"); setBtn.className = "tool-btn"; setBtn.textContent = "📌 Set baseline";
  blHead.appendChild(setBtn); blCard.appendChild(blHead);
  const blBody = document.createElement("div"); blBody.innerHTML = `<div class="meta">loading…</div>`; blCard.appendChild(blBody);
  const loadVariance = () => {
    blBody.innerHTML = `<div class="meta">loading…</div>`;
    void ctx.host.api.scheduleVariance(pid).then((v) => {
      const s = v.summary;
      blBody.innerHTML = `<div class="meta">Baseline ${v.captured_at} · ${v.baseline_count} activities · `
        + `<b style="color:var(--status-crit)">${s.slipped || 0} slipped</b> · ${s.on_baseline || 0} on plan · `
        + `${s.improved || 0} improved · ${s.added || 0} added · max slip <b>${s.max_slip_days || 0}d</b></div>`;
      for (const a of v.activities.filter((x) => (x.finish_var || 0) !== 0 || x.status === "added" || x.status === "removed").slice(0, 8)) {
        const row = document.createElement("div"); row.className = "meta"; row.style.margin = "1px 0";
        const fv = a.finish_var; const tag = fv == null ? a.status : fv > 0 ? `+${fv}d late` : `${fv}d early`;
        const col = fv != null && fv > 0 ? "var(--status-crit)" : fv != null && fv < 0 ? "var(--status-good)" : "var(--muted)";
        row.innerHTML = `<span style="color:${col}">◷</span> ${a.name} · <span style="color:${col}">${tag}</span>`;
        blBody.appendChild(row);
      }
    }).catch(() => { blBody.innerHTML = `<div class="meta">No baseline set — click <b>📌 Set baseline</b> to snapshot the current plan and start tracking slip.</div>`; });
  };
  setBtn.onclick = async () => {
    if (!(await confirmModal("Snapshot the current schedule as the baseline? Variance will be measured against it (re-baseline anytime).", ""))) return;
    try { const b = await ctx.host.api.setBaseline(pid); ctx.host.setStatus(`baseline set (${b.count} activities)`); loadVariance(); }
    catch (e) { ctx.host.setStatus(`baseline failed: ${(e as Error).message}`); }
  };
  ctx.root.appendChild(blCard); loadVariance();

  // Gantt + Line-of-Balance, fetched as inline SVG
  for (const [kind, title] of [["gantt", "Gantt"], ["lob", "Line of Balance (linear)"]] as const) {
    const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "10px";
    card.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: title }));
    const holder = document.createElement("div"); holder.style.overflowX = "auto";
    holder.innerHTML = `<div class="meta">loading ${title}…</div>`;
    card.appendChild(holder); ctx.root.appendChild(card);
    void ctx.host.api.scheduleSvg(pid, kind).then((svg) => { holder.innerHTML = svg; })
      .catch(() => { holder.innerHTML = `<div class="meta">No ${title.toLowerCase()} yet — add activities with start/finish dates.</div>`; });
  }

  // Takt — actual vs plan: the line-of-balance takt chart with the actual ascent overlaid, plus a
  // per-trade variance table (floors ahead/behind, achieved vs planned production rate) + PPC.
  const taktCard = document.createElement("div"); taktCard.className = "dash-card"; taktCard.style.marginBottom = "10px";
  taktCard.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Takt — actual vs plan" }));
  const taktChart = document.createElement("div"); taktChart.style.overflowX = "auto";
  taktChart.setAttribute("role", "img");
  taktChart.setAttribute("aria-label", "Takt line-of-balance chart: planned trade ascent floor-by-floor, with actual progress overlaid when trades have completed floors");
  taktChart.innerHTML = `<div class="meta">loading takt chart…</div>`;
  const taktBody = document.createElement("div"); taktBody.style.marginTop = "6px";
  taktCard.appendChild(taktChart); taktCard.appendChild(taktBody); ctx.root.appendChild(taktCard);
  void ctx.host.api.taktSvg(pid).then((svg) => { taktChart.innerHTML = svg; })
    .catch(() => { taktChart.innerHTML = `<div class="meta">No takt chart yet — the model's storey count drives the plan.</div>`; });
  void ctx.host.api.taktProgress(pid).then((tp) => {
    const pg = tp.progress;
    const color = (s: string) => s === "ahead" ? "var(--status-good)" : s === "behind" ? "var(--status-warn)" : "var(--text)";
    const head = `<div class="meta">Overall <b style="color:${color(pg.overall_status)}">${pg.overall_status}</b>`
      + ` · lead ${pg.lead_trade ?? "—"} at <b>${pg.lead_actual_floors_per_week}</b> vs plan <b>${pg.planned_floors_per_week}</b> floors/wk`
      + ` · PPC <b>${Math.round((tp.ppc.ppc ?? 0) * 100)}%</b> (${tp.ppc.rating})</div>`;
    const rows = pg.rows.map((r) =>
      `<tr><td>${r.trade}</td><td style="text-align:right">${r.floors_done}/${r.planned_done}</td>`
      + `<td style="text-align:right;color:${color(r.status)}">${r.variance_floors > 0 ? "+" : ""}${r.variance_floors}</td>`
      + `<td style="text-align:right">${r.actual_floors_per_week}</td><td style="text-align:right">${r.planned_floors_per_week}</td></tr>`).join("");
    taktBody.innerHTML = head + (pg.rows.length
      ? `<table class="mini-table" style="margin-top:4px;width:100%;font-size:11px"><thead><tr>`
        + `<th scope="col">Trade</th><th scope="col" style="text-align:right">Done/plan</th><th scope="col" style="text-align:right">Var</th>`
        + `<th scope="col" style="text-align:right">Act fl/wk</th><th scope="col" style="text-align:right">Plan fl/wk</th></tr></thead><tbody>${rows}</tbody></table>`
      : `<div class="meta">No completed floors yet — mark schedule activities complete (per trade) to track actual vs takt.</div>`);
  }).catch(() => { taktBody.innerHTML = `<div class="meta">actual-vs-takt unavailable</div>`; });
}
