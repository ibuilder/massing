/**
 * R36-DRAWINGS-RETURN — **a workspace that owns no rail must offer a way out, and it must be true.**
 *
 * The defect, as re-measured in the running app on 2026-08-09: **Drawings already had its return
 * control and its room tabs** — this file's original claim that neither did was true when written and
 * stale by the time it was read. What was still broken was Specs, and for a reason no destination
 * list could express: `openSpecs()` calls `setWorkspace("design")`, so Specs is not a workspace and
 * `DEAD_END_WS` never fired for it. The only exit was knowing the tabs along the top are navigation
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

import { DEAD_END_WS, offersReturn, returnLabel, returnTarget } from "./wsReturn";

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
 * The DOM plumbing, mirroring `main.ts`. Still reproduced — importing `main.ts` boots the whole
 * shell — but every DECISION is now imported from `./wsReturn`, which is the point of that module
 * existing.
 *
 * The previous version reproduced the decisions too, including its own
 * `DEAD_END_WS = new Set(["drawings"])`, and argued that drift "would be visible in the one place it
 * matters". It was not: this file's own header said *"and Specs behaves the same"* while its copy of
 * the set silently excluded Specs, so the suite passed for months over a gap it had described in
 * prose. A test asserting a reproduction cannot fail when the original is wrong.
 */
function makeNav() {
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
    const dest = returnTarget(previousWs, wsKey);          // the REAL rule, imported
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
    back.textContent = returnLabel(dest, wsLabel);         // the REAL label, imported
    back.onclick = () => setWorkspace(dest);
    bar.appendChild(back);
  }

  function setWorkspace(key: string, arrival: "jump" | "nav" = "nav"): void {
    const moved = key !== currentWs;
    if (moved) previousWs = currentWs;
    currentWs = key;
    document.querySelectorAll(".workspace").forEach((w) => w.classList.toggle("active", w.id === `ws-${key}`));
    if (offersReturn(key, moved ? previousWs : null, arrival)) renderReturnBar(key);  // REAL trigger
    else document.getElementById(`ws-${key}`)?.querySelector(".ws-return")?.remove();
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

describe("a JUMP out of your workspace owes you a return, even to a normal workspace", () => {
  beforeEach(mountShell);

  it("Specs — the case the old copy of DEAD_END_WS could not express", () => {
    // `openSpecs()` does `setWorkspace("design")`. Design is a perfectly ordinary workspace with
    // tabs, so no set of dead-end NAMES would ever have caught this. Measured in the running app
    // before the fix: of seven visible controls there mentioning model/3D, one was the Design tab
    // the user was already on, two were analysis modules, and four were project-home cards —
    // start-over actions, not a way back.
    const nav = makeNav();
    nav.setWorkspace("design", "jump");
    expect(returnBtn("design"), "pressing Specs from the model must not strand the user").not.toBeNull();
    expect(returnBtn("design")!.textContent).toBe("← Back to Model");
  });

  it("BOTH launch surfaces behave the same — asserted as a set, not one example", () => {
    // The defect was an ASYMMETRY: Drawings had the control and Specs did not. Checking them
    // together is what makes that expressible; two separate tests would both have passed while the
    // pair disagreed, which is exactly what happened.
    for (const [dest, arrival] of [["drawings", "jump"], ["design", "jump"]] as const) {
      mountShell();
      const nav = makeNav();
      nav.setWorkspace(dest, arrival);
      expect(returnBtn(dest), `${dest} reached by a rail jump has no way back`).not.toBeNull();
      expect(returnBtn(dest)!.textContent).toBe("← Back to Model");
    }
  });

  it("choosing a workspace from the NAV does not grow a return bar", () => {
    // The twin. Without it, "always render the bar" would pass every assertion above while putting a
    // back button on every ordinary navigation — a control that appears everywhere means nothing.
    const nav = makeNav();
    nav.setWorkspace("design", "nav");
    expect(returnBtn("design"), "ordinary navigation is not a trap and needs no escape").toBeNull();
  });

  it("a dead end stays a dead end however you reach it", () => {
    // Drawings owns no tabs of its own, so arriving from the workspace bar still traps you. The
    // journey rule ADDS to the destination rule rather than replacing it.
    const nav = makeNav();
    nav.setWorkspace("drawings", "nav");
    expect(returnBtn("drawings")).not.toBeNull();
  });

  it("a jump that does not change workspace offers nothing", () => {
    const nav = makeNav();
    nav.setWorkspace("design", "nav");
    nav.setWorkspace("design", "jump");
    expect(returnBtn("design"), "you never left, so there is nowhere to go back to").toBeNull();
  });
});

describe("the bar is removed, not merely not-rendered", () => {
  beforeEach(mountShell);

  it("a later ORDINARY visit clears a bar left by an earlier jump", () => {
    // Found live, and invisible to every test above: each one mounts a fresh DOM, so a bar that
    // outlives its reason had nowhere to show up. In the running app the Design workspace kept
    // "← Back to Model" permanently after one press of Specs — telling the next arrival they had
    // been carried somewhere they had in fact walked into, and offering an exit from no trap.
    const nav = makeNav();
    nav.setWorkspace("design", "jump");
    expect(returnBtn("design"), "the jump earns a bar").not.toBeNull();

    nav.setWorkspace("model");
    nav.setWorkspace("design", "nav");
    expect(returnBtn("design"), "walking in yourself must clear it").toBeNull();
  });

  it("a dead end KEEPS its bar on an ordinary visit", () => {
    // The twin: "remove whenever arrival is nav" would pass the test above and silently strip the
    // control from Drawings, which is the original defect restored.
    const nav = makeNav();
    nav.setWorkspace("drawings", "jump");
    nav.setWorkspace("model");
    nav.setWorkspace("drawings", "nav");
    expect(returnBtn("drawings"), "drawings owns no tabs — it is a trap however you arrive").not.toBeNull();
  });
});
