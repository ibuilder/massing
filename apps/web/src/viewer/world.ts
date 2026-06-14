import * as OBC from "@thatopen/components";

export type World = OBC.SimpleWorld<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>;

export interface Viewer {
  components: OBC.Components;
  world: World;
  container: HTMLElement;
}

/**
 * Sets up the shared viewer World (scene + camera + renderer) that every tool module
 * reads from. See guide §6 — one World, many tools.
 */
export function createViewer(container: HTMLElement): Viewer {
  const components = new OBC.Components();

  const worlds = components.get(OBC.Worlds);
  const world = worlds.create<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>();

  world.scene = new OBC.SimpleScene(components);
  world.scene.setup();
  world.scene.three.background = null;

  world.renderer = new OBC.SimpleRenderer(components, container);
  world.camera = new OBC.SimpleCamera(components);

  components.init();

  world.camera.controls.setLookAt(12, 8, 12, 0, 0, 0);

  // light reference grid
  const grids = components.get(OBC.Grids);
  grids.create(world);

  return { components, world, container };
}
