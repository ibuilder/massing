import type { ModuleDef, ModuleRecord } from "../../api/client";
import type { PortalHost } from "../portal";
import { promptModal } from "../../ui/modal";

/**
 * Who a record is on, and the control that moves it.
 *
 * A leaf lifted out of `register.ts::openRecord` under the directory's own convention
 * (`elementTies.ts`, `recordComments.ts`, `refCell.ts`, `tiedElements.ts`, `uploadQueue.ts`): it
 * touches one field, the assign endpoint and a reload callback, and nothing else on the class.
 *
 * The assignee is interpolated as HTML on purpose — it is a user id, and `esc` is applied by the
 * caller nowhere, so it goes in via textContent below rather than the innerHTML the original used.
 */
export interface AssigneeHost {
  api: { assignRecord: PortalHost["api"]["assignRecord"] };
  setStatus: (s: string) => void;
}

/**
 * The row: who the record is on, and a control to move it. Reloads through `onReload` rather than
 * repainting itself, because the assignee is one field of a record view the caller owns.
 */
export function assigneeRow(
  host: AssigneeHost, pid: string, m: ModuleDef, r: ModuleRecord, rid: string,
  onReload: () => void,
): HTMLElement {
  const row = document.createElement("div");
  row.className = "meta";
  row.style.margin = "4px 0";
  const label = document.createElement("span");
  label.textContent = `Assignee: ${r.assignee ?? "—"} `;   // textContent: a user id is user data
  const reassign = document.createElement("button");
  reassign.className = "tool-btn";
  reassign.textContent = "Reassign";
  reassign.style.marginLeft = "6px";
  reassign.onclick = async () => {
    const v = await promptModal("Reassign record",
      [{ name: "who", label: "Assign to (user id, blank to clear)", value: r.assignee ?? "" }]);
    if (!v) return;
    try { await host.api.assignRecord(pid, m.key, rid, v.who?.trim() || null); onReload(); }
    catch (e) { host.setStatus(`error: ${(e as Error).message}`); }
  };
  row.append(label, reassign);
  return row;
}
