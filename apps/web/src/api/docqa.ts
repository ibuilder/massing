/** Document QA: extractive answers over ingested documents, contract-risk and scope-gap review,
 *  and fetching the source document a citation points at.
 *
 *  SCALE-SEAM. Route-groups `/projects/{pid}/review/*` and `/projects/{pid}/doctext/*`, taken out of
 *  `client.ts` by the route each method calls — the same recipe `contracts.ts` records.
 *
 *  **This extraction was forced by the ratchet, and that is the ratchet working.** `client.ts` was
 *  pinned at 3,703 in `test_file_sizes.py`, and adding the one method R31-CITE-HIGHLIGHT needed
 *  (`doctextSource`) put it at 3,715 and failed the build. `contracts.ts` hit the identical wall and
 *  wrote down the right response: ask whether the method belongs in a domain module instead. For
 *  document QA the answer was plainly yes — the three `review*` methods were already a cluster
 *  sharing one helper and one route prefix, sitting in the middle of the dashboard/vitals block for
 *  no reason but arrival order. So the pin moves DOWN rather than up.
 *
 *  `reviewPost` came with them. It had been sitting `protected` in `modules.ts` purely so the three
 *  review methods left behind in `client.ts` could still reach it — its own comment said as much.
 *  With those methods here it is `private` again and there is no cross-mixin reach at all, which
 *  also removes a real typing hazard: a mixin constraint cannot see a `protected` member, so
 *  constraining on one silently collapses the inferred base and every OTHER mixin's methods vanish
 *  from `ApiClient`. That failed as `editIfc` going missing — a symptom nowhere near its cause.
 *
 *  `api/surface.test.ts` is what makes this safe — it captures the runtime method surface and fails
 *  if an extraction drops one. A typecheck cannot: deleting a method and deleting its last caller
 *  both compile clean.
 */
import type { DocCitation } from "./types";
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withDocQa<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class DocQa extends Base {
    /** Shared multipart POST for the `/review/*` endpoints. */
    private async reviewPost<T>(pid: string, kind: string,
        opts: { file?: File; text?: string; question?: string }) {
      const fd = new FormData();
      if (opts.file) fd.append("file", opts.file);
      if (opts.text != null) fd.append("text", opts.text);
      if (opts.question != null) fd.append("question", opts.question);
      const res = await fetch(this.url(`/projects/${pid}/review/${kind}`), {
        method: "POST", body: fd, headers: this.authHeaders() });
      if (!res.ok) throw new Error(`Review ${kind} -> ${res.status}`);
      return res.json() as Promise<T>;
    }

    reviewContract(pid: string, opts: { file?: File; text?: string }) {
      return this.reviewPost<{ findings: { clause: string; severity: "high" | "medium" | "low"; category: string;
        rationale: string; suggested_action: string; snippet: string }[];
        counts: Record<string, number>; source: string; message?: string }>(pid, "contract", opts);
    }

    reviewScope(pid: string, opts: { file?: File; text?: string }) {
      return this.reviewPost<{ gaps: { marker: string; note: string; snippet: string }[];
        source: string; message?: string }>(pid, "scope", opts);
    }

    reviewAsk(pid: string, question: string, opts: { file?: File; text?: string }) {
      return this.reviewPost<{ answer: string; citations: DocCitation[]; source: string;
        message?: string }>(pid, "ask", { ...opts, question });
    }

    /** The source PDF behind a citation, so the citation can be opened (R31-CITE-HIGHLIGHT).
     *
     * Fetched as a blob rather than linked: auth here is a bearer header, so a plain `<a href>` to
     * this route arrives unauthenticated and 401s. Callers should gate on the citation's `openable`
     * flag — a text-only ingest never had a document behind it, and the route answers 404 saying
     * exactly that, which is an answer rather than a failure.
     */
    async doctextSource(pid: string, docId: string): Promise<Blob> {
      const res = await fetch(this.url(`/projects/${pid}/doctext/${encodeURIComponent(docId)}/source`),
        { headers: this.authHeaders() });
      if (!res.ok) throw new Error(`doctext source -> ${res.status}`);
      return res.blob();
    }
  };
}
