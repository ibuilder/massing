import * as OBC from "@thatopen/components";
import * as THREE from "three";
import { cameraProfile } from "./cameraProfile";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { SSAOPass } from "three/examples/jsm/postprocessing/SSAOPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { attachPixelGovernor, shadowFrustum } from "./pixelGovernor";

export type World = OBC.SimpleWorld<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>;

export interface Viewer {
  components: OBC.Components;
  world: World;
  container: HTMLElement;
  grid: OBC.SimpleGrid;
  /** Stops the pixel governor's frame loop. Exposed rather than discarded — dropping the handle is
   *  exactly the un-stoppable-loop mistake R23-RAF-LEAK was about, and it does not stop being one
   *  because the loop happens to be ours. */
  stopPixelGovernor: () => void;
  /** Disconnects the container ResizeObserver that keeps the canvas matched to its box. Same
   *  reasoning as `stopPixelGovernor`: an observer nobody can stop is a leak. */
  stopResizeObserver: () => void;
}

/**
 * Sets up the shared viewer World (scene + camera + renderer) that every tool module
 * reads from. See guide §6 — one World, many tools.
 */
export function createViewer(container: HTMLElement): Viewer {
  const components = new OBC.Components();

  const worlds = components.get(OBC.Worlds);
  const world = worlds.create<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>();

  world.scene = new OBC.SimpleScene(components);
  world.scene.setup();
  world.scene.three.background = null;

  // R23-RENDERER-FLAGS: these are WebGL CONTEXT attributes, fixed at construction — there is no
  // setter to reach for later, so passing nothing here silently locked in the defaults forever.
  //
  //  * `powerPreference` was unset, which lets a dual-GPU laptop hand a BIM model to the integrated
  //    chip. This is the actual win here and it costs nothing.
  //  * `antialias` STAYS ON. The tempting saving is to drop it on the theory that the
  //    post-processing composer already resolves 4× MSAA — but `setPresentationFx` is opt-in
  //    (VIZ-2 presentation mode), so the ordinary BIM view renders straight to this canvas. Turning
  //    it off would put jagged edges on every model for a saving that only applies in a mode most
  //    users never enter. Stated explicitly so the next reader doesn't re-derive the wrong answer.
  //  * `alpha` must stay true — the scene background is deliberately null so the page shows through.
  //  * `stencil: false` is a genuine saving: nothing in the pipeline uses the stencil buffer, and
  //    the default allocates one per frame-buffer.
  world.renderer = new OBC.SimpleRenderer(components, container, {
    antialias: true,
    powerPreference: "high-performance",
    alpha: true,
    stencil: false,
  });
  // The That Open Company mark, off.
  //
  // It is a deliberate, documented feature of `@thatopen/components` (`showLogo`, default `true`),
  // not a bug — the library's own docs ask you to consider leaving it on, because it is how the team
  // funding this open-source stack gets discovered, and name "white-label embed, customer-branded
  // surface" as fair reasons to turn it off. This is that case: a customer-branded product surface.
  //
  // Turning it off is NOT the end of the obligation. MIT requires the copyright notice to travel
  // with the source, which it does, and we credit the stack in the docs — see `docs/credits.md`.
  // If that credit ever disappears, this line should go back.
  world.renderer.showLogo = false;

  world.camera = new OBC.OrthoPerspectiveCamera(components);

  components.init();

  void world.camera.controls.setLookAt(12, 8, 12, 0, 0, 0);

  // R23-PIXEL-GOVERNOR: the engine pins the pixel ratio in its constructor and never revisits it, so
  // a 4K display shades every pixel of a tall tower at 2x for ever regardless of how the frame rate is
  // actually doing. Dropping to 1x is a 4x cut in fragment work — the cheapest large win available on
  // a heavy model. Degrades quickly (the user is suffering now) and recovers slowly (be sure it holds).
  const stopPixelGovernor = attachPixelGovernor(world.renderer.three, {
    raf: (cb) => requestAnimationFrame(cb),
    caf: (h) => cancelAnimationFrame(h),
  }, () => performance.now(), Math.min(window.devicePixelRatio || 1, 2));

  // light reference grid (toggled from the bottom settings bar)
  const grids = components.get(OBC.Grids);
  const grid = grids.create(world);

  // CANVAS-RESIZE — the renderer sizes itself once, from whatever the container measured at
  // construction. If the container is not at its final width yet — a rail still expanding, a
  // workspace not yet shown, a font or CSS pass still to land — the canvas keeps that first size
  // for ever. Measured 2026-08-02 on a real project: container 830x572, canvas 0x493, four visible
  // meshes and 230 triangles built and drawn into a zero-width canvas.
  //
  // **That is what "the geometry loader stalls" has actually been all along.** The .frag fetch
  // returns 200, the worker parses, the meshes exist and are visible — and nothing appears, which
  // from outside is indistinguishable from a loader that never finished. It was recorded as an
  // environment quirk and repeated as a verification limitation for weeks; it is a resize bug, and
  // it reaches any user whose viewer mounts before layout settles.
  //
  // `onModelShown` already re-resizes, but only on a workspace transition — nothing watched the
  // container itself. A ResizeObserver does, and covers every cause at once. Zero sizes are skipped
  // deliberately: resizing at 0x0 sets a NaN camera aspect, which is the failure this repo has
  // already been bitten by (see fitToModels' deferral).
  let lastW = 0, lastH = 0;
  const ro = new ResizeObserver(() => {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;                       // hidden/collapsed — resizing now bakes a NaN aspect
    if (w === lastW && h === lastH) return;     // observers fire on no-op layout passes too
    lastW = w; lastH = h;
    world.renderer?.resize();
    applyCameraProfile(world, w, h);
  });
  ro.observe(container);
  // Apply once at construction as well as on resize. The observer fires on the first layout pass in
  // a browser, but not if the container is already at its final size — and a camera that only gets
  // its profile when something moves is a camera that is wrong on the paths where nothing does.
  applyCameraProfile(world, container.clientWidth, container.clientHeight);

  return { components, world, container, grid, stopPixelGovernor, stopResizeObserver: () => ro.disconnect() };
}

