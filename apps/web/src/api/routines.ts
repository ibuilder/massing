/** Scheduled routines: what is due, and the sweep that actually enqueues it.
 *
 *  Route-group `/projects/{pid}/routines/*`. A NEW file rather than an addition to `client.ts`,
 *  which sits exactly on its 3,780 `PER_FILE` pin — the ratchet's own words are that "a new endpoint
 *  added straight to `client.ts` will fail this, and that friction is the point".
 *
 *  **`routinesRunDue` exists because the endpoint was unreachable**: `test_route_reachability` flagged
 *  `/routines/run-due` as a new uncalled route, correctly, and the honest fix is a caller rather than
 *  an exemption.
 *
 *  Note the sibling `GET /routines/due` is *also* uncalled and the ratchet cannot see it — its last
 *  static segment is `due`, three characters, below the 5-char distinctiveness floor the rule needs to
 *  avoid 40% noise. That is the gate's documented blind spot rather than a defect in it, but it means
 *  the read half of this pair is still unwired and a UI will want it.
 *
 *  SCALE-SEAM ❺ adds the meeting action tracker — *are meeting actions closing?*
 *  `projectHealth` sat immediately below and did **not** come.
 *
 *  SCALE-SEAM ⓱ adds the inbox — *what needs my attention?* Work queue, my-work,
 *  notifications, SLA due-feed. Escalations sat below and did **not** come with ⓱.
 *
 *  SCALE-SEAM ⓲ adds overdue escalation and the digest — *what's overdue, and who
 *  gets told?* Scan, apply, digest email, saved-view alerts, live notification stream.
 *  Clash imports sat below and did **not** come.
 *
 *  SCALE-SEAM ⓵ adds the job tray — *what's running in the background?* Enqueue, status, list, artifact URL. The leftover R24-JOB-TRAY banner travelled with them. 5D heatmap sat below and did **not** come.
 */
import { HttpCore, type LiveStream } from "./httpCore";
import type { DueFeed, EscalationRun, EscalationScan, Job, NotifItem, WorkItem, WorkQueue } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withRoutines<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Routines extends Base {
  /** Enqueue every routine that is due now. One job per DUE routine — never one per missed window;
   *  a routine dormant for a year fires once with its missed count reported. Routines whose kind
   *  already has queued or running work are skipped as in-flight, and one naming an unregistered
   *  kind is listed under `refused` without aborting the sweep. */
  routinesRunDue(pid: string) {
    return this.json<{
      project_id: string; as_of: string; due_count: number;
      enqueued: { routine_id: string; kind: string; job_id: string; window_start: string | null;
        missed_windows: number | null; status: "enqueued" }[];
      enqueued_count: number;
      refused: { routine_id: string; kind: string; status: "unknown_kind"; reason: string }[];
      skipped: { id: string; kind: string; status: string; reason: string }[];
      in_flight_kinds: string[]; total_missed_windows: number; note: string;
    }>(`/projects/${pid}/routines/run-due`, { method: "POST" });
  }

  /** actionTracker — open/overdue by assignee, completion, meeting log. */
  actionTracker(pid: string) {
    return this.json<{ action_count: number; open_count: number; done_count: number;
      overdue_count: number; completion_pct: number | null; meeting_count: number;
      last_meeting: string | null; by_assignee: Record<string, number>;
      meetings_by_type: Record<string, number>; rows: Record<string, unknown>[] }>(
      `/projects/${pid}/action-items/tracker`);
  }
  /** Work queue — open items across modules that need attention. */
  workQueue(pid: string) {
    return this.json<WorkQueue>(`/projects/${pid}/work-queue`);
  }
  /** My work — items assigned to the caller. */
  myWork(pid: string) {
    return this.json<WorkItem[]>(`/projects/${pid}/my-work`);
  }
  /** Project notifications, newest first. */
  notifications(pid: string) {
    return this.json<NotifItem[]>(`/projects/${pid}/notifications`);
  }
  /** Cross-module SLA feed — open records past or near their due date (overdue / due-soon). */
  dueFeed(pid: string, days = 7) {
    return this.json<DueFeed>(`/projects/${pid}/due-feed?days=${days}`);
  }
  /** WORKFLOW-ENGINE — read-only escalation preview: overdue records with their computed level. */
  escalationsScan(pid: string) {
    return this.json<EscalationScan>(`/projects/${pid}/escalations`);
  }
  /** Apply the overdue-escalation pass (admin) — notifies the ball-in-court party + assignee. */
  escalationsRun(pid: string) {
    return this.json<EscalationRun>(`/projects/${pid}/escalations/run`, { method: "POST" });
  }
  /** Admin: send each member with open items a work-queue digest email. */
  sendDigest(pid: string) {
    return this.json<{ smtp_configured: boolean; results: Record<string, string[]>; skipped_no_email: string[] }>(
      `/projects/${pid}/notifications/digest`, { method: "POST" });
  }
  /** Saved-view alerts — new rows matching a watched filter. */
  viewAlerts(pid: string) {
    return this.json<{ id: string; name: string; module: string; total: number; new: number;
      config: { q?: string; state?: string; sort?: unknown } }[]>(`/projects/${pid}/views/alerts`);
  }
  /** Live notification stream — count plus items as they arrive. */
  notificationStream(pid: string, onMessage: (d: { count: number; items: NotifItem[] }) => void,
                     onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    return this.liveStream(`/projects/${pid}/notifications/stream`,
                           onMessage as (d: unknown) => void, onStatus);
  }
  /** Queue a background job. 400 on an unregistered kind (a typo fails at submit, not silently). */
  enqueueJob(pid: string, kind: string, params?: Record<string, unknown>) {
    return this.json<Job>(`/projects/${pid}/jobs`,
      { method: "POST", body: JSON.stringify({ kind, params: params ?? {} }) });
  }
  /** One job's state + result/error. 404 when it belongs to another project. */
  job(pid: string, jobId: string) {
    return this.json<Job>(`/projects/${pid}/jobs/${jobId}`);
  }
  /** The project's jobs, newest first. The server bounds `limit` at 200. */
  async jobs(pid: string, limit = 50): Promise<Job[]> {
    const r = await this.json<{ jobs: Job[] }>(`/projects/${pid}/jobs?limit=${limit}`);
    return r.jobs ?? [];
  }
  /** Absolute URL of a finished job's artifact — an href the browser fetches directly, so a big
   *  compiled set never round-trips through JS memory. 409 while queued/running. */
  jobArtifactUrl(pid: string, jobId: string): string {
    return this.url(`/projects/${pid}/jobs/${jobId}/artifact`);
  }
  };
}
