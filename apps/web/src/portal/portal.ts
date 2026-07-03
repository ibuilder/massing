import type { ApiClient, ModuleDef, ModuleRecord, RecordBrief } from "../api/client";
import { escapeHtml as esc, toast } from "../ui/feedback";
import { progressBar, groupedBar, lineChart, money as cmoney } from "../ui/charts";
import { modalShell, promptModal } from "../ui/modal";
import { noProjectHtml } from "../ui/empty";
import { allQueued, dequeue, enqueueUpload, queuedCountForRecord } from "./offlineQueue";

/**
 * GC portal UI — one config-driven engine renders every module's list / form / record pages
 * from its module.json (fetched at /modules). No per-module code: the same views drive RFIs,
 * the change-order chain, daily reports, etc. Workflow actions are server-gated by party role.
 */
export interface PortalHost {
  api: ApiClient;
  projectId: () => string | null;
  anchorPoint: () => { x: number; y: number; z: number } | null;  // last clicked 3D point
  selectedGuid: () => string | null;
  onSelectGuids: (guids: string[]) => void;                       // highlight in 3D
  onPinsChanged: () => void;                                      // refresh model pins
  setStatus: (m: string) => void;
}

interface Conversion {
  to: string;                                          // target module key
  label: string;                                       // button text (target name)
  back?: string;                                       // reference field on the target pointing back to the source
  when?: (d: Record<string, unknown>) => boolean;      // only offer when this holds (else fall through)
  map: (d: Record<string, unknown>) => Record<string, unknown>;  // copy source fields → new record
}

export class PortalUI {
  private mods: ModuleDef[] = [];
  private nav?: HTMLElement;          // persistent left module-nav rail (built once)
  private activeKey: string | null = null;
  // R2 — workspace split: this portal serves either the "construction" (GC build) or "developer"
  // (real-estate) module set. `showAll` is the escape hatch so every role can still reach every
  // register (the user's "everyone has access to all data, just a few more clicks").
  private wsFilter: "construction" | "developer" = "construction";
  private showAll = false;
  /** Which workspace this portal renders. Call before init(). */
  setWorkspace(ws: "construction" | "developer") { this.wsFilter = ws; }
  /** True when a module belongs in the active workspace (or Show-all is on). */
  private inWs(m: ModuleDef) { return this.showAll || (m.workspace || "construction") === this.wsFilter; }
  // field/offline: uploads attempted while offline are persisted in IndexedDB (offlineQueue) so they
  // survive a reload, and flushed on reconnect / next launch.
  private onlineHooked = false;

  // C1 — one-click cross-module conversions (Procore "convert RFI to PCO" etc.). The new record is
  // pre-filled from the source and linked back (via a reference field when one exists, else an explicit link).
  private static CONVERSIONS: Record<string, Conversion[]> = {
    cor: [
      { to: "sov", label: "SOV line", back: "cor",
        map: (d) => ({ item_no: "CO", description: d.subject, scheduled_value: d.amount, cost_code: d.cost_code }) },
    ],
    bid_submission: [
      { to: "subcontract", label: "Award → Subcontract", back: "bid_submission",
        map: (d) => ({ vendor: d.bidder, value: d.amount }) },
    ],
    rfi: [
      { to: "change_event", label: "Change Event", back: "source_rfi",
        map: (d) => ({ subject: d.subject, cost_code: d.cost_code }) },
      { to: "pco_request", label: "PCO", back: "source_rfi",
        map: (d) => ({ subject: d.subject, description: d.question, origin: "RFI", cost_code: d.cost_code }) },
    ],
    observation: [
      { to: "ncr", label: "NCR",
        map: (d) => ({ subject: d.description, description: d.corrective_action, severity: d.severity }) },
      { to: "punchlist", label: "Punch item", back: "observation",
        map: (d) => ({ description: d.description, location: d.location, trade: d.trade }) },
    ],
    inspection: [
      { to: "deficiency", label: "Deficiency", back: "inspection",
        when: (d) => d.result === "Fail" || d.result === "Conditional",
        map: (d) => ({ description: d.subject, location: d.location, trade: d.inspection_type }) },
      { to: "ncr", label: "NCR", back: "inspection",
        when: (d) => d.result === "Fail" || d.result === "Conditional",
        map: (d) => ({ subject: d.subject, description: d.spec_section }) },
    ],
    deficiency: [
      { to: "punchlist", label: "Punch item",
        map: (d) => ({ description: d.description, location: d.location, trade: d.trade }) },
    ],
  };

  constructor(private root: HTMLElement, private host: PortalHost) {}

  async init() {
    if (!this.host.projectId()) { this.root.innerHTML = noProjectHtml(this.wsFilter === "developer" ? "the developer workspace" : "the GC portal"); return; }
    this.mods = await this.host.api.modules();
    // build the persistent shell once: [nav rail | content]. `this.root` is redirected to the
    // content pane, so every existing render path writes into it while the nav rail stays put.
    const outer = this.root;
    outer.innerHTML = ""; outer.classList.add("portal-shell");
    this.nav = document.createElement("nav"); this.nav.className = "portal-nav";
    const content = document.createElement("div"); content.className = "portal-content";
    outer.append(this.nav, content);
    this.root = content;
    this.buildNav();
    // re-order the module catalog's default-open sections when the persona changes
    window.addEventListener("aec:persona", () => { this.refreshCatalog(); this.buildNav(); });
    // drain any uploads queued offline in a previous session, and keep watching for reconnect
    this.hookOnline(); void this.flushUploads();
    await this.renderHome();
  }

