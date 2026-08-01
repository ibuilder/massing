/**
 * The annotation store: the single source of truth for markups, selection, calibration and sheet
 * metadata, with an undo stack over it.
 *
 * Everything mutates through here so that (a) every change emits exactly one event, (b) derived
 * fields (`nx`/`ny`, `version`, `updatedAt`) are always consistent, and (c) undo is a property of
 * the store rather than something each tool has to remember to implement.
 */
import type { EventBus } from "./events";
import type { Policy } from "./policy";
import { bbox } from "./geometry";
import { matchesFilter } from "./filter";
import type {
  Annotation, AnnotationDraft, AnnotFilter, Calibration, Pt, SavedView, SheetMeta,
} from "./types";

/** One reversible step. Coarser than a single field write — a drag is one entry, not sixty. */
type Patch =
  | { t: "add"; annots: Annotation[] }
  | { t: "remove"; annots: Annotation[] }
  | { t: "update"; before: Annotation[]; after: Annotation[] }
  | { t: "reset"; before: Annotation[]; after: Annotation[] };

export interface StoreOpts {
  bus: EventBus;
  /**
   * Permission and audit gate.
   *
   * Sits here rather than in the UI because this is the one seam every mutation crosses — tool,
   * keyboard, import, adapter, host script. A check in the toolbar guards the toolbar.
   */
  policy?: Policy;
  /** Who is authoring. Read at mutation time so a host can change it mid-session. */
  author: () => string;
  org?: () => string | undefined;
  /** Page box lookup (PDF points at scale 1), for the normalised anchor. */
  pageSize: (page: number) => { width: number; height: number } | undefined;
  /** Sheet key for a page — lets markups follow a sheet number across re-issues. */
  sheetIdFor?: (page: number) => string;
  /** Depth of the undo stack. */
  undoLimit?: number;
}

