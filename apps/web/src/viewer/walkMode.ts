import * as THREE from "three";

/** WALK-MODE (R17 Sprint B) — first-person walkthrough over the loaded model: WASD + pointer-lock at
 *  eye height, the coordination-review move that orbit cameras hide. The math lives in a headless
 *  `WalkController` (unit-tested; no DOM/three dependency in the core) and the installer wires
 *  pointer-lock + a rAF loop that drives `camera.controls.setLookAt` each frame. Desktop walk mode is
 *  the high-ROI half; a WebXR pass can reuse the same controller later. */

const LOOK_SENS = 0.0025;         // radians per pixel of mouse travel
const PITCH_LIMIT = (85 * Math.PI) / 180;

export class WalkController {
  /** position in world metres; y is held (walk, don't fly) unless raise/lower keys are used */
  pos = { x: 0, y: 1.65, z: 0 };
  yaw = 0;                        // 0 looks toward -Z (three convention)
  pitch = 0;
  speed = 3.5;                    // m/s walk
  runMultiplier = 2.5;            // holding Shift
  private keys = new Set<string>();

  keyDown(code: string) { this.keys.add(code); }
  keyUp(code: string) { this.keys.delete(code); }
  clearKeys() { this.keys.clear(); }

  /** Mouse-look: dx/dy in pixels. Pitch clamps to ±85° so the view never flips. */
  look(dx: number, dy: number) {
    this.yaw -= dx * LOOK_SENS;
    this.pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, this.pitch - dy * LOOK_SENS));
  }

  /** Advance dt seconds: W/S along the heading (horizontal), A/D strafe, E/Q (or PageUp/Down) raise/
   *  lower eye height, Shift runs. Forward stays horizontal regardless of pitch — walking, not flying. */
  step(dt: number) {
    const run = this.keys.has("ShiftLeft") || this.keys.has("ShiftRight");
    const v = this.speed * (run ? this.runMultiplier : 1) * dt;
    const sin = Math.sin(this.yaw), cos = Math.cos(this.yaw);
    let fwd = 0, strafe = 0, rise = 0;
    if (this.keys.has("KeyW") || this.keys.has("ArrowUp")) fwd += 1;
    if (this.keys.has("KeyS") || this.keys.has("ArrowDown")) fwd -= 1;
    if (this.keys.has("KeyD") || this.keys.has("ArrowRight")) strafe += 1;
    if (this.keys.has("KeyA") || this.keys.has("ArrowLeft")) strafe -= 1;
    if (this.keys.has("KeyE") || this.keys.has("PageUp")) rise += 1;
    if (this.keys.has("KeyQ") || this.keys.has("PageDown")) rise -= 1;
    // yaw 0 → forward -Z; strafe +1 → +X at yaw 0
    this.pos.x += (-sin * fwd + cos * strafe) * v;
    this.pos.z += (-cos * fwd - sin * strafe) * v;
    this.pos.y += rise * v;
    return this.pos;
  }

  /** The look-at target 1 m ahead along the current heading (pitch applied). */
  target() {
    const cp = Math.cos(this.pitch);
    return {
      x: this.pos.x - Math.sin(this.yaw) * cp,
      y: this.pos.y + Math.sin(this.pitch),
      z: this.pos.z - Math.cos(this.yaw) * cp,
    };
  }

  moving() { return this.keys.size > 0; }
}

export interface WalkModeDeps {
  viewer: { world: { camera: { controls: { getPosition(v: THREE.Vector3): void; getTarget(v: THREE.Vector3): void; setLookAt(px: number, py: number, pz: number, tx: number, ty: number, tz: number, transition?: boolean): void } } } };
  canvas: HTMLElement;
  toolBtn: (icon: string, title: string, onClick: (b: HTMLButtonElement) => void, cap?: "edit" | "review") => HTMLButtonElement;
  setStatus: (m: string) => void;
}

/** Install the 🚶 walk-mode toggle. Enter = pointer-lock + WASD from the current camera position;
 *  Esc (or the button) exits and the orbit camera resumes exactly where the walk ended. */
export function installWalkMode(d: WalkModeDeps): { walking: () => boolean; exit: () => void } {
  const ctl = new WalkController();
  let walking = false;
  let raf = 0;
  let last = 0;
  let btnRef: HTMLButtonElement | null = null;

  const onKey = (down: boolean) => (e: KeyboardEvent) => {
    if (!walking) return;
    if (down) ctl.keyDown(e.code); else ctl.keyUp(e.code);
    if (["KeyW", "KeyA", "KeyS", "KeyD", "KeyQ", "KeyE", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Space"].includes(e.code)) e.preventDefault();
  };
  const keyDown = onKey(true);
  const keyUp = onKey(false);
  const onMouse = (e: MouseEvent) => { if (walking && document.pointerLockElement) ctl.look(e.movementX, e.movementY); };
  const onLockChange = () => { if (walking && !document.pointerLockElement) exit(); };

  function frame(t: number) {
    if (!walking) return;
    const dt = Math.min(0.1, (t - last) / 1000);   // clamp long tab-away frames
    last = t;
    ctl.step(dt);
    const tgt = ctl.target();
    d.viewer.world.camera.controls.setLookAt(ctl.pos.x, ctl.pos.y, ctl.pos.z, tgt.x, tgt.y, tgt.z, false);
    raf = requestAnimationFrame(frame);
  }

  function enter() {
    const p = new THREE.Vector3(), t = new THREE.Vector3();
    d.viewer.world.camera.controls.getPosition(p);
    d.viewer.world.camera.controls.getTarget(t);
    ctl.pos = { x: p.x, y: p.y, z: p.z };
    ctl.yaw = Math.atan2(-(t.x - p.x), -(t.z - p.z));
    const horiz = Math.hypot(t.x - p.x, t.z - p.z);
    ctl.pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, Math.atan2(t.y - p.y, horiz || 1e-6)));
    walking = true;
    last = performance.now();
    document.addEventListener("keydown", keyDown, true);
    document.addEventListener("keyup", keyUp, true);
    document.addEventListener("mousemove", onMouse, true);
    document.addEventListener("pointerlockchange", onLockChange);
    void (d.canvas as HTMLElement & { requestPointerLock?: () => Promise<void> | void }).requestPointerLock?.();
    raf = requestAnimationFrame(frame);
    d.setStatus("walk mode — WASD move · mouse look · Shift run · E/Q up/down · Esc exit");
    btnRef?.classList.add("on");
  }

  function exit() {
    if (!walking) return;
    walking = false;
    cancelAnimationFrame(raf);
    ctl.clearKeys();
    document.removeEventListener("keydown", keyDown, true);
    document.removeEventListener("keyup", keyUp, true);
    document.removeEventListener("mousemove", onMouse, true);
    document.removeEventListener("pointerlockchange", onLockChange);
    if (document.pointerLockElement) document.exitPointerLock?.();
    d.setStatus("walk mode off");
    btnRef?.classList.remove("on");
  }

  btnRef = d.toolBtn("🚶", "Walk mode — first-person WASD walkthrough (Esc exits)", () => {
    if (walking) exit(); else enter();
  });
  return { walking: () => walking, exit };
}
