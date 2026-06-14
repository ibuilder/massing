import * as OBC from "@thatopen/components";
import * as OBCF from "@thatopen/components-front";
import type { World } from "../viewer/world";

export type MeasureMode = "off" | "length" | "area" | "angle";

/**
 * Measurement (guide §6): point-to-point distance, area, angle. Snaps to vertices/edges/
 * faces via the Fragments raycaster. Click to add points; double-click to finish a chain.
 */
export class MeasureTool {
  private length: OBCF.LengthMeasurement;
  private area: OBCF.AreaMeasurement;
  private angle: OBCF.AngleMeasurement;
  private _mode: MeasureMode = "off";

  constructor(components: OBC.Components, world: World) {
    this.length = components.get(OBCF.LengthMeasurement);
    this.area = components.get(OBCF.AreaMeasurement);
    this.angle = components.get(OBCF.AngleMeasurement);
    for (const m of [this.length, this.area, this.angle]) {
      m.world = world;
      m.enabled = false;
    }
  }

  get mode() {
    return this._mode;
  }

  setMode(mode: MeasureMode) {
    this._mode = mode;
    this.length.enabled = mode === "length";
    this.area.enabled = mode === "area";
    this.angle.enabled = mode === "angle";
  }

  /** Commit the current measurement point (wire to a click/dblclick). */
  create() {
    if (this._mode === "length") this.length.create();
    else if (this._mode === "area") this.area.create();
    else if (this._mode === "angle") this.angle.create();
  }

  /** Delete the measurement currently under the cursor for the active mode. */
  deleteCurrent() {
    if (this._mode === "length") this.length.delete();
    else if (this._mode === "area") this.area.delete();
    else if (this._mode === "angle") this.angle.delete();
  }
}
