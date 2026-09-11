/** What a lender draw package actually says, once you read the whole reply.
 *
 *  `POST /proforma/scenarios/{sid}/draw-package` returns five keys and the client declared three,
 *  so the status line could report a payment due and a line count and nothing else. The two it
 *  dropped are the two the route exists for:
 *
 *  * `g703_totals` — the schedule of values the G702 certificate is computed FROM. A payment due
 *    with no visible completed-to-date and no visible retainage is a number nobody downstream can
 *    check, and retainage is the line owners and subcontractors argue about.
 *  * `forecast_returns` — the route's own docstring says the point is *"so the IRR you underwrote
 *    and the lender draw run off the SAME cost tree"*. This is that IRR, re-forecast with the
 *    actuals folded in. It answers *is this still the deal we signed?* and it was computed on every
 *    draw and shown on none.
 *
 *  Pure, so the money formatting and the null handling are testable without a scenario.
 */
import { usd } from "../ui/charts";

export interface DrawPackageReply {
  sov_lines_created: number;
  g702: Record<string, number>;
  g703_totals: { scheduled: number; completed: number; balance: number; retainage: number };
  forecast_returns: { equity_irr: number | null; equity_multiple: number };
}

/**
 * The lines to show beside the generated package, most load-bearing first.
 *
 * `equity_irr` is `null` when the cash flows do not support a rate — an unsolvable IRR, not a zero.
 * It renders as `n/a`, because printing `0%` there would report a specific and wrong answer on the
 * screen a draw request is assembled from.
 */
export function drawPackageLines(dp: DrawPackageReply): string[] {
  const t = dp.g703_totals, f = dp.forecast_returns;
  const due = dp.g702.line8_current_payment_due ?? 0;
  return [
    `SOV ${dp.sov_lines_created} line${dp.sov_lines_created === 1 ? "" : "s"} → G702 due ${usd(due)}`,
    `G703: ${usd(t.completed)} completed of ${usd(t.scheduled)} scheduled · `
      + `${usd(t.retainage)} retained · ${usd(t.balance)} to finish`,
    `Forecast with these actuals: equity IRR ${f.equity_irr === null ? "n/a" : `${(f.equity_irr * 100).toFixed(1)}%`}`
      + ` · ${f.equity_multiple}× multiple`,
  ];
}
