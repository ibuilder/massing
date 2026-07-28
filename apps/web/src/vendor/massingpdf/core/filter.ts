/**
 * One filter predicate, shared by the overlay, the markup list, the reports and every export.
 *
 * That sharing is deliberate: "export what I'm looking at" is only trustworthy if the thing drawing
 * the sheet and the thing writing the CSV agree on what passes.
 */
import type { Annotation, AnnotFilter } from "./types";

export function matchesFilter(a: Annotation, f: AnnotFilter): boolean {
  if (f.kinds?.length && !f.kinds.includes(a.kind)) return false;
  if (f.status?.length && !f.status.includes(a.status)) return false;
  if (f.discipline?.length && !(a.discipline && f.discipline.includes(a.discipline))) return false;
  if (f.authors?.length && !f.authors.includes(a.author)) return false;
  if (f.pages?.length && !f.pages.includes(a.page)) return false;
  if (f.labels?.length && !f.labels.some((l) => a.labels?.includes(l))) return false;
  if (f.hasIssue !== undefined && Boolean(a.links?.issueId) !== f.hasIssue) return false;
  if (f.since && a.createdAt < f.since) return false;
  if (f.until && a.createdAt > f.until) return false;
  if (f.query) {
    const q = f.query.toLowerCase();
    const hay = [a.subject, a.note, a.text, a.author, a.org, a.trade, ...(a.labels ?? [])]
      .filter(Boolean).join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

/** True when the filter would let everything through — lets the UI show "no filter". */
export function isEmptyFilter(f: AnnotFilter): boolean {
  return !f.kinds?.length && !f.status?.length && !f.discipline?.length && !f.authors?.length
    && !f.pages?.length && !f.labels?.length && f.hasIssue === undefined
    && !f.since && !f.until && !f.query;
}

/** Facet counts for the list panel — how many markups each value would match. */
export function facets(annots: readonly Annotation[]) {
  const count = <T>(pick: (a: Annotation) => T | T[] | undefined) => {
    const m = new Map<T, number>();
    for (const a of annots) {
      const v = pick(a);
      if (v === undefined) continue;
      for (const one of Array.isArray(v) ? v : [v]) m.set(one, (m.get(one) ?? 0) + 1);
    }
    return [...m.entries()].sort((x, y) => y[1] - x[1]);
  };
  return {
    kinds: count((a) => a.kind),
    status: count((a) => a.status),
    discipline: count((a) => a.discipline),
    authors: count((a) => a.author),
    labels: count((a) => a.labels),
    pages: count((a) => a.page),
  };
}
