import type * as THREE from "three";

import type { ApiClient } from "../../api/client";
import { withLoading } from "../../ui/feedback";
import { askText } from "../../ui/prompt";
import type { LayerManager } from "../../tools/layers";
import { kvTable, resultNote, showResult } from "../../ui/result";

/**
 * R39-DECOMP-VIEWER ⑪ — **MEP, fire protection and life safety**, out of `app.ts`.
 *
 * Six tools: an MEP fitting at the last-clicked point, fire-protection equipment, a fire-alarm
 * device, a telecom device, a vertical riser, and the `IfcDistributionSystem` browser that reports
 * per-system counts plus elements with unconnected ports.
 *
 * ## The capture that makes this slice different
 *
 * ⑨ threaded `selectedGuid`. This one threads **`lastPoint`** — the second mutable capture the
 * decomposition plan names, and the last of the two. It is a `THREE.Vector3 | null` held as `let` in
 * `app.ts` and rewritten on **every click in the 3D view**, which makes it the most volatile state
 * that crosses any of these seams: `selectedGuid` changes when you pick an element, `lastPoint`
 * changes when you click anywhere at all.
 *
 * A value copy would freeze it at panel-build time — `null` — and five of these six tools place
 * geometry *at that point*. They would refuse forever with "click a point in the model first", which
 * is the same silent-inert failure `qaSection.ts` shipped, one capture over. Each handler reads it **once, at click time**, into a local named `pt` -- which is the
 * point-of-use read the accessor rule asks for, not the build-time collapse it forbids. The
 * distinction is the *when*, not the presence of a local: `const pt = d.lastPoint()` inside a
 * click handler is evaluated on every click; the same line at module scope is evaluated once,
 * before anything has been clicked.
 *
 * `THREE` is imported **type-only**: this module reads `.x` and `.z` off the vector and never
 * constructs one, so it carries no runtime dependency on three.js and stays as testable as the rest
 * of `tools/`.
 */
export interface MepDeps {
  /** A full-width tool button. Declared inside `buildToolsPanel`, handed over whole. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  /** The project id, non-null-asserted by the caller inside its project gate. */
  pid: string;
  /** `const` in `app.ts`, so a value is safe. */
  projectId: string | null;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** The canvas host `withLoading` overlays. `const` in `app.ts`. */
  container: HTMLElement;
  /** **Accessor.** Rewritten on every click in the 3D view — the most volatile state on any seam. */
  lastPoint: () => THREE.Vector3 | null;
  /** **Accessor.** `let` in `app.ts`; changes with the selection. */
  selectedGuid: () => string | null;
  /**
   * Layer visibility manager. A live object, like `modeSwitch` -- state read at click time.
   *
   * Typed as the REAL `LayerManager`, not a hand-written `{ rebuild(): void }`. The invented shape
   * compiled until a call site used `isolateGuids`, which it did not declare: guessing a dep's
   * *type* is the same mistake as guessing its *name*, and `tsc` caught both on this slice.
   */
  layerMgr: LayerManager;
  /**
   * Re-fetches and re-tessellates the project model.
   *
   * Returns `Promise<boolean>` -- the real signature, not `Promise<void>`. `tsc` rejected the
   * narrowing, and it was right to: the boolean is whether the reload SUCCEEDED, and a dep
   * type that discards it lets a caller here treat a failed re-tessellation as a good one.
   * Same class of defect as narrowing `authorAndReload` in slice ⑨.
   */
  loadProjectModel: () => Promise<boolean>;
  /** Re-hangs BCF pins after the geometry changes underneath them. */
  reloadModelPins: () => Promise<void>;
  /** Blocks until the server finishes republishing. Built from `api`, so it travels with it. */
  waitForPublish: (jobId: string) => Promise<unknown>;
  /** Runs an edit recipe and republishes. Carries the committer + overlay with it. */
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string,
                    previewId?: string | null, previewGuid?: string)
                   => Promise<{ applied: boolean; refused: boolean }>;
}

/** The six MEP / life-safety buttons, named so re-ordering cannot silently re-map them. */
export interface MepButtons {
  mepFittingBtn: HTMLButtonElement;
  fireBtn: HTMLButtonElement;
  faBtn: HTMLButtonElement;
  commsBtn: HTMLButtonElement;
  riserBtn: HTMLButtonElement;
  /** First-pass sizing calculator — sizes a run BEFORE one is authored, unlike the velocity
   *  check on `mepSysBtn`, which validates runs already in the model. */
  sizeCalcBtn: HTMLButtonElement;
  mepSysBtn: HTMLButtonElement;
}

