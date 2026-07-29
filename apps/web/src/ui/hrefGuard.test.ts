/**
 * SEC — a ZERO-baseline gate on URL attributes assigned from external data.
 *
 * `href` and `src` are a sink class every other guard in this repo misses, for structural reasons
 * rather than oversight:
 *
 * - `textContent` does not apply — an attribute is not a text node.
 * - `escapeHtml()` does not help — `javascript:alert(1)` has nothing to escape, and escaping a DOM
 *   *property* actively corrupts it (`?v=2&inline=true` → `?v=2&amp;inline=true`, a broken link that
 *   still looks defended).
 * - `innerHtmlGuard` watches `.innerHTML` interpolation only, by design.
 *
 * Found in `ui/jobTray.ts`: a plugin-supplied job rendered its label through `textContent` —
 * correctly — beside an anchor whose `href` came from a caller-supplied function. Safe, but safe *by
 * argument*: the invariant holding it up was "that function builds a URL rather than passing one
 * through", and nothing enforced it. `ui/update.ts` was the same shape with a real external source
 * (`html_url` off the GitHub releases API).
 *
 * **The scope is deliberately narrow so the zero can be honest.** A line-local regex cannot do
 * dataflow: `img.src = mediaSrc` is safe because `mediaSrc` came from `safeMediaUrl()` one line
 * above, and no pattern match can see that. A first draft flagged eleven such sites, every one of
 * them safe — and a gate that cries wolf eleven times is one people learn to switch off, which is
 * worse than no gate at all.
 *
 * So this matches only the shape that carries the risk: **a URL field read off a data object**
 * (`info.url`, `job.artifact_url`, `d.html_url`) assigned straight to an attribute. That is the shape
 * of every real instance — a value that arrived from a server, a plugin, or a third-party API. A bare
 * local identifier is left alone, because its provenance is visible in the same function. Narrow and
 * true beats broad and ignored.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

/** `x.href = …`, `x.src = …`, `setAttribute("href"|"src"|"xlink:href", …)`. */
const SINK =
  /(?:\.(?:href|src)\s*=(?!=)|setAttribute\(\s*["'](?:href|src|xlink:href)["']\s*,)\s*([^;\n]*)/g;

/**
 * A URL read off a data object — `info.url`, `job.artifact_url`, `att.fileUrl`, `d.html_url`.
 * This is the provenance that matters: the value came from somewhere this code did not write.
 */
// NB: no leading word-boundary — camelCase `fileUrl` has none before `Url`, and that is the
// commonest field name of all. The trailing one still stops `linkedThing` matching `link`.
const FIELD_READ = /^[A-Za-z_$][\w$]*\.[\w$.]*(url|href|src|link|uri)\b/i;

/**
 * Right-hand sides that cannot carry an attacker-chosen scheme even when they are field reads:
 * the scheme-allowlist helpers, `URL.createObjectURL` (always `blob:` for an object we made), and
 * the `api.*Url(…)` / `.url(…)` builders that put a path onto a fixed origin.
 */
const SAFE_RHS = [
  /^["'`]/,
  /\bURL\.createObjectURL\s*\(/,
  /\bsafeHref\s*\(/,
  /\bsafeUrl\s*\(/,
  /\bsafeMediaUrl\s*\(/,
  /\.url\s*\(/,
  /\b\w*[Uu]rl\s*\(/,
];

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p);
  }
  return out;
}

function unguardedSinks(src: string, file: string): string[] {
  const bad: string[] = [];
  src.split("\n").forEach((line, i) => {
    const t = line.trimStart();
    if (t.startsWith("*") || t.startsWith("//")) return;
    for (const m of line.matchAll(SINK)) {
      const rhs = (m[1] ?? "").trim();
      if (!rhs) continue;
      if (SAFE_RHS.some((re) => re.test(rhs))) continue;
      if (!FIELD_READ.test(rhs)) continue; // local identifier — provenance visible in-function
      bad.push(`${file}:${i + 1} — ${rhs.slice(0, 70)}`);
    }
  });
  return bad;
}

describe("href/src scheme gate", () => {
  it("assigns no URL attribute from an unguarded external field", () => {
    const bad: string[] = [];
    for (const f of walk(SRC)) {
      bad.push(...unguardedSinks(readFileSync(f, "utf8"), relative(SRC, f).replace(/\\/g, "/")));
    }
    // Zero, not a baseline. If this fails, wrap the value in `safeHref()` from ui/feedback — an
    // attribute cannot be defended by escaping, and `javascript:` has nothing to escape.
    expect(bad).toEqual([]);
  });

  it("fires on an external field read, and not on the shapes the codebase legitimately uses", () => {
    for (const bad of [
      "a.href = job.artifact_url;",
      "dl.href = info.url;",
      "img.src = att.fileUrl;",
      'el.setAttribute("href", d.html_url);',
    ]) {
      expect(unguardedSinks(bad, "probe.ts").length).toBe(1);
    }
    for (const ok of [
      "a.href = safeHref(opts.artifactUrl(j));",
      "a.href = URL.createObjectURL(blob);",
      "pdf.href = ctx.host.api.url(`/projects/x.pdf`);",
      "btn.href = api.accountingIifUrl(pid);",
      'img.src = "/static/logo.png";',
      "img.src = mediaSrc;", // local: guarded on the line above
      "a.href = url;", // local: createObjectURL above
      "dl.href = safeHref(info.url);", // the fix this gate asks for
    ]) {
      expect(unguardedSinks(ok, "probe.ts")).toEqual([]);
    }
  });
});
