import type { ApiClient } from "../../api/client";
import { escapeHtml } from "../../ui/feedback";
import { resultNote, showResult } from "../../ui/result";

/**
 * R39-DECOMP-VIEWER ⑨ — **fabrication detail**, out of `app.ts`.
 *
 * The LOD 350/400 connection tools: a base plate under a steel column, a shear tab at a beam end, a
 * reinforcement cage in a concrete column, the ACI 318 envelope check on that cage, and the bar
 * bending schedule the fabricator actually buys steel from. Five buttons, returned in rail order.
 *
 * ## Why this one, and what it proves that ⑧ did not
 *
 * Slice ⑧ (drawings) threaded `activeStorey` / `activeStoreyZ` as accessors. This slice threads
 * **`selectedGuid`** — the capture the decomposition plan named first, and the one with the worst
 * failure mode, because `qaSection.ts` has already shipped that bug once: it opened with
 * `const selectedGuid = d.selectedGuid();` under a docstring explaining why that was impossible, and
 * two tools answered *"select an element in 3D first"* for the life of every session.
 *
 * Every tool here is selection-gated — all five refuse without a selected element — so collapsing
 * the accessor would not break them loudly. It would make the whole group permanently inert, with a
 * polite error message, which is the failure that survives review. **There are eight reads of
 * `d.selectedGuid()` below and not one local binding of it**; `accessorNotCollapsed.test.ts` is the
 * gate, and it checks the shape rather than the name.
 *
 * `authorAndReload` crosses as a function. It closes over the delta committer, the loading overlay
 * and the republish path, and handing it over whole is what keeps this module free of all three.
 */
export interface FabricationDeps {
  /** A full-width tool button. Declared inside `buildToolsPanel`, handed over whole. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  /** The project id, non-null-asserted by the caller inside its project gate. */
  pid: string;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /**
   * **An accessor, never a value.** `selectedGuid` is `let` in `app.ts` and changes with every
   * click in the 3D view. A value copy would freeze it at panel-build time — `null` — and every
   * tool here would refuse forever while looking like it was working.
   */
  selectedGuid: () => string | null;
  /**
   * Runs an edit recipe and republishes. Carries the committer + overlay with it.
   *
   * The signature is the REAL one, verdict and optional preview args included, not a convenient
   * narrowing of it. `tsc` rejected `=> Promise<void>` outright, which is the parity gate working:
   * a dep type that quietly drops the `{applied, refused}` result would let a future caller here
   * treat a REFUSED edit as a successful one.
   */
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string,
                    previewId?: string | null, previewGuid?: string)
                   => Promise<{ applied: boolean; refused: boolean }>;
}

/**
 * Builds the fabrication-detail buttons.
 *
 * Returns a NAMED, explicitly-typed record rather than an array. Under `noUncheckedIndexedAccess`
 * both a destructured array element AND an index into `Record<string, T>` are `T | undefined`, and
 * the caller appends these straight into the rail, so `tsc` refused both in turn. An interface with
 * declared keys is the only shape that carries non-optional types across the seam -- and names
 * survive re-ordering, which an index does not.
 */
export interface FabricationButtons {
  basePlateBtn: HTMLButtonElement;
  shearTabBtn: HTMLButtonElement;
  rebarBtn: HTMLButtonElement;
  cageChkBtn: HTMLButtonElement;
  bbsBtn: HTMLButtonElement;
}

