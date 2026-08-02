/**
 * R38-NODE-SLIDERS — the node canvas's numeric inputs, exposed as NAMED sliders.
 *
 * The canvas stores each node's params as a JSON textarea, which is honest but is typing, not
 * designing: exploring "what if this wall were taller" means editing a number in a string and
 * re-running. A slider per numeric parameter — labelled `n2 · height`, scrubbed with the mouse,
 * optionally re-running the graph on release — is the difference between *authoring a graph* and
 * *playing an instrument*. This is the Grasshopper/Dynamo interaction the ring named, at its
 * smallest honest size.
 *
 * The textarea stays the single source of truth: a slider READS the JSON and WRITES the JSON, so
 * hand-edits and scrubs can interleave without two copies of the params drifting. Only top-level
 * finite scalars slide — coordinates (`start: [0,0]`) are positions, not magnitudes, and a slider
 * over an array index would invite exactly the shifted-field confusion PLAN-IDENTITY's tests exist
 * to catch.
 */

export interface SliderSpec {
  /** Param name, e.g. "height". */
  key: string;
  value: number;
  min: number;
  max: number;
  step: number;
}

/** A scrub range derived from the current value — generous enough to explore, bounded enough that
 *  one pixel of mouse is a meaningful change. Zero gets a default span instead of a dead slider. */
export function rangeFor(v: number): { min: number; max: number; step: number } {
  const mag = Math.abs(v);
  const step = mag >= 100 ? 1 : mag >= 10 ? 0.5 : mag >= 1 ? 0.1 : 0.01;
  const max = mag === 0 ? 10 : mag * 4;
  const min = v < 0 ? -max : 0;
  return { min, max, step };
}

/** The slidable params of one node: top-level finite numbers only, in declaration order. */
export function sliderSpecs(params: Record<string, unknown>): SliderSpec[] {
  const out: SliderSpec[] = [];
  for (const [key, v] of Object.entries(params)) {
    if (typeof v !== "number" || !Number.isFinite(v)) continue;
    out.push({ key, value: v, ...rangeFor(v) });
  }
  return out;
}

/**
 * Write one slider's value back into a params JSON string. Returns the new JSON, or null when the
 * text is not valid JSON — a scrub must never destroy a half-edited textarea by "fixing" it.
 * The value is rounded to the step's precision so the JSON doesn't fill with 2.4000000000000004.
 */
export function applySlider(paramsJson: string, key: string, value: number, step: number): string | null {
  let p: Record<string, unknown>;
  try { p = JSON.parse(paramsJson || "{}") as Record<string, unknown>; } catch { return null; }
  if (typeof p !== "object" || p === null || Array.isArray(p)) return null;
  const decimals = step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
  p[key] = Number(value.toFixed(decimals));
  return JSON.stringify(p, null, 0);
}
