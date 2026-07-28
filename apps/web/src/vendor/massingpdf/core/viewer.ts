/**
 * The kernel.
 *
 * Owns the document, the page layout, zoom/pan/rotation, the annotation overlay, hit-testing,
 * selection, the tool gesture loop, and the plugin registries. It owns no domain knowledge: it does
 * not know what a revision cloud means, only that a tool asked for a `cloud` with four points.
 */
import { PdfDocument, type PdfSource, type TextItem } from "./document";
import { PageView } from "./renderer";
import { TextLayer, clearSelection, type TextSelection } from "./textLayer";
import { EventBus, type EventName, type Handler, type Unsubscribe } from "./events";
import { AnnotationStore } from "./store";
import {
  displaySize, displayToPage, eventToPage, normalizeRotation, rotationTransform, type Rotation,
} from "./coords";
import { bbox, distToPath, pointInPolygon, simplify, snapAngle } from "./geometry";
import { measure } from "./units";
import { drawAnnotation, drawDraft, el } from "../render/svg";
import type {
  ActionDef, KindRenderer, PanelDef, PluginContext, ToolDef, ViewerPlugin,
} from "./plugin";
import type { Annotation, AnnotationDraft, AnnotKind, Pt } from "./types";
import { POINT_KINDS } from "./types";
import { createLiveRegion } from "./a11y";
import { PermissionError, Policy, type AuditSink, type PermissionCheck } from "./policy";

export interface ViewerOptions {
  /** Where to mount. The viewer takes over this element's contents. */
  container: HTMLElement;
  /** Who is marking up. */
  author?: string;
  org?: string;
  /** Start zoom, or a fit mode applied once the document loads. */
  initialZoom?: number | "fit-width" | "fit-page";
  /** Render every page in one scroller (the default) or one page at a time. */
  layout?: "continuous" | "single";
  /** Read-only: tools and editing are disabled, viewing and export are not. */
  readOnly?: boolean;
  /** Imperial lengths render as feet-and-inches. */
  feetInches?: boolean;
  /** Map a page to a stable sheet key so markups survive a re-issued container file. */
  sheetIdFor?: (page: number) => string;
  /** Build a selectable text layer over each page. On by default; scans have no text to select. */
  textLayer?: boolean;
  /**
   * Ignore touch contacts while a pen is in use. On by default — without it, a hand resting on a
   * tablet draws across whatever the stylus is writing.
   */
  palmRejection?: boolean;
  /**
   * Vary freehand stroke width with stylus pressure. On by default where the device reports it;
   * pressure samples are kept on the markup either way.
   */
  penPressure?: boolean;
  /**
   * Decide whether the current user may do something. Absent means everything is allowed.
   *
   * Enforced in the store, not in the toolbar — see `core/policy.ts` for why that distinction
   * matters, and for what a client-side check can and cannot promise.
   */
  permissions?: PermissionCheck;
  /**
   * Receives a record of every gated act, allowed or refused.
   *
   * Construction markups become contract evidence, so this is usually a compliance requirement
   * rather than analytics. Write it to the host's own audit pipeline.
   */
  audit?: AuditSink;
  /** Plugins to install at construction. More can be added with `use()` before `load()`. */
  plugins?: ViewerPlugin[];
}

/** One page's DOM: raster surface + annotation overlay, stacked in a positioned wrapper. */
interface PageLayer {
  page: number;
  wrap: HTMLDivElement;
  view: PageView;
  overlay: SVGSVGElement;
  /** The group carrying the rotation transform; annotations go inside it. */
  content: SVGGElement;
  /** Selectable text over the raster. Built lazily, the first time a text tool is armed. */
  text: TextLayer;
  dirty: boolean;
}

const ZOOM_MIN = 0.08;
const ZOOM_MAX = 16;
const PAGE_GAP = 16;
/**
 * How long after a pen event touch stays ignored.
 *
 * Long enough to cover the gap between strokes while a hand stays down, short enough that putting
 * the stylus aside and using fingers works without a wait anyone would notice.
 */
const PEN_PALM_WINDOW_MS = 700;

export class Viewer {
  readonly bus = new EventBus();
  readonly store: AnnotationStore;
  readonly el: {
    root: HTMLDivElement;
    toolbar: HTMLDivElement;
    body: HTMLDivElement;
    left: HTMLElement;
    scroll: HTMLDivElement;
    pages: HTMLDivElement;
    right: HTMLElement;
    status: HTMLDivElement;
  };

  doc: PdfDocument | null = null;

  private opts: ViewerOptions;
  private layers = new Map<number, PageLayer>();
  private _zoom = 1;
  private _rotation: Rotation = 0;
  private _page = 1;
  private pendingFit: "fit-width" | "fit-page" | null = null;

  private tools = new Map<string, ToolDef>();
  private actions = new Map<string, ActionDef>();
  private panels: PanelDef[] = [];
  private renderers: KindRenderer[] = [];
  private plugins: ViewerPlugin[] = [];
  private cleanups: (() => void)[] = [];

  private activeToolId: string | null = null;
  /** Points collected so far in the current gesture, page space. */
  private draft: Pt[] = [];
  private draftPage = 1;
  private gesture: GestureState | null = null;
  private destroyed = false;
  private scrollRaf = 0;
  /** Live touch points, for pinch and two-finger pan. Keyed by pointerId. */
  private touches = new Map<number, { x: number; y: number }>();
  /**
   * When a pen was last seen. Within `PEN_PALM_WINDOW_MS` of that, touch contacts are ignored:
   * a hand resting on the sheet is a palm, not a second finger, and on a tablet with a stylus it
   * would otherwise draw across everything the pen is writing.
   */
  private lastPenAt = 0;
  /**
   * Touch contacts rejected as palm, by pointerId.
   *
   * Identity, not elapsed time: a stylus held still mid-stroke lets the window lapse, and a purely
   * time-based test would then let the palm's `pointerup` end the stroke the pen is still drawing.
   * A contact rejected on landing stays rejected until it lifts.
   */
  private rejectedTouches = new Set<number>();
  /** Pressure samples for the current freehand stroke, when the device reports them. */
  private strokePressures: number[] = [];
  private pinch: {
    distance: number;
    zoom: number;
    page: number;
    /** The page-space point that was under the fingers when the pinch began. */
    anchor: Pt | null;
  } | null = null;
  /** A pinch update is in flight; a move arriving now re-runs once it lands. */
  private pinchBusy = false;
  private pinchPending = false;
  /** OCR output per page, for scans whose PDF carries no text layer. */
  private recognised = new Map<number, TextItem[]>();
  /**
   * Screen-reader announcements.
   *
   * Everything this viewer tells the user — a save failing, a tool arming, a page changing — is
   * conveyed by a small visual change somewhere. None of it reaches a reader without this.
   */
  private live: ReturnType<typeof createLiveRegion>;
  /** Permission gate and audit trail. Inert unless the host configured one. */
  readonly policy: Policy;