export function buildFabricationSection(d: FabricationDeps): FabricationButtons {
  // W11 B6: steel connections — base plate on the selected column, shear tab on the selected beam
  // (bare LOD-300 members → LOD-350/400 fabrication assemblies).
  const basePlateBtn = d.toolBtn2("🔩 Base plate (steel column)", async () => {
    if (!d.selectedGuid()) { d.notify("select a steel column first", "error"); return; }
    await d.authorAndReload("add_base_plate", { column_guid: d.selectedGuid(), bolts: 4 }, "base plate");
  });
  basePlateBtn.title = "Author a base plate + 4 anchor bolts under the selected steel column and group "
    + "them into an IfcElementAssembly — the LOD 350/400 fabrication connection. GUID-stable.";
  const shearTabBtn = d.toolBtn2("🔩 Shear tab (steel beam)", async () => {
    if (!d.selectedGuid()) { d.notify("select a steel beam first", "error"); return; }
    await d.authorAndReload("add_shear_tab", { beam_guid: d.selectedGuid(), bolts: 3 }, "shear tab");
  });
  shearTabBtn.title = "Author a shear-tab plate + bolts at the selected steel beam's end and assemble it "
    + "with the beam — a simple beam-to-column shear connection (LOD 350/400). GUID-stable.";
  const rebarBtn = d.toolBtn2("🪝 Rebar cage (concrete column)", async () => {
    if (!d.selectedGuid()) { d.notify("select a concrete column first", "error"); return; }
    await d.authorAndReload("add_rebar_cage", { column_guid: d.selectedGuid() }, "rebar cage");
  });
  rebarBtn.title = "Author a reinforcement cage — 4 longitudinal corner bars + stirrups (swept-disk "
    + "IfcReinforcingBar) in the selected concrete column, assembled with it (LOD 400). GUID-stable.";
  const cageChkBtn = d.toolBtn2("✓ Check cage (ACI envelope)", async () => {
    // Read once at click time. Two calls cannot narrow, and they could genuinely differ.
    const guid = d.selectedGuid();
    if (!guid) { d.notify("select the caged concrete column first", "error"); return; }
    try {
      const r = await d.api.rebarCheckCage(d.pid, guid);
      const ok = r.checked && !r.violations.length;
      showResult("Rebar cage check", (body) => {
        body.appendChild(resultNote(ok
          ? `✅ cage OK — ${r.longitudinal_bars} bars · ${r.ties} ties · tie spacing within `
            + `${r.params.tie_spacing} m (${escapeHtml(r.params.governing)})`
          : `🔴 ${r.violations.map(escapeHtml).join(" · ")}`, ok ? "ok" : ""));
        body.appendChild(resultNote(`Rule: ${escapeHtml(r.params.rule)} — #bars ≥ ${r.params.min_longitudinal_bars}, `
          + `envelope ${r.params.tie_spacing} m for ${escapeHtml(r.params.bar_size)}/${escapeHtml(r.params.tie_size)}.`, ""));
      });
    } catch (e) { d.notify((e as Error).message, "error"); }
  });
  cageChkBtn.title = "Verify the selected column's authored cage against the ACI 318 envelope — "
    + "longitudinal bar count and tie spacing min(16·d_bar, 48·d_tie, least dimension).";
  const bbsBtn = d.toolBtn2("📋 Bar bending schedule", async () => {
    try {
      const r = await d.api.rebarBbs(d.pid);
      showResult("Bar bending schedule", (body) => {
        body.appendChild(resultNote(`<b>${r.bars}</b> bars · ${r.marks} marks · `
          + `${r.total_length_m.toLocaleString()} m · <b>${r.total_tonnes} t</b>`
          + (r.skipped ? ` · ${r.skipped} skipped (no swept geometry)` : ""), r.bars ? "ok" : ""));
        if (r.rows.length) {
          const t = document.createElement("table"); t.className = "mini-table";
          t.style.cssText = "width:100%;font-size:11px;border-collapse:collapse";
          t.innerHTML = `<thead><tr><th>Mark</th><th>Size</th><th>Shape</th><th>Cut (m)</th>`
            + `<th>Count</th><th>kg/m</th><th>Total kg</th></tr></thead><tbody>`
            + r.rows.map((x) => `<tr><td>${escapeHtml(x.mark)}</td><td>${escapeHtml(x.size || String(x.diameter_mm) + "mm")}</td>`
              + `<td>${escapeHtml(x.shape)}</td><td style="text-align:right">${x.cut_length_m}</td>`
              + `<td style="text-align:center">${x.count}</td><td style="text-align:right">${x.unit_mass_kg_m}</td>`
              + `<td style="text-align:right">${x.total_kg}</td></tr>`).join("") + `</tbody>`;
          body.appendChild(t);
          const dl = document.createElement("a"); dl.className = "file-btn"; dl.style.marginTop = "6px";
          dl.textContent = "⬇ BBS (CSV)"; dl.href = d.api.rebarBbsCsvUrl(d.pid);
          body.appendChild(dl);
        } else {
          body.appendChild(resultNote("No IfcReinforcingBar elements — author cages first (🪝).", ""));
        }
      });
    } catch (e) { d.notify((e as Error).message, "error"); }
  });
  bbsBtn.title = "Group every authored IfcReinforcingBar into marks (size · shape · cut length) with "
    + "unit mass and total tonnage — the fabricator/5D quantity, downloadable as CSV.";
  return { basePlateBtn, shearTabBtn, rebarBtn, cageChkBtn, bbsBtn };
}
