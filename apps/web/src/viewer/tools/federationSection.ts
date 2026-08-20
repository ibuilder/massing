import type { ApiClient } from "../../api/client";
import type { LayerManager } from "../../tools/layers";
import { escapeHtml } from "../../ui/feedback";
import { kvTable, resultNote, showResult } from "../../ui/result";

/**
 * R39-DECOMP-VIEWER ⑬ — **model federation and version compare**, out of `app.ts`.
 *
 * The "Data · Models (federation)" group: the federated-model list and the 3D version comparison
 * that overlays two published versions (added green / modified amber).
 *
 * ## Why this group and not the ones beside it
 *
 * ⑫ settled that the renderer-free seam ends there, and it does — for the *annotation* group, which
 * writes to `let` captures and mutates the live scene. This group is a different case that the same
 * sentence was covering: **95 lines with zero `viewer.world` / `THREE` / `screenToGround` touches.**
 * It reaches the 3D view only through `layerMgr`, which is a live object handed over whole, exactly
 * as ⑨–⑫ hand it. So it is a lift, not the bigger change ⑫ described.
 *
 * ## `layerMgr` is typed, not guessed
 *
 * ⑩ recorded the one dep whose type was *guessed* — `layerMgr` as `{ rebuild(): void }` — which
 * compiled until a call site reached for `isolateGuids`. **Guessing a dep's type is the same error
 * as guessing its name.** It is imported as `LayerManager` here for that reason, and this module was
 * written imported-by-nothing first so `tsc` could enumerate what it actually needs, rather than a
 * hand-written list that has already been wrong once (⑩ found 12 of 17 captures by hand).
 */

export interface FederationDeps {
  /** The section body `app.ts` created; this module fills it. */
  fedBody: HTMLElement;
  /** A full-width tool button. Declared inside `buildToolsPanel`, handed over whole. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  /** The project id, non-null-asserted by the caller inside its project gate. */
  pid: string;
  /** `const` in `app.ts`, so a value is safe — it is the gate this group is built behind. */
  projectId: string | null;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /**
   * Layer visibility manager — a LIVE object handed over whole, not a copied shape.
   * Typed as `LayerManager` rather than the `{ rebuild(): void }` a hand-written list would
   * produce: ⑩ guessed exactly that and it compiled until a call site reached `isolateGuids`.
   */
  layerMgr: LayerManager;
  /** Repaints the federated-model list into `fedBody`. Owned by `app.ts`, which also calls it. */
  refreshFederation: () => void;
  /** Selects an element in the 3D view by IFC GlobalId — never a transient viewer id. */
  selectByGuid: (guid: string, fit?: boolean) => void;
}

