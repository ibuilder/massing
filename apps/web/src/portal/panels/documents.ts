import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import { confirmModal } from "../../ui/modal";
import type { DocFile, DocFolderNode } from "../../api/client";
import type { PanelContext } from "../panelContext";

/**
 * Document Control — an elFinder-style file manager (F4). Two panes: the standard, role-based folder
 * tree on the left (counts + required-doc gaps + owner role), the selected folder's files on the right
 * (revision, CDE state, discipline, download / move / delete). Uploads auto-name to the information
 * standard and supersede prior revisions. Backed by docmanager.py over object storage.
 */
export async function renderDocuments(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("📁 Documents", () => { ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav(); }));
  const pid = ctx.host.projectId();
  if (!pid) { root.innerHTML = noProjectHtml("Documents"); return; }
  const api = ctx.host.api;

  // health strip
  const health = el("div", "meta"); health.style.cssText = "margin-bottom:8px";
  health.textContent = "loading document-control health…";
  root.appendChild(health);
  void api.documentsHealth(pid).then((h) => {
    const p = (v: number | null) => (v == null ? "—" : `${v}%`);
    health.innerHTML = `📄 <b>${h.total_files}</b> on file · naming <b>${p(h.naming_compliance_pct)}</b> · `
      + `required coverage <b>${p(h.required_coverage_pct)}</b> · revision control <b>${p(h.revision_control_pct)}</b>`
      + (h.superseded_kept ? ` · <span class="meta">${h.superseded_kept} superseded kept</span>` : "");
  }).catch(() => { health.textContent = ""; });

  // controls: filter the tree by owner role, or check required-doc gaps for a design phase
  const controls = el("div"); controls.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px";
  const roleSel = el("select", "portal-filter") as HTMLSelectElement;
  roleSel.setAttribute("aria-label", "Filter folders by owner role");
  roleSel.innerHTML = ["All roles", "PM", "Superintendent", "Architect", "Engineer", "QS"]
    .map((r) => `<option>${r}</option>`).join("");
  const phaseSel = el("select", "portal-filter") as HTMLSelectElement;
  phaseSel.setAttribute("aria-label", "Check required documents for a design phase");
  phaseSel.innerHTML = `<option value="">Phase gaps…</option>`
    + ["SD", "DD", "CD", "CA", "CLOSEOUT"].map((p) => `<option>${p}</option>`).join("");
  controls.append(roleSel, phaseSel); root.appendChild(controls);

  // two-pane, but wraps to stacked on narrow viewports (min-width:0 lets the table scroll, not overflow)
  const wrap = el("div"); wrap.style.cssText = "display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap";
  const left = el("div", "dash-card");
  left.style.cssText = "flex:1 1 280px;min-width:0;max-height:70vh;overflow:auto;padding:6px";
  const right = el("div", "dash-card");
  right.style.cssText = "flex:2 1 360px;min-width:0;max-height:70vh;overflow:auto";
  wrap.append(left, right); root.appendChild(wrap);

  let nodes: DocFolderNode[] = [];
  let selected = "";

  const stateChip = (s: string) => {
    const color: Record<string, string> = { published: "#16a34a", shared: "#2563eb", wip: "#a16207",
      archived: "#6b7280" };
    const c = el("span"); c.textContent = s;
    c.style.cssText = `font-size:10px;padding:1px 6px;border-radius:8px;color:#fff;background:${color[s] || "#6b7280"}`;
    return c;
  };

  async function loadFolder(path: string) {
    selected = path;
    // re-highlight tree
    left.querySelectorAll("[data-fp]").forEach((n) => {
      (n as HTMLElement).style.background = (n as HTMLElement).dataset.fp === path ? "var(--hover,#e5edff)" : "";
    });
    right.innerHTML = ""; right.appendChild(el("div", "meta")).textContent = "loading…";
    let data;
    try { data = await api.documentsFolder(pid!, path); } catch (e) { right.textContent = `failed: ${(e as Error).message}`; return; }
    right.innerHTML = "";
    const head = el("div"); head.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px";
    const h = el("div"); h.style.fontWeight = "600";
    h.innerHTML = `${esc(path)} ${data.owner_role ? `<span class="meta">· owner: ${esc(data.owner_role)}</span>` : ""}`;
    head.appendChild(h);
    // upload control
    const up = el("label", "btn"); up.textContent = "⬆ Upload"; up.style.cursor = "pointer";
    const file = el("input") as HTMLInputElement; file.type = "file"; file.style.display = "none";
    up.appendChild(file);
    file.onchange = async () => {
      const f = file.files?.[0]; if (!f) return;
      up.textContent = "uploading…";
      try {
        const r = await api.uploadDocument(pid!, path, f, { title: f.name.replace(/\.[^.]+$/, "") });
        toast(r.superseded ? `Uploaded ${r.entry.revision} (superseded prior)` : `Uploaded ${r.entry.name}`);
        if (!r.naming.valid) toast(`Naming note: ${r.naming.issues[0] || "non-standard"}`);
        await refreshTreeCounts(); await loadFolder(path);
      } catch (e) { toast(`Upload failed: ${(e as Error).message}`); up.textContent = "⬆ Upload"; }
    };
    head.appendChild(up); right.appendChild(head);

    if (!data.files.length) { right.appendChild(el("div", "meta")).textContent = "No files in this folder yet."; return; }
    const t = el("table", "portal-table") as HTMLTableElement; t.style.cssText = "width:100%;font-size:12px";
    t.innerHTML = "<thead><tr><th scope=\"col\">Document</th><th scope=\"col\">Disc.</th>"
      + "<th scope=\"col\">Rev</th><th scope=\"col\">State</th><th scope=\"col\">Uploaded</th>"
      + "<th scope=\"col\"></th></tr></thead>";
    const tb = el("tbody");
    for (const f of data.files) tb.appendChild(fileRow(f, path));
    t.appendChild(tb); right.appendChild(t);
  }

  function fileRow(f: DocFile, path: string): HTMLElement {
    const el2 = (t: string) => document.createElement(t);
    const tr = el2("tr");
    const link = el2("a") as HTMLAnchorElement;
    link.href = api.documentDownloadUrl(pid!, f.id); link.textContent = f.name; link.target = "_blank"; link.setAttribute("download", "");
    const nameTd = el2("td"); nameTd.appendChild(link);
    const disc = el2("td"); disc.textContent = f.discipline || "—";
    const rev = el2("td"); rev.textContent = f.revision || "—";
    const st = el2("td"); st.appendChild(stateChip(f.cde_state));
    const when = el2("td"); when.textContent = (f.uploaded_at || "").replace("T", " ");
    const act = el2("td"); act.style.whiteSpace = "nowrap";
    // move dropdown
    const mv = el2("select") as HTMLSelectElement; mv.title = "Move to folder";
    mv.style.cssText = "font-size:11px;max-width:120px";
    mv.innerHTML = `<option value="">move…</option>` + nodes.filter((n) => n.path !== path)
      .map((n) => `<option value="${esc(n.path)}">${"— ".repeat(n.depth)}${esc(n.label)}</option>`).join("");
    mv.onchange = async () => {
      if (!mv.value) return;
      try { await api.moveDocument(pid!, f.id, mv.value); toast("Moved"); await refreshTreeCounts(); await loadFolder(path); }
      catch (e) { toast(`Move failed: ${(e as Error).message}`); }
    };
    const del = el2("button") as HTMLButtonElement; del.textContent = "🗑"; del.title = "Delete";
    del.style.cssText = "background:none;border:none;cursor:pointer";
    del.onclick = async () => {
      const ok = await confirmModal("Delete document", `Delete ${f.name}?\nThe file is removed from ${path}.`,
        "Delete", true);
      if (!ok) return;
      try { await api.deleteDocument(pid!, f.id); toast("Deleted"); await refreshTreeCounts(); await loadFolder(path); }
      catch (e) { toast(`Delete failed: ${(e as Error).message}`); }
    };
    // PDFs open in the in-app viewer for markup; saving supersedes to a new revision (docmanager versioning)
    const extras: HTMLElement[] = [];
    if (/\.pdf$/i.test(f.name)) {
      const mk = el2("button") as HTMLButtonElement; mk.textContent = "✎"; mk.title = "Open in viewer & mark up (saves a new revision)";
      mk.style.cssText = "background:none;border:none;cursor:pointer";
      mk.onclick = async () => {
        const { openPdfUrl } = await import("../../drawings/openPdf");
        await openPdfUrl(api, api.documentDownloadUrl(pid!, f.id), f.name, {
          saveLabel: "Save as new revision",
          onSave: async (blob) => {
            await api.uploadDocument(pid!, path, new File([blob], f.name, { type: "application/pdf" }),
              f.discipline ? { discipline: f.discipline } : {});
            await refreshTreeCounts(); await loadFolder(path);
          },
        });
      };
      extras.push(mk);
    }
    act.append(mv, ...extras, del);
    tr.append(nameTd, disc, rev, st, when, act);
    return tr;
  }

  function renderTree(list: DocFolderNode[] = nodes) {
    left.innerHTML = "";
    const title = el("div"); title.style.cssText = "font-weight:600;padding:4px 6px"; title.textContent = "Standard folders";
    left.appendChild(title);
    if (!list.length) { const e = el("div", "meta"); e.style.padding = "6px"; e.textContent = "No folders for this filter."; left.appendChild(e); return; }
    for (const n of list) {
      const row = el("div"); row.dataset.fp = n.path;
      // real button semantics: keyboard-focusable + Enter/Space activate (the primary nav surface)
      row.setAttribute("role", "button"); row.tabIndex = 0;
      row.setAttribute("aria-label", `${n.label}${n.count ? `, ${n.count} files` : ", empty"}${n.gap ? ", required" : ""}`);
      row.style.cssText = `padding:3px 6px;cursor:pointer;border-radius:4px;display:flex;align-items:center;gap:6px;`
        + `padding-left:${6 + n.depth * 14}px;font-weight:${n.depth === 0 ? 600 : 400};outline-offset:-2px`;
      const label = el("span"); label.textContent = `📁 ${n.label}`;
      row.appendChild(label);
      if (n.count) { const b = el("span", "meta"); b.textContent = String(n.count); b.style.cssText = "font-size:10px;background:var(--hover,#e5edff);border-radius:8px;padding:0 6px"; row.appendChild(b); }
      if (n.gap) { const g = el("span"); g.textContent = "⚠"; g.title = "required — no documents yet"; row.appendChild(g); }
      if (n.owner_role) { const o = el("span", "meta"); o.textContent = n.owner_role; o.style.fontSize = "10px"; o.style.marginLeft = "auto"; row.appendChild(o); }
      const go = () => void loadFolder(n.path);
      row.onclick = go;
      row.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } };
      left.appendChild(row);
    }
  }

  async function refreshTreeCounts() {
    try { const t = await api.documentsTree(pid!); nodes = t.nodes; renderTree();
      if (selected) left.querySelectorAll("[data-fp]").forEach((x) => {
        if ((x as HTMLElement).dataset.fp === selected) (x as HTMLElement).style.background = "var(--hover,#e5edff)"; });
    } catch { /* ignore */ }
  }

  // role filter → the role-based view of the tree (uses the by-role endpoint)
  roleSel.onchange = async () => {
    if (roleSel.selectedIndex === 0) { renderTree(nodes); return; }
    try { const r = await api.documentsByRole(pid, roleSel.value); renderTree(r.folders); }
    catch { renderTree(nodes); }
  };
  // phase-gaps → required-document checklist for a design phase, shown in the right pane
  phaseSel.onchange = async () => {
    if (!phaseSel.value) return;
    right.innerHTML = ""; (right.appendChild(el("div", "meta")) as HTMLElement).textContent = "checking…";
    try {
      const g = await api.documentsPhaseGaps(pid, phaseSel.value);
      right.innerHTML = "";
      const h = el("div"); h.style.cssText = "font-weight:600;margin-bottom:6px";
      h.textContent = `${g.phase} required documents — ${g.complete ? "all present ✅" : `${g.missing} missing`}`;
      const tb = el("table", "portal-table") as HTMLTableElement; tb.style.cssText = "width:100%;font-size:12px";
      tb.innerHTML = "<thead><tr><th scope=\"col\">Folder</th><th scope=\"col\">Needs</th>"
        + "<th scope=\"col\">Status</th></tr></thead>";
      const body = el("tbody");
      for (const it of g.items) {
        const tr = el("tr");
        tr.innerHTML = `<td>${esc(it.folder)}</td><td>${esc(it.description)}</td>`
          + `<td>${it.present ? "✅" : "⚠ missing"}</td>`;
        body.appendChild(tr);
      }
      tb.appendChild(body); right.append(h, tb);
    } catch (e) { right.textContent = `failed: ${(e as Error).message}`; }
  };

  try {
    const t = await api.documentsTree(pid);
    nodes = t.nodes; renderTree();
    right.innerHTML = `<div class="meta" style="padding:8px">Select a folder to view its documents. `
      + `${t.required_gaps.length ? `<b>${t.required_gaps.length}</b> required folder(s) still empty.` : "All required folders populated."}</div>`;
    if (nodes.length) void loadFolder(nodes[0].path);
  } catch (e) {
    left.textContent = `failed to load folders: ${(e as Error).message}`;
  }
}
