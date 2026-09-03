/** Project auto-sync — Procore pull/push, the schedule that runs it, and live presence.
 *
 *  SCALE-SEAM ⑬. Route-group `/projects/{pid}/sync/…`, taken out of `client.ts` by the route
 *  each method calls. They sat immediately under the `/connections` run ⑫ moved; grouping by
 *  the nearby section comment would have dragged them into ⑫. Different first path segment,
 *  so they wait their own cut.
 *
 *  Named `withSync` rather than anything involving "schedule": `withSchedule` is already the
 *  CPM / 4D mixin. The collision is the point of locating by route rather than by English.
 *
 *  SCALE-SEAM ⓰ adds presence — *who is looking at the model right now?* Heartbeat plus
 *  optional camera viewpoint. Route is `/projects/{pid}/presence`, not `/sync`. Grouped by
 *  what it ANSWERS (live peers on the model), not by first path segment. Project CRUD stayed.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { SyncScheduleItem, Vec3 } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withSync<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Sync extends Base {
  /** Import a Procore project's RFIs / submittals / change events into the matching modules. */
  syncProcore(pid: string, connectionId: string, procoreProjectId: string, kinds?: string[]) {
    return this.json<{ source: string; imported_total: number; results: Record<string, { module: string; fetched: number; imported: number; skipped: number }> }>(
      `/projects/${pid}/sync/procore`,
      { method: "POST", body: JSON.stringify({ connection_id: connectionId, procore_project_id: procoreProjectId, ...(kinds ? { kinds } : {}) }) });
  }
  /** Two-way: push locally-resolved records (RFI status + answer) back to Procore. */
  pushProcore(pid: string, connectionId: string, procoreProjectId: string, kinds: string[] = ["rfi"]) {
    return this.json<{ pushed_total: number; results: Record<string, { pushed: number; skipped: number; errors: string[] }> }>(
      `/projects/${pid}/sync/procore/push`,
      { method: "POST", body: JSON.stringify({ connection_id: connectionId, procore_project_id: procoreProjectId, kinds }) });
  }
  syncSchedules(pid: string) {
    return this.json<SyncScheduleItem[]>(`/projects/${pid}/sync/schedules`);
  }
  createSyncSchedule(pid: string, body: { connection_id: string; procore_project_id: string; kinds?: string[]; interval_minutes?: number; push?: boolean }) {
    return this.json<SyncScheduleItem>(`/projects/${pid}/sync/schedules`, { method: "POST", body: JSON.stringify(body) });
  }
  updateSyncSchedule(pid: string, sid: string, patch: { enabled?: boolean; interval_minutes?: number; kinds?: string[]; push?: boolean }) {
    return this.json<SyncScheduleItem>(`/projects/${pid}/sync/schedules/${sid}`, { method: "PUT", body: JSON.stringify(patch) });
  }
  deleteSyncSchedule(pid: string, sid: string) {
    return this.json<{ ok: boolean }>(`/projects/${pid}/sync/schedules/${sid}`, { method: "DELETE" });
  }
  runSyncSchedule(pid: string, sid: string) {
    return this.json<{ imported_total?: number; error?: string }>(`/projects/${pid}/sync/schedules/${sid}/run-now`, { method: "POST" });
  }
  /** Heartbeat presence (optionally sharing the current camera viewpoint) → live peer roster. */
  presence(pid: string, viewpoint?: unknown) {
    return this.json<{ user: string; active: { user: string; seconds_ago: number; viewpoint: { position: Vec3; target: Vec3 } | null }[] }>(
      `/projects/${pid}/presence`, { method: "POST", body: JSON.stringify({ viewpoint }) });
  }
  };
}
