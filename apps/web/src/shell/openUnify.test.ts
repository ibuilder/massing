import { describe, expect, it } from "vitest";

import { baseName, decideModelOpen, decideProjectOpen, nameFromFile } from "./openUnify";

const ctx = (over: Partial<Parameters<typeof decideModelOpen>[0]> = {}) => ({
  connected: true, openProjectId: null, fileName: "Tower.ifc", projects: [], ...over,
});

// --- offline never creates ---------------------------------------------------------------------------
describe("with no API, opening a model is a pure viewing act", () => {
  it("stays in the viewer and creates nothing", () => {
    const d = decideModelOpen(ctx({ connected: false }));
    expect(d.intent).toBe("viewer-only");
    expect(d.projectId).toBeNull();
    expect(d.suggestedName).toBeNull();
  });
  it("says WHY there is no project, rather than leaving the panels mysteriously empty", () => {
    // This is the exact confusion the ring exists to remove: a model on screen and no data anywhere.
    expect(decideModelOpen(ctx({ connected: false })).reason).toContain("no API reachable");
  });
  it("offline wins even when a matching project would otherwise be found", () => {
    const d = decideModelOpen(ctx({
      connected: false,
      projects: [{ id: "p1", name: "Tower", source_ifc: "/srv/Tower.ifc" }],
    }));
    expect(d.intent).toBe("viewer-only");
  });
});

// --- an existing project is joined, not duplicated -----------------------------------------------------
describe("opening a model the server already holds joins that project", () => {
  const projects = [{ id: "p1", name: "Riverside Tower", source_ifc: "/app/ifc/abc/Tower.ifc" }];

  it("attaches, bringing the project's data with it", () => {
    const d = decideModelOpen(ctx({ projects }));
    expect(d.intent).toBe("attach-existing");
    expect(d.projectId).toBe("p1");
  });
  it("matches across differing paths and case — the file name is the comparable part", () => {
    expect(decideModelOpen(ctx({ fileName: "C:\\Users\\me\\TOWER.IFC", projects })).intent)
      .toBe("attach-existing");
  });
  it("declares the match as WEAK rather than presenting it as certain", () => {
    // Two firms' Building.ifc are not the same building. The basis is stated so a user can check.
    const d = decideModelOpen(ctx({ projects }));
    expect(d.matchedOn).toBe("filename");
    expect(d.reason).toContain("FILE NAME only");
  });
  it("does not match a project that has no model at all", () => {
    expect(decideModelOpen(ctx({ projects: [{ id: "p9", name: "Empty", source_ifc: null }] })).intent)
      .toBe("create");
  });
  it("refuses to match on a stem too short to mean anything", () => {
    // A one-character stem would match half a register; better to propose a project than to guess.
    const d = decideModelOpen(ctx({ fileName: "A.ifc",
                                    projects: [{ id: "p1", name: "A", source_ifc: "/x/A.ifc" }] }));
    expect(d.intent).toBe("create");
  });
});

// --- a project already open wins ------------------------------------------------------------------------
describe("a model opened while a project is open loads INTO it", () => {
  it("never starts a rival project", () => {
    const d = decideModelOpen(ctx({ openProjectId: "open-1",
                                    projects: [{ id: "p1", name: "T", source_ifc: "/x/Tower.ifc" }] }));
    expect(d.intent).toBe("load-into-open");
    expect(d.projectId).toBe("open-1");        // the OPEN one, not the name-matched one
    expect(d.matchedOn).toBe("open-project");
  });
});

// --- creating is proposed, never silent --------------------------------------------------------------------
describe("an unrecognised model proposes a project rather than minting one", () => {
  it("returns `create` with a name taken from the file", () => {
    const d = decideModelOpen(ctx({ fileName: "Riverside Tower.ifc" }));
    expect(d.intent).toBe("create");
    expect(d.suggestedName).toBe("Riverside Tower");
    expect(d.projectId).toBeNull();            // nothing exists yet — the caller confirms
  });
  it("keeps the author's words instead of normalising them away", () => {
    expect(nameFromFile("/models/West Wing — Rev C.ifc")).toBe("West Wing — Rev C");
  });
  it("never produces an empty name", () => {
    expect(nameFromFile(".ifc")).toBe("Untitled project");
    expect(nameFromFile("")).toBe("Untitled project");
  });
});

describe("baseName is the comparable part of a file reference", () => {
  it("strips directories, extension and case", () => {
    expect(baseName("/app/ifc/uuid/Source.IFC")).toBe("source");
    expect(baseName("C:\\a\\b\\Model.frag")).toBe("model");
  });
  it("survives a bare name and an empty one", () => {
    expect(baseName("Tower.ifc")).toBe("tower");
    expect(baseName("")).toBe("");
  });
});

// --- the mirror of the bug ------------------------------------------------------------------------------------
describe("opening a project with no model offers one to author", () => {
  it("a project without a model is a dead end, so a blank model is offered", () => {
    expect(decideProjectOpen({ source_ifc: null, model_kind: null })).toBe("offer-blank-model");
  });
  it("a project with a model just loads it", () => {
    expect(decideProjectOpen({ source_ifc: "/app/ifc/x/source.ifc" })).toBe("load-model");
    expect(decideProjectOpen({ model_kind: "frag" })).toBe("load-model");
  });
});
