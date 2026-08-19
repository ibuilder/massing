/**
 * Shared landing chrome for R36-ROOM-BRIEFS.
 *
 * Each room still owns its three questions and its engines. This file only builds the three
 * cards so a fourth room does not copy the markup a third time.
 */
export type BriefQuestion = { key: string; title: string };

export type BriefCard = { root: HTMLElement; body: HTMLElement };

export function card(title: string): BriefCard {
  const root = document.createElement("div");
  root.className = "dash-card";
  root.style.cssText = "flex:1 1 220px;min-width:200px;margin:0";
  const h = document.createElement("div");
  h.className = "section-title";
  h.style.margin = "0 0 4px";
  h.textContent = title;
  const body = document.createElement("div");
  body.className = "meta";
  body.textContent = "Loading…";
  root.append(h, body);
  return { root, body };
}

/** A failed engine is a reason. Never leave the loading text, never invent a zero. */
export function fail(body: HTMLElement, reason: string): void {
  body.dataset.unavailable = "1";
  body.textContent = reason;
}

export function mountBrief(
  datasetName: string,
  questions: readonly BriefQuestion[],
): { wrap: HTMLElement; byKey: Record<string, BriefCard> } {
  const wrap = document.createElement("div");
  wrap.dataset[datasetName] = "1";
  wrap.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px";
  const byKey = Object.fromEntries(
    questions.map((q) => {
      const c = card(q.title);
      c.root.dataset.brief = q.key;
      wrap.appendChild(c.root);
      return [q.key, c] as const;
    }),
  );
  return { wrap, byKey };
}
