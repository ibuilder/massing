import type { ApiClient } from "../../api/client";
import { kvTable, showResult } from "../../ui/result";
import { openTakeoff2d } from "../takeoff2d";

/**
 * R39-DECOMP-VIEWER ① — the Exports & issue tool section, out of `app.ts`.
 *
 * The first slice of the viewer decomposition, chosen to prove the recipe rather than to move the
 * most lines. `app.ts` is 5,160 lines and `buildToolsPanel` alone is 3,071 of them (60%), holding a
 * 1,257-line `builders` map of which this is the smallest member at 51.
 *
 * ## The recipe, and why it is not the SCALE-SEAM one
 *
 * `client.ts` could be split against `surface.test.ts`, which pins its public surface and fails if a
 * method stops existing. **`app.ts` has no such gate — nothing in the suite imports it at all**,
 * because `createViewerApp` needs a WebGL context and a Fragments worker. So a green suite says
 * nothing about a move here, and the recipe has to get its safety somewhere else:
 *
 *  1. **Every dependency is an explicit typed parameter.** A capture that fails to be threaded is
 *     then a *compile error*, so `tsc` — not the suite — is the parity gate for this work.
 *  2. **Mutable state is passed as an accessor, never by value.** This is the one failure class
 *     `tsc` cannot see: `app.ts` holds `selectedGuid` and `lastPoint` as `let`, so passing either by
 *     value would compile cleanly and silently freeze whatever it held at panel-build time. It is
 *     removed by construction rather than by remembering. **This section touches neither**, which is
 *     part of why it goes first — but `ExportsDeps` is shaped so the next one can.
 *  3. **Renderer-free slices first.** The file is untested *because* it needs a renderer, and risky
 *     to split *for the same reason* — the absence is self-reinforcing. Extracting the parts that
 *     need no renderer first is what makes them testable at all; this module is pure DOM assembly
 *     over an API client, and can be unit-tested in a way `app.ts` never could.
 *
 * `section` and `toolBtn2` arrive as **functions**, not as the state they close over. Both are
 * declared inside `buildToolsPanel` and already capture the panel, the persona ordering and the
 * `hasIfc` flag; handing them over whole is what turns a long list of captures into a signature.
 */

export interface ExportsDeps {
  /** Creates the tool group, or returns null when its `requires` gate is unmet. */
  section: (key: string, title: string,
            opts?: { requires?: "project" | "sourceIfc"; tool?: boolean }) => HTMLElement | null;
  /** A full-width tool button. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  /** `const` in `app.ts`, so a value is safe here. Anything `let` must arrive as an accessor. */
  projectId: string | null;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
}

