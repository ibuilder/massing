import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * R24-PERF-BUDGET — every modal is classified: it either reports a `panel_load`, or it is declared
 * synchronous with a reason.
 *
 * ## Why a gate and not just the wiring
 *
 * `panel_load` sat `measurable: false` for fourteen releases. The blocker was never the beacon — it
 * was a **moment**: `modalShell` builds an empty shell and each caller fills it afterwards, so timing
 * the chokepoint records DOM construction and files it as a panel load. `perf_budget.py` refused to
 * flip the flag on that basis, on the grounds that *"a budget reported green against a measurement of
 * the wrong thing is the exact failure this file was written to prevent"*.
 *
 * Wiring the call sites answers that. It also creates a new way to be wrong: a p95 over **whichever
 * panels somebody remembered to wire** is a figure whose population nobody can state — the same
 * objection `perfBeacon.ts` already makes against instrumenting click handlers one at a time. So the
 * population is not left implicit. Every call site is enumerated here and must be accounted for.
 *
 * ## The classification, and why it is not a regex's job
 *
 * Two rules were considered and both are biased:
 *
 *   * **exclude the fast ones** — refused for the same reason the click budget refuses it: "a
 *     percentile over only the suspicious ones is not a percentile".
 *   * **include every modal** — most opens in this app are trivial dialogs built from data already in
 *     hand, so a healthy-looking p95 could be produced entirely by dialogs that never load anything,
 *     no matter how slow the real panels are.
 *
 * So the rule is: **a modal reports if the user waited for data between their click and the panel
 * being usable.** That cannot be read off the call site, because the wait is often in the CALLER —
 * `conceptBudgetView`, `estimateConfidenceView` and `composeExhibit` all fetch before opening a shell
 * that then builds synchronously. Which is why the interval is measured from the click rather than
 * from the shell, and why this list is a human classification a reviewer can argue with.
 *
 * **Two groups here were classified wrongly on the first pass, both by inference from the call
 * site.** `qr.ts` was assumed instant from its name and awaits `QRCode.toCanvas`; three register
 * dialogs were assumed instant because their own bodies contain no `await`, and their callers fetch.
 * Both were caught by reading, neither by a rule. That is the whole argument for this shape.
 */

const SRC = resolve(process.cwd(), "src");

/**
 * Modals that do NOT report, each with the reason. Keyed by `file:enclosingFunction`, because that is
 * the unit a reviewer reasons about — a line number would churn on every edit above it, and the
 * modal's title is not unique (`accountUI.ts` opens two different "Two-factor authentication" dialogs
 * with different classifications).
 *
 * The set may not grow silently: an unrecognised site fails, and so does a key that no longer matches
 * one.
 */
const DECLARED_SYNCHRONOUS: Record<string, string> = {
  "account/accountUI.ts:mfaChallengeModal":
    "the code field and its two buttons, built from arguments. Nothing is fetched before the user types.",
  "account/accountUI.ts:resetModal":
    "two inputs and a button. The reset call happens on submit, which is an action rather than a load.",
  "account/accountUI.ts:passwordModal":
    "two inputs and a button; the change happens on submit, not on open.",
  "main.ts:showFreeImportHelp":
    "static help text and three external links. There is nothing here to wait for.",
  "main.ts:pickModelTemplate":
    "a grid built from the in-module MODEL_TEMPLATES constant, with no request behind it.",
  "main.ts:openProjectBundle":
    "EXCLUDED rather than merely synchronous, and for a different reason: a native FILE CHOOSER sits "
    + "between the user's click and this panel. The interval would be dominated by however long they "
    + "spent browsing for a file — a number about the human, not the app, and one large enough that a "
    + "handful of them would move the p95 further than any real regression.",
  "portal/register/register.ts:columnPicker":
    "checkboxes built from the module's own field list, which is already in memory.",
  "portal/register/register.ts:pasteRows":
    "a textarea and help text. The import preview runs on the NEXT step, not on open.",
  "portal/register/register.ts:signContract":
    "a party select and a name input; signing happens on submit rather than on open.",
  "ui/modal.ts:confirmModal":
    "a message and Confirm/Cancel, built from arguments — the accessible replacement for window.confirm.",
  "ui/modal.ts:promptModal":
    "fields built from the PromptField[] argument; nothing is fetched before the user can type.",
  "ui/prompt.ts:askText":
    "one field and two buttons, built entirely from the options argument.",
  "ui/prompt.ts:askConfirm":
    "a message and two buttons, from arguments — the confirm dialog. Nothing is fetched.",
};

/**
 * `ui/modal.ts` is in this list, and leaving it out was a real hole rather than a tidy exclusion.
 *
 * It DEFINES `modalShell`, so the obvious instinct is to skip it — but it also *calls* it twice, for
 * `confirmModal` and `promptModal`. Excluded, those two modals sat outside a population this file
 * claims to enumerate, and nothing would ever have said so. **A gate's scope is part of its claim.**
 * The definition itself is skipped by line, not by file.
 */
const FILES = [
  "account/accountUI.ts", "connections/connectionsUI.ts", "main.ts",
  "portal/register/register.ts", "reportCenter.ts", "ui/modal.ts", "ui/prompt.ts", "ui/qr.ts",
];