/**
 * R23-CAMERA-CLASS — put the viewport-derived fov/near/far onto the live camera.
 *
 * Separate from `cameraProfile()` so the arithmetic stays testable without a WebGL context: that
 * module is pure and unit-tested, this is the three lines that touch the renderer.
 *
 * `updateProjectionMatrix()` is not optional — three caches the projection and a changed `fov` is
 * inert until it is called, which fails silently and looks exactly like the profile being wrong.
 */
export function applyCameraProfile(
  world: { camera?: { three?: unknown } }, width: number, height: number, walk = false,
): void {
  // Structural, not `World`: `walkMode.ts` types its viewer with the minimum it needs precisely to
  // keep three/DOM out of its core, and demanding the full library type here would force that file
  // to give that up for three lines of camera state.
  const cam = world.camera?.three as THREE.PerspectiveCamera | undefined;
  if (!cam?.isPerspectiveCamera) return;          // ortho/plan mode has no fov to set
  const p = cameraProfile(width, height, { walk });
  if (cam.fov === p.fov && cam.near === p.near && cam.far === p.far) return;
  cam.fov = p.fov; cam.near = p.near; cam.far = p.far;
  cam.updateProjectionMatrix();
}

const SUN = "aec-sun", HEMI = "aec-hemi", FILL = "aec-fill", GROUND = "aec-shadow-ground";

let envMap: THREE.Texture | null = null;   // PMREM-prefiltered IBL, built lazily from the renderer

/** A neutral studio environment for image-based lighting/reflections (built once, cached). */
function studioEnv(r: THREE.WebGLRenderer): THREE.Texture {
  if (envMap) return envMap;
  const pmrem = new THREE.PMREMGenerator(r);
  envMap = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();
  return envMap;
}

