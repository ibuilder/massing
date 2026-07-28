/**
 * Export actions: marked-up PDF, XFDF, BCF topics, CSV, takeoff roll-up, and the native JSON
 * tool-set. Each exports the *filtered* set, so narrowing the markup list narrows the report.
 */
import { definePlugin } from "../core/plugin";
import { flattenToPdf, type FlattenOptions } from "../io/flatten";
import { toXfdf, fromXfdf } from "../io/xfdf";
import { toBcfTopics, toBcfZip } from "../io/bcf";
import { toCsv, toTakeoffCsv } from "../io/csv";
import type { Annotation, Calibration, SheetMeta } from "../core/types";
import type { Viewer } from "../core/viewer";

/** The native, lossless session format — markups plus calibration plus sheet register. */
export interface MarkupSet {
  format: "massing-pdf-markups";
  version: 1;
  document?: { name: string; fingerprint: string; pages: number };
  exportedAt: string;
  annotations: Annotation[];
  calibrations: Calibration[];
  sheets: SheetMeta[];
}

/** UTF-8 byte-order mark. Excel reads a BOM-less CSV as the system codepage and mangles accents. */
const BOM = "﻿";

export interface ExportOptions {
  /** Export everything rather than the filtered subset. */
  all?: boolean;
  /** Hand the produced file to the host instead of triggering a browser download. */
  onFile?: (blob: Blob, filename: string) => void | Promise<void>;
  flatten?: Omit<FlattenOptions, "annotations">;
}

