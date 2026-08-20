import type { PanelContext } from "../panelContext";
import { firstOpenStep, type ReadinessStep } from "./readinessStrip";
import { briefPrimary, fail, mountBrief } from "./roomBriefChrome";

/**
 * R36-ROOM-BRIEFS — Deal (developer).
 *
 * The room opens with three answers, then the portfolio book. Work (`workQueue.ts`) is the template.
 *
 * 1. **Returns vs guardrails** — live IRR against the underwriting band. No IRR is a sentence,
 *    never 0.0%.
 * 2. **Open diligence** — go/no-go plus flagged studies. A failed fetch is a reason, never "0 flagged".
 * 3. **Next decision gate** — first non-ready developer protocol step. A 500 is "unavailable".
 *
 * Engines already exist (`projectPulse`, `diligenceReadiness`, `masterBuilderBrief`).
 */
export const DEAL_BRIEF_QUESTIONS = [
  { key: "returns", title: "Returns vs guardrails" },
  { key: "diligence", title: "Open diligence" },
  { key: "gate", title: "Next decision gate" },
] as const;

export async function renderDealBrief(ctx: PanelContext): Promise<HTMLElement> {
  const pid = ctx.host.projectId()!;
  const { wrap, byKey } = mountBrief("dealBrief", DEAL_BRIEF_QUESTIONS);
  const retCard = byKey.returns!;
  const dilCard = byKey.diligence!;
  const gateCard = byKey.gate!;

  const [pulse, dil, brief] = await Promise.allSettled([
    ctx.host.api.projectPulse(pid),
    ctx.host.api.diligenceReadiness(pid),
    ctx.host.api.masterBuilderBrief(pid, { workspace: "developer", persona: "developer" }),
  ]);

  if (pulse.status === "rejected") {
    fail(retCard.body, `Returns unavailable: ${(pulse.reason as Error).message}`);
  } else if (!pulse.value.deal || pulse.value.deal.irrPct == null) {
    retCard.body.textContent = "No IRR yet — there is no underwriting scenario to measure against.";
  } else {
    const d = pulse.value.deal;
    const irr = d.irrPct as number;
    const band = d.band;
    let vs = "";
    if (band && band.length === 2) {
      const [lo, hi] = band;
      vs = irr < lo ? `below the ${lo}–${hi}% band`
        : irr > hi ? `above the ${lo}–${hi}% band`
        : `inside the ${lo}–${hi}% band`;
    }
    retCard.body.textContent = `Equity IRR ${irr.toFixed(1)}%${vs ? ` · ${vs}` : ""}`
      + (d.staleSince ? ` · stale since ${d.staleSince}` : "");
    if (d.reserveSuggestionFails) {
      const extra = document.createElement("div");
      extra.textContent = "Suggested reserve contribution does not clear the horizon.";
      retCard.body.appendChild(extra);
    }
  }

  if (dil.status === "rejected") {
    fail(dilCard.body, `Diligence unavailable: ${(dil.reason as Error).message}`);
  } else {
    const dd = dil.value.due_diligence;
    const en = dil.value.entitlements;
    dilCard.body.textContent = dil.value.go
      ? `GO — ${dd.cleared}/${dd.total} studies cleared, entitlements approved.`
      : `Not ready — ${dd.flagged} flagged · ${dd.total - dd.cleared} studies still open · ${en.pending} entitlements pending.`;
  }

  if (brief.status === "rejected") {
    fail(gateCard.body, `Decision gate unavailable: ${(brief.reason as Error).message}`);
  } else {
    const steps: ReadinessStep[] = brief.value.steps.map((s) => ({
      n: s.n, key: s.key, title: s.title, dest: s.dest, status: s.status, gaps: s.gaps,
    }));
    const next = firstOpenStep(steps);
    if (!next) {
      gateCard.body.textContent = "No open gate in the developer protocol.";
    } else {
      gateCard.body.textContent = next.title;
      if (next.gaps[0]) {
        const g = document.createElement("div");
        g.textContent = next.gaps[0];
        gateCard.body.appendChild(g);
      }
      if (ctx.hasDest(next.dest)) {
        briefPrimary(gateCard, "deal", "Open", () => ctx.navigate(next.dest));
      } else {
        briefPrimary(gateCard, "deal", "See the book", () => ctx.navigate("__portfolio__"));
      }
    }
  }

  if (!wrap.querySelector("[data-room-primary]")) {
    briefPrimary(gateCard, "deal", "See the book", () => ctx.navigate("__portfolio__"));
  }
  return wrap;
}
