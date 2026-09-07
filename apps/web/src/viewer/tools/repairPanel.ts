import { type ApiClient } from "../../api/client";
import type { ModelIdMap } from "../modelIds";
import { resultNote, showResult } from "../../ui/result";
import { escapeHtml } from "../../ui/feedback";
import { SelectionSets } from "../selectionSets";

/**
 * The two REPAIR tools, out of `qaSection.ts`.
 *
 * ## Why these two are one module
 *
 * `docs/roadmap.md` filed four recipes under *"the diagnosis ships, the repair does not"*. Checked
 * against the SCREEN rather than the server, it was right about one of the four — and the two errors
 * it made are the two controls in this file.
 *
 * **Model cleanup was never the gap it was filed as.** The *Purge* button below has shipped all
 * along. It POSTs `row.recipe` — a name the SERVER sent, out of `ifcpatch_lib.scan` — so the recipe
 * name is a literal only inside the engine, and `services/api/test_recipe_reach.py` (which excludes
 * the engine as a catalog) reported both purges as reachable by nothing. *A dispatch by value has no
 * name to grep.* That gate now reads the scan's RESPONSE as a third reach source.
 *
 * **Wall joins was the opposite error.** `GET /model/wall-joins` and `api.wallJoins` both existed and
 * neither was on screen — the client method sat on the uncalled-method ratchet in
 * `apps/web/src/api/clientCallers.test.ts` with no caller anywhere. *A route and a client method are
 * two thirds of a feature, and counting either one reports it as shipped.*
 *
 * ## Why a module rather than two more blocks in `qaSection.ts`
 *
 * That file was at **exactly** its `services/api/test_file_sizes.py` pin (1,334) with zero headroom,
 * and the wall-joins tool is 80 lines. The ratchet refused, which is the outcome it exists for: its
 * own note records the same thing happening to the R41 yaw fit, where *"the panel was extracted
 * instead"*. Taking the cleanup tool along is what pays for the addition rather than merely
 * relocating it — and the two belong together on the merits, being the only two controls in the app
 * that repair the model rather than report on it.
 *
 * **This file is listed in `SECTION_SOURCES` in `apps/web/src/viewer/toolsSplit.test.ts`.** That test
 * reads the section sources as text to check no control changed sides or vanished, so a control moved
 * to a file it does not read looks exactly like a deleted one. `🧹 Model cleanup (maintenance)` is in
 * its frozen inventory; forgetting the list entry turns it red rather than silent.
 */
export interface RepairDeps {
  api: ApiClient;
  pid: string;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  selectMap: (map: ModelIdMap | null, opts?: { guid?: string; fit?: boolean }) => Promise<void>;
  sets: SelectionSets;
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string,
                    previewId?: string | null) => Promise<{ applied: boolean; refused: boolean }>;
}

