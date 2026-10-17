/**
 * FIN-GOV — the scenario review workflow, which shipped complete on the server and reachable from
 * nowhere.
 *
 * `fin_gov.REVIEW_ACTIONS` is a five-transition state machine (draft → in_review → approved →
 * published, with reject and reopen walking back), `Scenario` carries `review_status`,
 * `reviewed_by`, `reviewed_at` and `review_note`, `review_scenario` audits every move, and
 * `update_scenario` refuses an edit to a committed row with *"scenario is approved and immutable in
 * place — clone a revision to iterate"*. **None of it could be driven from the app:**
 *
 * | route | before |
 * |---|---|
 * | `POST /proforma/scenarios/{sid}/review` | `ApiClient.reviewScenario` existed and was frozen in `apps/web/src/api/clientCallers.test.ts`'s callerless list |
 * | `PUT /proforma/scenarios/{sid}` | no client method at all — **a saved scenario could never be edited** |
 * | `POST /proforma/scenarios/{sid}/clone` | no client method at all — the remedy the 409 names |
 * | `review_status` on the list route | returned by the server, declared nowhere in the client |
 *
 * **The three compose into one defect rather than three.** Because the edit path was missing, the
 * 409 never reached a user, so nobody ever needed the clone, so nothing looked absent — the
 * workflow was consistent *and* inert. *A missing door is invisible when the corridor to it is also
 * missing*, and a frozen callerless list records the symptom one layer too low: `reviewScenario`
 * reads as "written ahead of its screen" rather than as the middle of a severed chain.
 *
 * ### The transition table is DECLARED here and gated against the server's
 *
 * A UI that offers review buttons must know which are legal from a given state, and that table
 * lives in `services/api/src/aec_api/fin_gov.py`. Copying it is a second source of truth — this
 * repo's most-repeated finding — so `scenarioGovernance.test.ts` parses `REVIEW_ACTIONS` out of the
 * Python and asserts agreement **in both directions**: a transition added there and not here means
 * a button nobody can reach, and one here and not there is a button that 404s. Deriving it at
 * runtime was the alternative and is worse: the route does not publish the table, and adding an
 * endpoint to describe a five-row constant is more surface than the constant.
 *
 * ### `returns: null` is THREE states, not one
 *
 * `list_scenarios` sends `(s.result or {}).get("returns")`, so `null` arrives for a row that was
 * never solved AND for one that solved to no returns — and this screen's whole job is telling a
 * developer which scenario is the committed one. Rendering both as "—" states a fact about the deal
 * that the data does not carry. `returnsReading` keeps them apart, and a clone is the case that
 * makes it matter: before this change `clone_scenario` copied the parent's stored `result`, so a
 * revision displayed returns it had never computed.
 */
import { escapeHtml as esc } from "../ui/feedback";
import { money, pct } from "./format";

export type ReviewStatus = "draft" | "in_review" | "approved" | "published";
export type ReviewAction = "submit" | "approve" | "reject" | "publish" | "reopen";

/** `action → [required state, resulting state]`. Mirrors `fin_gov.REVIEW_ACTIONS`; gated against it. */
export const REVIEW_TRANSITIONS: Record<ReviewAction, [ReviewStatus, ReviewStatus]> = {
  submit: ["draft", "in_review"],
  approve: ["in_review", "approved"],
  reject: ["in_review", "draft"],
  publish: ["approved", "published"],
  reopen: ["approved", "draft"],
};

/** States whose assumptions may no longer change in place. Mirrors `fin_gov.IMMUTABLE_STATES`. */
export const IMMUTABLE_STATES: readonly ReviewStatus[] = ["approved", "published"];

/** What each action's button should say — the verb a person recognises, not the wire word. */
const ACTION_LABEL: Record<ReviewAction, string> = {
  submit: "Submit for review",
  approve: "Approve",
  reject: "Send back to draft",
  publish: "Publish",
  reopen: "Reopen as draft",
};

const STATUS_LABEL: Record<ReviewStatus, string> = {
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  published: "Published",
};

/** The status as a human reads it, tolerating one this client has never heard of.
 *
 *  `review_status` arrives from the server as a string. A sixth state added there would be a
 *  `ReviewStatus` by declaration and `undefined` by lookup, and an unguarded
 *  `STATUS_LABEL[s].toLowerCase()` then throws inside the render — **the whole card disappears
 *  because one row carries a word this build predates**. A declared union is a claim about the
 *  server, not a guarantee from it. */
function statusLabel(s: ReviewStatus): string {
  return STATUS_LABEL[s] ?? String(s);
}