  constructor(opts: ViewerOptions) {
    this.opts = opts;
    this.el = buildShell(opts.container);
    this.live = createLiveRegion(this.el.root);
    // Notices are the viewer's own voice; route them so they are heard, not only seen.
    this.bus.on("notice", ({ level, message }) => {
      this.live.announce(message, level === "error" ? "assertive" : "polite");
    });
    this.policy = new Policy({
      actor: () => this.opts.author ?? "unknown",
      documentId: () => this.doc?.fingerprint,
      ...(opts.permissions ? { check: opts.permissions } : {}),
      ...(opts.audit ? { audit: opts.audit } : {}),
      onDeny: (reason) => this.bus.emit("notice", { level: "warn", message: reason }),
    });
    this.store = new AnnotationStore({
      bus: this.bus,
      ...(opts.permissions || opts.audit ? { policy: this.policy } : {}),
      author: () => this.opts.author ?? "unknown",
      org: () => this.opts.org,
      pageSize: (p) => this.doc?.pageInfoSync(p),
      ...(opts.sheetIdFor ? { sheetIdFor: opts.sheetIdFor } : {}),
    });
    if (typeof opts.initialZoom === "number") this._zoom = opts.initialZoom;
    else this.pendingFit = opts.initialZoom ?? "fit-width";

    this.wireStore();
    this.wireInput();
    for (const p of opts.plugins ?? []) void this.use(p);
  }

  // ---- lifecycle -----------------------------------------------------------

  /** Install a plugin. Safe before or after `load()`. */
  async use(plugin: ViewerPlugin): Promise<this> {
    if (this.plugins.some((p) => p.id === plugin.id)) return this;
    this.plugins.push(plugin);
    this.plugins.sort((a, b) => (a.order ?? 100) - (b.order ?? 100));
    const ctx: PluginContext = {
      viewer: this,
      bus: this.bus,
      store: this.store,
      registerTool: (t) => { this.tools.set(t.id, t); },
      registerAction: (a) => { this.actions.set(a.id, a); },
      registerPanel: (p) => { this.panels.push(p); this.panels.sort((a, b) => (a.order ?? 100) - (b.order ?? 100)); },
      registerRenderer: (r) => { this.renderers.push(r); },
      onCleanup: (fn) => { this.cleanups.push(fn); },
    };
    await plugin.setup(ctx);
    return this;
  }

  /** Load a PDF. Replaces any open document; markups are *not* cleared (a slip-sheet keeps them). */
  async load(source: PdfSource, opts: { keepMarkups?: boolean } = {}): Promise<PdfDocument> {
    this.closeDoc();
    const doc = await PdfDocument.load(source);
    this.doc = doc;
    await doc.primeInfo();
    if (!opts.keepMarkups) { this.store.reset([], { undoable: false }); this.store.clearHistory(); }
    this._page = 1;
    await this.buildPages();
    if (this.pendingFit) { await this.applyFit(this.pendingFit); this.pendingFit = null; }
    else await this.applyZoom();
    this.bus.emit("doc:loaded", { name: doc.name, pages: doc.numPages, fingerprint: doc.fingerprint });
    this.mountPanels();
    return doc;
  }

  private closeDoc(): void {
    for (const l of this.layers.values()) { l.view.destroy(); l.text.destroy(); l.wrap.remove(); }
    this.layers.clear();
    this.recognised.clear();
    if (this.doc) { this.doc.destroy(); this.doc = null; this.bus.emit("doc:closed", undefined); }
  }

  destroy(): void {
    if (this.destroyed) return;
    this.destroyed = true;
    for (const fn of this.cleanups.splice(0)) { try { fn(); } catch (e) { console.error(e); } }
    for (const p of this.plugins) { try { p.teardown?.(); } catch (e) { console.error(e); } }
    this.closeDoc();
    this.live.destroy();
    this.bus.clear();
    this.el.root.remove();
  }

  // ---- registries ----------------------------------------------------------

  get toolList(): ToolDef[] { return [...this.tools.values()]; }
  get actionList(): ActionDef[] { return [...this.actions.values()]; }
  get panelList(): PanelDef[] { return [...this.panels]; }
  tool(id: string): ToolDef | undefined { return this.tools.get(id); }
  action(id: string): ActionDef | undefined { return this.actions.get(id); }

  get activeTool(): ToolDef | null {
    return this.activeToolId ? this.tools.get(this.activeToolId) ?? null : null;
  }

  /** Enter a drawing mode, or `null` for select. */
  setTool(id: string | null): void {
    if (this.opts.readOnly) id = null;
    if (id === this.activeToolId) return;
    this.activeTool?.deactivate?.(this);
    this.cancelDraft();
    this.activeToolId = id && this.tools.has(id) ? id : null;
    const t = this.activeTool;
    t?.activate?.(this);
    this.el.pages.style.cursor = t?.cursor ?? (t ? "crosshair" : "default");
    this.applyTouchAction();
    this.syncTextLayers();
    // Arming a tool changes the cursor and highlights a button. Neither is perceivable without
    // sight, and a reviewer needs to know which tool a keypress just selected.
    this.announce(t ? `${t.label} tool selected` : "Tool cleared");
    this.bus.emit("tool:changed", { id: this.activeToolId });
  }

  /**
   * Say something to a screen reader.
   *
   * Public because a plugin's status changes are just as invisible as the kernel's, and a host
   * replacing the toolbar still needs a way to be heard.
   */
  announce(message: string, urgency: "polite" | "assertive" = "polite"): void {
    this.live.announce(message, urgency);
  }

  async runAction(id: string): Promise<void> {
    const a = this.actions.get(id);
    if (!a) return;
    if (a.enabled && !a.enabled(this)) return;
    await a.run(this);
  }

  get readOnly(): boolean { return Boolean(this.opts.readOnly); }
  setReadOnly(v: boolean): void {
    this.opts.readOnly = v;
    if (v) this.setTool(null);
  }

  get author(): string { return this.opts.author ?? "unknown"; }
  setAuthor(name: string, org?: string): void {
    this.opts.author = name;
    if (org !== undefined) this.opts.org = org;
  }

  get feetInches(): boolean { return this.opts.feetInches ?? true; }

  // ---- view state ----------------------------------------------------------

  get zoom(): number { return this._zoom; }
  get rotation(): Rotation { return this._rotation; }
  get page(): number { return this._page; }
  get numPages(): number { return this.doc?.numPages ?? 0; }

