import type { ApiClient } from "../../api/client";
import type { ModelSetupFacts } from "../../api/model";
import { escapeHtml, toast, withLoading } from "../../ui/feedback";
import { kvTable, resultNote, showResult } from "../../ui/result";

/**
 * MODEL-SETUP — the project's UNITS and its ORIGIN: what they are, and how to change them.
 *
 * ## Why this module exists at all
 *
 * `services/api/src/aec_api/authoring_matrix.py` keeps an `UNREACHED` set and calls it, in its own
 * words, *"a capability no user can reach", which is a defect*. Two of its members are whole-model
 * setup operations that have been in the recipe registry — and therefore runnable through
 * `POST /projects/{pid}/edit` — the entire time:
 *
 *   `convert_length_unit`  rescales the length data so real-world size is unchanged, and reports
 *                          every entity type it touched so the conversion is auditable.
 *   `rebase_origin`        shifts every ROOT placement so a chosen model point becomes the origin
 *                          **and pushes the same offset into the `IfcMapConversion`**, so the
 *                          real-world coordinate of every element is unchanged. That is the
 *                          georeferencing rule this project states as a non-negotiable — implemented
 *                          correctly, and until now with nothing on screen to invoke it.
 *
 * ## Why the diagnosis moved here rather than the repair moving there
 *
 * `🌍 Georeferencing (survey basis / LoGeoRef)` was in `qaSection.ts`, forty lines of pure report.
 * It is the diagnosis for exactly the condition `rebase_origin` repairs, and this codebase has
 * already paid for keeping those apart: `repairPanel.ts` exists because the wall-join detector and
 * the wall-join fix shipped on opposite sides of the app and each looked complete alone.
 *
 * It also pays for the addition. `qaSection.ts` sits **exactly** on its `test_file_sizes.py` pin, so
 * two new controls could not simply be appended — the ratchet's remedy is extraction, never
 * headroom, and taking the related read along is what makes this an extraction rather than a move.
 *
 * ## The state has to be visible before either repair can be offered
 *
 * Neither control could be built before `GET /projects/{pid}/model/setup` existed, because nothing
 * exposed the current unit. *"Convert to millimetres"* with no statement of the present unit is a
 * coin flip the user is asked to call. The panel therefore reads first and offers second — the same
 * shape as the wall-joins tool next door, and for the same reason.
 */
export interface ProjectSetupDeps {
  api: ApiClient;
  pid: string;
  /** A full-width tool button, owned by `buildToolsPanel` and handed over whole. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  /** The element the section writes its one-line result into. */
  out: HTMLElement;
  /** The surface `withLoading` dims while a request is in flight. */
  container: HTMLElement;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** Runs an edit recipe and republishes. The REAL signature — a narrowed `Promise<void>` would let
   *  a caller treat a REFUSED edit as a successful one. */
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string)
                   => Promise<{ applied: boolean; refused: boolean }>;
}

/** The survey basis, unchanged from where it used to live in `qaSection.ts`. */
export function georeferencingButton(d: ProjectSetupDeps): HTMLButtonElement {
  const { api, pid, out, container, toolBtn2 } = d;
  return toolBtn2("🌍 Georeferencing (survey basis / LoGeoRef)", () => withLoading(container, "Reading survey basis", async () => {
    let r;
    try { r = await api.modelGeoreferencing(pid); }
    catch (e) { toast((e as Error).message, "error"); return; }
    out.textContent = r.level_label;
    showResult("Georeferencing", (body) => {
      // The level IS the verdict — a bare "georeferenced: true" hides the difference between an
      // elevation-only model and a projected CRS, and those export very differently.
      body.appendChild(resultNote(
        `<b>${escapeHtml(r!.level_label)}</b>${r!.note ? " — " + escapeHtml(r!.note) : ""}`,
        r!.level >= 40 ? "ok" : r!.level === 0 ? "bad" : ""));
      const rows: { k: string; v: string }[] = [];
      const mc = r!.map_conversion, crs = r!.crs, site = r!.site;
      // Every field is rendered as "not set" rather than omitted when absent. An absent row and
      // a zero row look identical once one is missing, and eastings of 0 is a real value.
      const num = (v: number | null | undefined) => (typeof v === "number" ? String(v) : "not set");
      if (mc) {
        rows.push({ k: "Eastings", v: num(mc.eastings) }, { k: "Northings", v: num(mc.northings) },
          { k: "Orthogonal height", v: num(mc.orthogonal_height) },
          { k: "True north bearing", v: mc.true_north_bearing_deg == null ? "not set" : `${mc.true_north_bearing_deg}°` },
          { k: "Scale", v: num(mc.scale) });
      }
      if (crs) {
        rows.push({ k: "CRS", v: crs.name || "not set" }, { k: "Geodetic datum", v: crs.geodetic_datum || "not set" },
          { k: "Vertical datum", v: crs.vertical_datum || "not set" },
          { k: "Map projection", v: crs.map_projection || "not set" }, { k: "Map zone", v: crs.map_zone || "not set" });
      }
      if (site) {
        const dms = (v: number[] | null) => (Array.isArray(v) && v.length ? v.join("° ") : "not set");
        rows.push({ k: "Site latitude", v: dms(site.ref_latitude) }, { k: "Site longitude", v: dms(site.ref_longitude) },
          { k: "Site elevation", v: num(site.ref_elevation) });
      }
      if (!rows.length) {
        body.appendChild(resultNote("No IfcMapConversion, projected CRS or IfcSite reference — "
          + "the model carries no survey basis at all.", "bad"));
        return;
      }
      body.appendChild(kvTable(rows));
    });
  }));
}

