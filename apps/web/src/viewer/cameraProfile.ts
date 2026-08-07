// R23-CAMERA-CLASS — camera parameters chosen from the viewport and the mode, instead of once.
//
// `@thatopen/components` constructs the world camera as `PerspectiveCamera(60, aspect, 1, 1e3)` and
// nothing in this app has ever revisited those numbers. Two measured consequences:
//
// **1. A fixed VERTICAL fov gives a phone a third of the view a desktop gets.** Horizontal fov is
// derived from vertical fov and aspect, so a portrait viewport collapses it:
//
//     phone portrait  aspect 0.46  ->  30deg horizontal
//     tablet          aspect 0.75  ->  47deg
//     desktop         aspect 1.60  ->  85deg
//
// The fix is to hold the HORIZONTAL angle roughly constant and derive vertical from it — the "Hor+"
// convention games have used for two decades. Clamped, because the un-clamped answer for a portrait
// phone is a 127deg vertical fov, which is a fisheye.
//
// **The clamp floor is 60 — today's value — on purpose: this can only ever WIDEN the view, never
// narrow it.** A profile that computed a "better" 51deg for desktop would be a regression shipped as
// an improvement, and nobody would report it as a bug; they would just see less.
//
// **2. `near = 1 metre` is wrong for a first-person walkthrough.** `walkMode.ts` puts the eye at
// 1.65 m and calls itself "the coordination-review move that orbit cameras hide" — but everything
// within a metre of the eye is clipped, so walking up to a wall, a column or a duct makes it vanish
// before you reach it. You cannot inspect anything closely, which is the entire point of the mode.
//
// **Why that is not simply fixed globally, with the number that decides it.** Depth precision at
// distance scales with `near`. For a 24-bit buffer the resolvable gap is about `z^2 / (near * 2^24)`:
//
//     near=1     0.1mm @50m   0.6mm @100m   2.4mm @200m
//     near=0.1   1.5mm @50m   6.0mm @100m  23.8mm @200m
//
// `guideUnderlay.ts` lifts its plane by `LEVEL_LIFT_M = 0.005` (5 mm) to avoid z-fighting with the
// storey slab. At `near=0.1` the resolvable gap passes 5 mm before 100 m, so a global change would
// make that underlay z-fight on any model of real size — trading a walk-mode defect for a rendering
// one. So the near plane moves **only in walk mode**, where `far` comes in too: indoors you are not
// looking 1 km, and pulling `far` back keeps the far-field precision loss bounded.

export type ViewportClass = "phone" | "tablet" | "desktop";

export interface CameraProfile {
  /** Vertical field of view, degrees. */
  fov: number;
  near: number;
  far: number;
  viewport: ViewportClass;
}

/** Breakpoints match the app's own responsive CSS rather than inventing a second set. */
export function viewportClass(width: number): ViewportClass {
  if (!Number.isFinite(width) || width <= 0) return "desktop";   // unmeasurable: keep today's behaviour
  if (width < 768) return "phone";
  if (width < 1024) return "tablet";
  return "desktop";
}

/** The horizontal angle a 60deg vertical fov gives at a reference 16:10 desktop — the target to hold. */
const TARGET_H_FOV = 85;
/** Never narrower than the library default (no regression), never wide enough to fisheye. */
const FOV_MIN = 60;
const FOV_MAX = 85;

const deg = (r: number) => (r * 180) / Math.PI;
const rad = (d: number) => (d * Math.PI) / 180;

export function cameraProfile(
  width: number, height: number, opts: { walk?: boolean } = {},
): CameraProfile {
  const viewport = viewportClass(width);
  const aspect = width > 0 && height > 0 ? width / height : 16 / 10;

  // vertical from horizontal: tan(v/2) = tan(h/2) / aspect
  const v = 2 * deg(Math.atan(Math.tan(rad(TARGET_H_FOV) / 2) / aspect));
  const fov = Math.min(FOV_MAX, Math.max(FOV_MIN, Math.round(v)));

  // Walk mode trades far-field depth precision for being able to see what you walk up to. `far` is
  // pulled in with `near` so the ratio — and so the precision loss — stays bounded; 200 m of draw
  // distance is far more than an interior review needs.
  return opts.walk
    ? { fov, near: 0.1, far: 200, viewport }
    : { fov, near: 1, far: 1000, viewport };
}

/** The horizontal angle a profile actually achieves — what the user experiences. Reported by tests. */
export function horizontalFov(fov: number, width: number, height: number): number {
  const aspect = width > 0 && height > 0 ? width / height : 16 / 10;
  return 2 * deg(Math.atan(Math.tan(rad(fov) / 2) * aspect));
}
