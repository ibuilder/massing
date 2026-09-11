import { describe, it, expect } from "vitest";
import { sealIdentity, type AssetRightsStatus } from "./assetRights";

const st = (o: Partial<AssetRightsStatus>): AssetRightsStatus =>
  ({ enabled: true, signing: true, issuer: "did:web:example.com", public_key: "k".repeat(43), ...o });

describe("sealIdentity", () => {
  it("names the issuer and the key a verifier would check against", () => {
    const id = sealIdentity(st({}));
    expect(id).toEqual({ issuer: "did:web:example.com", key: "k".repeat(43) });
  });

  it("is null when the deployment cannot sign at all", () => {
    // Sealing still works unsigned — tamper-evident, no attribution — and the dialog must not offer
    // an identity in that case, because there is nothing anyone could verify it against.
    expect(sealIdentity(st({ signing: false, public_key: "" }))).toBeNull();
  });

  it("is null when signing is claimed but NO key is published", () => {
    // The case worth having a test for: `signing: true` with an empty `public_key` would otherwise
    // render "Verification key:" followed by nothing, which reads as an identity a third party can
    // check and is not one. The server sends "" deliberately so "no key here" is distinguishable
    // from "key withheld"; this is the client honouring that distinction.
    expect(sealIdentity(st({ public_key: "" }))).toBeNull();
    expect(sealIdentity(st({ public_key: "   " }))).toBeNull();
  });

  it("refuses a key when `signing` is false, even if one is somehow present", () => {
    // Mutation-driven. The first version of the "cannot sign" test above set `public_key: ""` too,
    // so it passed with the `signing` check deleted — the empty-key guard caught it instead, and the
    // two guards were indistinguishable from the tests. Today's server cannot produce this state
    // (it sends "" whenever signing is unavailable), but the TYPE permits it and the meaning is not
    // ambiguous: `signing` is the field that says whether this deployment signs, so a key beside a
    // false is a server bug and must not be advertised as an identity.
    expect(sealIdentity(st({ signing: false }))).toBeNull();
  });

  it("still returns the key when no issuer NAME is configured", () => {
    // An unnamed issuer is a real state, not an error: the key alone is what the signature is
    // checked against. Dropping the identity here would hide a publishable key.
    expect(sealIdentity(st({ issuer: "" }))).toEqual({ issuer: "", key: "k".repeat(43) });
  });

  it("trims, so whitespace around a configured value is not rendered", () => {
    expect(sealIdentity(st({ issuer: "  did:web:x  ", public_key: " abc " })))
      .toEqual({ issuer: "did:web:x", key: "abc" });
  });
});
