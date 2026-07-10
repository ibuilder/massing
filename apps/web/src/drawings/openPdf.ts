import type { ApiClient } from "../api/client";
import { openPdfTakeoff, type TakeoffOpts } from "./pdfTakeoff";

/**
 * Open a server-hosted PDF (by URL) in the in-app markup viewer — the single entry every
 * PDF surface routes through so a stored/generated PDF can be viewed, marked up, and (when
 * `opts.onSave` is provided) saved back to its source. The URL is fetched with the client's
 * auth headers, so authenticated download endpoints work without a signed URL.
 */
export async function openPdfUrl(api: ApiClient, url: string, name: string, opts: TakeoffOpts = {}): Promise<void> {
  await openPdfTakeoff({ url, name, headers: api.authHeaders() }, opts);
}
