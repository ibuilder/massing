import { describe, it, expect } from "vitest";
import { signInDoors, collapsedDoors } from "./signInDoors";

const G = { id: "google", label: "Google" };
const M = { id: "microsoft", label: "Microsoft" };
const P = { id: "procore", label: "Procore" };

describe("signInDoors", () => {
  it("offers the SAML door when the server says the workspace has one", () => {
    // The regression this file exists for: `GET /auth/providers` returns `saml`, the client type did
    // not declare it, and the modal branched on `providers.length` alone — so a workspace with a
    // configured IdP and a tier that entitles SSO saw a hint telling it to configure OAuth.
    const doors = signInDoors([], true);
    expect(doors.map((d) => d.key)).toEqual(["saml"]);
    expect(doors[0]!.path).toBe("/auth/saml/login");
    expect(doors[0]!.lead).toBe(true);
  });

  it("is empty only when NEITHER door is configured", () => {
    expect(signInDoors([], false)).toEqual([]);
    expect(signInDoors([], true).length).toBe(1);
    expect(signInDoors([P], false).length).toBe(1);
  });

  it("puts SAML ahead of the OAuth providers", () => {
    expect(signInDoors([G, M], true).map((d) => d.key)).toEqual(["saml", "google", "microsoft"]);
  });

  it("never routes SAML through the OAuth login path", () => {
    // SAML is not an entry in `providers` and has no `/auth/oauth/{id}/login` URL; sending it there
    // would 404 on a provider id the server has never heard of.
    for (const d of signInDoors([G, P], true)) {
      expect(d.path).toBe(d.key === "saml" ? "/auth/saml/login" : `/auth/oauth/${d.key}/login`);
    }
  });

  it("leads with Google and Microsoft and collapses the rest", () => {
    const doors = signInDoors([P, G, M], false);
    expect(doors.filter((d) => d.lead).map((d) => d.key)).toEqual(["google", "microsoft"]);
    expect(collapsedDoors(doors).map((d) => d.key)).toEqual(["procore"]);
  });

  it("promotes the first provider when neither primary is configured", () => {
    // Otherwise a server with only Procore hides its only OAuth door behind a disclosure link.
    const doors = signInDoors([P], false);
    expect(doors[0]!.lead).toBe(true);
    expect(collapsedDoors(doors)).toEqual([]);
  });

  it("does not promote an OAuth provider just because SAML is present", () => {
    // SAML leading must not change which OAuth doors collapse — the two rules are independent.
    const withSaml = signInDoors([P, G, M], true);
    const without = signInDoors([P, G, M], false);
    expect(collapsedDoors(withSaml).map((d) => d.key)).toEqual(collapsedDoors(without).map((d) => d.key));
  });

  it("keeps the server's provider order inside each group", () => {
    const doors = signInDoors([M, G], false);
    expect(doors.filter((d) => d.lead).map((d) => d.key)).toEqual(["microsoft", "google"]);
  });

  it("carries the server's label, not the id", () => {
    const doors = signInDoors([{ id: "google", label: "Google Workspace" }], false);
    expect(doors[0]!.label).toBe("Google Workspace");
  });
});