export function buildFederationSection(d: FederationDeps): void {
  const l = document.createElement("div"); l.id = "fed-models"; d.fedBody.appendChild(l); d.refreshFederation();
  if (d.projectId) d.fedBody.appendChild(d.toolBtn2("🕔 Version compare (3D)", async () => {
    const h = await d.api.modelVersions(d.pid);
    showResult("Version compare", async (body) => {
      if (!h.length) { body.appendChild(resultNote("No versions yet — publish the model (Authoring) to snapshot one.")); return; }
      if (h.length >= 2) {
        // VERSION-COMPARE-3D: pick any two versions → summary + a 3D overlay (added green / modified amber)
        const versionOpts = (sel: HTMLSelectElement, def: number) => {
          for (const v of h) { const o = document.createElement("option"); o.value = String(v.version); o.textContent = `v${v.version}`; sel.appendChild(o); }
          sel.value = String(def);
        };
        const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0";
        const aSel = document.createElement("select"); aSel.className = "portal-filter"; aSel.style.fontSize = "12px"; versionOpts(aSel, h[1]!.version);
        const bSel = document.createElement("select"); bSel.className = "portal-filter"; bSel.style.fontSize = "12px"; versionOpts(bSel, h[0]!.version);
        const cmp = document.createElement("button"); cmp.className = "mini-btn on"; cmp.textContent = "Compare";
        row.append(document.createTextNode("from "), aSel, document.createTextNode(" → "), bSel, cmp);
        body.appendChild(row);
        const out = document.createElement("div"); body.appendChild(out);
        const render = async () => {
          const a = Number(aSel.value), b = Number(bSel.value);
          out.innerHTML = "<div class=\"meta\">comparing…</div>";
          let diff; try { diff = await d.api.versionDiff(d.pid, a, b); } catch (e) { out.innerHTML = ""; out.appendChild(resultNote(`compare failed: ${escapeHtml((e as Error).message)}`, "")); return; }
          out.innerHTML = "";
          out.appendChild(resultNote(`v${a} → v${b}: <b style="color:var(--status-good)">+${diff.added_count}</b> added / `
            + `<b style="color:var(--status-crit)">−${diff.removed_count}</b> removed`
            + (diff.modified_available ? ` / <b style="color:#e0a020">~${diff.modified_count}</b> modified` : " / modified n/a (older version)")
            + ` · ${diff.unchanged_count} unchanged`, "ok"));
          const ctl = document.createElement("div"); ctl.style.cssText = "display:flex;gap:6px;margin:4px 0";
          const overlay = document.createElement("button"); overlay.className = "mini-btn on"; overlay.textContent = "◉ Overlay in 3D";
          overlay.title = "Colour added elements green and modified elements amber in the loaded model (removed elements aren't in it).";
          const reset = document.createElement("button"); reset.className = "mini-btn"; reset.textContent = "Reset";
          const cost = document.createElement("button"); cost.className = "mini-btn"; cost.textContent = "$ Cost impact";
          cost.title = "REVISION-DELTA: conceptual cost of this revision — added elements priced from the current takeoff, removed counted by class, quantity changes flagged for re-estimate";
          overlay.onclick = async () => {
            try {
              await d.layerMgr.resetColors();
              if (diff!.added.length) await d.layerMgr.colorGuids(diff!.added, "#33d17a");
              if (diff!.modified.length) await d.layerMgr.colorGuids(diff!.modified.map((m) => m.guid), "#e0a020");
              d.notify(`overlaid +${diff!.added_count} / ~${diff!.modified_count}`, "success");
            } catch (e) { d.notify((e as Error).message, "error"); }
          };
          reset.onclick = async () => { await d.layerMgr.resetColors(); await d.layerMgr.showAll(); };
          cost.onclick = () => void (async () => {
            let cd; try { cd = await d.api.versionCostDelta(d.pid, a, b); } catch (e) { d.notify((e as Error).message, "error"); return; }
            showResult(`Revision cost impact — v${a} → v${b}`, (cb) => {
              cb.appendChild(resultNote(`<b>+$${cd!.added.cost.toLocaleString()}</b> added `
                + `(${cd!.added.priced_count}/${cd!.added.count} priced) · `
                + `<b>${cd!.removed.count}</b> removed (by class) · `
                + `<b>${cd!.requantified.count}</b> flagged for re-estimate`, "ok"));
              if (cd!.added.lines.length) {
                cb.appendChild(resultNote("Added — priced from the current takeoff:", ""));
                cb.appendChild(kvTable(cd!.added.lines.map((l) => ({
                  k: `${l.ifc_class.replace("Ifc", "")} ×${l.count}`,
                  v: `${l.quantity} ${l.unit} × $${l.rate} = <b>$${l.amount.toLocaleString()}</b>`,
                }))));
              }
              if (cd!.removed.by_class.length) {
                cb.appendChild(resultNote("Removed — counted by class (not priced; prior quantities aren't stored):", ""));
                cb.appendChild(kvTable(cd!.removed.by_class.map((l) => ({
                  k: `${l.ifc_class.replace("Ifc", "")} (${escapeHtml(l.discipline)})`, v: `−${l.count}`,
                }))));
              }
              const n = document.createElement("div"); n.className = "meta"; n.style.cssText = "margin-top:8px;font-size:11px";
              n.textContent = cd!.note; cb.appendChild(n);
            });
          })();
          ctl.append(overlay, cost, reset); out.appendChild(ctl);
          if (diff.modified_count) {
            out.appendChild(resultNote("Modified elements (click to select in 3D):", ""));
            out.appendChild(kvTable(diff.modified.slice(0, 40).map((m) => {
              // name the exact properties/quantities that changed (VERSION-COMPARE per-property), if available
              const props = (m.changed_properties || []).slice(0, 6)
                .map((p) => `${p.property}${p.status !== "changed" ? ` (${p.status})` : ""}`).join(", ");
              const extra = (m.changed_properties && m.changed_properties.length > 6) ? "…" : "";
              return {
                k: `${(m.ifc_class || "").replace("Ifc", "")} · ${m.name || m.guid.slice(0, 8)}`,
                v: m.changes.join(", ") + (props ? ` — ${props}${extra}` : ""),
                onClick: () => d.selectByGuid(m.guid, false),
              };
            })));
          }
        };
        cmp.onclick = () => void render();
        void render();
      }
      body.appendChild(resultNote("Version history:", ""));
      body.appendChild(kvTable(h.map((v) => ({
        k: `v${v.version}${v.note ? " (" + v.note + ")" : ""}`,
        v: `${v.element_count} elements · ${(v.created_at || "").slice(0, 10)}` }))));
    });
  }));
}
