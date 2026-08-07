import * as THREE from "three";

import { type ApiClient } from "../../api/client";
import { escapeHtml } from "../../ui/feedback";
import { openNodeCanvas } from "../nodeCanvas";
import { describePlan, planApply, type ApplyPlan, type LockVariable } from "../dimLocks";

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
  /**
   * ACCESSOR for the same reason — `selectedGuid` is a `let` in app.ts and changes on every pick.
   * A value copy would compile cleanly and freeze whatever was selected when the panel was BUILT,
   * so the locks editor would silently edit the wrong element for the rest of the session.
   */
  selectedGuid: () => string | null;
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
        b.append(fix, pub, furnish, nodeBtn, locksBtn(d, out), out);
}

/**
 * R38-SOLVER-LOCKS — dimensional locks on the selected element.
 *
 * Lives in this section rather than its own because `app.ts` is at its size pin and a new builder
 * entry costs it lines it does not have — and locks ARE authoring, so this is where the ratchet was
 * pointing anyway.
 *
 * Reads the element's numeric properties, lets the user fix or relate them, solves server-side, and
 * applies through the existing guid-keyed recipes. The three things it must not do quietly:
 *
 *  - **A conflict must be named.** The solver's whole argument for existing is that "an
 *    over-constrained system NAMES the conflict"; satisfying one of a contradictory pair silently
 *    produces geometry that looks deliberate and is not.
 *  - **Remaining freedom must be reported.** `dof > 0` means infinitely many solutions and one was
 *    picked; that is how a "solved" sketch drifts on the next edit.
 *  - **A refusal must be visible.** `planApply` refuses a variable no recipe can write; showing the
 *    applied count without the refusals is a result that looks complete and is not.
 */
function locksBtn(d: AuthoringDeps, out: HTMLElement): HTMLButtonElement {
  const { api, pid, notify } = d;
  const btn = d.toolBtn2("⟺ Dimensional locks", () => void openLocks());
  btn.dataset.cap = "edit";
  btn.title = "Fix or relate this element's dimensions, solve the system, and apply the result";

  async function openLocks(): Promise<void> {
    const guid = d.selectedGuid();
    if (!guid) { notify("Select an element first", "info"); return; }
    out.textContent = "reading properties…";
    let vars: LockVariable[];
    try {
      vars = await readNumericParams(api, pid, guid);
    } catch { out.textContent = "could not read this element's properties"; return; }
    if (!vars.length) { out.textContent = "this element has no numeric parameters to lock"; return; }

    out.innerHTML = "";
    const rows = document.createElement("div");
    const state = new Map<string, number | null>();   // variable -> fixed value, or null for free
    for (const v of vars) {
      const row = document.createElement("label");
      row.style.cssText = "display:flex;gap:6px;align-items:center;margin:2px 0";
      const cb = document.createElement("input"); cb.type = "checkbox";
      const num = document.createElement("input");
      num.type = "number"; num.step = "any"; num.value = String(v.current);
      num.style.width = "7em"; num.disabled = true;
      cb.onchange = () => { num.disabled = !cb.checked; state.set(v.name, cb.checked ? Number(num.value) : null); };
      num.oninput = () => { if (cb.checked) state.set(v.name, Number(num.value)); };
      const name = document.createElement("span");
      name.textContent = `${v.param} (${v.current})`;
      row.append(cb, name, num);
      rows.appendChild(row);
    }
    const result = document.createElement("div"); result.className = "meta"; result.style.marginTop = "4px";
    const apply = document.createElement("button");
    apply.className = "tool-btn"; apply.textContent = "Solve & apply"; apply.disabled = true;
    let plan: ApplyPlan | null = null;

    const solveBtn = document.createElement("button");
    solveBtn.className = "tool-btn"; solveBtn.textContent = "Solve";
    solveBtn.onclick = async () => {
      const constraints = [...state.entries()]
        .filter(([, val]) => typeof val === "number" && Number.isFinite(val))
        .map(([nm, val]) => ({ kind: "fix", a: nm, value: val, strength: "required" }));
      if (!constraints.length) { result.textContent = "Lock at least one value first."; return; }
      result.textContent = "solving…";
      try {
        const r = await api.solveConstraints(pid, Object.fromEntries(vars.map((v) => [v.name, v.current])), constraints);
        plan = planApply(vars, r.values);
        const bits: string[] = [];
        // Conflicts and remaining freedom are stated whether or not anything is applicable — a plan
        // that says "2 changes" over an unsolved system is the misleading half of this feature.
        if (!r.solved) bits.push("⚠ over-constrained");
        for (const c of r.conflicts || []) bits.push(`conflict: ${escapeHtml(String(c.detail ?? `${c.a} ↔ ${c.b}`))}`);
        if (r.dof > 0) bits.push(`${r.dof} degree(s) of freedom left — one solution of many`);
        bits.push(describePlan(plan));
        result.innerHTML = bits.map((t) => escapeHtml(t)).join("<br>");
        apply.disabled = plan.writes.length === 0;
      } catch { result.textContent = "solve failed"; plan = null; apply.disabled = true; }
    };

    apply.onclick = async () => {
      if (!plan?.writes.length) return;
      apply.disabled = true;
      let done = 0;
      try {
        for (const w of plan.writes) { await api.editIfc(pid, w.op, w.params, false); done++; }
        await api.publish(pid);
        const state2 = await d.waitForPublish(pid);
        if (state2 === "done") await d.loadProjectModel();
        // The refusals are repeated HERE, after applying, because this is the moment someone reads
        // it as finished. "Applied 3" alone is the silent-drop failure.
        notify(plan.refused.length
          ? `Applied ${done} — ${plan.refused.length} could not be written: ${plan.refused.map((r) => r.variable).join(", ")}`
          : `Applied ${done} change(s)`, plan.refused.length ? "info" : "success");
      } catch { notify(`Applied ${done} of ${plan.writes.length} — the rest failed`, "error"); }
    };

    out.append(rows, solveBtn, apply, result);
  }
  return btn;
}

/** Numeric instance properties, as solver variables bound to their element. */
async function readNumericParams(api: ApiClient, pid: string, guid: string): Promise<LockVariable[]> {
  const props = await api.elementEffectiveProps(pid, guid);
  const out: LockVariable[] = [];
  for (const [pset, entries] of Object.entries(props.psets || {})) {
    for (const [prop, cell] of Object.entries(entries)) {
      const v = (cell as { value: unknown }).value;
      if (typeof v !== "number" || !Number.isFinite(v)) continue;
      out.push({
        name: `${pset}.${prop}`, current: v, guid,
        ifcClass: String((props as { ifc_class?: string }).ifc_class ?? ""),
        param: prop.toLowerCase(),
      });
    }
  }
  return out;
}
