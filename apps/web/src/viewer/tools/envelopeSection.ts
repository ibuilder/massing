import type * as THREE from "three";

import type { ApiClient } from "../../api/client";
import { withLoading } from "../../ui/feedback";
import { askText } from "../../ui/prompt";
import { resultNote, showResult } from "../../ui/result";

/**
 * R39-DECOMP-VIEWER ⑫ — **envelope & free-form geometry**, out of `app.ts`.
 *
 * Three authoring tools: a curtain wall along a line, a sloped wall top, and a raw mesh from
 * verts/faces JSON — the escape hatch for geometry the parametric recipes cannot express.
 *
 * ## Two things about this slice that are findings, not notes
 *
 * **It is two non-contiguous ranges.** The sandboxed IFC-code runner sits between the curtain wall
 * and the slope/mesh pair in `app.ts`, and it stays there: it is a *code sandbox*, a different
 * concern with a different risk profile, and folding it in for the sake of one contiguous cut would
 * trade cohesion for convenience. Extraction boundaries follow meaning, not line numbers.
 *
 * **The annotation group was tried first and rejected.** The roadmap claimed both remaining groups
 * were renderer-free. That was written without checking, and it was wrong: the annotation tools add
 * and remove objects on the live `viewer.world.scene.three`, raycast through `screenToGround`, and
 * **assign** to `annotGuide` / `guideWired`, which are `let` in `app.ts`. Reading a mutable capture
 * through an accessor is cheap; *writing* one across a seam needs a setter pair, and the result would
 * still need a WebGL context — which is precisely the untestability these extractions exist to
 * escape. So the renderer-free seam ends here. What is left needs a different technique: move the
 * scene state into the module and let it own its objects, rather than reaching back through a seam.
 *
 * The check that settled it was a **typecheck of the unwired module** — written, present in the
 * project, imported by nothing. `tsc` listed `viewer`, `screenToGround`, `annotGuide`, `guideWired`
 * and four more in one pass, before a single line of `app.ts` had been touched.
 */
export interface EnvelopeDeps {
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  pid: string;
  projectId: string | null;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  container: HTMLElement;
  /** **Accessor.** Rewritten on every click in the 3D view; the curtain wall starts from it. */
  lastPoint: () => THREE.Vector3 | null;
  /** **Accessor.** Changes with the selection; the slope tool acts on it. */
  selectedGuid: () => string | null;
  /** Re-fetches and re-tessellates. `Promise<boolean>` -- the boolean is whether it SUCCEEDED. */
  loadProjectModel: () => Promise<boolean>;
  /** Re-hangs BCF pins after the geometry changes underneath them. */
  reloadModelPins: () => Promise<void>;
  /** Blocks until the server finishes republishing. */
  waitForPublish: (jobId: string) => Promise<unknown>;
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string,
                    previewId?: string | null, previewGuid?: string)
                   => Promise<{ applied: boolean; refused: boolean }>;
}

/** The three envelope buttons, named so re-ordering cannot silently re-map them. */
export interface EnvelopeButtons {
  curtainBtn: HTMLButtonElement;
  slopeBtn: HTMLButtonElement;
  meshBtn: HTMLButtonElement;
}