/** MODEL-SETUP — change the project length unit, real-world size unchanged. */
export function projectUnitsButton(d: ProjectSetupDeps): HTMLButtonElement {
  const { api, pid, toolBtn2, notify, container, authorAndReload } = d;
  return toolBtn2("📏 Project units (metre / mm / cm)", () => withLoading(container, "Reading project units", async () => {
    let facts;
    try { facts = await api.modelSetup(pid); }
    catch (e) { notify((e as Error).message, "error"); return; }
    showResult("Project units", (body) => {
      // **The panel is REDRAWN from a fresh read after a conversion, never left showing the unit the
      // project had before it.** Converting is not a one-shot: m -> mm -> cm is an ordinary thing to
      // do, and a second conversion offered against the FIRST reading would name the wrong source
      // unit and disable the wrong option. Re-measuring is the same choice the wall-joins tool next
      // door makes for the same reason — the request having succeeded is not a measurement.
      const render = (f: ModelSetupFacts) => {
        body.replaceChildren();
        body.appendChild(resultNote(
          `The project reads in <b>${escapeHtml(f.length_unit ?? "an unrecognised unit")}</b>`
          + (f.length_unit_metres ? ` (${f.length_unit_metres} m per unit)` : "")
          + ". Converting rescales the length data so the building stays the same real size — only the "
          + "numbers change. GUID-stable: pins, RFIs and clashes survive.",
          f.convertible ? "" : "bad"));
        if (!f.convertible) {
          body.appendChild(resultNote("This file carries no LENGTHUNIT assignment, so there is nothing "
            + "to convert from. Nothing was changed.", "bad"));
          return;
        }
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0";
        const lbl = document.createElement("span"); lbl.className = "meta"; lbl.textContent = "convert to";
        const sel = document.createElement("select"); sel.className = "portal-filter";
        sel.style.cssText = "font-size:12px";
        // The options come from the SERVER's own accepted list. Hardcoding them here is how a dropdown
        // ends up offering a unit the recipe refuses — the client would render a 400 as a bug report.
        for (const t of f.targets) {
          const o = document.createElement("option"); o.value = t; o.textContent = t;
          if (t === f.length_unit) o.disabled = true;             // already there; nothing to do
          sel.appendChild(o);
        }
        if (f.length_unit && f.targets.includes(f.length_unit)) {
          const first = f.targets.find((t) => t !== f.length_unit);
          if (first) sel.value = first;
        }
        const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Convert";
        go.onclick = async () => {
          const to = sel.value;
          go.disabled = true; sel.disabled = true; go.textContent = "Converting…";
          const res = await authorAndReload("convert_length_unit", { to }, `convert units to ${to}`);
          if (!res.applied || res.refused) {
            go.disabled = false; sel.disabled = false; go.textContent = "Convert";
            return;
          }
          notify(`project now reads in ${to}`, "success");
          // A failed re-read must not leave the OLD unit on screen looking current: the conversion
          // did land, so the figures above are known-stale whether or not the re-read succeeds.
          try { render(await api.modelSetup(pid)); }
          catch (e) {
            body.replaceChildren();
            body.appendChild(resultNote(`Converted to <b>${escapeHtml(to)}</b>, but re-reading the `
              + `project failed: ${escapeHtml((e as Error).message)}. Reopen this panel to see the `
              + "current unit.", ""));
          }
        };
        row.append(lbl, sel, go);
        body.appendChild(row);
      };
      render(facts!);
    });
  }));
}

