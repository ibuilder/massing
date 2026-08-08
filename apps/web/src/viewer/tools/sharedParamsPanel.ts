import type { ApiClient } from "../../api/client";
import { confirmModal } from "../../ui/modal";
import { resultNote, showResult } from "../../ui/result";
import { escapeHtml, toast, withLoading } from "../../ui/feedback";

/**
 * The project's shared-parameter registry — read it, and retire one definition from it.
 *
 * EXTRACTED FROM `qaSection.ts` RATHER THAN RAISING ITS SIZE PIN. That file is where every reach fix
 * has landed; it was pinned at 1,373 lines earlier the same day precisely so the next addition would
 * have to answer "should this live somewhere else?" instead of quietly growing it. Adding the retire
 * flow took it to 1,439 and the pin fired on the change that added it, which is the ratchet working
 * on its author. Shared parameters are a self-contained feature with their own read, their own write
 * and their own failure modes, so the answer here is plainly yes.
 *
 * WHY THE WRITE IS SHAPED THE WAY IT IS. `saveSharedParams` is a `PUT` and `PUT` REPLACES THE WHOLE
 * REGISTRY — the server validates and stores exactly the list it is handed. So the dangerous version
 * of this feature is the OBVIOUS one: a form that saves the rows it happens to be holding silently
 * deletes every definition it does not know about, and every model in the project is authored
 * against that standard. This is the endpoint R41-REACH-WRITES exists to stop a reach sweep wiring
 * with the same three lines as a read-only one.
 *
 * The payload is therefore always the FULL list this dialog just read, minus exactly one entry.
 * There is no partial save and no second copy of "current state" that could drift: the retire button
 * cannot express anything except "everything I was shown, without this row".
 */

/** One definition, matching what `GET /projects/{pid}/shared-params` returns. The retire flow
 *  round-trips the whole list back through `PUT`, so read and write share one shape. */
export type SharedParamDef = {
  name: string; pset: string; ptype: string; applies_to: string[];
  label: string; description: string;
};

export type SharedParamsDeps = {
  api: ApiClient;
  pid: string;
  /** The rail's one-line status slot. */
  out: HTMLElement;
  /** The element `withLoading` covers while a request is in flight. */
  container: HTMLElement;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
};

export function sharedParamsButton(deps: SharedParamsDeps): HTMLButtonElement {
  const { api, pid, out, container, toolBtn2 } = deps;

  const render = (r: { params: SharedParamDef[]; max: number }) => {
    out.textContent = `${r.params.length} parameter(s)`;
    showResult("Shared parameters", (body) => {
      if (!r.params.length) {
        body.appendChild(resultNote("No shared parameters defined for this project.", ""));
        return;
      }
      body.appendChild(resultNote(`<b>${r.params.length}</b> of a maximum ${r.max}.`, ""));
      for (const x of r.params) {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:8px;align-items:baseline;justify-content:space-between;"
          + "padding:4px 0;border-bottom:1px solid var(--hairline,rgba(128,128,128,.2))";
        const txt = document.createElement("div");
        // `applies_to` is a LIST of IFC classes. Joined explicitly — handing the array to escapeHtml
        // renders JS's comma-join with no spaces, which reads as one malformed class name.
        txt.innerHTML = `<b>${escapeHtml(x.pset)}.${escapeHtml(x.name)}</b>`
          + `<div class="meta">${escapeHtml(x.ptype)} · ${escapeHtml(x.applies_to.join(", "))}`
          + `${x.description ? " — " + escapeHtml(x.description) : ""}</div>`;

        const rm = document.createElement("button");
        rm.className = "file-btn";
        rm.textContent = "Retire";
        rm.title = "Remove this definition from the project standard";
        rm.onclick = async () => {
          const remaining = r.params.filter((y) => !(y.pset === x.pset && y.name === x.name));
          // Refuse rather than guess if the identity is not unique. Sending a list that drops TWO
          // definitions when the user asked to drop one is exactly the silent loss this file is
          // shaped to prevent, and pset+name is the server's own uniqueness key.
          if (remaining.length !== r.params.length - 1) {
            toast(`Cannot identify ${x.pset}.${x.name} uniquely — not changing the standard.`, "error");
            return;
          }
          // The confirmation names WHAT IS LOST and what survives. "Are you sure?" tells a reader
          // nothing they can weigh; the count and the consequence do.
          const ok = await confirmModal(
            `Retire ${x.pset}.${x.name}?`,
            `This rewrites the project standard: ${remaining.length} definition(s) will remain `
            + `(was ${r.params.length}).\n\nElements already carrying this property keep their values — `
            + `the definition stops appearing as a schedule column and stops being part of what new `
            + `work is authored against.`,
            "Retire", true);
          if (!ok) return;

          rm.disabled = true;
          try {
            await api.saveSharedParams(pid, remaining);
          } catch (e) {
            rm.disabled = false;
            toast(`Not retired: ${(e as Error).message}`, "error");
            return;
          }
          // Re-READ rather than assume. The server validates and may normalise what it stored, so
          // the count shown next must come from the registry, not from our own arithmetic.
          try {
            const after = await api.sharedParams(pid);
            toast(`Retired ${x.pset}.${x.name} — ${after.params.length} remain`, "success");
            render(after);
          } catch {
            toast("Retired, but the registry could not be re-read — reopen to confirm.", "error");
          }
        };
        row.append(txt, rm);
        body.appendChild(row);
      }
    });
  };

  return toolBtn2("📐 Shared parameters (project standard)",
    () => withLoading(container, "Reading shared parameters", async () => {
      let r;
      try { r = await api.sharedParams(pid); }
      catch (e) { toast((e as Error).message, "error"); return; }
      render(r);
    }));
}
