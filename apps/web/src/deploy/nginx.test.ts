/**
 * Deployment-header regression gate over nginx.conf.
 *
 * Two failure modes this exists to catch, both of which ship silently:
 *
 *   1. **The add_header inheritance trap.** An nginx location with ANY `add_header` of its own
 *      drops ALL server-level ones — so the `location = /index.html` block (which must add
 *      Cache-Control) has to repeat every security header verbatim. A header added at server
 *      level but not in that block is absent from the one response that matters most: the
 *      top-level document. This test asserts the two scopes carry an IDENTICAL security set.
 *
 *   2. **CSP vs the entry point.** script-src deliberately has no 'unsafe-inline', which means
 *      an inline <script> in index.html would be blocked by the very policy we ship — a blank
 *      app in production with a green build. The entry point is asserted inline-script-free
 *      here, next to the policy that makes it a requirement.
 *
 * Parsed as text on purpose: the config's meaning IS its text (nginx has no schema to load),
 * and a text assertion fails on exactly the line a reviewer would need to look at.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const conf = readFileSync(resolve(__dirname, "../../nginx.conf"), "utf8");
const indexHtml = readFileSync(resolve(__dirname, "../../index.html"), "utf8");

/** Every security header that must be present in BOTH header scopes (see trap #1 above). */
const SECURITY_HEADERS = [
  "Cross-Origin-Opener-Policy",
  "Cross-Origin-Embedder-Policy",
  "Strict-Transport-Security",
  "X-Content-Type-Options",
  "Referrer-Policy",
  "X-Frame-Options",
  "Content-Security-Policy",
];

function headerLines(name: string): string[] {
  return conf.split("\n")
    .filter((l) => l.trim().startsWith(`add_header ${name}`))
    .map((l) => l.trim());
}

describe("nginx security headers", () => {
  it.each(SECURITY_HEADERS)("%s is set in both scopes with the same value", (name) => {
    const lines = headerLines(name);
    expect(lines.length, `${name} must appear at server level AND in location = /index.html — ` +
      "a location-level add_header drops the inherited set").toBe(2);
    expect(new Set(lines).size, `${name} differs between the two scopes`).toBe(1);
  });

  it("every add_header uses `always` so headers survive error responses", () => {
    for (const l of conf.split("\n").map((s) => s.trim())) {
      if (!l.startsWith("add_header")) continue;
      // Cache-Control on immutable assets is a caching hint, not a security boundary
      if (l.includes('"public, immutable"')) continue;
      expect(l.endsWith("always;"), `missing 'always': ${l}`).toBe(true);
    }
  });
});

describe("Content-Security-Policy directives", () => {
  const csp = headerLines("Content-Security-Policy")[0] ?? "";

  it("script-src is 'self' + wasm only — no inline, no eval, no remote hosts", () => {
    expect(csp).toMatch(/script-src 'self' 'wasm-unsafe-eval'[;"]/);
    const scriptSrc = /script-src ([^;"]*)/.exec(csp)?.[1] ?? "";
    expect(scriptSrc).not.toContain("'unsafe-inline'");
    expect(scriptSrc).not.toContain("'unsafe-eval'");
  });

  it("workers may come from blobs — the geometry workers are spawned that way", () => {
    expect(csp).toContain("worker-src 'self' blob:");
  });

  it("the classic injection side doors are closed", () => {
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
    expect(csp).toContain("frame-ancestors 'self'");
  });

  it("the entry point has no inline script, so the no-'unsafe-inline' policy cannot blank it", () => {
    // <script src=...> is fine; <script> with a body is what the CSP would block.
    const inline = [...indexHtml.matchAll(/<script\b([^>]*)>/gi)]
      .filter(([, attrs]) => !/\bsrc\s*=/.test(attrs ?? ""));
    expect(inline, "inline <script> found in index.html — it would be blocked by our own CSP")
      .toEqual([]);
  });
});
