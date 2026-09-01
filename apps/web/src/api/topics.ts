/** BCF topics: create, viewpoints, board, timeline, comments, and RFI readiness / NL-QA.
 *
 *  SCALE-SEAM ⑳. Route-group `/projects/{pid}/topics`, taken out of `client.ts` by the route
 *  each method calls. Seven methods in **three** regions — create/viewpoints next to pins,
 *  the board next to share links, timeline/comments next to model-version review.
 *  `pins()` is `/pins` and stays. Clash `create_topics` query flags stay with `/clash`.
 *
 *  SCALE-SEAM ㉟ adds the three RFI methods that answer *what does this model still need, and
 *  can we ask it a cited question?* — readiness gaps, promoting those gaps to BCF topics, and
 *  NL-QA. They were not contiguous in `client.ts` (logistics and the model graph sat between
 *  readiness and QA). Logistics and the graph did **not** come.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { Topic, Viewpoint } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withTopics<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Topics extends Base {
  createTopic(pid: string, body: Partial<Topic>) {
    return this.json<Topic>(`/projects/${pid}/topics`, { method: "POST", body: JSON.stringify(body) });
  }
  viewpoints(pid: string, tid: string) {
    return this.json<Viewpoint[]>(`/projects/${pid}/topics/${tid}/viewpoints`);
  }
  addViewpoint(pid: string, tid: string, body: Partial<Viewpoint>) {
    return this.json<Viewpoint>(`/projects/${pid}/topics/${tid}/viewpoints`, {
      method: "POST", body: JSON.stringify(body),
    });
  }
  topicsBoard(pid: string, groupBy: "status" | "priority" | "assignee" | "type" = "status", filter?: string) {
    type T = { id: string; guid: string; type: string; title: string; status: string;
      priority: string | null; assignee: string | null; author: string | null; labels: string[] | null;
      element_guids: string[] | null; due_date: string | null; created_at: string | null; modified_at: string | null };
    const q = new URLSearchParams({ group_by: groupBy });
    if (filter) q.set("filter", filter);
    return this.json<{
      group_by: string; filter: string | null; total: number; column_count: number;
      columns: { key: string; count: number; topics: T[] }[]; note: string;
    }>(`/projects/${pid}/topics/board?${q.toString()}`);
  }
  topicTimeline(pid: string, tid: string) {
    return this.json<{
      topic_id: string; title: string; type: string; status: string;
      events: { ts: string | null; kind: string; actor: string | null; summary: string;
        detail?: Record<string, unknown> }[];
      event_count: number; statuses: string[]; allowed_next: string[];
    }>(`/projects/${pid}/topics/${tid}/timeline`);
  }
  topicComments(pid: string, tid: string) {
    return this.json<{ id: string; topic_id: string; author: string | null; text: string;
      viewpoint_id: string | null; reply_to: string | null; created_at: string }[]>(
      `/projects/${pid}/topics/${tid}/comments`);
  }
  addTopicComment(pid: string, tid: string, body: { author?: string; text: string; reply_to?: string }) {
    return this.json<{ id: string; reply_to: string | null }>(
      `/projects/${pid}/topics/${tid}/comments`, { method: "POST", body: JSON.stringify(body) });
  }

  /** rfiReadiness — decision-readiness gaps on this model (cited, severity-ranked). */
  rfiReadiness(pid: string) {
    return this.json<{ ready: boolean; total_gaps: number; high_severity: number; summary: string; disclaimer: string;
      by_category: Record<string, number>;
      gaps: { category: string; severity: string; title: string; detail: string; fix: string; citation?: string;
        count?: number | null; guids?: string[] }[] }>(`/projects/${pid}/rfi/readiness`);
  }
  /** rfiReadinessBcf — promote those readiness gaps to BCF topics (one per gap, GUID-anchored). */
  rfiReadinessBcf(pid: string) {
    return this.json<{ created: number; topics: string[]; ready: boolean; high_severity: number }>(
      `/projects/${pid}/rfi/readiness/bcf`, { method: "POST", body: "{}" });
  }
  /** rfiQa — a plain-language question to a cited answer from the model's own data. */
  rfiQa(pid: string, question: string) {
    return this.json<{
      question: string; intent: string; answer: string;
      citations: { kind: string; ref: string; source?: string; guids?: string[] }[];
      disclaimer: string; found?: boolean; ready?: boolean;
    }>(`/projects/${pid}/rfi/qa`, { method: "POST", body: JSON.stringify({ question }) });
  }
  };
}