  /** The always-visible left nav: Dashboard + a filter + favorites + collapsible sections of modules.
   *  Clicking a module loads it into the content pane (the rail persists, unlike the old full replace). */
  private buildNav() {
    const nav = this.nav; if (!nav) return;
    nav.innerHTML = "";
    const home = document.createElement("button");
    home.className = "pnav-item pnav-home" + (this.activeKey === null ? " active" : "");
    home.innerHTML = `<span class="ic">🏠</span> Dashboard`;
    home.onclick = () => { this.activeKey = null; void this.renderHome(); this.buildNav(); };
    nav.appendChild(home);

    // First-class destinations, grouped by lifecycle stage — journey-based IA: people think in
    // project phases (plan → build → turn over → operate), not in a flat feature list, and stage
    // headers keep the rail scannable as destinations keep growing. Cross-project roll-ups get
    // their own group so single-project and portfolio views don't interleave.
    type Dest = { key: string; icon: string; label: string; go?: () => void };
    const dests: Record<string, () => unknown> = {
      __schedule__: () => { const m = this.mods.find((x) => x.key === "schedule_activity"); if (m) void this.renderScheduleViews(m); },
      __budget__: () => this.renderBudget(), __review__: () => this.renderRiskReview(),
      __aiassist__: () => this.renderAiAssist(), __riskcost__: () => this.renderRiskCost(),
      __ids__: () => this.renderIds(), __turnover__: () => this.renderTurnover(),
      __operations__: () => this.renderOperations(), __energy__: () => this.renderEnergy(),
      __land__: () => this.renderLandScreen(), __lifecycle__: () => this.renderLifecycle(),
      __diligence__: () => this.renderDiligence(), __esg__: () => this.renderEsg(),
      __standards__: () => this.renderStandards(),
      __portfolio__: () => this.renderPortfolio(), __benchmarks__: () => this.renderBenchmarks(),
    };
    const stages: [string, Dest[]][] = this.wsFilter === "construction"
      ? [
        ["Plan & derisk", [
          { key: "__review__", icon: "🛡", label: "Risk Review" },          // contract clauses / scope gaps / doc Q&A
          { key: "__riskcost__", icon: "⚖️", label: "Risk & Cost" },        // prequal, lien exposure, carbon, takeoff
          { key: "__ids__", icon: "📋", label: "IDS Requirements" },
          { key: "__standards__", icon: "🗂", label: "CDE / Standards" },   // ISO 19650 container discipline + reqs
        ]],
        ["Build", [
          ...(this.mods.some((x) => x.key === "schedule_activity") ? [{ key: "__schedule__", icon: "📅", label: "Schedule" }] : []),
          { key: "__budget__", icon: "💰", label: "Budget" },
          { key: "__aiassist__", icon: "✍️", label: "AI Assist" },
        ]],
        ["Turn over & operate", [
          { key: "__turnover__", icon: "🏁", label: "Turnover" },
          { key: "__operations__", icon: "🔧", label: "Operations" },
          { key: "__energy__", icon: "⚡", label: "Energy" },
        ]],
      ]
      : [
        ["Acquire", [
          { key: "__uw__", icon: "📊", label: "Underwriting",
            go: () => window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: "finance" })) },
          { key: "__land__", icon: "🗺️", label: "Land Screening" },
          { key: "__diligence__", icon: "📜", label: "Diligence & Entitlements" },
        ]],
        ["Design & build", [{ key: "__lifecycle__", icon: "🧭", label: "Project Lifecycle" }]],
        ["Operate", [{ key: "__esg__", icon: "🌱", label: "ESG & POE" }]],
      ];
    stages.push(["Across projects", [
      { key: "__portfolio__", icon: "🏢", label: "Portfolio" },
      { key: "__benchmarks__", icon: "📈", label: "Benchmarks" },
    ]]);
    for (const [stage, items] of stages) {
      if (!items.length) continue;
      const h = document.createElement("div"); h.className = "pnav-stage"; h.textContent = stage;
      nav.appendChild(h);
      for (const d of items) {
        const b = document.createElement("button");
        b.className = "pnav-item pnav-home" + (this.activeKey === d.key ? " active" : "");
        b.innerHTML = `<span class="ic">${d.icon}</span> ${d.label.replace("&", "&amp;")}`;
        b.onclick = d.go ?? (() => { this.activeKey = d.key; void dests[d.key]?.(); this.buildNav(); });
        nav.appendChild(b);
      }
    }

    const filter = document.createElement("input");
    filter.type = "search"; filter.placeholder = "Filter…"; filter.className = "portal-filter pnav-filter";
    nav.appendChild(filter);

    const favs = this.favs();
    const persona = document.body.dataset.persona || localStorage.getItem("persona") || "all";
    const openSecs = PortalUI.SECTIONS_BY_PERSONA[persona];

    const item = (m: ModuleDef) => {
      const b = document.createElement("button");
      b.className = "pnav-item" + (this.activeKey === m.key ? " active" : "");
      b.dataset.modname = m.name.toLowerCase();
      b.innerHTML = `<span class="ic">${m.icon || "•"}</span> ${m.name}`;
      b.onclick = () => { this.activeKey = m.key; void this.openModule(m); this.buildNav(); };
      return b;
    };
    const group = (title: string, mods: ModuleDef[], open: boolean) => {
      const det = document.createElement("details"); det.open = open; det.className = "pnav-group"; det.dataset.sec = title;
      const sum = document.createElement("summary"); sum.textContent = title; det.appendChild(sum);
      mods.forEach((m) => det.appendChild(item(m)));
      nav.appendChild(det);
    };
    const visible = this.mods.filter((m) => this.inWs(m));
    if (favs.size) {
      const favMods = visible.filter((m) => favs.has(m.key));
      if (favMods.length) group("★ Favorites", favMods, true);
    }
    // Recent — auto-populated last-opened registers (favorites are the opt-in layer; recents work
    // with zero effort). Skip modules already pinned to Favorites to avoid duplicate rows.
    const recentMods = this.recents()
      .map((k) => visible.find((m) => m.key === k))
      .filter((m): m is ModuleDef => !!m && !favs.has(m.key));
    if (recentMods.length) group("🕘 Recent", recentMods, true);
    const sections = new Map<string, ModuleDef[]>();
    for (const m of visible) { const s = m.section || "Other"; (sections.get(s) ?? sections.set(s, []).get(s)!).push(m); }
    // if the persona's preferred sections don't exist in this workspace (e.g. a GC browsing the
    // Developer registers), open everything rather than render a fully-collapsed nav.
    const anyMatch = !openSecs || [...sections.keys()].some((s) => openSecs.includes(s));
    for (const [section, mods] of sections) group(section, mods, !openSecs || !anyMatch || openSecs.includes(section));

    // "Show all modules" — reveal the other workspace's registers so every role can reach all data
    // (a few more clicks, per the product principle). Persisted to the toggle for the session.
    const other = this.wsFilter === "construction" ? "developer" : "construction";
    const otherCount = this.mods.filter((m) => (m.workspace || "construction") === other).length;
    if (otherCount) {
      const toggle = document.createElement("button");
      toggle.className = "pnav-item pnav-showall" + (this.showAll ? " active" : "");
      toggle.innerHTML = this.showAll
        ? `<span class="ic">▾</span> Showing all modules`
        : `<span class="ic">▸</span> Show all modules (+${otherCount})`;
      toggle.title = this.showAll ? "Hide the other workspace's registers" : `Also show ${other} registers`;
      toggle.onclick = () => { this.showAll = !this.showAll; this.buildNav(); };
      nav.appendChild(toggle);
    }

    // teach the accelerator in context: the palette is the long-tail navigator for ~100 registers
    const hint = document.createElement("div");
    hint.className = "pnav-khint meta";
    hint.innerHTML = `Jump anywhere: <kbd>${navigator.platform.startsWith("Mac") ? "⌘" : "Ctrl"}</kbd>+<kbd>K</kbd>`;
    nav.appendChild(hint);

    filter.oninput = () => {
      const q = filter.value.trim().toLowerCase();
      nav.querySelectorAll<HTMLElement>(".pnav-group").forEach((det) => {
        let any = false;
        det.querySelectorAll<HTMLElement>(".pnav-item").forEach((b) => {
          const hit = !q || (b.dataset.modname || "").includes(q);
          b.style.display = hit ? "" : "none"; if (hit) any = true;
        });
        det.style.display = any ? "" : "none";
        if (q) (det as HTMLDetailsElement).open = true;
      });
    };
  }

  // --- role-tailored dashboard (command center; the left rail handles module nav) -----
  /** The PX executive band: on-schedule (SPI / % complete / lookahead / milestones) next to
   *  on-budget (GMP / EAC / variance / draw), with an overall status pill. Clicks jump to the
   *  Schedule and Budget destinations. Hides itself if there's no schedule/budget data yet. */
  private async renderPxBand(host: HTMLElement, pid: string) {
    let px;
    try { px = await this.host.api.pxSummary(pid); } catch { return; }
    if (!px.schedule.activities && !px.budget.gmp) return;     // nothing to summarize yet
    const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;
    const sched = px.schedule, bud = px.budget;
    const pill = { on_track: ["On track", "var(--status-good)"], at_risk: ["At risk", "var(--status-warn)"], behind: ["Behind", "var(--status-crit)"] }[px.status];
    const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "10px";
    const head = document.createElement("div"); head.className = "section-title";
    head.style.cssText = "display:flex;justify-content:space-between;align-items:center";
    head.append(Object.assign(document.createElement("span"), { textContent: "Project executive — on schedule & on budget" }));
    const tag = document.createElement("span"); tag.className = "ball-badge";
    tag.style.cssText = `background:${pill[1]}22;color:${pill[1]};border-color:${pill[1]}`; tag.textContent = pill[0];
    head.appendChild(tag); card.appendChild(head);

    const cols = document.createElement("div"); cols.className = "dash-cols";
    const spiColor = sched.spi == null ? "var(--muted)" : sched.spi >= 0.95 ? "var(--status-good)" : sched.spi >= 0.85 ? "var(--status-warn)" : "var(--status-crit)";
    const sCol = document.createElement("div"); sCol.className = "dash-card kpi-click"; sCol.style.flex = "1";
    sCol.innerHTML = `<div class="meta">📅 On schedule</div>`
      + `<div style="font-size:16px;font-weight:700;color:${spiColor}">SPI ${sched.spi ?? "—"}</div>`
      + `<div class="meta">${sched.pct_complete}% complete · ${sched.activities} activities · CP ${sched.critical_path_days}d</div>`
      + `<div class="meta">${sched.lookahead_3wk} in 3-wk lookahead · milestones: `
      + `<span style="color:var(--status-crit)">${sched.milestones.late} late</span> · ${sched.milestones.due_soon} due soon</div>`;
    sCol.onclick = () => { const m = this.mods.find((x) => x.key === "schedule_activity"); if (m) { this.activeKey = "__schedule__"; void this.renderScheduleViews(m); this.buildNav(); } };
    const vColor = bud.variance_at_completion < 0 ? "var(--status-crit)" : "var(--status-good)";
    const bCol = document.createElement("div"); bCol.className = "dash-card kpi-click"; bCol.style.flex = "1";
    bCol.innerHTML = `<div class="meta">💰 On budget</div>`
      + `<div style="font-size:16px;font-weight:700">GMP ${usd(bud.revised_gmp || bud.gmp)}</div>`
      + `<div class="meta">EAC ${usd(bud.eac)} · VAC <span style="color:${vColor}">${usd(bud.variance_at_completion)}</span></div>`
      + `<div class="meta">${bud.committed_pct}% bought out · ${bud.spent_pct}% spent`
      + (bud.draw_this_month ? ` · draw ${usd(bud.draw_this_month)}/mo` : "")
      + (bud.buyout && bud.buyout.savings ? ` · savings ${usd(bud.buyout.savings)}` : "") + `</div>`;
    bCol.onclick = () => { this.activeKey = "__budget__"; void this.renderBudget(); this.buildNav(); };
    cols.append(sCol, bCol); card.appendChild(cols);
    // progress bars — % complete, bought out, spent — the at-a-glance health strip
    const prog = document.createElement("div"); prog.style.cssText = "margin-top:8px";
    prog.innerHTML = progressBar(sched.pct_complete ?? 0, 100, { label: "Schedule % complete" })
      + progressBar(bud.committed_pct ?? 0, 100, { label: "Bought out (committed)" })
      + progressBar(bud.spent_pct ?? 0, 100, { label: "Spent (actual / budget)" });
    card.appendChild(prog);
    host.appendChild(card);
  }

  /** Developer (real-estate) home: deal returns + RE register KPIs (listings / comps / capital /
   *  leases / feasibility). Every card jumps to its register; underwriting lives one click away. */
  private async renderDeveloperHome(root: HTMLElement, pid: string,
      el: (tag: string, cls?: string) => HTMLElement, jump: (key: string, state?: string) => void) {
    const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;
    const head = el("div", "section-title"); head.style.cssText = "display:flex;justify-content:space-between;align-items:center";
    head.append("Developer — real estate");
    const uw = el("button", "tool-btn") as HTMLButtonElement;
    uw.textContent = "Underwriting →"; uw.title = "Open the proforma / underwriting workspace";
    uw.onclick = () => window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: "finance" }));
    head.append(uw); root.appendChild(head);

    // returns strip — blended proforma returns for the deal (hides cleanly if no proforma yet)
    const ret = el("div"); root.appendChild(ret);
    void this.host.api.portfolio().then((pf) => {
      if (!pf.deal_count) return;
      const t = pf.totals || {};
      const irr = (t.equity_irr as number | null) ?? pf.deals[0]?.equity_irr ?? null;
      const em = (t.equity_multiple as number | null) ?? pf.deals[0]?.equity_multiple ?? null;
      const card = el("div", "dash-card"); card.style.marginBottom = "10px";
      card.style.cssText += ";cursor:pointer";
      card.title = "Open underwriting"; card.onclick = () => window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: "finance" }));
      const kpi = (v: string, l: string, tone?: string) =>
        `<div class="dash-card" style="flex:1;text-align:center"><div style="font-size:18px;font-weight:700${tone ? `;color:${tone}` : ""}">${v}</div><div class="meta">${l}</div></div>`;
      card.innerHTML = `<div class="meta" style="margin-bottom:6px">📊 Deal returns · ${pf.deal_count} scenario${pf.deal_count === 1 ? "" : "s"}</div>`
        + `<div class="dash-cols" style="display:flex;gap:8px">`
        + kpi(irr == null ? "—" : `${(irr * 100).toFixed(1)}%`, "Equity IRR", irr != null && irr >= 0.15 ? "var(--status-good)" : irr != null && irr < 0.08 ? "var(--status-warn)" : undefined)
        + kpi(em == null ? "—" : `${em.toFixed(2)}×`, "Equity multiple")
        + kpi(usd((t.equity as number) || 0), "Equity")
        + kpi(usd((t.loan as number) || 0), "Loan")
        + `</div>`;
      root.insertBefore(card, ret.nextSibling);
    }).catch(() => {});

    // RE register KPIs from the dashboard's per-module counts
    try {
      const d = await this.host.api.dashboard(pid);
      const cnt = (k: string) => d.by_module.find((m) => m.key === k)?.count ?? 0;
      const active = (k: string, states: string[]) => {
        const bm = d.by_module.find((m) => m.key === k); if (!bm) return 0;
        return states.reduce((s, st) => s + (bm.by_state[st] ?? 0), 0);
      };
      const kpis = el("div", "kpi-grid");
      const cards: [string, number, (() => void) | undefined][] = [
        ["Active listings", active("listing", ["active", "listed", "available"]) || cnt("listing"), () => jump("listing")],
        ["Comparables", cnt("comparable"), () => jump("comparable")],
        ["Investors", cnt("investor"), () => jump("investor")],
        ["Leases", cnt("lease"), () => jump("lease")],
        ["Feasibility", cnt("zoning"), () => jump("zoning")],
      ];
      for (const [label, val, onClick] of cards) {
        const c = el("div", "kpi" + (onClick ? " kpi-click" : "")) as HTMLElement;
        c.innerHTML = `<div class="kpi-v">${val}</div><div class="kpi-l">${label}</div>`;
        if (onClick) { c.onclick = onClick; c.tabIndex = 0; c.setAttribute("role", "button"); c.onkeydown = (e) => { if ((e as KeyboardEvent).key === "Enter") onClick(); }; }
        kpis.appendChild(c);
      }
      root.appendChild(kpis);
    } catch { /* dashboard unavailable — KPI grid just omitted */ }

    // quick-create row for the common developer records
    const quick = el("div"); quick.style.cssText = "margin-top:10px";
    quick.innerHTML = `<div class="section-title">Quick add</div>`;
    const qrow = el("div"); qrow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:4px";
    for (const [k, lbl] of [["listing", "＋ Listing"], ["comparable", "＋ Comp"], ["investor", "＋ Investor"], ["lease", "＋ Lease"]] as const) {
      if (!this.mods.find((m) => m.key === k)) continue;
      const b = el("button", "tool-btn") as HTMLButtonElement; b.textContent = lbl;
      b.onclick = () => jump(k);
      qrow.appendChild(b);
    }
    quick.appendChild(qrow); root.appendChild(quick);
  }

  // --- Risk Review (preconstruction intelligence) ------------------------------------------------
  private static SEV_TONE: Record<string, string> = {
    high: "var(--status-crit)", medium: "var(--status-warn)", low: "var(--status-good)" };

  private renderRiskReview() {
    const root = this.root; root.innerHTML = "";
    const pid = this.host.projectId();
    if (!pid) { root.innerHTML = noProjectHtml("Risk Review"); return; }
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("🛡 Risk Review", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const intro = el("div", "meta");
    intro.textContent = "Review an incoming contract for risky clauses, find scope gaps in specs/notes, "
      + "or ask a document a question with citations. Works offline (built-in clause library); set an "
      + "Anthropic key in Settings for full AI review.";
    intro.style.marginBottom = "8px"; root.appendChild(intro);

    const tabs = el("div"); tabs.style.cssText = "display:flex;gap:6px;margin-bottom:8px";
    const body = el("div"); root.append(tabs, body);
    const TABS: [string, string][] = [["contract", "🛡 Contract risk"], ["scope", "🔍 Scope gaps"], ["ask", "💬 Ask a doc"]];
    let active = "contract";

    const render = () => {
      body.innerHTML = "";
      [...tabs.children].forEach((b, i) => b.classList.toggle("active", TABS[i][0] === active));
      const fileInp = el("input") as HTMLInputElement; fileInp.type = "file"; fileInp.accept = ".pdf,.txt";
      fileInp.style.cssText = "display:block;margin:4px 0";
      const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
      ta.placeholder = active === "ask" ? "Paste the document text (or choose a PDF above)…"
        : `Paste the ${active === "contract" ? "contract" : "spec / drawing notes"} text (or choose a PDF above)…`;
      ta.style.cssText = "width:100%;min-height:120px;margin:6px 0";
      let qInp: HTMLInputElement | undefined;
      if (active === "ask") {
        qInp = el("input", "portal-filter") as HTMLInputElement;
        qInp.placeholder = "Your question — e.g. what is the retainage %?"; qInp.style.cssText = "width:100%;margin:6px 0";
      }
      const run = el("button", "file-btn") as HTMLButtonElement;
      run.textContent = active === "contract" ? "Review contract" : active === "scope" ? "Find scope gaps" : "Ask";
      const out = el("div"); out.style.marginTop = "8px";
      const doRun = async () => {
        const opts = { file: fileInp.files?.[0], text: ta.value.trim() || undefined };
        if (active === "ask" && !(qInp!.value.trim())) { toast("Enter a question", "error"); return; }
        if (!opts.file && !opts.text) { toast("Choose a PDF or paste text", "error"); return; }
        out.textContent = "analyzing…";
        try {
          if (active === "contract") this.renderContractFindings(out, await this.host.api.reviewContract(pid, opts), pid);
          else if (active === "scope") this.renderScopeGaps(out, await this.host.api.reviewScope(pid, opts));
          else this.renderDocAnswer(out, await this.host.api.reviewAsk(pid, qInp!.value.trim(), opts));
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      run.onclick = () => void doRun();
      body.append(fileInp);
      if (qInp) body.append(qInp);
      body.append(ta, run, out);
    };
    for (const [k, label] of TABS) {
      const b = el("button", "tool-btn") as HTMLButtonElement; b.textContent = label;
      b.onclick = () => { active = k; render(); };
      tabs.appendChild(b);
    }
    render();
  }

  // --- AI Assist: draft RFI / scope / submittal summary + bid leveling --------------------------
  private async renderAiAssist() {
    const root = this.root; root.innerHTML = "";
    const pid = this.host.projectId();
    if (!pid) { root.innerHTML = noProjectHtml("AI Assist"); return; }
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("✍️ AI Assist", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const intro = el("div", "meta");
    intro.textContent = "Turn a note or a PDF into an editable draft, and level bids apples-to-apples. "
      + "Works offline; set an Anthropic key in Settings for full AI output. Nothing is created until you click Create.";
    intro.style.marginBottom = "8px"; root.appendChild(intro);
    const tabs = el("div"); tabs.style.cssText = "display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap";
    const body = el("div"); root.append(tabs, body);
    const TABS: [string, string][] = [["rfi", "📝 Draft RFI"], ["scope", "📋 Draft scope"],
      ["submittal", "📄 Submittal summary"], ["level", "⚖️ Bid leveling"], ["code", "🏛️ Code check"]];
    let active = "rfi";

    const fileRow = (accept: string) => {
      const f = el("input") as HTMLInputElement; f.type = "file"; f.accept = accept;
      f.style.cssText = "display:block;margin:4px 0"; return f;
    };
    const list = (title: string, items: string[]) => {
      const w = el("div"); w.style.marginTop = "6px";
      const h = el("div", "meta"); h.innerHTML = `<b>${title}</b> (${items.length})`; w.appendChild(h);
      const ul = el("ul"); ul.style.cssText = "margin:2px 0 0 16px;font-size:12px";
      items.forEach((s) => { const li = el("li"); li.textContent = s; ul.appendChild(li); });
      if (!items.length) { const li = el("div", "meta"); li.textContent = "—"; li.style.marginLeft = "4px"; w.appendChild(li); }
      else w.appendChild(ul);
      return w;
    };

    const render = async () => {
      body.innerHTML = "";
      [...tabs.children].forEach((b, i) => b.classList.toggle("active", TABS[i][0] === active));

      if (active === "level") {
        const pick = el("select", "portal-filter") as HTMLSelectElement; pick.style.cssText = "margin:4px 0";
        pick.innerHTML = `<option value="">Loading packages…</option>`;
        const out = el("div"); out.style.marginTop = "8px";
        body.append(pick, out);
        try {
          const pkgs = await this.host.api.moduleRecords(pid, "bid_package");
          pick.innerHTML = `<option value="">Choose a bid package…</option>`
            + pkgs.map((p) => `<option value="${p.id}">${(p.title || p.ref || p.id) as string}</option>`).join("");
        } catch { pick.innerHTML = `<option value="">No bid packages</option>`; }
        pick.onchange = async () => {
          if (!pick.value) return;
          out.textContent = "leveling…";
          try { this.renderLeveling(out, await this.host.api.bidLevelingDetail(pid, pick.value)); }
          catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
        };
        return;
      }

      if (active === "code") {
        const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
        ta.placeholder = "Describe the project — occupancy/use, area (sf), stories, occupants…";
        ta.style.cssText = "width:100%;min-height:80px;margin:6px 0";
        const run = el("button", "file-btn") as HTMLButtonElement; run.textContent = "Check applicable codes";
        const out = el("div"); out.style.marginTop = "8px";
        run.onclick = async () => {
          if (!ta.value.trim()) { toast("Describe the project", "error"); return; }
          out.textContent = "checking…";
          try {
            const r = await this.host.api.codeComplianceCheck(pid, ta.value.trim());
            out.innerHTML = "";
            const d = r.detected;
            const head = el("div", "meta");
            head.textContent = "Detected: " + [d?.occupancy ? `${d.occupancy.label} (${d.occupancy.group})` : null,
              d?.area_sf ? `${d.area_sf.toLocaleString()} sf` : null, d?.stories ? `${d.stories} stories` : null]
              .filter(Boolean).join(" · ") + `  ·  ${r.source}`;
            out.append(head);
            const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px;margin-top:6px";
            tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Code</th><th scope="col" style="text-align:left">Section</th>`
              + `<th scope="col" style="text-align:left">Requirement</th></tr></thead><tbody>`
              + r.topics.map((t) => `<tr><td>${t.code}</td><td><b>${t.section}</b> — ${t.title}</td>`
                + `<td>${t.requirement}</td></tr>`).join("") + `</tbody>`;
            out.append(tbl);
            const note = el("div", "meta"); note.style.marginTop = "6px";
            note.textContent = r.message || "Confirm all provisions with the Authority Having Jurisdiction (AHJ).";
            out.append(note);
          } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
        };
        body.append(ta, run, out);
        return;
      }

      const wantsTrade = active === "scope";
      let tradeInp: HTMLInputElement | undefined;
      if (wantsTrade) {
        tradeInp = el("input", "portal-filter") as HTMLInputElement;
        tradeInp.placeholder = "Trade — e.g. Concrete, Electrical, HVAC"; tradeInp.style.cssText = "width:100%;margin:4px 0";
      }
      const noteInp = active === "rfi" ? el("input", "portal-filter") as HTMLInputElement : undefined;
      if (noteInp) { noteInp.placeholder = "Describe the question — e.g. beam at B4 clashes with duct per 5/S-201";
        noteInp.style.cssText = "width:100%;margin:4px 0"; }
      const file = fileRow(".pdf,.txt");
      const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
      ta.placeholder = "Or paste the spec/plan/submittal text…"; ta.style.cssText = "width:100%;min-height:100px;margin:6px 0";
      const run = el("button", "file-btn") as HTMLButtonElement;
      run.textContent = active === "rfi" ? "Draft RFI" : active === "scope" ? "Draft scope" : "Summarize submittal";
      const out = el("div"); out.style.marginTop = "8px";

      const doRun = async () => {
        const opts = { file: file.files?.[0], text: ta.value.trim() || undefined };
        out.textContent = "drafting…";
        try {
          if (active === "rfi") {
            const d = await this.host.api.aiDraftRfi(pid, { note: noteInp!.value.trim(), ...opts });
            this.renderRfiDraft(out, pid, d);
          } else if (active === "scope") {
            const d = await this.host.api.draftScope(pid, tradeInp!.value.trim() || "General", opts);
            out.innerHTML = "";
            const h = el("div", "meta"); h.innerHTML = `<b>Scope — ${d.trade}</b> · <span class="meta">${d.source}</span>`;
            out.append(h, list("Inclusions", d.inclusions || []), list("Exclusions", d.exclusions || []),
              list("Clarifications", d.clarifications || []), list("Spec sections", d.spec_sections || []));
            if (d.message) { const m = el("div", "meta"); m.textContent = d.message; m.style.marginTop = "6px"; out.append(m); }
          } else {
            const d = await this.host.api.draftSubmittalSummary(pid, opts);
            out.innerHTML = "";
            const h = el("div"); h.innerHTML = `<b>${d.title || "Submittal"}</b> — ${d.spec_section || ""} ${d.type || ""}`;
            const s = el("div"); s.style.cssText = "font-size:12px;margin:4px 0"; s.textContent = d.summary || "";
            out.append(h, s, list("Key items", d.key_items || []), list("Missing / review", d.missing_or_review || []));
            if (d.message) { const m = el("div", "meta"); m.textContent = d.message; m.style.marginTop = "6px"; out.append(m); }
          }
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      run.onclick = () => void doRun();
      if (tradeInp) body.append(tradeInp);
      if (noteInp) body.append(noteInp);
      body.append(file, ta, run, out);
    };
    for (const [k, label] of TABS) {
      const b = el("button", "tool-btn") as HTMLButtonElement; b.textContent = label;
      b.onclick = () => { active = k; void render(); };
      tabs.appendChild(b);
    }
    await render();
  }

  private renderRfiDraft(out: HTMLElement, pid: string,
      d: { subject: string; question: string; discipline: string; spec_section?: string; priority: string;
           citations?: { page: number; snippet?: string }[]; source: string; message?: string }) {
    out.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    const subj = el("input", "portal-filter") as HTMLInputElement; subj.value = d.subject; subj.style.cssText = "width:100%;margin:2px 0";
    const q = el("textarea", "portal-filter") as HTMLTextAreaElement; q.value = d.question; q.style.cssText = "width:100%;min-height:80px;margin:2px 0";
    const meta = el("div", "meta"); meta.style.margin = "4px 0";
    meta.textContent = `Discipline: ${d.discipline}${d.spec_section ? " · Spec " + d.spec_section : ""} · Priority ${d.priority} · ${d.source}`;
    const cite = el("div", "meta");
    if (d.citations?.length) cite.textContent = "Source: " + d.citations.map((c) => `p.${c.page}`).join(", ");
    const create = el("button", "file-btn") as HTMLButtonElement; create.textContent = "Create RFI";
    create.onclick = async () => {
      create.disabled = true; create.textContent = "creating…";
      try {
        await this.host.api.createModuleRecord(pid, "rfi", { data: {
          subject: subj.value, question: q.value, discipline: d.discipline,
          spec_section: d.spec_section || "", priority: d.priority } });
        toast("RFI created", "success"); create.textContent = "✓ Created";
      } catch (e) { toast(`Create failed: ${(e as Error).message}`, "error"); create.disabled = false; create.textContent = "Create RFI"; }
    };
    out.append(el("div", "meta").appendChild(document.createTextNode("Subject")).parentElement!, subj, q, meta, cite, create);
    if (d.message) { const m = el("div", "meta"); m.textContent = d.message; m.style.marginTop = "6px"; out.append(m); }
  }

  private renderLeveling(out: HTMLElement, r: Awaited<ReturnType<ApiClient["bidLevelingDetail"]>>) {
    out.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    if (!r.vendors.length) { out.innerHTML = `<div class="meta">${r.message || "No bids to level."}</div>`; return; }
    const bs = r.base_stats;
    const head = el("div", "meta"); head.style.marginBottom = "6px";
    head.innerHTML = `<b>${r.package}</b> · ${r.vendors.length} bidders · low ${cmoney(bs.low ?? 0)} · median ${cmoney(bs.median ?? 0)}`
      + ` · high ${cmoney(bs.high ?? 0)} · spread ${bs.spread_pct ?? 0}%`
      + (r.outliers.length ? ` · <span style="color:var(--status-warn)">outliers: ${r.outliers.join(", ")}</span>` : "");
    out.append(head);
    if (r.recommendation) {
      const rec = el("div"); rec.style.cssText = "margin:4px 0;font-size:12px";
      rec.innerHTML = `<b>Recommend:</b> ${r.recommendation.apparent_low} @ ${cmoney(r.recommendation.base)} — `
        + `<span style="color:${r.recommendation.missing_scope.length ? "var(--status-warn)" : "var(--status-good)"}">${r.recommendation.note}</span>`;
      out.append(rec);
    }
    // scope matrix
    const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:11px;margin-top:6px";
    const thead = `<tr><th scope="col" style="text-align:left">Scope item</th>${r.vendors.map((v) => `<th scope="col">${v}</th>`).join("")}</tr>`;
    const rows = r.scope_rows.map((row) => {
      const cells = r.vendors.map((v) => {
        const inc = row.included_by.includes(v); const exc = row.excluded_by.includes(v);
        const mark = inc ? "✓" : exc ? "✗" : "–";
        const col = inc ? "var(--status-good)" : exc ? "var(--status-crit)" : "var(--muted)";
        return `<td style="text-align:center;color:${col}">${mark}</td>`;
      }).join("");
      const bg = row.gap ? ' style="background:var(--status-warn-bg,#3a2a0022)"' : "";
      return `<tr${bg}><td>${row.item}${row.gap ? ' <span title="scope gap">⚠️</span>' : ""}</td>${cells}</tr>`;
    }).join("");
    tbl.innerHTML = `<thead>${thead}</thead><tbody>${rows}</tbody>`;
    out.append(tbl);
    if (r.gaps.length) { const g = el("div", "meta"); g.style.marginTop = "6px";
      g.textContent = `⚠️ ${r.gaps.length} scope gap(s) — items some bidders carry that others don't. Level these before award.`;
      out.append(g); }
  }

  // --- Benchmarks: cross-project cost distribution + response rates ------------------------------
  private async renderBenchmarks() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("📈 Benchmarks", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Your own history across every project: what things actually cost (per cost code) and "
      + "how fast RFIs/submittals turn around. Sanity-check a new estimate or hold the team accountable.";
    root.appendChild(intro);
    const rr = el("div"); const costs = el("div"); costs.style.marginTop = "10px";
    root.append(rr, costs);
    rr.textContent = "loading…"; costs.textContent = "";
    try {
      const resp = await this.host.api.benchmarkResponseRates();
      rr.innerHTML = "";
      const card = (title: string, m: { total: number; open: number; avg_turnaround_days: number | null; overdue: number; overdue_pct: number }) => {
        const c = el("div", "kpi-card"); c.style.cssText = "display:inline-block;margin:4px 8px 4px 0;padding:8px 12px;border:1px solid var(--line);border-radius:8px";
        c.innerHTML = `<div class="meta"><b>${title}</b></div>`
          + `<div style="font-size:12px">${m.total} total · ${m.open} open · ${m.overdue} overdue (${m.overdue_pct}%)`
          + ` · avg turnaround ${m.avg_turnaround_days ?? "—"} d</div>`;
        return c;
      };
      rr.append(card("RFIs", resp.rfi), card("Submittals", resp.submittal));
    } catch (e) { rr.textContent = `response rates failed: ${(e as Error).message}`; }
    try {
      const cb = await this.host.api.benchmarkCosts();
      if (!cb.cost_codes.length) { costs.innerHTML = `<div class="meta">${cb.message || "No cost history yet."}</div>`; }
      else {
        const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px";
        tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Cost code</th><th scope="col">n</th><th scope="col">low</th><th scope="col">p25</th>`
          + `<th scope="col">median</th><th scope="col">p75</th><th scope="col">high</th></tr></thead><tbody>`
          + cb.cost_codes.map((c) => `<tr><td>${c.cost_code}</td><td style="text-align:center">${c.samples}</td>`
            + `<td style="text-align:right">${cmoney(c.low)}</td><td style="text-align:right">${cmoney(c.p25)}</td>`
            + `<td style="text-align:right"><b>${cmoney(c.median)}</b></td><td style="text-align:right">${cmoney(c.p75)}</td>`
            + `<td style="text-align:right">${cmoney(c.high)}</td></tr>`).join("") + `</tbody>`;
        const h = el("div", "meta"); h.style.margin = "10px 0 4px"; h.innerHTML = `<b>Actual cost by code</b> (${cb.code_count} codes, ≥${cb.min_samples} samples each)`;
        costs.append(h, tbl);
      }
    } catch (e) { costs.textContent = `cost benchmarks failed: ${(e as Error).message}`; }
  }

  // --- Risk & Cost: prequal, COI, lien exposure, carbon, pricing, accounting export -------------
  private async renderRiskCost() {
    const root = this.root; root.innerHTML = "";
    const pid = this.host.projectId();
    if (!pid) { root.innerHTML = noProjectHtml("Risk & Cost"); return; }
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    const api = this.host.api;
    root.appendChild(this.bar("🛡 Risk & Cost", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const tone = (band: string) => band === "high" ? "var(--status-crit)" : band === "medium" ? "var(--status-warn)" : "var(--status-good)";
    const section = (title: string) => { const h = el("div", "meta"); h.style.cssText = "margin:12px 0 4px;font-weight:600"; h.textContent = title; root.appendChild(h); return h; };
    const slot = () => { const d = el("div"); d.textContent = "loading…"; root.appendChild(d); return d; };

    section("Subcontractor prequalification (Q-score, worst first)");
    const pqSlot = slot();
    section("Insurance (COI) expiry");
    const coiSlot = slot();
    section("Lien exposure (paid without an unconditional waiver)");
    const lienSlot = slot();
    section("Embodied carbon");
    const carbonSlot = slot();
    section("Takeoff pricing vs estimate");
    const priceSlot = slot();
    section("Model classification (improve QTO + carbon)");
    const classifySlot = slot();
    section("Conceptual estimate (parametric $/SF)");
    const ceWrap = el("div");
    root.appendChild(ceWrap);
    section("Materials 3-way match (PO ↔ delivery ↔ invoice)");
    const matchSlot = slot();
    section("Accounting export");
    const acct = el("div");
    const glBtn = el("a", "file-btn") as HTMLAnchorElement; glBtn.textContent = "⬇ GL (CSV)";
    glBtn.href = api.accountingGlCsvUrl(pid); glBtn.style.marginRight = "8px";
    const iifBtn = el("a", "file-btn") as HTMLAnchorElement; iifBtn.textContent = "⬇ QuickBooks bills (IIF)";
    iifBtn.href = api.accountingIifUrl(pid);
    acct.append(glBtn, iifBtn); root.appendChild(acct);

    api.prequalScores(pid).then((r) => {
      pqSlot.innerHTML = "";
      if (!r.count) { pqSlot.innerHTML = `<div class="meta">No prequalification records yet.</div>`; return; }
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Company</th><th scope="col">Trade</th><th scope="col">Score</th><th scope="col" style="text-align:left">Flags</th></tr></thead><tbody>`
        + r.subs.map((s) => `<tr><td>${s.company || ""}</td><td style="text-align:center">${s.trade || ""}</td>`
          + `<td style="text-align:center;color:${tone(s.risk_band)}"><b>${s.score}</b> ${s.risk_band}</td>`
          + `<td>${(s.flags || []).join("; ")}</td></tr>`).join("") + `</tbody>`;
      pqSlot.append(t);
    }).catch((e) => { pqSlot.textContent = `failed: ${(e as Error).message}`; });

    api.coiExpiry(pid).then((r) => {
      coiSlot.innerHTML = `<div class="meta">${r.expired_count} expired · ${r.expiring_count} expiring ≤30d</div>`;
      const rows = [...r.expired.map((x) => ({ ...x, k: "EXPIRED" })), ...r.expiring_soon.map((x) => ({ ...x, k: "soon" }))];
      if (rows.length) {
        const ul = el("ul"); ul.style.cssText = "margin:4px 0 0 16px;font-size:12px";
        rows.forEach((x) => { const li = el("li");
          li.innerHTML = `<span style="color:${x.k === "EXPIRED" ? "var(--status-crit)" : "var(--status-warn)"}">${x.k}</span> `
            + `${x.vendor || ""} — ${x.coverage_type || ""} exp ${x.expires} (${x.days}d)`; ul.append(li); });
        coiSlot.append(ul);
      }
    }).catch((e) => { coiSlot.textContent = `failed: ${(e as Error).message}`; });

    api.lienExposure(pid).then((r) => {
      lienSlot.innerHTML = `<div class="meta">Total exposure <b style="color:${r.total_lien_exposure > 0 ? "var(--status-crit)" : "var(--status-good)"}">${cmoney(r.total_lien_exposure)}</b>`
        + (r.vendors_at_risk.length ? ` · at risk: ${r.vendors_at_risk.join(", ")}` : "") + `</div>`;
      const risky = r.vendors.filter((v) => v.exposure > 0);
      if (risky.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Vendor</th><th scope="col">Paid</th><th scope="col">Unconditional waived</th><th scope="col">Exposure</th></tr></thead><tbody>`
          + risky.map((v) => `<tr><td>${v.vendor}</td><td style="text-align:right">${cmoney(v.paid)}</td>`
            + `<td style="text-align:right">${cmoney(v.waived_unconditional)}</td>`
            + `<td style="text-align:right;color:var(--status-crit)">${cmoney(v.exposure)}</td></tr>`).join("") + `</tbody>`;
        lienSlot.append(t);
      }
    }).catch((e) => { lienSlot.textContent = `failed: ${(e as Error).message}`; });

    api.projectCarbon(pid).then((r) => {
      if (!r.line_count) { carbonSlot.innerHTML = `<div class="meta">${r.message || "No material quantities."}</div>`; return; }
      const mats = Object.entries(r.by_material).slice(0, 6).map(([m, v]) => `${m}: ${(v / 1000).toFixed(1)} t`).join(" · ");
      carbonSlot.innerHTML = `<div><b>${r.total_tco2e.toLocaleString()} tCO₂e</b> embodied (A1-A3)`
        + (r.unmatched ? ` · ${r.unmatched} line(s) unmatched` : "") + `</div><div class="meta">${mats}</div>`;
    }).catch((e) => { carbonSlot.textContent = `failed: ${(e as Error).message}`; });

    api.pricingReconcile(pid).then((r) => {
      if (!r.matched) { priceSlot.innerHTML = `<div class="meta">No priced quantities (${r.pricing_source}).</div>`; return; }
      const v = r.variance_total;
      priceSlot.innerHTML = `<div>Priced <b>${cmoney(r.priced_total)}</b> (${r.pricing_source})`
        + (v != null ? ` vs estimate ${cmoney(r.estimated_total)} — variance <b style="color:${v > 0 ? "var(--status-warn)" : "var(--status-good)"}">${cmoney(v)}</b>` : "")
        + `</div>`;
    }).catch((e) => { priceSlot.textContent = `failed: ${(e as Error).message}`; });

    api.ifcClassify(pid).then((r) => {
      if (!r.count) { classifySlot.innerHTML = `<div class="meta">${r.message || "No reclassification suggestions (load a model in the Model workspace)."}</div>`; return; }
      const tops = Object.entries(r.by_target_class).slice(0, 5).map(([c, n]) => `${c}: ${n}`).join(" · ");
      classifySlot.innerHTML = `<div><b>${r.count}</b> element(s) suggested for reclassification`
        + (r.generic_elements ? ` (${r.generic_elements} generic/proxy)` : "") + `</div><div class="meta">${tops}</div>`;
    }).catch((e) => { classifySlot.textContent = `failed: ${(e as Error).message}`; });

    // conceptual estimate mini-form (developer-side $/SF from building params)
    void api.conceptualCatalog().then((cat) => {
      ceWrap.innerHTML = "";
      const type = el("select", "portal-filter") as HTMLSelectElement; type.style.cssText = "margin:2px 4px 2px 0";
      type.setAttribute("aria-label", "Building type");
      type.innerHTML = cat.building_types.map((t) => `<option value="${t}">${t}</option>`).join("");
      const region = el("select", "portal-filter") as HTMLSelectElement; region.style.cssText = "margin:2px 4px";
      region.setAttribute("aria-label", "Region");
      region.innerHTML = cat.regions.map((rg) => `<option value="${rg}"${rg === "us_average" ? " selected" : ""}>${rg}</option>`).join("");
      const gfa = el("input", "portal-filter") as HTMLInputElement; gfa.type = "number"; gfa.placeholder = "GFA (sf)"; gfa.setAttribute("aria-label", "Gross floor area (sf)"); gfa.style.cssText = "width:110px;margin:2px 4px";
      const go = el("button", "file-btn") as HTMLButtonElement; go.textContent = "Estimate";
      const out = el("div"); out.style.marginTop = "6px";
      go.onclick = async () => {
        if (!Number(gfa.value)) { toast("Enter GFA", "error"); return; }
        out.textContent = "estimating…";
        try {
          const r = await api.conceptualEstimate(pid, { building_type: type.value, region: region.value, gfa_sf: Number(gfa.value) });
          if (r.error) { out.textContent = r.error; return; }
          out.innerHTML = `<div><b>${cmoney(r.total_cost)}</b> total (${cmoney(r.range.low)}–${cmoney(r.range.high)}) `
            + `· ${cmoney(r.metrics.total_per_sf)}/sf · hard ${cmoney(r.hard_cost)} + soft ${cmoney(r.soft_cost)}</div>`;
        } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
      };
      ceWrap.append(type, region, gfa, go, out);
    }).catch(() => { ceWrap.innerHTML = `<div class="meta">conceptual estimator unavailable</div>`; });

    api.procurementThreeWayMatch(pid).then((r) => {
      if (!r.po_count) { matchSlot.innerHTML = `<div class="meta">No purchase orders (commitments) yet.</div>`; return; }
      matchSlot.innerHTML = `<div class="meta">${r.po_count} PO(s)`
        + (r.flagged.length ? ` · <span style="color:var(--status-warn)">${r.flagged.length} need review</span>` : " · all clear") + `</div>`;
      const flagged = r.pos.filter((p) => p.status === "review");
      if (flagged.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:11px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">PO</th><th scope="col">Vendor</th><th scope="col">PO</th><th scope="col">Recd</th><th scope="col">Invoiced</th><th scope="col" style="text-align:left">Issue</th></tr></thead><tbody>`
          + flagged.map((p) => `<tr><td>${p.po}</td><td>${p.vendor || ""}</td><td style="text-align:right">${cmoney(p.po_amount)}</td>`
            + `<td style="text-align:center">${p.received}</td><td style="text-align:right;color:${p.variance > 0 ? "var(--status-crit)" : "inherit"}">${cmoney(p.invoiced)}</td>`
            + `<td>${(p.flags || []).join("; ")}</td></tr>`).join("") + `</tbody>`;
        matchSlot.append(t);
      }
    }).catch((e) => { matchSlot.textContent = `failed: ${(e as Error).message}`; });
  }

  // --- Land Screening: filter a parcel set → max-buildable envelope + cost ----------------------
  private async renderLandScreen() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("🗺️ Land Screening", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Screen a parcel set by size / zoning / flood / utilities and rank by max-buildable "
      + "opportunity — each parcel gets an envelope (area × FAR) and a conceptual cost. Paste parcels as "
      + "JSON (from a GIS export). Nationwide parcel data is an optional paid connector (Settings).";
    root.appendChild(intro);
    const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
    ta.placeholder = '[{"id":"A","acres":5,"zoning":"MU","flood_zone":"X","sewer":true,"price":2000000,"far":2.0}]';
    ta.setAttribute("aria-label", "Parcels as JSON");
    ta.style.cssText = "width:100%;min-height:90px;margin:4px 0;font-family:monospace;font-size:11px";
    const row = el("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
    const minAc = el("input", "portal-filter") as HTMLInputElement; minAc.type = "number"; minAc.placeholder = "min acres"; minAc.setAttribute("aria-label", "Minimum acres"); minAc.style.width = "90px";
    const zoning = el("input", "portal-filter") as HTMLInputElement; zoning.placeholder = "zoning (comma)"; zoning.setAttribute("aria-label", "Allowed zoning (comma-separated)"); zoning.style.width = "130px";
    const far = el("input", "portal-filter") as HTMLInputElement; far.type = "number"; far.placeholder = "assume FAR"; far.setAttribute("aria-label", "Assumed FAR"); far.style.width = "90px";
    const btype = el("input", "portal-filter") as HTMLInputElement; btype.placeholder = "building type"; btype.setAttribute("aria-label", "Building type"); btype.value = "multifamily"; btype.style.width = "120px";
    const flood = el("label", "meta") as HTMLLabelElement; const floodCk = el("input") as HTMLInputElement; floodCk.type = "checkbox"; floodCk.checked = true;
    flood.append(floodCk, document.createTextNode(" exclude flood"));
    row.append(minAc, zoning, far, btype, flood);
    const go = el("button", "file-btn") as HTMLButtonElement; go.textContent = "Screen";
    const out = el("div"); out.style.marginTop = "8px";
    go.onclick = async () => {
      let parcelList: unknown[];
      try { parcelList = JSON.parse(ta.value || "[]"); if (!Array.isArray(parcelList)) throw new Error("expected an array"); }
      catch (e) { toast(`Invalid JSON: ${(e as Error).message}`, "error"); return; }
      const criteria: Record<string, unknown> = { building_type: btype.value || undefined, exclude_flood: floodCk.checked };
      if (minAc.value) criteria.min_acres = Number(minAc.value);
      if (far.value) criteria.assume_far = Number(far.value);
      if (zoning.value.trim()) criteria.zoning_in = zoning.value.split(",").map((z) => z.trim()).filter(Boolean);
      out.textContent = "screening…";
      try {
        const r = await this.host.api.parcelsScreen(parcelList, criteria);
        out.innerHTML = `<div class="meta"><b>${r.match_count}</b> of ${r.screened} parcels pass</div>`;
        if (r.matches.length) {
          const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:12px;margin-top:4px";
          tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Parcel</th><th scope="col">Acres</th><th scope="col">Zoning</th><th scope="col">Max GFA</th><th scope="col">Concept. cost</th><th scope="col">Land $/bldbl sf</th></tr></thead><tbody>`
            + r.matches.map((m) => `<tr><td>${m.id}</td><td style="text-align:center">${m.acres}</td><td style="text-align:center">${m.zoning || ""}</td>`
              + `<td style="text-align:right">${m.buildable.max_gfa_sf ? m.buildable.max_gfa_sf.toLocaleString() : "—"}</td>`
              + `<td style="text-align:right">${m.buildable.conceptual_cost ? cmoney(m.buildable.conceptual_cost) : "—"}</td>`
              + `<td style="text-align:right">${m.buildable.land_cost_per_buildable_sf ? cmoney(m.buildable.land_cost_per_buildable_sf) : "—"}</td></tr>`).join("") + `</tbody>`;
          out.append(tbl);
        }
        if (r.rejected.length) { const rj = el("div", "meta"); rj.style.marginTop = "6px";
          rj.textContent = "Rejected: " + r.rejected.map((x) => `${x.id} (${x.failed[0]})`).join(", "); out.append(rj); }
      } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
    };
    root.append(ta, row, go, out);
  }

  // --- Project Lifecycle: RIBA/AIA design phases + gate sign-off + soft-cost allocation ----------
  private async renderLifecycle() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("🧭 Project Lifecycle", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const pid = this.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Project Lifecycle")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "The architect/engineer design-to-turnover lifecycle: RIBA Plan of Work 0–7 "
      + "mapped to AIA phases (SD · DD · CD · CA). Each phase is a gate the Architect + Owner sign off "
      + "before advancing, with its A/E design-fee share and ISO-19650 information status.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    const load = async () => {
      let lc;
      try { lc = await this.host.api.lifecycle(pid); }
      catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
      body.innerHTML = "";
      if (!lc.seeded || !lc.phases.length) {
        const seedBtn = el("button", "file-btn") as HTMLButtonElement;
        seedBtn.textContent = "Seed design phases";
        seedBtn.onclick = () => void this.host.api.lifecycleSeed(pid)
          .then(() => { toast("Design phases seeded", "success"); void load(); })
          .catch((e) => toast((e as Error).message, "error"));
        const note = el("div", "meta"); note.textContent = "No design phases yet for this project.";
        note.style.marginBottom = "6px";
        body.append(note, seedBtn);
        return;
      }
      if (lc.current_stage) {
        const cur = el("div", "meta"); cur.style.margin = "2px 0 8px";
        cur.innerHTML = `Current stage: <b>${lc.current_stage.riba_stage}</b> — ${lc.current_stage.aia_phase}`;
        body.append(cur);
      }
      const STATE_TONE: Record<string, string> = { approved: "var(--status-good)", in_review: "var(--status-warn)",
        returned: "var(--status-crit)", active: "var(--muted)" };
      for (const ph of lc.phases) {
        const card = el("div", "dash-card"); card.style.cssText = `border-left:3px solid ${STATE_TONE[ph.state] || "var(--muted)"};margin:6px 0`;
        const fee = ph.design_fee_amount ? ` · A/E fee ${cmoney(ph.design_fee_amount)}` : "";
        card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">`
          + `<div><b>${ph.riba_stage}</b> <span class="meta">→ ${ph.aia_phase}</span></div>`
          + `<span class="badge">${ph.state}</span></div>`
          + `<div class="meta" style="margin-top:2px">Fee ${ph.design_fee_pct || 0}%${fee} · ${ph.iso_status || ""}</div>`
          + (ph.deliverables.length ? `<ul style="margin:4px 0 0 16px;font-size:12px">${ph.deliverables.map((d) => `<li>${d}</li>`).join("")}</ul>` : "");
        // gate actions
        const actions = el("div"); actions.style.cssText = "margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center";
        const act = (label: string, action: string, pre?: () => Promise<boolean>) => {
          const b = el("button", "file-btn") as HTMLButtonElement; b.textContent = label;
          b.onclick = async () => {
            if (pre && !(await pre())) return;
            try { await this.host.api.transitionRecord(pid, "project_phase", ph.id, action);
              toast(`${label} ✓`, "success"); void load(); }
            catch (e) { toast((e as Error).message, "error"); }
          };
          actions.append(b);
        };
        if (ph.state === "active") act("Submit for gate review", "submit_for_review");
        if (ph.state === "in_review") {
          act("Approve gate (Architect/Owner)", "approve_gate", async () => {
            const v = await promptModal("Gate sign-off",
              [{ name: "name", label: "Certifying name (Architect / Owner)", required: true }], "Approve");
            if (!v) return false;
            await this.host.api.updateModuleRecord(pid, "project_phase", ph.id, { signed_by: v.name });
            return true;
          });
          act("Return", "return");
        }
        if (ph.state === "returned") act("Revise", "revise");
        if (ph.signed_by) { const s = el("span", "meta"); s.textContent = `signed: ${ph.signed_by}`; actions.append(s); }
        card.append(actions);
        body.append(card);
      }
      // soft-cost allocation
      if (lc.soft_costs) {
        const sc = el("div"); sc.style.marginTop = "12px";
        sc.innerHTML = `<div class="meta"><b>Itemized soft costs</b> — total ${cmoney(lc.soft_costs.total)} (of ${cmoney(lc.hard_cost)} hard)</div>`;
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin-top:4px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Soft cost</th><th scope="col">% of hard</th><th scope="col">Amount</th></tr></thead><tbody>`
          + lc.soft_costs.lines.map((x) => `<tr><td>${x.label}</td><td style="text-align:center">${x.pct_of_hard}%</td>`
            + `<td style="text-align:right">${cmoney(x.amount)}</td></tr>`).join("") + `</tbody>`;
        sc.append(t); body.append(sc);
      }
    };
    await load();
  }

  // --- Diligence & Entitlements: pre-acquisition go/no-go rollup --------------------------------
  private async renderDiligence() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("📜 Diligence & Entitlements", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const pid = this.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Diligence & Entitlements")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Pre-acquisition readiness: due-diligence studies (title/ALTA, Phase I ESA, "
      + "geotech, utilities, traffic, …) and entitlement applications (rezoning, site plan, variances) "
      + "rolled into a go/no-go before releasing contingencies. Add records in the Acquisition section.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let rd;
    try { rd = await this.host.api.diligenceReadiness(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    // go / no-go banner
    const dd = rd.due_diligence; const en = rd.entitlements;
    const banner = el("div", "dash-card");
    banner.style.cssText = `border-left:4px solid ${rd.go ? "var(--status-good)" : "var(--status-warn)"};margin-bottom:8px`;
    banner.innerHTML = `<b>${rd.go ? "✅ GO — diligence cleared, entitlements approved"
      : "⏳ NOT READY — open items below"}</b>`
      + `<div class="meta">Due diligence: ${dd.cleared}/${dd.total} cleared · ${dd.flagged} flagged · `
      + `Entitlements: ${en.approved} approved · ${en.pending} pending · ${en.denied} denied</div>`;
    body.append(banner);
    // high-risk flags
    if (dd.high_risk.length) {
      const hr = el("div", "dash-card"); hr.style.cssText = "border-left:3px solid var(--status-crit);margin:6px 0";
      hr.innerHTML = `<b>High-risk findings</b><ul style="margin:4px 0 0 16px;font-size:12px">`
        + dd.high_risk.map((x) => `<li>${esc(x.ref)} ${esc(x.item || "")} — <b>${esc(x.risk)}</b> (${esc(x.category)})</li>`).join("") + `</ul>`;
      body.append(hr);
    }
    // DD by category
    const cats = Object.entries(dd.by_category);
    if (cats.length) {
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin:6px 0";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Category</th><th scope="col">Cleared</th>`
        + `<th scope="col">Flagged</th><th scope="col">Open</th></tr></thead><tbody>`
        + cats.map(([c, v]) => `<tr><td>${esc(c)}</td><td style="text-align:center">${v.cleared}/${v.total}</td>`
          + `<td style="text-align:center">${v.flagged || ""}</td><td style="text-align:center">${v.open || ""}</td></tr>`).join("")
        + `</tbody>`;
      body.append(t);
    } else {
      const none = el("div", "meta"); none.textContent = "No due-diligence items yet — add them under Acquisition → Due Diligence.";
      body.append(none);
    }
    // expiring approvals
    if (en.expiring_within_180d.length) {
      const ex = el("div", "dash-card"); ex.style.cssText = "border-left:3px solid var(--status-warn);margin:6px 0";
      ex.innerHTML = `<b>Approvals expiring ≤180 days</b><ul style="margin:4px 0 0 16px;font-size:12px">`
        + en.expiring_within_180d.map((x) => `<li>${esc(x.ref)} ${esc(x.application || "")} — expires ${esc(x.expires)}</li>`).join("") + `</ul>`;
      body.append(ex);
    }
  }

  // --- ESG & POE: asset sustainability scorecard + Stage-7 feedback loop ------------------------
  private async renderEsg() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("🌱 ESG & Post-Occupancy", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const pid = this.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("ESG & POE")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "The asset's sustainability scorecard, computed locally: metered energy (EUI), "
      + "operational greenhouse gas by scope, water, certification tracking — plus post-occupancy "
      + "evaluations closing the loop between design intent and measured performance.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let s;
    try { s = await this.host.api.esgSummary(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    const perf = s.performance;
    // KPI cards
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    const card = (label: string, value: string) => {
      const c = el("div", "dash-card"); c.style.minWidth = "125px";
      c.innerHTML = `<div style="font-size:20px;font-weight:600">${value}</div><div class="meta">${label}</div>`;
      return c;
    };
    cards.append(
      card("EUI (kBtu/sf/yr)", perf.energy.eui_kbtu_sf_yr != null ? String(perf.energy.eui_kbtu_sf_yr) : "—"),
      card("GHG total (tCO₂e)", String(perf.ghg.total_tco2e)),
      card("Scope 1 / Scope 2", `${perf.ghg.scope1_tco2e} / ${perf.ghg.scope2_tco2e}`),
      card("water (gal)", perf.water.gallons.toLocaleString()),
      card("cert points", `${s.certifications.points_achieved}/${s.certifications.points_targeted}`));
    body.append(cards);
    // GHG detail
    const g = el("div", "dash-card"); g.style.marginBottom = "8px";
    g.innerHTML = `<b>Operational GHG</b><div class="meta">${esc(perf.ghg.note)}</div>`
      + `<div class="meta">Intensity: ${perf.ghg.intensity_kgco2e_sf != null ? `${perf.ghg.intensity_kgco2e_sf} kgCO₂e/sf` : "— (needs GFA)"} · `
      + `grid factor ${perf.ghg.grid_factor_kgco2e_kwh} kgCO₂e/kWh · ${s.data_coverage.meter_months} meter month(s)</div>`;
    body.append(g);
    // POE
    const p = s.poe.latest;
    const pc = el("div", "dash-card"); pc.style.marginBottom = "8px";
    if (p) {
      const gap = p.eui_gap_pct;
      pc.innerHTML = `<b>Post-occupancy evaluation</b> <span class="meta">(${s.poe.reported}/${s.poe.count} reported)</span>`
        + `<div class="meta">${esc(p.ref)} · ${esc(p.level || "")} · ${esc(p.state)}`
        + (p.satisfaction_score != null ? ` · satisfaction ${p.satisfaction_score}/7` : "") + `</div>`
        + `<div class="meta">Design EUI ${p.design_eui ?? "—"} → actual ${p.actual_eui ?? "—"}`
        + (gap != null ? ` · <b style="color:var(${gap > 10 ? "--status-warn" : "--status-good"})">${gap > 0 ? "+" : ""}${gap}% vs design</b>` : "")
        + `</div>`;
    } else {
      pc.innerHTML = `<b>Post-occupancy evaluation</b><div class="meta">None yet — add one under `
        + `Operations → Post-Occupancy Evaluations (level 1 indicative → 3 diagnostic; a reported POE `
        + `compares design EUI against the metered actual).</div>`;
    }
    body.append(pc);
    // report link
    const rb = el("div");
    const a = document.createElement("a"); a.className = "portal-btn"; a.textContent = "⬇ ESG summary (PDF)";
    a.href = this.host.api.reportUrl(pid, "esg", "pdf"); a.target = "_blank"; a.rel = "noopener";
    rb.append(a); body.append(rb);
  }

  // --- CDE / Standards: ISO 19650 container discipline + requirements register ------------------
  private async renderStandards() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("🗂 CDE / Standards (ISO 19650)", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const pid = this.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("CDE / Standards")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Information management to ISO 19650: deliverables move through the Common "
      + "Data Environment (Work-in-progress → Shared → Published → Archived) with suitability codes "
      + "and revisions, and the appointment carries its information requirements (EIR, BEP, AIR). "
      + "Manage records under Information Management → Information Containers / Requirements.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let st; let reg;
    try { st = await this.host.api.cdeStatus(pid); reg = await this.host.api.infoRequirementsRegister(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";
    // container state distribution
    const stages: [string, string][] = [["wip", "WIP"], ["shared", "Shared"], ["published", "Published"], ["archived", "Archived"]];
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    for (const [k, label] of stages) {
      const c = el("div", "dash-card"); c.style.minWidth = "90px";
      c.innerHTML = `<div style="font-size:20px;font-weight:600">${st.by_state[k] ?? 0}</div><div class="meta">${label}</div>`;
      cards.append(c);
    }
    body.append(cards);
    // CDE discipline metrics
    const d = st.discipline;
    const disc = el("div", "dash-card"); disc.style.marginBottom = "8px";
    const pct = (v: number | null) => v != null ? `${v}%` : "—";
    disc.innerHTML = `<b>CDE discipline</b>`
      + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
      + `<tr><td>Revision control</td><td class="num">${pct(d.revision_control_pct)}</td></tr>`
      + `<tr><td>Approval status (past WIP)</td><td class="num">${pct(d.approval_status_pct)}</td></tr>`
      + `<tr><td>Metadata completeness</td><td class="num">${pct(d.metadata_completeness_pct)}</td></tr>`
      + `</table>`;
    body.append(disc);
    // requirements register + core coverage
    const rc = el("div", "dash-card");
    const cov = reg.core_coverage;
    rc.style.cssText = `border-left:3px solid var(${cov.complete ? "--status-good" : "--status-warn"});margin-bottom:8px`;
    rc.innerHTML = `<b>Information requirements</b> <span class="meta">(${reg.total})</span>`
      + `<div class="meta">${cov.complete ? "✅ core documents on file (EIR, BEP, AIR)"
        : `⏳ missing core: ${cov.missing.map(esc).join(", ")}`}</div>`;
    const types = Object.entries(reg.by_type);
    if (types.length) {
      rc.innerHTML += `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
        + `<tr><th style="text-align:left">Type</th><th class="num">Issued</th><th class="num">Draft</th></tr>`
        + types.map(([t, v]) => `<tr><td>${esc(t)}</td><td class="num">${v.issued}</td><td class="num">${v.draft}</td></tr>`).join("")
        + `</table>`;
    }
    body.append(rc);
    if (!st.total && !reg.total) {
      const none = el("div", "meta");
      none.textContent = "No containers or requirements yet — add them under Information Management.";
      body.append(none);
    }

    // openBIM model quality — only meaningful with a model loaded; degrades to a hint on 404.
    const q = el("div", "dash-card"); q.style.marginTop = "8px";
    q.innerHTML = `<b>openBIM model quality</b> <span class="meta">scoring the loaded model…</span>`;
    body.append(q);
    try {
      const oq = await this.host.api.openbimQuality(pid, "fire_life_safety");
      const eh = oq.export_health, lo = oq.loin, bs = oq.bsdd;
      const grade = (g: string) => g === "pass" ? "✅" : g === "warn" ? "⚠️" : g === "fail" ? "❌" : "—";
      q.innerHTML = `<b>openBIM model quality</b>`
        + `<table class="fin-table" style="width:100%;font-size:12px;margin-top:4px">`
        + `<tr><td>LOIN — avg ${lo.avg_score}/${lo.max_score}, coordinated</td><td class="num">${lo.coordinated_pct ?? "—"}%</td></tr>`
        + (oq.ids ? `<tr><td>IDS compliance (fire &amp; life safety)</td><td class="num">${oq.ids.compliance_pct ?? "—"}%</td></tr>` : "")
        + `<tr><td>bSDD / classification coverage</td><td class="num">${bs.alignment_pct ?? "—"}%</td></tr>`
        + eh.checks.map((c) => `<tr><td>${grade(c.grade)} ${esc(c.label)}</td><td class="num">${c.pct ?? "—"}%</td></tr>`).join("")
        + `</table>`;
    } catch {
      q.innerHTML = `<b>openBIM model quality</b><div class="meta">Load a model (Model workspace) to `
        + `score LOIN, IDS compliance, export health and bSDD alignment.</div>`;
    }
  }

  // --- Operations: CMMS — work orders, PM generation, maintenance KPIs --------------------------
  private async renderOperations() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("🔧 Operations — Maintenance", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const pid = this.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Operations")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Post-turnover maintenance: PM schedules generate preventive work orders "
      + "before failures happen; KPIs show whether the building is run proactively (PM compliance) "
      + "or reactively (MTTR, overdue backlog). Manage records under Operations → Work Orders / PM Schedules.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    const load = async () => {
      body.innerHTML = "";
      let k; let wos;
      try {
        k = await this.host.api.cmmsKpis(pid);
        wos = await this.host.api.moduleRecords(pid, "work_order");
      } catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
      // KPI cards
      const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
      const card = (label: string, value: string, warn = false) => {
        const c = el("div", "dash-card"); c.style.cssText = `min-width:110px${warn ? ";border-left:3px solid var(--status-warn)" : ""}`;
        c.innerHTML = `<div style="font-size:20px;font-weight:600">${value}</div><div class="meta">${label}</div>`;
        return c;
      };
      cards.append(card("open work orders", String(k.open)),
        card("overdue", String(k.overdue), k.overdue > 0),
        card("PM compliance", k.pm_compliance_pct != null ? `${k.pm_compliance_pct}%` : "—"),
        card("MTTR (days)", k.mttr_days != null ? String(k.mttr_days) : "—"),
        card("completed", String(k.completed)));
      body.append(cards);
      // generate-PM action
      const act = el("div"); act.style.marginBottom = "8px";
      const gen = el("button", "portal-btn") as HTMLButtonElement;
      gen.textContent = "Generate PM work orders";
      gen.title = "Create preventive work orders for every active PM schedule that is due";
      gen.onclick = async () => {
        gen.disabled = true;
        try {
          const r = await this.host.api.cmmsGeneratePm(pid);
          toast(r.generated ? `${r.generated} PM work order(s) created` : "No PM schedules due", "success");
          void load();
        } catch (e) { toast(`failed: ${(e as Error).message}`, "error"); gen.disabled = false; }
      };
      act.append(gen); body.append(act);
      // open-by-priority chart
      const pri = Object.entries(k.open_by_priority);
      if (pri.length) {
        const wrap = el("div", "dash-card"); wrap.style.marginBottom = "8px";
        wrap.innerHTML = groupedBar(pri.map(([p, n]) => ({ label: p, bars: [{ name: "open", value: n }] })),
          { title: "Open work orders by priority", fmt: (n) => String(Math.round(n)) });
        body.append(wrap);
      }
      // open WO table
      const open = wos.filter((w) => w.workflow_state !== "completed" && w.workflow_state !== "verified");
      if (open.length) {
        const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
        t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Ref</th><th scope="col" style="text-align:left">Work order</th>`
          + `<th scope="col">Type</th><th scope="col">Priority</th><th scope="col">Due</th><th scope="col">State</th></tr></thead><tbody>`
          + open.slice(0, 50).map((w) => {
            const d = (w.data || {}) as Record<string, string>;
            return `<tr><td>${esc(w.ref || "")}</td><td>${esc(d.subject || "")}</td>`
              + `<td style="text-align:center">${esc(d.wo_type || "")}</td><td style="text-align:center">${esc(d.priority || "")}</td>`
              + `<td style="text-align:center">${esc(d.due_date || "")}</td><td style="text-align:center">${esc(w.workflow_state || "")}</td></tr>`;
          }).join("") + `</tbody>`;
        body.append(t);
      } else {
        const none = el("div", "meta");
        none.textContent = "No open work orders — add corrective ones under Operations → Work Orders, or set up PM Schedules and generate.";
        body.append(none);
      }
    };
    await load();
  }

  // --- Energy: metered utilities — EUI, monthly trend, cost by utility --------------------------
  private async renderEnergy() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("⚡ Energy — Metered Utilities", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const pid = this.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Energy")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Operational energy from meter readings (entered manually or CSV-imported "
      + "under Operations → Meter Readings), converted to site kBtu and normalized to EUI "
      + "(kBtu/sf/yr) — the benchmarking currency for building performance. Fully offline.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    let e0; let bs;
    try {
      e0 = await this.host.api.energyActual(pid);
      bs = await this.host.api.energyBenchmarkStatus();
    } catch (err) { body.textContent = `failed: ${(err as Error).message}`; return; }
    body.innerHTML = "";
    // KPI cards
    const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px";
    const card = (label: string, value: string) => {
      const c = el("div", "dash-card"); c.style.minWidth = "120px";
      c.innerHTML = `<div style="font-size:20px;font-weight:600">${value}</div><div class="meta">${label}</div>`;
      return c;
    };
    cards.append(card("EUI (kBtu/sf/yr)", e0.eui_kbtu_sf_yr != null ? String(e0.eui_kbtu_sf_yr) : "—"),
      card("site energy (kBtu)", e0.total_kbtu.toLocaleString()),
      card("utility cost", cmoney(e0.total_cost)),
      card("water (gal)", e0.water_gallons.toLocaleString()),
      card("months covered", String(e0.months_covered)));
    body.append(cards);
    if (e0.eui_kbtu_sf_yr == null && e0.total_kbtu > 0) {
      const hint = el("div", "meta"); hint.style.marginBottom = "8px";
      hint.textContent = "EUI needs a gross floor area — load the model (space quantities) or record GFA on the project.";
      body.append(hint);
    }
    // monthly trend
    if (e0.monthly.length > 1) {
      const wrap = el("div", "dash-card"); wrap.style.marginBottom = "8px";
      wrap.innerHTML = lineChart([{ name: "site kBtu", values: e0.monthly.map((m) => m.kbtu) }],
        { title: "Monthly site energy (kBtu)", xlabels: e0.monthly.map((m) => m.month),
          fmt: (n) => n.toLocaleString() });
      body.append(wrap);
    }
    // by-utility table
    const utils = Object.entries(e0.by_utility);
    if (utils.length) {
      const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px;margin:6px 0";
      t.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Utility</th><th scope="col">Consumption</th>`
        + `<th scope="col">kBtu</th><th scope="col">Cost</th></tr></thead><tbody>`
        + utils.map(([u, v]) => `<tr><td>${esc(u)}</td><td style="text-align:right">${v.consumption.toLocaleString()} ${esc(v.unit)}</td>`
          + `<td style="text-align:right">${v.kbtu.toLocaleString()}</td><td style="text-align:right">${cmoney(v.cost)}</td></tr>`).join("")
        + `</tbody>`;
      body.append(t);
    } else {
      const none = el("div", "meta");
      none.textContent = "No meter readings yet — add meters and readings under Operations, or import a CSV.";
      body.append(none);
    }
    // benchmarking bridge status (honest, flagged)
    const b = el("div", "meta"); b.style.marginTop = "8px"; b.textContent = bs.message;
    body.append(b);
  }

  // --- Turnover: substantial completion (G704) + architect punch-list sign-off ------------------
  private async renderTurnover() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("🏁 Turnover — Substantial Completion", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const pid = this.host.projectId();
    if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Turnover")); return; }
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Certify substantial completion (AIA G704): the Architect signs off the punch "
      + "list, the current model version is stamped as the record (as-built) model, and the signed "
      + "certificate joins the turnover package.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading…"; root.appendChild(body);
    const load = async () => {
      body.innerHTML = "";
      let rd; let certs;
      try {
        rd = await this.host.api.turnoverReadiness(pid);
        certs = (await this.host.api.moduleRecords(pid, "completion_certificate"))
          .filter((r) => (r.data as { type?: string } | undefined)?.type === "Substantial");
      } catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
      // readiness
      const p = rd.punch;
      const rdiv = el("div", "dash-card"); rdiv.style.marginBottom = "8px";
      rdiv.innerHTML = `<div class="meta"><b>Punch list</b>: ${p.count} item(s) · ${p.open} open · ${p.verified} verified`
        + (p.complete_pct != null ? ` · ${p.complete_pct}% complete` : "") + `</div>`
        + `<div class="meta">Latest model version: <b>${rd.latest_model_version ?? "—"}</b> · `
        + `${rd.ready_for_substantial_completion ? "<span style=\"color:var(--status-good)\">ready to certify</span>" : "<span style=\"color:var(--status-warn)\">prepare a punch list first</span>"}</div>`;
      body.append(rdiv);
      // substantial-completion certificate(s)
      if (!certs.length) {
        const note = el("div", "meta"); note.textContent = "No substantial-completion certificate yet.";
        const mk = el("button", "file-btn") as HTMLButtonElement; mk.textContent = "Create certificate";
        mk.onclick = () => void this.host.api.createModuleRecord(pid, "completion_certificate",
          { data: { subject: "Substantial Completion", type: "Substantial" } })
          .then(() => { toast("Certificate created", "success"); void load(); })
          .catch((e) => toast((e as Error).message, "error"));
        note.style.marginBottom = "6px"; body.append(note, mk);
        return;
      }
      for (const cert of certs) {
        const d = (cert.data || {}) as { signatures?: { party: string; certifies?: boolean }[]; record_model_version?: number };
        const certified = (d.signatures || []).some((s) => s.party === "Architect" && s.certifies);
        const card = el("div", "dash-card"); card.style.cssText = "margin:6px 0";
        card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">`
          + `<b>${cert.ref || "Certificate"}</b><span class="badge">${cert.workflow_state}</span></div>`
          + `<div class="meta">${certified ? `✅ Architect certified · record model v${d.record_model_version ?? "—"}` : "Awaiting architect certification"}</div>`;
        const actions = el("div"); actions.style.cssText = "margin-top:6px;display:flex;gap:6px;flex-wrap:wrap";
        if (!certified) {
          const cbtn = el("button", "file-btn") as HTMLButtonElement; cbtn.textContent = "Architect: certify substantial completion";
          cbtn.onclick = async () => {
            if (!rd!.ready_for_substantial_completion) { toast("Prepare a punch list first", "error"); return; }
            const v = await promptModal("Certify substantial completion (G704)", [
              { name: "arch", label: "Certifying Architect (name / license)", required: true },
              { name: "owner", label: "Owner signatory (optional)" },
            ], "Certify");
            if (!v) return;
            try { await this.host.api.turnoverCertify(pid, cert.id, v.arch, v.owner || undefined);
              toast("Substantial completion certified", "success"); void load(); }
            catch (e) { toast((e as Error).message, "error"); }
          };
          actions.append(cbtn);
        }
        const dl = el("a", "file-btn") as HTMLAnchorElement; dl.textContent = "⬇ G704 certificate";
        dl.href = this.host.api.g704Url(pid, cert.id); dl.target = "_blank";
        actions.append(dl);
        card.append(actions); body.append(card);
      }
    };
    await load();
  }

  // --- IDS Requirements: author buildingSMART IDS + EIR from templates --------------------------
  private async renderIds() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("📋 IDS Requirements", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const intro = el("div", "meta"); intro.style.marginBottom = "8px";
    intro.textContent = "Author information requirements: pick a use case, download a standards-valid "
      + "buildingSMART IDS file to check delivered models against, plus an EIR document for the BIM "
      + "contract. Validate a model against an IDS from the Model workspace.";
    root.appendChild(intro);
    const body = el("div"); body.textContent = "loading templates…"; root.appendChild(body);
    try {
      const cat = await this.host.api.idsTemplates();
      body.innerHTML = "";
      const pick = el("select", "portal-filter") as HTMLSelectElement; pick.style.cssText = "margin:4px 0";
      pick.setAttribute("aria-label", "IDS use case");
      pick.innerHTML = cat.use_cases.map((u) => `<option value="${u.key}">${u.label}</option>`).join("");
      const detail = el("div"); detail.style.margin = "8px 0";
      const showDetail = () => {
        const uc = cat.use_cases.find((u) => u.key === pick.value);
        const groups = uc ? uc.groups : [];
        const els = cat.elements.filter((e) => groups.includes(e.key));
        detail.innerHTML = `<div class="meta">Requires data on: ${els.map((e) => e.label).join(", ")}</div>`;
        const tbl = el("table", "portal-table") as HTMLTableElement; tbl.style.cssText = "width:100%;font-size:11px;margin-top:4px";
        tbl.innerHTML = `<thead><tr><th scope="col" style="text-align:left">Element</th><th scope="col" style="text-align:left">Property set</th><th scope="col" style="text-align:left">Property</th></tr></thead><tbody>`
          + els.flatMap((e) => e.requirements.map((r) => `<tr><td>${e.ifc_class}</td><td>${r.pset}</td><td>${r.property}</td></tr>`)).join("") + `</tbody>`;
        detail.append(tbl);
      };
      pick.onchange = showDetail;
      const dlIds = el("button", "file-btn") as HTMLButtonElement; dlIds.textContent = "⬇ Download IDS";
      dlIds.style.marginRight = "8px";
      dlIds.onclick = () => void this.host.api.idsDownload("build", { use_case: pick.value }, `${pick.value}.ids`)
        .then(() => toast("IDS downloaded", "success")).catch((e) => toast((e as Error).message, "error"));
      const dlEir = el("button", "file-btn") as HTMLButtonElement; dlEir.textContent = "⬇ Download EIR (contract)";
      dlEir.onclick = () => void this.host.api.idsDownload("eir", { use_case: pick.value }, `EIR-${pick.value}.md`)
        .then(() => toast("EIR downloaded", "success")).catch((e) => toast((e as Error).message, "error"));
      body.append(pick, detail, dlIds, dlEir);
      showDetail();
    } catch (e) { body.textContent = `failed: ${(e as Error).message}`; }
  }

  private renderContractFindings(out: HTMLElement, r: { findings: { clause: string; severity: string; category: string;
      rationale: string; suggested_action: string; snippet: string }[]; counts: Record<string, number>; source: string; message?: string }, pid: string) {
    out.innerHTML = "";
    const head = document.createElement("div"); head.className = "meta"; head.style.marginBottom = "6px";
    head.innerHTML = `<b>${r.findings.length}</b> flagged`
      + ` · <span style="color:${PortalUI.SEV_TONE.high}">${r.counts.high || 0} high</span>`
      + ` · <span style="color:${PortalUI.SEV_TONE.medium}">${r.counts.medium || 0} med</span>`
      + ` · <span style="color:${PortalUI.SEV_TONE.low}">${r.counts.low || 0} low</span>`
      + `  <span class="badge">${r.source === "claude" ? "AI" : "rules"}</span>`;
    out.appendChild(head);
    if (r.message) { const m = document.createElement("div"); m.className = "meta"; m.textContent = r.message; out.appendChild(m); }
    for (const f of r.findings) {
      const tone = PortalUI.SEV_TONE[f.severity] || "var(--muted)";
      const card = document.createElement("div"); card.className = "dash-card"; card.style.cssText = `border-left:3px solid ${tone};margin:6px 0`;
      card.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center">`
        + `<b>${esc(f.clause)}</b><span class="ball-badge" style="background:${tone}22;color:${tone};border-color:${tone}">${esc(f.severity)}</span></div>`
        + `<div class="meta" style="margin:3px 0">${esc(f.rationale)}</div>`
        + `<div style="font-size:12px"><b>Suggested:</b> ${esc(f.suggested_action)}</div>`
        + (f.snippet ? `<div class="meta" style="font-style:italic;margin-top:3px">“${esc(f.snippet)}”</div>` : "");
      const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;margin-top:6px";
      const add = document.createElement("button"); add.className = "tool-btn"; add.textContent = "＋ Add to Risk Register";
      add.onclick = async () => {
        const sev = f.severity === "high" ? "High" : f.severity === "medium" ? "Medium" : "Low";
        try {
          await this.host.api.createModuleRecord(pid, "risk", { data: {
            title: `${f.category}: ${f.clause}`, category: "Other", probability: sev, impact: sev,
            response_strategy: "Mitigate", mitigation: f.suggested_action, trigger: f.snippet } });
          add.textContent = "✓ Added"; add.disabled = true; toast("Added to Risk Register", "success");
        } catch (e) { toast(`Add failed: ${(e as Error).message}`, "error"); }
      };
      actions.appendChild(add); card.appendChild(actions); out.appendChild(card);
    }
  }

  private renderScopeGaps(out: HTMLElement, r: { gaps: { marker: string; note: string; snippet: string }[]; source: string; message?: string }) {
    out.innerHTML = "";
    const head = document.createElement("div"); head.className = "meta"; head.style.marginBottom = "6px";
    head.innerHTML = `<b>${r.gaps.length}</b> scope-gap marker${r.gaps.length === 1 ? "" : "s"} <span class="badge">${r.source === "claude" ? "AI" : "rules"}</span>`;
    out.appendChild(head);
    if (r.message) { const m = document.createElement("div"); m.className = "meta"; m.textContent = r.message; out.appendChild(m); }
    for (const g of r.gaps) {
      const card = document.createElement("div"); card.className = "dash-card"; card.style.margin = "6px 0";
      card.innerHTML = `<b>${esc(g.marker)}</b><div class="meta" style="margin:2px 0">${esc(g.note)}</div>`
        + (g.snippet ? `<div class="meta" style="font-style:italic">“${esc(g.snippet)}”</div>` : "");
      out.appendChild(card);
    }
  }

  private renderDocAnswer(out: HTMLElement, r: { answer: string; citations: { page: number; snippet: string }[]; source: string; message?: string }) {
    out.innerHTML = "";
    const ans = document.createElement("div"); ans.className = "dash-card"; ans.style.margin = "6px 0";
    ans.innerHTML = `<div>${esc(r.answer || r.message || "No answer.")}</div>`
      + `<div class="meta" style="margin-top:4px"><span class="badge">${r.source === "claude" ? "AI" : "extract"}</span></div>`;
    out.appendChild(ans);
    for (const c of r.citations) {
      const cite = document.createElement("div"); cite.className = "meta"; cite.style.margin = "3px 0";
      cite.innerHTML = `<b>p.${c.page}</b> — ${esc(c.snippet)}`;
      out.appendChild(cite);
    }
  }

  private async renderHome() {
    this.root.innerHTML = "";
    const pid = this.host.projectId()!;
    const root = this.root;
    const el = (tag: string, cls = "") => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };

    // cross-module search
    const search = el("input") as HTMLInputElement;
    search.type = "search"; search.placeholder = "🔍 Search all records…"; search.className = "portal-filter";
    search.style.cssText = "width:100%;margin-bottom:8px";
    const results = el("div");
    let timer: number | undefined;
    search.oninput = () => {
      clearTimeout(timer);
      timer = window.setTimeout(async () => {
        results.innerHTML = "";
        if (search.value.trim().length < 2) return;
        const hits = await this.host.api.searchAll(pid, search.value.trim());
        if (!hits.length) { results.innerHTML = `<div class="empty-state">No matches</div>`; return; }
        for (const h of hits) {
          const row = el("button", "portal-mod") as HTMLButtonElement;
          row.innerHTML = `<span class="ic">${h.icon}</span> ${esc(h.ref)} ${esc(h.title ?? "")} <span class="badge">${esc(h.module_name)}</span>`;
          row.onclick = () => { const m = this.mods.find((x) => x.key === h.module); if (m) this.openRecord(m, h.id); };
          results.appendChild(row);
        }
      }, 250);
    };
    root.append(search, results);

    // saved-search alerts — surface saved views that have NEW matches since last opened
    const alertBand = el("div"); root.append(alertBand);
    void this.host.api.viewAlerts(pid).then((alerts) => {
      const withNew = alerts.filter((a) => a.new > 0);
      if (!withNew.length) return;
      const head = el("div", "meta"); head.textContent = "🔔 Saved searches with new matches";
      head.style.cssText = "margin:4px 0";
      alertBand.append(head);
      const wrap = el("div"); wrap.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px";
      for (const a of withNew) {
        const m = this.mods.find((x) => x.key === a.module); if (!m) continue;
        const chip = el("button", "tool-btn");
        chip.innerHTML = `${a.name} <span class="badge">${a.new} new</span> <span class="meta">of ${a.total}</span>`;
        chip.title = `${m.name} — open this saved search`;
        chip.onclick = async () => {
          this.sort[m.key] = a.config.sort as (typeof this.sort)[string];
          await this.host.api.markViewSeen(pid, a.module, a.id).catch(() => {});
          this.openModule(m, { q: a.config.q, state: a.config.state });
        };
        wrap.append(chip);
      }
      alertBand.append(wrap);
    }).catch(() => {});

    const jump = (key: string, state?: string) => {
      const m = this.mods.find((x) => x.key === key); if (!m) return;
      this.activeKey = key; void this.openModule(m, state ? { state } : {}); this.buildNav();
    };

    // R2 — the developer workspace gets a real-estate command center (deal returns, listings,
    // comps, capital, leases) instead of the GC's on-schedule/on-budget PX bands.
    if (this.wsFilter === "developer") { await this.renderDeveloperHome(root, pid, el, jump); return; }

    // PX executive band — "are we on schedule and on budget?" — loads independently, hides if no data
    const pxBand = el("div"); root.appendChild(pxBand);
    void this.renderPxBand(pxBand, pid);

    try {
      const d = await this.host.api.dashboard(pid);

      // header + status report
      const head = el("div", "section-title"); head.style.cssText = "display:flex;justify-content:space-between;align-items:center";
      head.append(`Dashboard — ${d.party}`);
      const rpt = el("button", "tool-btn") as HTMLButtonElement;
      rpt.textContent = "↓ Status report (PDF)"; rpt.title = "Project status report — KPIs, cost, open items, ball-in-court";
      rpt.onclick = () => window.open(this.host.api.url(`/projects/${pid}/report.pdf`), "_blank");
      head.append(rpt); root.appendChild(head);

      // KPI cards — clickable: jump straight to the relevant (filtered) module.
      // R2 — ordered by role: the superintendent lives in the field (punchlist/safety/quality first),
      // the project manager runs controls (RFIs/COs/overdue first). Everyone sees the same cards —
      // only the emphasis (order) changes. All data stays reachable via the nav + Show-all.
      const kpis = el("div", "kpi-grid");
      const pool: Record<string, [string, number, (() => void) | undefined]> = {
        ball:   ["Ball in court", d.kpis.my_action_items ?? 0, undefined],
        overdue:["Overdue", d.kpis.overdue ?? 0, undefined],
        rfis:   ["Open RFIs", d.kpis.open_rfis ?? 0, () => jump("rfi", "open")],
        cos:    ["Pending COs", d.kpis.pending_change_orders ?? 0, () => jump("cor")],
        quality:["Quality", d.kpis.open_quality ?? 0, () => jump("ncr")],
        safety: ["Safety", d.kpis.open_safety ?? 0, () => jump("incident")],
        punch:  ["Open punchlist", d.kpis.open_punchlist ?? 0, () => jump("punchlist")],
      };
      const persona = document.body.dataset.persona || localStorage.getItem("persona") || "all";
      const ORDER_BY_PERSONA: Record<string, string[]> = {
        // field roles — jobsite/today first
        superintendent: ["ball", "punch", "safety", "quality", "overdue", "rfis"],
        subcontractor:  ["ball", "punch", "safety", "rfis", "overdue", "quality"],
        // office/controls roles — RFIs/COs/schedule first
        project_manager:["ball", "rfis", "cos", "overdue", "quality", "safety"],
        gc:             ["ball", "rfis", "cos", "overdue", "quality", "safety"],
      };
      const order = ORDER_BY_PERSONA[persona] || ["ball", "overdue", "rfis", "cos", "quality", "safety"];
      const cards = order.map((k) => pool[k]).filter(Boolean);
      for (const [label, val, onClick] of cards) {
        const c = el("div", "kpi" + (onClick ? " kpi-click" : "")) as HTMLElement;
        c.innerHTML = `<div class="kpi-v">${val}</div><div class="kpi-l">${label}</div>`;
        if (onClick) {
          c.onclick = onClick; c.tabIndex = 0; c.setAttribute("role", "button");
          c.onkeydown = (e) => { if ((e as KeyboardEvent).key === "Enter") onClick(); };
        }
        kpis.appendChild(c);
      }
      root.appendChild(kpis);

      // executive health banner — unified RAG score across the analytics domains
      const hb = el("div"); hb.id = "dash-health"; root.appendChild(hb);
      void this.host.api.projectHealth(pid).then((h) => {
        if (!h.domains.length) { hb.innerHTML = ""; return; }
        const tone: Record<string, string> = { red: "var(--status-crit)", amber: "var(--status-warn)", green: "var(--status-good)", na: "#9aa0a6" };
        const dot = (s: string) => `<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${tone[s] || "#9aa0a6"};margin-right:5px"></span>`;
        const c = tone[h.overall_status] || "#9aa0a6";
        const chips = h.domains.map((d) =>
          `<span title="${d.headline.replace(/"/g, "&quot;")}" style="display:inline-flex;align-items:center;font-size:11px;background:#ffffff10;border:1px solid #ffffff22;border-radius:12px;padding:2px 8px;margin:2px 4px 2px 0">${dot(d.status)}${d.label}</span>`).join("");
        const att = h.attention_items.slice(0, 4).map((a) =>
          `<div style="display:flex;gap:8px;align-items:baseline;font-size:12px;margin:2px 0">${dot(a.status)}<span><b>${a.domain}</b> — ${a.issue}</span></div>`).join("");
        hb.innerHTML = `<div class="dash-card" style="border-left:4px solid ${c};margin-top:8px">`
          + `<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">`
          + `<div style="font-size:30px;font-weight:800;color:${c};line-height:1">${h.health_score ?? "—"}<span style="font-size:13px;font-weight:600;opacity:.6">/100</span></div>`
          + `<div><div style="font-weight:700">Project health · <span style="color:${c};text-transform:uppercase">${h.overall_status}</span></div>`
          + `<div class="meta">${h.open_items_total} open · ${h.overdue_items_total} overdue across ${h.domains.length} domains</div></div></div>`
          + `<div style="margin:8px 0 4px">${chips}</div>`
          + (att ? `<div style="margin-top:6px">${att}</div>` : "")
          + `</div>`;
      }).catch(() => { hb.innerHTML = ""; });

      // risk summary (full width — owner/PM reporting)
      const risk = el("div"); risk.id = "dash-risk"; root.appendChild(risk);
      void this.host.api.riskSummary(pid).then((rs) => {
        const colors: Record<string, string> = { high: "var(--status-crit)", medium: "var(--status-warn)", low: "#6cb6ff" };
        risk.innerHTML = `<div class="section-title" style="margin-top:8px">Risk summary`
          + `<span class="meta" style="font-weight:400"> · ${rs.source === "claude" ? "AI" : "rules"}</span></div>`
          + `<div class="meta" style="margin:2px 0 6px">${rs.headline}</div>`
          + rs.risks.map((r) => `<div style="display:flex;gap:8px;align-items:baseline;margin:3px 0;font-size:12px">`
            + `<span style="color:${colors[r.level] || "#9aa0a6"};font-weight:700;text-transform:uppercase;font-size:10px;min-width:54px">${r.level}</span>`
            + `<span>${r.text}</span></div>`).join("");
      }).catch(() => { risk.innerHTML = ""; });

      // two-column body: [ needs attention + notifications ] | [ health + charts ]
      const cols = el("div", "dash-cols");
      const main = el("div", "dash-col"); const side = el("div", "dash-col dash-side");
      cols.append(main, side); root.appendChild(cols);

      // MAIN — Ball in your court (the most actionable list)
      main.appendChild(Object.assign(el("div", "section-title"), { textContent: "Ball in your court" }));
      if (d.action_items.length) {
        for (const a of d.action_items.slice(0, 20)) {
          const row = el("button", "portal-mod") as HTMLButtonElement;
          row.innerHTML = `<span class="ic">→</span> ${esc(a.ref)} ${esc(a.title ?? "")} <span class="badge">${esc(a.state)}</span>`;
          row.onclick = () => { const m = this.mods.find((x) => x.key === a.module); if (m) this.openRecord(m, a.id); };
          main.appendChild(row);
        }
      } else {
        main.appendChild(Object.assign(el("div", "empty-state"), { textContent: "✓ Nothing in your court — you are caught up" }));
      }
      // MAIN — overdue / due-soon (cross-module SLA feed)
      void this.host.api.dueFeed(pid, 7).then((due) => {
        if (!due.counts.overdue && !due.counts.due_soon) return;
        main.appendChild(Object.assign(el("div", "section-title"),
          { textContent: `⏰ Deadlines — ${due.counts.overdue} overdue · ${due.counts.due_soon} due this week` }));
        const rowFor = (x: typeof due.overdue[number], overdue: boolean) => {
          const row = el("button", "portal-mod") as HTMLButtonElement;
          const when = overdue ? `${Math.abs(x.days)}d overdue` : (x.days === 0 ? "due today" : `in ${x.days}d`);
          row.innerHTML = `<span class="ic">${x.icon}</span> <b>${esc(x.ref)}</b> ${esc(x.title ?? "")} `
            + `<span class="badge ${overdue ? "rfi" : "open"}">${when}</span>`;
          row.onclick = () => { const m = this.mods.find((mm) => mm.key === x.module); if (m) this.openRecord(m, x.id); };
          main.appendChild(row);
        };
        for (const x of due.overdue.slice(0, 10)) rowFor(x, true);
        for (const x of due.due_soon.slice(0, 6)) rowFor(x, false);
      }).catch(() => {});

      // MAIN — recent notifications
      void this.host.api.notifications(pid).then((notes) => {
        if (!notes.length) return;
        main.appendChild(Object.assign(el("div", "section-title"), { textContent: `🔔 Notifications (${notes.length})` }));
        for (const n of notes.slice(0, 8)) {
          const row = el("button", "portal-mod notif") as HTMLButtonElement;
          const ago = n.ts ? new Date(n.ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
          row.innerHTML = `<span class="ic">${n.icon}</span> <b>${esc(n.ref)}</b> ${esc(n.action)} `
            + `<span class="badge ${n.reason === "assigned" ? "rfi" : "open"}">${esc(n.reason)}</span> `
            + `<span class="notif-meta">${esc(n.actor ?? "")} · ${ago}</span>`;
          row.onclick = () => { const m = this.mods.find((x) => x.key === n.module); if (m) this.openRecord(m, n.record_id); };
          main.appendChild(row);
        }
      }).catch(() => {});

      // SIDE — project health (cost / safety / lean) grouped in one card
      const health = el("div", "dash-card"); side.appendChild(health);
      health.appendChild(Object.assign(el("div", "section-title"), { textContent: "Project health" }));
      if (d.cost) {
        const ou = d.cost.projected_over_under;
        const cd = el("div", "meta"); cd.style.margin = "2px 0";
        cd.innerHTML = `Budget <b>$${d.cost.budget.toLocaleString()}</b> · `
          + `<span style="color:${ou > 0 ? "var(--status-crit)" : "var(--status-good)"}">${ou > 0 ? "over" : "under"} $${Math.abs(ou).toLocaleString()}</span>`;
        health.appendChild(cd);
      }
      const safety = el("div", "meta"); safety.style.margin = "2px 0"; health.appendChild(safety);
      void this.host.api.safetyMetrics(pid).then((s) => {
        if (!s.incident_count) { safety.textContent = "Safety: no recordable incidents ✓"; return; }
        const trir = s.trir != null ? ` · TRIR ${s.trir}` : ""; const dart = s.dart != null ? ` · DART ${s.dart}` : "";
        safety.textContent = `Safety: ${s.recordable_count} recordable / ${s.incident_count} incidents · ${s.lost_days} lost days${trir}${dart}`;
      }).catch(() => {});
      const lean = el("div", "meta"); lean.style.margin = "2px 0"; health.appendChild(lean);
      void this.host.api.leanPpc(pid).then((l) => {
        if (!l.commitments) return;
        const top = l.top_variance_reasons[0];
        const color = l.rating === "good" ? "var(--status-good)" : l.rating === "fair" ? "var(--status-warn)" : "var(--status-crit)";
        lean.innerHTML = `Lean PPC: <b style="color:${color}">${(l.ppc * 100).toFixed(0)}%</b> `
          + `(${l.completed}/${l.commitments} commitments${l.missed ? ` · ${l.missed} missed` : ""})`
          + (top ? ` · top reason: ${top.reason}` : "");
      }).catch(() => {});
      // compliance: COI / permit expiries — don't let insurance or permits lapse silently
      const comp = el("div", "meta"); comp.style.margin = "2px 0"; health.appendChild(comp);
      void this.host.api.complianceExpiring(pid, 30).then((cc) => {
        if (!cc.count) { comp.textContent = "Compliance: no COI/permit expiries ✓"; return; }
        const color = cc.expired.length ? "var(--status-crit)" : "var(--status-warn)";
        comp.innerHTML = `Compliance: <b style="color:${color}">${cc.expired.length} expired · ${cc.expiring.length} expiring</b> (COI/permit) `;
        const a = document.createElement("a"); a.href = "#"; a.className = "ref-link"; a.textContent = "review";
        a.onclick = (e) => { e.preventDefault(); const m = this.mods.find((x) => x.key === (cc.expired[0] ?? cc.expiring[0])?.module); if (m) this.openModule(m); };
        comp.appendChild(a);
      }).catch(() => {});

      // SIDE — charts (status mix + busiest sections)
      const states = new Map<string, number>(); const sections = new Map<string, number>();
      for (const bm of d.by_module) {
        for (const [st, n] of Object.entries(bm.by_state)) states.set(st, (states.get(st) ?? 0) + n);
        if (bm.count) sections.set(bm.section || "Other", (sections.get(bm.section || "Other") ?? 0) + bm.count);
      }
      const STATE_COLOR: Record<string, string> = { draft: "#9aa0a6", open: "var(--status-warn)", answered: "#6cb6ff", closed: "var(--status-good)", void: "var(--status-crit)", approved: "var(--status-good)", rejected: "var(--status-crit)" };
      if (states.size) side.appendChild(this.barChart("Records by status",
        [...states.entries()].sort((a, b) => b[1] - a[1]), (k) => STATE_COLOR[k] ?? "#b083d6"));
      if (sections.size) side.appendChild(this.barChart("Busiest sections",
        [...sections.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6), () => "#4a8cff"));

      // Ask AI — full width, bottom
      const ask = el("div"); ask.style.cssText = "margin:12px 0 4px";
      ask.innerHTML = `<div class="section-title">Ask AI</div>`;
      const arow = el("div"); arow.style.cssText = "display:flex;gap:6px;margin:4px 0";
      const input = el("input", "portal-filter") as HTMLInputElement; input.style.flex = "1";
      input.placeholder = "Ask about this project — e.g. what is overdue, open RFIs, are we over budget";
      const go = el("button", "file-btn") as HTMLButtonElement; go.textContent = "Ask";
      const out = el("div", "meta"); out.style.cssText = "white-space:pre-wrap;margin-top:4px";
      const askRun = async () => {
        const q = input.value.trim(); if (!q) return;
        out.textContent = "thinking…";
        try {
          const r = await this.host.api.aiAsk(pid, q);
          let text = r.answer;
          const snap = r.snapshot as { record_counts?: Record<string, number>; kpis?: Record<string, number> } | undefined;
          if (r.source !== "claude" && snap) {
            const k = snap.kpis || {}, c = snap.record_counts || {};
            const line = (label: string, v: unknown) => (v ? `\n• ${label}: ${v}` : "");
            text += line("Open RFIs", k.open_rfis) + line("Overdue", k.overdue)
              + line("Pending change orders", k.pending_change_orders) + line("Open punchlist", k.open_punchlist)
              + line("RFIs (total)", c.rfi) + line("Change events", c.change_event);
            if (!r.ai_enabled) text += "\n\n(Set an Anthropic API key in Settings for full plain-English answers.)";
          }
          out.textContent = text;
        } catch { out.textContent = "Could not reach the assistant."; }
      };
      go.onclick = () => void askRun();
      input.onkeydown = (e) => { if (e.key === "Enter") void askRun(); };
      arow.append(input, go); ask.append(arow, out); root.appendChild(ask);
    } catch { /* dashboard optional */ }
  }

  // --- module catalog: favorites + collapsible, persona-aware sections + filter --
  private catalogEl?: HTMLElement;

  /** Which sections open by default per persona (the rest collapse). Undefined persona = all open. */
  // R2 — which nav sections open first for each role (research-backed: Procore super-vs-PM split;
  // real-estate developer lifecycle = feasibility → market/sales → capital → operations). The section
  // names here must match the workspace a role lives in — the developer's are the *Developer* sections,
  // not construction ones. buildNav also falls back to "open all" when none of these match the active
  // workspace, so a role browsing the other workspace never sees everything collapsed.
  private static SECTIONS_BY_PERSONA: Record<string, string[]> = {
    gc: ["Field", "Cost", "Change Management", "Contracts"],
    // the super works the field (daily reports, manpower, safety, quality, schedule);
    // the PM works the office (RFIs/submittals, cost, change, contracts, preconstruction).
    superintendent: ["Field", "Safety", "Quality", "Schedule"],
    project_manager: ["Engineering", "Cost", "Change Management", "Contracts", "Preconstruction"],
    // the real-estate developer lives in the Developer workspace — feasibility, market/sales, capital, ops.
    developer: ["Feasibility", "Market & Sales", "Capital", "Operations"],
    architect: ["Engineering", "Preconstruction", "BIM", "Closeout"],
    engineer: ["Engineering", "Quality", "BIM"],
    subcontractor: ["Field", "Safety", "Quality"],
  };

  private favs(): Set<string> {
    try { return new Set(JSON.parse(localStorage.getItem("portal-favs") || "[]") as string[]); }
    catch { return new Set(); }
  }
  /** Last-opened module keys, newest first — auto-populated so the nav works with zero setup. */
  private recents(): string[] {
    try { return JSON.parse(localStorage.getItem("portal-recents") || "[]") as string[]; }
    catch { return []; }
  }
  private pushRecent(key: string) {
    const r = [key, ...this.recents().filter((k) => k !== key)].slice(0, 5);
    localStorage.setItem("portal-recents", JSON.stringify(r));
  }
  private toggleFav(key: string) {
    const f = this.favs(); f.has(key) ? f.delete(key) : f.add(key);
    localStorage.setItem("portal-favs", JSON.stringify([...f]));
    this.refreshCatalog();
  }
  private refreshCatalog() {
    if (!this.catalogEl) return;
    const next = this.renderModuleCatalog();
    this.catalogEl.replaceWith(next); this.catalogEl = next;
  }

  private renderModuleCatalog(): HTMLElement {
    const wrap = document.createElement("div");
    const favs = this.favs();
    const persona = document.body.dataset.persona || localStorage.getItem("persona") || "all";
    const openSecs = PortalUI.SECTIONS_BY_PERSONA[persona];   // undefined => all sections open

    const filter = document.createElement("input");
    filter.type = "search"; filter.placeholder = "Filter modules…"; filter.className = "portal-filter";
    filter.style.cssText = "width:100%;margin:2px 0 8px";
    wrap.appendChild(filter);

    const mkBtn = (m: ModuleDef) => {
      // a row of two real buttons (favorite toggle + open) — both keyboard-focusable, no nested
      // interactive elements (a <button> inside a <button> is invalid + unfocusable).
      const row = document.createElement("div"); row.className = "portal-mod-row"; row.dataset.modname = m.name.toLowerCase();
      const fav = favs.has(m.key);
      const star = document.createElement("button");
      star.type = "button"; star.className = "mod-fav" + (fav ? " on" : ""); star.textContent = fav ? "★" : "☆";
      star.title = fav ? "Unfavorite" : "Favorite";
      star.setAttribute("aria-label", `${fav ? "Unfavorite" : "Favorite"} ${m.name}`);
      star.setAttribute("aria-pressed", String(fav));
      star.onclick = (e) => { e.stopPropagation(); this.toggleFav(m.key); };
      const open = document.createElement("button"); open.type = "button"; open.className = "portal-mod";
      open.append(Object.assign(document.createElement("span"), { className: "ic", textContent: m.icon || "•" }),
        document.createTextNode(" " + m.name));
      open.onclick = () => this.openModule(m);
      row.append(star, open);
      return row;
    };

    const sections = new Map<string, ModuleDef[]>();
    for (const m of this.mods) { const s = m.section || "Other"; (sections.get(s) ?? sections.set(s, []).get(s)!).push(m); }

    if (favs.size) {
      const favMods = this.mods.filter((m) => favs.has(m.key));
      wrap.appendChild(this.catalogGroup("★ Favorites", "fav", favMods.map(mkBtn), true));
    }
    for (const [section, mods] of sections)
      wrap.appendChild(this.catalogGroup(section, `sec:${section}`, mods.map(mkBtn), !openSecs || openSecs.includes(section)));

    // live filter: hide non-matching modules, hide empty groups, auto-expand groups with hits
    filter.oninput = () => {
      const q = filter.value.trim().toLowerCase();
      wrap.querySelectorAll<HTMLElement>(".tool-group").forEach((g) => {
        let any = false;
        g.querySelectorAll<HTMLElement>(".portal-mod-row").forEach((row) => {
          const hit = !q || (row.dataset.modname || "").includes(q);
          row.style.display = hit ? "" : "none"; if (hit) any = true;
        });
        g.style.display = any ? "" : "none";
        if (q) g.classList.toggle("open", any);
      });
    };
    return wrap;
  }

  private catalogGroup(title: string, key: string, buttons: HTMLElement[], openDefault: boolean): HTMLElement {
    const g = document.createElement("section"); g.className = "tool-group";
    const saved = localStorage.getItem(`portal-open:${key}`);
    const open0 = saved == null ? openDefault : saved === "1";
    g.classList.toggle("open", open0);
    const head = document.createElement("button"); head.type = "button"; head.className = "tool-group-head";
    head.setAttribute("aria-expanded", String(open0));
    head.innerHTML = `<span class="chev">▸</span><span class="t">${title}</span><span class="cnt">${buttons.length}</span>`;
    const body = document.createElement("div"); body.className = "tool-group-body";
    for (const b of buttons) body.appendChild(b);
    head.onclick = () => { const o = !g.classList.contains("open"); g.classList.toggle("open", o); head.setAttribute("aria-expanded", String(o)); localStorage.setItem(`portal-open:${key}`, o ? "1" : "0"); };
    g.append(head, body);
    return g;
  }

  // --- record list (sortable / filterable data table + bulk actions) ---------
  private sort: Record<string, { col: string; dir: 1 | -1 } | undefined> = {};

  /** Immediate loading placeholder so a click gives feedback before the fetch returns. */
  private skeleton(label: string) {
    this.root.innerHTML = `<div class="section-title">${label}</div>`
      + `<div>${'<div class="skel-row"></div>'.repeat(6)}</div>`;
  }

  /** First-class Budget destination — the GC's GMP project budget. Direct trade work (by CSI
   *  division + bid package) + General Conditions / Requirements (incl. staffing) + Overhead + Fee
   *  + Contingency = GMP, each line budget vs committed (buyout) vs variance, reconciled to the
   *  prime contract value and the developer proforma's construction hard cost. The on-budget half of
   *  what a project executive lives in, next to the Schedule destination. */
  /** Cross-project executive portfolio — every job's on-schedule + on-budget status at a glance.
   *  Rows are clickable to switch projects. The 'how's the whole book doing?' destination. */
  private async renderPortfolio() {
    this.root.innerHTML = "";
    this.root.appendChild(this.bar("Portfolio", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;
    const vcol = (v: number) => v < 0 ? "var(--status-crit)" : v > 0 ? "var(--status-good)" : "var(--muted)";
    const pill: Record<string, [string, string]> = { on_track: ["On track", "var(--status-good)"], at_risk: ["At risk", "var(--status-warn)"], behind: ["Behind", "var(--status-crit)"] };
    const status = document.createElement("div"); status.className = "meta"; status.textContent = "loading portfolio…";
    this.root.appendChild(status);
    const here = this.host.projectId();

    void this.host.api.executivePortfolio().then((pf) => {
      status.remove();
      const t = pf.totals, ta = pf.status_tally;
      const kpis = document.createElement("div"); kpis.className = "dash-cols"; kpis.style.marginBottom = "10px";
      const kpi = (label: string, val: string, color?: string) => {
        const c = document.createElement("div"); c.className = "dash-card"; c.style.flex = "1";
        c.innerHTML = `<div class="meta">${label}</div><div style="font-size:18px;font-weight:700${color ? `;color:${color}` : ""}">${val}</div>`;
        return c;
      };
      const irrPct = (v: number | null) => v == null ? "—" : `${(v * 100).toFixed(1)}%`;
      kpis.append(
        kpi("Projects", String(pf.project_count)),
        kpi("Portfolio GMP", usd(t.gmp)),
        kpi("Variance at completion", usd(t.variance_at_completion), vcol(t.variance_at_completion)),
        kpi("Blended equity IRR", irrPct(t.blended_equity_irr)),
        kpi("Status", `${ta.on_track}✓ ${ta.at_risk}△ ${ta.behind}⚠`),
      );
      this.root.appendChild(kpis);

      const card = document.createElement("div"); card.className = "dash-card";
      const tbl = document.createElement("table"); tbl.className = "portal-table"; tbl.style.fontSize = "11px";
      tbl.innerHTML = `<thead><tr><th scope="col">Project</th><th scope="col">Status</th><th scope="col" style="text-align:right">SPI</th>`
        + `<th scope="col" style="text-align:right">% cmpl</th><th scope="col" style="text-align:right">GMP</th>`
        + `<th scope="col" style="text-align:right">VAC</th><th scope="col" style="text-align:right">Equity IRR</th><th scope="col" style="text-align:right">EM</th><th scope="col" style="text-align:right">Late MS</th></tr></thead>`;
      const tb = document.createElement("tbody");
      for (const p of pf.projects) {
        const tr = document.createElement("tr"); tr.className = "kpi-click";
        if (p.id === here) tr.style.fontWeight = "700";
        const [lbl, col] = pill[p.status] ?? ["—", "var(--muted)"];
        const irrCol = p.equity_irr == null ? "var(--muted)" : p.equity_irr >= 0.15 ? "var(--status-good)" : p.equity_irr >= 0.12 ? "var(--status-warn)" : "var(--status-crit)";
        tr.innerHTML = `<td>${esc(p.name)}${p.id === here ? " ·" : ""}</td>`
          + `<td><span class="ball-badge" style="background:${col}22;color:${col};border-color:${col}">${lbl}</span></td>`
          + `<td style="text-align:right;color:${p.spi == null ? "var(--muted)" : p.spi >= 0.95 ? "var(--status-good)" : "var(--status-crit)"}">${p.spi ?? "—"}</td>`
          + `<td style="text-align:right">${p.pct_complete}%</td><td style="text-align:right">${usd(p.gmp)}</td>`
          + `<td style="text-align:right;color:${vcol(p.variance_at_completion)}">${usd(p.variance_at_completion)}</td>`
          + `<td style="text-align:right;color:${irrCol}">${irrPct(p.equity_irr)}</td>`
          + `<td style="text-align:right">${p.equity_multiple == null ? "—" : p.equity_multiple + "×"}</td>`
          + `<td style="text-align:right;color:${p.milestones_late ? "var(--status-crit)" : "var(--muted)"}">${p.milestones_late || "—"}</td>`;
        tr.onclick = () => { if (p.id !== here) window.location.search = `?project=${p.id}`; };
        tb.appendChild(tr);
      }
      tbl.appendChild(tb); card.appendChild(tbl); this.root.appendChild(card);
      this.root.appendChild(Object.assign(document.createElement("div"), { className: "meta",
        textContent: "Click a project to switch to it. On-schedule (SPI / % complete / late milestones) + on-budget (GMP / variance) + developer returns (IRR / EM) across the book." }));
    }).catch(() => { status.className = "empty-state"; status.innerHTML = `Portfolio unavailable<span class="es-hint">Needs at least one project with schedule/budget data.</span>`; });
  }

  private async renderBudget() {
    const pid = this.host.projectId()!;
    this.root.innerHTML = "";
    this.root.appendChild(this.bar("Budget", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;
    const vcol = (v: number) => v < 0 ? "var(--status-crit)" : v > 0 ? "var(--status-good)" : "var(--muted)";
    const jumpTo = (k: string) => { const tm = this.mods.find((x) => x.key === k); if (tm) { this.activeKey = k; this.openModule(tm); this.buildNav(); } };

    const intro = document.createElement("div"); intro.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:2px 0 8px";
    const jump = document.createElement("select"); jump.className = "sb-sel"; jump.title = "Open a budget input list";
    jump.innerHTML = `<option value="">＋ edit inputs…</option><option value="cost_code">Cost codes</option>`
      + `<option value="budget">Budget lines</option><option value="staffing">Staffing plan</option>`
      + `<option value="commitment">Commitments / POs</option><option value="bid_package">Bid packages</option>`
      + `<option value="prime_contract">Prime contract (markups)</option>`;
    jump.onchange = () => { if (jump.value) jumpTo(jump.value); };
    const sovBtn = document.createElement("button"); sovBtn.className = "tool-btn"; sovBtn.dataset.cap = "edit";
    sovBtn.textContent = "⎘ Build owner SOV"; sovBtn.title = "Seed the owner pay-app Schedule of Values from these GMP lines";
    sovBtn.onclick = async () => {
      try {
        let r = await this.host.api.sovFromBudget(pid);
        if (!r.created && r.skipped && confirm(`The SOV already has ${r.skipped} lines. Rebuild it from the budget?`))
          r = await this.host.api.sovFromBudget(pid, true);
        this.host.setStatus(r.created ? `built ${r.created} SOV lines from the budget` : "SOV unchanged");
        if (r.created) jumpTo("sov");
      } catch (e) { this.host.setStatus(`couldn't build SOV: ${(e as Error).message}`); }
    };
    const baseBtn = document.createElement("button"); baseBtn.className = "tool-btn"; baseBtn.dataset.cap = "edit";
    baseBtn.textContent = "📌 Set baseline"; baseBtn.title = "Snapshot the current GMP budget to track movement against";
    baseBtn.onclick = async () => {
      if (!confirm("Snapshot the current GMP budget as the baseline? (re-baseline after an approved change)")) return;
      try { const r = await this.host.api.setBudgetBaseline(pid); this.host.setStatus(`baseline set (${r.lines} lines)`); void this.renderBudget(); }
      catch (e) { this.host.setStatus(`couldn't set baseline: ${(e as Error).message}`); }
    };
    const note = document.createElement("span"); note.className = "meta";
    note.innerHTML = "The agreed <b>GMP</b> broken to every cost code & bid package + GC/GR, overhead, fee & contingency — budget vs committed vs actual.";
    intro.append(jump, sovBtn, baseBtn, note); this.root.appendChild(intro);

    // budget movement vs baseline (shown only if a baseline exists; 409 otherwise → ignored)
    const bvHolder = document.createElement("div"); this.root.appendChild(bvHolder);
    void this.host.api.budgetVariance(pid).then((v) => {
      const col = v.total_delta > 0 ? "var(--status-crit)" : v.total_delta < 0 ? "var(--status-good)" : "var(--muted)";
      bvHolder.className = "meta"; bvHolder.style.margin = "0 0 6px";
      bvHolder.innerHTML = `Vs baseline (${v.captured_at}): GMP moved <span style="color:${col}">${v.total_delta > 0 ? "+" : ""}$${Math.round(v.total_delta).toLocaleString()}</span>`
        + (v.lines.length ? ` across ${v.lines.length} line${v.lines.length > 1 ? "s" : ""}` : " — no drift");
    }).catch(() => {});

    const status = document.createElement("div"); status.className = "meta"; status.textContent = "loading budget…";
    this.root.appendChild(status);

    void this.host.api.gmpBudget(pid).then((b) => {
      status.remove();
      const g = b.gmp;
      // headline KPI row
      const kpis = document.createElement("div"); kpis.className = "dash-cols"; kpis.style.marginBottom = "10px";
      const kpi = (label: string, val: string, color?: string) => {
        const c = document.createElement("div"); c.className = "dash-card"; c.style.flex = "1";
        c.innerHTML = `<div class="meta">${label}</div><div style="font-size:18px;font-weight:700${color ? `;color:${color}` : ""}">${val}</div>`;
        return c;
      };
      // defensive defaults so the page renders against any API version (new fields fill once present)
      const comp = b.completion ?? { eac: b.totals.forecast, etc: 0, actual_to_date: b.totals.actual,
        projected_over_under: b.totals.variance, pct_spent: 0, bac: b.totals.budget };
      const buyout = b.buyout ?? { packages: b.bid_packages.length, bought_out: 0, budget: 0, awarded: 0, savings: 0 };
      kpis.append(
        kpi("GMP (computed)", usd(g.computed)),
        kpi("Committed (buyout)", usd(b.totals.committed)),
        kpi("Forecast at completion", usd(comp.eac)),
        kpi("Projected variance", usd(comp.projected_over_under), vcol(comp.projected_over_under)),
      );
      this.root.appendChild(kpis);

      // cost-to-complete + buyout savings line
      const ctc = document.createElement("div"); ctc.className = "meta"; ctc.style.margin = "0 0 6px";
      ctc.innerHTML = `Cost to complete (ETC) <b>${usd(comp.etc)}</b> · spent ${usd(comp.actual_to_date)} (${comp.pct_spent}%)`
        + (buyout.bought_out
            ? ` · buyout ${buyout.bought_out}/${buyout.packages} · savings <span style="color:${vcol(buyout.savings)}">${usd(buyout.savings)}</span>` : "");
      this.root.appendChild(ctc);

      if (g.approved_changes) {
        const ch = document.createElement("div"); ch.className = "meta"; ch.style.margin = "0 0 6px";
        ch.innerHTML = `Approved changes <b>${usd(g.approved_changes)}</b> → revised GMP <b>${usd(g.revised ?? g.computed)}</b>`
          + (g.unallocated_changes ? ` <span style="color:var(--status-warn)">(${usd(g.unallocated_changes)} unallocated — assign a cost code)</span>` : "");
        this.root.appendChild(ch);
      }

      if (g.contract_value || b.proforma) {
        const recon = document.createElement("div"); recon.className = "meta"; recon.style.margin = "0 0 8px";
        recon.innerHTML = (g.contract_value
          ? `Contract GMP <b>${usd(g.contract_value)}</b> · reconciliation <span style="color:${vcol(g.reconciliation ?? 0)}">${usd(g.reconciliation ?? 0)}</span>` : "")
          + (b.proforma ? `${g.contract_value ? " · " : ""}vs developer proforma hard cost <b>${usd(b.proforma.hard_cost)}</b> `
              + `<span style="color:${vcol(-b.proforma.gmp_vs_hard)}">(${b.proforma.gmp_vs_hard > 0 ? "+" : ""}${usd(b.proforma.gmp_vs_hard)})</span>` : "");
        this.root.appendChild(recon);
      }

      // category table, with expandable direct-work division groups
      const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "10px";
      card.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Budget by category" }));
      const tbl = document.createElement("table"); tbl.className = "portal-table"; tbl.style.fontSize = "11px";
      tbl.innerHTML = `<thead><tr><th scope="col">Category</th><th scope="col" style="text-align:right">Budget</th>`
        + `<th scope="col" style="text-align:right">Committed</th><th scope="col" style="text-align:right">Actual</th>`
        + `<th scope="col" style="text-align:right">Forecast (EAC)</th><th scope="col" style="text-align:right">Variance</th></tr></thead>`;
      const tb = document.createElement("tbody");
      const row = (name: string, c: { budget: number; committed: number; actual: number; eac?: number; variance: number }, opts: { bold?: boolean; indent?: boolean } = {}) => {
        const tr = document.createElement("tr"); if (opts.bold) tr.style.fontWeight = "700";
        tr.innerHTML = `<td style="${opts.indent ? "padding-left:16px;color:var(--muted)" : ""}">${name}</td>`
          + `<td style="text-align:right">${usd(c.budget)}</td><td style="text-align:right">${usd(c.committed)}</td>`
          + `<td style="text-align:right">${usd(c.actual)}</td><td style="text-align:right">${usd(c.eac ?? c.budget)}</td>`
          + `<td style="text-align:right;color:${vcol(c.variance)}">${usd(c.variance)}</td>`;
        return tr;
      };
      for (const cat of b.categories) {
        tb.appendChild(row(cat.name, cat, { bold: cat.key === "direct" }));
        if (cat.key === "direct") for (const grp of (cat.groups ?? [])) {       // division breakdown
          tb.appendChild(row(grp.name, { budget: grp.budget, committed: 0, actual: 0, variance: 0 } as any, { indent: true }));
        }
      }
      tb.appendChild(row("Total (GMP)", b.totals, { bold: true }));
      tbl.appendChild(tb); card.appendChild(tbl);
      // budget vs committed vs actual vs EAC, by category — grouped bar
      const cats = (b.categories || []).filter((c: { budget?: number }) => (c.budget ?? 0) > 0);
      if (cats.length) {
        const chart = document.createElement("div"); chart.style.marginTop = "8px";
        chart.innerHTML = `<div class="section-title" style="margin:0 0 2px">Budget vs committed vs actual vs EAC</div>`
          + groupedBar(cats.map((c: { name: string; budget?: number; committed?: number; actual?: number; eac?: number }) => ({
              label: c.name, bars: [
                { name: "Budget", value: c.budget ?? 0 }, { name: "Committed", value: c.committed ?? 0 },
                { name: "Actual", value: c.actual ?? 0 }, { name: "EAC", value: c.eac ?? c.budget ?? 0 },
              ],
            })), { title: "Budget vs committed vs actual vs EAC", fmt: cmoney, height: 180 });
        card.appendChild(chart);
      }
      this.root.appendChild(card);

      // bid-package buyout
      const bc = document.createElement("div"); bc.className = "dash-card"; bc.style.marginBottom = "10px";
      const bh = document.createElement("div"); bh.className = "section-title";
      bh.style.cssText = "display:flex;justify-content:space-between;align-items:center";
      bh.append(Object.assign(document.createElement("span"), { textContent: `Bid-package buyout (${b.bid_packages.length})` }));
      bh.append(Object.assign(document.createElement("span"), { className: "meta",
        textContent: buyout.bought_out ? ` ${buyout.bought_out} bought out · savings ${usd(buyout.savings)}` : "" }));
      const openBp = document.createElement("button"); openBp.className = "tool-btn"; openBp.textContent = "open"; openBp.onclick = () => jumpTo("bid_package");
      bh.appendChild(openBp); bc.appendChild(bh);
      if (b.bid_packages.length) {
        for (const bp of b.bid_packages) {
          const r = document.createElement("div"); r.className = "meta"; r.style.margin = "1px 0";
          r.innerHTML = `${bp.name ?? bp.ref}${bp.trade ? ` · ${bp.trade}` : ""} · budget <b>${usd(bp.budget)}</b>`
            + (bp.bought_out
                ? ` · awarded <b>${usd(bp.awarded)}</b> · savings <span style="color:${vcol(bp.savings)}">${usd(bp.savings)}</span>`
                : ` · ${bp.submissions || 0} bids · <span style="color:var(--status-warn)">not bought out</span>`);
          bc.appendChild(r);
        }
      } else { bc.appendChild(Object.assign(document.createElement("div"), { className: "meta", textContent: "No bid packages yet." })); }
      this.root.appendChild(bc);

      // owner billing — close the loop: budget → SOV → G702/G703 pay app → owner invoice
      const billing = document.createElement("div"); billing.className = "dash-card"; billing.style.marginBottom = "10px";
      billing.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Owner billing" }));
      const brow = document.createElement("div"); brow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center";
      const seedBtn = document.createElement("button"); seedBtn.className = "tool-btn"; seedBtn.dataset.cap = "edit";
      seedBtn.textContent = "↻ Seed SOV from budget";
      seedBtn.onclick = async () => {
        try { const r = await this.host.api.sovFromBudget(pid, true);
          this.host.setStatus(`SOV seeded: ${r.created} lines${r.scheduled_value ? ` = $${Math.round(r.scheduled_value).toLocaleString()}` : ""}`); }
        catch (e) { this.host.setStatus(`SOV seed failed: ${(e as Error).message}`); }
      };
      const pdfBtn = document.createElement("button"); pdfBtn.className = "tool-btn"; pdfBtn.textContent = "⬇ Pay app (PDF)";
      pdfBtn.onclick = async () => {
        try { const blob = await this.host.api.payAppPdf(pid, 1);
          const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "pay-app-1.pdf"; a.click(); URL.revokeObjectURL(a.href);
          this.host.setStatus("pay-app PDF generated"); }
        catch (e) { this.host.setStatus(`pay app failed: ${(e as Error).message}`); }
      };
      const invBtn = document.createElement("button"); invBtn.className = "tool-btn"; invBtn.dataset.cap = "edit";
      invBtn.textContent = "＋ Owner invoice from draw";
      invBtn.onclick = async () => {
        try { const r = await this.host.api.payAppInvoice(pid, 1);
          this.host.setStatus(`owner invoice created: $${Math.round(r.amount).toLocaleString()}`); jumpTo("owner_invoice"); }
        catch (e) { this.host.setStatus(`invoice failed: ${(e as Error).message}`); }
      };
      brow.append(seedBtn, pdfBtn, invBtn); billing.appendChild(brow);
      billing.appendChild(Object.assign(document.createElement("div"), { className: "meta",
        textContent: "The G702/G703 pay app and owner invoice draw from this same budget-seeded Schedule of Values." }));
      this.root.appendChild(billing);

      // subcontractor billing — the GC-pays-subs mirror of owner billing
      const subc = document.createElement("div"); subc.className = "dash-card"; subc.style.marginBottom = "10px";
      const sh = document.createElement("div"); sh.className = "section-title";
      sh.style.cssText = "display:flex;justify-content:space-between;align-items:center";
      sh.append(Object.assign(document.createElement("span"), { textContent: "Subcontractor billing" }));
      const openSi = document.createElement("button"); openSi.className = "tool-btn"; openSi.textContent = "open"; openSi.onclick = () => jumpTo("sub_invoice");
      sh.appendChild(openSi); subc.appendChild(sh);
      const sbody = document.createElement("div"); sbody.innerHTML = `<div class="meta">loading…</div>`;
      subc.appendChild(sbody); this.root.appendChild(subc);
      void this.host.api.subcontractorBilling(pid).then((sb) => {
        if (!sb.invoice_count) { sbody.innerHTML = `<div class="meta">No subcontractor invoices yet — log them in Subcontractor Invoices.</div>`; return; }
        const t = sb.totals;
        sbody.innerHTML = `<div class="meta" style="margin-bottom:4px">${sb.subs.length} subs · billed <b>${usd(t.billed)}</b> of ${usd(t.contract_value)} `
          + `· retainage ${usd(t.retainage)} · paid ${usd(t.paid)} · remaining ${usd(t.remaining)}</div>`;
        for (const s of sb.subs.slice(0, 8)) {
          const r = document.createElement("div"); r.className = "meta"; r.style.margin = "1px 0";
          r.innerHTML = `${s.vendor ?? s.subcontract_ref ?? "—"}${s.trade ? ` · ${s.trade}` : ""}: billed <b>${usd(s.billed)}</b>`
            + (s.contract_value ? ` / ${usd(s.contract_value)}` : "") + ` · retainage ${usd(s.retainage)} · paid ${usd(s.paid)}`;
          sbody.appendChild(r);
        }
      }).catch(() => { sbody.innerHTML = `<div class="meta">Subcontractor billing unavailable.</div>`; });

      // cash-flow / draw curve — the cost-loaded schedule (monthly bars + cumulative S-curve)
      const cfCard = document.createElement("div"); cfCard.className = "dash-card"; cfCard.style.marginBottom = "10px";
      cfCard.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Cash flow (cost-loaded schedule)" }));
      const cfBody = document.createElement("div"); cfBody.innerHTML = `<div class="meta">loading cash flow…</div>`;
      cfCard.appendChild(cfBody); this.root.appendChild(cfCard);
      void this.host.api.budgetCashflow(pid).then((cf) => {
        if (!cf.series.length) { cfBody.innerHTML = `<div class="meta">No cash flow yet — give schedule activities a budgeted cost + start/finish dates.</div>`; return; }
        const W = 560, H = 130, pad = 22, n = cf.series.length;
        const maxCost = Math.max(...cf.series.map((s) => s.cost), 1);
        const bw = (W - pad * 2) / n;
        const bars = cf.series.map((s, i) => {
          const h = (s.cost / maxCost) * (H - pad * 2);
          return `<rect x="${pad + i * bw + 1}" y="${H - pad - h}" width="${Math.max(1, bw - 2)}" height="${h}" fill="var(--accent)" opacity="0.55"/>`;
        }).join("");
        const pts = cf.series.map((s, i) => `${pad + i * bw + bw / 2},${(H - pad) - (s.pct / 100) * (H - pad * 2)}`).join(" ");
        const ticks = cf.series.map((s, i) => (i % Math.ceil(n / 6) === 0
          ? `<text x="${pad + i * bw + bw / 2}" y="${H - 6}" fill="var(--muted)" font-size="8" text-anchor="middle">${s.month.slice(2)}</text>` : "")).join("");
        cfBody.innerHTML = `<div class="meta" style="margin-bottom:4px">Total <b>${usd(cf.total)}</b> over ${cf.months} months · peak ${usd(cf.peak_month_cost)}/mo · ${cf.loaded_activities} cost-loaded activities</div>`
          + `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="cash flow curve">${bars}`
          + `<polyline points="${pts}" fill="none" stroke="var(--status-good)" stroke-width="1.5"/>${ticks}</svg>`;
      }).catch(() => { cfBody.innerHTML = `<div class="meta">Cash flow unavailable.</div>`; });

      const foot = document.createElement("div"); foot.className = "meta"; foot.style.marginTop = "2px";
      foot.innerHTML = `Staffing projection ${usd(b.staffing.projected)} across ${b.staffing.headcount_roles} roles · `
        + `markups: ${g.markups.overhead_pct}% OH · ${g.markups.fee_pct}% fee · ${g.markups.contingency_pct}% contingency`;
      this.root.appendChild(foot);
    }).catch(() => {
      status.className = "empty-state";
      status.innerHTML = `Budget not available yet<span class="es-hint">Add cost codes + budget lines, a staffing plan, bid packages, and a prime contract with markup % — then the GMP assembles here.</span>`;
    });
  }

  /** Unified schedule visuals for the GC Schedule module: Gantt + Line-of-Balance (the same
   *  activities that drive the 3D 4D scrub) + a CPM critical-path summary. */
  private async renderScheduleViews(m: ModuleDef) {
    const pid = this.host.projectId()!;
    this.root.innerHTML = "";
    this.root.appendChild(this.bar("Schedule", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const intro = document.createElement("div"); intro.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:2px 0 8px";
    const listBtn = document.createElement("button"); listBtn.className = "tool-btn"; listBtn.textContent = "✎ Activities (list)";
    listBtn.title = "Open the activity list to add / edit / import tasks";
    listBtn.onclick = () => { this.activeKey = "schedule_activity"; this.openModule(m); this.buildNav(); };
    const note = document.createElement("span"); note.className = "meta";
    note.innerHTML = "One relational schedule — these views + the 3D <b>4D sequence</b> (Model → ⏱ 4D) share the same activities.";
    intro.append(listBtn, note);
    this.root.appendChild(intro);

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
      void this.host.api.scheduleLookahead(pid, weeks).then((la) => {
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
    this.root.appendChild(laCard); loadLookahead(3);

    // Milestone schedule — key dates with status
    const msCard = document.createElement("div"); msCard.className = "dash-card"; msCard.style.marginBottom = "10px";
    msCard.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: "Milestones" }));
    const msBody = document.createElement("div"); msBody.innerHTML = `<div class="meta">loading…</div>`; msCard.appendChild(msBody);
    void this.host.api.scheduleMilestones(pid).then((ms) => {
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
    this.root.appendChild(msCard);

    // CPM summary line (critical path + float)
    const cpmBox = document.createElement("div"); cpmBox.className = "meta"; cpmBox.style.margin = "0 0 8px";
    cpmBox.textContent = "Computing critical path…"; this.root.appendChild(cpmBox);
    void this.host.api.scheduleCpm(pid).then((c) => {
      if (!c.activity_count) { cpmBox.textContent = "CPM: no activities with durations yet."; return; }
      const cp = c.critical_path.slice(0, 12).join(" → ") || "—";
      cpmBox.innerHTML = `<b>CPM</b>: project ${c.project_duration}d · ${c.critical_count}/${c.activity_count} on the `
        + `<span style="color:var(--status-crit)">critical path</span>${c.has_cycle ? " · ⚠ cycle broken" : ""}<br>`
        + `<span class="meta">Critical: ${cp}</span>`;
    }).catch(() => { cpmBox.textContent = "CPM unavailable."; });

    // Earned value (schedule performance) — SPI + dollar schedule variance
    const evBox = document.createElement("div"); evBox.className = "meta"; evBox.style.margin = "0 0 8px";
    evBox.textContent = "Computing earned value…"; this.root.appendChild(evBox);
    void this.host.api.scheduleEarnedValue(pid).then((e) => {
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
      void this.host.api.scheduleVariance(pid).then((v) => {
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
      if (!confirm("Snapshot the current schedule as the baseline? Variance will be measured against it (re-baseline anytime).")) return;
      try { const b = await this.host.api.setBaseline(pid); this.host.setStatus(`baseline set (${b.count} activities)`); loadVariance(); }
      catch (e) { this.host.setStatus(`baseline failed: ${(e as Error).message}`); }
    };
    this.root.appendChild(blCard); loadVariance();

    // Gantt + Line-of-Balance, fetched as inline SVG
    for (const [kind, title] of [["gantt", "Gantt"], ["lob", "Line of Balance (linear)"]] as const) {
      const card = document.createElement("div"); card.className = "dash-card"; card.style.marginBottom = "10px";
      card.appendChild(Object.assign(document.createElement("div"), { className: "section-title", textContent: title }));
      const holder = document.createElement("div"); holder.style.overflowX = "auto";
      holder.innerHTML = `<div class="meta">loading ${title}…</div>`;
      card.appendChild(holder); this.root.appendChild(card);
      void this.host.api.scheduleSvg(pid, kind).then((svg) => { holder.innerHTML = svg; })
        .catch(() => { holder.innerHTML = `<div class="meta">No ${title.toLowerCase()} yet — add activities with start/finish dates.</div>`; });
    }
  }

  private async openModule(m: ModuleDef, filter: { q?: string; state?: string; offset?: number } = {}) {
    const pid = this.host.projectId()!;
    this.pushRecent(m.key);
    this.skeleton(`Loading ${m.name}…`);
    const PAGE = 100, offset = filter.offset ?? 0;          // page large modules so they never render 1000s of rows
    const page = await this.host.api.moduleRecordsFiltered(pid, m.key, { ...filter, limit: PAGE + 1, offset });
    const hasMore = page.length > PAGE;
    const records = hasMore ? page.slice(0, PAGE) : page;
    this.root.innerHTML = "";
    this.root.appendChild(this.bar(m.name, () => this.renderHome()));

    const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;margin:6px 0;flex-wrap:wrap;align-items:center";
    const newBtn = document.createElement("button"); newBtn.className = "tool-btn"; newBtn.dataset.cap = "review"; newBtn.textContent = "+ New";
    newBtn.onclick = () => this.renderForm(m);
    const boardBtn = document.createElement("button"); boardBtn.className = "tool-btn"; boardBtn.textContent = "▦ Board";
    boardBtn.onclick = () => this.renderBoard(m);
    const csvBtn = document.createElement("button"); csvBtn.className = "tool-btn"; csvBtn.textContent = "↓ CSV";
    csvBtn.onclick = () => window.open(this.host.api.url(`/projects/${pid}/modules/${m.key}/export.csv`), "_blank");
    // filter box + state dropdown
    const fbox = document.createElement("input"); fbox.type = "search"; fbox.placeholder = "filter…";
    fbox.value = filter.q ?? ""; fbox.className = "portal-filter";
    fbox.onkeydown = (e) => { if (e.key === "Enter") this.openModule(m, { ...filter, q: fbox.value || undefined }); };
    const stateSel = document.createElement("select"); stateSel.className = "sb-sel";
    const anyOpt = document.createElement("option"); anyOpt.value = ""; anyOpt.textContent = "any state"; stateSel.appendChild(anyOpt);
    for (const s of m.workflow.states ?? []) { const o = document.createElement("option"); o.value = o.textContent = s; stateSel.appendChild(o); }
    stateSel.value = filter.state ?? "";
    stateSel.onchange = () => this.openModule(m, { ...filter, state: stateSel.value || undefined });
    // saved views (server-side, per user+module; falls back to empty if offline)
    const views = await this.host.api.listViews(pid, m.key).catch(() => []);
    const viewSel = document.createElement("select"); viewSel.className = "sb-sel"; viewSel.title = "Saved views";
    const vNone = document.createElement("option"); vNone.value = ""; vNone.textContent = "views…"; viewSel.appendChild(vNone);
    for (const v of views) { const o = document.createElement("option"); o.value = v.id; o.textContent = v.name; viewSel.appendChild(o); }
    viewSel.onchange = () => { const v = views.find((x) => x.id === viewSel.value); if (v) { this.sort[m.key] = v.config.sort; void this.host.api.markViewSeen(pid, m.key, v.id).catch(() => {}); this.openModule(m, { q: v.config.q, state: v.config.state }); } };
    const saveView = document.createElement("button"); saveView.className = "tool-btn"; saveView.textContent = "＋view";
    saveView.title = "Save current filter/sort as a view (synced to your account)";
    saveView.onclick = async () => {
      const v = await promptModal("Save view", [{ name: "name", label: "View name", required: true }], "Save");
      if (!v) return;
      await this.host.api.saveView(pid, m.key, v.name, { q: filter.q, state: filter.state, sort: this.sort[m.key] });
      this.openModule(m, filter);
    };
    // reusable templates: apply a saved set of records, or save the current ones as a template
    const tplBtn = document.createElement("button"); tplBtn.className = "tool-btn"; tplBtn.dataset.cap = "review"; tplBtn.textContent = "⌹ Templates";
    tplBtn.title = "Apply or save a reusable template for this module";
    tplBtn.onclick = async () => {
      const tpls = await this.host.api.templates(m.key).catch(() => []);
      let pick = "";
      if (tpls.length) {
        const v = await promptModal(`${m.name} templates`,
          [{ name: "pick", label: "Template # to apply (blank = save current as new)" }], "Apply",
          tpls.map((t, i) => `${i + 1}. ${t.name} (${t.item_count})`).join("\n"));
        if (!v) return;
        pick = v.pick;
      } else {
        toast(`No ${m.name} templates yet — saving the current records as one.`, "info");
      }
      if (pick && pick.trim()) {
        const t = tpls[parseInt(pick) - 1];
        if (!t) return;
        const r = await this.host.api.applyTemplate(pid, m.key, t.id);
        this.host.setStatus(`applied "${r.applied}" — ${r.created} record(s)`);
        this.openModule(m, filter);
      } else {
        const nv = await promptModal("Save template",
          [{ name: "name", label: "Template name", required: true }], "Save");
        if (!nv) return;
        try { const s = await this.host.api.saveTemplate(pid, m.key, nv.name); this.host.setStatus(`saved template (${s.item_count} items)`); }
        catch (e) { this.host.setStatus(`couldn't save: ${(e as Error).message}`); }
      }
    };
    // generic Excel/CSV import (any module): pick a file -> map columns -> preview -> import
    const impBtn = document.createElement("button"); impBtn.className = "tool-btn"; impBtn.dataset.cap = "review";
    impBtn.textContent = "⤓ Import"; impBtn.title = "Import records from an Excel (.xlsx) or CSV file with column mapping";
    const impFile = document.createElement("input"); impFile.type = "file"; impFile.accept = ".xlsx,.xlsm,.csv"; impFile.style.display = "none";
    impFile.onchange = () => { const f = impFile.files?.[0]; if (f) void this.renderImport(m, f); impFile.value = ""; };
    impBtn.onclick = () => impFile.click();
    actions.append(newBtn, boardBtn, csvBtn, impBtn, impFile, tplBtn, fbox, stateSel, viewSel, saveView);
    // the Schedule module is the relational home for the same activities behind Gantt / LOB / CPM /
    // the 3D 4D scrub — surface those views here so linear + gantt live with the GC schedule.
    if (m.key === "schedule_activity") {
      const sv = document.createElement("button"); sv.className = "tool-btn"; sv.textContent = "📊 Views";
      sv.onclick = () => this.renderScheduleViews(m);
      actions.append(sv);
    }
    // coordination issues round-trip via BCF with other BIM tools (Solibri/ACC/BIMcollab)
    if (m.key === "coordination_issue") {
      const exp = document.createElement("button"); exp.className = "tool-btn"; exp.textContent = "⬇ BCF";
      exp.title = "Export these coordination issues as a BCF .bcfzip";
      exp.onclick = async () => {
        try {
          const blob = await this.host.api.downloadModuleBcf(pid, m.key);
          const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
          a.download = "coordination_issues.bcfzip"; a.click(); URL.revokeObjectURL(a.href);
          this.host.setStatus("exported BCF");
        } catch (e) { this.host.setStatus(`BCF export failed: ${(e as Error).message}`); }
      };
      const impInput = document.createElement("input"); impInput.type = "file"; impInput.accept = ".bcfzip,.bcf,application/zip";
      impInput.style.display = "none";
      impInput.onchange = async () => {
        const f = impInput.files?.[0]; if (!f) return;
        try { const r = await this.host.api.importModuleBcf(pid, m.key, f);
          this.host.setStatus(`imported ${r.count} BCF issue${r.count === 1 ? "" : "s"}`); this.openModule(m); }
        catch (e) { this.host.setStatus(`BCF import failed: ${(e as Error).message}`); }
      };
      const imp = document.createElement("button"); imp.className = "tool-btn"; imp.dataset.cap = "review";
      imp.textContent = "⬆ Import BCF"; imp.title = "Import a BCF .bcfzip from another BIM tool";
      imp.onclick = () => impInput.click();
      actions.append(exp, imp, impInput);
    }
    // permits seed from municipal open data (NYC/SF/Chicago/LA/Austin… interchangeable cities)
    if (m.key === "permit") {
      const imp = document.createElement("button"); imp.className = "tool-btn"; imp.dataset.cap = "review";
      imp.textContent = "🏛 Import from city open data";
      imp.title = "Pull issued/filed permits for the site from a city's open data and add them to this log";
      imp.onclick = () => void this.openPermitImport(m);
      actions.append(imp);
    }
    this.root.appendChild(actions);

    if (!records.length) {
      const e = document.createElement("div"); e.className = "empty-state";
      e.innerHTML = filter.q || filter.state
        ? `No matching records<span class="es-hint">Try clearing the filter or state.</span>`
        : `No ${m.name.toLowerCase()} yet<span class="es-hint">Use “+ New” to create the first one.</span>`;
      this.root.appendChild(e);
      return;
    }

    // columns: module.json list_columns, else first 2 input fields; always ref/status/assignee
    const inputFields = m.fields.filter((f) => f.type !== "rollup" && f.type !== "signature");
    const cols = (m.list_columns ?? inputFields.slice(0, 2).map((f) => f.name))
      .map((name) => m.fields.find((f) => f.name === name)).filter(Boolean) as ModuleDef["fields"];

    // sort
    const sort = this.sort[m.key];
    const val = (r: ModuleRecord, col: string) => col === "ref" ? r.ref : col === "status" ? r.workflow_state
      : col === "assignee" ? (r.assignee ?? "") : col === "title" ? (r.title ?? "") : (r.data[col] ?? "");
    if (sort) records.sort((a, b) => { const x = val(a, sort.col), y = val(b, sort.col); return (x < y ? -1 : x > y ? 1 : 0) * sort.dir; });

    // bulk action bar
    const selected = new Set<string>();
    const bulkBar = document.createElement("div"); bulkBar.className = "bulk-bar"; bulkBar.hidden = true;
    const bulkCount = document.createElement("span"); bulkCount.className = "meta";
    const syncBulk = () => { bulkBar.hidden = selected.size === 0; bulkCount.textContent = `${selected.size} selected`; };
    // apply a bulk action to the selection, then toast + reload (no more raw prompt() pickers)
    const runBulk = async (action: "assign" | "transition" | "delete", verb: string, value?: string) => {
      const n = selected.size; if (!n) return;
      try {
        await this.host.api.bulkAction(pid, m.key, [...selected], action, value);
        toast(`${verb} ${n} ${m.name.toLowerCase()} record${n === 1 ? "" : "s"}`, "info");
        this.openModule(m, filter);
      } catch (e) { this.host.setStatus(`bulk action failed: ${(e as Error).message}`); }
    };
    bulkBar.append(bulkCount);
    // Transition: a dropdown of valid workflow actions + Apply
    const txActions = [...new Set((m.workflow.transitions ?? []).map((t) => t.action))];
    if (txActions.length) {
      const txSel = document.createElement("select"); txSel.className = "sb-sel";
      const d = document.createElement("option"); d.value = ""; d.textContent = "Transition…"; txSel.appendChild(d);
      for (const a of txActions) { const o = document.createElement("option"); o.value = o.textContent = a; txSel.appendChild(o); }
      const txBtn = document.createElement("button"); txBtn.className = "tool-btn"; txBtn.textContent = "Apply";
      txBtn.onclick = () => { if (txSel.value) void runBulk("transition", "Transitioned", txSel.value); };
      bulkBar.append(txSel, txBtn);
    }
    // Assign: an input + Assign
    const asgIn = document.createElement("input"); asgIn.type = "text"; asgIn.placeholder = "assign to…"; asgIn.className = "portal-filter"; asgIn.style.maxWidth = "140px";
    const asgBtn = document.createElement("button"); asgBtn.className = "tool-btn"; asgBtn.textContent = "Assign";
    asgBtn.onclick = () => void runBulk("assign", "Assigned", asgIn.value.trim());
    // Delete (kept behind a confirm)
    const delBtn = document.createElement("button"); delBtn.className = "tool-btn"; delBtn.textContent = "Delete";
    delBtn.onclick = () => { if (confirm(`Delete ${selected.size} record(s)? This cannot be undone.`)) void runBulk("delete", "Deleted"); };
    bulkBar.append(asgIn, asgBtn, delBtn);
    this.root.appendChild(bulkBar);

    const rowCbs: HTMLInputElement[] = [];
    const table = document.createElement("table"); table.className = "portal-table";
    const headRow = document.createElement("tr");
    const selAllTh = document.createElement("th");      // select-all (builders act in batches)
    const selAll = document.createElement("input"); selAll.type = "checkbox"; selAll.title = "Select all";
    selAll.onclick = (e) => {
      e.stopPropagation();
      for (const r of records) selAll.checked ? selected.add(r.id) : selected.delete(r.id);
      for (const cb of rowCbs) cb.checked = selAll.checked;
      syncBulk();
    };
    selAllTh.appendChild(selAll); headRow.appendChild(selAllTh);
    const th = (label: string, col: string) => {
      const h = document.createElement("th"); h.textContent = label + (sort?.col === col ? (sort.dir === 1 ? " ▲" : " ▼") : "");
      h.style.cursor = "pointer";
      h.onclick = () => { const cur = this.sort[m.key]; this.sort[m.key] = { col, dir: cur?.col === col && cur.dir === 1 ? -1 : 1 }; this.openModule(m, filter); };
      headRow.appendChild(h);
    };
    th("Ref", "ref"); th("Title", "title");
    for (const c of cols) th(c.label, c.name);
    th("Assignee", "assignee"); th("Ball", ""); th("Status", "status");
    const thead = document.createElement("thead"); thead.appendChild(headRow); table.appendChild(thead);

    const tb = document.createElement("tbody");
    for (const r of records) {
      const tr = document.createElement("tr");
      const cbTd = document.createElement("td");
      const cb = document.createElement("input"); cb.type = "checkbox"; rowCbs.push(cb);
      cb.onclick = (e) => { e.stopPropagation(); if (cb.checked) selected.add(r.id); else selected.delete(r.id); selAll.checked = selected.size === records.length; syncBulk(); };
      cbTd.appendChild(cb); cbTd.onclick = (e) => e.stopPropagation(); tr.appendChild(cbTd);
      // textContent, not innerHTML: titles/field values are user data (stored-XSS guard)
      const cell = (text: string) => { const td = document.createElement("td"); td.textContent = text; tr.appendChild(td); };
      cell(r.ref); cell(r.title ?? "");
      for (const c of cols) cell(this.fmtCell(c, r.data[c.name]));
      tr.appendChild(this.assigneeCell(pid, m, r));   // inline-editable
      tr.appendChild(this.ballCell(m, r));            // ball-in-court party (who owes the next move)
      tr.appendChild(this.statusCell(pid, m, r));     // inline workflow transition
      tr.onclick = () => this.openRecord(m, r.id);
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    this.root.appendChild(table);

    // pager — only shown when the list spills past one page (keeps large modules snappy)
    if (offset > 0 || hasMore) {
      const pager = document.createElement("div");
      pager.style.cssText = "display:flex;gap:8px;align-items:center;margin:8px 0";
      const prev = document.createElement("button"); prev.className = "tool-btn"; prev.textContent = "‹ Prev";
      prev.disabled = offset === 0;
      prev.onclick = () => this.openModule(m, { ...filter, offset: Math.max(0, offset - PAGE) });
      const next = document.createElement("button"); next.className = "tool-btn"; next.textContent = "Next ›";
      next.disabled = !hasMore;
      next.onclick = () => this.openModule(m, { ...filter, offset: offset + PAGE });
      const lbl = document.createElement("span"); lbl.className = "meta";
      lbl.textContent = `${offset + 1}–${offset + records.length}${hasMore ? "+" : ""}`;
      pager.append(prev, lbl, next); this.root.appendChild(pager);
    }
  }

  /** Ball-in-court: which party(ies) own the next action from the current state, read straight from
   *  the workflow transitions. The "who owes the next move" signal both supers and PMs scan for. */
  private ballInCourt(m: ModuleDef, state: string): string[] {
    const parties = new Set<string>();
    for (const t of m.workflow?.transitions ?? []) {
      if (t.from === state) (t.party ?? []).forEach((p) => p && parties.add(p));
    }
    return [...parties];
  }
  private ballCell(m: ModuleDef, r: ModuleRecord): HTMLTableCellElement {
    const td = document.createElement("td");
    const parties = this.ballInCourt(m, r.workflow_state);
    td.innerHTML = parties.length
      ? parties.map((p) => `<span class="ball-badge">${p}</span>`).join(" ")
      : `<span class="meta">—</span>`;
    return td;
  }

  /** C1 — create a pre-filled, linked record in another module (e.g. RFI → Change Event). */
  private async convert(m: ModuleDef, r: ModuleRecord, c: Conversion) {
    const pid = this.host.projectId()!;
    const tgt = this.mods.find((x) => x.key === c.to);
    if (!tgt) return;
    if (!confirm(`Create a ${tgt.name} from ${r.ref}? It will be pre-filled and linked back to ${r.ref}.`)) return;
    try {
      const data = c.map(r.data);
      if (c.back) data[c.back] = r.id;                 // back-reference field on the new record → this record
      for (const k of Object.keys(data)) if (data[k] === undefined || data[k] === "") delete data[k];
      const nv = await this.host.api.createModuleRecord(pid, c.to, { data });
      if (!c.back) await this.host.api.linkRecord(pid, m.key, r.id, c.to, nv.id);  // else use an explicit link
      toast(`Created ${nv.ref} from ${r.ref}`, "info");
      this.host.onPinsChanged();
      this.openRecord(tgt, nv.id);
    } catch (e) { toast(`convert failed: ${(e as Error).message}`, "error"); }
  }

  /** Format a field value for a compact table cell. */
  private fmtCell(f: ModuleDef["fields"][number], v: unknown): string {
    if (v == null || v === "") return "";
    if (f.type === "currency") return `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
    if (f.type === "multiselect" && Array.isArray(v)) return (v as string[]).join(", ");
    if (f.type === "reference") return String(v).slice(0, 8);
    return String(v).slice(0, 40);
  }

  /** Inline-editable assignee cell — click to reassign without opening the record.
   *  Mutates r in place + persists via the assign endpoint (server still gates by role). */
  private assigneeCell(pid: string, m: ModuleDef, r: ModuleRecord): HTMLTableCellElement {
    const td = document.createElement("td"); td.className = "editable"; td.title = "Click to reassign";
    const show = () => { td.textContent = r.assignee ?? "—"; };
    show();
    td.onclick = (e) => {
      e.stopPropagation();
      if (td.querySelector("input")) return;
      const inp = document.createElement("input"); inp.className = "portal-filter";
      inp.value = r.assignee ?? ""; inp.style.width = "110px"; inp.placeholder = "user";
      td.textContent = ""; td.appendChild(inp); inp.focus();
      inp.onclick = (ev) => ev.stopPropagation();
      inp.onkeydown = (ev) => { if (ev.key === "Enter") inp.blur(); else if (ev.key === "Escape") { inp.value = r.assignee ?? ""; inp.blur(); } };
      inp.onblur = async () => {
        const v = inp.value.trim();
        if (v === (r.assignee ?? "")) { show(); return; }
        try { const u = await this.host.api.assignRecord(pid, m.key, r.id, v || null); r.assignee = u.assignee ?? null; this.host.setStatus(`${r.ref} assigned → ${r.assignee ?? "unassigned"}`); }
        catch (err) { this.host.setStatus(`assign blocked: ${(err as Error).message}`); }
        show();
      };
    };
    return td;
  }

  /** Inline status cell — a dropdown of the workflow transitions valid from the current state
   *  (terminal states stay read-only). Selecting one calls /transition; party gates apply server-side. */
  private statusCell(pid: string, m: ModuleDef, r: ModuleRecord): HTMLTableCellElement {
    const td = document.createElement("td");
    const render = () => { td.innerHTML = `<span class="badge">${r.workflow_state}</span>`; };
    render();
    const nexts = (m.workflow.transitions ?? []).filter((t) => t.from === r.workflow_state);
    if (!nexts.length) return td;          // terminal — nothing to transition to
    td.className = "editable"; td.title = "Click to change status";
    td.onclick = (e) => {
      e.stopPropagation();
      if (td.querySelector("select")) return;
      const sel = document.createElement("select"); sel.className = "sb-sel";
      const cur = document.createElement("option"); cur.value = ""; cur.textContent = r.workflow_state; sel.appendChild(cur);
      for (const t of nexts) { const o = document.createElement("option"); o.value = t.action; o.textContent = `${t.action} → ${t.to}`; sel.appendChild(o); }
      td.textContent = ""; td.appendChild(sel); sel.focus();
      sel.onclick = (ev) => ev.stopPropagation();
      sel.onblur = () => render();
      sel.onchange = async () => {
        if (!sel.value) { render(); return; }
        try { const u = await this.host.api.transitionRecord(pid, m.key, r.id, sel.value); r.workflow_state = u.workflow_state; this.host.setStatus(`${r.ref} → ${r.workflow_state}`); }
        catch (err) { this.host.setStatus(`transition blocked: ${(err as Error).message}`); }
        render();
      };
    };
    return td;
  }

  // --- generic Excel/CSV import: map columns -> fields, preview, import -------
  private async renderImport(m: ModuleDef, file: File) {
    const pid = this.host.projectId()!;
    this.root.innerHTML = "";
    this.root.appendChild(this.bar(`Import ${m.name}`, () => this.openModule(m)));
    const wrap = document.createElement("div"); wrap.className = "portal-form"; this.root.appendChild(wrap);
    const status = document.createElement("div"); status.className = "meta"; status.textContent = `Reading ${file.name}…`;
    wrap.appendChild(status);
    let pv: Awaited<ReturnType<typeof this.host.api.importPreview>>;
    try { pv = await this.host.api.importPreview(pid, m.key, file); }
    catch (e) { status.textContent = `Couldn't read the file: ${(e as Error).message}`; return; }

    status.textContent = `${pv.row_count} row(s) found in ${file.name}. Map each spreadsheet column to a field, then import.`;
    const tmpl = document.createElement("a"); tmpl.href = this.host.api.importTemplateUrl(pid, m.key);
    tmpl.textContent = "↓ download a blank template"; tmpl.style.cssText = "font-size:12px;margin-left:8px"; tmpl.target = "_blank";
    status.appendChild(tmpl);

    // mapping table: one row per source column -> a field <select>
    const selects: { header: string; sel: HTMLSelectElement }[] = [];
    const tbl = document.createElement("table"); tbl.className = "portal-table"; tbl.style.marginTop = "8px";
    const thead = document.createElement("tr");
    for (const h of ["Spreadsheet column", "→ Field", "Sample"]) { const th = document.createElement("th"); th.textContent = h; thead.appendChild(th); }
    tbl.appendChild(thead);
    for (const h of pv.headers) {
      const tr = document.createElement("tr");
      const c1 = document.createElement("td"); c1.textContent = h; c1.style.fontFamily = "monospace";
      const c2 = document.createElement("td");
      const sel = document.createElement("select"); sel.className = "sb-sel";
      const skip = document.createElement("option"); skip.value = ""; skip.textContent = "— skip —"; sel.appendChild(skip);
      for (const f of pv.fields) {
        const o = document.createElement("option"); o.value = f.name; o.textContent = f.label + (f.required ? " *" : ""); sel.appendChild(o);
      }
      sel.value = pv.suggested_mapping[h] ?? "";
      selects.push({ header: h, sel }); c2.appendChild(sel);
      const c3 = document.createElement("td"); c3.style.color = "var(--muted)";
      const fld = pv.suggested_mapping[h];
      c3.textContent = fld && pv.sample[0] ? String(pv.sample[0][fld] ?? "") : "";
      tr.append(c1, c2, c3); tbl.appendChild(tr);
    }
    wrap.appendChild(tbl);

    const req = pv.fields.filter((f) => f.required).map((f) => f.name);
    const warn = document.createElement("div"); warn.className = "meta"; warn.style.color = "var(--warn, #c60)"; wrap.appendChild(warn);
    const importBtn = document.createElement("button"); importBtn.className = "tool-btn"; importBtn.textContent = `Import ${pv.row_count} row(s)`;
    importBtn.style.marginTop = "8px";
    const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "8px";
    const checkReq = () => {
      const mapped = new Set(selects.map((s) => s.sel.value).filter(Boolean));
      const missing = req.filter((r) => !mapped.has(r));
      warn.textContent = missing.length ? `⚠ Required field(s) not mapped: ${missing.map((n) => pv.fields.find((f) => f.name === n)?.label ?? n).join(", ")}` : "";
      importBtn.disabled = missing.length > 0;
    };
    for (const s of selects) s.sel.onchange = checkReq;
    checkReq();
    importBtn.onclick = async () => {
      const mapping: Record<string, string> = {};
      for (const s of selects) if (s.sel.value) mapping[s.header] = s.sel.value;
      importBtn.disabled = true; out.textContent = "Importing…";
      try {
        const r = await this.host.api.importModuleRecords(pid, m.key, file, mapping);
        out.innerHTML = "";
        const ok = document.createElement("div");
        ok.textContent = `✓ Imported ${r.imported} record(s)${r.error_count ? ` · ${r.error_count} row(s) skipped` : ""}${r.truncated ? " · file truncated at the row cap" : ""}.`;
        out.appendChild(ok);
        for (const er of r.errors.slice(0, 10)) { const e = document.createElement("div"); e.style.color = "var(--warn,#c60)"; e.textContent = `Row ${er.row}: ${er.error}`; out.appendChild(e); }
        const done = document.createElement("button"); done.className = "tool-btn"; done.style.marginTop = "6px"; done.textContent = "← Back to the list";
        done.onclick = () => this.openModule(m); out.appendChild(done);
        this.host.setStatus(`imported ${r.imported} ${m.name} record(s)`);
      } catch (e) { out.textContent = `Import failed: ${(e as Error).message}`; importBtn.disabled = false; }
    };
    wrap.append(importBtn, out);
  }

  // --- create / edit form (fields from module.json) --------------------------
  private async renderForm(m: ModuleDef, existing?: ModuleRecord) {
    const pid = this.host.projectId()!;
    const editing = !!existing;
    // reference fields need their target module's records as options — fetch up front
    const refOpts = new Map<string, { id: string; label: string }[]>();
    await Promise.all(m.fields.filter((f) => f.type === "reference" && f.module).map(async (f) => {
      const recs = await this.host.api.moduleRecords(pid, f.module!);
      refOpts.set(f.name, recs.map((r) => ({ id: r.id, label: `${r.ref} — ${r.title ?? ""}` })));
    }));
    // E1 — project-level custom select options, merged into the module.json options below
    const custom = await this.host.api.enumOptions(pid).catch(() => ({} as Record<string, Record<string, string[]>>));
    const optsFor = (f: ModuleDef["fields"][number]) => [...(f.options ?? []), ...((custom[m.key]?.[f.name]) ?? [])];
    // "＋ option" button: add a new enum value to a select/multiselect without editing JSON
    const addOptBtn = (f: ModuleDef["fields"][number], selEl: HTMLSelectElement) => {
      const b = document.createElement("button"); b.type = "button"; b.className = "pf-addopt";
      b.textContent = "＋ option"; b.title = `Add a new ${f.label} option`;
      b.onclick = async () => {
        const v = await promptModal(`Add ${f.label} option`,
          [{ name: "val", label: `New ${f.label} option`, required: true }], "Add");
        if (!v) return;
        const val = v.val;
        try {
          const res = await this.host.api.addEnumOption(pid, m.key, f.name, val.trim());
          let opt = [...selEl.options].find((o) => o.value === res.value);
          if (!opt) { opt = document.createElement("option"); opt.value = opt.textContent = res.value; selEl.appendChild(opt); }
          if (selEl.multiple) opt.selected = true; else selEl.value = res.value;
          toast(`Added ${f.label}: ${res.value}`, "info");
        } catch (e) { toast(`could not add option: ${(e as Error).message}`, "error"); }
      };
      return b;
    };

    this.root.innerHTML = "";
    this.root.appendChild(this.bar(`${editing ? "Edit" : "New"} ${m.name}`,
      () => (editing ? this.openRecord(m, existing!.id) : this.openModule(m))));
    const inputs: Record<string, HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement> = {};
    const sigs: Record<string, () => string> = {};   // signature field getters (data-URI)
    const cur = (n: string) => (existing?.data?.[n] as string | number | string[] | undefined);
    let curFieldset: string | undefined;   // F1 — emit a labeled header when the fieldset changes
    for (const f of m.fields) {
      if (f.type === "rollup") continue;   // computed, not user-entered
      if (f.fieldset && f.fieldset !== curFieldset) {
        curFieldset = f.fieldset;
        const h = document.createElement("div"); h.className = "portal-fieldset-head"; h.textContent = f.fieldset;
        this.root.appendChild(h);
      }
      const wrap = document.createElement("label"); wrap.className = "portal-field";
      wrap.textContent = f.label + (f.required ? " *" : "");
      if (f.type === "signature") {
        sigs[f.name] = this.signaturePad(wrap);
        this.root.appendChild(wrap);
        continue;
      }
      let el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
      if (f.type === "textarea") { el = document.createElement("textarea"); el.value = String(cur(f.name) ?? ""); }
      else if (f.type === "select") {
        el = document.createElement("select");
        const blank = document.createElement("option"); blank.value = ""; blank.textContent = "— select —"; el.appendChild(blank);
        for (const o of optsFor(f)) { const opt = document.createElement("option"); opt.value = opt.textContent = o; el.appendChild(opt); }
        if (cur(f.name) != null) el.value = String(cur(f.name));
      } else if (f.type === "multiselect") {
        const opts = optsFor(f);
        el = document.createElement("select"); el.multiple = true; el.size = Math.min(opts.length, 5);
        const chosen = new Set(Array.isArray(cur(f.name)) ? (cur(f.name) as string[]) : []);
        for (const o of opts) { const opt = document.createElement("option"); opt.value = opt.textContent = o; opt.selected = chosen.has(o); el.appendChild(opt); }
      } else if (f.type === "reference") {
        const sel = document.createElement("select"); el = sel;
        const none = document.createElement("option"); none.value = ""; none.textContent = `— none —`; sel.appendChild(none);
        for (const o of refOpts.get(f.name) ?? []) { const opt = document.createElement("option"); opt.value = o.id; opt.textContent = o.label; sel.appendChild(opt); }
        // D1: inline "add new" — create the referenced record (e.g. a cost code) without leaving the form
        const tgt = this.mods.find((x) => x.key === f.module);
        const addOpt = document.createElement("option"); addOpt.value = "__new__";
        addOpt.textContent = `＋ Add new ${tgt?.name ?? f.module}…`; sel.appendChild(addOpt);
        if (cur(f.name) != null) sel.value = String(cur(f.name));
        // searchable picker: for long lists, a type-to-filter box hides non-matching options
        if ((refOpts.get(f.name) ?? []).length > 8) {
          const fx = document.createElement("input"); fx.type = "search";
          fx.placeholder = `filter ${tgt?.name ?? "records"}…`; fx.className = "portal-filter";
          fx.style.cssText = "display:block;margin-bottom:4px;width:100%";
          fx.oninput = () => {
            const q = fx.value.trim().toLowerCase();
            for (const o of [...sel.options]) {
              if (o.value === "" || o.value === "__new__") continue;
              o.hidden = !!q && !(o.textContent ?? "").toLowerCase().includes(q);
            }
          };
          wrap.appendChild(fx);
        }
        sel.addEventListener("change", async () => {
          if (sel.value !== "__new__") return;
          // the field to set on the new record: the module's title_field, else its first required
          // (or first) field — so e.g. a Cost Code gets `code`, not a non-existent `title`.
          const tgtFields = (tgt?.fields ?? []).filter((x) => x.type !== "rollup");
          const tf = tgt?.title_field || tgtFields.find((x) => x.required)?.name || tgtFields[0]?.name || "title";
          const nv = await promptModal(`New ${tgt?.name ?? f.module}`,
            [{ name: "val", label: tf, required: true }], "Create");
          const val = nv?.val;
          sel.value = String(cur(f.name) ?? "");
          if (!val || !val.trim()) return;
          try {
            const rec = await this.host.api.createModuleRecord(pid, f.module!, { data: { [tf]: val.trim() } });
            const opt = document.createElement("option"); opt.value = rec.id; opt.textContent = `${rec.ref} — ${val.trim()}`;
            sel.insertBefore(opt, addOpt); sel.value = rec.id;
            toast(`Added ${tgt?.name ?? f.module}: ${val.trim()}`, "info");
          } catch { toast(`could not create ${tgt?.name ?? f.module}`, "error"); }
        });
      } else { el = document.createElement("input"); (el as HTMLInputElement).type = (f.type === "number" || f.type === "currency") ? "number" : f.type === "date" ? "date" : "text"; if (f.type === "currency") (el as HTMLInputElement).step = "0.01"; (el as HTMLInputElement).value = String(cur(f.name) ?? ""); }
      inputs[f.name] = el; wrap.appendChild(el);
      if (f.type === "select" || f.type === "multiselect") wrap.appendChild(addOptBtn(f, el as HTMLSelectElement));
      this.root.appendChild(wrap);
    }
    // assignee (drives the cross-module "My work" queue) — set at creation
    const asg = document.createElement("input"); asg.type = "text"; asg.placeholder = "user id";
    if (!editing) {
      const asgWrap = document.createElement("label"); asgWrap.className = "portal-field";
      asgWrap.textContent = "Assignee";
      asgWrap.appendChild(asg); this.root.appendChild(asgWrap);
    }

    // pin-to-model option (create only)
    const pinCb = document.createElement("input"); pinCb.type = "checkbox"; pinCb.checked = m.pinnable;
    if (m.pinnable && !editing) {
      const pinLabel = document.createElement("label"); pinLabel.className = "portal-field";
      pinLabel.append(pinCb, document.createTextNode(" Pin to last-clicked model point"));
      this.root.appendChild(pinLabel);
    }

    // field-level validation: outline offending inputs + focus the first (no more silent 422s)
    const labelOf = (n: string) => m.fields.find((f) => f.name === n)?.label ?? n;
    const markInvalid = (names: string[]) => {
      for (const f of m.fields) { const el = inputs[f.name]; if (el) el.style.borderColor = ""; }
      for (const n of names) { const el = inputs[n]; if (el) el.style.borderColor = "var(--err, #d9534f)"; }
      const first = names.map((n) => inputs[n]).find(Boolean); if (first) first.focus();
    };
    const isEmpty = (f: ModuleDef["fields"][number]): boolean => {
      const el = inputs[f.name]; if (!el) return false;
      if (f.type === "signature") return !sigs[f.name]?.();
      if (f.type === "multiselect") return [...(el as HTMLSelectElement).selectedOptions].length === 0;
      return !String((el as HTMLInputElement).value || "").trim();
    };
    const save = document.createElement("button");
    save.className = "file-btn"; save.textContent = editing ? "Save" : "Create"; save.style.marginTop = "8px";
    save.onclick = async () => {
      // client-side required check before hitting the server
      const missing = m.fields.filter((f) => f.required && f.type !== "rollup" && isEmpty(f)).map((f) => f.name);
      if (missing.length) {
        markInvalid(missing);
        this.host.setStatus(`Please fill required field(s): ${missing.map(labelOf).join(", ")}`);
        return;
      }
      markInvalid([]);
      const data: Record<string, unknown> = {};
      for (const f of m.fields) {
        if (f.type === "rollup") continue;
        if (f.type === "signature") { const s = sigs[f.name]?.(); if (s) data[f.name] = s; continue; }
        const el = inputs[f.name];
        if (f.type === "multiselect") { data[f.name] = [...(el as HTMLSelectElement).selectedOptions].map((o) => o.value); continue; }
        const v = el.value; if (v) data[f.name] = (f.type === "number" || f.type === "currency") ? Number(v) : v;
      }
      try {
        if (editing) {
          await this.host.api.updateModuleRecord(pid, m.key, existing!.id, data);
          this.host.setStatus(`saved ${existing!.ref}`);
          this.openRecord(m, existing!.id);
        } else {
          const body: Record<string, unknown> = { data };
          if (asg.value.trim()) body.assignee = asg.value.trim();
          if (m.pinnable && pinCb.checked) {
            body.anchor = this.host.anchorPoint();
            const g = this.host.selectedGuid(); if (g) body.element_guids = [g];
          }
          const rec = await this.host.api.createModuleRecord(pid, m.key, body);
          this.host.setStatus(`created ${rec.ref}`);
          if (body.anchor) this.host.onPinsChanged();
          this.openRecord(m, rec.id);
        }
      } catch (e) {
        const msg = (e as Error).message;
        const mm = /missing required field\(s\):\s*([^"}]+)/i.exec(msg);   // server-side required rules
        if (mm) { const names = mm[1].split(",").map((s) => s.trim()).filter(Boolean); markInvalid(names); }
        this.host.setStatus(`error: ${msg}`);
      }
    };
    this.root.appendChild(save);
  }

  /** Compact workflow state diagram — states left→right in declared order, current one highlighted,
   *  with reachable next states shown as arrows. Reads the module's workflow (no server call). */
  private workflowMap(m: ModuleDef, current: string): HTMLElement {
    const states = m.workflow.states ?? [];
    const wrap = document.createElement("div"); wrap.className = "wf-map";
    wrap.style.cssText = "display:flex;align-items:center;flex-wrap:wrap;gap:2px;margin:4px 0 8px;font-size:11px";
    const nexts = new Set((m.workflow.transitions ?? []).filter((t) => t.from === current).map((t) => t.to));
    states.forEach((s, i) => {
      if (i) { const arr = document.createElement("span"); arr.textContent = "→"; arr.style.opacity = "0.4"; wrap.appendChild(arr); }
      const node = document.createElement("span");
      const isCur = s === current, isNext = nexts.has(s);
      node.textContent = s.replace(/_/g, " ");
      node.style.cssText = "padding:2px 7px;border-radius:10px;white-space:nowrap;border:1px solid var(--border,#3a4654);"
        + (isCur ? "background:var(--accent,#4a8cff);color:#fff;font-weight:700;"
                 : isNext ? "background:rgba(74,140,255,0.16);" : "opacity:0.55;");
      wrap.appendChild(node);
    });
    return wrap;
  }

  // --- record detail + workflow actions + activity ---------------------------
  // contract modules → the document they generate, and whether an Exhibit A applies
  private static CONTRACT_DOCS: Record<string, { doc: string; label: string; exhibit: boolean }> = {
    prime_contract: { doc: "prime", label: "Prime Contract", exhibit: false },
    subcontract: { doc: "agreement", label: "Subcontract", exhibit: true },
    commitment: { doc: "agreement", label: "Agreement", exhibit: true },
    cor: { doc: "co", label: "Change Order", exhibit: false },
  };

  /** Contract lifecycle actions on a contract/CO record: generate the document, compose Exhibit A,
   *  open it with redline/markup tools, and capture signatures — with a signed-by status line. */
  private contractActions(m: ModuleDef, r: ModuleRecord, rid: string, tools: HTMLElement) {
    const spec = PortalUI.CONTRACT_DOCS[m.key];
    if (!spec) return;
    const pid = this.host.projectId()!;
    const api = this.host.api;
    const btn = (label: string, title: string, fn: () => void) => {
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label; b.title = title; b.onclick = fn; tools.appendChild(b);
    };
    btn(`📄 Generate ${spec.label}`, "Generate the contract document (PDF)",
        () => window.open(api.contractDocUrl(pid, m.key, rid, spec.doc), "_blank"));
    if (spec.exhibit) btn("📐 Compose Exhibit A", "Build the scope-of-work exhibit from the clause library", () => void this.composeExhibit(m, r, rid));
    btn("🖊 View & markup", "Open the document with redline / markup tools", async () => {
      try {
        const res = await fetch(api.contractDocUrl(pid, m.key, rid, spec.doc), { headers: api.authHeaders() });
        const file = new File([await res.arrayBuffer()], `${spec.doc}-${r.ref}.pdf`, { type: "application/pdf" });
        const mod = await import("../drawings/pdfTakeoff"); await mod.openPdfTakeoff(file);
      } catch (e) { toast(`couldn't open document: ${(e as Error).message}`, "error"); }
    });
    btn("✍ Sign", "Record a party's signature", () => void this.signContract(m, r, rid));
    btn("🔏 Digitally sign", "Apply a tamper-evident PAdES digital signature to the document", async () => {
      try {
        const res = await api.digitalSignContract(pid, m.key, rid);
        toast(`digitally signed (${res.kind}) · cert ${res.fingerprint.slice(0, 8)}…`, "success");
        void this.openRecord(m, rid);
      } catch (e) { toast(`digital sign failed: ${(e as Error).message}`, "error"); }
    });
    btn("📨 Send for signature", "Route through the configured e-signature provider (DocuSeal etc.)", async () => {
      try {
        const st = await api.esignStatus();
        if (!st.bridge.enabled) { toast(st.bridge.message, "info"); return; }
        const v = await promptModal("Send for signature",
          [{ name: "emails", label: "Signer email(s), comma-separated", required: true }], "Send");
        if (!v) return;
        const signers = v.emails.split(",").map((e) => ({ email: e.trim() })).filter((s) => s.email);
        if (!signers.length) return;
        const res = await api.sendForSignature(pid, m.key, rid, signers);
        toast(`sent via ${res.provider} · submission ${res.submission_id ?? "?"}`, "success");
        void this.openRecord(m, rid);
      } catch (e) { toast(`send for signature failed: ${(e as Error).message}`, "error"); }
    });
    const sigs = (r.data?.signatures as { party: string; name: string }[] | undefined) ?? [];
    const dsigs = (r.data?.digital_signatures as { signer: string; fingerprint: string }[] | undefined) ?? [];
    if (sigs.length || dsigs.length) {
      const s = document.createElement("span"); s.className = "meta"; s.style.marginLeft = "6px";
      const parts = [];
      if (sigs.length) parts.push("✓ signed: " + sigs.map((x) => `${x.party} (${x.name})`).join(", "));
      if (dsigs.length) parts.push("🔏 digitally signed (" + dsigs.length + ")");
      s.textContent = parts.join(" · ");
      tools.appendChild(s);
    }
  }

  private async composeExhibit(m: ModuleDef, r: ModuleRecord, rid: string) {
    const pid = this.host.projectId()!;
    let lib;
    try { lib = (await this.host.api.scopeLibrary()).clauses; } catch { toast("couldn't load scope library", "error"); return; }
    const { card } = modalShell("Compose Exhibit A — Scope of Work", 360);
    card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: "Select clauses to include:" }));
    const trade = (r.data?.trade as string | undefined)?.toLowerCase();
    const boxes: Record<string, HTMLInputElement> = {};
    const list = document.createElement("div"); list.style.cssText = "max-height:300px;overflow:auto;display:flex;flex-direction:column;gap:3px;margin:6px 0";
    for (const cl of lib) {
      const row = document.createElement("label"); row.style.cssText = "display:flex;gap:6px;align-items:center;font-size:12.5px";
      const cb = document.createElement("input"); cb.type = "checkbox";
      cb.checked = cl.category !== "Scope" || !trade || (cl.trade ?? "").toLowerCase() === trade;
      boxes[cl.id] = cb;
      row.append(cb, Object.assign(document.createElement("span"), { textContent: `${cl.title} · ${cl.category}` }));
      list.appendChild(row);
    }
    card.appendChild(list);
    const open = document.createElement("button"); open.className = "file-btn"; open.textContent = "View Exhibit A"; open.style.alignSelf = "flex-start";
    open.onclick = () => {
      const ids = Object.entries(boxes).filter(([, b]) => b.checked).map(([id]) => id);
      if (!ids.length) { toast("select at least one clause", "error"); return; }
      window.open(this.host.api.contractDocUrl(pid, m.key, rid, "exhibit", ids.join(",")), "_blank");
    };
    card.appendChild(open);
  }

  private async signContract(m: ModuleDef, r: ModuleRecord, rid: string) {
    const pid = this.host.projectId()!;
    const { card, close } = modalShell("Sign " + r.ref, 300);
    const party = document.createElement("select"); party.className = "portal-filter";
    for (const p of ["GC", "Owner", "OwnersRep", "Consultant", "Subcontractor"]) party.appendChild(Object.assign(document.createElement("option"), { value: p, textContent: p }));
    const name = document.createElement("input"); name.className = "portal-filter"; name.placeholder = "Full name";
    const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Sign";
    go.onclick = async () => {
      if (!name.value.trim()) { toast("enter a name", "error"); return; }
      try { await this.host.api.signContract(pid, m.key, rid, party.value, name.value.trim()); close(); toast("signed", "success"); void this.openRecord(m, rid); }
      catch (e) { toast(`sign failed: ${(e as Error).message}`, "error"); }
    };
    card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: "Record a typed signature:" }), party, name, go);
  }

  private async rfiTriage(rid: string) {
    const pid = this.host.projectId()!;
    let t;
    try { t = await this.host.api.triageRfi(pid, rid); }
    catch (e) { toast(`triage failed: ${(e as Error).message}`, "error"); return; }
    const { card } = modalShell("RFI triage (AI)", 360);
    if (!t.ai_enabled) card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: "AI not configured — showing a template suggestion." }));
    const kv = (k: string, v: string) => { const d = document.createElement("div"); d.className = "meta"; d.innerHTML = `<b>${k}:</b> `; d.append(v); card.appendChild(d); };
    kv("Discipline", t.discipline); kv("Category", t.category); kv("Urgency", t.urgency); kv("Ball-in-court", t.ball_in_court);
    const h = document.createElement("div"); h.className = "meta"; h.style.marginTop = "6px"; h.innerHTML = "<b>Draft response:</b>"; card.appendChild(h);
    const body = document.createElement("div"); body.style.cssText = "white-space:pre-wrap;font-size:12.5px"; body.textContent = t.draft_response; card.appendChild(body);
  }

  private async openPermitImport(m: ModuleDef) {
    const pid = this.host.projectId()!;
    const { card } = modalShell("Import permits from city open data", 420);
    const note = (t: string) => card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: t }));
    note("Pull a city's building-permit filings for the site and add them to this log (source-tagged, deduped on re-import).");
    const sel = document.createElement("select"); sel.className = "portal-filter"; sel.style.width = "100%";
    sel.innerHTML = `<option value="">Loading cities…</option>`;
    card.appendChild(sel);
    const field = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "width:100%;margin-top:6px"; card.appendChild(i); return i; };
    const addr = field("Address or keyword (e.g. street name) — optional");
    const geoRow = document.createElement("div"); geoRow.style.cssText = "display:flex;gap:6px;margin-top:6px"; card.appendChild(geoRow);
    const lat = Object.assign(document.createElement("input"), { className: "portal-filter", placeholder: "lat (optional)" });
    const lon = Object.assign(document.createElement("input"), { className: "portal-filter", placeholder: "lon (optional)" });
    const rad = Object.assign(document.createElement("input"), { className: "portal-filter", placeholder: "radius m", value: "1500" });
    for (const el of [lat, lon, rad]) { el.style.flex = "1"; geoRow.appendChild(el); }
    const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "8px"; card.appendChild(out);
    let cities: { id: string; label: string; geo: boolean }[] = [];
    try { cities = (await this.host.api.permitCities()).cities; }
    catch (e) { out.textContent = `Could not load cities: ${(e as Error).message}`; }
    sel.innerHTML = cities.map((c) => `<option value="${c.id}">${c.label}${c.geo ? "" : " (text search only)"}</option>`).join("");
    const opts = () => ({
      city: sel.value, address: addr.value.trim() || undefined,
      lat: lat.value ? Number(lat.value) : undefined, lon: lon.value ? Number(lon.value) : undefined,
      radius: rad.value ? Number(rad.value) : undefined,
    });
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:10px";
    const preview = document.createElement("button"); preview.className = "tool-btn"; preview.textContent = "Preview";
    preview.onclick = async () => {
      out.textContent = "searching…";
      try { const r = await this.host.api.opendataPermits(pid, { ...opts(), limit: 50 });
        out.textContent = r.count ? `${r.count} filing(s) found — first: ${r.permits[0].address ?? r.permits[0].permit_number}` : "No filings found — try an address/keyword or coordinates.";
      } catch (e) { out.textContent = `Search failed: ${(e as Error).message}`; }
    };
    const imp = document.createElement("button"); imp.className = "file-btn"; imp.textContent = "Import";
    imp.onclick = async () => {
      out.textContent = "importing…";
      try { const r = await this.host.api.importOpendataPermits(pid, { ...opts(), max: 50 });
        toast(`Imported ${r.imported} permit(s)${r.skipped ? `, skipped ${r.skipped} duplicate(s)` : ""}`, "success");
        this.openModule(m);
      } catch (e) { out.textContent = `Import failed: ${(e as Error).message}`; }
    };
    row.append(preview, imp); card.appendChild(row);
  }

  private async openRecord(m: ModuleDef, rid: string) {
    const pid = this.host.projectId()!;
    const r = await this.host.api.moduleRecord(pid, m.key, rid);
    this.root.innerHTML = "";
    this.root.appendChild(this.bar(`${r.ref}`, () => this.openModule(m)));

    const head = document.createElement("div");
    const ball = this.ballInCourt(m, r.workflow_state);
    head.innerHTML = `<div class="portal-rec-title">${esc(r.title ?? r.ref)}</div>` +
      `<div class="meta">status <span class="badge">${esc(r.workflow_state)}</span> · ${esc(r.party_owner ?? "")}` +
      (ball.length ? ` · ball-in-court ${ball.map((p) => `<span class="ball-badge">${esc(p)}</span>`).join(" ")}` : "") +
      `</div>`;
    // revision chain: this record's number + links to prior / superseding revision
    if (r.revision && (r.revision.number || r.revision.revises || r.revision.superseded_by)) {
      const rev = document.createElement("div"); rev.className = "meta";
      rev.append(`Revision ${r.revision.number}`);
      const link = (label: string, b: RecordBrief | null) => {
        if (!b) return;
        rev.append(` · ${label} `);
        const a = document.createElement("a"); a.href = "#"; a.className = "ref-link"; a.textContent = b.ref;
        a.onclick = (e) => { e.preventDefault(); this.openByBrief(b.module, b.id); };
        rev.append(a);
      };
      link("supersedes", r.revision.revises);
      link("superseded by", r.revision.superseded_by);
      head.appendChild(rev);
    }
    this.root.appendChild(head);

    const tools = document.createElement("div"); tools.style.cssText = "display:flex;gap:6px;margin:4px 0;flex-wrap:wrap";
    const editBtn = document.createElement("button");
    editBtn.className = "tool-btn"; editBtn.textContent = "✎ Edit";
    editBtn.onclick = () => this.renderForm(m, r);
    const delBtn = document.createElement("button");
    delBtn.className = "tool-btn"; delBtn.textContent = "🗑 Delete";
    delBtn.onclick = async () => {
      if (!confirm(`Delete ${r.ref}? This cannot be undone.`)) return;
      try { await this.host.api.deleteModuleRecord(pid, m.key, rid); this.host.setStatus(`deleted ${r.ref}`); this.host.onPinsChanged(); this.openModule(m); }
      catch (e) { this.host.setStatus(`error: ${(e as Error).message}`); }
    };
    const pdfBtn = document.createElement("button");
    pdfBtn.className = "tool-btn"; pdfBtn.textContent = "↓ PDF";
    pdfBtn.onclick = () => window.open(this.host.api.url(`/projects/${pid}/modules/${m.key}/${rid}/pdf`), "_blank");
    tools.append(editBtn, delBtn, pdfBtn);
    if (m.revisable) {
      const reviseBtn = document.createElement("button");
      reviseBtn.className = "tool-btn"; reviseBtn.dataset.cap = "review";
      const superseded = !!r.revision?.superseded_by;
      reviseBtn.textContent = "⎘ Revise"; reviseBtn.disabled = superseded;
      reviseBtn.title = superseded ? "Already revised" : "Create a tracked revision (re-opens the workflow)";
      reviseBtn.onclick = async () => {
        if (!confirm(`Create a revision of ${r.ref}? It re-opens the workflow as a new record (${r.ref}.${(r.revision?.number ?? 0) + 1}).`)) return;
        try { const nv = await this.host.api.reviseRecord(pid, m.key, rid); this.host.setStatus(`created ${nv.ref}`); this.openRecord(m, nv.id); }
        catch (e) { this.host.setStatus(`revise failed: ${(e as Error).message}`); }
      };
      tools.append(reviseBtn);
    }
    // C1 — convert-to buttons (offered when the source state/data warrants it)
    for (const c of PortalUI.CONVERSIONS[m.key] ?? []) {
      if (c.when && !c.when(r.data)) continue;
      const tgt = this.mods.find((x) => x.key === c.to); if (!tgt) continue;
      const cb = document.createElement("button");
      cb.className = "tool-btn"; cb.textContent = `⤳ ${c.label}`;
      cb.title = `Create a ${tgt.name} from this ${m.name}, linked back`;
      cb.onclick = () => this.convert(m, r, c);
      tools.append(cb);
    }
    this.contractActions(m, r, rid, tools);
    if (m.key === "rfi") {
      const tb = document.createElement("button");
      tb.className = "tool-btn"; tb.textContent = "✨ Triage (AI)"; tb.title = "AI: categorize + ball-in-court + draft response";
      tb.onclick = () => void this.rfiTriage(rid);
      tools.appendChild(tb);
    }
    this.root.appendChild(tools);

    // photo-heavy field modules put photos up top (the super's first action on the record)
    const photoFirst = ["daily_report", "punchlist", "inspection", "observation", "incident"].includes(m.key);
    if (photoFirst) this.renderAttachments(m, r, rid);

    // fields (reference fields render as clickable links to the target record)
    const fields = document.createElement("div"); fields.className = "portal-kv";
    for (const f of m.fields) {
      const v = r.data[f.name];
      if (v === undefined || v === "") continue;
      if (f.type === "reference") {
        const ref = r.data_refs?.[f.name];
        const k = document.createElement("div"); k.className = "k"; k.textContent = f.label;
        const vd = document.createElement("div"); vd.className = "v";
        if (ref) {
          const a = document.createElement("a"); a.href = "#"; a.className = "ref-link";
          a.textContent = `${ref.ref} — ${ref.title ?? ""}`;
          a.onclick = (e) => { e.preventDefault(); this.openByBrief(ref.module, ref.id); };
          vd.appendChild(a);
        } else vd.textContent = String(v);
        fields.append(k, vd);
      } else if (f.type === "signature") {
        fields.insertAdjacentHTML("beforeend",
          `<div class="k">${esc(f.label)}</div><div class="v"><img src="${esc(v)}" style="max-width:200px;border:1px solid var(--line);background:#fff"/></div>`);
      } else {
        // field values are user data — escape everything interpolated into HTML (stored-XSS guard)
        let disp = esc(v);
        if (f.type === "currency") disp = `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
        else if (f.type === "multiselect" && Array.isArray(v)) disp = (v as string[]).map((x) => `<span class="chip">${esc(x)}</span>`).join(" ");
        else if (f.type === "rollup") disp = `<span class="computed">${Number(v).toLocaleString()}</span>`;
        fields.insertAdjacentHTML("beforeend", `<div class="k">${esc(f.label)}</div><div class="v">${disp}</div>`);
      }
    }
    this.root.appendChild(fields);

    // assignee + reassign
    const asgRow = document.createElement("div"); asgRow.className = "meta"; asgRow.style.margin = "4px 0";
    asgRow.innerHTML = `Assignee: <b>${r.assignee ?? "—"}</b> `;
    const reassign = document.createElement("button"); reassign.className = "tool-btn"; reassign.textContent = "Reassign";
    reassign.style.marginLeft = "6px";
    reassign.onclick = async () => {
      const v = await promptModal("Reassign record",
        [{ name: "who", label: "Assign to (user id, blank to clear)", value: r.assignee ?? "" }]);
      if (!v) return;
      try { await this.host.api.assignRecord(pid, m.key, rid, v.who.trim() || null); this.openRecord(m, rid); }
      catch (e) { this.host.setStatus(`error: ${(e as Error).message}`); }
    };
    asgRow.appendChild(reassign);
    this.root.appendChild(asgRow);

    // attachments (files in object storage)
    if (!photoFirst) this.renderAttachments(m, r, rid);

    // related records (outgoing references + incoming records that point here)
    const relatedBox = document.createElement("div");
    this.root.appendChild(relatedBox);
    void this.renderRelated(relatedBox, m.key, rid);

    // model elements — show / tie the current 3D selection (hard-ties a schedule activity for an
    // exact 4D; also lets any record point at the elements it concerns)
    const guids = r.element_guids ?? [];
    const elHead = document.createElement("div"); elHead.className = "section-title";
    elHead.textContent = `Model elements${guids.length ? ` (${guids.length})` : ""}`;
    this.root.appendChild(elHead);
    const elRow = document.createElement("div"); elRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
    const tagBtn = document.createElement("button"); tagBtn.className = "tool-btn";
    tagBtn.textContent = "🔗 Tie current 3D selection";
    tagBtn.title = "Add the element selected in the 3D model to this record";
    tagBtn.onclick = async () => {
      const g = this.host.selectedGuid();
      if (!g) { this.host.setStatus("select an element in the 3D model first (Model workspace)"); return; }
      try { const res = await this.host.api.tagElements(pid, m.key, rid, [g], "add");
        this.host.setStatus(`tied ${res.count} element${res.count === 1 ? "" : "s"}`); this.openRecord(m, rid); }
      catch (e) { this.host.setStatus(`tie failed: ${(e as Error).message}`); }
    };
    elRow.appendChild(tagBtn);
    if (guids.length) {
      const showBtn = document.createElement("button"); showBtn.className = "tool-btn"; showBtn.textContent = "👁 Show in model";
      showBtn.onclick = () => this.host.onSelectGuids(guids); elRow.appendChild(showBtn);
      const clrBtn = document.createElement("button"); clrBtn.className = "tool-btn"; clrBtn.textContent = "✕ Clear ties";
      clrBtn.onclick = async () => {
        if (!confirm(`Untie all ${guids.length} elements from ${r.ref}?`)) return;
        try { await this.host.api.tagElements(pid, m.key, rid, [], "set"); this.openRecord(m, rid); }
        catch (e) { this.host.setStatus(`clear failed: ${(e as Error).message}`); }
      };
      elRow.appendChild(clrBtn);
    }
    this.root.appendChild(elRow);
    if (m.key === "schedule_activity" && guids.length) {
      const hint = document.createElement("div"); hint.className = "meta";
      hint.textContent = "These elements complete on this activity's finish date in the 4D scrub.";
      this.root.appendChild(hint);
    }

    // workflow actions (server-gated by party)
    const acts = r.available_actions ?? [];
    if (acts.length) {
      const ad = document.createElement("div"); ad.className = "section-title"; ad.textContent = "Workflow";
      this.root.appendChild(ad);
      this.root.appendChild(this.workflowMap(m, r.workflow_state));   // visual state diagram
      const labelOf = (f: string) => m.fields.find((x) => x.name === f)?.label ?? f;
      for (const a of acts) {
        // transition field-gate: which required fields are still empty on this record
        const missing = (a.requires ?? []).filter((f) => {
          const v = (r.data ?? {})[f]; return v === undefined || v === null || v === "";
        });
        const b = document.createElement("button"); b.className = "tool-btn";
        b.textContent = `${a.action} → ${a.to}` + (missing.length ? ` (needs ${missing.map(labelOf).join(", ")})` : "");
        b.style.cssText = "display:block;margin:3px 0;width:100%;text-align:left";
        b.disabled = missing.length > 0;
        if (missing.length) b.title = `Fill ${missing.map(labelOf).join(", ")} before ${a.action}`;
        b.onclick = async () => {
          try { await this.host.api.transitionRecord(pid, m.key, rid, a.action); this.openRecord(m, rid); }
          catch (e) { this.host.setStatus(`blocked: ${(e as Error).message}`); }
        };
        this.root.appendChild(b);
      }
    }

    // linked records (change-order chain)
    if (r.links?.length) {
      const ld = document.createElement("div"); ld.className = "section-title"; ld.textContent = "Linked";
      this.root.appendChild(ld);
      for (const l of r.links) {
        const e = document.createElement("div"); e.className = "meta"; e.textContent = `${l.module}: ${l.ref}`;
        this.root.appendChild(e);
      }
    }

    // comments
    const cd = document.createElement("div"); cd.className = "section-title"; cd.textContent = "Comments";
    this.root.appendChild(cd);
    for (const cm of r.comments ?? []) {
      const e = document.createElement("div"); e.className = "portal-act";
      e.textContent = `${cm.author ?? ""}: ${cm.text}`;
      this.root.appendChild(e);
    }
    const ta = document.createElement("textarea");
    ta.className = "portal-field"; ta.placeholder = "Add a comment…"; ta.style.width = "100%";
    const addBtn = document.createElement("button");
    addBtn.className = "tool-btn"; addBtn.textContent = "Comment"; addBtn.style.margin = "4px 0";
    addBtn.onclick = async () => {
      if (!ta.value.trim()) return;
      await this.host.api.addComment(pid, m.key, rid, ta.value.trim());
      this.openRecord(m, rid);
    };
    this.root.append(ta, addBtn);

    // activity timeline
    const td = document.createElement("div"); td.className = "section-title"; td.textContent = "Activity";
    this.root.appendChild(td);
    for (const a of r.activity ?? []) {
      const e = document.createElement("div"); e.className = "portal-act";
      e.textContent = `${(a.ts || "").slice(0, 16).replace("T", " ")} · ${a.actor ?? ""} · ${a.action}`;
      this.root.appendChild(e);
    }
  }

  /** Compact horizontal bar chart (inline SVG, no deps). */
  private barChart(title: string, data: [string, number][], color: (k: string) => string): HTMLElement {
    const box = document.createElement("div"); box.className = "chart-box";
    const t = document.createElement("div"); t.className = "section-title"; t.textContent = title;
    box.appendChild(t);
    const max = Math.max(1, ...data.map(([, v]) => v));
    const rowH = 20, w = 240, labelW = 90, barW = w - labelW - 34;
    const svg = `<svg viewBox="0 0 ${w} ${data.length * rowH}" width="100%" role="img" aria-label="${title}">` +
      data.map(([k, v], i) => {
        const y = i * rowH, bw = Math.max(2, (v / max) * barW);
        return `<text x="0" y="${y + 14}" fill="var(--muted)" font-size="11">${k.slice(0, 14)}</text>` +
          `<rect x="${labelW}" y="${y + 4}" width="${bw}" height="12" rx="2" fill="${color(k)}"/>` +
          `<text x="${labelW + bw + 4}" y="${y + 14}" fill="var(--text)" font-size="11">${v}</text>`;
      }).join("") + `</svg>`;
    const holder = document.createElement("div"); holder.innerHTML = svg;
    box.appendChild(holder.firstChild!);
    return box;
  }

  /** Open a record given a module key + id (used by reference + related links). */
  private openByBrief(moduleKey: string, id: string) {
    const m = this.mods.find((x) => x.key === moduleKey);
    if (m) this.openRecord(m, id);
  }

  /** Public: the loaded module definitions (for the command palette). */
  moduleList(): { key: string; name: string; section?: string }[] {
    return this.mods.map((m) => ({ key: m.key, name: m.name, section: m.section }));
  }
  /** Public: open a module's list by key (command palette / deep links). */
  openModuleByKey(key: string) {
    const m = this.mods.find((x) => x.key === key);
    if (m) { this.activeKey = key; void this.openModule(m); this.buildNav(); }
  }
  /** Public: open a specific record by module key + id (command palette). */
  openRecordByKey(moduleKey: string, id: string) { this.openByBrief(moduleKey, id); }

  /** Render the outgoing/incoming relation graph for a record into `box`. */
  private async renderRelated(box: HTMLElement, key: string, rid: string) {
    const pid = this.host.projectId()!;
    let rel;
    try { rel = await this.host.api.relatedRecords(pid, key, rid); }
    catch { return; }
    if (!rel.outgoing.length && !rel.incoming.length) return;
    box.innerHTML = `<div class="section-title">Related</div>`;
    const link = (label: string, b: { module: string; module_name: string; id: string; ref: string; title: string | null; state: string }) => {
      const row = document.createElement("button"); row.className = "portal-mod";
      row.innerHTML = `<span class="ic">↳</span> <b>${label}</b> ${b.ref} ${b.title ?? ""} <span class="badge">${b.state}</span>`;
      row.onclick = () => this.openByBrief(b.module, b.id);
      box.appendChild(row);
    };
    for (const o of rel.outgoing) link(o.label, o);
    for (const i of rel.incoming) link(i.module_name, i);
  }

  /** Attachments section: image thumbnails + file links, with multi-file (bulk) + drag-drop upload —
   *  the field reality is a batch of site photos, not one file at a time. */
  private renderAttachments(m: ModuleDef, r: ModuleRecord, rid: string) {
    const pid = this.host.projectId()!;
    const atts = r.attachments ?? [];
    const t = document.createElement("div"); t.className = "section-title";
    t.textContent = `Attachments${atts.length ? ` (${atts.length})` : ""}`;
    this.root.appendChild(t);

    if (atts.length) {
      const gallery = document.createElement("div"); gallery.className = "att-gallery";
      for (const a of atts) {
        const isImg = (a.content_type || "").startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp)$/i.test(a.filename);
        const url = this.host.api.attachmentUrl(a.id);
        const kb = a.size > 1024 * 1024 ? `${(a.size / 1048576).toFixed(1)} MB` : a.size > 1024 ? `${Math.round(a.size / 1024)} KB` : `${a.size} B`;
        const cell = document.createElement("a"); cell.className = "att-cell"; cell.href = url; cell.target = "_blank"; cell.title = `${a.filename} · ${kb}`;
        if (isImg) {
          const img = document.createElement("img"); img.src = url; img.loading = "lazy"; img.alt = a.filename; cell.appendChild(img);
        } else {
          cell.classList.add("att-file"); cell.innerHTML = `<span class="att-ic">📎</span><span class="att-name">${a.filename}</span>`;
        }
        gallery.appendChild(cell);
      }
      this.root.appendChild(gallery);
    }

    const file = document.createElement("input"); file.type = "file"; file.multiple = true;
    file.accept = "image/*,application/pdf,.dwg,.doc,.docx,.xls,.xlsx";
    file.style.display = "none";
    // camera capture — on a phone this opens the camera directly (field photo in one tap)
    const cam = document.createElement("input"); cam.type = "file"; cam.accept = "image/*";
    cam.setAttribute("capture", "environment"); cam.style.display = "none";
    const drop = document.createElement("div"); drop.className = "att-drop";
    drop.innerHTML = `<b>＋ Add photos / files</b><span class="meta">drag &amp; drop a batch, or click to pick multiple</span>`;
    drop.onclick = () => file.click();
    const doUpload = async (files: FileList | File[]) => {
      const list = Array.from(files); if (!list.length) return;
      if (!navigator.onLine) { await this.queueUpload(pid, m.key, rid, list); this.openRecord(m, rid); return; }
      drop.classList.add("busy"); drop.querySelector("b")!.textContent = `Uploading ${list.length} file${list.length > 1 ? "s" : ""}…`;
      try {
        if (list.length === 1) await this.host.api.uploadAttachment(pid, m.key, rid, list[0]);
        else await this.host.api.uploadAttachmentsBulk(pid, m.key, rid, list);
        this.host.setStatus(`attached ${list.length} file${list.length > 1 ? "s" : ""}`); this.openRecord(m, rid);
      } catch (e) {
        if (!navigator.onLine) { await this.queueUpload(pid, m.key, rid, list); this.openRecord(m, rid); return; }
        this.host.setStatus(`upload failed: ${(e as Error).message}`); drop.classList.remove("busy");
      }
    };
    file.onchange = () => { if (file.files) void doUpload(file.files); };
    cam.onchange = () => { if (cam.files) void doUpload(cam.files); };
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer?.files) void doUpload(e.dataTransfer.files); };
    const camBtn = document.createElement("button"); camBtn.className = "tool-btn"; camBtn.textContent = "📷 Take photo";
    camBtn.style.marginTop = "4px"; camBtn.onclick = () => cam.click();
    this.root.append(file, cam, drop, camBtn);
    const qWarn = document.createElement("div"); qWarn.className = "meta"; qWarn.style.cssText = "color:var(--status-warn);margin-top:3px";
    this.root.appendChild(qWarn);
    void queuedCountForRecord(rid).then((queued) => {
      qWarn.textContent = queued
        ? `⏳ ${queued} file${queued > 1 ? "s" : ""} queued (offline) — will upload when back online` : "";
    });
  }

  /** Persist an upload that couldn't go out (offline) and flush when the connection returns. */
  private async queueUpload(pid: string, key: string, rid: string, files: File[]) {
    await enqueueUpload({ pid, key, rid, files });
    this.host.setStatus(`offline — ${files.length} file${files.length > 1 ? "s" : ""} queued, will upload on reconnect`);
    this.hookOnline();
  }

  /** Register the reconnect flush once (also called at startup to drain a prior session's queue). */
  private hookOnline() {
    if (this.onlineHooked) return;
    this.onlineHooked = true;
    window.addEventListener("online", () => void this.flushUploads());
  }

  private async flushUploads() {
    if (!navigator.onLine) return;
    let done = 0;
    for (const q of await allQueued()) {
      try {
        if (q.files.length === 1) await this.host.api.uploadAttachment(q.pid, q.key, q.rid, q.files[0]);
        else await this.host.api.uploadAttachmentsBulk(q.pid, q.key, q.rid, q.files);
        await dequeue(q.id); done += q.files.length;
      } catch { /* leave it queued for the next reconnect */ }
    }
    if (done) { this.host.setStatus(`back online — uploaded ${done} queued file${done > 1 ? "s" : ""}`); this.host.onPinsChanged(); }
  }

  // --- kanban / "scrum" board: columns by workflow state, drag to transition --
  private async renderBoard(m: ModuleDef) {
    const pid = this.host.projectId()!;
    this.skeleton(`Loading ${m.name} board…`);
    const data = await this.host.api.moduleBoard(pid, m.key);
    this.root.innerHTML = "";
    this.root.appendChild(this.bar(`${m.name} — board`, () => this.openModule(m)));
    const board = document.createElement("div"); board.className = "kanban";
    for (const state of data.states) {
      const col = document.createElement("div"); col.className = "kan-col"; col.dataset.state = state;
      col.innerHTML = `<div class="kan-head">${state} <span class="count">${(data.columns[state] ?? []).length}</span></div>`;
      // drop target: on drop, find a transition from the card's state -> this column's state
      col.ondragover = (e) => { e.preventDefault(); col.classList.add("over"); };
      col.ondragleave = () => col.classList.remove("over");
      col.ondrop = async (e) => {
        e.preventDefault(); col.classList.remove("over");
        const rid = e.dataTransfer?.getData("rid"); const from = e.dataTransfer?.getData("from");
        if (!rid || from === state) return;
        const tr = data.transitions.find((t) => t.from === from && t.to === state);
        if (!tr) { this.host.setStatus(`no direct transition ${from} → ${state}`); return; }
        try { await this.host.api.transitionRecord(pid, m.key, rid, tr.action); this.renderBoard(m); }
        catch (err) { this.host.setStatus(`blocked: ${(err as Error).message}`); }
      };
      for (const c of data.columns[state] ?? []) {
        const card = document.createElement("div"); card.className = "kan-card"; card.draggable = true;
        card.innerHTML = `<div class="kc-ref">${c.ref}</div><div class="kc-title">${c.title ?? ""}</div>` +
          (c.assignee ? `<div class="kc-asg">@${c.assignee}</div>` : "");
        card.ondragstart = (e) => { e.dataTransfer?.setData("rid", c.id); e.dataTransfer?.setData("from", state); };
        card.onclick = () => this.openRecord(m, c.id);
        col.appendChild(card);
      }
      board.appendChild(col);
    }
    this.root.appendChild(board);
  }

  /** Draw-to-sign canvas pad; returns a getter for the signature data-URI ("" if blank). */
  private signaturePad(wrap: HTMLElement): () => string {
    const cv = document.createElement("canvas");
    cv.width = 240; cv.height = 90;
    cv.style.cssText = "display:block;margin-top:4px;border:1px solid var(--line);background:#fff;border-radius:4px;touch-action:none";
    const ctx = cv.getContext("2d")!;
    ctx.strokeStyle = "#111"; ctx.lineWidth = 2; ctx.lineCap = "round";
    let drawing = false, dirty = false;
    cv.onpointerdown = (e) => { drawing = true; ctx.beginPath(); ctx.moveTo(e.offsetX, e.offsetY); };
    cv.onpointermove = (e) => { if (drawing) { ctx.lineTo(e.offsetX, e.offsetY); ctx.stroke(); dirty = true; } };
    cv.onpointerup = () => (drawing = false);
    cv.onpointerleave = () => (drawing = false);
    const clear = document.createElement("button");
    clear.type = "button"; clear.className = "tool-btn"; clear.textContent = "Clear"; clear.style.marginTop = "4px";
    clear.onclick = () => { ctx.clearRect(0, 0, cv.width, cv.height); dirty = false; };
    wrap.append(cv, clear);
    return () => (dirty ? cv.toDataURL("image/png") : "");
  }

  private bar(title: string, back: () => void): HTMLElement {
    const bar = document.createElement("div"); bar.className = "portal-bar";
    const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = "←";
    b.onclick = back;
    const t = document.createElement("strong"); t.textContent = title;
    bar.append(b, t);
    return bar;
  }
}
