/**
 * Wires the annotation store to a storage adapter.
 *
 * Saves are debounced and coalesced per annotation id: dragging a markup produces one write, not
 * one per frame. Inbound changes from other people are merged by version rather than applied
 * wholesale, so a colleague's save never clobbers an edit in progress locally.
 */
import { definePlugin } from "../core/plugin";
import { ConflictError, type Mutation, type StorageAdapter, type StoreKey } from "../adapters/types";
import type { Annotation } from "../core/types";
import type { Viewer } from "../core/viewer";

/** Both sides of a rejected write. */
export interface Conflict {
  id: string;
  /** What was being written. */
  mine?: Annotation;
  /** What the server holds now. */
  theirs?: Annotation;
}

export interface PersistenceOptions {
  adapter: StorageAdapter;
  /** Identify the markup set. Called after the document loads, so it can use the fingerprint. */
  key: (viewer: Viewer) => StoreKey;
  /** Coalescing window, ms. */
  debounceMs?: number;
  /** Subscribe to other people's changes when the adapter supports it. */
  live?: boolean;
  /** Load the stored set on document open. */
  autoLoad?: boolean;
  /**
   * Ceiling for the retry backoff after a failed save, ms.
   *
   * A rejected batch is put back on the queue and retried, doubling from the debounce interval up
   * to this. Without a ceiling a long outage would back off past any useful window; without the
   * backoff a dead server is polled continuously.
   */
  maxRetryMs?: number;
  /**
   * How to settle a write the server rejected because someone else edited the markup first.
   *
   * `theirs` (the default) keeps the server's copy and discards the local edit. `mine` re-applies
   * the local edit on top of the server's version — last-writer-wins, but at least deliberately.
   * `ask` hands both sides to `onConflict`.
   */
  onConflictResolve?: "theirs" | "mine" | "ask";
  /**
   * Called with both sides of each conflict. Return the annotation to keep, or `null` to accept the
   * server's copy. Only consulted when `onConflictResolve` is `ask`.
   */
  onConflict?: (conflict: Conflict) => Promise<Annotation | null>;
}

