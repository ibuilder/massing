import type { ApiClient } from "../../api/client";
import { escapeHtml as esc, withLoading } from "../../ui/feedback";
import { kvTable, resultNote, showResult } from "../../ui/result";
import type { LayerManager } from "../../tools/layers";

/**
 * CODE-READY-DARK — does the model carry the data a plan review needs, and **which rules were not
 * asked at all**.
 *
 * `/projects/{pid}/elements/code-check` had no client caller. It is the presence-only half of the
 * code pre-check — its own router docstring calls `codecheck_egress` *"the depth layer above the
 * presence-only /elements/code-check"* — and the two belong beside each other, which is why this
 * lands in the same section as Occupancy & egress rather than in one of its own.
 *
 * ## The headline excludes the rules it could not run, and says nothing about having done so
 *
 * Six rules ship: egress door width, wall fire rating, space area, space occupancy classification,
 * egress stairs, and element typing. A rule whose `applies` class is absent from the model gets
 * `status: "n/a"` and is then **filtered out of the summary** — `rules` is `len(checked_rules)`,
 * and `checked`, `passed` and `readiness_pct` sum over that filtered list. So a model with no
 * `IfcSpace` authored — the ordinary state of an early massing — reports a readiness percentage
 * that silently omits **both** occupant-load rules, which are the two a plan review actually turns
 * on. `checks` carries all six; the numbers describe four.
 *
 * That is this session's recurring shape with the coverage spread across the rows instead of
 * counted in a field: there is no `skipped` to render, so the consumer has to derive it. It is
 * derived from `checks` here — the array the screen shows — rather than from `rules`, and the
 * server's own filter expression is pinned in the test, because a change there would leave every
 * fixture green.
 *
 * ## The isolate set is a page and the count is a total
 *
 * `fail_guids` is capped at 5,000 per rule and again across rules, while `failed` is the true
 * count. Isolating the capped list while printing the total is TRUNC-COUNTED, so a rule whose
 * failures exceed the cap says which it is handing you.
 *
 * Neither number is a code finding: the route answers whether the DATA is there, not whether the
 * building complies, and that sentence travels with the result.
 */
export type CodeReadiness = Awaited<ReturnType<ApiClient["codeCheck"]>>;
type Check = CodeReadiness["checks"][number];

/** The server's cap on a returned guid list, pinned in the test against `properties.py`. */
export const GUID_CAP = 5000;

export interface ReadinessScope {
  /** Rules with at least one subject element — the ones the percentage is about. */
  ran: number;
  /** Rules with no subject element, which the server's own numbers leave out. */
  skipped: number;
  total: number;
  failedRules: number;
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * The headline, over the rules that RAN, with the ones that did not named.
 *
 * Plain text in two parts, escaped by the caller — the shape CODE-ADOPT-DARK had to learn from
 * `apps/web/src/ui/innerHtmlGuard.test.ts`, since a rule's `applies` class is server text.
 */
export function readinessScope(r: CodeReadiness): ReadinessScope {
  const total = r.checks.length;
  const na = r.checks.filter((c) => c.status === "n/a");
  const skipped = na.length;
  const ran = total - skipped;
  const failedRules = r.checks.filter((c) => c.status === "fail").length;
  if (!ran) {
    return {
      ran, skipped, total, failedRules, tone: "",
      headline: "No rule could be checked",
      detail: `none of the ${total} rules has a subject element in this model, so the `
        + "percentage is about nothing. Author the model, then re-run.",
    };
  }
  const pct = `${r.readiness_pct}% of ${r.checked} element check(s) carry the data`;
  if (skipped) {
    return {
      ran, skipped, total, failedRules,
      tone: failedRules ? "bad" : "warn",
      headline: `${ran} of ${total} rules checked — ${pct}`,
      detail: `${skipped} rule(s) were NOT checked because this model has no `
        + `${na.map((c) => c.applies).join(", ")}: ${na.map((c) => c.label).join("; ")}. `
        + "The percentage excludes them entirely.",
    };
  }
  return {
    ran, skipped, total, failedRules,
    tone: failedRules ? "bad" : "ok",
    headline: `All ${total} rules checked — ${pct}`,
    detail: failedRules
      ? `${failedRules} rule(s) have elements missing the data a review needs.`
      : "every rule has a subject and every subject carries the data.",
  };
}

/** One row per rule — including the ones that did not run, which is the whole point. */
export function readinessRows(r: CodeReadiness): { k: string; v: string; strong?: boolean }[] {
  return r.checks.map((c) => ({
    k: `${c.label} (${c.code})`,
    v: c.status === "n/a"
      ? `not checked — no ${c.applies} in this model`
      : `${c.passed}/${c.checked} carry it`
        + (c.failed ? ` · ${c.failed} missing` : "")
        + (c.below_min ? ` · ${c.below_min} below the minimum` : ""),
    strong: c.status === "fail",
  }));
}

/**
 * What the isolate button is actually about to select, when that is not what the count says.
 *
 * `null` when the list is the whole set — the ordinary case — so the note appears only where it
 * changes what the user is looking at.
 */
export function isolateNote(c: Pick<Check, "failed" | "fail_guids" | "label">): string | null {
  const shown = c.fail_guids.length;
  if (c.failed <= shown) return null;
  return `${c.label}: isolating the first ${shown} of ${c.failed} failing element(s) — the server `
    + `caps a returned list at ${GUID_CAP}, so the 3D selection is a page, not the finding.`;
}

export interface CodeReadinessDeps {
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  pid: string;
  container: HTMLElement;
  layerMgr: LayerManager;
  toast: (msg: string, kind?: "info" | "success" | "error") => void;
}

/**
 * Named `*Button` and inlined into its caller's append, because `sectionButtonsWired.test.ts`
 * derives its population from that convention and a third spelling sits outside it — the one
 * mutation that survived MACRO-DARK's first pass.
 */
export function codeReadinessButton(d: CodeReadinessDeps): HTMLButtonElement {
  const btn = d.toolBtn2("📋 Code data-readiness (plan review)", () =>
    withLoading(d.container, "Checking the data a plan review needs", async () => {
      let r: CodeReadiness;
      try { r = await d.api.codeCheck(d.pid); }
      catch (e) {
        d.toast(`Needs a loaded model with a properties index — ${(e as Error).message}`, "error");
        return;
      }
      const scope = readinessScope(r);
      showResult("Code data-readiness — plan-review pre-check", (body) => {
        body.appendChild(resultNote(`<b>${esc(scope.headline)}</b> — ${esc(scope.detail)}`,
                                    scope.tone));
        body.appendChild(kvTable(readinessRows(r)));
        for (const c of r.checks) {
          const note = isolateNote(c);
          if (note) body.appendChild(resultNote(esc(note), "warn"));
          if (c.status === "fail" && c.fail_guids.length) {
            body.appendChild(d.toolBtn2(`◎ Isolate ${c.fail_guids.length} element(s) missing ${c.label}`,
              () => { void d.layerMgr.isolateGuids(c.fail_guids); }));
          }
        }
        body.appendChild(resultNote(`Checked against <b>${esc(r.code)}</b>. This answers whether the `
          + "MODEL CARRIES the data a plan review needs — it is not a code finding and not a "
          + "certified review.", ""));
      });
    }));
  btn.title = "Does the model carry the data a plan review needs (egress widths, fire ratings, space "
    + "areas and occupancy, stairs, typing)? Rules with no subject element are named rather than "
    + "dropped from the percentage.";
  return btn;
}