  async setZoom(z: number, anchor?: { clientX: number; clientY: number }): Promise<void> {
    const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
    if (Math.abs(next - this._zoom) < 1e-6) return;
    const s = this.el.scroll;
    // Keep the point under the cursor fixed — the difference between usable and infuriating.
    const rect = s.getBoundingClientRect();
    const ax = anchor ? anchor.clientX - rect.left : s.clientWidth / 2;
    const ay = anchor ? anchor.clientY - rect.top : s.clientHeight / 2;

    // Measured relative to the *page*, not to the scroll content. Pages are centred in the
    // scroller, so a page narrower than the viewport sits at an offset that changes with zoom;
    // anchoring to scroll coordinates makes zooming in from fit-width jump sideways.
    const layer = this.layers.get(this._page);
    const held = layer
      ? {
          x: (s.scrollLeft + ax - layer.wrap.offsetLeft) / this._zoom,
          y: (s.scrollTop + ay - layer.wrap.offsetTop) / this._zoom,
        }
      : null;

    this._zoom = next;
    await this.applyZoom();

    if (held && layer) {
      // Offsets are re-read after the relayout, so the new centring is accounted for.
      s.scrollLeft = layer.wrap.offsetLeft + held.x * next - ax;
      s.scrollTop = layer.wrap.offsetTop + held.y * next - ay;
    }
    this.emitView();
  }

  zoomIn(anchor?: { clientX: number; clientY: number }): Promise<void> { return this.setZoom(this._zoom * 1.25, anchor); }
  zoomOut(anchor?: { clientX: number; clientY: number }): Promise<void> { return this.setZoom(this._zoom / 1.25, anchor); }

  async fitWidth(): Promise<void> { await this.applyFit("fit-width"); }
  async fitPage(): Promise<void> { await this.applyFit("fit-page"); }

  private async applyFit(mode: "fit-width" | "fit-page"): Promise<void> {
    const info = this.doc?.pageInfoSync(this._page);
    if (!info) { this.pendingFit = mode; return; }
    const d = displaySize(info.width, info.height, this._rotation);
    const availW = this.el.scroll.clientWidth - 48;
    const availH = this.el.scroll.clientHeight - 48;
    const z = mode === "fit-width" ? availW / d.w : Math.min(availW / d.w, availH / d.h);
    this._zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
    await this.applyZoom();
    this.emitView();
  }

  /** Rotate the view by a multiple of 90°. Markup geometry is untouched. */
  async rotate(deltaDeg: number): Promise<void> {
    this._rotation = normalizeRotation(this._rotation + deltaDeg);
    await this.applyZoom();
    this.emitView();
  }

  /** Scroll a page into view and make it current. */
  async goToPage(n: number): Promise<void> {
    const page = Math.min(Math.max(1, Math.round(n)), this.numPages || 1);
    const layer = this.layers.get(page);
    this._page = page;
    if (layer) this.el.scroll.scrollTop = layer.wrap.offsetTop - 8;
    this.announce(`Page ${page} of ${this.numPages || 1}`);
    this.bus.emit("page:changed", { page });
    this.emitView();
    this.updateVisible();
  }

  /** Centre the view on a markup, zooming in if it is small on screen. */
  async goToAnnotation(a: Annotation, opts: { zoom?: boolean } = {}): Promise<void> {
    await this.goToPage(a.page);
    const info = this.doc?.pageInfoSync(a.page);
    const layer = this.layers.get(a.page);
    if (!info || !layer) return;
    const b = bbox(a.points);
    if (opts.zoom !== false && b.w > 0 && b.h > 0) {
      const target = Math.min(4, Math.max(0.5, Math.min(
        (this.el.scroll.clientWidth * 0.6) / (b.w || 1),
        (this.el.scroll.clientHeight * 0.6) / (b.h || 1),
      )));
      if (target > this._zoom) { this._zoom = target; await this.applyZoom(); }
    }
    const c = { x: b.x + b.w / 2, y: b.y + b.h / 2 };
    const d = this.pageToLocal(c, info.width, info.height);
    this.el.scroll.scrollLeft = layer.wrap.offsetLeft + d.x - this.el.scroll.clientWidth / 2;
    this.el.scroll.scrollTop = layer.wrap.offsetTop + d.y - this.el.scroll.clientHeight / 2;
    this.emitView();
    this.updateVisible();
  }

  private pageToLocal(p: Pt, w: number, h: number): Pt {
    const d = this._rotation === 0 ? p
      : this._rotation === 90 ? { x: h - p.y, y: p.x }
      : this._rotation === 180 ? { x: w - p.x, y: h - p.y }
      : { x: p.y, y: w - p.x };
    return { x: d.x * this._zoom, y: d.y * this._zoom };
  }

  private emitView(): void {
    this.bus.emit("view:changed", { zoom: this._zoom, page: this._page, rotation: this._rotation });
  }

  // ---- layout --------------------------------------------------------------

  private async buildPages(): Promise<void> {
    const doc = this.doc;
    if (!doc) return;
    this.el.pages.innerHTML = "";
    const pages = this.opts.layout === "single" ? [this._page] : rangeOf(doc.numPages);
    for (const n of pages) this.layers.set(n, this.makeLayer(n));
    for (const n of pages) this.el.pages.appendChild(this.layers.get(n)!.wrap);
  }

  private makeLayer(page: number): PageLayer {
    const wrap = document.createElement("div");
    wrap.className = "mpdf-page-wrap";
    wrap.dataset.page = String(page);
    const view = new PageView({
      doc: this.doc!,
      page,
      onRendered: (p, s) => this.bus.emit("page:rendered", { page: p, scale: s }),
    });
    const overlay = el("svg", { class: "mpdf-overlay" }) as SVGSVGElement;
    overlay.dataset.page = String(page);
    const content = el("g", { class: "mpdf-overlay-content" });
    overlay.appendChild(content);
    const text = new TextLayer(this.doc!, page);
    // Stacking: raster, then text (selectable), then the annotation overlay on top.
    wrap.append(view.el, text.el, overlay);
    return { page, wrap, view, overlay, content, text, dirty: true };
  }

  /** Push the current zoom/rotation into every page, then repaint what's on screen. */
  private async applyZoom(): Promise<void> {
    const doc = this.doc;
    if (!doc) return;
    for (const layer of this.layers.values()) {
      const info = doc.pageInfoSync(layer.page);
      if (!info) continue;
      await layer.view.setTransform(this._zoom, this._rotation);
      const d = displaySize(info.width, info.height, this._rotation);
      const css = { w: d.w * this._zoom, h: d.h * this._zoom };
      layer.wrap.style.width = `${css.w}px`;
      layer.wrap.style.height = `${css.h}px`;
      layer.overlay.setAttribute("width", String(css.w));
      layer.overlay.setAttribute("height", String(css.h));
      layer.overlay.setAttribute("viewBox", `0 0 ${d.w} ${d.h}`);
      const t = rotationTransform(info.width, info.height, this._rotation);
      if (t) layer.content.setAttribute("transform", t);
      else layer.content.removeAttribute("transform");
      layer.text.setScale(this._zoom);
      // The text layer is positioned in unrotated page space, so it can only line up with the ink
      // when the view is unrotated. Hide it rather than offer a selection that lands in the wrong
      // place — a subtly wrong highlight is worse than no highlight.
      layer.text.el.style.display = this._rotation === 0 ? "" : "none";
      layer.dirty = true;
    }
    this.updateVisible();
    this.redraw();
  }

