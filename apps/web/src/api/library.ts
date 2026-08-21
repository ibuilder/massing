/** The sample library — packaged `.mass` showcase projects.
 *
 *  A **new** domain landing as a mixin rather than as two more methods on `client.ts`. That file is
 *  the roadmap's named scaling breakpoint (4,956 lines, 152 commits/fortnight), and a seam only
 *  helps if new work goes through it — otherwise extraction is a treadmill: carve 15 methods out one
 *  week, add 15 back the next.
 *
 *  Two calls, matching the server exactly: list what is packaged, and open one as a new project.
 *  Opening runs through `bundle.import_bundle` server-side, the same path a user's own `.mass` takes.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

/** One packaged container, described from its own manifest (never a hand-kept catalog). */
export interface SampleInfo {
  id: string;
  name: string;
  bytes: number;
  entries: number;
  elements: number;
  has_geometry: boolean;
  /** `false` when the container could not be read — still listed, so a packaging mistake is visible. */
  readable: boolean;
  /** Row counts per table, zero-count tables omitted. */
  contents: Record<string, number>;
  format?: string | null;
  version?: number | null;
}

export function withLibrary<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Library extends Base {
    /** Every packaged sample. Empty array is a valid answer — a checkout may ship none. */
    samples() {
      return this.json<{ samples: SampleInfo[] }>("/samples");
    }

    /** Open a sample as a NEW project and return it. The id must come from `samples()` — the server
     *  resolves it by enumeration, so anything not in that list is a 404 rather than a path.
     *
     *  Multipart via `fetch` rather than `json()`, matching `importBundle`: the endpoint takes a
     *  `Form(...)` name field, and `json()` sets `Content-Type: application/json`, which would make
     *  FastAPI reject the body. Deliberately NOT setting Content-Type here — the browser must add
     *  the multipart boundary itself. */
    async openSample(sampleId: string, name?: string) {
      const fd = new FormData();
      if (name) fd.append("name", name);
      const res = await fetch(this.url(`/samples/${encodeURIComponent(sampleId)}/open`), {
        method: "POST", body: fd, headers: this.authHeaders(),
      });
      if (!res.ok) throw new Error(`open sample -> ${res.status}`);
      return res.json() as Promise<{ id: string; name: string }>;
    }

    /** R28-BUNDLE — what a `.mass` / `.mmproj` holds, without creating a project. */
    async previewBundle(file: File) {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(this.url(`/projects/preview-bundle`), {
        method: "POST", body: fd, headers: this.authHeaders(),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: res.statusText })) as { detail?: unknown };
        const detail = typeof e.detail === "string" ? e.detail : `preview -> ${res.status}`;
        throw new Error(detail);
      }
      return res.json() as Promise<{
        readable: boolean; importable: boolean; format?: string; version?: number;
        project_name?: string | null; has_geometry: boolean; entry_count: number;
        table_count: number; row_count: number; tables: Record<string, number>;
        excluded: { tables: string[]; why: string }; reason: string;
      }>;
    }
  };
}
