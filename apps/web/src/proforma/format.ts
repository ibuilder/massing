/** Formatting shared by the proforma tabs — split out of proforma.ts with the tab extraction so
 *  the coordinator and the extracted tab modules agree on one money/percent rendering. */
export const money = (n: number) => "$" + Math.round(n).toLocaleString();
export const pct = (n: number | null) => (n == null ? "n/a" : (n * 100).toFixed(1) + "%");
