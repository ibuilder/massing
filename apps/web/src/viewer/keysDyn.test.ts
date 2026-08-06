import { beforeEach, describe, expect, it, vi } from "vitest";
import { installKeysDyn } from "./keysDyn";
import { createSnapOverride, type SnapOverrideHandle } from "./snapOverride";

/**
 * AUTH-SNAP-OVERRIDE — the *reachability* half.
 *
 * `snapOverride.test.ts` proves the state machine and the geometry. Neither would notice if the chord
 * never arrived: the override is armed from a two-letter buffer that already belongs to the draw-tool
 * shortcuts, and "an engine with nothing calling it" is this repo's most-repeated defect. So these
 * tests press keys at the real installed handler.
 */

function install(opts: { armed?: boolean; points?: number } = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const s = {
    container,
    notify: vi.fn((_msg: string, _kind: "info" | "success" | "error") => {}),
    onEscape: vi.fn(() => {}),
    override: createSnapOverride() as SnapOverrideHandle,
    armed: opts.armed ?? true,
    points: opts.points ?? 1,
  };
  installKeysDyn({
    container: s.container,
    notify: s.notify,
    isArmed: () => s.armed,
    armedPoints: () => s.points,
    draftHandle: () => null,
    onEscape: s.onEscape,
    snapOverride: s.override,
  });
  return s;
}

const press = (key: string) => window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
const type = (code: string) => { for (const ch of code) press(ch); };

beforeEach(() => { document.body.innerHTML = ""; });

describe("the one-shot code reaches the override through the real key handler", () => {
  it("PE while a tool is armed arms the perpendicular override", () => {
    const s = install({ armed: true });
    type("pe");
    expect(s.override.peek()).toBe("perpendicular");
  });

  it("all six codes arm, so none is published-but-dead", () => {
    for (const [code, kind] of [["EN", "endpoint"], ["MI", "midpoint"], ["CE", "center"],
      ["PE", "perpendicular"], ["NE", "nearest"], ["NO", "none"]] as const) {
      const s = install({ armed: true });
      type(code);
      expect(s.override.peek(), `code ${code}`).toBe(kind);
    }
  });

  // With no tool armed there is no "next pick", so the code must stay inert exactly as it was before
  // this feature existed — not arm an override that then steers an unrelated click.
  it("does nothing when no draw tool is armed", () => {
    const s = install({ armed: false });
    type("pe");
    expect(s.override.peek()).toBeNull();
  });

  it("a draw-tool code does not arm a snap override", () => {
    const s = install({ armed: true });
    type("wa");
    expect(s.override.peek()).toBeNull();
  });

  it("an unknown two-letter code arms nothing at all", () => {
    const s = install({ armed: true });
    type("zq");
    expect(s.override.peek()).toBeNull();
    expect(s.notify).not.toHaveBeenCalled();
  });

  it("tells the user what the next pick will do", () => {
    const s = install({ armed: true });
    type("ce");
    expect(s.notify).toHaveBeenCalledWith(expect.stringMatching(/next pick: centre/i), "info");
  });

  it("ignores keys typed into a text field", () => {
    const s = install({ armed: true });
    const input = document.createElement("input");
    document.body.appendChild(input);
    for (const ch of "pe") input.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true }));
    expect(s.override.peek()).toBeNull();
  });
});

describe("Escape cancels the pending override before it cancels the tool", () => {
  it("first Escape clears the override and leaves the draw tool alone", () => {
    const s = install({ armed: true });
    type("pe");
    press("Escape");
    expect(s.override.peek()).toBeNull();
    expect(s.onEscape).not.toHaveBeenCalled();       // the points already placed survive
  });

  it("Escape with nothing armed still disarms the tool, as it always did", () => {
    const s = install({ armed: true });
    press("Escape");
    expect(s.onEscape).toHaveBeenCalledTimes(1);
  });

  it("a second Escape disarms the tool", () => {
    const s = install({ armed: true });
    type("pe");
    press("Escape");
    press("Escape");
    expect(s.onEscape).toHaveBeenCalledTimes(1);
  });
});

describe("the HUD says what is armed and stops saying it when nothing is", () => {
  const hud = (s: ReturnType<typeof install>) => s.container.querySelector<HTMLElement>(".snap-override-hud")!;

  it("is hidden until something is armed", () => {
    const s = install({ armed: true });
    expect(hud(s).style.display).toBe("none");
  });

  it("names the armed kind", () => {
    const s = install({ armed: true });
    type("pe");
    expect(hud(s).style.display).toBe("block");
    expect(hud(s).textContent).toMatch(/perpendicular/i);
  });

  // A HUD still promising "perpendicular" after the pick that spent it is a statement about the next
  // click that is no longer true.
  it("clears when the override is consumed by a pick", () => {
    const s = install({ armed: true });
    type("pe");
    s.override.consume();
    expect(hud(s).style.display).toBe("none");
  });

  it("clears on Escape", () => {
    const s = install({ armed: true });
    type("ne");
    press("Escape");
    expect(hud(s).style.display).toBe("none");
  });
});

describe("the typed distance/angle buffer still works beside the codes", () => {
  it("digits build the dyn constraint rather than the two-letter buffer", () => {
    const s = install({ armed: true, points: 1 });
    press("6");
    const dyn = s.container.querySelector<HTMLElement>(".dyn-hud")!;
    expect(dyn.textContent).toContain("6");
  });
});
