import { beforeEach, describe, expect, it } from "vitest";

import type { ApiClient, ModuleDef } from "../api/client";
import { type PortalHost, PortalUI } from "./portal";

/**
 * `PortalUI.init()` may be entered twice, and must not build a second shell.
 *
 * **This defect was created by the fix beside it.** `main.ts::openPortalTab` used to latch
 * `portalReady = true` before awaiting `portal.init()`, so a rejection was terminal — the tab
 * stayed broken for the session (the bug `openDeveloperTab` carries a comment about) and, as a side
 * effect, `init()` was never re-entered. PR #577 made it retry, because the pin jump needs to WAIT
 * for the portal rather than guess at 500 ms. That turned every partial mutation on the way to a
 * rejection into reachable state: `init()` reassigns `this.root` to the content pane and registers
 * a `window` listener BEFORE it awaits `renderHome()`, which can reject.
 *
 * So a retry would have appended a second shell inside the first one's content pane, and added a
 * second `aec:persona` listener — each rebuilding the rail, compounding per failure.
 *
 * *Making a failure recoverable makes every partial mutation on the way to it reachable.* The retry
 * was the fix; the fix is what exposed this. Raised in review on PR #577.
 *
 * The guard is `if (!this.nav)` — `nav` is already the "shell exists" sentinel `buildNav` reads, so
 * the check costs nothing new. Everything AFTER it still re-runs on a retry: the module fetch, the
 * spine, the nav rebuild, the render. *A retry that cannot render is not a retry*, which is why the
 * guard wraps only the two mutations that must happen once rather than the whole method.
 * `reg.hookOnline()` needs no guard either way: `UploadQueue` latches its own `hooked`.
 *
 * The reasoning lives here rather than beside the code because `portal.ts` is under an extraction
 * ratchet, and the ratchet caught the eleven lines this paragraph used to be — *the lesson belongs
 * next to the check that holds it, which is this file.*
 */
const MODS = [
  { key: "rfi", name: "RFIs", section: "Coordination", room: "schedule", icon: "?", fields: [] },
] as unknown as ModuleDef[];

/** The private surface this reaches for — the same technique as `favourites.test.ts`. */
type Inner = { root: HTMLElement; renderHome: () => Promise<void>; buildNav: () => void };

function mount() {
  const root = document.createElement("div");
  document.body.appendChild(root);
  const api = {
    url: (p: string) => p,
    modules: async () => MODS,
    listViews: async () => [],
  } as unknown as ApiClient;
  const host: PortalHost = {
    api,
    projectId: () => "p1",
    anchorPoint: () => null,
    selectedGuid: () => null,
    onSelectGuids: () => {},
    onPinsChanged: () => {},
    setStatus: () => {},
  };
  const ui = new PortalUI(root, host);
  return { ui, root, inner: ui as unknown as Inner };
}

beforeEach(() => { document.body.innerHTML = ""; localStorage.clear(); });

describe("PortalUI.init() is safe to retry after a partial initialisation", () => {
  it("builds ONE shell when the first init rejects after the shell is up", async () => {
    const { ui, root, inner } = mount();
    let blowUp = true;
    inner.renderHome = () => {
      if (blowUp) { blowUp = false; return Promise.reject(new Error("renderHome failed")); }
      return Promise.resolve();
    };

    await expect(ui.init()).rejects.toThrow("renderHome failed");
    // The shell class goes on `root` ITSELF, so a NESTED shell is one found by a descendant query.
    expect(root.classList.contains("portal-shell"),
      "precondition: the first attempt got as far as building the shell — without that this test "
      + "is about a case that does not arise").toBe(true);

    await ui.init();                                   // the retry `openPortalTab` now permits
    expect(root.querySelectorAll(".portal-shell").length,
      "a second shell is nested inside the first one's content pane").toBe(0);
    expect(root.querySelectorAll(".portal-content").length,
      "a second content pane: every later render writes into the wrong one").toBe(1);
  });

  it("registers ONE `aec:persona` listener across both attempts — a duplicate rebuilds the rail "
     + "twice per persona change, and compounds with every failed init", async () => {
    const { ui, inner } = mount();
    let blowUp = true;
    inner.renderHome = () => {
      if (blowUp) { blowUp = false; return Promise.reject(new Error("renderHome failed")); }
      return Promise.resolve();
    };
    await expect(ui.init()).rejects.toThrow();
    await ui.init();

    let builds = 0;
    inner.buildNav = () => { builds++; };               // the listener calls it through `this`
    window.dispatchEvent(new CustomEvent("aec:persona"));
    expect(builds).toBe(1);
  });
});
