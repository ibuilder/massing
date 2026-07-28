/**
 * A typed event bus. Every cross-plugin conversation goes through here — plugins never import each
 * other. That is what keeps the extension points stable while the plugin set churns.
 */
import type { Annotation, AnnotFilter, Calibration, SavedView, SheetMeta } from "./types";

/** The event map. Adding an event here is the only way to add one — no string-typed `emit`. */
export interface ViewerEvents {
  /** A document finished loading; `pages` is its page count. */
  "doc:loaded": { name: string; pages: number; fingerprint: string };
  "doc:closed": void;
  /** The visible page changed (continuous scroll reports the page most in view). */
  "page:changed": { page: number };
  /** A page finished painting to its canvas. */
  "page:rendered": { page: number; scale: number };
  /** Zoom / pan / rotation changed. */
  "view:changed": { zoom: number; page: number; rotation: number };

  /** The active tool changed. `id` is the `ToolDef.id`, `null` for the default select tool. */
  "tool:changed": { id: string | null };
  /** A tool is mid-gesture and wants the overlay repainted with `draft` geometry. */
  "tool:draft": { id: string; points: { x: number; y: number }[] } | null;

  "annot:added": { annot: Annotation };
  "annot:updated": { annot: Annotation; before: Annotation };
  "annot:removed": { annot: Annotation };
  /** Bulk replacement (load, undo, import). Consumers should re-read the whole store. */
  "annot:reset": { count: number };
  "annot:selected": { ids: string[] };
  /** A markup was activated (double-click / list click) — the cue to open a detail panel. */
  "annot:activated": { annot: Annotation };

  "filter:changed": { filter: AnnotFilter };
  "calibration:changed": { calibration: Calibration | null; page: number };
  "sheet:changed": { meta: SheetMeta };
  "view:saved": { view: SavedView };

  /** Persistence lifecycle, so a host can show a sync indicator. */
  "sync:state": { state: "idle" | "saving" | "offline" | "error"; pending: number; message?: string };
  /**
   * Stored markups have finished loading into the store — or failed to.
   *
   * Restore is asynchronous and lands well after `doc:loaded`, silently replacing the whole store
   * when it does. Anything that writes markups on open (a host seeding a review, a test) has to wait
   * for this or watch its work get overwritten.
   */
  "markups:restored": { count: number; ok: boolean };

  /** Anything worth telling the user. Hosts wire this to their own toast system. */
  notice: { level: "info" | "success" | "warn" | "error"; message: string };
}

export type EventName = keyof ViewerEvents;
export type Handler<K extends EventName> = (payload: ViewerEvents[K]) => void;

/** Unsubscribe. */
export type Unsubscribe = () => void;

export class EventBus {
  private map = new Map<EventName, Set<(p: never) => void>>();

  on<K extends EventName>(name: K, fn: Handler<K>): Unsubscribe {
    let set = this.map.get(name);
    if (!set) { set = new Set(); this.map.set(name, set); }
    set.add(fn as (p: never) => void);
    return () => { set!.delete(fn as (p: never) => void); };
  }

  /** Subscribe for exactly one delivery. */
  once<K extends EventName>(name: K, fn: Handler<K>): Unsubscribe {
    const off = this.on(name, (p) => { off(); fn(p); });
    return off;
  }

  emit<K extends EventName>(name: K, payload: ViewerEvents[K]): void {
    const set = this.map.get(name);
    if (!set) return;
    // Copy first: a handler that unsubscribes (or subscribes) during dispatch must not corrupt
    // the iteration, and one that throws must not silence the rest.
    for (const fn of [...set]) {
      try { (fn as Handler<K>)(payload); }
      catch (e) { console.error(`[massing-pdf] handler for "${String(name)}" threw`, e); }
    }
  }

  /** Drop every subscription — called on viewer teardown. */
  clear(): void { this.map.clear(); }
}