/** AUTH-CONSTRAINTS ③ — detect L/T wall joins and butt-join them. */
export function wallJoinsButton(d: RepairDeps): HTMLButtonElement {
  const { api, pid, toolBtn2, selectMap, sets, authorAndReload } = d;
  // AUTH-CONSTRAINTS ③ — wall joins, and NEITHER half of it was on screen.
  //
  // Walls are authored to their CENTRELINES, so an L or a T meeting leaves the corner open or
  // the stub running through the other wall: right as a diagram, wrong as geometry, and it is
  // what a takeoff and a clash run both read. `wall_joins.find` detects them; the
  // `resolve_wall_joins` recipe butt-joins them.
  //
  // `docs/roadmap.md` filed this under *"the diagnosis ships, the repair does not"*. The
  // diagnosis shipped as a ROUTE and a CLIENT METHOD — `api.wallJoins` sat on the uncalled-method
  // ratchet in `apps/web/src/api/clientCallers.test.ts` with no caller anywhere in the app. *A
  // route and a client method are two thirds of a feature, and counting either one reports it
  // as shipped.* The same conflation the reach gate exists to catch, one layer up from the
  // recipe.
  return toolBtn2("📐 Wall joins (open corners / stubs)", () => {
    showResult("Wall joins — detect and butt-join", (body) => {
      body.appendChild(resultNote("Walls are authored to their <b>centrelines</b>, so an L or T meeting "
        + "leaves the corner open or the stub crossing through. Butt-joining trims the stub back to the "
        + "through wall's face, and closes the outside of an L. GUID-stable and idempotent — pins, RFIs "
        + "and clashes keyed by GlobalId survive.", ""));
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0";
      const tolLbl = document.createElement("span"); tolLbl.className = "meta"; tolLbl.textContent = "tolerance (m)";
      const tolI = document.createElement("input");
      tolI.className = "portal-filter"; tolI.type = "number";
      tolI.step = "0.005"; tolI.min = "0.005"; tolI.max = "0.5"; tolI.value = "0.05";
      tolI.style.cssText = "width:90px;font-size:12px";
      tolI.title = "How close two wall ends must be to count as a join (metres)";
      const scanBtn = document.createElement("button"); scanBtn.className = "mini-btn on"; scanBtn.textContent = "⟳ Scan";
      const fixBtn = document.createElement("button"); fixBtn.className = "mini-btn"; fixBtn.textContent = "🔨 Butt-join all";
      fixBtn.disabled = true;
      row.append(tolLbl, tolI, scanBtn, fixBtn);
      const out2 = document.createElement("div"); out2.style.cssText = "margin-top:6px;max-height:40vh;overflow:auto";
      body.append(row, out2);

      // The route already clamps to [0.005, 0.5]; clamping here too keeps the number the user
      // sees and the number the server used the same, rather than silently differing.
      const tol = () => {
        const v = Number(tolI.value);
        return Number.isFinite(v) ? Math.min(Math.max(v, 0.005), 0.5) : 0.05;
      };

      // **The repair runs at the tolerance of the LIST ON SCREEN, never at whatever the input holds
      // when the button is pressed.** Reading `tol()` again at repair time is a real divergence: scan
      // at 0.05, see three joins, nudge the input to 0.5, press butt-join — and the server resolves
      // at 0.5, trimming walls that were never displayed. *The list is the user's consent, and it is
      // specific to the number it was measured at.* So the accepted scan's tolerance is stored with
      // it, editing the input invalidates the list rather than silently re-scoping the repair, and a
      // slow scan that lands after a newer one has started is discarded instead of overwriting it.
      //
      // This is the same shape as everything else in this PR — what is shown and what is acted on
      // coming apart — found by a reviewer one layer inside the fix for it.
      let scannedTol: number | null = null;      // null = no list on screen the repair may act on
      let scanSeq = 0;                           // guards against an out-of-order scan response
      const invalidate = (why: string) => {
        scannedTol = null;
        fixBtn.disabled = true;
        out2.replaceChildren();
        out2.appendChild(resultNote(why, ""));
      };
      tolI.oninput = () => invalidate("tolerance changed — scan again to see which joins this finds");

      const scan = async () => {
        const seq = ++scanSeq;
        const used = tol();
        out2.replaceChildren(); fixBtn.disabled = true; scannedTol = null;
        out2.appendChild(resultNote("scanning…", ""));
        let r;
        try { r = await api.wallJoins(pid, used); }
        catch (e) {
          if (seq !== scanSeq) return;
          out2.replaceChildren();
          out2.appendChild(resultNote(`scan failed: ${escapeHtml((e as Error).message)}`, "bad"));
          return;
        }
        if (seq !== scanSeq) return;             // a newer scan started; this answer is already stale
        out2.replaceChildren();
        out2.appendChild(resultNote(r.joins.length
          ? `<b>${r.joins.length}</b> open join(s) — ${r.counts.L} L · ${r.counts.T} T, across ${r.wall_count} wall(s)`
          : `No open L/T joins among <b>${r.wall_count}</b> wall(s) at this tolerance.`,
          r.joins.length ? "" : "ok"));
        scannedTol = used;
        fixBtn.disabled = r.joins.length === 0;
        for (const j of r.joins.slice(0, 200)) {
          const line = document.createElement("div");
          line.className = "meta";
          line.style.cssText = "padding:3px 0;border-bottom:1px solid var(--line);cursor:pointer";
          line.innerHTML = `<b>${escapeHtml(j.kind)}</b> at ${j.corner.map((n) => n.toFixed(2)).join(", ")} m`
            + ` — stub <code>${escapeHtml(j.stub)}</code> butts into <code>${escapeHtml(j.through)}</code>`;
          line.title = "Select both walls";
          line.onclick = async () => { await selectMap(await sets.fromGuids(j.walls)); };
          out2.appendChild(line);
        }
      };
      scanBtn.onclick = () => { void scan(); };
      fixBtn.onclick = async () => {
        const at = scannedTol;
        if (at === null) { invalidate("scan again before repairing — the list is out of date"); return; }
        fixBtn.disabled = true;
        const res = await authorAndReload("resolve_wall_joins", { tol: at }, "wall joins");
        // `authorAndReload` already reports a refusal and a failed republish/reload. What it
        // cannot say is whether the joins are actually gone, so the count the user is owed is
        // re-MEASURED rather than inferred from the request having succeeded.
        if (res.applied) await scan();
        else fixBtn.disabled = false;
      };
      void scan();
    });
  });
}

