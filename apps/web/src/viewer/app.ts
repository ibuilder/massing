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
import { applyDynamicInput, polarConstrain, resolveSnap } from "./snapEngine";
import {
  OVERRIDE_LABEL, createSnapOverride, overrideCandidates, type OverrideKind,
} from "./snapOverride";
import { canAcceptDraftDrag, dropCompletion, readDraftDragKey } from "./railDrag";
import { parseDynConstraint } from "./dynInput";
import { parseCadCommand } from "./cadCommands";
import { ModelLoader } from "./loader";
import { loadProjectModel as loadProjectModelImpl } from "./loadProjectModel";
import { DeltaStore, deltaCommitter, deltaIndicator } from "./deltaCommit";
import { makeWaitForPublish } from "./publishWait";
import { buildElementProps, buildRawProps } from "./propsView";
import { buildInspectorTabs, type InspectorData, type TabKey } from "./inspectorTabs";
import { buildLifecycleStrip } from "../ui/lifecycleStrip";
import { type ModelIdMap } from "./modelIds";
import { photoVerdict, photoVerdictSummary } from "../ui/photoVerdict";
import { askText } from "../ui/prompt";
import { confirmModal } from "../ui/modal";
import { SelectionSets } from "./selectionSets";
import { MeasureTool } from "../tools/measure";
import { SectionTool } from "../tools/section";
import { installMeasureTools, installSectionBox } from "./measureSection";
import { installWalkMode } from "./walkMode";
import { createRailToolbox } from "./railToolbox";
import { VisibilityTool } from "../tools/visibility";
import { ColorizeTool } from "../tools/colorize";
import { LayerManager } from "../tools/layers";
import { loadSelSets, saveSelSets } from "../tools/selectionSetsStore";
import { OriginTool } from "../tools/origin";
import { installDraftPanel, type ArmedDraft, type DraftPanelHandle } from "./draft/draftPanel";
import { type FamilyDef } from "./draft/draftCatalog";
import { GridOverlay } from "./draft/gridOverlay";
import { LogisticsOverlay } from "./draft/logisticsOverlay";
import { DraftProxyLayer } from "./draft/draftProxy";
import { TransformGizmo } from "./draft/transformGizmo";
import { PushPullGizmo, stretchTransform } from "./draft/pushPull";
import { PlanPane } from "./planPane";
import { type PlanBounds, validatePlacement } from "./placeValid";
import { planBoundsFromModels } from "./modelBounds";
import { buildExportsSection } from "./tools/exportsSection";
import { buildQaSection } from "./tools/qaSection";
import { buildAnalyseSection } from "./tools/analyseSection";
import { buildAuthoringSection } from "./tools/authoringSection";
import { buildProjectPanels } from "./tools/projectPanel";
import { GuideUnderlay, openUnderlayPanel } from "./guideUnderlay";
import { type SpatialElement, type SpatialScope, nextScope, scopeSelection } from "./spatialSelect";
import { DraftPointHistory } from "./draftHistory";
import { DEFAULT_RISE_M, runReadout } from "./draft/stairLive";
import { createTestHarness } from "@massingifc/plugin-sdk";

