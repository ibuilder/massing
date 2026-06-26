import * as THREE from "three";

/**
 * Set an origin / georeferencing (guide §6, explicit requirement).
 *
 * Large real-world coordinates wreck float precision and federated alignment. We render
 * near the scene origin by applying an offset to every loaded model, while preserving the
 * real coordinates for export and measurement readouts. The offset persists per project
 * (stored on Project.origin via the API) so models from different sources align.
 */
export interface WorkingOrigin {
  /** real-world coordinates of the scene origin (E/N/elevation or PBP/Survey point). */
  e: number;
  n: number;
  z: number;
}

export class OriginTool {
  private origin: WorkingOrigin = { e: 0, n: 0, z: 0 };

  setOrigin(origin: WorkingOrigin) {
    this.origin = origin;
  }

  getOrigin(): WorkingOrigin {
    return this.origin;
  }

  /** Apply the working-origin offset to a freshly loaded model so it renders near (0,0,0).
   *  Accepts any Object3D — a fragment model's `.object` or a reference overlay. */
  applyTo(obj: THREE.Object3D) {
    obj.position.set(-this.origin.e, -this.origin.z, this.origin.n); // Y-up: swap N/Z
    obj.updateMatrixWorld(true);
  }

  /** Convert a scene-space point back to real-world coordinates (for export/readouts). */
  toReal(point: THREE.Vector3): WorkingOrigin {
    return { e: point.x + this.origin.e, n: -point.z + this.origin.n, z: point.y + this.origin.z };
  }
}