export function buildEnvelopeSection(d: EnvelopeDeps): EnvelopeButtons {
  // W11 B6: curtain wall along a line (start = last-clicked point, end from a prompt).
  const curtainBtn = d.toolBtn2("🪟 Curtain wall", async () => {
    // One read at click time. The ternary called the accessor three times, so neither
  // branch could narrow, and in principle the three calls could disagree.
  const pt = d.lastPoint();
  const start: [number, number] = pt ? [pt.x, -pt.z] : [0, 0];
    const endS = await askText("Curtain wall", { label: "End point E, N (metres) — start is the last click", value: `${(start[0] + 6).toFixed(1)}, ${start[1].toFixed(1)}` });
    if (!endS) return;
    const ep = endS.split(",").map((v) => Number(v.trim()));
    const grid = await askText("Curtain wall", { label: "Bays × rows (cols, rows)", value: "3, 2" });
    const g = (grid || "3,2").split(/[,x×]/).map((v) => Math.max(1, Math.round(Number(v.trim()) || 1)));
    await d.authorAndReload("add_curtain_wall",
      { start, end: [ep[0] ?? start[0] + 6, ep[1] ?? start[1]], cols: g[0] ?? 3, rows: g[1] ?? 2 },
      "curtain wall");
  });
  curtainBtn.title = "Author an IfcCurtainWall along a line — vertical mullions + horizontal transoms + "
    + "glazing panels on a bays×rows grid, aggregated as one assembly (LOD 350/400). GUID-stable.";

  // B3 — sloped-top wall (parapet slope / shed / gable): rebuild the selected wall's top to slope
  // from start_height → end_height.
  const slopeBtn = d.toolBtn2("⟋ Slope wall top", () => {
    const guid = d.selectedGuid();
    if (!guid) { d.notify("select a wall first", "error"); return; }
    showResult("Slope wall top", (body) => {
      body.appendChild(resultNote("Give the selected wall a <b>sloped top</b> — the top rises from "
        + "the start height (at the wall's start point) to the end height (parapet slope / shed / "
        + "gable). GUID-stable, versioned (undo restores the flat top).", ""));
      const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;margin:4px 0";
      const sIn = document.createElement("input"); sIn.type = "number"; sIn.className = "portal-filter"; sIn.placeholder = "start height (m)"; sIn.step = "0.1"; sIn.style.cssText = "flex:1;min-width:0;font-size:12px";
      const eIn = document.createElement("input"); eIn.type = "number"; eIn.className = "portal-filter"; eIn.placeholder = "end height (m)"; eIn.step = "0.1"; eIn.style.cssText = "flex:1;min-width:0;font-size:12px";
      row.append(sIn, eIn); body.appendChild(row);
      const go = d.toolBtn2("⟋ Apply slope + republish", async () => {
        const sh = parseFloat(sIn.value), eh = parseFloat(eIn.value);
        if (!(sh > 0) || !(eh > 0)) { d.notify("enter positive start & end heights", "error"); return; }
        await withLoading(d.container, "sloping the wall top + republishing", async () => {
          try {
            await d.api.setWallSlope(d.pid, guid, sh, eh, true);
            const state = await d.waitForPublish(d.projectId!);
            if (state === "done") { await d.loadProjectModel(); d.notify("wall top sloped", "success"); }
            else d.notify(`sloped — publish ${state}`, state === "error" ? "error" : "info");
            await d.reloadModelPins();
          } catch (e) { d.notify(`slope failed: ${(e as Error).message}`, "error"); }
        });
      });
      body.appendChild(go);
    });
  });
  slopeBtn.title = "Give the selected wall a sloped top (start height → end height) — parapet slope, "
    + "shed, or gable wall. Rebuilds the Body as a trapezoidal extrusion; GUID-stable + undo-able.";

  // B4 — procedural-mesh escape hatch: author an element from a raw triangle mesh (JSON verts/faces).
  const meshBtn = d.toolBtn2("△ Add mesh (verts/faces JSON)", () => {
    showResult("Add procedural mesh", (body) => {
      body.appendChild(resultNote("Author an element from a raw triangle mesh for geometry the "
        + "recipes can't express. Paste <code>{\"verts\":[[x,y,z]…],\"faces\":[[i,j,k]…]}</code> "
        + "(faces are 0-based vertex indices, coords in metres). GUID-stable + undo-able.", ""));
      const ta = document.createElement("textarea"); ta.className = "portal-filter";
      ta.style.cssText = "width:100%;min-height:100px;font-family:monospace;font-size:12px";
      ta.placeholder = '{"verts":[[0,0,0],[2,0,0],[2,2,0],[0,2,0],[1,1,2]],"faces":[[0,1,4],[1,2,4],[2,3,4],[3,0,4],[0,2,1],[0,3,2]]}';
      body.appendChild(ta);
      const go = d.toolBtn2("△ Add mesh + republish", async () => {
        let parsed: { verts?: number[][]; faces?: number[][] };
        try { parsed = JSON.parse(ta.value); } catch { d.notify("invalid JSON", "error"); return; }
        if (!parsed.verts?.length || !parsed.faces?.length) { d.notify("need verts and faces", "error"); return; }
        await withLoading(d.container, "authoring mesh + republishing", async () => {
          try {
            await d.api.addMesh(d.pid, parsed.verts!, parsed.faces!, "Mesh", true);
            const state = await d.waitForPublish(d.projectId!);
            if (state === "done") { await d.loadProjectModel(); d.notify("mesh added", "success"); }
            else d.notify(`added — publish ${state}`, state === "error" ? "error" : "info");
            await d.reloadModelPins();
          } catch (e) { d.notify(`mesh failed: ${(e as Error).message}`, "error"); }
        });
      });
      body.appendChild(go);
    });
  });
  meshBtn.title = "Author an element from a raw triangle mesh (IfcTriangulatedFaceSet) — the escape "
    + "hatch for geometry the parametric recipes can't express.";

  return { curtainBtn, slopeBtn, meshBtn };
}
