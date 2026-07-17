/** TAKEOFF-2D — quantity takeoff from an uploaded 2D drawing (PDF page image / scan).
 *
 *  A drawings-only takeoff: load a drawing image, calibrate the scale (click two points at a known real
 *  distance), then trace regions — either by clicking polygon vertices, or one-click **flood fill** inside
 *  an enclosed area (the OpenTakeoff technique). Each region is priced by assembly via the server
 *  (`POST /projects/{pid}/takeoff/2d`), feeding the same 5D estimate. Plain DOM + canvas, themed with the
 *  app's CSS variables; no dependencies.
 */

type Pt = [number, number];
type Region = { category: string; points: Pt[]; label?: string };
type QuantifyResult = {
  region_count: number; total_cost: number; unit: string;
  regions: { index: number; category: string; assembly: string; measure: string; quantity: number;
             unit: string; rate: number; cost: number }[];
  by_assembly: { category: string; assembly: string; unit: string; quantity: number; cost: number; count: number }[];
  assemblies: { category: string; measure: string; rate: number; label: string; unit: string | null }[];
};

interface Takeoff2dOpts {
  quantify: (regions: Region[], scaleUnitsPerPx: number, unit: string) => Promise<QuantifyResult>;
  notify: (message: string, kind?: "error" | "info" | "success") => void;
  assemblies?: { category: string; measure: string; rate: number; label: string; unit: string | null }[];
}

type Mode = "idle" | "calibrate" | "trace" | "fill";

const AREA_ASSEMBLIES = [
  { category: "floor_slab", label: "Floor slab" }, { category: "roofing", label: "Roofing" },
  { category: "ceiling", label: "Ceiling" }, { category: "partition", label: "Partition (area)" },
  { category: "exterior_wall", label: "Exterior wall (area)" }, { category: "curtain_wall", label: "Curtain wall" },
  { category: "paving", label: "Paving" }, { category: "generic_area", label: "Generic area" },
  { category: "wall_linear", label: "Wall (linear)" }, { category: "footing_linear", label: "Strip footing (linear)" },
  { category: "generic_linear", label: "Generic linear" },
];
const LINEAR = new Set(["wall_linear", "footing_linear", "generic_linear"]);

