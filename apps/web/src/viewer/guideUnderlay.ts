/**
 * A29-GUIDE-UNDERLAY — trace over a plan.
 *
 * A 2D reference image (a scan, a photographed survey, a plan exported as PNG) pinned to a level and
 * **scaled to real metres**, so an existing building can be redrawn over it with the ordinary draw
 * tools. The image is a guide only: nothing about it enters IFC, and it is not selectable, not
 * snappable and not part of the model.
 *
 * ## Scale is the whole feature
 *
 * An underlay that is merely *placed* is decoration. The reason this is worth building is that walls
 * traced over it come out at real dimensions — so the calibration is not a nicety, it is the thing.
 * Two ways in, both reduced to one number (metres per pixel):
 *
 *   - **known width** — "this scan is 42.5 m across". One number, no picking.
 *   - **two points** — the drafter names a distance they know between two points on the image (a grid
 *     bay, a scale bar). This is the same idea `drawings/pdfTakeoff.ts` uses for PDF takeoff.
 *
 * Every derivation refuses rather than guessing. A zero-length reference, a non-finite number, a
 * negative distance or an implausible scale returns a REASON, because a silently-wrong scale is the
 * one failure mode that poisons everything traced afterwards — and unlike a mis-placed image, it
 * looks completely fine on screen.
 *
 * ## Why this file is nearly all pure functions
 *
 * The THREE object is mechanical: a plane, a texture, an opacity. What can actually be *wrong* is the
 * arithmetic and the refusals, and none of that needs a renderer. So the decisions live here as
 * plain functions and `GuideUnderlay` only applies them — the same split that let `snapEngine` and
 * `placeValid` be exhaustively tested while the viewer stayed untestable.
 *
 * ## It must not become part of the model
 *
 * Adding a large plane to the scene is exactly what broke `modelPlanBounds` before `modelBounds.ts`
 * existed: a 2000x2000 shadow-catcher made the model's plan extent +/-1000 m and defeated the
 * mis-click guard. That is now an allowlist over loaded Fragments models, so this plane is
 * structurally out of scope for bounds — but it is also given a name and marked non-raycastable so
 * every other consumer has something explicit to key on.
 */
import * as THREE from "three";

/** The object name, so anything walking the scene can identify (and skip) the underlay. */
export const UNDERLAY_NAME = "aec-guide-underlay";

/** Raster formats a browser can decode into a texture without any new dependency. */
export const UNDERLAY_EXTENSIONS = ["png", "jpg", "jpeg", "webp", "gif", "bmp"] as const;

/** Below this an "image" is a decoding artefact; above it a texture will not upload on most GPUs. */
const MIN_PX = 2;
const MAX_PX = 32_768;

/** A scale outside this is not a plan — it is a typo. 1 mm/px to 100 m/px spans every real drawing. */
const MIN_MPP = 1e-4;
const MAX_MPP = 100;

export type Derived<T> = { ok: true; value: T } | { ok: false; reason: string };

const bad = (reason: string): Derived<never> => ({ ok: false, reason });

export function isSupportedImageName(name: string): boolean {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  return (UNDERLAY_EXTENSIONS as readonly string[]).includes(ext);
}

function finitePositive(n: number): boolean {
  return Number.isFinite(n) && n > 0;
}

/**
 * Metres per pixel from the image's known real-world width.
 *
 * The simplest calibration and the one most people have: a survey says how wide the building is.
 */
export function mppFromWidth(pixelWidth: number, realWidthM: number): Derived<number> {
  if (!Number.isInteger(pixelWidth) || pixelWidth < MIN_PX || pixelWidth > MAX_PX) {
    return bad(`image width ${pixelWidth} px is not a usable image`);
  }
  if (!finitePositive(realWidthM)) return bad("enter the real width in metres (greater than zero)");
  const mpp = realWidthM / pixelWidth;
  if (mpp < MIN_MPP || mpp > MAX_MPP) {
    return bad(`that gives ${mpp.toPrecision(3)} m per pixel — check the width, it looks like a typo`);
  }
  return { ok: true, value: mpp };
}

/**
 * Metres per pixel from two points on the image whose real separation is known.
 *
 * `a` and `b` are in image pixels. The refusal that matters is the coincident pick: two points at the
 * same place give a zero pixel distance, and dividing by it yields `Infinity` — which would render
 * as an underlay the size of the solar system, or as nothing at all, depending on the driver.
 */
