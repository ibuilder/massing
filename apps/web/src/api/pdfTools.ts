/** PDF tools and A/E/C seals: merge, split, rotate, extract; the stamp library, stamping, and the
 *  PAdES-signed professional seal with the licences that back it.
 *
 *  SCALE-SEAM ㉗. Grouped by what these methods DO, following ㉖ rather than the route prefix: the
 *  group spans `/pdf/*`, `/stamps/library` and `/licenses/mine`, and splitting on the prefix would
 *  separate `stampLibrary` from the `pdfStamp` that consumes it, and `myLicenses` from the `pdfSeal`
 *  dialog that is its only reason to exist.
 *
 *  `_pdfPost` is NOT moved: it is `protected` on `HttpCore`, which every mixin extends, so it is
 *  already where shared transport belongs. **The seam is the feature, not the plumbing** — the same
 *  call ㉔ made when `idsDownload` and `pinProjectIds` moved despite not being `json()` calls.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";
import type { ProfessionalLicense, StampTemplate } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withPdfTools<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class PdfTools extends Base {
  // --- PDF manipulation (server pypdf): merge / split / rotate / extract uploaded PDFs -----------
  /** Page count + flags for an uploaded PDF. */
  async pdfInfo(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(this.url("/pdf/info"), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.json() as Promise<{ pages: number; encrypted: boolean }>;
  }
  /** Merge several uploaded PDFs into one (order = list order). */
  pdfMerge(files: File[]) { return this._pdfPost("/pdf/merge", (fd) => { for (const f of files) fd.append("files", f); }); }
  /** Split a PDF into one PDF per page, returned as a .zip. */
  pdfSplitZip(file: File) { return this._pdfPost("/pdf/split", (fd) => fd.append("file", file)); }
  /** Rotate pages by `angle` (multiple of 90); `pages` (1-based '1,3-5') limits it, blank = all. */
  pdfRotate(file: File, angle: number, pages = "") { return this._pdfPost("/pdf/rotate", (fd) => { fd.append("file", file); fd.append("angle", String(angle)); if (pages) fd.append("pages", pages); }); }
  /** Extract the given pages ('1,3,5-7', 1-based) into a new PDF. */
  pdfExtract(file: File, pages: string) { return this._pdfPost("/pdf/extract", (fd) => { fd.append("file", file); fd.append("pages", pages); }); }
  // --- A/E/C stamps (server: reportlab overlay + pypdf; seals add a PAdES signature) --------------
  /** The stamp template library — review (EJCDC + CSI), inspection, status, and PE/RA seal templates. */
  stampLibrary() { return this.json<{ templates: StampTemplate[] }>("/stamps/library"); }
  /** Composite a review / inspection / status stamp onto a page (1-based). (x,y) = top-left in PDF points. */
  pdfStamp(file: File, o: { template_id: string; page?: number; x?: number; y?: number; disposition?: string; values?: Record<string, string> }) {
    return this._pdfPost("/pdf/stamp", (fd) => {
      fd.append("file", file); fd.append("template_id", o.template_id);
      fd.append("page", String(o.page ?? 1)); fd.append("x", String(o.x ?? 36)); fd.append("y", String(o.y ?? 36));
      if (o.disposition) fd.append("disposition", o.disposition);
      if (o.values) fd.append("values", JSON.stringify(o.values));
    });
  }
  /** Apply a *visible* professional seal, then a tamper-evident PAdES signature LAST. Returns the sealed
   *  PDF plus the compliance note the server reports (demo cert vs configured cert). */
  async pdfSeal(file: File, o: { template_id: string; license_id?: string; step_up?: string; profile?: Record<string, string>; page?: number; x?: number; y?: number; sign?: boolean }) {
    const fd = new FormData();
    fd.append("file", file); fd.append("template_id", o.template_id);
    // `license_id` + `step_up` is the supported path: the server builds the seal text from the
    // caller's own verified licence, so a name/number typed here cannot reach the document. `profile`
    // remains only for single-operator (desktop) mode, where there are no accounts to hold a licence.
    if (o.license_id) fd.append("license_id", o.license_id);
    if (o.step_up) fd.append("step_up", o.step_up);
    if (o.profile) fd.append("profile", JSON.stringify(o.profile));
    fd.append("page", String(o.page ?? 1)); fd.append("x", String(o.x ?? 36)); fd.append("y", String(o.y ?? 36));
    fd.append("sign", String(o.sign ?? true));
    const r = await fetch(this.url("/pdf/seal"), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return { blob: await r.blob(), sealed: r.headers.get("X-Seal-Sealed") === "true", compliance: r.headers.get("X-Seal-Compliance") || "" };
  }
  /** The signed-in user's own verified PE/RA licenses — what the seal dialog offers. */
  myLicenses() { return this.json<{ licenses: ProfessionalLicense[] }>("/licenses/mine"); }
  };
}
