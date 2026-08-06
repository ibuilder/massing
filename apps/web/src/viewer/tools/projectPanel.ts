import type { ApiClient, DisciplineTree, ElementProps } from "../../api/client";
import { buildTree, setDisciplineLookup } from "../../tree/tree";
import { type SelSet, loadSelSets, resolveGuids, saveSelSets } from "../../tools/selectionSetsStore";
import { LayerManager } from "../../tools/layers";
import { askText } from "../../ui/prompt";
import type { ModelIdMap } from "../modelIds";
import type { SpatialElement } from "../spatialSelect";

/** Same one-liner `app.ts` uses; a module-level helper there, kept local here. */
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

/**
 * R39-DECOMP-VIEWER ⑤ — the project-browser / layers panel, out of `app.ts`.
 *
 * 216 contiguous lines: `buildPanels` and `buildSelSets`, which is called from exactly one place
 * inside it. `app.ts` 3,953 → 3,741.
 *
 * ## Scope: three neighbouring blocks were deliberately NOT taken
 *
 * `railGroup`, `distributeToolGroups` and `clearDistributed` are `buildToolsPanel`'s own helpers —
 * every one of their call sites is inside it. Extracting a helper without its caller means exporting
 * something `app.ts` immediately re-imports to hand back to the function that stayed: churn with a
 * line-count reduction attached, which the ratchet would record as progress. `refreshFederation` is
 * worse — 8 call sites across the file, one already threaded into `qaSection`.
 *
 * ## The discipline state is a REF, and it costs more here than last time
 *
 * `discTree` and `colorMode` are `let` in `app.ts`, **written inside this code and read outside it**
 * (`discTree ??=`, and the `<select>` handler), so per the ref rule ownership stays where it is and a
 * mutable ref crosses. The ref is a get/set adapter over the original `let`s, so **not one read site
 * in `app.ts` changes** — `disciplineOfClass` and the colour lookup keep reading the variables.
 *
 * The cost is visible and stated: **10 lines of the moved body reference them**, against 2 in the
 * `analyse` slice. Those 10 are the *only* non-identical lines, proven by diff rather than claimed.
 * Byte-identity is evidence, not the goal — the rule is what keeps a stale closure impossible, and a
 * `??=` cannot be expressed by a getter at any line count.
 *
 * `tsc` is the parity gate for the threading. The suite is **not** claimed as one for `app.ts`;
 * `toolsSplit.test.ts` does not cover this block (it reads tool-section sources, not panels).
 */

export interface ProjectPanelDeps {
  api: ApiClient;
  projectId: string | null;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  setStatus: (msg: string) => void;
  selectByGuid: (guid: string, fit?: boolean) => Promise<void | boolean>;
  reloadModelPins: () => Promise<void | boolean>;
  colorFor: (cls: string) => string;
  /** Stays in `app.ts`: also called from the colour lookup outside this block. */
  disciplineOfClass: (cls: string) => string | null;
  /**
   * REF. `spatialElements` is a `let` in `app.ts` that this code REBUILDS from the fetched element
   * list (`spatialElements = elements.map(...)`) and that A29-SPATIAL-SELECT reads on every pick.
   * A third read-write capture in one 216-line block — which is the point of the reword: in a
   * closure this size, state a builder OWNS is written by it, and only state it consults is not.
   */
  spatialElements: { value: SpatialElement[] };
  layerMgr: LayerManager;
  fitToItems: (map: ModelIdMap) => Promise<void>;
  refreshIssues: () => Promise<void | boolean>;
  /**
   * REF, not accessor. Both fields are written by this code and read by `app.ts` afterwards, and a
   * getter cannot express `??=`. Ownership stays with the original `let`s; this is a get/set view of
   * them, so `app.ts`'s own reads are untouched.
   */
  discipline: { tree: DisciplineTree | null; mode: "class" | "discipline" };
}