export function buildMepSection(d: MepDeps): MepButtons {
  // W11 B6: MEP fitting at the last-clicked point + a system browser.
  const mepFittingBtn = d.toolBtn2("🔀 MEP fitting (elbow / tee)", async () => {
    // Read once at click time: an accessor cannot narrow across two calls, and this one
    // changes on every click in the 3D view.
    const pt = d.lastPoint();
    if (!pt) { d.notify("click a point in the model first, then add the fitting", "error"); return; }
    const kind = await askText("MEP fitting", { label: "Type: bend (elbow) · junction (tee) · transition", value: "bend" });
    if (!kind) return;
    const sys = await askText("MEP fitting", { label: "System name", value: "HVAC Supply" });
    const pd = { bend: "BEND", elbow: "BEND", junction: "JUNCTION", tee: "JUNCTION", transition: "TRANSITION" }[kind.trim().toLowerCase()] || "BEND";
    await d.authorAndReload("add_mep_fitting",
      { ifc_class: "IfcDuctFitting", point: [pt.x, -pt.z], predefined: pd, system: sys?.trim() || "HVAC Supply" },
      `MEP ${pd.toLowerCase()}`);
  });
  mepFittingBtn.title = "Author a MEP fitting (elbow/tee/transition, with ports) at the last-clicked point "
    + "and assign it to a distribution system — the LOD 350/400 detailing that joins loose runs. GUID-stable.";

  // MEP-FP: place fire-protection equipment at the last-clicked point (onto the Fire Protection system).
  const fireBtn = d.toolBtn2("🧯 Fire-protection equipment", async () => {
    // Read once at click time: an accessor cannot narrow across two calls, and this one
    // changes on every click in the 3D view.
    const pt = d.lastPoint();
    if (!pt) { d.notify("click a point in the model first, then place the device", "error"); return; }
    const kind = await askText("Fire protection", {
      label: "Device: sprinkler · hose_reel · fdc (fire-dept connection) · hydrant · fire_pump", value: "sprinkler" });
    if (!kind) return;
    const k = kind.trim().toLowerCase().replace(/[ -]/g, "_");
    const known = ["sprinkler", "hose_reel", "fdc", "hydrant", "fire_pump"];
    await d.authorAndReload("add_fire_equipment",
      { kind: known.includes(k) ? k : "sprinkler", point: [pt.x, -pt.z] },
      `fire ${k}`);
  });
  fireBtn.title = "Author a fire-protection device (sprinkler head, hose reel, fire-department/siamese "
    + "connection, hydrant, or fire pump) as the right IFC class on the Fire Protection distribution system.";

  // DISC-4a: fire-alarm / life-safety device (distinct from fire protection) at the last-clicked point.
  const faBtn = d.toolBtn2("🔔 Fire-alarm device", async () => {
    // Read once at click time: an accessor cannot narrow across two calls, and this one
    // changes on every click in the 3D view.
    const pt = d.lastPoint();
    if (!pt) { d.notify("click a point in the model first, then place the device", "error"); return; }
    const kind = await askText("Fire alarm / life safety", {
      label: "Device: smoke_detector · heat_detector · pull_station · horn_strobe · strobe · bell · facp",
      value: "smoke_detector" });
    if (!kind) return;
    const k = kind.trim().toLowerCase().replace(/[ -]/g, "_");
    const known = ["smoke_detector", "heat_detector", "duct_detector", "pull_station", "horn_strobe", "strobe", "bell", "facp"];
    await d.authorAndReload("add_fa_device",
      { kind: known.includes(k) ? k : "smoke_detector", point: [pt.x, -pt.z] },
      `fire-alarm ${k}`);
  });
  faBtn.title = "Author a fire-alarm / life-safety device (smoke/heat detector, manual pull station, "
    + "horn-strobe, bell, or FACP) on the Fire Alarm system — its own discipline, apart from fire protection.";

  // DISC-4a: telecom / low-voltage device at the last-clicked point.
  const commsBtn = d.toolBtn2("📶 Telecom device", async () => {
    // Read once at click time: an accessor cannot narrow across two calls, and this one
    // changes on every click in the 3D view.
    const pt = d.lastPoint();
    if (!pt) { d.notify("click a point in the model first, then place the device", "error"); return; }
    const kind = await askText("Telecom / low-voltage", {
      label: "Device: idf · mdf · rack · switch · wap (wireless AP) · data_outlet", value: "idf" });
    if (!kind) return;
    const k = kind.trim().toLowerCase().replace(/[ -]/g, "_");
    const known = ["mdf", "idf", "rack", "switch", "wap", "data_outlet"];
    await d.authorAndReload("add_comms_device",
      { kind: known.includes(k) ? k : "idf", point: [pt.x, -pt.z] },
      `telecom ${k}`);
  });
  commsBtn.title = "Author a telecom / low-voltage device (MDF/IDF rack, network switch, wireless access "
    + "point, or data outlet) on the Telecommunications system (discipline T).";

  // MEP-FP / MEP: a vertical riser (standpipe / stack / vent) at the last-clicked point.
  const riserBtn = d.toolBtn2("⭱ Vertical riser (standpipe / stack)", async () => {
    // Read once at click time: an accessor cannot narrow across two calls, and this one
    // changes on every click in the 3D view.
    const pt = d.lastPoint();
    if (!pt) { d.notify("click a point in the model first, then add the riser", "error"); return; }
    const range = await askText("Vertical riser", { label: "Bottom, top elevation (m) — [E,N] is the last click", value: "0, 9" });
    if (!range) return;
    const parts = range.split(",").map((x) => parseFloat(x.trim()));
    const b = parts[0] ?? NaN, t = parts[1] ?? NaN;
    if (!isFinite(b) || !isFinite(t) || t <= b) { d.notify("enter bottom, top with top above bottom", "error"); return; }
    await d.authorAndReload("add_riser",
      { point: [pt.x, -pt.z], bottom_z: b, top_z: t, size: 0.1, system: "Fire Protection", discipline: "fire" },
      "riser");
  });
  riserBtn.title = "Author a vertical MEP riser (fire standpipe / plumbing stack / vent) from a bottom to "
    + "top elevation at the last-clicked point — the vertical complement to horizontal MEP runs.";
  // R27 / R37 — the first-pass sizing CALCULATOR. Distinct from "MEP size check" below, and the
  // distinction is which question is being asked: the check validates runs already authored in the
  // model, this sizes one before anything exists. `/projects/{pid}/mep/size` has been complete since
  // v0.3.1116 and had no caller in this app at all, which is what made `block_cooling`
  // product-unreachable — a built capability nobody could reach is indistinguishable from a missing one.
  const sizeCalcBtn = d.toolBtn2("🧮 First-pass MEP sizing", async () => {
    // The route's dispatcher falls through to `size_duct` for any kind it does not recognise, so a
    // typo would return duct dimensions labelled as whatever was typed — a confident wrong answer,
    // not an error. Refusing here is the honest outcome, and it also keeps free text out of the
    // result title. (`showResult` no longer renders its title as markup either; both halves, because
    // one guard on a shared sink and one on this caller protect different things.)
    const KINDS = ["duct", "pipe", "cooling", "block_cooling", "hanger"] as const;
    const kind = (await askText("First-pass MEP sizing", {
      label: `${KINDS.join(" · ")} — duct is CFM @ fpm, pipe GPM @ fps, cooling BTU/h → tons, `
        + "block_cooling area → tons, hanger size in inches",
      value: "block_cooling",
    }))?.trim();
    if (!kind) return;
    if (!(KINDS as readonly string[]).includes(kind)) {
      d.notify(`unknown sizing kind ${kind} — expected one of ${KINDS.join(", ")}`, "error");
      return;
    }
    const num = async (label: string, dflt = "") => {
      const v = await askText("First-pass MEP sizing", { label, value: dflt });
      return v === null ? null : Number(v);
    };
    const o: { flow?: number; velocity?: number; load?: number; size?: number;
               hangerKind?: string; gfaSf?: number; sfPerTon?: number } = {};
    if (kind === "duct" || kind === "pipe") {
      const f = await num(kind === "duct" ? "Airflow (CFM)" : "Flow (GPM)");
      const v = await num(kind === "duct" ? "Velocity (fpm)" : "Velocity (ft/s)");
      if (f === null || v === null) return;
      o.flow = f; o.velocity = v;
    } else if (kind === "cooling") {
      const l = await num("Cooling load (BTU/h)");
      if (l === null) return;
      o.load = l;
    } else if (kind === "block_cooling") {
      // Both optional on purpose: leave the area blank and the server derives it from the loaded
      // model, which is the whole point of asking this question early.
      const a = await num("Gross floor area (sf) — blank to derive from the model", "");
      const r = await num("sf per ton", "350");
      if (a !== null && Number.isFinite(a) && a > 0) o.gfaSf = a;
      if (r !== null && Number.isFinite(r) && r > 0) o.sfPerTon = r;
    } else if (kind === "hanger") {
      const hk = await askText("First-pass MEP sizing", {
        label: "Hanger kind: duct | pipe_steel | pipe_copper", value: "pipe_steel" });
      const sz = await num("Nominal size (in)");
      if (!hk || sz === null) return;
      o.hangerKind = hk.trim(); o.size = sz;
    }
    let out: Record<string, unknown>;
    try { out = await d.api.mepSize(d.pid, kind as (typeof KINDS)[number], o); }
    catch (e) { d.notify((e as Error).message, "error"); return; }
    showResult(`First-pass sizing — ${kind}`, (body) => {
      body.appendChild(kvTable(Object.entries(out).map(([k, v]) => ({
        k: k.replace(/_/g, " "),
        v: typeof v === "number" ? String(Math.round(v * 1000) / 1000) : String(v),
      }))));
      body.appendChild(resultNote("First-pass sizing only — not a stamped design. Confirm against the "
        + "authored model with the velocity size check.", ""));
    });
  });
  sizeCalcBtn.title = "Size a duct, pipe, cooling load, block cooling load or hanger before anything "
    + "is authored — the question asked at concept, when no run exists to check.";

  let mepConnectFrom: string | null = null;   // W10-4: first element of a port-to-port connect
  const mepSysBtn = d.toolBtn2("🔀 MEP systems", async () => {
    let s, c;
    try { [s, c] = await Promise.all([d.api.mepSummary(d.pid), d.api.mepConnectivity(d.pid)]); }
    catch (e) { d.notify(`MEP failed: ${(e as Error).message}`, "error"); return; }
    showResult("MEP systems & connectivity", (body) => {
      // W10-4 connectivity validation
      body.appendChild(resultNote(`<b>Connectivity</b> — ${c!.connections} port-to-port link(s) · `
        + `${c!.ports_connected}/${c!.ports_total} ports connected (${c!.connected_pct}%) · `
        + `<b>${c!.dangling_count}</b> floating element(s).`, c!.dangling_count ? "" : "ok"));
      // two-step connect: pick one element, then connect it to another
      const cw = document.createElement("div"); cw.style.cssText = "display:flex;gap:6px;margin:4px 0;flex-wrap:wrap";
      const pick = d.toolBtn2(mepConnectFrom ? "① picked — select the 2nd element" : "🔗 Connect: pick first element", () => {
        const g = d.selectedGuid();
        if (!g) { d.notify("select an MEP element first", "error"); return; }
        mepConnectFrom = g; d.notify("first element picked — select the second, then Connect", "info");
      });
      const doConn = d.toolBtn2("🔗 Connect to second element", async () => {
        if (!mepConnectFrom) { d.notify("pick the first element first", "error"); return; }
        // One read, before the guard, so the narrowing survives into `connectMep`.
        const b = d.selectedGuid();
        if (!b || b === mepConnectFrom) { d.notify("select a different second element", "error"); return; }
        const a = mepConnectFrom;
        await withLoading(d.container, "connecting MEP ports + republishing", async () => {
          try {
            await d.api.connectMep(d.pid, a, b, true);
            const state = await d.waitForPublish(d.projectId!);
            if (state === "done") { await d.loadProjectModel(); d.notify("connected port-to-port", "success"); }
            else d.notify(`connected — publish ${state}`, state === "error" ? "error" : "info");
            mepConnectFrom = null; await d.reloadModelPins();
          } catch (e) { d.notify(`connect failed: ${(e as Error).message}`, "error"); }
        });
      });
      cw.append(pick, doConn); body.appendChild(cw);
      if (c!.dangling.length) {
        const iso = d.toolBtn2("◎ Isolate floating elements in 3D", () => { void d.layerMgr.isolateGuids(c!.dangling.map((d) => d.guid)); });
        body.appendChild(iso);
      }
      if (!s.systems.length) { body.appendChild(resultNote("No distribution systems yet — add duct/pipe runs + fittings.", "")); return; }
      // MEP-FP: by-discipline rollup (fire protection is a first-class discipline beside HVAC/plumbing/electrical)
      const discIcon: Record<string, string> = { hvac: "💨", plumbing: "🚰", electrical: "⚡", fire: "🧯", comms: "📶", other: "🔀" };
      if (s.by_discipline && Object.keys(s.by_discipline).length) {
        const roll = Object.entries(s.by_discipline)
          .map(([d, v]) => `${discIcon[d] || "🔀"} ${d} (${v.systems})`).join(" · ");
        body.appendChild(resultNote(`<b>Disciplines</b> — ${roll}.`
          + (s.has_fire_protection ? "" : " <i>No fire-protection system yet.</i>"), s.has_fire_protection ? "ok" : ""));
        const sizeBtn = d.toolBtn2("📐 MEP size check (velocity)", async () => {
          let mz;
          try { mz = await d.api.mepSizing(d.pid); }
          catch (e) { d.notify((e as Error).message, "error"); return; }
          if (!mz.checked) { body.appendChild(resultNote("No sized MEP runs to check — author ducts/pipes with a design size + flow first.", "")); return; }
          body.appendChild(resultNote(`<b>MEP size check</b> — ${mz.passed} pass · <b>${mz.failed} fail</b> · ${mz.info} info`
            + ` of ${mz.checked} run(s). Limits: air ≤ ${mz.limits.duct_max_fpm} fpm · water ≤ ${mz.limits.pipe_max_fps} ft/s.`,
            mz.failed ? "bad" : "ok"));
          const icon = (st: string) => st === "pass" ? "✅" : st === "fail" ? "❌" : "ℹ️";
          body.appendChild(kvTable(mz.checks.slice(0, 20).map((c) => ({
            k: `${icon(c.status)} ${c.class.replace("Ifc", "")}${c.system ? ` · ${c.system}` : ""}`,
            v: `${c.size_mm}mm ${c.flow != null ? `@ ${c.flow} ${c.flow_unit ?? ""}` : ""} — ${c.note}`,
          }))));
          const bad = mz.checks.filter((c) => c.status === "fail").map((c) => c.guid);
          if (bad.length) body.appendChild(d.toolBtn2("◎ Isolate undersized runs in 3D", () => { void d.layerMgr.isolateGuids(bad); }));
          body.appendChild(resultNote(mz.disclaimer, ""));
        });
        sizeBtn.title = "Velocity/fill size check over authored MEP (ASHRAE air, erosion-limit water) — preliminary, not a stamped design";
        body.appendChild(sizeBtn);
        if (s.has_fire_protection) {
          const covBtn = d.toolBtn2("🧯 Sprinkler coverage (NFPA 13)", async () => {
            let cov;
            try { cov = await d.api.sprinklerCoverage(d.pid, "light"); }
            catch (e) { d.notify((e as Error).message, "error"); return; }
            const ok = cov.adequate;
            body.appendChild(resultNote(`<b>Sprinkler coverage</b> (${cov.hazard} hazard) — `
              + `${cov.sprinkler_heads} head(s) vs <b>${cov.required_heads}</b> required for `
              + `${cov.protected_area_m2.toLocaleString()} m² (≤${cov.max_coverage_m2_per_head} m²/head): `
              + `<b>${ok == null ? "n/a" : ok ? "adequate" : `short ${cov.shortfall}`}</b>. `
              + `<span class="meta">${cov.citation}. ${cov.verify}</span>`,
              ok == null ? "" : ok ? "ok" : "bad"));
          });
          covBtn.title = "NFPA-13-informed head-count vs protected-area coverage pre-check (not a hydraulic design)";
          body.appendChild(covBtn);
        }
      }
      for (const sy of s.systems) {
        const di = discIcon[sy.discipline || "other"] || "🔀";
        body.appendChild(kvTable([
          { k: `${di} ${sy.name}`, v: `${sy.members} elements${sy.discipline ? ` · ${sy.discipline}` : ""}`, strong: true },
          { k: "  segments · fittings · terminals", v: `${sy.segments} · ${sy.fittings} · ${sy.terminals}` },
          { k: "  elements with open ports", v: String(sy.elements_with_open_ports) },
        ]));
      }
      if (s.unassigned.segments || s.unassigned.fittings) {
        body.appendChild(resultNote(`⚠ Unassigned to any system: <b>${s.unassigned.segments}</b> segment(s), `
          + `<b>${s.unassigned.fittings}</b> fitting(s).`, "bad"));
      }
    });
  });
  mepSysBtn.title = "Browse IfcDistributionSystems — per-system segment/fitting/terminal counts, a "
    + "connectivity signal (elements with unconnected ports), and anything not yet assigned to a system.";
  return { mepFittingBtn, fireBtn, faBtn, commsBtn, riserBtn, mepSysBtn, sizeCalcBtn };
}
