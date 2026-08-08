import * as THREE from "three";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GridOverlay } from "./gridOverlay";

/**
 * GRID-OVERLAY-LEAK — found while premise-checking R23-BATCH-OVERLAYS, which points at this file.
 *
 * That item proposes instancing app-authored overlays. The population turned out to be mostly
 * absent — pins are DOM elements, the GIS layer already merges every feature into three buffers,
 * and most overlays are singletons — but the grid genuinely is per-axis, and measuring it turned up
 * a resource bug instead of a draw-call one:
 *
 *   AXES=8  textures made=8  leaked after ONE rebuild=8
 *
 * `set()` runs on every work-plane move, so this is proportional to axes x elevation changes during
 * ordinary authoring.
 *
 * **Why the file had no tests, which is the third bug.** `bubbleSprite` called `canvas.getContext("2d")!`
 * — a non-null assertion on something that is genuinely null under happy-dom. Constructing the
 * overlay threw a TypeError, so no test could reach it, so nothing here was ever covered. The
 * untestability and the defect had the same cause.
 */

/** happy-dom has no 2D context; stub exactly the calls the bubble draw makes. */
function stubCanvas() {
  return vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    fillStyle: "", font: "", textAlign: "", textBaseline: "",
    beginPath() {}, arc() {}, fill() {}, fillText() {},
  } as unknown as CanvasRenderingContext2D);
}

/** Track every texture disposal so a leak is a number rather than an impression. */
function trackDisposals() {
  const disposed = new Set<THREE.Texture>();
  const orig = THREE.Texture.prototype.dispose;
  vi.spyOn(THREE.Texture.prototype, "dispose").mockImplementation(function (this: THREE.Texture) {
    disposed.add(this);
    return orig.call(this);
  });
  return disposed;
}

const AXES = (n: number) => Array.from({ length: n }, (_, i) => ({
  tag: `A${i}`, start: [0, i] as [number, number], end: [10, i] as [number, number],
}));

const data = (n: number) => ({ axes: AXES(n), intersections: [] }) as never;

/** Every sprite texture currently in the group. */
function texturesIn(g: GridOverlay): THREE.Texture[] {
  const out: THREE.Texture[] = [];
  g.group.traverse((o) => {
    const m = (o as THREE.Sprite).material as THREE.SpriteMaterial | undefined;
    if (m && "map" in m && m.map) out.push(m.map);
  });
  return out;
}

let scene: THREE.Scene;
beforeEach(() => { stubCanvas(); scene = new THREE.Scene(); });
afterEach(() => { vi.restoreAllMocks(); });

describe("GridOverlay builds a grid at all", () => {
  it("draws one line and one bubble per axis", () => {
    // The positive control. Without it every leak assertion below could pass by building nothing.
    const g = new GridOverlay(scene);
    g.set(data(5), 0);
    expect(g.group.children.filter((o) => (o as THREE.Line).isLine)).toHaveLength(5);
    expect(g.group.children.filter((o) => (o as THREE.Sprite).isSprite)).toHaveLength(5);
    expect(g.hasData).toBe(true);
  });

  it("survives a canvas with no 2D context, without the labels", () => {
    // The assertion that used to be `getContext("2d")!`. A missing label beats a dead draft grid —
    // and per kernel/markupPlugin.ts, a throw on an overlay path takes the caller's work with it.
    vi.restoreAllMocks();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const g = new GridOverlay(scene);
    expect(() => g.set(data(3), 0)).not.toThrow();
    expect(g.group.children.filter((o) => (o as THREE.Line).isLine),
      "the grid lines must still be there — only the bubbles depend on a canvas").toHaveLength(3);
    expect(g.group.children.filter((o) => (o as THREE.Sprite).isSprite)).toHaveLength(0);
  });
});

describe("rebuilding on a work-plane move does not leak GPU textures", () => {
  it("reuses the cached bubble textures instead of allocating new ones", () => {
    // The churn half. `set()` runs on every elevation change; re-rasterising identical bubbles is
    // pure waste, and it was also what produced the orphans.
    const g = new GridOverlay(scene);
    g.set(data(8), 0);
    const first = texturesIn(g);
    g.set(data(8), 3);
    const second = texturesIn(g);
    expect(first).toHaveLength(8);
    expect(new Set([...first, ...second]).size,
      "a rebuild allocated fresh textures — the cache is not being hit").toBe(8);
  });

  it("orphans nothing across a rebuild — the measured defect, as a test", () => {
    const disposed = trackDisposals();
    const g = new GridOverlay(scene);
    g.set(data(8), 0);
    const made = texturesIn(g);
    g.set(data(8), 3);
    // Before the fix this was 8 of 8. A texture is safe if it is either still in use or disposed;
    // what must never happen is an orphan — dropped from the scene AND never released.
    const live = new Set(texturesIn(g));
    const orphaned = made.filter((t) => !live.has(t) && !disposed.has(t));
    expect(orphaned, `${orphaned.length} texture(s) orphaned by one rebuild`).toHaveLength(0);
  });

  it("releases every cached texture on dispose", () => {
    // The other half of ownership. Caching without this just moves the leak to teardown.
    const disposed = trackDisposals();
    const g = new GridOverlay(scene);
    g.set(data(6), 0);
    const made = texturesIn(g);
    expect(made).toHaveLength(6);
    g.dispose();
    expect(made.filter((t) => !disposed.has(t)),
      "cached textures outlived the overlay that owned them").toHaveLength(0);
    expect(scene.children).not.toContain(g.group);
  });

  it("a distinct tag still gets its own texture — the cache is not over-sharing", () => {
    // The paired control for the cache. A cache keyed too loosely would collapse every bubble to one
    // texture and pass the leak tests above while drawing the wrong labels.
    const g = new GridOverlay(scene);
    g.set(data(4), 0);
    expect(new Set(texturesIn(g)).size, "four different tags must not share one bubble").toBe(4);
  });
});
