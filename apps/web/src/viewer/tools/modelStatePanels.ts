/**
 * R39-DECOMP-VIEWER ③ — the five panels that read and write an element's *state*, moved out of
 * `app.ts`: family types, groups/arrays, phasing, LOD, and as-built verification.
 *
 * WHY THESE FIVE, AND WHY NOW
 * ---------------------------
 * `app.ts` sits on a per-file ratchet with zero headroom, and R36-VIEWER-SUBAPP needs room in it for
 * the Model ▸ Sheets ▸ Specs switch. Rather than raise the pin to make space — the direction of
 * travel is down — this takes ~344 lines out.
 *
 * They group cleanly because they are the same *kind* of tool: each opens a result panel, shows what
 * the model currently says about some per-element attribute, and offers to change it through
 * `authorAndReload`. None of them owns geometry. `openGroupsPanel` and `openPhasingPanel` do reach
 * the renderer, but only through `layerMgr.isolateGuids` — a visibility call, not a scene edit, and
 * one a fake satisfies in a test.
 *
 * THE PARITY GATE IS `tsc`, NOT THE SUITE
 * ---------------------------------------
 * Nothing in the suite imports `app.ts`; `createViewerApp` needs a WebGL context and a Fragments
 * worker. A green suite after a move like this says nothing at all. So, as with ① and ②: every
 * dependency is an **explicit typed parameter**, which makes an unthreaded capture a compile error.
 *
 * `selectedGuid` crosses as an **accessor**, because `app.ts` holds it as a `let`. This is not a
 * theoretical hazard — `qaSection.ts` opened with `const selectedGuid = d.selectedGuid();` directly
 * beneath a docstring explaining why that could not happen, and shipped two permanently-dead tools to
 * main. `accessorNotCollapsed.test.ts` now fails on that shape, and it covers this file too.
 *
 * ONE DELIBERATE BEHAVIOUR CHANGE, NOT A VERBATIM MOVE
 * ----------------------------------------------------
 * The phasing and LOD rows were written as `bt.onclick = () => tag(ph, [selectedGuid!], …)`. The `!`
 * was justified by an `if (selectedGuid)` guard — but that guard runs when the row is *rendered*,
 * while the handler reads the variable when it is *clicked*. Deselect between the two and the
 * original passed `[null]` to the recipe. Here each handler re-reads the accessor and refuses if the
 * selection is gone. Called out because "moved verbatim" is the claim that makes a move reviewable,
 * and this is the one place that claim would be false.
 */

import { type ApiClient } from "../../api/client";
import { LayerManager } from "../../tools/layers";
import { toast, withLoading } from "../../ui/feedback";
import { askText } from "../../ui/prompt";
import { kvTable, resultNote, showResult } from "../../ui/result";
import { loadSelSets } from "../../tools/selectionSetsStore";

/** LOD maturity stages, BIMForum 100 (schematic) → 500 (field-verified as-built). */
const LODS = ["100", "200", "300", "350", "400", "500"] as const;

/** Element phase status — the renovation / demolition-sequencing dimension. */
const PHASES = [["new", "🟢 New"], ["existing", "⚪ Existing"], ["demolish", "🔴 Demolish"],
  ["temporary", "🟡 Temporary"]] as const;

/** `"1.8, 0.6, 0.9"` → `[1.8, 0.6, 0.9]`, or null unless all three are finite and positive. */
export function parseDims(s: string): [number, number, number] | null {
  const p = s.split(/[,x×]/).map((v) => Number(v.trim()));
  return p.length === 3 && p.every((n) => Number.isFinite(n) && n > 0) ? [p[0]!, p[1]!, p[2]!] : null;
}

/** `IfcFurnitureType` → `Furniture`. Display only — never use this to match an IFC class. */
export function shortClass(c: string): string {
  return c.replace(/^Ifc/, "").replace(/Type$/, "");
}