/** Build the "Document · Exports & issue" section. No-op when its gate refuses. */
export function buildExportsSection(d: ExportsDeps): void {
  const { section, toolBtn2, api, projectId, notify } = d;
  const b = section("exports", "Document · Exports & issue", { requires: "sourceIfc", tool: true });
  if (!b) return;

  for (const [label, file] of [["Quantity takeoff (QTO/5D)", "qto"], ["COBie", "cobie"],
                               ["Space schedule", "spaces"], ["4D schedule", "schedule"]] as const) {
    b.appendChild(toolBtn2(`↓ ${label}`,
      () => window.open(api.url(`/projects/${projectId}/exports/${file}.xlsx`), "_blank")));
  }

  // gbXML — spaces + envelope areas for OpenStudio / EnergyPlus / IES energy modelling
  const gbx = toolBtn2("↓ gbXML (energy model)",
    () => window.open(api.url(`/projects/${projectId}/exports/model.gbxml`), "_blank"));
  gbx.title = "Green Building XML — spaces + areas/volumes from the IFC geometry, to seed an energy "
    + "model (OpenStudio/EnergyPlus/IES). Simplified: building-level envelope, not per-space surfaces.";
  b.appendChild(gbx);

  // ENERGY phase 1 — the thermal-model writers. Distinct from the simplified gbXML above:
  // these serialize zones / surfaces / constructions from `energy_export`. The client method
  // existed with no caller; both formats it offers were frozen as deliberately unreachable.
  const envGbx = toolBtn2("↓ Energy envelope (gbXML)", () => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    window.open(api.energyExportUrl(projectId, "gbxml"), "_blank");
  });
  envGbx.title = "Thermal envelope as gbXML — Campus / Building / Space / Surface + Construction "
    + "from the IFC assemblies. Geometry and constructions only; no HVAC, schedules or loads.";
  b.appendChild(envGbx);

  const envIdf = toolBtn2("↓ EnergyPlus IDF", () => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    window.open(api.energyExportUrl(projectId, "idf"), "_blank");
  });
  envIdf.title = "EnergyPlus IDF envelope — Building / Zone / Material / Construction / "
    + "BuildingSurface:Detailed. Add HVAC, schedules and loads in the simulation setup.";
  b.appendChild(envIdf);

  // discipline quantities — reinforcement tonnage, MEP linear runs, structural volume
  b.appendChild(toolBtn2("🔩 Discipline quantities", async () => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    try {
      const q = await api.disciplineQuantities(projectId);
      showResult("Discipline quantities", (body) => {
        body.appendChild(kvTable([
          { k: `Reinforcement${q.rebar.estimated ? " (est. from volume)" : ""}`,
            v: `${q.rebar.tonnes} t · ${q.rebar.count} bars` },
          { k: "Ductwork", v: `${q.mep.duct_m} m · ${q.mep.counts.duct} seg` },
          { k: "Piping", v: `${q.mep.pipe_m} m · ${q.mep.counts.pipe} seg` },
          { k: "Cable / carrier", v: `${q.mep.cable_m} m · ${q.mep.counts.cable} seg` },
          { k: "MEP fittings", v: String(q.mep.counts.fittings) },
          { k: "Structural element volume", v: `${q.structure.element_volume_m3} m³` },
        ]));
      });
    } catch (e) { notify(`quantities failed: ${(e as Error).message}`, "error"); }
  }));

  // full turnover deliverable: as-built IFC + COBie/QTO/spaces + status PDF + closeout records
  const pkg = toolBtn2("📦 Closeout package (.zip)",
    () => window.open(api.url(`/projects/${projectId}/closeout/package.zip`), "_blank"));
  pkg.title = "Everything for handover in one ZIP: as-built model, data workbooks, status report, closeout records";
  b.appendChild(pkg);

  // geometry / model interchange exports (EXPORT)
  const ifcOut = toolBtn2("⬇ Export IFC (source of truth)",
    () => window.open(api.modelIfcUrl(projectId!), "_blank"));
  ifcOut.title = "First-class IFC re-export — the current authored source IFC, GUID-stable, round-trips through any openBIM tool";
  b.appendChild(ifcOut);

  const ifcx = toolBtn2("⬇ Export IFC5 JSON (.ifcx)", () => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    window.open(api.modelExportIfcxUrl(projectId), "_blank");
  });
  ifcx.title = "IFC5 data layer as ifcJSON — properties and structure, not geometry";
  b.appendChild(ifcx);

  const fp = toolBtn2("⬇ Footprint (GeoJSON)", () => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    window.open(api.footprintGeojsonUrl(projectId), "_blank");
  });
  fp.title = "WGS84 FeatureCollection of the building footprint + site point for a web map";
  b.appendChild(fp);

  const compiled = toolBtn2("⬇ Compiled drawing set (PDF)", () => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    window.open(api.compiledPdfUrl(projectId), "_blank");
  });
  compiled.title = "Cover, floor plans, and door/window/room schedules in one PDF";
  b.appendChild(compiled);

  const pkgPdf = toolBtn2("⬇ Project package (PDF)", () => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    window.open(api.projectPackagePdfUrl(projectId), "_blank");
  });
  pkgPdf.title = "Shareable package: cover, views, drawing set, cost and feasibility summary";
  b.appendChild(pkgPdf);

  const glb = toolBtn2("⬇ Export 3D (.glb)", () => window.open(api.modelGlbUrl(projectId!), "_blank"));
  glb.title = "Binary glTF — the compact single-file 3D form Blender / three.js / game engines import directly";
  b.appendChild(glb);

  const gltf = toolBtn2("⬇ Export 3D (.gltf)", () => window.open(api.modelGltfUrl(projectId!), "_blank"));
  gltf.title = "Self-contained glTF 2.0 JSON (interchange)";
  b.appendChild(gltf);

  // TAKEOFF-2D — quantify from an uploaded drawing (no model needed), feeds the 5D estimate
  const to2d = toolBtn2("📐 2D takeoff (from a drawing)", () => {
    if (!projectId) { notify("connect a project first", "error"); return; }
    openTakeoff2d({
      quantify: (regions, sc, unit, scoping) =>
        api.takeoff2d(projectId, regions, sc, unit, scoping),
      // R27-LAYOUT — the producer for the `layout` the takeoff scopes against. Passing the fetcher
      // rather than the layout means the request only happens when the tool is opened, and a project
      // with no model simply never shows the control.
      sheetLayout: (preset, page) => api.sheetRegions(projectId, preset, page),
      notify,
    });
  });
  to2d.title = "Upload a PDF-page image / scan, calibrate the scale, trace or flood-fill regions → priced quantities into the 5D estimate";
  b.appendChild(to2d);
}
