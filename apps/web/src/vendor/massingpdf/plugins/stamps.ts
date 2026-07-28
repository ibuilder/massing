/**
 * Stamps and tool chests.
 *
 * Two ideas from Bluebeam that matter more than they look. A *dynamic* stamp resolves
 * `{{user}}`/`{{date}}` at placement, so the record says who approved what and when rather than
 * "APPROVED" floating with no provenance. A *tool chest* is a saved, shareable set of pre-styled
 * markups — the mechanism by which a firm's redline standard becomes something people actually
 * follow instead of a PDF in a folder.
 */
import { definePlugin } from "../core/plugin";
import type { AnnotationDraft, AnnotStyle, Discipline } from "../core/types";
import type { Viewer } from "../core/viewer";

/** A stamp template. `text` may contain `{{field}}` placeholders. */
export interface StampTemplate {
  id: string;
  name: string;
  text: string;
  category?: "review" | "inspection" | "status" | "seal" | "custom";
  style?: AnnotStyle;
  /** Fan out one stamp per disposition, e.g. `["Approved", "Approved as Noted", "Revise & Resubmit"]`. */
  dispositions?: string[];
}

/** One entry in a tool chest: a kind plus the styling and classification to apply. */
export interface ChestTool {
  id: string;
  label: string;
  kind: AnnotationDraft["kind"];
  style?: AnnotStyle;
  discipline?: Discipline;
  subject?: string;
  labels?: string[];
  text?: string;
}

export interface ToolChest {
  id: string;
  name: string;
  /** Firm / project the chest belongs to, for the picker. */
  owner?: string;
  tools: ChestTool[];
}

/** The EJCDC/CSI-flavoured defaults. A project library replaces or extends these. */
export const DEFAULT_STAMPS: StampTemplate[] = [
  { id: "approved", name: "Approved", text: "APPROVED — {{user}} · {{date}}", category: "review", style: { color: "#2f9e5f" } },
  { id: "approved-as-noted", name: "Approved as Noted", text: "APPROVED AS NOTED — {{user}} · {{date}}", category: "review", style: { color: "#2f9e5f" } },
  { id: "revise", name: "Revise & Resubmit", text: "REVISE & RESUBMIT — {{user}} · {{date}}", category: "review", style: { color: "#e2554a" } },
  { id: "rejected", name: "Rejected", text: "REJECTED — {{user}} · {{date}}", category: "review", style: { color: "#8a1f1f" } },
  { id: "reviewed", name: "Reviewed", text: "REVIEWED — {{user}} · {{date}}", category: "review" },
  { id: "for-construction", name: "For Construction", text: "ISSUED FOR CONSTRUCTION — {{date}}", category: "status", style: { color: "#2f6fd0" } },
  { id: "not-for-construction", name: "Not For Construction", text: "NOT FOR CONSTRUCTION", category: "status", style: { color: "#e2554a" } },
  { id: "for-record", name: "As-Built / Record", text: "AS-BUILT — {{date}}", category: "status" },
  { id: "void", name: "Void", text: "VOID — {{date}}", category: "status", style: { color: "#5c6670" } },
  { id: "site-verified", name: "Site Verified", text: "SITE VERIFIED — {{user}} · {{date}}", category: "inspection", style: { color: "#2f9e5f" } },
  { id: "field-observed", name: "Field Observation", text: "FIELD OBSERVATION {{date}} {{time}}", category: "inspection" },
  { id: "coordination", name: "For Coordination", text: "FOR COORDINATION — {{user}}", category: "review", style: { color: "#a24bd0" } },
];

/** The starter chest — a general redline set that works before anyone configures anything. */
export const DEFAULT_CHEST: ToolChest = {
  id: "default", name: "General redline",
  tools: [
    { id: "issue", label: "Issue cloud", kind: "cloud", subject: "Issue", style: { color: "#e2554a", width: 1.6 } },
    { id: "coord", label: "Coordination cloud", kind: "cloud", subject: "Coordination", style: { color: "#a24bd0", width: 1.6 } },
    { id: "dim-check", label: "Dimension check", kind: "distance", subject: "Verify dimension", style: { color: "#ffb02e" } },
    { id: "keynote", label: "Keynote", kind: "callout", subject: "Keynote", style: { color: "#2f6fd0" } },
    { id: "struct", label: "Structural note", kind: "text", discipline: "structural", subject: "Structural" },
    { id: "mep", label: "MEP conflict", kind: "cloud", discipline: "mechanical", subject: "MEP conflict", labels: ["clash"] },
  ],
};