  /**
   * Raster the pages intersecting the scroll viewport; release those far away.
   *
   * Rasterisation is deliberately *not* awaited. pdf.js drives its canvas render loop from
   * `requestAnimationFrame`, which browsers stop firing in a background tab — so awaiting the
   * pixels would make `load()` (and every zoom) hang until the tab is foregrounded again. Layout is
   * synchronous and settled by the time this returns; painting catches up and announces itself via
   * `page:rendered`.
   */
  private updateVisible(): void {
    const s = this.el.scroll;
    const top = s.scrollTop, bottom = top + s.clientHeight;
    let best: { page: number; overlap: number } | null = null;
    for (const layer of this.layers.values()) {
      const y0 = layer.wrap.offsetTop, y1 = y0 + layer.wrap.offsetHeight;
      const overlap = Math.min(bottom, y1) - Math.max(top, y0);
      if (overlap <= 0) {
        // Two screens of slack before dropping rasters, so a flick-scroll back is instant.
        if (y1 < top - s.clientHeight * 2 || y0 > bottom + s.clientHeight * 2) layer.view.release();
        continue;
      }
      if (!best || overlap > best.overlap) best = { page: layer.page, overlap };
      void layer.view.update({
        x: Math.max(0, s.scrollLeft - layer.wrap.offsetLeft),
        y: Math.max(0, top - y0),
        w: s.clientWidth,
        h: s.clientHeight,
      }).catch((e: unknown) => console.warn(`[massing-pdf] page ${layer.page} raster failed`, e));
    }
    if (best && best.page !== this._page) {
      this._page = best.page;
      this.bus.emit("page:changed", { page: best.page });
    }
  }

  private mountPanels(): void {
    for (const side of ["left", "right"] as const) {
      const host = this.el[side];
      host.innerHTML = "";
      const mine = this.panels.filter((p) => (p.side ?? "right") === side);
      host.style.display = mine.length ? "" : "none";
      for (const p of mine) {
        const box = document.createElement("section");
        box.className = "mpdf-panel";
        box.dataset.panel = p.id;
        const h = document.createElement("header");
        h.className = "mpdf-panel-title";
        h.textContent = p.title;
        const bodyEl = document.createElement("div");
        bodyEl.className = "mpdf-panel-body";
        box.append(h, bodyEl);
        host.appendChild(box);
        const dispose = p.mount(bodyEl, this);
        if (typeof dispose === "function") this.cleanups.push(dispose);
      }
    }
  }

  // ---- overlay drawing -----------------------------------------------------

  /** Repaint annotation overlays. Omit `page` to repaint every mounted page. */
  redraw(page?: number): void {
    const list = page !== undefined
      ? [this.layers.get(page)].filter((l): l is PageLayer => !!l)
      : [...this.layers.values()];
    for (const layer of list) this.paint(layer);
  }

  private paint(layer: PageLayer): void {
    const content = layer.content;
    content.textContent = "";
    const ctx = {
      zoom: this._zoom,
      viewer: this,
      el,
      selected: false,
    };
    for (const a of this.store.visibleOnPage(layer.page)) {
      const selected = this.store.isSelected(a.id);
      const custom = this.renderers.find((r) => r.kinds.includes(a.kind));
      if (custom) {
        const out = custom.render(a, { ...ctx, selected });
        if (!out) continue;
        const g = el("g", { "data-annot": a.id, "data-kind": a.kind, class: "mpdf-annot" });
        for (const node of Array.isArray(out) ? out : [out]) g.appendChild(node);
        content.appendChild(g);
      } else {
        content.appendChild(drawAnnotation(a, { zoom: this._zoom, selected, feetInches: this.feetInches }));
      }
    }
    if (this.draft.length && this.draftPage === layer.page && this.activeTool) {
      content.appendChild(drawDraft(this.activeTool.kind, this.draft, this._zoom));
    }
  }

  private wireStore(): void {
    const repaint = () => this.redraw();
    for (const ev of ["annot:added", "annot:updated", "annot:removed", "annot:reset", "annot:selected", "filter:changed"] as const) {
      this.bus.on(ev, repaint);
    }
  }

  // ---- page text -----------------------------------------------------------

  /**
   * Text for a page: the PDF's own text layer, or recognised text when it has none.
   *
   * This is the single seam every text consumer goes through — search, spec parsing, title-block
   * extraction. Putting it in the kernel is what lets an OCR plugin light all three up on a scanned
   * set without any of them knowing OCR exists.
   */
  async pageText(page: number): Promise<TextItem[]> {
    // A failure to read the native layer — an out-of-range page, a malformed one — must fall through
    // to recognised text rather than propagate. Callers here are indexers looping over every page,
    // and one bad page should not abort the sweep.
    let native: TextItem[] = [];
    try { native = (await this.doc?.textItems(page)) ?? []; }
    catch { native = []; }
    if (native.length) return native;
    return this.recognised.get(page) ?? [];
  }

  /** Supply recognised text for a page. Ignored while the page has real text of its own. */
  setRecognisedText(page: number, items: TextItem[]): void {
    this.recognised.set(page, items);
  }

  /** True when a page has neither a text layer nor recognised text — i.e. a scan awaiting OCR. */
  async needsText(page: number): Promise<boolean> {
    return (await this.pageText(page)).length === 0;
  }

  /** Pages that have been given recognised text. */
  recognisedPages(): number[] { return [...this.recognised.keys()].sort((a, b) => a - b); }

  // ---- text layer ----------------------------------------------------------

  /** The text layer for a page, if one was built. */
  textLayer(page: number): TextLayer | undefined { return this.layers.get(page)?.text; }

  /**
   * Arm or disarm text selection to match the active tool. Layers are built lazily here rather than
   * on load: a 400-page set would otherwise create hundreds of thousands of spans nobody selects.
   */
  private syncTextLayers(): void {
    const on = this.opts.textLayer !== false && this.activeTool?.input === "text-select";
    for (const layer of this.layers.values()) {
      if (on) void layer.text.build().then(() => layer.text.setScale(this._zoom));
      layer.text.setSelectable(on);
    }
    if (!on) clearSelection();
  }

  /** Read the current text selection from whichever page owns it. */
  private readSelection(): TextSelection | null {
    for (const layer of this.layers.values()) {
      const sel = layer.text.currentSelection();
      if (sel) return sel;
    }
    return null;
  }

  // ---- hit testing ---------------------------------------------------------

  /**
   * The topmost markup within `tolerance` *screen* pixels of a page-space point. Later markups win,
   * matching the paint order — the thing drawn on top is the thing you grab.
   */
  hitTest(page: number, p: Pt, tolerancePx = 6): Annotation | null {
    const tol = tolerancePx / this._zoom;
    const list = this.store.visibleOnPage(page);
    for (let i = list.length - 1; i >= 0; i--) {
      const a = list[i]!;
      if (this.hits(a, p, tol)) return a;
    }
    return null;
  }

