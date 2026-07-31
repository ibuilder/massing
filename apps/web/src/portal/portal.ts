import type { ApiClient, ModuleDef, ModuleRecord, RecordBrief } from "../api/client";
import { escapeHtml as esc, toast } from "../ui/feedback";
import { progressBar } from "../ui/charts";
import { countNarrative, statusChip } from "../ui/chips";
import { confirmModal, modalShell, promptModal } from "../ui/modal";
import { noProjectHtml } from "../ui/empty";
import { emptyHint } from "../ui/emptyGuide";
import { allQueued, dequeue, enqueueUpload, queuedCountForRecord } from "./offlineQueue";
import { buildPulse, pulseRailEl } from "./panels/pulse";
import type { PanelContext } from "./panelContext";
import { SECTIONS_BY_PERSONA, pushRecent, readDensity, readFavs, readRecents, readRoomOpen, setDensity, setRoomOpen, toggleFav } from "./prefs";
import { el } from "../ui/dom";
import { ALL_DESTS, type Dest, stagesFor } from "../shell/destinations";
import { FALLBACK_ROOMS, type SpineState, destRoom, loadSpine, orderRooms, preselectedRoom, unroomedDests } from "../shell/spine";
import type { ModuleFilterOp, RoomDef } from "../api/types";
// PANEL-LAZY (PERF): the ~30 secondary portal panels are DYNAMICALLY imported at first render
// (see the wrapper methods below), not eagerly bundled into the app shell — each panel file (and
// its heavy deps: charts, tables, module-graph, etc.) becomes its own chunk fetched only when the
// user opens that destination. This was the single biggest eager-bundle cut. Panel modules are
// grouped per source file so one dynamic import covers all its exports (Vite dedupes the chunk).

/**
 * How many records of a referenced module are fetched to build the id→label map for a table.
 *
 * A bound is necessary — a reference column must not pull an unbounded register to render one page —
 * but the bound is also a correctness boundary, so it is named rather than buried as a literal. Past
 * this many records the tail of the target module is genuinely unresolvable from the client, and
 * `refCell` is required to SAY so instead of inventing a label. See MOD-SWEEP below.
 */
const REF_RESOLVE_LIMIT = 500;

/** A record id is a `uuid.uuid4()` string server-side, so this distinguishes an id from free text. */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * MOD-FILTER — everything currently narrowing a register view.
 *
 * `q` and `state` were the whole vocabulary; `fields` is the per-field half. It is threaded through
 * `openModule` rather than held on the instance so that every re-render — a saved view, a page step,
 * an inline edit — either passes the filters on deliberately or drops them visibly. A filter
 * surviving in hidden state while the controls show something else is the worst of both.
 */
/**
 * MOD-PERCENT — the field types that hold a MAGNITUDE, named once.
 *
 * The form layer asked `f.type === "number" || f.type === "currency"` in three separate places, and
 * `percent` was in none of them. That was survivable while two fields in the whole system were typed
 * `percent`; the field sweep converted 21 more across 16 registers — every retainage, fee, overhead
 * and contingency percentage — and each of the three sites failed differently and quietly:
 *
 * 1. `EDITABLE` omitted it, so those fields stopped being inline-editable. A capability removed with
 *    no error and no visible cause.
 * 2. The record form rendered `<input type="text">` — no numeric keyboard on a phone, no step, no
 *    browser validation.
 * 3. The save path skipped `Number(v)`, storing the STRING "5". `validate_record` calls `float(value)`
 *    so it passes, and every consumer coerces, so nothing ever failed — the column just accumulated a
 *    mixture of `5` and `"5"` depending on which form last touched the record. That is the worst of
 *    the three precisely because it never surfaces.
 *
 * One list, referenced three times, so adding the next numeric type is one edit rather than three
 * that can be done two-thirds of the way. `test_module_fields.py` could not have caught any of this:
 * it reads config shape and says nothing about whether the UI can render it.
 */
export const NUMERIC_FIELD_TYPES = ["number", "currency", "percent"] as const;
const isNumericField = (t: string) => (NUMERIC_FIELD_TYPES as readonly string[]).includes(t);

/**
 * Field types the table can edit IN PLACE. Hoisted out of the row loop and exported so a test can
 * compare it against the types the shipped modules actually declare — the check that would have
 * caught `percent` missing here, and the one that catches the NEXT type rather than this one.
 *
 * A type absent from both this list and `READ_ONLY_FIELD_TYPES` is a type the form silently cannot
 * handle, which is exactly how `percent` went unnoticed: nothing errored, a capability just stopped
 * existing for 21 fields.
 */
export const EDITABLE_FIELD_TYPES = [
  "text", "textarea", ...NUMERIC_FIELD_TYPES, "date", "select", "checkbox", "email", "phone",
] as const;

/** Types deliberately NOT inline-editable, each for a stated reason — so "not editable" is a
 *  decision on the record rather than an omission nobody noticed. */
export const READ_ONLY_FIELD_TYPES = [
  "rollup",      // computed from other records; editing it would be editing a derived value
  "signature",   // captured through the signing flow, which carries the attestation
  "file",        // needs an upload control, not a cell
  "reference",   // edited through the record picker (`inlineRefCell`), not as free text
  "multiselect", // needs a multi-choice control a table cell has no room for
  // MOD-TABLE. A line-item grid has no cell-sized inline editor: its value is an array of objects,
  // and a register cell shows the summary ("3 lines · $118,260") instead. Edited in the record form
  // via `tableEditor`, which is where a grid has room to exist.
  //
  // This entry is the gate working as designed. `fieldTypeCoverage.test.ts` was written one PR ago to
  // catch a type added to `FIELD_TYPES` without a renderer classification — and the very next PR to
  // add a type was this one. It failed until the type was classified, which is exactly the outcome
  // that was wanted: the cost of a new type is one deliberate line saying how it renders.
  "table",
] as const;