export interface ModelStateDeps {
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  /** `const` in app.ts — safe by value. */
  pid: string;
  /** `const` in app.ts — safe by value. */
  projectId: string | null;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** ACCESSOR: `selectedGuid` is a `let` in app.ts. A value here freezes at panel-build time. */
  selectedGuid: () => string | null;
  layerMgr: LayerManager;
  /** The viewer's host element — `withLoading` mounts its overlay on it. */
  container: HTMLElement;
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string,
                    previewId?: string | null) => Promise<{ applied: boolean; refused: boolean }>;
  waitForPublish: (pid: string, onTick?: (s: string) => void) => Promise<string>;
  loadProjectModel: () => Promise<boolean>;
  reloadModelPins: () => Promise<void | boolean>;
}

// ── family types ──────────────────────────────────────────────────────────────────────────────────

export async function openTypeInspector(d: ModelStateDeps, guid: string, reopen: () => void): Promise<void> {
  let det;
  try { det = await d.api.typeDetail(d.pid, guid); }
  catch (e) { d.notify(`type load failed: ${(e as Error).message}`, "error"); return; }
  showResult(`Type — ${det.name}`, (body) => {
    const back = d.toolBtn2("‹ All types", reopen); back.style.marginBottom = "6px"; body.appendChild(back);
    body.appendChild(kvTable([
      { k: "Class", v: shortClass(det.ifc_class), strong: true },
      { k: "Predefined", v: det.predefined || "—" },
      { k: "Size (w×d×h m)", v: det.dims ? det.dims.map((n) => n.toFixed(3)).join(" × ") : "no box geometry" },
      { k: "Placed occurrences", v: String(det.occurrence_count) },
      { k: "Material layers", v: det.materials.length
        ? det.materials.map((m) => `${m.material ?? "?"}${m.thickness != null ? ` ${(m.thickness * 1000).toFixed(0)}mm` : ""}`).join(" · ") : "—" },
    ]));
    const psetNames = Object.keys(det.psets || {});
    if (psetNames.length) {
      const rows = psetNames.flatMap((pn) =>
        Object.entries(det.psets[pn] as Record<string, unknown>).map(([k, v]) => ({ k: `${pn}.${k}`, v: String(v) })));
      body.appendChild(resultNote(`<b>Type properties</b> — inherited by all ${det.occurrence_count} occurrence(s).`, ""));
      body.appendChild(kvTable(rows.slice(0, 40)));
    }
    const editSize = d.toolBtn2("✎ Edit size (propagates to occurrences)", async () => {
      const cur = det.dims ? det.dims.map((n) => n.toFixed(3)).join(", ") : "1.0, 0.5, 0.75";
      const v = await askText("Edit type size", { label: "Width, depth, height (metres)", value: cur }); if (!v) return;
      const dims = parseDims(v); if (!dims) { d.notify("need three positive numbers, e.g. 1.8, 0.6, 0.9", "error"); return; }
      await d.authorAndReload("edit_type_params", { type_guid: guid, dims }, `resize ${det.name}`);
      await openTypeInspector(d, guid, reopen);
    });
    editSize.title = "Changes the type's box — every placed occurrence updates at once (GUID-stable)";
    body.appendChild(editSize);
    const mat = d.toolBtn2("🧱 Set material layers", async () => {
      const cur = det.materials.map((m) => `${m.material ?? "Material"}:${m.thickness ?? 0.1}`).join(", ") || "Gypsum:0.015, Steel:0.1, Gypsum:0.015";
      const v = await askText("Material layer set", { label: "name:thickness_m, … (outer → inner)", value: cur }); if (!v) return;
      const layers = v.split(",").map((seg) => { const [n, t] = seg.split(":"); return { material: (n || "Material").trim(), thickness: Number((t || "0.1").trim()) || 0.1 }; });
      if (!layers.length) return;
      await d.authorAndReload("assign_material_set", { type_guid: guid, layers }, `material set for ${det.name}`);
      await openTypeInspector(d, guid, reopen);
    });
    mat.title = "Assign an IfcMaterialLayerSet — occurrences inherit the assembly (walls/slabs/roofs)";
    body.appendChild(mat);
  });
}

