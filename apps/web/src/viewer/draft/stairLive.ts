/**
 * R38-STAIR-LIVE — the consequence, shown before the commit.
 *
 * A client-side mirror of the server's `stair_geometry` / `ramp_geometry` (edit_enclosure.py):
 * while the stair or ramp tool is armed and a run is being dragged out, the readout says what THIS
 * run length means — riser count, riser, tread (or slope) — and whether it lands inside the shaped
 * limits, before any geometry is authored. The server's report stays authoritative on the authored
 * element; this mirror exists so the drawing hand learns the rule at the moment it matters.
 *
 * The constants are duplicated deliberately and PINNED BY TEST to the server's values
 * (`MAX_RISER_M` 0.19 · `MIN_TREAD_M` 0.25 · `MAX_RAMP_SLOPE` 1/12): a drifted mirror would show
 * green for a run the server reports as outside limits — worse than no readout. As on the server:
 * a REPORT, never a gate — the run is placed where it is drawn.
 */

export const MAX_RISER_M = 0.19;
export const MIN_TREAD_M = 0.25;
export const MAX_RAMP_SLOPE = 1 / 12;

/** The server default rise when the draw tool sends no target storey (add_stair/add_ramp). */
export const DEFAULT_RISE_M = 3.0;

export interface RunReadout {
  ok: boolean | null;
  text: string;
}

/** Mirror of stair_geometry: riser count from ceil(rise / MAX_RISER), riser and tread derived. */
export function stairReadout(rise: number, run: number): RunReadout {
  if (!(run > 0) || !(rise > 0)) return { ok: null, text: "stair — drag out the run" };
  const n = Math.max(1, Math.ceil(rise / MAX_RISER_M));
  const riser = rise / n;
  const tread = run / n;
  const ok = riser <= MAX_RISER_M + 1e-9 && tread >= MIN_TREAD_M - 1e-9;
  const base = `stair  ${n} risers @ ${riser.toFixed(3)} · tread ${tread.toFixed(3)}`;
  return ok
    ? { ok, text: `${base} ✓` }
    : { ok, text: `${base} ✗ tread < ${MIN_TREAD_M} — lengthen the run` };
}

/** Mirror of ramp_geometry: slope = rise / run against the 1:12 accessible limit. */
export function rampReadout(rise: number, run: number): RunReadout {
  if (!(run > 0)) return { ok: null, text: "ramp — drag out the run" };
  const slope = rise / run;
  const ok = slope <= MAX_RAMP_SLOPE + 1e-9;
  const ratio = slope > 0 ? `1:${Math.round(1 / slope)}` : "level";
  return ok
    ? { ok, text: `ramp  slope ${ratio} ✓ (limit 1:12)` }
    : { ok, text: `ramp  slope ${ratio} ✗ steeper than 1:12 — lengthen the run` };
}

/** The readout for a draw-tool key, or null when the armed tool has no run semantics. */
export function runReadout(toolKey: string, rise: number, run: number): RunReadout | null {
  if (toolKey === "stair") return stairReadout(rise, run);
  if (toolKey === "ramp") return rampReadout(rise, run);
  return null;
}
