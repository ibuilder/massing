import * as THREE from "three";

import type { ApiClient } from "../api/client";
import { sunAltAz, sunSceneDir } from "./solar";
import { positionSun, renderMode } from "./world";
import type { ModelLoader } from "./loader";

/** REL-4 leaf (split from `app.ts`): the environment & navigation toolbar tools — render mode
 *  (sun + soft shadows), the sun/shadow study panel, the first-person walkthrough, and the storey
 *  levels overlay. Pure extraction: behaviour and DOM are unchanged; `app.ts` passes the seams it
 *  already owned (viewer, loader, toolbar factory, viewpoint capture, settings). */

type Viewpoint = { position: THREE.Vector3Like; target: THREE.Vector3Like; projection?: string; fov?: number } | null;

export interface EnvToolsDeps {
  viewer: ReturnType<typeof import("./world").createViewer>;
  loader: ModelLoader;
  api: ApiClient;
  projectId: () => string | null;
  toolBtn: (icon: string, title: string, onClick: (b: HTMLButtonElement) => void, cap?: "edit" | "review") => HTMLButtonElement;
  notify: (m: string, kind?: "info" | "success" | "error") => void;
  setStatus: (m: string) => void;
  getSettings: () => { projection: "Perspective" | "Orthographic" };
  captureViewpoint: () => Viewpoint;
  jumpToViewpoint: (vp: Viewpoint) => void;
}

/** Install the four tools onto the toolbar (in the original order) and return the render-mode state
 *  accessor `fitToModels` needs. */