export async function openTypeBrowser(d: ModelStateDeps): Promise<void> {
  let rows;
  try { rows = (await d.api.types(d.pid)).types; }
  catch (e) { d.notify(`types failed: ${(e as Error).message}`, "error"); return; }
  showResult("Family types", (body) => {
    const create = d.toolBtn2("＋ New type", async () => {
      const cls = await askText("New type", { label: "Type class (e.g. IfcFurnitureType, IfcWallType)", value: "IfcFurnitureType" }); if (!cls) return;
      const name = await askText("New type", { label: "Type name", value: "New Type" }); if (!name) return;
      const dimsS = await askText("New type", { label: "Size w, d, h (metres) — blank for no geometry", value: "1.0, 0.5, 0.75" });
      const dims = dimsS ? parseDims(dimsS) : null;
      await d.authorAndReload("create_type", { ifc_class: cls.trim(), name: name.trim(), dims }, `type ${name.trim()}`);
      await openTypeBrowser(d);
    });
    create.style.marginBottom = "6px"; body.appendChild(create);
    if (!rows.length) { body.appendChild(resultNote("No types yet — create one, or place a family from the library.", "")); return; }
    body.appendChild(resultNote(`<b>${rows.length}</b> type(s). Click one to inspect, resize, or set materials.`, ""));
    for (const t of rows.slice().sort((a, b) => b.occurrence_count - a.occurrence_count || a.name.localeCompare(b.name))) {
      const btn = d.toolBtn2(`${t.name} · ${shortClass(t.ifc_class)}${t.occurrence_count ? ` ×${t.occurrence_count}` : ""}`,
        () => openTypeInspector(d, t.guid, () => void openTypeBrowser(d)));
      if (!t.has_geometry) btn.title = "No box geometry — resize will build one";
      body.appendChild(btn);
    }
  });
}

// ── groups, assemblies & arrays ───────────────────────────────────────────────────────────────────

