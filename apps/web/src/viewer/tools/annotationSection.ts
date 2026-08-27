import * as THREE from "three";

import type { ApiClient } from "../../api/client";
import { withLoading } from "../../ui/feedback";
import { askText } from "../../ui/prompt";

/**
 * R39-DECOMP-VIEWER ⑭ — **interactive annotation**, out of `app.ts`.
 *
 * The four tools that place 2D annotation against a picked point: a text note, a two-point
 * dimension, a two-corner revision cloud, and a tag bound to the selected element. Plus the rubber
 * band that shows the first point while you pick the second.
 *
 * ## Why this cluster, and why its state came WITH it
 *
 * `annotGuide` and `guideWired` were `let`s in `app.ts` whose every read and write was already
 * inside this cluster — only the declarations sat outside — so they move here rather than being
 * threaded through the deps object. But they land at MODULE scope, not inside the builder: their
 * position in `app.ts` (just before `buildToolsPanel`, which re-runs on every persona switch) was
 * load-bearing, and the block comment on them below says what breaks if that is missed.
 *
 * `dimFrom` and `cloudFrom` (the pending first point of a dimension / cloud) were already local to
 * the cluster and move unchanged.
 *
 * ## The two accessors, and why they are accessors
 *
 * `lastPoint` and `selectedGuid` are `let` in `app.ts` and change with **every click in the 3D
 * view**. A value copy would compile clean and freeze both at panel-build time — `null` — and all
 * four tools here are gated on one or the other, so they would not fail loudly. They would answer
 * *"click a point in the model first"* forever, which is the failure `qaSection.ts` shipped once
 * and `accessorNotCollapsed.test.ts` now guards by shape.
 *
 * Each handler reads its accessor **once, inside itself** (`const at = d.lastPoint()`), which is
 * the rule `drawingsSection.ts` states: at click time, which is the whole point. That is not the
 * collapse the gate forbids — the collapse is a binding taken OUTSIDE a handler, at panel-build
 * time, which freezes it before the user has clicked anything. Reading it twice in one expression
 * is the other failure: two calls TS cannot narrow, and two values if the user clicks mid-await.
 */
export interface AnnotationDeps {
  /** A full-width tool button. Declared inside `buildToolsPanel`, handed over whole. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  projectId: string | null;
  container: HTMLElement;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** The live viewer — this cluster adds and removes its rubber-band line from the scene. */
  viewer: { world: { scene: { three: THREE.Scene } } };
  /** Screen point -> a point on the working ground plane. Closes over the camera and the plane. */
  screenToGround: (e: MouseEvent) => THREE.Vector3 | null;
  /** Re-reads the pins after an annotation lands, so the new one appears without a reload. */
  reloadModelPins: () => Promise<void>;
  /**
   * Re-publishes and reloads the model after a write.
   *
   * `Promise<boolean>`, not `Promise<void>` — the REAL signature. `tsc` rejected the narrowed
   * version, which is the parity check working: the boolean says whether the reload actually
   * produced a model, and a dep type that dropped it would let a future caller here treat a failed
   * reload as a successful one. Nothing in this module reads it today; the type still carries it.
   */
  loadProjectModel: () => Promise<boolean>;
  waitForPublish: (pid: string, onTick?: (s: string) => void) => Promise<string>;
  /**
   * **An accessor, never a value.** The last point clicked in the 3D view; `let` in `app.ts` and
   * reassigned on every pick. Ten reads below, all through the call.
   */
  lastPoint: () => THREE.Vector3 | null;
  /** **An accessor, never a value** — same reason; the tag tool is selection-gated. */
  selectedGuid: () => string | null;
}