let idSeq = 0;
/** Collision-resistant id without pulling in a uuid dep. `crypto.randomUUID` when available. */
export function makeId(prefix = "an"): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return `${prefix}_${c.randomUUID()}`;
  return `${prefix}_${Date.now().toString(36)}${(idSeq++).toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

export class AnnotationStore {
  private items = new Map<string, Annotation>();
  private selection = new Set<string>();
  private calibrations = new Map<number, Calibration>();   // page → calibration; key 0 = default
  private sheets = new Map<number, SheetMeta>();
  private views: SavedView[] = [];
  private filter: AnnotFilter = {};
  private undoStack: Patch[] = [];
  private redoStack: Patch[] = [];
  /** Set while applying an undo/redo so those applications do not re-enter the stack. */
  private replaying = false;

  constructor(private o: StoreOpts) {}

  private get bus() { return this.o.bus; }
  private get limit() { return this.o.undoLimit ?? 100; }

  // ---- reads ---------------------------------------------------------------

  get(id: string): Annotation | undefined { return this.items.get(id); }
  get size(): number { return this.items.size; }

  /** Every markup, in creation order. */
  all(): Annotation[] { return [...this.items.values()]; }

  /** Markups on a page, in creation order. */
  onPage(page: number): Annotation[] { return this.all().filter((a) => a.page === page); }

  /** Markups passing the active filter (or an explicit one). */
  visible(filter = this.filter): Annotation[] {
    return this.all().filter((a) => matchesFilter(a, filter));
  }

  /** Markups on a page passing the active filter — what the overlay draws. */
  visibleOnPage(page: number): Annotation[] {
    return this.visible().filter((a) => a.page === page);
  }

  getFilter(): AnnotFilter { return { ...this.filter }; }

  setFilter(f: AnnotFilter): void {
    this.filter = { ...f };
    this.bus.emit("filter:changed", { filter: this.getFilter() });
  }

  // ---- selection -----------------------------------------------------------

  selected(): Annotation[] {
    return [...this.selection].map((id) => this.items.get(id)).filter((a): a is Annotation => !!a);
  }

  selectedIds(): string[] { return [...this.selection]; }

  isSelected(id: string): boolean { return this.selection.has(id); }

  select(ids: string[] | string | null, additive = false): void {
    const next = ids === null ? [] : Array.isArray(ids) ? ids : [ids];
    if (!additive) this.selection.clear();
    for (const id of next) {
      if (!this.items.has(id)) continue;
      if (additive && this.selection.has(id)) this.selection.delete(id);   // toggle
      else this.selection.add(id);
    }
    this.bus.emit("annot:selected", { ids: this.selectedIds() });
  }

  // ---- calibration ---------------------------------------------------------

  /** Calibration for a page, falling back to the document default. */
  calibration(page: number): Calibration | undefined {
    return this.calibrations.get(page) ?? this.calibrations.get(0);
  }

  setCalibration(cal: Calibration | null, page = 0): void {
    // Re-deriving every measurement on a sheet from a wrong scale is one of the more expensive
    // mistakes available here, which is why it is a permission of its own.
    if (this.o.policy && !this.o.policy.allows("calibrate")) return;
    if (cal) this.calibrations.set(page, { ...cal, page });
    else this.calibrations.delete(page);
    this.bus.emit("calibration:changed", { calibration: cal, page });
  }

  allCalibrations(): Calibration[] { return [...this.calibrations.values()]; }

  // ---- sheet metadata ------------------------------------------------------

  sheet(page: number): SheetMeta | undefined { return this.sheets.get(page); }

  setSheet(meta: SheetMeta): void {
    if (this.o.policy && !this.o.policy.allows("sheet:edit")) return;
    this.sheets.set(meta.page, meta);
    this.bus.emit("sheet:changed", { meta });
  }

  allSheets(): SheetMeta[] { return [...this.sheets.values()].sort((a, b) => a.page - b.page); }

  // ---- saved views ---------------------------------------------------------

  savedViews(): SavedView[] { return [...this.views]; }

  addView(v: Omit<SavedView, "id" | "createdAt">): SavedView {
    const view: SavedView = { ...v, id: makeId("vw"), createdAt: new Date().toISOString() };
    this.views.push(view);
    this.bus.emit("view:saved", { view });
    return view;
  }

  removeView(id: string): void { this.views = this.views.filter((v) => v.id !== id); }

  // ---- mutations -----------------------------------------------------------

  /** Create a markup from a tool's draft. */
  add(draft: AnnotationDraft): Annotation | undefined {
    const annot = this.materialise(draft);
    if (this.o.policy && !this.o.policy.allows("markup:create", annot)) return undefined;
    this.items.set(annot.id, annot);
    this.push({ t: "add", annots: [annot] });
    this.bus.emit("annot:added", { annot });
    return annot;
  }

  /** Create several as one undo step (paste, import, migration). */
  addMany(drafts: AnnotationDraft[]): Annotation[] {
    const policy = this.o.policy;
    const made = drafts.map((d) => this.materialise(d))
      .filter((a) => !policy || policy.allows("import", a));
    for (const a of made) this.items.set(a.id, a);
    this.push({ t: "add", annots: made });
    for (const annot of made) this.bus.emit("annot:added", { annot });
    return made;
  }

  /**
   * Patch a markup. `bump` false suppresses the version/`updatedAt` bump — used by the drag handler
   * for intermediate frames so a gesture produces one logical revision, not one per pointer move.
   */
  update(id: string, patch: Partial<Annotation>, opts: { bump?: boolean; undoable?: boolean } = {}): Annotation | undefined {
    const before = this.items.get(id);
    if (!before) return undefined;
    if (this.o.policy) {
      // *Every* capability the patch implies, not whichever one it looks most like. A status change
      // is its own permission — a reviewer may close an issue without being allowed to reword it —
      // but picking a single capability let a patch carrying both slip the other one past the gate:
      // `{ status: "resolved", subject: "hijacked" }` was checked only against `markup:status`.
      const changesStatus = patch.status !== undefined && patch.status !== before.status;
      // Any other key is an edit. Store-managed fields are excluded because the store writes them
      // itself on every mutation, so their presence says nothing about intent.
      const MANAGED = new Set(["id", "version", "updatedAt"]);
      const changesContent = Object.keys(patch).some((k) => k !== "status" && !MANAGED.has(k));

      if (changesStatus && !this.o.policy.allows("markup:status", before)) return undefined;
      if (changesContent && !this.o.policy.allows("markup:edit", before)) return undefined;
      // Neither: nothing to authorise, and nothing to do.
    }
    if (before.locked && !("locked" in patch)) return before;
    const after = this.derive({ ...before, ...patch, id: before.id });
    if (opts.bump !== false) {
      after.version = before.version + 1;
      after.updatedAt = new Date().toISOString();
    }
    this.items.set(id, after);
    if (opts.undoable !== false) this.push({ t: "update", before: [before], after: [after] });
    this.bus.emit("annot:updated", { annot: after, before });
    return after;
  }

  /** Patch several as one undo step. */
  updateMany(patches: { id: string; patch: Partial<Annotation> }[]): Annotation[] {
    const before: Annotation[] = [], after: Annotation[] = [];
    for (const { id, patch } of patches) {
      const prev = this.items.get(id);
      if (!prev || prev.locked) continue;
      const next = this.derive({ ...prev, ...patch, id: prev.id });
      next.version = prev.version + 1;
      next.updatedAt = new Date().toISOString();
      this.items.set(id, next);
      before.push(prev); after.push(next);
    }
    if (!after.length) return [];
    this.push({ t: "update", before, after });
    for (let i = 0; i < after.length; i++) this.bus.emit("annot:updated", { annot: after[i]!, before: before[i]! });
    return after;
  }

  remove(ids: string[] | string): Annotation[] {
    const list = (Array.isArray(ids) ? ids : [ids])
      .map((id) => this.items.get(id))
      .filter((a): a is Annotation => !!a && !a.locked)
      .filter((a) => !this.o.policy || this.o.policy.allows("markup:delete", a));
    if (!list.length) return [];
    for (const a of list) { this.items.delete(a.id); this.selection.delete(a.id); }
    this.push({ t: "remove", annots: list });
    for (const annot of list) this.bus.emit("annot:removed", { annot });
    if (list.length) this.bus.emit("annot:selected", { ids: this.selectedIds() });
    return list;
  }

  removeSelected(): Annotation[] { return this.remove(this.selectedIds()); }

  /**
   * Replace the whole set — a load, or a revision migration. Annotations arriving from a store are
   * already materialised, so their ids and versions are preserved.
   */
  reset(annots: Annotation[], opts: { undoable?: boolean } = {}): void {
    const before = this.all();
    this.items.clear();
    this.selection.clear();
    for (const a of annots) this.items.set(a.id, this.derive(a));
    if (opts.undoable !== false) this.push({ t: "reset", before, after: this.all() });
    this.bus.emit("annot:reset", { count: this.items.size });
  }

  /** Merge incoming records by id, newest `version` wins. The sync path. */
  merge(incoming: Annotation[]): { added: number; updated: number } {
    let added = 0, updated = 0;
    for (const a of incoming) {
      const mine = this.items.get(a.id);
      if (!mine) { this.items.set(a.id, this.derive(a)); added++; }
      else if ((a.version ?? 0) > (mine.version ?? 0)) { this.items.set(a.id, this.derive(a)); updated++; }
    }
    if (added || updated) this.bus.emit("annot:reset", { count: this.items.size });
    return { added, updated };
  }

  // ---- undo / redo ---------------------------------------------------------

  get canUndo(): boolean { return this.undoStack.length > 0; }
  get canRedo(): boolean { return this.redoStack.length > 0; }

  undo(): void {
    const p = this.undoStack.pop();
    if (!p) return;
    this.replaying = true;
    this.apply(p, true);
    this.replaying = false;
    this.redoStack.push(p);
  }

  redo(): void {
    const p = this.redoStack.pop();
    if (!p) return;
    this.replaying = true;
    this.apply(p, false);
    this.replaying = false;
    this.undoStack.push(p);
  }

  /** Drop history — after a load, when the prior document's steps are meaningless. */
  clearHistory(): void { this.undoStack = []; this.redoStack = []; }

  private push(p: Patch): void {
    if (this.replaying) return;
    this.undoStack.push(p);
    if (this.undoStack.length > this.limit) this.undoStack.shift();
    this.redoStack = [];                      // a new edit forks the timeline
  }

  private apply(p: Patch, reverse: boolean): void {
    const add = (list: Annotation[]) => {
      for (const a of list) this.items.set(a.id, a);
      for (const annot of list) this.bus.emit("annot:added", { annot });
    };
    const del = (list: Annotation[]) => {
      for (const a of list) { this.items.delete(a.id); this.selection.delete(a.id); }
      for (const annot of list) this.bus.emit("annot:removed", { annot });
    };
    switch (p.t) {
      case "add": if (reverse) del(p.annots); else add(p.annots); break;
      case "remove": if (reverse) add(p.annots); else del(p.annots); break;
      case "update": {
        const list = reverse ? p.before : p.after;
        const other = reverse ? p.after : p.before;
        for (let i = 0; i < list.length; i++) {
          this.items.set(list[i]!.id, list[i]!);
          this.bus.emit("annot:updated", { annot: list[i]!, before: other[i]! });
        }
        break;
      }
      case "reset": {
        const list = reverse ? p.before : p.after;
        this.items.clear();
        this.selection.clear();
        for (const a of list) this.items.set(a.id, a);
        this.bus.emit("annot:reset", { count: this.items.size });
        break;
      }
    }
  }

  // ---- derivation ----------------------------------------------------------

  /** Fill identity + defaults for a fresh draft. */
  private materialise(d: AnnotationDraft): Annotation {
    const now = new Date().toISOString();
    // Caller fields first, then the resolved defaults — so an explicit `undefined` in the draft
    // can't punch a hole through a default, and `points` is always our own copy.
    const annot: Annotation = {
      ...stripUndefined(d),
      id: d.id ?? makeId(),
      kind: d.kind,
      sheetId: d.sheetId ?? this.o.sheetIdFor?.(d.page) ?? String(d.page),
      page: d.page,
      points: d.points.map((p) => ({ x: p.x, y: p.y })),
      author: d.author ?? this.o.author(),
      org: d.org ?? this.o.org?.(),
      createdAt: d.createdAt ?? now,
      updatedAt: d.updatedAt ?? now,
      version: d.version ?? 1,
      status: d.status ?? "open",
    };
    return this.derive(annot);
  }

  /** Recompute the fields that are a function of the others. */
  private derive(a: Annotation): Annotation {
    const size = this.o.pageSize(a.page);
    const anchor: Pt = a.points[0] ?? { x: 0, y: 0 };
    const out: Annotation = { ...a, points: a.points.map((p) => ({ x: p.x, y: p.y })) };
    if (size && size.width > 0 && size.height > 0) {
      out.nx = anchor.x / size.width;
      out.ny = anchor.y / size.height;
    }
    return out;
  }

  /** Bounding box of a markup in page space — the hit-test and zoom-to-markup primitive. */
  static boundsOf(a: Annotation): { x: number; y: number; w: number; h: number } {
    return bbox(a.points);
  }
}

/** `{...draft}` would splat explicit `undefined`s over the defaults; this stops that. */
function stripUndefined<T extends object>(o: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(o)) if (v !== undefined) out[k] = v;
  return out as Partial<T>;
}
