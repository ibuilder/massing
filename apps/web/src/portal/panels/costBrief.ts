import { usd } from "../../ui/charts";
import type { PanelContext } from "../panelContext";
import { briefPrimary, fail, mountBrief, openRoomModule } from "./roomBriefChrome";

/**
 * R36-ROOM-BRIEFS — Cost (PM / estimator).
 *
 * The room opens with three answers, then the GMP board.
 *
 * 1. **Vs GMP** — EAC against the agreed contract. No GMP is a sentence, never 0% of a missing number.
 * 2. **Unpriced exposure** — Pulse's unpriced-change count. A missing count is a reason, never "0 unpriced".
 * 3. **Buyout / committed** — packages bought vs awarded. No packages is a sentence, not 0% buyout.
 *
 * Engines already exist (`gmpBudget`, `projectPulse`).
 */
export const COST_BRIEF_QUESTIONS = [
  { key: "gmp", title: "Vs GMP" },
  { key: "unpriced", title: "Unpriced exposure" },
  { key: "buyout", title: "Buyout / committed" },
] as const;

export async function renderCostBrief(ctx: PanelContext): Promise<HTMLElement> {
  const pid = ctx.host.projectId()!;
  const { wrap, byKey } = mountBrief("costBrief", COST_BRIEF_QUESTIONS);
  const gmpCard = byKey.gmp!;
  const unpCard = byKey.unpriced!;
  const buyCard = byKey.buyout!;

  const [gmp, pulse] = await Promise.allSettled([
    ctx.host.api.gmpBudget(pid),
    ctx.host.api.projectPulse(pid),
  ]);

  if (gmp.status === "rejected") {
    fail(gmpCard.body, `GMP unavailable: ${(gmp.reason as Error).message}`);
    fail(buyCard.body, `Buyout unavailable: ${(gmp.reason as Error).message}`);
  } else {
    const g = gmp.value.gmp;
    const agreed = g.revised || g.contract_value || gmp.value.totals.budget;
    const eac = gmp.value.completion.eac;
    if (!agreed && !gmp.value.totals.budget) {
      gmpCard.body.textContent = "No GMP agreed yet — there is no contract to measure EAC against.";
    } else {
      const varn = gmp.value.completion.projected_over_under;
      const vs = varn > 0 ? `${usd(varn)} over` : varn < 0 ? `${usd(Math.abs(varn))} under` : "on the number";
      gmpCard.body.textContent = `EAC ${usd(eac)} vs GMP ${usd(agreed)} · ${vs}`;
    }

    const bo = gmp.value.buyout;
    if (!bo.packages) {
      buyCard.body.textContent = "No bid packages to buy out yet.";
    } else {
      buyCard.body.textContent =
        `${bo.bought_out} of ${bo.packages} packages bought`
        + ` · awarded ${usd(bo.awarded)} of ${usd(bo.budget)}`
        + (bo.savings ? ` · savings ${usd(bo.savings)}` : "");
    }
  }

  if (pulse.status === "rejected") {
    fail(unpCard.body, `Unpriced exposure unavailable: ${(pulse.reason as Error).message}`);
  } else if (pulse.value.cost?.unpricedChanges == null) {
    unpCard.body.textContent = "Pulse has no unpriced-change count yet.";
  } else {
    const n = pulse.value.cost.unpricedChanges;
    const exp = pulse.value.cost.exposurePct;
    unpCard.body.textContent = n === 0
      ? "No unpriced changes on Pulse."
      : `${n} unpriced change${n === 1 ? "" : "s"}`
        + (exp != null ? ` · exposure ${exp > 0 ? "+" : ""}${exp.toFixed(1)}%` : "");
  }

  briefPrimary(gmpCard, "cost", "Open budget lines", () => openRoomModule(ctx, "budget"));
  return wrap;
}
