// Heavy viewer module — dynamically imported by main.ts on first Model-workspace open,
// so the ~6MB three + @thatopen bundle never loads for users who only use the
// Construction (GC portal) or Finance (proforma) workspaces.
import * as THREE from "three";
import CameraControls from "camera-controls";
import { createViewer, renderMode } from "./world";
import { installFileIO } from "./fileIO";
import { installCollabPresence } from "./collabPresence";
import { installKeysDyn } from "./keysDyn";
import { installEnvTools } from "./envTools";
import { inferDirection } from "./inference";
import { applyDynamicInput, polarConstrain } from "./snapEngine";
import { parseDynConstraint } from "./dynInput";
import { parseCadCommand } from "./cadCommands";
import { ModelLoader } from "./loader";
import { buildElementProps, buildRawProps } from "./propsView";
import { type ModelIdMap } from "./modelIds";
import { askText } from "../ui/prompt";
import { confirmModal, promptModal } from "../ui/modal";
import { SelectionSets } from "./selectionSets";
import { MeasureTool } from "../tools/measure";
import { SectionTool } from "../tools/section";
import { installMeasureTools, installSectionBox } from "./measureSection";
import { VisibilityTool } from "../tools/visibility";
import { ColorizeTool } from "../tools/colorize";
import { LayerManager } from "../tools/layers";
import { type SelSet, loadSelSets, saveSelSets, resolveGuids } from "../tools/selectionSetsStore";
import { OriginTool } from "../tools/origin";
import { buildTree, setDisciplineLookup } from "../tree/tree";
import { installDraftPanel, type ArmedDraft, type DraftPanelHandle } from "./draft/draftPanel";
import { type FamilyDef } from "./draft/draftCatalog";
import { GridOverlay } from "./draft/gridOverlay";
import { LogisticsOverlay } from "./draft/logisticsOverlay";
import { type LogisticsResource } from "../api/client";
import { DraftProxyLayer } from "./draft/draftProxy";
import { populate4dPanel } from "./fourD";
import { TransformGizmo } from "./draft/transformGizmo";
import { PinOverlay, restoreCamera } from "../pins/pins";
import { type ApiClient, type DisciplineTree, type ElementProps, type PropLayer, type PropMapRule, type Topic } from "../api/client";
import { escapeHtml, fetchArrayBufferWithProgress, setLoadingLabel, toast, withLoading } from "../ui/feedback";
import { showResult, kvTable, resultNote } from "../ui/result";
import { openNodeCanvas } from "./nodeCanvas";
import { openTakeoff2d } from "./takeoff2d";

/** View options the settings bar owns (in main) and the viewer applies. */
export type Settings = {
  theme: "dark" | "light"; grid: boolean; projection: "Perspective" | "Orthographic";
  background: "dark" | "light" | "none"; zoomCursor: boolean;
  nav: "orbit" | "pan" | "cad"; units: "m" | "cm" | "mm" | "ft"; section: boolean;
  snap: number;   // grid-snap increment in metres (0 = off) for authoring placement
};

/** What main passes in. */
export interface ViewerCtx {
  container: HTMLElement;
  api: ApiClient;
  projectId: string | null;
  connected: boolean;
  projectName: string;
  setStatus: (m: string) => void;
  notify: (m: string, kind?: "info" | "success" | "error") => void;
  getSettings: () => Settings;
}

/** What main calls back into. */
export interface ViewerApp {
  applySettings(): void;
  selectByGuid(guid: string, fit?: boolean): Promise<void>;
  reloadModelPins(): Promise<void>;
  fitToModels(): Promise<void>;
  refreshIssues(): Promise<void>;
  anchorPoint(): { x: number; y: number; z: number } | null;
  selectedGuidValue(): string | null;
  triggerOpen(kind: "ifc" | "frag" | "convert"): void;
  openFile(kind: "ifc" | "frag" | "convert" | "ref", file: File): Promise<void>;
  addReferenceObject(object: import("three").Object3D, label: string): string;
  loadSample(file: string, label: string): Promise<void>;
  exportFrag(): Promise<void>;
  exportIfc(): void;
  handleKey(key: string): boolean;
  onModelShown(): void;
  openAuthoring(): void;
}

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

/** Build the whole 3D app: viewer, tools, selection, panels, authoring. Self-initialises
 *  (loads the project model + builds its rail panels) at the end. */
