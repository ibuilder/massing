/**
 * R26-TOOLBAR — 25 unlabeled glyphs, all of them, always → a handful of **labeled** verbs plus More.
 *
 * The audit's most concrete finding, and the easiest one to get wrong. Two wrong fixes were available:
 * delete tools nobody could identify (they are used, they were just unlabelled), or add labels to all
 * 25 (a wider wall of options is still a wall). What actually helps is **fewer things visible at
 * once, each of them readable, and nothing removed** — the rest one click away under More.
 *
 * Three decisions carry the design:
 *
 * * **Context, not preference.** The primary set depends on what you have selected, because the
 *   answer to "what can I do right now" genuinely changes. Move/Copy/Delete are meaningless with
 *   nothing selected, and burying Measure behind More while they sit in the open is the current
 *   toolbar's actual problem in miniature.
 * * **A glyph without a word is a puzzle.** `⧉`, `✥`, `◧`, `◨`, `⬚`, `⊞` are not guessable, and the
 *   tooltip only helps someone who already suspects what the button does. Primary buttons show a
 *   short verb; More lists label *and* description, so the long tail is scannable as text.
 * * **Nothing is dropped, and nothing is silently misfiled.** Every button the viewer installs must
 *   appear in the table below. One that does not is put in More *and reported* (`data-unlaid`),
 *   because a tool that quietly vanishes from a toolbar is indistinguishable from one that was
 *   deliberately removed.
 */

/** What the user has to work with right now. */
export interface ToolContext {
  /** An element is selected — the transform/edit verbs become meaningful. */
  selection: boolean;
  /** The caller may author on this project (the `edit` capability). */
  canEdit: boolean;
}

export type ToolGroup = "look" | "measure" | "author" | "collaborate" | "analyse";

export interface ToolSpec {
  /** The button's `title`, verbatim — the key, so a retitled button fails the gate rather than drifts. */
  title: string;
  /** The word shown beside the glyph when this tool is primary. Short: it sits in a floating bar. */
  label: string;
  group: ToolGroup;
  /**
   * `"always"` pins the tool to the bar; a predicate promotes it only in that context; absent means
   * it lives in More.
   *
   * The distinction is load-bearing, and the first version of this table got it wrong. Treating
   * always-on tools as merely "a predicate that returns true" let contextual verbs push them past
   * the cap — so **Ask** silently moved into More the moment you selected something. A verb that
   * relocates in response to unrelated state is worse than one that was never on the bar: you learn
   * where it is, and then it is not there.
   */
  primary?: "always" | ((ctx: ToolContext) => boolean);
}

const onSelection = (c: ToolContext) => c.selection;
const onEditableSelection = (c: ToolContext) => c.selection && c.canEdit;

/**
 * Every button `installTools` creates, in the order the toolbar should read.
 *
 * Ordering is deliberate: look → measure → author → the rest. It is the order of the questions people
 * actually ask of a model — *what am I looking at*, then *how big is it*, then *change it*.
 */
export const TOOLS: ToolSpec[] = [
  // ── look ───────────────────────────────────────────────────────────────────────────────────────
  { title: "Toggle storey levels overlay", label: "Levels", group: "look", primary: "always" },
  { title: "Show all (H)", label: "Show all", group: "look", primary: onSelection },
  { title: "Isolate selection", label: "Isolate", group: "look", primary: onSelection },
  { title: "Color selection", label: "Colour", group: "look" },
  { title: "Section plane (S) — dbl-click a face", label: "Section", group: "look", primary: "always" },
  { title: "Section box (clip to model bounds)", label: "Section box", group: "look" },
  { title: "Render mode — sun, soft shadows, PBR lighting, SSAO & bloom", label: "Render", group: "look" },
  { title: "Sun & shadow study (date · time · location)", label: "Sun", group: "look" },
  // Labelling the toolbar surfaced a real duplicate: TWO first-person walk tools, both 🚶, both
  // installed, sitting next to each other. `envTools` drives the camera per frame and you drag to
  // look; the later R17 `walkMode` takes a pointer lock and exits on Esc. They are not the same
  // control, but as two identical glyphs they read as a rendering bug. Distinct labels make the
  // duplication legible; deciding which one is canonical is a behaviour change, not a layout one,
  // so it is recorded in the roadmap rather than settled here by whichever I happened to keep.
  { title: "Walk through (first-person — W/A/S/D, drag to look)", label: "Walk (drag)", group: "look" },
  { title: "Walk mode — first-person WASD walkthrough (Esc exits)", label: "Walk (locked)", group: "look" },
  // ── measure ────────────────────────────────────────────────────────────────────────────────────
  { title: "Measure distance (M)", label: "Measure", group: "measure", primary: "always" },
  { title: "Measure area (A)", label: "Area", group: "measure" },
  { title: "Clear measurements", label: "Clear", group: "measure" },
  // ── author ─────────────────────────────────────────────────────────────────────────────────────
  { title: "Edit in place — drag the gizmo to move the selected element", label: "Edit in place",
    group: "author", primary: onEditableSelection },
  // R38-PUSHPULL — shipped v0.3.821 and NOT registered here, so the bar logged
  // "not described by toolbarLayout" on every load. R26-TOOLBAR's gate is about nothing
  // disappearing; an unregistered tool is exactly that failure arriving from the other side.
  // NOT primary: the bar has a hard cap, and promoting this pushed "Move" into More — the exact
  // silent-demotion the pinned-positions test below exists to catch. It caught it. Push/pull stays
  // in More and on the rail, where it was already reachable.
  { title: "Push/pull — drag the top handle to make the selected element taller or thicker",
    label: "Push/pull", group: "author" },
  { title: "Plan beside model", label: "Plan pane", group: "look" },
  { title: "Move selected element (E,N,Z metres)", label: "Move", group: "author", primary: onEditableSelection },
  { title: "Copy selected element (offset E,N,Z metres)", label: "Copy", group: "author", primary: onEditableSelection },
  // A29-GUIDE-UNDERLAY. In `author` rather than `look` because it is not a way of viewing the model —
  // it is a reference you draw ON TOP OF, so it belongs beside the verbs that draw.
  { title: "Guide underlay — pin a scanned plan to this level and trace over it",
    label: "Guide underlay", group: "author" },
  { title: "Rotate selected element (degrees about Z)", label: "Rotate", group: "author" },
  { title: "Delete selected element", label: "Delete", group: "author" },
  { title: "Edit a property on the selected element", label: "Property", group: "author" },
  { title: "Add door to selected wall", label: "Add door", group: "author" },
  { title: "Add window to selected wall", label: "Add window", group: "author" },
  { title: "Script this — see the GUID-safe recipe plan behind a plain-English command, then apply",
    label: "Script", group: "author" },
  // ── analyse ────────────────────────────────────────────────────────────────────────────────────
  { title: "Ask the model — plain-English questions about the data", label: "Ask", group: "analyse",
    primary: "always" },
  // ── collaborate ────────────────────────────────────────────────────────────────────────────────
  { title: "Live presence", label: "Presence", group: "collaborate" },
  { title: "Share your current view with everyone", label: "Share view", group: "collaborate" },
  { title: "Share via QR — open this project on a phone or tablet", label: "QR", group: "collaborate" },
  { title: "Capture hero image — this view becomes page 2 of the client project package (PDF)",
    label: "Capture", group: "collaborate" },
];

