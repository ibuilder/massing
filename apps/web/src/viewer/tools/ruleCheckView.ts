import type { ApiClient } from "../../api/client";
import { escapeHtml, toast } from "../../ui/feedback";
import { resultNote, showResult } from "../../ui/result";

/**
 * FIRM-RULES-OPTIONAL — the rule check, and what it is a check OF.
 *
 * `/projects/{pid}/rules/run` reported *"0 of 3 rules failing"* in a pass tone on a project where
 * nobody had authored a rule at all. Three SAMPLE rules ship as a starting point, and the two things
 * that evaluate a model fell back to them — so the reassuring sentence was about examples, and
 * nothing in the response said so. `GET /projects/{pid}/rules` has always returned `seeded` for
 * exactly that fallback, one route away from the consumer that needed it.
 *
 * Worse, the firm's own library was evaluated by nothing. `firm_standards.effective_rules` answers
 * *what applies here*, says in its docstring that the failure mode is **"a firm discovering its
 * standards were quietly optional"**, and had one consumer: its own route, which no screen reached.
 * So a firm could author a standard, watch every project list it as inherited on a page that could
 * not be opened, and have it gate nothing.
 *
 * This module is the screen half. Three things it is careful about:
 *
 *  1. **A clean result over samples is not toned as a pass.** Unassessable and clean are different
 *     claims, and the pass tone is the whole misreading.
 *  2. **A failure found by a sample rule is still shown as a failure.** The defect is real whoever
 *     wrote the rule — a door with no fire rating is a door with no fire rating — so the samples are
 *     relabelled, never suppressed.
 *  3. **Every row says where its rule came from.** An override is legitimate and being invisible is
 *     not, so a project rule displacing a firm standard is badged as an override and names what it
 *     replaced.
 *
 * Extracted into its own module rather than added to `qaSection.ts`, for the two reasons that file's
 * other extractions give: it is under a down-only line ratchet in `services/api/test_file_sizes.py`
 * and sits exactly on its pin, and `viewer/tools/*` is the eager `app-*` chunk whose budget has no
 * headroom. The shapes are DERIVED from the client methods (`Awaited<ReturnType<…>>`) rather than
 * re-spelled, which is what `apps/web/src/api/noRespelledShapes.test.ts` exists to require.
 */
export type RuleRun = Awaited<ReturnType<ApiClient["rulesRun"]>>;
export type EffectiveRules = Awaited<ReturnType<ApiClient["rulesEffective"]>>;
type Provenance = NonNullable<RuleRun["provenance"]>;