export function persistencePlugin(options: PersistenceOptions) {
  const wait = options.debounceMs ?? 600;
  const maxRetry = options.maxRetryMs ?? 30_000;

  return definePlugin({
    id: "persistence",
    order: 80,
    setup(ctx) {
      const { viewer, store } = ctx;
      let key: StoreKey | null = null;
      let timer: ReturnType<typeof setTimeout> | undefined;
      let unsubscribe: (() => void) | undefined;
      /** Coalesced pending work: last write per id wins. */
      const pendingUpserts = new Map<string, Annotation>();
      const pendingRemovals = new Set<string>();
      const pendingMeta: Mutation[] = [];
      /** Suppresses the save loop while applying inbound remote changes. */
      let applying = false;
      /**
       * The version each pending edit was made *against* — the last one the server confirmed, not
       * the one being sent. Sending the new version as its own base would always match and defeat
       * the check entirely.
       */
      const baseVersions = new Map<string, number>();
      /** Current backoff, ms. Zero when the last save succeeded. */
      let retryDelay = 0;

      /** Everything one save attempt carried, kept so a rejection can put back what it didn't settle. */
      interface Batch {
        upserts: Map<string, Annotation>;
        removals: string[];
        meta: Mutation[];
      }

      /** How many individual changes are waiting. */
      const pendingCount = () => pendingUpserts.size + pendingRemovals.size + pendingMeta.length;

      /**
       * Put a rejected batch back on the queue, minus the ids that were settled explicitly.
       *
       * A server rejects the *whole* request, so a 409 naming one markup also means the other edits
       * in that request were never stored. Dropping them loses work silently: the markups still
       * render locally, so nothing looks wrong until someone else opens the sheet.
       *
       * Anything edited again while the request was in flight is already newer than what was sent,
       * so the pending entry always wins over the restored one.
       */
      const requeue = (batch: Batch, settled: ReadonlySet<string>): void => {
        for (const [id, annot] of batch.upserts) {
          if (settled.has(id) || pendingUpserts.has(id) || pendingRemovals.has(id)) continue;
          pendingUpserts.set(id, annot);
        }
        for (const id of batch.removals) {
          if (settled.has(id) || pendingUpserts.has(id)) continue;
          pendingRemovals.add(id);
        }
        // Calibration and sheet metadata carry no version and cannot conflict, so they are always
        // restored — keyed so a repeated failure cannot grow the queue without bound, and appended
        // after the restored ones so a newer edit still lands last.
        if (batch.meta.length) {
          const keyOf = (m: Mutation) =>
            m.op === "calibration" ? `cal:${m.page}` : m.op === "sheet" ? `sheet:${m.sheet.sheetId}` : "";
          const merged = new Map<string, Mutation>();
          for (const m of [...batch.meta, ...pendingMeta]) merged.set(keyOf(m), m);
          pendingMeta.length = 0;
          pendingMeta.push(...merged.values());
        }
      };

      const flush = async () => {
        if (!key) return;
        const withBase = (id: string) =>
          (baseVersions.has(id) ? { baseVersion: baseVersions.get(id)! } : {});
        const mutations: Mutation[] = [
          ...[...pendingRemovals].map((id) => ({ op: "remove" as const, id, ...withBase(id) })),
          ...[...pendingUpserts.values()].map((annot) => ({ op: "upsert" as const, annot, ...withBase(annot.id) })),
          ...pendingMeta,
        ];
        const batch: Batch = {
          upserts: new Map(pendingUpserts),
          removals: [...pendingRemovals],
          meta: [...pendingMeta],
        };
        pendingUpserts.clear();
        pendingRemovals.clear();
        pendingMeta.length = 0;
        if (!mutations.length) return;
        try {
          ctx.bus.emit("sync:state", { state: "saving", pending: mutations.length });
          await options.adapter.save(key, mutations);
          // Accepted: the local copies are now the server's, and the next edit measures from here.
          for (const [id, annot] of batch.upserts) baseVersions.set(id, annot.version);
          for (const id of batch.removals) baseVersions.delete(id);
          ctx.bus.emit("sync:state", { state: "idle", pending: pendingCount() });
          retryDelay = 0;
        } catch (e) {
          if (e instanceof ConflictError) { await settleConflicts(e, batch); return; }
          // Nothing was stored, so the batch goes back on the queue to be retried rather than lost.
          requeue(batch, new Set());
          scheduleRetry();
          ctx.bus.emit("sync:state", { state: "error", pending: pendingCount(), message: (e as Error).message });
          ctx.bus.emit("notice", { level: "error", message: `Couldn't save markups: ${(e as Error).message}` });
        }
      };

      /**
       * Settle a rejected write.
       *
       * Defaulting to the server's copy is the conservative choice: silently re-sending over the
       * top is precisely the last-writer-wins behaviour the version check exists to prevent, and
       * doing it automatically would make the check theatre.
       */
      const settleConflicts = async (error: ConflictError, batch: Batch): Promise<void> => {
        const mode = options.onConflictResolve ?? "theirs";
        const settled = new Set(error.ids);

        for (const raw of error.conflicts) {
          const conflict: Conflict = { ...raw, mine: raw.mine ?? batch.upserts.get(raw.id) };
          const theirs = conflict.theirs;

          let keep: Annotation | null = null;
          if (mode === "mine") keep = conflict.mine ?? null;
          else if (mode === "ask" && options.onConflict) keep = await options.onConflict(conflict);

          if (theirs) {
            applying = true;
            store.merge([theirs]);
            applying = false;
            baseVersions.set(theirs.id, theirs.version);
          }

          if (!keep) continue;

          if (theirs) {
            // Re-apply the local edit on top of the server's version, so the retry carries a base
            // the server will accept.
            store.update(theirs.id, { ...keep, version: theirs.version + 1 }, { undoable: false, bump: false });
            pendingUpserts.set(theirs.id, store.get(theirs.id) ?? keep);
          } else {
            // The server rejected the write without saying what it holds, so there is no version to
            // rebase onto. Retry unconditionally rather than discard the edit: dropping the base is
            // last-writer-wins, but that is exactly what choosing "mine" asked for, and silently
            // throwing away a resolution the caller just made is worse.
            baseVersions.delete(keep.id);
            pendingUpserts.set(keep.id, store.get(keep.id) ?? keep);
          }
        }

        // Whatever the server did not name was never stored either — put it back.
        requeue(batch, settled);

        viewer.redraw();
        ctx.bus.emit("sync:state", { state: "error", pending: pendingCount(), message: error.message });
        ctx.bus.emit("notice", {
          level: "warn",
          message: mode === "theirs"
            ? `${error.message} — their version was kept, and your change to ${error.ids.length === 1 ? "it" : "them"} was discarded.`
            : `${error.message} — reapplied on top of their version.`,
        });
        if (pendingCount()) schedule();
      };

      const schedule = () => {
        clearTimeout(timer);
        timer = setTimeout(() => void flush(), wait);
      };

      /**
       * Retry a failed batch, backing off.
       *
       * The requeue alone is not enough: without a retry the restored work sits in memory until the
       * user happens to edit something else, and is lost if they close the tab first. Backing off
       * matters as much — a server that is down stays down, and the debounce interval would mean
       * hammering it twice a second for as long as the page is open.
       */
      const scheduleRetry = () => {
        // Starts at the debounce interval and doubles: quick enough that a blip costs nothing,
        // and past a real outage within a handful of attempts.
        retryDelay = Math.min(retryDelay ? retryDelay * 2 : wait, maxRetry);
        clearTimeout(timer);
        timer = setTimeout(() => void flush(), retryDelay);
      };

      const queueUpsert = (annot: Annotation) => {
        if (applying) return;
        pendingRemovals.delete(annot.id);
        // Capture the base once per pending batch: the *first* local edit is the one that still
        // knows which version the server last confirmed. A create (version 1) has no base.
        if (!pendingUpserts.has(annot.id) && !baseVersions.has(annot.id) && annot.version > 1) {
          baseVersions.set(annot.id, annot.version - 1);
        }
        pendingUpserts.set(annot.id, annot);
        schedule();
      };

      ctx.bus.on("annot:added", ({ annot }) => queueUpsert(annot));
      ctx.bus.on("annot:updated", ({ annot }) => queueUpsert(annot));
      ctx.bus.on("annot:removed", ({ annot }) => {
        if (applying) return;
        pendingUpserts.delete(annot.id);
        pendingRemovals.add(annot.id);
        schedule();
      });
      ctx.bus.on("calibration:changed", ({ calibration, page }) => {
        if (applying) return;
        pendingMeta.push({ op: "calibration", calibration, page });
        schedule();
      });
      ctx.bus.on("sheet:changed", ({ meta }) => {
        if (applying) return;
        pendingMeta.push({ op: "sheet", sheet: meta });
        schedule();
      });

      ctx.bus.on("doc:loaded", () => {
        unsubscribe?.();
        key = options.key(viewer);
        if (options.autoLoad === false) return;
        void (async () => {
          try {
            const result = await options.adapter.load(key!);
            applying = true;
            store.reset(result.annotations, { undoable: false });
            for (const c of result.calibrations ?? []) store.setCalibration(c, c.page);
            for (const s of result.sheets ?? []) store.setSheet(s);
            applying = false;
            // Everything just loaded sits at the server's version.
            baseVersions.clear();
            for (const a of result.annotations) baseVersions.set(a.id, a.version);
            store.clearHistory();
            viewer.redraw();
            if (result.annotations.length) {
              ctx.bus.emit("notice", { level: "info", message: `Loaded ${result.annotations.length} saved markups.` });
            }
            ctx.bus.emit("markups:restored", { count: result.annotations.length, ok: true });
          } catch (e) {
            applying = false;
            ctx.bus.emit("notice", { level: "warn", message: `Couldn't load saved markups: ${(e as Error).message}` });
            // Still announced on failure: a caller waiting to seed the store must not wait forever.
            ctx.bus.emit("markups:restored", { count: 0, ok: false });
          }
        })();

        if (options.live !== false && options.adapter.subscribe) {
          unsubscribe = options.adapter.subscribe(key, (result) => {
            applying = true;
            // Merge by version: a remote record only wins if it is genuinely newer.
            const { added, updated } = store.merge(result.annotations);
            // Advance the base for anything we accepted wholesale, or the next local edit would
            // conflict against a version already reconciled.
            for (const a of result.annotations) {
              if (store.get(a.id)?.version === a.version) baseVersions.set(a.id, a.version);
            }
            applying = false;
            if (added || updated) viewer.redraw();
          });
        }
      });

      ctx.registerAction({
        id: "persistence.save", label: "Save now", icon: "💾", group: "io", shortcut: "S",
        run: async () => { clearTimeout(timer); await flush(); },
      });

      ctx.registerAction({
        id: "persistence.reload", label: "Reload markups", icon: "⟲", group: "io",
        async run(v) {
          if (!key) return;
          const result = await options.adapter.load(key);
          applying = true;
          v.store.reset(result.annotations, { undoable: false });
          applying = false;
          v.redraw();
          v.bus.emit("notice", { level: "success", message: `Reloaded ${result.annotations.length} markups.` });
        },
      });

      ctx.onCleanup(() => {
        clearTimeout(timer);
        unsubscribe?.();
        // A pending batch on teardown is exactly the batch most worth not losing.
        void flush();
      });
    },
  });
}
