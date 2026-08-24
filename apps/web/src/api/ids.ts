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
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

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
    if (!res.ok) throw new Error(`ids ${kind} -> ${res.status}`);
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
    if (!res.ok) throw new Error(`ids build -> ${res.status}`);
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
    if (!res.ok) throw new Error(`pin IDS -> ${res.status}`);
    return res.json() as Promise<{ stored: boolean; bytes: number }>;
  }
  unpinProjectIds(pid: string) {
    return this.json<{ deleted: boolean }>(`/projects/${pid}/ids`, { method: "DELETE" });
  }
  };
}
