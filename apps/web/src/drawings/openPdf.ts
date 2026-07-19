import type { ApiClient, DocFolderNode } from "../api/client";
import { openPdfTakeoff, type TakeoffOpts } from "./pdfTakeoff";

/**
 * Open a server-hosted PDF (by URL) in the in-app markup viewer — the single entry every
 * PDF surface routes through so a stored/generated PDF can be viewed, marked up, and (when
 * `opts.onSave` is provided) saved back to its source. The URL is fetched with the client's
 * auth headers, so authenticated download endpoints work without a signed URL.
 */
export async function openPdfUrl(api: ApiClient, url: string, name: string, opts: TakeoffOpts = {}): Promise<void> {
  // MARKUP-2a: every server-PDF editor session gets the project stamp library in its stamp picker
  // (review/inspection/status templates fan out per disposition) unless the caller overrides.
  opts.stamps ??= () => api.stampLibrary().then((r) => r.templates);
  await openPdfTakeoff({ url, name, headers: api.authHeaders() }, opts);
}

/** A save-back that files the (marked-up) PDF into the Document Manager — prompts for a standard
 *  folder. Use as `onSave` for generated PDFs (reports, statements) that have no record home. */
export function saveToDocuments(api: ApiClient, pid: string) {
  return async (pdf: Blob, name: string): Promise<void> => {
    const { nodes } = await api.documentsTree(pid);
    if (!nodes?.length) throw new Error("no document folders in this project");
    const path = await pickFolder(nodes, name);
    if (!path) return;                                            // user cancelled
    await api.uploadDocument(pid, path, new File([pdf], name, { type: "application/pdf" }));
  };
}

/** Minimal folder-pick modal for saveToDocuments. Resolves the chosen folder path (or null). */
function pickFolder(nodes: DocFolderNode[], name: string): Promise<string | null> {
  return new Promise((res) => {
    const ov = document.createElement("div");
    ov.style.cssText = "position:fixed;inset:0;z-index:400;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center";
    const box = document.createElement("div");
    box.style.cssText = "background:var(--panel,#23262d);color:var(--fg,#eee);border:1px solid var(--line,#3a3f47);border-radius:8px;padding:16px;min-width:320px;max-width:90vw";
    box.innerHTML = `<div style="font-weight:600;margin-bottom:4px">Save to Documents</div><div class="meta" style="margin-bottom:10px">${name} → choose a standard folder</div>`;
    const sel = document.createElement("select"); sel.className = "portal-filter"; sel.style.cssText = "width:100%;margin-bottom:12px";
    for (const n of nodes) { const o = document.createElement("option"); o.value = n.path; o.textContent = `${"— ".repeat(n.depth)}${n.label}`; sel.appendChild(o); }
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end";
    const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel";
    const ok = document.createElement("button"); ok.className = "file-btn"; ok.textContent = "Save revision";
    const done = (v: string | null) => { ov.remove(); res(v); };
    cancel.onclick = () => done(null);
    ok.onclick = () => done(sel.value || null);
    ov.onclick = (e) => { if (e.target === ov) done(null); };
    row.append(cancel, ok); box.append(sel, row); ov.appendChild(box); document.body.appendChild(ov);
  });
}