/** MODEL-SETUP — move the model near the file origin without moving the building on the earth. */
export function projectOriginButton(d: ProjectSetupDeps): HTMLButtonElement {
  const { api, pid, toolBtn2, notify, container, authorAndReload } = d;
  return toolBtn2("📍 Project origin (rebase far-from-origin geometry)", () => withLoading(container, "Measuring distance from origin", async () => {
    let facts;
    try { facts = await api.modelSetup(pid); }
    catch (e) { notify((e as Error).message, "error"); return; }
    showResult("Project origin", (body) => {
      // **The point is in the coordinates the model has NOW, and rebasing is NOT idempotent by
      // point.** Rebase to (1000, 2000) and the model moves; do it again against the figures this
      // form was opened with and it moves a second time, because the coordinates those figures
      // describe no longer exist. So the panel is redrawn from a FRESH read after every applied
      // rebase — the distance shown, and the frame the next point is expressed in, are both
      // re-measured. That is the same choice the wall-joins tool next door makes, and for the same
      // reason: a request having succeeded is not a measurement of what it did.
      const render = (f: ModelSetupFacts) => {
        body.replaceChildren();
        const far = f.distance_from_origin;
        body.appendChild(resultNote(
          `The furthest root placement sits <b>${far.toFixed(1)}</b> file units from the origin`
          + (f.distance_from_origin_m != null ? ` (${f.distance_from_origin_m.toFixed(1)} m)` : "")
          + `, across ${f.root_placements} root placement${f.root_placements === 1 ? "" : "s"}. `
          + "A model authored against a survey grid can sit kilometres out, which costs depth precision "
          + "in the viewer. Rebasing shifts the geometry <b>and</b> pushes the same offset into the map "
          + "conversion, so the real-world position of every element is unchanged. No element is created "
          + "or destroyed — every GlobalId survives.",
          far > 10_000 ? "bad" : far > 1_000 ? "" : "ok"));
        if (!f.georeference) {
          body.appendChild(resultNote("This file carries no IfcMapConversion, so there is no "
            + "georeference to carry the offset. The geometry still moves; the survey basis was never "
            + "recorded here to begin with.", ""));
        }
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0";
        const lbl = document.createElement("span"); lbl.className = "meta";
        lbl.textContent = "point to move to the origin (current model coords)";
        const mk = (ph: string) => {
          const i = document.createElement("input");
          i.className = "portal-filter"; i.type = "number"; i.step = "any"; i.value = "0";
          i.placeholder = ph; i.style.cssText = "width:110px;font-size:12px";
          return i;
        };
        const xi = mk("E"), yi = mk("N"), zi = mk("Z");
        const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Rebase";
        go.onclick = async () => {
          const pt = [Number(xi.value) || 0, Number(yi.value) || 0, Number(zi.value) || 0];
          if (!pt[0] && !pt[1] && !pt[2]) { notify("that point is already the origin", "info"); return; }
          go.disabled = true; go.textContent = "Rebasing…";
          const res = await authorAndReload("rebase_origin", { point: pt },
                                            `rebase origin to ${pt.join(", ")}`);
          if (!res.applied || res.refused) { go.disabled = false; go.textContent = "Rebase"; return; }
          notify("model rebased — survey position unchanged", "success");
          // A failed re-read must not leave the OLD distance on screen next to a live Rebase button:
          // the model DID move, so acting on those figures again is the double-rebase this comment
          // is about. The form is replaced rather than re-enabled.
          try { render(await api.modelSetup(pid)); }
          catch (e) {
            body.replaceChildren();
            body.appendChild(resultNote("Rebased, but re-measuring the model failed: "
              + `${escapeHtml((e as Error).message)}. Reopen this panel before rebasing again — the `
              + "figures shown were taken before the move.", ""));
          }
        };
        row.append(lbl, xi, yi, zi, go);
        body.appendChild(row);
      };
      render(facts!);
    });
  }));
}
