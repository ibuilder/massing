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
 */
import { HttpCore } from "./httpCore";

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
  };
}