/** Which actions are legal from `status` — derived from the table, never a per-state list. */
export function actionsFrom(status: ReviewStatus): ReviewAction[] {
  return (Object.keys(REVIEW_TRANSITIONS) as ReviewAction[])
    .filter((a) => REVIEW_TRANSITIONS[a][0] === status);
}

export interface ScenarioRow {
  id: string;
  name: string;
  review_status: ReviewStatus;
  returns: { equity_irr?: number | null; equity_multiple?: number | null;
    project_irr?: number | null; yield_on_cost?: number | null; npv?: number | null } | null;
}

export interface ReturnsReading {
  /** `unsolved` — no result stored at all. `no_returns` — solved, and the returns are all absent.
   *  `solved` — at least one return to show. The first two are what a bare "—" conflates. */
  kind: "unsolved" | "no_returns" | "solved";
  text: string;
}

export function returnsReading(r: ScenarioRow): ReturnsReading {
  if (r.returns == null) {
    return { kind: "unsolved", text: "not solved yet — no result stored for this revision" };
  }
  const parts: string[] = [];
  if (r.returns.equity_irr != null) parts.push(`${pct(r.returns.equity_irr)} equity IRR`);
  if (r.returns.equity_multiple != null) parts.push(`${r.returns.equity_multiple.toFixed(2)}× equity`);
  if (r.returns.yield_on_cost != null) parts.push(`${pct(r.returns.yield_on_cost)} YoC`);
  if (r.returns.npv != null) parts.push(`${money(r.returns.npv)} NPV`);
  return parts.length
    ? { kind: "solved", text: parts.join(" · ") }
    : { kind: "no_returns", text: "solved, and it returns nothing — no IRR, multiple, yield or NPV" };
}

export interface GovernanceReading {
  rows: ScenarioRow[];
  /** The published scenario, if the project has committed to one. At most one is expected; if the
   *  server ever holds several, the NEWEST wins and `multiple_published` says so rather than one
   *  being picked silently. */
  published: ScenarioRow | null;
  multiple_published: number;
  /** How many rows carry no solved result. Rendered beside any verdict below — a committed-ness
   *  claim over rows that were never solved is the subset verdict this repo keeps finding. */
  unsolved: number;
  /** `true` only when a published scenario exists. `null` when the project has NO scenarios: an
   *  empty register and an uncommitted one are different facts, and one `false` for both is the
   *  defect `test_negated_verdict.py` exists for. */
  committed: boolean | null;
  summary: string;
}

export function governanceReading(rows: readonly ScenarioRow[]): GovernanceReading {
  const list = [...rows];
  const pub = list.filter((r) => r.review_status === "published");
  const unsolved = list.filter((r) => r.returns == null).length;
  const committed = list.length ? pub.length > 0 : null;
  const inReview = list.filter((r) => r.review_status === "in_review").length;
  const summary = committed == null
    ? "No scenarios saved yet — save a solve to start the underwriting record."
    : committed
      ? `Committed: “${pub[pub.length - 1]!.name}” is published.`
            + (inReview ? ` ${inReview} revision(s) in review.` : "")
      : `Not committed — ${list.length} scenario(s), none published.`
            + (inReview ? ` ${inReview} in review.` : "");
  return {
    rows: list,
    published: pub.length ? pub[pub.length - 1]! : null,
    multiple_published: pub.length,
    unsolved,
    committed,
    summary,
  };
}

export interface GovernanceCtx {
  /** Apply a review action and refresh. */
  review: (sid: string, action: ReviewAction) => void;
  /** Clone `sid` as a new draft revision, and refresh. */
  clone: (sid: string, name: string) => void;
  /** Overwrite `sid`'s saved assumptions with the ones currently on screen, and refresh.
   *
   *  **This is the edit path that did not exist**, and its absence is what made the clone look
   *  like a lone gap: `update_scenario` shipped with a 409 naming the clone as the remedy, and with
   *  no client method the refusal could not be reached, so neither could the remedy. Offered only
   *  where `review_status` permits it — the 409 is still the authority, since another person can
   *  approve the row between this render and the click. */
  updateFromCurrent: (sid: string, name: string) => void;
  /** Name a new revision. Returns null when the person cancels. */
  askName: (suggested: string) => Promise<string | null>;
}

/** A revision's default name — the parent's, with a revision counter the person can overwrite. */
export function revisionName(parent: string, existing: readonly string[]): string {
  const base = parent.replace(/\s+rev\s*\d+$/i, "");
  let n = 2;
  const taken = new Set(existing);
  while (taken.has(`${base} rev ${n}`)) n++;
  return `${base} rev ${n}`;
}

