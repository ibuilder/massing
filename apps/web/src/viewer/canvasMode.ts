/**
 * R36-VIEWER-SUBAPP ④ — the canvas becomes one thing at a time, instead of 3D with a pane stuck to it.
 *
 * WHAT WAS THERE BEFORE
 * --------------------
 * The generated plan was a side pane: `position:absolute; right:0; width:38%`, toggled by
 * "◫ Plan beside model". So 2D was not a peer of 3D — it was a 38% strip of it, and the model was
 * always the thing the canvas *was*. The roadmap's ask is that the canvas switch what it renders in
 * place, which is a different claim: at any moment there is exactly one primary surface.
 *
 * WHY THIS IS A REDUCER AND NOT A `display:none` TOGGLE
 * ----------------------------------------------------
 * Two surfaces with independent `hidden` flags have four states, and two of them are wrong — both
 * visible, or neither. Nothing prevents them; you get the invariant by everyone remembering. Here
 * the mode IS the state, visibility is derived from it, and "exactly one visible" is not a rule
 * anyone has to follow.
 *
 * SPECS IS NOT REGISTERED, AND THAT IS THE POINT
 * ----------------------------------------------
 * The roadmap names three modes: Model ▸ Sheets ▸ Specs. Only two ship here, because the spec book
 * exists solely as a modal (`showResult("Project manual — 3-part MasterFormat spec book", …)`) and
 * has no canvas surface at all. Registering it would produce a tab that highlights and shows nothing
 * — the failure this repo has already recorded as "existence is not arrival". So a mode cannot be
 * registered without a surface to enter, and `canvasMode.test.ts` asserts the switch's tabs are
 * exactly the registered modes. Specs arrives when its renderer does, and the type already has a
 * seat for it.
 *
 * A REFUSAL CARRIES A REASON
 * --------------------------
 * `switchTo` returns `{ok:false, reason}` rather than silently doing nothing. A mode that cannot be
 * entered — Sheets before a model is loaded — must say so, because a tab that swallows the click is
 * indistinguishable from one that is broken.
 */

export type CanvasMode = "model" | "sheets" | "specs";

/** Declaration order is tab order. */
export const MODE_ORDER: readonly CanvasMode[] = ["model", "sheets", "specs"] as const;

export interface ModeDef {
  key: CanvasMode;
  /** Tab label. */
  label: string;
  /** Tooltip / accessible description. */
  title?: string;
  /** Why this mode cannot be entered right now, or null when it can. Re-evaluated per switch. */
  blocked?: () => string | null;
  /** Make this surface the canvas. Called only on an actual change. */
  enter: () => void;
  /** Yield the canvas. Called before the next mode's `enter`. */
  leave: () => void;
}

export interface SwitchResult {
  ok: boolean;
  /** Present only when `ok` is false — always a sentence a user can act on. */
  reason?: string;
}

export class CanvasModeSwitch {
  private readonly defs = new Map<CanvasMode, ModeDef>();
  private current: CanvasMode;

  /**
   * @param defs      the modes that have a real surface — order is normalised to `MODE_ORDER`
   * @param onChange  notified after a successful switch (for tab styling, telemetry, URL state)
   */
  constructor(defs: ModeDef[], private readonly onChange?: (mode: CanvasMode) => void) {
    if (!defs.length) throw new Error("CanvasModeSwitch needs at least one mode");
    for (const d of defs) {
      if (this.defs.has(d.key)) throw new Error(`duplicate canvas mode: ${d.key}`);
      this.defs.set(d.key, d);
    }
    this.current = this.modes()[0]!;
    // The opening mode is entered so the canvas and the state agree from the first frame. Without
    // this the switch believes it is in `model` while whatever the DOM happens to show is showing.
    this.defs.get(this.current)!.enter();
  }

  /** Registered modes, in `MODE_ORDER`. */
  modes(): CanvasMode[] {
    return MODE_ORDER.filter((m) => this.defs.has(m));
  }

  get active(): CanvasMode { return this.current; }

  def(mode: CanvasMode): ModeDef | undefined { return this.defs.get(mode); }

  /**
   * Enter `mode`, or refuse with a reason.
   *
   * Switching to the mode already active is a successful no-op — it must NOT re-enter, or every
   * click on the current tab would reset that surface's camera, scroll position and zoom.
   */
  switchTo(mode: CanvasMode): SwitchResult {
    const def = this.defs.get(mode);
    if (!def) {
      return { ok: false, reason: `${mode} is not available in this viewer yet` };
    }
    if (mode === this.current) return { ok: true };

    const why = def.blocked?.() ?? null;
    if (why) return { ok: false, reason: why };

    this.defs.get(this.current)!.leave();
    this.current = mode;
    def.enter();
    this.onChange?.(mode);
    return { ok: true };
  }
}

/**
 * Which surface is visible, derived from the mode.
 *
 * Exported separately so the invariant is testable without constructing DOM: for any mode, exactly
 * one registered surface is visible.
 */
export function visibility(mode: CanvasMode, registered: readonly CanvasMode[]): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const m of registered) out[m] = m === mode;
  return out;
}
