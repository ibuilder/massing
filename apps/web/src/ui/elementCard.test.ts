import { describe, expect, it, vi } from "vitest";

import type { LifecycleStrip } from "../api/types";
import { buildIdentityLine, mountElementCard, renderElementCard, shortGuid } from "./elementCard";

/**
 * R24-ELEMENT-CARD ②.
 *
 * The card's job is to make one claim visible — that geometry, cost, schedule and field verification
 * share a key. Its dangerous failure is therefore not an ugly card but a **confident** one: a strip
 * rendered when nothing was asked, or a key shown truncated in a way that cannot be recovered.
 */

/**
 * A complete fixture, with **no `as` cast**.
 *
 * The first version of this omitted `reached`, `done_count`, `unknown_count`, `next` and
 * `inconsistencies` and papered over it with `as LifecycleStrip`. It compiled, and then blew up at
 * runtime on `data.inconsistencies` — because the cast is an assertion that the shape is right, and
 * asserting it does not make it so. A fixture that lies about its type is a test proving something
 * about a payload the server never sends.
 */
const STRIP = (over: Partial<LifecycleStrip> = {}): LifecycleStrip => ({
  guid: "1kP9xAbCdEf7Qa",
  states: [
    { key: "designed", status: "yes" },
    { key: "checked", status: "unknown" },
    { key: "priced", status: "yes" },
    { key: "scheduled", status: "none" },
    { key: "installed", status: "unknown" },
    { key: "verified", status: "unknown" },
  ] as LifecycleStrip["states"],
  reached: "designed",
  done_count: 2,
  unknown_count: 3,
  next: { key: "checked", advance: null },
  inconsistencies: [],
  ...over,
});

describe("the key is shortened for the eye, never for the clipboard", () => {
  it("truncates in the middle so both ends stay recognisable", () => {
    expect(shortGuid("1kP9xAbCdEf7Qa")).toBe("1kP9x…7Qa");
  });

  it("leaves a short id alone", () => {
    expect(shortGuid("abc123")).toBe("abc123");
    expect(shortGuid("")).toBe("");
  });

  it("keeps the FULL id in the DOM, not just the visible fragment", () => {
    const line = buildIdentityLine("1kP9xAbCdEf7Qa", "Slab — 200 PT");
    const key = line.querySelector<HTMLElement>("[title]")!;
    // The visible text is abbreviated; the recoverable value is not. A GlobalId a user cannot copy
    // is the one thing this card exists to hand them.
    expect(key.textContent).toBe("1kP9x…7Qa");
    expect(key.title).toBe("1kP9xAbCdEf7Qa");
  });

  it("renders a server-supplied label as text, never as markup", () => {
    const line = buildIdentityLine("g1", "<img src=x onerror=alert(1)>");
    expect(line.querySelector("img")).toBeNull();
    expect(line.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("works with no label at all", () => {
    expect(buildIdentityLine("g1").textContent).toContain("g1");
  });
});

describe("an unasked lifecycle renders NO strip, not an empty one", () => {
  it("omits the strip entirely when there is none", () => {
    const host = document.createElement("div");
    renderElementCard(host, { guid: "g1", label: "Wall", strip: null });
    // Six blank cells would claim six things were checked and none passed — a different and worse
    // statement than "nobody asked". Same rule the strip applies to `unknown` vs `none`.
    expect(host.querySelector(".lc-strip, .lifecycle-strip")).toBeNull();
    expect(host.textContent).toContain("Wall");
  });

  it("renders the strip when there is one", () => {
    const host = document.createElement("div");
    renderElementCard(host, { guid: "1kP9xAbCdEf7Qa", label: "Slab", strip: STRIP() });
    expect(host.children.length).toBe(2);          // identity line + strip
    expect(host.textContent).toMatch(/design/i);
  });

  it("replaces its contents rather than appending on re-render", () => {
    const host = document.createElement("div");
    renderElementCard(host, { guid: "g1", strip: STRIP() });
    renderElementCard(host, { guid: "g1", strip: STRIP() });
    expect(host.children.length).toBe(2);
  });
});

describe("a failed lookup degrades to the key, and never takes the host panel with it", () => {
  it("still renders the identity line when the request throws", async () => {
    const host = document.createElement("div");
    const api = { elementLifecycle: vi.fn().mockRejectedValue(new Error("500")) };
    await mountElementCard(host, api, "p1", "1kP9xAbCdEf7Qa", "Slab");
    // A cost trace must not lose its table because one lifecycle request failed.
    expect(host.textContent).toContain("1kP9x…7Qa");
    expect(host.textContent).toContain("Slab");
    expect(host.children.length).toBe(1);          // identity only — no fabricated strip
  });

  it("renders the strip on success", async () => {
    const host = document.createElement("div");
    const api = { elementLifecycle: vi.fn().mockResolvedValue(STRIP()) };
    await mountElementCard(host, api, "p1", "1kP9xAbCdEf7Qa");
    expect(api.elementLifecycle).toHaveBeenCalledWith("p1", "1kP9xAbCdEf7Qa");
    expect(host.children.length).toBe(2);
  });
});