const BY_TITLE = new Map(TOOLS.map((t) => [t.title, t]));

export function specFor(title: string): ToolSpec | null {
  return BY_TITLE.get(title) ?? null;
}

/** Capped, because "contextual" that still yields fifteen buttons has solved nothing. */
export const MAX_PRIMARY = 8;

/**
 * The titles visible as labeled buttons: the pinned verbs first, then whatever this context promotes.
 *
 * The two-phase order is the whole point. Pinned verbs hold **fixed positions** — you learn where
 * Measure is once — and contextual verbs append after them, so gaining a selection never reshuffles
 * what was already on the bar. The cap therefore only ever trims the contextual tail.
 *
 * `available` restricts to the tools this toolbar actually installed, **before** the cap. Capping
 * against the full table and intersecting afterwards would leave a stripped-down build with fewer
 * primary buttons than it has room for — the cap would be spending slots on tools that do not exist.
 */
export function primaryTitles(ctx: ToolContext, available?: string[]): string[] {
  const pool = available ? TOOLS.filter((t) => available.includes(t.title)) : TOOLS;
  const pinned = pool.filter((t) => t.primary === "always");
  const contextual = pool.filter((t) => typeof t.primary === "function" && t.primary(ctx));
  return [...pinned, ...contextual].map((t) => t.title).slice(0, MAX_PRIMARY);
}

/** Titles the viewer registered that this table does not describe. Must be empty; surfaced, not hidden. */
export function unlaidTitles(registered: string[]): string[] {
  return registered.filter((t) => !BY_TITLE.has(t));
}

/** Human group headings for the More menu, in reading order. */
export const GROUP_LABELS: [ToolGroup, string][] = [
  ["look", "View"], ["measure", "Measure"], ["author", "Modify"],
  ["analyse", "Analyse"], ["collaborate", "Share"],
];

/** The description shown beside a label in More — the part of the title after the em dash, if any. */
export function describe(spec: ToolSpec): string {
  const i = spec.title.indexOf(" — ");
  return i > 0 ? spec.title.slice(i + 3) : "";
}

/**
 * R26-ICONS — the icon each labelled verb wears, keyed by label.
 *
 * Keyed by LABEL rather than by title, because the label is the word already chosen for the button
 * and the two must agree: an icon that disagrees with the word beside it is worse than no icon,
 * since the reader now has two claims and no way to choose. `toolbarLayout.test` asserts every
 * label here resolves to a vendored icon and that no label is missed, so a new verb cannot ship
 * wearing a blank.
 */
export const TOOL_ICON: Record<string, string> = {
  "Guide underlay": "scan",     // A29-GUIDE-UNDERLAY — a scanned plan, traced over
  "Levels": "layers",
  "Show all": "eye",
  "Isolate": "focus",
  "Colour": "palette",
  "Section": "scissors",
  "Section box": "box",
  "Render": "sparkles",
  "Sun": "sun",
  // Two walk tools, deliberately the same icon: they ARE the same verb, and v0.3.691 established
  // that the DUPLICATION is the finding. Giving them different icons would disguise it.
  "Walk (drag)": "footprints",
  "Walk (locked)": "footprints",
  "Measure": "ruler",
  "Area": "scan",
  "Clear": "eraser",
  "Edit in place": "pencil",
  "Push/pull": "box",
  "Plan pane": "layers",
  "Move": "move-3d",
  "Copy": "copy",
  "Rotate": "rotate-cw",
  "Delete": "trash-2",
  "Property": "info",
  "Add door": "door-open",
  "Add window": "panel-top",
  "Script": "code",
  "Ask": "message-circle-question-mark",
  "Presence": "users",
  "Share view": "share-2",
  "QR": "qr-code",
  "Capture": "camera",
};

/** The icon for a tool, or null when it has none — the caller falls back to its label. */
export function iconFor(label: string): string | null {
  return Object.prototype.hasOwnProperty.call(TOOL_ICON, label) ? TOOL_ICON[label]! : null;
}
