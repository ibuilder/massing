import * as THREE from "three";

import type { ApiClient } from "../api/client";
import { confirmModal } from "../ui/modal";
import { fetchArrayBufferWithProgress, setLoadingLabel, withLoading } from "../ui/feedback";
import { loadReferenceModel } from "./referenceLoader";
import type { ModelLoader } from "./loader";

/** REL-4 leaf (split from `app.ts`): every file-open / import / export path — IFC (small in-browser,
 *  large via the server pipeline), Fragments, the paid convert bridge, reference overlays, sample
 *  models, and the Tauri-native open/save dialogs. Pure extraction behind an explicit deps seam. */

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

export interface FileIODeps {
  viewer: ReturnType<typeof import("./world").createViewer>;
  loader: ModelLoader;
  api: ApiClient;
  container: HTMLElement;
  projectId: () => string | null;
  connected: () => boolean;
  notify: (m: string, kind?: "info" | "success" | "error") => void;
  setStatus: (m: string) => void;
  nextId: (label?: string) => string;
  referenceModels: Map<string, { object: THREE.Object3D; label: string; dispose?: () => void }>;
  refreshFederation: () => void;
  fitToModels: () => Promise<void>;
  waitForPublish: (pid: string, onTick?: (s: string) => void) => Promise<string>;
  loadProjectModel: () => Promise<boolean>;
  buildToolsPanel: () => Promise<void> | void;
  buildClashPanel: () => Promise<void> | void;
}