export function mppFromTwoPoints(
  a: { x: number; y: number }, b: { x: number; y: number }, realDistanceM: number,
): Derived<number> {
  if (![a?.x, a?.y, b?.x, b?.y].every((n) => Number.isFinite(n))) return bad("pick two points on the image");
  const px = Math.hypot(b.x - a.x, b.y - a.y);
  if (px < 1) return bad("those two points are the same spot — pick two points further apart");
  if (!finitePositive(realDistanceM)) return bad("enter the real distance in metres (greater than zero)");
  const mpp = realDistanceM / px;
  if (mpp < MIN_MPP || mpp > MAX_MPP) {
    return bad(`that gives ${mpp.toPrecision(3)} m per pixel — check the distance, it looks like a typo`);
  }
  return { ok: true, value: mpp };
}

/** The plane's real size. Aspect ratio is preserved by construction — one scale, both axes. */
export function underlayPlanSize(pixelW: number, pixelH: number, mpp: number): Derived<{ widthM: number; heightM: number }> {
  if (!finitePositive(pixelW) || !finitePositive(pixelH)) return bad("image has no usable dimensions");
  if (!finitePositive(mpp)) return bad("scale is not set");
  return { ok: true, value: { widthM: pixelW * mpp, heightM: pixelH * mpp } };
}

/** Opacity is clamped rather than refused: a slider cannot produce a meaningful error, and an
 *  underlay at 0 is a legitimate "hide it for a moment" that must not throw. */
export function clampOpacity(v: number): number {
  if (!Number.isFinite(v)) return 0.5;
  return Math.min(1, Math.max(0, v));
}

/** Rotation normalised to [0, 360). Non-finite falls back to 0 — an unrotated guide is always valid. */
export function normaliseRotation(deg: number): number {
  if (!Number.isFinite(deg)) return 0;
  return ((deg % 360) + 360) % 360;
}

export interface UnderlayPlacement {
  metresPerPixel: number;
  widthM: number;
  heightM: number;
  /** Plan offset of the image centre, in metres (E = +x, N = -z). */
  offsetE: number;
  offsetN: number;
  rotationDeg: number;
  opacity: number;
  /** World Y the plane sits at — the active level, nudged so it never z-fights the slab it traces. */
  levelZ: number;
}

/** How far above the level the guide floats. Small enough to read as "on" the level, large enough
 *  that a slab authored at exactly that level does not z-fight with it. */
export const LEVEL_LIFT_M = 0.005;

/**
 * Assemble a full placement, or refuse with the first reason found.
 *
 * Everything the panel can get wrong funnels through here, so the panel has no arithmetic of its own
 * and the refusal text is written once.
 */
export function buildPlacement(input: {
  pixelW: number; pixelH: number;
  scale: { kind: "width"; realWidthM: number }
       | { kind: "two-points"; a: { x: number; y: number }; b: { x: number; y: number }; realDistanceM: number };
  offsetE?: number; offsetN?: number; rotationDeg?: number; opacity?: number; levelZ?: number;
}): Derived<UnderlayPlacement> {
  const mppRes = input.scale.kind === "width"
    ? mppFromWidth(input.pixelW, input.scale.realWidthM)
    : mppFromTwoPoints(input.scale.a, input.scale.b, input.scale.realDistanceM);
  if (!mppRes.ok) return mppRes;

  const size = underlayPlanSize(input.pixelW, input.pixelH, mppRes.value);
  if (!size.ok) return size;

  const num = (v: number | undefined, fallback: number) => (Number.isFinite(v) ? (v as number) : fallback);
  return {
    ok: true,
    value: {
      metresPerPixel: mppRes.value,
      widthM: size.value.widthM,
      heightM: size.value.heightM,
      offsetE: num(input.offsetE, 0),
      offsetN: num(input.offsetN, 0),
      rotationDeg: normaliseRotation(num(input.rotationDeg, 0)),
      opacity: clampOpacity(num(input.opacity, 0.5)),
      levelZ: num(input.levelZ, 0) + LEVEL_LIFT_M,
    },
  };
}

/**
 * The scene object. Mechanical by design — every decision above it is a pure function.
 *
 * The plane lies in the ground plane (rotated -90° about X, like `world.ts`'s shadow catcher) and is
 * positioned in WORLD coordinates from the plan offsets: E maps to +x and N maps to **-z**, the same
 * convention the draft pipeline uses.
 */
export class GuideUnderlay {
  private mesh: THREE.Mesh | null = null;
  private texture: THREE.Texture | null = null;

  constructor(private readonly scene: THREE.Object3D) {}

