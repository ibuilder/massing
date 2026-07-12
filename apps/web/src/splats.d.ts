// Minimal ambient types for @mkkellogg/gaussian-splats-3d (MIT) — the package ships no .d.ts.
// Only the surface splat.ts uses is declared; DropInViewer extends THREE.Group at runtime.
declare module "@mkkellogg/gaussian-splats-3d" {
  import { Group } from "three";
  export const SceneFormat: { Splat: number; KSplat: number; Ply: number; [k: string]: number };

  export interface AddSplatSceneOptions {
    format?: number;
    showLoadingUI?: boolean;
    progressiveLoad?: boolean;
    splatAlphaRemovalThreshold?: number;
    position?: number[];
    rotation?: number[];
    scale?: number[];
  }

  export class DropInViewer extends Group {
    constructor(options?: {
      sharedMemoryForWorkers?: boolean;
      gpuAcceleratedSort?: boolean;
      renderMode?: number;
      sceneRevealMode?: number;
      [k: string]: unknown;
    });
    addSplatScene(path: string, options?: AddSplatSceneOptions): Promise<void>;
    addSplatScenes(scenes: Array<{ path: string } & AddSplatSceneOptions>): Promise<void>;
    getSplatScene(index: number): unknown;
    update(): void;
    render(): void;
    dispose(): Promise<void> | void;
  }
}
