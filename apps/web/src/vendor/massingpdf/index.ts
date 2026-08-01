/**
 * `@massingcloud/pdf-viewer` — a construction drawing review engine.
 *
 * Two ways in:
 *
 * ```ts
 * // 1. Batteries included.
 * import { createViewer } from "@massingcloud/pdf-viewer";
 * import "@massingcloud/pdf-viewer/style.css";
 * import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
 *
 * const viewer = await createViewer({ container, workerUrl, author: "A. Reviewer" });
 * await viewer.load({ url: "/sheets/A-201.pdf", name: "A-201.pdf" });
 * ```
 *
 * ```ts
 * // 2. Kernel plus the plugins you want.
 * import { Viewer, configureWorker, markupPlugin, measurePlugin } from "@massingcloud/pdf-viewer";
 * configureWorker(workerUrl);
 * const viewer = new Viewer({ container, plugins: [markupPlugin(), measurePlugin()] });
 * ```
 */

// Emits `dist/massing-pdf.css`. Vite extracts it rather than injecting it, so consumers still
// `import "@massingcloud/pdf-viewer/style.css"` — which is what lets a host drop it and ship its own.
import "./styles.css";

// ---- kernel ----------------------------------------------------------------
export { Viewer, type ViewerOptions } from "./core/viewer";
export { PdfDocument, configureWorker, workerConfigured, type PdfSource, type PageInfo, type TextItem, type OutlineItem } from "./core/document";
export { PageView, tileBoxes, type Rect } from "./core/renderer";
export {
  TextLayer, splitWords, mergeByLine, unionBox, clearSelection, quadContains,
  type TextSelection, type TextQuad, type Word,
} from "./core/textLayer";
export { AnnotationStore, makeId, type StoreOpts } from "./core/store";
export { EventBus, type ViewerEvents, type EventName, type Handler, type Unsubscribe } from "./core/events";
export { matchesFilter, isEmptyFilter, facets } from "./core/filter";
export { definePlugin } from "./core/plugin";
export type {
  ActionDef, KindRenderer, PanelDef, PluginContext, RenderCtx, ToolCommit, ToolDef, ToolInput, ViewerPlugin,
} from "./core/plugin";

// ---- model -----------------------------------------------------------------
export type {
  Annotation, AnnotationDraft, AnnotAttachment, AnnotFilter, AnnotKind, AnnotLinks, AnnotPriority,
  AnnotReply, AnnotStatus, AnnotStyle, Box, Calibration, Discipline, Pt, Provenance, Quantity,
  RevisionContext, SavedView, SheetKind, SheetMeta,
} from "./core/types";
export { DISCIPLINE_COLORS, STATUS_COLORS, MEASURE_KINDS, POINT_KINDS, isMeasureKind } from "./core/types";

// ---- geometry & units ------------------------------------------------------
export {
  angleAt, bbox, boxContains, boxesOverlap, centroid, circumradius, cloudPath, dist, distToPath,
  distToSegment, growBox, linePath, mean, pathLength, perimeter, pointInPolygon, polygonArea,
  rectCorners, rotateAbout, scaleAbout, simplify, smoothPath, snapAngle, translate,
} from "./core/geometry";
export {
  LENGTH_UNITS, SCALE_PRESETS, calibrationFromMeasure, calibrationFromPreset, convertLength,
  findPreset, formatCalibration, formatFeetInches, formatQuantity, isLengthUnit, measure,
  parseLength, recalculate, type LengthUnit, type ScalePreset, type FormatOpts,
} from "./core/units";
export {
  displaySize, displayToPage, eventToPage, normalizeRotation, pageToDisplay, rotationTransform,
  type Rotation,
} from "./core/coords";

// ---- rendering -------------------------------------------------------------
export { drawAnnotation, drawDraft, resolveStyle, el as svgEl, SVG_NS, type DrawOpts } from "./render/svg";

