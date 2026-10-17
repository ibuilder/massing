/** VG-DARK — a whole graphics-override engine with no reader, and a client type that reached for a
 *  shape the server has never sent.
 *
 *  ## What the card showed
 *
 *  `view_templates.graphics` resolves, for every visible element, the line weight, colour, pattern
 *  and halftone of the **cut side and the projection side separately**. Its own module calls that
 *  distinction *"the single distinction that separates a drawing from a dump"* — the same element
 *  draws heavy where the view plane cuts it and light where it is merely seen beyond, and a reader
 *  uses that weight difference to read depth off a flat sheet. The Standards card rendered:
 *
 *  > `1 template(s) · graphics for Sheet Lines · 42857 visible`
 *
 *  and nothing else. Not one weight, not one colour, neither side, and **1 of the 3 counts** — so a
 *  template hiding 7,143 of 50,000 elements rendered identically to one hiding none.
 *
 *  ## Two of the three declared members were phantoms
 *
 *  `viewTemplateGraphics` declared `visible_count?`, `cut?` and `projection?` **at the top level**.
 *  Measured against a live route, the top-level keys are `cut_count`, `graphics`, `hidden_count`,
 *  `name`, `note`, `template`, `visible_count`: the cut and projection sides live PER ELEMENT inside
 *  `graphics`. Both members type-checked, resolved to `undefined` on every call ever served, and no
 *  compiler error could reach them — the client-side form of SYSTEM-COLUMN-PHANTOM. The declaration
 *  was inline, so DEADFIELD-INLINE is why nothing noticed: a shape declared in a `this.json<{…}>`
 *  type argument is outside every audit built over interface declarations. *A phantom is worse than
 *  an omission — an omission stops a reader, a phantom gives them `undefined` and a clean build.*
 *
 *  ## `cut_count: 0` had two causes and one rendering
 *
 *  `cut` is an optional GUID list naming what the view plane actually cuts, and the card passed
 *  none, so `cut_count` was 0 on every call this product has ever made. The engine's docstring calls
 *  that *"the honest answer for a 3D view: the cut side is still resolved and reported so a caller
 *  can apply it later, but no element is claimed to be cut"* — and a reader shown `0 cut` cannot
 *  tell that from a view where nothing happens to be cut. `cut_supplied` separates them now.
 *
 *  ## And the response was 8.9 MB
 *
 *  Measured on a 50,000-element index: 42,857 per-element entries, **8.9 MB in a viewer-role GET**,
 *  on every call, consumed by nothing — `graphics()` has exactly one caller, the route, and no
 *  drawing generator reads it. That is the cheap-GET amplification class, and it is why the reading
 *  and the bound had to land together: **wiring a screen to this route without bounding it first
 *  turns a latent payload defect into a live one.** The per-element map is opt-in now and the route
 *  serves `styles` — the distinct resolved states and how many elements carry each, 4 rows over
 *  those 42,857 elements, 1,854 bytes. *A screen wants the distribution, not the rows.*
 */
import type { GraphicOverride, GraphicStyleBucket, ViewTemplateGraphics } from "../../api/model";

export type { Tone } from "./statedBasis";
import type { Tone } from "./statedBasis";

/** The headline, over the population it is about.
 *
 *  `visible_count` alone was the whole card. Hidden is the other half of the same decision: a
 *  template exists to take things OUT of a view, so how much it removed is the number that says
 *  whether it did anything. */
export function graphicsHeadline(g: ViewTemplateGraphics): { text: string; tone: Tone } {
  const total = g.visible_count + g.hidden_count;
  if (total === 0) {
    return { tone: "warn", text: "No model index loaded — nothing for this template to resolve against." };
  }
  if (g.visible_count === 0) {
    return {
      tone: "crit",
      text: `This template hides ALL ${total.toLocaleString()} element(s) — it resolves to an `
        + `empty view.`,
    };
  }
  const pct = Math.round((1000 * g.hidden_count) / total) / 10;
  return {
    tone: g.hidden_count ? "good" : "",
    text: `${g.visible_count.toLocaleString()} visible · ${g.hidden_count.toLocaleString()} hidden `
      + `(${pct}% of ${total.toLocaleString()}) · ${g.style_count} distinct style(s).`,
  };
}

/** Whether the cut side is CLAIMED of anything, and why not when it is not.
 *
 *  Returned for both states rather than suppressed on zero: "no cut list was supplied" is the fact
 *  that makes the 0 readable, and it is the normal state for a 3D view. */
export function cutCoverageNote(g: ViewTemplateGraphics): string {
  if (!g.cut_supplied) {
    return `Cut side resolved for all ${g.visible_count.toLocaleString()} visible element(s) and `
      + `claimed of none — no cut list was supplied, which is the honest answer for a 3D view. Pass `
      + `the elements the view plane cuts to see the heavy side applied.`;
  }
  if (g.cut_count === 0) {
    return "A cut list was supplied and none of its elements are visible under this template — the "
      + "cut side is resolved for every element and applied to none.";
  }
  return `${g.cut_count.toLocaleString()} of ${g.visible_count.toLocaleString()} visible element(s) `
    + `are cut by the view plane and draw with the heavy cut weight.`;
}