export function openTakeoff2d(opts: Takeoff2dOpts): void {
  const overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;inset:0;z-index:9998;background:rgba(0,0,0,.55);display:flex;"
    + "align-items:center;justify-content:center";
  const panel = document.createElement("div");
  panel.style.cssText = "background:var(--panel,#1b1e24);color:var(--text,#e8e8e8);border:1px solid var(--line,#333);"
    + "border-radius:10px;width:min(1100px,95vw);height:min(820px,94vh);display:flex;flex-direction:column;overflow:hidden";
  overlay.appendChild(panel);

  // ---- header ----
  const head = document.createElement("div");
  head.style.cssText = "display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--line,#333);flex-wrap:wrap";
  head.innerHTML = '<b style="font-size:14px">📐 2D Takeoff</b>'
    + '<span class="meta" style="font-size:11px;opacity:.7">upload a drawing · calibrate · trace/flood-fill regions · quantify</span>';
  const spacer = document.createElement("div"); spacer.style.flex = "1";
  head.appendChild(spacer);
  const close = btn("✕ Close"); close.onclick = () => overlay.remove(); head.appendChild(close);
  panel.appendChild(head);

  // ---- toolbar ----
  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;align-items:center;gap:6px;padding:8px 12px;border-bottom:1px solid var(--line,#333);flex-wrap:wrap";
  const fileIn = document.createElement("input"); fileIn.type = "file"; fileIn.accept = "image/*"; fileIn.style.fontSize = "11px";
  const calBtn = btn("① Calibrate scale");
  const catSel = document.createElement("select"); catSel.style.cssText = "font-size:12px;padding:2px";
  for (const a of AREA_ASSEMBLIES) {
    const o = document.createElement("option"); o.value = a.category; o.textContent = a.label;
    catSel.appendChild(o);
  }
  const traceBtn = btn("② Trace polygon"); const fillBtn = btn("② Flood-fill area");
  const undoBtn = btn("Undo region"); const clearBtn = btn("Clear"); const goBtn = btn("③ Quantify →");
  goBtn.style.fontWeight = "700";
  const status = document.createElement("span"); status.className = "meta"; status.style.cssText = "font-size:11px;margin-left:6px";
  bar.append(fileIn, calBtn, catSel, traceBtn, fillBtn, undoBtn, clearBtn, goBtn, status);
  panel.appendChild(bar);

  // ---- body: canvas + results ----
  const body = document.createElement("div"); body.style.cssText = "flex:1;display:flex;min-height:0";
  const cwrap = document.createElement("div"); cwrap.style.cssText = "flex:1;overflow:auto;background:#0e0f12;position:relative";
  const canvas = document.createElement("canvas"); canvas.style.cssText = "display:block;cursor:crosshair";
  cwrap.appendChild(canvas);
  const results = document.createElement("div");
  results.style.cssText = "width:330px;border-left:1px solid var(--line,#333);overflow:auto;padding:10px;font-size:12px";
  results.innerHTML = '<div class="meta">Quantify to see quantities + cost.</div>';
  body.append(cwrap, results); panel.appendChild(body);

  // ---- state ----
  const ctx = canvas.getContext("2d")!;
  let img: HTMLImageElement | null = null;
  let scale = 0;                         // real units per pixel
  const unit = "m";
  let mode: Mode = "idle";
  const regions: Region[] = [];
  let draft: Pt[] = [];                  // in-progress polygon (trace) or calibration points
  let calPts: Pt[] = [];

  const setStatus = (t: string) => { status.textContent = t; };
  const setMode = (m: Mode) => {
    mode = m; draft = []; calPts = [];
    for (const [b, mm] of [[calBtn, "calibrate"], [traceBtn, "trace"], [fillBtn, "fill"]] as [HTMLElement, Mode][]) {
      b.style.outline = mode === mm ? "2px solid var(--accent,#4c8bf5)" : "none";
    }
    setStatus(m === "calibrate" ? "click two points a known distance apart"
      : m === "trace" ? "click vertices; double-click / Enter to close"
      : m === "fill" ? "click inside an enclosed area to flood-fill"
      : scale ? `scale ${scale.toFixed(4)} ${unit}/px` : "load a drawing, then calibrate");
  };

  function draw() {
    if (!img) return;
    canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
    ctx.drawImage(img, 0, 0);
    for (const r of regions) drawPoly(ctx, r.points, !LINEAR.has(r.category), "#4c8bf5", "rgba(76,139,245,.18)");
    if (draft.length) drawPoly(ctx, draft, false, "#f5a24c", "transparent", true);
    if (calPts.length) {
      ctx.fillStyle = "#5cd67a";
      for (const p of calPts) { ctx.beginPath(); ctx.arc(p[0], p[1], 4, 0, 7); ctx.fill(); }
      if (calPts.length === 2) { ctx.strokeStyle = "#5cd67a"; ctx.beginPath(); ctx.moveTo(calPts[0]![0], calPts[0]![1]); ctx.lineTo(calPts[1]![0], calPts[1]![1]); ctx.stroke(); }
    }
  }

  fileIn.onchange = () => {
    const f = fileIn.files?.[0]; if (!f) return;
    const im = new Image();
    im.onload = () => { img = im; draw(); setMode("idle"); };
    im.onerror = () => opts.notify("could not load that image", "error");
    im.src = URL.createObjectURL(f);
  };
  calBtn.onclick = () => { if (!img) return opts.notify("load a drawing first", "error"); setMode("calibrate"); };
  traceBtn.onclick = () => { if (!ensureReady()) return; setMode("trace"); };
  fillBtn.onclick = () => { if (!ensureReady()) return; setMode("fill"); };
  undoBtn.onclick = () => { regions.pop(); draw(); };
  clearBtn.onclick = () => { regions.length = 0; draft = []; draw(); setStatus("cleared"); };

  function ensureReady(): boolean {
    if (!img) { opts.notify("load a drawing first", "error"); return false; }
    if (!scale) { opts.notify("calibrate the scale first", "error"); return false; }
    return true;
  }

  const toImg = (ev: MouseEvent): Pt => {
    const r = canvas.getBoundingClientRect();
    return [Math.round((ev.clientX - r.left) * (canvas.width / r.width)),
            Math.round((ev.clientY - r.top) * (canvas.height / r.height))];
  };

  canvas.onclick = (ev) => {
    if (!img) return;
    const p = toImg(ev);
    if (mode === "calibrate") {
      calPts.push(p);
      if (calPts.length === 2) {
        const c0 = calPts[0]!, c1 = calPts[1]!;
        const dpx = Math.hypot(c1[0] - c0[0], c1[1] - c0[1]);
        const real = parseFloat(prompt(`Real distance between the two points, in ${unit}:`, "5") || "0");
        if (dpx > 0 && real > 0) { scale = real / dpx; opts.notify(`scale set: ${scale.toFixed(4)} ${unit}/px`, "success"); }
        setMode("idle");
      }
      draw();
    } else if (mode === "trace") {
      draft.push(p); draw();
    } else if (mode === "fill") {
      const poly = floodFillPolygon(ctx, canvas.width, canvas.height, p[0], p[1]);
      if (poly.length >= 3) { regions.push({ category: catSel.value, points: poly }); draw(); setStatus(`region added (${regions.length})`); }
      else opts.notify("no enclosed area found there", "error");
    }
  };
  canvas.ondblclick = () => { if (mode === "trace" && draft.length >= 3) { regions.push({ category: catSel.value, points: draft.slice() }); draft = []; draw(); setStatus(`region added (${regions.length})`); } };
  window.addEventListener("keydown", onKey);
  function onKey(e: KeyboardEvent) {
    if (!overlay.isConnected) { window.removeEventListener("keydown", onKey); return; }
    if (e.key === "Enter" && mode === "trace" && draft.length >= 3) { regions.push({ category: catSel.value, points: draft.slice() }); draft = []; draw(); }
    if (e.key === "Escape") { if (draft.length) { draft = []; draw(); } else overlay.remove(); }
  }

  goBtn.onclick = async () => {
    if (!ensureReady()) return;
    if (!regions.length) return opts.notify("trace at least one region", "error");
    setStatus("quantifying…");
    try {
      const res = await opts.quantify(regions, scale, unit);
      renderResults(results, res);
      setStatus(`${res.region_count} region(s) · $${Math.round(res.total_cost).toLocaleString()}`);
    } catch (e) { opts.notify((e as Error).message, "error"); setStatus("quantify failed"); }
  };

  setMode("idle");
  document.body.appendChild(overlay);
}

// ---- helpers ----
function btn(label: string): HTMLButtonElement {
  const b = document.createElement("button"); b.textContent = label;
  b.style.cssText = "font-size:12px;padding:4px 8px;background:var(--panel2,#262a31);color:inherit;"
    + "border:1px solid var(--line,#333);border-radius:5px;cursor:pointer";
  return b;
}

function drawPoly(ctx: CanvasRenderingContext2D, pts: Pt[], closed: boolean, stroke: string, fill: string, dashed = false) {
  if (pts.length < 1) return;
  ctx.save(); ctx.lineWidth = 2; ctx.strokeStyle = stroke; ctx.fillStyle = fill;
  if (dashed) ctx.setLineDash([6, 4]);
  ctx.beginPath(); ctx.moveTo(pts[0]![0], pts[0]![1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i]![0], pts[i]![1]);
  if (closed) { ctx.closePath(); if (fill !== "transparent") ctx.fill(); }
  ctx.stroke();
  ctx.setLineDash([]); ctx.fillStyle = stroke;
  for (const p of pts) { ctx.beginPath(); ctx.arc(p[0], p[1], 3, 0, 7); ctx.fill(); }
  ctx.restore();
}

/** Flood-fill from a seed over the canvas raster (colour within tolerance), then trace the filled region's
 *  bounding contour into a simplified polygon. A pragmatic "one-click area" — good for clean line drawings. */
function floodFillPolygon(ctx: CanvasRenderingContext2D, w: number, h: number, sx: number, sy: number, tol = 32): Pt[] {
  const data = ctx.getImageData(0, 0, w, h).data;
  const at = (x: number, y: number) => (y * w + x) * 4;
  const s = at(sx, sy);
  const sr = data[s] ?? 0, sg = data[s + 1] ?? 0, sb = data[s + 2] ?? 0;
  const mask = new Uint8Array(w * h);
  const stack: number[] = [sx, sy];
  let minX = sx, maxX = sx, minY = sy, maxY = sy;
  const near = (i: number) => Math.abs((data[i] ?? 0) - sr) + Math.abs((data[i + 1] ?? 0) - sg)
    + Math.abs((data[i + 2] ?? 0) - sb) <= tol;
  let guard = 0;
  const cap = w * h;
  while (stack.length && guard++ < cap) {
    const y = stack.pop()!, x = stack.pop()!;
    if (x < 0 || y < 0 || x >= w || y >= h) continue;
    const mi = y * w + x;
    if (mask[mi]) continue;
    if (!near(at(x, y))) continue;
    mask[mi] = 1;
    if (x < minX) minX = x; if (x > maxX) maxX = x; if (y < minY) minY = y; if (y > maxY) maxY = y;
    stack.push(x + 1, y, x - 1, y, x, y + 1, x, y - 1);
  }
  // approximate the filled area as its bounding rectangle refined by per-row extents → a coarse outline.
  // (A full contour trace is overkill for a preliminary takeoff; the row-extent hull captures the shape.)
  const left: Pt[] = [], right: Pt[] = [];
  for (let y = minY; y <= maxY; y++) {
    let lo = -1, hi = -1;
    for (let x = minX; x <= maxX; x++) { if (mask[y * w + x]) { if (lo < 0) lo = x; hi = x; } }
    if (lo >= 0) { left.push([lo, y]); right.push([hi, y]); }
  }
  if (left.length < 2) return [];
  const ring = left.concat(right.reverse());
  return simplify(ring, 2.0);
}

/** Douglas–Peucker polyline simplification (keeps the shape, drops near-collinear points). */
function simplify(pts: Pt[], eps: number): Pt[] {
  if (pts.length < 3) return pts;
  let maxD = 0, idx = 0;
  const a = pts[0]!, b = pts[pts.length - 1]!;
  for (let i = 1; i < pts.length - 1; i++) { const d = segDist(pts[i]!, a, b); if (d > maxD) { maxD = d; idx = i; } }
  if (maxD > eps) {
    const l = simplify(pts.slice(0, idx + 1), eps), r = simplify(pts.slice(idx), eps);
    return l.slice(0, -1).concat(r);
  }
  return [a, b];
}
function segDist(p: Pt, a: Pt, b: Pt): number {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  return Math.abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / len;
}

function renderResults(host: HTMLElement, res: QuantifyResult) {
  const rows = res.by_assembly.map((a) =>
    `<tr><td>${a.assembly}</td><td style="text-align:right">${a.quantity.toLocaleString()} ${a.unit}</td>`
    + `<td style="text-align:right">$${Math.round(a.cost).toLocaleString()}</td></tr>`).join("");
  host.innerHTML = `<div style="font-weight:700;margin-bottom:6px">Takeoff — $${Math.round(res.total_cost).toLocaleString()}</div>`
    + `<table style="width:100%;border-collapse:collapse;font-size:12px">`
    + `<tr style="opacity:.7"><th style="text-align:left">Assembly</th><th style="text-align:right">Qty</th><th style="text-align:right">Cost</th></tr>`
    + rows + `</table>`
    + `<div class="meta" style="margin-top:8px;font-size:10px;opacity:.65">Preliminary — trace/scale dependent; verify against the model takeoff where a model exists.</div>`;
}