/** IFCPATCH-LIB — the dry-run cleanup scan, with a Purge per advertised recipe. */
export function modelCleanupButton(d: RepairDeps): HTMLButtonElement {
  const { api, pid, toolBtn2, notify } = d;
  return toolBtn2("🧹 Model cleanup (maintenance)", () => {
    showResult("Model cleanup — maintenance recipes", (body) => {
      body.appendChild(resultNote("Remove dead data an IFC accumulates over its life. A dry-run scan "
        + "shows what each recipe would drop; running it republishes the model (element GUIDs are "
        + "preserved, so pins / RFIs / clashes survive).", ""));
      const out = document.createElement("div"); body.appendChild(out);
      const refresh = async () => {
        out.innerHTML = "<div class=\"meta\">scanning…</div>";
        let s; try { s = await api.modelMaintenance(pid); }
        catch (e) { out.innerHTML = ""; out.appendChild(resultNote(`scan failed: ${escapeHtml((e as Error).message)}`, "")); return; }
        out.innerHTML = "";
        out.appendChild(resultNote(`<b>${s.cleanable}</b> cleanable entity(ies) across ${s.total_entities} total`, s.cleanable ? "" : "ok"));
        for (const r of s.recipes) {
          const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;align-items:center;margin:3px 0";
          const label = document.createElement("span"); label.style.cssText = "flex:1;font-size:12px";
          label.innerHTML = `<b>${escapeHtml(r.label)}</b> — ${r.removable} removable`
            + (r.sample.length ? ` <span class="meta">(${r.sample.slice(0, 5).map(escapeHtml).join(", ")}${r.sample.length > 5 ? "…" : ""})</span>` : "");
          const run = document.createElement("button"); run.className = "mini-btn on"; run.textContent = "Purge"; run.disabled = r.removable === 0;
          run.onclick = async () => {
            run.disabled = true; run.textContent = "purging…";
            try {
              const res = await api.editIfc(pid, r.recipe, {}, true);
              notify(`removed ${res.changed} — model republishing, reload to see it`, "success");
              await refresh();
            } catch (e) { notify((e as Error).message, "error"); run.disabled = false; run.textContent = "Purge"; }
          };
          row.append(label, run); out.appendChild(row);
        }
      };
      void refresh();
    });
  });
}