function mm(o: GraphicOverride): string {
  return o.weight == null ? "—" : `${o.weight} mm`;
}

/** `weight · colour · pattern · halftone`, for one side. The weight leads because the weight is the
 *  distinction: a reader comparing two rows is comparing the first column. */
export function sideCell(o: GraphicOverride): string {
  const bits = [mm(o), o.color ?? "—", o.pattern ?? "—"];
  if (o.halftone) bits.push("halftone");
  return bits.join(" · ");
}

/** One row per distinct resolved style: how many elements, and what both sides draw at.
 *
 *  Cut and projection are two columns and never one, because collapsing them is exactly the
 *  flattening this engine exists to prevent. */
export function styleRows(g: ViewTemplateGraphics): {
  group: string; count: string; cut: string; projection: string; heavier: string;
}[] {
  return g.styles.map((b) => ({
    group: b.group,
    count: b.count.toLocaleString() + (b.cut_count ? ` (${b.cut_count} cut)` : ""),
    cut: sideCell(b.cut),
    projection: sideCell(b.projection),
    heavier: heavierBy(b),
  }));
}

/** How much heavier the cut side draws, as the ratio a drafter checks.
 *
 *  A style whose two sides are the SAME weight has lost the distinction — which is what an override
 *  applied as a full replacement would do to everything it touched — so it is named rather than
 *  rendered as a quiet `1.0×`. */
export function heavierBy(b: GraphicStyleBucket): string {
  const c = b.cut.weight;
  const p = b.projection.weight;
  if (c == null || p == null) return "—";
  if (p === 0) return "—";
  const r = Math.round((100 * c) / p) / 100;
  return r > 1 ? `${r}×` : r === 1 ? "SAME — no cut/projection distinction" : `${r}× (cut is LIGHTER)`;
}

/** The styles whose cut side is not heavier than their projection side. Empty is the expected
 *  answer: every category default ships cut-heavier, so a row here is an override that flattened
 *  one, and that is a finding rather than a preference. */
export function flattenedStyles(g: ViewTemplateGraphics): GraphicStyleBucket[] {
  return g.styles.filter((b) => {
    const c = b.cut.weight;
    const p = b.projection.weight;
    return c != null && p != null && c <= p;
  });
}

export function flattenedNote(g: ViewTemplateGraphics): string | null {
  const bad = flattenedStyles(g);
  if (!bad.length) return null;
  const n = bad.reduce((a, b) => a + b.count, 0);
  return `${bad.length} style(s) covering ${n.toLocaleString()} element(s) draw the cut side no `
    + `heavier than the projection side (${bad.map((b) => b.group).join(", ")}) — on a sheet those `
    + `elements lose the depth cue entirely.`;
}

/** The engine's own statement of what the resolution IS. Verbatim — the client does not paraphrase
 *  a basis. */
export function graphicsNote(g: ViewTemplateGraphics): string {
  return g.note;
}

/** What shipped versus what exists, and which of the three modes asked for it.
 *
 *  `graphics_count` is the full visible population in every mode, so this never prints the length
 *  of a page as a total. "You did not ask" and "it was cut off" are different sentences. */
export function detailNote(g: ViewTemplateGraphics): string {
  const have = Object.keys(g.graphics).length;
  if (g.graphics_mode === "none") {
    return `Per-element detail not requested — ${g.graphics_count.toLocaleString()} element(s) are `
      + `resolved server-side. Ask about specific GlobalIds, or request the whole map (capped at `
      + `${g.max_graphics.toLocaleString()}).`;
  }
  if (g.graphics_mode === "guids") {
    const miss = g.graphics_unknown.length
      ? ` ${g.graphics_unknown.length} asked-for GlobalId(s) are not visible under this template: `
        + `${g.graphics_unknown.slice(0, 5).join(", ")}.`
      : "";
    return `Showing ${have} named element(s) of ${g.graphics_count.toLocaleString()} resolved.${miss}`;
  }
  return g.graphics_truncated
    ? `Showing ${have.toLocaleString()} of ${g.graphics_count.toLocaleString()} element(s) — the `
      + `server caps the per-element map at ${g.max_graphics.toLocaleString()}. Ask about specific `
      + `GlobalIds to reach the rest.`
    : `Showing all ${have.toLocaleString()} resolved element(s).`;
}

/** Per-element rows, for the GUIDs a reader asked about. `is_cut` is a column because it is the
 *  reason the two weight columns differ for that row. */
export function elementRows(g: ViewTemplateGraphics): {
  guid: string; group: string; cut: string; projection: string; isCut: string;
}[] {
  return Object.entries(g.graphics).map(([guid, st]) => ({
    guid,
    group: st.group,
    cut: sideCell(st.cut),
    projection: sideCell(st.projection),
    isCut: st.is_cut ? "cut" : "seen beyond",
  }));
}

/** The GlobalIds a reader can paste into the inspector without typing one out. Comes from the style
 *  buckets' samples, which is why the engine carries them. */
export function sampleGuids(g: ViewTemplateGraphics, max = 5): string[] {
  const out: string[] = [];
  for (const b of g.styles) {
    for (const s of b.sample) {
      if (out.length >= max) return out;
      if (!out.includes(s)) out.push(s);
    }
  }
  return out;
}
