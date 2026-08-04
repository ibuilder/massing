import type { ApiClient, ModuleDef } from "../api/client";
import { escapeHtml as esc, toast } from "../ui/feedback";
import { progressBar } from "../ui/charts";
import { countNarrative, statusChip } from "../ui/chips";
import { noProjectHtml } from "../ui/empty";
import { buildPulse, pulseRailEl } from "./panels/pulse";
import type { PanelContext } from "./panelContext";
import { type RegisterFilter, RegisterUI } from "./register/register";
import { SECTIONS_BY_PERSONA, readDensity, readFavs, readRecents, readRoomOpen, setDensity, setRoomOpen, toggleFav } from "./prefs";
import { el } from "../ui/dom";
import { ALL_DESTS, type Dest, stagesFor } from "../shell/destinations";
import { FALLBACK_ROOMS, ROOM_HOME, type SpineState, destRoom, loadSpine, portalRooms, preselectedRoom, unroomedDests, visibleRooms } from "../shell/spine";
import type { RoomDef } from "../api/types";
// PANEL-LAZY (PERF): the ~30 secondary portal panels are DYNAMICALLY imported at first render
// (see the wrapper methods below), not eagerly bundled into the app shell — each panel file (and
// its heavy deps: charts, tables, module-graph, etc.) becomes its own chunk fetched only when the
// user opens that destination. This was the single biggest eager-bundle cut. Panel modules are
// grouped per source file so one dynamic import covers all its exports (Vite dedupes the chunk).

/** The bridge the portal needs to the rest of the app: API, project, 3D selection, status line. */
export interface PortalHost {
  api: ApiClient;
  projectId: () => string | null;
  anchorPoint: () => { x: number; y: number; z: number } | null;  // last clicked 3D point
  selectedGuid: () => string | null;
  onSelectGuids: (guids: string[]) => void;                       // highlight in 3D
  onPinsChanged: () => void;                                      // refresh model pins
  setStatus: (m: string) => void;
}

/**
 * The portal **shell**: the left nav rail, the room spine, the workspace/persona filters, the
 * dashboards, the module catalog, and the `__key__` dispatch that first-class destinations and
 * lazily-imported panels hang off.
 *
 * It is deliberately *not* the register renderer any more. Until v0.3.850 this class was both, which
 * made one file the property of two lanes at once — `register/register.ts` carries that history and
 * the reasoning. What is left here is Lane A · Shell & IA work; a register is Lane B's.
 *
 * The shell reaches into the register in exactly four places, all on the dashboard, all through the
 * wrappers below: open a register, open a record, set a saved view's sort, and drain the offline
 * upload queue at init. Anything more than that is a sign the split is being undone.
 */
export class PortalUI {
  private mods: ModuleDef[] = [];
  private nav?: HTMLElement;          // persistent left module-nav rail (built once)
  /** R26 spine allocation, loaded only when the flag is on. Null = render the classic stage rail. */
  private spine: SpineState | null = null;
  private activeKey: string | null = null;
  // R2 — workspace split: this portal serves the "construction" (GC build), "developer"
  // (real-estate), or "design" (architect/engineer) module set. `showAll` is the escape hatch so
  // every role can still reach every register (the user's "everyone has access to all data, just a
  // few more clicks").
  private wsFilter: "construction" | "developer" | "design" = "construction";
  private showAll = false;
  /**
   * ROOM-NAV — the room this portal is IN, set by the tab bar's `aec:room` event. Null until the
   * user picks one; the workspace's preselected room until then. This is the state the old shell
   * never had: room switching was a DOM click-simulation precisely because nothing owned "which
   * room", so the tab bar had to reach in and poke the rail it was racing.
   */
  private activeRoom: string | null = null;
  /** Escape hatch: render the other rooms' groups below the active one. Session-scoped, like showAll. */
  private showAllRooms = false;
  private room(): string { return this.activeRoom ?? preselectedRoom(this.wsFilter); }
  /** Which workspace this portal renders. Call before init(). */
  setWorkspace(ws: "construction" | "developer" | "design") { this.wsFilter = ws; }
  /** A module's workspace membership as a list — supports "|"-separated multi-membership. */
  private wsOf(m: ModuleDef): string[] { return (m.workspace || "construction").split("|"); }
  /** True when a module belongs in the active workspace (or Show-all is on). */
  private inWs(m: ModuleDef) { return this.showAll || this.wsOf(m).includes(this.wsFilter); }

  /**
   * The generic register renderer, which used to be the back half of this file (see
   * `register/register.ts` for why it moved and which lane owns it). Assigned in the constructor
   * rather than as a field initialiser because `panelCtx()` closes over `this`, and the shell's
   * `root` is *reassigned* by `init()` — the context reads it through a getter so the register
   * always writes into the content pane rather than the pane that existed at construction time.
   */
  private reg!: RegisterUI;

  constructor(private root: HTMLElement, private host: PortalHost) {
    this.reg = new RegisterUI(this.panelCtx());
    // The tab bar announces the room; the portal that hosts it responds. Registered in the
    // constructor rather than init() because the first room click usually PRECEDES init — the
    // workspace switch that triggers lazy init and the room event arrive in the same tick, and a
    // listener added in init would miss the event that caused it. Pre-init the handler only records
    // the room; init() reads it and lands there instead of the dashboard.
    window.addEventListener("aec:room", (e) => {
      const id = (e as CustomEvent<string>).detail;
      if (!portalRooms(this.wsFilter).includes(id)) return;   // another portal's room
      this.activeRoom = id;
      this.showAllRooms = false;                              // a deliberate switch re-scopes the rail
      if (!this.nav) return;                                  // not initialised yet — init() lands
      const home = ROOM_HOME[id];
      // Invoke the destination DIRECTLY — this is the whole fix. The previous shell clicked
      // `[data-dest]` buttons under a 4s retry poll, raced the workspace rebuild, and visibly lost:
      // Planning/Schedule rendered empty, Cost/Work showed the previous room (measured 2026-08-02).
      if (home && this.destDispatch()[home]) this.goToDest(home);
      else this.buildNav();
    });
  }

