import type { PanelContext } from "../panelContext";
import { fail, mountBrief } from "./roomBriefChrome";

/**
 * R36-ROOM-BRIEFS — Operate (facility / CMMS).
 *
 * The room opens with three answers, then the work-order board.
 *
 * 1. **Overdue work orders** — backlog that has already missed its due date.
 * 2. **PM compliance** — `null` is not 0%. No due PMs is a sentence.
 * 3. **FCI** — facility condition. No scored elements is a sentence, never an FCI of 0%.
 *
 * Engines already exist (`cmmsKpis`, `fcaIndex`).
 */
export const OPERATE_BRIEF_QUESTIONS = [
  { key: "overdue", title: "Overdue work orders" },
  { key: "pm", title: "PM compliance" },
  { key: "fci", title: "Facility condition (FCI)" },
] as const;

export async function renderOperateBrief(ctx: PanelContext): Promise<HTMLElement> {
  const pid = ctx.host.projectId()!;
  const { wrap, byKey } = mountBrief("operateBrief", OPERATE_BRIEF_QUESTIONS);
  const odCard = byKey.overdue!;
  const pmCard = byKey.pm!;
  const fciCard = byKey.fci!;

  const [kpis, fca] = await Promise.allSettled([
    ctx.host.api.cmmsKpis(pid),
    ctx.host.api.fcaIndex(pid),
  ]);

  if (kpis.status === "rejected") {
    const why = (kpis.reason as Error).message;
    fail(odCard.body, `Overdue work orders unavailable: ${why}`);
    fail(pmCard.body, `PM compliance unavailable: ${why}`);
  } else {
    const k = kpis.value;
    odCard.body.textContent = k.overdue === 0
      ? `None overdue · ${k.open} open`
      : `${k.overdue} overdue · ${k.open} open`;
    if (k.pm_compliance_pct == null) {
      pmCard.body.textContent = "PM compliance is not scored yet — there are no due PM schedules to measure.";
    } else {
      pmCard.body.textContent = `${k.pm_compliance_pct}%`
        + (k.mttr_days != null ? ` · MTTR ${k.mttr_days} d` : "");
    }
  }

  if (fca.status === "rejected") {
    fail(fciCard.body, `FCI unavailable: ${(fca.reason as Error).message}`);
  } else if (!fca.value.elements) {
    fciCard.body.textContent = fca.value.note
      || "No FCA elements scored — facility condition has not been assessed.";
  } else {
    fciCard.body.textContent =
      `FCI ${fca.value.fci_pct}% (${fca.value.band}) · ${fca.value.elements} elements`
      + ` · ${fca.value.open_deficiencies} open deficiencies`;
  }

  return wrap;
}
