/**
 * Deployment-header regression gate over nginx.conf.
 *
 * Three failure modes this exists to catch, all of which ship silently:
 *
 *   1. **The add_header inheritance trap.** An nginx location with ANY `add_header` of its own
 *      drops ALL server-level ones — so the `location = /index.html` block (which must add
 *      Cache-Control) has to repeat every security header verbatim. A header added at server
 *      level but not in that block is absent from the one response that matters most: the
 *      top-level document. The `.mjs` worker location also defines Cache-Control, so it must
 *      repeat COOP/COEP or geometry loading can stall despite a 200 response.
 *
 *   2. **Worker isolation.** The hashed `.mjs` geometry worker must preserve COOP/COEP.
 *
 *   3. **CSP vs the entry point.** script-src deliberately has no 'unsafe-inline', which means
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

/**
 * Every location block that declares ANY `add_header` of its own must repeat the WHOLE security
 * set — derived from the file, not from a list kept here.
 *
 * nginx inherits `add_header` from the enclosing scope only while the current scope declares none.
 * `location = /index.html` was written knowing that. Three *other* locations were not: `~* \.mjs$`,
 * `/assets/` and `/wasm/` each declare `Cache-Control` for immutable caching, and each therefore
 * silently dropped all seven server-level headers — including `X-Content-Type-Options: nosniff`,
 * from exactly the responses where MIME sniffing matters most: every hashed bundle, every WASM
 * binary, every module worker the app serves.
 *
 * PR #311 found the trap and restored COOP/COEP on the `.mjs` block, which fixed the reported
 * symptom (module workers losing cross-origin isolation, so geometry loading stalls). Its test
 * then encoded the partial state as correct — `Cross-Origin-*` required in three scopes and
 * everything else in two — which would have passed forever with `nosniff` still missing.
 *
 * **A count is the wrong assertion.** It has to be re-tuned every time a location is added, and
 * re-tuning is how a partial fix becomes the specification. This derives the population instead:
 * find the blocks that declare an `add_header`, and require the full set in each. A fourth such
 * location fails the day it is added, not the day someone re-audits.
 */
function locationsDeclaringAddHeader(): { name: string; body: string }[] {
  const out: { name: string; body: string }[] = [];
  const re = /^\s*location\s+([^{]+?)\s*\{/gm;
  for (let m = re.exec(conf); m; m = re.exec(conf)) {
    const open = conf.indexOf("{", m.index);
    let depth = 0, i = open;
    for (; i < conf.length; i++) {
      if (conf[i] === "{") depth++;
      else if (conf[i] === "}" && --depth === 0) break;
    }
    const body = conf.slice(open, i + 1);
    if (/^\s*add_header\s/m.test(body)) out.push({ name: m[1]!.trim(), body });
  }
  return out;
}

describe("nginx security headers", () => {
  const SCOPED = locationsDeclaringAddHeader();

  it("finds the location blocks that opt out of inheritance — otherwise this suite is vacuous", () => {
    expect(SCOPED.map((s) => s.name).sort(), "parser drifted from nginx.conf's syntax")
      .toEqual(["/assets/", "/wasm/", "= /index.html", "~* \\.mjs$"]);
  });

  it.each(SECURITY_HEADERS)("%s is present at server level and in EVERY scoped location", (name) => {
    const missing = SCOPED.filter((s) => !s.body.includes(`add_header ${name} `)).map((s) => s.name);
    expect(missing, `${name} is dropped by ${missing.join(", ")} — that location declares its own ` +
      "add_header, so nginx stops inheriting the server-level set entirely").toEqual([]);
    // one value everywhere, server level included
    expect(new Set(headerLines(name)).size, `${name} differs between scopes`).toBe(1);
    expect(headerLines(name).length, `${name} missing at server level`).toBe(SCOPED.length + 1);
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