  private hits(a: Annotation, p: Pt, tol: number): boolean {
    const pts = a.points;
    if (!pts.length) return false;
    if (POINT_KINDS.includes(a.kind)) {
      // Point markups get a generous target — a pin is drawn at screen scale, so its target is too.
      const r = a.kind === "pin" ? 18 / this._zoom : Math.max(tol, 10 / this._zoom);
      return pts.some((q) => Math.hypot(q.x - p.x, q.y - p.y) <= r);
    }
    if (BOX_KINDS.has(a.kind)) {
      if (pts.length < 2) return false;
      const b = bbox([pts[0]!, pts[1]!]);
      const inside = p.x >= b.x - tol && p.x <= b.x + b.w + tol && p.y >= b.y - tol && p.y <= b.y + b.h + tol;
      if (!inside) return false;
      // Filled shapes are grabbable anywhere; outlines only near the edge, so you can still click
      // through a large empty rectangle to what is underneath it.
      if (a.style?.fill || a.kind === "highlight") return true;
      const edge = distToPath(p, [{ x: b.x, y: b.y }, { x: b.x + b.w, y: b.y }, { x: b.x + b.w, y: b.y + b.h }, { x: b.x, y: b.y + b.h }], true);
      return edge <= tol * 2;
    }
    if (CLOSED_KINDS.has(a.kind)) {
      if (pointInPolygon(p, pts)) return true;
      return distToPath(p, pts, true) <= tol * 2;
    }
    return distToPath(p, pts, false) <= tol * 2;
  }

  // ---- gesture loop --------------------------------------------------------

