import type { ApiClient } from "../api/client";

/** SHEET-VIEWPORTS — the interactive paper-space editor over the v0.3.449 layout endpoints.
 *
 *  A sheet is a set of viewport rectangles; each has a view (plan storey / section / elevation), an
 *  optional fixed 1:N scale (true paper scale, server-clipped), and an optional class freeze. This
 *  editor is the client half: preset picker → per-viewport controls → live SVG preview with
 *  **drag-to-move viewport overlays** (drag a rectangle on the preview; its fraction rect updates and
 *  the sheet re-composes) → submittable PDF. All composition stays server-side and deterministic. */

type Vp = {
  kind: "plan" | "section" | "elevation";
  rect: [number, number, number, number];
  elevation?: number; axis?: "x" | "y"; offset?: number; direction?: string;
  scale?: number | null; classes?: string[]; title?: string;
};

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const r2 = (v: number) => Math.round(v * 100) / 100;

export function openLayoutEditor(api: ApiClient, pid: string, mount: HTMLElement): void {
  mount.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.style.cssText = "display:flex;gap:12px;height:100%;min-height:0;padding:8px";
  const ctrl = document.createElement("div");
  ctrl.style.cssText = "width:330px;flex:none;overflow:auto;display:flex;flex-direction:column;gap:8px;font-size:12px";
  const previewWrap = document.createElement("div");
  previewWrap.style.cssText = "flex:1;min-width:0;overflow:auto;position:relative;background:var(--hover,#1b1e27);border-radius:8px;padding:8px";
  const preview = document.createElement("div");
  preview.style.cssText = "position:relative;display:inline-block";   // overlay anchors to the SVG box
  previewWrap.appendChild(preview);
  wrap.append(ctrl, previewWrap);
  mount.appendChild(wrap);

  let viewports: Vp[] = [];
  let presets: Record<string, Vp[]> = {};
  let previewTimer = 0;

  // --- controls -----------------------------------------------------------------------------------
  const row = (label: string, el: HTMLElement) => {
    const d = document.createElement("label");
    d.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px";
    d.append(Object.assign(document.createElement("span"), { textContent: label }), el);
    return d;
  };
  const mkSel = (opts: string[], val?: string) => {
    const s = document.createElement("select"); s.className = "portal-filter";
    s.innerHTML = opts.map((o) => `<option${o === val ? " selected" : ""}>${o}</option>`).join("");
    return s;
  };
  const mkNum = (val: number | "" = "", step = 0.05, w = 62) => {
    const i = document.createElement("input"); i.type = "number"; i.step = String(step);
    i.className = "portal-filter"; i.style.width = `${w}px`; i.value = val === "" ? "" : String(val);
    return i;
  };

  const head = document.createElement("div");
  head.innerHTML = `<b>⊞ Paper space</b> <span class="meta">— viewports compose server-side; drag a
    rectangle on the preview to move it</span>`;
  const presetSel = mkSel(["key", "quad", "plan-pair"]);
  const pageSel = mkSel(["A1", "A3", "A4"], "A1");
  const numberIn = Object.assign(document.createElement("input"), { value: "A-100" });
  numberIn.className = "portal-filter"; numberIn.style.width = "80px";
  const titleIn = Object.assign(document.createElement("input"), { value: "LAYOUT" });
  titleIn.className = "portal-filter"; titleIn.style.width = "150px";
  const vpList = document.createElement("div");
  vpList.style.cssText = "display:flex;flex-direction:column;gap:6px";
  const addBtn = document.createElement("button");
  addBtn.className = "file-btn"; addBtn.textContent = "＋ viewport";
  const pdfBtn = document.createElement("button");
  pdfBtn.className = "file-btn"; pdfBtn.textContent = "⬇ PDF";
  const status = document.createElement("div"); status.className = "meta";
  ctrl.append(head, row("Preset", presetSel), row("Page", pageSel), row("Sheet №", numberIn),
              row("Title", titleIn), vpList, addBtn, pdfBtn, status);

  function vpRow(vp: Vp, idx: number): HTMLElement {
    const box = document.createElement("div");
    box.style.cssText = "border:1px solid var(--line,#2c3140);border-radius:6px;padding:6px;display:flex;flex-direction:column;gap:4px";
    const kind = mkSel(["plan", "section", "elevation"], vp.kind);
    const param = document.createElement("span");
    const renderParam = () => {
      param.innerHTML = "";
      if (kind.value === "plan") {
        const e = mkNum(vp.elevation ?? 0, 0.5); e.title = "storey elevation (m)";
        e.oninput = () => { vp.elevation = Number(e.value) || 0; schedule(); };
        param.append("elev ", e);
      } else if (kind.value === "section") {
        const ax = mkSel(["x", "y"], vp.axis ?? "x"); const off = mkNum(vp.offset ?? 0, 0.5);
        ax.onchange = () => { vp.axis = ax.value as "x" | "y"; schedule(); };
        off.oninput = () => { vp.offset = Number(off.value) || 0; schedule(); };
        param.append(ax, " @ ", off);
      } else {
        const d = mkSel(["north", "south", "east", "west"], vp.direction ?? "north");
        d.onchange = () => { vp.direction = d.value; schedule(); };
        param.append(d);
      }
    };
    kind.onchange = () => { vp.kind = kind.value as Vp["kind"]; renderParam(); schedule(); };
    renderParam();
    const scale = mkNum(vp.scale ?? "", 25, 70); scale.placeholder = "fit";
    scale.title = "fixed drawing scale 1:N (blank = fit-to-rect)";
    scale.oninput = () => { vp.scale = scale.value ? Number(scale.value) : null; schedule(); };
    const cls = Object.assign(document.createElement("input"), { value: (vp.classes || []).join(",") });
    cls.className = "portal-filter"; cls.placeholder = "class freeze (IfcWall,…)"; cls.style.width = "150px";
    cls.oninput = () => { vp.classes = cls.value.split(",").map((c) => c.trim()).filter(Boolean); schedule(); };
    const rect = document.createElement("span"); rect.className = "meta";
    rect.textContent = `rect ${vp.rect.map(r2).join(", ")}`;
    (box as HTMLElement & { _syncRect?: () => void })._syncRect = () => { rect.textContent = `rect ${vp.rect.map(r2).join(", ")}`; };
    const del = document.createElement("button"); del.className = "file-btn"; del.textContent = "✕";
    del.style.cssText = "padding:0 6px"; del.title = "remove viewport";
    del.onclick = () => { viewports.splice(idx, 1); renderVps(); schedule(); };
    const l1 = document.createElement("div"); l1.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
    l1.append(kind, param, "1:", scale, del);
    const l2 = document.createElement("div"); l2.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
    l2.append(cls, rect);
    box.append(l1, l2);
    return box;
  }
  function renderVps() {
    vpList.innerHTML = "";
    viewports.forEach((vp, i) => vpList.appendChild(vpRow(vp, i)));
  }

  // --- preview + drag overlays --------------------------------------------------------------------
  async function refresh() {
    status.textContent = "composing…";
    try {
      const res = await fetch(api.url(`/projects/${pid}/drawings/layout.svg`), {
        method: "POST", headers: { "Content-Type": "application/json", ...api.authHeaders() },
        body: JSON.stringify({ viewports, page: pageSel.value,
                               meta: { number: numberIn.value, title: titleIn.value } }),
      });
      if (!res.ok) { status.textContent = `compose failed: ${res.status}`; return; }
      preview.innerHTML = await res.text();
      const svg = preview.querySelector("svg");
      if (svg) { svg.style.maxWidth = "100%"; svg.style.height = "auto"; svg.style.display = "block"; }
      drawOverlays();
      status.textContent = `composed ${viewports.length} viewport(s)`;
    } catch (e) { status.textContent = `failed: ${(e as Error).message}`; }
  }
  function schedule() {
    window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(() => void refresh(), 500);
    [...vpList.children].forEach((c) => (c as HTMLElement & { _syncRect?: () => void })._syncRect?.());
  }

  function drawOverlays() {
    preview.querySelectorAll(".vp-ovl").forEach((n) => n.remove());
    const svg = preview.querySelector("svg");
    if (!svg) return;
    const box = svg.getBoundingClientRect();
    // the drawable area mirrors the server: margin 36pt all round + a 90pt titleblock band on top,
    // scaled from page points to rendered pixels via the SVG viewBox
    const vb = (svg.getAttribute("viewBox") || "0 0 2384 1684").split(/\s+/).map(Number);
    const sx = box.width / vb[2]!, sy = box.height / vb[3]!;
    const ax = 36 * sx, ay = (36 + 90) * sy, aw = (vb[2]! - 72) * sx, ah = (vb[3]! - 72 - 90) * sy;
    viewports.forEach((vp, i) => {
      const o = document.createElement("div");
      o.className = "vp-ovl";
      const [fx, fy, fw, fh] = vp.rect;
      o.style.cssText = `position:absolute;border:1.5px dashed var(--accent,#4a8cff);border-radius:3px;`
        + `left:${ax + fx * aw}px;top:${ay + fy * ah}px;width:${fw * aw}px;height:${fh * ah}px;`
        + "cursor:move;background:rgba(74,140,255,.06)";
      o.title = `viewport ${i + 1} — drag to move`;
      let drag: { px: number; py: number; ox: number; oy: number } | null = null;
      o.addEventListener("pointerdown", (e) => {
        drag = { px: e.clientX, py: e.clientY, ox: vp.rect[0], oy: vp.rect[1] };
        o.setPointerCapture(e.pointerId); e.preventDefault();
      });
      o.addEventListener("pointermove", (e) => {
        if (!drag) return;
        vp.rect[0] = r2(clamp01(drag.ox + (e.clientX - drag.px) / aw));
        vp.rect[1] = r2(clamp01(drag.oy + (e.clientY - drag.py) / ah));
        o.style.left = `${ax + vp.rect[0] * aw}px`; o.style.top = `${ay + vp.rect[1] * ah}px`;
      });
      o.addEventListener("pointerup", () => { drag = null; schedule(); });
      preview.appendChild(o);
    });
  }

  // --- actions ------------------------------------------------------------------------------------
  presetSel.onchange = () => {
    viewports = JSON.parse(JSON.stringify(presets[presetSel.value] || []));
    renderVps(); void refresh();
  };
  pageSel.onchange = () => schedule();
  numberIn.oninput = titleIn.oninput = () => schedule();
  addBtn.onclick = () => {
    viewports.push({ kind: "plan", elevation: 0, rect: [0.05, 0.05, 0.4, 0.4] });
    renderVps(); schedule();
  };
  pdfBtn.onclick = async () => {
    status.textContent = "rendering PDF…";
    try {
      const res = await fetch(api.url(`/projects/${pid}/drawings/layout.pdf`), {
        method: "POST", headers: { "Content-Type": "application/json", ...api.authHeaders() },
        body: JSON.stringify({ viewports, page: pageSel.value,
                               meta: { number: numberIn.value, title: titleIn.value } }),
      });
      if (!res.ok) { status.textContent = `PDF failed: ${res.status}`; return; }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob());
      a.download = `${numberIn.value || "layout"}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1500);
      status.textContent = "PDF downloaded";
    } catch (e) { status.textContent = `failed: ${(e as Error).message}`; }
  };

  // --- boot: presets from the server, start on "key" ----------------------------------------------
  void (async () => {
    try {
      const res = await fetch(api.url(`/projects/${pid}/drawings/layout/presets`), { headers: api.authHeaders() });
      presets = res.ok ? await res.json() : {};
    } catch { presets = {}; }
    viewports = JSON.parse(JSON.stringify(presets.key || [{ kind: "plan", elevation: 0, rect: [0, 0, 1, 1] }]));
    renderVps(); void refresh();
  })();
}