  get hasImage(): boolean { return !!this.mesh; }

  /** Swap in a texture and its pixel dimensions. Replaces any existing underlay. */
  setTexture(texture: THREE.Texture, placement: UnderlayPlacement): void {
    this.clear();
    const geo = new THREE.PlaneGeometry(placement.widthM, placement.heightM);
    const mat = new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      opacity: placement.opacity,
      depthWrite: false,          // a guide must never occlude the model it is traced against
      side: THREE.DoubleSide,     // visible from below, so an underhung view still shows it
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = UNDERLAY_NAME;
    // Not a pick target and not a snap target: it is a picture, not geometry. `raycast` is emptied
    // rather than relying on a layer, because a layer is a rendering concern that a future camera
    // change could silently undo, while an empty raycast is a property of THIS object.
    mesh.raycast = () => {};
    mesh.renderOrder = -1;        // behind the model
    this.mesh = mesh;
    this.texture = texture;
    this.apply(placement);
    this.scene.add(mesh);
  }

  /** Re-apply a placement to the existing plane (scale/rotate/move/fade without reloading). */
  apply(placement: UnderlayPlacement): void {
    const mesh = this.mesh;
    if (!mesh) return;
    mesh.rotation.set(-Math.PI / 2, 0, -placement.rotationDeg * Math.PI / 180);
    // plan E = +x, plan N = -z
    mesh.position.set(placement.offsetE, placement.levelZ, -placement.offsetN);
    const mat = mesh.material as THREE.MeshBasicMaterial;
    mat.opacity = placement.opacity;
    mat.needsUpdate = true;
    const geo = mesh.geometry as THREE.PlaneGeometry;
    const p = geo.parameters;
    if (p.width !== placement.widthM || p.height !== placement.heightM) {
      mesh.geometry.dispose();
      mesh.geometry = new THREE.PlaneGeometry(placement.widthM, placement.heightM);
    }
  }

  set visible(v: boolean) { if (this.mesh) this.mesh.visible = v; }
  get visible(): boolean { return this.mesh?.visible ?? false; }

  /** Remove and release. Safe to call when nothing is loaded. */
  clear(): void {
    if (!this.mesh) return;
    this.scene.remove(this.mesh);
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
    this.texture?.dispose();
    this.mesh = null;
    this.texture = null;
  }
}

// ---------------------------------------------------------------------------------------------
// Loading and the panel. Kept in this file rather than in `app.ts` deliberately: app.ts is at 5,150
// of a 5,200-line ceiling and is the file most likely to red the next build, so a feature that can
// own its own UI should.
// ---------------------------------------------------------------------------------------------

export interface LoadedImage { texture: THREE.Texture; pixelW: number; pixelH: number; name: string }

/**
 * Decode an image file into a texture, with its true pixel dimensions.
 *
 * The dimensions come from the decoded image rather than from anything the user typed, because the
 * whole scale calculation divides by them — a wrong pixel width produces a confidently wrong
 * metres-per-pixel and every traced wall inherits it.
 *
 * The object URL is revoked once decoding finishes: an underlay is a big raster and a viewer session
 * that swaps several of them would otherwise hold every one alive until the tab closes.
 */
export function loadImageTexture(file: File): Promise<LoadedImage> {
  return new Promise((resolve, reject) => {
    if (!isSupportedImageName(file.name)) {
      reject(new Error(`${file.name} is not an image this can decode (${UNDERLAY_EXTENSIONS.join(", ")})`));
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const texture = new THREE.Texture(img);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.needsUpdate = true;
      resolve({ texture, pixelW: img.naturalWidth, pixelH: img.naturalHeight, name: file.name });
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error(`could not decode ${file.name}`)); };
    img.src = url;
  });
}

export interface UnderlayPanelDeps {
  underlay: GuideUnderlay;
  /** World Y of the level currently being authored on. */
  levelZ: () => number;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  showResult: (title: string, build: (body: HTMLElement) => void) => void;
}

/** Build the underlay panel body into `body`. Exported separately from `openUnderlayPanel` so it can
 *  be exercised without the app's modal chrome. */
