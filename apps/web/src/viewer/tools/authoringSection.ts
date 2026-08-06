import * as THREE from "three";

import { type ApiClient } from "../../api/client";
import { escapeHtml } from "../../ui/feedback";
import { openNodeCanvas } from "../nodeCanvas";

/**
 * R39-DECOMP-VIEWER — the advanced authoring / annotate / library section, out of `app.ts`.
 *
 * `lastPoint` arrives as an ACCESSOR for the same reason as the analyse section: it is a `let`, and the placement tools read it when clicked, not when built.
 *
 * The body is byte-identical to what it replaced and deliberately NOT re-indented: re-indenting
 * risks silently changing the content of a multi-line template literal inside what is meant to be
 * a no-behaviour-change move. `tsc` is the parity gate for the threading; `toolsSplit.test.ts`,
 * which reads section SOURCE, is the gate for "no control was dropped" — this file is listed in
 * its `SECTION_SOURCES` for that reason.
 */

export interface AuthoringDeps {
  section: (key: string, title: string,
            opts?: { requires?: "project" | "sourceIfc"; tool?: boolean }) => HTMLElement | null;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  pid: string;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** ACCESSOR: `lastPoint` is a `let` in app.ts, read at click time. */
  lastPoint: () => THREE.Vector3 | null;
  /** The tools panel element — this section dims itself for non-editors via `data-cap`. */
  panel: HTMLElement;
  waitForPublish: (pid: string, onTick?: (s: string) => void) => Promise<string>;
  loadProjectModel: () => Promise<boolean>;
}

export function buildAuthoringSection(d: AuthoringDeps): void {
  const { section, toolBtn2, api, pid, notify, panel, waitForPublish, loadProjectModel } = d;
  const lastPoint = d.lastPoint();
        const b = section("authoring", "Build · Advanced authoring, annotate & library", { requires: "sourceIfc", tool: true });
        const group = panel.querySelector('.tool-group[data-tool="authoring"]') as HTMLElement | null;
        if (group) group.dataset.cap = "edit";   // whole section hidden for non-editors
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px"; out.id = "au-out";
        const fix = toolBtn2("✎ Fix slabs: set LoadBearing", async () => {
          out.textContent = "editing IFC…";
          const r = await api.editIfc(pid, "set_pset", { ifc_class: "IfcSlab", pset: "Pset_SlabCommon", prop: "LoadBearing", value: true, dtype: "bool" }, true);
          const v = await api.validate(pid);
          out.innerHTML = `edited ${r.changed} slabs · IDS now: <b>${v.status.toUpperCase()}</b> · converting…`;
          const state = await waitForPublish(pid);
          if (state === "done") await loadProjectModel();
          out.innerHTML += `<br>publish: ${state}`;
        });
        fix.dataset.cap = "edit";
        const pub = toolBtn2("⟳ Republish (reconvert + reindex)", async () => {
          out.textContent = "publishing… (running in background)";
          await api.publish(pid);
          const state = await waitForPublish(pid, (s) => (out.textContent = `publish: ${s}…`));
          if (state === "done") await loadProjectModel();
          out.textContent = `publish ${state}`;
        });
        pub.dataset.cap = "edit";
        // Furnish & equip — add starter-library families (furniture / sanitary / appliances /
        // plants). Works on a generated massing model too, since the types are generated on demand.
        const furnish = document.createElement("div"); furnish.style.marginTop = "6px";
        const hint = document.createElement("div"); hint.className = "meta";
        hint.textContent = "Click a point in the model to set placement, then pick a family.";
        const sel = document.createElement("select"); sel.className = "tool-btn";
        sel.style.cssText = "display:block;width:100%;margin:4px 0"; sel.dataset.cap = "edit";
        sel.innerHTML = `<option value="">＋ Furnish & equip…</option>`;
        void api.familyLibrary().then((c) => {
          for (const [cat, items] of Object.entries(c.categories)) {
            const og = document.createElement("optgroup"); og.label = cat;
            for (const it of items) {
              const o = document.createElement("option"); o.value = it.key; o.textContent = it.label; og.appendChild(o);
            }
            sel.appendChild(og);
          }
          const ext = c.external.length ? ` · ${c.external.length} external` : "";
          hint.textContent = `${c.count} families in the library${ext}. Click a point to set placement, then pick a family — or import an IFC for more.`;
        }).catch(() => { hint.textContent = "Family library unavailable (API offline)."; });
        const place = toolBtn2("⊕ Place selected family", async () => {
          const key = sel.value;
          if (!key) { out.textContent = "pick a family first"; return; }
          const label = sel.options[sel.selectedIndex]?.text ?? key;
          const pos: [number, number] | null = lastPoint ? [lastPoint.x, -lastPoint.z] : null;
          out.textContent = `adding ${label}…`;
          await api.addFamily(pid, key, pos);
          out.textContent = `${label} added · converting…`;
          const state = await waitForPublish(pid);
          if (state === "done") await loadProjectModel();
          out.innerHTML = `added <b>${escapeHtml(label)}</b>${pos ? ` at ${pos[0].toFixed(1)}, ${pos[1].toFixed(1)} m` : " at origin"}<br>publish: ${escapeHtml(state)}`;
        });
        place.dataset.cap = "edit";
        // Import external IFC type content (manufacturer / 3rd-party families) into the project.
        const impInput = document.createElement("input");
        impInput.type = "file"; impInput.accept = ".ifc"; impInput.style.display = "none";
        const imp = toolBtn2("⇪ Import IFC families…", () => impInput.click());
        imp.dataset.cap = "edit";
        imp.title = "Import type content (families) from a manufacturer / 3rd-party IFC";
        impInput.addEventListener("change", async () => {
          const f = impInput.files?.[0]; if (!f) return;
          out.textContent = `importing families from ${f.name}…`;
          try {
            const r = await api.importFamilies(pid, f);
            if (!r.count) { out.textContent = "no new families found in that IFC"; impInput.value = ""; return; }
            const state = await waitForPublish(pid);
            if (state === "done") await loadProjectModel();
            out.innerHTML = `imported <b>${r.count}</b> famil${r.count === 1 ? "y" : "ies"} `
              + `(${r.imported.slice(0, 3).map((i) => i.name).join(", ")}${r.count > 3 ? "…" : ""}) · publish: ${state}`;
          } catch (e) { out.textContent = `import failed: ${(e as Error).message}`; }
          impInput.value = "";
        });
        furnish.append(hint, sel, place, imp, impInput);
        // AUTH-VS: open the visual node-authoring canvas (chain recipes as a graph, run in one pass)
        const nodeBtn = toolBtn2("🕸 Visual node authoring", () => {
          openNodeCanvas({
            recipes: ["add_wall", "add_column", "add_beam", "add_slab", "add_base_plate", "add_curtain_wall", "derive_analytical"],
            runGraph: async (graph) => {
              const r = await api.editGraph(pid, graph, { publish: true });
              const state = await waitForPublish(pid);
              if (state === "done") await loadProjectModel();
              return r;
            },
            notify,
          });
        });
        nodeBtn.dataset.cap = "edit";
        nodeBtn.title = "Drag recipe nodes, wire outputs → inputs, and run the graph as one GUID-stable authoring pass";
        b.append(fix, pub, furnish, nodeBtn, out);
}