export async function openGroupsPanel(d: ModelStateDeps): Promise<void> {
  let existing;
  try { existing = await d.api.groups(d.pid); }
  catch (e) { d.notify(`groups failed: ${(e as Error).message}`, "error"); return; }
  const sets = loadSelSets(d.pid);
  showResult("Groups, assemblies & arrays", (body) => {
    const arr = d.toolBtn2(d.selectedGuid() ? "▦ Array selected element" : "▦ Array (select an element first)", async () => {
      const guid = d.selectedGuid();
      if (!guid) { d.notify("select an element to array", "error"); return; }
      const counts = await askText("Array", { label: "Columns × rows (nx, ny)", value: "3, 1" }); if (!counts) return;
      const cd = counts.split(/[,x×]/).map((v) => Math.max(1, Math.round(Number(v.trim()) || 1)));
      const pitch = await askText("Array", { label: "Pitch dx, dy (metres)", value: "1.5, 0" }); if (!pitch) return;
      const pd = pitch.split(",").map((v) => Number(v.trim()) || 0);
      await d.authorAndReload("array_element",
        { guid, nx: cd[0] ?? 2, ny: cd[1] ?? 1, dx: pd[0] ?? 1, dy: pd[1] ?? 0 },
        `array ${(cd[0] ?? 2)}×${(cd[1] ?? 1)}`);
    });
    arr.style.marginBottom = "6px"; body.appendChild(arr);

    body.appendChild(resultNote(sets.length
      ? "<b>Group or assemble a selection set</b> — a Group is a named set; an Assembly is a real part-of whole."
      : "Save a named selection set (model browser) to group or assemble it.", ""));
    for (const s of sets) {
      const row = document.createElement("div"); row.className = "level-row";
      const label = document.createElement("span"); label.className = "meta";
      label.textContent = `${s.name} · ${s.guids.length}`; label.style.flex = "1";
      const gBtn = document.createElement("button"); gBtn.className = "mini-btn"; gBtn.textContent = "Group";
      gBtn.onclick = () => void d.authorAndReload("create_group", { name: s.name, guids: s.guids }, `group ${s.name}`);
      const aBtn = document.createElement("button"); aBtn.className = "mini-btn"; aBtn.textContent = "Assemble";
      aBtn.onclick = () => void d.authorAndReload("create_assembly", { name: s.name, guids: s.guids }, `assembly ${s.name}`);
      row.append(label, gBtn, aBtn); body.appendChild(row);
    }

    const all = [...existing.groups.map((g) => ({ ...g, kind: "group" as const, count: g.members })),
      ...existing.assemblies.map((a) => ({ guid: a.guid, name: a.name, kind: "assembly" as const, count: a.parts }))];
    if (all.length) {
      body.appendChild(resultNote(`<b>${all.length}</b> group(s)/assembly(ies) — click to isolate members.`, ""));
      for (const it of all) {
        const b = d.toolBtn2(`${it.kind === "assembly" ? "▣" : "▢"} ${it.name} · ${it.count}`, async () => {
          try {
            const det = await d.api.groupDetail(d.pid, it.guid);
            await d.layerMgr.isolateGuids(det.members.map((mm) => mm.guid));
            d.notify(`${it.name}: isolated ${det.member_count} member(s)`, "success");
          } catch (e) { d.notify(`inspect failed: ${(e as Error).message}`, "error"); }
        });
        if (it.kind === "group") {
          b.oncontextmenu = (ev) => { ev.preventDefault();
            void d.authorAndReload("ungroup", { guid: it.guid }, `ungroup ${it.name}`); };
          b.title = "Click: isolate members · right-click: ungroup";
        }
        body.appendChild(b);
      }
    }
  });
}

// ── phasing ───────────────────────────────────────────────────────────────────────────────────────