/** Only these plain lit materials are safe to upgrade to PBR. We deliberately skip Fragments'
 *  own `ShaderMaterial` meshes — they carry `onBeforeRender` hooks that feed custom uniforms, so
 *  swapping their material would break the engine's rendering/highlighting. */
const PBR_CONVERTIBLE = new Set(["MeshLambertMaterial", "MeshBasicMaterial", "MeshPhongMaterial"]);

/**
 * Swap a Fragments mesh between its default lit material and a PBR `MeshStandardMaterial` that adds
 * roughness/metalness + responds to the IBL environment (reflections), preserving the per-element
 * IFC surface colours (M1). The original is stashed on `userData` so toggling render mode off
 * restores it exactly. Idempotent, and a no-op for materials we shouldn't touch (see above).
 */
function setMeshPbr(m: THREE.Mesh, on: boolean): void {
  const ud = m.userData as { _flatMat?: THREE.Material | THREE.Material[] };
  const first = Array.isArray(m.material) ? m.material[0] : m.material;
  if (on) {
    if (ud._flatMat || !first || !PBR_CONVERTIBLE.has(first.type)) return;   // already done / not safe
    const make = (src: THREE.Material): THREE.Material => {
      const b = src as THREE.MeshLambertMaterial;
      return new THREE.MeshStandardMaterial({
        color: b.color?.clone?.() ?? new THREE.Color(0xcfd3da),
        map: b.map ?? null,
        vertexColors: b.vertexColors,              // keep the per-element IFC surface colours (M1)
        transparent: b.transparent, opacity: b.opacity, side: b.side,
        alphaTest: b.alphaTest, depthWrite: b.depthWrite,
        roughness: 0.82, metalness: 0.0, envMapIntensity: 0.9,   // matte architectural default
      });
    };
    ud._flatMat = m.material;
    m.material = Array.isArray(m.material) ? m.material.map(make) : make(m.material);
  } else if (ud._flatMat) {
    const cur = m.material;                         // dispose the PBR clone(s) we created
    (Array.isArray(cur) ? cur : [cur]).forEach((mat) => mat.dispose());
    m.material = ud._flatMat;
    delete ud._flatMat;
  }
}

// VIZ-2: presentation post-processing (SSAO + bloom), installed by wrapping the engine renderer's
// `render` call — @thatopen's SimpleRenderer owns the frame loop, so routing its per-frame render
// through an EffectComposer is the only seam that needs no engine changes. Internal composer passes
// re-enter the wrapped `render`; the `inComposer` flag routes those to the raw renderer.
interface Fx {
  composer: EffectComposer;
  ssao: SSAOPass;
  raw: THREE.WebGLRenderer["render"];
  resize: () => void;
}
let fx: Fx | null = null;

function setPresentationFx(world: World, on: boolean): void {
  const r = world.renderer!.three;
  if (on && !fx) {
    const scene = world.scene.three;
    const size = r.getSize(new THREE.Vector2());
    // MSAA + half-float target so the composer chain doesn't lose the canvas's antialiasing
    const target = new THREE.WebGLRenderTarget(size.x, size.y, { samples: 4, type: THREE.HalfFloatType });
    const composer = new EffectComposer(r, target);
    const ssao = new SSAOPass(scene, world.camera.three, size.x, size.y);
    ssao.kernelRadius = 0.55;                       // metres-scale scenes: tight contact shadows
    ssao.minDistance = 0.001;
    ssao.maxDistance = 0.15;
    const bloom = new UnrealBloomPass(size.clone(), 0.22, 0.5, 0.85); // subtle — highlights only
    composer.addPass(ssao);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());             // applies the renderer's ACES + sRGB at the end
    const raw = r.render.bind(r);
    let inComposer = false;
    r.render = (s: THREE.Object3D, c: THREE.Camera): void => {
      // only the world scene through a perspective camera gets the FX chain — SSAO's shader is
      // compiled for a perspective depth reconstruction, and overlay/internal renders must stay raw
      if (inComposer || s !== scene || !(c as THREE.PerspectiveCamera).isPerspectiveCamera) {
        raw(s, c);
        return;
      }
      ssao.camera = c;
      inComposer = true;
      try {
        composer.render();
      } finally {
        inComposer = false;
      }
    };
    const resize = () => {
      const v = r.getSize(new THREE.Vector2());
      composer.setSize(v.x, v.y);
      ssao.setSize(v.x, v.y);
      bloom.setSize(v.x, v.y);
    };
    world.renderer!.onResize.add(resize);
    fx = { composer, ssao, raw, resize };
  } else if (!on && fx) {
    world.renderer!.onResize.remove(fx.resize);
    r.render = fx.raw;
    for (const p of fx.composer.passes) (p as Partial<{ dispose: () => void }>).dispose?.();
    fx.composer.dispose();
    fx = null;
  }
}

