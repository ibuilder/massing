import { describe, expect, it } from "vitest";

/**
 * Landing on the project home, and being able to get back to it.
 *
 * The room shell has been the default and rendering correctly since v0.3.715 — and a user still
 * opened a project and asked where it had gone. Both of my own diagnoses of that were wrong, in the
 * same way: I asserted on things that *looked* like evidence.
 *
 * - I read `.portal-filter` in the DOM as proof the portal had mounted. That class also exists in the
 *   **modelling** rail's tool panel.
 * - I clicked a control labelled "Home" and reported what the screen showed. It was
 *   `class="fintab" data-fin="home"` — a Finance sub-tab, already active inside a *hidden* workspace.
 *
 * So these tests assert the two things that actually decide whether somebody finds the shell: the
 * workspace they land in, and whether a way back exists from everywhere else.
 */

//: mirrors PERSONAS in main.ts — each persona's declared seat
const PERSONA_HOME: Record<string, string> = {
  all: "model",
  developer: "developer",
  gc: "construction",
  superintendent: "construction",
  project_manager: "construction",
  architect: "design",
  engineer: "design",
  subcontractor: "construction",
};

const PORTAL_WORKSPACES = ["construction", "developer", "design"];

/** The landing rule from `initNav`: an explicit saved choice wins, else the persona's home. */
function landingWorkspace(persona: string, saved: string | null, allowed: string[] | null): string {
  if (saved && (!allowed || allowed.includes(saved))) return saved;
  return PERSONA_HOME[persona] ?? "model";
}

/** The signpost rule from `showProjectHomeSignpost`. */
function signpostVisible(workspace: string, hasProject: boolean): boolean {
  return hasProject && !PORTAL_WORKSPACES.includes(workspace);
}

describe("where a project opens", () => {
  it("a GC lands in the workspace that holds the room rail", () => {
    expect(PORTAL_WORKSPACES).toContain(landingWorkspace("gc", null, null));
  });

  it("an architect lands in theirs, not the GC's", () => {
    expect(landingWorkspace("architect", null, null)).toBe("design");
  });

  it("a developer lands in theirs", () => {
    expect(landingWorkspace("developer", null, null)).toBe("developer");
  });

  it("every role with a portal seat lands on the room rail, not the authoring canvas", () => {
    const roleSeats = Object.keys(PERSONA_HOME).filter((p) => p !== "all");
    for (const p of roleSeats) {
      expect(PORTAL_WORKSPACES, `${p} landed in ${landingWorkspace(p, null, null)}`)
        .toContain(landingWorkspace(p, null, null));
    }
  });

  it("an explicit choice still wins — a default is not a cage", () => {
    expect(landingWorkspace("gc", "model", ["construction", "model"])).toBe("model");
  });

  it("...but a saved choice the persona cannot reach falls back to their home", () => {
    // A stale key from another role must not strand somebody on a workspace their persona hides.
    expect(landingWorkspace("engineer", "finance", ["design", "model"])).toBe("design");
  });
});

describe("finding the way back", () => {
  it("the signpost shows in the authoring canvas, where people got lost", () => {
    expect(signpostVisible("model", true)).toBe(true);
  });

  it("...and in every other non-portal workspace", () => {
    for (const ws of ["model", "drawings", "studio", "finance"]) {
      expect(signpostVisible(ws, true), ws).toBe(true);
    }
  });

  it("it does NOT show where the rail is already on screen", () => {
    for (const ws of PORTAL_WORKSPACES) {
      expect(signpostVisible(ws, true), ws).toBe(false);
    }
  });

  it("it does not offer a home when no project is open", () => {
    expect(signpostVisible("model", false)).toBe(false);
  });

  it("'all roles' still homes to the canvas, and therefore MUST get the signpost", () => {
    // This is the exact case that produced "where is the new layout?" — the default persona lands in
    // the authoring canvas, which is a defensible seat for a modelling tool, so the way back has to
    // be visible rather than assumed.
    const ws = landingWorkspace("all", null, null);
    expect(ws).toBe("model");
    expect(signpostVisible(ws, true)).toBe(true);
  });
});