export function installEnvTools(d: EnvToolsDeps): { isRenderOn: () => boolean } {
  let renderBtn: HTMLButtonElement | null = null;
  // render mode: presentation lighting + soft shadows (off by default — flat is cheaper/faster)
  let renderOn = false;
  renderBtn = d.toolBtn("◓", "Render mode — sun, soft shadows, PBR lighting, SSAO & bloom", (b) => {
    renderOn = !renderOn;
    renderMode(d.viewer.world, renderOn);
    b.classList.toggle("on", renderOn);
    d.setStatus(renderOn ? "render mode on — sun + soft shadows + SSAO/bloom" : "render mode off (flat shading)");
    void d.loader.fragments.core.update(true);
  });

  // sun / shadow study: drive the render-mode sun by date · time · location (live shadows)
  let sunPanel: HTMLElement | null = null;
  function applySun(lat: number, lon: number, date: Date) {
    const pos = sunAltAz(date, lat, lon);
    const up = positionSun(d.viewer.world, sunSceneDir(pos));
    void d.loader.fragments.core.update(true);
    const compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(pos.azimuth / 45) % 8];
    const out = document.getElementById("sun-readout");
    if (out) out.textContent = up
      ? `altitude ${pos.altitude.toFixed(0)}° · azimuth ${pos.azimuth.toFixed(0)}° (${compass})`
      : `sun below horizon — night (alt ${pos.altitude.toFixed(0)}°)`;
  }
  d.toolBtn("☀", "Sun & shadow study (date · time · location)", (b) => {
    if (sunPanel) { sunPanel.remove(); sunPanel = null; b.classList.remove("on"); return; }
    if (!renderOn) {   // the study drives the render-mode sun, so make sure it's on
      renderOn = true; renderMode(d.viewer.world, true);
      renderBtn?.classList.add("on");
    }
    b.classList.add("on");
    const p = document.createElement("div");
    p.id = "sun-study-panel"; p.className = "floating-panel";
    p.style.cssText = "position:absolute;right:12px;top:64px;z-index:30;background:var(--panel);border:1px solid var(--line);"
      + "border-radius:10px;padding:12px;width:230px;display:flex;flex-direction:column;gap:8px;font-size:12px;box-shadow:0 6px 24px #0007";
    const today = new Date();
    p.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>☀ Sun &amp; shadow study</strong>
        <button id="sun-close" class="icon-btn" title="Close" style="width:22px;height:22px">✕</button>
      </div>
      <label style="display:flex;justify-content:space-between;gap:6px">Lat
        <input id="sun-lat" type="number" step="0.1" value="40.7" style="width:80px"></label>
      <label style="display:flex;justify-content:space-between;gap:6px">Lon
        <input id="sun-lon" type="number" step="0.1" value="-74.0" style="width:80px"></label>
      <label style="display:flex;justify-content:space-between;gap:6px">Date
        <input id="sun-date" type="date" value="${today.toISOString().slice(0, 10)}" style="width:130px"></label>
      <label>Time of day <span id="sun-time" style="float:right">12:00</span>
        <input id="sun-hour" type="range" min="0" max="1439" step="5" value="720" style="width:100%"></label>
      <div id="sun-readout" class="meta" style="min-height:16px"></div>`;
    (d.viewer.container.parentElement || d.viewer.container).appendChild(p);
    sunPanel = p;
    const $$ = <T extends HTMLElement>(id: string) => p.querySelector(`#${id}`) as T;
    const recompute = () => {
      const lat = +$$<HTMLInputElement>("sun-lat").value, lon = +$$<HTMLInputElement>("sun-lon").value;
      const mins = +$$<HTMLInputElement>("sun-hour").value;
      const d = new Date($$<HTMLInputElement>("sun-date").value || today.toISOString().slice(0, 10));
      d.setHours(Math.floor(mins / 60), mins % 60, 0, 0);
      $$("sun-time").textContent = `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
      applySun(lat, lon, d);
    };
    p.querySelectorAll("input").forEach((el) => el.addEventListener("input", recompute));
    $$("sun-close").addEventListener("click", () => { p.remove(); sunPanel = null; b.classList.remove("on"); });
    recompute();
  });

  // first-person walkthrough (Matterport-style): WASD to walk at eye height, drag to look. Movement
  // is locked horizontal (feet on the floor) while look can still pitch; cooperates with the orbit
  // controls rather than fighting them — when no key is held, normal drag-to-look is untouched.
  const EYE_HEIGHT = 1.6;   // metres (model units are METRE per project convention)
  let walkRAF = 0; const walkKeys = new Set<string>();
  let walkSaved: Viewpoint = null;
  function onWalkKey(e: KeyboardEvent) {
    const k = e.key.toLowerCase();
    if (!["w", "a", "s", "d"].includes(k)) return;
    if (e.type === "keydown") walkKeys.add(k); else walkKeys.delete(k);
    e.preventDefault();
  }
  function setWalk(on: boolean) {
    const c = d.viewer.world.camera.controls;
    if (on) {
      walkSaved = d.captureViewpoint();
      void d.viewer.world.camera.projection.set("Perspective");   // ortho walk feels wrong
      const p = new THREE.Vector3(), t = new THREE.Vector3();
      c.getPosition(p); c.getTarget(t);
      const dir = new THREE.Vector3().subVectors(t, p); dir.y = 0;
      if (dir.lengthSq() < 1e-4) dir.set(0, 0, -1); dir.normalize();
      const eye = new THREE.Vector3(p.x, EYE_HEIGHT, p.z);
      const look = eye.clone().addScaledVector(dir, 6); look.y = EYE_HEIGHT;
      void c.setLookAt(eye.x, eye.y, eye.z, look.x, look.y, look.z, true);
      window.addEventListener("keydown", onWalkKey);
      window.addEventListener("keyup", onWalkKey);
      const sp = 0.07;   // metres per frame ≈ a brisk walk at 60fps
      const step = () => {
        walkRAF = requestAnimationFrame(step);
        if (!walkKeys.size) return;
        c.getPosition(p); c.getTarget(t);
        const fwd = new THREE.Vector3().subVectors(t, p); fwd.y = 0;
        if (fwd.lengthSq() < 1e-6) return; fwd.normalize();
        const right = new THREE.Vector3(-fwd.z, 0, fwd.x);   // 90° CW in plan
        let dx = 0, dz = 0;
        if (walkKeys.has("w")) { dx += fwd.x; dz += fwd.z; }
        if (walkKeys.has("s")) { dx -= fwd.x; dz -= fwd.z; }
        if (walkKeys.has("d")) { dx += right.x; dz += right.z; }
        if (walkKeys.has("a")) { dx -= right.x; dz -= right.z; }
        // keep eye at EYE_HEIGHT (feet on floor); shift the look-target by the same plan delta so
        // the view direction (incl. any pitch from dragging) is preserved as you walk.
        void c.setLookAt(p.x + dx * sp, EYE_HEIGHT, p.z + dz * sp,
          t.x + dx * sp, t.y, t.z + dz * sp, false);
      };
      step();
      d.notify("walk mode — W/A/S/D to move, drag to look. Toggle to exit.", "info");
    } else {
      cancelAnimationFrame(walkRAF); walkRAF = 0; walkKeys.clear();
      window.removeEventListener("keydown", onWalkKey);
      window.removeEventListener("keyup", onWalkKey);
      void d.viewer.world.camera.projection.set(d.getSettings().projection);
      if (walkSaved) d.jumpToViewpoint(walkSaved);
    }
  }
  d.toolBtn("🚶", "Walk through (first-person — W/A/S/D, drag to look)", (b) => {
    const on = !walkRAF;
    setWalk(on);
    b.classList.toggle("on", on);
    d.setStatus(on ? "walk mode on — W/A/S/D + drag" : "walk mode off");
  });

  // levels overlay: a horizontal grid + label at each storey elevation (from the API)
  const levelObjs: THREE.Object3D[] = [];
  d.toolBtn("☰", "Toggle storey levels overlay", async (b) => {
    if (levelObjs.length) { for (const o of levelObjs) d.viewer.world.scene.three.remove(o); levelObjs.length = 0; b.classList.remove("on"); void d.loader.fragments.core.update(true); return; }
    const pid = d.projectId();
    if (!pid) { d.notify("connect a project for storey levels", "error"); return; }
    let storeys: { name: string | null; elevation: number; guid: string }[] = [];
    try { storeys = await d.api.drawingStoreys(pid); } catch { d.notify("no storeys (needs source IFC)", "error"); return; }
    const box = new THREE.Box3();
    d.viewer.world.scene.three.traverse((o: THREE.Object3D) => { const msh = o as THREE.Mesh; if (msh.isMesh) box.expandByObject(msh); });
    const size = box.isEmpty() ? 20 : Math.max(box.getSize(new THREE.Vector3()).x, box.getSize(new THREE.Vector3()).z) * 1.1;
    const cx = box.isEmpty() ? 0 : box.getCenter(new THREE.Vector3()).x;
    const cz = box.isEmpty() ? 0 : box.getCenter(new THREE.Vector3()).z;
    for (const s of storeys) {
      const grid = new THREE.GridHelper(size, 10, 0x4a8cff, 0x33384a);
      grid.position.set(cx, s.elevation, cz);   // model Y is up; elevation in metres
      (grid.material as THREE.Material).opacity = 0.35; (grid.material as THREE.Material).transparent = true;
      d.viewer.world.scene.three.add(grid); levelObjs.push(grid);
    }
    b.classList.add("on"); void d.loader.fragments.core.update(true);
    d.setStatus(`levels: ${storeys.length} storeys`);
  });
  return { isRenderOn: () => renderOn };
}