export function buildUnderlayPanel(body: HTMLElement, d: UnderlayPanelDeps): void {
  let loaded: LoadedImage | null = null;

  const row = (label: string, control: HTMLElement) => {
    const r = document.createElement("label");
    r.style.cssText = "display:flex;align-items:center;gap:8px;margin:4px 0";
    const s = document.createElement("span");
    s.textContent = label; s.style.cssText = "flex:1;font-size:12px";
    r.append(s, control);
    body.appendChild(r);
    return r;
  };
  const num = (value: number, step = "0.1", width = "90px") => {
    const i = document.createElement("input");
    i.type = "number"; i.value = String(value); i.step = step;
    i.className = "portal-filter"; i.style.width = width;
    return i;
  };

  const note = document.createElement("div");
  note.className = "meta";
  note.style.marginBottom = "6px";
  note.textContent = "Pin a scanned or exported plan to this level and trace over it. The guide is "
    + "never selectable, never snapped to, and never enters IFC — only what you draw does.";
  body.appendChild(note);

  const file = document.createElement("input");
  file.type = "file";
  file.accept = UNDERLAY_EXTENSIONS.map((e) => `.${e}`).join(",");
  file.setAttribute("aria-label", "Guide image");
  row("Image", file);

  const widthM = num(50, "0.1");
  widthM.setAttribute("aria-label", "Real width in metres");
  row("Real width (m)", widthM);

  const offE = num(0, "0.5"); offE.setAttribute("aria-label", "East offset in metres");
  const offN = num(0, "0.5"); offN.setAttribute("aria-label", "North offset in metres");
  row("Offset E (m)", offE);
  row("Offset N (m)", offN);

  const rot = num(0, "1"); rot.setAttribute("aria-label", "Rotation in degrees");
  row("Rotation (°)", rot);

  const opacity = document.createElement("input");
  opacity.type = "range"; opacity.min = "0"; opacity.max = "1"; opacity.step = "0.05";
  opacity.value = "0.5"; opacity.style.width = "120px";
  opacity.setAttribute("aria-label", "Guide opacity");
  row("Opacity", opacity);

  const status = document.createElement("div");
  status.className = "meta";
  status.style.marginTop = "6px";
  body.appendChild(status);

  /** One place where the panel's fields become a placement — or a refusal the user can act on. */
  function currentPlacement() {
    if (!loaded) return { ok: false as const, reason: "choose an image first" };
    return buildPlacement({
      pixelW: loaded.pixelW, pixelH: loaded.pixelH,
      scale: { kind: "width", realWidthM: Number(widthM.value) },
      offsetE: Number(offE.value), offsetN: Number(offN.value),
      rotationDeg: Number(rot.value), opacity: Number(opacity.value),
      levelZ: d.levelZ(),
    });
  }

  function applyNow(announce: boolean) {
    const r = currentPlacement();
    if (!r.ok) { status.textContent = `⚠ ${r.reason}`; if (announce) d.notify(r.reason, "error"); return; }
    if (!d.underlay.hasImage) d.underlay.setTexture(loaded!.texture, r.value);
    else d.underlay.apply(r.value);
    status.textContent = `${loaded!.name} — ${r.value.widthM.toFixed(1)} × ${r.value.heightM.toFixed(1)} m `
      + `at ${(r.value.metresPerPixel * 1000).toFixed(1)} mm/px`;
    if (announce) d.notify("guide underlay placed", "success");
  }

  file.onchange = () => {
    const f = file.files?.[0];
    if (!f) return;
    loadImageTexture(f)
      .then((img) => { loaded = img; status.textContent = `${img.name} — ${img.pixelW}×${img.pixelH} px`; applyNow(false); })
      .catch((e: Error) => { status.textContent = `⚠ ${e.message}`; d.notify(e.message, "error"); });
  };
  for (const el of [widthM, offE, offN, rot, opacity]) el.oninput = () => { if (loaded) applyNow(false); };

  const btns = document.createElement("div");
  btns.style.cssText = "display:flex;gap:6px;margin-top:8px";
  const apply = document.createElement("button");
  apply.className = "tool-btn"; apply.textContent = "Apply";
  apply.onclick = () => applyNow(true);
  const hide = document.createElement("button");
  hide.className = "tool-btn"; hide.textContent = "Hide / show";
  hide.onclick = () => { d.underlay.visible = !d.underlay.visible; };
  const remove = document.createElement("button");
  remove.className = "tool-btn"; remove.textContent = "Remove";
  remove.onclick = () => { d.underlay.clear(); loaded = null; status.textContent = "removed"; };
  btns.append(apply, hide, remove);
  body.appendChild(btns);
}

/** Open the guide-underlay panel in the app's standard result chrome. */
export function openUnderlayPanel(d: UnderlayPanelDeps): void {
  d.showResult("🖼 Guide underlay", (body) => buildUnderlayPanel(body, d));
}