/**
 * "Render mode": a presentation-grade upgrade over the flat default scene — a directional sun with
 * soft shadows, hemisphere sky/ground fill, ACES tone mapping + sRGB output, a shadow-catching
 * ground plane, **IBL environment lighting**, a **PBR material swap** (plain lit surfaces →
 * `MeshStandardMaterial`) so they gain roughness/metalness + environment reflections on top of the
 * sun, and (VIZ-2) an **SSAO + bloom post chain** for contact shadows and highlight glow. Off by
 * default (cheaper, flat); toggled from the viewer toolbar. Idempotent — safe to call
 * repeatedly and after new models load.
 */
export function renderMode(world: World, on: boolean): void {
  const r = world.renderer!.three;
  const s = world.scene.three;

  setPresentationFx(world, on);               // VIZ-2: SSAO + bloom post chain
  s.environment = on ? studioEnv(r) : null;   // IBL ambient + reflections (PBR materials only)

  r.shadowMap.enabled = on;
  r.shadowMap.type = THREE.PCFSoftShadowMap;
  // R23-SHADOW-COST: re-rendering the shadow map every frame is the expensive half, and almost all
  // of it is wasted — a DIRECTIONAL light's shadow depends on the geometry and the sun, NOT on where
  // the camera is. Because `fitShadowFrustum` fits the shadow camera to the MODEL rather than to the
  // view, orbiting cannot change a single shadow texel, so the per-frame re-render buys nothing.
  // Switching it off is only safe given that property; the two changes are one change.
  r.shadowMap.autoUpdate = false;
  r.toneMapping = on ? THREE.ACESFilmicToneMapping : THREE.NoToneMapping;
  r.toneMappingExposure = on ? 1.05 : 1;
  r.outputColorSpace = THREE.SRGBColorSpace;

  let sun = s.getObjectByName(SUN) as THREE.DirectionalLight | null;
  if (on && !sun) {
    sun = new THREE.DirectionalLight(0xfff4e6, 2.4);
    sun.name = SUN;
    sun.position.set(45, 90, 35);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.04;
    s.add(sun);
    fitShadowFrustum(world);       // replaces the fixed ±140 m box — see below

    const hemi = new THREE.HemisphereLight(0xbcd4ff, 0x556070, 0.55); // sky / ground bounce
    hemi.name = HEMI;
    s.add(hemi);

    const fill = new THREE.DirectionalLight(0x9fb4d0, 0.5);
    fill.name = FILL;
    fill.position.set(-40, 30, -25);
    s.add(fill);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(2000, 2000),
      new THREE.ShadowMaterial({ opacity: 0.28 }),
    );
    ground.name = GROUND;
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.01; // just under the model so it catches shadows without z-fighting
    ground.receiveShadow = true;
    s.add(ground);
  } else if (!on) {
    for (const name of [SUN, HEMI, FILL, GROUND]) {
      const o = s.getObjectByName(name);
      if (o) s.remove(o);
    }
  }

  // (Re)apply cast/receive flags + the PBR material swap to all current model meshes.
  s.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh && m.name !== GROUND) {
      m.castShadow = on;
      m.receiveShadow = on;
      setMeshPbr(m, on);
    }
  });

  // the cast/receive flags just changed on every mesh, and `shadowMap.enabled` with them — the
  // fourth and last input that can alter a shadow, so it gets the fourth invalidation
  if (on) { fitShadowFrustum(world); }
}