export async function openPhasingPanel(d: ModelStateDeps): Promise<void> {
  let sum;
  try { sum = await d.api.phasing(d.pid); }
  catch (e) { d.notify(`phasing failed: ${(e as Error).message}`, "error"); return; }
  const sets = loadSelSets(d.pid);
  showResult("Phasing (new / existing / demolish / temporary)", (body) => {
    body.appendChild(kvTable([
      { k: "🟢 New", v: String(sum.counts.NEW), bar: sum.total ? sum.counts.NEW / sum.total : 0 },
      { k: "⚪ Existing", v: String(sum.counts.EXISTING), bar: sum.total ? sum.counts.EXISTING / sum.total : 0 },
      { k: "🔴 Demolish", v: String(sum.counts.DEMOLISH), bar: sum.total ? sum.counts.DEMOLISH / sum.total : 0 },
      { k: "🟡 Temporary", v: String(sum.counts.TEMPORARY), bar: sum.total ? sum.counts.TEMPORARY / sum.total : 0 },
      { k: "Unphased", v: String(sum.counts.UNSET), bar: sum.total ? sum.counts.UNSET / sum.total : 0 },
    ]));
    const tag = async (phase: "new" | "existing" | "demolish" | "temporary", guids: string[], what: string) => {
      if (!guids.length) { d.notify("nothing to phase", "error"); return; }
      await d.authorAndReload("set_phase", { guids, phase }, `${what} → ${phase}`);
      await openPhasingPanel(d);
    };
    body.appendChild(resultNote(d.selectedGuid()
      ? "<b>Tag the selected element</b>" : "<b>Select an element</b>, or use a saved selection set below.", ""));
    if (d.selectedGuid()) {
      const rowS = document.createElement("div"); rowS.className = "level-row";
      for (const [ph, lbl] of PHASES) {
        const bt = document.createElement("button"); bt.className = "mini-btn"; bt.textContent = lbl;
        // Re-read at CLICK time. The row was rendered while something was selected; that is not a
        // promise it still is when the button is pressed.
        bt.onclick = () => {
          const guid = d.selectedGuid();
          if (!guid) { d.notify("nothing selected any more — pick an element again", "error"); return; }
          void tag(ph, [guid], "selection");
        };
        rowS.appendChild(bt);
      }
      body.appendChild(rowS);
    }
    for (const s of sets) {
      const row = document.createElement("div"); row.className = "level-row";
      const label = document.createElement("span"); label.className = "meta";
      label.textContent = `${s.name} · ${s.guids.length}`; label.style.flex = "1"; row.appendChild(label);
      for (const [ph, lbl] of PHASES) {
        const bt = document.createElement("button"); bt.className = "mini-btn"; bt.textContent = lbl.slice(0, 2);
        bt.title = `Tag "${s.name}" as ${ph}`; bt.onclick = () => void tag(ph, s.guids, s.name);
        row.appendChild(bt);
      }
      body.appendChild(row);
    }
    const iso = d.toolBtn2("◎ Isolate a phase in 3D", async () => {
      try {
        const r = await d.api.colorBy(d.pid, "Massing_Phasing.Status", 6);
        showResult("Isolate by phase", (b2) => {
          if (!r.buckets.length) { b2.appendChild(resultNote("No phased elements yet.", "")); return; }
          for (const bk of r.buckets) {
            b2.appendChild(d.toolBtn2(`◎ ${bk.label} · ${bk.count}`,
              () => { void d.layerMgr.isolateGuids(bk.guids); d.notify(`isolated ${bk.count} · ${bk.label}`, "success"); }));
          }
          b2.appendChild(d.toolBtn2("Show all", () => { void d.layerMgr.showAll?.(); }));
        });
      } catch (e) { d.notify(`isolate failed: ${(e as Error).message}`, "error"); }
    });
    iso.style.marginTop = "6px"; body.appendChild(iso);
  });
}

// ── level of development ──────────────────────────────────────────────────────────────────────────

export async function openLodPanel(d: ModelStateDeps): Promise<void> {
  let sum;
  try { sum = await d.api.lodSummary(d.pid); }
  catch (e) { d.notify(`LOD failed: ${(e as Error).message}`, "error"); return; }
  const sets = loadSelSets(d.pid);
  showResult("Level of Development (schematic → construction)", (body) => {
    body.appendChild(kvTable(LODS.map((s) => ({
      k: `LOD ${s}`, v: String(sum.counts[s]), bar: sum.total ? sum.counts[s] / sum.total : 0 }))
      .concat([{ k: "Unstaged", v: String(sum.counts.UNSET), bar: sum.total ? sum.counts.UNSET / sum.total : 0 }])));
    const tag = async (stage: typeof LODS[number], guids: string[], what: string) => {
      if (!guids.length) { d.notify("nothing to stage", "error"); return; }
      await d.authorAndReload("set_lod", { guids, stage }, `${what} → LOD ${stage}`);
      await openLodPanel(d);
    };
    body.appendChild(resultNote(d.selectedGuid()
      ? "<b>Set the selected element's LOD</b>" : "<b>Select an element</b> or use a saved selection set.", ""));
    if (d.selectedGuid()) {
      const row = document.createElement("div"); row.className = "level-row";
      for (const s of LODS) {
        const bt = document.createElement("button"); bt.className = "mini-btn"; bt.textContent = s;
        bt.onclick = () => {
          const guid = d.selectedGuid();
          if (!guid) { d.notify("nothing selected any more — pick an element again", "error"); return; }
          void tag(s, [guid], "selection");
        };
        row.appendChild(bt);
      }
      body.appendChild(row);
    }
    for (const s of sets) {
      const row = document.createElement("div"); row.className = "level-row";
      const label = document.createElement("span"); label.className = "meta";
      label.textContent = `${s.name} · ${s.guids.length}`; label.style.flex = "1"; row.appendChild(label);
      for (const st of LODS) {
        const bt = document.createElement("button"); bt.className = "mini-btn"; bt.textContent = st;
        bt.title = `Set "${s.name}" to LOD ${st}`; bt.onclick = () => void tag(st, s.guids, s.name); row.appendChild(bt);
      }
      body.appendChild(row);
    }
    const ctx = d.toolBtn2("⚙ Establish drawing contexts", async () => {
      try {
        const r = await d.api.ensureContexts(d.pid);
        const created = (r.changed as { created?: number })?.created ?? 0;
        d.notify(created ? `created ${created} view context(s)` : "drawing contexts already present", "success");
      } catch (e) { d.notify(`contexts failed: ${(e as Error).message}`, "error"); }
    });
    ctx.style.marginTop = "6px";
    ctx.title = "Create the Model+Plan / Body·Axis·Box·Annotation·FootPrint representation contexts "
      + "(by TargetView) that construction-drawing generation needs. Idempotent.";
    body.appendChild(ctx);
  });
}

