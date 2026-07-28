/**
 * CSV / TSV export of the markup list — the report an estimator or a PM actually forwards.
 *
 * Exports the *filtered* set by default, because "export what I'm looking at" is the only behaviour
 * that doesn't surprise people after they've spent a minute narrowing a filter.
 */
import { formatQuantity } from "../core/units";
import type { Annotation } from "../core/types";

export interface CsvOptions {
  delimiter?: "," | "\t" | ";";
  /** Render imperial lengths as feet-and-inches instead of decimal. */
  feetInches?: boolean;
  /** Columns, in order. Omit for the default set. */
  columns?: CsvColumn[];
  /** Sheet number lookup, so rows carry `A-201` rather than `page 7`. */
  sheetNumber?: (page: number) => string | undefined;
}

export interface CsvColumn {
  header: string;
  value: (a: Annotation, ctx: { feetInches: boolean; sheetNumber?: (p: number) => string | undefined }) => string | number;
}

export const DEFAULT_COLUMNS: CsvColumn[] = [
  { header: "ID", value: (a) => a.id },
  { header: "Sheet", value: (a, c) => c.sheetNumber?.(a.page) ?? a.sheetId },
  { header: "Page", value: (a) => a.page },
  { header: "Type", value: (a) => a.kind },
  { header: "Subject", value: (a) => a.subject ?? "" },
  { header: "Comment", value: (a) => a.note ?? a.text ?? "" },
  { header: "Status", value: (a) => a.status },
  { header: "Priority", value: (a) => a.priority ?? "" },
  { header: "Discipline", value: (a) => a.discipline ?? "" },
  { header: "Trade", value: (a) => a.trade ?? "" },
  { header: "Labels", value: (a) => (a.labels ?? []).join("; ") },
  { header: "Author", value: (a) => a.author },
  { header: "Organisation", value: (a) => a.org ?? "" },
  { header: "Created", value: (a) => a.createdAt },
  { header: "Updated", value: (a) => a.updatedAt ?? "" },
  { header: "Quantity", value: (a, c) => (a.quantity ? formatQuantity(a.quantity, { feetInches: c.feetInches }) : "") },
  // The raw number and unit are separate columns too, so the file is usable in a spreadsheet
  // formula without anyone having to parse `12'-6"` back into a number.
  { header: "Value", value: (a) => (a.quantity ? round(a.quantity.value, 4) : "") },
  { header: "Unit", value: (a) => a.quantity?.unit ?? "" },
  { header: "Assembly", value: (a) => a.quantity?.assembly ?? "" },
  { header: "Replies", value: (a) => a.replies?.length ?? 0 },
  { header: "Issue", value: (a) => a.links?.issueId ?? "" },
  { header: "Spec", value: (a) => (a.links?.spec ? `${a.links.spec.section}${a.links.spec.clause ? ` §${a.links.spec.clause}` : ""}` : "") },
  { header: "IFC GUIDs", value: (a) => (a.links?.ifcGuids ?? []).join("; ") },
  { header: "Revision", value: (a) => a.revision?.rev ?? "" },
  { header: "Provenance", value: (a) => a.provenance?.archive ?? "" },
  { header: "Confidence", value: (a) => a.provenance?.confidence ?? "" },
];

export function toCsv(annots: readonly Annotation[], options: CsvOptions = {}): string {
  const d = options.delimiter ?? ",";
  const cols = options.columns ?? DEFAULT_COLUMNS;
  const ctx = {
    feetInches: options.feetInches ?? true,
    ...(options.sheetNumber ? { sheetNumber: options.sheetNumber } : {}),
  };
  const rows = [
    cols.map((c) => c.header),
    ...annots.map((a) => cols.map((c) => String(c.value(a, ctx)))),
  ];
  return rows.map((r) => r.map((cell) => quote(cell, d)).join(d)).join("\r\n");
}

/**
 * A takeoff roll-up: one row per assembly/subject, with a summed quantity per unit. Mixed units in
 * one bucket are reported as separate rows rather than silently added together.
 */
export function toTakeoffCsv(annots: readonly Annotation[], options: CsvOptions = {}): string {
  const d = options.delimiter ?? ",";
  const buckets = new Map<string, { item: string; unit: string; count: number; total: number }>();
  for (const a of annots) {
    if (!a.quantity) continue;
    const item = a.quantity.assembly || a.subject || a.kind;
    // Bucket per item *and* unit, separated by a character that cannot occur in either.
    const key = `${item}\u0000${a.quantity.unit}`;
    const b = buckets.get(key) ?? { item, unit: a.quantity.unit, count: 0, total: 0 };
    b.count++;
    b.total += a.quantity.value;
    buckets.set(key, b);
  }
  const rows = [
    ["Item", "Unit", "Count", "Total", "Formatted"],
    ...[...buckets.values()]
      .sort((a, b) => a.item.localeCompare(b.item) || a.unit.localeCompare(b.unit))
      .map((b) => [
        b.item, b.unit, String(b.count), String(round(b.total, 4)),
        formatQuantity({ value: b.total, unit: b.unit }, { feetInches: options.feetInches ?? true }),
      ]),
  ];
  return rows.map((r) => r.map((cell) => quote(cell, d)).join(d)).join("\r\n");
}

/** RFC 4180 quoting, plus a guard against spreadsheet formula injection. */
function quote(value: string, delimiter: string): string {
  let v = value;
  if (/^[=+\-@\t\r]/.test(v)) v = `'${v}`;
  if (v.includes(delimiter) || v.includes('"') || /[\r\n]/.test(v)) return `"${v.replace(/"/g, '""')}"`;
  return v;
}

const round = (n: number, dp: number): number => {
  const k = 10 ** dp;
  return Math.round(n * k) / k;
};
