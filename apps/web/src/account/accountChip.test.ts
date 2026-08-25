import { beforeEach, describe, expect, it } from "vitest";

import { avatarEl, initialsFor, renderChip } from "./accountChip";

/**
 * The identity chip — "signed in as", with the massing.cloud (WordPress) avatar.
 *
 * The interesting cases are all about the **absence** of a cloud profile, because that is the normal
 * state for password and direct-IdP accounts and it must never read as an error. A missing
 * `avatarUrl` has to produce a real element, and a *broken* one has to degrade to the same element
 * rather than leaving the browser's broken-image glyph on the most-looked-at control in the shell.
 */
describe("initialsFor", () => {
  it("takes one glyph from each of two name parts", () => {
    expect(initialsFor("Ada Lovelace")).toBe("AL");
  });

  it("splits an email local-part on separators, ignoring the domain", () => {
    // "ada.lovelace@example.com" must not become "AD" — and must never reach into the domain.
    expect(initialsFor("ada.lovelace@example.com")).toBe("AL");
    expect(initialsFor("ada@example.com")).toBe("AD");
  });

  it("falls back to the first two characters for a single-word name", () => {
    expect(initialsFor("ada")).toBe("AD");
    expect(initialsFor("x")).toBe("X");
  });

  it("never returns an empty string, so the disc is never blank", () => {
    expect(initialsFor("")).toBe("?");
    expect(initialsFor("   ")).toBe("?");
    // A name that is *only* separators still has to yield something paintable.
    expect(initialsFor("@example.com").length).toBeGreaterThan(0);
  });

  it("is at most two glyphs", () => {
    for (const n of ["Ada Lovelace", "ada.lovelace@example.com", "Wolfgang Amadeus Mozart", "x"]) {
      expect(initialsFor(n).length).toBeLessThanOrEqual(2);
    }
  });
});

describe("avatarEl", () => {
  it("renders an <img> when the cloud supplied an avatar", () => {
    const el = avatarEl({ username: "ada@example.com", avatarUrl: "https://cloud/a.jpg" });
    expect(el.tagName).toBe("IMG");
    expect((el as HTMLImageElement).src).toBe("https://cloud/a.jpg");
    // Decorative: the accessible name is on the button, not repeated here.
    expect((el as HTMLImageElement).alt).toBe("");
    // Never leak the app's URL to the avatar host as a referrer.
    expect((el as HTMLImageElement).referrerPolicy).toBe("no-referrer");
  });

  it("refuses a dangerous scheme and falls back to the disc", () => {
    // `avatar_url` is external data — it comes from massing.cloud's userinfo, which reflects
    // whatever avatar host the account uses. A non-http(s) scheme must never reach `src`.
    for (const bad of ["javascript:alert(1)", "data:text/html,<script>", "vbscript:x", "file:///etc"]) {
      const el = avatarEl({ username: "ada@example.com", displayName: "Ada Lovelace", avatarUrl: bad });
      expect(el.tagName, `${bad} must not become an <img>`).toBe("SPAN");
      expect(el.textContent).toBe("AL");
    }
  });

  it("still accepts an ordinary https avatar", () => {
    const el = avatarEl({ username: "ada@example.com", avatarUrl: "https://www.massing.cloud/a.jpg" });
    expect(el.tagName).toBe("IMG");
  });

  it("renders an initials disc when there is no avatar", () => {
    const el = avatarEl({ username: "ada@example.com", displayName: "Ada Lovelace" });
    expect(el.tagName).toBe("SPAN");
    expect(el.textContent).toBe("AL");
    expect(el.getAttribute("aria-hidden")).toBe("true");
  });

  it("swaps a broken avatar for the disc instead of showing a broken image", () => {
    const el = avatarEl({ username: "ada@example.com", displayName: "Ada Lovelace",
      avatarUrl: "https://cloud/gone.jpg" }) as HTMLImageElement;
    const host = document.createElement("div");
    host.append(el);
    el.onerror?.(new Event("error"));
    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toBe("AL");
  });

  it("gives the same person the same fallback colour across renders", () => {
    // Read the raw style attribute, NOT `el.style.background`: happy-dom does not reflect the
    // `background` shorthand back, so both sides would be "" and the equality assertion below
    // would pass no matter what the code did.
    const hue = (el: HTMLElement) => {
      const css = el.getAttribute("style") || "";
      const m = /hsl\((\d+)/.exec(css);
      expect(m, `expected an hsl() background in: ${css}`).not.toBeNull();
      return m![1];
    };
    expect(hue(avatarEl({ username: "ada@example.com" })))
      .toBe(hue(avatarEl({ username: "ada@example.com" })));
    expect(hue(avatarEl({ username: "ada@example.com" })))
      .not.toBe(hue(avatarEl({ username: "bob@example.com" })));
  });
});

describe("renderChip", () => {
  let btn: HTMLButtonElement;
  beforeEach(() => { btn = document.createElement("button"); });

  it("shows the display name, not the raw username, when the cloud gave one", () => {
    renderChip(btn, { username: "ada@example.com", displayName: "Ada Lovelace" });
    expect(btn.textContent).toContain("Ada Lovelace");
    expect(btn.getAttribute("aria-label")).toBe("Account: Ada Lovelace");
  });

  it("falls back to the username when there is no display name", () => {
    renderChip(btn, { username: "ada@example.com" });
    expect(btn.textContent).toContain("ada@example.com");
    expect(btn.getAttribute("aria-label")).toBe("Account: ada@example.com");
  });

  it("badges an admin, and does not badge a regular user", () => {
    renderChip(btn, { username: "ada@example.com", isAdmin: true });
    expect(btn.textContent).toContain("admin");
    const plain = document.createElement("button");
    renderChip(plain, { username: "bob@example.com", isAdmin: false });
    expect(plain.textContent).not.toContain("admin");
  });

  it("names the plan in the tooltip when one is known", () => {
    renderChip(btn, { username: "ada@example.com", displayName: "Ada", tierLabel: "Commercial" });
    expect(btn.title).toBe("Ada — Commercial plan");
  });

  it("is idempotent — re-rendering does not stack a second avatar or chevron", () => {
    const id = { username: "ada@example.com", displayName: "Ada Lovelace", isAdmin: true };
    renderChip(btn, id);
    const styleAfterFirst = btn.getAttribute("style");
    renderChip(btn, id);
    expect(btn.querySelectorAll("span").length).toBe(4);   // disc + label + badge + chevron
    expect(btn.textContent!.match(/Ada Lovelace/g)!.length).toBe(1);
    // ...and the inline style does not grow on every render either.
    expect(btn.getAttribute("style")).toBe(styleAfterFirst);
  });
});