  private wireInput(): void {
    const pages = this.el.pages;
    const scroll = this.el.scroll;

    const onDown = (e: PointerEvent) => this.onPointerDown(e);
    const onMove = (e: PointerEvent) => this.onPointerMove(e);
    const onUp = (e: PointerEvent) => this.onPointerUp(e);
    // A browser that claims a gesture mid-way (a scroll taking over, a system edge swipe) sends
    // pointercancel and never a pointerup. Without this the viewer is left mid-drag forever.
    const onCancel = (e: PointerEvent) => this.onPointerCancel(e);
    const onDbl = (e: MouseEvent) => this.onDoubleClick(e);
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      void this.setZoom(this._zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12), e);
    };
    const onScroll = () => {
      if (this.scrollRaf) return;
      this.scrollRaf = requestAnimationFrame(() => { this.scrollRaf = 0; this.updateVisible(); });
    };
    const onKey = (e: KeyboardEvent) => this.onKeyDown(e);

    pages.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    pages.addEventListener("dblclick", onDbl);
    scroll.addEventListener("wheel", onWheel, { passive: false });
    scroll.addEventListener("scroll", onScroll, { passive: true });
    this.el.root.addEventListener("keydown", onKey);
    this.el.root.tabIndex = 0;
    this.applyTouchAction();

    const ro = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(() => this.updateVisible())
      : null;
    ro?.observe(scroll);

    this.cleanups.push(() => {
      pages.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      pages.removeEventListener("dblclick", onDbl);
      scroll.removeEventListener("wheel", onWheel);
      scroll.removeEventListener("scroll", onScroll);
      this.el.root.removeEventListener("keydown", onKey);
      ro?.disconnect();
      if (this.scrollRaf) cancelAnimationFrame(this.scrollRaf);
    });
  }

  // ---- touch ---------------------------------------------------------------

  /**
   * Who owns a one-finger drag: the browser (scrolling) or the viewer (drawing).
   *
   * With a tool armed, a touch-drag has to reach the gesture loop, which means taking the gesture
   * away from the browser's scroller — otherwise the sheet pans and nothing is drawn. In select
   * mode the opposite is true: one finger should scroll, as it does everywhere else.
   *
   * `pinch-zoom` stays out of both, because the viewer implements zoom itself; letting the browser
   * also zoom would double-apply it against a canvas that is already re-rasterising.
   */
  private applyTouchAction(): void {
    this.el.pages.style.touchAction = this.activeTool ? "none" : "pan-x pan-y";
  }

  /** True while a pen is in use, so a touch contact is more likely a palm than a finger. */
  private palmRejected(): boolean {
    return this.opts.palmRejection !== false && Date.now() - this.lastPenAt < PEN_PALM_WINDOW_MS;
  }

  private touchMidpoint(): { x: number; y: number } {
    const pts = [...this.touches.values()];
    const n = pts.length || 1;
    return {
      x: pts.reduce((s, p) => s + p.x, 0) / n,
      y: pts.reduce((s, p) => s + p.y, 0) / n,
    };
  }

  private touchSpread(): number {
    const [a, b] = [...this.touches.values()];
    return a && b ? Math.hypot(b.x - a.x, b.y - a.y) : 0;
  }

  /** Begin a pinch once a second finger lands, abandoning any single-finger gesture in progress. */
  private beginPinch(): void {
    const distance = this.touchSpread();
    if (distance < 1) return;
    this.cancelDraft();
    this.gesture = null;
    const mid = this.touchMidpoint();
    this.pinch = {
      distance,
      zoom: this._zoom,
      page: this._page,
      anchor: this.clientToPage(mid.x, mid.y, this._page),
    };
  }

  /**
   * Track a pinch: scale from the ratio of finger spread, and pan by however far the midpoint
   * moved, so a two-finger gesture zooms and repositions in one motion the way every map does.
   *
   * Serialised, because `setZoom` is async. Fingers emit moves far faster than a re-raster
   * completes, and overlapping calls each read a scroll position the previous one has not yet
   * corrected — which shows up as the sheet crawling away from under the fingers. Only one update
   * runs at a time; a move arriving during it sets a flag so the newest finger positions are
   * applied as soon as it lands, rather than being dropped.
   */
  private updatePinch(): void {
    if (this.pinchBusy) { this.pinchPending = true; return; }
    const p = this.pinch;
    if (!p || this.touches.size < 2) return;
    const spread = this.touchSpread();
    if (spread < 1) return;

    const target = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, p.zoom * (spread / p.distance)));
    this.pinchBusy = true;
    void this.setZoom(target)
      .then(() => {
        // Put the page point that was under the fingers back under them, solved against the pinch
        // *start* rather than nudged each frame. Incremental corrections compound: coalesced moves
        // mean the intermediate states a per-frame delta assumes never actually happened, and the
        // sheet creeps out from under the fingers over a long pinch.
        const info = this.doc?.pageInfoSync(p.page);
        const layer = this.layers.get(p.page);
        if (!info || !layer || !p.anchor) return;
        const mid = this.touchMidpoint();
        const s = this.el.scroll;
        const rect = s.getBoundingClientRect();
        const local = this.pageToLocal(p.anchor, info.width, info.height);
        s.scrollLeft = layer.wrap.offsetLeft + local.x - (mid.x - rect.left);
        s.scrollTop = layer.wrap.offsetTop + local.y - (mid.y - rect.top);
      })
      .finally(() => {
        this.pinchBusy = false;
        if (this.pinchPending) { this.pinchPending = false; this.updatePinch(); }
      });
  }

  private endPinch(): void {
    if (this.touches.size >= 2) return;
    this.pinch = null;
    this.pinchPending = false;
  }

  private onPointerCancel(e: PointerEvent): void {
    // A rejected palm owns no gesture and no pinch; its cancellation must not end either, and the
    // set would otherwise keep the id forever, since a cancelled contact never sends a pointerup.
    if (this.rejectedTouches.delete(e.pointerId)) return;
    this.touches.delete(e.pointerId);
    this.endPinch();
    if (this.gesture?.pointerId === e.pointerId) {
      this.gesture = null;
      this.cancelDraft();
    }
  }

  /** Locate the page under an event and convert to page space. */
  private locate(e: { clientX: number; clientY: number; target: EventTarget | null }): { page: number; pt: Pt } | null {
    const node = e.target instanceof Element ? e.target.closest<HTMLElement>(".mpdf-page-wrap") : null;
    const page = node ? Number(node.dataset.page) : this._page;
    const layer = this.layers.get(page);
    const info = this.doc?.pageInfoSync(page);
    if (!layer || !info) return null;
    const rect = layer.overlay.getBoundingClientRect();
    return { page, pt: eventToPage(e, rect, this._zoom, info.width, info.height, this._rotation) };
  }

  private onPointerDown(e: PointerEvent): void {
    if (e.button !== 0) return;

    if (e.pointerType === "pen") {
      this.lastPenAt = Date.now();
      // A pen landing mid-pinch means the hand is resting; drop the touch state rather than let a
      // stale finger keep zooming.
      if (this.touches.size) { this.touches.clear(); this.pinch = null; }
    } else if (e.pointerType === "touch") {
      if (this.palmRejected()) { this.rejectedTouches.add(e.pointerId); return; }
      this.touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
      // Two fingers is always a pinch, whatever tool is armed — it is how you reposition mid-markup
      // without putting the tool down.
      if (this.touches.size >= 2) { this.beginPinch(); return; }
    }
    this.strokePressures = [];
    if (e.pointerType === "pen" && e.pressure > 0) this.strokePressures.push(e.pressure);

    this.el.root.focus({ preventScroll: true });
    const at = this.locate(e);
    if (!at) return;
    const tool = this.activeTool;

    if (!tool) { this.beginSelect(e, at.page, at.pt); return; }
    if (this.opts.readOnly) return;

    // A text-select tool has no geometry of its own; the browser owns the drag.
    if (tool.input === "text-select") return;

    this.draftPage = at.page;
    switch (tool.input) {
      case "click":
        this.draft = [at.pt];
        void this.commit(tool, e);
        break;
      case "drag":
        this.gesture = { mode: "draw", start: at.pt, page: at.page, pointerId: e.pointerId };
        this.draft = [at.pt, at.pt];
        this.el.pages.setPointerCapture?.(e.pointerId);
        break;
      case "freehand":
        this.gesture = { mode: "draw", start: at.pt, page: at.page, pointerId: e.pointerId };
        this.draft = [at.pt];
        this.el.pages.setPointerCapture?.(e.pointerId);
        break;
      case "poly": {
        // A poly gesture spans clicks; only reset when starting on a different page.
        if (this.draft.length && this.draftPage !== at.page) this.draft = [];
        this.draft.push(at.pt);
        const max = tool.maxPoints;
        if (max && this.draft.length >= max) void this.commit(tool, e);
        break;
      }
    }
    this.redraw(at.page);
  }

  private onPointerMove(e: PointerEvent): void {
    if (e.pointerType === "pen") this.lastPenAt = Date.now();
    if (e.pointerType === "touch") {
      if (!this.touches.has(e.pointerId)) return;      // a rejected palm, still sliding around
      this.touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (this.pinch) { this.updatePinch(); return; }
    }
    if (e.pointerType === "pen" && e.pressure > 0 && this.gesture?.mode === "draw") {
      this.strokePressures.push(e.pressure);
    }

    const g = this.gesture;
    if (!g) {
      // Live rubber-band for poly tools: the segment from the last vertex to the cursor.
      if (this.activeTool?.input === "poly" && this.draft.length) {
        const at = this.locate(e);
        if (at && at.page === this.draftPage) {
          const pts = [...this.draft, e.shiftKey ? snapAngle(this.draft[this.draft.length - 1]!, at.pt) : at.pt];
          this.paintDraftPreview(pts);
        }
      }
      return;
    }
    const at = this.locate(e);
    if (!at) return;

    if (g.mode === "draw") {
      const tool = this.activeTool;
      if (!tool) return;
      if (tool.input === "freehand") this.draft.push(at.pt);
      else this.draft = [g.start, e.shiftKey ? snapAngle(g.start, at.pt) : at.pt];
      this.redraw(g.page);
      return;
    }

    if (g.mode === "move") {
      const dx = at.pt.x - g.start.x, dy = at.pt.y - g.start.y;
      for (const [id, orig] of g.originals) {
        this.store.update(id, { points: orig.map((p) => ({ x: p.x + dx, y: p.y + dy })) }, { bump: false, undoable: false });
      }
      g.moved = true;
      return;
    }

    if (g.mode === "vertex") {
      const orig = g.originals.get(g.id);
      if (!orig) return;
      const pts = orig.map((p, i) => (i === g.index ? at.pt : p));
      this.store.update(g.id, { points: pts }, { bump: false, undoable: false });
      g.moved = true;
    }
  }

  private onPointerUp(e: PointerEvent): void {
    if (e.pointerType === "pen") this.lastPenAt = Date.now();
    if (e.pointerType === "touch") {
      // A palm was never tracked, so its release must not end a stroke the pen is still drawing —
      // however long the stylus has been resting between marks.
      if (this.rejectedTouches.delete(e.pointerId)) return;
      this.touches.delete(e.pointerId);
      const wasPinching = Boolean(this.pinch);
      this.endPinch();
      // Lifting one finger of a pinch must not commit whatever the other finger is over.
      if (wasPinching) return;
    }

    const tool = this.activeTool;
    if (tool?.input === "text-select") {
      // Let the browser finish settling the selection before reading it.
      setTimeout(() => void this.commitTextSelection(tool, e), 0);
      return;
    }
    const g = this.gesture;
    if (!g) return;
    this.gesture = null;
    this.el.pages.releasePointerCapture?.(e.pointerId);

    if (g.mode === "draw") {
      const tool = this.activeTool;
      if (!tool) { this.cancelDraft(); return; }
      if (tool.input === "freehand") this.draft = simplify(this.draft, 0.6 / this._zoom);
      // A click that never moved is not a drag — discard rather than create a zero-size markup.
      const b = bbox(this.draft);
      if (tool.input === "drag" && b.w * this._zoom < 3 && b.h * this._zoom < 3) { this.cancelDraft(); return; }
      if (tool.input === "freehand" && this.draft.length < 2) { this.cancelDraft(); return; }
      void this.commit(tool, e);
      return;
    }

    // A move/vertex drag was applied frame-by-frame without history; record one step for the whole
    // gesture now, so undo reverses the drag rather than the last pixel of it.
    if (g.moved) {
      const patches = [...g.originals.keys()]
        .map((id) => ({ id, annot: this.store.get(id) }))
        .filter((x): x is { id: string; annot: Annotation } => !!x.annot);
      // Restore the pre-drag geometry silently, then re-apply it as one undoable update.
      for (const { id } of patches) {
        const orig = g.originals.get(id)!;
        this.store.update(id, { points: orig }, { bump: false, undoable: false });
      }
      this.store.updateMany(patches.map(({ id, annot }) => ({ id, patch: { points: annot.points } })));
    }
  }

  private onDoubleClick(e: MouseEvent): void {
    const tool = this.activeTool;
    if (tool?.input === "poly" && this.draft.length >= (tool.minPoints ?? 2)) {
      e.preventDefault();
      void this.commit(tool, e);
      return;
    }
    if (tool) return;
    const at = this.locate(e);
    if (!at) return;
    const hit = this.hitTest(at.page, at.pt);
    if (hit) this.bus.emit("annot:activated", { annot: hit });
  }

  private onKeyDown(e: KeyboardEvent): void {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "z") {
      e.preventDefault();
      if (e.shiftKey) this.store.redo(); else this.store.undo();
      return;
    }
    if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); this.store.redo(); return; }
    if (mod && e.key.toLowerCase() === "a") {
      e.preventDefault();
      this.store.select(this.store.visibleOnPage(this._page).map((a) => a.id));
      return;
    }
    if (e.key === "Escape") {
      if (this.draft.length) this.cancelDraft();
      else if (this.activeToolId) this.setTool(null);
      else this.store.select(null);
      return;
    }
    if (e.key === "Enter") {
      const tool = this.activeTool;
      if (tool?.input === "poly" && this.draft.length >= (tool.minPoints ?? 2)) { e.preventDefault(); void this.commit(tool, e); }
      return;
    }
    if ((e.key === "Delete" || e.key === "Backspace") && !this.opts.readOnly) {
      if (this.store.selectedIds().length) { e.preventDefault(); this.store.removeSelected(); }
      return;
    }
    if (mod || e.altKey) return;
    // Single-key tool and action shortcuts.
    for (const t of this.tools.values()) if (t.shortcut === e.key) { e.preventDefault(); this.setTool(t.id); return; }
    for (const a of this.actions.values()) if (a.shortcut === e.key) { e.preventDefault(); void this.runAction(a.id); return; }
  }

  private beginSelect(e: PointerEvent, page: number, pt: Pt): void {
    const hit = this.hitTest(page, pt);
    if (!hit) { if (!e.shiftKey) this.store.select(null); return; }

    // Grabbing a vertex handle of an already-selected markup edits geometry; grabbing its body moves it.
    if (this.store.isSelected(hit.id) && !e.shiftKey) {
      const idx = this.nearestVertex(hit, pt, 8 / this._zoom);
      if (idx >= 0 && !hit.locked && !this.opts.readOnly) {
        this.gesture = { mode: "vertex", id: hit.id, index: idx, start: pt, page, pointerId: e.pointerId, moved: false, originals: new Map([[hit.id, hit.points]]) };
        this.el.pages.setPointerCapture?.(e.pointerId);
        return;
      }
    }
    if (!this.store.isSelected(hit.id)) this.store.select(hit.id, e.shiftKey);
    if (this.opts.readOnly) return;
    const originals = new Map<string, Pt[]>();
    for (const a of this.store.selected()) if (!a.locked) originals.set(a.id, a.points);
    if (!originals.size) return;
    this.gesture = { mode: "move", start: pt, page, pointerId: e.pointerId, moved: false, originals };
    this.el.pages.setPointerCapture?.(e.pointerId);
  }

  private nearestVertex(a: Annotation, p: Pt, tol: number): number {
    let best = -1, bestD = tol;
    a.points.forEach((q, i) => {
      const d = Math.hypot(q.x - p.x, q.y - p.y);
      if (d <= bestD) { bestD = d; best = i; }
    });
    return best;
  }

  /** Repaint only the in-progress preview, without rebuilding committed markups. */
  private paintDraftPreview(pts: Pt[]): void {
    const layer = this.layers.get(this.draftPage);
    const tool = this.activeTool;
    if (!layer || !tool) return;
    layer.content.querySelector(".mpdf-draft")?.remove();
    layer.content.appendChild(drawDraft(tool.kind, pts, this._zoom));
  }

  private cancelDraft(): void {
    if (!this.draft.length) return;
    const page = this.draftPage;
    this.draft = [];
    this.gesture = null;
    this.redraw(page);
    this.bus.emit("tool:draft", null);
  }

  /** Turn the collected gesture into a stored annotation. */
  private async commit(tool: ToolDef, e: { shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean }): Promise<void> {
    const points = this.draft;
    const page = this.draftPage;
    const min = tool.minPoints ?? (tool.input === "click" ? 1 : 2);
    if (points.length < min) { this.cancelDraft(); return; }

    if (tool.needsCalibration && !this.store.calibration(page)) {
      this.bus.emit("notice", { level: "error", message: "Set the drawing scale before measuring — use Calibrate or pick a scale preset." });
      this.cancelDraft();
      return;
    }

    this.draft = [];
    let draft: AnnotationDraft | null;
    try {
      draft = tool.create
        ? await tool.create({
            points, page, viewer: this,
            modifiers: { shift: e.shiftKey, alt: e.altKey, ctrl: e.ctrlKey, meta: e.metaKey },
          })
        : { kind: tool.kind, points, page };
    } catch (err) {
      this.bus.emit("notice", { level: "error", message: `${tool.label} failed: ${(err as Error).message}` });
      this.redraw(page);
      return;
    }
    if (!draft) { this.redraw(page); return; }

    // Measurements get their quantity from the kernel so every tool computes it the same way.
    if (!draft.quantity) {
      const q = measure(draft.kind, draft.points, this.store.calibration(page));
      if (q) draft.quantity = q;
    }
    this.applyPenPressure(draft);
    const annot = this.store.add({ ...draft, page: draft.page ?? page });
    if (!tool.sticky) this.setTool(null);
    this.redraw(page);
    // Undefined means the policy refused. The store has already announced why via the audit sink
    // and the notice; there is simply nothing to select.
    if (annot) this.store.select(annot.id);
  }

  /**
   * Commit a `text-select` tool from the live DOM selection. The markup's `points` are the union
   * box, so every existing consumer (hit-testing, flatten, XFDF) works unchanged; the per-line quads
   * ride in `ext.quads` for renderers that want to draw one band per line.
   */
  private async commitTextSelection(
    tool: ToolDef,
    e: { shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean },
  ): Promise<void> {
    const selection = this.readSelection();
    if (!selection || !selection.text.trim()) return;
    const b = selection.bounds;
    const points: Pt[] = [{ x: b.x, y: b.y }, { x: b.x + b.w, y: b.y + b.h }];

    let draft: AnnotationDraft | null;
    try {
      draft = tool.create
        ? await tool.create({
            points, page: selection.page, viewer: this, selection,
            modifiers: { shift: e.shiftKey, alt: e.altKey, ctrl: e.ctrlKey, meta: e.metaKey },
          })
        : { kind: tool.kind, points, page: selection.page };
    } catch (err) {
      this.bus.emit("notice", { level: "error", message: `${tool.label} failed: ${(err as Error).message}` });
      return;
    }
    if (!draft) return;

    draft.ext = { ...draft.ext, quads: selection.quads, selectedText: selection.text };
    if (!draft.text && !draft.subject) draft.subject = truncate(selection.text, 80);
    const annot = this.store.add({ ...draft, page: draft.page ?? selection.page });
    clearSelection();
    if (!tool.sticky) this.setTool(null);
    if (!annot) return;
    this.redraw(annot.page);
    this.store.select(annot.id);
  }

  /**
   * Fold stylus pressure into a freehand stroke.
   *
   * The samples are kept on the record regardless — they are what a future variable-width renderer
   * would need, and discarding them at capture time would make that unrecoverable. The visible
   * effect today is a single width scaled by the mean, which is a real difference between a light
   * annotation stroke and a deliberate one without pretending to be a paint program.
   */
  private applyPenPressure(draft: AnnotationDraft): void {
    const samples = this.strokePressures;
    this.strokePressures = [];
    if (draft.kind !== "ink" || samples.length < 2) return;

    const mean = samples.reduce((s, p) => s + p, 0) / samples.length;
    // Devices that cannot measure pressure report a flat 0.5 for every sample; treating that as a
    // real reading would silently thin every stroke on a mouse or a basic stylus.
    const varies = samples.some((p) => Math.abs(p - mean) > 0.02);
    draft.ext = { ...draft.ext, pressures: samples };
    if (!varies || this.opts.penPressure === false) return;

    const base = draft.style?.width ?? 1.8;
    draft.style = { ...draft.style, width: Math.max(0.4, base * (0.5 + mean)) };
  }

  /** Programmatic creation — the scripting/test surface, and how a host imports markups. */
  addAnnotation(draft: AnnotationDraft): Annotation {
    if (!draft.quantity) {
      const q = measure(draft.kind, draft.points, this.store.calibration(draft.page));
      if (q) draft.quantity = q;
    }
    const a = this.store.add(draft);
    // This is the host's scripting entry point, where a silent no-op returning `undefined` would
    // surface later as an unrelated error. A tool commit can shrug a refusal off; a caller that
    // asked for a markup and got nothing needs to be told.
    if (!a) throw new PermissionError("Creating a markup was refused by the permission check.");
    this.redraw(draft.page);
    return a;
  }

  /** Recompute every measurement on a page after its calibration changed. */
  recalculatePage(page: number): void {
    const cal = this.store.calibration(page);
    if (!cal) return;
    const patches = this.store.onPage(page)
      .filter((a) => a.quantity)
      .map((a) => ({ id: a.id, patch: { quantity: measure(a.kind, a.points, cal) ?? a.quantity } }));
    if (patches.length) this.store.updateMany(patches);
  }

  /** Convert a client point to page space on a given page — for hosts driving the viewer. */
  clientToPage(clientX: number, clientY: number, page = this._page): Pt | null {
    const layer = this.layers.get(page);
    const info = this.doc?.pageInfoSync(page);
    if (!layer || !info) return null;
    const rect = layer.overlay.getBoundingClientRect();
    return displayToPage(
      { x: (clientX - rect.left) / this._zoom, y: (clientY - rect.top) / this._zoom },
      info.width, info.height, this._rotation,
    );
  }

  /** Subscribe to a viewer event. Sugar for `viewer.bus.on`. */
  on<K extends EventName>(name: K, fn: Handler<K>): Unsubscribe {
    return this.bus.on(name, fn);
  }
}

