/**
 * Offline-first composition: local IndexedDB is the working copy, the remote adapter is the truth,
 * and a durable queue bridges them.
 *
 * The write path is local-then-queue-then-network, never network-first. A field user should never
 * see a spinner or lose a markup because the connection dropped mid-save; they should see their
 * markup immediately and a "3 pending" indicator until it drains.
 */
import { IndexedDbAdapter, indexedDbAvailable } from "./indexeddb";
import type { LoadResult, Mutation, StorageAdapter, StoreKey } from "./types";
import type { Annotation } from "../core/types";

export interface OfflineOptions {
  /** The authoritative backend. */
  remote: StorageAdapter;
  /** Local cache; defaults to IndexedDB. */
  local?: IndexedDbAdapter;
  /** Retry cadence for a failed drain, ms. Backs off to 4× this. */
  retryMs?: number;
  /** Called whenever the pending count or connectivity changes. */
  onState?: (state: { state: "idle" | "saving" | "offline" | "error"; pending: number; message?: string }) => void;
}

export class OfflineAdapter implements StorageAdapter {
  readonly id = "offline";
  private local: IndexedDbAdapter;
  private remote: StorageAdapter;
  private draining = false;
  private retry: ReturnType<typeof setTimeout> | undefined;
  private backoff: number;
  private key: StoreKey | null = null;

  constructor(private o: OfflineOptions) {
    if (!indexedDbAvailable()) {
      throw new Error("OfflineAdapter needs IndexedDB — use the remote adapter directly in this environment.");
    }
    this.local = o.local ?? new IndexedDbAdapter();
    this.remote = o.remote;
    this.backoff = o.retryMs ?? 5000;
    if (typeof window !== "undefined") {
      window.addEventListener("online", () => void this.drain());
      window.addEventListener("offline", () => void this.report("offline"));
    }
  }

  /**
   * Serve the local copy immediately, then refresh from the remote in the background. A field user
   * gets their sheet's markups instantly rather than after a round trip.
   */
  async load(key: StoreKey): Promise<LoadResult> {
    this.key = key;
    const local = await this.local.load(key).catch(() => ({ annotations: [] as Annotation[] }));
    void this.refresh(key);
    void this.drain();
    return local;
  }

  /** Pull the remote copy and write it through to the local cache. */
  async refresh(key: StoreKey): Promise<LoadResult | null> {
    if (!this.online()) return null;
    try {
      const remote = await this.remote.load(key);
      await this.local.save(key, [
        ...remote.annotations.map((annot) => ({ op: "upsert" as const, annot })),
        ...(remote.calibrations ?? []).map((calibration) => ({ op: "calibration" as const, calibration, page: calibration.page })),
        ...(remote.sheets ?? []).map((sheet) => ({ op: "sheet" as const, sheet })),
      ]);
      return remote;
    } catch {
      await this.report("offline");
      return null;
    }
  }

  /** Local write, durable queue, then a best-effort drain. */
  async save(key: StoreKey, mutations: Mutation[]): Promise<void> {
    this.key = key;
    await this.local.save(key, mutations);
    await this.local.enqueue(key, mutations);
    await this.drain();
  }

  subscribe(key: StoreKey, onChange: (result: LoadResult) => void): () => void {
    if (!this.remote.subscribe) return () => {};
    return this.remote.subscribe(key, (remote) => {
      // Mirror inbound changes into the cache so they survive going offline.
      void this.local.save(key, remote.annotations.map((annot) => ({ op: "upsert" as const, annot })));
      onChange(remote);
    });
  }

  online(): boolean {
    if (typeof navigator !== "undefined" && navigator.onLine === false) return false;
    return this.remote.online?.() ?? true;
  }

  /** Push everything queued. Safe to call at any time; re-entrant calls are ignored. */
  async drain(): Promise<void> {
    const key = this.key;
    if (!key || this.draining) return;
    if (!this.online()) { await this.report("offline"); return; }

    this.draining = true;
    try {
      const pending = await this.local.pending(key);
      if (!pending.length) { await this.report("idle"); return; }
      await this.report("saving");
      // One request for the whole queue: the batch is already ordered, and a bulk save that
      // replaces the sheet must see every change at once or it will drop the ones left behind.
      await this.remote.save(key, pending.map((p) => p.mutation));
      await this.local.ack(pending.map((p) => p.seq));
      this.backoff = this.o.retryMs ?? 5000;
      await this.report("idle");
    } catch (e) {
      await this.report("error", (e as Error).message);
      clearTimeout(this.retry);
      this.retry = setTimeout(() => void this.drain(), this.backoff);
      this.backoff = Math.min(this.backoff * 2, (this.o.retryMs ?? 5000) * 4);
    } finally {
      this.draining = false;
    }
  }

  /** How many mutations are waiting. */
  async pendingCount(): Promise<number> {
    return this.key ? (await this.local.pending(this.key)).length : 0;
  }

  private async report(state: "idle" | "saving" | "offline" | "error", message?: string): Promise<void> {
    const pending = await this.pendingCount().catch(() => 0);
    this.o.onState?.({ state, pending, ...(message ? { message } : {}) });
  }

  /** Stop retrying and release listeners. */
  dispose(): void { clearTimeout(this.retry); }
}