import { modelIdMapFromRefs } from "../kernel/elementRef";
import { markupPlugin, reloadMarkup } from "../kernel/markupPlugin";
import type { ModulePin } from "../api/types";
import { PinOverlay, restoreCamera } from "../pins/pins";
import { type ApiClient, type DisciplineTree, type ElementProps, type Topic } from "../api/client";
import { escapeHtml, toast, withLoading } from "../ui/feedback";
import { showResult, kvTable, resultNote } from "../ui/result";

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
  const waitForPublish = makeWaitForPublish(api);
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
  // FOURD-SIM playback teardown (restores visibility). A REF rather than a `let` since
  // R39-DECOMP-VIEWER ③: the analyse section writes it, and ownership stays here so its
  // lifetime still spans `buildToolsPanel` running again on a persona change.
  const fourD: { dispose: (() => void) | null } = { dispose: null };
  const origin = new OriginTool();

  let selection: ModelIdMap | null = null;
  let lastPoint: THREE.Vector3 | null = null;
  let selectedGuid: string | null = null;
  // R38-SYNC-SELECT: every selection change flows through selectMap, which is defined long before
  // the plan pane exists — so the pane subscribes through this hook rather than selectMap reaching
  // forward to a const that has not been initialised yet.
  let onSelectionChanged: (guid: string | null) => void = () => {};
  // A29-SPATIAL-SELECT — re-clicking a selected element widens the scope (item → level → model).
  // The anchor is the CLICKED element, tracked separately from selectedGuid because a widened
  // selection sets selectedGuid to the set's first element, which may not be the one under the mouse.
  let spatialAnchor: string | null = null;
  let spatialScope: SpatialScope = "item";
  let spatialElements: SpatialElement[] = [];
  let editInPlace = false;            // P5: show the move gizmo on the selected element
  let gizmo: TransformGizmo | null = null;
  let pushPullOn = false;             // R38-PUSHPULL: drag the top handle to deepen the extrusion
  let ppGizmo: PushPullGizmo | null = null;
  let modelCount = 0;
  // track a human label per loaded model so the federation panel can list disciplines
  const modelLabels = new Map<string, string>();
  // R42-COMMIT-DELTA — edits authored but not yet in the base fragment. `refreshDeltas` is set
  // by the rail when it builds its indicator; null until then, which is why every call is `?.`.
  const deltas = new DeltaStore();
  let refreshDeltas: (() => void) | null = null;
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
  /** R26-TOOLBAR: re-lay the floating toolbar for the current context. Assigned once every tool has
   *  registered (the layout pass runs last), so selection changes before then are harmless no-ops. */
  let relayoutTools: () => void = () => {};

  async function selectMap(map: ModelIdMap | null, opts: { guid?: string; fit?: boolean } = {}) {
    if (selection) await loader.fragments.resetHighlight(selection);
    selection = map;
    relayoutTools();          // what you can do depends on what you have selected
    if (!map) { gizmo?.hide(); ppGizmo?.hide(); propsHint(); updateInfoBox(null); props5d.innerHTML = ""; propsVerify.innerHTML = ""; propsLinks.replaceChildren(); onSelectionChanged(null); spatialAnchor = null; spatialScope = "item"; return; }
    await loader.fragments.highlight(SELECT_MAT(), map);
    await loader.fragments.core.update(true);
    if (opts.fit) await fitToItems(map);
    await showProps(map, opts.guid);
    if (editInPlace) await attachGizmo(map);
    else if (pushPullOn) await attachPushPull(map);
    onSelectionChanged(opts.guid ?? selectedGuid);
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

    // R22-PHOTO-CV — the front door for element-attached photos. The upload endpoint and its whole
    // analysis stack (quality gate, change screening, detection) previously had NO caller in this
    // app: reachable by API, unreachable by a person. `capture="environment"` makes a phone open the
    // rear camera directly rather than the gallery, which is what someone standing at the element
    // wants.
    const photoIn = document.createElement("input");
    photoIn.type = "file"; photoIn.accept = "image/*"; photoIn.hidden = true;
    photoIn.setAttribute("capture", "environment");
    const photoBtn = document.createElement("button");
    photoBtn.className = "file-btn"; photoBtn.textContent = "\u{1F4F7} Photo";
    photoBtn.style.cssText = "font-size:11px;padding:2px 8px";
    photoBtn.title = "Attach a field photo to this element";
    photoBtn.onclick = () => photoIn.click();
    const verdict = document.createElement("div");
    verdict.className = "meta"; verdict.style.cssText = "margin-top:4px;line-height:1.45";
    photoIn.onchange = async () => {
      const f = photoIn.files?.[0]; if (!f) return;
      photoIn.value = "";                       // so re-picking the SAME file fires change again
      verdict.textContent = "uploading\u2026";
      photoBtn.disabled = true;
      try {
        const res = await api.uploadVerificationPhoto(projectId!, guid, f, f.name || "photo.jpg");
        verdict.textContent = "";
        const lines = photoVerdict(res);
        if (!lines.length) verdict.textContent = "photo attached";
        for (const ln of lines) {
          const el = document.createElement("div");
          // textContent, never innerHTML: these strings carry server-derived text.
          el.textContent = (ln.tone === "warn" ? "\u26A0 " : ln.tone === "ok" ? "\u2713 " : "\u00B7 ") + ln.text;
          if (ln.tone === "warn") el.style.color = "#e2554a";
          verdict.appendChild(el);
        }
        setStatus(photoVerdictSummary(res) || "photo attached");
      } catch (e) {
        verdict.textContent = "upload failed: " + (e as Error).message;
        verdict.style.color = "#e2554a";
      } finally { photoBtn.disabled = false; }
    };
    bar.append(photoBtn, photoIn);
    row.appendChild(bar); row.appendChild(verdict); propsVerify.appendChild(row);
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
    const propsView = buildElementProps(el, hooks);
    // R38-LIVE-PARAMS (slices 1+2) — the element's one server-editable GEOMETRIC parameter today:
    // extrusion depth (wall height / slab thickness / mass rise), the same commit path as the
    // push/pull gesture. Slice 1 is the number field; slice 2 is the SLIDER with a live
    // base-anchored ghost while dragging (the tested stretchTransform from push/pull — the bottom
    // face never moves, so the preview agrees with what the recipe commits) and commit on release.
    // Prefilled from the selection's bounding box; non-extrusions refused via the recipe error path.
    let geoRow: HTMLElement | null = null;
    if (connected && projectId) {
      geoRow = document.createElement("div");
      geoRow.style.cssText = "display:flex;align-items:center;gap:6px;margin:0 0 8px;padding:6px 10px;"
        + "border:1px solid var(--line);border-radius:8px;background:var(--panel2);font-size:12px;flex-wrap:wrap";
      const lbl = document.createElement("span");
      lbl.textContent = "Depth / height (m)";
      lbl.style.cssText = "color:var(--muted,#94a3b8)";
      const inp = document.createElement("input");
      inp.type = "number"; inp.step = "0.05"; inp.min = "0.02"; inp.style.cssText = "width:70px";
      const slider = document.createElement("input");
      slider.type = "range"; slider.min = "0.02"; slider.step = "0.05";
      slider.style.cssText = "flex:1;min-width:90px";
      slider.disabled = true;                       // until the current depth is known
      const elBox = new THREE.Box3();               // the selection's bbox, once resolved
      let ghost: THREE.LineSegments | null = null;  // live preview outline while sliding
      const dropGhost = () => {
        if (ghost) { viewer.world.scene.three.remove(ghost); ghost.geometry.dispose(); ghost = null; }
      };
      if (selection) {
        void loader.fragments.getBBoxes(selection).then((boxes) => {
          for (const b of boxes) elBox.union(b);
          if (elBox.isEmpty()) return;
          const h0 = elBox.max.y - elBox.min.y;
          inp.value = h0.toFixed(2);
          // range spans collapse→triple the current depth: enough travel to feel, no silly extremes
          slider.max = Math.max(1, 3 * h0).toFixed(2);
          slider.value = h0.toFixed(2);
          slider.disabled = false;
        }).catch(() => { /* leave blank — the field still accepts a typed value */ });
      }
      const previewDepth = (depth: number) => {
        // live ghost: the element's outline stretched from ITS BASE to the new depth
        if (elBox.isEmpty() || !(depth > 0)) return;
        const h0 = elBox.max.y - elBox.min.y;
        if (!(h0 > 0)) return;
        if (!ghost) {
          const size = elBox.getSize(new THREE.Vector3());
          const g = new THREE.EdgesGeometry(new THREE.BoxGeometry(size.x, size.y, size.z));
          ghost = new THREE.LineSegments(g, new THREE.LineBasicMaterial(
            { color: 0xffb000, transparent: true, opacity: 0.95, depthTest: false }));
          viewer.world.scene.three.add(ghost);
        }
        const t = stretchTransform(h0, depth - h0, elBox.min.y);
        const c = elBox.getCenter(new THREE.Vector3());
        ghost.position.set(c.x, t.centerY, c.z);
        ghost.scale.y = t.scaleY;
        setStatus(`depth ${depth.toFixed(2)} m — release to apply`);
      };
      const commit = async (depth: number) => {
        dropGhost();
        if (!Number.isFinite(depth) || depth <= 0) { notify("enter a positive depth in metres", "error"); return; }
        await authorAndReload("set_extrusion_depth", { guid: el.guid, depth }, "depth edit");
        try { renderProps(await api.element(projectId!, el.guid)); } catch { /* index rebuilding */ }
      };
      slider.oninput = () => { inp.value = slider.value; previewDepth(Number(slider.value)); };
      slider.onchange = () => { void commit(Number(slider.value)); };   // release = the decision
      const apply = document.createElement("button");
      apply.className = "tool-btn"; apply.textContent = "Apply";
      apply.onclick = () => void commit(Number(inp.value));
      geoRow.append(lbl, inp, slider, apply);
      // R38-LIVE-PARAMS slice 3 (chips) — the profile's two plan dimensions, editable through
      // set_profile_dims. The server REFUSES non-rectangular profiles by design (which dimension
      // "width" means on an I-section is not this UI's judgement to make on a fabricator's behalf),
      // and that refusal IS the chip's unavailable state: the first refused edit greys both chips
      // for this selection, labelled with the reason, rather than pretending the edit didn't land.
      // Prefill is deliberately absent — the world bbox lies about a rotated element's profile, and
      // a wrong prefill invites committing it. An empty chip edits nothing (server: omitted
      // dimension comes back unchanged, never zeroed).
      const dimChip = (label: string, param: "width" | "length") => {
        const chip = document.createElement("span");
        chip.style.cssText = "display:inline-flex;align-items:center;gap:3px;border:1px solid "
          + "var(--line);border-radius:12px;padding:1px 8px;font-size:11px";
        const t = document.createElement("span"); t.textContent = label; t.style.color = "var(--muted,#94a3b8)";
        const v = document.createElement("input");
        v.type = "number"; v.step = "0.05"; v.min = "0.02"; v.placeholder = "m";
        v.style.cssText = "width:52px;border:none;background:transparent;font-size:11px";
        v.onkeydown = (e) => { if (e.key === "Enter") v.blur(); };
        v.onblur = async () => {
          const val = Number(v.value);
          if (!v.value || !Number.isFinite(val) || val <= 0) return;   // empty chip edits nothing
          const r = await authorAndReload("set_profile_dims", { guid: el.guid, [param]: val }, `${label} edit`);
          if (r.applied) {
            try { renderProps(await api.element(projectId!, el.guid)); } catch { /* index rebuilding */ }
          } else if (r.refused) {
            // the recipe refused (non-rectangular profile) — grey both chips for this selection.
            // A publish flake (neither applied nor refused) leaves the chips editable to retry.
            for (const c of geoRow!.querySelectorAll<HTMLElement>("[data-dim-chip]")) {
              c.style.opacity = "0.45";
              c.title = "profile is not rectangular — section dimensions are the fabricator's, not editable here";
              c.querySelector("input")?.setAttribute("disabled", "true");
            }
          }
        };
        chip.append(t, v);
        chip.dataset.dimChip = param;
        return chip;
      };
      geoRow.append(dimChip("W", "width"), dimChip("L", "length"));
    }
    // R26-INSPECTOR ② — the strip is the SPINE of this panel, so it sits above the tabs rather than
    // inside one of them: it summarises all four, and burying it in Properties would make the summary
    // a peer of the things it summarises.
    //
    // Properties renders IMMEDIATELY and never waits on a fetch. The other three tabs start
    // `unknown` — which is exactly true, because nothing has been requested yet — and fill in as
    // their data lands. Starting them at "empty" would state an absence nobody had checked for.
    let insp: InspectorData = { fived: null, lifecycle: null };
    let activeTab: TabKey = "properties";
    const paint = () => {
      const kids: HTMLElement[] = [head];
      if (geoRow) kids.push(geoRow);
      if (insp.lifecycle) kids.push(buildLifecycleStrip(insp.lifecycle));
      kids.push(buildInspectorTabs(propsView, insp,
                                   { active: activeTab, onSelect: (k) => { activeTab = k; } }));
      wrap.replaceChildren(...kids);
    };
    paint();
    propsBody.replaceChildren(wrap);
    updateInfoBox(el);
    if (connected && projectId) {
      const forGuid = el.guid;
      // Two independent fetches, each repainting on arrival. A failure leaves its tab `unknown`
      // rather than `none`: an older server with no such route has told us nothing about this
      // element, and rendering that as "no cost" would be an absence we invented.
      void api.elementLifecycle(projectId, forGuid).then((lc) => {
        if (selectedGuid !== forGuid) return;              // selection moved on while we waited
        insp = { ...insp, lifecycle: lc };
        paint();
      }).catch(() => { /* no lifecycle route (older server): strip stays absent, tabs stay unknown */ });
      void api.element5d(projectId, forGuid).then((f) => {
        if (selectedGuid !== forGuid) return;
        insp = { ...insp, fived: f };
        paint();
      }).catch(() => { /* no 5D route: Cost and Schedule stay `unknown`, never `none` */ });
    }
  }

  async function selectByGuid(guid: string, fit = false) {
    selectedGuid = guid;
    await selectMap(await sets.fromGuids([guid]), { guid, fit });
  }

  /** UX-ACT: select a whole set of GUIDs at once — the target of a `select_elements` resolve action
   *  (a rule's failing elements, a clash set). The properties panel keys off a single element, so it
   *  shows the first; the highlight covers them all. */
  async function selectByGuids(guids: string[], fit = true) {
    const list = (guids || []).filter(Boolean);
    if (!list.length) return;
    selectedGuid = list[0]!;
    // KERNEL-ADOPT ①: resolve reports what it could NOT find. Before v0.3.713 those GlobalIds were
    // dropped, so a rule's 10 failing elements could highlight 7 with nothing said — and a short
    // selection reads as "the model changed", not "3 of these are not in any loaded model".
    const outcome = await sets.resolve(list);
    await selectMap(modelIdMapFromRefs(outcome.refs), { guid: list[0]!, fit });
    if (!outcome.complete) {
      const n = outcome.unresolved.length;
      setStatus(`${outcome.refs.length} of ${list.length} selected — ${n} `
        + `GlobalId${n === 1 ? "" : "s"} not in any loaded model`);
    }
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
    // A29-SPATIAL-SELECT — re-clicking the anchored element widens: item → its level → the whole
    // model → back to the item. Built on the storey the MODEL states per element, so an element
    // with no level skips the level step rather than selecting an invented "(no level)" grab-bag.
    if (guid && guid === spatialAnchor) {
      const me = spatialElements.find((e) => e.guid === guid);
      spatialScope = nextScope(spatialScope, !!me?.storey);
      const sel = scopeSelection(guid, spatialScope, spatialElements);
      if (spatialScope === "item") {
        selectedGuid = guid;
        await selectMap({ [hit.fragments.modelId]: new Set([hit.localId]) }, { guid });
      } else {
        await selectByGuids(sel.guids, false);
      }
      setStatus(`selected ${sel.label} — click again to widen`);
      return;
    }
    spatialAnchor = guid ?? null;
    spatialScope = "item";
    selectedGuid = guid ?? null;
    await selectMap({ [hit.fragments.modelId]: new Set([hit.localId]) }, { guid: guid ?? undefined });
    setStatus(guid ? `selected ${guid} — click again to select its level` : `selected ${hit.localId}`);
  });
  // ---- RAIL-DRAG: drop a palette element onto the canvas ---------------------
  //
  // A second GESTURE onto the click pipeline, never a second pipeline: the drop arms the tool and
  // then hands the event straight to `captureDraftPoint`, so snapping, typed constraints, inference,
  // the grid and `placeValid` all apply exactly as they do to a click. DragEvent extends MouseEvent,
  // so it is literally the same input that function already takes.
  //
  // `dragover` must decide from `types` alone — the payload is unreadable there (protected mode), and
  // reading it would silently refuse every drop. See `railDrag.ts`.
  container.addEventListener("dragover", (e) => {
    if (!canAcceptDraftDrag(e.dataTransfer)) return;      // a file/text drag is left for others
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
    container.classList.add("rail-drag-over");
  });
  const clearDragCue = () => container.classList.remove("rail-drag-over");
  container.addEventListener("dragleave", (e) => { if (e.target === container) clearDragCue(); });
  container.addEventListener("drop", async (e) => {
    const key = readDraftDragKey(e.dataTransfer);
    clearDragCue();
    if (!key) return;                                     // not ours — do not preventDefault
    e.preventDefault();
    // `armByKey` notifies and returns null when the key is unknown or authoring is unavailable
    // (no project / no source IFC), so a refused drop already explains itself.
    if (!draftHandle?.armByKey(key)) return;
    const spec = armed;
    if (!spec) return;
    mouse.set(e.clientX, e.clientY);
    const hit = await Promise.race([
      loader.fragments.raycast({
        camera: viewer.world.camera.three, mouse, dom: viewer.world.renderer!.three.domElement,
      }),
      new Promise<null>((res) => window.setTimeout(() => res(null), 1500)),
    ]);
    await captureDraftPoint(e, hit ?? null);
    // One drop is one point. Only a points:1 element is finished by it; the rest keep the tool armed,
    // and are told so rather than left to wonder whether the drag worked.
    const done = dropCompletion(spec.points, spec.label);
    if (!done.completes) notify(done.message, "info");
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
  const { openFile, addReferenceObject, exportFrag, exportIfc, triggerOpen } = fileIO;

  // ---- the toolbox lives in the RAIL, not over the model (RAIL-TOOLBOX) -----
  // The window is a canvas; the rail is the instrument. `toolBtn` is the one seam every tool passes
  // through, so re-parenting here moves all 28 without touching a single call site — and a pass
  // that only moves nodes cannot lose one.
  const viewerTools = $("viewer-tools");
  viewerTools.style.display = "none";   // the floating bar is gone; kept in the DOM as the old anchor
  const railToolbox = createRailToolbox();
  function toolBtn(icon: string, title: string, onClick: (b: HTMLButtonElement) => void, cap?: "edit" | "review") {
    const b = document.createElement("button");
    b.textContent = icon; b.className = "tool-btn icon-btn"; b.title = title;
    b.setAttribute("aria-label", title);
    if (cap) b.dataset.cap = cap;   // hidden by CSS when the caller lacks the project capability
    b.onclick = () => onClick(b);
    railToolbox.place(b, title);
    return b;
  }
  /** Was a separator in the icon row. The rail groups by heading, so this is now a no-op kept for
   *  the call sites that still mark where a group ended — deleting them is a separate tidy. */
  function toolDivider(_cap?: "edit" | "review") { /* groups are headings in the rail now */ }
  // REL-4 leaf: the measure / visibility button group lives in measureSection.ts
  const msDeps = {
    viewer, loader, toolBtn, setStatus, notify, measure, section,
    selection: () => selection, visibility, colorize,
  };
  installMeasureTools(msDeps);
  // R17 WALK-MODE — first-person WASD walkthrough (pointer-lock; Esc exits back to orbit)
  installWalkMode({ viewer, canvas: viewer.world.renderer!.three.domElement, toolBtn, setStatus });
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
  toolBtn("🖼", "Guide underlay — pin a scanned plan to this level and trace over it", () => {
    openUnderlayPanel({
      underlay: guideUnderlay, levelZ: () => activeStoreyZ, notify, showResult,
    });
  }, "edit");

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
  // R38-STAIR-LIVE — while a stair/ramp run is being dragged out, say what THIS length means
  // (riser count / tread, or slope) against the server's limits, before anything is authored.
  // One listener, installed once; every other armed tool falls through runReadout() as null.
  container.addEventListener("pointermove", (e) => {
    if (!armed || armPts.length < 1) return;
    const readout = armed.key === "stair" || armed.key === "ramp" ? (() => {
      const p = screenToGround(e);
      if (!p) return null;
      const a = armPts[armPts.length - 1]!;
      const run = Math.hypot(p.x - a.x, p.z - a.z);
      return runReadout(armed.key, DEFAULT_RISE_M, run);
    })() : null;
    if (readout) setStatus(readout.text);
  });
  // REL-4 leaf: the KEYS 2-letter shortcuts, the typed distance/angle constraint (dynamic input),
  // and the snap-glyph feedback live in keysDyn.ts; the handle exposes the dyn buffer for the draft
  // flow and Escape routes back through disarmDraft.
  // AUTH-SNAP-OVERRIDE — one-shot osnap, armed by a two-letter code and spent by the next pick.
  const snapOverride = createSnapOverride();
  const keysDyn = installKeysDyn({
    container, notify,
    isArmed: () => !!armed, armedPoints: () => armPts.length,
    draftHandle: () => draftHandle, onEscape: () => disarmDraft(),
    snapOverride,
  });
  const setDynBuf = keysDyn.setDynBuf;
  const flashSnapGlyph = keysDyn.flashSnapGlyph;
  function disarmDraft() { armed = null; armPts.length = 0; draftHistory.clear(); setDynBuf(""); snapOverride.clear(); draftHandle?.onArmCleared(); }
  // A29-UNDO-LOCAL — Ctrl+Z pops the last clicked point of the IN-PROGRESS draft (Ctrl+Shift+Z
  // restores it); the server's versioned history stays the record for committed work. Registered on
  // window because the canvas never holds focus; consumed ONLY while a draft is armed, so committed-
  // element undo (the rail's ↶, a republish) and the browser's own undo keep the key elsewhere.
  const draftHistory = new DraftPointHistory<THREE.Vector3>();
  window.addEventListener("keydown", (e) => {
    if (!armed || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
    e.preventDefault();
    if (e.shiftKey) {
      const back = draftHistory.redo(armPts);
      setStatus(back ? `point restored — ${armPts.length} placed` : "nothing to restore");
      return;
    }
    const undone = draftHistory.undo(armPts);
    if (!undone) { setStatus(`${armed.label}: no points yet — Esc cancels the tool`); return; }
    setStatus(`point removed — ${armPts.length} remain (Ctrl+Shift+Z restores, Esc cancels)`);
  });
  // P1 grid/level drafting refs: the grid overlay + snap, and the active storey/work-plane.
  const gridOverlay = new GridOverlay(viewer.world.scene.three);
  const logisticsOverlay = new LogisticsOverlay(viewer.world.scene.three);
  // A29-GUIDE-UNDERLAY — a scanned plan pinned to the active level, to trace over. It owns its own
  // panel (see `guideUnderlay.ts`) so this file stays out of it; app.ts is near its size ceiling.
  const guideUnderlay = new GuideUnderlay(viewer.world.scene.three);
  const draftProxies = new DraftProxyLayer(viewer.world.scene.three);   // P6: optimistic placement feedback
  let activeStorey: string | null = null;       // name passed to Draft recipes; sets the work-plane Z
  let activeStoreyZ = 0;
  // R38-SYNC-VIEW + R38-SYNC-SELECT — the plan docked beside the model, following the active level,
  // and now selection-synced both ways: PLAN-IDENTITY carried the GlobalId through the bake, the
  // SVG carries it as data-guid, so a click on plan linework is a real selection and a 3D pick
  // lights its loops in the plan.
  const planPane = new PlanPane({
    url: (p) => api.url(p),
    projectId: () => projectId,
    activeStorey: () => activeStorey,
    notify,
    onPick: (guid) => { void selectByGuid(guid, true); },
    headers: () => api.authHeaders(),
  });
  container.appendChild(planPane.el);
  onSelectionChanged = (guid) => planPane.highlight(guid);
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
      pushPullOn = false; ppGizmo?.hide();   // one gesture at a time — two gizmos on one box read as noise
      if (selection) { void attachGizmo(selection); }
      notify("Edit-in-place on — select an element and drag the gizmo to move it", "info");
    } else {
      gizmo?.hide();
      setStatus("edit-in-place off");
    }
  }, "edit");
  toolBtn("⇕", "Push/pull — drag the top handle to make the selected element taller or thicker", (b) => {
    pushPullOn = !pushPullOn;
    b.classList.toggle("on", pushPullOn);
    if (pushPullOn) {
      editInPlace = false; gizmo?.hide();
      if (selection) { void attachPushPull(selection); }
      notify("Push/pull on — select an element and drag its top handle; the base stays put", "info");
    } else {
      ppGizmo?.hide();
      setStatus("push/pull off");
    }
  }, "edit");

  // R26-TOOLBAR — every tool is installed by now, so lay the bar out: a handful of LABELED verbs for
  // the current context, the rest under More. Runs last on purpose; a layout pass that only moves
  // nodes between two containers cannot lose a tool, which is the risk in a toolbar change.
  const toolbarView = railToolbox;
  // Author verbs are promoted only when they are *usable*. Below Editor they stay in More, where the
  // existing capability styling still shows them dimmed with a padlock — the house rule is "a dimmed
  // button that says 'needs Editor' is onboarding, a missing one is a support ticket", and neither is
  // served by spending one of eight primary slots on something the caller cannot do.
  relayoutTools = () => toolbarView.update({
    selection: !!selectedGuid,
    canEdit: document.body.dataset.capEdit !== "off",
  });
  relayoutTools();
  if (toolbarView.unlaid().length) {
    // Not fatal — the tools are all still reachable under More — but it means the layout table has
    // fallen behind the toolbar, and a silent version of that is how a tool goes missing.
    console.warn("[toolbar] not described by toolbarLayout:", toolbarView.unlaid());
  }

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

  /** AUTH-SNAP-OVERRIDE — resolve ONE named snap kind against the picked element's plan footprint.
   *
   *  Null when the model has nothing of that kind to offer; the caller then keeps the raw cursor and
   *  says so on the glyph. It deliberately does **not** fall back to another kind — the drafter named
   *  one, and a point silently placed on a midpoint while the HUD said "perpendicular" carries a
   *  GlobalId into the schedules.
   *
   *  No aperture. The automatic path uses a 0.4 m tolerance because it is guessing which of six kinds
   *  the drafter meant; here the kind is stated and the candidates are the ≤4 points of the element
   *  the drafter explicitly picked, so a distance cut would only make a stated intent fail. */
  async function snapByOverride(raw: THREE.Vector3, hit: Hit | null, kind: OverrideKind,
                                from: THREE.Vector3 | null): Promise<THREE.Vector3 | null> {
    if (kind === "none" || !hit) return null;
    try {
      const boxes = await loader.fragments.getBBoxes({ [hit.fragments.modelId]: new Set([hit.localId]) });
      const bx = boxes[0];
      if (!bx) return null;
      const cur = { x: raw.x, z: raw.z };
      const cands = overrideCandidates(kind, { minX: bx.min.x, maxX: bx.max.x, minZ: bx.min.z, maxZ: bx.max.z },
                                       cur, from ? { x: from.x, z: from.z } : null);
      const r = resolveSnap(cur, cands, Number.POSITIVE_INFINITY, kind);
      return r ? new THREE.Vector3(r.x, raw.y, r.z) : null;
    } catch { return null; }
  }

  // --- P0 Draft placement: parameter-driven (params baked into `armed.build`), no prompt() --------
  async function captureDraftPoint(e: MouseEvent, hit: Hit | null) {
    const spec = armed;
    if (!spec) return;
    const raw = hit?.point ?? screenToGround(e);
    // AUTH-SNAP-OVERRIDE — spent by THIS pick whether or not it resolves, so a miss never steers the
    // click after it. While armed it replaces the automatic geometry snap and suppresses every
    // automatic stage below (grid increment, grid overlay, axis inference, polar, Shift ortho): a
    // stated "this pick, perpendicular" that then got re-snapped to a grid line is not an override.
    // A TYPED constraint still wins, because exact numbers are the more specific statement of the two.
    const ovr = snapOverride.consume();
    const ovrFrom = armPts.length >= 1 ? armPts[armPts.length - 1]! : null;
    const geoSnap = raw
      ? (ovr ? await snapByOverride(raw, hit, ovr, ovrFrom) : await snapToGeometry(raw, hit))
      : null;                                                      // hard endpoint/edge/vertex snap
    let p = raw ? (geoSnap ?? (ovr ? raw.clone() : snapPoint(raw))) : null;
    if (ovr === "none") flashSnapGlyph(e, "⊾ no snap");
    else if (ovr) flashSnapGlyph(e, geoSnap ? `⊾ ${OVERRIDE_LABEL[ovr]}` : `⊾ no ${OVERRIDE_LABEL[ovr]} here`);
    else if (geoSnap) flashSnapGlyph(e, "◻ snap");
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
    } else if (p && e.shiftKey && armPts.length >= 1 && !ovr) {   // ortho lock from the previous point
      const a = armPts[armPts.length - 1]!; // safe: armPts.length >= 1 checked above
      if (Math.abs(p.x - a.x) >= Math.abs(p.z - a.z)) p = new THREE.Vector3(p.x, p.y, a.z);
      else p = new THREE.Vector3(a.x, p.y, p.z);
    } else if (p && !geoSnap && armPts.length >= 1 && !ovr) {
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
    if (gridOverlay.hasData && !dynC && !ovr) {
      const gs = gridOverlay.nearestSnap(p.x, -p.z, 0.6);
      if (gs) p = new THREE.Vector3(gs[0], p.y, -gs[1]);
    }
    showCoords(p); armPts.push(p.clone()); draftHistory.noteAdded();
    // R38-DIM-INPUT — refresh the dyn HUD: a stale typed constraint must not survive the click that
    // ignored it, and with >=1 point placed the box now shows its hint state (the grammar, visible).
    setDynBuf("");
    if (spec.points === "poly") { notify(`${spec.label}: ${armPts.length} point(s) — double-click to close`, "info"); return; }
    if (armPts.length < spec.points) { notify(`${spec.label}: click the next point (Shift = ortho)`, "info"); return; }
    await finishDraft();
  }
  /** A29-PLACE-VALID: the loaded model's plan extent, from the same mesh traversal fitToModels
   *  uses. Null when nothing is loaded — a blank model must never refuse its first element. */
  function modelPlanBounds(): PlanBounds | null {
    // The MODEL, not the scene. Walking the scene expanded over the 2000x2000 shadow-catcher plane
    // `world.ts` adds in presentation mode, so the "model extent" became +/-1000 m and the mis-click
    // refusal it feeds stopped refusing anything. See `modelBounds.ts` for why this is an allowlist.
    return planBoundsFromModels(
      [...loader.fragments.list].map(([, m]) => m as unknown as { object: THREE.Object3D }),
    );
  }

  async function finishDraft() {
    if (!armed || !projectId) { disarmDraft(); return; }
    const a = armed;
    const planPts = armPts.map((v): [number, number] => [v.x, -v.z]);   // plan coords: E=x, N=-z
    // A29-PLACE-VALID — refuse before the round-trip. A refusal names the reason and KEEPS the
    // draft armed: the user adjusts and re-clicks; nothing is torn down, nothing was authored.
    const verdict = validatePlacement(a.points === "poly" ? "poly" : a.points === 2 ? "run" : "point",
                                      planPts, modelPlanBounds());
    if (!verdict.ok) { armPts.length = 0; notify(`${a.label}: ${verdict.reason}`, "error"); return; }
    const params = a.build(planPts);
    if (activeStorey && params.storey === undefined) params.storey = activeStorey;   // author onto the active level
    disarmDraft();
    draftProxies.fromParams(params, activeStoreyZ);                                   // instant optimistic proxy
    // Incremental preview: real one-element geometry immediately (fail-open — the proxy stands on
    // error). A29-LOCAL-PREVIEW: the amber proxy is deliberately NOT cleared when the preview
    // loads. The preview is real-looking geometry, and real-looking geometry with no marker is
    // indistinguishable from a committed element — which becomes a lie the moment the recipe
    // fails. Amber outline over accurate preview geometry states exactly the truth: this shape,
    // not yet on the record. Since R42-COMMIT-DELTA it drops when the RECIPE lands, not a reconvert.
    let previewId: string | null = null, previewGuid: string | undefined;
    try {
      const pv = await api.editPreview(projectId, a.recipe, params);
      if (pv?.frag) {
        previewGuid = pv.guid || undefined; previewId = `preview-${previewGuid || Date.now()}`;
        await loader.loadFragments(pv.frag, previewId);
      }
    } catch { /* preview unavailable — the optimistic proxy stands until the full reload */ }
    await authorAndReload(a.recipe, params, a.label, previewId, previewGuid);
  }

  const committer = deltaCommitter({
    store: deltas, refresh: () => refreshDeltas?.(),
    editIfc: (r, p, pub, g) => api.editIfc(projectId!, r, p, pub, g),
    publish: (reconvert) => api.publish(projectId!, reconvert),
    awaitPublish: () => waitForPublish(projectId!),
    reloadModel: () => loadProjectModel(), reloadPins: () => reloadModelPins(),
    dispose: (id) => loader.disposeOne(id),
    clearDraft: () => draftProxies.clear(),
    markFailed: () => draftProxies.markFailed(),
    notify,
  });

  /** Author a recipe and republish. Returns the outcome so a caller can react to a REFUSAL
   *  (`refused` — the recipe itself said no, e.g. a non-rectangular profile) distinctly from a
   *  publish flake (`applied: false, refused: false`). Existing callers ignore the return. */
  async function authorAndReload(recipe: string, params: Record<string, unknown>, label: string,
                                 previewId: string | null = null, previewGuid?: string): Promise<{ applied: boolean; refused: boolean }> {
    let outcome = { applied: false, refused: false };
    // The delta path does not republish, so it must not say it does — the two paths differ in what
    // the user is waiting for, which is the whole job of this string.
    await withLoading(container, previewId ? `authoring ${label}` : `authoring ${label} + republishing`,
      async () => { outcome = await committer.commit(recipe, params, label, previewId, previewGuid); });
    return outcome;
  }

  async function loadProjectModel(): Promise<boolean> {
    // R39-DECOMP-VIEWER ⑥ — body extracted to ./loadProjectModel.ts, which is also where
    // R39-VIEWER-OBS instruments the load journey. Every dependency below was `const` here.
    return loadProjectModelImpl({
      api, projectId, projectName: ctx.projectName, container, loader, modelLabels,
      refreshFederation, fitToModels, collabResync: () => collab.resync(), setStatus,
      canvas: () => viewer.world.renderer?.three.domElement ?? null,
      timings: { send: (p) => { if (projectId) void api.reportViewerLoad(projectId, p); } },
    });
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

  // ---- R38-PUSHPULL: drag the top handle, the extrusion deepens ------------
  // The gesture commits through `set_extrusion_depth` — a recipe-parameter edit, GUID-stable, which
  // the server refuses for non-extrusions. No client-side allowlist: the refusal arrives through the
  // normal recipe error path and the A29 failure marker rules apply.
  function ensurePushPull(): PushPullGizmo {
    if (ppGizmo) return ppGizmo;
    const g = new PushPullGizmo(
      viewer.world.camera.three,
      viewer.world.renderer!.three.domElement,
      viewer.world.scene.three,
      (enabled) => { viewer.world.camera.controls.enabled = enabled; },
    );
    g.onDrag = (depth) => setStatus(`push/pull  depth ${depth.toFixed(2)} m`);
    g.onCommit = async (depth) => {
      const guid = selectedGuid;
      if (!guid || !projectId) return;
      await authorAndReload("set_extrusion_depth", { guid, depth }, "push/pull");
      if (pushPullOn && selectedGuid === guid) await selectByGuid(guid);   // re-attach at the new height
    };
    ppGizmo = g;
    return g;
  }
  async function attachPushPull(map: ModelIdMap) {
    const boxes = await loader.fragments.getBBoxes(map);
    const box = new THREE.Box3();
    for (const b of boxes) box.union(b);
    if (box.isEmpty()) return;
    ensurePushPull().attach(box);
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

  // R39-DECOMP-VIEWER ⑤ — moved to `tools/projectPanel.ts`. The discipline state crosses as a
  // REF (get/set over the `let`s above) because the moved code WRITES both: `discTree ??=` and
  // the colour-mode <select>. Ownership stays here, so the reads at `disciplineOfClass` and in
  // the colour lookup below are untouched.
  const disciplineRef = {
    get tree() { return discTree; }, set tree(v: DisciplineTree | null) { discTree = v; },
    get mode() { return colorMode; }, set mode(v: "class" | "discipline") { colorMode = v; },
  };
  const buildPanels = () => buildProjectPanels({
    api, projectId, notify, setStatus, selectByGuid, reloadModelPins, colorFor,
    disciplineOfClass, discipline: disciplineRef, layerMgr, fitToItems, refreshIssues,
    spatialElements: { get value() { return spatialElements; },
                       set value(v: SpatialElement[]) { spatialElements = v; } },
  });

  // KERNEL-ADOPT ②: markup runs as a kernel plugin. Lazily built because the pin overlay and the
  // click handler only exist once the viewer has, and a kernel per viewer instance is correct —
  // nothing here is global state.
  let markupKernel: ReturnType<typeof createTestHarness> | null = null;
  async function markupCommands() {
    if (!markupKernel) {
      markupKernel = createTestHarness();
      await markupKernel.load(markupPlugin({
        pins,
        onPinClick: async (p: ModulePin) => {
          if (p.element_guids?.[0]) await selectByGuid(p.element_guids[0], true);
          setStatus(`${p.ref} · ${p.module_name} · ${p.status}`);
        },
      }));
    }
    return markupKernel.kernel.commands;
  }

  /**
   * Reload pins, and REPORT a failure rather than propagating it.
   *
   * This used to `await pins.load(...)` bare, so one 503 or a single malformed record aborted
   * whatever the caller had queued after it — the panel build, the issue refresh — with nothing on
   * screen explaining why. Going through the kernel command bus turns that throw into a Result: the
   * user is told the pins did not load, and the rest of the setup still runs.
   */
  async function reloadModelPins() {
    if (!projectId) return;
    const outcome = await reloadMarkup(await markupCommands(), projectId);
    if (!outcome.ok) notify(`pins did not load — ${outcome.detail}`, "error");
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
  const ALL_TOOLS = ["authoring", "qa", "analyse", "exports"];
  // R24-TOOLS-SPLIT: `analyse` is primary for every persona that has a list. A section left out of a
  // persona's list renders collapsed under a "more" badge — which was the right default while every
  // section shared one panel and you had to scroll past it. It is the wrong default now that Analyse
  // IS its own rail item: clicking an item and finding its one group folded shut reads as an empty
  // room. Code, cost, egress and 4D are the reading each of these roles opens the model for anyway.
  const TOOLS_BY_PERSONA: Record<string, string[]> = {
    gc: ["qa", "analyse", "exports"],
    developer: ["analyse", "exports"],
    architect: ["authoring", "analyse", "exports"],
    engineer: ["qa", "analyse", "authoring"],
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
    // RAIL-TOOLBOX: the toolbox element is PERSISTENT — its buttons are created once at viewer
    // setup by the modules that own them. `innerHTML = ""` would destroy them and they would never
    // be rebuilt, so detach it first and re-insert below. (This is the trap: buildToolsPanel re-runs
    // on every persona switch.)
    // RAIL-TOOLBOX hosts are PERSISTENT — their buttons are created once at viewer setup by the
    // modules that own them. `innerHTML = ""` would destroy them and nothing rebuilds them, so
    // detach first. (buildToolsPanel re-runs on every persona switch.)
    for (const key of railToolbox.hostKeys()) railToolbox.hostFor(key)?.remove();
    // ...and only now empty the panels the distribution writes into. The hosts are detached above,
    // so this cannot destroy them; anything still in those panels is last build's output, which
    // would otherwise survive as a second identical-looking copy with dead handlers.
    clearDistributed();
    panel.innerHTML = "";
    const intro = document.createElement("div");
    intro.className = "meta"; intro.style.cssText = "margin:2px 2px 6px;font-size:11px;line-height:1.4";
    intro.textContent = "Tools grouped by the modeling lifecycle — Build · Analyze & Coordinate · Document · Data.";
    panel.appendChild(intro);
    // RAIL-SPLIT: each toolbox group renders into the rail panel that owns its job (View / Build /
    // Analyse), not into one blob. Persistent hosts — detach before the wipe above already happened,
    // so re-insert here.
    for (const key of railToolbox.hostKeys()) {
      const host = railToolbox.hostFor(key);
      const target = document.getElementById(`panel-${key}`);
      if (host && target && host.parentElement !== target) target.appendChild(host);
    }
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
      if (projectId) fedBody.appendChild(toolBtn2("🕔 Version compare (3D)", async () => {
        const h = await api.modelVersions(pid);
        showResult("Version compare", async (body) => {
          if (!h.length) { body.appendChild(resultNote("No versions yet — publish the model (Authoring) to snapshot one.")); return; }
          if (h.length >= 2) {
            // VERSION-COMPARE-3D: pick any two versions → summary + a 3D overlay (added green / modified amber)
            const versionOpts = (sel: HTMLSelectElement, def: number) => {
              for (const v of h) { const o = document.createElement("option"); o.value = String(v.version); o.textContent = `v${v.version}`; sel.appendChild(o); }
              sel.value = String(def);
            };
            const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0";
            const aSel = document.createElement("select"); aSel.className = "portal-filter"; aSel.style.fontSize = "12px"; versionOpts(aSel, h[1]!.version);
            const bSel = document.createElement("select"); bSel.className = "portal-filter"; bSel.style.fontSize = "12px"; versionOpts(bSel, h[0]!.version);
            const cmp = document.createElement("button"); cmp.className = "mini-btn on"; cmp.textContent = "Compare";
            row.append(document.createTextNode("from "), aSel, document.createTextNode(" → "), bSel, cmp);
            body.appendChild(row);
            const out = document.createElement("div"); body.appendChild(out);
            const render = async () => {
              const a = Number(aSel.value), b = Number(bSel.value);
              out.innerHTML = "<div class=\"meta\">comparing…</div>";
              let d; try { d = await api.versionDiff(pid, a, b); } catch (e) { out.innerHTML = ""; out.appendChild(resultNote(`compare failed: ${escapeHtml((e as Error).message)}`, "")); return; }
              out.innerHTML = "";
              out.appendChild(resultNote(`v${a} → v${b}: <b style="color:var(--status-good)">+${d.added_count}</b> added / `
                + `<b style="color:var(--status-crit)">−${d.removed_count}</b> removed`
                + (d.modified_available ? ` / <b style="color:#e0a020">~${d.modified_count}</b> modified` : " / modified n/a (older version)")
                + ` · ${d.unchanged_count} unchanged`, "ok"));
              const ctl = document.createElement("div"); ctl.style.cssText = "display:flex;gap:6px;margin:4px 0";
              const overlay = document.createElement("button"); overlay.className = "mini-btn on"; overlay.textContent = "◉ Overlay in 3D";
              overlay.title = "Colour added elements green and modified elements amber in the loaded model (removed elements aren't in it).";
              const reset = document.createElement("button"); reset.className = "mini-btn"; reset.textContent = "Reset";
              const cost = document.createElement("button"); cost.className = "mini-btn"; cost.textContent = "$ Cost impact";
              cost.title = "REVISION-DELTA: conceptual cost of this revision — added elements priced from the current takeoff, removed counted by class, quantity changes flagged for re-estimate";
              overlay.onclick = async () => {
                try {
                  await layerMgr.resetColors();
                  if (d!.added.length) await layerMgr.colorGuids(d!.added, "#33d17a");
                  if (d!.modified.length) await layerMgr.colorGuids(d!.modified.map((m) => m.guid), "#e0a020");
                  notify(`overlaid +${d!.added_count} / ~${d!.modified_count}`, "success");
                } catch (e) { notify((e as Error).message, "error"); }
              };
              reset.onclick = async () => { await layerMgr.resetColors(); await layerMgr.showAll(); };
              cost.onclick = () => void (async () => {
                let cd; try { cd = await api.versionCostDelta(pid, a, b); } catch (e) { notify((e as Error).message, "error"); return; }
                showResult(`Revision cost impact — v${a} → v${b}`, (cb) => {
                  cb.appendChild(resultNote(`<b>+$${cd!.added.cost.toLocaleString()}</b> added `
                    + `(${cd!.added.priced_count}/${cd!.added.count} priced) · `
                    + `<b>${cd!.removed.count}</b> removed (by class) · `
                    + `<b>${cd!.requantified.count}</b> flagged for re-estimate`, "ok"));
                  if (cd!.added.lines.length) {
                    cb.appendChild(resultNote("Added — priced from the current takeoff:", ""));
                    cb.appendChild(kvTable(cd!.added.lines.map((l) => ({
                      k: `${l.ifc_class.replace("Ifc", "")} ×${l.count}`,
                      v: `${l.quantity} ${l.unit} × $${l.rate} = <b>$${l.amount.toLocaleString()}</b>`,
                    }))));
                  }
                  if (cd!.removed.by_class.length) {
                    cb.appendChild(resultNote("Removed — counted by class (not priced; prior quantities aren't stored):", ""));
                    cb.appendChild(kvTable(cd!.removed.by_class.map((l) => ({
                      k: `${l.ifc_class.replace("Ifc", "")} (${escapeHtml(l.discipline)})`, v: `−${l.count}`,
                    }))));
                  }
                  const n = document.createElement("div"); n.className = "meta"; n.style.cssText = "margin-top:8px;font-size:11px";
                  n.textContent = cd!.note; cb.appendChild(n);
                });
              })();
              ctl.append(overlay, cost, reset); out.appendChild(ctl);
              if (d.modified_count) {
                out.appendChild(resultNote("Modified elements (click to select in 3D):", ""));
                out.appendChild(kvTable(d.modified.slice(0, 40).map((m) => {
                  // name the exact properties/quantities that changed (VERSION-COMPARE per-property), if available
                  const props = (m.changed_properties || []).slice(0, 6)
                    .map((p) => `${p.property}${p.status !== "changed" ? ` (${p.status})` : ""}`).join(", ");
                  const extra = (m.changed_properties && m.changed_properties.length > 6) ? "…" : "";
                  return {
                    k: `${(m.ifc_class || "").replace("Ifc", "")} · ${m.name || m.guid.slice(0, 8)}`,
                    v: m.changes.join(", ") + (props ? ` — ${props}${extra}` : ""),
                    onClick: () => selectByGuid(m.guid, false),
                  };
                })));
              }
            };
            cmp.onclick = () => void render();
            void render();
          }
          body.appendChild(resultNote("Version history:", ""));
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
        arm: (a) => { armed = a; armPts.length = 0; setDynBuf(""); },  // re-arm resets the dyn HUD
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
      cadIn.type = "text"; cadIn.className = "portal-filter"; cadIn.style.cssText = "flex:1;font-family:var(--mono)";
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
          } catch (err) { cadStatus.innerHTML = `<span style="color:var(--status-crit)">${escapeHtml((err as Error).message)}</span>`; notify(`${parsed.echo} failed: ${escapeHtml((err as Error).message)}`, "error"); }
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
        void planPane.refresh();     // R38-SYNC-VIEW: the plan follows the level you work in
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
      const planPaneBtn = toolBtn2("◫ Plan beside model", () => {
        const open = planPane.toggle();
        planPaneBtn.classList.toggle("on", open);
        if (open) notify("Plan pane open — it follows the active level", "info");
      });
      planPaneBtn.title = "Dock the generated plan beside the 3D view; it re-cuts when you change the "
        + "active level, and selection syncs both ways — click linework in the plan to select in 3D.";
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

      // R42-COMMIT-DELTA — rebuild the base geometry so it matches the data. The deltas are dropped
      // only AFTER the new base has loaded: dropping first would blink the elements off screen, and
      // on a failed publish would leave the user with neither the delta nor the rebuild.
      const deltaUi = deltaIndicator(deltas, () =>
        withLoading(container, "rebuilding model geometry", () => committer.consolidate()));
      refreshDeltas = deltaUi.refresh;

      // `planPaneBtn` before `planBtn`: the docked pane is the daily surface, the SVG export the
      // occasional one. (It was CREATED and never appended from v0.3.826 until 2026-08-02 — the pane
      // shipped wired, tested and unreachable, which no test caught because tests exercised the
      // class, not the rail. The [[what-did-we-build-that-nothing-calls]] shape, one button wide.)
      // RAIL-SPLIT ②: this one section had grown to hold five jobs — levels, the document set,
      // annotation, the content library and fabrication detail. The seams were already here as
      // named variables; they just all ended up in one `append`. Each group now goes to the rail
      // item that owns it, which is what finally gives **Annotate** and **Detail** real contents
      // instead of shipping them empty.
      glBody.append(status, levelSel, undoRow, deltaUi.el, load, toggle, addLvl, addRooms, furnish, typesBtn, groupsBtn,
        phaseBtn, queryBtn, lodBtn, asBuiltBtn, manage, levelsMgr);
      // The drawing set: produced from the model, read as documents.
      railGroup("export", "Drawings & sheets", [planPaneBtn, planBtn, sheetBtn, pdfBtn, schedBtn,
        schedPdfBtn, manualBtn, sectBtn]);
      railGroup("annotate", "Annotate", [annotateHead, annotateWrap]);
      railGroup("library", "Families & content", [libHead, libWrap]);
      // Detail IS the advanced tools — so no toggle and no heading inside it. Keeping either would
      // be three levels of chrome (rail item "Detail" -> group "Fabrication detail" -> toggle
      // "Advanced fabrication tools ▾") to reach a list you already asked for by clicking Detail.
      // The toggle earned its place when these lived inside a crowded Build section; the rail item
      // replaced that job, and a disclosure whose parent already discloses is just a second click.
      advWrap.hidden = false;
      advToggle.remove();
      railGroup("detail", "", [advWrap]);
    }

    // --- persona-ordered tool sections ---------------------------------------
    const builders: Record<string, () => void> = {
      // R39-DECOMP-VIEWER ① — moved verbatim to `tools/exportsSection.ts`. `section` and
      // `toolBtn2` are handed over as FUNCTIONS: both close over the panel, the persona
      // ordering and `hasIfc`, so passing them whole is what keeps this a signature rather
      // than a re-plumbing. `projectId` is `const` here, so a value is safe.
      exports: () => buildExportsSection({ section, toolBtn2, api, projectId, notify }),
      // R39-DECOMP-VIEWER ② — moved verbatim to `tools/qaSection.ts` (851 lines).
      // `selectedGuid` is passed as an ACCESSOR, not a value: it is a `let` here, and a value
      // would freeze the selection at panel-build time for every handler in that section.
      qa: () => buildQaSection({
        section, toolBtn2, api, pid, projectId, notify,
        selectedGuid: () => selectedGuid,
        selectMap, sets, layerMgr, loader, nextId, refreshIssues,
        container, reloadModelPins, selectByGuid, waitForPublish, refreshFederation,
        authorAndReload, fitToModels, loadProjectModel,
      }),
      /**
       * R24-TOOLS-SPLIT — *what does it tell you*, cut out of `qa` (*is the model right*).
       *
       * `qa` reached 1087 lines and 42 controls under one heading with **no internal structure at
       * all** — zero sub-headings, one divider. That is why RAIL-SPLIT could not route Analyse to
       * its own rail item and `GROUP_PANEL` folded it into Review: there was nothing to re-parent.
       * The sub-group had to be created before anything could be routed.
       *
       * The seam is the one the deferral note named: interrogating the model (clash, health,
       * rules, hygiene, queries) stays in `qa`; the analyses that *produce a reading* from it —
       * code, egress, cost, 4D, and the natural-language Ask — come here.
       *
       * **This is still a move, not a rewrite.** Both builders close over the same `api`, `pid`,
       * `container` and layer manager, and each declares its own local `b` and `out`, so every
       * range below is the original text at the original indent. `toolsSplit.test.ts` asserts the
       * partition by label in both directions, because a control that silently vanishes looks
       * exactly like one deliberately removed.
       */
      // R39-DECOMP-VIEWER ③ — moved verbatim to `tools/analyseSection.ts`.
      // `lastPoint` is an ACCESSOR: a `let` here, read at click time by the placement tools.
      analyse: () => buildAnalyseSection({
        section, toolBtn2, api, pid, projectId, notify, container, logisticsOverlay,
        layerMgr, refreshIssues, fourD,
        lastPoint: () => lastPoint,
      }),
      // R39-DECOMP-VIEWER ④ — moved verbatim to `tools/authoringSection.ts`.
      authoring: () => buildAuthoringSection({
        section, toolBtn2, api, pid, notify, panel, waitForPublish, loadProjectModel,
        lastPoint: () => lastPoint, selectedGuid: () => selectedGuid,
      }),
    };
    for (const key of order) builders[key]?.();
    regroupByPhase();                                        // UX-1: physical phase clusters + headers
    // RAIL-SPLIT: distribute BEFORE restoring the ribbon tab, and restore it only over what is left.
    //
    // The other order shipped a trap. `applyPhase` inline-hides the groups outside the saved
    // lifecycle tab; the distribution then moved some of those hidden groups into rail panels that
    // have **no ribbon at all**, so nothing could ever un-hide them. A user whose last tab was, say,
    // "Construct" opened Build or Export and found it empty — with no control anywhere on screen to
    // explain why, because the tab that hid it lives in a panel they were no longer looking at.
    //
    // Distributing first makes the ribbon govern only the groups that remain under it, which is the
    // only set it can still reach.
    distributeToolGroups(panel);                             // RAIL-SPLIT: one job per rail item
    applyPhase(localStorage.getItem(RIBBON_KEY) || "All");   // UX-1: restore the active lifecycle tab
    // A group that moved out from under the ribbon must not carry a stale inline hide with it.
    for (const key of DISTRIBUTED_PANELS) {
      const p = document.getElementById(`panel-${key}`);
      p?.querySelectorAll<HTMLElement>(".tool-group").forEach((g) => { g.style.display = ""; });
    }
  }

  /**
   * RAIL-SPLIT — move each `tool-group` to the rail panel that owns its job.
   *
   * Measured live: this one panel held **182 buttons and 11 inputs under 7 headings**, doing about
   * ten unrelated jobs. "Tools" was not a category — it was where a control went when nobody
   * decided. Each `section()` already declares what it is via `data-tool`, so the split is a
   * re-parenting pass keyed off that, not a rewrite of 154 call sites. **A pass that only moves
   * nodes cannot lose one**, which is the same property that made RAIL-TOOLBOX safe.
   *
   * A group with no destination stays in `panel-tools` on purpose. Unrouted must mean *visible in
   * the old place*, never *gone*: a control that silently disappears looks exactly like one that was
   * deliberately removed, and the next person to notice is a user who needed it.
   */
  /**
   * RAIL-SPLIT ② — put a named group of already-built controls into a rail panel.
   *
   * The controls are created by the code that owns their behaviour, exactly as before; this only
   * decides which rail item they live under. Re-parenting again, for the same reason: a pass that
   * moves nodes cannot lose one, whereas re-creating them somewhere else can.
   */
  function railGroup(railKey: string, heading: string, nodes: (HTMLElement | null | undefined)[]) {
    const target = document.getElementById(`panel-${railKey}`);
    const present = nodes.filter((n): n is HTMLElement => !!n);
    if (!target || !present.length) return;
    const sec = document.createElement("section");
    sec.className = "tool-group open";
    sec.dataset.tool = `${railKey}-group`;
    const body = document.createElement("div"); body.className = "tool-group-body";
    body.append(...present);
    // An empty heading means the rail item already names this — render the contents bare rather
    // than wrapping them in a collapsible whose label repeats the item you just clicked.
    if (heading) {
      const head = document.createElement("button");
      head.type = "button"; head.className = "tool-group-head";
      head.innerHTML = `<span class="chev">▾</span><span class="t">${heading}</span>`;
      head.onclick = () => sec.classList.toggle("open");
      sec.append(head, body);
    } else {
      sec.appendChild(body);
    }
    target.appendChild(sec);
  }

  /**
   * Every rail panel this distribution writes into — the set that must be cleared before a rebuild.
   *
   * `buildToolsPanel` clears `panel-tools` and then rebuilds, which was correct while everything
   * landed there. Once the groups distribute, the destination panels are **never cleared**, so each
   * persona switch (`aec:persona` re-runs the build) appended a second, third, fourth copy of every
   * group. The duplicates are not cosmetic: they are detached from the rebuilt handlers, so they
   * look identical to the live controls and simply do nothing.
   */
  const DISTRIBUTED_PANELS = ["view", "build", "library", "detail", "annotate", "export", "review", "analyse"];

  /** Empty the panels this pass owns, so a rebuild replaces rather than stacks. */
  function clearDistributed() {
    for (const key of DISTRIBUTED_PANELS) {
      const p = document.getElementById(`panel-${key}`);
      if (p) p.textContent = "";
    }
  }

  function distributeToolGroups(panel: HTMLElement) {
    // `authoring` is deliberately NOT split here. It genuinely mixes annotation, the content
    // library and fabrication detail under one heading, and splitting a section by guessing which
    // button belongs where is how a tool ends up somewhere nobody looks. It stays in Build until
    // its buttons are separated at the source — which is what unblocks the Detail and Annotate rail
    // items (both intentionally absent until they would have contents).
    const HOME: Record<string, string> = {
      draft: "library",        // the element/content palette — and the future drag source
      gridlevels: "build",
      authoring: "build",      // mixed; see above
      models: "build",         // federation lives with the model you are building
      origin: "build",
      qa: "review",            // "is the model right"
      analyse: "analyse",      // R24-TOOLS-SPLIT: "what does it tell you" — code, cost, egress, 4D
      exports: "export",
    };
    for (const [tool, railKey] of Object.entries(HOME)) {
      const group = panel.querySelector<HTMLElement>(`.tool-group[data-tool="${CSS.escape(tool)}"]`);
      const target = document.getElementById(`panel-${railKey}`);
      if (group && target) target.appendChild(group);
    }
    // ...and everything still here goes to Build.
    //
    // The original rule was "a group with no destination stays in `panel-tools` on purpose —
    // unrouted must mean *visible in the old place*, never *gone*." That rule quietly stopped being
    // true the moment the split removed the Tools rail item: nothing opens `panel-tools` any more,
    // so "stays put" became "is unreachable", which is the exact failure the rule existed to
    // prevent. Build is the honest fallback for the same reason the toolbox spill uses it — an
    // undescribed group is most likely an authoring verb, and it must land somewhere people open.
    const strays = [...panel.querySelectorAll<HTMLElement>(".tool-group")];
    const build = document.getElementById("panel-build");
    if (build) for (const g of strays) build.appendChild(g);
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
    // R17 BCF-VIEWPOINT: ALWAYS capture the live view (camera + selection + active section planes), not
    // only when a point was picked — every issue becomes navigable-in-context on reopen.
    {
      const tgt = new THREE.Vector3();
      viewer.world.camera.controls.getTarget(tgt);
      const target = lastPoint ? { x: lastPoint.x, y: lastPoint.y, z: lastPoint.z }
        : { x: tgt.x, y: tgt.y, z: tgt.z };
      const planes = section.serialize();
      await api.addViewpoint(projectId, topic.id, {
        camera: { type: "perspective", position: cameraPos(), target, fov: 60 },
        components: guid ? [guid] : [],
        ...(planes.length ? { clipping_planes: planes } : {}),
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
  (window as unknown as Record<string, unknown>).__viewer = { viewer, loader, fitToModels, selectByGuid, selectByGuids, openFile, referenceModels, THREE };

  // ---- self-initialise: load the project model + build panels --------------
  void (async () => {
    applySettings();
    await withLoading(container, `Loading ${ctx.projectName || "model"}`, async () => {
      if (projectId && await loadProjectModel()) return;
      // No project model → render nothing.
      //
      // This used to fall back to three `.frag` files bundled in `public/`, picked by a REGEX ON THE
      // PROJECT'S NAME. A user project called "Riverside School" with no published model silently
      // loaded an unrelated demo's structural frame, and any session with no project at all always
      // did. Geometry that is not this project's, shown as this project's, is worse than an empty
      // canvas: the canvas is honest, the status bar already says what to do ("open a sample or
      // ＋ New"), and the sample library is the real way in.
      //
      // The gate that was supposed to prevent this asserted the filenames were gone from `main.ts`
      // and passed — while they lived one file over, as the default. A check scoped to one file
      // measures that file, not the behaviour; `library.test.ts` now reads this one too.
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
    triggerOpen, openFile, addReferenceObject, exportFrag, exportIfc, handleKey,
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
