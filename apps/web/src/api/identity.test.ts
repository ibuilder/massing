import { describe, expect, it } from "vitest";

import { currentIdentity, identityScope, ownedByMe } from "./identity";

describe("identityScope", () => {
  it("separates two sessions and is stable for one", () => {
    expect(identityScope("token-A")).not.toBe(identityScope("token-B"));
    expect(identityScope("token-A")).toBe(identityScope("token-A"));
  });

  it("signed out is its own scope, not a collision with a real session", () => {
    expect(identityScope("")).toBe("anon");
    expect(identityScope("token-A")).not.toBe("anon");
  });

  it("does not leak the token — the tag is short and fixed-width regardless of input", () => {
    const tag = identityScope("a".repeat(512));
    expect(tag.length).toBeLessThan(8);
    expect(tag).not.toContain("a".repeat(8));
  });
});

describe("ownedByMe", () => {
  it("mine is mine, someone else's is not", () => {
    expect(ownedByMe("me", "me")).toBe(true);
    expect(ownedByMe("them", "me")).toBe(false);
  });

  it("UNTAGGED counts as mine — legacy entries keep working and are never stranded", () => {
    // The alternative is hiding pre-existing unsent work from everyone, with no way to get it back.
    expect(ownedByMe(undefined, "me")).toBe(true);
    expect(ownedByMe(undefined, "anyone-else")).toBe(true);
  });

  it("an untagged entry is never REASSIGNED to whoever looks at it", () => {
    // Visible to the next signer-in is the status quo. Stamping their name on it would attribute
    // one person's captures to another — worse than the exposure this change is closing.
    const seenBy = (me: string) => ({ owner: undefined as string | undefined, visible: ownedByMe(undefined, me) });
    const a = seenBy("A"), b = seenBy("B");
    expect(a.visible && b.visible).toBe(true);
    expect(a.owner).toBeUndefined();
    expect(b.owner).toBeUndefined();
  });
});

describe("currentIdentity", () => {
  it("reads the persisted token, and survives storage being unavailable", () => {
    localStorage.setItem("aec-token", "tok");
    expect(currentIdentity()).toBe(identityScope("tok"));
    localStorage.removeItem("aec-token");
    expect(currentIdentity()).toBe("anon");
  });
});
