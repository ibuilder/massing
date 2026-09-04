/** Annotation — *put a note, a dimension, a cloud or a tag ON the model.*
 *
 *  SCALE-SEAM (92). Four methods, one contiguous run out of `client.ts`, all four authoring real
 *  `IfcAnnotation` entities at world `[E,N]` through `editIfc`.
 *
 *  ### The set is BOUNDED by two sources, not by the marker
 *
 *  1. **`services/api/src/aec_api/authoring_matrix.py`** — the curated recipe→category map behind
 *     the public authoring-coverage endpoint, maintained for a different purpose than this
 *     extraction. Its `annotate` category holds **exactly four** of the map's 99 recipes across 15
 *     categories, and they are exactly these: `add_annotation`, `add_dimension`, `add_revision_cloud`,
 *     `add_tag`. A complete category — nothing left behind, nothing pulled in.
 *  2. **`services/api/test_annotation.py`** exercises all four annotation recipes, and no other
 *     recipe as its SUBJECT — it calls `add_wall` and `add_column` once each as fixtures, to give
 *     `add_tag` a host element to label.
 *
 *  *That qualification was missing from the first draft, which said "and no others" — and it is the
 *  SECOND CONSECUTIVE SLICE to make it: (91) claimed no `test_cre_*` file reached outside its set
 *  while `test_cre_tier3` reached three routes as fixtures. Both times the claim counted what a test
 *  TARGETS and ignored what it SETS UP. **A "nothing else" claim about a test must say whether it
 *  means assertions or every call the file makes**, because those are different sets and the smaller
 *  one is the one you notice.*
 *
 *  Both are groupings somebody else authored, which is the kind of source (87) argued to prefer over
 *  a list this extraction wrote for itself.
 *
 *  **The `UX-2` marker on all four does NOT bound the set, and saying so matters.** (91) had a
 *  marker that did — `CRE-` occurred only in `client.ts`, so it drew the boundary itself. `UX-2` is
 *  different: 12 occurrences across three files (here, `viewer/app.ts`, `viewer/tools/annotationSection.ts`).
 *  It marks a FEATURE WORKSTREAM spanning UI and client, so it corroborates *purpose* and is silent
 *  on *membership*. Two markers, two different strengths — worth naming rather than treating every
 *  prefix as a set boundary.
 *
 *  Corroborated a third way: `apps/web/src/viewer/tools/annotationSection.ts` — the UI these serve —
 *  makes exactly four `api.*` calls, and they are these four. One surface, one cluster.
 *
 *  ### Why not `markup.ts`, which is the obvious guess
 *
 *  `markup.ts` is **2D SHEET markup**: a pin at a sheet's `(x, y)` carrying a note, stored as a
 *  markup record, promotable to an RFI (SCALE-SEAM ⑭, route-group `/drawings/markup`). These four
 *  author **model content**: `IfcAnnotation` entities at real-world `[E,N]` coordinates that render
 *  on the generated plan and travel with the IFC. *A comment layer over a drawing and drawing
 *  content authored into the model are different questions that share the word "annotation".*
 *
 *  ### Why not `authoring.ts`, which is where `editIfc` itself lives
 *
 *  This is the harder call, because `authoring.ts` defines `editIfc` and already holds seven
 *  recipes — and its own header claims "the endpoints that WRITE to the model rather than read from
 *  it", which would take all 24 recipes still in `client.ts`.
 *
 *  **A description broad enough to take everything is not a seam.** `authoring.ts`'s demonstrated
 *  practice is much narrower than its sentence: it declined detailing at ⓼, property-override layers
 *  at ㊳ (*"those compose properties, they do not write recipes"*), and groups at ⓻ until a later
 *  slice took them deliberately. It accepts a recipe when the recipe answers a question already
 *  there — families, types, groups, macros, massing. Annotation is none of those.
 *
 *  And `mep.ts`'s header already settled the general principle: its methods *"use `editIfc`
 *  (`/edit`) and stay"*. **A shared helper is a mechanism, not a question** — the same trap as
 *  (85)'s "they are all multipart uploads" and (89)'s "they are all module records". The proof is in
 *  the matrix: those 24 recipes split across NINE categories, so `editIfc` cannot be the seam.
 *
 *  A mixin, so every call site resolves unchanged. All four are named in `api/surface.test.ts` —
 *  which (91) established is necessary rather than optional, because that file's count is a floor
 *  with slack and would not notice four methods going missing.
 */
import type { NeedsEditIfc } from "./types";

type Ctor<T> = new (...args: any[]) => T;

/** The `editIfc` requirement now lives in `./types` as `NeedsEditIfc`, shared with `mep.ts`.
 *
 *  It was declared inline here in (92). (93) needed the identical shape and moved it: two
 *  hand-copied signatures are exactly the drift the #409 review had to check by hand, since a copy
 *  subtly WIDER than the real `editIfc` typechecks at the mixin and still breaks at a call site.
 *  `withAnnotate` must still be composed OUTSIDE `withAuthoring`; composing it inside fails with
 *  `TS2345` naming `editIfc` rather than at runtime.
 *
 *  *(92) also recommended moving `editIfc` down into `HttpCore` to unblock the remaining recipes.
 *  (93) TESTED that forecast and it does not hold — see the note on `NeedsEditIfc` in `./types`.
 *  `httpCore.ts` exists to keep transport separate from the endpoint surface, and `editIfc` is a
 *  domain endpoint. A forecast is a hypothesis for the next slice to test, and this one was mine.* */

export function withAnnotate<TBase extends Ctor<NeedsEditIfc>>(Base: TBase) {
  return class Annotate extends Base {
  /** UX-2: place a 2D text annotation (note / tag / callout) as an IfcAnnotation at an [E,N] point. */
  addAnnotation(pid: string, point: [number, number], text: string,
                opts: { kind?: "note" | "tag" | "callout"; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_annotation", { point, text, ...opts }, publish);
  }
  /** UX-2: place a dimension annotation (line + measured distance) between two [E,N] points. */
  addDimension(pid: string, start: [number, number], end: [number, number],
               opts: { text?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_dimension", { start, end, ...opts }, publish);
  }
  /** UX-2: place a revision cloud (scalloped outline + optional delta/number tag) around a region —
   *  two opposite [E,N] corners, or >=3 boundary points. Renders on the generated plan. */
  addRevisionCloud(pid: string, points: [number, number][],
                   opts: { tag?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_revision_cloud", { points, ...opts }, publish);
  }
  /** UX-2: place an element-aware tag on a host element — the label is auto-read from the host
   *  (its Name / Pset mark / type), or overridden with `text`; assigned to the element it labels. */
  addTag(pid: string, hostGuid: string,
         opts: { text?: string; storey?: string; z?: number } = {}, publish = true) {
    return this.editIfc(pid, "add_tag", { host_guid: hostGuid, ...opts }, publish);
  }
  };
}