// ── as-built verification (LOD 500) ───────────────────────────────────────────────────────────────

export async function openAsBuiltPanel(d: ModelStateDeps): Promise<void> {
  let s;
  try { s = await d.api.lod500(d.pid); }
  catch { toast("Needs a source IFC", "error"); return; }
  showResult("As-built verification (LOD 500)", (body) => {
    body.appendChild(resultNote(`<b>LOD 500</b> is a field-verified as-built reliability attribute — BIMForum sets no `
      + `geometric requirement for it. Model readiness: <b>${s!.readiness_pct}%</b> `
      + `(${s!.verified} of ${s!.total} elements verified). O&M data: <b>${s!.with_manufacturer}</b> with manufacturer · `
      + `<b>${s!.with_serial}</b> with serial · <b>${s!.with_dimensions}</b> dimensioned`
      + (s!.dimensions_out_of_tolerance ? ` (<b>${s!.dimensions_out_of_tolerance}</b> out of tolerance)` : "")
      + (s!.with_om_docs ? ` · <b>${s!.with_om_docs}</b> with O&M/warranty docs` : "")
      + `.`, s!.readiness_pct >= 100 ? "ok" : ""));
    if (Object.keys(s!.by_method).length) {
      body.appendChild(kvTable(Object.entries(s!.by_method).map(([k, v]) => ({ k, v: `${v} element(s)` }))));
    }

    /** Every stamp here is the same shape: write, wait for the republish, reload, refresh pins. */
    const stamp = async (what: string, run: (guid: string) => Promise<void>) => {
      const guid = d.selectedGuid();
      if (!guid) { d.notify("select the element(s) first", "error"); return; }
      await withLoading(d.container, `${what} + republishing`, async () => {
        try {
          await run(guid);
          const state = await d.waitForPublish(d.projectId!);
          if (state === "done") { await d.loadProjectModel(); d.notify(`${what} — done`, "success"); }
          else d.notify(`${what} — publish ${state}`, state === "error" ? "error" : "info");
          await d.reloadModelPins();
        } catch (e) { d.notify(`${what} failed: ${(e as Error).message}`, "error"); }
      });
    };

    const form = document.createElement("div"); form.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:6px 0";
    const who = document.createElement("input"); who.className = "portal-filter"; who.placeholder = "verified by"; who.style.cssText = "flex:1 1 100px;min-width:0;font-size:12px";
    const method = document.createElement("select"); method.className = "portal-filter"; method.style.fontSize = "12px";
    for (const mth of s!.methods) { const o = document.createElement("option"); o.value = mth; o.textContent = mth; method.appendChild(o); }
    form.append(who, method); body.appendChild(form);
    const doVerify = d.toolBtn2("✅ Verify selection as-built", () => void stamp("stamping as-built verification",
      (guid) => d.api.verifyAsbuilt(d.pid, [guid], { verified_by: who.value.trim(), method: method.value }, true).then(() => undefined)));
    doVerify.title = "Stamp the selected element(s) with Massing_AsBuilt (VERIFIED + who/when/method) — the "
      + "field-verified reliability layer that makes it a genuine LOD-500 record.";
    body.appendChild(doVerify);

    body.appendChild(resultNote("<b>Manufacturer / serial</b> (O&M · turnover) — stamps the standard "
      + "Pset_Manufacturer* on the selection; round-trips to COBie / asset systems.", ""));
    const mf = document.createElement("div"); mf.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:4px 0";
    const mkIn = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "flex:1 1 90px;min-width:0;font-size:12px"; return i; };
    const manIn = mkIn("manufacturer"); const modIn = mkIn("model"); const serIn = mkIn("serial"); const yrIn = mkIn("year");
    mf.append(manIn, modIn, serIn, yrIn); body.appendChild(mf);
    const doMfr = d.toolBtn2("🏷 Stamp manufacturer/serial on selection", () => {
      if (![manIn, modIn, serIn, yrIn].some((i) => i.value.trim())) { d.notify("fill at least one field", "error"); return; }
      void stamp("stamping manufacturer/serial", (guid) => d.api.setManufacturerInfo(d.pid, [guid],
        { manufacturer: manIn.value.trim(), model_label: modIn.value.trim(), serial: serIn.value.trim(), production_year: yrIn.value.trim() },
        true).then(() => undefined));
    });
    body.appendChild(doMfr);

    body.appendChild(resultNote("<b>Field-verified dimension</b> — record a measured value (+ optional "
      + "design value) → variance vs design, the dimensional half of LOD 500.", ""));
    const df = document.createElement("div"); df.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:4px 0";
    const dimName = document.createElement("input"); dimName.className = "portal-filter"; dimName.placeholder = "dimension (Length)"; dimName.value = "Length"; dimName.style.cssText = "flex:1 1 90px;min-width:0;font-size:12px";
    const measIn = mkIn("measured (m)"); const desIn = mkIn("design (m, opt)");
    df.append(dimName, measIn, desIn); body.appendChild(df);
    const doDim = d.toolBtn2("📏 Record measured dimension on selection", () => {
      const meas = parseFloat(measIn.value);
      if (!isFinite(meas)) { d.notify("enter a measured value", "error"); return; }
      const des = parseFloat(desIn.value);
      void stamp("recording as-built dimension", (guid) => d.api.recordAsbuiltDimension(d.pid, [guid],
        dimName.value.trim() || "Length", meas, isFinite(des) ? des : undefined, true).then(() => undefined));
    });
    body.appendChild(doDim);

    body.appendChild(resultNote("<b>O&M / warranty document</b> — attach a manual/warranty reference "
      + "(name + link) to the selection via IfcRelAssociatesDocument; counts toward turnover readiness.", ""));
    const of = document.createElement("div"); of.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:4px 0";
    const docName = mkIn("document name"); const docUrl = mkIn("link / URI (opt)");
    const docKind = document.createElement("select"); docKind.className = "portal-filter"; docKind.style.fontSize = "12px";
    for (const [v, l] of [["om", "O&M manual"], ["warranty", "warranty"]] as const) { const o = document.createElement("option"); o.value = v; o.textContent = l; docKind.appendChild(o); }
    of.append(docName, docUrl, docKind); body.appendChild(of);
    const doDoc = d.toolBtn2("📄 Attach O&M / warranty doc to selection", () => {
      if (!docName.value.trim()) { d.notify("enter a document name", "error"); return; }
      void stamp("attaching document", (guid) => d.api.attachOmDocument(d.pid, [guid], docName.value.trim(),
        { location: docUrl.value.trim() || undefined, kind: docKind.value as "om" | "warranty" }, true).then(() => undefined));
    });
    body.appendChild(doDoc);
  });
}
