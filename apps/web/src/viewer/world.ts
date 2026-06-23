import * as OBC from "@thatopen/components";
import * as THREE from "three";

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

  world.camera.controls.setLookAt(12, 8, 12, 0, 0, 0);

  // light reference grid (toggled from the bottom settings bar)
  const grids = components.get(OBC.Grids);
  const grid = grids.create(world);

  return { components, world, container, grid };
}

const SUN = "aec-sun", HEMI = "aec-hemi", FILL = "aec-fill", GROUND = "aec-shadow-ground";

/**
 * "Render mode": a presentation-grade lighting rig over the flat default scene — a directional sun
 * with soft shadows, hemisphere sky/ground fill, ACES tone mapping and sRGB output, plus a large
 * shadow-catching ground plane. Off by default (cheaper, flat); toggled from the viewer toolbar.
 * Idempotent — safe to call repeatedly and after new models load (re-applies mesh shadow flags).
 */
export function renderMode(world: World, on: boolean): void {
  const r = world.renderer!.three;
  const s = world.scene.three;

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

  // (Re)apply cast/receive flags to all current model meshes.
  s.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh && m.name !== GROUND) {
      m.castShadow = on;
      m.receiveShadow = on;
    }
  });
}
