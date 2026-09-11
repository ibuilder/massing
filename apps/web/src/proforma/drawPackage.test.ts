import { describe, it, expect } from "vitest";
import { drawPackageLines, type DrawPackageReply } from "./drawPackage";

const dp = (o: Partial<DrawPackageReply> = {}): DrawPackageReply => ({
  sov_lines_created: 12,
  g702: { line8_current_payment_due: 412_500.4 },
  g703_totals: { scheduled: 8_200_000, completed: 3_150_000, balance: 5_050_000, retainage: 157_500 },
  forecast_returns: { equity_irr: 0.1847, equity_multiple: 1.92 },
  ...o,
});

describe("drawPackageLines", () => {
  it("reports the payment due and the schedule of values it was computed from", () => {
    const [due, g703] = drawPackageLines(dp());
    expect(due).toContain("SOV 12 lines");
    expect(due).toContain("$412,500");
    // Retainage is the line owners and subs argue about; it must be on screen, not only in the PDF.
    expect(g703).toContain("$3,150,000 completed of $8,200,000 scheduled");
    expect(g703).toContain("$157,500 retained");
    expect(g703).toContain("$5,050,000 to finish");
  });

  it("reports the RE-FORECAST returns, which is what the bridge exists to produce", () => {
    expect(drawPackageLines(dp())[2]).toBe(
      "Forecast with these actuals: equity IRR 18.5% · 1.92× multiple");
  });

  it("says n/a for an unsolvable IRR, never 0%", () => {
    // `equity_irr` is null when the cash flows do not support a rate. Printing 0% there reports a
    // specific and wrong answer on the screen a draw request is assembled from.
    expect(drawPackageLines(dp({ forecast_returns: { equity_irr: null, equity_multiple: 0.8 } }))[2])
      .toContain("equity IRR n/a");
  });

  it("does not swallow a legitimate zero IRR", () => {
    expect(drawPackageLines(dp({ forecast_returns: { equity_irr: 0, equity_multiple: 1 } }))[2])
      .toContain("equity IRR 0.0%");
  });

  it("survives a G702 with no payment-due line", () => {
    // `g702` is a loose number map; an app with nothing due omits the key rather than sending 0.
    expect(drawPackageLines(dp({ g702: {} }))[0]).toContain("$0");
  });

  it("agrees with itself in the singular", () => {
    expect(drawPackageLines(dp({ sov_lines_created: 1 }))[0]).toContain("SOV 1 line ");
  });
});
