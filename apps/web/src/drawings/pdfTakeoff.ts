/**
 * PDF takeoff & markup — open a PDF drawing, calibrate its scale, then measure distances / areas,
 * count items, and drop annotations directly on the sheet, with running totals and CSV export.
 *
 * Everything is stored in PDF user-space (click px ÷ render scale) so measurements stay correct as
 * you zoom. pdf.js renders the page; an SVG overlay carries the vector tools. The worker is bundled
 * locally (Vite ?url) — offline, no CDN (CLAUDE.md).
 */
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { toast } from "../ui/feedback";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

type Mode = "pan" | "distance" | "area" | "count" | "rect" | "calibrate" | "text" | "stamp";
interface Pt { x: number; y: number }                       // PDF user-space
export interface Measure { id: number; kind: Mode; pts: Pt[]; value: number; unit: string; label: string; page: number; text?: string }

// Dynamic stamps (Bluebeam-style): {{user}}/{{date}}/{{time}}/{{file}} resolve at placement time.
const STAMPS = ["APPROVED", "REVIEWED", "FOR CONSTRUCTION", "NOT FOR CONSTRUCTION", "VOID",
                "AS-BUILT", "REVISE & RESUBMIT", "{{user}} · {{date}}", "REVISED {{date}}"];

const shoelace = (p: Pt[]) => Math.abs(p.reduce((s, a, i) => {
  const b = p[(i + 1) % p.length]; return s + (a.x * b.y - b.x * a.y);
}, 0)) / 2;
const pathLen = (p: Pt[]) => p.slice(1).reduce((s, a, i) => s + Math.hypot(a.x - p[i].x, a.y - p[i].y), 0);

/** A PDF to open: a local File, or a server URL (fetched with optional auth headers). */
export type PdfSource = File | { url: string; name: string; headers?: Record<string, string> };
/** Optional wiring so the marked-up PDF can be saved back to its source (attachment / document / etc.). */
export interface TakeoffOpts {
  onSave?: (pdf: Blob, name: string) => Promise<void>; saveLabel?: string;
  /** Persist the structured markups to a shared store (e.g. a drawing sheet) so they reload + promote to
   *  RFI like pins — rather than only flattening to a throwaway PDF. `save` also gets a `norm` helper that
   *  maps a markup's anchor to a page-normalized (0..1) coordinate, so the SVG sheet viewer can place the
   *  same markup in its own content box (a shared coordinate space across the two 2D editors). */
  persist?: {
    load: () => Promise<Measure[]>;
    save: (m: Measure[], norm: (m: Measure) => { nx: number; ny: number }) => Promise<void>;
  };
}

