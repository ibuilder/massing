/**
 * Measurement and takeoff.
 *
 * Calibration is per page, because a plan sheet and its enlarged detail are different scales and a
 * document-wide factor quietly produces wrong numbers on half the set. The `raw` page-unit
 * magnitude is retained on every quantity, so re-calibrating a page re-derives every measurement on
 * it instead of forcing the estimator to draw them again.
 */
import { definePlugin } from "../core/plugin";
import { pathLength } from "../core/geometry";
import {
  SCALE_PRESETS, calibrationFromMeasure, calibrationFromPreset, formatCalibration,
  formatQuantity, parseLength,
} from "../core/units";
import type { Annotation, Calibration } from "../core/types";
import type { Viewer } from "../core/viewer";

export interface MeasureOptions {
  /** Prompt for free text. Defaults to `window.prompt`. */
  promptText?: (title: string, initial?: string) => Promise<string | null>;
  /** Pick from a list. Defaults to a prompt showing the labels. */
  pickOption?: (title: string, options: string[]) => Promise<string | null>;
  /** Default unit assumed when a calibration length is typed without one. */
  defaultUnit?: string;
}

const defaultPrompt = async (t: string, i = ""): Promise<string | null> => globalThis.prompt?.(t, i) ?? null;

export function measurePlugin(options: MeasureOptions = {}) {
  const ask = options.promptText ?? defaultPrompt;
  const pick = options.pickOption ?? (async (title, opts) => {
    const answer = await ask(`${title}\n\n${opts.map((o, i) => `${i + 1}. ${o}`).join("\n")}`, "");
    if (!answer) return null;
    const n = Number(answer.trim());
    if (Number.isInteger(n) && n >= 1 && n <= opts.length) return opts[n - 1]!;
    return opts.find((o) => o.toLowerCase() === answer.trim().toLowerCase()) ?? null;
  });

  return definePlugin({
    id: "measure",
    order: 20,
    setup(ctx) {
      const { viewer } = ctx;

      // --- calibration ------------------------------------------------------
      ctx.registerTool({
        id: "calibrate", label: "Calibrate", icon: "📏", kind: "distance", input: "drag",
        group: "measure", shortcut: "k", cursor: "crosshair",
        async create({ points, page }) {
          const px = pathLength(points);
          if (px <= 0) return null;
          const answer = await ask("Real length of the line you just drew (e.g. 5 m, 20', 12'-6\")", "");
          if (!answer) return null;
          const parsed = parseLength(answer, options.defaultUnit ?? "m");
          if (!parsed) {
            viewer.bus.emit("notice", { level: "error", message: `Couldn't read "${answer}" as a length.` });
            return null;
          }
          const cal = calibrationFromMeasure(px, parsed.value, parsed.unit, page);
          if (!cal) return null;
          viewer.store.setCalibration(cal, page);
          viewer.recalculatePage(page);
          viewer.bus.emit("notice", {
            level: "success",
            message: `Page ${page} scale set — ${formatCalibration(cal)}${cal.label ? "" : " (no matching standard scale)"}`,
          });
          // The calibration line itself is a transient, not a markup.
          return null;
        },
      });

      ctx.registerAction({
        id: "measure.preset", label: "Scale preset", icon: "⧉", group: "measure",
        async run(v) {
          const labels = SCALE_PRESETS.map((p) => p.label);
          const chosen = await pick(`Drawing scale for page ${v.page}`, labels);
          if (!chosen) return;
          const cal = calibrationFromPreset(chosen, v.page);
          if (!cal) return;
          v.store.setCalibration(cal, v.page);
          v.recalculatePage(v.page);
          v.bus.emit("notice", { level: "success", message: `Page ${v.page}: ${chosen}` });
        },
      });

      ctx.registerAction({
        id: "measure.applyAllPages", label: "Apply scale to all pages", icon: "⇉", group: "measure",
        enabled: (v) => Boolean(v.store.calibration(v.page)),
        run(v) {
          const cal = v.store.calibration(v.page);
          if (!cal) return;
          for (let p = 1; p <= v.numPages; p++) {
            v.store.setCalibration({ ...cal, page: p }, p);
            v.recalculatePage(p);
          }
          v.bus.emit("notice", { level: "success", message: `Applied ${formatCalibration(cal)} to all ${v.numPages} pages.` });
        },
      });

      // --- measurement tools -------------------------------------------------
      const M = (id: string, label: string, icon: string, kind: Annotation["kind"], input: "drag" | "poly" | "click", extra = {}) =>
        ctx.registerTool({
          id, label, icon, kind, input, group: "measure", needsCalibration: kind !== "count" && kind !== "angle",
          create: ({ points, page }) => ({ kind, points, page, subject: label }),
          ...extra,
        });

      M("distance", "Distance", "📐", "distance", "drag", { shortcut: "d" });
      M("polydistance", "Polyline length", "〰", "distance", "poly", { minPoints: 2 });
      M("area", "Area", "▱", "area", "poly", { minPoints: 3, shortcut: "e" });
      M("perimeter", "Perimeter", "⬡", "perimeter", "poly", { minPoints: 3 });
      M("angle", "Angle", "∠", "angle", "poly", { minPoints: 3, maxPoints: 3 });
      M("radius", "Radius", "◜", "radius", "poly", { minPoints: 3, maxPoints: 3 });

      /** Count is sticky: an estimator drops fifty of them without re-picking the tool. */
      ctx.registerTool({
        id: "count", label: "Count", icon: "#", kind: "count", input: "click", group: "measure",
        shortcut: "n", sticky: true,
        create: ({ points, page }) => ({ kind: "count", points, page, subject: "Count" }),
      });

      /** Area × depth, for slabs, walls and excavation. Asks once, stores the factor. */
      ctx.registerTool({
        id: "volume", label: "Volume", icon: "⬢", kind: "volume", input: "poly", group: "measure",
        minPoints: 3, needsCalibration: true,
        async create({ points, page }) {
          const cal = viewer.store.calibration(page);
          const answer = await ask(`Depth / height (in ${cal?.unit ?? "m"})`, "");
          const parsed = answer ? parseLength(answer, cal?.unit ?? "m") : null;
          if (!parsed) return null;
          return { kind: "volume", points, page, subject: "Volume", quantity: undefined, ext: { depth: parsed.value } };
        },
      });

      // --- roll-up panel ------------------------------------------------------
      ctx.registerPanel({
        id: "takeoff", title: "Takeoff", side: "right", order: 20,
        mount(host, v) { return mountTakeoff(host, v); },
      });

      // Volume needs its depth folded in after the kernel's generic measure pass.
      ctx.bus.on("annot:added", ({ annot }) => {
        const depth = annot.ext?.["depth"];
        if (annot.kind !== "volume" || typeof depth !== "number" || !annot.quantity) return;
        const cal = viewer.store.calibration(annot.page);
        if (!cal || annot.quantity.depth === depth) return;
        viewer.store.update(annot.id, {
          quantity: { ...annot.quantity, depth, value: (annot.quantity.raw ?? 0) * cal.unitsPerPoint ** 2 * depth, unit: `${cal.unit}³` },
        }, { undoable: false });
      });
    },
  });
}

