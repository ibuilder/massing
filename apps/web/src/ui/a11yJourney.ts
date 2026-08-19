/**
 * R39-A11Y-JOURNEYS ② — keyboard journeys for the seven rooms.
 *
 * Attribute sweeps already ran. A keyboard user does not experience an attribute: they Tab to the
 * thing they came to do, operate it, and land somewhere they can keep going. This file is that
 * journey as code — one primary per room, the same focusable query the rest of the app uses, and
 * a check that focus did not fall on `document.body`.
 *
 * Design has no portal home (`ROOM_HOME.design` is null — the viewer *is* the room). Its primary
 * is the Design tab. The other six mark `[data-room-primary]` on the landing the room already
 * renders.
 */
import { ROOM_IDS } from "../shell/spine";

/** Native + explicit tab stops. Matches `ui/result.ts` / `ui/modal.ts`. */
export const FOCUSABLE_SEL =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export type RoomId = (typeof ROOM_IDS)[number];

export interface RoomPrimary {
  room: RoomId;
  /** Query from the room chrome (tablist + pane). */
  selector: string;
}

/**
 * One primary per room. Labels are not duplicated here — the renderer owns the visible verb so a
 * test that copied the string would agree with itself while the button drifted.
 */
export const ROOM_PRIMARY: Record<RoomId, RoomPrimary> = {
  design: { room: "design", selector: '[data-room="design"]' },
  planning: { room: "planning", selector: '[data-room-primary="planning"]' },
  schedule: { room: "schedule", selector: '[data-room-primary="schedule"]' },
  cost: { room: "cost", selector: '[data-room-primary="cost"]' },
  deal: { room: "deal", selector: '[data-room-primary="deal"]' },
  work: { room: "work", selector: '[data-room-primary="work"]' },
  operate: { room: "operate", selector: '[data-room-primary="operate"]' },
};

export function markPrimary(el: HTMLElement, room: RoomId): void {
  el.dataset.roomPrimary = room;
}

export function focusables(root: ParentNode): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE_SEL)].filter((el) => isOperable(el));
}

/** Hidden, `inert`, or `aria-hidden` is not a stop. `offsetParent` is a layout lie in jsdom. */
export function isOperable(el: HTMLElement): boolean {
  if (el.hidden || el.getAttribute("aria-hidden") === "true") return false;
  if (el.closest("[hidden], [inert], [aria-hidden='true']")) return false;
  const tn = el.tagName;
  if (tn === "BUTTON" || tn === "SELECT" || tn === "TEXTAREA" || tn === "INPUT") {
    if ((el as HTMLButtonElement).disabled) return false;
  }
  return true;
}

/** Tab to the next operable control inside `root`. Returns the newly focused node. */
export function tabForward(root: ParentNode): HTMLElement | null {
  const items = focusables(root);
  if (!items.length) return null;
  const active = document.activeElement;
  const i = items.findIndex((el) => el === active);
  const next = i < 0 ? items[0]! : items[(i + 1) % items.length]!;
  next.focus();
  return next;
}

export function tabReach(root: ParentNode, target: HTMLElement): boolean {
  const items = focusables(root);
  if (!items.includes(target)) return false;
  const start = items[0]!;
  start.focus();
  if (document.activeElement === target) return true;
  for (let n = 0; n < items.length; n++) {
    if (tabForward(root) === target) return true;
  }
  return false;
}

/** Enter / Space activate a control the way a keyboard user does — then click for jsdom. */
export function operate(el: HTMLElement): void {
  el.focus();
  el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
  el.click();
}

/**
 * Focus after operate is sane when it is still a real control the user can keep using:
 * inside the room chrome, or inside an opened dialog / region that the action created.
 */
export function focusIsSane(root: ParentNode): boolean {
  const el = document.activeElement;
  if (!(el instanceof HTMLElement)) return false;
  if (el === document.body || el === document.documentElement) return false;
  if (!isOperable(el)) return false;
  if (root.contains(el)) return true;
  if (el.closest('[role="dialog"], [role="region"]')) return true;
  return false;
}