// MODULE scope, not function scope — and the linter is what caught this.
//
// `buildToolsPanel()` re-runs on every `aec:persona` event, and both of these were declared in
// `app.ts` immediately BEFORE it, deliberately outside, so they survive a rebuild. Scoped inside
// `buildAnnotationSection` they reset on every rebuild, and two things break at once:
//
//   * `guideWired` guards installing the `pointermove` tracker EXACTLY ONCE. Reset per rebuild, a
//     persona switch stacks another listener on `container` — each one running `screenToGround`
//     on every mouse move, forever.
//   * the tracker installed by the FIRST call closes over the FIRST `annotGuide`. After a rebuild
//     the new buttons write to a new binding the live listener cannot see, so the rubber band
//     silently stops following the cursor.
//
// Neither is visible to `tsc` and neither breaks a test: 619 viewer tests passed with both bugs in
// place. `no-useless-assignment` flagged `guideWired = true` as dead — dead WITHIN one call, which
// is exactly the symptom of state that was never meant to be per-call.
let annotGuide: { grp: THREE.Group; line: THREE.Line } | null = null;
let guideWired = false;

export function buildAnnotationSection(d: AnnotationDeps) {
    // UX-2 — interactive annotation: place a 2D text note/tag/callout as an IfcAnnotation at the last point
    const annotBtn = d.toolBtn2("🏷 Add note / annotation", async () => {
      // Read once, INSIDE the handler — at click time, which is the point of the accessor.
      // Repeated `d.lastPoint()!` would be three separate calls TS cannot narrow, each able to
      // return a different point if the user clicks mid-await.
      const at = d.lastPoint();
      if (!at) { d.notify("click a point in the model first, then add the note", "error"); return; }
      const text = await askText("Annotation", { label: "Note text:", value: "" });
      if (!text || !text.trim()) return;
      const kind = await askText("Annotation", { label: "Kind: note · tag · callout", value: "note" });
      const k = (["note", "tag", "callout"].includes((kind || "").trim().toLowerCase()) ? kind!.trim().toLowerCase() : "note") as "note" | "tag" | "callout";
      await withLoading(d.container, "placing annotation + republishing", async () => {
        try {
          await d.api.addAnnotation(d.projectId!, [at.x, -at.z], text.trim(), { kind: k, z: at.y }, true);
          const state = await d.waitForPublish(d.projectId!);
          if (state === "done") { await d.loadProjectModel(); d.notify("annotation placed", "success"); }
          else d.notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
          await d.reloadModelPins();
        } catch (e) { d.notify(`annotate failed: ${(e as Error).message}`, "error"); }
      });
    });
    annotBtn.title = "Place a 2D text note / tag / callout as an IfcAnnotation at the last-clicked point — "
      + "round-trips as real IFC and feeds the drawing generator.";

    // UX-2 — live guide line: a dashed rubber line + anchor dot from a pending first point to the
    // cursor while a two-click annotation flow (dimension / revision cloud) waits for its second
    // click — the drafter sees exactly what's being measured before committing.
    const setGuideAnchor = (from: THREE.Vector3 | null) => {
      if (annotGuide) {
        d.viewer.world.scene.three.remove(annotGuide.grp);
        annotGuide.grp.traverse((o) => {
          const m = o as THREE.Mesh;
          if (m.geometry) m.geometry.dispose();
          if (m.material) (m.material as THREE.Material).dispose();
        });
        annotGuide = null;
      }
      if (!from) return;
      const grp = new THREE.Group(); grp.name = "annot-guide";
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 10),
        new THREE.MeshBasicMaterial({ color: 0xffd479, depthTest: false }));
      dot.position.copy(from);
      const geo = new THREE.BufferGeometry().setFromPoints([from.clone(), from.clone()]);
      const line = new THREE.Line(geo, new THREE.LineDashedMaterial({
        color: 0xffd479, dashSize: 0.4, gapSize: 0.25, depthTest: false }));
      line.computeLineDistances();
      grp.add(dot, line);
      d.viewer.world.scene.three.add(grp);
      annotGuide = { grp, line };
    };
    if (!guideWired) {                    // install the cursor tracker exactly once (see PERF-4 note)
      guideWired = true;
      d.container.addEventListener("pointermove", (e) => {
        if (!annotGuide) return;
        const p = d.screenToGround(e);
        if (!p) return;
        const pos = annotGuide.line.geometry.attributes.position as THREE.BufferAttribute;
        pos.setXYZ(1, p.x, p.y, p.z); pos.needsUpdate = true;
        annotGuide.line.computeLineDistances();
      });
    }

    // UX-2 — dimension: two-click flow (pick first point, then second → measured dimension annotation)
    let dimFrom: THREE.Vector3 | null = null;
    const dimBtn = d.toolBtn2("📐 Dimension (2 points)", async () => {
      const at = d.lastPoint();          // read once, at click time
      if (!at) { d.notify("click a point in the model first", "error"); return; }
      if (!dimFrom) { dimFrom = at.clone(); setGuideAnchor(dimFrom); d.notify("first point set — click the second point, then press Dimension again", "info"); return; }
      const a: [number, number] = [dimFrom.x, -dimFrom.z], b: [number, number] = [at.x, -at.z];
      dimFrom = null; setGuideAnchor(null);
      await withLoading(d.container, "placing dimension + republishing", async () => {
        try {
          const r = await d.api.addDimension(d.projectId!, a, b, { z: at.y }, true);
          const state = await d.waitForPublish(d.projectId!);
          if (state === "done") { await d.loadProjectModel(); d.notify(`dimension ${(r as { distance_m?: number }).distance_m ?? ""} m placed`, "success"); }
          else d.notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
          await d.reloadModelPins();
        } catch (e) { d.notify(`dimension failed: ${(e as Error).message}`, "error"); }
      });
    });
    dimBtn.title = "Measure + annotate a dimension between two clicked points — a dimension line + the "
      + "distance label as an IfcAnnotation. Press once to set the first point, again for the second.";

    // UX-2 — revision cloud: two-corner flow (pick one corner, then the opposite → scalloped cloud + rev tag)
    let cloudFrom: THREE.Vector3 | null = null;
    const cloudBtn = d.toolBtn2("☁ Revision cloud (2 corners)", async () => {
      const at = d.lastPoint();          // read once, at click time
      if (!at) { d.notify("click a corner of the region in the model first", "error"); return; }
      if (!cloudFrom) { cloudFrom = at.clone(); setGuideAnchor(cloudFrom); d.notify("first corner set — click the opposite corner, then press Revision cloud again", "info"); return; }
      const a: [number, number] = [cloudFrom.x, -cloudFrom.z], b: [number, number] = [at.x, -at.z];
      cloudFrom = null; setGuideAnchor(null);
      const tag = (prompt("Revision tag (e.g. a delta number) — leave blank for none:", "") || "").trim();
      await withLoading(d.container, "placing revision cloud + republishing", async () => {
        try {
          await d.api.addRevisionCloud(d.projectId!, [a, b], { tag: tag || undefined, z: at.y }, true);
          const state = await d.waitForPublish(d.projectId!);
          if (state === "done") { await d.loadProjectModel(); d.notify("revision cloud placed", "success"); }
          else d.notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
          await d.reloadModelPins();
        } catch (e) { d.notify(`revision cloud failed: ${(e as Error).message}`, "error"); }
      });
    });
    cloudBtn.title = "Draw a revision cloud around a region as an IfcAnnotation (a scalloped outline + an "
      + "optional revision tag). Press once for the first corner, again for the opposite corner. Renders on the plan.";

    // UX-2 — element-aware tag: label auto-read from the SELECTED element (its Name / mark / type)
    const tagBtn = d.toolBtn2("🏷 Tag selected element", async () => {
      const host = d.selectedGuid();
      if (!host) { d.notify("select an element first, then tag it", "error"); return; }
      const override = (prompt("Tag label — leave blank to auto-read the element's name/mark/type:", "") || "").trim();
      await withLoading(d.container, "placing tag + republishing", async () => {
        try {
          const r = await d.api.addTag(d.projectId!, host, override ? { text: override } : {}, true);
          const state = await d.waitForPublish(d.projectId!);
          if (state === "done") { await d.loadProjectModel(); d.notify(`tagged "${(r as { label?: string }).label ?? ""}"`, "success"); }
          else d.notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
          await d.reloadModelPins();
        } catch (e) { d.notify(`tag failed: ${(e as Error).message}`, "error"); }
      });
    });
    tagBtn.title = "Tag the selected element with an IfcAnnotation whose label is auto-read from the element "
      + "(its Name, Pset mark, or type) and assigned to it — so the tag tracks the element. Renders on the plan.";

  return { annotBtn, dimBtn, cloudBtn, tagBtn };
}
