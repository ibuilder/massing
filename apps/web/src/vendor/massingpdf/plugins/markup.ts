/**
 * The markup toolset — the redline vocabulary a drawing reviewer actually uses.
 *
 * Deliberately not "PDF comment types". A revision cloud, a keyed callout and a discipline-coloured
 * strikeout are drawing conventions inherited from the dyeline era; a tool that only offers a
 * sticky note and a highlighter is a document annotator, not a review desk.
 */
import { definePlugin, type ToolDef } from "../core/plugin";
import { DISCIPLINE_COLORS, type AnnotationDraft, type Discipline } from "../core/types";
import type { Viewer } from "../core/viewer";

export interface MarkupOptions {
  /** Discipline applied to new markups; drives the default colour. */
  discipline?: Discipline;
  /** Override the discipline colour. */
  color?: string;
  /** Default stroke width in PDF points. */
  width?: number;
  /** Ask the user for text. Defaults to `window.prompt`; hosts should pass their own modal. */
  promptText?: (title: string, initial?: string) => Promise<string | null>;
}

/** Mutable per-session drawing settings the toolbar can bind to. */
export class MarkupSettings {
  discipline: Discipline;
  color: string | undefined;
  width: number;
  constructor(o: MarkupOptions = {}) {
    this.discipline = o.discipline ?? "general";
    this.color = o.color;
    this.width = o.width ?? 1.8;
  }
  /** The style stamped onto each new markup. */
  style() {
    return { color: this.color ?? DISCIPLINE_COLORS[this.discipline], width: this.width };
  }
}

const defaultPrompt = async (title: string, initial = ""): Promise<string | null> =>
  globalThis.prompt?.(title, initial) ?? null;

export function markupPlugin(options: MarkupOptions = {}) {
  const settings = new MarkupSettings(options);
  const ask = options.promptText ?? defaultPrompt;

  /** Shared decoration for every tool this plugin registers. */
  const decorate = (d: AnnotationDraft): AnnotationDraft => ({
    ...d,
    discipline: settings.discipline,
    style: { ...settings.style(), ...d.style },
  });

  const shape = (
    id: string, label: string, icon: string, kind: ToolDef["kind"],
    input: ToolDef["input"], extra: Partial<ToolDef> = {},
  ): ToolDef => ({
    id, label, icon, kind, input, group: "markup",
    create: ({ points, page }) => decorate({ kind, points, page }),
    ...extra,
  });

  return definePlugin({
    id: "markup",
    order: 10,
    setup(ctx) {
      const t = ctx.registerTool;

      // --- shapes ----------------------------------------------------------
      t(shape("rect", "Rectangle", "▭", "rect", "drag", { shortcut: "r" }));
      t(shape("ellipse", "Ellipse", "◯", "ellipse", "drag", { shortcut: "o" }));
      t(shape("line", "Line", "╱", "line", "drag", { shortcut: "l" }));
      t(shape("arrow", "Arrow", "➔", "arrow", "drag", { shortcut: "a" }));
      t(shape("polyline", "Polyline", "⌇", "polyline", "poly", { minPoints: 2 }));
      t(shape("polygon", "Polygon", "⬠", "polygon", "poly", { minPoints: 3 }));
      t(shape("ink", "Freehand", "✎", "ink", "freehand", { shortcut: "f", sticky: true }));

      // --- the one that makes it read as a drawing --------------------------
      t({
        ...shape("cloud", "Revision cloud", "☁", "cloud", "poly", { minPoints: 3, shortcut: "c" }),
        create: ({ points, page }) => decorate({
          kind: "cloud", points, page,
          subject: "Revision",
          style: { ...settings.style(), width: Math.max(1.2, settings.width * 0.9) },
        }),
      });

      // --- text -------------------------------------------------------------
      t({
        id: "text", label: "Text", icon: "T", kind: "text", input: "click", group: "markup", shortcut: "t",
        async create({ points, page }) {
          const body = await ask("Markup text");
          if (!body?.trim()) return null;
          return decorate({ kind: "text", points, page, text: body.trim(), subject: firstLine(body) });
        },
      });

      t({
        id: "callout", label: "Callout", icon: "⤺", kind: "callout", input: "poly", group: "markup",
        minPoints: 2, maxPoints: 3,
        async create({ points, page }) {
          const body = await ask("Callout text");
          if (!body?.trim()) return null;
          return decorate({ kind: "callout", points, page, text: body.trim(), subject: firstLine(body) });
        },
      });

      // --- text-anchored markups --------------------------------------------
      // These select real glyphs rather than dragging a box, so the markup records *which words*
      // it covers. That is what lets a highlight span three lines without swallowing the margins,
      // and what gives a spec citation something to anchor to.
      t({
        id: "highlight", label: "Highlight", icon: "▤", kind: "highlight", input: "text-select",
        group: "markup", shortcut: "h", sticky: true,
        create: ({ points, page, selection }) => decorate({
          kind: "highlight", points, page,
          note: selection?.text,
          style: { color: "#ffe14d", fill: "#ffe14d", fillOpacity: 0.35, width: 0 },
        }),
      });
      t({
        id: "strikeout", label: "Strikeout", icon: "S̶", kind: "strikeout", input: "text-select",
        group: "markup", sticky: true,
        create: ({ points, page, selection }) => decorate({ kind: "strikeout", points, page, note: selection?.text }),
      });
      t({
        id: "underline", label: "Underline", icon: "U̲", kind: "underline", input: "text-select",
        group: "markup", sticky: true,
        create: ({ points, page, selection }) => decorate({ kind: "underline", points, page, note: selection?.text }),
      });

      // --- settings actions --------------------------------------------------
      ctx.registerAction({
        id: "markup.discipline", label: "Discipline", icon: "◧", group: "markup",
        async run(viewer: Viewer) {
          const list = Object.keys(DISCIPLINE_COLORS) as Discipline[];
          const picked = await ask(`Discipline (${list.join(", ")})`, settings.discipline);
          if (!picked) return;
          const d = picked.trim().toLowerCase() as Discipline;
          if (!list.includes(d)) {
            viewer.bus.emit("notice", { level: "error", message: `Unknown discipline "${picked}"` });
            return;
          }
          settings.discipline = d;
          settings.color = undefined;                 // fall back to the discipline colour
          viewer.bus.emit("notice", { level: "info", message: `Markup discipline: ${d}` });
        },
      });

      /** Restyle the selection — the "make these all structural blue" operation. */
      ctx.registerAction({
        id: "markup.applyStyle", label: "Apply style to selection", icon: "🖌",
        group: "markup",
        enabled: (v) => v.store.selectedIds().length > 0,
        run(viewer) {
          const style = settings.style();
          viewer.store.updateMany(viewer.store.selected().map((a) => ({
            id: a.id,
            patch: { style: { ...a.style, ...style }, discipline: settings.discipline },
          })));
        },
      });

      ctx.viewer.markup = settings;
    },
  });
}

const firstLine = (s: string): string => {
  const line = s.split("\n")[0]!.trim();
  return line.length > 60 ? `${line.slice(0, 57)}…` : line;
};

declare module "../core/viewer" {
  interface Viewer {
    /** Present once the markup plugin is installed. */
    markup?: MarkupSettings;
  }
}