  /** Build the PanelContext handed to extracted feature panels (portal/panels/*). */
  /** The `__key__` → render map for first-class portal destinations. Hoisted out of buildNav so a panel
   *  can programmatically jump to a destination (SPRINT MB deep-links) via `PanelContext.navigate`. */
  private destDispatch(): Record<string, () => unknown> {
    return {
      __schedule__: () => { const m = this.mods.find((x) => x.key === "schedule_activity"); if (m) void this.renderScheduleViews(m); },
      __budget__: () => this.renderBudget(), __review__: () => this.renderRiskReview(),
      __aiassist__: () => this.renderAiAssist(), __riskcost__: () => this.renderRiskCost(),
      __ids__: () => this.renderIds(), __turnover__: () => this.renderTurnover(),
      __operations__: () => this.renderOperations(), __energy__: () => this.renderEnergy(),
      __fca__: () => this.renderFca(), __resilience__: () => this.renderResilience(),
      __spine__: () => this.renderSpine(),
      __land__: () => this.renderLandScreen(), __lifecycle__: () => this.renderLifecycle(),
      __diligence__: () => this.renderDiligence(), __esg__: () => this.renderEsg(),
      __market__: () => this.renderMarket(), __conceptrender__: () => this.renderConceptRender(),
      __materials__: () => this.renderMaterials(),
      __modulegraph__: () => this.renderModuleGraph(),
      __evm__: () => this.renderEvm(), __resload__: () => this.renderResourceLoading(),
      __wip__: () => this.renderWip(), __ledger__: () => this.renderLedger(),
      __traceability__: () => this.renderTraceability(),
      __standards__: () => this.renderStandards(), __bimkpi__: () => this.renderBimKpi(),
      __masterbuilder__: () => this.renderMasterBuilder(), __selections__: () => this.renderSelections(),
      __margin__: () => this.renderMargin(), __assets__: () => this.renderAssets(),
      __workqueue__: () => this.renderWorkQueue(),
      __equipment__: () => this.renderEquipment(), __massingopt__: () => this.renderMassingOpt(),
      __designmetrics__: () => this.renderDesignMetrics(), __mepfittings__: () => this.renderMepFittings(),
      __topicboard__: () => this.renderTopicBoard(),
      __spaceutil__: () => this.renderSpaceUtil(),
      __responsibility__: () => this.renderResponsibility(),
      __program__: () => this.renderProgram(), __modelqa__: () => this.renderModelQa(),
      __modelanalysis__: () => this.renderModelAnalysis(),
      __documents__: () => this.renderDocuments(),
      __portfolio__: () => this.renderPortfolio(), __benchmarks__: () => this.renderBenchmarks(),
    };
  }

  /** Jump to a first-class destination by its `__key__` (no-op for an unknown key). */
  private goToDest(key: string): void {
    const fn = this.destDispatch()[key];
    if (!fn) return;
    this.activeKey = key;
    void fn();
    this.buildNav();
  }

  private panelCtx(): PanelContext {
    const self = this;
    return {
      get root() { return self.root; },
      host: self.host,
      get mods() { return self.mods; },
      get activeKey() { return self.activeKey; },
      set activeKey(v: string | null) { self.activeKey = v; },
      bar: (t, b) => self.bar(t, b),
      buildNav: () => self.buildNav(),
      renderHome: () => self.renderHome(),
      openModule: (m, f) => self.reg.openModule(m, f),
      navigate: (k) => self.goToDest(k),
      hasDest: (k) => Boolean(self.destDispatch()[k]),
    };
  }

  // --- the register renderer, reached through `reg` -------------------------
  // Four call sites, all in the dashboard: a register link, a record link, a saved-view link (which
  // sets `reg.sort` first) and the palette's `openModuleByKey`. They are wrappers rather than direct
  // `this.reg.x(...)` calls at each site so the shell's dependency on the register is a short,
  // readable list rather than something you have to grep the file to find.
  private openModule(m: ModuleDef, filter: RegisterFilter = {}) { return this.reg.openModule(m, filter); }
  private openRecord(m: ModuleDef, rid: string) { return this.reg.openRecord(m, rid); }
  private openByBrief(moduleKey: string, id: string) { this.reg.openByBrief(moduleKey, id); }