/** Live totals by kind and by assembly — the panel an estimator keeps open. */
function mountTakeoff(host: HTMLElement, v: Viewer): () => void {
  const box = document.createElement("div");
  box.className = "mpdf-takeoff";
  host.appendChild(box);

  const render = () => {
    const cal = v.store.calibration(v.page);
    const annots = v.store.visible().filter((a) => a.quantity);
    const groups = new Map<string, { count: number; total: number; unit: string }>();
    for (const a of annots) {
      const key = a.quantity!.assembly || a.subject || a.kind;
      const g = groups.get(key) ?? { count: 0, total: 0, unit: a.quantity!.unit };
      g.count++;
      // Only sum like units — a mixed bucket reports a count and no total rather than nonsense.
      if (g.unit === a.quantity!.unit) g.total += a.quantity!.value;
      else g.unit = "—";
      groups.set(key, g);
    }
    box.innerHTML = "";
    const scale = document.createElement("div");
    scale.className = "mpdf-takeoff-scale";
    scale.textContent = `Page ${v.page}: ${formatCalibration(cal)}`;
    if (!cal) scale.classList.add("mpdf-warn");
    box.appendChild(scale);

    if (!groups.size) {
      const empty = document.createElement("p");
      empty.className = "mpdf-empty";
      empty.textContent = "No measurements yet. Calibrate the page, then measure.";
      box.appendChild(empty);
      return;
    }
    const table = document.createElement("table");
    table.className = "mpdf-table";
    table.innerHTML = "<thead><tr><th>Item</th><th>Qty</th><th>Total</th></tr></thead>";
    const tb = document.createElement("tbody");
    for (const [key, g] of [...groups].sort((a, b) => a[0].localeCompare(b[0]))) {
      const tr = document.createElement("tr");
      const total = g.unit === "—" ? "—" : formatQuantity({ value: g.total, unit: g.unit }, { feetInches: v.feetInches });
      for (const text of [key, String(g.count), total]) {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      }
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    box.appendChild(table);
  };

  const offs = [
    v.on("annot:added", render), v.on("annot:updated", render), v.on("annot:removed", render),
    v.on("annot:reset", render), v.on("calibration:changed", render), v.on("filter:changed", render),
    v.on("page:changed", render),
  ];
  render();
  return () => offs.forEach((off) => off());
}

/** Re-derive every quantity in the document against its page calibration. */
export function recalculateAll(v: Viewer): void {
  for (let p = 1; p <= v.numPages; p++) v.recalculatePage(p);
}

export type { Calibration };
