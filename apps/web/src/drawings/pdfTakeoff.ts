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

type Mode = "pan" | "distance" | "area" | "count" | "rect" | "calibrate";
interface Pt { x: number; y: number }                       // PDF user-space
interface Measure { id: number; kind: Mode; pts: Pt[]; value: number; unit: string; label: string; page: number }

const shoelace = (p: Pt[]) => Math.abs(p.reduce((s, a, i) => {
  const b = p[(i + 1) % p.length]; return s + (a.x * b.y - b.x * a.y);
}, 0)) / 2;
const pathLen = (p: Pt[]) => p.slice(1).reduce((s, a, i) => s + Math.hypot(a.x - p[i].x, a.y - p[i].y), 0);

export async function openPdfTakeoff(preFile?: File): Promise<void> {
  const file = preFile ?? await pickPdf();
  if (!file) return;
  let doc: pdfjsLib.PDFDocumentProxy;
  try { doc = await pdfjsLib.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise; }
  catch (e) { toast(`couldn't open PDF: ${(e as Error).message}`, "error"); return; }

  let pageNum = 1, scale = 1, mode: Mode = "distance";
  let unitsPerPt = 0, unit = "m";                            // calibration (real units per PDF point)
  let draft: Pt[] = [];
  const measures: Measure[] = [];
  let seq = 0;

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
    name.textContent = file!.name; bar.append(name);
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
      tbtn("✋ Pan", "Pan / select", () => setMode("pan"), mode === "pan"),
      tbtn("⌫ Undo", "Remove last point / measurement", undo),
      tbtn("↧ CSV", "Export takeoff as CSV", exportCsv),
      tbtn("⤓ PDF", "Download the marked-up PDF (markups burned in)", () => void exportPdf()),
      tbtn("✕ Close", "Close takeoff", () => ov.remove()),
    );
  }
  const calOk = () => unitsPerPt > 0;

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
    if (mode === "count") { commit(); draft = []; }          // each click = one count
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
    if (mode !== "rect" && mode !== "count" && !calOk()) { toast("calibrate the scale first (📏)", "error"); draft = []; return; }
    const pts = [...draft];
    let value = 0, u = unit;
    if (mode === "distance") { value = pathLen(pts) * unitsPerPt; }
    else if (mode === "area") { value = shoelace(pts) * unitsPerPt * unitsPerPt; u = unit + "²"; }
    else if (mode === "rect") { const w = Math.abs(pts[1].x - pts[0].x), h = Math.abs(pts[1].y - pts[0].y); value = calOk() ? w * h * unitsPerPt * unitsPerPt : 0; u = unit + "²"; }
    else if (mode === "count") { value = 1; u = "ea"; }
    measures.push({ id: ++seq, kind: mode, pts, value, unit: u, label: `${mode} ${seq}`, page: pageNum });
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
    for (const m of measures) if (m.page === pageNum) drawShape(m.kind, m.pts, m.kind === "area" || m.kind === "rect" ? "#33d17a" : "#ffd479");
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
  async function exportPdf() {
    if (!measures.length) { toast("nothing to export yet", "error"); return; }
    try {
      const { PDFDocument, rgb, StandardFonts } = await import("pdf-lib");
      const out = await PDFDocument.load(await file!.arrayBuffer());
      const font = await out.embedFont(StandardFonts.Helvetica);
      const pages = out.getPages();
      const YELLOW = rgb(1, 0.83, 0.47), GREEN = rgb(0.2, 0.82, 0.48);
      for (const m of measures) {
        const pg = pages[(m.page ?? 1) - 1]; if (!pg) continue;
        const H = pg.getSize().height;
        const col = (m.kind === "area" || m.kind === "rect") ? GREEN : YELLOW;
        const P = (p: Pt) => ({ x: p.x, y: H - p.y });
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
      const bytes = await out.save();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" }));
      a.download = `${file!.name.replace(/\.pdf$/i, "")}-markup.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      toast(`exported marked-up PDF (${measures.length} markups)`, "success");
    } catch (e) { toast(`PDF export failed: ${(e as Error).message}`, "error"); }
  }
  function exportCsv() {
    if (!measures.length) { toast("nothing to export yet", "error"); return; }
    const rows = [["label", "type", "quantity", "unit"], ...measures.map((m) => [m.label, m.kind, m.kind === "count" ? "1" : m.value.toFixed(3), m.unit])];
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `${file!.name.replace(/\.pdf$/i, "")}-takeoff.csv`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast(`exported ${measures.length} takeoff lines`, "success");
  }

  buildBar(); renderList(); await render();
  // fit width on first open
  const avail = viewport.clientWidth - 40; if (canvas.width > avail) setScale(scale * (avail / canvas.width));
  // test hook (mirrors __viewer): drive modes/clicks/commit from preview_eval
  (window as unknown as Record<string, unknown>).__takeoff = {
    setMode, click: (xPdf: number, yPdf: number) => { draft.push({ x: xPdf, y: yPdf }); if (mode === "count") { commit(); draft = []; } else if (mode === "calibrate" && draft.length === 2) calibrate(); else if (mode === "rect" && draft.length === 2) commit(); drawOverlay(); },
    commit, measures, calibrated: () => calOk(), exportPdf, close: () => ov.remove(),
  };
}

function pickPdf(): Promise<File | null> {
  return new Promise((resolve) => {
    const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".pdf,application/pdf";
    inp.onchange = () => resolve(inp.files?.[0] ?? null);
    inp.click();
  });
}
