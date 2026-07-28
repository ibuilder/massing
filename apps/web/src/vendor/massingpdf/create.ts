/**
 * The batteries-included entry point.
 *
 * `new Viewer({...})` plus the standard plugin set, in the order they expect. Hosts that want a
 * different UI or a subset construct the `Viewer` themselves — this is a convenience, not a
 * requirement, and nothing in the kernel depends on it.
 */
import { Viewer, type ViewerOptions } from "./core/viewer";
import { configureWorker, workerConfigured } from "./core/document";
import { markupPlugin, type MarkupOptions } from "./plugins/markup";
import { measurePlugin, type MeasureOptions } from "./plugins/measure";
import { stampsPlugin, type StampOptions } from "./plugins/stamps";
import { pinsPlugin, type PinOptions } from "./plugins/pins";
import { markupListPlugin, type MarkupListOptions } from "./plugins/markupList";
import { comparePlugin, type CompareOptions } from "./plugins/compare";
import { migrationPlugin, type MigrationOptions } from "./plugins/migration";
import { searchPlugin, type SearchOptions } from "./plugins/search";
import { specsPlugin, type SpecsOptions } from "./plugins/specs";
import { historicalPlugin, type HistoricalOptions } from "./plugins/historical";
import { attachmentsPlugin, type AttachmentOptions } from "./plugins/attachments";
import { ocrPlugin, type OcrOptions } from "./plugins/ocr";
import { viewsPlugin, type ViewsOptions } from "./plugins/views";
import { sheetsPlugin, type SheetsOptions } from "./plugins/sheets";
import { toolbarPlugin, type ToolbarOptions } from "./plugins/toolbar";
import { exportersPlugin, type ExportOptions } from "./plugins/exporters";
import { persistencePlugin, type PersistenceOptions } from "./plugins/persistence";
import type { ViewerPlugin } from "./core/plugin";

export interface CreateViewerOptions extends Omit<ViewerOptions, "plugins"> {
  /** URL of the bundled pdf.js worker. Required unless `configureWorker` was already called. */
  workerUrl?: string;
  /** Per-plugin options; `false` disables a plugin entirely. */
  markup?: MarkupOptions | false;
  measure?: MeasureOptions | false;
  stamps?: StampOptions | false;
  pins?: PinOptions | false;
  list?: MarkupListOptions | false;
  compare?: CompareOptions | false;
  /** Slip-sheet migration. Depends on compare's alignment; enabled by default. */
  migration?: MigrationOptions | false;
  search?: SearchOptions | false;
  /** Saved views and the split pane. */
  views?: ViewsOptions | false;
  sheets?: SheetsOptions | false;
  /**
   * The specifications workspace. Enabled, but parsing is on demand — a 900-page spec book is not
   * something to index before anyone asks for it.
   */
  specs?: SpecsOptions | false;
  /** Preservation mode: provenance, uncertainty, legibility adjustments. Off unless configured. */
  historical?: HistoricalOptions | false;
  /** Photo/file attachments on markups. Off unless configured. */
  attachments?: AttachmentOptions | false;
  /**
   * OCR for scanned sheets. Off unless configured, and the recogniser is yours to supply — see
   * `tesseractProvider` for offline, `restOcrProvider` for a service.
   */
  ocr?: OcrOptions | false;
  toolbar?: ToolbarOptions | false;
  exporters?: ExportOptions | false;
  /** Persistence is opt-in — omit it and markups live only in memory. */
  persistence?: PersistenceOptions;
  /** Extra plugins, installed after the standard set. */
  plugins?: ViewerPlugin[];
}

/** Build a viewer with the standard plugin set. */
export async function createViewer(options: CreateViewerOptions): Promise<Viewer> {
  const {
    workerUrl, markup, measure, stamps, pins, list, compare, migration, search, sheets, specs,
    historical, attachments, ocr, views, toolbar, exporters, persistence, plugins = [], ...viewerOptions
  } = options;

  if (workerUrl) configureWorker(workerUrl);
  if (!workerConfigured()) {
    throw new Error(
      "No pdf.js worker configured. Pass `workerUrl` (bundle it — do not load it from a CDN, the viewer must work offline) " +
      "or call configureWorker() yourself before creating a viewer.",
    );
  }

  const viewer = new Viewer(viewerOptions);
  const standard: (ViewerPlugin | null)[] = [
    // Before sheets: title-block extraction reads through the same kernel seam OCR fills.
    ocr ? ocrPlugin(ocr) : null,
    sheets === false ? null : sheetsPlugin(sheets ?? {}),
    markup === false ? null : markupPlugin(markup ?? {}),
    measure === false ? null : measurePlugin(measure ?? {}),
    stamps === false ? null : stampsPlugin(stamps ?? {}),
    pins === false ? null : pinsPlugin(pins ?? {}),
    list === false ? null : markupListPlugin(list ?? {}),
    search === false ? null : searchPlugin(search ?? {}),
    views === false ? null : viewsPlugin(views ?? {}),
    specs === false ? null : specsPlugin(specs ?? {}),
    compare === false ? null : comparePlugin(compare ?? {}),
    migration === false ? null : migrationPlugin(migration ?? {}),
    // Opt-in: these add panels most projects don't want on screen by default.
    historical ? historicalPlugin(historical) : null,
    attachments ? attachmentsPlugin(attachments) : null,
    exporters === false ? null : exportersPlugin(exporters ?? {}),
    persistence ? persistencePlugin(persistence) : null,
    ...plugins,
    // The toolbar last, so it sees every registered tool and action.
    toolbar === false ? null : toolbarPlugin(toolbar ?? {}),
  ];

  for (const plugin of standard) {
    if (plugin) await viewer.use(plugin);
  }
  return viewer;
}
