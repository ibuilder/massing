/**
 * SEC — a ratchet on unescaped `innerHTML` interpolation.
 *
 * The 2026-07 audit found user-controlled text reaching `innerHTML` unescaped: a submittal title
 * lifted from an UPLOADED document, a `trade` parameter echoed straight back, an upload filename,
 * and server error strings (a 422 detail can quote the caller's own input). Each was one missed
 * `esc()` away from stored XSS, and the surrounding code in those very functions already used
 * `textContent` — so the defect was inconsistency, not ignorance.
 *
 * Escaping every site at once is not possible to do safely: many interpolations are literals passed
 * to a helper (`stat("Budget", n)`) and a few deliberately carry markup (rail icons), so blanket
 * escaping would be churn at best and broken UI at worst. What IS enforceable is that the count never
 * grows. New code must escape, and any file that drops below its baseline should tighten the baseline
 * on the way past — the number only ever goes down.
 *
 * CLAUDE.md: "If a rule matters, write it as a test — anything held only as prose will drift."
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

/** Escapers that make an interpolation safe. */
const SAFE = /\b(esc|escapeHtml|sanitizeSvg|safeUrl)\s*\(/;
/** Identifiers that carry free text a user or a third-party document controls. */
const HOT =
  /(name|title|desc|description|message|label|file|filename|user|author|comment|note|text|trade|source|summary|subject|company|vendor|email|address|code|mark|tag|reason|detail|question|answer|value|key|spec_section|type)\b/i;
/** Structurally safe to interpolate: loop counters, lengths, numbers. */
const COLD = /^(i|idx|j|n|k|len|count|total|pct|num|\d+)$/i;

/**
 * Known unescaped sinks, per file. Every entry is a place a future reader should check rather than
 * trust. Lower a number when you escape one; never raise one.
 */
const BASELINE: Record<string, number> = {
  "main.ts": 1,
  "portal/panels/aiassist.ts": 3,
  "portal/panels/analytics.ts": 6,
  "portal/panels/budget.ts": 3,
  "portal/panels/design.ts": 1,
  "portal/panels/evm.ts": 1,
  "portal/panels/operations.ts": 3,
  "portal/panels/resourceLoading.ts": 1,
  "portal/panels/schedule.ts": 7,
  "portal/panels/standards.ts": 5,
  "portal/panels/traceability.ts": 1,
  "portal/panels/wip.ts": 1,
  "portal/portal.ts": 13,
  "proforma/proforma.ts": 16,
  "reportCenter.ts": 1,
  "studio/nodeEditor.ts": 1,
  "ui/onboarding.ts": 1,
  "ui/result.ts": 2,
  "viewer/app.ts": 4,
  "viewer/draft/draftPanel.ts": 1,
};

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p);
  }
  return out;
}

/** Count lines in `src` that push a hot, unescaped interpolation into innerHTML. */
function hotSinks(src: string): number {
  let n = 0;
  for (const line of src.split("\n")) {
    if (!line.includes("innerHTML") || !line.includes("${")) continue;
    for (const m of line.matchAll(/\$\{([^}]*)\}/g)) {
      const expr = (m[1] ?? "").trim();
      if (SAFE.test(expr) || COLD.test(expr)) continue;
      if (HOT.test(expr)) { n++; break; }
    }
  }
  return n;
}

describe("innerHTML escaping ratchet", () => {
  const actual: Record<string, number> = {};
  for (const file of walk(SRC)) {
    const n = hotSinks(readFileSync(file, "utf8"));
    if (n) actual[relative(SRC, file).replace(/\\/g, "/")] = n;
  }

  it("introduces no NEW unescaped innerHTML interpolation", () => {
    const regressions: string[] = [];
    for (const [file, n] of Object.entries(actual)) {
      const allowed = BASELINE[file] ?? 0;
      if (n > allowed) {
        regressions.push(
          `${file}: ${n} unescaped hot interpolation(s), baseline ${allowed}. ` +
            `Wrap the interpolated value in esc()/escapeHtml() — a 422 detail or an uploaded ` +
            `document's title is attacker-controlled text.`,
        );
      }
    }
    expect(regressions).toEqual([]);
  });

  it("keeps the baseline honest — a file that improved must tighten its number", () => {
    const stale: string[] = [];
    for (const [file, allowed] of Object.entries(BASELINE)) {
      const n = actual[file] ?? 0;
      if (n < allowed) {
        stale.push(`${file}: now ${n}, baseline still ${allowed} — lower it to ${n}.`);
      }
    }
    expect(stale).toEqual([]);
  });
});
