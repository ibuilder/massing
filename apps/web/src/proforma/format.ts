/** Formatting shared by the proforma tabs — split out of proforma.ts with the tab extraction so
 *  the coordinator and the extracted tab modules agree on one money/percent rendering.
 *
 *  R24-CHARTS-GRAMMAR ②: `money` was a second implementation — `"$" + Math.round(n).toLocaleString()`,
 *  which renders a loss as `$-1,000` with the currency mark on the wrong side of the minus. It is
 *  now the app-wide one, re-exported under the name the proforma tabs already import so nothing
 *  downstream had to change. Agreeing with itself was never the problem; agreeing with the rest of
 *  the app was. */
export { usd as money } from "../ui/charts";
export const pct = (n: number | null) => (n == null ? "n/a" : (n * 100).toFixed(1) + "%");
