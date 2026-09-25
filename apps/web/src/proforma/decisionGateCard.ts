/** The pre-committee readiness gate — the keystone over everything else on this tab.
 *
 *  `services/api/src/aec_api/decision_gate.py` names the failure it exists to prevent:
 *
 *  > a package that *looks* finished reaching a committee, because nothing between the analyst and
 *  > the room ever asked whether the numbers were sourced.
 *
 *  Seven gates — citation coverage, comp tiering, the T-12 tie-out, the rent-roll scrub, the
 *  deal-room authority gate, exhibits, and a named human sign-off — and two rules that make it
 *  honest rather than decorative:
 *
 *  > A gate whose evidence was not supplied is `unknown`, and unknown BLOCKS — absent evidence must
 *  > never read as a pass. The actions list says what to do, not just what failed.
 *
 *  **That is the principle this whole session has been enforcing in consumers, implemented here at
 *  the composition level** — so the card's job is not to add judgement but to avoid subtracting it:
 *  render `unknown` as blocking rather than as neutral, and lead with the actions.
 *
 *  `ApiClient.decisionGate()` was callerless, so none of that was reachable.
 *
 *  MEASURED WITH NO EVIDENCE: 6 of 7 `unknown`, verdict `blocked`, six actions emitted. The seventh,
 *  `exhibits`, passes *"no exhibits were required for this package"* — a vacuous pass, rendered with
 *  its reason rather than as a bare tick, because a pass that was never tested is the thing the other
 *  six are protected against.
 *
 *  WHAT IT SENDS, AND WHAT IT DELIBERATELY DOES NOT INVENT
 *  The card gathers the two pieces of evidence this app can already produce on demand — the
 *  deal-room authority assessment and the rent-roll scrub — and sends them. The other five it leaves
 *  absent, which makes them `unknown`, which blocks. **That is the correct answer, not a gap in the
 *  card**: a committee package without a citation contract, tiered comps, a tied-out T-12 or a named
 *  signer is not ready, and saying so with the engine's own actions is more useful than a card that
 *  quietly omits the gates it cannot feed. *An absent input is a finding here, which is the one place
 *  in this product where that is true by design.*
 */
import type { ApiClient } from "../api/client";
import { escapeHtml as esc } from "../ui/feedback";

type Gate = Awaited<ReturnType<ApiClient["decisionGate"]>>;

const meta = (html: string, colour?: string) =>
  `<div class="meta" style="margin-top:4px${colour ? `;color:${colour}` : ""}">${html}</div>`;

/** `unknown` is not neutral here — the engine blocks on it, so it must not READ as neutral either. */
const COLOUR: Record<string, string> = {
  pass: "var(--status-good)",
  fail: "var(--status-crit)",
  unknown: "var(--status-warn)",
};

/** The word for a status, in the engine's own terms rather than a tick and a cross. */
const WORD: Record<string, string> = {
  pass: "pass",
  fail: "fail",
  unknown: "no evidence — blocks",
};