type GestureState =
  | { mode: "draw"; start: Pt; page: number; pointerId: number }
  | { mode: "move"; start: Pt; page: number; pointerId: number; moved: boolean; originals: Map<string, Pt[]> }
  | { mode: "vertex"; id: string; index: number; start: Pt; page: number; pointerId: number; moved: boolean; originals: Map<string, Pt[]> };

const BOX_KINDS = new Set<AnnotKind>(["rect", "ellipse", "highlight", "underline", "strikeout"]);
const CLOSED_KINDS = new Set<AnnotKind>(["polygon", "area", "volume", "cloud"]);

const truncate = (t: string, n: number): string =>
  t.length > n ? `${t.slice(0, n - 1)}…` : t;

const rangeOf = (n: number): number[] => Array.from({ length: n }, (_, i) => i + 1);

/** Build the viewer's DOM skeleton. */
function buildShell(container: HTMLElement): Viewer["el"] {
  container.innerHTML = "";
  const root = document.createElement("div");
  root.className = "mpdf-root";
  // Landmarks, so a screen-reader user can jump between the toolbar, the drawing and the panels
  // instead of arrowing through everything in between.
  root.setAttribute("role", "application");
  root.setAttribute("aria-label", "Drawing review");

  const toolbar = document.createElement("div");
  toolbar.className = "mpdf-toolbar";
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "Markup tools");

  const body = document.createElement("div");
  body.className = "mpdf-body";

  const left = document.createElement("aside");
  left.className = "mpdf-side mpdf-side-left";
  left.setAttribute("aria-label", "Sheets and navigation");

  const scroll = document.createElement("div");
  scroll.className = "mpdf-scroll";
  scroll.setAttribute("role", "region");
  scroll.setAttribute("aria-label", "Drawing");

  const pages = document.createElement("div");
  pages.className = "mpdf-pages";
  pages.style.setProperty("--mpdf-page-gap", `${PAGE_GAP}px`);

  const right = document.createElement("aside");
  right.className = "mpdf-side mpdf-side-right";
  right.setAttribute("aria-label", "Markups and review");

  const status = document.createElement("div");
  status.className = "mpdf-status";
  status.setAttribute("role", "status");
  scroll.appendChild(pages);
  body.append(left, scroll, right);
  root.append(toolbar, body, status);
  container.appendChild(root);
  return { root, toolbar, body, left, scroll, pages, right, status };
}
