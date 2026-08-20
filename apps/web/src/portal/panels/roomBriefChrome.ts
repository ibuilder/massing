/**
 * Shared landing chrome for R36-ROOM-BRIEFS.
 *
 * Each room still owns its three questions and its engines. This file only builds the three
 * cards so a fourth room does not copy the markup a third time.
 */
import type { RoomId } from "../../ui/a11yJourney";
import { markPrimary } from "../../ui/a11yJourney";
import type { PanelContext } from "../panelContext";

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

/** Open a register from a room landing. No-ops when the catalog has not loaded that module. */
export function openRoomModule(ctx: PanelContext, moduleKey: string): void {
  const m = ctx.mods.find((x) => x.key === moduleKey);
  if (!m) return;
  ctx.activeKey = moduleKey;
  void ctx.openModule(m);
  ctx.buildNav();
}

/**
 * The room's one keyboard primary — a real button on a brief card, not a clickable card.
 * Exactly one of these should exist per room landing.
 */
export function briefPrimary(
  card: BriefCard,
  room: RoomId,
  label: string,
  onClick: () => void,
): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "tool-btn";
  b.style.marginTop = "6px";
  b.textContent = label;
  b.onclick = onClick;
  markPrimary(b, room);
  card.root.appendChild(b);
  return b;
}