export interface StampOptions {
  /** Project stamp library. Sync or async; the picker refreshes when a promise resolves. */
  templates?: StampTemplate[] | (() => Promise<StampTemplate[]>);
  chests?: ToolChest[] | (() => Promise<ToolChest[]>);
  /** Resolve extra `{{placeholders}}` — project number, contract, submittal ref. */
  fields?: () => Record<string, string>;
  promptText?: (title: string, initial?: string) => Promise<string | null>;
}

/** Substitute `{{field}}` placeholders. Unknown fields resolve to an em dash, never to raw braces. */
export function resolveTemplate(text: string, fields: Record<string, string>): string {
  return text.replace(/\{\{(\w+)\}\}/g, (_, k: string) => fields[k] ?? "—");
}

/** The standard field set available to every stamp. */
export function standardFields(viewer: Viewer, extra: Record<string, string> = {}): Record<string, string> {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    user: viewer.author,
    org: (viewer as { org?: string }).org ?? "",
    date: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
    time: `${pad(now.getHours())}:${pad(now.getMinutes())}`,
    datetime: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`,
    year: String(now.getFullYear()),
    file: viewer.doc?.name ?? "",
    page: String(viewer.page),
    sheet: viewer.store.sheet(viewer.page)?.number ?? "",
    ...extra,
  };
}

export function stampsPlugin(options: StampOptions = {}) {
  let templates: StampTemplate[] = Array.isArray(options.templates) ? options.templates : DEFAULT_STAMPS;
  let chests: ToolChest[] = Array.isArray(options.chests) ? options.chests : [DEFAULT_CHEST];
  let active: StampTemplate = templates[0] ?? DEFAULT_STAMPS[0]!;

  return definePlugin({
    id: "stamps",
    order: 30,
    setup(ctx) {
      const { viewer } = ctx;

      // A server-hosted library lands after the shell opens; the picker re-renders in place.
      if (typeof options.templates === "function") {
        void options.templates()
          .then((loaded) => {
            if (!loaded.length) return;
            templates = loaded;
            active = expand(templates)[0] ?? active;
            ctx.bus.emit("notice", { level: "info", message: `Stamp library loaded (${expand(templates).length} stamps).` });
          })
          .catch(() => { /* library unavailable → built-ins stay */ });
      }
      if (typeof options.chests === "function") {
        void options.chests().then((loaded) => { if (loaded.length) chests = loaded; }).catch(() => {});
      }

      ctx.registerTool({
        id: "stamp", label: "Stamp", icon: "🔖", kind: "stamp", input: "click", group: "review",
        shortcut: "s", sticky: true,
        create({ points, page }) {
          const fields = standardFields(viewer, options.fields?.() ?? {});
          return {
            kind: "stamp", points, page,
            text: resolveTemplate(active.text, fields),
            subject: active.name,
            style: active.style,
            ext: { stampId: active.id, stampTemplate: active.text },
          };
        },
      });

      ctx.registerAction({
        id: "stamps.pick", label: "Choose stamp", icon: "▾", group: "review",
        async run(v) {
          const all = expand(templates);
          const chosen = await choose(v, options.promptText, "Stamp", all.map((s) => s.name));
          const hit = all.find((s) => s.name === chosen);
          if (!hit) return;
          active = hit;
          v.setTool("stamp");
          v.bus.emit("notice", { level: "info", message: `Stamp: ${hit.name}` });
        },
      });

      ctx.registerPanel({
        id: "chest", title: "Tool chest", side: "left", order: 30,
        mount: (host, v) => mountChest(host, v, () => chests),
      });

      viewer.stamps = {
        get templates() { return expand(templates); },
        get active() { return active; },
        setActive(id: string) {
          const hit = expand(templates).find((t) => t.id === id || t.name === id);
          if (hit) active = hit;
          return Boolean(hit);
        },
        get chests() { return chests; },
      };
    },
  });
}

/** A template with dispositions becomes one stamp per disposition. */
function expand(templates: StampTemplate[]): StampTemplate[] {
  return templates.flatMap((t) =>
    t.dispositions?.length
      ? t.dispositions.map((d) => ({
          ...t,
          id: `${t.id}:${slug(d)}`,
          name: `${t.name} — ${d}`,
          text: t.text.includes("{{disposition}}")
            ? t.text.replace(/\{\{disposition\}\}/g, d.toUpperCase())
            : `${d.toUpperCase()} — {{user}} · {{date}}`,
        }))
      : [t],
  );
}

const slug = (s: string): string => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

async function choose(
  v: Viewer,
  promptText: StampOptions["promptText"],
  title: string,
  options: string[],
): Promise<string | null> {
  const ask = promptText ?? (async (t: string, i = "") => globalThis.prompt?.(t, i) ?? null);
  const answer = await ask(`${title}\n\n${options.map((o, i) => `${i + 1}. ${o}`).join("\n")}`, "1");
  void v;
  if (!answer) return null;
  const n = Number(answer.trim());
  if (Number.isInteger(n) && n >= 1 && n <= options.length) return options[n - 1]!;
  return options.find((o) => o.toLowerCase() === answer.trim().toLowerCase()) ?? null;
}

/**
 * The chest panel. Clicking an entry arms the underlying tool *and* pre-loads the entry's styling,
 * so the next markup you draw carries the firm's standard without any further clicks.
 */
function mountChest(host: HTMLElement, v: Viewer, chests: () => ToolChest[]): () => void {
  const render = () => {
    host.innerHTML = "";
    for (const chest of chests()) {
      const h = document.createElement("div");
      h.className = "mpdf-chest-name";
      h.textContent = chest.owner ? `${chest.name} · ${chest.owner}` : chest.name;
      host.appendChild(h);
      const grid = document.createElement("div");
      grid.className = "mpdf-chest-grid";
      for (const tool of chest.tools) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "mpdf-chest-tool";
        b.textContent = tool.label;
        b.style.borderLeftColor = tool.style?.color ?? "var(--mpdf-accent)";
        b.title = `${tool.kind}${tool.discipline ? ` · ${tool.discipline}` : ""}`;
        b.onclick = () => armChestTool(v, tool);
        grid.appendChild(b);
      }
      host.appendChild(grid);
    }
  };
  render();
  return () => { host.innerHTML = ""; };
}

/**
 * Arm a chest entry: pick the tool whose kind matches, and hook the next `annot:added` to stamp the
 * chest styling onto it. One-shot — it unsubscribes as soon as it fires or the tool changes.
 */
function armChestTool(v: Viewer, tool: ChestTool): void {
  const match = v.toolList.find((t) => t.kind === tool.kind);
  if (!match) {
    v.bus.emit("notice", { level: "error", message: `No tool registered for "${tool.kind}".` });
    return;
  }
  v.setTool(match.id);
  const offAdd = v.on("annot:added", ({ annot }) => {
    if (annot.kind !== tool.kind) return;
    done();
    v.store.update(annot.id, {
      style: { ...annot.style, ...tool.style },
      ...(tool.discipline ? { discipline: tool.discipline } : {}),
      ...(tool.subject ? { subject: tool.subject } : {}),
      ...(tool.labels ? { labels: [...(annot.labels ?? []), ...tool.labels] } : {}),
      ...(tool.text && !annot.text ? { text: tool.text } : {}),
    }, { undoable: false });
  });
  const offTool = v.on("tool:changed", () => done());
  const done = () => { offAdd(); offTool(); };
}

declare module "../core/viewer" {
  interface Viewer {
    /** Present once the stamps plugin is installed. */
    stamps?: {
      readonly templates: StampTemplate[];
      readonly active: StampTemplate;
      setActive(id: string): boolean;
      readonly chests: ToolChest[];
    };
  }
}
