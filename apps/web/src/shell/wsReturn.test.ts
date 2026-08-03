/**
 * R36-DRAWINGS-RETURN — **a workspace that owns no rail must offer a way out, and it must be true.**
 *
 * The defect: `drawings.ts` renders into its own workspace with no back control and no route into the
 * viewer, and Specs behaves the same. The only exit is knowing the tabs along the top are navigation
 * — which is knowledge someone has to give you, and not what a person reaches for when a screen has
 * trapped them. They look for a way *back*.
 *
 * Two properties, and the second is the one that makes the control worth having:
 *
 *   1. **Every dead-end workspace has a return control.** A missing one is the whole bug.
 *   2. **It names where it goes, and goes where it came from.** A bare arrow makes the user try it to
 *      find out; a hard-coded destination sends someone who arrived from Design into the model, which
 *      is wrong-but-plausible — the class of behaviour that teaches people not to trust a control.
 *      Landing somewhere unexpected is a second trap, not an escape.
 *
 * The label is read from the workspace tab that already names it rather than a second lookup table:
 * a duplicated label list is exactly how the rail ended up with `undefinedView` on screen.
 */
import { beforeEach, describe, expect, it } from "vitest";

/** The shell fragment these controls live in — workspaces plus their tab strip. */
function mountShell(): void {
  document.body.innerHTML = `
    <!-- The SHIPPING tab strip: rooms carry data-room, and there is no .ws-btn anywhere in the app.
         The first fixture here invented .ws-btn elements, so the label lookup passed in test and
         fell back to the raw key live ("Back to design", lowercase). A fixture is a claim about the
         DOM, and that one was a claim about a DOM I made up. This is copied from what the app
         renders. model and drawings deliberately have NO tab here, because they have none in the
         app either, and the fallback has to be right for them. -->
    <div id="workspaces">
      <button data-room="design">Design</button>
      <button data-room="cost">Cost</button>
    </div>
    <main>
      <section id="ws-model" class="workspace active"></section>
      <section id="ws-drawings" class="workspace"></section>
      <section id="ws-design" class="workspace"></section>
    </main>`;
}

/**
 * The behaviour under test, mirroring `main.ts`. Reproduced rather than imported because `main.ts` is
 * the app entry point and importing it boots the whole shell; the logic asserted here is the
 * origin-tracking rule, and it is small enough that a drift between the two would be visible in the
 * one place it matters — the `DEAD_END_WS` set and the "previous, else model" fallback.
 */
function makeNav() {
  const DEAD_END_WS = new Set(["drawings"]);
  let currentWs = "model";
  let previousWs: string | null = null;

  const wsLabel = (key: string) => {
    const tab = document.querySelector<HTMLElement>(`[data-room="${key}"]`);
    const named = (tab?.textContent || "").trim();
    return named || key.charAt(0).toUpperCase() + key.slice(1);
  };

  function renderReturnBar(wsKey: string): void {
    const host = document.getElementById(`ws-${wsKey}`);
    if (!host) return;
    const dest = previousWs && previousWs !== wsKey ? previousWs : "model";
    let bar = host.querySelector<HTMLElement>(".ws-return");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "ws-return";
      host.prepend(bar);
    }
    bar.textContent = "";
    const back = document.createElement("button");
    back.type = "button";
    back.className = "tool-btn ws-return-btn";
    back.textContent = `← Back to ${wsLabel(dest)}`;
    back.onclick = () => setWorkspace(dest);
    bar.appendChild(back);
  }

  function setWorkspace(key: string): void {
    if (key !== currentWs) previousWs = currentWs;
    currentWs = key;
    document.querySelectorAll(".workspace").forEach((w) => w.classList.toggle("active", w.id === `ws-${key}`));
    if (DEAD_END_WS.has(key)) renderReturnBar(key);
  }

  return { setWorkspace, active: () => currentWs, DEAD_END_WS };
}

const returnBtn = (ws: string) =>
  document.querySelector<HTMLButtonElement>(`#ws-${ws} .ws-return button`);

describe("a dead-end workspace offers a way out", () => {
  beforeEach(mountShell);

  it("every dead-end workspace renders a return control", () => {
    const nav = makeNav();
    for (const ws of nav.DEAD_END_WS) {
      nav.setWorkspace(ws);
      expect(returnBtn(ws), `${ws} has no way back — the defect this file exists for`).not.toBeNull();
    }
  });

  it("the control NAMES its destination — a bare arrow makes you try it to find out", () => {
    const nav = makeNav();
    nav.setWorkspace("drawings");
    expect(returnBtn("drawings")!.textContent).toBe("← Back to Model");
  });

  it("it returns where you CAME FROM, not to a hard-coded home", () => {
    // The assertion that makes the control trustworthy. Arriving from Design and being sent to the
    // model is a second trap, not an escape.
    const nav = makeNav();
    nav.setWorkspace("design");
    nav.setWorkspace("drawings");
    expect(returnBtn("drawings")!.textContent, "arrived from Design").toBe("← Back to Design");

    nav.setWorkspace("model");
    nav.setWorkspace("drawings");
    expect(returnBtn("drawings")!.textContent, "arrived from the model").toBe("← Back to Model");
  });

  it("clicking it actually lands there", () => {
    // Existence is not arrival — a tab that highlights without navigating is a defect this repo has
    // already shipped once.
    const nav = makeNav();
    nav.setWorkspace("design");
    nav.setWorkspace("drawings");
    returnBtn("drawings")!.click();
    expect(nav.active()).toBe("design");
    expect(document.getElementById("ws-design")!.classList.contains("active")).toBe(true);
    expect(document.getElementById("ws-drawings")!.classList.contains("active")).toBe(false);
  });

  it("re-entering from a different origin UPDATES the destination", () => {
    // The bar is built once and reused, so a stale label would send the second visitor to the first
    // visitor's origin — a wrong destination that looks entirely deliberate.
    const nav = makeNav();
    nav.setWorkspace("design");
    nav.setWorkspace("drawings");
    nav.setWorkspace("design");
    nav.setWorkspace("model");
    nav.setWorkspace("drawings");
    expect(returnBtn("drawings")!.textContent).toBe("← Back to Model");
    expect(document.querySelectorAll("#ws-drawings .ws-return").length, "one bar, not one per visit")
      .toBe(1);
  });

  it("never offers to return to ITSELF", () => {
    // Re-entering the workspace you are already in must not produce "← Back to Drawings".
    const nav = makeNav();
    nav.setWorkspace("drawings");
    nav.setWorkspace("drawings");
    expect(returnBtn("drawings")!.textContent).not.toContain("Drawings");
  });
});