interface RegisterFilter {
  q?: string;
  state?: string;
  offset?: number;
  /** field name -> {op, value}. Sent as `f.<field>[.<op>]`; the server 400s on an unknown field. */
  fields?: Record<string, { op: ModuleFilterOp; value: string }>;
}

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
  /** R26 spine allocation, loaded only when the flag is on. Null = render the classic stage rail. */
  private spine: SpineState | null = null;
  private activeKey: string | null = null;
  // R2 — workspace split: this portal serves the "construction" (GC build), "developer"
  // (real-estate), or "design" (architect/engineer) module set. `showAll` is the escape hatch so
  // every role can still reach every register (the user's "everyone has access to all data, just a
  // few more clicks").
  private wsFilter: "construction" | "developer" | "design" = "construction";
  private showAll = false;
  /** Which workspace this portal renders. Call before init(). */
  setWorkspace(ws: "construction" | "developer" | "design") { this.wsFilter = ws; }
  /** A module's workspace membership as a list — supports "|"-separated multi-membership. */
  private wsOf(m: ModuleDef): string[] { return (m.workspace || "construction").split("|"); }
  /** True when a module belongs in the active workspace (or Show-all is on). */
  private inWs(m: ModuleDef) { return this.showAll || this.wsOf(m).includes(this.wsFilter); }
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
      openModule: (m, f) => self.openModule(m, f),
      navigate: (k) => self.goToDest(k),
    };
  }

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
    this.hookOnline(); void this.flushUploads();
    await this.renderHome();
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
    const home = preselectedRoom(this.wsFilter);
    for (const room of orderRooms(rooms, this.wsFilter)) {
      const det = document.createElement("details"); det.className = "pnav-stage-group pnav-room";
      det.dataset.room = room.id;
      const skey = `${this.wsFilter}:${room.id}`;
      const items = byRoom.get(room.id) ?? [];
      // Only the workspace's own room opens by default. Five rooms expanded is 45 destinations on
      // screen at once — the same wall the spine exists to replace. The other four are one click
      // away and stay wherever the user last put them.
      const said = readRoomOpen(skey);
      det.open = items.some((d) => d.key === this.activeKey) || (said ?? room.id === home);
      det.ontoggle = () => setRoomOpen(skey, det.open);
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
      setTimeout(() => (document.querySelector('.rail-btn[data-rail="tools"]') as HTMLElement | null)?.click(), 60); };
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
          this.sort[m.key] = a.config.sort as (typeof this.sort)[string];
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

  // --- record list (sortable / filterable data table + bulk actions) ---------
  private sort: Record<string, { col: string; dir: 1 | -1 } | undefined> = {};
  // per-module inline-edit toggle: when on, data cells become autosaving inputs (bulk data entry)
  private editInline: Record<string, boolean> = {};

  /** An inline-editable table cell that autosaves the field on change/blur (no form round-trip).
   *  Used only in inline-edit mode; reference/multiselect/other types stay read-only for now. */
  private inlineCell(pid: string, m: ModuleDef, r: ModuleRecord, c: ModuleDef["fields"][number]): HTMLTableCellElement {
    const td = document.createElement("td");
    td.onclick = (e) => e.stopPropagation();          // editing a cell must not open the record
    const save = async (v: unknown) => {
      try { await this.host.api.updateModuleRecord(pid, m.key, r.id, { [c.name]: v }); r.data[c.name] = v; td.classList.add("saved"); setTimeout(() => td.classList.remove("saved"), 700); }
      catch (e) { toast(`Couldn't save ${c.label}: ${(e as Error).message}`, "error"); }
    };
    if (c.type === "select") {
      const sel = document.createElement("select"); sel.className = "cell-input";
      const blank = document.createElement("option"); blank.value = ""; blank.textContent = "—"; sel.append(blank);
      for (const o of (c.options ?? [])) { const op = document.createElement("option"); op.value = op.textContent = o; sel.append(op); }
      sel.value = (r.data[c.name] as string) ?? "";
      sel.onchange = () => void save(sel.value);
      td.append(sel);
    } else if (c.type === "checkbox") {
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = !!r.data[c.name];
      cb.onchange = () => void save(cb.checked);
      td.append(cb);
    } else {
      const inp = document.createElement("input"); inp.className = "cell-input";
      inp.type = (c.type === "number" || c.type === "currency") ? "number" : c.type === "date" ? "date" : "text";
      inp.value = r.data[c.name] == null ? "" : String(r.data[c.name]);
      let orig = inp.value;
      inp.onblur = () => {
        if (inp.value === orig) return;
        orig = inp.value;
        const num = c.type === "number" || c.type === "currency";
        void save(inp.value === "" ? "" : num ? Number(inp.value) : inp.value);
      };
      inp.onkeydown = (e) => { if (e.key === "Enter") inp.blur(); };
      td.append(inp);
    }
    return td;
  }

  /** Inline reference picker for edit mode — set/change which record a reference field points at,
   *  straight in the grid. Options come from the reference column's pre-fetched map (no extra fetch);
   *  each reads as "ref · title". Saves the linked record's id; a current value outside the fetched
   *  window (>500) is preserved as its own option so toggling edit mode never drops a link. */
  private inlineRefCell(pid: string, m: ModuleDef, r: ModuleRecord, c: ModuleDef["fields"][number],
                        map: Map<string, { ref: string; title: string | null }> | undefined): HTMLTableCellElement {
    const td = document.createElement("td");
    td.onclick = (e) => e.stopPropagation();
    const sel = document.createElement("select"); sel.className = "cell-input";
    const blank = document.createElement("option"); blank.value = ""; blank.textContent = "—"; sel.append(blank);
    const entries = map ? [...map.entries()].sort((a, b) => a[1].ref.localeCompare(b[1].ref)) : [];
    for (const [id, info] of entries) {
      const op = document.createElement("option"); op.value = id;
      op.textContent = info.title ? `${info.ref} · ${info.title}` : info.ref;
      sel.append(op);
    }
    const cur = r.data[c.name] == null ? "" : String(r.data[c.name]);
    if (cur && !map?.has(cur)) { const op = document.createElement("option"); op.value = cur; op.textContent = cur.slice(0, 8); sel.append(op); }
    sel.value = cur;
    sel.onchange = async () => {
      try { await this.host.api.updateModuleRecord(pid, m.key, r.id, { [c.name]: sel.value }); r.data[c.name] = sel.value; td.classList.add("saved"); setTimeout(() => td.classList.remove("saved"), 700); }
      catch (e) { toast(`Couldn't link ${c.label}: ${(e as Error).message}`, "error"); }
    };
    td.append(sel);
    return td;
  }

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

  private async openModule(m: ModuleDef, filter: RegisterFilter = {}) {
    const pid = this.host.projectId()!;
    pushRecent(m.key);
    this.skeleton(`Loading ${m.name}…`);
    const PAGE = 100, offset = filter.offset ?? 0;          // page large modules so they never render 1000s of rows
    // MOD-FILTER — per-field filters and the sort go to the SERVER, so both apply to the whole
    // register rather than to the hundred rows that happen to be on this page.
    const sortState = this.sort[m.key];
    const sortField = sortState ? this.serverSortField(m, sortState.col) : null;
    // A range puts TWO clauses on one field (`amount.gte` and `amount.lte`). The controls key
    // themselves `<field>__<op>` so both can coexist in the state map; the suffix is stripped here,
    // into a LIST, which is the shape that can actually carry both. Flattening to a field-keyed map
    // instead would drop one clause and turn a range into a single bound — a narrower result that
    // looks entirely correct on screen.
    const wireFilters = Object.entries(filter.fields ?? {}).map(([k, v]) => ({
      field: k.includes("__") ? k.slice(0, k.lastIndexOf("__")) : k, op: v.op, value: v.value,
    }));
    const page = await this.host.api.moduleRecordsFiltered(pid, m.key, {
      q: filter.q, state: filter.state, limit: PAGE + 1, offset,
      filters: wireFilters,
      ...(sortField ? { sort: sortField, sortDir: sortState!.dir === -1 ? "desc" : "asc" } : {}),
    });
    const hasMore = page.length > PAGE;
    const records = hasMore ? page.slice(0, PAGE) : page;
    const editing = !!this.editInline[m.key];              // inline-edit mode: data cells become inputs
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
    fbox.onkeydown = (e) => { if (e.key === "Enter") void this.openModule(m, { ...filter, q: fbox.value || undefined }); };
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
    viewSel.onchange = () => { const v = views.find((x) => x.id === viewSel.value); if (v) { this.sort[m.key] = v.config.sort; void this.host.api.markViewSeen(pid, m.key, v.id).catch(() => {}); void this.openModule(m, { q: v.config.q, state: v.config.state }); } };
    const saveView = document.createElement("button"); saveView.className = "tool-btn"; saveView.textContent = "＋view";
    saveView.title = "Save current filter/sort as a view (synced to your account)";
    saveView.onclick = async () => {
      const v = await promptModal("Save view", [{ name: "name", label: "View name", required: true }], "Save");
      if (!v) return;
      await this.host.api.saveView(pid, m.key, v.name ?? "", { q: filter.q, state: filter.state, sort: this.sort[m.key] });
      void this.openModule(m, filter);
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
        pick = v.pick ?? "";
      } else {
        toast(`No ${m.name} templates yet — saving the current records as one.`, "info");
      }
      if (pick && pick.trim()) {
        const t = tpls[parseInt(pick) - 1];
        if (!t) return;
        const r = await this.host.api.applyTemplate(pid, m.key, t.id);
        this.host.setStatus(`applied "${r.applied}" — ${r.created} record(s)`);
        void this.openModule(m, filter);
      } else {
        const nv = await promptModal("Save template",
          [{ name: "name", label: "Template name", required: true }], "Save");
        if (!nv) return;
        try { const s = await this.host.api.saveTemplate(pid, m.key, nv.name ?? ""); this.host.setStatus(`saved template (${s.item_count} items)`); }
        catch (e) { this.host.setStatus(`couldn't save: ${(e as Error).message}`); }
      }
    };
    // generic Excel/CSV import (any module): pick a file -> map columns -> preview -> import
    const impBtn = document.createElement("button"); impBtn.className = "tool-btn"; impBtn.dataset.cap = "review";
    impBtn.textContent = "⤓ Import"; impBtn.title = "Import records from an Excel (.xlsx) or CSV file with column mapping";
    const impFile = document.createElement("input"); impFile.type = "file"; impFile.accept = ".xlsx,.xlsm,.csv"; impFile.style.display = "none";
    impFile.onchange = () => { const f = impFile.files?.[0]; if (f) void this.renderImport(m, f); impFile.value = ""; };
    impBtn.onclick = () => impFile.click();
    // paste-from-spreadsheet — Ctrl-V a block of Excel/Sheets cells to bulk-add without a file
    const pasteBtn = document.createElement("button"); pasteBtn.className = "tool-btn"; pasteBtn.dataset.cap = "review";
    pasteBtn.textContent = "⎘ Paste"; pasteBtn.title = "Paste rows copied from Excel or Google Sheets to bulk-add records";
    pasteBtn.onclick = () => this.pasteRows(m);
    // inline-edit toggle — turn the data cells into autosaving inputs for fast multi-record entry
    const editBtn = document.createElement("button"); editBtn.className = "tool-btn"; editBtn.dataset.cap = "editor";
    editBtn.textContent = editing ? "✓ Editing (done)" : "✎ Edit inline";
    if (editing) editBtn.classList.add("on");
    editBtn.title = "Edit cells directly in the table — type across many records; changes save automatically";
    editBtn.onclick = () => { this.editInline[m.key] = !editing; void this.openModule(m, filter); };
    // column chooser — pick which fields show as columns in wide modules (personal, persisted)
    const colBtn = document.createElement("button"); colBtn.className = "tool-btn";
    colBtn.textContent = "⚙ Columns"; colBtn.title = "Choose which fields show as columns";
    if (this.readColPrefs(m.key)) colBtn.classList.add("on");   // signal a non-default column set is active
    colBtn.onclick = () => this.columnPicker(m, colNames, filter);
    actions.append(newBtn, boardBtn, csvBtn, impBtn, impFile, pasteBtn, editBtn, tplBtn, colBtn, fbox, stateSel, viewSel, saveView);
    // R30-TOOLS — the tools this register declares, rendered from `module.json` rather than hardcoded.
    //
    // The audit's finding was that every optional key a module could carry was presentation — icon,
    // columns, pinnable — and none said what the register could *do*. So a register rendered as a
    // table, a form and a status chip, which is exactly a paper form, while `bid_leveling.py`,
    // `schedule_cpm.py` and `fca.py` sat one unlinked screen away. `tools[]` is that link, and the
    // hardcoded `schedule_activity` "Views" button that used to live here is the reason it is
    // declarative now: one register got a door because someone remembered to write the branch.
    //
    // An unknown dest renders nothing rather than a dead button — `goToDest` no-ops on a key it does
    // not know, and a button that silently does nothing is worse than an absent one.
    const dispatch = this.destDispatch();          // built once, not once per declared tool
    for (const t of m.tools ?? []) {
      if ((t.scope ?? "register") !== "register") continue;   // record-scoped tools render on the record
      if (!dispatch[t.dest]) continue;
      const tb = document.createElement("button"); tb.className = "tool-btn"; tb.dataset.dest = t.dest;
      tb.textContent = `⚙ ${t.label}`;
      tb.title = `Open ${t.label} — the tool that works on these ${m.name.toLowerCase()}`;
      tb.onclick = () => this.goToDest(t.dest);
      actions.append(tb);
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
          this.host.setStatus(`imported ${r.count} BCF issue${r.count === 1 ? "" : "s"}`); void this.openModule(m); }
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
    this.root.appendChild(this.filterRow(m, filter));

    if (!records.length) {
      // R24-EMPTY-GUIDE ② — an empty register says where its rows come from. "Use + New" restates a
      // button three inches away; what the user cannot see is that an RFI is asked against a drawing
      // and a submittal is driven by a spec section. Curated per module, generic where it is not —
      // an invented upstream would be a confident wrong answer somewhere nobody can check it.
      const e = document.createElement("div"); e.className = "empty-state";
      if (filter.q || filter.state) {
        e.innerHTML = `No matching records<span class="es-hint">Try clearing the filter or state.</span>`;
      } else {
        // textContent for the module name: it is server-supplied and this is an innerHTML sink.
        e.textContent = `No ${m.name.toLowerCase()} yet`;
        const hint = document.createElement("span");
        hint.className = "es-hint";
        hint.textContent = emptyHint(m.key);
        e.appendChild(hint);
      }
      this.root.appendChild(e);
      return;
    }

    // columns: a saved per-user choice (⚙ Columns) wins; else module.json list_columns, else first 2
    // input fields. Ref/Title/Assignee/Ball/Status always frame the row regardless.
    const inputFields = m.fields.filter((f) => f.type !== "rollup" && f.type !== "signature");
    const defaultColNames = (m.list_columns ?? inputFields.slice(0, 2).map((f) => f.name));
    const colNames = this.readColPrefs(m.key) ?? defaultColNames;
    // O(1) field lookup by name (was O(colNames × fields) via .find per column) — REL-4 hotspot fix
    const fieldByName = new Map(m.fields.map((f) => [f.name, f]));
    const cols = colNames
      .map((name) => fieldByName.get(name)).filter(Boolean) as ModuleDef["fields"];

    // sort
    const sort = this.sort[m.key];
    const val = (r: ModuleRecord, col: string) => col === "ref" ? r.ref : col === "status" ? r.workflow_state
      : col === "assignee" ? (r.assignee ?? "") : col === "title" ? (r.title ?? "") : (r.data[col] ?? "");
    // Type-aware comparator: numeric fields compare as numbers ("10" after "9", not before), blanks
    // group at the end regardless of direction. `5 < ""` and `5 > ""` are both false, so the old raw
    // </>` compare scattered blank-valued rows randomly through a numeric sort.
    const cmp = (x: unknown, y: unknown): number => {
      const xe = x === "" || x == null, ye = y === "" || y == null;
      if (xe || ye) return xe && ye ? 0 : xe ? 1 : -1;             // blanks last (direction-independent)
      const xn = Number(x), yn = Number(y);
      if (Number.isFinite(xn) && Number.isFinite(yn)) return xn - yn;
      return String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: "base" });
    };
    // MOD-FILTER — the server sorted the whole register, so re-sorting here would be a no-op at best.
    //
    // This comparator is correct and stays, but only for a column the server cannot order (see
    // `serverSortField`). The distinction matters: sorting in the browser orders **the fetched page**,
    // so "sort by amount" on a 500-row register ordered 200 rows and presented the top of that as the
    // largest values in the register. Nothing was wrong on screen; it was the wrong 200 rows.
    if (sort && !this.serverSortField(m, sort.col)) records.sort((a, b) => {
      const x = val(a, sort.col), y = val(b, sort.col);
      const xe = x === "" || x == null, ye = y === "" || y == null;
      if (xe || ye) return xe && ye ? 0 : xe ? 1 : -1;             // blanks stay last even when descending
      return cmp(x, y) * sort.dir;
    });

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
        void this.openModule(m, filter);
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
    delBtn.onclick = async () => { if (await confirmModal(`Delete ${selected.size} record(s)? This cannot be undone.`, "", "Delete", true)) void runBulk("delete", "Deleted"); };
    bulkBar.append(asgIn, asgBtn, delBtn);
    this.root.appendChild(bulkBar);

    const rowCbs: HTMLInputElement[] = [];
    const table = document.createElement("table"); table.className = "portal-table";
    const headRow = document.createElement("tr");
    const selAllTh = document.createElement("th");      // select-all (builders act in batches)
    const selAll = document.createElement("input"); selAll.type = "checkbox"; selAll.title = "Select all";
    selAll.onclick = (e) => {
      e.stopPropagation();
      for (const r of records) { if (selAll.checked) selected.add(r.id); else selected.delete(r.id); }
      for (const cb of rowCbs) cb.checked = selAll.checked;
      syncBulk();
    };
    selAllTh.appendChild(selAll); headRow.appendChild(selAllTh);
    const th = (label: string, col: string) => {
      const h = document.createElement("th"); h.textContent = label + (sort?.col === col ? (sort.dir === 1 ? " ▲" : " ▼") : "");
      h.style.cursor = "pointer";
      h.onclick = () => { const cur = this.sort[m.key]; this.sort[m.key] = { col, dir: cur?.col === col && cur.dir === 1 ? -1 : 1 }; void this.openModule(m, filter); };
      headRow.appendChild(h);
    };
    th("Ref", "ref"); th("Title", "title");
    for (const c of cols) th(c.label, c.name);
    th("Assignee", "assignee"); th("Ball", ""); th("Status", "status");
    const thead = document.createElement("thead"); thead.appendChild(headRow); table.appendChild(thead);

    // Relational cells: resolve each reference column's ids → {ref,title} once (one fetch per
    // referenced module, not per cell), so a reference reads as the linked record and navigates on
    // click instead of showing a raw id.
    //
    // The fetch is BOUNDED, and that bound is the reason `refCell` exists rather than an inline
    // fallback: past 500 records of the target module the tail is simply not in the map, and the old
    // code rendered any unresolved value as a link labelled `String(v).slice(0, 8)`. On a project with
    // 600 companies, company #550 therefore drew a clickable link showing eight characters of its own
    // id, opening nothing — a control that looks resolved and is not. See `refCell`.
    const refCols = cols.filter((c) => c.type === "reference" && c.module);
    const refMaps: Record<string, Map<string, { ref: string; title: string | null }>> = {};
    if (refCols.length) {
      await Promise.all(refCols.map(async (c) => {
        try {
          const recs = await this.host.api.moduleRecordsFiltered(pid, c.module!, { limit: REF_RESOLVE_LIMIT });
          const map = new Map<string, { ref: string; title: string | null }>();
          for (const rr of recs) map.set(rr.id, { ref: rr.ref, title: rr.title });
          refMaps[c.name] = map;
        } catch { /* leave unresolved — refCell states so rather than faking a link */ }
      }));
    }

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
      // MOD-PERCENT: `percent` was absent from this list, so the 21 fields the sweep converted from
      // `number` stopped being inline-editable overnight — a capability removed with no error to
      // notice. Now module-scope and exported, so `fieldTypeCoverage.test.ts` can hold it against the
      // types the shipped modules actually declare.
      const EDITABLE = EDITABLE_FIELD_TYPES as readonly string[];
      for (const c of cols) {
        const v = r.data[c.name];
        if (editing && c.type === "reference" && c.module) {
          tr.appendChild(this.inlineRefCell(pid, m, r, c, refMaps[c.name]));
        } else if (editing && EDITABLE.includes(c.type)) {
          tr.appendChild(this.inlineCell(pid, m, r, c));
        } else if (c.type === "reference" && c.module && v) {
          tr.appendChild(this.refCell(String(v), c, refMaps[c.name]));
        } else {
          cell(this.fmtCell(c, v));
        }
      }
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
    if (!(await confirmModal(`Create a ${tgt.name} from ${r.ref}? It will be pre-filled and linked back to ${r.ref}.`, ""))) return;
    try {
      const data = c.map(r.data);
      if (c.back) data[c.back] = r.id;                 // back-reference field on the new record → this record
      for (const k of Object.keys(data)) if (data[k] === undefined || data[k] === "") delete data[k];
      const nv = await this.host.api.createModuleRecord(pid, c.to, { data });
      if (!c.back) await this.host.api.linkRecord(pid, m.key, r.id, c.to, nv.id);  // else use an explicit link
      toast(`Created ${nv.ref} from ${r.ref}`, "info");
      this.host.onPinsChanged();
      void this.openRecord(tgt, nv.id);
    } catch (e) { toast(`convert failed: ${(e as Error).message}`, "error"); }
  }

  /**
   * MOD-SWEEP — a reference cell that never pretends to have resolved.
   *
   * The old inline version rendered EVERY non-empty reference as a clickable link labelled
   * `String(v).slice(0, 8)`, falling back to those eight characters whenever the id was not in the
   * resolved map. Three different values took that path and all three looked identical to a working
   * link: a record deleted since it was referenced, a record past `REF_RESOLVE_LIMIT` in a large
   * register, and — the one that matters for the field sweep — a **legacy free-text value** in a field
   * that used to be `text`. Converting `coi.vendor` from text to reference would have turned
   * "Acme Electrical Inc" into a link reading `Acme Ele` that opens nothing.
   *
   * So the three cases are now distinguished, because they call for different things from the user:
   *
   * - **resolved** → the link, labelled `REF-001 · Title`, navigating on click.
   * - **an id we could not resolve** (UUID-shaped, absent from the map) → the short id, NOT a link,
   *   marked as unresolved. The record may be deleted or beyond the fetch bound; either way clicking
   *   is not the answer and offering it is a lie.
   * - **not an id at all** → the value verbatim, full length, marked as unlinked text. This is what a
   *   pre-conversion value looks like, and showing it whole is what lets someone re-link it by hand.
   *
   * Truncating to 8 characters was the specific harm in every case: it is short enough to look like an
   * id and long enough to look deliberate.
   */
  private refCell(
    v: string,
    c: ModuleDef["fields"][number],
    map: Map<string, { ref: string; title: string | null }> | undefined,
  ): HTMLElement {
    const td = document.createElement("td");
    const info = map?.get(v);
    const target = String(c.module ?? "record").replace(/_/g, " ");
    if (info) {
      const a = document.createElement("a"); a.href = "#"; a.className = "ref-link";
      a.textContent = info.title ? `${info.ref} · ${info.title}` : info.ref;
      a.title = `Open linked ${target} ${info.ref}`;
      a.onclick = (e) => { e.preventDefault(); e.stopPropagation(); this.openByBrief(c.module!, v); };
      td.appendChild(a);
      return td;
    }
    const span = document.createElement("span");
    if (UUID_RE.test(v)) {
      span.className = "ref-unresolved";
      span.textContent = `${v.slice(0, 8)}…`;
      span.title = `This ${target} could not be resolved — it may have been deleted, or lie beyond `
        + `the first ${REF_RESOLVE_LIMIT} records of ${target}. Not a working link.`;
    } else {
      span.className = "ref-unlinked";
      span.textContent = v;                        // in full: it is the only handle for re-linking
      span.title = `Plain text, not a link to a ${target} record. Edit the field to pick the `
        + `${target} it refers to.`;
    }
    td.appendChild(span);
    return td;
  }

  /**
   * MOD-FILTER — the per-field filter bar.
   *
   * One control per field, chosen by type, because the useful question differs by type and offering a
   * single text box for all of them is how you end up with a filter nobody uses:
   *
   * - **select / multiselect** → a dropdown of the declared options. The only exact-match control that
   *   cannot be mistyped, and the options are already in the schema.
   * - **date** → from / to, i.e. `gte` + `lte`. A single date is almost never the question; a range is.
   * - **number / currency / percent** → min / max, compared numerically by the server.
   * - **reference** → a dropdown of the target register's records, so you filter by the record rather
   *   than by remembering its id.
   * - **everything else** → `contains`, case-insensitive.
   *
   * Collapsed by default and summarised when active ("3 filters"), so a register does not open behind
   * a wall of controls, and an active filter can never be invisible — a page showing a subset while
   * looking unfiltered is indistinguishable from missing data.
   */
  private filterRow(m: ModuleDef, filter: RegisterFilter): HTMLElement {
    const active = filter.fields ?? {};
    const wrap = document.createElement("div"); wrap.className = "filter-row";
    const count = Object.keys(active).length;

    const toggle = document.createElement("button");
    toggle.className = "tool-btn" + (count ? " on" : "");
    toggle.textContent = count ? `⧧ ${count} filter${count === 1 ? "" : "s"}` : "⧧ Filter";
    toggle.title = "Filter this register by any field — applied by the server, so it narrows every "
      + "record, not just the page on screen";
    const body = document.createElement("div"); body.className = "filter-body";
    body.hidden = count === 0;                       // open when something is already filtered
    toggle.onclick = () => { body.hidden = !body.hidden; };
    wrap.append(toggle, body);

    const next: Record<string, { op: ModuleFilterOp; value: string }> = { ...active };
    const apply = () => {
      for (const k of Object.keys(next)) {
        const v = next[k]!;
        if (v.op !== "empty" && v.op !== "nonempty" && !v.value) delete next[k];
      }
      void this.openModule(m, { ...filter, offset: 0, fields: { ...next } });
    };
    const label = (f: ModuleDef["fields"][number], node: HTMLElement, suffix = "") => {
      const cell = document.createElement("label"); cell.className = "filter-cell";
      const t = document.createElement("span"); t.className = "meta";
      t.textContent = (f.label || f.name) + suffix;
      cell.append(t, node); body.appendChild(cell);
    };
    const setOn = (name: string, op: ModuleFilterOp, value: string) => {
      if (value) next[name] = { op, value }; else delete next[name];
      apply();
    };

    for (const f of this.filterableFields(m)) {
      if (f.type === "select" || f.type === "multiselect") {
        const s = document.createElement("select"); s.className = "sb-sel";
        const any = document.createElement("option"); any.value = ""; any.textContent = "any";
        s.appendChild(any);
        for (const o of f.options ?? []) {
          const opt = document.createElement("option"); opt.value = opt.textContent = o; s.appendChild(opt);
        }
        s.value = active[f.name]?.value ?? "";
        s.onchange = () => setOn(f.name, "eq", s.value);
        label(f, s);
      } else if (f.type === "date") {
        for (const [op, suffix] of [["gte", " from"], ["lte", " to"]] as const) {
          const i = document.createElement("input"); i.type = "date"; i.className = "portal-filter";
          const key = `${f.name}__${op}`;
          i.value = active[key]?.value ?? "";
          // A range needs two independent clauses on ONE field, so the second cannot overwrite the
          // first in a field-keyed map. The `__op` suffix keys them apart here and is stripped when
          // the request is built, which is why `fields` is keyed by control rather than by field.
          i.onchange = () => { if (i.value) next[key] = { op, value: i.value }; else delete next[key]; apply(); };
          label(f, i, suffix);
        }
      } else if (f.type === "number" || f.type === "currency" || f.type === "percent") {
        for (const [op, suffix] of [["gte", " min"], ["lte", " max"]] as const) {
          const i = document.createElement("input"); i.type = "number"; i.className = "portal-filter";
          const key = `${f.name}__${op}`;
          i.value = active[key]?.value ?? "";
          i.onchange = () => { if (i.value) next[key] = { op, value: i.value }; else delete next[key]; apply(); };
          // The declared `unit` would belong in this label ("Amount min ($/day)"), but `unit` arrives
          // with the field sweep on a separate branch. Deliberately not duplicated here: two branches
          // adding the same schema key is a merge conflict for a label suffix.
          label(f, i, suffix);
        }
      } else if (f.type === "reference" && f.module) {
        const s = document.createElement("select"); s.className = "sb-sel";
        const any = document.createElement("option"); any.value = ""; any.textContent = "any";
        s.appendChild(any);
        s.onchange = () => setOn(f.name, "eq", s.value);
        label(f, s);
        // populated lazily: a register with six reference columns would otherwise fire six fetches
        // before the user has expressed any interest in filtering at all
        toggle.addEventListener("click", () => {
          if (s.dataset.loaded) return;
          s.dataset.loaded = "1";
          void this.host.api.moduleRecordsFiltered(this.host.projectId()!, f.module!, { limit: 200 })
            .then((rs) => {
              for (const r of rs) {
                const o = document.createElement("option");
                o.value = r.id; o.textContent = r.title ? `${r.ref} · ${r.title}` : r.ref;
                s.appendChild(o);
              }
              s.value = active[f.name]?.value ?? "";
            }).catch(() => { /* leave it as "any" — a filter you cannot populate is not an error */ });
        }, { once: false });
      } else {
        const i = document.createElement("input"); i.type = "search"; i.className = "portal-filter";
        i.placeholder = "contains…";
        i.value = active[f.name]?.value ?? "";
        i.onchange = () => setOn(f.name, "contains", i.value);
        label(f, i);
      }
    }

    if (count) {
      const clear = document.createElement("button"); clear.className = "tool-btn";
      clear.textContent = "✕ Clear filters";
      clear.onclick = () => void this.openModule(m, { ...filter, offset: 0, fields: {} });
      body.appendChild(clear);
    }
    return wrap;
  }

  /**
   * MOD-FILTER — the server-side field name for a table column, or null if the server cannot sort it.
   *
   * The table shows four pseudo-columns that are not module fields: `ref` and `assignee` are real row
   * columns, `status` is the row's `workflow_state` under a friendlier heading, and `title` is whatever
   * the module nominated as its `title_field`. Mapping them here is what lets a header click order the
   * whole register instead of the fetched page. A column with no mapping falls back to the in-browser
   * comparator rather than sending a name the server would (correctly) reject with a 400.
   */
  private serverSortField(m: ModuleDef, col: string): string | null {
    if (col === "status") return "workflow_state";
    if (col === "title") return m.title_field ?? null;
    if (col === "ref" || col === "assignee") return col;
    return m.fields.some((f) => f.name === col && f.type !== "rollup" && f.type !== "signature")
      ? col : null;
  }

  /** Fields worth offering a filter control for — everything a value can be narrowed by. */
  private filterableFields(m: ModuleDef): ModuleDef["fields"] {
    return m.fields.filter((f) => !["rollup", "signature", "file", "textarea"].includes(f.type));
  }

  /**
   * MOD-TABLE — the line-item grid for a `table` field.
   *
   * The sweep found 22 places a LIST had been flattened into one textarea, and the deeper version of
   * the same gap: `sov` is one record *per line* with no parent document, and `estimate` is a single
   * `amount`. A schedule of values, a bid, an estimate and a daily manpower log are all line-item
   * documents; the config had no way to say so and the form had no way to draw one.
   *
   * **A legacy string is shown, not discarded.** Those 22 fields were textareas, so live records hold
   * prose where rows are now expected. It is rendered above the grid, verbatim and read-only, because
   * it is the only copy of that information — dropping it on first save would destroy data the config
   * change never intended to touch, and silently, since nothing else records what was there.
   */
  private tableEditor(
    f: ModuleDef["fields"][number],
    value: unknown,
    store: Record<string, Record<string, unknown>[]>,
  ): HTMLElement {
    const cols = f.columns ?? [];
    const wrap = document.createElement("div"); wrap.className = "tbl-field";

    if (typeof value === "string" && value.trim()) {
      const legacy = document.createElement("pre"); legacy.className = "tbl-legacy";
      legacy.textContent = value;
      legacy.title = "This field held free text before it became a line-item table. It is kept "
        + "verbatim until the lines are entered below — it is the only copy.";
      const note = document.createElement("div"); note.className = "meta";
      note.textContent = "Previous free-text entry (kept until itemised):";
      wrap.append(note, legacy);
    }

    const rows: Record<string, unknown>[] = Array.isArray(value)
      ? (value as Record<string, unknown>[]).map((r) => ({ ...r })) : [];
    store[f.name] = rows;

    const table = document.createElement("table"); table.className = "tbl-grid";
    const thead = document.createElement("thead"); const htr = document.createElement("tr");
    for (const c of cols) {
      const th = document.createElement("th");
      th.textContent = (c.label || c.name) + (c.unit ? ` (${c.unit})` : "");
      if (c.width) th.style.width = c.width;
      htr.appendChild(th);
    }
    htr.appendChild(document.createElement("th"));          // row-remove column
    thead.appendChild(htr); table.appendChild(thead);
    const tbody = document.createElement("tbody"); table.appendChild(tbody);

    const foot = document.createElement("div"); foot.className = "tbl-total";
    const isNum = (t: string) => t === "number" || t === "currency" || t === "percent";
    const retotal = () => {
      if (!f.total_column) return;
      const col = cols.find((c) => c.name === f.total_column);
      const sum = rows.reduce((n, r) => n + (Number(r[f.total_column!]) || 0), 0);
      // Currency is formatted as currency; a bare count is not dressed up as money.
      foot.textContent = `${cols.find((c) => c.name === f.total_column)?.label ?? f.total_column}: `
        + (col?.type === "currency"
          ? `$${sum.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
          : sum.toLocaleString(undefined, { maximumFractionDigits: 2 }))
        + (col?.unit ? ` ${col.unit}` : "");
    };

    const drawRow = (row: Record<string, unknown>) => {
      const tr = document.createElement("tr");
      for (const c of cols) {
        const td = document.createElement("td");
        let inp: HTMLInputElement | HTMLSelectElement;
        if (c.type === "select") {
          inp = document.createElement("select");
          const blank = document.createElement("option"); blank.value = ""; blank.textContent = "—";
          inp.appendChild(blank);
          for (const o of c.options ?? []) {
            const opt = document.createElement("option"); opt.value = opt.textContent = o;
            inp.appendChild(opt);
          }
        } else {
          inp = document.createElement("input");
          const i = inp as HTMLInputElement;
          i.type = c.type === "checkbox" ? "checkbox" : isNum(c.type) ? "number" : c.type === "date" ? "date" : "text";
          if (c.type === "currency" || c.type === "percent") i.step = "0.01";
        }
        inp.className = "tbl-cell";
        if (c.type === "checkbox") (inp as HTMLInputElement).checked = !!row[c.name];
        else inp.value = String(row[c.name] ?? "");
        inp.oninput = () => {
          // Numbers are stored as NUMBERS, not the input's string. Storing "5" here is what makes a
          // SQL comparison go lexicographic later ('9' >= 10 is true), and it is the same defect the
          // record form had for `percent` fields.
          row[c.name] = c.type === "checkbox" ? (inp as HTMLInputElement).checked
            : isNum(c.type) ? (inp.value === "" ? "" : Number(inp.value))
            : inp.value;
          retotal();
        };
        td.appendChild(inp); tr.appendChild(td);
      }
      const rm = document.createElement("td");
      const del = document.createElement("button"); del.type = "button"; del.className = "tbl-del";
      del.textContent = "✕"; del.title = "Remove this line";
      del.onclick = () => {
        const i = rows.indexOf(row);
        if (i >= 0) rows.splice(i, 1);
        tr.remove(); retotal();
      };
      rm.appendChild(del); tr.appendChild(rm);
      tbody.appendChild(tr);
    };

    for (const r of rows) drawRow(r);

    const add = document.createElement("button"); add.type = "button"; add.className = "tool-btn";
    add.textContent = "+ Add line";
    add.onclick = () => { const r: Record<string, unknown> = {}; rows.push(r); drawRow(r); retotal(); };

    wrap.append(table, add);
    if (f.total_column) { wrap.appendChild(foot); retotal(); }
    return wrap;
  }

  /** Format a field value for a compact table cell. */
  private fmtCell(f: ModuleDef["fields"][number], v: unknown): string {
    if (v == null || v === "") return "";
    if (f.type === "currency") return `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
    if (f.type === "percent") return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
    if (f.type === "multiselect" && Array.isArray(v)) return (v as string[]).join(", ");
    // MOD-TABLE: a cell has no room for a grid, so it carries the two facts worth scanning — how many
    // lines, and the total if the field declares one. `String(v)` on an array of objects renders
    // "[object Object]" per row, which is the kind of output that looks like a rendering bug and is
    // actually a missing branch. A legacy string still shows as text (see `tableEditor`).
    if (f.type === "table") {
      if (typeof v === "string") return v.slice(0, 40);
      if (!Array.isArray(v)) return "";
      const n = v.length;
      const label = `${n} line${n === 1 ? "" : "s"}`;
      if (!f.total_column || !n) return label;
      const col = f.columns?.find((c) => c.name === f.total_column);
      const sum = (v as Record<string, unknown>[]).reduce((t, r) => t + (Number(r[f.total_column!]) || 0), 0);
      const shown = col?.type === "currency"
        ? `$${sum.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
        : sum.toLocaleString(undefined, { maximumFractionDigits: 2 });
      return `${label} · ${shown}`;
    }
    // Same defect as the old refCell fallback, in the path taken when a reference is NOT a resolved
    // column: eight characters of a value, indistinguishable from a resolved label. A UUID at least
    // announces itself as an id; anything else is shown as the text it is.
    if (f.type === "reference") return UUID_RE.test(String(v)) ? `${String(v).slice(0, 8)}…` : String(v);
    if (f.unit) return `${String(v)} ${f.unit}`;
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
    // UX-CHIPS — one tone vocabulary for every module's lifecycle, so "approved" reads the same
    // green in the drawing register (DRAW-STATUS), the submittal log and the RFI list. This is the
    // single widest-reach chip site: every module record grid renders its state through here.
    const render = () => { td.innerHTML = statusChip(r.workflow_state); };
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

  /** Per-module column choice (localStorage). null = use the module's default columns. */
  private readColPrefs(key: string): string[] | null {
    try { const s = localStorage.getItem(`portal-cols:${key}`); const a = s ? JSON.parse(s) : null; return Array.isArray(a) ? a as string[] : null; }
    catch { return null; }
  }

  /** Column chooser — pick which fields render as columns in a wide module. Personal + persisted;
   *  Ref / Title / Assignee / Ball / Status always frame the row, so only data fields are offered.
   *  Reset clears the choice and falls back to the module's default columns. */
  private columnPicker(m: ModuleDef, current: string[], filter: { q?: string; state?: string; offset?: number }) {
    const fields = m.fields.filter((f) => f.type !== "rollup" && f.type !== "signature");
    const dlg = modalShell(`Columns — ${m.name}`, 360);
    const help = document.createElement("div"); help.className = "meta";
    help.textContent = "Choose which fields show as columns. Ref, Title, Assignee, Ball-in-court and Status always show.";
    const list = document.createElement("div");
    list.style.cssText = "display:flex;flex-direction:column;gap:6px;max-height:44vh;overflow:auto;margin:8px 0";
    const boxes = new Map<string, HTMLInputElement>();
    for (const f of fields) {
      const lab = document.createElement("label"); lab.style.cssText = "display:flex;gap:8px;align-items:center;font-size:13px;cursor:pointer";
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = current.includes(f.name);
      lab.append(cb, document.createTextNode(f.label)); list.appendChild(lab); boxes.set(f.name, cb);
    }
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:4px";
    const reset = document.createElement("button"); reset.textContent = "Reset to default"; reset.className = "file-btn"; reset.style.marginRight = "auto";
    reset.onclick = () => { localStorage.removeItem(`portal-cols:${m.key}`); dlg.close(); void this.openModule(m, filter); };
    const cancel = document.createElement("button"); cancel.textContent = "Cancel"; cancel.className = "file-btn"; cancel.onclick = () => dlg.close();
    const ok = document.createElement("button"); ok.textContent = "Apply"; ok.className = "file-btn"; ok.style.fontWeight = "600";
    ok.onclick = () => {
      const names = fields.filter((f) => boxes.get(f.name)?.checked).map((f) => f.name);   // preserve field order
      localStorage.setItem(`portal-cols:${m.key}`, JSON.stringify(names));
      dlg.close(); void this.openModule(m, filter);
    };
    row.append(reset, cancel, ok);
    dlg.card.append(help, list, dlg.msg, row);
  }

  /** Paste-from-spreadsheet bulk entry — Ctrl-V a block of cells copied from Excel/Google Sheets
   *  (tab-separated) straight in, no file needed. The pasted table is converted to CSV and handed to
   *  the same import flow (preview + column mapping + commit), so paste and file import share one
   *  robust, validated server path rather than a second bespoke bulk-create loop. */
  private pasteRows(m: ModuleDef) {
    const dlg = modalShell(`Paste ${m.name} rows`, 460);
    const help = document.createElement("div");
    help.className = "meta";
    help.textContent = "Copy a block of cells from Excel or Google Sheets and paste below — keep the header row. "
      + "The next step lets you map each column to a field before anything is created.";
    const ta = document.createElement("textarea");
    ta.placeholder = "name\tstatus\tamount\nFooting F-1\topen\t1200\n…";
    ta.setAttribute("aria-label", "Pasted spreadsheet rows");
    ta.style.cssText = "width:100%;min-height:150px;margin:8px 0;padding:8px;border:1px solid var(--line);"
      + "border-radius:6px;background:var(--bg);color:inherit;font-family:ui-monospace,monospace;font-size:12px;white-space:pre;overflow:auto";
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:4px";
    const cancel = document.createElement("button"); cancel.textContent = "Cancel"; cancel.className = "file-btn";
    cancel.onclick = () => dlg.close();
    const ok = document.createElement("button"); ok.textContent = "Continue →"; ok.className = "file-btn"; ok.style.fontWeight = "600";
    ok.onclick = () => {
      const text = ta.value.replace(/\r\n?/g, "\n").replace(/\n+$/, "");
      if (!text.trim()) { dlg.msg.textContent = "Nothing pasted yet."; return; }
      // TSV → CSV: quote every cell (doubling internal quotes) so tabs/commas survive the round-trip.
      const csv = text.split("\n")
        .map((line) => line.split("\t").map((cell) => `"${cell.replace(/"/g, '""')}"`).join(","))
        .join("\n");
      const file = new File([csv], "pasted.csv", { type: "text/csv" });
      dlg.close();
      void this.renderImport(m, file);
    };
    row.append(cancel, ok);
    dlg.card.append(help, ta, dlg.msg, row);
    setTimeout(() => ta.focus(), 0);
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
        const val = v.val ?? "";
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
    // MOD-TABLE: live rows per table field. Held apart from `inputs` because a table's value is an
    // array of objects, not an `el.value` string — the shape the rest of the form assumes.
    const tableRows: Record<string, Record<string, unknown>[]> = {};
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
      } else if (f.type === "table") {
        // MOD-TABLE: a line-item grid is NOT one of the form's three input elements, and it is
        // deliberately not registered in `inputs` — its value is an array of objects rather than an
        // `el.value` string, so every consumer of `inputs` (the required check, the save loop, the
        // invalid-marker) would read it wrongly. `tableRows` holds the live rows; the save path reads
        // from there. Appending it here and `continue`-ing keeps `el` honestly typed as an input.
        wrap.appendChild(this.tableEditor(f, cur(f.name), tableRows));
        this.root.appendChild(wrap);
        continue;
            } else {
        el = document.createElement("input");
        const inp = el as HTMLInputElement;
        // MOD-PERCENT: a percent field rendered as `type="text"` — no numeric keypad on a phone, no
        // step, no browser validation. It is a magnitude like the other two.
        inp.type = isNumericField(f.type) ? "number" : f.type === "date" ? "date" : "text";
        if (f.type === "currency" || f.type === "percent") inp.step = "0.01";
        // The declared unit is shown beside the input, not only in table cells. A unit that renders in
        // one place and not the other is half of what declaring it was for: the moment it matters most
        // is while somebody is TYPING the number.
        //
        // Read structurally rather than via `ModuleField.unit`. `unit` is declared on that interface by
        // the field-sweep branch, which is merged to `main` but not into this one — and it cannot be
        // merged in right now without git overwriting two files another session is holding dirty. A
        // local structural read is correct on both sides of that merge and costs nothing once it lands.
        const unit = f.unit;
        // MOD-FIELDATTRS: an explicit placeholder wins over the unit hint — the unit was only ever a
        // fallback for "this box has no guidance at all".
        if (f.placeholder) inp.placeholder = f.placeholder;
        else if (unit) inp.placeholder = unit;
        if (unit) inp.setAttribute("aria-description", `in ${unit}`);
        if (f.min != null) inp.min = String(f.min);
        if (f.max != null) inp.max = String(f.max);
        // A default is for a NEW record. On an edit, an absent value is a value the user cleared.
        const existing = cur(f.name);
        // `@today` is resolved on both sides: the form shows the date the user is about to save, and
        // the server fills it for any caller that never opened a form (import, integration, script).
        const dflt = f.default === "@today" ? new Date().toISOString().slice(0, 10) : f.default;
        inp.value = String(existing ?? (editing ? "" : (dflt ?? "")));
      }
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
      // MOD-TABLE: checked BEFORE the `!el` guard, because a table is deliberately absent from
      // `inputs` — and `!el → return false` means "not empty", so a `required` table with zero rows
      // would have sailed through the check. None of the eight tables shipped here is required, so
      // this is a hole rather than a bug today; it is the same "plausible answer for the missing
      // case" shape that keeps costing this codebase, so it is closed at the point it was created.
      if (f.type === "table") {
        return !(tableRows[f.name] ?? []).some(
          (row) => Object.values(row).some((x) => x !== "" && x != null));
      }
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
        if (!el) continue;
        if (f.type === "multiselect") { data[f.name] = [...(el as HTMLSelectElement).selectedOptions].map((o) => o.value); continue; }
        // MOD-PERCENT: the quietest of the three. Without `percent` here a percentage saved as the
        // STRING "5"; `validate_record` does `float(value)` so it passed, and every consumer coerces,
        // so nothing ever failed — the column simply accumulated a mix of 5 and "5" depending on which
        // form last touched the record. Numbers stored as text are also what makes SQL comparison go
        // lexicographic, which is the bug MOD-FILTER's cast exists to survive.
        const v = el.value; if (v) data[f.name] = isNumericField(f.type) ? Number(v) : v;
      }
      // MOD-TABLE: rows come from their own state, and are written even when EMPTY — unlike a text
      // field, "the user deleted every line" is a real edit that must persist. Skipping empty here
      // would make clearing a schedule of values silently impossible.
      for (const f of m.fields) {
        if (f.type !== "table" || !(f.name in tableRows)) continue;
        data[f.name] = tableRows[f.name]!.filter(
          (row) => Object.values(row).some((x) => x !== "" && x != null));
      }
      try {
        if (editing) {
          // optimistic lock: send the modified_at we loaded; a concurrent edit 409s rather than
          // silently overwriting the other person's change (real-time collaboration safety).
          await this.host.api.updateModuleRecord(pid, m.key, existing!.id, data, existing!.modified_at);
          this.host.setStatus(`saved ${existing!.ref}`);
          void this.openRecord(m, existing!.id);
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
          void this.openRecord(m, rec.id);
        }
      } catch (e) {
        const msg = (e as Error).message;
        if (/-> 409$/.test(msg) && editing) {          // optimistic-lock conflict — someone edited first
          this.host.setStatus("Someone else changed this record while you had it open — reloading the latest; re-apply your edit.");
          void this.openRecord(m, existing!.id);
          return;
        }
        const mm = /missing required field\(s\):\s*([^"}]+)/i.exec(msg);   // server-side required rules
        if (mm) { const names = (mm[1] ?? "").split(",").map((s) => s.trim()).filter(Boolean); markInvalid(names); }
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
    btn("🖊 View & markup", "Open the document with redline / markup tools (save annotations back as an attachment)", async () => {
      const { openPdfUrl } = await import("../drawings/openPdf");
      await openPdfUrl(api, api.contractDocUrl(pid, m.key, rid, spec.doc), `${spec.doc}-${r.ref}.pdf`, {
        saveLabel: "Attach marked-up copy",
        onSave: async (blob, name) => { await api.uploadAttachment(pid, m.key, rid, new File([blob], name.replace(/\.pdf$/i, "") + "-markup.pdf", { type: "application/pdf" })); },
      });
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
        const signers = (v.emails ?? "").split(",").map((e) => ({ email: e.trim() })).filter((s) => s.email);
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
        out.textContent = r.count ? `${r.count} filing(s) found — first: ${r.permits[0]?.address ?? r.permits[0]?.permit_number}` : "No filings found — try an address/keyword or coordinates.";
      } catch (e) { out.textContent = `Search failed: ${(e as Error).message}`; }
    };
    const imp = document.createElement("button"); imp.className = "file-btn"; imp.textContent = "Import";
    imp.onclick = async () => {
      out.textContent = "importing…";
      try { const r = await this.host.api.importOpendataPermits(pid, { ...opts(), max: 50 });
        toast(`Imported ${r.imported} permit(s)${r.skipped ? `, skipped ${r.skipped} duplicate(s)` : ""}`, "success");
        void this.openModule(m);
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
      if (!(await confirmModal(`Delete ${r.ref}? This cannot be undone.`, "", "Delete", true))) return;
      try { await this.host.api.deleteModuleRecord(pid, m.key, rid); this.host.setStatus(`deleted ${r.ref}`); this.host.onPinsChanged(); void this.openModule(m); }
      catch (e) { this.host.setStatus(`error: ${(e as Error).message}`); }
    };
    const pdfBtn = document.createElement("button");
    pdfBtn.className = "tool-btn"; pdfBtn.textContent = "↓ PDF";
    pdfBtn.onclick = () => window.open(this.host.api.url(`/projects/${pid}/modules/${m.key}/${rid}/pdf`), "_blank");
    const pdfMk = document.createElement("button");
    pdfMk.className = "tool-btn"; pdfMk.textContent = "🖊 Markup";
    pdfMk.title = "Open the record PDF in the in-app viewer to mark up (saves back as an attachment)";
    pdfMk.onclick = async () => {
      const { openPdfUrl } = await import("../drawings/openPdf");
      await openPdfUrl(this.host.api, this.host.api.url(`/projects/${pid}/modules/${m.key}/${rid}/pdf`), `${r.ref}.pdf`, {
        saveLabel: "Attach marked-up copy",
        onSave: async (blob, name) => { await this.host.api.uploadAttachment(pid, m.key, rid, new File([blob], name.replace(/\.pdf$/i, "") + "-markup.pdf", { type: "application/pdf" })); void this.openRecord(m, rid); },
      });
    };
    tools.append(editBtn, delBtn, pdfBtn, pdfMk);
    if (m.revisable) {
      const reviseBtn = document.createElement("button");
      reviseBtn.className = "tool-btn"; reviseBtn.dataset.cap = "review";
      const superseded = !!r.revision?.superseded_by;
      reviseBtn.textContent = "⎘ Revise"; reviseBtn.disabled = superseded;
      reviseBtn.title = superseded ? "Already revised" : "Create a tracked revision (re-opens the workflow)";
      reviseBtn.onclick = async () => {
        if (!(await confirmModal(`Create a revision of ${r.ref}? It re-opens the workflow as a new record (${r.ref}.${(r.revision?.number ?? 0) + 1}).`, ""))) return;
        try { const nv = await this.host.api.reviseRecord(pid, m.key, rid); this.host.setStatus(`created ${nv.ref}`); void this.openRecord(m, nv.id); }
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
      try { await this.host.api.assignRecord(pid, m.key, rid, v.who?.trim() || null); void this.openRecord(m, rid); }
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
        this.host.setStatus(`tied ${res.count} element${res.count === 1 ? "" : "s"}`); void this.openRecord(m, rid); }
      catch (e) { this.host.setStatus(`tie failed: ${(e as Error).message}`); }
    };
    elRow.appendChild(tagBtn);
    if (guids.length) {
      const showBtn = document.createElement("button"); showBtn.className = "tool-btn"; showBtn.textContent = "👁 Show in model";
      showBtn.onclick = () => this.host.onSelectGuids(guids); elRow.appendChild(showBtn);
      const clrBtn = document.createElement("button"); clrBtn.className = "tool-btn"; clrBtn.textContent = "✕ Clear ties";
      clrBtn.onclick = async () => {
        if (!(await confirmModal(`Untie all ${guids.length} elements from ${r.ref}?`, "", "Untie", true))) return;
        try { await this.host.api.tagElements(pid, m.key, rid, [], "set"); void this.openRecord(m, rid); }
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
          try { await this.host.api.transitionRecord(pid, m.key, rid, a.action); void this.openRecord(m, rid); }
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
      void this.openRecord(m, rid);
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
    if (m) void this.openRecord(m, id);
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
    box.innerHTML = "";
    type Brief = { module: string; module_name: string; id: string; ref: string; title: string | null; state: string; label?: string | null };
    // Two labelled, counted directions so "what this record points to" reads distinctly from "what
    // points back at it" (the incoming side is the dependency signal — e.g. the change orders raised
    // against this budget line). textContent/esc throughout: ref+title are user data (stored-XSS guard).
    const group = (title: string, caption: string, icon: string, items: Brief[], labelOf: (b: Brief) => string) => {
      if (!items.length) return;
      const h = document.createElement("div"); h.className = "section-title"; h.textContent = `${title} (${items.length})`;
      box.appendChild(h);
      const cap = document.createElement("div"); cap.className = "meta"; cap.textContent = caption; box.appendChild(cap);
      for (const b of items) {
        const row = document.createElement("button"); row.className = "portal-mod";
        row.innerHTML = `<span class="ic">${icon}</span> <b>${esc(labelOf(b))}</b> ${esc(b.ref)} ${esc(b.title ?? "")} ${statusChip(b.state)}`;
        row.onclick = () => this.openByBrief(b.module, b.id);
        box.appendChild(row);
      }
    };
    group("References", "Records this one points to.", "↳", rel.outgoing, (b) => b.label ?? b.module_name);
    group("Referenced by", "Records that point to this one — its dependents.", "↰", rel.incoming, (b) => b.module_name);
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
        const isPdf = (a.content_type || "").includes("pdf") || /\.pdf$/i.test(a.filename);
        const url = this.host.api.attachmentUrl(a.id);
        const kb = a.size > 1024 * 1024 ? `${(a.size / 1048576).toFixed(1)} MB` : a.size > 1024 ? `${Math.round(a.size / 1024)} KB` : `${a.size} B`;
        if (isPdf) {
          // open in the in-app viewer for markup; saving posts a marked-up copy back as a new attachment
          const pc = document.createElement("button"); pc.className = "att-cell att-file"; pc.title = `${a.filename} · ${kb} — open in viewer / mark up`;
          pc.innerHTML = `<span class="att-ic">📄</span><span class="att-name">${a.filename}</span>`;
          pc.onclick = async () => {
            const { openPdfUrl } = await import("../drawings/openPdf");
            await openPdfUrl(this.host.api, url, a.filename, {
              saveLabel: "Save marked-up copy back",
              onSave: async (blob, nm) => {
                await this.host.api.uploadAttachment(pid, m.key, rid, new File([blob], nm.replace(/\.pdf$/i, "") + "-markup.pdf", { type: "application/pdf" }));
                void this.openRecord(m, rid);
              },
            });
          };
          gallery.appendChild(pc); continue;
        }
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
      if (!navigator.onLine) { await this.queueUpload(pid, m.key, rid, list); void this.openRecord(m, rid); return; }
      drop.classList.add("busy"); drop.querySelector("b")!.textContent = `Uploading ${list.length} file${list.length > 1 ? "s" : ""}…`;
      try {
        if (list.length === 1) await this.host.api.uploadAttachment(pid, m.key, rid, list[0]!); // safe: list.length === 1 checked
        else await this.host.api.uploadAttachmentsBulk(pid, m.key, rid, list);
        this.host.setStatus(`attached ${list.length} file${list.length > 1 ? "s" : ""}`); void this.openRecord(m, rid);
      } catch (e) {
        if (!navigator.onLine) { await this.queueUpload(pid, m.key, rid, list); void this.openRecord(m, rid); return; }
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
        if (q.files.length === 1) await this.host.api.uploadAttachment(q.pid, q.key, q.rid, q.files[0]!); // safe: q.files.length === 1 checked
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
        try { await this.host.api.transitionRecord(pid, m.key, rid, tr.action); void this.renderBoard(m); }
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
