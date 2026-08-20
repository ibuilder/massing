/**
 * R31-CITE-HIGHLIGHT — one control for a document citation.
 *
 * Opening used to `window.open` a blob tab: the page number was in the button, the PDF was in
 * another context, and `citeLocate` had nothing to draw on. The in-app takeoff viewer supplies
 * `PageWords` (`PdfDocument.textItems`) so the passage can be boxed. A text-only ingest stays
 * inert text — `openable: false` is the server's answer, not a guess.
 */
import type { ApiClient, DocCitation } from "../../api/client";
import { toast } from "../../ui/feedback";

export async function openCitedSource(
  api: ApiClient,
  pid: string,
  c: DocCitation,
  openPdf?: (source: File, opts: { cite: { page: number; snippet?: string; docId?: string } }) => Promise<void>,
): Promise<void> {
  if (!c.doc_id) throw new Error("citation has no document id");
  const blob = await api.doctextSource(pid, c.doc_id);
  const name = `${(c.doc || "source").replace(/[^\w.-]+/g, "_")}.pdf`;
  const file = new File([blob], name, { type: "application/pdf" });
  const open = openPdf ?? (await import("../../drawings/pdfTakeoff")).openPdfTakeoff;
  await open(file, {
    cite: { page: c.page, snippet: c.snippet, docId: c.doc_id },
  });
}

export function citationEl(api: ApiClient, pid: string, c: DocCitation): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "meta";
  wrap.style.cssText = "margin:2px 0 0 8px;border-left:2px solid var(--line);padding-left:6px";
  const head = document.createElement(c.openable && c.doc_id ? "button" : "span");
  const label = `p.${c.page}${c.section ? " §" + c.section : ""}${c.doc ? " — " + c.doc : ""}`;
  head.textContent = label;
  if (c.openable && c.doc_id) {
    const btn = head as HTMLButtonElement;
    btn.className = "file-btn";
    btn.style.cssText = "padding:1px 6px;font-size:11px";
    btn.title = "Open the source and highlight the cited passage";
    btn.onclick = async () => {
      const was = btn.textContent; btn.disabled = true; btn.textContent = "opening…";
      try {
        await openCitedSource(api, pid, c);
      } catch (e) {
        toast(`Could not open source: ${(e as Error).message}`, "error");
      } finally { btn.disabled = false; btn.textContent = was; }
    };
  }
  wrap.appendChild(head);
  if (c.snippet) {
    const q = document.createElement("div");
    q.style.cssText = "font-style:italic;margin-top:2px";
    q.textContent = `“${c.snippet}”`;
    wrap.appendChild(q);
  }
  return wrap;
}
