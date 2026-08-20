/**
 * R24-ELEMENT-CARD ② — the same card wherever a register names an element.
 *
 * The register already listed `element_guids` (tie / show / clear). A PM on an RFI, an estimator on
 * a line, a billing clerk on an SOV (the G703 / pay-app line — there is no `pay_app` module), or
 * FM on an asset-register row (the in-app COBie Component) saw a GlobalId and nothing else. The
 * lifecycle card already existed; this file is the call site.
 *
 * Cards mount for every tied GUID, not only those four modules — "wherever an element is named".
 * More than {@link ELEMENT_CARD_CAP} is a sample, named as a sample.
 */
import type { ModuleRecord } from "../../api/client";
import type { PortalHost } from "../portal";
import { confirmModal } from "../../ui/modal";
import { mountElementCard } from "../../ui/elementCard";

/** How many lifecycle cards one record will fetch. The rest stay as a count. */
export const ELEMENT_CARD_CAP = 8;

/** Keys a line-item row may use for the IFC GlobalId. First hit wins. */
export const LINE_GUID_KEYS = [
  "guid", "element_guid", "global_id", "GlobalId", "ExtIdentifier",
] as const;

export function lineGuids(rows: unknown): string[] {
  if (!Array.isArray(rows)) return [];
  const out: string[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const rec = row as Record<string, unknown>;
    for (const k of LINE_GUID_KEYS) {
      const v = rec[k];
      if (typeof v === "string" && v.trim()) {
        out.push(v.trim());
        break;
      }
    }
  }
  return out;
}

export function recordElementGuids(r: Pick<ModuleRecord, "element_guids"> & {
  data?: Record<string, unknown> | null;
}): string[] {
  const tied = r.element_guids ?? [];
  const fromLines = lineGuids(r.data?.line_items);
  return [...new Set([...tied, ...fromLines])];
}

export interface TiedElementsOpts {
  pid: string;
  moduleKey: string;
  ref: string;
  record: Pick<ModuleRecord, "id" | "element_guids" | "data">;
  host: PortalHost;
  onReload: () => void;
}

export async function renderTiedElements(opts: TiedElementsOpts): Promise<HTMLElement> {
  const { pid, moduleKey, ref, record, host, onReload } = opts;
  const wrap = document.createElement("div");
  wrap.dataset.tiedElements = "1";
  const guids = recordElementGuids(record);

  const elHead = document.createElement("div");
  elHead.className = "section-title";
  elHead.textContent = `Model elements${guids.length ? ` (${guids.length})` : ""}`;
  wrap.appendChild(elHead);

  const elRow = document.createElement("div");
  elRow.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin:4px 0";
  const tagBtn = document.createElement("button");
  tagBtn.className = "tool-btn";
  tagBtn.textContent = "🔗 Tie current 3D selection";
  tagBtn.title = "Add the element selected in the 3D model to this record";
  tagBtn.onclick = async () => {
    const g = host.selectedGuid();
    if (!g) {
      host.setStatus("select an element in the 3D model first (Model workspace)");
      return;
    }
    try {
      const res = await host.api.tagElements(pid, moduleKey, record.id, [g], "add");
      host.setStatus(`tied ${res.count} element${res.count === 1 ? "" : "s"}`);
      onReload();
    } catch (e) { host.setStatus(`tie failed: ${(e as Error).message}`); }
  };
  elRow.appendChild(tagBtn);
  if (guids.length) {
    const showBtn = document.createElement("button");
    showBtn.className = "tool-btn";
    showBtn.textContent = "👁 Show in model";
    showBtn.onclick = () => host.onSelectGuids(guids);
    elRow.appendChild(showBtn);
    const clrBtn = document.createElement("button");
    clrBtn.className = "tool-btn";
    clrBtn.textContent = "✕ Clear ties";
    clrBtn.onclick = async () => {
      if (!(await confirmModal(`Untie all ${guids.length} elements from ${ref}?`, "", "Untie", true))) return;
      try {
        await host.api.tagElements(pid, moduleKey, record.id, [], "set");
        onReload();
      } catch (e) { host.setStatus(`clear failed: ${(e as Error).message}`); }
    };
    elRow.appendChild(clrBtn);
  }
  wrap.appendChild(elRow);

  if (moduleKey === "schedule_activity" && guids.length) {
    const hint = document.createElement("div");
    hint.className = "meta";
    hint.textContent = "These elements complete on this activity's finish date in the 4D scrub.";
    wrap.appendChild(hint);
  }

  if (guids.length) {
    const shown = guids.slice(0, ELEMENT_CARD_CAP);
    if (guids.length > ELEMENT_CARD_CAP) {
      const note = document.createElement("div");
      note.className = "meta";
      note.textContent = `${guids.length} elements — showing the first ${ELEMENT_CARD_CAP}`;
      wrap.appendChild(note);
    }
    const cards = document.createElement("div");
    cards.dataset.elementCards = "1";
    cards.style.cssText = "display:flex;flex-direction:column;gap:6px;margin:6px 0";
    wrap.appendChild(cards);
    await Promise.all(shown.map(async (g) => {
      const hostEl = document.createElement("div");
      hostEl.className = "dash-card";
      hostEl.dataset.elementCard = g;
      hostEl.style.cssText = "margin:0;padding:8px";
      cards.appendChild(hostEl);
      await mountElementCard(hostEl, host.api, pid, g);
    }));
  }

  return wrap;
}
