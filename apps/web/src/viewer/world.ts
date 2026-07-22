import * as OBC from "@thatopen/components";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { SSAOPass } from "three/examples/jsm/postprocessing/SSAOPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

export type World = OBC.SimpleWorld<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>;

export interface Viewer {
  components: OBC.Components;
  world: World;
  container: HTMLElement;
  grid: OBC.SimpleGrid;
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

  world.renderer = new OBC.SimpleRenderer(components, container);
  world.camera = new OBC.OrthoPerspectiveCamera(components);

  components.init();

  void world.camera.controls.setLookAt(12, 8, 12, 0, 0, 0);

  // light reference grid (toggled from the bottom settings bar)
  const grids = components.get(OBC.Grids);
  const grid = grids.create(world);

  return { components, world, container, grid };
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
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 500;
    const d = 140;
    Object.assign(sun.shadow.camera, { left: -d, right: d, top: d, bottom: -d });
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.04;
    s.add(sun);

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
  s.traverse((o: THREE.Object3D) => {
    const m = o as THREE.Mesh;
    if (m.isMesh && m.name !== GROUND) {
      m.castShadow = on;
      m.receiveShadow = on;
      setMeshPbr(m, on);
    }
  });
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
  const up = dir.y > 0;
  // intensity fades to 0 at/below the horizon; warmer + softer when low in the sky
  const t = Math.max(0, Math.min(1, dir.y / 0.25));            // 0 at horizon → 1 once well up
  sun.intensity = up ? 0.6 + 2.0 * Math.min(1, dir.y * 3) : 0;
  sun.color.setHSL(0.09 + 0.04 * t, 0.55 - 0.25 * t, 0.5 + 0.08 * t); // sunrise orange → midday white
  return up;
}