/**
 * R23-SHADOW-COST — mark the shadow map for one re-render.
 *
 * With `autoUpdate` off, this is the ONLY thing that refreshes shadows, so every caller that changes
 * either input must call it: the sun moved, or the geometry did. Missing one leaves a stale shadow,
 * which is a worse defect than the cost this saves — hence the deliberately small number of inputs.
 */
export function invalidateShadows(world: World): void {
  const r = world.renderer?.three;
  if (r?.shadowMap.enabled) r.shadowMap.needsUpdate = true;
}

/**
 * Fit the sun's shadow camera to what is actually in the scene.
 *
 * The old frustum was a fixed ±140 m box: 280 m across a 2048² map is ~13.7 cm per texel, so a
 * building's shadows were quantised to roughly a brick course whatever its size — and a small model
 * wasted almost the whole map on empty space. Fitting to the model's own bounds spends every texel on
 * geometry, so a 20 m house gets ~1 cm texels and a 200 m tower still gets a frustum that contains it.
 *
 * Fitted in WORLD space, deliberately: a camera-fitted shadow frustum would have to re-render on every
 * orbit, which is exactly the cost being removed.
 */
export function fitShadowFrustum(world: World): void {
  const s = world.scene.three;
  const sun = s.getObjectByName(SUN) as THREE.DirectionalLight | null;
  if (!sun) return;
  const box = new THREE.Box3();
  s.traverse((o) => {
    // the shadow-catching ground is 1 km across and would swallow the fit; the lights have no extent
    if (o.name === GROUND || (o as THREE.Light).isLight) return;
    if ((o as THREE.Mesh).isMesh) box.expandByObject(o);
  });
  const c = sun.shadow.camera;
  if (box.isEmpty()) {
    const d = 140;                                   // nothing loaded yet — keep the old default
    Object.assign(c, { left: -d, right: d, top: d, bottom: -d, near: 1, far: 500 });
  } else {
    const size = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());
    Object.assign(c, shadowFrustum(size.length(), sun.position.length()));
    sun.target.position.copy(centre);
    if (!sun.target.parent) s.add(sun.target);
    sun.target.updateMatrixWorld();
  }
  c.updateProjectionMatrix();
  invalidateShadows(world);
}

/**
 * Aim the render-mode sun from a scene-space direction (unit vector *toward* the sun) — used by the
 * sun/shadow study. Warms the colour and dims the sun near the horizon (and below it) so dawn/dusk
 * and night read correctly. No-op if render mode isn't on. Returns true when the sun is up.
 */
export function positionSun(world: World, dir: { x: number; y: number; z: number }, distance = 160): boolean {
  const sun = world.scene.three.getObjectByName(SUN) as THREE.DirectionalLight | null;
  if (!sun) return false;
  sun.position.set(dir.x * distance, Math.max(dir.y, -0.2) * distance, dir.z * distance);
  invalidateShadows(world);      // the sun moved — one of the two things that can change a shadow
  const up = dir.y > 0;
  // intensity fades to 0 at/below the horizon; warmer + softer when low in the sky
  const t = Math.max(0, Math.min(1, dir.y / 0.25));            // 0 at horizon → 1 once well up
  sun.intensity = up ? 0.6 + 2.0 * Math.min(1, dir.y * 3) : 0;
  sun.color.setHSL(0.09 + 0.04 * t, 0.55 - 0.25 * t, 0.5 + 0.08 * t); // sunrise orange → midday white
  return up;
}