export async function buildProjectPanels(d: ProjectPanelDeps): Promise<void> {
  const { api, projectId, setStatus, selectByGuid, reloadModelPins,
          colorFor, disciplineOfClass, discipline, spatialElements, layerMgr,
          fitToItems, refreshIssues } = d;
    if (!projectId) return;
    // A project with no model 404s here. Fetching BEFORE rendering meant the throw escaped to a
    // console.warn at the call site and left the Project Browser — the rail's default panel —
    // completely blank, with the AUTHOR tools sitting one unmarked click away. An empty panel reads
    // as a broken app, not as an empty project, so the empty state is rendered first and the
    // elements are layered on only if they arrive.
    let elements: ElementProps[] = [];
    let noModel = false;
    try {
      elements = await api.elements(projectId, { limit: 5000 });
      // A29-SPATIAL-SELECT reads containment from this same list — one fetch, one truth.
      spatialElements.value = elements.map((e) => ({ guid: e.guid, storey: e.storey }));
    } catch {
      noModel = true;
    }
    const treePanel = $("panel-tree");
    treePanel.innerHTML = "";
    // UX-4 Project-Browser spine: a Views · Sheets · Schedules nav strip above the spatial/element tree,
    // so the model browser is a full project index (à la Revit's Project Browser), not just elements.
    const spine = document.createElement("div");
    spine.className = "browser-spine";
    spine.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;padding:4px 6px 6px;border-bottom:1px solid var(--border,#334155);margin-bottom:4px";
    const spineTitle = document.createElement("div");
    spineTitle.className = "section-title"; spineTitle.textContent = "Project browser"; spineTitle.style.width = "100%";
    spine.appendChild(spineTitle);
    const goWs = (key: string) => window.dispatchEvent(new CustomEvent("aec:workspace", { detail: key }));
    for (const [label, ws, title] of [
      ["📐 Plans & views", "drawings", "Open the Drawings workspace — plans, sections, elevations"],
      ["📄 Sheets", "drawings", "Composed sheets (titleblock + viewports) in the Drawings workspace"],
      ["📋 Schedules", "drawings", "Door / window / room schedules in the Drawings workspace"],
    ] as const) {
      const btn = document.createElement("button"); btn.className = "mini-btn"; btn.textContent = label;
      btn.style.cssText = "font-size:10.5px;padding:2px 7px"; btn.title = title;
      btn.onclick = () => goWs(ws);
      spine.appendChild(btn);
    }
    const treeHead = document.createElement("div");
    treeHead.className = "section-title"; treeHead.textContent = "Model";
    treeHead.style.cssText = "padding:0 6px";
    treePanel.append(spine, treeHead);
    if (noModel || !elements.length) {
      // Name the state and give it the two things that resolve it. Without this the panel is blank
      // and a reader cannot tell an empty project from a failed load.
      const empty = document.createElement("div");
      empty.className = "browser-empty";
      empty.style.cssText = "padding:10px 8px;font-size:11.5px;line-height:1.55;color:var(--muted,#94a3b8)";
      const msg = document.createElement("div");
      msg.textContent = noModel
        ? "No model in this project yet."
        : "This model published with no elements.";
      const hint = document.createElement("div");
      hint.style.cssText = "margin-top:6px";
      hint.textContent = "Open an IFC to browse it here — or start authoring from the AUTHOR group in the rail.";
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;margin-top:9px;flex-wrap:wrap";
      const openBtn = document.createElement("button");
      openBtn.className = "mini-btn"; openBtn.textContent = "📂 Open IFC";
      openBtn.title = "Load an IFC into this project";
      openBtn.onclick = () => ($("ifc-input") as HTMLInputElement | null)?.click();
      const authorBtn = document.createElement("button");
      authorBtn.className = "mini-btn"; authorBtn.textContent = "✎ Authoring tools";
      authorBtn.title = "Jump to the AUTHOR tools — create levels, grids, walls without a model";
      authorBtn.onclick = () => document.querySelector<HTMLElement>('[data-panel="tools"]')?.click();
      row.append(openBtn, authorBtn);
      empty.append(msg, hint, row);
      treePanel.appendChild(empty);
    } else {
      treePanel.appendChild(buildTree(elements, (guid) => selectByGuid(guid, false)));
    }
    if (noModel) return;   // meta/discipline calls below all need a published model

    const meta = await api.meta(projectId);
    discipline.tree ??= await api.disciplineTree().catch(() => null);
    // hand the served IFC-class→discipline map to the model browser so it stops re-deriving disciplines
    // from its own regex (one shared vocabulary).
    if (discipline.tree) setDisciplineLookup(discipline.tree.ifc_class_discipline,
      Object.fromEntries(discipline.tree.disciplines.map((d) => [d.code, d.name])));
    const layersPanel = $("panel-layers");
    layersPanel.innerHTML = `<div class="section-title">IFC classes</div>`;

    // Color-by toggle (Class ↔ Discipline) + a one-click "paint the model" so a coordinator can flip the
    // whole model to discipline colors (fire=red, plumbing=green, …) the way Navisworks/Revit do.
    const swatchRows: { cls: string; swatch: HTMLElement; ensure: () => Promise<string> }[] = [];
    const paintAll = async () => {
      for (const r of swatchRows) { r.swatch.style.background = colorFor(r.cls); await layerMgr.setColor(await r.ensure(), colorFor(r.cls)); }
    };
    if (discipline.tree) {
      const bar = document.createElement("div"); bar.className = "layer-row"; bar.style.cssText = "gap:6px;margin-bottom:4px";
      const lbl = document.createElement("span"); lbl.className = "name"; lbl.textContent = "Color by"; lbl.style.flex = "0 0 auto";
      const sel = document.createElement("select"); sel.className = "mini-select";
      sel.innerHTML = `<option value="class">IFC class</option><option value="discipline">Discipline</option>`;
      sel.value = discipline.mode;
      const paint = document.createElement("button"); paint.className = "mini-btn"; paint.textContent = "Paint model";
      paint.title = "Apply the current color scheme to every element in the 3D view";
      paint.onclick = paintAll;
      sel.onchange = () => {
        discipline.mode = sel.value === "discipline" ? "discipline" : "class";
        for (const r of swatchRows) r.swatch.style.background = colorFor(r.cls);
        legend.style.display = discipline.mode === "discipline" ? "" : "none";
        buildLegend();
      };
      bar.append(lbl, sel, paint);
      layersPanel.appendChild(bar);
    }
    // discipline color legend (shown in discipline mode) — the palette, so the colors read as a system.
    const legend = document.createElement("div"); legend.className = "disc-legend";
    legend.style.display = discipline.mode === "discipline" ? "" : "none";
    const buildLegend = () => {
      legend.innerHTML = "";
      if (discipline.mode !== "discipline" || !discipline.tree) return;
      const present = new Set(meta.facets.classes.map((c) => disciplineOfClass(c)).filter(Boolean));
      for (const d of discipline.tree.disciplines) {
        if (!present.has(d.code)) continue;
        const chip = document.createElement("span"); chip.className = "disc-chip";
        const sw = document.createElement("span"); sw.className = "swatch"; sw.style.background = d.color;
        const nm = document.createElement("span"); nm.textContent = d.name;
        chip.append(sw, nm); legend.appendChild(chip);
      }
    };
    buildLegend();
    layersPanel.appendChild(legend);

    for (const cls of meta.facets.classes) {
      const row = document.createElement("div"); row.className = "layer-row";
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = true;
      const name = document.createElement("span"); name.className = "name"; name.textContent = cls;
      const swatch = document.createElement("span"); swatch.className = "swatch"; swatch.style.background = colorFor(cls);
      let layerId: string | null = null;
      const ensure = async () => (layerId ??= (await layerMgr.addClassLayer(cls, cls)).id);
      swatchRows.push({ cls, swatch, ensure });
      cb.onchange = async () => { await ensure(); await layerMgr.setVisible(layerId!, cb.checked); };
      swatch.onclick = async () => { await ensure(); await layerMgr.setColor(layerId!, colorFor(cls)); };
      name.onclick = async () => {
        await ensure();
        const layer = layerMgr.layers.get(layerId!);
        await layerMgr.isolate(layerId!);
        if (layer) await fitToItems(layer.items);
        setStatus(`isolated ${cls}`);
      };
      row.append(cb, swatch, name);
      layersPanel.appendChild(row);
    }

    // Named selection sets (the saved-search-set pattern) — saved queries you can isolate.
    buildSelSets(layersPanel, elements, d);

    await refreshIssues();
    await reloadModelPins();
  }

  /** Render the "Selection sets" block into the Layers panel: saved queries → isolate. */
  function buildSelSets(host: HTMLElement, elements: ElementProps[], d: ProjectPanelDeps) {
    const { projectId, notify, setStatus, layerMgr } = d;
    if (!projectId) return;
    const pid = projectId;
    const wrap = document.createElement("div"); wrap.className = "selset-block";
    const title = document.createElement("div"); title.className = "section-title"; title.style.marginTop = "10px";
    title.textContent = "Selection sets";
    wrap.appendChild(title);

    const list = document.createElement("div"); wrap.appendChild(list);

    const draw = () => {
      const sets = loadSelSets(pid);
      list.innerHTML = "";
      if (!sets.length) {
        const hint = document.createElement("div"); hint.className = "meta"; hint.style.fontSize = "11px";
        hint.textContent = "Save a search as a set to isolate it in one click.";
        list.appendChild(hint);
      }
      sets.forEach((s, i) => {
        const row = document.createElement("div"); row.className = "selset-row";
        const label = document.createElement("span"); label.className = "selset-name";
        label.textContent = `${s.name} (${s.guids.length})`;
        label.title = `Isolate — query: “${s.q}”`;
        label.onclick = async () => {
          if (!s.guids.length) { notify(`“${s.name}” has no elements`, "error"); return; }
          await layerMgr.isolateGuids(s.guids);
          setStatus(`isolated set “${s.name}” · ${s.guids.length}`);
        };
        const del = document.createElement("button");
        del.className = "selset-del"; del.textContent = "✕"; del.title = "Delete set";
        del.setAttribute("aria-label", `Delete set ${s.name}`);
        del.onclick = () => { const next = loadSelSets(pid); next.splice(i, 1); saveSelSets(pid, next); draw(); };
        row.append(label, del);
        list.appendChild(row);
      });
    };

    const actions = document.createElement("div"); actions.className = "selset-actions";
    const add = document.createElement("button"); add.className = "mini-btn"; add.textContent = "➕ New set…";
    add.title = "Save a search (by name / class / type / discipline / level) as an isolatable set";
    add.onclick = async () => {
      const q = await askText("New selection set", { label: "Match elements containing (name / class / type / discipline / level):", value: "" });
      if (!q) return;
      const guids = resolveGuids(elements, q);
      if (!guids.length) { notify(`no elements match “${q}”`, "error"); return; }
      const name = await askText("New selection set", { label: `Name this set (${guids.length} elements)`, value: q });
      if (!name) return;
      const sets = loadSelSets(pid);
      const existing = sets.findIndex((s) => s.name === name);
      const entry: SelSet = { name, q, guids };
      if (existing >= 0) sets[existing] = entry; else sets.push(entry);
      saveSelSets(pid, sets);
      draw();
      notify(`saved set “${name}” · ${guids.length} elements`, "success");
    };
    const showAll = document.createElement("button"); showAll.className = "mini-btn"; showAll.textContent = "👁 Show all";
    showAll.title = "Clear isolation — make every element visible again";
    showAll.onclick = async () => { await layerMgr.showAll(); setStatus("all elements visible"); };
    actions.append(add, showAll);

    wrap.append(actions);
    draw();
    host.appendChild(wrap);
  }