export function renderDecisionGate(host: HTMLElement, g: Gate): HTMLElement {
  const el = document.createElement("div");
  el.style.marginTop = "8px";
  const c = g.counts;

  el.insertAdjacentHTML("beforeend",
    `<div style="font-weight:600;color:${g.ready ? "var(--status-good)" : "var(--status-crit)"}">`
    + (g.ready ? "Ready for committee" : "Blocked — not ready for committee")
    + `</div>`
    + meta(`${c.passed ?? 0} passed · ${c.failed ?? 0} failed · `
           + `<strong>${c.unknown ?? 0} with no evidence</strong> — of ${c.total ?? 0} gates.`));

  // THE ACTIONS LEAD, because the engine's contract is that the verdict says what to DO. A list of
  // failures is a status report; a list of actions is the thing somebody can act on at the moment
  // they are stopped.
  if (g.actions.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>To unblock</td><td>do this</td></tr>`
      + g.actions.map((a) => `<tr><td>${esc(labelOf(g, a.gate))}</td>`
          + `<td>${esc(a.action)}</td></tr>`).join("")
      + `</table>`);
  }

  el.insertAdjacentHTML("beforeend",
    `<table class="fin-table" style="margin-top:6px">`
    + `<tr class="fin-sub"><td>Gate</td><td>state</td><td>detail</td></tr>`
    + g.gates.map((x) =>
        `<tr><td>${esc(x.label)}</td>`
        + `<td style="color:${COLOUR[x.status] ?? ""}">${esc(WORD[x.status] ?? x.status)}</td>`
        + `<td>${esc(x.detail)}</td></tr>`).join("")
    + `</table>`);

  el.insertAdjacentHTML("beforeend", meta(esc(g.note)));
  host.appendChild(el);
  return el;
}

function labelOf(g: Gate, gate: string): string {
  return g.gates.find((x) => x.gate === gate)?.label ?? gate;
}

export interface DecisionGateCtx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
}

/** Gather the evidence this app can produce on demand. The rest stays absent — and therefore
 *  `unknown`, and therefore blocking, which is the honest answer rather than a gap in the card. */
export async function gatherEvidence(api: ApiClient, pid: string): Promise<Record<string, unknown>> {
  const [authority, scrub] = await Promise.allSettled([
    api.dealAuthority(pid),
    api.rentRollScrub(pid),
  ]);
  const ev: Record<string, unknown> = {};
  if (authority.status === "fulfilled") ev.authority = authority.value;
  if (scrub.status === "fulfilled") ev.rent_scrub = scrub.value;
  return ev;
}

export function renderDecisionGateCard(root: HTMLElement, ctx: DecisionGateCtx): HTMLElement {
  const host = document.createElement("div");
  host.id = "pf-decision-gate";
  host.className = "fin-card";
  host.style.marginTop = "10px";
  host.innerHTML = `<div class="section-title">Pre-committee readiness</div>`
    + `<div class="meta">Seven gates over the evidence, not over the conclusions. A gate whose `
    + `evidence was not supplied is <strong>unknown</strong>, and unknown blocks — absent evidence `
    + `must never read as a pass.</div>`;

  const actions = document.createElement("div"); actions.style.marginTop = "6px";
  const go = document.createElement("button");
  go.className = "file-btn"; go.textContent = "Check readiness";
  actions.appendChild(go); host.appendChild(actions);
  const out = document.createElement("div"); host.appendChild(out);
  root.appendChild(host);

  go.onclick = async () => {
    const pid = ctx.projectId();
    if (!pid) { out.innerHTML = meta("Open a project first."); return; }
    go.disabled = true;
    out.innerHTML = meta("gathering evidence…");
    ctx.setStatus("checking pre-committee readiness…");
    try {
      const evidence = await gatherEvidence(ctx.api, pid);
      const g = await ctx.api.decisionGate(pid, evidence);
      out.replaceChildren();
      // Name which evidence this card supplied, so an `unknown` is legible as "not gathered here"
      // rather than as "gathered and found wanting" — two different things to do about it.
      const supplied = Object.keys(evidence).sort();
      out.insertAdjacentHTML("beforeend", meta(
        supplied.length
          ? `Supplied from this project: ${supplied.map((k) => esc(k.replace(/_/g, " "))).join(", ")}. `
            + `Anything else was not gathered here and shows as no evidence.`
          : `No evidence could be gathered from this project — every gate below is reporting an `
            + `absence, not a failure.`));
      renderDecisionGate(out, g);
      ctx.setStatus(g.ready ? "ready for committee" : `blocked — ${g.actions.length} action(s)`);
    } catch (e) {
      out.innerHTML = meta(esc((e as Error).message), "var(--status-crit)");
      ctx.setStatus("readiness check failed");
    } finally {
      go.disabled = false;
    }
  };

  return host;
}
