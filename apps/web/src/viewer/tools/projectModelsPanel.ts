import type { ApiClient } from "../../api/client";
import { confirmModal } from "../../ui/modal";
import { resultNote, showResult } from "../../ui/result";
import { escapeHtml, toast, withLoading } from "../../ui/feedback";

/**
 * The discipline models registered SERVER-side, and the ability to remove one.
 *
 * WHAT THE DELETE ACTUALLY COSTS — this is the whole reason the endpoint sat unwired. It unlinks the
 * IFC from storage and drops the row, with **no reference check of any kind**. Researching what
 * depends on a `ProjectModel` before writing the button changed what the confirmation had to say:
 *
 *   * Federated clash is computed LIVE — there is no stored clash table, so existing results do not
 *     silently go stale. That is the reassuring half.
 *
 *   * But `routers/analysis.py` raises **409 "need >=2 accessible discipline models"**. The clash set
 *     is the project's `source_ifc` plus every registered model whose file still exists. So deleting
 *     the second-to-last model does not DEGRADE federated clash, it TURNS IT OFF — and the user
 *     discovers that the next time they run it, not when they press delete. A confirmation that said
 *     only "are you sure?" would hide the one consequence worth knowing.
 *
 *   * `ViewerLoadTiming.model_id` is a nullable non-FK, so load telemetry survives the delete as rows
 *     pointing at a model id that no longer resolves. Observability, not user work — named here so
 *     the next person does not rediscover it as a mystery.
 *
 * So the confirmation states the remaining count, and says plainly when the delete will disable
 * federated clash. That prediction is computed from the same two inputs the server uses (the
 * project's source IFC + the registry), not guessed.
 */

export type ProjectModelRow = { id: string; discipline: string; created_at: string | null };

export type ProjectModelsDeps = {
  api: ApiClient;
  pid: string;
  out: HTMLElement;
  container: HTMLElement;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
};

export function projectModelsButton(deps: ProjectModelsDeps): HTMLButtonElement {
  const { api, pid, out, container, toolBtn2 } = deps;

  const render = (rows: ProjectModelRow[], hasSourceIfc: boolean) => {
    out.textContent = `${rows.length} registered model(s)`;
    showResult("Registered models", (body) => {
      if (!rows.length) {
        body.appendChild(resultNote("No discipline models registered for this project yet.", ""));
        return;
      }
      // The clash set the SERVER builds: source_ifc (when present) + each registered model. Stated
      // here so the number in the warning below is traceable to the rule that produces the 409.
      const clashSetNow = (hasSourceIfc ? 1 : 0) + rows.length;
      body.appendChild(resultNote(
        `<b>${rows.length}</b> registered · federated clash currently runs across <b>${clashSetNow}</b> `
        + `model(s)${hasSourceIfc ? " (including the project's source IFC)" : ""}. It needs at least two.`, ""));

      for (const m of rows) {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:8px;align-items:baseline;justify-content:space-between;"
          + "padding:4px 0;border-bottom:1px solid var(--hairline,rgba(128,128,128,.2))";
        const txt = document.createElement("div");
        txt.innerHTML = `<b>${escapeHtml(m.discipline || "(no discipline)")}</b>`
          + `<div class="meta">${escapeHtml(m.id)}`
          + `${m.created_at ? " · added " + escapeHtml(m.created_at.slice(0, 10)) : ""}</div>`;

        const del = document.createElement("button");
        del.className = "file-btn";
        del.textContent = "Remove";
        del.title = "Delete this discipline model and its IFC file";
        del.onclick = async () => {
          const after = clashSetNow - 1;
          const breaksClash = after < 2;
          const lines = [
            `The IFC file is deleted from storage. This cannot be undone from the app.`,
            ``,
            `${rows.length - 1} registered model(s) will remain.`,
          ];
          // LEAD WITH THE CONSEQUENCE WHEN THERE IS ONE. A warning appended after the routine text
          // reads as boilerplate; this is the sentence that should change someone's mind.
          if (breaksClash) {
            lines.push(
              ``,
              `⚠ Federated clash will STOP WORKING for this project. It needs at least two accessible `
              + `models and only ${after} would remain — the next run refuses with "need >=2 accessible `
              + `discipline models" rather than returning fewer clashes.`);
          }
          const ok = await confirmModal(
            `Remove ${m.discipline || "this model"}?`, lines.join("\n"),
            breaksClash ? "Remove and disable clash" : "Remove", true);
          if (!ok) return;

          del.disabled = true;
          try {
            await api.deleteProjectModel(pid, m.id);
          } catch (e) {
            del.disabled = false;
            toast(`Not removed: ${(e as Error).message}`, "error");
            return;
          }
          // Re-read both inputs. The registry is the authority on what remains, and re-deriving the
          // clash-set size from a fresh read is what keeps the next confirmation honest.
          try {
            const [fresh, proj] = await Promise.all([api.projectModels(pid), api.project(pid)]);
            toast(`Removed — ${fresh.length} model(s) remain`, "success");
            render(fresh, Boolean(proj.has_source_ifc));
          } catch {
            toast("Removed, but the registry could not be re-read — reopen to confirm.", "error");
          }
        };
        row.append(txt, del);
        body.appendChild(row);
      }
    });
  };

  return toolBtn2("🗃 Registered models (server-side federation)",
    () => withLoading(container, "Listing models", async () => {
      let rows: ProjectModelRow[];
      // Declared without an initialiser: every path below assigns it, and a placeholder `false` here
      // would be a dead store that also happens to be the WRONG default (see the catch).
      let hasSourceIfc: boolean;
      try {
        rows = await api.projectModels(pid);
      } catch (e) { toast((e as Error).message, "error"); return; }
      // A failure here must not block the list — but it MUST NOT be silently treated as "no source
      // IFC" either, because that would understate the clash set and could claim a delete breaks
      // clash when it does not. Assume present on failure: the warning then errs toward not firing,
      // and a missing warning is recoverable where a false one trains people to ignore it.
      try { hasSourceIfc = Boolean((await api.project(pid)).has_source_ifc); }
      catch { hasSourceIfc = true; }
      render(rows, hasSourceIfc);
    }));
}