interface Site { file: string; fn: string; line: number; reports: boolean }

/** Every `modalShell(` call, with the function it sits in and whether it destructures `ready`. */
function sites(): Site[] {
  const out: Site[] = [];
  const DECL = /^\s*(?:export\s+)?(?:private\s+|protected\s+|public\s+)?(?:async\s+)?(?:function\s+)?([a-zA-Z_]\w*)\s*(?:<[^>]*>)?\s*\(/;
  const NOT_A_FN = new Set(["if", "for", "while", "switch", "catch", "return", "await"]);
  for (const file of FILES) {
    const lines = readFileSync(resolve(SRC, file), "utf8").split("\n");
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i] ?? "";
      if (!l.includes("modalShell(")) continue;
      if (/^\s*export function modalShell\(/.test(l)) continue;   // the definition, not a call
      // Walk out to the nearest declaration at a SHALLOWER indent. Taking the nearest declaration at
      // any depth would name an inner arrow function, which is not a unit anyone classifies.
      const indent = l.search(/\S/);
      let fn = "?";
      let fnStart = -1;
      for (let j = i; j >= 0; j--) {
        const cand = lines[j] ?? "";
        const ci = cand.search(/\S/);
        if (ci < 0 || ci >= indent) continue;
        const m = DECL.exec(cand);
        if (m?.[1] && !NOT_A_FN.has(m[1])) { fn = m[1]; fnStart = j; break; }
      }
      // The CALL, not the destructure.
      //
      // This asked only whether the `modalShell(` line mentioned `ready`. While writing the release a
      // botched edit removed two `ready()` calls and left their destructures in place — two panels
      // stopped reporting and this gate stayed green. **A gate that reads the declaration and not the
      // use is satisfied by dead wiring**, the same shape as a beacon installed and never fired.
      const fnIndent = fnStart >= 0 ? (lines[fnStart] ?? "").search(/\S/) : 0;
      let fnEnd = lines.length;
      for (let j = fnStart + 1; j < lines.length; j++) {
        const cand = lines[j] ?? "";
        if (cand.search(/\S/) === fnIndent && cand.trim().startsWith("}")) { fnEnd = j; break; }
      }
      const body = lines.slice(fnStart < 0 ? i : fnStart, fnEnd).join("\n");
      const calls = /\bready\s*\(\s*\)|finally\(\s*ready\s*\)/.test(body);
      out.push({ file, fn, line: i + 1, reports: /\bready\b/.test(l) && calls });
    }
  }
  return out;
}

const SITES = sites();

describe("panel_load — every modal is classified, so the percentile's population can be stated", () => {
  it("found every call site — a shrunken list would make each check below vacuous", () => {
    expect(SITES.length, `parsed ${SITES.length} modalShell call sites`).toBeGreaterThanOrEqual(31);
    expect(SITES.filter((s) => s.fn === "?"),
      "a site whose enclosing function cannot be identified cannot be classified either").toEqual([]);
  });

  it("EVERY modal either reports a panel_load or is declared synchronous with a reason", () => {
    const unclassified = SITES
      .filter((s) => !s.reports && !DECLARED_SYNCHRONOUS[`${s.file}:${s.fn}`])
      .map((s) => `${s.file}:${s.line} ${s.fn}() neither reports nor is declared synchronous`);
    expect(unclassified,
      "a new modal is a new member of the panel_load population. Destructure `ready` from modalShell "
      + "and call it when the panel is USABLE, or add it to DECLARED_SYNCHRONOUS with the reason it "
      + "has nothing to wait for. Leaving it out silently makes the p95 a figure over an unstated set.")
      .toEqual([]);
  });

  /**
   * The other direction, which is what stops the list rotting into a dumping ground. A declaration
   * whose call site is gone reads as a considered exclusion and is nothing of the kind; a declaration
   * on a site that now reports is simply contradictory.
   */
  it("names no declaration that has no matching site, or whose site now reports", () => {
    const keys = new Set(SITES.filter((s) => !s.reports).map((s) => `${s.file}:${s.fn}`));
    const stale = Object.keys(DECLARED_SYNCHRONOUS).filter((k) => !keys.has(k));
    expect(stale, "delete it — a declaration about a modal that is gone, or that now reports, is a "
      + "false statement sitting where the next reader will trust it").toEqual([]);
  });

  it("every declaration carries a real reason, not a placeholder", () => {
    for (const [k, why] of Object.entries(DECLARED_SYNCHRONOUS)) {
      expect(why.length, `${k} needs a reason worth reading`).toBeGreaterThan(40);
    }
  });

  /**
   * The anti-vacuity twin. Every check above is satisfied by declaring ALL of them synchronous — a
   * green gate over a budget with no producer at all, which is exactly the `no_observations` outcome
   * `perf_budget.py` warns reads like an outage rather than the stated gap it is.
   */
  it("A SUBSTANTIAL SHARE of modals actually report — else the budget has no producer", () => {
    const reporting = SITES.filter((s) => s.reports).length;
    expect(reporting, `only ${reporting} of ${SITES.length} modals report a panel_load`)
      .toBeGreaterThanOrEqual(14);
  });
});
