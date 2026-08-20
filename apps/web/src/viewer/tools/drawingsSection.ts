import type { ApiClient } from "../../api/client";
import { toast, withLoading } from "../../ui/feedback";
import { kvTable, resultNote, showResult } from "../../ui/result";
import type { CanvasModeSwitch } from "../canvasMode";
import {
  type ViewSpec, PAGE_CATALOG, isSheetPage, railSheetOptions, readSheetPage,
  sheetPath, viewsForCanvas, writeSheetPage,
} from "../sheetSpecs";

/**
 * R39-DECOMP-VIEWER ⑧ — the **Drawings & sheets** rail group, out of `app.ts`.
 *
 * The drawing set as the rail presents it: the plan (as a docked canvas or an SVG export), the
 * issuable A-101 sheet in SVG and PDF, "place this view on a sheet", the computed schedules and
 * their A-601 sheet, the MasterFormat project manual, and sections/elevations with their DXF
 * siblings. A paper-size picker plus nine buttons, returned in rail order so the caller's
 * `railGroup` call stays the ordering decision it already was.
 *
 * ## Why this slice, after the builders map was already out
 *
 * Slices ①–⑥ emptied the `builders` map and `app.ts` fell 5,160 → 3,444. What they did **not**
 * touch is the ~1,100 lines still sitting directly in `buildToolsPanel` above that map, and this is
 * the first coherent group lifted out of it.
 *
 * It is also the first slice where **the accessor rule actually bites.** `exportsSection.ts` says
 * plainly that it "touches neither" `selectedGuid` nor `lastPoint`, and that `ExportsDeps` is
 * shaped so the next one can. This is that one: `activeStorey` and `activeStoreyZ` are `let` in
 * `app.ts`, reassigned every time the level selector changes (`app.ts` — the level `<select>`
 * handler). Passing either by value would compile without complaint and freeze the level at
 * panel-build time, which is *before any level exists* — so every plan, every DXF and every sheet
 * would silently render the whole building instead of the level the user is looking at. Nothing in
 * the type system can see that, and `qaSection.ts` proves the docstring alone cannot either: it
 * collapsed an accessor on its first line under a comment explaining why that was impossible.
 * `accessorNotCollapsed.test.ts` is the gate; this module is written to pass it by construction.
 *
 * `modeSwitch` crosses as the **object**, not as `modeSwitch.active`. That is the same rule, not an
 * exception to it: the object holds its own live state, so reading `.active` inside a handler is a
 * read at click time. Copying `.active` out here would be the frozen-value bug wearing a different
 * name.
 */
export interface DrawingsDeps {
  /** A full-width tool button. Declared inside `buildToolsPanel`, handed over whole. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  /** `const` in `app.ts`, so a value is safe. */
  projectId: string | null;
  /** The same id, non-null-asserted by the caller inside its project gate. */
  pid: string;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** The canvas host `withLoading` overlays. `const` in `app.ts`. */
  container: HTMLElement;
  /** Live object — `.active` is read at click time, never copied out here. */
  modeSwitch: CanvasModeSwitch;
  /** **Accessors, not values.** Both are `let` in `app.ts` and change with the level selector. */
  activeStorey: () => string | null;
  activeStoreyZ: () => number;
}

function paperPicker(): HTMLSelectElement {
  const sel = document.createElement("select");
  sel.className = "portal-filter";
  sel.style.width = "100%";
  sel.title = "Sheet paper. 24×18 in is ARCH C, not an ISO A size. ARCH D is full-size US CDs "
    + "(36×24); ARCH B is half of D; ARCH A is the next step (often called quarter of D).";
  const current = readSheetPage();
  for (const { key, label } of PAGE_CATALOG) {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = label;
    if (key === current) opt.selected = true;
    sel.appendChild(opt);
  }
  sel.onchange = () => { if (isSheetPage(sel.value)) writeSheetPage(sel.value); };
  return sel;
}