export async function openPdfTakeoff(source?: PdfSource, opts: TakeoffOpts = {}): Promise<void> {
  let docName = "document.pdf";
  let srcBuf: ArrayBuffer;
  if (source && "url" in source) {
    docName = source.name || "document.pdf";
    try {
      const r = await fetch(source.url, { headers: source.headers });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      srcBuf = await r.arrayBuffer();
    } catch (e) { toast(`couldn't fetch PDF: ${(e as Error).message}`, "error"); return; }
  } else {
    const f = source ?? await pickPdf();
    if (!f) return;
    docName = f.name; srcBuf = await f.arrayBuffer();
  }
  let doc: pdfjsLib.PDFDocumentProxy;
  // pdf.js may transfer/detach its input buffer — hand it a private copy, keep srcBuf for pdf-lib export.
  try { doc = await pdfjsLib.getDocument({ data: new Uint8Array(srcBuf.slice(0)) }).promise; }
  catch (e) { toast(`couldn't open PDF: ${(e as Error).message}`, "error"); return; }

  let pageNum = 1, scale = 1, mode: Mode = "distance";
  let unitsPerPt = 0, unit = "m";                            // calibration (real units per PDF point)
  let draft: Pt[] = [];
  const measures: Measure[] = [];
  let seq = 0;
  let stampTpl = STAMPS[0];
  // resolve a dynamic stamp's {{fields}} at placement time
  const resolveStamp = (tpl: string): string => {
    const now = new Date();
    let user = localStorage.getItem("aec_markup_user") || "";
    if (/\{\{user\}\}/.test(tpl) && !user) { user = (prompt("Your name (for stamps):", "") || "").trim(); if (user) localStorage.setItem("aec_markup_user", user); }
    const ctx: Record<string, string> = { user: user || "—", file: docName,
      date: now.toISOString().slice(0, 10), time: now.toTimeString().slice(0, 5),
      day: String(now.getDate()), month: String(now.getMonth() + 1), year: String(now.getFullYear()) };
    return tpl.replace(/\{\{(\w+)\}\}/g, (_, k) => ctx[k] ?? "");
  };

  // ---- overlay shell -------------------------------------------------------
  const ov = document.createElement("div");
  ov.style.cssText = "position:fixed;inset:0;z-index:250;background:var(--bg,#1b1d22);display:flex;flex-direction:column";
  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;gap:6px;align-items:center;padding:8px 10px;border-bottom:1px solid var(--line);flex-wrap:wrap";
  const body = document.createElement("div"); body.style.cssText = "flex:1;display:flex;min-height:0";
  const viewport = document.createElement("div");
  viewport.style.cssText = "flex:1;overflow:auto;position:relative;background:#33363d;display:flex;align-items:flex-start;justify-content:center;padding:16px";
  const stage = document.createElement("div"); stage.style.cssText = "position:relative;line-height:0";
  const canvas = document.createElement("canvas");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.style.cssText = "position:absolute;inset:0;cursor:crosshair";
  stage.append(canvas, svg); viewport.append(stage);
  const sidebar = document.createElement("div");
  sidebar.style.cssText = "width:260px;border-left:1px solid var(--line);display:flex;flex-direction:column;overflow:auto;padding:10px;gap:8px";
  body.append(viewport, sidebar); ov.append(bar, body); document.body.appendChild(ov);

  // ---- toolbar -------------------------------------------------------------
  const tbtn = (label: string, title: string, on: () => void, active = false) => {
    const b = document.createElement("button"); b.className = "tool-btn" + (active ? " on" : "");
    b.textContent = label; b.title = title; b.onclick = on; return b;
  };
  const setMode = (m: Mode) => { mode = m; draft = []; buildBar(); drawOverlay(); };
  function buildBar() {
    bar.innerHTML = "";
    const name = document.createElement("span"); name.className = "meta"; name.style.fontWeight = "600";
    name.textContent = docName; bar.append(name);
    const sp = document.createElement("span"); sp.style.flex = "1"; bar.append(sp);
    bar.append(
      tbtn("⟸", "Previous page", () => gotoPage(pageNum - 1)),
      tbtn(`${pageNum}/${doc.numPages}`, "Page", () => {}),
      tbtn("⟹", "Next page", () => gotoPage(pageNum + 1)),
      tbtn("−", "Zoom out", () => setScale(scale / 1.25)),
      tbtn("+", "Zoom in", () => setScale(scale * 1.25)),
      tbtn("📏 Calibrate", calOk() ? `Scale set: 1 unit shown in ${unit}` : "Set the drawing scale (required)", () => setMode("calibrate"), mode === "calibrate"),
      tbtn("📐 Distance", "Measure distance", () => setMode("distance"), mode === "distance"),
      tbtn("▱ Area", "Measure area", () => setMode("area"), mode === "area"),
      tbtn("# Count", "Count items", () => setMode("count"), mode === "count"),
      tbtn("▭ Rect", "Rectangle annotation", () => setMode("rect"), mode === "rect"),
      tbtn("𝗧 Text", "Text markup", () => setMode("text"), mode === "text"),
      tbtn("🔖 Stamp", "Place the selected stamp", () => setMode("stamp"), mode === "stamp"),
      stampPicker(),
      tbtn("✋ Pan", "Pan / select", () => setMode("pan"), mode === "pan"),
      tbtn("⌫ Undo", "Remove last point / measurement", undo),
      tbtn("💾 Save", "Save markups as a tool set (JSON)", saveSet),
      tbtn("📂 Load", "Load a saved tool set (JSON)", loadSet),
      tbtn("↧ CSV", "Export takeoff as CSV", exportCsv),
      tbtn("⤓ PDF", "Download the marked-up PDF (markups burned in)", () => void exportPdf()),
      ...(opts.persist ? [tbtn("⭳ Save to sheet", "Persist these markups to the drawing sheet (reload + promote to RFI)", () => void saveMarkupsToSheet())] : []),
      ...(opts.onSave ? [tbtn("⭱ Save to source", opts.saveLabel || "Save the marked-up PDF back to its source", () => void saveToServer())] : []),
      tbtn("✕ Close", "Close takeoff", () => ov.remove()),
    );
  }
  const calOk = () => unitsPerPt > 0;
  function stampPicker(): HTMLSelectElement {
    const s = document.createElement("select"); s.className = "portal-filter"; s.title = "Stamp template"; s.style.maxWidth = "160px";
    for (const t of STAMPS) { const o = document.createElement("option"); o.value = t; o.textContent = t; s.appendChild(o); }
    s.value = stampTpl; s.onchange = () => { stampTpl = s.value; setMode("stamp"); };
    return s;
  }
  // Tool set = the serialized markup scene (calibration + markups) — save/share/reload, Bluebeam-style.
  function saveSet() {
    const data = JSON.stringify({ v: 1, calibration: { unitsPerPt, unit }, measures });
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([data], { type: "application/json" }));
    a.download = `${docName.replace(/\.pdf$/i, "")}-markups.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast(`saved ${measures.length} markups`, "success");
  }
  function loadSet() {
    const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".json,application/json";
    inp.onchange = async () => {
      const f = inp.files?.[0]; if (!f) return;
      try {
        const d = JSON.parse(await f.text());
        if (d.calibration) { unitsPerPt = d.calibration.unitsPerPt || unitsPerPt; unit = d.calibration.unit || unit; }
        if (Array.isArray(d.measures)) { measures.length = 0; for (const m of d.measures) { measures.push(m); if (m.id > seq) seq = m.id; } }
        buildBar(); renderList(); drawOverlay();
        toast(`loaded ${measures.length} markups`, "success");
      } catch (e) { toast(`couldn't load: ${(e as Error).message}`, "error"); }
    };
    inp.click();
  }

  // ---- page render ---------------------------------------------------------
  async function render() {
    const page = await doc.getPage(pageNum);
    const vp = page.getViewport({ scale });
    canvas.width = vp.width; canvas.height = vp.height;
    canvas.style.width = `${vp.width}px`; canvas.style.height = `${vp.height}px`;
    svg.setAttribute("width", String(vp.width)); svg.setAttribute("height", String(vp.height));
    svg.setAttribute("viewBox", `0 0 ${vp.width} ${vp.height}`);
    await page.render({ canvas, canvasContext: canvas.getContext("2d")!, viewport: vp }).promise;
    drawOverlay();
  }
  const setScale = (s: number) => { scale = Math.min(8, Math.max(0.2, s)); void render(); buildBar(); };
  const gotoPage = (n: number) => { if (n >= 1 && n <= doc.numPages) { pageNum = n; draft = []; void render(); buildBar(); } };

  // ---- interaction (coords stored in PDF user-space = screenPx / scale) -----
  const toPdf = (e: MouseEvent): Pt => { const r = svg.getBoundingClientRect(); return { x: (e.clientX - r.left) / scale, y: (e.clientY - r.top) / scale }; };
  svg.addEventListener("click", (e) => {
    if (mode === "pan") return;
    draft.push(toPdf(e));
    if (mode === "count" || mode === "text" || mode === "stamp") { commit(); draft = []; }  // single-click placement
    else if (mode === "calibrate" && draft.length === 2) calibrate();
    else if (mode === "rect" && draft.length === 2) commit();
    drawOverlay();
  });
  svg.addEventListener("dblclick", () => { if ((mode === "distance" && draft.length >= 2) || (mode === "area" && draft.length >= 3)) commit(); });

  function calibrate() {
    const px = Math.hypot(draft[1].x - draft[0].x, draft[1].y - draft[0].y);
    const ans = prompt("Real length of the drawn line (e.g. 5 m, 20 ft):", "5 m");
    draft = [];
    if (!ans) { drawOverlay(); return; }
    const m = ans.trim().match(/^([\d.]+)\s*(\w+)?/);
    if (!m || !+m[1] || px <= 0) { toast("couldn't read that length", "error"); return; }
    unit = m[2] || "m"; unitsPerPt = +m[1] / px;
    toast(`scale set — 1 ${unit} = ${(1 / unitsPerPt).toFixed(1)} pt`, "success");
    buildBar(); renderList();
  }
  function commit() {
    const needsCal = mode === "distance" || mode === "area";
    if (needsCal && !calOk()) { toast("calibrate the scale first (📏)", "error"); draft = []; return; }
    const pts = [...draft];
    let value = 0, u = unit, text: string | undefined;
    if (mode === "distance") { value = pathLen(pts) * unitsPerPt; }
    else if (mode === "area") { value = shoelace(pts) * unitsPerPt * unitsPerPt; u = unit + "²"; }
    else if (mode === "rect") { const w = Math.abs(pts[1].x - pts[0].x), h = Math.abs(pts[1].y - pts[0].y); value = calOk() ? w * h * unitsPerPt * unitsPerPt : 0; u = unit + "²"; }
    else if (mode === "count") { value = 1; u = "ea"; }
    else if (mode === "text") { text = (prompt("Markup text:", "") || "").trim(); if (!text) { draft = []; return; } u = ""; }
    else if (mode === "stamp") { text = resolveStamp(stampTpl); u = ""; }
    measures.push({ id: ++seq, kind: mode, pts, value, unit: u, label: text || `${mode} ${seq}`, page: pageNum, text });
    draft = []; drawOverlay(); renderList();
  }
  function undo() {
    if (draft.length) draft.pop();
    else measures.pop();
    drawOverlay(); renderList();
  }

  // ---- overlay + sidebar rendering -----------------------------------------
  const NS = "http://www.w3.org/2000/svg";
  const el = (n: string, a: Record<string, string>) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); return e; };
  function drawOverlay() {
    svg.innerHTML = "";
    const S = (p: Pt) => [p.x * scale, p.y * scale] as const;
    const drawShape = (kind: Mode, pts: Pt[], color: string, dash = false) => {
      if (kind === "count") { for (const p of pts) { const [x, y] = S(p); svg.append(el("circle", { cx: `${x}`, cy: `${y}`, r: "5", fill: color, "fill-opacity": "0.8" })); } return; }
      if (kind === "rect" && pts.length === 2) { const [x0, y0] = S(pts[0]), [x1, y1] = S(pts[1]); svg.append(el("rect", { x: `${Math.min(x0, x1)}`, y: `${Math.min(y0, y1)}`, width: `${Math.abs(x1 - x0)}`, height: `${Math.abs(y1 - y0)}`, fill: color, "fill-opacity": "0.15", stroke: color, "stroke-width": "1.5" })); return; }
      const d = pts.map((p, i) => `${i ? "L" : "M"}${S(p)[0]},${S(p)[1]}`).join(" ") + (kind === "area" ? " Z" : "");
      svg.append(el("path", { d, fill: kind === "area" ? color : "none", "fill-opacity": "0.15", stroke: color, "stroke-width": "1.8", ...(dash ? { "stroke-dasharray": "5 4" } : {}) }));
      for (const p of pts) { const [x, y] = S(p); svg.append(el("circle", { cx: `${x}`, cy: `${y}`, r: "3", fill: color })); }
    };
    const renderText = (m: Measure) => {
      const [x, y] = S(m.pts[0]); const stamp = m.kind === "stamp"; const col = stamp ? "#e2554a" : "#111";
      const fs = stamp ? 18 : 13;
      if (stamp) svg.append(el("rect", { x: `${x - 5}`, y: `${y - fs}`, width: `${(m.text || "").length * fs * 0.6 + 10}`, height: `${fs + 8}`, fill: col, "fill-opacity": "0.08", stroke: col, "stroke-width": "1.5" }));
      const t = el("text", { x: `${x}`, y: `${y}`, fill: col, "font-size": `${fs}`, "font-weight": "700", "font-family": "sans-serif" });
      t.textContent = m.text || ""; svg.append(t);
    };
    for (const m of measures) if (m.page === pageNum) {
      if (m.kind === "text" || m.kind === "stamp") renderText(m);
      else drawShape(m.kind, m.pts, m.kind === "area" || m.kind === "rect" ? "#33d17a" : "#ffd479");
    }
    if (draft.length) drawShape(mode, draft, mode === "calibrate" ? "#e2554a" : "#4a8cff", mode === "calibrate");
  }
  function renderList() {
    sidebar.innerHTML = "";
    const cal = document.createElement("div"); cal.className = "meta";
    cal.innerHTML = calOk() ? `Scale: <b>1 ${unit}</b> = ${(1 / unitsPerPt).toFixed(1)} pt` : `<b style="color:#e2554a">Not calibrated</b> — click 📏 Calibrate`;
    sidebar.append(cal);
    const totLen = measures.filter((m) => m.kind === "distance").reduce((s, m) => s + m.value, 0);
    const totArea = measures.filter((m) => m.kind === "area" || m.kind === "rect").reduce((s, m) => s + m.value, 0);
    const totCount = measures.filter((m) => m.kind === "count").length;
    const tot = document.createElement("div"); tot.className = "meta"; tot.style.cssText = "border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:6px 0";
    tot.innerHTML = `<div>Σ length: <b>${totLen.toFixed(2)} ${unit}</b></div><div>Σ area: <b>${totArea.toFixed(2)} ${unit}²</b></div><div>Σ count: <b>${totCount}</b></div>`;
    sidebar.append(tot);
    for (const m of measures) {
      const row = document.createElement("div"); row.className = "layer-row";
      const lbl = document.createElement("input"); lbl.value = m.label; lbl.className = "portal-filter"; lbl.style.cssText = "flex:1;font-size:12px";
      lbl.onchange = () => { m.label = lbl.value; };
      const v = document.createElement("span"); v.className = "meta"; v.style.whiteSpace = "nowrap";
      v.textContent = m.kind === "count" ? "1 ea" : `${m.value.toFixed(2)} ${m.unit}`;
      const del = document.createElement("button"); del.className = "tool-btn"; del.textContent = "✕";
      del.onclick = () => { const i = measures.indexOf(m); if (i >= 0) measures.splice(i, 1); drawOverlay(); renderList(); };
      row.append(lbl, v, del); sidebar.append(row);
    }
  }
  // ---- flatten markups into a real PDF (pdf-lib, MIT — the "persistence" layer) ------------------
  // Coords are stored in PDF.js viewport-at-scale-1 space = PDF points, TOP-LEFT origin. pdf-lib draws
  // BOTTOM-LEFT origin, so flip Y: pdfY = pageHeight − y. (Assumes page rotation 0 / cropbox=mediabox,
  // the common case for construction sheets — rotated pages would need the viewport transform.)
  // Flatten all markups into the PDF and return the bytes (shared by download + save-to-server).
  async function buildMarkedPdf(): Promise<Uint8Array | null> {
    if (!measures.length) { toast("nothing to export yet", "error"); return null; }
    try {
      const { PDFDocument, rgb, StandardFonts } = await import("pdf-lib");
      const out = await PDFDocument.load(srcBuf.slice(0));
      const font = await out.embedFont(StandardFonts.Helvetica);
      const pages = out.getPages();
      const YELLOW = rgb(1, 0.83, 0.47), GREEN = rgb(0.2, 0.82, 0.48), RED = rgb(0.89, 0.33, 0.29);
      for (const m of measures) {
        const pg = pages[(m.page ?? 1) - 1]; if (!pg) continue;
        const H = pg.getSize().height;
        const col = (m.kind === "area" || m.kind === "rect") ? GREEN : YELLOW;
        const P = (p: Pt) => ({ x: p.x, y: H - p.y });
        if (m.kind === "text" || m.kind === "stamp") {
          const q = P(m.pts[0]); const stamp = m.kind === "stamp"; const size = stamp ? 14 : 11;
          const txt = m.text || ""; const w = txt.length * size * 0.6 + 10;
          if (stamp) pg.drawRectangle({ x: q.x - 4, y: q.y - size - 2, width: w, height: size + 8, borderColor: RED, borderWidth: 1.5, color: RED, opacity: 0.08, borderOpacity: 1 });
          pg.drawText(txt, { x: q.x, y: q.y - size + 2, size, font, color: stamp ? RED : rgb(0, 0, 0) });
          continue;
        }
        if (m.kind === "count") {
          for (const p of m.pts) { const q = P(p); pg.drawCircle({ x: q.x, y: q.y, size: 4, color: col }); }
        } else if (m.kind === "rect" && m.pts.length === 2) {
          const a = P(m.pts[0]), b = P(m.pts[1]);
          pg.drawRectangle({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(b.x - a.x),
            height: Math.abs(b.y - a.y), borderColor: col, borderWidth: 1.5, color: col, opacity: 0.12, borderOpacity: 1 });
        } else {
          const pts = m.kind === "area" ? [...m.pts, m.pts[0]] : m.pts;
          for (let i = 1; i < pts.length; i++) { const s = P(pts[i - 1]), e = P(pts[i]); pg.drawLine({ start: s, end: e, thickness: 1.8, color: col }); }
        }
        const lp = P(m.pts[0]);
        const txt = `${m.label}: ${m.kind === "count" ? "1 ea" : m.value.toFixed(2) + " " + m.unit}`;
        pg.drawText(txt, { x: lp.x + 4, y: lp.y + 4, size: 8, font, color: col });
      }
      return await out.save();
    } catch (e) { toast(`PDF export failed: ${(e as Error).message}`, "error"); return null; }
  }
  async function exportPdf() {
    const bytes = await buildMarkedPdf(); if (!bytes) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" }));
    a.download = `${docName.replace(/\.pdf$/i, "")}-markup.pdf`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast(`exported marked-up PDF (${measures.length} markups)`, "success");
  }
  // Save the flattened markup back to its source (attachment / document version) via the host callback.
  async function saveToServer() {
    if (!opts.onSave) return;
    const bytes = await buildMarkedPdf(); if (!bytes) return;
    try { await opts.onSave(new Blob([bytes as BlobPart], { type: "application/pdf" }), docName); toast(opts.saveLabel ? `${opts.saveLabel} — saved` : "saved to server", "success"); }
    catch (e) { toast(`save failed: ${(e as Error).message}`, "error"); }
  }
  // Persist the structured markups to the shared sheet store (reload + promote to RFI like pins).
  const _pageDims = new Map<number, { w: number; h: number }>();
  async function pageDims(n: number): Promise<{ w: number; h: number }> {
    if (!_pageDims.has(n)) {
      const vp = (await doc.getPage(n)).getViewport({ scale: 1 });
      _pageDims.set(n, { w: vp.width, h: vp.height });
    }
    return _pageDims.get(n)!;
  }
  async function saveMarkupsToSheet() {
    if (!opts.persist) return;
    try {
      for (const p of new Set(measures.map((m) => m.page))) await pageDims(p);  // prime the cache
      const norm = (m: Measure) => {
        const d = _pageDims.get(m.page) || { w: 1, h: 1 }; const a = m.pts[0] || { x: 0, y: 0 };
        return { nx: d.w ? a.x / d.w : 0, ny: d.h ? a.y / d.h : 0 };
      };
      await opts.persist.save(measures, norm);
      toast(`saved ${measures.length} markups to the sheet`, "success");
    } catch (e) { toast(`save failed: ${(e as Error).message}`, "error"); }
  }
  function exportCsv() {
    if (!measures.length) { toast("nothing to export yet", "error"); return; }
    const rows = [["label", "type", "quantity", "unit"], ...measures.map((m) => [m.label, m.kind, m.kind === "count" ? "1" : m.value.toFixed(3), m.unit])];
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `${docName.replace(/\.pdf$/i, "")}-takeoff.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast(`exported ${measures.length} takeoff lines`, "success");
  }

  // Load any markups already persisted for this sheet, so the 2D editor is a live view of the sheet.
  if (opts.persist) {
    try { for (const mm of await opts.persist.load()) { mm.id = ++seq; measures.push(mm); } }
    catch (e) { toast(`couldn't load sheet markups: ${(e as Error).message}`, "error"); }
  }
  buildBar(); renderList(); await render();
  // fit width on first open
  const avail = viewport.clientWidth - 40; if (canvas.width > avail) setScale(scale * (avail / canvas.width));
  // test hook (mirrors __viewer): drive modes/clicks/commit from preview_eval
  (window as unknown as Record<string, unknown>).__takeoff = {
    setMode, click: (xPdf: number, yPdf: number) => { draft.push({ x: xPdf, y: yPdf }); if (mode === "count") { commit(); draft = []; } else if (mode === "calibrate" && draft.length === 2) calibrate(); else if (mode === "rect" && draft.length === 2) commit(); drawOverlay(); },
    commit, measures, calibrated: () => calOk(), exportPdf, saveSet,
    placeText: (t: string, x: number, y: number) => { measures.push({ id: ++seq, kind: "text", pts: [{ x, y }], value: 0, unit: "", label: t, page: pageNum, text: t }); drawOverlay(); renderList(); },
    placeStamp: (tpl: string, x: number, y: number) => { const t = resolveStamp(tpl); measures.push({ id: ++seq, kind: "stamp", pts: [{ x, y }], value: 0, unit: "", label: t, page: pageNum, text: t }); drawOverlay(); renderList(); },
    close: () => ov.remove(),
  };
}

function pickPdf(): Promise<File | null> {
  return new Promise((resolve) => {
    const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".pdf,application/pdf";
    inp.onchange = () => resolve(inp.files?.[0] ?? null);
    inp.click();
  });
}
