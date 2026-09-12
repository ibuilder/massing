/** IDS authoring (BIMIDS): templates, build/download, and the IDS pinned to a project.
 *
 *  SCALE-SEAM ㉔. Route-group `/ids` and `/projects/{pid}/ids`, taken out of `client.ts` by the route
 *  each method calls. **Six methods, one contiguous run** — found by measuring the longest same-prefix
 *  run left in the file rather than by picking a domain that sounded tidy.
 *
 *  Two of these are not `json()` calls: `idsDownload` triggers a browser download and `pinProjectIds`
 *  sends multipart. They move with the group anyway — the seam is the ROUTE, not the transport, and
 *  splitting on transport would put two halves of one feature in two files.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 *
 *  **BSDD-LOOKUP added `bsddSearch` / `bsddClass` here, and NOT as their own mixin, because
 *  `client.ts` has hit a hard compiler ceiling.** Route-group `/bsdd` is its own group, so by this
 *  file's own stated rule — the seam is the ROUTE — they should have been `withBsdd`. Adding a 51st
 *  mixin to the chain in `client.ts` makes `tsc` fail outright with TS2589, *"Type instantiation is
 *  excessively deep and possibly infinite"*, on the `extends` clause; removing it makes the error
 *  vanish, so the count is the cause and not anything in the new code. **That quietly reverses the
 *  SCALE-SEAM strategy: new route groups can no longer get their own mixin, they must lodge with a
 *  neighbour, until the chain is composed in stages.** Recorded here rather than worked around
 *  silently, because the next person to reach for `withX()` will hit the same wall and the error
 *  message names neither the cause nor the limit.
 *
 *  Of the available neighbours this is the honest one: bSDD and IDS are both buildingSMART
 *  REFERENCE surfaces — one says what a class *is*, the other what a deliverable must *carry* — and
 *  both are consumed by the same screen (`portal/panels/standards.ts`). They are also the only
 *  methods in this file that are **not** project-scoped: a bSDD class is the same class for every
 *  project, which is why the server caches it module-wide.
 */
import { HttpCore, HttpError } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

/** One hit from a bSDD free-text search (`GET /bsdd/search`). */
export interface BsddHit {
  uri: string | null;
  name: string | null;
  code: string | null;
  dictionary: string | null;
}

/** One bSDD class with the properties the dictionary defines for it (`GET /bsdd/class`). */
export interface BsddClass extends BsddHit {
  properties: { name: string | null; code: string | null; dataType: string | null }[];
}


export function withIds<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Ids extends Base {
  idsTemplates() {
    return this.json<{ elements: { key: string; label: string; ifc_class: string;
      requirements: { pset: string; property: string; data_type: string }[] }[];
      use_cases: { key: string; label: string; groups: string[] }[] }>(`/ids/templates`);
  }
  /** POST a use_case (or specs) and download the resulting .ids / EIR.md file. */
  async idsDownload(kind: "build" | "eir", body: Record<string, unknown>, filename: string) {
    const res = await fetch(this.url(`/ids/${kind}`), {
      method: "POST", body: JSON.stringify(body),
      headers: { "Content-Type": "application/json", ...this.authHeaders() } });
    if (!res.ok) throw new HttpError(`ids ${kind} -> ${res.status}`, res.status);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }

  /** Build a use-case IDS and return its bytes (for pinning), rather than triggering a download. */
  async idsBuildBlob(useCase: string): Promise<Blob> {
    const res = await fetch(this.url(`/ids/build`), {
      method: "POST", body: JSON.stringify({ use_case: useCase }),
      headers: { "Content-Type": "application/json", ...this.authHeaders() } });
    if (!res.ok) throw new HttpError(`ids build -> ${res.status}`, res.status);
    return res.blob();
  }
  /** Whether a project has a pinned IDS (+ its size). */
  projectIdsStatus(pid: string) {
    return this.json<{ exists: boolean; bytes: number }>(`/projects/${pid}/ids`);
  }
  /** Pin an IDS to the project so /validate runs against it with no re-upload. */
  async pinProjectIds(pid: string, ids: Blob, filename = "project.ids") {
    const fd = new FormData(); fd.append("file", ids, filename);
    const res = await fetch(this.url(`/projects/${pid}/ids`),
      { method: "PUT", body: fd, headers: { ...this.authHeaders() } });
    if (!res.ok) throw new HttpError(`pin IDS -> ${res.status}`, res.status);
    return res.json() as Promise<{ stored: boolean; bytes: number }>;
  }
  unpinProjectIds(pid: string) {
    return this.json<{ deleted: boolean }>(`/projects/${pid}/ids`, { method: "DELETE" });
  }

  /** One hit from a bSDD free-text search. Every field is nullable: the live bSDD response shape
   *  varies by dictionary and `bsdd.py` parses it defensively rather than asserting a schema. */
  bsddSearch(q: string, opts: { dictionary?: string; limit?: number } = {}) {
    const params = new URLSearchParams({ q });
    if (opts.dictionary) params.set("dictionary", opts.dictionary);
    if (opts.limit != null) params.set("limit", String(opts.limit));
    return this.json<{ classes: BsddHit[] }>(`/bsdd/search?${params.toString()}`);
  }
  /** One bSDD class and the properties the dictionary defines for it, by full class URI.
   *  404 when the dictionary has no such class; 502 when bSDD itself is unreachable — the caller
   *  MUST tell those two apart, because an outage and an empty dictionary look identical on screen
   *  and mean opposite things. Both arrive as `HttpError`, which carries `.status`. */
  bsddClass(uri: string) {
    return this.json<BsddClass>(`/bsdd/class?uri=${encodeURIComponent(uri)}`);
  }
  };
}