/** Builds the Drawings & sheets controls, in the order the rail group expects them. */
export function buildDrawingsSection(d: DrawingsDeps): HTMLElement[] {
  // W11 C1: generate a schematic plan drawing (SVG) from the model, at the active level if one is set.
  // Routes through the mode switch rather than toggling the pane itself: two independent
  // controls over one element is how "both visible" and "neither visible" become reachable.
  const planPaneBtn = d.toolBtn2("◫ Plan as canvas", () => {
    const to = d.modeSwitch.active === "sheets" ? "model" : "sheets";
    const r = d.modeSwitch.switchTo(to);
    if (!r.ok) { d.notify(r.reason ?? "cannot open the plan", "error"); return; }
    planPaneBtn.classList.toggle("on", d.modeSwitch.active === "sheets");
  });
  planPaneBtn.title = "Make the generated plan the canvas (same as the Sheets tab). It re-cuts "
    + "when you change the active level, and selection syncs both ways — click linework in the "
    + "plan to select in 3D.";
  const planBtn = d.toolBtn2("🖨 Generate plan (SVG)", () => {
    const q = new URLSearchParams({ scale: "100" });
    // Read once, INSIDE the handler — at click time, which is the whole point of the accessor.
    // `if (d.activeStorey()) q.set(..., d.activeStorey())` does not typecheck: two calls, so TS
    // cannot narrow the second, where the `let` in `app.ts` narrowed for free. The compiler is
    // asking the right question here, because two calls could genuinely return different values.
    const storey = d.activeStorey();
    if (storey) q.set("storey", storey);
    window.open(d.api.url(`/projects/${d.projectId}/drawings/plan.svg?${q.toString()}`), "_blank");
  });
  planBtn.title = "Generate a schematic plan drawing (SVG, 1:100) from the model geometry — walls/columns/"
    + "slabs as class-styled poché with dimensions + keynotes. The active level scopes it.";

  // W11 C3: compose an issuable sheet (picker paper + titleblock) around the plan.
  const openSheet = (fmt: "svg" | "pdf", views?: ViewSpec[]) => window.open(
    d.api.url(sheetPath(d.projectId!, fmt, railSheetOptions(d.activeStorey(), views))), "_blank");
  const sheetBtn = d.toolBtn2("📄 Issue sheet (A-101)", () => openSheet("svg"));
  sheetBtn.title = "Compose an issuable construction sheet — selected paper + titleblock (project, sheet "
    + "number, scale, north arrow) with the plan placed in a scaled viewport. Default paper is ARCH C "
    + "(24×18 in).";
  const pdfBtn = d.toolBtn2("⤓ Sheet PDF (A-101)", () => openSheet("pdf"));
  const placeBtn = d.toolBtn2("🖼 Place this view on a sheet",
    () => openSheet("pdf", viewsForCanvas(d.modeSwitch.active === "sheets" ? "2d" : "3d", d.activeStoreyZ())));
  placeBtn.title = "Sheet PDF of the view you are looking at — the active level's plan in 2D, a true "
    + "isometric in 3D. Both are vector drawings that keep their GlobalIds, not screenshots. Paper "
    + "size is the picker value (default ARCH C, 24×18 in).";
  pdfBtn.title = "Download the sheet as a PDF (selected paper, titleblock, plan poché + dimensions + "
    + "keynotes) — the submittable construction-document deliverable, rendered server-side.";

  // W11 C4: computed door / window / room schedules from the model.
  const openSchedules = async () => {
    let sc;
    try { sc = await d.api.drawingSchedules(d.pid); }
    catch (e) { d.notify(`schedules failed: ${(e as Error).message}`, "error"); return; }
    showResult("Schedules (door / window / room)", (body) => {
      for (const [kind, label] of [["doors", "Door schedule"], ["windows", "Window schedule"], ["rooms", "Room schedule"]] as const) {
        const t = sc[kind];
        body.appendChild(resultNote(`<b>${label}</b> — ${t.rows.length} row(s)`, ""));
        if (!t.rows.length) continue;
        const tbl = document.createElement("table"); tbl.className = "kv-table"; tbl.style.marginBottom = "6px";
        const hr = document.createElement("tr");
        for (const c of t.columns) { const th = document.createElement("th"); th.textContent = c; hr.appendChild(th); }
        tbl.appendChild(hr);
        for (const row of t.rows.slice(0, 60)) {
          const tr = document.createElement("tr");
          for (const cell of row) { const td = document.createElement("td"); td.textContent = cell; tr.appendChild(td); }
          tbl.appendChild(tr);
        }
        body.appendChild(tbl);
      }
    });
  };
  const schedBtn = d.toolBtn2("📋 Schedules", openSchedules);
  schedBtn.title = "Computed door / window / room schedules (marks, sizes, types, levels, areas) — the "
    + "tabular half of the CD set, straight from the model. Also at GET /drawings/schedule.svg.";

  // W11 C6: the schedules laid out on an issuable ARCH-D sheet (PDF) — the submittable tabular sheet.
  const schedPdfBtn = d.toolBtn2("⤓ Schedules sheet (A-601 PDF)", () => {
    window.open(d.api.url(`/projects/${d.projectId}/drawings/schedule.pdf?number=A-601`), "_blank");
  });
  schedPdfBtn.title = "Lay the door / window / room schedules on an ARCH-D titleblock sheet and download "
    + "as a submittable PDF — the tabular half of the CD set as an issuable sheet.";

  // W11 D6: the 3-part MasterFormat project manual (the spec book), seeded from classifications.
  const manualBtn = d.toolBtn2("📖 Project manual (spec book)", () => withLoading(d.container, "Assembling the project manual", async () => {
    let man;
    try { man = await d.api.specManual(d.projectId!); }
    catch { toast("Needs a source IFC", "error"); return; }
    showResult("Project manual — 3-part MasterFormat spec book", (body) => {
      body.appendChild(resultNote(`<b>${man!.division_count}</b> division(s) · <b>${man!.section_count}</b> section(s), `
        + `seeded from MasterFormat classifications. ${man!.note}`, man!.section_count ? "ok" : ""));
      if (!man!.section_count) {
        body.appendChild(resultNote("No MasterFormat-classified elements yet — classify elements in the "
          + "🏷 Detailing tool (advanced) to seed the manual.", ""));
      }
      for (const div of man!.divisions) {
        const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:600;margin:8px 0 2px";
        h.textContent = `DIVISION ${div.division} — ${div.title}`;
        body.appendChild(h);
        for (const s of div.sections) {
          body.appendChild(kvTable([
            { k: `§ ${s.code}`, v: `${s.title} — ${s.element_count} element(s)`, strong: true },
            { k: "Part 2 — Products", v: s.part2_products.join(", ") },
            { k: "Part 3 — Execution", v: s.part3_execution.join("; ") },
          ]));
        }
      }
      const dl = d.toolBtn2("⤓ Download manual (.txt)", () => window.open(d.api.url(`/projects/${d.projectId}/spec/manual.txt`), "_blank"));
      body.appendChild(dl);
    });
  }));
  manualBtn.title = "Generate the 3-part MasterFormat project manual — elements grouped into CSI "
    + "divisions → sections (Part 1 General / Part 2 Products / Part 3 Execution), seeded from the "
    + "model's classifications + attached install docs. The spec book that accompanies the drawings.";

  // W11 C5: sections & elevations — cut linework straight from the baked model geometry. The
  // section auto-centres on the model (no offset needed); elevations project each cardinal face.
  const sectBtn = d.toolBtn2("📐 Sections & elevations", () => {
    showResult("Sections & elevations", (body) => {
      body.appendChild(resultNote("Generate a cut <b>section</b> (through the middle of the model) or a projected "
        + "<b>elevation</b> of each face — true linework from the model geometry, opens as SVG.", "ok"));
      const openDrawing = (path: string) => window.open(d.api.url(`/projects/${d.projectId}/drawings/${path}`), "_blank");
      const row = (label: string) => { const d = document.createElement("div"); d.className = "meta"; d.style.margin = "6px 0 2px"; d.textContent = label; body.appendChild(d); return d; };
      const btnRow = () => { const r = document.createElement("div"); r.style.cssText = "display:flex;flex-wrap:wrap;gap:6px"; body.appendChild(r); return r; };
      row("Sections (auto-centred cut)");
      const secR = btnRow();
      for (const [axis, lbl] of [["x", "Section X–X"], ["y", "Section Y–Y"]] as const) {
        const b2 = document.createElement("button"); b2.className = "mini-btn"; b2.textContent = `✂ ${lbl}`;
        b2.onclick = () => openDrawing(`section.svg?axis=${axis}&title=${encodeURIComponent(lbl)}`);
        const dx = document.createElement("button"); dx.className = "mini-btn"; dx.textContent = "⤓ DXF"; dx.title = `${lbl} → DXF (CAD)`;
        dx.onclick = () => openDrawing(`section.dxf?axis=${axis}`);
        secR.append(b2, dx);
      }
      row("Elevations");
      const elR = btnRow();
      for (const dir of ["north", "south", "east", "west"] as const) {
        const b2 = document.createElement("button"); b2.className = "mini-btn"; b2.textContent = `🧭 ${dir.charAt(0).toUpperCase()}${dir.slice(1)}`;
        b2.onclick = () => openDrawing(`elevation.svg?direction=${dir}`);
        const dx = document.createElement("button"); dx.className = "mini-btn"; dx.textContent = "⤓"; dx.title = `${dir} elevation → DXF (CAD)`;
        dx.onclick = () => openDrawing(`elevation.dxf?direction=${dir}`);
        elR.append(b2, dx);
      }
      row("Plan");
      const plR = btnRow();
      const planDxf = document.createElement("button"); planDxf.className = "mini-btn"; planDxf.textContent = "⤓ Plan DXF (CAD)";
      planDxf.title = "Export the plan cut linework as a DXF any CAD tool can open" + (d.activeStorey() ? ` (${d.activeStorey()})` : "");
      planDxf.onclick = () => { const q = new URLSearchParams(); if (d.activeStoreyZ()) q.set("elevation", String(d.activeStoreyZ())); openDrawing(`plan.dxf?${q.toString()}`); };
      plR.appendChild(planDxf);
    });
  });
  sectBtn.title = "Cut sections (auto-centred on the model) and projected N/S/E/W elevations — vector "
    + "linework from the model geometry, the other half of the drawing set alongside plans.";
  // Returned in rail order. Picker first so Issue/PDF/Place all read the same stored size.
  // `planPaneBtn` before `planBtn`: the docked pane is the daily surface, the SVG export the occasional one.
  return [paperPicker(), planPaneBtn, planBtn, sheetBtn, pdfBtn, placeBtn, schedBtn, schedPdfBtn, manualBtn, sectBtn];
}