/**
 * Render the governance card into `host`, replacing its contents.
 *
 * The coverage line is rendered unconditionally when anything is unsolved, beside the summary —
 * `verdictCoverage`'s rule, and `scenarioGovernance.test.ts` asserts the text is present rather
 * than trusting this comment.
 */
export function renderGovernanceCard(host: HTMLElement, reading: GovernanceReading,
                                     ctx: GovernanceCtx): void {
  host.innerHTML = "";
  const card = document.createElement("div");
  card.className = "dash-card";

  const head = document.createElement("div");
  head.className = "section-title";
  head.textContent = "📒 Underwriting record — scenario review";
  card.appendChild(head);

  const sum = document.createElement("div");
  sum.className = "meta";
  sum.textContent = reading.summary;
  card.appendChild(sum);

  if (reading.unsolved > 0) {
    const cov = document.createElement("div");
    cov.className = "meta";
    cov.style.color = "var(--status-warn)";
    cov.textContent = `${reading.unsolved} of ${reading.rows.length} scenario(s) have no solved `
      + "result — their returns are unknown, not zero.";
    card.appendChild(cov);
  }
  if (reading.multiple_published > 1) {
    const warn = document.createElement("div");
    warn.className = "meta";
    warn.style.color = "var(--status-crit)";
    warn.textContent = `${reading.multiple_published} scenarios are published — the newest is shown `
      + "as committed, but only one should be.";
    card.appendChild(warn);
  }

  if (!reading.rows.length) { host.appendChild(card); return; }

  const names = reading.rows.map((r) => r.name);
  for (const r of reading.rows) {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;align-items:center;flex-wrap:wrap;"
      + "padding:6px 0;border-top:1px solid var(--line)";
    row.dataset.scenario = r.id;

    const title = document.createElement("div");
    title.style.cssText = "flex:1;min-width:180px";
    const rr = returnsReading(r);
    title.innerHTML = `<div style="font-weight:600">${esc(r.name)}</div>`
      + `<div class="meta"${rr.kind === "solved" ? "" : ` style="color:var(--status-warn)"`}>`
      + `${esc(rr.text)}</div>`;
    row.appendChild(title);

    const pill = document.createElement("span");
    pill.className = "ball-badge";
    pill.dataset.status = r.review_status;
    pill.textContent = statusLabel(r.review_status);
    row.appendChild(pill);

    for (const a of actionsFrom(r.review_status)) {
      const b = document.createElement("button");
      b.className = "file-btn";
      b.dataset.action = a;
      b.textContent = ACTION_LABEL[a];
      b.title = `${ACTION_LABEL[a]} — moves this scenario to `
        + `${statusLabel(REVIEW_TRANSITIONS[a][1])}`;
      b.onclick = () => ctx.review(r.id, a);
      row.appendChild(b);
    }

    // The EDIT path, on rows the state machine still allows it for. Deliberately "from the current
    // solve" rather than an inline assumption editor: the panel above already holds a full, solved
    // assumption set that the person has been working on, and writing THAT into the saved row is
    // both the common intent and the one operation that cannot produce a scenario whose stored
    // result disagrees with its stored assumptions — the route re-solves what it is given.
    if (!IMMUTABLE_STATES.includes(r.review_status)) {
      const upd = document.createElement("button");
      upd.className = "file-btn";
      upd.dataset.action = "update";
      upd.textContent = "Save current solve into this";
      upd.title = `Overwrite “${r.name}”'s saved assumptions with the ones on screen now, and `
        + "re-solve it. The changed assumption paths are reported.";
      upd.onclick = () => ctx.updateFromCurrent(r.id, r.name);
      row.appendChild(upd);
    }

    // Revise is offered on EVERY row, not only the immutable ones: cloning a draft is a legitimate
    // way to explore a variant, and `published` is terminal in the state machine so it is the ONLY
    // forward move there. The button says which it is.
    const rev = document.createElement("button");
    rev.className = "file-btn";
    rev.dataset.action = "clone";
    rev.textContent = "Revise";
    rev.title = IMMUTABLE_STATES.includes(r.review_status)
      ? `“${r.name}” is ${statusLabel(r.review_status).toLowerCase()} and cannot be edited in `
        + "place — this copies it as a new draft you can change"
      : "Copy this scenario as a new draft revision";
    rev.onclick = async () => {
      const name = await ctx.askName(revisionName(r.name, names));
      if (name) ctx.clone(r.id, name);
    };
    row.appendChild(rev);

    card.appendChild(row);
  }
  host.appendChild(card);
}
