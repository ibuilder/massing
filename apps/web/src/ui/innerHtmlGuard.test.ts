/**
 * SEC — a ratchet on unescaped `innerHTML` interpolation.
 *
 * The 2026-07 audit found user-controlled text reaching `innerHTML` unescaped: a submittal title
 * lifted from an UPLOADED document, a `trade` parameter echoed straight back, an upload filename, and
 * server error strings (a 422 detail can quote the caller's own input). Each was one missed `esc()`
 * away from stored XSS, and the surrounding code in those very functions already used `textContent` —
 * so the defect was inconsistency, not ignorance.
 *
 * Escaping every remaining site at once is not safe to do blind: many interpolations are literals
 * passed to a helper (`stat("Budget", n)`) and a few deliberately carry markup (rail icons). So this
 * does not demand zero — it demands that the number never grows.
 *
 * **Improving the code must never fail the build.** An earlier draft also failed when a file dropped
 * BELOW its baseline, to keep the numbers honest. That punished the exact behaviour it wanted: a
 * contributor who escaped one interpolation got a red build, and on this repo an autonomous agent
 * commits straight to main and would trip it without knowing this file exists. The rule is now
 * one-directional — down is always fine, up is never fine.
 *
 * CLAUDE.md: "If a rule matters, write it as a test — anything held only as prose will drift."
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

/** Escapers that make an interpolation safe. Tested per `${…}`, never per line. */
const SAFE = /\b(esc|escapeHtml|sanitizeSvg|safeUrl)\s*\(/;
/** Identifiers that carry free text a user or a third-party document controls. */
const HOT =
  /(name|title|desc|description|message|label|file|filename|user|author|comment|note|text|trade|source|summary|subject|company|vendor|email|address|code|mark|tag|reason|detail|question|answer|value|key|spec_section|type)\b/i;
/** Structurally safe to interpolate: loop counters, lengths, numbers. */
const COLD = /^(i|idx|j|n|k|len|count|total|pct|num|\d+)$/i;

/**
 * Known unescaped interpolations, per file. Every entry is a place a future reader should check
 * rather than trust. Lower a number freely; raising one needs a reason.
 */
const BASELINE: Record<string, number> = {
  "main.ts": 2,
  "portal/panels/aiassist.ts": 3,
  "portal/panels/analytics.ts": 6,
  "portal/panels/budget.ts": 4,
  "portal/panels/design.ts": 2,
  "portal/panels/evm.ts": 1,
  "portal/panels/operations.ts": 5,
  "portal/panels/resourceLoading.ts": 1,
  "portal/panels/schedule.ts": 6,
  "portal/panels/standards.ts": 8,
  "portal/panels/traceability.ts": 1,
  "portal/panels/wip.ts": 1,
  "portal/portal.ts": 14,
  "proforma/proforma.ts": 16,
  "reportCenter.ts": 4,
  "studio/nodeEditor.ts": 1,
  "ui/onboarding.ts": 1,
  "ui/result.ts": 3,
  "viewer/app.ts": 6,
  "viewer/draft/draftPanel.ts": 1,
};

const BASELINE_TOTAL = Object.values(BASELINE).reduce((a, b) => a + b, 0);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p);
  }
  return out;
}

/**
 * Count EVERY hot, unescaped interpolation pushed into innerHTML — not one per line.
 *
 * An earlier draft stopped at the first hot match on a line, which meant adding a second unescaped
 * value to an already-counted line was invisible: `` `<b>${d.label}</b>` `` growing into
 * `` `<b>${d.label}</b><i>${d.author}</i>` `` kept the count at 1. That is exactly the shape of edit
 * that grows an existing render function.
 */
function hotSinks(src: string): number {
  let n = 0;
  for (const line of src.split("\n")) {
    if (!line.includes("innerHTML") || !line.includes("${")) continue;
    for (const m of line.matchAll(/\$\{([^}]*)\}/g)) {
      const expr = (m[1] ?? "").trim();
      if (SAFE.test(expr) || COLD.test(expr)) continue;
      if (HOT.test(expr)) n++;
    }
  }
  return n;
}

const ADVICE =
  "Wrap the interpolated value in esc()/escapeHtml() — an uploaded document's title, a filename, " +
  "or a 422 detail quoting the caller's own input is attacker-controlled text.";

describe("innerHTML escaping ratchet", () => {
  const actual: Record<string, number> = {};
  for (const file of walk(SRC)) {
    const n = hotSinks(readFileSync(file, "utf8"));
    if (n) actual[relative(SRC, file).replace(/\\/g, "/")] = n;
  }
  const total = Object.values(actual).reduce((a, b) => a + b, 0);

  it("adds no unescaped innerHTML interpolation to an already-known file", () => {
    // Only files the baseline names. A file that was renamed away simply reports 0 here, which can
    // never fail — the total below is what keeps a rename from laundering a new sink.
    const regressions: string[] = [];
    for (const [file, allowed] of Object.entries(BASELINE)) {
      const n = actual[file] ?? 0;
      if (n > allowed) regressions.push(`${file}: ${n} unescaped, baseline ${allowed}. ${ADVICE}`);
    }
    expect(regressions).toEqual([]);
  });

  it("does not grow the repo-wide count", () => {
    // Rename-proof and improvement-friendly: moving a file keeps the total flat, escaping anything
    // lowers it, and only genuinely NEW unescaped text can push it up. This is also the gate that
    // covers files the baseline has never heard of.
    const newcomers = Object.keys(actual)
      .filter((f) => !(f in BASELINE))
      .map((f) => `${f} (${actual[f]})`);
    expect(
      `${total} unescaped interpolation(s)` +
        (total > BASELINE_TOTAL && newcomers.length ? ` — not baselined: ${newcomers.join(", ")}` : ""),
    ).toBe(
      total > BASELINE_TOTAL
        ? `at most ${BASELINE_TOTAL}. ${ADVICE}`
        : `${total} unescaped interpolation(s)`,
    );
  });
});
