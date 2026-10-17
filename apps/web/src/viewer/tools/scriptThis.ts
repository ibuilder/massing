import type { ApiClient } from "../../api/client";
import { escapeHtml, withLoading } from "../../ui/feedback";
import { resultNote } from "../../ui/result";

/**
 * "Script this" — the plain-English → recipe-plan window, out of `app.ts`.
 *
 * **The extraction is what pays for the fix.** BATCH-DARK replaces three per-step loops with one
 * `/edit/batch` call, and the explanation of why is longer than the code it replaces;
 * `services/api/test_file_sizes.py` pins `app.ts` at an exact size and it sat exactly on that pin,
 * so the change was refused until something left. This block is the right thing to move on the
 * merits too: 54 contiguous lines, one entry point, and it reads no `app.ts` state it does not also
 * finish with — which is the same test `projectPanel.ts` and `repairPanel.ts` applied to theirs.
 *
 * `selectedGuid` and `activeStorey` cross as **accessors, not values**. Both are `let`s in `app.ts`
 * that change as the user picks and switches storey, and this window is open across those changes:
 * a value copied at construction would plan every command against whatever was selected when the
 * window opened. Per the ref rule in `projectPanel.ts`'s note, state this code only CONSULTS gets a
 * getter — it writes neither, so neither needs a ref.
 */
export interface ScriptThisDeps {
  api: ApiClient;
  projectId: string;
  container: HTMLElement;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  showResult: (title: string, render: (body: HTMLElement) => void) => void;
  /** Read at command time, not at open time — see the note above. */
  selectedGuid: () => string | null;
  activeStorey: () => string | null;
  waitForPublish: (pid: string) => Promise<string>;
  loadProjectModel: () => Promise<unknown>;
  reloadModelPins: () => Promise<unknown>;
}

export function scriptThisTool(d: ScriptThisDeps): void {
  const { api, projectId, container, notify, showResult } = d;
  showResult("Script this — the recipe interface", (body) => {
    body.appendChild(resultNote("Every tool here is a <b>GUID-safe recipe</b> — the same verbs the AI "
      + "command bar and the sandboxed <code>ifcopenshell</code> runner drive. Type what you want in plain "
      + "English to see the exact recipe plan it maps to, then apply it. (Advanced: run sandboxed code via "
      + "the rail's Build → 🔧 Advanced → ⚡ Run IFC code.)", ""));
    const inp = document.createElement("input"); inp.type = "text"; inp.className = "portal-filter";
    inp.placeholder = "✨ e.g. add a 3m wall from 0,0 to 5,0";
    inp.style.cssText = "width:100%;padding:8px;box-sizing:border-box;margin-bottom:6px";
    const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Interpret →";
    const out = document.createElement("div"); out.style.marginTop = "8px";
    const run = async () => {
      const text = inp.value.trim(); if (!text) return;
      out.innerHTML = `<div class="meta">Interpreting…</div>`;
      let res;
      try {
        const guid = d.selectedGuid();
        const storey = d.activeStorey();
        res = await api.aiAuthor(projectId, text,
          { selected_guids: guid ? [guid] : undefined, active_storey: storey || undefined });
      } catch (e) { out.innerHTML = `<div class="meta">command failed: ${escapeHtml((e as Error).message)}</div>`; return; }
      if (res.needs_clarification) { out.innerHTML = `<div class="meta">${escapeHtml(res.needs_clarification)}</div>`; return; }
      out.innerHTML = "";
      out.appendChild(resultNote(`Maps to <b>${res.plan.length}</b> GUID-safe recipe step(s):`, ""));
      const pre = document.createElement("pre");
      pre.style.cssText = "white-space:pre-wrap;font-size:11px;background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:8px;overflow:auto";
      pre.textContent = res.plan.map((s, i) => `${i + 1}. ${s.recipe}(${JSON.stringify(s.params)})`).join("\n") || "(no steps)";
      out.appendChild(pre);
      if (res.plan.length && !res.plan.some((s) => s.destructive)) {
        const apply = document.createElement("button"); apply.className = "file-btn";
        apply.textContent = `✓ Apply ${res.plan.length} step(s)`; apply.style.marginTop = "6px";
        apply.onclick = () => withLoading(container, "authoring + republishing", async () => {
          // BATCH-DARK. This looped `editIfc` once per step, which is the opposite of every
          // property `/edit/batch` was built for — and that route's own docstring names THIS caller
          // as its reason for existing: *"so a multi-step NL command undoes as a single step"*. The
          // loop gave N undo entries for one typed sentence, N model opens, no lock check between
          // steps, and — the part a user pays for — a failure at step k left the k-1 earlier steps
          // written to the model while the message said only "apply failed". *A partial write
          // reported as a failure is worse than a failure, because the reader believes nothing
          // happened.* One call now, all-or-nothing, so the message can say so truthfully.
          try {
            await api.editBatch(projectId,
              res!.plan.map((s) => ({ recipe: s.recipe, params: s.params })), true);
            const st = await d.waitForPublish(projectId);
            if (st === "done") {
              await d.loadProjectModel(); await d.reloadModelPins(); notify("applied", "success");
            } else notify(`applied — publish ${st}`, st === "error" ? "error" : "info");
          } catch (e) {
            notify(`command failed — nothing was applied: ${(e as Error).message}`, "error");
          }
        });
        out.appendChild(apply);
      }
    };
    go.onclick = () => void run();
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") void run(); });
    body.append(inp, go, out); inp.focus();
  });
}
