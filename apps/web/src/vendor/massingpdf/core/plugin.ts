/**
 * The extension contract.
 *
 * The kernel owns rendering, coordinates, selection, the store and the event bus. Everything with a
 * domain opinion — what a revision cloud is, how a takeoff rolls up, what a punch pin means — is a
 * plugin. Plugins never import one another; they meet at the bus and at these registries.
 */
import type { EventBus } from "./events";
import type { AnnotationStore } from "./store";
import type { TextSelection } from "./textLayer";
import type { Annotation, AnnotationDraft, AnnotKind, Pt } from "./types";
import type { Viewer } from "./viewer";

/** How a tool collects its geometry. */
export type ToolInput =
  /** One click → one point. Pins, stamps, counts, text. */
  | "click"
  /** Press, drag, release → two points. Rects, ellipses, lines, arrows, single measurements. */
  | "drag"
  /** Click per vertex, double-click or Enter to finish. Polygons, polylines, clouds, areas. */
  | "poly"
  /** Pointer path sampled while held. Ink. */
  | "freehand"
  /**
   * No geometry of its own — the markup is anchored to selected *text*. The kernel makes the text
   * layer selectable while such a tool is active and hands `create` the resulting quads. Highlight,
   * strikeout, underline, and anything that cites a spec clause.
   */
  | "text-select";

/** What a tool is handed when its gesture completes. */
export interface ToolCommit {
  /** Collected points, page space, in order. */
  points: Pt[];
  page: number;
  viewer: Viewer;
  /** Modifier state at the moment the gesture finished. */
  modifiers: { shift: boolean; alt: boolean; ctrl: boolean; meta: boolean };
  /** The text selection, for `text-select` tools. Absent for every other input mode. */
  selection?: TextSelection;
}

/** A drawing tool. Registering one is how a plugin adds a markup type. */
export interface ToolDef {
  id: string;
  label: string;
  /** Toolbar glyph. Text or emoji — the toolbar is intentionally font-only, no icon sprite. */
  icon?: string;
  /** Toolbar grouping key, e.g. `markup`, `measure`, `review`. */
  group?: string;
  /** Single-key shortcut, matched against `KeyboardEvent.key` when no modifier is held. */
  shortcut?: string;
  input: ToolInput;
  /** The kind the tool produces. Drives the default renderer branch and the default style. */
  kind: AnnotKind;
  /** Minimum points before the gesture may commit. Defaults by `input`. */
  minPoints?: number;
  /** Commit automatically once this many points are collected. */
  maxPoints?: number;
  /** CSS cursor while the tool is active. */
  cursor?: string;
  /**
   * Stay armed after committing, instead of falling back to select. Off by default; turn it on for
   * tools used in runs — counts, stamps, pins, ink.
   */
  sticky?: boolean;
  /** Require a page calibration; the kernel refuses the commit and explains why if absent. */
  needsCalibration?: boolean;
  /**
   * Turn the gesture into a draft. Return `null` to abort (e.g. the user cancelled a text prompt).
   * Omit it and the kernel builds a plain `{ kind, points, page }` draft.
   */
  create?(ctx: ToolCommit): AnnotationDraft | null | Promise<AnnotationDraft | null>;
  /** Called when the tool becomes/stops being active — for cursor chrome or an options popover. */
  activate?(viewer: Viewer): void;
  deactivate?(viewer: Viewer): void;
}

/** A side panel contributed by a plugin. */
export interface PanelDef {
  id: string;
  title: string;
  icon?: string;
  side?: "left" | "right";
  /** Sort key within its side; lower is nearer the top. */
  order?: number;
  /** Build the panel body. Called once; the element is kept and shown/hidden. */
  mount(host: HTMLElement, viewer: Viewer): void | (() => void);
}

/** A toolbar button that runs a command rather than entering a drawing mode. */
export interface ActionDef {
  id: string;
  label: string;
  icon?: string;
  group?: string;
  shortcut?: string;
  /** Grey the button out when this returns false. */
  enabled?(viewer: Viewer): boolean;
  run(viewer: Viewer): void | Promise<void>;
}

/**
 * A custom renderer for a markup kind. Plugins that invent a kind supply one; the built-in kinds
 * are covered by the default renderer. Emit SVG in **page space** — the overlay's viewBox handles
 * zoom, so a `width` of 2 means 2 PDF points on the sheet at every zoom level.
 */
export interface KindRenderer {
  kinds: AnnotKind[];
  render(annot: Annotation, ctx: RenderCtx): SVGElement | SVGElement[] | null;
}

export interface RenderCtx {
  /** Current zoom, for anything that must stay a constant size on screen. */
  zoom: number;
  selected: boolean;
  /** Create an SVG element with attributes. */
  el<K extends keyof SVGElementTagNameMap>(tag: K, attrs?: Record<string, string | number | undefined>): SVGElementTagNameMap[K];
  viewer: Viewer;
}

/** What `setup` receives. */
export interface PluginContext {
  viewer: Viewer;
  bus: EventBus;
  store: AnnotationStore;
  registerTool(tool: ToolDef): void;
  registerAction(action: ActionDef): void;
  registerPanel(panel: PanelDef): void;
  registerRenderer(renderer: KindRenderer): void;
  /** Run on viewer teardown. Prefer this to a `teardown` method for one-off listeners. */
  onCleanup(fn: () => void): void;
}

export interface ViewerPlugin {
  id: string;
  /** Plugins with a lower value set up first. Default 100. */
  order?: number;
  setup(ctx: PluginContext): void | Promise<void>;
  teardown?(): void;
}

/** Sugar for defining a plugin inline without losing type inference. */
export const definePlugin = (p: ViewerPlugin): ViewerPlugin => p;
