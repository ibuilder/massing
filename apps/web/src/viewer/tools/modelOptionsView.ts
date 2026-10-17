import { escapeHtml } from "../../ui/feedback";
import { activateCaveat, branchLine, branchSummary, classDeltaLine, diffHeadline, diffTruncation,
  snapshotCaveat } from "./modelOptionRead";
import type { ModelOptionsDeps } from "./modelOptionsPanel";

/**
 * MODELOPT-DARK — the model-branch controls, behind a dynamic import.
 *
 * **It is a separate module because of the bundle budget, and the budget was right.**
 * `apps/web/src/viewer/tools/*` is the EAGER app-shell chunk, and the panel put the shell at
 * exactly 225.0 KB against a 225 KB budget — `apps/web/scripts/bundle-budget.mjs` refused it. That
 * is the same refusal FIRM-RULES-OPTIONAL records, with the same remedy and the same reason for
 * going further than it looks like it needs to: *"deferring the RENDERING alone left the shell 5
 * bytes over, so the fetch, the toast, the status line and the `showResult` call went too."* So
 * everything but the button itself is here, including the readings — nothing in this file is
 * reachable until somebody clicks.
 *
 * The `ApiClient` type is not imported here at all: the live instance arrives on `deps`, and
 * naming the type would pull the client graph into this chunk for nothing.
 */

export async function renderBranches(out: HTMLElement, d: ModelOptionsDeps): Promise<void> {
  const { api, pid, toolBtn2, notify, waitForPublish, loadProjectModel } = d;
  const refresh = () => renderBranches(out, d);

    out.innerHTML = `<div class="meta">loading branches…</div>`;
    let r;
    try { r = await api.modelOptionList(pid); }
    catch (e) { out.textContent = `branches failed: ${(e as Error).message}`; return; }

    const summary = branchSummary(r);
    out.innerHTML = summary
      ? `<div class="meta">${escapeHtml(summary)}</div>`
      : `<div class="meta">No branches yet — snapshot the working model to make one.</div>`;

    // --- snapshot ---------------------------------------------------------------------------
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:6px;align-items:center;margin:6px 0;flex-wrap:wrap";
    const nameI = document.createElement("input");
    nameI.className = "portal-filter";
    nameI.placeholder = "branch name, e.g. Scheme A — steel frame";
    nameI.style.cssText = "flex:1 1 220px;min-width:0";
    const noteI = document.createElement("input");
    noteI.className = "portal-filter";
    noteI.placeholder = "note (optional)";
    noteI.style.cssText = "flex:1 1 160px;min-width:0";
    const snapB = toolBtn2("📸 Snapshot", () => { void snap(); });
    const caveat = document.createElement("div");
    caveat.className = "meta";
    caveat.style.cssText = "flex:1 1 100%;color:var(--status-warn)";
    // The overwrite warning is shown as the name is TYPED, not after the write: re-using a name
    // replaces that branch head, which is not what "save" usually means.
    nameI.oninput = () => { caveat.textContent = snapshotCaveat(r!, nameI.value) || ""; };
    row.append(nameI, noteI, snapB, caveat);
    out.append(row);

    async function snap(): Promise<void> {
      const name = nameI.value.trim();
      if (!name) { notify("a branch needs a name", "error"); return; }
      snapB.disabled = true;
      try {
        const e = await api.modelOptionSnapshot(pid, name, noteI.value.trim() || undefined);
        notify(`branched as "${e.name}"`, "success");
        nameI.value = ""; noteI.value = ""; caveat.textContent = "";
        await refresh();
      } catch (e) { notify((e as Error).message, "error"); }
      finally { snapB.disabled = false; }
    }

    // --- the branches -----------------------------------------------------------------------
    for (const b of r.options) {
      const card = document.createElement("div");
      card.style.cssText = "border-top:1px solid var(--line);padding:6px 0";
      card.innerHTML = `<div class="meta"${b.current ? ' style="color:var(--status-good)"' : ""}>`
        + `${escapeHtml(branchLine(b))}</div>`;
      const acts = document.createElement("div");
      acts.style.cssText = "display:flex;gap:6px;margin-top:4px;flex-wrap:wrap";
      const detail = document.createElement("div");
      detail.className = "meta";

      const diffB = toolBtn2("⇄ Diff vs current", () => { void showDiff(); });
      async function showDiff(): Promise<void> {
        detail.textContent = "diffing…";
        try {
          const dd = await api.modelOptionDiff(pid, b.slug);
          const lines = [diffHeadline(dd), classDeltaLine(dd), diffTruncation(dd)];
          detail.innerHTML = lines.filter(Boolean)
            .map((l) => `<div class="meta">${escapeHtml(l!)}</div>`).join("");
        } catch (e) { detail.textContent = `diff failed: ${(e as Error).message}`; }
      }

      const actB = toolBtn2("↪ Switch to this branch", () => { void activate(); });
      actB.title = activateCaveat(b);
      async function activate(): Promise<void> {
        actB.disabled = true;
        detail.textContent = activateCaveat(b);
        try {
          await api.modelOptionActivate(pid, b.slug);
          // The route republishes, so the viewer has to wait for it and reload — otherwise the
          // switch succeeds server-side and the screen keeps showing the branch you left.
          await waitForPublish(pid, (s) => { detail.textContent = `switching… ${s}`; });
          await loadProjectModel();
          notify(`switched to "${b.name}" — one undo step`, "success");
          await refresh();
        } catch (e) { notify((e as Error).message, "error"); actB.disabled = false; }
      }

      const delB = toolBtn2("🗑 Drop branch", () => { void drop(); });
      async function drop(): Promise<void> {
        // `confirm` is what the rest of the rail uses for a destructive one-click.
        if (!window.confirm(`Drop the branch "${b.name}"? The edit history is untouched.`)) return;
        delB.disabled = true;
        try {
          const res = await api.modelOptionDelete(pid, b.slug);
          notify(res.deleted ? `dropped "${b.name}"` : `"${b.name}" was already gone`, "info");
          await refresh();
        } catch (e) { notify((e as Error).message, "error"); delB.disabled = false; }
      }

      // `current` is where you already are, so switching to it is a no-op the button should not
      // offer — but the diff and the drop still mean something.
      acts.append(diffB);
      if (!b.current && b.available !== false) acts.append(actB);
      acts.append(delB);
      card.append(acts, detail);
      out.append(card);
    }
  }
