import type { PanelContext } from "../panelContext";
import { briefPrimary, fail, mountBrief, openRoomModule } from "./roomBriefChrome";

/**
 * R36-ROOM-BRIEFS — Planning (PM).
 *
 * The room opens with three answers, then the full benchmark tables.
 *
 * 1. **RFI clock** — overdue share and average turnaround. No RFIs is a sentence, not a fake clock.
 * 2. **Submittal clock** — same for submittals.
 * 3. **Cost history** — own-history medians by code. No history is a sentence, never a invented median.
 *
 * Engines already exist (`benchmarkResponseRates`, `benchmarkCosts`).
 */
export const PLANNING_BRIEF_QUESTIONS = [
  { key: "rfi", title: "RFI clock" },
  { key: "submittal", title: "Submittal clock" },
  { key: "costs", title: "Cost history to check an estimate" },
] as const;

function clock(
  body: HTMLElement,
  kind: string,
  m: { total: number; open: number; overdue: number; overdue_pct: number; avg_turnaround_days: number | null },
): void {
  if (!m.total) {
    body.textContent = `No ${kind}s in the history yet.`;
    return;
  }
  const avg = m.avg_turnaround_days == null ? "average turnaround not scored"
    : `avg ${m.avg_turnaround_days} d`;
  body.textContent = `${m.total} ${kind}${m.total === 1 ? "" : "s"} · ${m.open} open`
    + ` · ${m.overdue} overdue (${m.overdue_pct}%) · ${avg}`;
}

export async function renderPlanningBrief(ctx: PanelContext): Promise<HTMLElement> {
  const { wrap, byKey } = mountBrief("planningBrief", PLANNING_BRIEF_QUESTIONS);
  const rfiCard = byKey.rfi!;
  const subCard = byKey.submittal!;
  const costCard = byKey.costs!;

  const [rates, costs] = await Promise.allSettled([
    ctx.host.api.benchmarkResponseRates(),
    ctx.host.api.benchmarkCosts(),
  ]);

  if (rates.status === "rejected") {
    const why = (rates.reason as Error).message;
    fail(rfiCard.body, `RFI clock unavailable: ${why}`);
    fail(subCard.body, `Submittal clock unavailable: ${why}`);
  } else {
    clock(rfiCard.body, "RFI", rates.value.rfi);
    clock(subCard.body, "submittal", rates.value.submittal);
  }

  if (costs.status === "rejected") {
    fail(costCard.body, `Cost history unavailable: ${(costs.reason as Error).message}`);
  } else if (!costs.value.cost_codes.length) {
    costCard.body.textContent = costs.value.message || "No cost history yet — there is no median to check an estimate against.";
  } else {
    const top = costs.value.cost_codes.slice(0, 4);
    costCard.body.innerHTML = "";
    const sub = document.createElement("div");
    sub.style.marginBottom = "4px";
    sub.textContent = `${costs.value.code_count} codes with ≥${costs.value.min_samples} samples each`;
    costCard.body.appendChild(sub);
    for (const c of top) {
      const row = document.createElement("div");
      row.style.margin = "1px 0";
      const med = Math.round(c.median).toLocaleString();
      row.textContent = `${c.cost_code} · median $${med} (n=${c.samples})`;
      costCard.body.appendChild(row);
    }
  }

  briefPrimary(rfiCard, "planning", "Open RFIs", () => openRoomModule(ctx, "rfi"));
  return wrap;
}