  /** Returns whether the portal actually initialised. A caller that latches "already done" MUST key
   *  that latch off this and not off "we called init once" — see `openDeveloperTab` in main.ts. The
   *  no-project branch below is a *deferral*, not a completion: the project usually arrives moments
   *  later, and a latch set here freezes the empty state in place for the rest of the session. */
  async init(): Promise<boolean> {
    if (!this.host.projectId()) { this.root.innerHTML = noProjectHtml(this.wsFilter === "developer" ? "the developer workspace" : this.wsFilter === "design" ? "the design workspace" : "the GC portal"); return false; }
    this.mods = await this.host.api.modules();
    // build the persistent shell once: [nav rail | content]. `this.root` is redirected to the
    // content pane, so every existing render path writes into it while the nav rail stays put.
    const outer = this.root;
    outer.innerHTML = ""; outer.classList.add("portal-shell");
    this.nav = document.createElement("nav"); this.nav.className = "portal-nav";
    const content = document.createElement("div"); content.className = "portal-content";
    outer.append(this.nav, content);
    this.root = content;
    // The spine costs one request. A failure leaves `spine` null and the rail falls back to
    // FALLBACK_ROOMS — the six rooms are structural, so losing the *allocation* must not lose the
    // *shell*. With the classic rail gone (v0.3.779) there is nothing else to fall back to, which
    // makes that fallback load-bearing rather than belt-and-braces.
    try { this.spine = await loadSpine(this.host.api); } catch { this.spine = null; }
    this.buildNav();
    // re-order the module catalog's default-open sections when the persona changes
    window.addEventListener("aec:persona", () => { this.refreshCatalog(); this.buildNav(); });
    // drain any uploads queued offline in a previous session, and keep watching for reconnect
    this.reg.hookOnline(); void this.reg.flushUploads();
    // Land on the active room's home when a room was picked before init finished (the common path:
    // the tab click both triggers this init and names the room). Dashboard otherwise.
    const landing = this.activeRoom ? ROOM_HOME[this.activeRoom] : null;
    if (landing && this.destDispatch()[landing]) this.goToDest(landing);
    else await this.renderHome();
    return true;
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

    // The rail's upper half is the room spine — the only shell since v0.3.779.
    const dests = this.destDispatch();
    this.buildRoomRail(nav, dests);

    const filter = document.createElement("input");
    filter.type = "search"; filter.placeholder = "Filter…"; filter.className = "portal-filter pnav-filter";
    nav.appendChild(filter);

    const favs = readFavs();

    const item = (m: ModuleDef) => this.moduleButton(m);
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
    const recentMods = readRecents()
      .map((k) => visible.find((m) => m.key === k))
      .filter((m): m is ModuleDef => !!m && !favs.has(m.key));
    if (recentMods.length) group("🕘 Recent", recentMods, true);
    // Every register is already listed inside its room, so grouping them AGAIN by section here would
    // show each module twice under two different taxonomies — the exact condition the spine was built
    // to remove. Favourites and Recent stay: those are one module under a personal shortcut, not a
    // second filing system.

    // "Show all modules" — reveal the other workspaces' registers so every role can reach all data
    // (a few more clicks, per the product principle). Persisted to the toggle for the session.
    const otherCount = this.mods.filter((m) => !this.wsOf(m).includes(this.wsFilter)).length;
    if (otherCount) {
      const toggle = document.createElement("button");
      toggle.className = "pnav-item pnav-showall" + (this.showAll ? " active" : "");
      toggle.innerHTML = this.showAll
        ? `<span class="ic">▾</span> Showing all modules`
        : `<span class="ic">▸</span> Show all modules (+${otherCount})`;
      toggle.title = this.showAll ? "Hide the other workspaces' registers" : `Also show every other register`;
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

  /**
   * A rail button for a module register. Shared by the room rail and the section list, for the same
   * reason `destButton` is shared: two places building the same button is how they come to differ.
   */
  private moduleButton(m: ModuleDef): HTMLButtonElement {
    const b = document.createElement("button");
    b.className = "pnav-item" + (this.activeKey === m.key ? " active" : "");
    b.dataset.modname = m.name.toLowerCase();
    b.dataset.mod = m.key;
    // Server-supplied name and icon: escaped, because a module.json is a file on disk and the rail
    // renders on every screen.
    b.innerHTML = `<span class="ic">${esc(m.icon || "•")}</span> ${esc(m.name)}`;
    b.onclick = () => { this.activeKey = m.key; void this.openModule(m); this.buildNav(); };
    return b;
  }

  /** A rail button for a first-class destination. Shared by both shells so they cannot diverge. */
  private destButton(d: Dest, dests: Record<string, () => unknown>): HTMLButtonElement {
    const b = document.createElement("button");
    b.className = "pnav-item pnav-home" + (this.activeKey === d.key ? " active" : "");
    // Addressable by key. Without this the rail is navigable only by a human clicking it: the pinned
    // rail and the room tabs both try to reach a destination with `[data-dest="…"]`, and until now
    // the ONLY nodes carrying that attribute were the pinned rail's own buttons — so its
    // "open what I pinned" handler matched itself and clicked itself instead of navigating.
    b.dataset.dest = d.key;
    b.innerHTML = `<span class="ic">${d.icon}</span> ${d.label.replace(/&/g, "&amp;").replace(/</g, "&lt;")}`;
    // A `goto` destination hands off to another workspace and renders NOTHING here, so it must not
    // mark itself active. v0.3.770 tried that — to make a `goto` destination usable as a room's
    // landing target — and it was wrong in the worst direction: the marker is sticky, nothing clears
    // it, so `goToRoom`'s "have we arrived?" check returned true for a navigation that never
    // happened. A second Deal click skipped the dispatch entirely and stranded the user with the tab
    // lit and the previous panel showing. The live check that "confirmed" it read the same marker the
    // retry keys on, which is circular; the content pane still said Budget the whole time.
    //
    // The rule this restores: **a room's home must be a destination that actually renders**
    // (`spine.test.ts` now asserts it). Reaching Underwriting from the Deal tab needs a real panel,
    // not a truer-looking flag.
    b.onclick = d.goto
      ? () => window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: d.goto }))
      : () => { this.activeKey = d.key; void dests[d.key]?.(); this.buildNav(); };
    return b;
  }

  /**
   * The room spine: **Design · Planning · Cost · Schedule · Deal · Work**, the same for every role.
   *
   * A workspace *weights* the spine — its room comes first and opens — but never removes a room. A
   * room that disappears in one workspace is a room the user has to relearn where to find, which is
   * the failure the spine exists to end.
   *
   * Two things are deliberately visible rather than tidied away: a destination with no room, and a
   * module the API could not place. Both are defects, and an IA restructure's characteristic failure
   * is making something unreachable in a way that looks perfectly fine.
   */
  private buildRoomRail(nav: HTMLElement, dests: Record<string, () => unknown>) {
    // Degrade the BADGES, not the shell. `GET /rooms` supplies the allocation and the
    // ball-in-your-court counts; the rooms themselves are a fixed set both sides already agree
    // on. Silently rebuilding the old rail when that request fails — which is what happened until
    // v0.3.718 — hands somebody the previous shell with no explanation, and is indistinguishable
    // from the redesign never having shipped.
    const served = this.spine?.alloc.rooms ?? [];
    const rooms: RoomDef[] = served.length ? served : [...FALLBACK_ROOMS];
    nav.dataset.spineSource = served.length ? "server" : "fallback";
    const byRoom = new Map<string, Dest[]>();
    const shown = stagesFor(this.wsFilter, (k) => this.mods.some((x) => x.key === k))
      .flatMap(([, items]) => items);
    // Every destination the platform HAS, not just this workspace's slice: the spine's promise is
    // that all of it stays reachable, so a destination only the Developer rail used to show is
    // placed in its room here rather than lost.
    const seen = new Set<string>();
    for (const d of [...shown, ...ALL_DESTS]) {
      if (seen.has(d.key)) continue;
      if (d.needs && !this.mods.some((x) => x.key === d.needs)) continue;
      seen.add(d.key);
      const room = destRoom(d.key);
      if (!room) continue;                                            // reported below, not filed
      (byRoom.get(room) ?? byRoom.set(room, []).get(room)!).push(d);
    }
    // ROOM-NAV (2026-08-02): render the ACTIVE room only, not all seven collapsed. The all-rooms
    // rail read as "every module on every screen" — the user said exactly this — and it forced the
    // tab bar to switch rooms by clicking rail nodes it was racing. Each room now has its own menu;
    // the other rooms are the tab bar's job, plus the escape hatch below.
    const active = this.room();
    for (const room of visibleRooms(rooms, this.wsFilter, active, this.showAllRooms)) {
      const det = document.createElement("details"); det.className = "pnav-stage-group pnav-room";
      det.dataset.room = room.id;
      const skey = `${this.wsFilter}:${room.id}`;
      const items = byRoom.get(room.id) ?? [];
      // The active room is the rail's whole content, so it is always open — collapse memory only
      // governs the OTHER rooms, which render solely under the escape hatch.
      const said = readRoomOpen(skey);
      det.open = room.id === active || items.some((d) => d.key === this.activeKey) || (said ?? false);
      det.ontoggle = () => setRoomOpen(skey, det.open);
      det.classList.toggle("pnav-room-active", room.id === active);
      // The room's MODULES, not only its first-class destinations.
      //
      // Until v0.3.767 `byRoom` was built from `ALL_DESTS` alone, so a room group showed only its
      // panels while its registers were grouped by *section* in a second list further down the rail.
      // That is two taxonomies in one rail — the exact failure the spine was built to end — and it
      // showed: Planning owned 16 modules and its group displayed 2. The room is authoritative and
      // the server already states it per module (`ModuleDef.room`), so it is read here rather than
      // re-derived, which is how the four competing rails came to exist in the first place.
      const roomMods = this.mods
        .filter((m) => m.room === room.id)
        .sort((a, b) => a.name.localeCompare(b.name));
      const sum = document.createElement("summary"); sum.className = "pnav-stage";
      // The job line is the room's whole justification — "Cost" alone is a noun, "price it, buy it
      // out, change it and pay for it" is what you came here to do.
      sum.innerHTML = `${esc(room.label)} <span class="meta">${esc(room.job)}</span>`;
      sum.title = room.job;
      det.appendChild(sum);
      for (const d of items) det.appendChild(this.destButton(d, dests));
      // Registers after panels, and separated: a panel answers a question, a register is a table you
      // keep. Same room, different kind of thing, so the eye should be able to tell them apart
      // without reading every label.
      if (roomMods.length) {
        // Sub-rooms, by SECTION.
        //
        // Design owns 32 registers and Schedule 38 — a flat list at that size is precisely the wall
        // the spine was built to replace, so the room needs a second level. The grouping key is the
        // module's `section`, which is *already* what decides its room: a strict refinement of the
        // existing table, not a new taxonomy competing with it.
        //
        // R31-DESIGN-GROUPS: the ORDER and the membership now come from `/rooms`, for the same reason
        // stated forty lines up about the room itself — the server already computes this, and a
        // client that re-derives it is how four competing rails came to exist. The local fallback
        // stays because the rail must render when `/rooms` fails.
        //
        // **The headings were the actual defect, not the absence of them.** This grouping shipped
        // before the sections were fit to be read as headings: Design's largest was `Engineering`,
        // nine modules that included drawings, RFIs, submittals and MEP equipment — a heading a user
        // would open expecting engineering and find a filing accident. Grouping by a meaningless key
        // produces meaningless groups, confidently labelled, which is worse than a flat list because
        // it looks like somebody decided.
        //
        // Server order is largest-first: the heading most likely to be wanted should not sit under a
        // three-module one because of its initial letter.
        //
        // Below SUBGROUP_MIN the headings cost more than they explain, so a small room stays flat.
        const SUBGROUP_MIN = 8;
        const byKey = new Map(roomMods.map((m) => [m.key, m]));
        const bySection = new Map<string, ModuleDef[]>();
        for (const g of room.groups ?? []) {
          const mods = g.modules.map((k) => byKey.get(k)).filter(Boolean) as ModuleDef[];
          if (mods.length) bySection.set(g.section || "Other", mods);
        }
        if (!bySection.size) {
          for (const m of roomMods) {
            const sec = m.section || "Other";
            (bySection.get(sec) ?? bySection.set(sec, []).get(sec)!).push(m);
          }
        }
        const subgroup = roomMods.length >= SUBGROUP_MIN && bySection.size > 1;
        const rule = document.createElement("div");
        rule.className = "pnav-subhead meta";
        rule.textContent = `Registers (${roomMods.length})`;
        det.appendChild(rule);
        if (subgroup) {
          for (const [sec, mods] of bySection) {
            const h = document.createElement("div");
            h.className = "pnav-subsec meta";
            h.textContent = `${sec} · ${mods.length}`;
            det.appendChild(h);
            for (const m of mods) det.appendChild(this.moduleButton(m));
          }
        } else {
          for (const m of roomMods) det.appendChild(this.moduleButton(m));
        }
      }
      nav.appendChild(det);
    }
    // The escape hatch: reveal the other rooms' groups, collapsed, below the active one. Everything
    // stays reachable from every screen (the spine's promise) — the tabs are the fast path, this is
    // the browse path. Only rendered when there IS more than one room to show.
    if (rooms.length > 1) {
      const t = document.createElement("button");
      t.className = "pnav-item pnav-showall" + (this.showAllRooms ? " active" : "");
      t.innerHTML = this.showAllRooms
        ? `<span class="ic">▾</span> This room only`
        : `<span class="ic">▸</span> All rooms (+${rooms.length - 1})`;
      t.title = this.showAllRooms ? "Scope the rail back to this room" : "Also list the other rooms' panels and registers";
      t.onclick = () => { this.showAllRooms = !this.showAllRooms; this.buildNav(); };
      nav.appendChild(t);
    }
    const orphans = unroomedDests([...seen]);
    if (orphans.length || this.spine?.unplaced.length) {
      const warn = document.createElement("div");
      warn.className = "pnav-khint meta";
      const bits: string[] = [];
      if (orphans.length) bits.push(`${orphans.length} destination${orphans.length > 1 ? "s" : ""} with no room`);
      if (this.spine?.unplaced.length) bits.push(`${this.spine.unplaced.length} module(s) unplaced`);
      warn.textContent = `⚠ ${bits.join(" · ")} — reachable below, but not filed`;
      warn.title = [...orphans, ...(this.spine?.unplaced ?? []).map((u) => u.key)].join(", ");
      nav.appendChild(warn);
    }
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
    tag.style.cssText = `background:${pill[1]}22;color:${pill[1]};border-color:${pill[1]}`; tag.textContent = pill[0] ?? "";
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
    // UX-KPI: the one-line plain narrative — a template string over numbers we already hold
    const parts: [number, string][] = [
      [sched.milestones.late, "milestones late"],
      [sched.milestones.due_soon, "due soon"],
      [bud.variance_at_completion < 0 ? 1 : 0, "budget over at completion"],
      [sched.lookahead_3wk, "activities in the 3-week lookahead"],
    ];
    const line = document.createElement("div"); line.className = "kpi-narrative";
    line.textContent = countNarrative(parts, "On plan — no exceptions to chase");
    card.appendChild(line);
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
      // UX-KPI — the one-line narrative band above the tiles, so the home says what the numbers mean
      // instead of leaving the reader to total them. Deterministic template text, never an LLM; a
      // register with nothing in it is simply absent rather than reported as a zero.
      const narrative = countNarrative(
        cards.map(([label, val]) => [val, label.toLowerCase()] as [number, string]),
        "No developer registers have records yet");
      const band = el("div", "kpi-narrative"); band.style.margin = "2px 0 6px";
      band.textContent = narrative;
      root.appendChild(band);
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

  // PANEL-LAZY: each wrapper dynamic-imports its panel chunk on first open (Vite splits per file).
  private async renderRiskReview() { return (await import("./panels/aiassist")).renderRiskReview(this.panelCtx()); }
  private async renderAiAssist() { return (await import("./panels/aiassist")).renderAiAssist(this.panelCtx()); }

  private async renderBenchmarks() { return (await import("./panels/analytics")).renderBenchmarks(this.panelCtx()); }
  private async renderRiskCost() { return (await import("./panels/analytics")).renderRiskCost(this.panelCtx()); }
  private async renderMarket() { return (await import("./panels/analytics")).renderMarket(this.panelCtx()); }
  private async renderEvm() { return (await import("./panels/evm")).renderEvm(this.panelCtx()); }
  private async renderResourceLoading() { return (await import("./panels/resourceLoading")).renderResourceLoading(this.panelCtx()); }
  private async renderWip() { return (await import("./panels/wip")).renderWip(this.panelCtx()); }
  private async renderLedger() { return (await import("./panels/ledger")).renderLedger(this.panelCtx()); }
  private async renderTraceability() { return (await import("./panels/traceability")).renderTraceability(this.panelCtx()); }

  private async renderLandScreen() { return (await import("./panels/design")).renderLandScreen(this.panelCtx()); }
  private async renderLifecycle() { return (await import("./panels/design")).renderLifecycle(this.panelCtx()); }
  private async renderDiligence() { return (await import("./panels/design")).renderDiligence(this.panelCtx()); }
  private async renderEsg() { return (await import("./panels/design")).renderEsg(this.panelCtx()); }
  private async renderConceptRender() { return (await import("./panels/design")).renderConceptRender(this.panelCtx()); }
  private async renderMaterials() { return (await import("./panels/materials")).renderMaterials(this.panelCtx()); }
  private async renderModuleGraph() { return (await import("./panels/moduleGraph")).renderModuleGraph(this.panelCtx()); }

  // --- Model Health launcher: the model-QA checks live in the Model viewer's Tools rail (they need
  //     the loaded 3D geometry), so from Design we explain them and deep-link straight there. --------
  private renderModelQa() {
    const root = this.root; root.innerHTML = "";
    const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
    root.appendChild(this.bar("✅ Model Health", () => { this.activeKey = null; void this.renderHome(); this.buildNav(); }));
    const intro = el("div", "meta"); intro.style.marginBottom = "10px";
    intro.innerHTML = "The model-health checks run against the loaded 3D model, so they live in "
      + "<b>Model → Tools</b>. Open the model, then run these to verify the design is coordinated and "
      + "carries the data the downstream trades, estimators, and plan reviewers need.";
    root.appendChild(intro);
    const goTools = () => { window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: "model" }));
      // RAIL-SPLIT renamed this destination: the model-QA checks this card describes live under
      // Review. The old selector matched nothing, so the button silently did nothing.
      setTimeout(() => (document.querySelector('.rail-btn[data-rail="review"]') as HTMLElement | null)?.click(), 60); };
    const open = el("button", "tool-btn"); open.textContent = "Open Model → Tools →"; open.onclick = goTools;
    open.style.marginBottom = "12px"; root.appendChild(open);
    const checks: [string, string][] = [
      ["✅ Data QA (completeness)", "Every element carries its required/recommended attributes — highlights the gaps in 3D."],
      ["🏛 Code-readiness check", "Does the model hold the data a plan review needs (egress, ratings, occupancy)?"],
      ["⚡ Run clash / 🔗 Federated clash", "Hard/soft clashes within a model or across discipline models → BCF issues."],
      ["📐 Alignment check", "Storeys + working origin line up across the federated discipline models."],
      ["✓ Validate (IDS)", "The model conforms to the project's IDS rule set (buildingSMART Information Delivery Specification)."],
      ["🎨 Color by property", "Shade the model by any attribute to spot missing / inconsistent data visually."],
    ];
    const list = el("div"); list.style.cssText = "display:flex;flex-direction:column;gap:8px";
    for (const [name, desc] of checks) {
      const c = el("div", "dash-card"); c.style.cssText = "cursor:pointer"; c.onclick = goTools;
      c.innerHTML = `<div style="font-weight:600">${esc(name)}</div><div class="meta">${esc(desc)}</div>`;
      list.appendChild(c);
    }
    root.appendChild(list);
  }

  // --- Design (architect/engineer) home: model-health + phase-progress command center, with quick
  //     jumps to the program, standards, and coordination destinations. -----------------------------
  private async renderDesignHome(root: HTMLElement, pid: string,
      el: (tag: string, cls?: string) => HTMLElement, jump: (key: string, state?: string) => void) {
    const head = el("div", "section-title"); head.style.cssText = "display:flex;justify-content:space-between;align-items:center";
    head.append("Design — architect & engineer");
    const modelBtn = el("button", "tool-btn") as HTMLButtonElement;
    modelBtn.textContent = "Open Model →"; modelBtn.title = "Open the 3D model & its coordination tools";
    modelBtn.onclick = () => window.dispatchEvent(new CustomEvent("aec:goto-workspace", { detail: "model" }));
    head.append(modelBtn); root.appendChild(head);
    const intro = el("div", "meta"); intro.style.margin = "2px 0 10px";
    intro.textContent = "Program the brief, author the model against the information requirements, and "
      + "coordinate the drawings — AIA SD/DD/CD · RIBA stages 2–4.";
    root.appendChild(intro);

    // quick-launch tiles for the design destinations (call the special renderers directly)
    const goDest = (key: string, fn: () => unknown) => { this.activeKey = key; void fn(); this.buildNav(); };
    const tiles: [string, string, () => void][] = [
      ["🧩", "Space Program", () => goDest("__program__", () => this.renderProgram())],
      ["🧭", "Project Lifecycle", () => goDest("__lifecycle__", () => this.renderLifecycle())],
      ["📋", "IDS Requirements", () => goDest("__ids__", () => this.renderIds())],
      ["🗂", "CDE / Standards", () => goDest("__standards__", () => this.renderStandards())],
      ["📊", "BIM KPIs", () => goDest("__bimkpi__", () => this.renderBimKpi())],
      ["✅", "Model Health", () => goDest("__modelqa__", () => this.renderModelQa())],
    ];
    const grid = el("div"); grid.style.cssText = "display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-bottom:12px";
    for (const [ic, label, on] of tiles) {
      const c = el("div", "dash-card"); c.style.cssText = "cursor:pointer;text-align:center";
      c.innerHTML = `<div style="font-size:22px">${ic}</div><div style="font-weight:600">${label}</div>`;
      c.onclick = on; grid.appendChild(c);
    }
    root.appendChild(grid);

    // MODEL SNAPSHOT — the design home's substance. The register KPIs below only render when a
    // register already has records, so on a real project with an authored model and empty registers
    // this pane collapsed to the tiles alone: ~200px of content beside a 30-item nav rail, which
    // reads as an empty workspace. Model health comes from the MODEL, so it populates exactly when
    // the design workspace is being used for what it is for.
    try {
      const [health, qa] = await Promise.all([
        this.host.api.modelHealth(pid).catch(() => null),
        this.host.api.modelQa(pid).catch(() => null),
      ]);
      if (health?.model_available || qa) {
        const h = el("div", "section-title"); h.textContent = "Model snapshot"; h.style.marginBottom = "6px";
        const row = el("div"); row.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px";
        const tile = (big: string, small: string, go?: () => void, title?: string) => {
          const c = el("div", "dash-card" + (go ? " kpi-click" : "")); c.style.minWidth = "128px";
          if (go) { c.style.cursor = "pointer"; c.onclick = go; }
          if (title) c.title = title;
          c.innerHTML = `<div style="font-size:20px;font-weight:600">${big}</div><div class="meta">${small}</div>`;
          row.appendChild(c);
        };
        if (health?.overall_score != null) {
          tile(`${Math.round(health.overall_score)}`, `Model health · ${health.band}`,
            () => goDest("__modelqa__", () => this.renderModelQa()),
            `${health.scored_lenses} lenses scored`);
        }
        if (qa) {
          tile(qa.element_count.toLocaleString(), "Elements");
          // a clean model says so rather than showing a bare 0 that reads as "not run"
          tile(qa.clean ? "Clean" : String(qa.total_issues), qa.clean ? "Integrity" : "Integrity issues",
            () => goDest("__modelqa__", () => this.renderModelQa()));
        }
        if (row.childElementCount) root.append(h, row);
      }
    } catch { /* model snapshot is additive — its absence must never blank the home */ }

    // register-count KPIs for the design-owned registers (from the dashboard's per-module counts)
    try {
      const d = await this.host.api.dashboard(pid);
      const cnt = (k: string) => d.by_module.find((m) => m.key === k)?.count ?? 0;
      const regs: [string, string][] = [
        ["drawing", "Drawings"], ["submittal", "Submittals"], ["rfi", "RFIs"],
        ["coordination_issue", "Coordination"], ["design_review", "Design reviews"],
        ["information_container", "Info containers"],
      ];
      const cards = el("div"); cards.style.cssText = "display:flex;gap:8px;flex-wrap:wrap";
      let any = false;
      for (const [key, label] of regs) {
        const n = cnt(key); if (!n) continue; any = true;
        const tile = el("div", "dash-card kpi-click"); tile.style.minWidth = "120px"; tile.style.cursor = "pointer";
        tile.innerHTML = `<div style="font-size:20px;font-weight:600">${n}</div><div class="meta">${label}</div>`;
        tile.onclick = () => jump(key); cards.appendChild(tile);
      }
      if (any) {
        const h = el("div", "section-title"); h.textContent = "Design registers"; h.style.marginBottom = "6px";
        // UX-KPI — the same one-line narrative treatment as the developer home
        const band = el("div", "kpi-narrative"); band.style.margin = "0 0 6px";
        band.textContent = countNarrative(
          regs.map(([key, label]) => [cnt(key), label.toLowerCase()] as [number, string]),
          "No design registers have records yet");
        root.append(h, band, cards);
      }
    } catch { /* no dashboard yet — tiles above are enough */ }
  }

  private async renderProgram() { return (await import("./panels/standards")).renderProgram(this.panelCtx()); }
  private async renderBimKpi() { return (await import("./panels/standards")).renderBimKpi(this.panelCtx()); }
  private async renderMasterBuilder() { return (await import("./panels/masterBuilder")).renderMasterBuilder(this.panelCtx()); }
  private async renderSelections() { return (await import("./panels/selections")).renderSelections(this.panelCtx()); }
  private async renderMargin() { return (await import("./panels/margin")).renderMargin(this.panelCtx()); }
  private async renderAssets() { return (await import("./panels/assets")).renderAssets(this.panelCtx()); }
  private async renderWorkQueue() { return (await import("./panels/workQueue")).renderWorkQueue(this.panelCtx()); }
  private async renderEquipment() { return (await import("./panels/equipment")).renderEquipment(this.panelCtx()); }
  private async renderMassingOpt() { return (await import("./panels/massingOpt")).renderMassingOpt(this.panelCtx()); }
  private async renderDesignMetrics() { return (await import("./panels/designMetrics")).renderDesignMetrics(this.panelCtx()); }
  private async renderMepFittings() { return (await import("./panels/mepFittings")).renderMepFittings(this.panelCtx()); }
  private async renderTopicBoard() { return (await import("./panels/topicBoard")).renderTopicBoard(this.panelCtx()); }
  private async renderSpaceUtil() { return (await import("./panels/spaceUtil")).renderSpaceUtil(this.panelCtx()); }
  private async renderModelAnalysis() { return (await import("./panels/standards")).renderModelAnalysis(this.panelCtx()); }
  private async renderDocuments() { return (await import("./panels/documents")).renderDocuments(this.panelCtx()); }
  private async renderStandards() { return (await import("./panels/standards")).renderStandards(this.panelCtx()); }
  private async renderResponsibility() { return (await import("./panels/responsibility")).renderResponsibility(this.panelCtx()); }

  private async renderOperations() { return (await import("./panels/operations")).renderOperations(this.panelCtx()); }
  private async renderFca() { return (await import("./panels/operations")).renderFca(this.panelCtx()); }
  private async renderSpine() { return (await import("./panels/operations")).renderSpine(this.panelCtx()); }
  private async renderResilience() { return (await import("./panels/operations")).renderResilience(this.panelCtx()); }
  private async renderEnergy() { return (await import("./panels/operations")).renderEnergy(this.panelCtx()); }
  private async renderTurnover() { return (await import("./panels/operations")).renderTurnover(this.panelCtx()); }

  private async renderIds() { return (await import("./panels/standards")).renderIds(this.panelCtx()); }

  /** Reflect the persisted command-center density onto the portal root so `.dense …` CSS tightens
   *  the home dashboards. Harmless on other views (module tables carry no dash-cards). */
  private applyDensity() {
    this.root.classList.toggle("dense", readDensity() === "compact");
  }

  /**
   * Fetch the five pulse inputs and insert the rail, or do nothing at all.
   *
   * Every source is asked **in parallel and independently** — `allSettled`, not `all` — because the
   * whole point of a pulse is that it degrades. A project with no proforma still has a schedule; if
   * one rejection could blank the rail, the panel would be least useful exactly on the messy jobs
   * that need it most.
   *
   * The mapping from each engine's payload to `PulseInput` is the only place Pulse touches shapes it
   * does not own, so it is kept narrow and optional-chained throughout: a renamed field costs a
   * missing card, never a thrown home panel.
   */
  private async renderPulse(pid: string, root: HTMLElement) {
    try {
      const api = this.host.api as unknown as Record<string, (p: string) => Promise<unknown>>;
      const call = async (name: string) => {
        if (typeof api[name] !== "function") return null;
        try { return await api[name]!(pid); } catch { return null; }
      };
      const [model, cost, sched, work, deal] = await Promise.all(
        ["modelHealth", "costSummary", "scheduleVariance", "workQueue", "proformaLive"].map(call));

      const n = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
      const g = (o: unknown, k: string): unknown => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined);

      const cards = buildPulse({
        model: model ? { score: n(g(model, "score")), issues: n(g(model, "issues")) } : null,
        cost: cost ? { variancePct: n(g(cost, "variance_pct")) } : null,
        schedule: sched ? { floatDays: n(g(sched, "float_days")) } : null,
        work: work ? {
          open: n(g(work, "count")) ?? (Array.isArray(g(work, "items")) ? (g(work, "items") as unknown[]).length : null),
          mine: n(g(work, "mine")),
          overdue: Array.isArray(g(work, "overdue")) ? (g(work, "overdue") as string[]).slice(0, 3) : null,
        } : null,
        deal: deal ? { irrPct: n(g(deal, "irr")) } : null,
      });

      const rail = pulseRailEl(cards);
      // The home panel may have been re-rendered while this was in flight — appending into a root
      // that is no longer on screen would leave a rail nobody can see and a duplicate on the next
      // pass. Check before touching the DOM.
      if (rail && root.isConnected) root.prepend(rail);
    } catch {
      /* a pulse that cannot be built is simply absent */
    }
  }

  private async renderHome() {
    this.root.innerHTML = "";
    const pid = this.host.projectId()!;
    const root = this.root;
    const el = (tag: string, cls = "") => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };

    // command-center density: a compact/comfortable toggle that tightens the multi-card dashboards.
    this.applyDensity();
    const densRow = el("div"); densRow.style.cssText = "display:flex;justify-content:flex-end;margin-bottom:4px";
    const densBtn = el("button", "tool-btn") as HTMLButtonElement;
    densBtn.style.cssText = "font-size:11px;padding:2px 8px";
    const paintDens = () => {
      const compact = readDensity() === "compact";
      densBtn.textContent = compact ? "⊟ Compact" : "⊞ Comfortable";
      densBtn.title = compact ? "Switch to comfortable spacing" : "Switch to a denser command center";
      densBtn.setAttribute("aria-pressed", String(compact));
    };
    densBtn.onclick = () => { setDensity(readDensity() === "compact" ? "comfortable" : "compact"); this.applyDensity(); paintDens(); };
    paintDens();
    densRow.append(densBtn);
    root.append(densRow);

    // PROJECT PULSE — five numbers, each with a sentence naming what is at risk. Appended before the
    // rest of the home panel so the state of the job is the first thing read, not the last.
    //
    // Deliberately fire-and-forget and fully fail-open: a summary must never be able to break the
    // page it summarises. If an engine is slow or missing, the rail simply does not appear — which
    // is also why `pulseRailEl` returns null for an empty pulse rather than an empty heading.
    void this.renderPulse(pid, root);

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
          row.onclick = () => { const m = this.mods.find((x) => x.key === h.module); if (m) void this.openRecord(m, h.id); };
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
          this.reg.sort[m.key] = a.config.sort as (typeof this.reg.sort)[string];
          await this.host.api.markViewSeen(pid, a.module, a.id).catch(() => {});
          void this.openModule(m, { q: a.config.q, state: a.config.state });
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
    // The design workspace (architect/engineer) gets a model-health + phase-progress command center.
    if (this.wsFilter === "design") { await this.renderDesignHome(root, pid, el, jump); return; }

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
      rpt.onclick = async () => {
        const { openPdfUrl, saveToDocuments } = await import("../drawings/openPdf");
        await openPdfUrl(this.host.api, this.host.api.url(`/projects/${pid}/report.pdf`), "status-report.pdf", { saveLabel: "Save to Documents", onSave: saveToDocuments(this.host.api, pid) });
      };
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
      const cards = order.map((k) => pool[k]).filter((c): c is NonNullable<typeof c> => Boolean(c));
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
          // R26-ONE-HEALTH: the score is a MEAN and the band is WORST-OF, so a high score can carry a
          // red band. Naming the domain that governs turns "88/100 · RED" from an apparent
          // self-contradiction into the one sentence a PM actually needs.
          + (h.governing_domain
              ? `<div class="meta">${esc(h.governing_domain)} sets the band · score is the mean of `
                + `${h.domains.length} domains</div>`
              : `<div class="meta">all ${h.domains.length} domains clear</div>`)
          + `<div class="meta">${h.open_items_total} open · ${h.overdue_items_total} overdue</div></div></div>`
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
          row.innerHTML = `<span class="ic">→</span> ${esc(a.ref)} ${esc(a.title ?? "")} ${statusChip(a.state)}`;
          row.onclick = () => { const m = this.mods.find((x) => x.key === a.module); if (m) void this.openRecord(m, a.id); };
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
          row.onclick = () => { const m = this.mods.find((mm) => mm.key === x.module); if (m) void this.openRecord(m, x.id); };
          main.appendChild(row);
        };
        for (const x of due.overdue.slice(0, 10)) rowFor(x, true);
        for (const x of due.due_soon.slice(0, 6)) rowFor(x, false);
      }).catch(() => {});

      // MAIN — escalation status (WFE-2): overdue items that have crossed an escalation rung, with a
      // one-click "escalate & notify" action (admin-gated server-side; a 403 surfaces as a toast).
      void this.host.api.escalationsScan(pid).then((escd) => {
        if (!escd.pending) return;
        const summary = [3, 2, 1].filter((l) => escd.by_level[l]).map((l) => `L${l}×${escd.by_level[l]}`).join(" · ");
        main.appendChild(Object.assign(el("div", "section-title"),
          { textContent: `▲ Escalations — ${escd.pending} past threshold (${summary})` }));
        for (const x of escd.items.filter((i) => i.needs_escalation).slice(0, 8)) {
          const row = el("button", "portal-mod") as HTMLButtonElement;
          row.innerHTML = `<span class="ic">${x.icon ?? "•"}</span> <b>${esc(x.ref)}</b> ${esc(x.title ?? "")} `
            + `<span class="badge rfi">L${x.level} · ${x.days_overdue}d late</span>`
            + (x.court ? ` <span class="notif-meta">→ ${esc(x.court)}</span>` : "");
          row.onclick = () => { const m = this.mods.find((mm) => mm.key === x.module); if (m) void this.openRecord(m, x.id); };
          main.appendChild(row);
        }
        const runBtn = el("button", "portal-mod notif") as HTMLButtonElement;
        runBtn.innerHTML = `<span class="ic">▲</span> Escalate &amp; notify the ball-in-court party`;
        runBtn.onclick = async () => {
          runBtn.disabled = true;
          try {
            const r = await this.host.api.escalationsRun(pid);
            toast(`escalated ${r.escalated} item(s) — the responsible party has been notified`, "success");
            void this.renderHome();
          } catch (e) {
            toast(`couldn't escalate: ${(e as Error).message}`, "error");
            runBtn.disabled = false;
          }
        };
        main.appendChild(runBtn);
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
          row.onclick = () => { const m = this.mods.find((x) => x.key === n.module); if (m) void this.openRecord(m, n.record_id); };
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
        a.onclick = (e) => { e.preventDefault(); const m = this.mods.find((x) => x.key === (cc.expired[0] ?? cc.expiring[0])?.module); if (m) void this.openModule(m); };
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
  // Favorites / recents / per-persona section defaults live in ./prefs (T3) — shared by buildNav
  // and the module catalog, so both read the same localStorage-backed source of truth.
  private refreshCatalog() {
    if (!this.catalogEl) return;
    const next = this.renderModuleCatalog();
    this.catalogEl.replaceWith(next); this.catalogEl = next;
  }

  private renderModuleCatalog(): HTMLElement {
    const wrap = document.createElement("div");
    const favs = readFavs();
    const persona = document.body.dataset.persona || localStorage.getItem("persona") || "all";
    const openSecs = SECTIONS_BY_PERSONA[persona];   // undefined => all sections open

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
      star.onclick = (e) => { e.stopPropagation(); toggleFav(m.key); this.refreshCatalog(); };
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
    const saved = localStorage.getItem(`portal-open:${key}`);
    const open0 = saved == null ? openDefault : saved === "1";
    const g = el("section", { class: "tool-group" });
    g.classList.toggle("open", open0);
    const head = el("button", { type: "button", class: "tool-group-head" });
    head.setAttribute("aria-expanded", String(open0));
    head.innerHTML = `<span class="chev">▸</span><span class="t">${title}</span><span class="cnt">${buttons.length}</span>`;
    const body = el("div", { class: "tool-group-body" }, buttons);
    head.onclick = () => { const o = !g.classList.contains("open"); g.classList.toggle("open", o); head.setAttribute("aria-expanded", String(o)); localStorage.setItem(`portal-open:${key}`, o ? "1" : "0"); };
    g.append(head, body);
    return g;
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
      tbl.innerHTML = `<thead><tr><th scope="col">Project</th><th scope="col">Status</th><th scope="col" style="text-align:right">CPI</th><th scope="col" style="text-align:right">SPI</th>`
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
          + `<td style="text-align:right;color:${p.cpi == null ? "var(--muted)" : p.cpi >= 0.95 ? "var(--status-good)" : "var(--status-crit)"}">${p.cpi ?? "—"}</td>`
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
      // prioritization matrix — projects ranked 0-100 on return / budget / schedule / risk
      void this.host.api.portfolioPrioritization().then((pr) => {
        if (!pr.projects.length) return;
        const pc = document.createElement("div"); pc.className = "dash-card"; pc.style.marginTop = "10px";
        const bar = (v: number) => { const col = v >= 70 ? "var(--status-good)" : v >= 45 ? "var(--status-warn)" : "var(--status-crit)"; return `<span style="display:inline-block;min-width:34px;text-align:right;color:${col};font-variant-numeric:tabular-nums">${v}</span>`; };
        const pt = document.createElement("table"); pt.className = "portal-table"; pt.style.fontSize = "11px";
        pt.innerHTML = `<thead><tr><th scope="col">#</th><th scope="col">Project</th><th scope="col" style="text-align:right">Score</th>`
          + `<th scope="col" style="text-align:right">Return</th><th scope="col" style="text-align:right">Budget</th>`
          + `<th scope="col" style="text-align:right">Schedule</th><th scope="col" style="text-align:right">Risk</th></tr></thead>`;
        const pb = document.createElement("tbody");
        for (const p of pr.projects) {
          const tr = document.createElement("tr"); tr.className = "kpi-click";
          tr.innerHTML = `<td>${p.rank}</td><td>${esc(p.name)}</td>`
            + `<td style="text-align:right;font-weight:700">${bar(p.composite)}</td>`
            + `<td style="text-align:right">${bar(p.scores.return)}</td><td style="text-align:right">${bar(p.scores.budget)}</td>`
            + `<td style="text-align:right">${bar(p.scores.schedule)}</td><td style="text-align:right">${bar(p.scores.risk)}</td>`;
          tr.onclick = () => { if (p.id !== here) window.location.search = `?project=${p.id}`; };
          pb.appendChild(tr);
        }
        pt.appendChild(pb);
        pc.innerHTML = `<b>Prioritization matrix</b> <span class="meta">weighted 0–100 · return ${Math.round(pr.weights.return * 100)}% / budget ${Math.round(pr.weights.budget * 100)}% / schedule ${Math.round(pr.weights.schedule * 100)}% / risk ${Math.round(pr.weights.risk * 100)}%</span>`;
        pc.appendChild(pt);
        this.root.appendChild(pc);
      }).catch(() => { /* prioritization is best-effort */ });
    }).catch(() => { status.className = "empty-state"; status.innerHTML = `Portfolio unavailable<span class="es-hint">Needs at least one project with schedule/budget data.</span>`; });
  }

  private async renderBudget() { return (await import("./panels/budget")).renderBudget(this.panelCtx()); }

  private async renderScheduleViews(m: ModuleDef) { return (await import("./panels/schedule")).renderScheduleViews(this.panelCtx(), m); }

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

  private bar(title: string, back: () => void): HTMLElement {
    const bar = document.createElement("div"); bar.className = "portal-bar";
    const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = "←";
    b.onclick = back;
    const t = document.createElement("strong"); t.textContent = title;
    bar.append(b, t);
    return bar;
  }
}