export interface ProvenanceReading {
  /** `samples` — nobody authored anything. `firm` · `project` · `mixed` — an authored library. */
  kind: "samples" | "firm" | "project" | "mixed";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * What the rule set in front of the user actually IS.
 *
 * `samples` is toned `warn`, not `ok` and not `bad`: nothing is wrong and nothing has been
 * established either. The three authored kinds are toned `ok` because the set itself is sound — the
 * findings carry their own tone row by row.
 */
export function provenanceReading(p: Provenance): ProvenanceReading {
  if (p.using_starter) {
    return {
      kind: "samples", tone: "warn",
      headline: "These are the three SAMPLE rules — no standard has been authored.",
      detail: "Neither this project nor the firm has a rule library, so the fallback set ran. "
        + "A clean result here is not a pass against anything anybody chose; a failure is still a "
        + "real defect. Author a firm library so every project inherits it.",
    };
  }
  const bits: string[] = [];
  if (p.inherited_count) bits.push(`${p.inherited_count} inherited from the firm`);
  if (p.project_only_count) bits.push(`${p.project_only_count} this project's own`);
  if (p.overridden_count) bits.push(`${p.overridden_count} overriding a firm standard`);
  const kind = p.inherited_count || p.overridden_count
    ? (p.project_only_count ? "mixed" : "firm")
    : "project";
  return {
    kind, tone: "ok",
    headline: `${bits.join(" · ") || "no rules apply"}.`,
    detail: p.overridden_count
      ? "An override is legitimate — a client standard differing from the firm's is normal — and "
        + "every overriding row names the firm rule it replaced, so it reads as an override rather "
        + "than as the standard."
      : (p.firm_count
          ? "The firm's standards are evaluated here, not merely listed."
          : "No firm standards are authored, so this is exactly this project's own library."),
  };
}

/** `firm` · `project` · `override` · `sample` · `space pack` — never a bare unlabelled row. */
export function sourceBadge(source: string | null | undefined, overrides: unknown): string {
  if (overrides) return "⇄ override";
  switch (source) {
    case "firm": return "🏛 firm";
    case "project": return "📁 project";
    case "starter": return "🧪 sample";
    case "space-pack": return "▭ space pack";
    default: return "· origin unknown";
  }
}

/** The whole rule-check result: the provenance note, the rollup, then a badged row per rule. */
export function renderRuleCheck(r: RuleRun, body: HTMLElement,
                                isolate: (guids: string[]) => void): void {
  const prov = r.provenance;
  if (prov) {
    const read = provenanceReading(prov);
    body.appendChild(resultNote(`<b>${escapeHtml(read.headline)}</b> — ${escapeHtml(read.detail)}`,
                                read.tone));
  }
  const bySev = r.by_severity || {};
  const fails = r.failing_rules ?? 0;
  body.appendChild(resultNote(`<b>${fails}</b> of ${r.total_rules} rules failing · `
    + `${r.total_violations ?? 0} violations` + (bySev.high ? ` · 🔴 ${bySev.high} high` : "")
    + (bySev.medium ? ` · 🟡 ${bySev.medium} medium` : "") + (bySev.low ? ` · ⚪ ${bySev.low} low` : ""),
    // A clean result over the samples is NOT toned as a pass: that tone is the misreading this
    // whole item is about.
    fails || prov?.using_starter ? "" : "ok"));
  const sev: Record<string, string> = { high: "🔴", medium: "🟡", low: "⚪" };
  for (const rule of r.rules) {
    const icon = rule.status === "pass" ? "✅" : rule.status === "n/a" ? "➖" : (sev[rule.severity] || "•");
    const line = resultNote(`${icon} <b>${escapeHtml(rule.name)}</b> — ${rule.passed}/${rule.scoped} pass`
      + (rule.failed ? ` · <b>${rule.failed}</b> fail` : "")
      + ` · <span style="opacity:.7">${escapeHtml(sourceBadge(rule.source, rule.overrides))}</span>`
      + (rule.overrides ? ` <span style="opacity:.7">(firm: ${escapeHtml(rule.overrides.require)})</span>` : ""),
      rule.status === "fail" ? "" : "ok");
    if (rule.failed && rule.fail_guids.length) {
      const pick = document.createElement("a"); pick.href = "#"; pick.textContent = " isolate failures";
      pick.style.cssText = "font-size:11px;margin-left:6px";
      pick.onclick = (e) => { e.preventDefault(); isolate(rule.fail_guids.slice(0, 500)); };
      line.appendChild(pick);
    }
    body.appendChild(line);
  }
}

/**
 * The standards that apply here, without running them — the firm's library layered with this
 * project's, every row saying which it is.
 *
 * This is the door for `/projects/{pid}/rules/effective`, which existed, was tested, and was
 * reachable from nothing.
 */
export function renderEffectiveStandards(e: EffectiveRules, body: HTMLElement): void {
  body.appendChild(resultNote(
    `<b>${e.count}</b> rule(s) apply · ${e.inherited_count} inherited · ${e.project_only_count} `
    + `project-only · ${e.overridden_count} overriding · firm library holds ${e.firm_count}`,
    e.count ? "ok" : "warn"));
  body.appendChild(resultNote(escapeHtml(e.note), ""));
  if (!e.count) {
    body.appendChild(resultNote(
      "Nothing is authored here or at the firm, so a rule check falls back to three SAMPLE rules "
      + "and its result is about examples. Authoring a firm library is what makes every project's "
      + "check mean something.", "warn"));
    return;
  }
  for (const rule of e.rules) {
    body.appendChild(resultNote(
      `<b>${escapeHtml(rule.name)}</b> <span style="opacity:.7">${escapeHtml(sourceBadge(rule.source, rule.overrides))}`
      + ` · ${escapeHtml(rule.severity)}</span><br><code style="font-size:10.5px">`
      + `${escapeHtml(rule.scope)} ⟶ ${escapeHtml(rule.require)}</code>`
      + (rule.overrides
          ? `<br><span style="opacity:.7">replaces the firm rule: <code style="font-size:10.5px">`
            + `${escapeHtml(rule.overrides.require)}</code> (${escapeHtml(rule.overrides.severity)})</span>`
          : ""),
      ""));
  }
  for (const o of e.overridden) {
    body.appendChild(resultNote(
      `⇄ <b>${escapeHtml(o.name)}</b> — firm asks <code>${escapeHtml(o.firm_require)}</code>, this `
      + `project asks <code>${escapeHtml(o.project_require)}</code>`, "warn"));
  }
}


/**
 * The two CONTROL BODIES, here rather than in `qaSection.ts` — and this is the pattern the bundle
 * budget's own note called "the right shape" and then declined, on the grounds that no tool under
 * `viewer/tools/` used it. Three do on this branch now, and this one was forced: the shell came out
 * **5 bytes** over 224 KB with only the rendering deferred, so the fetch, the toast, the status line
 * and the `showResult` call moved too. *Deferring the rendering and keeping the handler is the same
 * half-measure the previous item paid for twice, one layer up.*
 *
 * `toast` and `showResult` are imported here directly: both are already in the eager shell because
 * the panel uses them for forty other controls, so reaching them from a lazy chunk costs nothing and
 * threading them through a context object would only have added eager bytes back.
 */
export async function runRuleCheck(api: ApiClient, pid: string, out: HTMLElement,
                                   isolate: (guids: string[]) => void): Promise<void> {
  let r: RuleRun;
  try { r = await api.rulesRun(pid); }
  catch (e) { toast((e as Error).message, "error"); return; }
  if (!r.model_scored) { toast(r.note || "no model loaded", "info"); return; }
  out.textContent = `rules: ${r.failing_rules ?? 0}/${r.total_rules} failing`;
  showResult("Rule library check", (body) => renderRuleCheck(r, body, isolate));
}

/** The standards that apply here, without running them — the first door for `/rules/effective`. */
export async function showEffectiveStandards(api: ApiClient, pid: string,
                                             out: HTMLElement): Promise<void> {
  let e: EffectiveRules;
  try { e = await api.rulesEffective(pid); }
  catch (err) { toast((err as Error).message, "error"); return; }
  out.textContent = `standards: ${e.count} apply · ${e.inherited_count} from the firm`;
  showResult("Standards that apply to this project", (body) => renderEffectiveStandards(e, body));
}
