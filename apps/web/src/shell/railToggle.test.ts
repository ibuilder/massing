import { beforeEach, describe, expect, it } from "vitest";

/**
 * The ☰ button must describe itself.
 *
 * A user looked at the top-left of the app and asked what the three lines do. That is the finding:
 * the control's entire explanation was `title="Toggle panel (\\)"` plus `aria-label="Toggle panel"`.
 * Three things wrong at once, and each is the kind that survives review because the button *works*:
 *
 *  1. "Toggle panel" names no panel. There are several.
 *  2. It never changes, so after collapsing, a button that will now REVEAL the panel still reads
 *     "Toggle panel" — a label that describes neither the current state nor the next action.
 *  3. `(\\)` is two literal backslashes in HTML. The shortcut is one.
 *
 * `aria-expanded` is the fix that can be *tested*: it is the only machine-readable claim about the
 * panel's state, so the button and the panel can be asserted to agree. Without it, "the label is
 * right" is an opinion.
 */

/** Mirrors `toggleRail` in main.ts. */
function toggleRail(app: HTMLElement, btn: HTMLElement): void {
  const collapsed = app.classList.toggle("rail-collapsed");
  btn.setAttribute("aria-expanded", String(!collapsed));
  const label = collapsed ? "Show side panel" : "Hide side panel";
  btn.setAttribute("aria-label", label);
  btn.setAttribute("title", `${label} (\\)`);
}

let app: HTMLElement;
let btn: HTMLElement;

beforeEach(() => {
  document.body.innerHTML =
    '<div id="app"><button id="rail-toggle" aria-label="Hide side panel" aria-expanded="true" ' +
    'aria-controls="rail-panel" title="Hide side panel (\\)">☰</button>' +
    '<div id="rail-panel"></div></div>';
  app = document.getElementById("app")!;
  btn = document.getElementById("rail-toggle")!;
});

describe("the side-panel toggle", () => {
  it("names the panel it controls, not just 'panel'", () => {
    expect(btn.getAttribute("aria-label")).toMatch(/side panel/i);
    expect(btn.getAttribute("aria-controls")).toBe("rail-panel");
    expect(document.getElementById(btn.getAttribute("aria-controls")!)).toBeTruthy();
  });

  it("states the panel's state before anything is clicked", () => {
    expect(btn.getAttribute("aria-expanded")).toBe("true");
  });

  it("the shortcut hint is ONE backslash, not two", () => {
    // `\\` in an HTML attribute is two literal characters. The key is `\`.
    expect(btn.getAttribute("title")).toContain("(\\)");
    expect(btn.getAttribute("title")).not.toContain("(\\\\)");
  });

  it("aria-expanded tracks the panel — the button cannot claim open while it is shut", () => {
    toggleRail(app, btn);
    expect(app.classList.contains("rail-collapsed")).toBe(true);
    expect(btn.getAttribute("aria-expanded")).toBe("false");

    toggleRail(app, btn);
    expect(app.classList.contains("rail-collapsed")).toBe(false);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
  });

  it("the label describes the NEXT action, so it is never stale", () => {
    expect(btn.getAttribute("aria-label")).toBe("Hide side panel");
    toggleRail(app, btn);                       // now collapsed
    expect(btn.getAttribute("aria-label")).toBe("Show side panel");
    toggleRail(app, btn);
    expect(btn.getAttribute("aria-label")).toBe("Hide side panel");
  });

  it("the tooltip and the aria-label never disagree", () => {
    // Two labels on one control is two chances to be wrong. They must be one string.
    for (let i = 0; i < 3; i++) {
      const aria = btn.getAttribute("aria-label")!;
      expect(btn.getAttribute("title")).toBe(`${aria} (\\)`);
      toggleRail(app, btn);
    }
  });
});
