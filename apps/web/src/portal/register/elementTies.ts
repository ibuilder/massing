/**
 * R24-ELEMENT-CARD ② — model-element ties on a register record, plus the lifecycle card on the
 * four surfaces the audit named (RFI, estimate, pay app, COBie/asset).
 *
 * Lived inline in `register.ts` until that file sat on its size pin with no headroom. The pin asked
 * whether this belonged in a domain module; for "tie GUIDs + maybe mount a card" the answer is yes.
 */
import type { ModuleDef, ModuleRecord } from "../../api/client";
import { mountElementCard } from "../../ui/elementCard";
import { confirmModal } from "../../ui/modal";
import type { PortalHost } from "../portal";

/** The four remaining call sites. Other modules still get the tie row; they do not get a strip. */
export const ELEMENT_CARD_MODULES = new Set([
  "rfi",
  "estimate",
  "owner_invoice",
  "asset_register",
]);

/** Cap so a 4D activity with hundreds of GUIDs cannot mount hundreds of cards. */
export const ELEMENT_CARD_MAX = 8;

export function appendRecordElementTies(
  root: HTMLElement,
  host: PortalHost,
  m: Pick<ModuleDef, "key">,
  r: Pick<ModuleRecord, "element_guids" | "ref">,
  rid: string,
  reload: () => void,
): void {
  const pid = host.projectId()!;
  const guids = r.element_guids ?? [];
  const elHead = document.createElement("div"); elHead.className = "section-title";
  elHead.textContent = `Model elements${guids.length ? ` (${guids.length})` : ""}`;
  root.appendChild(elHead);
  const elRow = document.createElement("div"); elRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
  const tagBtn = document.createElement("button"); tagBtn.className = "tool-btn";
  tagBtn.textContent = "🔗 Tie current 3D selection";
  tagBtn.title = "Add the element selected in the 3D model to this record";
  tagBtn.onclick = async () => {
    const g = host.selectedGuid();
    if (!g) { host.setStatus("select an element in the 3D model first (Model workspace)"); return; }
    try {
      const res = await host.api.tagElements(pid, m.key, rid, [g], "add");
      host.setStatus(`tied ${res.count} element${res.count === 1 ? "" : "s"}`);
      reload();
    } catch (e) { host.setStatus(`tie failed: ${(e as Error).message}`); }
  };
  elRow.appendChild(tagBtn);
  if (guids.length) {
    const showBtn = document.createElement("button"); showBtn.className = "tool-btn"; showBtn.textContent = "👁 Show in model";
    showBtn.onclick = () => host.onSelectGuids(guids); elRow.appendChild(showBtn);
    const clrBtn = document.createElement("button"); clrBtn.className = "tool-btn"; clrBtn.textContent = "✕ Clear ties";
    clrBtn.onclick = async () => {
      if (!(await confirmModal(`Untie all ${guids.length} elements from ${r.ref}?`, "", "Untie", true))) return;
      try { await host.api.tagElements(pid, m.key, rid, [], "set"); reload(); }
      catch (e) { host.setStatus(`clear failed: ${(e as Error).message}`); }
    };
    elRow.appendChild(clrBtn);
  }
  root.appendChild(elRow);
  if (m.key === "schedule_activity" && guids.length) {
    const hint = document.createElement("div"); hint.className = "meta";
    hint.textContent = "These elements complete on this activity's finish date in the 4D scrub.";
    root.appendChild(hint);
  }

  if (!ELEMENT_CARD_MODULES.has(m.key) || !guids.length) return;
  const cards = document.createElement("div");
  cards.style.cssText = "display:flex;flex-direction:column;gap:8px;margin:6px 0";
  root.appendChild(cards);
  for (const g of guids.slice(0, ELEMENT_CARD_MAX)) {
    const hostEl = document.createElement("div");
    hostEl.className = "dash-card";
    hostEl.style.cssText = "padding:8px";
    cards.appendChild(hostEl);
    void mountElementCard(hostEl, host.api, pid, g);
  }
  if (guids.length > ELEMENT_CARD_MAX) {
    const more = document.createElement("div"); more.className = "meta";
    more.textContent = `Showing ${ELEMENT_CARD_MAX} of ${guids.length} tied elements.`;
    root.appendChild(more);
  }
}
