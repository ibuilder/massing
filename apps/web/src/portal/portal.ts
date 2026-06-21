import type { ApiClient, ModuleDef, ModuleRecord, RecordBrief } from "../api/client";
import { toast } from "../ui/feedback";

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

export class PortalUI {
  private mods: ModuleDef[] = [];

  constructor(private root: HTMLElement, private host: PortalHost) {}

  async init() {
    if (!this.host.projectId()) { this.root.innerHTML = `<div class="empty-state">No project open<span class="es-hint">Pick a project in the toolbar to use the GC portal.</span></div>`; return; }
    this.mods = await this.host.api.modules();
    // re-order the module catalog's default-open sections when the persona changes
    window.addEventListener("aec:persona", () => this.refreshCatalog());
    await this.renderHome();
  }

  // --- role-tailored dashboard + module catalog ------------------------------
  private async renderHome() {
    this.root.innerHTML = "";
    const pid = this.host.projectId()!;

    // global cross-module search
    const search = document.createElement("input");
    search.type = "search"; search.placeholder = "🔍 Search all records…"; search.className = "portal-filter";
    search.style.cssText = "width:100%;margin-bottom:8px";
    const results = document.createElement("div");
    let timer: number | undefined;
    search.oninput = () => {
      clearTimeout(timer);
      timer = window.setTimeout(async () => {
        results.innerHTML = "";
        if (search.value.trim().length < 2) return;
        const hits = await this.host.api.searchAll(pid, search.value.trim());
        if (!hits.length) { results.innerHTML = `<div class="empty-state">No matches</div>`; return; }
        for (const h of hits) {
          const row = document.createElement("button"); row.className = "portal-mod";
          row.innerHTML = `<span class="ic">${h.icon}</span> ${h.ref} ${h.title ?? ""} <span class="badge">${h.module_name}</span>`;
          row.onclick = () => { const m = this.mods.find((x) => x.key === h.module); if (m) this.openRecord(m, h.id); };
          results.appendChild(row);
        }
      }, 250);
    };
    this.root.append(search, results);

    // notifications feed (recent activity relevant to me)
    try {
      const notes = await this.host.api.notifications(pid);
      if (notes.length) {
        const nt = document.createElement("div"); nt.className = "section-title";
        nt.textContent = `🔔 Notifications (${notes.length})`;
        this.root.appendChild(nt);
        for (const n of notes.slice(0, 8)) {
          const row = document.createElement("button"); row.className = "portal-mod notif";
          const ago = n.ts ? new Date(n.ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
          row.innerHTML = `<span class="ic">${n.icon}</span> <b>${n.ref}</b> ${n.action} ` +
            `<span class="badge ${n.reason === "assigned" ? "rfi" : "open"}">${n.reason}</span> ` +
            `<span class="notif-meta">${n.actor ?? ""} · ${ago}</span>`;
          row.onclick = () => { const m = this.mods.find((x) => x.key === n.module); if (m) this.openRecord(m, n.record_id); };
          this.root.appendChild(row);
        }
      }
    } catch { /* notifications optional */ }

    try {
      const d = await this.host.api.dashboard(pid);
      const head = document.createElement("div");
      head.className = "section-title"; head.style.cssText = "display:flex;justify-content:space-between;align-items:center";
      head.append(`Dashboard — ${d.party}`);
      const rpt = document.createElement("button");
      rpt.className = "tool-btn"; rpt.textContent = "↓ Status report (PDF)";
      rpt.title = "Project status report — KPIs, cost, open items, ball-in-court";
      rpt.onclick = () => window.open(this.host.api.url(`/projects/${pid}/report.pdf`), "_blank");
      head.append(rpt);
      this.root.appendChild(head);

      // KPI cards
      const kpis = document.createElement("div"); kpis.className = "kpi-grid";
      const cards: [string, number][] = [
        ["Ball in court", d.kpis.my_action_items ?? 0], ["Overdue", d.kpis.overdue ?? 0],
        ["Open RFIs", d.kpis.open_rfis ?? 0], ["Pending COs", d.kpis.pending_change_orders ?? 0],
        ["Quality", d.kpis.open_quality ?? 0], ["Safety", d.kpis.open_safety ?? 0],
      ];
      for (const [label, val] of cards) {
        const c = document.createElement("div"); c.className = "kpi";
        c.innerHTML = `<div class="kpi-v">${val}</div><div class="kpi-l">${label}</div>`;
        kpis.appendChild(c);
      }
      this.root.appendChild(kpis);

      // AI/rules risk summary (owner/PM reporting)
      const risk = document.createElement("div"); risk.id = "dash-risk"; this.root.appendChild(risk);
      void this.host.api.riskSummary(pid).then((rs) => {
        const colors: Record<string, string> = { high: "#e2554a", medium: "#ffd479", low: "#6cb6ff" };
        risk.innerHTML = `<div class="section-title" style="margin-top:10px">Risk summary`
          + `<span class="meta" style="font-weight:400"> · ${rs.source === "claude" ? "AI" : "rules"}</span></div>`
          + `<div class="meta" style="margin:2px 0 6px">${rs.headline}</div>`
          + rs.risks.map((r) => `<div style="display:flex;gap:8px;align-items:baseline;margin:3px 0;font-size:12px">`
            + `<span style="color:${colors[r.level] || "#9aa0a6"};font-weight:700;text-transform:uppercase;font-size:10px;min-width:54px">${r.level}</span>`
            + `<span>${r.text}</span></div>`).join("");
      }).catch(() => { risk.innerHTML = ""; });

      // Ask AI — natural-language Q&A grounded on the live project snapshot
      const ask = document.createElement("div"); ask.style.cssText = "margin:10px 0";
      ask.innerHTML = `<div class="section-title">Ask AI</div>`;
      const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;margin:4px 0";
      const input = document.createElement("input"); input.className = "portal-filter"; input.style.flex = "1";
      input.placeholder = "Ask about this project — e.g. “what’s overdue?”, “open RFIs?”, “are we over budget?”";
      const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Ask";
      const out = document.createElement("div"); out.className = "meta"; out.style.cssText = "white-space:pre-wrap;margin-top:4px";
      const run = async () => {
        const q = input.value.trim(); if (!q) return;
        out.textContent = "thinking…";
        try {
          const r = await this.host.api.aiAsk(pid, q);
          let text = r.answer;
          // graceful no-key/error path: surface the key snapshot numbers so it isn't a dead end
          const snap = r.snapshot as { record_counts?: Record<string, number>; kpis?: Record<string, number> } | undefined;
          if (r.source !== "claude" && snap) {
            const k = snap.kpis || {}, c = snap.record_counts || {};
            const line = (label: string, v: unknown) => (v ? `\n• ${label}: ${v}` : "");
            text += line("Open RFIs", k.open_rfis) + line("Overdue", k.overdue)
              + line("Pending change orders", k.pending_change_orders)
              + line("Open punchlist", k.open_punchlist)
              + line("RFIs (total)", c.rfi) + line("Change events", c.change_event);
            if (!r.ai_enabled) text += "\n\n(Set an Anthropic API key in Settings for full plain-English answers.)";
          }
          out.textContent = text;
        } catch { out.textContent = "Couldn’t reach the assistant."; }
      };
      go.onclick = () => void run();
      input.onkeydown = (e) => { if (e.key === "Enter") void run(); };
      row.append(input, go); ask.append(row, out); this.root.appendChild(ask);

      if (d.cost) {
        const cd = document.createElement("div"); cd.className = "meta";
        cd.style.margin = "6px 0";
        cd.textContent = `Budget $${d.cost.budget.toLocaleString()} · Over/Under $${d.cost.projected_over_under.toLocaleString()}`;
        this.root.appendChild(cd);
      }

      // safety analytics line (TRIR/DART + recordables) — shown once any incidents are logged
      const safety = document.createElement("div"); safety.className = "meta"; safety.style.margin = "2px 0 6px";
      this.root.appendChild(safety);
      void this.host.api.safetyMetrics(pid).then((s) => {
        if (!s.incident_count) return;
        const trir = s.trir != null ? ` · TRIR ${s.trir}` : "";
        const dart = s.dart != null ? ` · DART ${s.dart}` : "";
        safety.textContent = `Safety: ${s.recordable_count} recordable / ${s.incident_count} incidents · ${s.lost_days} lost days${trir}${dart}`;
      }).catch(() => {});

      // charts from by_module: workflow-state mix + busiest sections
      const states = new Map<string, number>();
      const sections = new Map<string, number>();
      for (const bm of d.by_module) {
        for (const [st, n] of Object.entries(bm.by_state)) states.set(st, (states.get(st) ?? 0) + n);
        if (bm.count) sections.set(bm.section || "Other", (sections.get(bm.section || "Other") ?? 0) + bm.count);
      }
      const STATE_COLOR: Record<string, string> = { draft: "#9aa0a6", open: "#ffd479", answered: "#6cb6ff", closed: "#33d17a", void: "#e2554a", approved: "#33d17a", rejected: "#e2554a" };
      if (states.size) this.root.appendChild(this.barChart("Records by status",
        [...states.entries()].sort((a, b) => b[1] - a[1]), (k) => STATE_COLOR[k] ?? "#b083d6"));
      if (sections.size) this.root.appendChild(this.barChart("Busiest sections",
        [...sections.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6), () => "#4a8cff"));

      // ball-in-your-court action items
      if (d.action_items.length) {
        const t = document.createElement("div"); t.className = "section-title"; t.textContent = "Ball in your court";
        this.root.appendChild(t);
        for (const a of d.action_items.slice(0, 20)) {
          const row = document.createElement("button");
          row.className = "portal-mod";
          row.innerHTML = `<span class="ic">→</span> ${a.ref} ${a.title ?? ""} <span class="badge">${a.state}</span>`;
          row.onclick = () => { const m = this.mods.find((x) => x.key === a.module); if (m) this.openRecord(m, a.id); };
          this.root.appendChild(row);
        }
      }
      const allTitle = document.createElement("div");
      allTitle.className = "section-title"; allTitle.textContent = "All modules";
      this.root.appendChild(allTitle);
    } catch { /* dashboard optional */ }

    this.catalogEl = this.renderModuleCatalog();
    this.root.appendChild(this.catalogEl);
  }

  // --- module catalog: favorites + collapsible, persona-aware sections + filter --
  private catalogEl?: HTMLElement;

  /** Which sections open by default per persona (the rest collapse). Undefined persona = all open. */
  private static SECTIONS_BY_PERSONA: Record<string, string[]> = {
    gc: ["Field", "Cost", "Change Management", "Contracts"],
    developer: ["Cost", "Contracts", "Preconstruction", "Closeout"],
    architect: ["Engineering", "Preconstruction", "BIM", "Closeout"],
    engineer: ["Engineering", "Quality", "BIM"],
    subcontractor: ["Field", "Safety", "Quality"],
  };

  private favs(): Set<string> {
    try { return new Set(JSON.parse(localStorage.getItem("portal-favs") || "[]") as string[]); }
    catch { return new Set(); }
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

  private async openModule(m: ModuleDef, filter: { q?: string; state?: string } = {}) {
    const pid = this.host.projectId()!;
    this.skeleton(`Loading ${m.name}…`);
    const records = await this.host.api.moduleRecordsFiltered(pid, m.key, filter);
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
    viewSel.onchange = () => { const v = views.find((x) => x.id === viewSel.value); if (v) { this.sort[m.key] = v.config.sort; this.openModule(m, { q: v.config.q, state: v.config.state }); } };
    const saveView = document.createElement("button"); saveView.className = "tool-btn"; saveView.textContent = "＋view";
    saveView.title = "Save current filter/sort as a view (synced to your account)";
    saveView.onclick = async () => {
      const name = prompt("Save view as:"); if (!name) return;
      await this.host.api.saveView(pid, m.key, name, { q: filter.q, state: filter.state, sort: this.sort[m.key] });
      this.openModule(m, filter);
    };
    // reusable templates: apply a saved set of records, or save the current ones as a template
    const tplBtn = document.createElement("button"); tplBtn.className = "tool-btn"; tplBtn.dataset.cap = "review"; tplBtn.textContent = "⌹ Templates";
    tplBtn.title = "Apply or save a reusable template for this module";
    tplBtn.onclick = async () => {
      const tpls = await this.host.api.templates(m.key).catch(() => []);
      const pick = tpls.length
        ? prompt(`Apply a ${m.name} template — enter a number, or blank to save current as new:\n`
            + tpls.map((t, i) => `${i + 1}. ${t.name} (${t.item_count})`).join("\n"))
        : (alert(`No ${m.name} templates yet — saving the current records as one.`), "");
      if (pick && pick.trim()) {
        const t = tpls[parseInt(pick) - 1];
        if (!t) return;
        const r = await this.host.api.applyTemplate(pid, m.key, t.id);
        this.host.setStatus(`applied "${r.applied}" — ${r.created} record(s)`);
        this.openModule(m, filter);
      } else {
        const name = prompt("Save current records as template named:"); if (!name) return;
        try { const s = await this.host.api.saveTemplate(pid, m.key, name); this.host.setStatus(`saved template (${s.item_count} items)`); }
        catch (e) { this.host.setStatus(`couldn't save: ${(e as Error).message}`); }
      }
    };
    actions.append(newBtn, boardBtn, csvBtn, tplBtn, fbox, stateSel, viewSel, saveView);
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
    // each action returns the number of records it acted on, or null if the user cancelled —
    // so we only toast + reload on a real change (no spurious reload on a cancelled prompt).
    const mkBulk = (label: string, verb: string, fn: () => Promise<number | null>) => {
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label;
      b.onclick = () => void fn().then((n) => {
        if (n == null) return;
        toast(`${verb} ${n} ${m.name.toLowerCase()} record${n === 1 ? "" : "s"}`, "info");
        this.openModule(m, filter);
      }).catch((e) => this.host.setStatus(`bulk action failed: ${(e as Error).message}`));
      return b;
    };
    bulkBar.append(bulkCount,
      mkBulk("Assign…", "Assigned", async () => { const who = prompt("Assign selected to:"); if (who === null) return null; const n = selected.size; await this.host.api.bulkAction(pid, m.key, [...selected], "assign", who.trim()); return n; }),
      mkBulk("Transition…", "Transitioned", async () => { const act = prompt("Workflow action to apply:"); if (!act) return null; const n = selected.size; await this.host.api.bulkAction(pid, m.key, [...selected], "transition", act.trim()); return n; }),
      mkBulk("Delete", "Deleted", async () => { if (!confirm(`Delete ${selected.size} record(s)?`)) return null; const n = selected.size; await this.host.api.bulkAction(pid, m.key, [...selected], "delete"); return n; }));
    this.root.appendChild(bulkBar);

    const table = document.createElement("table"); table.className = "portal-table";
    const headRow = document.createElement("tr");
    headRow.appendChild(document.createElement("th"));  // checkbox col
    const th = (label: string, col: string) => {
      const h = document.createElement("th"); h.textContent = label + (sort?.col === col ? (sort.dir === 1 ? " ▲" : " ▼") : "");
      h.style.cursor = "pointer";
      h.onclick = () => { const cur = this.sort[m.key]; this.sort[m.key] = { col, dir: cur?.col === col && cur.dir === 1 ? -1 : 1 }; this.openModule(m, filter); };
      headRow.appendChild(h);
    };
    th("Ref", "ref"); th("Title", "title");
    for (const c of cols) th(c.label, c.name);
    th("Assignee", "assignee"); th("Status", "status");
    const thead = document.createElement("thead"); thead.appendChild(headRow); table.appendChild(thead);

    const tb = document.createElement("tbody");
    for (const r of records) {
      const tr = document.createElement("tr");
      const cbTd = document.createElement("td");
      const cb = document.createElement("input"); cb.type = "checkbox";
      cb.onclick = (e) => { e.stopPropagation(); if (cb.checked) selected.add(r.id); else selected.delete(r.id); syncBulk(); };
      cbTd.appendChild(cb); cbTd.onclick = (e) => e.stopPropagation(); tr.appendChild(cbTd);
      const cell = (html: string) => { const td = document.createElement("td"); td.innerHTML = html; tr.appendChild(td); };
      cell(r.ref); cell(r.title ?? "");
      for (const c of cols) cell(this.fmtCell(c, r.data[c.name]));
      tr.appendChild(this.assigneeCell(pid, m, r));   // inline-editable
      tr.appendChild(this.statusCell(pid, m, r));     // inline workflow transition
      tr.onclick = () => this.openRecord(m, r.id);
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    this.root.appendChild(table);
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

    this.root.innerHTML = "";
    this.root.appendChild(this.bar(`${editing ? "Edit" : "New"} ${m.name}`,
      () => (editing ? this.openRecord(m, existing!.id) : this.openModule(m))));
    const inputs: Record<string, HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement> = {};
    const sigs: Record<string, () => string> = {};   // signature field getters (data-URI)
    const cur = (n: string) => (existing?.data?.[n] as string | number | string[] | undefined);
    for (const f of m.fields) {
      if (f.type === "rollup") continue;   // computed, not user-entered
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
        for (const o of f.options ?? []) { const opt = document.createElement("option"); opt.value = opt.textContent = o; el.appendChild(opt); }
        if (cur(f.name) != null) el.value = String(cur(f.name));
      } else if (f.type === "multiselect") {
        el = document.createElement("select"); el.multiple = true; el.size = Math.min((f.options ?? []).length, 5);
        const chosen = new Set(Array.isArray(cur(f.name)) ? (cur(f.name) as string[]) : []);
        for (const o of f.options ?? []) { const opt = document.createElement("option"); opt.value = opt.textContent = o; opt.selected = chosen.has(o); el.appendChild(opt); }
      } else if (f.type === "reference") {
        el = document.createElement("select");
        const none = document.createElement("option"); none.value = ""; none.textContent = `— none —`; el.appendChild(none);
        for (const o of refOpts.get(f.name) ?? []) { const opt = document.createElement("option"); opt.value = o.id; opt.textContent = o.label; el.appendChild(opt); }
        if (cur(f.name) != null) el.value = String(cur(f.name));
      } else { el = document.createElement("input"); (el as HTMLInputElement).type = (f.type === "number" || f.type === "currency") ? "number" : f.type === "date" ? "date" : "text"; if (f.type === "currency") (el as HTMLInputElement).step = "0.01"; (el as HTMLInputElement).value = String(cur(f.name) ?? ""); }
      inputs[f.name] = el; wrap.appendChild(el); this.root.appendChild(wrap);
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

    const save = document.createElement("button");
    save.className = "file-btn"; save.textContent = editing ? "Save" : "Create"; save.style.marginTop = "8px";
    save.onclick = async () => {
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
      } catch (e) { this.host.setStatus(`error: ${(e as Error).message}`); }
    };
    this.root.appendChild(save);
  }

  // --- record detail + workflow actions + activity ---------------------------
  private async openRecord(m: ModuleDef, rid: string) {
    const pid = this.host.projectId()!;
    const r = await this.host.api.moduleRecord(pid, m.key, rid);
    this.root.innerHTML = "";
    this.root.appendChild(this.bar(`${r.ref}`, () => this.openModule(m)));

    const head = document.createElement("div");
    head.innerHTML = `<div class="portal-rec-title">${r.title ?? r.ref}</div>` +
      `<div class="meta">status <span class="badge">${r.workflow_state}</span> · ${r.party_owner ?? ""}</div>`;
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
    this.root.appendChild(tools);

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
          `<div class="k">${f.label}</div><div class="v"><img src="${v}" style="max-width:200px;border:1px solid var(--line);background:#fff"/></div>`);
      } else {
        let disp = String(v);
        if (f.type === "currency") disp = `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
        else if (f.type === "multiselect" && Array.isArray(v)) disp = (v as string[]).map((x) => `<span class="chip">${x}</span>`).join(" ");
        else if (f.type === "rollup") disp = `<span class="computed">${Number(v).toLocaleString()}</span>`;
        fields.insertAdjacentHTML("beforeend", `<div class="k">${f.label}</div><div class="v">${disp}</div>`);
      }
    }
    this.root.appendChild(fields);

    // assignee + reassign
    const asgRow = document.createElement("div"); asgRow.className = "meta"; asgRow.style.margin = "4px 0";
    asgRow.innerHTML = `Assignee: <b>${r.assignee ?? "—"}</b> `;
    const reassign = document.createElement("button"); reassign.className = "tool-btn"; reassign.textContent = "Reassign";
    reassign.style.marginLeft = "6px";
    reassign.onclick = async () => {
      const who = prompt("Assign to (user id, blank to clear):", r.assignee ?? "");
      if (who === null) return;
      try { await this.host.api.assignRecord(pid, m.key, rid, who.trim() || null); this.openRecord(m, rid); }
      catch (e) { this.host.setStatus(`error: ${(e as Error).message}`); }
    };
    asgRow.appendChild(reassign);
    this.root.appendChild(asgRow);

    // attachments (files in object storage)
    this.renderAttachments(m, r, rid);

    // related records (outgoing references + incoming records that point here)
    const relatedBox = document.createElement("div");
    this.root.appendChild(relatedBox);
    void this.renderRelated(relatedBox, m.key, rid);

    // anchor / linked elements
    if (r.element_guids?.length) {
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = "Show in model";
      b.style.margin = "4px 0"; b.onclick = () => this.host.onSelectGuids(r.element_guids!);
      this.root.appendChild(b);
    }

    // workflow actions (server-gated by party)
    const acts = r.available_actions ?? [];
    if (acts.length) {
      const ad = document.createElement("div"); ad.className = "section-title"; ad.textContent = "Workflow";
      this.root.appendChild(ad);
      for (const a of acts) {
        const b = document.createElement("button"); b.className = "tool-btn";
        b.textContent = `${a.action} → ${a.to}`; b.style.cssText = "display:block;margin:3px 0;width:100%;text-align:left";
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

  /** Attachments section: list existing files (download) + upload a new one. */
  private renderAttachments(m: ModuleDef, r: ModuleRecord, rid: string) {
    const pid = this.host.projectId()!;
    const t = document.createElement("div"); t.className = "section-title"; t.textContent = "Attachments";
    this.root.appendChild(t);
    for (const a of r.attachments ?? []) {
      const row = document.createElement("div"); row.className = "portal-act";
      const kb = a.size > 1024 ? `${Math.round(a.size / 1024)} KB` : `${a.size} B`;
      const link = document.createElement("a"); link.className = "ref-link"; link.textContent = `📎 ${a.filename}`;
      link.href = this.host.api.attachmentUrl(a.id); link.target = "_blank";
      row.append(link, document.createTextNode(`  ${kb}`));
      this.root.appendChild(row);
    }
    const file = document.createElement("input"); file.type = "file"; file.style.cssText = "font-size:11px;margin:4px 0;max-width:100%";
    file.onchange = async () => {
      const f = file.files?.[0]; if (!f) return;
      try { await this.host.api.uploadAttachment(pid, m.key, rid, f); this.host.setStatus(`attached ${f.name}`); this.openRecord(m, rid); }
      catch (e) { this.host.setStatus(`upload failed: ${(e as Error).message}`); }
    };
    this.root.appendChild(file);
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