export function exportersPlugin(options: ExportOptions = {}) {
  const deliver = async (blob: Blob, filename: string) => {
    if (options.onFile) { await options.onFile(blob, filename); return; }
    download(blob, filename);
  };
  const setOf = (v: Viewer): Annotation[] => (options.all ? v.store.all() : v.store.visible());
  const stem = (v: Viewer): string => (v.doc?.name ?? "document").replace(/\.pdf$/i, "");

  return definePlugin({
    id: "exporters",
    order: 85,
    setup(ctx) {
      ctx.registerAction({
        id: "export.pdf", label: "Export marked-up PDF", icon: "⤓", group: "io",
        enabled: (v) => Boolean(v.doc),
        async run(v) {
          const annots = setOf(v);
          if (!annots.length) { v.bus.emit("notice", { level: "warn", message: "Nothing to export." }); return; }
          try {
            v.bus.emit("notice", { level: "info", message: "Building PDF…" });
            const bytes = await flattenToPdf(v.doc!, {
              annotations: annots,
              feetInches: v.feetInches,
              summaryPage: true,
              title: `${stem(v)} — markup schedule`,
              ...options.flatten,
            });
            await deliver(new Blob([bytes as BlobPart], { type: "application/pdf" }), `${stem(v)}-markup.pdf`);
            v.bus.emit("notice", { level: "success", message: `Exported ${annots.length} markups.` });
          } catch (e) {
            v.bus.emit("notice", { level: "error", message: `PDF export failed: ${(e as Error).message}` });
          }
        },
      });

      ctx.registerAction({
        id: "export.xfdf", label: "Export XFDF", icon: "⇥", group: "io",
        enabled: (v) => Boolean(v.doc),
        async run(v) {
          const pages = await pageBoxes(v);
          const xml = toXfdf(setOf(v), { pages, href: v.doc?.name ?? "" });
          await deliver(new Blob([xml], { type: "application/vnd.adobe.xfdf" }), `${stem(v)}.xfdf`);
          v.bus.emit("notice", { level: "success", message: "XFDF exported — opens in Bluebeam, Acrobat and Foxit." });
        },
      });

      ctx.registerAction({
        id: "import.xfdf", label: "Import XFDF", icon: "⇤", group: "io",
        enabled: (v) => Boolean(v.doc),
        async run(v) {
          const file = await pickFile(".xfdf,.xml,application/xml");
          if (!file) return;
          try {
            const pages = await pageBoxes(v);
            const drafts = fromXfdf(await file.text(), { pages, defaultAuthor: v.author });
            if (!drafts.length) { v.bus.emit("notice", { level: "warn", message: "No markups found in that file." }); return; }
            v.store.addMany(drafts);
            v.redraw();
            v.bus.emit("notice", { level: "success", message: `Imported ${drafts.length} markups.` });
          } catch (e) {
            v.bus.emit("notice", { level: "error", message: `XFDF import failed: ${(e as Error).message}` });
          }
        },
      });

      ctx.registerAction({
        id: "export.bcf", label: "Export BCF topics", icon: "⌂", group: "io",
        async run(v) {
          const topics = toBcfTopics(setOf(v), { documentName: v.doc?.name });
          if (!topics.length) { v.bus.emit("notice", { level: "warn", message: "No issues to export." }); return; }
          const json = JSON.stringify(topics, null, 2);
          await deliver(new Blob([json], { type: "application/json" }), `${stem(v)}-bcf-topics.json`);
          v.bus.emit("notice", { level: "success", message: `Exported ${topics.length} BCF topics.` });
        },
      });

      ctx.registerAction({
        id: "export.bcfzip", label: "Export BCF archive (.bcfzip)", icon: "🗂", group: "io",
        async run(v) {
          const topics = toBcfTopics(setOf(v), { documentName: v.doc?.name });
          if (!topics.length) { v.bus.emit("notice", { level: "warn", message: "No issues to export." }); return; }
          const bytes = toBcfZip(topics, { projectName: v.doc?.name ?? "Massing" });
          await deliver(new Blob([bytes as BlobPart], { type: "application/octet-stream" }), `${stem(v)}.bcfzip`);
          v.bus.emit("notice", {
            level: "success",
            message: `Exported ${topics.length} topics as a BCF archive — opens in Solibri, BIMcollab and Revit.`,
          });
        },
      });

      ctx.registerAction({
        id: "export.csv", label: "Export markup list (CSV)", icon: "↧", group: "io",
        async run(v) {
          const csv = toCsv(setOf(v), {
            feetInches: v.feetInches,
            sheetNumber: (p) => v.store.sheet(p)?.number,
          });
          await deliver(new Blob([BOM + csv], { type: "text/csv;charset=utf-8" }), `${stem(v)}-markups.csv`);
        },
      });

      ctx.registerAction({
        id: "export.takeoff", label: "Export takeoff (CSV)", icon: "Σ", group: "io",
        enabled: (v) => v.store.all().some((a) => a.quantity),
        async run(v) {
          const csv = toTakeoffCsv(setOf(v), { feetInches: v.feetInches });
          await deliver(new Blob([BOM + csv], { type: "text/csv;charset=utf-8" }), `${stem(v)}-takeoff.csv`);
        },
      });

      ctx.registerAction({
        id: "export.json", label: "Save markup set", icon: "⭳", group: "io",
        async run(v) {
          const json = JSON.stringify(buildSet(v, setOf(v)), null, 2);
          await deliver(new Blob([json], { type: "application/json" }), `${stem(v)}-markups.json`);
        },
      });

      ctx.registerAction({
        id: "import.json", label: "Load markup set", icon: "⭱", group: "io",
        async run(v) {
          const file = await pickFile(".json,application/json");
          if (!file) return;
          try {
            const set = JSON.parse(await file.text()) as MarkupSet;
            if (set.format !== "massing-pdf-markups") throw new Error("not a Massing markup set");
            applySet(v, set);
            v.bus.emit("notice", { level: "success", message: `Loaded ${set.annotations.length} markups.` });
          } catch (e) {
            v.bus.emit("notice", { level: "error", message: `Couldn't load that file: ${(e as Error).message}` });
          }
        },
      });
    },
  });
}

/** Serialise the current session. */
export function buildSet(v: Viewer, annotations: Annotation[] = v.store.all()): MarkupSet {
  return {
    format: "massing-pdf-markups",
    version: 1,
    ...(v.doc ? { document: { name: v.doc.name, fingerprint: v.doc.fingerprint, pages: v.doc.numPages } } : {}),
    exportedAt: new Date().toISOString(),
    annotations,
    calibrations: v.store.allCalibrations(),
    sheets: v.store.allSheets(),
  };
}

/** Apply a saved set over the current document. */
export function applySet(v: Viewer, set: MarkupSet): void {
  v.store.reset(set.annotations ?? []);
  for (const c of set.calibrations ?? []) v.store.setCalibration(c, c.page);
  for (const s of set.sheets ?? []) v.store.setSheet(s);
  v.redraw();
}

/** Page boxes for the whole document, which XFDF needs for its y-flip. */
async function pageBoxes(v: Viewer): Promise<Map<number, { width: number; height: number }>> {
  const map = new Map<number, { width: number; height: number }>();
  if (!v.doc) return map;
  for (const info of await v.doc.primeInfo()) map.set(info.page, { width: info.width, height: info.height });
  return map;
}

function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  // Revoking synchronously can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function pickFile(accept: string): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.onchange = () => resolve(input.files?.[0] ?? null);
    input.oncancel = () => resolve(null);
    input.click();
  });
}