// ---- plugins ---------------------------------------------------------------
export { markupPlugin, MarkupSettings, type MarkupOptions } from "./plugins/markup";
export { measurePlugin, recalculateAll, type MeasureOptions } from "./plugins/measure";
export {
  stampsPlugin, resolveTemplate, standardFields, DEFAULT_STAMPS, DEFAULT_CHEST,
  type StampOptions, type StampTemplate, type ToolChest, type ChestTool,
} from "./plugins/stamps";
export { pinsPlugin, DEFAULT_ISSUE_TYPES, type PinOptions, type IssueFields } from "./plugins/pins";
export { markupListPlugin, type MarkupListOptions } from "./plugins/markupList";
export { comparePlugin, comparePages, type CompareOptions, type CompareResult, type DiffRegion } from "./plugins/compare";
export {
  migrationPlugin, planMigration, migrate,
  type MigrationOptions, type MigrationProposal, type MigrationVerdict,
} from "./plugins/migration";
export { searchPlugin, findInWords, type SearchOptions, type SearchHit, type HitSource } from "./plugins/search";
export { viewsPlugin, applyView, type ViewsOptions } from "./plugins/views";
export {
  specsPlugin, parseSpecs, parseSpecLines, extractRequirements,
  findSpecReferences, scanSpecReferences,
  type SpecsOptions, type SpecSection, type SpecClause, type SpecLine, type SpecRequirement,
  type SpecReference,
} from "./plugins/specs";
export {
  historicalPlugin, CONFIDENCE_LEVELS,
  type HistoricalOptions, type Confidence, type ImageAdjustments,
} from "./plugins/historical";
export {
  attachmentsPlugin, recordVoiceNote, voiceSupported, type AttachmentOptions,
} from "./plugins/attachments";
export {
  ocrPlugin, tesseractProvider, restOcrProvider, toTextItems, planTileGrid, dedupeWords,
  type OcrOptions, type OcrProvider, type OcrInput, type OcrResult, type OcrWord,
  type TilePlanOptions,
} from "./plugins/ocr";
export {
  paddleOcrProvider,
  azureOcrProvider, googleVisionOcrProvider, fallbackOcrProvider, toBase64Png, toPngBlob,
  type PaddleOcrOptions, type AzureOcrOptions, type GoogleOcrOptions, type FallbackOptions,
} from "./plugins/ocr-providers";
export {
  Policy, PermissionError, capabilityCheck,
  type Capability, type PermissionCheck, type PermissionDecision, type PermissionRequest,
  type AuditEvent, type AuditSink,
} from "./core/policy";
export { safeMediaUrl, safeNavigableUrl } from "./core/url";
export {
  activate, rovingFocus, refreshRovingTabstops, createLiveRegion, trapFocus,
  type ActivateOptions,
} from "./core/a11y";
export { sheetsPlugin, extractSheetMeta, type SheetsOptions } from "./plugins/sheets";
export { toolbarPlugin, type ToolbarOptions } from "./plugins/toolbar";
export { persistencePlugin, type PersistenceOptions } from "./plugins/persistence";
export { exportersPlugin, buildSet, applySet, type ExportOptions, type MarkupSet } from "./plugins/exporters";

// ---- interchange -----------------------------------------------------------
export { toXfdf, fromXfdf, type XfdfExportOptions, type XfdfImportOptions, type XfdfPageBox } from "./io/xfdf";
export {
  toBcfTopic, toBcfTopics, fromBcfTopic, toBcfZip, topicMarkupXml,
  encodeAnchor, decodeAnchor, normaliseGuid,
  type BcfTopic, type BcfComment, type BcfExport, type SheetAnchor, type BcfZipOptions,
} from "./io/bcf";
export { zip, type ZipEntry } from "./io/zip";
export { toCsv, toTakeoffCsv, DEFAULT_COLUMNS, type CsvOptions, type CsvColumn } from "./io/csv";
export { flattenToPdf, type FlattenOptions } from "./io/flatten";

// ---- persistence -----------------------------------------------------------
export { MemoryAdapter } from "./adapters/memory";
export { IndexedDbAdapter, indexedDbAvailable } from "./adapters/indexeddb";
export { RestAdapter, toWire, fromWire, type RestOptions, type RestPaths } from "./adapters/rest";
export { OfflineAdapter, type OfflineOptions } from "./adapters/offline";
export { ConflictError, type LoadResult, type Mutation, type StorageAdapter, type StoreKey } from "./adapters/types";

// ---- convenience -----------------------------------------------------------
export { createViewer, type CreateViewerOptions } from "./create";
