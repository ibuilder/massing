import { describe, it, expect } from "vitest";
import { importConfirmText, importedSummary, installableNote } from "./costVintage";

describe("installableNote", () => {
  it("names the ROLE rather than offering an action", () => {
    // The budget card's reader is usually a cost manager, not a platform administrator. Offering a
    // button there would 403 for exactly the person most likely to press it — the same
    // offered-and-refused shape the saved-view delete picker had.
    const line = installableNote([{ note: "2025 Q1" }])!;
    expect(line).toContain("platform administrator");
    expect(line).toContain("no subscription");
    expect(line).toContain("(2025 Q1)");
  });

  it("is null when nothing is installable, so no line is rendered at all", () => {
    expect(installableNote([])).toBeNull();
    expect(installableNote(undefined)).toBeNull();
  });

  it("agrees with itself in the singular", () => {
    expect(installableNote([{}])).toContain("1 offline baseline installable");
    expect(installableNote([{}, {}])).toContain("2 offline baselines installable");
  });

  it("omits the parenthetical when the server sent no note", () => {
    expect(installableNote([{}])).not.toContain("(");
  });
});

describe("importConfirmText", () => {
  it("states the blast radius, which is the whole reason this is admin-only", () => {
    // The consequence belongs in the dialog, not in a docstring nobody clicking can see: this is a
    // server-wide reprice, not a change to one project.
    const t = importConfirmText();
    expect(t).toContain("NOT pinned");
    expect(t).toContain("server-wide");
    expect(t).toContain("Projects with a pinned vintage are unaffected");
    expect(t).toContain("idempotent");
  });
});

describe("importedSummary", () => {
  it("reports what landed", () => {
    expect(importedSummary({ name: "Public 2025 Q1" })).toBe("Installed Public 2025 Q1 and set it as latest.");
  });

  it("builds a label from vintage and quarter when the server sent no name", () => {
    expect(importedSummary({ vintage: 2025, quarter: 3 })).toContain("2025 Q3");
    expect(importedSummary({ vintage: 2025, quarter: null })).toContain("Installed 2025 ");
  });

  it("SURFACES the server's warning rather than swallowing it", () => {
    // The route returns `warning` when a `cloud` source was asked for and the offline public build
    // was served instead. Reporting plain success there would tell the operator they installed
    // something they did not.
    const s = importedSummary({ name: "Public 2025", warning: "no cloud subscription configured" });
    expect(s).toContain("Note: no cloud subscription configured");
  });

  it("falls back to a neutral label rather than printing undefined", () => {
    expect(importedSummary({})).toContain("new vintage");
  });
});