export function initViewerApp(ctx: ViewerCtx): ViewerApp {
  const { container, api, connected } = ctx;
  const projectId = ctx.projectId;
  const setStatus = ctx.setStatus;
  const notify = ctx.notify;
  const propsPanel = $("panel-props");   // Properties is now a docked rail panel (Revit-style), not a floating aside
  const propsBody = $("props-body");
  const propsHint = () => { propsBody.innerHTML = `<div class="meta">Select an element in the model to see its type, parameters, and property sets.</div>`; };

  // UX-4: an always-visible **Info-Box** — a compact strip on the 3D canvas showing the selected element's
  // key facts (name · class · level · discipline) regardless of which rail tab is open (ArchiCAD pattern).
  let discColorByName: Record<string, string> = {};
  void api.disciplineTree?.().then((t) => {
    discColorByName = Object.fromEntries(t.disciplines.map((d) => [d.name, d.color]));
  }).catch(() => { /* offline — Info-Box just omits the colour dot */ });
  const infoBox = document.createElement("div");
  infoBox.className = "info-box"; infoBox.hidden = true;
  infoBox.setAttribute("aria-live", "polite");
  container.appendChild(infoBox);
  const updateInfoBox = (el: ElementProps | null) => {
    if (!el) { infoBox.hidden = true; infoBox.innerHTML = ""; return; }
    const cls = el.ifc_class.replace("Ifc", "");
    const disc = el.discipline || "";
    const dot = disc && discColorByName[disc]
      ? `<span class="info-dot" style="background:${discColorByName[disc]}"></span>` : "";
    infoBox.innerHTML = `<b>${escapeHtml(el.name || cls)}</b>`
      + `<span class="info-sep">·</span><span>${escapeHtml(cls)}</span>`
      + (el.storey ? `<span class="info-sep">·</span><span>${escapeHtml(el.storey)}</span>` : "")
      + (disc ? `<span class="info-sep">·</span>${dot}<span>${escapeHtml(disc)}</span>` : "");
    infoBox.hidden = false;
  };

  const viewer = createViewer(container);
  const loader = new ModelLoader(viewer);
  // keep the federation list in sync whenever a model registers (fires after load completes)
  loader.fragments.list.onItemSet.add(() => refreshFederation());
  const sets = new SelectionSets(viewer.components);
  const measure = new MeasureTool(viewer.components, viewer.world);
  const section = new SectionTool(viewer.components, viewer.world);
  const visibility = new VisibilityTool(viewer.components);
  const colorize = new ColorizeTool(viewer.components);
  const layerMgr = new LayerManager(viewer.components);
  let dispose4d: (() => void) | null = null;   // FOURD-SIM playback teardown (restores visibility)
  const origin = new OriginTool();

  let selection: ModelIdMap | null = null;
  let lastPoint: THREE.Vector3 | null = null;
  let selectedGuid: string | null = null;
  let editInPlace = false;            // P5: show the move gizmo on the selected element
  let gizmo: TransformGizmo | null = null;
  let modelCount = 0;
  // track a human label per loaded model so the federation panel can list disciplines
  const modelLabels = new Map<string, string>();
  // view-only reference overlays (meshes / point clouds) added alongside the fragment models
  const referenceModels = new Map<string, { object: THREE.Object3D; label: string; dispose?: () => void }>();
  const nextId = (label?: string) => {
    const id = `model-${++modelCount}`;
    if (label) modelLabels.set(id, label);
    return id;
  };

  const SELECT_MAT = (): import("@thatopen/fragments").MaterialDefinition => ({
    color: new THREE.Color("#33d17a"), opacity: 1, transparent: false,
    renderedFaces: 1, preserveOriginalMaterial: false,
  });

  // ---- selection -----------------------------------------------------------
  async function selectMap(map: ModelIdMap | null, opts: { guid?: string; fit?: boolean } = {}) {
    if (selection) await loader.fragments.resetHighlight(selection);
    selection = map;
    if (!map) { gizmo?.hide(); propsHint(); updateInfoBox(null); props5d.innerHTML = ""; propsVerify.innerHTML = ""; propsLinks.replaceChildren(); return; }
    await loader.fragments.highlight(SELECT_MAT(), map);
    await loader.fragments.core.update(true);
    if (opts.fit) await fitToItems(map);
    await showProps(map, opts.guid);
    if (editInPlace) await attachGizmo(map);
  }

  // 5D inspector — appended under the property panel; populated on selection
  const props5d = document.createElement("div"); props5d.id = "props-5d";
  props5d.style.cssText = "margin-top:6px;font-size:11px;line-height:1.5";
  propsPanel.appendChild(props5d);

  // field-verification — mark the selected element installed/verified/deviation (Argyle-style QA)
  const propsVerify = document.createElement("div"); propsVerify.id = "props-verify";
  propsVerify.style.cssText = "margin-top:6px;font-size:11px;line-height:1.6";
  propsPanel.appendChild(propsVerify);

  // linked records — the reverse deep-link: which portal records (RFIs, issues, COs, verifications,
  // activities) reference the selected element by GlobalId. Completes the record→element round-trip.
  const propsLinks = document.createElement("div"); propsLinks.id = "props-links";
  propsLinks.style.cssText = "margin-top:6px;font-size:11px;line-height:1.6";
  propsPanel.appendChild(propsLinks);
  propsHint();   // show the "select an element" prompt until something is picked

  async function renderLinkedRecords(guid: string) {
    propsLinks.replaceChildren();
    if (!connected || !projectId || !guid) return;
    let d; try { d = await api.elementRecords(projectId, guid); } catch { return; }
    if (!d.total) return;
    const head = document.createElement("div");
    head.style.cssText = "font-weight:700;border-top:1px solid var(--line);padding-top:6px";
    head.textContent = `🔗 Linked records (${d.total})`;
    propsLinks.appendChild(head);
    for (const g of d.modules) {
      const row = document.createElement("div");
      const lab = document.createElement("b"); lab.textContent = `${g.icon} ${g.module_name} `;
      row.appendChild(lab);
      for (const r of g.records) {
        const chip = document.createElement("span");
        chip.className = "badge"; chip.textContent = r.ref ?? "";
        chip.title = `${r.title ?? ""} · ${r.state ?? ""}`;
        row.append(chip, document.createTextNode(" "));
      }
      propsLinks.appendChild(row);
    }
  }

  async function renderVerify(guid: string) {
    propsVerify.innerHTML = "";
    if (!connected || !projectId || !guid) return;
    const setBtn = (label: string, status: string, color: string) => {
      const b = document.createElement("button");
      b.className = "file-btn"; b.textContent = label;
      b.style.cssText = `font-size:11px;padding:2px 8px;border-color:${color}`;
      b.onclick = async () => {
        try {
          await api.setVerification(projectId!, guid, { status });
          lbl.textContent = ` ${label}`; lbl.style.color = color;
          setStatus(`element marked ${status}`);
        } catch (e) { setStatus("verify failed: " + (e as Error).message); }
      };
      return b;
    };
    const row = document.createElement("div");
    row.style.cssText = "border-top:1px solid var(--line);padding-top:6px";
    row.innerHTML = `<div style="font-weight:700">Field verification</div>`;
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:4px;align-items:center;flex-wrap:wrap;margin-top:3px";
    bar.append(setBtn("Installed", "installed", "#4a8cff"), setBtn("Verified", "verified", "#33d17a"),
               setBtn("Deviation", "deviation", "#e2554a"));
    const lbl = document.createElement("span"); lbl.className = "meta";
    bar.appendChild(lbl);
    row.appendChild(bar); propsVerify.appendChild(row);
  }

  async function render5D(guid: string) {
    props5d.innerHTML = "";
    if (!connected || !projectId) return;
    let d; try { d = await api.element5d(projectId, guid); } catch { return; }
    if (!d.schedule && !d.cost) return;
    const usd = (n: number) => "$" + Math.round(n).toLocaleString();
    let html = `<div style="font-weight:700;border-top:1px solid var(--line);padding-top:6px">5D — schedule &amp; cost</div>`;
    if (d.schedule) {
      const s = d.schedule;
      html += `<div>🗓 <b>${s.name}</b>${s.trade ? ` · ${s.trade}` : ""} · ${s.percent}% complete`
        + `${s.hard_tied ? "" : ` <span class="meta">(by trade)</span>`}</div>`;
      if (s.start || s.finish) html += `<div class="meta">${s.start ?? "?"} → ${s.finish ?? "?"}${s.state ? ` · ${s.state}` : ""}</div>`;
    }
    if (d.cost) {
      const c = d.cost; const vcol = c.variance < 0 ? "#e2554a" : "#33d17a";
      html += `<div>💰 <b>${c.code ?? c.name}</b> · budget ${usd(c.budget)} · committed ${usd(c.committed)} · actual ${usd(c.actual)}`
        + ` · <span style="color:${vcol}">var ${usd(c.variance)}</span></div>`;
    }
    props5d.innerHTML = html;
  }

  async function showProps(map: ModelIdMap, guid?: string) {
    if (guid) { void render5D(guid); void renderVerify(guid); void renderLinkedRecords(guid); }
    else { props5d.innerHTML = ""; propsVerify.innerHTML = ""; propsLinks.replaceChildren(); }
    if (connected && projectId && guid) {
      try { renderProps(await api.element(projectId, guid)); return; } catch { /* fall through */ }
    }
    const [modelId, ids] = Object.entries(map)[0] ?? [];
    if (!modelId) return;
    const model = loader.fragments.list.get(modelId);
    const localId = ids ? [...ids][0] : undefined;
    if (!model || localId === undefined) return;
    const [data] = await model.getItemsData([localId], {
      attributesDefault: true,
      relations: { IsDefinedBy: { attributes: true, relations: true } },
      relationsDefault: { attributes: false, relations: false },
    });
    propsBody.replaceChildren(buildRawProps(data));
  }

  function renderProps(el: ElementProps) {
    // structured property + classification editor — only when we can write (connected + project);
    // each edit applies a server recipe and re-publishes, then we re-fetch the element's props.
    const hooks = (connected && projectId) ? {
      setProp: async (pset: string, prop: string, value: string, dtype: string) => {
        await api.editIfc(projectId!, "set_element_pset", { guid: el.guid, pset, prop, value, dtype }, true);
        try { renderProps(await api.element(projectId!, el.guid)); } catch { /* index still rebuilding */ }
      },
      classify: async (system: string, code: string, name: string) => {
        await api.editIfc(projectId!, "set_classification", { guid: el.guid, system, code, name }, true);
        try { renderProps(await api.element(projectId!, el.guid)); } catch { /* index still rebuilding */ }
      },
    } : undefined;
    // Revit-style identity header: the Type (the family/type it's an instance of) sits above the
    // instance parameters + property sets, so "what is this" reads before "its values".
    const head = document.createElement("div");
    head.style.cssText = "border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px;background:var(--panel2)";
    const cls = el.ifc_class.replace("Ifc", "");
    head.innerHTML = `<div style="font-weight:700;font-size:13px">${escapeHtml(el.name || cls)}</div>`
      + `<div class="meta" style="font-size:11px;margin-top:2px">Type: <b>${escapeHtml(el.type_name || "—")}</b></div>`
      + `<div class="meta" style="font-size:11px">Class: ${escapeHtml(cls)}${el.storey ? ` · Level: ${escapeHtml(el.storey)}` : ""}</div>`;
    const wrap = document.createElement("div");
    wrap.append(head, buildElementProps(el, hooks));
    propsBody.replaceChildren(wrap);
    updateInfoBox(el);
  }

  async function selectByGuid(guid: string, fit = false) {
    selectedGuid = guid;
    await selectMap(await sets.fromGuids([guid]), { guid, fit });
  }

  $("props-close").addEventListener("click", () => void selectMap(null));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (armed) { disarmDraft(); notify("draft cancelled", "info"); return; }
    if (selectedGuid) void selectMap(null);
  });

  // ---- 3D click ------------------------------------------------------------
  const mouse = new THREE.Vector2();
  container.addEventListener("click", async (e) => {
    // An ARMED draw tool always wins over a lingering measure mode — otherwise a measure tool left on
    // silently eats every draft click with zero feedback (the drafter sees an armed wall tool and dead
    // clicks). Measure keeps the click only when nothing is armed.
    if (measure.mode !== "off" && !armed) { measure.create(); return; }
    if (gizmo?.dragging) return;                 // a gizmo-handle drag isn't a select/deselect click
    mouse.set(e.clientX, e.clientY);
    // A stalled Fragments worker (hidden tab / heavy load) must not silently eat clicks: race the
    // raycast with a short timeout and fall back to the ground plane — drafting keeps working, and a
    // selection click just misses (same as clicking empty space). Normal raycasts answer in ms.
    const hit = await Promise.race([
      loader.fragments.raycast({
        camera: viewer.world.camera.three, mouse, dom: viewer.world.renderer!.three.domElement,
      }),
      new Promise<null>((res) => window.setTimeout(() => res(null), 1500)),
    ]);
    if (armed) { await captureDraftPoint(e, hit ?? null); return; }
    if (!hit) { await selectMap(null); return; }
    // UX-2 snap-as-you-place: the picked point snaps to the element's nearest vertex / edge midpoint /
    // corner, so every lastPoint consumer (notes · dimensions · revision clouds · tags · fittings)
    // anchors exactly on geometry instead of the raw raycast point.
    const snapped = await snapToGeometry(hit.point, hit);
    lastPoint = (snapped ?? hit.point).clone();
    if (snapped) flashSnapGlyph(e, "◻ snap");
    showCoords(lastPoint);
    const [guid] = await hit.fragments.getGuidsByLocalIds([hit.localId]);
    selectedGuid = guid ?? null;
    await selectMap({ [hit.fragments.modelId]: new Set([hit.localId]) }, { guid: guid ?? undefined });
    setStatus(`selected ${guid ?? hit.localId}`);
  });
  container.addEventListener("dblclick", () => {
    if (armed && armed.points === "poly") {
      if (armPts.length >= 3) void finishDraft(); else notify("need at least 3 points to close", "error");
      return;
    }
    if (section.enabled) void section.createPlane();
  });

  // REL-4 leaf: all file open/import/export paths live in fileIO.ts
  const fileIO = installFileIO({
    viewer, loader, api, container, projectId: () => projectId, connected: () => connected,
    notify, setStatus, nextId, referenceModels,
    refreshFederation: () => refreshFederation(), fitToModels: () => fitToModels(),
    waitForPublish: (pid, cb) => waitForPublish(pid, cb), loadProjectModel: () => loadProjectModel(),
    buildToolsPanel: () => buildToolsPanel(), buildClashPanel: () => buildClashPanel(),
  });
  const { openFile, addReferenceObject, loadSample, exportFrag, exportIfc, triggerOpen } = fileIO;

  // ---- floating toolbar ----------------------------------------------------
  const viewerTools = $("viewer-tools");
  function toolBtn(icon: string, title: string, onClick: (b: HTMLButtonElement) => void, cap?: "edit" | "review") {
    const b = document.createElement("button");
    b.textContent = icon; b.className = "tool-btn icon-btn"; b.title = title;
    b.setAttribute("aria-label", title);
    if (cap) b.dataset.cap = cap;   // hidden by CSS when the caller lacks the project capability
    b.onclick = () => onClick(b);
    viewerTools.appendChild(b);
    return b;
  }
  /** Visual separator between functional groups of toolbar buttons (legibility for the icon row). */
  function toolDivider(cap?: "edit" | "review") {
    const d = document.createElement("span"); d.className = "tool-sep";
    if (cap) d.dataset.cap = cap;   // hide the divider too when its group is capability-hidden
    viewerTools.appendChild(d);
  }
  // REL-4 leaf: the measure / visibility button group lives in measureSection.ts
  const msDeps = {
    viewer, loader, toolBtn, setStatus, notify, measure, section,
    selection: () => selection, visibility, colorize,
  };
  installMeasureTools(msDeps);
  toolBtn("✦", "Ask the model — plain-English questions about the data", () => {
    if (!connected || !projectId) { notify("open a project to ask about its model", "error"); return; }
    showResult("Ask the model", (body) => {
      body.innerHTML = `<div class="meta" style="margin-bottom:8px">Ask in plain English — e.g. “how many fire-rated doors on level 3?”, “total curtain-wall area”, “which storeys have the most elements?”. Answers are grounded in this model's property index.</div>`;
      const inp = document.createElement("input");
      inp.type = "text"; inp.placeholder = "Type a question…";
      inp.style.cssText = "width:100%;padding:8px;box-sizing:border-box";
      const ans = document.createElement("div"); ans.style.cssText = "margin-top:10px;white-space:pre-wrap;line-height:1.5";
      const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Ask"; go.style.marginTop = "8px";
      const run = async () => {
        const q = inp.value.trim(); if (!q) return;
        ans.textContent = "Thinking…"; go.disabled = true;
        try {
          const r = await api.askModel(projectId!, q);
          ans.textContent = r.answer || "";
          if (r.source !== "claude") {
            const note = r.source === "disabled" ? "AI key not set — showing the model snapshot the assistant would use." : "";
            ans.textContent = (r.answer || "") + (note ? "\n\n" + note : "")
              + (r.snapshot ? "\n\n" + JSON.stringify(r.snapshot, null, 2) : "");
          }
        } catch (e) { ans.textContent = "Couldn't ask: " + (e as Error).message; }
        finally { go.disabled = false; }
      };
      go.onclick = () => void run();
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") void run(); });
      body.append(inp, go, ans); inp.focus();
    });
  });
  // UX-4: "Script this" — make the scriptable recipe interface a first-class, discoverable resource.
  // Plain-English → the GUID-safe recipe plan it maps to (the same verbs the AI bar + sandbox use) → apply.
  toolBtn("⌨", "Script this — see the GUID-safe recipe plan behind a plain-English command, then apply", () => {
    if (!connected || !projectId) { notify("open a project to script it", "error"); return; }
    showResult("Script this — the recipe interface", (body) => {
      body.appendChild(resultNote("Every tool here is a <b>GUID-safe recipe</b> — the same verbs the AI "
        + "command bar and the sandboxed <code>ifcopenshell</code> runner drive. Type what you want in plain "
        + "English to see the exact recipe plan it maps to, then apply it. (Advanced: run sandboxed code via "
        + "the rail's Build → 🔧 Advanced → ⚡ Run IFC code.)", ""));
      const inp = document.createElement("input"); inp.type = "text"; inp.className = "portal-filter";
      inp.placeholder = "✨ e.g. add a 3m wall from 0,0 to 5,0"; inp.style.cssText = "width:100%;padding:8px;box-sizing:border-box;margin-bottom:6px";
      const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Interpret →";
      const out = document.createElement("div"); out.style.marginTop = "8px";
      const run = async () => {
        const text = inp.value.trim(); if (!text) return;
        out.innerHTML = `<div class="meta">Interpreting…</div>`;
        let res;
        try { res = await api.aiAuthor(projectId!, text, { selected_guids: selectedGuid ? [selectedGuid] : undefined, active_storey: activeStorey || undefined }); }
        catch (e) { out.innerHTML = `<div class="meta">command failed: ${escapeHtml((e as Error).message)}</div>`; return; }
        if (res.needs_clarification) { out.innerHTML = `<div class="meta">${escapeHtml(res.needs_clarification)}</div>`; return; }
        out.innerHTML = "";
        out.appendChild(resultNote(`Maps to <b>${res.plan.length}</b> GUID-safe recipe step(s):`, ""));
        const pre = document.createElement("pre");
        pre.style.cssText = "white-space:pre-wrap;font-size:11px;background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:8px;overflow:auto";
        pre.textContent = res.plan.map((s, i) => `${i + 1}. ${s.recipe}(${JSON.stringify(s.params)})`).join("\n") || "(no steps)";
        out.appendChild(pre);
        if (res.plan.length && !res.plan.some((s) => s.destructive)) {
          const apply = document.createElement("button"); apply.className = "file-btn"; apply.textContent = `✓ Apply ${res.plan.length} step(s)`; apply.style.marginTop = "6px";
          apply.onclick = () => withLoading(container, "authoring + republishing", async () => {
            try {
              for (let i = 0; i < res.plan.length; i++) { const s = res.plan[i]; if (!s) continue; await api.editIfc(projectId!, s.recipe, s.params, i === res.plan.length - 1); }
              const st = await waitForPublish(projectId!);
              if (st === "done") { await loadProjectModel(); await reloadModelPins(); notify("applied", "success"); }
              else notify(`applied — publish ${st}`, st === "error" ? "error" : "info");
            } catch (e) { notify(`apply failed: ${(e as Error).message}`, "error"); }
          });
          out.appendChild(apply);
        }
      };
      go.onclick = () => void run();
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") void run(); });
      body.append(inp, go, out); inp.focus();
    });
  });
  toolDivider();   // ── measure / visibility ──┊── collaboration ──

  // REL-4 leaf: live presence + peer cursors + shared viewpoints + the publish-reload banner all
  // live in collabPresence.ts; the handle exposes capture/jump for env tools + BCF viewpoints and
  // resync() for loadProjectModel (our own publish never nags us).
  const collab = installCollabPresence({
    viewer, loader, api, container, projectId: () => projectId, toolBtn, notify,
    loadProjectModel: () => loadProjectModel(),
  });
  const captureViewpoint = collab.captureViewpoint;
  const jumpToViewpoint = collab.jumpToViewpoint;
  toolDivider();   // ── collaboration ──┊── view aids ──

  // REL-4 leaf: the section-box tool lives in measureSection.ts (positioned after the collab group)
  installSectionBox(msDeps);

  // 3D-HERO: capture the current 3D view → the project's hero image (page 2 of the package PDF).
  // Render one fresh frame synchronously before reading the canvas — WebGL buffers don't persist
  // between frames (preserveDrawingBuffer is off), so a stale read gives a black image.
  toolBtn("📸", "Capture hero image — this view becomes page 2 of the client project package (PDF)", (b) => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    const r = viewer.world.renderer!.three;
    r.render(viewer.world.scene.three, viewer.world.camera.three);
    r.domElement.toBlob(async (blob) => {
      if (!blob) { notify("couldn't capture the canvas", "error"); return; }
      b.disabled = true;
      try {
        const res = await api.uploadHero(projectId!, blob);
        notify(`hero captured (${Math.round(res.bytes / 1024)} KB) — it now leads the project package`, "success");
      } catch (e) { notify(`hero upload failed: ${(e as Error).message}`, "error"); }
      b.disabled = false;
    }, "image/png");
  });

  // REL-4 leaf: render mode + sun study + walk mode + levels overlay live in envTools.ts
  const envTools = installEnvTools({
    viewer, loader, api, projectId: () => projectId, toolBtn, notify, setStatus,
    getSettings: () => ctx.getSettings(), captureViewpoint, jumpToViewpoint,
  });

  // ---- modeling: author walls / columns / beams / families from ground clicks
  const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const groundRay = new THREE.Raycaster();
  // --- P0 Draft panel: parameter-driven placement (supersedes the prompt()-based buttons above) ----
  let armed: ArmedDraft | null = null;          // active Draft-panel element, or null
  const armPts: THREE.Vector3[] = [];
  let draftHandle: DraftPanelHandle | null = null;
  // REL-4 leaf: the KEYS 2-letter shortcuts, the typed distance/angle constraint (dynamic input),
  // and the snap-glyph feedback live in keysDyn.ts; the handle exposes the dyn buffer for the draft
  // flow and Escape routes back through disarmDraft.
  const keysDyn = installKeysDyn({
    container, notify,
    isArmed: () => !!armed, armedPoints: () => armPts.length,
    draftHandle: () => draftHandle, onEscape: () => disarmDraft(),
  });
  const setDynBuf = keysDyn.setDynBuf;
  const flashSnapGlyph = keysDyn.flashSnapGlyph;
  function disarmDraft() { armed = null; armPts.length = 0; setDynBuf(""); draftHandle?.onArmCleared(); }
  // P1 grid/level drafting refs: the grid overlay + snap, and the active storey/work-plane.
  const gridOverlay = new GridOverlay(viewer.world.scene.three);
  const logisticsOverlay = new LogisticsOverlay(viewer.world.scene.three);
  const draftProxies = new DraftProxyLayer(viewer.world.scene.three);   // P6: optimistic placement feedback
  let activeStorey: string | null = null;       // name passed to Draft recipes; sets the work-plane Z
  let activeStoreyZ = 0;
  // Authoring is done through the Draft panel (the parameter-driven, snapping, per-level surface) —
  // the old click-to-place toolbar buttons (wall/column/beam/family) were a redundant second way to do
  // the same thing and were removed. The buttons below act on the *selected* element.
  toolDivider("edit");   // ── view aids ──┊── authoring (editors only) ──
  toolBtn("␡", "Delete selected element", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    if (!(await confirmModal(`Delete element ${selectedGuid.slice(0, 8)}? This re-authors the IFC.`, "", "Delete", true))) return;
    await authorAndReload("delete_element", { guid: selectedGuid }, "delete");
  }, "edit");
  const addOpening = async (kind: "door" | "window") => {
    if (!selectedGuid) { notify(`select a wall first, then add the ${kind}`, "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to author", "error"); return; }
    // use where you clicked the wall as the position (projected onto the wall axis); else centered
    const params: Record<string, unknown> = { host_guid: selectedGuid };
    if (lastPoint) params.position = [lastPoint.x, -lastPoint.z];
    await authorAndReload(kind === "window" ? "add_window" : "add_door", params, kind);
  };
  toolBtn("◧", "Add door to selected wall", () => void addOpening("door"), "edit");
  toolBtn("◨", "Add window to selected wall", () => void addOpening("window"), "edit");
  toolBtn("✥", "Move selected element (E,N,Z metres)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const v = await askText("Move element", { label: "Move by E, N, Z metres (comma-separated):", value: "1, 0, 0" });
    if (!v) return;
    const [dx, dy, dz] = v.split(",").map((n) => Number(n.trim()) || 0);
    await authorAndReload("move_element", { guid: selectedGuid, dx, dy, dz }, "move");
  }, "edit");
  toolBtn("⟲", "Rotate selected element (degrees about Z)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const a = Number(await askText("Rotate element", { label: "Rotate by degrees (about vertical axis):", value: "90" }));
    if (!a) return;
    await authorAndReload("rotate_element", { guid: selectedGuid, angle: a }, "rotate");
  }, "edit");
  toolBtn("✎", "Edit a property on the selected element", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const pset = await askText("Edit property", { label: "Pset name:", value: "Pset_WallCommon" }); if (!pset) return;
    const propName = await askText("Edit property", { label: "Property:", value: "FireRating" }); if (!propName) return;
    const value = await askText("Edit property", { label: `Value for ${propName}:`, value: "" }); if (value === null) return;
    await authorAndReload("set_element_pset", { guid: selectedGuid, pset, prop: propName, value }, "property edit");
  }, "edit");
  toolBtn("⧉", "Copy selected element (offset E,N,Z metres)", async () => {
    if (!selectedGuid) { notify("select an element first", "error"); return; }
    if (!projectId) { notify("connect a project with a source IFC to edit", "error"); return; }
    const v = await askText("Copy element", { label: "Copy with offset E, N, Z metres:", value: "1, 0, 0" }); if (!v) return;
    const [dx, dy, dz] = v.split(",").map((n) => Number(n.trim()) || 0);
    await authorAndReload("copy_element", { guid: selectedGuid, dx, dy, dz }, "copy");
  }, "edit");
  toolBtn("◈", "Edit in place — drag the gizmo to move the selected element", (b) => {
    editInPlace = !editInPlace;
    b.classList.toggle("on", editInPlace);
    if (editInPlace) {
      if (selection) { void attachGizmo(selection); }
      notify("Edit-in-place on — select an element and drag the gizmo to move it", "info");
    } else {
      gizmo?.hide();
      setStatus("edit-in-place off");
    }
  }, "edit");

  /** Round a point's plan coords (x,z) to the grid-snap increment; leave height (y). */
  function snapPoint(p: THREE.Vector3): THREE.Vector3 {
    const inc = ctx.getSettings().snap;
    if (!inc) return p;
    return new THREE.Vector3(Math.round(p.x / inc) * inc, p.y, Math.round(p.z / inc) * inc);
  }

  type Hit = { point: THREE.Vector3; fragments: { modelId: string }; localId: number };
  /** Snap to the hit element's nearest mesh vertex within ~0.4 m (true endpoint snap), then to its
   *  bounding-box corners / edge midpoints / center (the classic osnap set), then to grid snap. */
  async function snapToGeometry(raw: THREE.Vector3, hit: Hit | null): Promise<THREE.Vector3 | null> {
    if (!hit) return null;
    const nearest = (pts: THREE.Vector3[]) => {
      let best: THREE.Vector3 | null = null, bd = 0.4;
      for (const v of pts) { const d = raw.distanceTo(v); if (d < bd) { bd = d; best = v; } }
      return best ? best.clone() : null;
    };
    try {
      const model = loader.fragments.list.get(hit.fragments.modelId);
      const verts = model ? await model.getPositions([hit.localId]) : null;
      if (verts?.length) { const v = nearest(verts); if (v) return v; }
    } catch { /* fall back to bbox candidates */ }
    try {
      const boxes = await loader.fragments.getBBoxes({ [hit.fragments.modelId]: new Set([hit.localId]) });
      if (!boxes.length) return null;
      const bx = boxes[0]!; // safe: boxes.length checked above
      const xs = [bx.min.x, bx.max.x], ys = [bx.min.y, bx.max.y], zs = [bx.min.z, bx.max.z];
      const corners = xs.flatMap((x) => ys.flatMap((y) => zs.map((z) => new THREE.Vector3(x, y, z))));
      // UX-2: edge midpoints (each axis at its midpoint × the other two axes' extremes) + the center —
      // the midpoint/center osnaps annotation placement expects.
      const mx = (bx.min.x + bx.max.x) / 2, my = (bx.min.y + bx.max.y) / 2, mz = (bx.min.z + bx.max.z) / 2;
      const mids = [
        ...ys.flatMap((y) => zs.map((z) => new THREE.Vector3(mx, y, z))),
        ...xs.flatMap((x) => zs.map((z) => new THREE.Vector3(x, my, z))),
        ...xs.flatMap((x) => ys.map((y) => new THREE.Vector3(x, y, mz))),
        new THREE.Vector3(mx, my, mz),
      ];
      return nearest([...corners, ...mids]);
    } catch { return null; }
  }

  // --- P0 Draft placement: parameter-driven (params baked into `armed.build`), no prompt() --------
  async function captureDraftPoint(e: MouseEvent, hit: Hit | null) {
    const spec = armed;
    if (!spec) return;
    const raw = hit?.point ?? screenToGround(e);
    const geoSnap = raw ? await snapToGeometry(raw, hit) : null;   // hard endpoint/edge/vertex snap
    let p = raw ? (geoSnap ?? snapPoint(raw)) : null;
    if (geoSnap) flashSnapGlyph(e, "◻ snap");
    // SNAP-KIT phase 2 — a TYPED constraint beats every automatic snap: the drafter said exactly
    // what they want. Plan angles are CCW-from-east with North "up" = -z, while the snap engine's
    // +z axis points south — so the typed angle's sign flips on the way in.
    const dynC = armPts.length >= 1 ? parseDynConstraint(keysDyn.dynBuf()) : null;
    if (p && dynC) {
      const a = armPts[armPts.length - 1]!;
      const applied = applyDynamicInput({ x: a.x, z: a.z }, { x: p.x, z: p.z },
        { distance: dynC.distance, angle: dynC.angle !== undefined ? -dynC.angle : undefined });
      p = new THREE.Vector3(applied.x, p.y, applied.z);
      showCoords(p);
      flashSnapGlyph(e, `⌨ ${keysDyn.dynBuf()}`);
      setDynBuf("");
    } else if (p && e.shiftKey && armPts.length >= 1) {   // ortho lock from the previous point
      const a = armPts[armPts.length - 1]!; // safe: armPts.length >= 1 checked above
      if (Math.abs(p.x - a.x) >= Math.abs(p.z - a.z)) p = new THREE.Vector3(p.x, p.y, a.z);
      else p = new THREE.Vector3(a.x, p.y, p.z);
    } else if (p && !geoSnap && armPts.length >= 1) {
      // E1 — automatic on-axis / parallel inference (SketchUp-style): snap the point onto a world axis
      // or the previous edge's direction/perpendicular when the cursor is within ~6° of it. A hard
      // geometry-vertex snap (above) always wins; Shift is the manual hard ortho-lock.
      const a = armPts[armPts.length - 1]!;
      const ref = armPts.length >= 2
        ? { x: a.x - armPts[armPts.length - 2]!.x, z: a.z - armPts[armPts.length - 2]!.z } : undefined;
      const inf = inferDirection({ x: a.x, z: a.z }, { x: p.x, z: p.z }, { tolDeg: 6, ref });
      if (inf) { p = new THREE.Vector3(inf.x, p.y, inf.z); showCoords(p); flashSnapGlyph(e, "∠ axis"); }
      else {
        // SNAP-KIT — polar tracking: when axis/parallel inference didn't lock, snap the bearing from
        // the previous point to the nearest 45° increment (catches the diagonals the axis-only
        // inference misses). Distance preserved; a hard geometry snap above still always wins.
        const pol = polarConstrain({ x: a.x, z: a.z }, { x: p.x, z: p.z }, 45, 4);
        if (pol.locked) { p = new THREE.Vector3(pol.x, p.y, pol.z); showCoords(p); flashSnapGlyph(e, `◇ ${pol.angle}°`); }
      }
    }
    if (!p) { notify("couldn't pick a point — click the floor or grid", "error"); return; }
    // snap to the nearest grid intersection when the grid overlay is loaded (plan E=x, N=-z) —
    // unless a TYPED constraint placed this point (explicit intent must not be re-snapped away)
    if (gridOverlay.hasData && !dynC) {
      const gs = gridOverlay.nearestSnap(p.x, -p.z, 0.6);
      if (gs) p = new THREE.Vector3(gs[0], p.y, -gs[1]);
    }
    showCoords(p); armPts.push(p.clone());
    if (spec.points === "poly") { notify(`${spec.label}: ${armPts.length} point(s) — double-click to close`, "info"); return; }
    if (armPts.length < spec.points) { notify(`${spec.label}: click the next point (Shift = ortho)`, "info"); return; }
    await finishDraft();
  }
  async function finishDraft() {
    if (!armed || !projectId) { disarmDraft(); return; }
    const a = armed;
    const planPts = armPts.map((v): [number, number] => [v.x, -v.z]);   // plan coords: E=x, N=-z
    const params = a.build(planPts);
    if (activeStorey && params.storey === undefined) params.storey = activeStorey;   // author onto the active level
    disarmDraft();
    draftProxies.fromParams(params, activeStoreyZ);                                   // instant optimistic proxy
    // incremental preview: real one-element geometry immediately (fail-open — keep the proxy on error)
    let previewId: string | null = null;
    try {
      const pv = await api.editPreview(projectId, a.recipe, params);
      if (pv?.frag) {
        previewId = `preview-${pv.guid || Date.now()}`;
        await loader.loadFragments(pv.frag, previewId);
        draftProxies.clear();
      }
    } catch { /* preview unavailable — the optimistic proxy stands until the full reload */ }
    await authorAndReload(a.recipe, params, a.label, previewId);
  }

  async function authorAndReload(recipe: string, params: Record<string, unknown>, label: string,
                                 previewId: string | null = null) {
    // the preview model is normally reclaimed by loadProjectModel()'s disposeAll; on any non-done
    // outcome it would otherwise orphan GPU geometry (unique id per attempt) — dispose it explicitly.
    const dropPreview = async () => { if (previewId) { await loader.disposeOne(previewId).catch(() => {}); } };
    await withLoading(container, `authoring ${label} + republishing`, async () => {
      try {
        await api.editIfc(projectId!, recipe, params, true);
        notify(`${label} authored — converting…`, "info");
        const state = await waitForPublish(projectId!);
        if (state === "done") { const shown = await loadProjectModel(); draftProxies.clear(); notify(`${label} applied${shown ? " — shown" : ""}`, "success"); }
        else { await dropPreview(); notify(`${label} authored — publish ${state}`, state === "error" ? "error" : "info"); }
        await reloadModelPins();
      } catch (err) { draftProxies.clear(); await dropPreview(); notify(`${label} failed: ${(err as Error).message}`, "error"); }
    });
  }

  async function waitForPublish(pid: string, onTick?: (s: string) => void): Promise<string> {
    const deadline = Date.now() + 12 * 60 * 1000;
    while (Date.now() < deadline) {
      let s: { state: string };
      try { s = await api.publishStatus(pid); } catch { return "error"; }
      onTick?.(s.state);
      if (s.state === "done" || s.state === "error") return s.state;
      await new Promise((r) => setTimeout(r, 1500));
    }
    return "running";
  }
  async function loadProjectModel(): Promise<boolean> {
    if (!projectId) return false;
    return (await withLoading(container, "loading model", async () => {
      const mb = (n: number) => (n / 1048576).toFixed(1);
      let buffer: ArrayBuffer;
      try {
        buffer = await fetchArrayBufferWithProgress(
          api.url(`/projects/${projectId}/model.frag`), { headers: api.authHeaders() },
          (loaded, total) => setLoadingLabel(container,
            `downloading model ${Math.round(loaded / total * 100)}% (${mb(loaded)}/${mb(total)} MB)`));
      } catch { return false; }                 // 404 / no published model yet — fall through to no-model
      // A metadata-only project (property index uploaded, geometry never published) has no .frag, so the
      // request 404s above. Guard the degenerate variants too: an empty body, or a non-.frag payload
      // (e.g. a proxy / SPA host that rewrites a 404 into a 200 HTML page) would otherwise reach the
      // Fragments worker, which can *hang* — not reject — on input it can't parse, leaving the
      // "loading model" overlay up forever. Fail open to the same graceful no-model state a brand-new
      // project already takes.
      if (buffer.byteLength === 0) return false;
      await loader.disposeAll();
      modelLabels.clear();
      const id = `project-${projectId}`;
      modelLabels.set(id, ctx.projectName || "project");
      setLoadingLabel(container, "preparing geometry…");
      try {
        await loader.loadFragments(buffer, id);
      } catch { modelLabels.delete(id); return false; }   // corrupt / non-.frag bytes — fall through
      refreshFederation();
      await fitToModels();
      // COLLAB-1: we now hold the latest published model — sync the known version + clear any reload
      // banner, so this client's own publish never re-nags us to reload.
      await collab.resync();
      // E7: tell the paper views (Drawings workspace plans + schedules) the model changed — an open
      // sheet re-renders itself against the new geometry.
      window.dispatchEvent(new CustomEvent("aec:model-published"));
      // PROFORMA-LIVE: the finance numbers follow the model — after every (re)load, surface the
      // takeoff-priced cost + budget delta in the status line (server-cached per version; best-effort)
      if (projectId) {
        void api.proformaLive(projectId).then((pl) => {
          const money = (n: number) => `$${Math.round(n).toLocaleString()}`;
          const delta = pl.delta_vs_budget != null
            ? ` · ${pl.delta_vs_budget >= 0 ? "▲" : "▼"} ${money(Math.abs(pl.delta_vs_budget))} vs budget` : "";
          setStatus(`model cost ${money(pl.est_construction_cost)} · GFA ${pl.gfa_m2} m²${delta}`);
        }).catch(() => { /* no source IFC / offline — the readout is optional */ });
      }
      return true;
    })) ?? false;
  }
  function screenToGround(e: MouseEvent): THREE.Vector3 | null {
    const dom = viewer.world.renderer!.three.domElement;
    const r = dom.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    groundRay.setFromCamera(ndc, viewer.world.camera.three);
    const pt = new THREE.Vector3();
    return groundRay.ray.intersectPlane(groundPlane, pt) ? pt : null;
  }
  // ---- settings application + coordinate readout ---------------------------
  const UNIT_FACTOR: Record<string, number> = { m: 1, cm: 100, mm: 1000, ft: 3.28084 };
  const BG: Record<string, number | null> = { dark: 0x1e1f22, light: 0xf0f1f3, none: null };
  const ACT = CameraControls.ACTION;
  function applySettings() {
    const settings = ctx.getSettings();
    viewer.grid.visible = settings.grid;
    void viewer.world.camera.projection.set(settings.projection);
    const bg = BG[settings.background];
    viewer.world.scene.three.background = bg === null ? null : new THREE.Color(bg);
    const c = viewer.world.camera.controls;
    c.dollyToCursor = settings.zoomCursor;
    if (settings.nav === "orbit") { c.mouseButtons.left = ACT.ROTATE; c.mouseButtons.right = ACT.TRUCK; c.mouseButtons.wheel = ACT.DOLLY; }
    else if (settings.nav === "pan") { c.mouseButtons.left = ACT.TRUCK; c.mouseButtons.right = ACT.ROTATE; c.mouseButtons.wheel = ACT.DOLLY; }
    else { c.mouseButtons.left = ACT.ROTATE; c.mouseButtons.middle = ACT.TRUCK; c.mouseButtons.wheel = ACT.ZOOM; }
    section.enabled = settings.section;
    showCoords(lastPoint);
    void loader.fragments.core.update(true);
  }
  function showCoords(p: THREE.Vector3 | null) {
    const el = document.getElementById("sb-coords"); if (!el) return;
    if (!p) { el.textContent = "—"; return; }
    const settings = ctx.getSettings();
    const f = UNIT_FACTOR[settings.units] ?? 1, u = settings.units, d = u === "mm" ? 0 : 2;
    el.textContent = `E ${(p.x * f).toFixed(d)} · N ${(-p.z * f).toFixed(d)} · Z ${(p.y * f).toFixed(d)} ${u}`;
  }

  // ---- camera fit ----------------------------------------------------------
  let fitPending = false;   // set when a fit was skipped because the viewport was hidden (0×0)
  async function fitToModels() {
    const box = new THREE.Box3();
    viewer.world.scene.three.traverse((o) => {
      const m = o as THREE.Mesh & THREE.Points;
      if (m.isMesh || m.isPoints) box.expandByObject(o);   // include reference point clouds, not just meshes
    });
    if (box.isEmpty()) return;
    // Defer when the viewport is hidden (0×0): fitting then divides by a zero aspect ratio and leaves
    // the camera at NaN, so the model is broken once the Model workspace is shown. onModelShown() runs
    // the pending fit once the container has real dimensions.
    const w = viewer.container.clientWidth, h = viewer.container.clientHeight;
    if (!w || !h) { fitPending = true; return; }   // hidden viewport → defer (fit would divide by 0 aspect)
    fitPending = false;
    const cam = viewer.world.camera.three as THREE.PerspectiveCamera;
    // OBC updates the camera aspect via an async ResizeObserver, so right after a workspace becomes
    // visible `cam.aspect` can still be 0/0 = NaN — and fitToSphere then bakes NaN into the position.
    // Force a valid aspect synchronously before fitting.
    viewer.world.renderer?.resize();
    if (cam.isPerspectiveCamera) { cam.aspect = w / h; cam.updateProjectionMatrix(); }
    // If the camera is already NaN (e.g. born while the container was hidden), camera-controls can't
    // recover via setLookAt alone — hard-reset the THREE camera object first, then re-seat the controls.
    if (Number.isNaN(cam.position.x)) {
      cam.position.set(12, 8, 12); cam.up.set(0, 1, 0); cam.quaternion.set(0, 0, 0, 1); cam.updateMatrixWorld(true);
      await viewer.world.camera.controls.setLookAt(12, 8, 12, 0, 0, 0, false);
    }
    if (envTools.isRenderOn()) renderMode(viewer.world, true);   // newly loaded meshes need cast/receive flags set
    // Animate only when the tab is VISIBLE: camera-controls resolves an animated transition from the
    // rAF-driven update loop, and a hidden tab throttles rAF to zero — the fit promise then never
    // settles and the "preparing geometry…" loading overlay hangs forever (hit by any user who switches
    // tabs mid-load, and by headless/embedded panes). Hidden → instant fit, no rAF needed.
    await viewer.world.camera.controls.fitToSphere(box.getBoundingSphere(new THREE.Sphere()), !document.hidden);
    await loader.fragments.core.update(true);
  }
  async function fitToItems(map: ModelIdMap) {
    const boxes = await loader.fragments.getBBoxes(map);
    const box = new THREE.Box3();
    for (const b of boxes) box.union(b);
    if (box.isEmpty()) return;
    await viewer.world.camera.controls.fitToSphere(box.getBoundingSphere(new THREE.Sphere()), !document.hidden);
    await loader.fragments.core.update(true);
  }

  // ---- P5 edit-in-place: drag-to-move gizmo --------------------------------
  function ensureGizmo(): TransformGizmo {
    if (gizmo) return gizmo;
    const g = new TransformGizmo(
      viewer.world.camera.three,
      viewer.world.renderer!.three.domElement,
      viewer.world.scene.three,
      (enabled) => { viewer.world.camera.controls.enabled = enabled; },
    );
    g.onDrag = (d) => setStatus(`move  ΔE ${d.dx.toFixed(2)} · ΔN ${d.dy.toFixed(2)} · ΔZ ${d.dz.toFixed(2)} m`);
    g.onCommit = async (d) => {
      const guid = selectedGuid;
      if (!guid || !projectId) return;
      await authorAndReload("move_element", { guid, dx: d.dx, dy: d.dy, dz: d.dz }, "move");
      if (editInPlace && selectedGuid === guid) await selectByGuid(guid);   // re-attach on the moved element
    };
    gizmo = g;
    return g;
  }
  /** Attach the move gizmo to a selection's world bounding box (edit-in-place mode). */
  async function attachGizmo(map: ModelIdMap) {
    const boxes = await loader.fragments.getBBoxes(map);
    const box = new THREE.Box3();
    for (const b of boxes) box.union(b);
    if (box.isEmpty()) return;
    const g = ensureGizmo();
    g.setSnap(ctx.getSettings().snap);
    g.attach(box);
  }

  // ---- rail panels ---------------------------------------------------------
  // The unified discipline tree (colors + IFC-class→discipline map), fetched once. `colorMode` drives
  // whether the IFC-classes panel + model paint by raw class (hashed hue) or by discipline (tree color).
  let discTree: DisciplineTree | null = null;
  let colorMode: "class" | "discipline" = "class";

  /** Discipline code for an IFC class via the served tree (falls back to the class itself). */
  function disciplineOfClass(cls: string): string | null {
    return discTree?.ifc_class_discipline[cls] ?? null;
  }

  async function buildPanels() {
    if (!projectId) return;
    const elements: ElementProps[] = await api.elements(projectId, { limit: 5000 });
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
    treePanel.appendChild(buildTree(elements, (guid) => selectByGuid(guid, false)));

    const meta = await api.meta(projectId);
    discTree ??= await api.disciplineTree().catch(() => null);
    // hand the served IFC-class→discipline map to the model browser so it stops re-deriving disciplines
    // from its own regex (one shared vocabulary).
    if (discTree) setDisciplineLookup(discTree.ifc_class_discipline,
      Object.fromEntries(discTree.disciplines.map((d) => [d.code, d.name])));
    const layersPanel = $("panel-layers");
    layersPanel.innerHTML = `<div class="section-title">IFC classes</div>`;

    // Color-by toggle (Class ↔ Discipline) + a one-click "paint the model" so a coordinator can flip the
    // whole model to discipline colors (fire=red, plumbing=green, …) the way Navisworks/Revit do.
    const swatchRows: { cls: string; swatch: HTMLElement; ensure: () => Promise<string> }[] = [];
    const paintAll = async () => {
      for (const r of swatchRows) { r.swatch.style.background = colorFor(r.cls); await layerMgr.setColor(await r.ensure(), colorFor(r.cls)); }
    };
    if (discTree) {
      const bar = document.createElement("div"); bar.className = "layer-row"; bar.style.cssText = "gap:6px;margin-bottom:4px";
      const lbl = document.createElement("span"); lbl.className = "name"; lbl.textContent = "Color by"; lbl.style.flex = "0 0 auto";
      const sel = document.createElement("select"); sel.className = "mini-select";
      sel.innerHTML = `<option value="class">IFC class</option><option value="discipline">Discipline</option>`;
      sel.value = colorMode;
      const paint = document.createElement("button"); paint.className = "mini-btn"; paint.textContent = "Paint model";
      paint.title = "Apply the current color scheme to every element in the 3D view";
      paint.onclick = paintAll;
      sel.onchange = () => {
        colorMode = sel.value === "discipline" ? "discipline" : "class";
        for (const r of swatchRows) r.swatch.style.background = colorFor(r.cls);
        legend.style.display = colorMode === "discipline" ? "" : "none";
        buildLegend();
      };
      bar.append(lbl, sel, paint);
      layersPanel.appendChild(bar);
    }
    // discipline color legend (shown in discipline mode) — the palette, so the colors read as a system.
    const legend = document.createElement("div"); legend.className = "disc-legend";
    legend.style.display = colorMode === "discipline" ? "" : "none";
    const buildLegend = () => {
      legend.innerHTML = "";
      if (colorMode !== "discipline" || !discTree) return;
      const present = new Set(meta.facets.classes.map((c) => disciplineOfClass(c)).filter(Boolean));
      for (const d of discTree.disciplines) {
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

    // Named selection sets (Navisworks/Bluebeam Search-Set pattern) — saved queries you can isolate.
    buildSelSets(layersPanel, elements);

    await refreshIssues();
    await reloadModelPins();
  }

  /** Render the "Selection sets" block into the Layers panel: saved queries → isolate. */
  function buildSelSets(host: HTMLElement, elements: ElementProps[]) {
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

  async function reloadModelPins() {
    if (!projectId) return;
    await pins.load(projectId);
    await pins.loadModulePins(projectId, async (pin) => {
      if (pin.element_guids?.[0]) await selectByGuid(pin.element_guids[0], true);
      setStatus(`${pin.ref} · ${pin.module_name} · ${pin.status}`);
    });
  }

  /** Federation list: every loaded model with a visibility toggle + remove. Repopulates the
   *  #fed-models container (if the Tools panel is built); models load additively via Open ▾. */
  function refreshFederation() {
    const host = document.getElementById("fed-models");
    if (!host) return;
    host.innerHTML = "";
    const ids = [...loader.fragments.list.keys()];
    if (!ids.length && !referenceModels.size) {
      host.innerHTML = `<div class="empty-state">No models loaded<span class="es-hint">Use Open ▾ to load an IFC, .frag, or a mesh / point cloud.</span></div>`;
      return;
    }
    for (const id of ids) {
      const model = loader.fragments.list.get(id) as { object: { visible: boolean } } | undefined;
      if (!model) continue;
      const row = document.createElement("div"); row.className = "layer-row";
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = model.object.visible !== false;
      cb.title = "Toggle visibility";
      cb.onchange = () => { model.object.visible = cb.checked; void loader.fragments.core.update(true); };
      const name = document.createElement("span"); name.className = "name"; name.textContent = modelLabels.get(id) || id;
      const rm = document.createElement("button"); rm.className = "tool-btn"; rm.textContent = "✕"; rm.title = "Remove model";
      rm.onclick = async () => {
        await loader.fragments.core.disposeModel(id); modelLabels.delete(id);
        await loader.fragments.core.update(true); refreshFederation();
      };
      row.append(cb, name, rm); host.appendChild(row);
    }
    // view-only reference overlays (meshes / point clouds)
    if (referenceModels.size) {
      const hdr = document.createElement("div"); hdr.className = "section-title"; hdr.textContent = "Reference models";
      host.appendChild(hdr);
      for (const [id, ref] of referenceModels) {
        const row = document.createElement("div"); row.className = "layer-row";
        const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = ref.object.visible !== false;
        cb.title = "Toggle visibility";
        cb.onchange = () => { ref.object.visible = cb.checked; void loader.fragments.core.update(true); };
        const name = document.createElement("span"); name.className = "name"; name.textContent = ref.label;
        const rm = document.createElement("button"); rm.className = "tool-btn"; rm.textContent = "✕"; rm.title = "Remove model";
        rm.onclick = () => { disposeReference(id); refreshFederation(); void loader.fragments.core.update(true); };
        const gear = document.createElement("button"); gear.className = "tool-btn"; gear.textContent = "⛭"; gear.title = "Align / transform";
        const panel = transformPanel(ref.object);
        gear.onclick = () => { panel.style.display = panel.style.display === "none" ? "block" : "none"; };
        row.append(cb, name, gear, rm); host.appendChild(row); host.appendChild(panel);
      }
    }
  }

  /** Per-model alignment controls (Navisworks-style): position offset, Z-up flip, uniform scale,
   *  move-to-picked-point and reset — applied directly to the reference object's transform. */
  function transformPanel(obj: THREE.Object3D): HTMLElement {
    const panel = document.createElement("div");
    panel.style.cssText = "display:none;padding:4px 0 8px 20px";
    const inputs: (() => void)[] = [];
    const refresh = () => { obj.updateMatrixWorld(true); void loader.fragments.core.update(true); };
    const numRow = (label: string, get: () => number, set: (v: number) => void) => {
      const r = document.createElement("div"); r.className = "layer-row";
      const l = document.createElement("span"); l.className = "name"; l.textContent = label;
      const i = document.createElement("input"); i.type = "number"; i.step = "0.5"; i.style.width = "88px";
      const sync = () => { i.value = String(+get().toFixed(3)); };
      sync(); inputs.push(sync);
      i.oninput = () => { set(+i.value || 0); refresh(); };
      r.append(l, i); panel.appendChild(r);
    };
    numRow("X", () => obj.position.x, (v) => { obj.position.x = v; });
    numRow("Y", () => obj.position.y, (v) => { obj.position.y = v; });
    numRow("Z", () => obj.position.z, (v) => { obj.position.z = v; });
    numRow("Scale", () => obj.scale.x, (v) => obj.scale.setScalar(v || 1));
    const zr = document.createElement("div"); zr.className = "layer-row";
    const zl = document.createElement("span"); zl.className = "name"; zl.textContent = "Z-up → Y-up";
    const zc = document.createElement("input"); zc.type = "checkbox";
    zc.checked = Math.abs(obj.rotation.x + Math.PI / 2) < 0.01;
    zc.onchange = () => { obj.rotation.x = zc.checked ? -Math.PI / 2 : 0; refresh(); };
    zr.append(zl, zc); panel.appendChild(zr);
    const btns = document.createElement("div"); btns.style.cssText = "display:flex;gap:6px;margin-top:4px";
    const move = document.createElement("button"); move.className = "tool-btn"; move.textContent = "Move to point";
    move.title = "Translate so the model's centre sits on the last picked point";
    move.onclick = () => {
      if (!lastPoint) { setStatus("click a point in the scene first"); return; }
      const c = new THREE.Box3().setFromObject(obj).getCenter(new THREE.Vector3());
      obj.position.add(lastPoint.clone().sub(c)); refresh(); inputs.forEach((f) => f());
    };
    const reset = document.createElement("button"); reset.className = "tool-btn"; reset.textContent = "Reset";
    reset.onclick = () => {
      obj.position.set(0, 0, 0); obj.rotation.set(0, 0, 0); obj.scale.setScalar(1);
      zc.checked = false; refresh(); inputs.forEach((f) => f());
    };
    btns.append(move, reset); panel.appendChild(btns);
    return panel;
  }

  /** Remove a reference overlay from the scene and free its GPU buffers. */
  function disposeReference(id: string) {
    const ref = referenceModels.get(id);
    if (!ref) return;
    viewer.world.scene.three.remove(ref.object);
    ref.object.traverse((o) => {
      const m = o as THREE.Mesh & THREE.Points;
      m.geometry?.dispose?.();
      const mat = (m as { material?: THREE.Material | THREE.Material[] }).material;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose?.();
    });
    ref.dispose?.();                 // splat overlays own a sort worker + GPU buffers to free
    referenceModels.delete(id);
  }

  // Which tool sections matter most per persona — primary ones sit on top, expanded; the rest
  // fold under a "More tools" divider, collapsed. `all` (no entry) keeps everything primary.
  // The model rail keeps only model-native tools. Cost / schedule / drawings / energy were removed —
  // they duplicate the Construction, Drawings, and Design workspaces (deep-linked below instead).
  // Ordered by the modeler's lifecycle (Build → Analyze/Coordinate → Document) — the UX-1 task ribbon.
  const ALL_TOOLS = ["authoring", "qa", "exports"];
  const TOOLS_BY_PERSONA: Record<string, string[]> = {
    gc: ["qa", "exports"],
    developer: ["exports"],
    architect: ["authoring", "exports"],
    engineer: ["qa", "authoring"],
  };
  const toolBtn2 = (label: string, onClick: () => void) => {
    const b = document.createElement("button");
    b.className = "tool-btn"; b.textContent = label;
    b.style.cssText = "display:block;margin:4px 0;width:100%;text-align:left";
    b.onclick = onClick;
    return b;
  };

  // PERF-4: the UX-2 guide-line cursor tracker lives at this (persistent) scope, so its single
  // container `pointermove` listener is installed ONCE — buildToolsPanel re-runs on every persona
  // switch, which previously stacked a new listener (and leaked its closure) on each rebuild.
  let annotGuide: { grp: THREE.Group; line: THREE.Line } | null = null;
  let guideWired = false;

  async function buildToolsPanel() {
    const panel = $("panel-tools");
    panel.innerHTML = "";
    const intro = document.createElement("div");
    intro.className = "meta"; intro.style.cssText = "margin:2px 2px 6px;font-size:11px;line-height:1.4";
    intro.textContent = "Tools grouped by the modeling lifecycle — Build · Analyze & Coordinate · Document · Data.";
    panel.appendChild(intro);
    const goWorkspace = (key: string) => window.dispatchEvent(new CustomEvent("aec:workspace", { detail: key }));
    // Cost / schedule / drawings / energy moved OUT of the model rail — they own their workspaces.
    // Leave one row of deep-links so they're a click away without cluttering the modeling surface.
    const links = document.createElement("div");
    links.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;margin:0 2px 8px";
    for (const [label, ws] of [["💰 Cost", "construction"], ["📅 Schedule", "construction"],
                               ["📐 Drawings", "drawings"], ["⚡ Energy", "design"]] as const) {
      const a = document.createElement("button"); a.className = "tool-btn"; a.textContent = label + " →";
      a.style.cssText = "font-size:10.5px;padding:2px 7px"; a.title = `Open the ${ws} workspace`;
      a.onclick = () => goWorkspace(ws); links.appendChild(a);
    }
    panel.appendChild(links);

    // UX-1 (full ribbon merge): the sections are PHYSICALLY regrouped by lifecycle phase — see
    // regroupByPhase() below, which reorders the DOM into Build → Analyze & Coordinate → Document →
    // Data with a phase header over each cluster. The ribbon filters by each group's declared
    // data-phase (set once at section() creation), never by parsing titles at runtime. Four real
    // phases: the old separate Analyze / Coordinate tabs both showed the same single section.
    const RIBBON_KEY = "tools-ribbon";
    const PHASES = ["All", "Build", "Analyze & Coordinate", "Document", "Data"];
    const ribbon = document.createElement("div");
    ribbon.className = "tools-ribbon";
    ribbon.style.cssText = "display:flex;flex-wrap:wrap;gap:3px;margin:0 2px 8px";
    const applyPhase = (name: string) => {
      if (!PHASES.includes(name)) name = "All";        // migrates stale saved tabs (e.g. "Coordinate")
      for (const g of panel.querySelectorAll<HTMLElement>(".tool-group")) {
        g.style.display = name === "All" || g.dataset.phase === name ? "" : "none";
      }
      for (const h of panel.querySelectorAll<HTMLElement>(".tools-phase-head")) {
        h.style.display = name === "All" ? "" : "none"; // headers are redundant on a filtered tab
      }
      for (const b of ribbon.querySelectorAll<HTMLElement>("button")) b.classList.toggle("on", b.dataset.phase === name);
    };
    for (const name of PHASES) {
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = name; b.dataset.phase = name;
      b.style.cssText = "font-size:10.5px;padding:2px 9px";
      b.onclick = () => { localStorage.setItem(RIBBON_KEY, name); applyPhase(name); };
      ribbon.appendChild(b);
    }
    panel.appendChild(ribbon);
    /** Physically reorder the accreted sections into phase clusters (primary tools before "more"
     *  tools inside each), with a header row per phase. Runs once after every section is built. */
    const regroupByPhase = () => {
      for (const phase of PHASES.slice(1)) {
        const groups = [...panel.querySelectorAll<HTMLElement>(`.tool-group[data-phase="${CSS.escape(phase)}"]`)];
        if (!groups.length) continue;
        const head = document.createElement("div");
        head.className = "tools-phase-head meta";
        head.style.cssText = "margin:10px 2px 2px;font-size:10px;letter-spacing:.08em;text-transform:uppercase;opacity:.75";
        head.textContent = phase;
        panel.appendChild(head);
        groups.sort((a, b2) => Number(a.dataset.secondary === "1") - Number(b2.dataset.secondary === "1"));
        for (const g of groups) panel.appendChild(g);   // appendChild MOVES the existing node
      }
    };

    // model metadata gates IFC-only tools (drawings, QA, energy, authoring, exports)
    let hasIfc = false;
    if (projectId) { try { hasIfc = !!(await api.project(projectId)).has_source_ifc; } catch { /* offline */ } }
    const pid = projectId as string;   // tool builders below only run inside project-gated sections

    const persona = localStorage.getItem("persona") || "all";
    const primary = TOOLS_BY_PERSONA[persona];
    const order = primary ? [...primary, ...ALL_TOOLS.filter((t) => !primary.includes(t))] : ALL_TOOLS;

    /** Collapsible section. Returns the body to fill, or null when its precondition is unmet
     *  (in which case it renders one muted reason line and stays collapsed). */
    function section(key: string, title: string,
                     opts: { requires?: "project" | "sourceIfc"; tool?: boolean } = {}): HTMLElement | null {
      const ok = opts.requires === "project" ? !!projectId
        : opts.requires === "sourceIfc" ? (!!projectId && hasIfc) : true;
      const reason = opts.requires === "sourceIfc" ? "needs a source IFC"
        : opts.requires === "project" ? "needs a project" : "";
      const isPrimary = !opts.tool || !primary || primary.includes(key);
      const group = document.createElement("section"); group.className = "tool-group"; group.dataset.tool = key;
      // UX-1 (physical regroup): every section declares its lifecycle phase ONCE, from its title
      // prefix — the ribbon and the regroup pass key off data-phase, never runtime title parsing
      group.dataset.phase = title.startsWith("Build") ? "Build"
        : title.startsWith("Analyze") ? "Analyze & Coordinate"
          : title.startsWith("Document") ? "Document" : "Data";
      if (opts.tool && primary && !isPrimary) group.dataset.secondary = "1";
      const head = document.createElement("button"); head.type = "button"; head.className = "tool-group-head";
      head.innerHTML = `<span class="chev">▸</span><span class="t">${title}</span>`
        + (opts.tool && primary && !isPrimary ? `<span class="why">more</span>` : "")
        + (ok ? "" : `<span class="why">${reason}</span>`);
      const body = document.createElement("div"); body.className = "tool-group-body";
      group.append(head, body);
      const saved = localStorage.getItem(`tools-open:${key}`);
      const open = saved == null ? (ok && isPrimary) : saved === "1";
      group.classList.toggle("open", open);
      head.setAttribute("aria-expanded", String(open));
      head.onclick = () => {
        const o = !group.classList.contains("open");
        group.classList.toggle("open", o); head.setAttribute("aria-expanded", String(o));
        localStorage.setItem(`tools-open:${key}`, o ? "1" : "0");
      };
      panel.appendChild(group);
      if (!ok) { const n = document.createElement("div"); n.className = "meta"; n.textContent = `${reason} to use this.`; body.appendChild(n); return null; }
      return body;
    }

    // --- always-on: model setup ----------------------------------------------
    const fedBody = section("models", "Data · Models (federation)");
    if (fedBody) {
      const l = document.createElement("div"); l.id = "fed-models"; fedBody.appendChild(l); refreshFederation();
      if (projectId) fedBody.appendChild(toolBtn2("🕔 Version history", async () => {
        const h = await api.modelVersions(pid);
        showResult("Model version history", async (body) => {
          if (!h.length) { body.appendChild(resultNote("No versions yet — publish the model (Authoring) to snapshot one.")); return; }
          if (h.length >= 2) {
            const d = await api.versionDiff(pid, h[1]!.version, h[0]!.version); // safe: h.length >= 2 checked above
            body.appendChild(resultNote(`v${h[1]!.version} → v${h[0]!.version}: <b>+${d.added_count}</b> added / <b>−${d.removed_count}</b> removed`
              + (d.modified_available ? ` / <b>~${d.modified_count}</b> modified` : "") + ` · ${d.unchanged_count} unchanged`, "ok"));
            if (d.modified_count) {
              body.appendChild(resultNote("Modified elements (click to select in 3D):", ""));
              body.appendChild(kvTable(d.modified.slice(0, 40).map((m) => ({
                k: `${(m.ifc_class || "").replace("Ifc", "")} · ${m.name || m.guid.slice(0, 8)}`,
                v: m.changes.join(", "),
                onClick: () => selectByGuid(m.guid, false),
              }))));
            }
          }
          body.appendChild(kvTable(h.map((v) => ({
            k: `v${v.version}${v.note ? " (" + v.note + ")" : ""}`,
            v: `${v.element_count} elements · ${(v.created_at || "").slice(0, 10)}` }))));
        });
      }));
    }

    const ob = section("origin", "Data · Working origin (E / N / Z)");
    if (ob) {
      const inputs: Record<string, HTMLInputElement> = {};
      const cur = origin.getOrigin();
      for (const k of ["e", "n", "z"] as const) {
        const row = document.createElement("div"); row.className = "layer-row";
        const label = document.createElement("span"); label.className = "name"; label.textContent = k.toUpperCase();
        const inp = document.createElement("input"); inp.type = "number"; inp.value = String(cur[k]); inp.style.width = "110px";
        inputs[k] = inp; row.append(label, inp); ob.appendChild(row);
      }
      const fromPt = toolBtn2("Set from selected point", () => {
        if (!lastPoint) { setStatus("click a point first"); return; }
        inputs.e!.value = lastPoint.x.toFixed(3); inputs.n!.value = (-lastPoint.z).toFixed(3); inputs.z!.value = lastPoint.y.toFixed(3); // safe: inputs.{e,n,z} populated by the loop above
      });
      fromPt.style.cssText = "";
      const apply = document.createElement("button");
      apply.className = "tool-btn"; apply.textContent = "Apply origin"; apply.style.marginLeft = "6px";
      apply.onclick = async () => {
        origin.setOrigin({ e: +inputs.e!.value, n: +inputs.n!.value, z: +inputs.z!.value }); // safe: inputs.{e,n,z} populated by the loop above
        for (const [, model] of loader.fragments.list) origin.applyTo(model.object as unknown as THREE.Object3D);
        await loader.fragments.core.update(true);
        if (connected && projectId) {
          fetch(api.url(`/projects/${projectId}`), { method: "PATCH", headers: { "Content-Type": "application/json", ...api.authHeaders() }, body: JSON.stringify({ origin: origin.getOrigin() }) }).catch(() => {});
        }
        setStatus(`origin set to E${inputs.e!.value} N${inputs.n!.value} Z${inputs.z!.value}`); // safe: inputs.{e,n,z} populated by the loop above
      };
      ob.append(fromPt, apply);
    }

    // --- Draft: parameter-driven family/element authoring (editors) ----------
    const draftBody = section("draft", "Build · Draw elements", { requires: "sourceIfc" });
    if (draftBody) {
      draftHandle = installDraftPanel({
        body: draftBody,
        fetchFamilies: async () => {
          const cat = await api.familyCatalog();
          return Object.values(cat.categories).flat() as FamilyDef[];
        },
        arm: (a) => { armed = a; armPts.length = 0; },
        notify,
        canAuthor: () => !!projectId && hasIfc,
      });
    }

    // --- Grid & Levels: drafting reference frame (grid snap + active work-plane) ----------
    const glBody = section("gridlevels", "Build · Grids & levels", { requires: "sourceIfc" });
    if (glBody) {
      // CADCMD — a deterministic CAD command line (instant, offline) over the same recipes. AutoCAD
      // grammar + aliases; up-arrow history; spacebar on an empty line repeats the last command.
      const cadWrap = document.createElement("div"); cadWrap.style.cssText = "display:flex;gap:4px;margin-bottom:4px";
      const cadIn = document.createElement("input");
      cadIn.type = "text"; cadIn.className = "portal-filter"; cadIn.style.cssText = "flex:1;font-family:ui-monospace,monospace";
      cadIn.placeholder = "⌨ CAD command — e.g. WALL 0,0 5,0 3  ·  type HELP";
      cadIn.setAttribute("aria-label", "CAD command line");
      const cadStatus = document.createElement("div"); cadStatus.className = "meta"; cadStatus.style.cssText = "min-height:14px;margin:-2px 0 6px 2px";
      const cadHistory: string[] = []; let cadHistIdx = -1; let cadLast = "";
      const runCad = async () => {
        const line = cadIn.value.trim();
        if (!line) { if (cadLast) { cadIn.value = cadLast; } return; }   // empty Enter = recall last (space handled below)
        const parsed = parseCadCommand(line);
        if (parsed.kind === "info") { cadStatus.textContent = parsed.text; return; }
        if (parsed.kind === "error") { cadStatus.innerHTML = `<span style="color:var(--status-warn)">${escapeHtml(parsed.text)}</span>`; return; }
        cadHistory.push(line); cadHistIdx = cadHistory.length; cadLast = line;
        cadIn.value = ""; cadStatus.textContent = `applying ${parsed.echo}…`;
        await withLoading(container, `authoring ${parsed.echo} + republishing`, async () => {
          try {
            for (let i = 0; i < parsed.steps.length; i++) {
              const s = parsed.steps[i]!;
              await api.editIfc(projectId!, s.recipe, s.params, i === parsed.steps.length - 1);
            }
            const state = await waitForPublish(projectId!);
            if (state === "done") { const shown = await loadProjectModel(); draftProxies.clear(); await reloadModelPins(); cadStatus.textContent = `✓ ${parsed.echo}${shown ? " — shown" : ""}`; notify(`${parsed.echo} applied`, "success"); }
            else { cadStatus.textContent = `authored — publish ${state}`; notify(`authored — publish ${state}`, state === "error" ? "error" : "info"); }
          } catch (err) { cadStatus.innerHTML = `<span style="color:var(--status-crit)">${escapeHtml((err as Error).message)}</span>`; notify(`${parsed.echo} failed: ${(err as Error).message}`, "error"); }
        });
      };
      cadIn.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); void runCad(); }
        else if (e.key === " " && cadIn.value === "" && cadLast) { e.preventDefault(); cadIn.value = cadLast; }  // spacebar repeats last
        else if (e.key === "ArrowUp") { e.preventDefault(); if (cadHistory.length) { cadHistIdx = Math.max(0, cadHistIdx - 1); cadIn.value = cadHistory[cadHistIdx] || ""; } }
        else if (e.key === "ArrowDown") { e.preventDefault(); if (cadHistIdx < cadHistory.length - 1) { cadHistIdx++; cadIn.value = cadHistory[cadHistIdx] || ""; } else { cadHistIdx = cadHistory.length; cadIn.value = ""; } }
        else if (e.key === "Escape") { cadIn.value = ""; cadStatus.textContent = ""; }
      });
      const cadGo = document.createElement("button"); cadGo.className = "mini-btn"; cadGo.textContent = "↵"; cadGo.title = "Run CAD command"; cadGo.onclick = () => void runCad();
      cadWrap.append(cadIn, cadGo);
      glBody.appendChild(cadWrap); glBody.appendChild(cadStatus);

      // Natural-language command bar — the low-barrier "type what you want" authoring surface.
      const cmdWrap = document.createElement("div"); cmdWrap.className = "nl-cmd";
      cmdWrap.style.cssText = "display:flex;gap:4px;margin-bottom:6px";
      const cmdIn = document.createElement("input");
      cmdIn.type = "text"; cmdIn.className = "portal-filter"; cmdIn.style.flex = "1";
      cmdIn.placeholder = "✨ Type what to build — e.g. add a 3m wall from 0,0 to 5,0";
      cmdIn.setAttribute("aria-label", "Natural-language authoring command");
      const cmdGo = document.createElement("button"); cmdGo.className = "mini-btn"; cmdGo.textContent = "Go";
      const runCmd = async () => {
        const text = cmdIn.value.trim(); if (!text) return;
        let res;
        try {
          res = await api.aiAuthor(pid, text, {
            selected_guids: selectedGuid ? [selectedGuid] : undefined,
            active_storey: activeStorey || undefined });
        } catch (e) { notify(`command failed: ${(e as Error).message}`, "error"); return; }
        if (res.needs_clarification) { notify(res.needs_clarification, "info"); return; }
        showResult("Interpreted command", (body) => {
          body.appendChild(resultNote(`“${text}” → ${res.source === "claude" ? "planned by AI" : "matched"} `
            + `<b>${res.plan.length}</b> step${res.plan.length === 1 ? "" : "s"}`, ""));
          // S3: a multi-step plan (e.g. a room = 4 walls) applies in ONE republish — chain each edit
          // with publish deferred to the last, so the model reconverts once instead of per step.
          if (res.plan.length > 1 && !res.plan.some((s) => s.destructive)) {
            const applyAll = toolBtn2(`✓ Apply all ${res.plan.length} steps`, () =>
              withLoading(container, `authoring ${res.plan.length} steps + republishing`, async () => {
                cmdIn.value = "";
                let applied = 0;
                try {
                  for (let i = 0; i < res.plan.length; i++) {
                    const s = res.plan[i]; if (!s) continue;
                    await api.editIfc(projectId!, s.recipe, s.params, i === res.plan.length - 1);
                    applied++;
                  }
                  const state = await waitForPublish(projectId!);
                  if (state === "done") { const shown = await loadProjectModel(); draftProxies.clear(); notify(`${res.plan.length} steps applied${shown ? " — shown" : ""}`, "success"); }
                  else notify(`steps authored — publish ${state}`, state === "error" ? "error" : "info");
                  await reloadModelPins();
                } catch (err) {
                  // a step failed mid-chain — earlier edits already advanced the source IFC but their
                  // republish (deferred to the last step) never fired. Republish now so they're not
                  // stranded, and report how far we got.
                  if (applied > 0) { try { await api.publish(projectId!); await waitForPublish(projectId!); await loadProjectModel(); await reloadModelPins(); } catch { /* leave as-is */ } }
                  draftProxies.clear();
                  notify(`apply-all stopped after ${applied}/${res.plan.length} step(s): ${(err as Error).message}`, "error");
                }
              }));
            applyAll.title = "Apply every step of the plan in order, republishing the model once at the end.";
            body.appendChild(applyAll);
          }
          for (const step of res.plan) {
            body.appendChild(kvTable([{ k: step.recipe, v: step.summary || "", strong: true }]));
            const apply = toolBtn2(step.destructive ? `⚠ Apply (destructive): ${step.recipe}` : `✓ Apply: ${step.recipe}`, async () => {
              if (step.destructive && !(await confirmModal(`This will ${step.recipe.replace("_", " ")}. Continue?`, "", "Apply", true))) return;
              // E8: surface guardrail warnings (e.g. an implausibly large size) before committing
              try {
                const pc = await api.editPrecheck(pid, step.recipe, step.params);
                if (!pc.ok) { notify(pc.errors.join("; "), "error"); return; }
                if (pc.warnings.length && !(await confirmModal(pc.warnings.join("; "), "Apply anyway?", "Apply", false))) return;
              } catch { /* precheck unavailable — the server gate still enforces on apply */ }
              cmdIn.value = "";
              await authorAndReload(step.recipe, step.params, step.summary || step.recipe);
            });
            body.appendChild(apply);
          }
        });
      };
      cmdGo.onclick = () => void runCmd();
      cmdIn.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); void runCmd(); } };
      cmdWrap.append(cmdIn, cmdGo);
      glBody.appendChild(cmdWrap);

      const status = document.createElement("div"); status.className = "meta";
      status.textContent = "Load the grid + levels to snap placement and set the active work-plane.";
      const levelSel = document.createElement("select"); levelSel.className = "portal-filter";
      levelSel.style.cssText = "width:100%;margin:4px 0"; levelSel.setAttribute("aria-label", "Active level");
      const applyLevel = () => {
        const opt = levelSel.selectedOptions[0]; if (!opt) return;
        activeStorey = opt.dataset.name || null; activeStoreyZ = Number(opt.dataset.z || 0);
        groundPlane.constant = -activeStoreyZ;                       // draft on the active level's plane
        if (gridOverlay.data) gridOverlay.set(gridOverlay.data, activeStoreyZ);
        setStatus(`active level: ${activeStorey ?? "—"} (Z ${activeStoreyZ.toFixed(2)} m)`);
      };
      levelSel.onchange = applyLevel;
      const load = toolBtn2("⊞ Load grid + levels", async () => {
        try {
          const g = await api.modelGrid(pid);
          gridOverlay.set(g.grid, activeStoreyZ); gridOverlay.visible = true;
          levelSel.innerHTML = "";
          for (const lv of g.levels) {
            const o = document.createElement("option");
            o.textContent = `${lv.name ?? "Level"} (${lv.elevation.toFixed(2)} m)`;
            o.dataset.name = lv.name ?? ""; o.dataset.z = String(lv.elevation); levelSel.appendChild(o);
          }
          if (g.levels.length) applyLevel();
          status.textContent = `grid: ${g.grid.source} · ${g.grid.axes.length} axes · `
            + `${g.grid.intersections.length} snap points · ${g.levels.length} level(s)`;
        } catch (e) { status.textContent = `failed: ${(e as Error).message}`; }
      });
      const toggle = toolBtn2("◻ Toggle grid overlay", () => {
        gridOverlay.visible = !gridOverlay.visible; setStatus(`grid ${gridOverlay.visible ? "shown" : "hidden"}`);
      });
      const addLvl = toolBtn2("➕ Add level", async () => {
        const name = await askText("Add level", { label: "Level name", value: "Level 2" }); if (!name) return;
        const elevS = await askText("Add level", { label: "Elevation (metres)", value: "3.0" });
        const elev = Number(elevS); await authorAndReload("add_storey",
          { name, elevation: Number.isFinite(elev) ? elev : 0 }, `level ${name}`);
      });
      // Author a room/space schedule — IfcSpace rooms gridded over each floor's footprint (add_spaces).
      // Rooms are core BIM (drive the space schedule, COBie, gbXML, area take-offs) and had no UI.
      const addRooms = toolBtn2("➕ Add rooms / spaces", async () => {
        const nS = await askText("Add rooms", { label: "Rooms per floor", value: "4" }); if (!nS) return;
        const hS = await askText("Add rooms", { label: "Ceiling height (metres)", value: "3.0" });
        const rooms = Math.max(1, Math.round(Number(nS) || 4));
        const ch = Number(hS); await authorAndReload("add_spaces",
          { rooms_per_storey: rooms, ceiling_height: Number.isFinite(ch) && ch > 0 ? ch : 3.0 }, `${rooms} rooms/floor`);
      });
      addRooms.title = "Author IfcSpace rooms gridded over each floor — the space schedule feeds COBie, gbXML, and area take-offs";

      // W9-6 generative fit-out: grid furniture into every space's footprint
      const furnish = toolBtn2("🪑 Furnish spaces", async () => {
        const item = await askText("Furnish spaces", { label: "Furniture (desk / table / bed / sofa)", value: "desk" }); if (!item) return;
        const nS = await askText("Furnish spaces", { label: "Per room (0 = fill the footprint)", value: "0" });
        const per = Math.max(0, Math.round(Number(nS) || 0));
        await authorAndReload("furnish_spaces", { item: item.trim().toLowerCase(), per_room: per }, `furnish (${item.trim()})`);
      });
      furnish.title = "Generative fit-out — grid IfcFurniture into each room's footprint with clearances (real IFC, feeds QTO/BOM)";

      // Manage levels: rename + set-elevation per storey (GUID-stable recipes). Inline editor.
      const levelsMgr = document.createElement("div");
      levelsMgr.className = "levels-mgr"; levelsMgr.hidden = true;
      const renderLevelsMgr = async () => {
        levelsMgr.innerHTML = `<div class="meta">Loading levels…</div>`;
        let storeys: { name: string | null; elevation: number; guid: string }[];
        try { storeys = await api.drawingStoreys(pid); }
        catch { levelsMgr.innerHTML = `<div class="meta">No levels (needs a source IFC).</div>`; return; }
        storeys.sort((a, b) => a.elevation - b.elevation);
        levelsMgr.innerHTML = "";
        if (!storeys.length) { levelsMgr.innerHTML = `<div class="meta">No levels yet — add one above.</div>`; return; }
        for (const s of storeys) {
          const row = document.createElement("div"); row.className = "level-row";
          const nameI = document.createElement("input");
          nameI.type = "text"; nameI.value = s.name ?? ""; nameI.className = "level-name";
          nameI.setAttribute("aria-label", "Level name");
          const elevI = document.createElement("input");
          elevI.type = "number"; elevI.step = "0.1"; elevI.value = s.elevation.toFixed(3); elevI.className = "level-elev";
          elevI.setAttribute("aria-label", "Elevation in metres");
          const unit = document.createElement("span"); unit.className = "meta"; unit.textContent = "m";
          const save = document.createElement("button");
          save.className = "mini-btn"; save.textContent = "Save"; save.title = "Apply rename / elevation change";
          save.onclick = async () => {
            const newName = nameI.value.trim();
            const newElev = Number(elevI.value);
            const renamed = !!newName && newName !== (s.name ?? "");
            const moved = Number.isFinite(newElev) && Math.abs(newElev - s.elevation) > 1e-6;
            if (!renamed && !moved) { notify("no change to this level", "info"); return; }
            if (renamed) await authorAndReload("rename_storey", { guid: s.guid, name: newName }, `rename level → ${newName}`);
            if (moved) await authorAndReload("set_storey_elevation", { guid: s.guid, elevation: newElev }, `set ${newName || "level"} to ${newElev} m`);
            await renderLevelsMgr();   // refresh baselines after republish
          };
          row.append(nameI, elevI, unit, save);
          levelsMgr.appendChild(row);
        }
      };
      const manage = toolBtn2("✎ Manage levels", async () => {
        if (levelsMgr.hidden) { await renderLevelsMgr(); levelsMgr.hidden = false; }
        else levelsMgr.hidden = true;
      });
      manage.title = "Rename levels and set their elevation — edits the IFC by storey GUID";

      // W10-1 first-class type/family system: browse types, create a custom type, edit a type's size
      // (propagates to every placed occurrence at once — shared RepresentationMap, GUID-stable), and
      // give it a material layer set. The Revit "type properties" surface, IFC-native.
      const parseDims = (s: string): [number, number, number] | null => {
        const p = s.split(/[,x×]/).map((v) => Number(v.trim()));
        return p.length === 3 && p.every((n) => Number.isFinite(n) && n > 0) ? [p[0]!, p[1]!, p[2]!] : null;
      };
      const shortClass = (c: string) => c.replace(/^Ifc/, "").replace(/Type$/, "");
      const openTypeInspector = async (guid: string, reopen: () => void) => {
        let det;
        try { det = await api.typeDetail(pid, guid); }
        catch (e) { notify(`type load failed: ${(e as Error).message}`, "error"); return; }
        showResult(`Type — ${det.name}`, (body) => {
          const back = toolBtn2("‹ All types", reopen); back.style.marginBottom = "6px"; body.appendChild(back);
          body.appendChild(kvTable([
            { k: "Class", v: shortClass(det.ifc_class), strong: true },
            { k: "Predefined", v: det.predefined || "—" },
            { k: "Size (w×d×h m)", v: det.dims ? det.dims.map((n) => n.toFixed(3)).join(" × ") : "no box geometry" },
            { k: "Placed occurrences", v: String(det.occurrence_count) },
            { k: "Material layers", v: det.materials.length
              ? det.materials.map((m) => `${m.material ?? "?"}${m.thickness != null ? ` ${(m.thickness * 1000).toFixed(0)}mm` : ""}`).join(" · ") : "—" },
          ]));
          const psetNames = Object.keys(det.psets || {});
          if (psetNames.length) {
            const rows = psetNames.flatMap((pn) =>
              Object.entries(det.psets[pn] as Record<string, unknown>).map(([k, v]) => ({ k: `${pn}.${k}`, v: String(v) })));
            body.appendChild(resultNote(`<b>Type properties</b> — inherited by all ${det.occurrence_count} occurrence(s).`, ""));
            body.appendChild(kvTable(rows.slice(0, 40)));
          }
          const editSize = toolBtn2("✎ Edit size (propagates to occurrences)", async () => {
            const cur = det.dims ? det.dims.map((n) => n.toFixed(3)).join(", ") : "1.0, 0.5, 0.75";
            const v = await askText("Edit type size", { label: "Width, depth, height (metres)", value: cur }); if (!v) return;
            const d = parseDims(v); if (!d) { notify("need three positive numbers, e.g. 1.8, 0.6, 0.9", "error"); return; }
            await authorAndReload("edit_type_params", { type_guid: guid, dims: d }, `resize ${det.name}`);
            await openTypeInspector(guid, reopen);
          });
          editSize.title = "Changes the type's box — every placed occurrence updates at once (GUID-stable)";
          body.appendChild(editSize);
          const mat = toolBtn2("🧱 Set material layers", async () => {
            const cur = det.materials.map((m) => `${m.material ?? "Material"}:${m.thickness ?? 0.1}`).join(", ") || "Gypsum:0.015, Steel:0.1, Gypsum:0.015";
            const v = await askText("Material layer set", { label: "name:thickness_m, … (outer → inner)", value: cur }); if (!v) return;
            const layers = v.split(",").map((seg) => { const [n, t] = seg.split(":"); return { material: (n || "Material").trim(), thickness: Number((t || "0.1").trim()) || 0.1 }; });
            if (!layers.length) return;
            await authorAndReload("assign_material_set", { type_guid: guid, layers }, `material set for ${det.name}`);
            await openTypeInspector(guid, reopen);
          });
          mat.title = "Assign an IfcMaterialLayerSet — occurrences inherit the assembly (walls/slabs/roofs)";
          body.appendChild(mat);
        });
      };
      const openTypeBrowser = async () => {
        let rows;
        try { rows = (await api.types(pid)).types; }
        catch (e) { notify(`types failed: ${(e as Error).message}`, "error"); return; }
        showResult("Family types", (body) => {
          const create = toolBtn2("＋ New type", async () => {
            const cls = await askText("New type", { label: "Type class (e.g. IfcFurnitureType, IfcWallType)", value: "IfcFurnitureType" }); if (!cls) return;
            const name = await askText("New type", { label: "Type name", value: "New Type" }); if (!name) return;
            const dimsS = await askText("New type", { label: "Size w, d, h (metres) — blank for no geometry", value: "1.0, 0.5, 0.75" });
            const dims = dimsS ? parseDims(dimsS) : null;
            await authorAndReload("create_type", { ifc_class: cls.trim(), name: name.trim(), dims }, `type ${name.trim()}`);
            await openTypeBrowser();
          });
          create.style.marginBottom = "6px"; body.appendChild(create);
          if (!rows.length) { body.appendChild(resultNote("No types yet — create one, or place a family from the library.", "")); return; }
          body.appendChild(resultNote(`<b>${rows.length}</b> type(s). Click one to inspect, resize, or set materials.`, ""));
          for (const t of rows.slice().sort((a, b) => b.occurrence_count - a.occurrence_count || a.name.localeCompare(b.name))) {
            const btn = toolBtn2(`${t.name} · ${shortClass(t.ifc_class)}${t.occurrence_count ? ` ×${t.occurrence_count}` : ""}`,
              () => openTypeInspector(t.guid, openTypeBrowser));
            if (!t.has_geometry) btn.title = "No box geometry — resize will build one";
            body.appendChild(btn);
          }
        });
      };
      const typesBtn = toolBtn2("🧱 Family types", openTypeBrowser);
      typesBtn.title = "Browse & author IFC type families (Revit-style type properties): create types, edit a "
        + "type's size (propagates to all occurrences), assign material layers — IFC-native, GUID-stable";

      // W10-3 groups / assemblies / arrays: organise placed elements. Groups/assemblies build from a
      // saved selection set (Navisworks-style); arrays duplicate the selected element on a grid.
      const openGroupsPanel = async () => {
        let existing;
        try { existing = await api.groups(pid); }
        catch (e) { notify(`groups failed: ${(e as Error).message}`, "error"); return; }
        const sets = loadSelSets(pid);
        showResult("Groups, assemblies & arrays", (body) => {
          // ── array the selected element ──
          const arr = toolBtn2(selectedGuid ? "▦ Array selected element" : "▦ Array (select an element first)", async () => {
            if (!selectedGuid) { notify("select an element to array", "error"); return; }
            const counts = await askText("Array", { label: "Columns × rows (nx, ny)", value: "3, 1" }); if (!counts) return;
            const cd = counts.split(/[,x×]/).map((v) => Math.max(1, Math.round(Number(v.trim()) || 1)));
            const pitch = await askText("Array", { label: "Pitch dx, dy (metres)", value: "1.5, 0" }); if (!pitch) return;
            const pd = pitch.split(",").map((v) => Number(v.trim()) || 0);
            await authorAndReload("array_element",
              { guid: selectedGuid, nx: cd[0] ?? 2, ny: cd[1] ?? 1, dx: pd[0] ?? 1, dy: pd[1] ?? 0 },
              `array ${(cd[0] ?? 2)}×${(cd[1] ?? 1)}`);
          });
          arr.style.marginBottom = "6px"; body.appendChild(arr);

          // ── group / assemble from a saved selection set ──
          body.appendChild(resultNote(sets.length
            ? "<b>Group or assemble a selection set</b> — a Group is a named set; an Assembly is a real part-of whole."
            : "Save a named selection set (model browser) to group or assemble it.", ""));
          for (const s of sets) {
            const row = document.createElement("div"); row.className = "level-row";
            const label = document.createElement("span"); label.className = "meta";
            label.textContent = `${s.name} · ${s.guids.length}`; label.style.flex = "1";
            const gBtn = document.createElement("button"); gBtn.className = "mini-btn"; gBtn.textContent = "Group";
            gBtn.onclick = () => authorAndReload("create_group", { name: s.name, guids: s.guids }, `group ${s.name}`);
            const aBtn = document.createElement("button"); aBtn.className = "mini-btn"; aBtn.textContent = "Assemble";
            aBtn.onclick = () => authorAndReload("create_assembly", { name: s.name, guids: s.guids }, `assembly ${s.name}`);
            row.append(label, gBtn, aBtn); body.appendChild(row);
          }

          // ── existing groups + assemblies ──
          const all = [...existing.groups.map((g) => ({ ...g, kind: "group" as const, count: g.members })),
            ...existing.assemblies.map((a) => ({ guid: a.guid, name: a.name, kind: "assembly" as const, count: a.parts }))];
          if (all.length) {
            body.appendChild(resultNote(`<b>${all.length}</b> group(s)/assembly(ies) — click to isolate members.`, ""));
            for (const it of all) {
              const b = toolBtn2(`${it.kind === "assembly" ? "▣" : "▢"} ${it.name} · ${it.count}`, async () => {
                try { const d = await api.groupDetail(pid, it.guid);
                  await layerMgr.isolateGuids(d.members.map((mm) => mm.guid));
                  notify(`${it.name}: isolated ${d.member_count} member(s)`, "success");
                } catch (e) { notify(`inspect failed: ${(e as Error).message}`, "error"); }
              });
              if (it.kind === "group") {
                b.oncontextmenu = (ev) => { ev.preventDefault();
                  void authorAndReload("ungroup", { guid: it.guid }, `ungroup ${it.name}`); };
                b.title = "Click: isolate members · right-click: ungroup";
              }
              body.appendChild(b);
            }
          }
        });
      };
      const groupsBtn = toolBtn2("🧩 Groups & arrays", openGroupsPanel);
      groupsBtn.title = "Organise placed elements — IfcGroup (named set), IfcElementAssembly (part-of whole), "
        + "and rectangular parametric arrays. Groups/assemblies build from saved selection sets; GUID-stable";

      // W10-8 element phasing: tag new/existing/demolish/temporary status (renovation/demolition modeling).
      const PHASES = [["new", "🟢 New"], ["existing", "⚪ Existing"], ["demolish", "🔴 Demolish"],
        ["temporary", "🟡 Temporary"]] as const;
      const openPhasingPanel = async () => {
        let sum;
        try { sum = await api.phasing(pid); }
        catch (e) { notify(`phasing failed: ${(e as Error).message}`, "error"); return; }
        const sets = loadSelSets(pid);
        showResult("Phasing (new / existing / demolish / temporary)", (body) => {
          body.appendChild(kvTable([
            { k: "🟢 New", v: String(sum.counts.NEW), bar: sum.total ? sum.counts.NEW / sum.total : 0 },
            { k: "⚪ Existing", v: String(sum.counts.EXISTING), bar: sum.total ? sum.counts.EXISTING / sum.total : 0 },
            { k: "🔴 Demolish", v: String(sum.counts.DEMOLISH), bar: sum.total ? sum.counts.DEMOLISH / sum.total : 0 },
            { k: "🟡 Temporary", v: String(sum.counts.TEMPORARY), bar: sum.total ? sum.counts.TEMPORARY / sum.total : 0 },
            { k: "Unphased", v: String(sum.counts.UNSET), bar: sum.total ? sum.counts.UNSET / sum.total : 0 },
          ]));
          const tag = async (phase: "new" | "existing" | "demolish" | "temporary", guids: string[], what: string) => {
            if (!guids.length) { notify("nothing to phase", "error"); return; }
            await authorAndReload("set_phase", { guids, phase }, `${what} → ${phase}`);
            await openPhasingPanel();
          };
          // tag the current selection
          body.appendChild(resultNote(selectedGuid
            ? "<b>Tag the selected element</b>" : "<b>Select an element</b>, or use a saved selection set below.", ""));
          if (selectedGuid) {
            const rowS = document.createElement("div"); rowS.className = "level-row";
            for (const [ph, lbl] of PHASES) {
              const bt = document.createElement("button"); bt.className = "mini-btn"; bt.textContent = lbl;
              bt.onclick = () => tag(ph, [selectedGuid!], "selection");
              rowS.appendChild(bt);
            }
            body.appendChild(rowS);
          }
          // tag a saved selection set
          for (const s of sets) {
            const row = document.createElement("div"); row.className = "level-row";
            const label = document.createElement("span"); label.className = "meta";
            label.textContent = `${s.name} · ${s.guids.length}`; label.style.flex = "1"; row.appendChild(label);
            for (const [ph, lbl] of PHASES) {
              const bt = document.createElement("button"); bt.className = "mini-btn"; bt.textContent = lbl.slice(0, 2);
              bt.title = `Tag "${s.name}" as ${ph}`; bt.onclick = () => tag(ph, s.guids, s.name);
              row.appendChild(bt);
            }
            body.appendChild(row);
          }
          const iso = toolBtn2("◎ Isolate a phase in 3D", async () => {
            try {
              const r = await api.colorBy(pid, "Massing_Phasing.Status", 6);
              showResult("Isolate by phase", (b2) => {
                if (!r.buckets.length) { b2.appendChild(resultNote("No phased elements yet.", "")); return; }
                for (const bk of r.buckets) {
                  b2.appendChild(toolBtn2(`◎ ${bk.label} · ${bk.count}`,
                    () => { void layerMgr.isolateGuids(bk.guids); notify(`isolated ${bk.count} · ${bk.label}`, "success"); }));
                }
                b2.appendChild(toolBtn2("Show all", () => { void layerMgr.showAll?.(); }));
              });
            } catch (e) { notify(`isolate failed: ${(e as Error).message}`, "error"); }
          });
          iso.style.marginTop = "6px"; body.appendChild(iso);
        });
      };
      const phaseBtn = toolBtn2("🕐 Phasing", openPhasingPanel);
      phaseBtn.title = "Tag elements new / existing / demolish / temporary (Massing_Phasing.Status) — the "
        + "renovation & demolition-sequencing dimension for as-built LOD-500 models. Colour by phase; GUID-stable";

      // W11 selector DSL: power-select by class / pset / material, then isolate or save as a selection set.
      const openQueryPanel = async () => {
        const q = await askText("Selector query", {
          label: "IfcOpenShell selector — e.g. IfcWall  ·  IfcWall, IfcDoor  ·  IfcWall, Pset_WallCommon.FireRating=2HR",
          value: "IfcWall, IfcColumn" });
        if (!q) return;
        let r;
        try { r = await api.queryElements(pid, q); }
        catch (e) { notify(`query failed: ${(e as Error).message}`, "error"); return; }
        showResult(`Query — ${r.count} match${r.count === 1 ? "" : "es"}`, (body) => {
          body.appendChild(resultNote(`<code>${q}</code> → <b>${r.count}</b> element(s)`
            + (r.truncated ? ` (showing ${r.elements.length})` : ""), r.count ? "ok" : "bad"));
          if (!r.elements.length) return;
          const guids = r.elements.map((e) => e.guid);
          body.appendChild(toolBtn2("◎ Isolate matches in 3D", () => {
            void layerMgr.isolateGuids(guids); notify(`isolated ${guids.length}`, "success"); }));
          body.appendChild(toolBtn2("💾 Save as selection set", async () => {
            const name = await askText("Save selection set", { label: "Set name", value: q.slice(0, 40) }); if (!name) return;
            const sets = loadSelSets(pid).filter((s) => s.name !== name);
            sets.push({ name, q, guids }); saveSelSets(pid, sets);
            notify(`saved "${name}" (${guids.length})`, "success");
          }));
          const list = document.createElement("div"); list.className = "meta"; list.style.marginTop = "4px";
          list.textContent = r.elements.slice(0, 12).map((e) => `${e.name} (${e.ifc_class.replace(/^Ifc/, "")})`).join(" · ")
            + (r.elements.length > 12 ? " …" : "");
          body.appendChild(list);
        });
      };
      const queryBtn = toolBtn2("🔎 Query (selector)", openQueryPanel);
      queryBtn.title = "Power-select with the IfcOpenShell selector DSL (by class, property, material) — "
        + "isolate matches or save them as a reusable selection set. The base for bulk edits & rule-driven detailing";

      // W11 F0: LOD-stage spine — dial an element's maturity 100→500, and establish the view-keyed
      // representation contexts the construction-drawing pipeline needs.
      const LODS = ["100", "200", "300", "350", "400", "500"] as const;
      const openLodPanel = async () => {
        let sum;
        try { sum = await api.lodSummary(pid); }
        catch (e) { notify(`LOD failed: ${(e as Error).message}`, "error"); return; }
        const sets = loadSelSets(pid);
        showResult("Level of Development (schematic → construction)", (body) => {
          body.appendChild(kvTable(LODS.map((s) => ({
            k: `LOD ${s}`, v: String(sum.counts[s]), bar: sum.total ? sum.counts[s] / sum.total : 0 }))
            .concat([{ k: "Unstaged", v: String(sum.counts.UNSET), bar: sum.total ? sum.counts.UNSET / sum.total : 0 }])));
          const tag = async (stage: typeof LODS[number], guids: string[], what: string) => {
            if (!guids.length) { notify("nothing to stage", "error"); return; }
            await authorAndReload("set_lod", { guids, stage }, `${what} → LOD ${stage}`);
            await openLodPanel();
          };
          body.appendChild(resultNote(selectedGuid
            ? "<b>Set the selected element's LOD</b>" : "<b>Select an element</b> or use a saved selection set.", ""));
          if (selectedGuid) {
            const row = document.createElement("div"); row.className = "level-row";
            for (const s of LODS) {
              const bt = document.createElement("button"); bt.className = "mini-btn"; bt.textContent = s;
              bt.onclick = () => tag(s, [selectedGuid!], "selection"); row.appendChild(bt);
            }
            body.appendChild(row);
          }
          for (const s of sets) {
            const row = document.createElement("div"); row.className = "level-row";
            const label = document.createElement("span"); label.className = "meta";
            label.textContent = `${s.name} · ${s.guids.length}`; label.style.flex = "1"; row.appendChild(label);
            for (const st of LODS) {
              const bt = document.createElement("button"); bt.className = "mini-btn"; bt.textContent = st;
              bt.title = `Set "${s.name}" to LOD ${st}`; bt.onclick = () => tag(st, s.guids, s.name); row.appendChild(bt);
            }
            body.appendChild(row);
          }
          const ctx = toolBtn2("⚙ Establish drawing contexts", async () => {
            try { const r = await api.ensureContexts(pid);
              const created = (r.changed as { created?: number })?.created ?? 0;
              notify(created ? `created ${created} view context(s)` : "drawing contexts already present", "success");
            } catch (e) { notify(`contexts failed: ${(e as Error).message}`, "error"); }
          });
          ctx.style.marginTop = "6px";
          ctx.title = "Create the Model+Plan / Body·Axis·Box·Annotation·FootPrint representation contexts "
            + "(by TargetView) that construction-drawing generation needs. Idempotent.";
          body.appendChild(ctx);
        });
      };
      const lodBtn = toolBtn2("📶 Level of Development", openLodPanel);
      lodBtn.title = "Dial an element's LOD maturity 100 (schematic) → 500 (as-built), and establish the "
        + "view-keyed representation contexts for construction-drawing generation. GUID-stable.";

      // W11 G1: LOD-500 = field-verified as-built (BIMForum defines no geometry for it — it's a
      // reliability/data attribute). Stamp the selection as verified + show model readiness.
      const openAsBuiltPanel = async () => {
        let s;
        try { s = await api.lod500(pid); }
        catch { toast("Needs a source IFC", "error"); return; }
        showResult("As-built verification (LOD 500)", (body) => {
          body.appendChild(resultNote(`<b>LOD 500</b> is a field-verified as-built reliability attribute — BIMForum sets no `
            + `geometric requirement for it. Model readiness: <b>${s!.readiness_pct}%</b> `
            + `(${s!.verified} of ${s!.total} elements verified). O&M data: <b>${s!.with_manufacturer}</b> with manufacturer · `
            + `<b>${s!.with_serial}</b> with serial · <b>${s!.with_dimensions}</b> dimensioned`
            + (s!.dimensions_out_of_tolerance ? ` (<b>${s!.dimensions_out_of_tolerance}</b> out of tolerance)` : "")
            + (s!.with_om_docs ? ` · <b>${s!.with_om_docs}</b> with O&M/warranty docs` : "")
            + `.`, s!.readiness_pct >= 100 ? "ok" : ""));
          if (Object.keys(s!.by_method).length) {
            body.appendChild(kvTable(Object.entries(s!.by_method).map(([k, v]) => ({ k, v: `${v} element(s)` }))));
          }
          const form = document.createElement("div"); form.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0";
          const who = document.createElement("input"); who.className = "portal-filter"; who.placeholder = "verified by"; who.style.cssText = "flex:1 1 100px;min-width:0;font-size:12px";
          const method = document.createElement("select"); method.className = "portal-filter"; method.style.fontSize = "12px";
          for (const mth of s!.methods) { const o = document.createElement("option"); o.value = mth; o.textContent = mth; method.appendChild(o); }
          form.append(who, method); body.appendChild(form);
          const doVerify = toolBtn2("✅ Verify selection as-built", async () => {
            const guid = selectedGuid;
            if (!guid) { notify("select the element(s) to verify first", "error"); return; }
            await withLoading(container, "stamping as-built verification + republishing", async () => {
              try {
                await api.verifyAsbuilt(pid, [guid], { verified_by: who.value.trim(), method: method.value }, true);
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify("verified as-built", "success"); }
                else notify(`verified — publish ${state}`, state === "error" ? "error" : "info");
                await reloadModelPins();
              } catch (e) { notify(`verify failed: ${(e as Error).message}`, "error"); }
            });
          });
          doVerify.title = "Stamp the selected element(s) with Massing_AsBuilt (VERIFIED + who/when/method) — the "
            + "field-verified reliability layer that makes it a genuine LOD-500 record.";
          body.appendChild(doVerify);

          // W11 G3: manufacturer / serial info (O&M / turnover) on the selection
          body.appendChild(resultNote("<b>Manufacturer / serial</b> (O&M · turnover) — stamps the standard "
            + "Pset_Manufacturer* on the selection; round-trips to COBie / asset systems.", ""));
          const mf = document.createElement("div"); mf.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:4px 0";
          const mkIn = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "flex:1 1 90px;min-width:0;font-size:12px"; return i; };
          const manIn = mkIn("manufacturer"); const modIn = mkIn("model"); const serIn = mkIn("serial"); const yrIn = mkIn("year");
          mf.append(manIn, modIn, serIn, yrIn); body.appendChild(mf);
          const doMfr = toolBtn2("🏷 Stamp manufacturer/serial on selection", async () => {
            const guid = selectedGuid;
            if (!guid) { notify("select the element(s) first", "error"); return; }
            if (![manIn, modIn, serIn, yrIn].some((i) => i.value.trim())) { notify("fill at least one field", "error"); return; }
            await withLoading(container, "stamping manufacturer/serial + republishing", async () => {
              try {
                await api.setManufacturerInfo(pid, [guid], { manufacturer: manIn.value.trim(), model_label: modIn.value.trim(), serial: serIn.value.trim(), production_year: yrIn.value.trim() }, true);
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify("manufacturer/serial stamped", "success"); }
                else notify(`stamped — publish ${state}`, state === "error" ? "error" : "info");
                await reloadModelPins();
              } catch (e) { notify(`stamp failed: ${(e as Error).message}`, "error"); }
            });
          });
          body.appendChild(doMfr);

          // W11 G2: field-verified as-built dimension + variance on the selection
          body.appendChild(resultNote("<b>Field-verified dimension</b> — record a measured value (+ optional "
            + "design value) → variance vs design, the dimensional half of LOD 500.", ""));
          const df = document.createElement("div"); df.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:4px 0";
          const dimName = document.createElement("input"); dimName.className = "portal-filter"; dimName.placeholder = "dimension (Length)"; dimName.value = "Length"; dimName.style.cssText = "flex:1 1 90px;min-width:0;font-size:12px";
          const measIn = mkIn("measured (m)"); const desIn = mkIn("design (m, opt)");
          df.append(dimName, measIn, desIn); body.appendChild(df);
          const doDim = toolBtn2("📏 Record measured dimension on selection", async () => {
            const guid = selectedGuid;
            if (!guid) { notify("select the element(s) first", "error"); return; }
            const meas = parseFloat(measIn.value);
            if (!isFinite(meas)) { notify("enter a measured value", "error"); return; }
            const des = parseFloat(desIn.value);
            await withLoading(container, "recording as-built dimension + republishing", async () => {
              try {
                await api.recordAsbuiltDimension(pid, [guid], dimName.value.trim() || "Length", meas, isFinite(des) ? des : undefined, true);
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify("dimension recorded", "success"); }
                else notify(`recorded — publish ${state}`, state === "error" ? "error" : "info");
                await reloadModelPins();
              } catch (e) { notify(`record failed: ${(e as Error).message}`, "error"); }
            });
          });
          body.appendChild(doDim);

          // G3: O&M / warranty document reference (turnover paperwork bound to the asset)
          body.appendChild(resultNote("<b>O&M / warranty document</b> — attach a manual/warranty reference "
            + "(name + link) to the selection via IfcRelAssociatesDocument; counts toward turnover readiness.", ""));
          const of = document.createElement("div"); of.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:4px 0";
          const docName = mkIn("document name"); const docUrl = mkIn("link / URI (opt)");
          const docKind = document.createElement("select"); docKind.className = "portal-filter"; docKind.style.fontSize = "12px";
          for (const [v, l] of [["om", "O&M manual"], ["warranty", "warranty"]] as const) { const o = document.createElement("option"); o.value = v; o.textContent = l; docKind.appendChild(o); }
          of.append(docName, docUrl, docKind); body.appendChild(of);
          const doDoc = toolBtn2("📄 Attach O&M / warranty doc to selection", async () => {
            const guid = selectedGuid;
            if (!guid) { notify("select the element(s) first", "error"); return; }
            if (!docName.value.trim()) { notify("enter a document name", "error"); return; }
            await withLoading(container, "attaching document + republishing", async () => {
              try {
                await api.attachOmDocument(pid, [guid], docName.value.trim(), { location: docUrl.value.trim() || undefined, kind: docKind.value as "om" | "warranty" }, true);
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify("document attached", "success"); }
                else notify(`attached — publish ${state}`, state === "error" ? "error" : "info");
                await reloadModelPins();
              } catch (e) { notify(`attach failed: ${(e as Error).message}`, "error"); }
            });
          });
          body.appendChild(doDoc);
        });
      };
      const asBuiltBtn = toolBtn2("✅ As-built verify (LOD 500)", openAsBuiltPanel);
      asBuiltBtn.title = "Mark elements field-verified as-built and see LOD-500 readiness — the data/reliability "
        + "attribute BIMForum actually defines as LOD 500 (no geometric requirement).";

      // W11 Track D: attach code/spec/detail carriers to the selected element (classification codes +
      // detail/instruction documents) — what keynotes, schedules and the spec/drawing generators read.
      const openDetailingPanel = async () => {
        if (!selectedGuid) { notify("select an element to detail", "error"); return; }
        const guid = selectedGuid;
        let det;
        try { det = await api.elementDetailing(pid, guid); }
        catch (e) { notify(`detailing failed: ${(e as Error).message}`, "error"); return; }
        showResult(`Detailing — ${det.name}`, (body) => {
          body.appendChild(kvTable(det.classifications.length
            ? det.classifications.map((c) => ({ k: c.system || "code", v: `${c.code ?? ""}${c.title ? " · " + c.title : ""}` }))
            : [{ k: "Classifications", v: "none" }]));
          body.appendChild(resultNote(det.documents.length
            ? "<b>Documents</b>: " + det.documents.map((d) => `${d.identification ?? ""} ${d.name ?? ""}`.trim()).join(" · ")
            : "No details/instructions attached.", ""));
          const reopen = () => openDetailingPanel();
          const CLS = [["MasterFormat", "spec section, e.g. 08 51 00"], ["UniFormat", "element/keynote, e.g. B2020"],
            ["OmniClass", "product, e.g. 23-17 11 11"], ["Uniclass", "e.g. SS_25_10"]] as const;
          for (const [sys, hint] of CLS) {
            body.appendChild(toolBtn2(`＋ ${sys} code`, async () => {
              const code = await askText(`${sys} code`, { label: hint, value: "" }); if (!code) return;
              const title = await askText(`${sys} code`, { label: "Title (optional)", value: "" });
              await authorAndReload("classify", { guids: [guid], system: sys, code: code.trim(), name: title?.trim() || undefined }, `${sys} ${code.trim()}`);
              await reopen();
            }));
          }
          body.appendChild(toolBtn2("📎 Attach detail / instruction", async () => {
            const name = await askText("Attach document", { label: "Document name", value: "Flashing detail" }); if (!name) return;
            const ident = await askText("Attach document", { label: "Detail no. / key (e.g. A-541/3)", value: "" });
            const loc = await askText("Attach document", { label: "Location (URI — SVG/PDF)", value: "" });
            await authorAndReload("attach_document",
              { guids: [guid], name: name.trim(), identification: ident?.trim() || undefined, location: loc?.trim() || undefined },
              `document ${name.trim()}`);
            await reopen();
          }));
        });
      };
      const detailBtn = toolBtn2("🏷 Detailing (codes & documents)", openDetailingPanel);
      detailBtn.title = "Attach keynote/spec codes (UniFormat/MasterFormat/OmniClass) and detail/instruction "
        + "documents to the selected element — IFC-native carriers that feed keynotes, schedules & the spec/drawing set";

      // W11 D3: auto-detail the whole model from the rule library + an IDS-style missing-keynote pre-flight.
      const openAutoDetail = async () => {
        let val;
        try { val = await api.validateDetailing(pid); }
        catch (e) { notify(`validate failed: ${(e as Error).message}`, "error"); return; }
        showResult("Auto-detail (code / spec / detail rules)", (body) => {
          body.appendChild(resultNote(val.gaps
            ? `<b>${val.gaps}</b> element(s) match a rule but are <b>missing</b> their keynote/spec — e.g. an `
              + `exterior window with no flashing detail. Run auto-detail to attach them.`
            : "Every rule-covered element already carries its code & detail. ✓", val.gaps ? "bad" : "ok"));
          if (val.gaps) {
            body.appendChild(kvTable(val.elements.slice(0, 12).map((g) => ({ k: g.name, v: g.missing }))));
          }
          const run = toolBtn2("✨ Auto-detail model (apply rules)", async () => {
            await authorAndReload("apply_detailing_rules", {}, "auto-detail");
            await openAutoDetail();
          });
          run.title = "Attach the code/spec/detail bundle to every element a rule matches — e.g. exterior "
            + "window → IBC §1404.4 / ASTM E2112 flashing detail + install instruction + spec 08 51 00. GUID-stable.";
          body.appendChild(run);
        });
      };
      const autoDetailBtn = toolBtn2("✨ Auto-detail (rules)", openAutoDetail);
      autoDetailBtn.title = "Run the condition→content rule library over the model — exterior windows/doors get "
        + "IBC/ASTM flashing details + specs, rated walls get assembly keynotes. Same rules validate as IDS QA.";

      // W11 C1: generate a schematic plan drawing (SVG) from the model, at the active level if one is set.
      const planBtn = toolBtn2("🖨 Generate plan (SVG)", () => {
        const q = new URLSearchParams({ scale: "100" });
        if (activeStorey) q.set("storey", activeStorey);
        window.open(api.url(`/projects/${projectId}/drawings/plan.svg?${q.toString()}`), "_blank");
      });
      planBtn.title = "Generate a schematic plan drawing (SVG, 1:100) from the model geometry — walls/columns/"
        + "slabs as class-styled poché with dimensions + keynotes. The active level scopes it.";

      // W11 C3: compose an issuable sheet (ARCH-D border + titleblock) around the plan.
      const sheetBtn = toolBtn2("📄 Issue sheet (A-101)", () => {
        const q = new URLSearchParams({ scale: "100", number: "A-101", title: "FLOOR PLAN" });
        if (activeStorey) { q.set("storey", activeStorey); q.set("title", `${activeStorey.toUpperCase()} PLAN`); }
        window.open(api.url(`/projects/${projectId}/drawings/sheet.svg?${q.toString()}`), "_blank");
      });
      sheetBtn.title = "Compose an issuable construction sheet — ARCH-D border + titleblock (project, sheet "
        + "number, scale, north arrow) with the plan placed in a scaled viewport. The deliverable.";

      // W11 C3b: the submittable PDF of the sheet (reportlab, permit-ready).
      const pdfBtn = toolBtn2("⤓ Sheet PDF (A-101)", () => {
        const q = new URLSearchParams({ scale: "100", number: "A-101", title: "FLOOR PLAN" });
        if (activeStorey) { q.set("storey", activeStorey); q.set("title", `${activeStorey.toUpperCase()} PLAN`); }
        window.open(api.url(`/projects/${projectId}/drawings/sheet.pdf?${q.toString()}`), "_blank");
      });
      pdfBtn.title = "Download the sheet as a PDF (ARCH-D, titleblock, plan poché + dimensions + keynotes) — "
        + "the submittable construction-document deliverable, rendered server-side.";

      // W11 C4: computed door / window / room schedules from the model.
      const openSchedules = async () => {
        let sc;
        try { sc = await api.drawingSchedules(pid); }
        catch (e) { notify(`schedules failed: ${(e as Error).message}`, "error"); return; }
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
      const schedBtn = toolBtn2("📋 Schedules", openSchedules);
      schedBtn.title = "Computed door / window / room schedules (marks, sizes, types, levels, areas) — the "
        + "tabular half of the CD set, straight from the model. Also at GET /drawings/schedule.svg.";

      // W11 C6: the schedules laid out on an issuable ARCH-D sheet (PDF) — the submittable tabular sheet.
      const schedPdfBtn = toolBtn2("⤓ Schedules sheet (A-601 PDF)", () => {
        window.open(api.url(`/projects/${projectId}/drawings/schedule.pdf?number=A-601`), "_blank");
      });
      schedPdfBtn.title = "Lay the door / window / room schedules on an ARCH-D titleblock sheet and download "
        + "as a submittable PDF — the tabular half of the CD set as an issuable sheet.";

      // W11 D6: the 3-part MasterFormat project manual (the spec book), seeded from classifications.
      const manualBtn = toolBtn2("📖 Project manual (spec book)", () => withLoading(container, "Assembling the project manual", async () => {
        let man;
        try { man = await api.specManual(projectId!); }
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
          const dl = toolBtn2("⤓ Download manual (.txt)", () => window.open(api.url(`/projects/${projectId}/spec/manual.txt`), "_blank"));
          body.appendChild(dl);
        });
      }));
      manualBtn.title = "Generate the 3-part MasterFormat project manual — elements grouped into CSI "
        + "divisions → sections (Part 1 General / Part 2 Products / Part 3 Execution), seeded from the "
        + "model's classifications + attached install docs. The spec book that accompanies the drawings.";

      // W11 C5: sections & elevations — cut linework straight from the baked model geometry. The
      // section auto-centres on the model (no offset needed); elevations project each cardinal face.
      const sectBtn = toolBtn2("📐 Sections & elevations", () => {
        showResult("Sections & elevations", (body) => {
          body.appendChild(resultNote("Generate a cut <b>section</b> (through the middle of the model) or a projected "
            + "<b>elevation</b> of each face — true linework from the model geometry, opens as SVG.", "ok"));
          const openDrawing = (path: string) => window.open(api.url(`/projects/${projectId}/drawings/${path}`), "_blank");
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
          planDxf.title = "Export the plan cut linework as a DXF any CAD tool can open" + (activeStorey ? ` (${activeStorey})` : "");
          planDxf.onclick = () => { const q = new URLSearchParams(); if (activeStoreyZ) q.set("elevation", String(activeStoreyZ)); openDrawing(`plan.dxf?${q.toString()}`); };
          plR.appendChild(planDxf);
        });
      });
      sectBtn.title = "Cut sections (auto-centred on the model) and projected N/S/E/W elevations — vector "
        + "linework from the model geometry, the other half of the drawing set alongside plans.";

      // W11 B6: steel connections — base plate on the selected column, shear tab on the selected beam
      // (bare LOD-300 members → LOD-350/400 fabrication assemblies).
      const basePlateBtn = toolBtn2("🔩 Base plate (steel column)", async () => {
        if (!selectedGuid) { notify("select a steel column first", "error"); return; }
        await authorAndReload("add_base_plate", { column_guid: selectedGuid, bolts: 4 }, "base plate");
      });
      basePlateBtn.title = "Author a base plate + 4 anchor bolts under the selected steel column and group "
        + "them into an IfcElementAssembly — the LOD 350/400 fabrication connection. GUID-stable.";
      const shearTabBtn = toolBtn2("🔩 Shear tab (steel beam)", async () => {
        if (!selectedGuid) { notify("select a steel beam first", "error"); return; }
        await authorAndReload("add_shear_tab", { beam_guid: selectedGuid, bolts: 3 }, "shear tab");
      });
      shearTabBtn.title = "Author a shear-tab plate + bolts at the selected steel beam's end and assemble it "
        + "with the beam — a simple beam-to-column shear connection (LOD 350/400). GUID-stable.";
      const rebarBtn = toolBtn2("🪝 Rebar cage (concrete column)", async () => {
        if (!selectedGuid) { notify("select a concrete column first", "error"); return; }
        await authorAndReload("add_rebar_cage", { column_guid: selectedGuid }, "rebar cage");
      });
      rebarBtn.title = "Author a reinforcement cage — 4 longitudinal corner bars + stirrups (swept-disk "
        + "IfcReinforcingBar) in the selected concrete column, assembled with it (LOD 400). GUID-stable.";
      const cageChkBtn = toolBtn2("✓ Check cage (ACI envelope)", async () => {
        if (!selectedGuid) { notify("select the caged concrete column first", "error"); return; }
        try {
          const r = await api.rebarCheckCage(pid, selectedGuid);
          const ok = r.checked && !r.violations.length;
          showResult("Rebar cage check", (body) => {
            body.appendChild(resultNote(ok
              ? `✅ cage OK — ${r.longitudinal_bars} bars · ${r.ties} ties · tie spacing within `
                + `${r.params.tie_spacing} m (${escapeHtml(r.params.governing)})`
              : `🔴 ${r.violations.map(escapeHtml).join(" · ")}`, ok ? "ok" : ""));
            body.appendChild(resultNote(`Rule: ${escapeHtml(r.params.rule)} — #bars ≥ ${r.params.min_longitudinal_bars}, `
              + `envelope ${r.params.tie_spacing} m for ${escapeHtml(r.params.bar_size)}/${escapeHtml(r.params.tie_size)}.`, ""));
          });
        } catch (e) { notify((e as Error).message, "error"); }
      });
      cageChkBtn.title = "Verify the selected column's authored cage against the ACI 318 envelope — "
        + "longitudinal bar count and tie spacing min(16·d_bar, 48·d_tie, least dimension).";
      const bbsBtn = toolBtn2("📋 Bar bending schedule", async () => {
        try {
          const r = await api.rebarBbs(pid);
          showResult("Bar bending schedule", (body) => {
            body.appendChild(resultNote(`<b>${r.bars}</b> bars · ${r.marks} marks · `
              + `${r.total_length_m.toLocaleString()} m · <b>${r.total_tonnes} t</b>`
              + (r.skipped ? ` · ${r.skipped} skipped (no swept geometry)` : ""), r.bars ? "ok" : ""));
            if (r.rows.length) {
              const t = document.createElement("table"); t.className = "mini-table";
              t.style.cssText = "width:100%;font-size:11px;border-collapse:collapse";
              t.innerHTML = `<thead><tr><th>Mark</th><th>Size</th><th>Shape</th><th>Cut (m)</th>`
                + `<th>Count</th><th>kg/m</th><th>Total kg</th></tr></thead><tbody>`
                + r.rows.map((x) => `<tr><td>${escapeHtml(x.mark)}</td><td>${escapeHtml(x.size || String(x.diameter_mm) + "mm")}</td>`
                  + `<td>${escapeHtml(x.shape)}</td><td style="text-align:right">${x.cut_length_m}</td>`
                  + `<td style="text-align:center">${x.count}</td><td style="text-align:right">${x.unit_mass_kg_m}</td>`
                  + `<td style="text-align:right">${x.total_kg}</td></tr>`).join("") + `</tbody>`;
              body.appendChild(t);
              const dl = document.createElement("a"); dl.className = "file-btn"; dl.style.marginTop = "6px";
              dl.textContent = "⬇ BBS (CSV)"; dl.href = api.rebarBbsCsvUrl(pid);
              body.appendChild(dl);
            } else {
              body.appendChild(resultNote("No IfcReinforcingBar elements — author cages first (🪝).", ""));
            }
          });
        } catch (e) { notify((e as Error).message, "error"); }
      });
      bbsBtn.title = "Group every authored IfcReinforcingBar into marks (size · shape · cut length) with "
        + "unit mass and total tonnage — the fabricator/5D quantity, downloadable as CSV.";

      // W11 B6: MEP fitting at the last-clicked point + a system browser.
      const mepFittingBtn = toolBtn2("🔀 MEP fitting (elbow / tee)", async () => {
        if (!lastPoint) { notify("click a point in the model first, then add the fitting", "error"); return; }
        const kind = await askText("MEP fitting", { label: "Type: bend (elbow) · junction (tee) · transition", value: "bend" });
        if (!kind) return;
        const sys = await askText("MEP fitting", { label: "System name", value: "HVAC Supply" });
        const pd = { bend: "BEND", elbow: "BEND", junction: "JUNCTION", tee: "JUNCTION", transition: "TRANSITION" }[kind.trim().toLowerCase()] || "BEND";
        await authorAndReload("add_mep_fitting",
          { ifc_class: "IfcDuctFitting", point: [lastPoint.x, -lastPoint.z], predefined: pd, system: sys?.trim() || "HVAC Supply" },
          `MEP ${pd.toLowerCase()}`);
      });
      mepFittingBtn.title = "Author a MEP fitting (elbow/tee/transition, with ports) at the last-clicked point "
        + "and assign it to a distribution system — the LOD 350/400 detailing that joins loose runs. GUID-stable.";

      // MEP-FP: place fire-protection equipment at the last-clicked point (onto the Fire Protection system).
      const fireBtn = toolBtn2("🧯 Fire-protection equipment", async () => {
        if (!lastPoint) { notify("click a point in the model first, then place the device", "error"); return; }
        const kind = await askText("Fire protection", {
          label: "Device: sprinkler · hose_reel · fdc (fire-dept connection) · hydrant · fire_pump", value: "sprinkler" });
        if (!kind) return;
        const k = kind.trim().toLowerCase().replace(/[ -]/g, "_");
        const known = ["sprinkler", "hose_reel", "fdc", "hydrant", "fire_pump"];
        await authorAndReload("add_fire_equipment",
          { kind: known.includes(k) ? k : "sprinkler", point: [lastPoint.x, -lastPoint.z] },
          `fire ${k}`);
      });
      fireBtn.title = "Author a fire-protection device (sprinkler head, hose reel, fire-department/siamese "
        + "connection, hydrant, or fire pump) as the right IFC class on the Fire Protection distribution system.";

      // DISC-4a: fire-alarm / life-safety device (distinct from fire protection) at the last-clicked point.
      const faBtn = toolBtn2("🔔 Fire-alarm device", async () => {
        if (!lastPoint) { notify("click a point in the model first, then place the device", "error"); return; }
        const kind = await askText("Fire alarm / life safety", {
          label: "Device: smoke_detector · heat_detector · pull_station · horn_strobe · strobe · bell · facp",
          value: "smoke_detector" });
        if (!kind) return;
        const k = kind.trim().toLowerCase().replace(/[ -]/g, "_");
        const known = ["smoke_detector", "heat_detector", "duct_detector", "pull_station", "horn_strobe", "strobe", "bell", "facp"];
        await authorAndReload("add_fa_device",
          { kind: known.includes(k) ? k : "smoke_detector", point: [lastPoint.x, -lastPoint.z] },
          `fire-alarm ${k}`);
      });
      faBtn.title = "Author a fire-alarm / life-safety device (smoke/heat detector, manual pull station, "
        + "horn-strobe, bell, or FACP) on the Fire Alarm system — its own discipline, apart from fire protection.";

      // DISC-4a: telecom / low-voltage device at the last-clicked point.
      const commsBtn = toolBtn2("📶 Telecom device", async () => {
        if (!lastPoint) { notify("click a point in the model first, then place the device", "error"); return; }
        const kind = await askText("Telecom / low-voltage", {
          label: "Device: idf · mdf · rack · switch · wap (wireless AP) · data_outlet", value: "idf" });
        if (!kind) return;
        const k = kind.trim().toLowerCase().replace(/[ -]/g, "_");
        const known = ["mdf", "idf", "rack", "switch", "wap", "data_outlet"];
        await authorAndReload("add_comms_device",
          { kind: known.includes(k) ? k : "idf", point: [lastPoint.x, -lastPoint.z] },
          `telecom ${k}`);
      });
      commsBtn.title = "Author a telecom / low-voltage device (MDF/IDF rack, network switch, wireless access "
        + "point, or data outlet) on the Telecommunications system (discipline T).";

      // MEP-FP / MEP: a vertical riser (standpipe / stack / vent) at the last-clicked point.
      const riserBtn = toolBtn2("⭱ Vertical riser (standpipe / stack)", async () => {
        if (!lastPoint) { notify("click a point in the model first, then add the riser", "error"); return; }
        const range = await askText("Vertical riser", { label: "Bottom, top elevation (m) — [E,N] is the last click", value: "0, 9" });
        if (!range) return;
        const parts = range.split(",").map((x) => parseFloat(x.trim()));
        const b = parts[0] ?? NaN, t = parts[1] ?? NaN;
        if (!isFinite(b) || !isFinite(t) || t <= b) { notify("enter bottom, top with top above bottom", "error"); return; }
        await authorAndReload("add_riser",
          { point: [lastPoint.x, -lastPoint.z], bottom_z: b, top_z: t, size: 0.1, system: "Fire Protection", discipline: "fire" },
          "riser");
      });
      riserBtn.title = "Author a vertical MEP riser (fire standpipe / plumbing stack / vent) from a bottom to "
        + "top elevation at the last-clicked point — the vertical complement to horizontal MEP runs.";
      let mepConnectFrom: string | null = null;   // W10-4: first element of a port-to-port connect
      const mepSysBtn = toolBtn2("🔀 MEP systems", async () => {
        let s, c;
        try { [s, c] = await Promise.all([api.mepSummary(pid), api.mepConnectivity(pid)]); }
        catch (e) { notify(`MEP failed: ${(e as Error).message}`, "error"); return; }
        showResult("MEP systems & connectivity", (body) => {
          // W10-4 connectivity validation
          body.appendChild(resultNote(`<b>Connectivity</b> — ${c!.connections} port-to-port link(s) · `
            + `${c!.ports_connected}/${c!.ports_total} ports connected (${c!.connected_pct}%) · `
            + `<b>${c!.dangling_count}</b> floating element(s).`, c!.dangling_count ? "" : "ok"));
          // two-step connect: pick one element, then connect it to another
          const cw = document.createElement("div"); cw.style.cssText = "display:flex;gap:6px;margin:4px 0;flex-wrap:wrap";
          const pick = toolBtn2(mepConnectFrom ? "① picked — select the 2nd element" : "🔗 Connect: pick first element", () => {
            if (!selectedGuid) { notify("select an MEP element first", "error"); return; }
            mepConnectFrom = selectedGuid; notify("first element picked — select the second, then Connect", "info");
          });
          const doConn = toolBtn2("🔗 Connect to second element", async () => {
            if (!mepConnectFrom) { notify("pick the first element first", "error"); return; }
            if (!selectedGuid || selectedGuid === mepConnectFrom) { notify("select a different second element", "error"); return; }
            const a = mepConnectFrom, b = selectedGuid;
            await withLoading(container, "connecting MEP ports + republishing", async () => {
              try {
                await api.connectMep(pid, a, b, true);
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify("connected port-to-port", "success"); }
                else notify(`connected — publish ${state}`, state === "error" ? "error" : "info");
                mepConnectFrom = null; await reloadModelPins();
              } catch (e) { notify(`connect failed: ${(e as Error).message}`, "error"); }
            });
          });
          cw.append(pick, doConn); body.appendChild(cw);
          if (c!.dangling.length) {
            const iso = toolBtn2("◎ Isolate floating elements in 3D", () => { void layerMgr.isolateGuids(c!.dangling.map((d) => d.guid)); });
            body.appendChild(iso);
          }
          if (!s.systems.length) { body.appendChild(resultNote("No distribution systems yet — add duct/pipe runs + fittings.", "")); return; }
          // MEP-FP: by-discipline rollup (fire protection is a first-class discipline beside HVAC/plumbing/electrical)
          const discIcon: Record<string, string> = { hvac: "💨", plumbing: "🚰", electrical: "⚡", fire: "🧯", comms: "📶", other: "🔀" };
          if (s.by_discipline && Object.keys(s.by_discipline).length) {
            const roll = Object.entries(s.by_discipline)
              .map(([d, v]) => `${discIcon[d] || "🔀"} ${d} (${v.systems})`).join(" · ");
            body.appendChild(resultNote(`<b>Disciplines</b> — ${roll}.`
              + (s.has_fire_protection ? "" : " <i>No fire-protection system yet.</i>"), s.has_fire_protection ? "ok" : ""));
            const sizeBtn = toolBtn2("📐 MEP size check (velocity)", async () => {
              let mz;
              try { mz = await api.mepSizing(pid); }
              catch (e) { notify((e as Error).message, "error"); return; }
              if (!mz.checked) { body.appendChild(resultNote("No sized MEP runs to check — author ducts/pipes with a design size + flow first.", "")); return; }
              body.appendChild(resultNote(`<b>MEP size check</b> — ${mz.passed} pass · <b>${mz.failed} fail</b> · ${mz.info} info`
                + ` of ${mz.checked} run(s). Limits: air ≤ ${mz.limits.duct_max_fpm} fpm · water ≤ ${mz.limits.pipe_max_fps} ft/s.`,
                mz.failed ? "bad" : "ok"));
              const icon = (st: string) => st === "pass" ? "✅" : st === "fail" ? "❌" : "ℹ️";
              body.appendChild(kvTable(mz.checks.slice(0, 20).map((c) => ({
                k: `${icon(c.status)} ${c.class.replace("Ifc", "")}${c.system ? ` · ${c.system}` : ""}`,
                v: `${c.size_mm}mm ${c.flow != null ? `@ ${c.flow} ${c.flow_unit ?? ""}` : ""} — ${c.note}`,
              }))));
              const bad = mz.checks.filter((c) => c.status === "fail").map((c) => c.guid);
              if (bad.length) body.appendChild(toolBtn2("◎ Isolate undersized runs in 3D", () => { void layerMgr.isolateGuids(bad); }));
              body.appendChild(resultNote(mz.disclaimer, ""));
            });
            sizeBtn.title = "Velocity/fill size check over authored MEP (ASHRAE air, erosion-limit water) — preliminary, not a stamped design";
            body.appendChild(sizeBtn);
            if (s.has_fire_protection) {
              const covBtn = toolBtn2("🧯 Sprinkler coverage (NFPA 13)", async () => {
                let cov;
                try { cov = await api.sprinklerCoverage(pid, "light"); }
                catch (e) { notify((e as Error).message, "error"); return; }
                const ok = cov.adequate;
                body.appendChild(resultNote(`<b>Sprinkler coverage</b> (${cov.hazard} hazard) — `
                  + `${cov.sprinkler_heads} head(s) vs <b>${cov.required_heads}</b> required for `
                  + `${cov.protected_area_m2.toLocaleString()} m² (≤${cov.max_coverage_m2_per_head} m²/head): `
                  + `<b>${ok == null ? "n/a" : ok ? "adequate" : `short ${cov.shortfall}`}</b>. `
                  + `<span class="meta">${cov.citation}. ${cov.verify}</span>`,
                  ok == null ? "" : ok ? "ok" : "bad"));
              });
              covBtn.title = "NFPA-13-informed head-count vs protected-area coverage pre-check (not a hydraulic design)";
              body.appendChild(covBtn);
            }
          }
          for (const sy of s.systems) {
            const di = discIcon[sy.discipline || "other"] || "🔀";
            body.appendChild(kvTable([
              { k: `${di} ${sy.name}`, v: `${sy.members} elements${sy.discipline ? ` · ${sy.discipline}` : ""}`, strong: true },
              { k: "  segments · fittings · terminals", v: `${sy.segments} · ${sy.fittings} · ${sy.terminals}` },
              { k: "  elements with open ports", v: String(sy.elements_with_open_ports) },
            ]));
          }
          if (s.unassigned.segments || s.unassigned.fittings) {
            body.appendChild(resultNote(`⚠ Unassigned to any system: <b>${s.unassigned.segments}</b> segment(s), `
              + `<b>${s.unassigned.fittings}</b> fitting(s).`, "bad"));
          }
        });
      });
      mepSysBtn.title = "Browse IfcDistributionSystems — per-system segment/fitting/terminal counts, a "
        + "connectivity signal (elements with unconnected ports), and anything not yet assigned to a system.";

      // W11 B6: curtain wall along a line (start = last-clicked point, end from a prompt).
      const curtainBtn = toolBtn2("🪟 Curtain wall", async () => {
        const start: [number, number] = lastPoint ? [lastPoint.x, -lastPoint.z] : [0, 0];
        const endS = await askText("Curtain wall", { label: "End point E, N (metres) — start is the last click", value: `${(start[0] + 6).toFixed(1)}, ${start[1].toFixed(1)}` });
        if (!endS) return;
        const ep = endS.split(",").map((v) => Number(v.trim()));
        const grid = await askText("Curtain wall", { label: "Bays × rows (cols, rows)", value: "3, 2" });
        const g = (grid || "3,2").split(/[,x×]/).map((v) => Math.max(1, Math.round(Number(v.trim()) || 1)));
        await authorAndReload("add_curtain_wall",
          { start, end: [ep[0] ?? start[0] + 6, ep[1] ?? start[1]], cols: g[0] ?? 3, rows: g[1] ?? 2 },
          "curtain wall");
      });
      curtainBtn.title = "Author an IfcCurtainWall along a line — vertical mullions + horizontal transoms + "
        + "glazing panels on a bays×rows grid, aggregated as one assembly (LOD 350/400). GUID-stable.";

      // E4 — progressive disclosure: everyday authoring + drawings stay visible; LOD-350/400 fabrication
      // and detailing tools tuck behind an "Advanced" toggle so a first-time modeler isn't overwhelmed.
      // The choice persists, so power users keep their fabrication tools open.
      // A1 — sandboxed ifcopenshell escape hatch (server-gated by AEC_ALLOW_IFC_CODE; returns a clear 403
      // when disabled, so no pre-check is needed). GUID-stable, versioned + undo-able like any edit.
      const ifcCodeBtn = toolBtn2("⚡ Run IFC code (sandboxed)", () => {
        showResult("Run IFC code — sandboxed ifcopenshell", (body) => {
          body.appendChild(resultNote("Author what the recipes can't express with a small ifcopenshell "
            + "snippet — <code>model</code> and <code>ifcopenshell</code> are in scope (e.g. "
            + "<code>ifcopenshell.api.run('root.create_entity', model, ifc_class='IfcWall')</code>). "
            + "AST-sandboxed (no imports / IO / reflection). <b>Disabled unless the operator sets "
            + "<code>AEC_ALLOW_IFC_CODE=1</code></b>. Versioned — undo restores the prior model.", ""));
          const ta = document.createElement("textarea"); ta.className = "portal-filter";
          ta.style.cssText = "width:100%;min-height:120px;font-family:monospace;font-size:12px";
          ta.placeholder = "for i in range(3):\n    ifcopenshell.api.run('root.create_entity', model, ifc_class='IfcWall', name='w'+str(i))";
          body.appendChild(ta);
          const run = toolBtn2("⚡ Run + republish", async () => {
            if (!ta.value.trim()) { notify("enter some code first", "error"); return; }
            await withLoading(container, "running IFC code + republishing", async () => {
              try {
                const r = await api.editIfc(projectId!, "execute_ifc_code", { code: ta.value }, true) as { changed?: { message?: string } };
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify(r?.changed?.message || "ran ok", "success"); }
                else notify(`ran — publish ${state}`, state === "error" ? "error" : "info");
                await reloadModelPins();
              } catch (e) { notify(`code failed: ${(e as Error).message}`, "error"); }
            });
          });
          body.appendChild(run);
        });
      });
      ifcCodeBtn.title = "Run a sandboxed ifcopenshell snippet against the model — the unbounded escape hatch "
        + "for authoring the recipes can't express. Disabled unless the server sets AEC_ALLOW_IFC_CODE=1.";

      // B3 — sloped-top wall (parapet slope / shed / gable): rebuild the selected wall's top to slope
      // from start_height → end_height.
      const slopeBtn = toolBtn2("⟋ Slope wall top", () => {
        if (!selectedGuid) { notify("select a wall first", "error"); return; }
        const guid = selectedGuid;
        showResult("Slope wall top", (body) => {
          body.appendChild(resultNote("Give the selected wall a <b>sloped top</b> — the top rises from "
            + "the start height (at the wall's start point) to the end height (parapet slope / shed / "
            + "gable). GUID-stable, versioned (undo restores the flat top).", ""));
          const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;margin:4px 0";
          const sIn = document.createElement("input"); sIn.type = "number"; sIn.className = "portal-filter"; sIn.placeholder = "start height (m)"; sIn.step = "0.1"; sIn.style.cssText = "flex:1;min-width:0;font-size:12px";
          const eIn = document.createElement("input"); eIn.type = "number"; eIn.className = "portal-filter"; eIn.placeholder = "end height (m)"; eIn.step = "0.1"; eIn.style.cssText = "flex:1;min-width:0;font-size:12px";
          row.append(sIn, eIn); body.appendChild(row);
          const go = toolBtn2("⟋ Apply slope + republish", async () => {
            const sh = parseFloat(sIn.value), eh = parseFloat(eIn.value);
            if (!(sh > 0) || !(eh > 0)) { notify("enter positive start & end heights", "error"); return; }
            await withLoading(container, "sloping the wall top + republishing", async () => {
              try {
                await api.setWallSlope(pid, guid, sh, eh, true);
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify("wall top sloped", "success"); }
                else notify(`sloped — publish ${state}`, state === "error" ? "error" : "info");
                await reloadModelPins();
              } catch (e) { notify(`slope failed: ${(e as Error).message}`, "error"); }
            });
          });
          body.appendChild(go);
        });
      });
      slopeBtn.title = "Give the selected wall a sloped top (start height → end height) — parapet slope, "
        + "shed, or gable wall. Rebuilds the Body as a trapezoidal extrusion; GUID-stable + undo-able.";

      // B4 — procedural-mesh escape hatch: author an element from a raw triangle mesh (JSON verts/faces).
      const meshBtn = toolBtn2("△ Add mesh (verts/faces JSON)", () => {
        showResult("Add procedural mesh", (body) => {
          body.appendChild(resultNote("Author an element from a raw triangle mesh for geometry the "
            + "recipes can't express. Paste <code>{\"verts\":[[x,y,z]…],\"faces\":[[i,j,k]…]}</code> "
            + "(faces are 0-based vertex indices, coords in metres). GUID-stable + undo-able.", ""));
          const ta = document.createElement("textarea"); ta.className = "portal-filter";
          ta.style.cssText = "width:100%;min-height:100px;font-family:monospace;font-size:12px";
          ta.placeholder = '{"verts":[[0,0,0],[2,0,0],[2,2,0],[0,2,0],[1,1,2]],"faces":[[0,1,4],[1,2,4],[2,3,4],[3,0,4],[0,2,1],[0,3,2]]}';
          body.appendChild(ta);
          const go = toolBtn2("△ Add mesh + republish", async () => {
            let parsed: { verts?: number[][]; faces?: number[][] };
            try { parsed = JSON.parse(ta.value); } catch { notify("invalid JSON", "error"); return; }
            if (!parsed.verts?.length || !parsed.faces?.length) { notify("need verts and faces", "error"); return; }
            await withLoading(container, "authoring mesh + republishing", async () => {
              try {
                await api.addMesh(pid, parsed.verts!, parsed.faces!, "Mesh", true);
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify("mesh added", "success"); }
                else notify(`added — publish ${state}`, state === "error" ? "error" : "info");
                await reloadModelPins();
              } catch (e) { notify(`mesh failed: ${(e as Error).message}`, "error"); }
            });
          });
          body.appendChild(go);
        });
      });
      meshBtn.title = "Author an element from a raw triangle mesh (IfcTriangulatedFaceSet) — the escape "
        + "hatch for geometry the parametric recipes can't express.";

      // UX-2 — interactive annotation: place a 2D text note/tag/callout as an IfcAnnotation at the last point
      const annotBtn = toolBtn2("🏷 Add note / annotation", async () => {
        if (!lastPoint) { notify("click a point in the model first, then add the note", "error"); return; }
        const text = await askText("Annotation", { label: "Note text:", value: "" });
        if (!text || !text.trim()) return;
        const kind = await askText("Annotation", { label: "Kind: note · tag · callout", value: "note" });
        const k = (["note", "tag", "callout"].includes((kind || "").trim().toLowerCase()) ? kind!.trim().toLowerCase() : "note") as "note" | "tag" | "callout";
        await withLoading(container, "placing annotation + republishing", async () => {
          try {
            await api.addAnnotation(projectId!, [lastPoint!.x, -lastPoint!.z], text.trim(), { kind: k, z: lastPoint!.y }, true);
            const state = await waitForPublish(projectId!);
            if (state === "done") { await loadProjectModel(); notify("annotation placed", "success"); }
            else notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
            await reloadModelPins();
          } catch (e) { notify(`annotate failed: ${(e as Error).message}`, "error"); }
        });
      });
      annotBtn.title = "Place a 2D text note / tag / callout as an IfcAnnotation at the last-clicked point — "
        + "round-trips as real IFC and feeds the drawing generator.";

      // UX-2 — live guide line: a dashed rubber line + anchor dot from a pending first point to the
      // cursor while a two-click annotation flow (dimension / revision cloud) waits for its second
      // click — the drafter sees exactly what's being measured before committing.
      const setGuideAnchor = (from: THREE.Vector3 | null) => {
        if (annotGuide) {
          viewer.world.scene.three.remove(annotGuide.grp);
          annotGuide.grp.traverse((o) => {
            const m = o as THREE.Mesh;
            if (m.geometry) m.geometry.dispose();
            if (m.material) (m.material as THREE.Material).dispose();
          });
          annotGuide = null;
        }
        if (!from) return;
        const grp = new THREE.Group(); grp.name = "annot-guide";
        const dot = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 10),
          new THREE.MeshBasicMaterial({ color: 0xffd479, depthTest: false }));
        dot.position.copy(from);
        const geo = new THREE.BufferGeometry().setFromPoints([from.clone(), from.clone()]);
        const line = new THREE.Line(geo, new THREE.LineDashedMaterial({
          color: 0xffd479, dashSize: 0.4, gapSize: 0.25, depthTest: false }));
        line.computeLineDistances();
        grp.add(dot, line);
        viewer.world.scene.three.add(grp);
        annotGuide = { grp, line };
      };
      if (!guideWired) {                    // install the cursor tracker exactly once (see PERF-4 note)
        guideWired = true;
        container.addEventListener("pointermove", (e) => {
          if (!annotGuide) return;
          const p = screenToGround(e);
          if (!p) return;
          const pos = annotGuide.line.geometry.attributes.position as THREE.BufferAttribute;
          pos.setXYZ(1, p.x, p.y, p.z); pos.needsUpdate = true;
          annotGuide.line.computeLineDistances();
        });
      }

      // UX-2 — dimension: two-click flow (pick first point, then second → measured dimension annotation)
      let dimFrom: THREE.Vector3 | null = null;
      const dimBtn = toolBtn2("📐 Dimension (2 points)", async () => {
        if (!lastPoint) { notify("click a point in the model first", "error"); return; }
        if (!dimFrom) { dimFrom = lastPoint.clone(); setGuideAnchor(dimFrom); notify("first point set — click the second point, then press Dimension again", "info"); return; }
        const a: [number, number] = [dimFrom.x, -dimFrom.z], b: [number, number] = [lastPoint.x, -lastPoint.z];
        dimFrom = null; setGuideAnchor(null);
        await withLoading(container, "placing dimension + republishing", async () => {
          try {
            const r = await api.addDimension(projectId!, a, b, { z: lastPoint!.y }, true);
            const state = await waitForPublish(projectId!);
            if (state === "done") { await loadProjectModel(); notify(`dimension ${(r as { distance_m?: number }).distance_m ?? ""} m placed`, "success"); }
            else notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
            await reloadModelPins();
          } catch (e) { notify(`dimension failed: ${(e as Error).message}`, "error"); }
        });
      });
      dimBtn.title = "Measure + annotate a dimension between two clicked points — a dimension line + the "
        + "distance label as an IfcAnnotation. Press once to set the first point, again for the second.";

      // UX-2 — revision cloud: two-corner flow (pick one corner, then the opposite → scalloped cloud + rev tag)
      let cloudFrom: THREE.Vector3 | null = null;
      const cloudBtn = toolBtn2("☁ Revision cloud (2 corners)", async () => {
        if (!lastPoint) { notify("click a corner of the region in the model first", "error"); return; }
        if (!cloudFrom) { cloudFrom = lastPoint.clone(); setGuideAnchor(cloudFrom); notify("first corner set — click the opposite corner, then press Revision cloud again", "info"); return; }
        const a: [number, number] = [cloudFrom.x, -cloudFrom.z], b: [number, number] = [lastPoint.x, -lastPoint.z];
        cloudFrom = null; setGuideAnchor(null);
        const tag = (prompt("Revision tag (e.g. a delta number) — leave blank for none:", "") || "").trim();
        await withLoading(container, "placing revision cloud + republishing", async () => {
          try {
            await api.addRevisionCloud(projectId!, [a, b], { tag: tag || undefined, z: lastPoint!.y }, true);
            const state = await waitForPublish(projectId!);
            if (state === "done") { await loadProjectModel(); notify("revision cloud placed", "success"); }
            else notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
            await reloadModelPins();
          } catch (e) { notify(`revision cloud failed: ${(e as Error).message}`, "error"); }
        });
      });
      cloudBtn.title = "Draw a revision cloud around a region as an IfcAnnotation (a scalloped outline + an "
        + "optional revision tag). Press once for the first corner, again for the opposite corner. Renders on the plan.";

      // UX-2 — element-aware tag: label auto-read from the SELECTED element (its Name / mark / type)
      const tagBtn = toolBtn2("🏷 Tag selected element", async () => {
        const host = selectedGuid;
        if (!host) { notify("select an element first, then tag it", "error"); return; }
        const override = (prompt("Tag label — leave blank to auto-read the element's name/mark/type:", "") || "").trim();
        await withLoading(container, "placing tag + republishing", async () => {
          try {
            const r = await api.addTag(projectId!, host, override ? { text: override } : {}, true);
            const state = await waitForPublish(projectId!);
            if (state === "done") { await loadProjectModel(); notify(`tagged "${(r as { label?: string }).label ?? ""}"`, "success"); }
            else notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
            await reloadModelPins();
          } catch (e) { notify(`tag failed: ${(e as Error).message}`, "error"); }
        });
      });
      tagBtn.title = "Tag the selected element with an IfcAnnotation whose label is auto-read from the element "
        + "(its Name, Pset mark, or type) and assigned to it — so the tag tracks the element. Renders on the plan.";

      // CONTENT-1 — site content library: place logistics / furniture / landscaping, each classified into
      // the right IFC class + phase (logistics = temporary, time-phases on the 4D slider).
      // UX-3: one unified, searchable Library palette — content parts (CONTENT-1) + family types (W10-1)
      // in a single filterable list; click an item to place it at an E,N point; import detailed meshes.
      const contentBtn = toolBtn2("📚 Content & family library", () => withLoading(container, "Loading the library", async () => {
        let cat, fams;
        try {
          [cat, fams] = await Promise.all([
            api.contentCatalog(),
            api.familyCatalog().catch(() => ({ count: 0, categories: {} as Record<string, FamilyDef[]> })),
          ]);
        } catch (e) { notify(`library failed: ${(e as Error).message}`, "error"); return; }

        const placeAt = (label: string, fn: (e: number, n: number) => Promise<unknown>) => async () => {
          const dflt = lastPoint ? `${lastPoint.x.toFixed(1)}, ${(-lastPoint.z).toFixed(1)}` : "0, 0";
          const v = await askText(`Place ${label}`, { label: "Location E, N (metres):", value: dflt });
          if (!v) return;
          const parts = v.split(",").map((s) => parseFloat(s.trim()));
          if (parts.length < 2 || parts.some((n) => !isFinite(n))) { notify("enter E, N", "error"); return; }
          await withLoading(container, `placing ${label} + republishing`, async () => {
            try {
              await fn(parts[0]!, parts[1]!);
              const state = await waitForPublish(projectId!);
              if (state === "done") { await loadProjectModel(); notify(`placed ${label}`, "success"); }
              else notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
              await reloadModelPins();
            } catch (e) { notify(`place failed: ${(e as Error).message}`, "error"); }
          });
        };

        type LibItem = { key: string; label: string; sub: string; cls: string; cat: string;
                         kind: "content" | "type"; search: string; onPlace: () => Promise<void> };
        const items: LibItem[] = [];
        for (const [group, gitems] of Object.entries(cat!.groups)) {
          for (const it of gitems) {
            const nm = it.key.replace(/_/g, " ");
            items.push({ key: `content:${it.key}`, label: nm + (it.phase === "temporary" ? " ⏱" : ""),
              sub: `${it.ifc_class.replace("Ifc", "")} · ${group}${it.phase ? ` · ${it.phase}` : ""}`,
              cls: it.ifc_class.toLowerCase(), cat: group.toLowerCase(), kind: "content",
              search: `${nm} ${it.ifc_class} ${it.classification} ${it.phase || ""} ${group} content`.toLowerCase(),
              onPlace: placeAt(nm, (e, n) => api.placeContent(projectId!, it.key, [e, n], undefined, true)) });
          }
        }
        for (const f of Object.values(fams!.categories).flat() as FamilyDef[]) {
          items.push({ key: `type:${f.key}`, label: f.label,
            sub: `${f.ifc_class.replace("Ifc", "")} · ${f.category} · type`,
            cls: f.ifc_class.toLowerCase(), cat: f.category.toLowerCase(), kind: "type",
            search: `${f.label} ${f.key} ${f.ifc_class} ${f.category} family type`.toLowerCase(),
            onPlace: placeAt(f.label, (e, n) => api.placeFamily(projectId!, f.key, [e, n])) });
        }
        // UX-3: a Recent bucket — the last handful of placed items, most-recent first (per-project)
        const RECENT_KEY = `lib-recent:${projectId}`;
        const readRecent = (): string[] => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; } };
        const pushRecent = (k: string) => {
          const r = [k, ...readRecent().filter((x) => x !== k)].slice(0, 6);
          try { localStorage.setItem(RECENT_KEY, JSON.stringify(r)); } catch { /* quota */ }
        };
        for (const it of items) { const orig = it.onPlace; it.onPlace = async () => { pushRecent(it.key); await orig(); }; }

        showResult("📚 Library", (body) => {
          body.appendChild(resultNote(`<b>${items.length}</b> library items — content parts + family types. `
            + `Search, then click to place at an E,N point (defaults to the last picked point). Import a `
            + `detailed mesh (glTF/OBJ/STL) below to place it auto-classified as the right IFC.`, ""));
          // import a detailed mesh → auto-detect category → placed as the right IFC
          const imp = document.createElement("div"); imp.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 8px";
          const impLbl = document.createElement("span"); impLbl.className = "meta"; impLbl.textContent = "⬆ Import mesh (auto-classified):";
          const catIn = document.createElement("input"); catIn.className = "portal-filter"; catIn.placeholder = "category (auto)"; catIn.style.cssText = "width:110px;font-size:11px";
          const fileIn = document.createElement("input"); fileIn.type = "file"; fileIn.accept = ".glb,.gltf,.obj,.stl,.ply"; fileIn.style.fontSize = "11px";
          fileIn.onchange = async () => {
            const f = fileIn.files?.[0]; if (!f) return;
            const eN = lastPoint ? lastPoint.x : 0, nN = lastPoint ? -lastPoint.z : 0;
            await withLoading(container, `importing ${f.name} + republishing`, async () => {
              try {
                const res = await api.importContent(projectId!, f, { category: catIn.value.trim() || undefined, e: eN, n: nN });
                const state = await waitForPublish(projectId!);
                if (state === "done") { await loadProjectModel(); notify(`imported as ${res.category} (${res.ifc_class}, ${res.faces} faces)`, "success"); }
                else notify(`imported — publish ${state}`, state === "error" ? "error" : "info");
                await reloadModelPins();
              } catch (err) { notify(`import failed: ${(err as Error).message}`, "error"); }
              finally { fileIn.value = ""; }
            });
          };
          imp.append(impLbl, catIn, fileIn); body.appendChild(imp);

          // searchable unified list — supports `type:` / `class:` / `category:` / `discipline:` operators
          const search = document.createElement("input"); search.className = "portal-filter";
          search.placeholder = "Search — or type:wall · class:ifccolumn · category:furniture · discipline:…";
          search.style.cssText = "width:100%;margin:2px 0 6px;font-size:12px";
          const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:3px;max-height:340px;overflow:auto";
          const mkBtn = (it: LibItem) => {
            const b2 = document.createElement("button"); b2.className = "mini-btn";
            b2.style.cssText = "text-align:left;width:100%";
            b2.innerHTML = `${it.label} <span class="meta" style="font-size:10px">— ${it.sub}</span>`;
            b2.onclick = () => { void it.onPlace().then(() => draw(search.value)); };
            return b2;
          };
          // parse a query into free terms + field:value operators (type→label/key, class→ifc class,
          // category→group, discipline→best-effort over the full search string)
          const matches = (it: LibItem, q: string): boolean => {
            for (const tok of q.trim().toLowerCase().split(/\s+/).filter(Boolean)) {
              const m = /^(type|class|category|cat|discipline|disc|tag):(.+)$/.exec(tok);
              if (m) {
                const [, op, val] = m;
                const ok = op === "type" ? (it.label.toLowerCase().includes(val!) || it.key.includes(val!))
                  : op === "class" ? it.cls.includes(val!)
                  : (op === "category" || op === "cat") ? it.cat.includes(val!)
                  : it.search.includes(val!);            // discipline/tag → full-text fallback
                if (!ok) return false;
              } else if (!it.search.includes(tok)) return false;
            }
            return true;
          };
          const draw = (q: string) => {
            list.innerHTML = "";
            const ql = q.trim();
            if (!ql) {
              const recentKeys = readRecent();
              const recent = recentKeys.map((k) => items.find((it) => it.key === k)).filter(Boolean) as LibItem[];
              if (recent.length) {
                const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-size:10px;opacity:.7;margin-top:2px";
                h.textContent = "RECENT"; list.appendChild(h);
                for (const it of recent) list.appendChild(mkBtn(it));
                const sep = document.createElement("div"); sep.className = "meta"; sep.style.cssText = "font-size:10px;opacity:.7;margin-top:4px";
                sep.textContent = "ALL"; list.appendChild(sep);
              }
            }
            const shown = items.filter((it) => !ql || matches(it, ql));
            for (const it of shown) list.appendChild(mkBtn(it));
            if (!shown.length) { const n = document.createElement("div"); n.className = "meta"; n.textContent = "No items match."; list.appendChild(n); }
          };
          search.oninput = () => draw(search.value);
          body.append(search, list);
          draw("");
        });
      }));
      contentBtn.title = "Browse + place the unified library — content parts (site logistics / furniture / "
        + "landscaping) and family types — search by name, IFC class, or category, then click to place at an "
        + "E,N point. Logistics time-phase on the 4D slider.";

      const advWrap = document.createElement("div");
      advWrap.style.cssText = "display:flex;flex-direction:column;gap:inherit";
      advWrap.append(detailBtn, autoDetailBtn, basePlateBtn, shearTabBtn, rebarBtn, cageChkBtn, bbsBtn, mepFittingBtn, fireBtn, faBtn, commsBtn, riserBtn, mepSysBtn, curtainBtn, slopeBtn, meshBtn, ifcCodeBtn);

      // UX-1b: surface the interactive annotation tools + the content library as their own labelled groups
      // (the Annotate + Library ribbon groups), instead of burying them in the Advanced-fabrication fold.
      const annotateHead = document.createElement("div"); annotateHead.className = "section-title";
      annotateHead.style.marginTop = "8px"; annotateHead.textContent = "✍ Annotate";
      const annotateWrap = document.createElement("div"); annotateWrap.style.cssText = "display:flex;flex-direction:column;gap:inherit";
      annotateWrap.append(annotBtn, dimBtn, cloudBtn, tagBtn);
      const libHead = document.createElement("div"); libHead.className = "section-title";
      libHead.style.marginTop = "8px"; libHead.textContent = "📚 Library";
      const libWrap = document.createElement("div"); libWrap.style.cssText = "display:flex;flex-direction:column;gap:inherit";
      libWrap.append(contentBtn);
      const advKey = "massing.viewer.advancedTools";
      let advOpen = false;
      try { advOpen = localStorage.getItem(advKey) === "1"; } catch { /* storage blocked */ }
      const advToggle = toolBtn2("🔧 Advanced fabrication tools ▾", () => {
        advOpen = !advOpen;
        advWrap.hidden = !advOpen;
        advToggle.textContent = `🔧 Advanced fabrication tools ${advOpen ? "▴" : "▾"}`;
        try { localStorage.setItem(advKey, advOpen ? "1" : "0"); } catch { /* storage blocked */ }
      });
      advToggle.title = "Show the LOD-350/400 fabrication + detailing tools (steel connections, rebar, MEP "
        + "fittings, curtain wall, auto-detail). Hidden by default to keep the everyday toolset simple.";
      advWrap.hidden = !advOpen;
      advToggle.textContent = `🔧 Advanced fabrication tools ${advOpen ? "▴" : "▾"}`;

      // S4 — model-level undo / redo: every authoring edit versions the source IFC, so undo restores the
      // prior version (GUID-stable). Buttons reflect the server-side history depth.
      const undoRow = document.createElement("div"); undoRow.style.cssText = "display:flex;gap:6px";
      const undoBtn = document.createElement("button"); undoBtn.className = "mini-btn"; undoBtn.textContent = "↶ Undo"; undoBtn.style.flex = "1";
      const redoBtn = document.createElement("button"); redoBtn.className = "mini-btn"; redoBtn.textContent = "↷ Redo"; redoBtn.style.flex = "1";
      undoRow.append(undoBtn, redoBtn);
      const refreshUndo = async () => {
        try { const st = await api.editHistory(projectId!); undoBtn.disabled = !st.can_undo; redoBtn.disabled = !st.can_redo; }
        catch { undoBtn.disabled = redoBtn.disabled = true; }
      };
      const doUndoRedo = (redo: boolean) => withLoading(container, redo ? "redoing + republishing" : "undoing + republishing", async () => {
        try {
          await (redo ? api.editRedo(projectId!) : api.editUndo(projectId!));
          const state = await waitForPublish(projectId!);
          if (state === "done") { await loadProjectModel(); notify(redo ? "redone" : "undone", "success"); }
          else notify(`${redo ? "redone" : "undone"} — publish ${state}`, state === "error" ? "error" : "info");
          await reloadModelPins(); await refreshUndo();
        } catch (e) { notify(`${redo ? "redo" : "undo"} failed: ${(e as Error).message}`, "error"); }
      });
      undoBtn.onclick = () => void doUndoRedo(false);
      redoBtn.onclick = () => void doUndoRedo(true);
      void refreshUndo();

      glBody.append(status, levelSel, undoRow, load, toggle, addLvl, addRooms, furnish, typesBtn, groupsBtn,
        phaseBtn, queryBtn, lodBtn, asBuiltBtn, planBtn, sheetBtn, pdfBtn, schedBtn, schedPdfBtn, manualBtn, sectBtn,
        annotateHead, annotateWrap, libHead, libWrap,
        advToggle, advWrap, manage, levelsMgr);
    }

    // --- persona-ordered tool sections ---------------------------------------
    const builders: Record<string, () => void> = {
      exports: () => {
        const b = section("exports", "Document · Exports & issue", { requires: "sourceIfc", tool: true });
        if (!b) return;
        for (const [label, file] of [["Quantity takeoff (QTO/5D)", "qto"], ["COBie", "cobie"], ["Space schedule", "spaces"], ["4D schedule", "schedule"]] as const)
          b.appendChild(toolBtn2(`↓ ${label}`, () => window.open(api.url(`/projects/${projectId}/exports/${file}.xlsx`), "_blank")));
        // gbXML — spaces + envelope areas for OpenStudio / EnergyPlus / IES energy modelling
        const gbx = toolBtn2("↓ gbXML (energy model)", () => window.open(api.url(`/projects/${projectId}/exports/model.gbxml`), "_blank"));
        gbx.title = "Green Building XML — spaces + areas/volumes from the IFC geometry, to seed an energy model (OpenStudio/EnergyPlus/IES). Simplified: building-level envelope, not per-space surfaces.";
        b.appendChild(gbx);
        // discipline quantities — reinforcement tonnage, MEP linear runs, structural volume (Koh rebar viz / WithRebar)
        b.appendChild(toolBtn2("🔩 Discipline quantities", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          try {
            const q = await api.disciplineQuantities(projectId);
            showResult("Discipline quantities", (body) => {
              body.appendChild(kvTable([
                { k: `Reinforcement${q.rebar.estimated ? " (est. from volume)" : ""}`, v: `${q.rebar.tonnes} t · ${q.rebar.count} bars` },
                { k: "Ductwork", v: `${q.mep.duct_m} m · ${q.mep.counts.duct} seg` },
                { k: "Piping", v: `${q.mep.pipe_m} m · ${q.mep.counts.pipe} seg` },
                { k: "Cable / carrier", v: `${q.mep.cable_m} m · ${q.mep.counts.cable} seg` },
                { k: "MEP fittings", v: String(q.mep.counts.fittings) },
                { k: "Structural element volume", v: `${q.structure.element_volume_m3} m³` },
              ]));
            });
          } catch (e) { notify(`quantities failed: ${(e as Error).message}`, "error"); }
        }));
        // full turnover deliverable: as-built IFC + COBie/QTO/spaces + status PDF + closeout records
        const pkg = toolBtn2("📦 Closeout package (.zip)", () => window.open(api.url(`/projects/${projectId}/closeout/package.zip`), "_blank"));
        pkg.title = "Everything for handover in one ZIP: as-built model, data workbooks, status report, closeout records";
        b.appendChild(pkg);
        // geometry / model interchange exports (EXPORT)
        const ifcOut = toolBtn2("⬇ Export IFC (source of truth)", () => window.open(api.modelIfcUrl(projectId!), "_blank"));
        ifcOut.title = "First-class IFC re-export — the current authored source IFC, GUID-stable, round-trips through any openBIM tool";
        b.appendChild(ifcOut);
        const glb = toolBtn2("⬇ Export 3D (.glb)", () => window.open(api.modelGlbUrl(projectId!), "_blank"));
        glb.title = "Binary glTF — the compact single-file 3D form Blender / three.js / game engines import directly";
        b.appendChild(glb);
        const gltf = toolBtn2("⬇ Export 3D (.gltf)", () => window.open(api.modelGltfUrl(projectId!), "_blank"));
        gltf.title = "Self-contained glTF 2.0 JSON (interchange)";
        b.appendChild(gltf);
        // TAKEOFF-2D — quantify from an uploaded drawing (no model needed), feeds the 5D estimate
        const to2d = toolBtn2("📐 2D takeoff (from a drawing)", () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          openTakeoff2d({
            quantify: (regions, sc, unit) => api.takeoff2d(projectId!, regions, sc, unit),
            notify,
          });
        });
        to2d.title = "Upload a PDF-page image / scan, calibrate the scale, trace or flood-fill regions → priced quantities into the 5D estimate";
        b.appendChild(to2d);
      },
      qa: () => {
        const b = section("qa", "Analyze & Coordinate · clash / QA", { requires: "sourceIfc", tool: true });
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px";
        b.appendChild(toolBtn2("⚡ Run clash (struct)", () => withLoading(container, "Running clash detection", async () => {
          const r = await api.runClash(pid, { a: "IfcBeam,IfcSlab", b: "IfcColumn", min_volume: 0.05 });
          out.textContent = `${r.count} clashes · ${r.created_topics} topics`;
          toast(`Clash: ${r.count} found, ${r.created_topics} topics created`, r.count ? "info" : "success");
          await refreshIssues(); await reloadModelPins();
          showResult("Clash detection", (body) => {
            body.appendChild(resultNote(`<b>${r.count}</b> clashes found · <b>${r.created_topics}</b> RFI topics created.`, r.count ? "bad" : "ok"));
            body.appendChild(toolBtn2("Open Issues panel", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
          });
        })));
        // A4: a compact scene digest — what's in the model, one glance (also grounds the AI command bar)
        b.appendChild(toolBtn2("🔎 Model digest (what's in the model)", () => withLoading(container, "Summarising the model", async () => {
          let d;
          try { d = await api.sceneDigest(pid); }
          catch { toast("Needs a source IFC", "error"); return; }
          out.textContent = `${d.totals.elements} elts · ${d.totals.storeys} storey(s)`;
          showResult("Model digest", (body) => {
            body.appendChild(resultNote(d!.prose, ""));
            const top = Object.entries(d!.by_class).slice(0, 10);
            if (top.length) body.appendChild(kvTable(top.map(([c, n]) => ({ k: c.replace(/^Ifc/, ""), v: String(n) }))));
            if (d!.mep.systems) body.appendChild(resultNote(`<b>MEP</b> — ${d!.mep.systems} system(s); `
              + Object.entries(d!.mep.by_discipline).map(([k, v]) => `${k} (${v.systems})`).join(", ")
              + (d!.mep.has_fire_protection ? " · fire-protection present" : ""), ""));
            const phased = Object.entries(d!.phasing).filter(([k, v]) => v && k !== "UNSET");
            if (phased.length) body.appendChild(resultNote(`<b>Phasing</b> — ` + phased.map(([k, v]) => `${v} ${k.toLowerCase()}`).join(", "), ""));
            if (d!.hygiene.issues) body.appendChild(resultNote(`<b>${d!.hygiene.issues}</b> model-hygiene issue(s) — see Model Health.`, "bad"));
          });
        })));
        b.appendChild(toolBtn2("🩺 Model Health (all checks, one score)", () => withLoading(container, "Scoring model health", async () => {
          let r;
          try { r = await api.modelHealth(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = r.overall_score != null ? `health ${r.overall_score} · ${r.band}` : "no model data";
          const dot: Record<string, string> = { good: "🟢", warn: "🟡", poor: "🔴", na: "⚪" };
          showResult("Model Health", (body) => {
            const tone = r!.overall_score == null ? "" : r!.overall_score >= 80 ? "ok" : r!.overall_score < 50 ? "bad" : "";
            body.appendChild(resultNote(r!.overall_score != null
              ? `Composite <b>${r!.overall_score}/100</b> — <b>${r!.band}</b> (${r!.scored_lenses} of ${r!.lenses.length} checks scored).`
              : "No model-quality inputs yet — load a model and log coordination / verification to score.", tone));
            body.appendChild(kvTable(r!.lenses.map((l) => ({
              k: `${dot[l.status] || "⚪"} ${l.label}`,
              v: `${l.score != null ? `${l.score}/100` : "n/a"} — ${l.headline}`,
            }))));
            const note = document.createElement("div"); note.className = "meta";
            note.style.cssText = "margin-top:8px;font-size:11px";
            note.textContent = "One score over integrity/hygiene (Model QA), ISO 19650 KPIs (BIM scorecard), "
              + "clash coordination, and verified-as-built. Each lens has its own tool in this rail (or the Report Center) to act on it.";
            body.appendChild(note);
          });
        })));
        // SURF-4: element data-QA (`/elements/qa`) was backed but unsurfaced — the per-rule
        // required-property completeness check (missing GUIDs are click-to-select).
        b.appendChild(toolBtn2("🔍 Data QA (required-property completeness)", () => withLoading(container, "Checking element data quality", async () => {
          let r;
          try { r = await api.dataQa(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = `data QA ${r.compliant_pct}% (${r.compliant}/${r.total})`;
          showResult("Element data QA", (body) => {
            const tone = r!.compliant_pct >= 90 ? "ok" : r!.compliant_pct < 60 ? "bad" : "";
            body.appendChild(resultNote(`<b>${r!.compliant_pct}%</b> of ${r!.total} elements carry their required properties `
              + `(${r!.noncompliant} non-compliant).`, tone));
            for (const rule of r!.rules) {
              // HARDEN-2 (B6): /elements/qa severities are "required"/"recommended" — the old
              // high/medium/low map never matched, so every row fell back to "•".
              const sev: Record<string, string> = { required: "🔴", recommended: "🟡" };
              const line = resultNote(`${sev[rule.severity] || "•"} <b>${rule.label}</b> — ${rule.present} present · <b>${rule.missing}</b> missing`,
                rule.missing ? "" : "ok");
              if (rule.missing && rule.missing_guids.length) {
                const pick = document.createElement("a"); pick.href = "#"; pick.textContent = " select missing";
                pick.style.cssText = "font-size:11px;margin-left:6px";
                pick.onclick = async (e) => { e.preventDefault(); await selectMap(await sets.fromGuids(rule.missing_guids.slice(0, 200))); };
                line.appendChild(pick);
              }
              body.appendChild(line);
            }
          });
        })));
        b.appendChild(toolBtn2("🔎 Query-select (filter language)", () => {
          showResult("Query-select — selector language", (body) => {
            body.appendChild(resultNote("Select elements by a selector string, then isolate them in 3D. "
              + "Combine terms with <b>&amp;</b>: <code>IfcWall &amp; Pset_WallCommon.FireRating=2HR &amp; storey=L3</code>. "
              + "Operators: <code>= != &gt;= &lt;= &gt; &lt; ~</code> (contains); a bare <code>Pset.Prop</code> tests existence.", ""));
            const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:6px 0";
            const inp = document.createElement("input"); inp.className = "portal-filter"; inp.style.cssText = "flex:1 1 240px;min-width:0;font-size:12px";
            inp.placeholder = "IfcWall & storey=L3"; inp.value = "IfcWall";
            const run = document.createElement("button"); run.className = "mini-btn on"; run.textContent = "Run";
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "4px";
            row.append(inp, run); body.append(row, status);
            const exec = async () => {
              const query = inp.value.trim(); if (!query) return;
              status.textContent = "querying…";
              try {
                const r = await api.modelSelect(pid, query);
                status.innerHTML = `<b>${r.matched}</b> matched${r.truncated ? " (showing first " + r.guids.length + ")" : ""}`;
                if (r.guids.length) await layerMgr.isolateGuids(r.guids);
                else { await layerMgr.showAll(); notify("no elements matched", "info"); }
              } catch (e) { status.textContent = `query error: ${(e as Error).message}`; }
            };
            run.onclick = () => void exec();
            inp.onkeydown = (e) => { if (e.key === "Enter") void exec(); };
          });
        }));
        b.appendChild(toolBtn2("★ Smart views (saved presets)", () => {
          showResult("Smart views — saved property-driven presets", (body) => {
            body.appendChild(resultNote("Save a QUERY-DSL selector as a reusable view — <b>isolate</b>, "
              + "<b>colour</b>, or <b>hide</b> the matching elements. Presets persist with the project so the "
              + "whole team re-applies the same coordination views.", ""));
            const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:4px;margin:6px 0";
            body.appendChild(list);
            const apply = async (v: { id?: string }) => {
              if (!v.id) return;
              try {
                const r = await api.smartViewRun(pid, v.id);
                if (r.error) { notify(`selector error: ${r.error}`, "error"); return; }
                if (!r.guids.length) { await layerMgr.showAll(); notify("no elements matched", "info"); return; }
                if (r.mode === "color") { await layerMgr.colorGuids(r.guids, r.color || "#ffb020"); }
                else if (r.mode === "hide") { const ly = await layerMgr.addGuidLayer(`hide:${r.name}`, r.guids); await layerMgr.setVisible(ly.id, false); }
                else { await layerMgr.isolateGuids(r.guids); }
                notify(`${r.name}: ${r.matched} element(s) · ${r.mode}`, "success");
              } catch (e) { notify((e as Error).message, "error"); }
            };
            const refresh = async () => {
              list.textContent = "loading…";
              let views: { id?: string; name: string; selector: string; mode: string; color?: string | null }[] = [];
              try { views = (await api.smartViews(pid)).views; }
              catch (e) { list.textContent = `failed: ${(e as Error).message}`; return; }
              list.innerHTML = "";
              if (!views.length) { list.appendChild(resultNote("No saved views yet — add one below.", "")); }
              for (const v of views) {
                const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;align-items:center";
                const dot = v.mode === "color" ? `<span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${escapeHtml(v.color || "#ffb020")};margin-right:4px"></span>` : "";
                const label = document.createElement("span"); label.style.cssText = "flex:1;font-size:12px";
                label.innerHTML = `${dot}<b>${escapeHtml(v.name)}</b> <span class="meta">${escapeHtml(v.mode)} · ${escapeHtml(v.selector)}</span>`;
                const go = document.createElement("button"); go.className = "mini-btn on"; go.textContent = "Apply"; go.onclick = () => void apply(v);
                const del = document.createElement("button"); del.className = "mini-btn"; del.textContent = "✕"; del.title = "delete";
                del.onclick = async () => {
                  try { await api.smartViewsSave(pid, views.filter((x) => x.id !== v.id) as never); await refresh(); }
                  catch (e) { notify((e as Error).message, "error"); }
                };
                row.append(label, go, del); list.appendChild(row);
              }
            };
            // add-new row: name + selector + mode (+ colour when mode=color)
            const add = document.createElement("div"); add.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px;border-top:1px solid var(--line,#3a3f47);padding-top:8px";
            const nameI = document.createElement("input"); nameI.className = "portal-filter"; nameI.placeholder = "view name"; nameI.style.cssText = "flex:1 1 120px;min-width:0;font-size:12px";
            const selI = document.createElement("input"); selI.className = "portal-filter"; selI.placeholder = "IfcDuctSegment & storey=L3"; selI.style.cssText = "flex:2 1 200px;min-width:0;font-size:12px";
            const modeS = document.createElement("select"); modeS.className = "portal-filter"; modeS.style.fontSize = "12px";
            for (const m of ["isolate", "color", "hide"]) { const o = document.createElement("option"); o.value = m; o.textContent = m; modeS.appendChild(o); }
            const colorI = document.createElement("input"); colorI.type = "color"; colorI.value = "#ffb020"; colorI.style.display = "none";
            modeS.onchange = () => { colorI.style.display = modeS.value === "color" ? "" : "none"; };
            const save = document.createElement("button"); save.className = "mini-btn on"; save.textContent = "＋ Save view";
            save.onclick = async () => {
              const name = nameI.value.trim(), selector = selI.value.trim();
              if (!name || !selector) { notify("name + selector required", "error"); return; }
              try {
                const cur = (await api.smartViews(pid)).views;
                const nv = { name, selector, mode: modeS.value as "isolate" | "color" | "hide",
                  ...(modeS.value === "color" ? { color: colorI.value } : {}) };
                await api.smartViewsSave(pid, [...cur, nv] as never);
                nameI.value = ""; selI.value = ""; await refresh();
                notify("view saved", "success");
              } catch (e) { notify((e as Error).message, "error"); }
            };
            add.append(nameI, selI, modeS, colorI, save); body.appendChild(add);
            void refresh();
          });
        }));
        b.appendChild(toolBtn2("⇄ Property round-trip (CSV/XLSX)", () => {
          showResult("Property round-trip — export · edit · re-import", (body) => {
            body.appendChild(resultNote("The daily openBIM workflow: export a GUID-keyed property table, edit it in "
              + "Excel/Sheets, upload it back — a <b>dry-run diff</b> shows exactly what would change before anything "
              + "is written (GUID-stable <code>set_props_by_guid</code> recipe + republish).", ""));
            const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:6px 0";
            const propsI = document.createElement("input"); propsI.className = "portal-filter"; propsI.style.cssText = "flex:1 1 260px;min-width:0;font-size:12px";
            propsI.placeholder = "Pset_WallCommon.FireRating, Pset_WallCommon.LoadBearing"; propsI.value = "Pset_WallCommon.FireRating";
            const exp = document.createElement("button"); exp.className = "mini-btn on"; exp.textContent = "⤓ Export CSV";
            const upLabel = document.createElement("label"); upLabel.className = "mini-btn"; upLabel.textContent = "⇪ Upload edited"; upLabel.style.cursor = "pointer";
            const upInput = document.createElement("input"); upInput.type = "file"; upInput.accept = ".csv,.xlsx"; upInput.style.display = "none";
            upLabel.appendChild(upInput);
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "4px";
            const diffBox = document.createElement("div"); diffBox.style.cssText = "margin-top:6px;max-height:40vh;overflow:auto";
            row.append(propsI, exp, upLabel); body.append(row, status, diffBox);
            exp.onclick = async () => {
              const props = propsI.value.split(",").map((s) => s.trim()).filter(Boolean);
              if (!props.length) { notify("name at least one Pset.Prop column", "error"); return; }
              try { await api.roundtripExport(pid, props); status.textContent = "exported — edit the CSV, then upload it back"; }
              catch (e) { status.textContent = `export failed: ${(e as Error).message}`; }
            };
            upInput.onchange = async () => {
              const f = upInput.files?.[0]; if (!f) return;
              status.textContent = "computing dry-run diff…"; diffBox.replaceChildren();
              try {
                const d = await api.roundtripDiff(pid, f);
                status.innerHTML = `<b>${d.changes.length}</b> change(s) across ${d.checked} rows`
                  + (d.unknown_guids.length ? ` · <b>${d.unknown_guids.length}</b> unknown GUID(s) skipped` : "")
                  + ` · ${d.unchanged} unchanged`;
                if (!d.changes.length) return;
                const tbl = document.createElement("table"); tbl.className = "result-table";
                for (const c of d.changes.slice(0, 300)) {
                  const tr = document.createElement("tr");
                  tr.innerHTML = `<td class="k">${escapeHtml(c.guid.slice(0, 8))}… ${escapeHtml(c.pset)}.${escapeHtml(c.prop)}</td>`
                    + `<td class="v">${escapeHtml(c.old ?? "—")} → <b>${escapeHtml(c.new)}</b></td>`;
                  tbl.appendChild(tr);
                }
                diffBox.appendChild(tbl);
                const apply = document.createElement("button"); apply.className = "mini-btn on"; apply.style.marginTop = "6px";
                apply.textContent = `✓ Apply ${d.changes.length} change(s) + republish`;
                apply.onclick = async () => {
                  apply.disabled = true; status.textContent = "applying via set_props_by_guid…";
                  try {
                    const r = await api.editIfc(pid, "set_props_by_guid", { changes: d.changes });
                    status.textContent = `applied ${r.changed} change(s) — model republishing`;
                    notify("properties applied — reload the model to see them", "success");
                  } catch (e) { status.textContent = `apply failed: ${(e as Error).message}`; apply.disabled = false; }
                };
                diffBox.appendChild(apply);
              } catch (e) { status.textContent = `diff failed: ${(e as Error).message}`; }
              finally { upInput.value = ""; }
            };
          });
        }));
        b.appendChild(toolBtn2("✔ Rule check (rule library)", () => withLoading(container, "Checking the rule library", async () => {
          let r;
          try { r = await api.rulesRun(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          if (!r.model_scored) { toast(r.note || "no model loaded", "info"); return; }
          out.textContent = `rules: ${r.failing_rules ?? 0}/${r.total_rules} failing`;
          showResult("Rule library check", (body) => {
            const bySev = r!.by_severity || {};
            body.appendChild(resultNote(`<b>${r!.failing_rules ?? 0}</b> of ${r!.total_rules} rules failing · `
              + `${r!.total_violations ?? 0} violations` + (bySev.high ? ` · 🔴 ${bySev.high} high` : "")
              + (bySev.medium ? ` · 🟡 ${bySev.medium} medium` : "") + (bySev.low ? ` · ⚪ ${bySev.low} low` : ""),
            (r!.failing_rules ?? 0) ? "" : "ok"));
            const sev: Record<string, string> = { high: "🔴", medium: "🟡", low: "⚪" };
            for (const rule of r!.rules) {
              const icon = rule.status === "pass" ? "✅" : rule.status === "n/a" ? "➖" : (sev[rule.severity] || "•");
              const line = resultNote(`${icon} <b>${escapeHtml(rule.name)}</b> — ${rule.passed}/${rule.scoped} pass`
                + (rule.failed ? ` · <b>${rule.failed}</b> fail` : ""), rule.status === "fail" ? "" : "ok");
              if (rule.failed && rule.fail_guids.length) {
                const pick = document.createElement("a"); pick.href = "#"; pick.textContent = " isolate failures";
                pick.style.cssText = "font-size:11px;margin-left:6px";
                pick.onclick = (e) => { e.preventDefault(); void layerMgr.isolateGuids(rule.fail_guids.slice(0, 500)); };
                line.appendChild(pick);
              }
              body.appendChild(line);
            }
          });
        })));
        b.appendChild(toolBtn2("⛶ Geometry check (clearance/egress)", () => withLoading(container, "Running geometric checks", async () => {
          let r;
          try { r = await api.rulesGeometryRun(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = `geometry: ${r.violation_total} violation(s)`;
          showResult("Geometric rule check", (body) => {
            const bySev = r!.by_severity || {};
            body.appendChild(resultNote(`<b>${r!.violation_total}</b> violation(s)`
              + (bySev.high ? ` · 🔴 ${bySev.high} high` : "") + (bySev.medium ? ` · 🟡 ${bySev.medium} medium` : "")
              + (bySev.low ? ` · ⚪ ${bySev.low} low` : ""), r!.violation_total ? "" : "ok"));
            for (const chk of r!.results) {
              const line = resultNote(`${chk.passed ? "✅" : "🔴"} <b>${escapeHtml(chk.name)}</b> — `
                + `${chk.checked} checked, ${chk.violations.length} violation(s)`
                + (chk.note ? ` · ${escapeHtml(chk.note)}` : ""), chk.passed ? "ok" : "");
              if (chk.violations.length) {
                const pick = document.createElement("a"); pick.href = "#"; pick.textContent = " isolate";
                pick.style.cssText = "font-size:11px;margin-left:6px";
                const guids = chk.violations.map((v) => v.guid);
                pick.onclick = (e) => { e.preventDefault(); void layerMgr.isolateGuids(guids.slice(0, 500)); };
                line.appendChild(pick);
              }
              body.appendChild(line);
              for (const v of chk.violations.slice(0, 12)) {
                body.appendChild(resultNote(`&nbsp;&nbsp;${escapeHtml(v.name || v.guid.slice(0, 8) + "…")} — ${escapeHtml(v.detail)}`, ""));
              }
            }
            body.appendChild(resultNote("AABB-level checks on the clash geometry path: door/equipment approach clearance, straight-line egress distance, accessible clear width. Property rules live in ✔ Rule check.", ""));
          });
        })));
        b.appendChild(toolBtn2("▢ Model CI (quality gate)", () => withLoading(container, "Running model CI checks", async () => {
          let r;
          try { r = await api.ciRun(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          const mark: Record<string, string> = { pass: "✅", warn: "🟡", fail: "🔴", skip: "➖", none: "➖" };
          out.textContent = `CI: ${r.badge}`;
          showResult("Model CI — quality gate", (body) => {
            body.appendChild(resultNote(`Overall <b>${mark[r!.overall] || ""} ${escapeHtml(r!.badge)}</b>`
              + (r!.ran_at ? ` · ${escapeHtml(r!.ran_at)}` : "")
              + ` · ${r!.passed ?? 0}/${r!.total_checks ?? r!.checks.length} passed`,
            r!.overall === "fail" ? "bad" : r!.overall === "pass" ? "ok" : ""));
            for (const chk of r!.checks) {
              body.appendChild(resultNote(`${mark[chk.status] || "•"} <b>${escapeHtml(chk.label)}</b> — ${escapeHtml(chk.summary)}`,
                chk.status === "fail" ? "" : "ok"));
            }
            body.appendChild(resultNote("Checks compose the rule library + data-completeness gates; the badge is stored so every model version carries a quality gate. Add rules via the ✔ Rule check tool.", ""));
          });
        })));
        b.appendChild(toolBtn2("🔗 Coordinate clashes (grouped issues)", () => withLoading(container, "Running federated clash + coordination", async () => {
          let r;
          try { r = await api.clashFederated(pid, { coordinate: true }); }
          catch { toast("Federated clash needs ≥2 models — add one with “＋ Add discipline IFC”", "error"); return; }
          const co = r.coordination;
          out.textContent = co ? `${r.count} clashes → ${co.group_count} issues (${co.reduction}× reduction)` : `${r.count} clashes`;
          toast(co ? `${co.new} new · ${co.active} active · ${co.resolved} resolved · ${co.reappeared} reappeared` : "no clashes", r.count ? "info" : "success");
          await refreshIssues(); await reloadModelPins();
          showResult("Clash coordination", (body) => {
            if (!co) { body.appendChild(resultNote(`<b>${r!.count}</b> cross-model clashes.`, r!.count ? "bad" : "ok")); return; }
            body.appendChild(resultNote(`<b>${r!.count}</b> raw clashes grouped into <b>${co.group_count}</b> tracked coordination issues `
              + `(<b>${co.reduction}×</b> reduction) across <b>${r!.disciplines.join(" × ")}</b>.`, co.group_count ? "bad" : "ok"));
            body.appendChild(kvTable([
              { k: "New", v: String(co.new) }, { k: "Active (carried forward)", v: String(co.active) },
              { k: "Resolved (auto)", v: String(co.resolved) }, { k: "Reappeared (reopened)", v: String(co.reappeared) },
            ]));
            if (Object.keys(co.by_severity).length) {
              const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "By severity"; body.appendChild(h);
              body.appendChild(kvTable(Object.entries(co.by_severity).map(([k, v]) => ({ k, v: String(v) }))));
            }
            if (Object.keys(co.by_discipline).length) {
              const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "By discipline pair"; body.appendChild(h);
              body.appendChild(kvTable(Object.entries(co.by_discipline).map(([k, v]) => ({ k, v: String(v) }))));
            }
            body.appendChild(toolBtn2("📊 Coordination KPIs", () => withLoading(container, "Loading clash KPIs", async () => {
              const m = await api.clashMetrics(pid);
              showResult("Clash coordination KPIs", (kb) => {
                kb.appendChild(resultNote(`<b>${m.open}</b> open · <b>${m.closed}</b> closed · <b>${m.resolution_rate}%</b> resolved · `
                  + `reappearance <b>${m.reappearance_rate}%</b> over <b>${m.runs}</b> run(s).`, m.open ? "bad" : "ok"));
                kb.appendChild(kvTable([
                  { k: "Open aging 0–7d", v: String(m.aging["0-7"] ?? 0) }, { k: "8–14d", v: String(m.aging["8-14"] ?? 0) },
                  { k: "15–30d", v: String(m.aging["15-30"] ?? 0) }, { k: "30d+", v: String(m.aging["30+"] ?? 0) },
                ]));
                if (m.burn_down.length) {
                  const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "Run burn-down"; kb.appendChild(h);
                  kb.appendChild(kvTable(m.burn_down.map((x) => ({ k: x.run, v: `+${x.new} / −${x.resolved}${x.reappeared ? ` / ↻${x.reappeared}` : ""}` }))));
                }
              });
            })));
            body.appendChild(toolBtn2("Open Issues panel", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
          });
        })));
        b.appendChild(toolBtn2("📍 Field layout (points CSV / DXF)", () => withLoading(container, "Extracting layout setout points", async () => {
          let r;
          try { r = await api.layoutPoints(pid); }
          catch { toast("Field layout needs a source IFC with columns/grids", "error"); return; }
          out.textContent = `${r.count} setout points`;
          toast(r.count ? `${r.count} layout points ready to stake` : "no setout points found", r.count ? "info" : "success");
          showResult("Model → field layout", (body) => {
            body.appendChild(resultNote(`<b>${r!.count}</b> georeferenced setout points (grids + column/footing/`
              + `opening/wall) — E/N/Z with the IFC GlobalId in each Description, ready for total stations, `
              + `marking robots and floor printers.`, r!.count ? "ok" : "bad"));
            if (Object.keys(r!.by_class).length) body.appendChild(kvTable(Object.entries(r!.by_class).map(([k, v]) => ({ k: k.replace("Ifc", ""), v: String(v) }))));
            const dl = (label: string, href: string) => { const a = document.createElement("a"); a.className = "file-btn"; a.textContent = label; a.href = href; a.target = "_blank"; a.rel = "noopener"; a.style.marginRight = "6px"; return a; };
            const row = document.createElement("div"); row.style.margin = "8px 0";
            row.append(dl("⬇ PENZD CSV", api.layoutCsvUrl(pid, "PENZD")), dl("⬇ PNEZD CSV", api.layoutCsvUrl(pid, "PNEZD")), dl("⬇ DXF (printers)", api.layoutDxfUrl(pid)));
            body.appendChild(row);
            body.appendChild(resultNote("Field round-trip: stake/print these, shoot the as-installed positions "
              + "with a total station, then upload that CSV to verify deviation by point number.", "ok"));
          });
        })));
        b.appendChild(toolBtn2("🏗 Site logistics (4D timeline)", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          let resources: LogisticsResource[];
          try { resources = (await api.getLogistics(pid)).resources; }
          catch { toast("Could not load logistics", "error"); return; }
          logisticsOverlay.render(resources); logisticsOverlay.showAll();
          showResult("Site logistics — time-phased on the 4D timeline", (body) => {
            body.appendChild(resultNote(`Temporary construction resources (cranes / laydown / gates / fencing / haul routes) placed in project coordinates with a schedule window — they show + hide as the timeline advances. Click in the model first to set a point, then add a resource there. <b>${resources.length}</b> placed.`, "ok"));
            const list = document.createElement("div"); list.style.margin = "6px 0";
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "6px";
            const draw = () => {
              list.innerHTML = "";
              resources.forEach((r, i) => {
                const row = document.createElement("div"); row.className = "selset-row";
                const s = document.createElement("span"); s.className = "selset-name"; s.style.cursor = "default";
                s.textContent = `${r.kind} · ${r.label || r.id}${r.start ? ` · ${r.start}→${r.end || "…"}` : ""}`;
                const del = document.createElement("button"); del.className = "selset-del"; del.textContent = "✕";
                del.onclick = () => { resources.splice(i, 1); logisticsOverlay.render(resources); draw(); };
                row.append(s, del); list.appendChild(row);
              });
              if (!resources.length) { const e = document.createElement("div"); e.className = "meta"; e.textContent = "No resources yet."; list.appendChild(e); }
            };
            draw(); body.appendChild(list);
            // add form
            const form = document.createElement("div"); form.style.cssText = "display:flex;flex-wrap:wrap;gap:2px;align-items:center;margin:6px 0";
            const kind = document.createElement("select"); kind.className = "portal-filter"; kind.style.cssText = "font-size:12px;margin:2px";
            for (const k of ["crane", "hoist", "laydown", "gate", "fence", "haul_route", "trailer", "parking"]) { const o = document.createElement("option"); o.value = k; o.textContent = k; kind.appendChild(o); }
            const mk = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "font-size:12px;margin:2px;flex:0 1 110px;min-width:0"; return i; };
            const label = mk("label"); const startI = mk("start YYYY-MM-DD"); const endI = mk("end YYYY-MM-DD");
            const add = document.createElement("button"); add.className = "mini-btn"; add.textContent = "＋ at last point";
            add.onclick = () => {
              if (!lastPoint) { notify("click a point in the model first", "error"); return; }
              const id = `r${Date.now().toString(36)}`;
              const e = lastPoint.x, n = -lastPoint.z;   // world (E, y, -N) → E, N
              const r: LogisticsResource = { id, kind: kind.value, label: label.value.trim() || kind.value, position: [e, 0, n], start: startI.value.trim() || undefined, end: endI.value.trim() || undefined };
              if (kind.value === "crane") r.radius = 25;
              resources.push(r); logisticsOverlay.render(resources); label.value = ""; draw();
              status.textContent = `added ${kind.value} at E ${e.toFixed(1)}, N ${n.toFixed(1)}`;
            };
            form.append(kind, label, startI, endI, add); body.appendChild(form);
            // time-phase + save
            const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center";
            const dateI = mk("show at date"); dateI.style.flex = "0 1 130px";
            const phase = document.createElement("button"); phase.className = "mini-btn"; phase.textContent = "⏱ Show at date";
            phase.onclick = async () => {
              try { const st = await api.putLogistics(pid, resources).then(() => api.logisticsState(pid, dateI.value.trim() || undefined));
                logisticsOverlay.showActive(new Set(st.active.map((x) => x.id)));
                status.textContent = `${st.active_count} of ${st.total} active${st.date ? ` on ${st.date}` : ""}`;
              } catch (e) { notify((e as Error).message, "error"); }
            };
            const showAll = document.createElement("button"); showAll.className = "mini-btn"; showAll.textContent = "👁 Show all";
            showAll.onclick = () => { logisticsOverlay.showAll(); status.textContent = ""; };
            const save = document.createElement("button"); save.className = "mini-btn on"; save.textContent = "💾 Save";
            save.onclick = async () => { try { await api.putLogistics(pid, resources); notify("logistics saved", "success"); } catch (e) { notify((e as Error).message, "error"); } };
            actions.append(dateI, phase, showAll, save); body.append(actions, status);
          });
        }));
        b.appendChild(toolBtn2("⏱ 4D construction sequence (playback)", () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          // teardown rides the modal's onClose (✕/Esc/backdrop/replaced) — stops the play timer and
          // restores visibility, so closing mid-play never leaves the model isolated (HARDEN-2 B5).
          showResult("4D construction sequence", (body) => {
            dispose4d = populate4dPanel(body, { api, pid, layers: layerMgr, notify });
          }, () => { dispose4d?.(); dispose4d = null; });
        }));
        b.appendChild(toolBtn2("🕸 Related elements (model graph)", () => withLoading(container, "Building model graph", async () => {
          if (!selectedGuid) { notify("select an element in 3D first", "error"); return; }
          const guid = selectedGuid;
          let r;
          try { r = await api.graphNeighbors(pid, guid, 2); }
          catch { toast("Needs a source IFC", "error"); return; }
          if (!r.found) { toast("Element not in the graph", "error"); return; }
          out.textContent = `${r.neighbor_count ?? 0} related`;
          const relLabel: Record<string, string> = { contained_in: "is in", aggregates: "contains", bounds: "bounds", has_opening: "has opening", fills: "fills", serves: "serves" };
          showResult("Related elements — model graph (IFC relationships)", (body) => {
            body.appendChild(resultNote(`Multi-hop relationships from the selected element, straight from the model's IFC structure — every hop is cited by relationship. <b>${r!.neighbor_count ?? 0}</b> related element(s) within 2 hops.`, "ok"));
            if (!r!.paths.length) { body.appendChild(resultNote("This element has no modelled relationships (no spatial containment, openings, or boundaries).", "")); return; }
            for (const p of r!.paths.slice(0, 40)) {
              const row = document.createElement("div"); row.className = "tree-leaf"; row.style.cssText = "cursor:pointer;padding:3px 6px;font-size:12px";
              const chain = p.path.map((s) => `${s.dir === "out" ? "→" : "←"} ${relLabel[s.rel] || s.rel}`).join(" ");
              row.innerHTML = `<b>${escapeHtml((p.name || p.class.replace("Ifc", "")))}</b> <span class="meta">${escapeHtml(p.class.replace("Ifc", ""))}</span> <span class="meta">${escapeHtml(chain)}</span>`;
              row.title = "Select this element in 3D";
              row.onclick = () => { void selectByGuid(p.guid, true); };
              body.appendChild(row);
            }
          });
        })));
        b.appendChild(toolBtn2("🧬 Property layers (IFC5 overlays)", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          let stack: PropLayer[];
          try { stack = (await api.getLayers(pid)).layers; }
          catch { toast("Could not load layers", "error"); return; }
          showResult("Property-override layers — IFC5 composition", (body) => {
            body.appendChild(resultNote(`Non-destructive <b>overlay layers</b> that compose over the model (IFC5-style) — the strongest enabled layer wins, disagreements surface as <b>conflicts</b>, and nothing touches the IFC until you <b>bake</b>. Layers are ordered base → strongest.`, "ok"));
            const list = document.createElement("div"); list.style.margin = "6px 0";
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "6px";
            const draw = () => {
              list.innerHTML = "";
              stack.forEach((L, i) => {
                const row = document.createElement("div"); row.className = "level-row";
                const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = L.enabled !== false;
                cb.onchange = () => { L.enabled = cb.checked; };
                const nm = document.createElement("span"); nm.style.flex = "1"; nm.style.fontSize = "12px";
                nm.textContent = `${i + 1}. ${L.name} `; const badge = document.createElement("span"); badge.className = "meta"; badge.textContent = `(${L.overrides.length} override${L.overrides.length === 1 ? "" : "s"})`; nm.appendChild(badge);
                const del = document.createElement("button"); del.className = "selset-del"; del.textContent = "✕";
                del.onclick = () => { stack.splice(i, 1); draw(); };
                row.append(cb, nm, del); list.appendChild(row);
              });
              if (!stack.length) { const e = document.createElement("div"); e.className = "meta"; e.textContent = "No layers yet — add one, then add overrides from a selected element."; list.appendChild(e); }
            };
            draw(); body.appendChild(list);
            // add-layer + add-override-from-selection
            const addL = document.createElement("button"); addL.className = "mini-btn"; addL.textContent = "＋ Layer";
            const ovForm = document.createElement("div"); ovForm.style.cssText = "display:flex;flex-wrap:wrap;gap:2px;align-items:center;margin:6px 0";
            const mk = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "font-size:12px;margin:2px;flex:1 1 80px;min-width:0"; return i; };
            const psetI = mk("Pset"), propI = mk("Prop"), valI = mk("value");
            const layerSel = document.createElement("select"); layerSel.className = "portal-filter"; layerSel.style.cssText = "font-size:12px;margin:2px";
            const drawSel = () => { layerSel.innerHTML = ""; stack.forEach((L, i) => { const o = document.createElement("option"); o.value = String(i); o.textContent = L.name; layerSel.appendChild(o); }); };
            const addOv = document.createElement("button"); addOv.className = "mini-btn"; addOv.textContent = "＋ override (selected element)";
            addOv.onclick = () => {
              if (!selectedGuid) { notify("select an element in 3D first", "error"); return; }
              if (!psetI.value.trim() || !propI.value.trim() || !stack.length) { notify("need a layer + Pset + Prop", "error"); return; }
              const L = stack[Number(layerSel.value) || 0]; if (!L) { notify("add a layer first", "error"); return; }
              L.overrides.push({ guid: selectedGuid, pset: psetI.value.trim(), prop: propI.value.trim(), value: valI.value });
              propI.value = ""; valI.value = ""; draw(); status.textContent = `added override on ${selectedGuid.slice(0, 8)}… to “${L.name}”`;
            };
            addL.onclick = async () => { const n = await askText("New layer", { label: "Layer name (e.g. Fire coordination):", value: "" }); if (!n) return; stack.push({ name: n, enabled: true, overrides: [] }); draw(); drawSel(); };
            drawSel();
            body.append(addL, ovForm); ovForm.append(document.createTextNode("to "), layerSel, psetI, propI, valI, addOv);
            const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;margin-top:6px;flex-wrap:wrap";
            const save = document.createElement("button"); save.className = "mini-btn"; save.textContent = "💾 Save layers";
            save.onclick = async () => { try { await api.putLayers(pid, stack); notify("layers saved", "success"); } catch (e) { notify((e as Error).message, "error"); } };
            const resolve = document.createElement("button"); resolve.className = "mini-btn"; resolve.textContent = "🔍 Resolve + conflicts";
            resolve.onclick = async () => {
              try { await api.putLayers(pid, stack); const r = await api.resolveLayers(pid);
                status.innerHTML = `<b>${r.effective_count}</b> effective override(s) · <b>${r.conflict_count}</b> conflict(s)`
                  + (r.conflicts.length ? "<br>" + r.conflicts.slice(0, 6).map((c) => `⚠ ${escapeHtml(c.pset)}.${escapeHtml(c.prop)}: ${c.values.map((v) => `${escapeHtml(String(v.value))} (${escapeHtml(v.layer)})`).join(" vs ")} → wins <b>${escapeHtml(c.winning_layer)}</b>`).join("<br>") : "");
              } catch (e) { notify((e as Error).message, "error"); }
            };
            const bake = document.createElement("button"); bake.className = "mini-btn on"; bake.textContent = "🔥 Bake to IFC";
            bake.onclick = async () => {
              if (!(await confirmModal("Bake the composed layers into the IFC? This writes the effective values as a new model version (GUID-stable).", "", "Bake", false))) return;
              await api.putLayers(pid, stack).catch(() => {});
              await withLoading(container, "Baking layers + republishing", async () => {
                try { const r = await api.bakeLayers(pid); notify(`baked ${r.baked} override(s) — converting…`, "info"); await waitForPublish(pid); await loadProjectModel(); notify("layers baked into the model", "success"); }
                catch (e) { notify((e as Error).message, "error"); }
              });
            };
            actions.append(save, resolve, bake); body.append(actions, status);
          });
        }));
        b.appendChild(toolBtn2("🏛 Occupancy & egress (IBC pre-check)", () => withLoading(container, "Computing occupancy load + egress", async () => {
          let r;
          try { r = await api.codecheckEgress(pid); }
          catch { toast("Needs a source IFC with IfcSpaces", "error"); return; }
          const load = r.building.occupant_load;
          out.textContent = `${load} occ · egress ${r.egress.adequate === false ? "SHORT" : "ok"}`;
          showResult("Occupancy load & egress — IBC pre-check", (body) => {
            body.appendChild(resultNote(`Computed from <b>${r!.building.spaces}</b> spaces + doors — <b>${load}</b> total occupants over ${r!.building.area_ft2.toLocaleString()} ft². `
              + `Required egress width <b>${r!.egress.required_width_in} in</b> vs <b>${r!.egress.provided_width_in} in</b> provided → `
              + `<b>${r!.egress.adequate == null ? "n/a" : r!.egress.adequate ? "adequate" : "SHORT — add egress width"}</b>.`,
              r!.egress.adequate === false ? "bad" : "ok"));
            if (r!.building.spaces_missing_area) body.appendChild(resultNote(`${r!.building.spaces_missing_area} space(s) have no floor-area quantity and were skipped — add areas for a complete count.`, ""));
            if (r!.by_occupancy.length) body.appendChild(kvTable(r!.by_occupancy.map((o) => ({ k: `${o.occupancy} (1:${o.factor} ${o.basis})`, v: `${o.load} occ · ${o.spaces} space(s) · ${o.area_ft2.toLocaleString()} ft²` }))));
            if (r!.doors.below_min_32in) {
              body.appendChild(resultNote(`${r!.doors.below_min_32in} of ${r!.doors.checked} doors are below the 32 in (0.81 m) minimum clear width (IBC 1010.1.1).`, "bad"));
              body.appendChild(toolBtn2("◎ Isolate narrow doors in 3D", () => { void layerMgr.isolateGuids(r!.doors.fail_guids); }));
            }
            const twoExit = r!.spaces.filter((s) => s.needs_2_exits);
            if (twoExit.length) body.appendChild(resultNote(`${twoExit.length} space(s) exceed 49 occupants → two exits required (IBC 1006.2): ${twoExit.slice(0, 6).map((s) => s.name || "space").join(", ")}${twoExit.length > 6 ? "…" : ""}.`, ""));
            body.appendChild(resultNote(r!.disclaimer + " Cited: " + r!.citations.join("; ") + ".", ""));
            const nFindings = r!.doors.below_min_32in + (r!.egress.adequate === false ? 1 : 0) + r!.spaces.filter((s) => s.needs_2_exits).length;
            if (nFindings) {
              const bcf = toolBtn2(`📌 Promote ${nFindings} finding${nFindings === 1 ? "" : "s"} to BCF issues`, async () => {
                try { const res = await api.codecheckEgressBcf(pid); notify(`created ${res.created} BCF issue${res.created === 1 ? "" : "s"} — see the Issues panel`, "success"); await refreshIssues(); }
                catch (e) { notify((e as Error).message, "error"); }
              });
              bcf.title = "Create trackable BCF topics from the code findings (below-min doors, egress shortfall, two-exit spaces)";
              body.appendChild(bcf);
            }
          });
        })));
        const runCodeAnalysis = (jur: string) => withLoading(container, "Assembling the IBC code-analysis summary", async () => {
          let r;
          try { r = await api.codeAnalysis(pid, jur ? { jurisdiction: jur } : {}); }
          catch { toast("Needs a source IFC with IfcSpaces", "error"); return; }
          const ed = r.code_context.ibc_edition;
          out.textContent = `${r.occupancy.group} · ${r.construction_type.split(" ")[0]} · ${r.building.stories} st${ed ? ` · IBC ${ed}` : ""}`;
          showResult("Code analysis — permit-set G-series summary", (body) => {
            const cc = r!.code_context;
            body.appendChild(resultNote(`Code edition: <b>IBC ${cc.ibc_edition ?? "—"}</b> `
              + (cc.resolved ? `(${cc.jurisdiction} adoption, as-of ${cc.as_of})` : "(national baseline — enter your state below)")
              + `. <i>${cc.verify}</i>`, cc.resolved ? "ok" : ""));
            body.appendChild(resultNote(`The IBC <b>code-analysis summary</b> a permit set carries on its G-series code sheet, assembled from the model. `
              + `Verify allowable area/height against the actual Table 506.2 with the AHJ.`, "ok"));
            body.appendChild(kvTable([
              { k: "Occupancy group", v: `${r!.occupancy.group}${r!.occupancy.primary && r!.occupancy.primary !== "—" ? ` — ${r!.occupancy.primary}` : ""}` },
              { k: "Occupancy mix", v: r!.occupancy.mix.length ? r!.occupancy.mix.join(", ") : "—" },
              { k: "Construction type", v: r!.construction_type },
              { k: "Sprinklered (NFPA-13)", v: r!.sprinklered ? "yes" : "no" },
              { k: "Stories", v: String(r!.building.stories) },
              { k: "Gross area", v: `${r!.building.gross_area_ft2.toLocaleString()} ft²` },
              { k: "Computed occupant load", v: `${r!.building.occupant_load} occ` },
            ]));
            body.appendChild(resultNote(`Egress width required <b>${r!.egress.required_width_in} in</b> vs <b>${r!.egress.provided_width_in} in</b> provided → `
              + `<b>${r!.egress.adequate == null ? "n/a" : r!.egress.adequate ? "adequate" : "SHORT"}</b>. `
              + `Doors checked ${r!.doors.checked}${r!.doors.below_min_32in ? ` · ${r!.doors.below_min_32in} below 32 in` : ""}.`,
              r!.egress.adequate === false || r!.doors.below_min_32in ? "bad" : "ok"));
            if (r!.occupant_load_by_occupancy.length) body.appendChild(kvTable(r!.occupant_load_by_occupancy.map((o) => ({ k: o.occupancy, v: `${o.load} occ · ${o.area_ft2.toLocaleString()} ft²` }))));
            body.appendChild(resultNote(`<b>Allowable area & height</b> — ${r!.allowable.note} Sprinkler increase: <b>${r!.allowable.sprinkler_increase}</b>. `
              + `Governing sections: ${r!.allowable.sections.join("; ")}.`, ""));
            // CODE-1/3: set the jurisdiction → re-run the analysis edition-aware (cites the adopted IBC).
            const jurWrap = document.createElement("div"); jurWrap.style.cssText = "display:flex;gap:6px;align-items:center;margin:6px 0";
            const jurLbl = document.createElement("span"); jurLbl.className = "meta"; jurLbl.textContent = "Jurisdiction (US state):";
            const jurIn = document.createElement("input"); jurIn.className = "portal-filter"; jurIn.placeholder = "e.g. CA"; jurIn.maxLength = 2; jurIn.value = cc.jurisdiction || ""; jurIn.style.cssText = "width:80px;font-size:12px";
            const jurBtn = document.createElement("button"); jurBtn.className = "mini-btn"; jurBtn.textContent = "↻ Re-check for this state";
            jurBtn.onclick = () => { void runCodeAnalysis(jurIn.value.trim().toUpperCase()); };
            jurIn.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); void runCodeAnalysis(jurIn.value.trim().toUpperCase()); } };
            jurWrap.append(jurLbl, jurIn, jurBtn); body.appendChild(jurWrap);
            body.appendChild(resultNote(r!.disclaimer, ""));
          });
        });
        b.appendChild(toolBtn2("🏛 Code analysis (G-series summary)", () => { void runCodeAnalysis(""); }));
        // CODE-EBC — existing-building scope classifier (IEBC Work Area Method), inferred from phasing
        const runEbc = (jur: string) => withLoading(container, "Classifying the existing-building scope (IEBC)", async () => {
          let r;
          try { r = await api.ebcClassify(pid, { infer: true, ...(jur ? { jurisdiction: jur } : {}) }); }
          catch { toast("Needs a source IFC to infer scope from phasing", "error"); return; }
          out.textContent = r.classification ? `${r.classification}${r.code.edition ? ` · IEBC ${r.code.edition}` : ""}` : "no scope";
          showResult("Existing-building scope — IEBC Work Area Method", (body) => {
            body.appendChild(resultNote(`Inferred from the model's <b>phasing</b> (existing vs new/demolish). `
              + `The IEBC governs renovation/adaptive-reuse; this classifies the <b>scope of work</b> → which provisions apply.`, ""));
            if (!r!.ok) {
              body.appendChild(resultNote(r!.reason || "No scope classified.", "bad"));
            } else {
              body.appendChild(resultNote(`Classification: <b>${r!.classification}</b>`
                + (r!.work_area_pct != null ? ` · work area ≈ <b>${Math.round(r!.work_area_pct)}%</b>` : "")
                + `. <span class="meta">${r!.gist || ""}</span>`, "ok"));
              body.appendChild(resultNote(`Compliance method: <b>${r!.method}</b> (${r!.method_cite}). `
                + `Code edition: <b>IEBC ${r!.code.edition ?? "—"}</b> `
                + (r!.code.adoption_resolved ? `(${r!.code.jurisdiction} adoption)` : "(national baseline — set your state below)")
                + `.`, r!.code.adoption_resolved ? "ok" : ""));
              if (r!.applies?.length) body.appendChild(kvTable(r!.applies.map((a) => ({ k: a.classification, v: `${a.section} · ${a.requirements}` }))));
              if (r!.basis?.length) body.appendChild(resultNote(`<b>How this was inferred:</b> ${r!.basis.join(" ")}`, ""));
              if (r!.notes?.length) body.appendChild(resultNote(r!.notes.join(" "), ""));
            }
            // jurisdiction re-check (edition-aware) — mirror the code-analysis flow
            const jurWrap = document.createElement("div"); jurWrap.style.cssText = "display:flex;gap:6px;align-items:center;margin:6px 0";
            const jurLbl = document.createElement("span"); jurLbl.className = "meta"; jurLbl.textContent = "Jurisdiction (US state):";
            const jurIn = document.createElement("input"); jurIn.className = "portal-filter"; jurIn.placeholder = "e.g. CA"; jurIn.maxLength = 2; jurIn.value = r!.code.jurisdiction || ""; jurIn.style.cssText = "width:80px;font-size:12px";
            const jurBtn = document.createElement("button"); jurBtn.className = "mini-btn"; jurBtn.textContent = "↻ Re-check for this state";
            jurBtn.onclick = () => { void runEbc(jurIn.value.trim().toUpperCase()); };
            jurIn.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); void runEbc(jurIn.value.trim().toUpperCase()); } };
            jurWrap.append(jurLbl, jurIn, jurBtn); body.appendChild(jurWrap);
            body.appendChild(resultNote(r!.disclaimer, ""));
          });
        });
        b.appendChild(toolBtn2("🏚 Existing-building code (IEBC scope)", () => { void runEbc(""); }));
        // EST-1 — rough labour cost + duration from the model's quantities (productivity rates)
        b.appendChild(toolBtn2("💰 Cost estimate (labour · material · equipment)", () => withLoading(container, "Estimating cost from the model", async () => {
          let e;
          try { e = await api.laborEstimate(projectId!, "commercial", 25, true); }
          catch { toast("Needs a source IFC", "error"); return; }
          const grand = e.total_cost ?? e.total_labor_cost;
          out.textContent = `${e.total_man_hours.toLocaleString()} mh · $${Math.round(grand).toLocaleString()}`;
          showResult("Cost estimate — productivity rates", (body) => {
            body.appendChild(resultNote(`Rough <b>cost</b> takeoff from the model (${e!.line_count} activity(ies), `
              + `${e!.loading} loading ×${e!.loading_factor}, $${e!.hourly_rate}/hr labour): `
              + `<b>${e!.total_man_hours.toLocaleString()} man-hours</b>.`, e!.line_count ? "ok" : ""));
            if (!e!.line_count) body.appendChild(resultNote("No estimable quantities yet — author walls / slabs / columns.", ""));
            if (e!.has_material_equipment) {
              body.appendChild(kvTable([
                { k: "Labour", v: `$${Math.round(e!.total_labor_cost).toLocaleString()}` },
                { k: "Material", v: `$${Math.round(e!.total_material_cost ?? 0).toLocaleString()}` },
                { k: "Equipment", v: `$${Math.round(e!.total_equipment_cost ?? 0).toLocaleString()}` },
                { k: "Total (excl. overhead/profit)", v: `$${Math.round(e!.total_cost ?? 0).toLocaleString()}`, strong: true },
              ]));
            }
            if (e!.lines.length) {
              body.appendChild(kvTable(e!.lines.map((l) => ({
                k: `${l.activity.replace(/_/g, " ")} (${l.group})`,
                v: `${l.quantity} ${l.unit} → ${l.man_hours} mh · ${l.crew_days} cd`
                  + (l.line_total != null ? ` · $${Math.round(l.line_total).toLocaleString()}` : ` · $${Math.round(l.labor_cost).toLocaleString()}`) }))));
            }
            body.appendChild(resultNote(e!.note, ""));
          });
        })));
        // W11 D8: plan-reviewer approvability pre-flight
        // RFI-0 — decision-readiness audit: the information gaps a builder would ask about, ranked
        b.appendChild(toolBtn2("🚫 Decision-readiness (RFI-prevention)", () => withLoading(container, "Auditing decision-readiness", async () => {
          let r;
          try { r = await api.rfiReadiness(projectId!); }
          catch { toast("Needs a source IFC", "error"); return; }
          out.textContent = r.ready ? "decision-ready" : `${r.total_gaps} gap(s) · ${r.high_severity} high`;
          showResult("Decision-readiness — RFI prevention", (body) => {
            body.appendChild(resultNote(r!.ready
              ? "<b>Decision-ready</b> — no obvious information gaps a builder would have to ask about."
              : `<b>${r!.total_gaps} information gap(s)</b> a builder would have to ask about `
                + `(<b>${r!.high_severity}</b> high-severity). Resolve before issuing to cut RFIs.`,
              r!.ready ? "ok" : "bad"));
            const icon = (s: string) => s === "high" ? "🔴" : s === "medium" ? "🟠" : "🟡";
            for (const g of r!.gaps) {
              body.appendChild(kvTable([
                { k: `${icon(g.severity)} ${g.title}`, v: `${g.detail}${g.citation ? " · " + g.citation : ""}`, strong: true },
                { k: "  fix", v: g.fix },
              ]));
              if (g.guids && g.guids.length) {
                const iso = toolBtn2(`◎ Isolate ${g.guids.length} element(s)`, () => { void layerMgr.isolateGuids(g.guids!); });
                body.appendChild(iso);
              }
            }
            if (r!.total_gaps) {
              const bcf = toolBtn2(`📌 Promote ${r!.total_gaps} gap${r!.total_gaps === 1 ? "" : "s"} to BCF issues`, async () => {
                try { const res = await api.rfiReadinessBcf(projectId!); notify(`created ${res.created} BCF issue${res.created === 1 ? "" : "s"} — see the Issues panel`, "success"); await refreshIssues(); }
                catch (e) { notify((e as Error).message, "error"); }
              });
              bcf.title = "Create trackable, GUID-anchored BCF topics from the readiness gaps so they round-trip with clashes/RFIs";
              body.appendChild(bcf);
            }
            body.appendChild(resultNote(r!.disclaimer, ""));
          });
        })));
        // RFI-0 NL-QA — ask a plain-language question, get a cited answer from the model's own data
        const qaWrap = document.createElement("div");
        qaWrap.style.cssText = "display:flex;gap:4px;margin:4px 2px";
        const qaInput = document.createElement("input");
        qaInput.type = "text";
        qaInput.placeholder = "Ask: what governs <element>? · what's blocking approval?";
        qaInput.style.cssText = "flex:1;min-width:0;font-size:11px;padding:3px 6px";
        qaInput.setAttribute("aria-label", "Ask a question about the model");
        const qaBtn = document.createElement("button");
        qaBtn.className = "tool-btn"; qaBtn.textContent = "Ask"; qaBtn.style.cssText = "font-size:11px;padding:3px 10px";
        const askQa = () => {
          const q = qaInput.value.trim();
          if (!q) return;
          void withLoading(container, "Asking the model", async () => {
            let r;
            try { r = await api.rfiQa(pid, q); }
            catch { toast("Needs a source IFC", "error"); return; }
            out.textContent = r.answer.slice(0, 60);
            showResult("Ask the model — cited answer", (body) => {
              body.appendChild(resultNote(r!.answer, r!.ready === false ? "bad" : "ok"));
              if (r!.citations.length) {
                body.appendChild(kvTable(r!.citations.map((c) => ({ k: c.kind, v: c.ref }))));
                const guids = r!.citations.flatMap((c) => c.guids || []);
                if (guids.length) body.appendChild(toolBtn2(`◎ Isolate ${guids.length} cited element(s)`, () => { void layerMgr.isolateGuids(guids); }));
              }
              body.appendChild(resultNote(r!.disclaimer, ""));
            });
          });
        };
        qaBtn.onclick = askQa;
        qaInput.onkeydown = (e) => { if (e.key === "Enter") askQa(); };
        qaWrap.append(qaInput, qaBtn);
        b.appendChild(qaWrap);
        // W10-7 structural analytical model — derived from the physical frame
        b.appendChild(toolBtn2("🏗 Structural analytical model", () => withLoading(container, "Reading the analytical model", async () => {
          let s;
          try { s = await api.analyticalSummary(pid); }
          catch { toast("Needs a source IFC", "error"); return; }
          out.textContent = s.has_model ? `${s.curve_members} members · ${s.point_connections} nodes` : "not derived";
          showResult("Structural analytical model", (body) => {
            if (!s!.has_model) {
              body.appendChild(resultNote("No analytical model yet. Derive one to idealise the physical frame — "
                + "columns/beams → curve members, slabs → surface members, tied at shared nodes with a self-weight load case.", ""));
            } else {
              body.appendChild(resultNote(`<b>${s!.curve_members}</b> curve members · <b>${s!.surface_members}</b> surface members`
                + ` · <b>${s!.point_connections}</b> nodes · load case: ${s!.load_cases.filter(Boolean).join(", ") || "—"}`
                + (s!.load_actions ? ` · <b>${s!.load_actions}</b> member load action(s)` : "")
                + (s!.supports ? ` · <b>${s!.supports}</b> support(s)` : "")
                + (s!.load_actions && s!.supports ? " — solver-ready" : ""), "ok"));
            }
            const derive = toolBtn2(s!.has_model ? "↻ Re-derive from the physical model" : "⚙ Derive from the physical model",
              () => withLoading(container, "Deriving the analytical model", async () => {
                try {
                  await api.editIfc(pid, "derive_analytical", {}, false);
                  const s2 = await api.analyticalSummary(pid);
                  notify(`Analytical model derived — ${s2.curve_members} curve, ${s2.surface_members} surface members, ${s2.point_connections} nodes`, "success");
                } catch (e) { notify((e as Error).message, "error"); }
              }));
            derive.title = "Build/refresh the IfcStructuralAnalysisModel alongside the physical model (GUID-stable, idempotent)";
            body.appendChild(derive);
            if (s!.has_model && s!.curve_members > 0) {
              const loads = toolBtn2("⬇ Write member loads (solver-ready IFC)",
                () => withLoading(container, "Writing structural load actions", async () => {
                  try {
                    const res = await api.editIfc(pid, "apply_structural_loads", { dead_klf: 1.0, live_klf: 0.5 }, false);
                    const applied = (res as { changed?: { applied?: number } })?.changed?.applied ?? 0;
                    notify(`Wrote ${applied} member load action(s) — the analytical IFC is now loaded (D+L) and solver-ready`, "success");
                  } catch (e) { notify((e as Error).message, "error"); }
                }));
              loads.title = "Write IfcStructuralLinearAction (D+L) onto every analytical member so a solver (SAP2000/RISA/Robot) imports the loads with the geometry";
              body.appendChild(loads);
              const sup = toolBtn2("⏚ Add base supports (pinned)",
                () => withLoading(container, "Adding base supports", async () => {
                  try {
                    const res = await api.editIfc(pid, "apply_structural_supports", { kind: "pinned" }, false);
                    const n = (res as { changed?: { supported?: number } })?.changed?.supported ?? 0;
                    notify(`Added ${n} pinned base support(s) — the analytical model is now statically stable`, "success");
                  } catch (e) { notify((e as Error).message, "error"); }
                }));
              sup.title = "Fix the base analytical nodes as pinned IfcBoundaryNodeCondition supports so the model is solvable";
              body.appendChild(sup);
            }
            if (s!.has_model && s!.curve_members > 0) {
              const solve = toolBtn2("📐 Apply loads + solve statics", () => withLoading(container, "Applying gravity loads + solving statics", async () => {
                let r;
                try { r = await api.structureSolve(pid, { liveOccupancy: "office" }); }
                catch (e) { notify((e as Error).message, "error"); return; }
                showResult("Structural statics — gravity load solve", (sb) => {
                  if (!r!.has_analytical) { sb.appendChild(resultNote(r!.message || "No analytical model.", "bad")); return; }
                  const lc = r!.load_case!, c = r!.counts!;
                  sb.appendChild(resultNote(`Load case <b>${lc.name}</b> — dead <b>${lc.dead_klf}</b> + live <b>${lc.live_klf}</b> = <b>${lc.service_klf} klf</b> service`
                    + ` · factored <b>${lc.factored_lrfd_klf} klf</b> (${lc.governing_combo}). Solved <b>${c.beams}</b> beam(s) + <b>${c.columns}</b> column(s) as determinate members.`, "ok"));
                  const gb = r!.governing_beam;
                  if (gb) {
                    const sv = gb.service;
                    sb.appendChild(resultNote(`<b>Governing beam</b> — ${gb.length_ft} ft span · reaction <b>${sv.reaction_kip} kip</b> · Vmax <b>${sv.shear_max_kip} kip</b> · Mmax <b>${sv.moment_max_kipft} kip·ft</b>`
                      + ` · deflection <b>${sv.deflection_in}"</b> vs L/360 limit ${sv.deflection_limit_in}" (${sv.deflection_ok ? "✅ OK" : "⚠ exceeds"})`, sv.deflection_ok ? "ok" : "bad"));
                    // mini shear (blue) + moment (orange) diagrams over the span
                    const W = 260, H = 60;
                    const dg = sv.diagram;
                    const maxX = Math.max(1, ...dg.map((d) => d.x_ft));
                    const px = (x: number) => 4 + (x / maxX) * (W - 8);
                    const band = (val: (d: typeof dg[number]) => number, color: string, label: string) => {
                      const mx = Math.max(1, ...dg.map((d) => Math.abs(val(d))));
                      const mid = H / 2;
                      const pts = dg.map((d) => `${px(d.x_ft).toFixed(1)},${(mid - (val(d) / mx) * (mid - 6)).toFixed(1)}`).join(" ");
                      return `<div class="meta" style="margin-top:6px">${label}</div>`
                        + `<svg width="${W}" height="${H}" style="background:var(--panel);border:1px solid var(--line);border-radius:4px">`
                        + `<line x1="4" y1="${mid}" x2="${W - 4}" y2="${mid}" stroke="var(--line)"/>`
                        + `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/></svg>`;
                    };
                    const svg = document.createElement("div");
                    svg.innerHTML = band((d) => d.shear_kip, "#4c8bf5", "Shear (kip)")
                      + band((d) => d.moment_kipft, "#f5a24c", "Moment (kip·ft)");
                    sb.appendChild(svg);
                  }
                  if (r!.columns_axial) {
                    const ca = r!.columns_axial;
                    sb.appendChild(resultNote(`<b>Column axial</b> (tributary takedown) — service <b>${ca.service_total_kip} kip</b> · factored <b>${ca.factored_lrfd_kip} kip</b> over ${ca.storeys} storey(s). <span class="meta">${ca.note}</span>`, ""));
                  }
                  sb.appendChild(resultNote(r!.disclaimer || "", ""));
                });
              }));
              solve.title = "Apply an ASCE 7 gravity load case to the analytical members and solve determinate statics (reactions, shear/moment/deflection)";
              body.appendChild(solve);
            }
            const lat = toolBtn2("🌪 Lateral (wind + seismic base shear)", () => withLoading(container, "Running ASCE 7 lateral analysis", async () => {
              let lr;
              try { lr = await api.structureLateral(pid, {}); }
              catch (e) { notify((e as Error).message, "error"); return; }
              showResult("Structural lateral — ASCE 7 wind + seismic", (sb) => {
                const g = lr!.governing, se = lr!.seismic, wi = lr!.wind;
                sb.appendChild(resultNote(`<b>Governing: ${g.system}</b> — base shear <b>${g.base_shear_kip} kip</b>`
                  + ` over ${lr!.story_count} stor${lr!.story_count === 1 ? "y" : "ies"} (est. weight ${se.seismic_weight_kip} kip).`, "ok"));
                sb.appendChild(kvTable([
                  { k: "🌎 Seismic (ELF §12.8)", v: `V = ${se.base_shear_kip} kip · Cs ${se.Cs} · T ${se.period_s}s · OTM ${se.overturning_kipft.toLocaleString()} k·ft`, strong: true },
                  { k: "🌬 Wind (MWFRS)", v: `V = ${wi.base_shear_kip} kip · qh ${wi.qh_psf} psf · OTM ${wi.overturning_kipft.toLocaleString()} k·ft`, strong: true },
                ]));
                const govStories = g.system === "seismic" ? se.stories : wi.stories;
                sb.appendChild(resultNote(`Story forces (${g.system}):`, ""));
                sb.appendChild(kvTable(govStories.slice().reverse().map((s) => ({
                  k: `Level ${s.level} @ ${s.height_ft} ft`, v: `F = ${s.force_kip} kip · V = ${s.shear_kip} kip`,
                }))));
                sb.appendChild(resultNote(lr!.disclaimer, ""));
              });
            }));
            lat.title = "ASCE 7 Equivalent Lateral Force (seismic) + simplified MWFRS (wind) → base shear + story forces; preliminary, not a stamped design";
            body.appendChild(lat);
          });
        })));
        b.appendChild(toolBtn2("✅ Approvability pre-flight (permit-readiness)", () => withLoading(container, "Running the plan-reviewer pre-flight", async () => {
          let a;
          try { a = await api.approvability(projectId!); }
          catch { toast("Needs a source IFC", "error"); return; }
          const s = a.summary;
          out.textContent = `${s.passed}/${s.gating} checks · ${s.ready ? "ready" : `${s.failed} to fix`}`;
          showResult("Approvability pre-flight — permit-readiness", (body) => {
            body.appendChild(resultNote(s.ready
              ? `<b>Ready for review</b> — all ${s.gating} gating check(s) pass${s.score_pct !== null ? ` (${s.score_pct}%)` : ""}.`
              : `<b>${s.failed} check(s) need attention</b> before review${s.score_pct !== null ? ` — ${s.score_pct}% passing` : ""}.`,
              s.ready ? "ok" : "bad"));
            const icon = (st: string) => st === "pass" ? "✅" : st === "fail" ? "❌" : st === "info" ? "ℹ️" : "—";
            body.appendChild(kvTable(a!.checks.map((c) => ({ k: `${icon(c.status)} ${c.check}`, v: `${c.detail} · ${c.citation}` }))));
            const failing = a!.checks.filter((c) => c.status === "fail" && c.guids && c.guids.length);
            if (failing.length) {
              const iso = toolBtn2("◎ Isolate flagged elements in 3D", () => { void layerMgr.isolateGuids(failing.flatMap((c) => c.guids || [])); });
              body.appendChild(iso);
            }
            body.appendChild(resultNote(a!.disclaimer, ""));
          });
        })));
        b.appendChild(toolBtn2("🔧 Normalize properties (IDS-ready)", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          let det;
          try { det = await api.propmapDetect(pid); }
          catch { toast("Property normalization needs a source IFC", "error"); return; }
          showResult("Normalize properties → standard structure", (body) => {
            body.appendChild(resultNote(`Remap this model's property names onto a standard (IDS / employer) structure — the <b>transform</b> step between IDS validation and COBie/export. Each rule moves a source <i>Pset.Property</i> to a target across every element, GUID-stable. Model has <b>${det!.element_count}</b> elements.`, "ok"));
            const rules: PropMapRule[] = [];
            const mk = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "font-size:12px;margin:2px;flex:1 1 90px;min-width:0"; return i; };
            const fromPset = mk("from Pset"), fromProp = mk("from Prop"), toPset = mk("to Pset (blank = same)"), toProp = mk("to Prop");
            const cast = document.createElement("select"); cast.className = "portal-filter"; cast.style.cssText = "font-size:12px;margin:2px";
            for (const c of ["string", "number", "bool"]) { const o = document.createElement("option"); o.value = c; o.textContent = c; cast.appendChild(o); }
            const lbl = document.createElement("div"); lbl.className = "meta"; lbl.style.marginTop = "6px"; lbl.textContent = "Detected properties (click to use as source):";
            const detWrap = document.createElement("div"); detWrap.style.cssText = "max-height:130px;overflow:auto;margin:4px 0;border:1px solid var(--line);border-radius:6px";
            for (const p of det!.properties.slice(0, 80)) {
              const row = document.createElement("div"); row.className = "tree-leaf"; row.style.cssText = "padding:3px 8px;cursor:pointer;font-size:12px";
              row.textContent = `${p.pset}.${p.prop}  ·  ${p.count}×  ·  e.g. ${p.sample}`;
              row.onclick = () => { fromPset.value = p.pset; fromProp.value = p.prop; };
              detWrap.appendChild(row);
            }
            body.append(lbl, detWrap);
            const form = document.createElement("div"); form.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:2px;margin:4px 0";
            const arrow = document.createElement("span"); arrow.textContent = "→"; arrow.style.margin = "0 2px";
            const addBtn = document.createElement("button"); addBtn.className = "mini-btn"; addBtn.textContent = "+ rule";
            form.append(fromPset, fromProp, arrow, toPset, toProp, cast, addBtn);
            body.appendChild(form);
            const ruleList = document.createElement("div"); ruleList.style.margin = "6px 0"; body.appendChild(ruleList);
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "6px";
            const drawRules = () => {
              ruleList.innerHTML = "";
              rules.forEach((r, i) => {
                const row = document.createElement("div"); row.className = "selset-row";
                row.innerHTML = `<span class="selset-name" style="cursor:default">${escapeHtml(r.from_pset)}.${escapeHtml(r.from_prop)} → ${escapeHtml(r.to_pset || r.from_pset)}.${escapeHtml(r.to_prop)} <span class="meta">(${r.cast})</span></span>`;
                const del = document.createElement("button"); del.className = "selset-del"; del.textContent = "✕";
                del.onclick = () => { rules.splice(i, 1); drawRules(); };
                row.appendChild(del); ruleList.appendChild(row);
              });
            };
            addBtn.onclick = () => {
              if (!fromPset.value.trim() || !fromProp.value.trim() || !toProp.value.trim()) { notify("need from Pset + from Prop + to Prop", "error"); return; }
              rules.push({ from_pset: fromPset.value.trim(), from_prop: fromProp.value.trim(), to_pset: toPset.value.trim() || undefined, to_prop: toProp.value.trim(), cast: cast.value as PropMapRule["cast"] });
              fromProp.value = ""; toProp.value = ""; status.textContent = ""; drawRules();
            };
            const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;margin-top:4px";
            const preview = document.createElement("button"); preview.className = "mini-btn"; preview.textContent = "👁 Preview";
            preview.onclick = async () => {
              if (!rules.length) { notify("add a rule first", "error"); return; }
              try { const pl = await api.propmapPlan(pid, rules); status.textContent = `${pl.changed} value(s) would change — ` + pl.rules.map((r) => `${r.to}: ${r.matched}`).join(" · "); }
              catch (e) { notify((e as Error).message, "error"); }
            };
            const apply = document.createElement("button"); apply.className = "mini-btn"; apply.textContent = "✔ Apply + republish";
            apply.onclick = async () => {
              if (!rules.length) { notify("add a rule first", "error"); return; }
              await authorAndReload("map_properties", { rules }, `normalize ${rules.length} propert${rules.length === 1 ? "y" : "ies"}`);
            };
            actions.append(preview, apply); body.append(actions, status);
          });
        }));
        b.appendChild(toolBtn2("🏛 Load takedown (preliminary)", async () => {
          let d; try { d = await api.loadsDefaults(pid); } catch { d = { storey_count: 0, column_count: 0, storey_names: [] }; }
          const v = await promptModal("Preliminary gravity load takedown",
            [{ name: "area", label: "Typical floor area (ft²)", value: "10000", required: true },
             { name: "storeys", label: "Storeys", value: String(d.storey_count || 5) },
             { name: "columns", label: "Interior columns / floor", value: String(d.column_count || 12) },
             { name: "occ", label: "Occupancy (office/residential/retail/parking…)", value: "office" }],
            "Compute",
            `Tributary-area gravity estimate + ASCE 7 combinations — PRELIMINARY only, not a substitute for a licensed engineer. Model has ${d.storey_count} storeys · ${d.column_count} columns.`);
          if (!v) return;
          await withLoading(container, "Running load takedown", async () => {
            let r;
            try { r = await api.loadsTakedown(pid, { floor_area_sf: Number(v.area), storey_count: Number(v.storeys) || undefined, column_count: Number(v.columns) || undefined, occupancy: v.occ || "office" }); }
            catch (e) { toast((e as Error).message, "error"); return; }
            out.textContent = `col ${r.column.factored_lrfd_kip}k (LRFD)`;
            showResult("Preliminary load takedown", (body) => {
              body.appendChild(resultNote(`Typical interior column — service <b>${r!.column.service_total_kip} kip</b> `
                + `(D ${r!.column.service_dead_kip} + L ${r!.column.service_live_kip}); factored <b>${r!.column.factored_lrfd_kip} kip</b> `
                + `LRFD / <b>${r!.column.factored_asd_kip} kip</b> ASD. Footing service ${r!.footing.service_total_kip} kip.`, "ok"));
              body.appendChild(kvTable([
                { k: "Governing LRFD", v: `${r!.combinations.governing_lrfd.combo} = ${r!.combinations.governing_lrfd.kips}k` },
                { k: "Governing ASD", v: `${r!.combinations.governing_asd.combo} = ${r!.combinations.governing_asd.kips}k` },
                { k: "Dead load", v: `${r!.assumptions.dead_psf} psf (slab ${r!.assumptions.slab_self_weight_psf} + SDL ${r!.assumptions.superimposed_dead_psf})` },
                { k: "Live reduction", v: `×${r!.assumptions.live_reduction_factor}` },
              ]));
              const warn = document.createElement("div"); warn.className = "meta";
              warn.style.cssText = "margin-top:8px;font-size:11px;border-left:3px solid var(--status-warn,#ffd479);padding-left:8px";
              warn.textContent = r!.disclaimer; body.appendChild(warn);
            });
          });
        }));
        b.appendChild(toolBtn2("✅ Verified-as-built progress", () => withLoading(container, "Rolling up verified progress", async () => {
          let r;
          try { r = await api.verifiedProgress(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          if (!r.elements_total) {
            toast("No verified elements yet — run the layout check or log Field Verification records", "info");
            out.textContent = "no verified elements"; return;
          }
          out.textContent = `verified ${r.verified_pct}% · gap ${r.trust_gap}`;
          showResult("Verified-as-built progress", (body) => {
            const tone = r!.trust_gap > 10 ? "bad" : r!.trust_gap <= 0 ? "ok" : "";
            body.appendChild(resultNote(`<b>${r!.verified_pct}%</b> verified in place vs <b>${r!.claimed_pct}%</b> `
              + `claimed — trust gap <b>${r!.trust_gap} pts</b>. ${r!.elements_verified}/${r!.elements_total} elements `
              + `verified, ${r!.elements_deviated} deviated (coverage ${r!.coverage_pct}%).`, tone));
            body.appendChild(kvTable(r!.activities.slice(0, 12).map((a) => ({
              k: `${a.activity}${a.trade ? ` · ${a.trade}` : ""}`,
              v: `verified ${a.verified_pct}% / claimed ${a.planned_pct ?? 0}% · gap ${a.trust_gap} (${a.verified}/${a.elements}${a.deviated ? `, ${a.deviated} dev` : ""})`,
            }))));
            const note = document.createElement("div"); note.className = "meta";
            note.style.cssText = "margin-top:8px;font-size:11px";
            note.textContent = "Trust gap = claimed − verified %. Verified from Field Verification records (or the "
              + "layout as-installed check), rolled up to each schedule activity by GlobalId. Full report: Report Center → Verified-as-built Progress.";
            body.appendChild(note);
          });
        })));
        b.appendChild(toolBtn2("📐 Alignment check (storey + origin)", () => withLoading(container, "Checking model alignment", async () => {
          let r;
          try { r = await api.modelAlignment(pid); }
          catch { toast("Alignment needs ≥2 models — add one with “＋ Add discipline IFC”", "error"); return; }
          out.textContent = r.aligned ? "Models aligned ✓" : `${r.issues.length} alignment issue(s)`;
          toast(r.message, r.aligned ? "success" : "info");
          const tone: Record<string, string> = { high: "var(--status-crit,#e2554a)", medium: "var(--status-warn,#ffd479)", low: "var(--muted)" };
          showResult("Model alignment", (body) => {
            body.appendChild(resultNote(r!.message, r!.aligned ? "ok" : "bad"));
            body.appendChild(kvTable(r!.models.map((m) => ({ k: m.name, v: m.error ? `error: ${m.error}` : `${m.storey_count} storeys${m.georef ? " · georef" : ""}` }))));
            for (const i of r!.issues) {
              const d = document.createElement("div"); d.style.cssText = `font-size:12px;margin:3px 0;border-left:3px solid ${tone[i.severity] || "var(--muted)"};padding-left:6px`;
              d.innerHTML = `<b>${i.model}</b> — ${i.detail}`;
              body.appendChild(d);
            }
          });
        })));
        b.appendChild(toolBtn2("＋ Add discipline IFC…", () => {
          const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".ifc";
          inp.onchange = async () => {
            const file = inp.files?.[0]; if (!file) return;
            const disc = ((await askText("Add discipline IFC", { label: "Discipline (e.g. STR, MEP, ARCH):",
              value: file.name.replace(/\.ifc$/i, "").slice(0, 16) })) || "").trim();
            if (!disc) return;
            await withLoading(container, "adding discipline model", async () => {
              await api.addProjectModel(pid, file, disc);                                 // register server-side (for clash)
              await loader.loadIfc(new Uint8Array(await file.arrayBuffer()), nextId(disc)); // view it layered
              await fitToModels(); refreshFederation();
              toast(`added ${disc} discipline model — now in federated clash`, "success");
            });
          };
          inp.click();
        }));
        b.appendChild(toolBtn2("✓ Validate (IDS)", () => withLoading(container, "Validating (IDS)", async () => {
          const r = await api.validate(pid);
          out.textContent = `IDS ${r.status.toUpperCase()} — ${r.summary.passed}/${r.summary.passed + r.summary.failed}`;
          toast(`IDS ${r.status.toUpperCase()} — ${r.summary.passed} pass / ${r.summary.failed} fail`, r.status === "pass" ? "success" : "error");
          const failing = r.specifications.flatMap((s) => s.failed_guids);
          showResult("IDS validation", (body) => {
            body.appendChild(resultNote(`<b>IDS: ${r.status.toUpperCase()}</b> — ${r.summary.passed} pass / ${r.summary.failed} fail`, r.status === "pass" ? "ok" : "bad"));
            body.appendChild(kvTable(r.specifications.map((s) => ({
              k: `${s.status === "pass" ? "✓" : "✗"} ${s.name}`, v: `${s.passed}/${s.applicable}` }))));
            if (failing.length) {
              const hl = toolBtn2(`Highlight ${failing.length} failures in 3D`, async () => { await selectMap(await sets.fromGuids(failing), { fit: true }); });
              body.appendChild(hl);
            }
          });
        })));
        b.appendChild(out);
      },
      authoring: () => {
        const b = section("authoring", "Build · Advanced authoring, annotate & library", { requires: "sourceIfc", tool: true });
        const group = panel.querySelector('.tool-group[data-tool="authoring"]') as HTMLElement | null;
        if (group) group.dataset.cap = "edit";   // whole section hidden for non-editors
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px"; out.id = "au-out";
        const fix = toolBtn2("✎ Fix slabs: set LoadBearing", async () => {
          out.textContent = "editing IFC…";
          const r = await api.editIfc(pid, "set_pset", { ifc_class: "IfcSlab", pset: "Pset_SlabCommon", prop: "LoadBearing", value: true, dtype: "bool" }, true);
          const v = await api.validate(pid);
          out.innerHTML = `edited ${r.changed} slabs · IDS now: <b>${v.status.toUpperCase()}</b> · converting…`;
          const state = await waitForPublish(pid);
          if (state === "done") await loadProjectModel();
          out.innerHTML += `<br>publish: ${state}`;
        });
        fix.dataset.cap = "edit";
        const pub = toolBtn2("⟳ Republish (reconvert + reindex)", async () => {
          out.textContent = "publishing… (running in background)";
          await api.publish(pid);
          const state = await waitForPublish(pid, (s) => (out.textContent = `publish: ${s}…`));
          if (state === "done") await loadProjectModel();
          out.textContent = `publish ${state}`;
        });
        pub.dataset.cap = "edit";
        // Furnish & equip — add starter-library families (furniture / sanitary / appliances /
        // plants). Works on a generated massing model too, since the types are generated on demand.
        const furnish = document.createElement("div"); furnish.style.marginTop = "6px";
        const hint = document.createElement("div"); hint.className = "meta";
        hint.textContent = "Click a point in the model to set placement, then pick a family.";
        const sel = document.createElement("select"); sel.className = "tool-btn";
        sel.style.cssText = "display:block;width:100%;margin:4px 0"; sel.dataset.cap = "edit";
        sel.innerHTML = `<option value="">＋ Furnish & equip…</option>`;
        void api.familyLibrary().then((c) => {
          for (const [cat, items] of Object.entries(c.categories)) {
            const og = document.createElement("optgroup"); og.label = cat;
            for (const it of items) {
              const o = document.createElement("option"); o.value = it.key; o.textContent = it.label; og.appendChild(o);
            }
            sel.appendChild(og);
          }
          const ext = c.external.length ? ` · ${c.external.length} external` : "";
          hint.textContent = `${c.count} families in the library${ext}. Click a point to set placement, then pick a family — or import an IFC for more.`;
        }).catch(() => { hint.textContent = "Family library unavailable (API offline)."; });
        const place = toolBtn2("⊕ Place selected family", async () => {
          const key = sel.value;
          if (!key) { out.textContent = "pick a family first"; return; }
          const label = sel.options[sel.selectedIndex]?.text ?? key;
          const pos: [number, number] | null = lastPoint ? [lastPoint.x, -lastPoint.z] : null;
          out.textContent = `adding ${label}…`;
          await api.addFamily(pid, key, pos);
          out.textContent = `${label} added · converting…`;
          const state = await waitForPublish(pid);
          if (state === "done") await loadProjectModel();
          out.innerHTML = `added <b>${escapeHtml(label)}</b>${pos ? ` at ${pos[0].toFixed(1)}, ${pos[1].toFixed(1)} m` : " at origin"}<br>publish: ${escapeHtml(state)}`;
        });
        place.dataset.cap = "edit";
        // Import external IFC type content (manufacturer / 3rd-party families) into the project.
        const impInput = document.createElement("input");
        impInput.type = "file"; impInput.accept = ".ifc"; impInput.style.display = "none";
        const imp = toolBtn2("⇪ Import IFC families…", () => impInput.click());
        imp.dataset.cap = "edit";
        imp.title = "Import type content (families) from a manufacturer / 3rd-party IFC";
        impInput.addEventListener("change", async () => {
          const f = impInput.files?.[0]; if (!f) return;
          out.textContent = `importing families from ${f.name}…`;
          try {
            const r = await api.importFamilies(pid, f);
            if (!r.count) { out.textContent = "no new families found in that IFC"; impInput.value = ""; return; }
            const state = await waitForPublish(pid);
            if (state === "done") await loadProjectModel();
            out.innerHTML = `imported <b>${r.count}</b> famil${r.count === 1 ? "y" : "ies"} `
              + `(${r.imported.slice(0, 3).map((i) => i.name).join(", ")}${r.count > 3 ? "…" : ""}) · publish: ${state}`;
          } catch (e) { out.textContent = `import failed: ${(e as Error).message}`; }
          impInput.value = "";
        });
        furnish.append(hint, sel, place, imp, impInput);
        // AUTH-VS: open the visual node-authoring canvas (chain recipes as a graph, run in one pass)
        const nodeBtn = toolBtn2("🕸 Visual node authoring", () => {
          openNodeCanvas({
            recipes: ["add_wall", "add_column", "add_beam", "add_slab", "add_base_plate", "add_curtain_wall", "derive_analytical"],
            runGraph: async (graph) => {
              const r = await api.editGraph(pid, graph, { publish: true });
              const state = await waitForPublish(pid);
              if (state === "done") await loadProjectModel();
              return r;
            },
            notify,
          });
        });
        nodeBtn.dataset.cap = "edit";
        nodeBtn.title = "Drag recipe nodes, wire outputs → inputs, and run the graph as one GUID-stable authoring pass";
        b.append(fix, pub, furnish, nodeBtn, out);
      },
    };
    for (const key of order) builders[key]?.();
    regroupByPhase();                                        // UX-1: physical phase clusters + headers
    applyPhase(localStorage.getItem(RIBBON_KEY) || "All");   // UX-1: restore the active lifecycle tab
  }

  /** Hashed hue for an IFC class — the stable per-class fallback color. */
  function classHue(s: string): string {
    let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360;
    return `hsl(${h} 65% 55%)`;
  }

  /** The swatch/paint color for an IFC class under the current color mode: the discipline's canonical
   * color when coloring by discipline (unmapped classes fall back to the hashed hue), else the hue. */
  function colorFor(cls: string): string {
    if (colorMode === "discipline" && discTree) {
      const code = disciplineOfClass(cls);
      if (code && discTree.colors[code]) return discTree.colors[code];
    }
    return classHue(cls);
  }

  // ---- issues / pins -------------------------------------------------------
  const pins = new PinOverlay(viewer.components, viewer.world, api, async (topic, vp) => {
    restoreCamera(viewer.world, vp);
    if (topic.element_guids?.[0]) await selectByGuid(topic.element_guids[0]);
    setStatus(`restored: ${topic.title}`);
  });

  // --- Clash & coordination panel (its own rail toggle) --------------------
  // Surfaces the clash/coordination engine as a first-class panel: run cross-discipline clash, click a
  // clash to fly to it, see coordination KPIs, and promote to tracked issues (BCF). Modeled on Autodesk
  // Model Coordination's clash-group list. All backed by endpoints that already ship.
  async function buildClashPanel() {
    const panel = $("panel-clash");
    if (!panel) return;
    panel.innerHTML = `<div class="section-title">Clash &amp; coordination</div>`;
    if (!projectId) { panel.insertAdjacentHTML("beforeend", `<div class="meta">Open a project to run clash coordination.</div>`); return; }
    const intro = document.createElement("div"); intro.className = "meta"; intro.style.cssText = "font-size:11px;margin-bottom:8px;line-height:1.4";
    intro.textContent = "Detect cross-discipline interferences, click a clash to fly to it in 3D, and promote to a tracked issue (BCF).";
    panel.appendChild(intro);
    const cbtn = (label: string, on: () => void, cap?: "edit" | "review") => {
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label;
      b.style.cssText = "display:block;width:100%;text-align:left;margin:3px 0"; if (cap) b.dataset.cap = cap;
      b.onclick = on; return b;
    };
    const out = document.createElement("div"); out.className = "meta"; out.style.cssText = "margin:6px 0;font-size:11.5px;line-height:1.45";
    const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:2px;max-height:44vh;overflow:auto;margin-top:4px";
    const renderClashes = (clashes: { a_class: string; b_class: string; a_guid: string; b_guid: string; a_model: string; b_model: string; volume: number }[]) => {
      list.innerHTML = "";
      if (!clashes.length) { list.innerHTML = `<div class="meta" style="color:var(--status-good)">No hard clashes 🎉</div>`; return; }
      list.insertAdjacentHTML("beforeend", `<div class="section-title" style="margin:4px 0 2px">${clashes.length} clash${clashes.length === 1 ? "" : "es"} — click to inspect</div>`);
      clashes.slice(0, 300).forEach((c, i) => {
        const row = document.createElement("button"); row.className = "tool-btn";
        row.style.cssText = "display:flex;justify-content:space-between;gap:8px;width:100%;text-align:left;font-size:11px;padding:4px 7px";
        row.innerHTML = `<span>${i + 1}. ${c.a_class.replace("Ifc", "")} <span style="color:var(--status-crit)">✕</span> ${c.b_class.replace("Ifc", "")}</span>`
          + `<span class="meta">${c.volume.toFixed(3)} m³</span>`;
        row.title = `${c.a_model} vs ${c.b_model} — click to select + zoom to the clash`;
        row.onclick = () => void selectByGuid(c.a_guid || c.b_guid, true).then(() => setStatus(`clash ${i + 1}: ${c.a_class} ✕ ${c.b_class}`));
        list.appendChild(row);
      });
    };
    panel.appendChild(cbtn("💥 Run clash — all disciplines", () => void withLoading(panel, "Running federated clash", async () => {
      try {
        const r = await api.clashFederated(projectId!, { create_topics: true, coordinate: true });
        const co = r.coordination;
        out.innerHTML = `<b>${r.count}</b> clashes · ${r.disciplines.length} disciplines · <b>${r.created_topics}</b> issue(s)`
          + (co ? `<br>${co.new} new · ${co.active} active · ${co.resolved} resolved${co.reduction ? ` · ${Math.round(co.reduction * 100)}% ↓` : ""}` : "");
        renderClashes(r.clashes);
      } catch {
        out.innerHTML = `Federated clash needs ≥2 layered models. Add a discipline IFC (Tools → Models federation), or run the single-model check below.`;
        list.innerHTML = "";
      }
    }), "edit"));
    panel.appendChild(cbtn("⚡ Single-model check (structure ✕ MEP/walls)", () => void withLoading(panel, "Running clash", async () => {
      try {
        const r = await api.runClash(projectId!, { a: "IfcBeam,IfcSlab,IfcColumn,IfcStair", b: "IfcDuctSegment,IfcPipeSegment,IfcWall", min_volume: 0.02 });
        out.innerHTML = `<b>${r.count}</b> clashes · <b>${r.created_topics}</b> issue(s) created. Open <b>Issues</b> to coordinate.`;
        list.innerHTML = "";
      } catch (e) { out.textContent = `failed: ${(e as Error).message}`; }
    }), "edit"));
    panel.appendChild(cbtn("📊 Coordination metrics", () => void (async () => {
      try {
        const m = await api.clashMetrics(projectId!);
        showResult("Clash coordination metrics", (body) => {
          body.appendChild(resultNote(`<b>${m.open}</b> open · <b>${m.closed}</b> closed · ${Math.round(m.resolution_rate * 100)}% resolved · ${m.runs} run(s)`, m.open ? "bad" : "ok"));
          body.appendChild(kvTable([
            { k: "By discipline pair", v: Object.entries(m.by_discipline).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—" },
            { k: "By severity", v: Object.entries(m.by_severity).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—" },
            { k: "Reappearance rate", v: `${Math.round(m.reappearance_rate * 100)}%` },
          ]));
        });
      } catch (e) { toast(`metrics: ${(e as Error).message}`, "error"); }
    })()));
    panel.appendChild(cbtn("📌 Open in Issues (BCF)", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
    panel.append(out, list);
  }

  async function refreshIssues() {
    if (!projectId) return;
    const topics = await api.pins(projectId);
    const panel = $("panel-issues");
    panel.innerHTML = `<div class="section-title">Issues (${topics.length})</div>`;
    const newBtn = document.createElement("button");
    newBtn.className = "tool-btn"; newBtn.dataset.cap = "review"; newBtn.textContent = "+ RFI from selection"; newBtn.style.marginBottom = "8px";
    newBtn.onclick = createRfiFromSelection;
    panel.appendChild(newBtn);
    for (const t of topics) panel.appendChild(issueCard(t));
  }
  function issueCard(t: Topic): HTMLElement {
    const el = document.createElement("div"); el.className = "issue";
    el.innerHTML = `<div class="t">${t.title}</div><div class="meta"><span class="badge ${t.type}">${t.type}</span> <span class="badge ${t.status}">${t.status}</span> ${t.assignee ?? ""}</div>`;
    el.onclick = async () => {
      const vps = projectId ? await api.viewpoints(projectId, t.id) : [];
      restoreCamera(viewer.world, vps[0] ?? null);
      if (t.element_guids?.[0]) await selectByGuid(t.element_guids[0]);
    };
    return el;
  }
  async function createRfiFromSelection() {
    if (!projectId || !selection) { setStatus("select an element first"); return; }
    const entry = Object.entries(selection)[0];
    if (!entry) { setStatus("select an element first"); return; }
    const [modelId, ids] = entry;
    const model = loader.fragments.list.get(modelId);
    const localId = [...ids][0];
    if (localId === undefined) { setStatus("select an element first"); return; }
    const [guid] = model ? await model.getGuidsByLocalIds([localId]) : [null];
    // AI/template draft from the selected element's context (Procore Draft-RFI parity)
    let suggestedTitle = "New RFI";
    let description: string | undefined;
    if (guid) {
      const note = (await askText("Describe the issue", { label: "Briefly describe the issue (optional — leave blank to let AI draft it):", value: "" })) || undefined;
      try {
        const el = await api.element(projectId, guid);
        const d = await api.draftRfi(projectId, el, note);
        suggestedTitle = d.subject || suggestedTitle;
        description = d.question;
        setStatus(d.source === "claude" ? `AI-drafted RFI (${d.discipline})` : `drafted RFI (${d.discipline})`);
      } catch { if (note) description = note; }
    }
    const title = (await askText("RFI title", { label: "RFI title:", value: suggestedTitle })) || suggestedTitle;
    const topic = await api.createTopic(projectId, {
      type: "rfi", title, description, status: "open",
      anchor: lastPoint ? { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z } : undefined,
      element_guids: guid ? [guid] : undefined,
    });
    if (lastPoint) {
      await api.addViewpoint(projectId, topic.id, {
        camera: { type: "perspective", position: cameraPos(), target: { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z }, fov: 60 },
        components: guid ? [guid] : [],
      });
    }
    await refreshIssues();
    await pins.load(projectId);
    setStatus(`created RFI: ${title}`);
  }
  function cameraPos() {
    const p = new THREE.Vector3();
    viewer.world.camera.controls.getPosition(p);
    return { x: p.x, y: p.y, z: p.z };
  }

  function fragsForProject(name: string): [string, string][] {
    if (/basichouse/i.test(name)) return [["/basichouse.frag", "BasicHouse-ARCH"]];
    if (/school/i.test(name)) return [["/school_str.frag", "school-STR"], ["/school_arq.frag", "school-ARQ"]];
    return [];
  }

  // ---- keyboard (viewer keys; nav keys stay in main) -----------------------
  function handleKey(key: string): boolean {
    switch (key) {
      case "f": void fitToModels(); return true;
      case "escape": void selectMap(null); return true;
      case "m": measure.setMode(measure.mode === "length" ? "off" : "length"); setStatus(`measure: ${measure.mode}`); return true;
      case "a": measure.setMode(measure.mode === "area" ? "off" : "area"); setStatus(`measure: ${measure.mode}`); return true;
      case "s": section.enabled = !section.enabled; setStatus(`section ${section.enabled ? "on (dbl-click face)" : "off"}`); return true;
      case "h": void visibility.showAll(); void colorize.reset(); return true;
      default: return false;
    }
  }

  // debug hook for automated/preview testing
  (window as unknown as Record<string, unknown>).__viewer = { viewer, loader, fitToModels, selectByGuid, openFile, referenceModels, THREE };

  // ---- self-initialise: load the project model + build panels --------------
  void (async () => {
    applySettings();
    await withLoading(container, `Loading ${ctx.projectName || "model"}`, async () => {
      if (projectId && await loadProjectModel()) return;
      const frags = ctx.projectName ? fragsForProject(ctx.projectName) : [["/school_str.frag", "school-STR"], ["/school_arq.frag", "school-ARQ"]];
      for (const [file, id] of frags) {
        if (!file || !id) continue;
        const res = await fetch(import.meta.env.BASE_URL + file.replace(/^\//, ""));
        if (res.ok) { await loader.loadFragments(await res.arrayBuffer(), id); modelLabels.set(id, id); }
      }
      refreshFederation();
      await fitToModels();
    });
    if (projectId) {
      try { await buildPanels(); } catch (e) { console.warn("panels:", e); }
    }
    void buildToolsPanel();
    void buildClashPanel();
  })();

  // rebuild the tools + clash panels when the persona changes (reorders primary vs "More tools")
  window.addEventListener("aec:persona", () => { void buildToolsPanel(); void buildClashPanel(); });

  return {
    applySettings, selectByGuid, reloadModelPins, fitToModels, refreshIssues,
    anchorPoint: () => (lastPoint ? { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z } : null),
    selectedGuidValue: () => selectedGuid,
    triggerOpen, openFile, addReferenceObject, loadSample, exportFrag, exportIfc, handleKey,
    // Open the authoring surface: rebuild the tools panel (so a just-published model's Draft section
    // appears) and expand + scroll to the "Draft — author elements" group. Called when a new model is
    // started from scratch, so the drawing tools are front-and-centre instead of buried.
    openAuthoring: () => {
      void Promise.resolve(buildToolsPanel()).then(() => {
        const g = document.querySelector('[data-tool="draft"]');
        if (!g) return;
        g.classList.add("open");
        g.querySelector(".tool-group-head")?.setAttribute("aria-expanded", "true");
        localStorage.setItem("tools-open:draft", "1");
        g.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    },
    onModelShown: () => {
      // Wait for the container to actually have dimensions (the workspace just toggled visible, so
      // layout may not have flushed yet) before resizing — resizing at 0×0 sets a NaN aspect.
      let tries = 60;
      const ready = () => {
        if ((!viewer.container.clientWidth || !viewer.container.clientHeight) && tries-- > 0) {
          requestAnimationFrame(ready); return;
        }
        viewer.world.renderer?.resize();   // container now has real dimensions → valid camera aspect
        const camNaN = Number.isNaN(viewer.world.camera.three.position.x);
        if (fitPending || camNaN) void fitToModels(); else void loader.fragments.core.update(true);
      };
      ready();
    },
  };
}