export function installFileIO(d: FileIODeps) {
  let refCount = 0;
  // ---- file loading --------------------------------------------------------
  // The hidden file <input>s live in index.html and are opened + wired by main.ts, so the native
  // file dialog can appear instantly on click without waiting for this (heavy) module to finish
  // loading. main hands the chosen File straight to openFile() once the viewer is ready.
  async function openFile(kind: "ifc" | "frag" | "convert" | "ref", file: File) {
    if (kind === "frag") await loadFile(file, (b, id) => d.loader.loadFragments(b, id), "loading");
    else if (kind === "convert") await convertAndLoad(file);
    else if (kind === "ref") await openReference(file);
    else await openIfc(file);
  }
  // Register a pre-built THREE object (e.g. a basemap tile group) as a reference overlay.
  function addReferenceObject(object: THREE.Object3D, label: string) {
    const id = `ref-${++refCount}`;
    d.viewer.world.scene.three.add(object);
    d.referenceModels.set(id, { object, label });
    d.refreshFederation();
    void d.fitToModels();
    void d.loader.fragments.core.update(true);
    return id;
  }
  // Load a mesh / point cloud as a view-only reference overlay (IFC stays the source of truth).
  async function openReference(file: File) {
    try {
      const res = await withLoading(d.container, `loading ${file.name}`, () => loadReferenceModel(file));
      if (!res) return;
      const id = `ref-${++refCount}`;
      d.viewer.world.scene.three.add(res.object);
      d.referenceModels.set(id, { object: res.object, label: file.name, dispose: res.dispose });
      d.refreshFederation();
      await d.fitToModels();
      void d.loader.fragments.core.update(true);
      d.notify(`loaded ${file.name}${res.info ? ` — ${res.info}` : ""}`, "success");
    } catch (e) { d.notify(`couldn't load ${file.name}: ${(e as Error).message}`, "error"); }
  }
  // Above this, parsing the IFC in the browser (web-ifc WASM) is too slow / memory-heavy. When a
  // project + backend are available we skip the in-browser parse entirely and let the server convert
  // the IFC to Fragments off-thread, then stream the optimized result — the production large-model
  // path (CLAUDE.md: never parse a full IFC in the browser at runtime).
  const CLIENT_IFC_MAX = 60 * 1024 * 1024;   // ~60 MB
  const mb = (n: number) => (n / 1048576).toFixed(0);

  // Open an IFC: small files parse in-browser for an instant view (and, with a project open, also
  // upload so drawings / clash / IDS / energy / exports / authoring regenerate server-side). Large
  // files route straight to the server pipeline and stream back the published fragments.
  async function openIfc(file: File) {
    const pid = d.projectId();
    const big = file.size > CLIENT_IFC_MAX;

    // Large model + backend: server converts → we stream the published .frag. No in-browser parse.
    if (big && d.connected() && pid) {
      let replace = true;
      try { if ((await d.api.project(pid)).has_source_ifc) replace = await confirmModal(`Replace this project's model with ${file.name} (${mb(file.size)} MB)? Drawings & analysis will regenerate.`, ""); }
      catch { /* offline check — proceed */ }
      if (!replace) { d.notify(`kept the current project model`, "info"); return; }
      d.notify(`${file.name} is large (${mb(file.size)} MB) — converting on the server for smooth streaming…`, "info");
      try {
        await d.api.uploadSourceIfc(pid, file);          // saves + sets source_ifc + publishes off-thread
        const state = await d.waitForPublish(pid, (s) => d.setStatus(`processing model: ${s}…`));
        if (state === "done") {
          await d.loadProjectModel();                    // stream the optimized fragments with progress
          void d.buildToolsPanel();
          d.notify(`${file.name} loaded — drawings, QA, energy & authoring are ready`, "success");
        } else {
          d.notify(`model uploaded; server processing: ${state}`, "info");
        }
      } catch (e) { d.notify(`couldn't process on the server: ${(e as Error).message}`, "error"); }
      return;
    }

    // Small file (or no backend): parse in-browser for an instant view.
    if (big) d.notify(`${file.name} is large (${mb(file.size)} MB) — in-browser parsing may be slow; open a project for server-side conversion.`, "info");
    await withLoading(d.container, `loading ${file.name}`, async () => {
      await d.loader.loadIfc(new Uint8Array(await file.arrayBuffer()), d.nextId(file.name));
      await d.fitToModels();
    });
    if (!d.connected() || !pid) { d.notify(`loaded ${file.name} (no project — view only)`, "success"); return; }
    let replace = true;
    try { if ((await d.api.project(pid)).has_source_ifc) replace = await confirmModal(`Replace this project's model with ${file.name}? Drawings & analysis will regenerate.`, ""); }
    catch { /* offline check — proceed */ }
    if (!replace) { d.notify(`loaded ${file.name} (project model unchanged)`, "info"); return; }
    d.notify(`Adding ${file.name} to the project — generating drawings & analysis…`, "info");
    try {
      await d.api.uploadSourceIfc(pid, file);            // saves + sets source_ifc + publishes off-thread
      const state = await d.waitForPublish(pid, (s) => d.setStatus(`processing model: ${s}…`));
      void d.buildToolsPanel();                          // re-checks has_source_ifc → un-gates the tools
      void d.buildClashPanel();
      d.notify(state === "done"
        ? `${file.name} is the project model — drawings, QA, energy & authoring are ready`
        : `model added; server processing: ${state}`, state === "done" ? "success" : "info");
    } catch (e) { d.notify(`couldn't add to project: ${(e as Error).message}`, "error"); }
  }
  async function loadFile(file: File, load: (b: Uint8Array, id: string) => Promise<unknown>, verb: string) {
    await withLoading(d.container, `${verb} ${file.name}`, async () => {
      await load(new Uint8Array(await file.arrayBuffer()), d.nextId(file.name));
      await d.fitToModels();
      d.notify(`loaded ${file.name}`, "success");
    });
  }
  async function loadSample(file: string, label: string) {
    await withLoading(d.container, `loading ${label}`, async () => {
      const mb = (n: number) => (n / 1048576).toFixed(1);
      const buffer = await fetchArrayBufferWithProgress(
        import.meta.env.BASE_URL + file.replace(/^\//, ""), {},   // respect the deploy base
        (loaded, total) => setLoadingLabel(d.container,
          `downloading ${label} ${Math.round(loaded / total * 100)}% (${mb(loaded)}/${mb(total)} MB)`));
      setLoadingLabel(d.container, "preparing geometry…");
      await d.loader.loadFragments(buffer, d.nextId(label));
      await d.fitToModels();
      d.notify(`loaded ${label}`, "success");
    });
  }
  async function convertAndLoad(file: File) {
    await withLoading(d.container, `converting ${file.name} (Autodesk bridge)`, async () => {
      const fd = new FormData(); fd.append("file", file);
      const res = await fetch(d.api.url("/convert"), { method: "POST", body: fd, headers: d.api.authHeaders() });
      if (!res.ok) { const msg = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(msg.detail || "conversion unavailable"); }
      await d.loader.loadFragments(await res.arrayBuffer(), d.nextId(file.name));
      await d.fitToModels();
      d.notify(`converted + loaded ${file.name}`, "success");
    });
  }
  function download(blob: Blob, name: string) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  // running inside the Tauri desktop shell? then use native file dialogs + fs
  const isTauri = () => "__TAURI_INTERNALS__" in window;

  async function tauriOpen(kind: "ifc" | "frag" | "convert") {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const { readFile } = await import("@tauri-apps/plugin-fs");
    const exts = kind === "ifc" ? ["ifc"] : kind === "frag" ? ["frag"] : ["rvt", "dwg", "nwc"];
    const path = await open({ multiple: false, filters: [{ name: kind.toUpperCase(), extensions: exts }] });
    if (!path || typeof path !== "string") return;
    const bytes = await readFile(path);
    const name = path.split(/[\\/]/).pop() || "model";
    await withLoading(d.container, `loading ${name}`, async () => {
      if (kind === "frag") await d.loader.loadFragments(bytes, d.nextId(name));
      else if (kind === "ifc") await d.loader.loadIfc(bytes, d.nextId(name));
      else {
        const fd = new FormData(); fd.append("file", new Blob([bytes as BlobPart]), name);
        const res = await fetch(d.api.url("/convert"), { method: "POST", body: fd, headers: d.api.authHeaders() });
        if (!res.ok) { const m = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(m.detail || "conversion unavailable"); }
        await d.loader.loadFragments(await res.arrayBuffer(), d.nextId(name));
      }
      await d.fitToModels();
      d.notify(`loaded ${name}`, "success");
    });
  }
  function triggerOpen(kind: "ifc" | "frag" | "convert") {
    if (isTauri()) void tauriOpen(kind); else $(`${kind}-input`).click();
  }

  async function tauriSave(defaultName: string, ext: string, bytes: Uint8Array): Promise<boolean> {
    const { save } = await import("@tauri-apps/plugin-dialog");
    const { writeFile } = await import("@tauri-apps/plugin-fs");
    const path = await save({ defaultPath: defaultName, filters: [{ name: ext.toUpperCase(), extensions: [ext] }] });
    if (!path) return false;
    await writeFile(path, bytes); d.notify(`saved ${path}`, "success"); return true;
  }
  async function exportFrag() {
    const id = [...d.loader.fragments.list.keys()][0];
    if (!id) { d.notify("no model loaded", "error"); return; }
    const buf = new Uint8Array(await d.loader.fragments.list.get(id)!.getBuffer(false));
    if (isTauri()) { await tauriSave(`${id}.frag`, "frag", buf); return; }
    download(new Blob([buf]), `${id}.frag`);
    d.notify(`exported ${id}.frag`, "success");
  }
  async function exportIfc() {
    const pid = d.projectId();
    if (!pid) { d.notify("connect a project to export its IFC", "error"); return; }
    if (isTauri()) {
      const res = await fetch(d.api.url(`/projects/${pid}/source.ifc`), { headers: d.api.authHeaders() });
      if (!res.ok) { d.notify("no source IFC to export", "error"); return; }
      await tauriSave("model.ifc", "ifc", new Uint8Array(await res.arrayBuffer()));
      return;
    }
    window.open(d.api.url(`/projects/${pid}/source.ifc`), "_blank");
  }
  return { openFile, addReferenceObject, openReference, loadSample, convertAndLoad,
           exportFrag, exportIfc, triggerOpen, download };
}
