/**
 * The annotation schema — the whole point of the product.
 *
 * A markup here is a *record*, not ink. It carries who/when/why, a discipline and a status, a
 * measured quantity with units, the revision it was drawn against, and links out to issues, spec
 * clauses and BIM objects. Rendering is a projection of this record; XFDF, BCF and CSV are other
 * projections. Nothing in the viewer stores presentation-only state that can't round-trip.
 *
 * Geometry lives in **page space**: PDF user units (1/72"), origin top-left, y down, unrotated.
 * That is the same space `pdf.js` reports at `scale: 1` — so a markup is zoom-, rotation- and
 * viewport-independent, and `nx`/`ny` (0..1 of the page box) give a resolution-free anchor that a
 * different renderer (an SVG sheet, a mobile canvas) can place in its own box.
 */

/** A point in page space (PDF user units, top-left origin). */
export interface Pt { x: number; y: number }

/** Axis-aligned box in page space. */
export interface Box { x: number; y: number; w: number; h: number }

/**
 * Every markup kind the engine understands. Adding one means: a `ToolDef` that produces the
 * geometry, a branch in the renderer, and (if it should survive a flatten) a branch in the burner.
 */
export type AnnotKind =
  // --- shape markups -------------------------------------------------------
  | "rect" | "ellipse" | "polygon" | "polyline" | "line" | "arrow" | "cloud" | "ink"
  // --- text markups --------------------------------------------------------
  | "text" | "callout" | "highlight" | "strikeout" | "underline"
  // --- construction markups ------------------------------------------------
  | "stamp" | "pin" | "symbol"
  // --- measurements --------------------------------------------------------
  | "distance" | "perimeter" | "area" | "count" | "angle" | "radius" | "volume";

/** Measurement kinds — the subset that carries a calibrated quantity. */
export const MEASURE_KINDS = ["distance", "perimeter", "area", "count", "angle", "radius", "volume"] as const;
export const isMeasureKind = (k: AnnotKind): boolean => (MEASURE_KINDS as readonly string[]).includes(k);

/** Kinds anchored by a single point rather than a path. */
export const POINT_KINDS: readonly AnnotKind[] = ["text", "stamp", "pin", "count", "symbol"];

/** Review status. Drives filtering, roll-ups and the status board — not just a colour. */
export type AnnotStatus = "open" | "in_review" | "accepted" | "rejected" | "resolved" | "void" | "info";

export type AnnotPriority = "low" | "normal" | "high" | "critical";

/** CSI-ish discipline code used for colour presets, filters and per-discipline roll-ups. */
export type Discipline =
  | "general" | "architectural" | "structural" | "civil" | "mechanical" | "electrical"
  | "plumbing" | "fire" | "landscape" | "interiors" | "survey" | "preservation";

/** How the drawing this markup sits on is classified. Drives tool presets and navigation. */
export type SheetKind =
  | "plan" | "ceiling_plan" | "site_plan" | "elevation" | "section" | "detail" | "schedule"
  | "spec" | "shop_drawing" | "historic" | "sketch" | "unknown";

/** A threaded reply on a markup. */
export interface AnnotReply {
  id: string;
  author: string;
  org?: string;
  body: string;
  createdAt: string;             // ISO 8601
  mentions?: string[];
}

/** A file/photo/voice-note pinned to the markup (stored by reference — the host owns the bytes). */
export interface AnnotAttachment {
  id: string;
  name: string;
  mime: string;
  url?: string;
  size?: number;
  kind?: "photo" | "video" | "audio" | "file";
  /** Where on the sheet the attachment icon sits, if not at the markup anchor. */
  at?: Pt;
}

/** The calibrated quantity a measurement carries. */
export interface Quantity {
  value: number;
  /** Display unit, e.g. `m`, `ft`, `m²`, `ea`, `°`. */
  unit: string;
  /** Raw geometric magnitude in page units before calibration — lets a re-calibration re-derive
   *  every quantity on the page without re-measuring. */
  raw?: number;
  /** Extra depth/height factor for volume and wall-area style derivations. */
  depth?: number;
  /** Free-text takeoff bucket (assembly, cost code, trade package). */
  assembly?: string;
}

/** Provenance for archival / scanned sheets — spec §11, first-class rather than an edge case. */
export interface Provenance {
  archive?: string;               // holding institution or collection
  collection?: string;
  sourceRef?: string;             // catalogue / accession number
  scanDpi?: number;
  drawnDate?: string;             // ISO date of the original drawing, if known
  architect?: string;
  /** How much the reviewer trusts what they read off the sheet here. */
  confidence?: "certain" | "probable" | "uncertain" | "illegible";
  /** Verbatim transcription of a handwritten note under this markup. */
  transcript?: string;
}

/** Outbound links — a markup is a join table between the sheet and the rest of the project. */
export interface AnnotLinks {
  /** Issue / RFI / punch item id in the host system (BCF topic GUID when BCF-backed). */
  issueId?: string;
  /** Spec section + clause this markup cites, e.g. `{ section: "079200", clause: "2.1.A" }`. */
  spec?: { section: string; clause?: string; documentId?: string };
  /** IFC GlobalIds this markup refers to. Massing addresses model elements by GUID, never by
   *  transient viewer ids — so do the same here. */
  ifcGuids?: string[];
  /** Another markup (e.g. the same note carried to a detail sheet). */
  relatedAnnotIds?: string[];
  /** Arbitrary host record, e.g. `{ module: "submittal", id: "…" }`. */
  record?: { module: string; id: string };
}

/** Revision bookkeeping — how a markup survives a slip-sheet. */
export interface RevisionContext {
  /** Sheet revision the markup was authored against. */
  rev?: string;
  /** Revision it was carried forward from, set when a slip-sheet migrates it. */
  carriedFrom?: string;
  /** Migration state after a compare: `ok` geometry still matches, `shifted` was relocated,
   *  `orphan` needs a human to re-place it, `obsolete` the referenced content is gone. */
  migration?: "ok" | "shifted" | "orphan" | "obsolete";
  /** Who accepted the migration, and when. */
  migratedBy?: string;
  migratedAt?: string;
}

/** Presentation. Deliberately small: colour/width/opacity and nothing that encodes meaning. */
export interface AnnotStyle {
  color?: string;                 // stroke, `#rrggbb`
  fill?: string;                  // fill, `#rrggbb` (opacity from `fillOpacity`)
  width?: number;                 // stroke width in page units
  opacity?: number;               // 0..1, stroke + text
  fillOpacity?: number;           // 0..1
  dash?: number[];                // page-unit dash pattern
  fontSize?: number;              // page units
  fontWeight?: number;
  /** Arrowheads for line/arrow/callout: `[start, end]`. */
  heads?: [boolean, boolean];
}

/** The record. */
export interface Annotation {
  // --- identity ------------------------------------------------------------
  id: string;
  kind: AnnotKind;
  /** Document-scoped sheet key. For a plain PDF this is the document id; for a plan set it is the
   *  sheet number, so markups follow the sheet across re-issues of the container file. */
  sheetId: string;
  /** 1-based page within the document. */
  page: number;

  // --- geometry (page space) ----------------------------------------------
  /** Path/anchor points. Point kinds carry exactly one. */
  points: Pt[];
  /** Rotation of the markup itself, degrees clockwise. Text and stamps mostly. */
  rotation?: number;
  /** Page-normalised anchor (0..1) derived from `points[0]` — the shared coordinate space that lets
   *  a non-PDF renderer place this markup without knowing the page box. Maintained by the store. */
  nx?: number;
  ny?: number;

  // --- authorship ----------------------------------------------------------
  author: string;
  org?: string;
  createdAt: string;              // ISO 8601
  updatedAt?: string;
  /** Bumped on every mutation — the optimistic-concurrency token for sync. */
  version: number;

  // --- classification ------------------------------------------------------
  subject?: string;               // short title, shows in the markup list
  note?: string;                  // body text of the comment
  /** Rendered text for `text` / `stamp` / `callout`. Distinct from `note`: this is *on the sheet*. */
  text?: string;
  status: AnnotStatus;
  priority?: AnnotPriority;
  discipline?: Discipline;
  trade?: string;                 // e.g. "09 Finishes", free-text or CSI division
  labels?: string[];
  /** Set by the host when the markup must not be edited (issued for construction, signed off). */
  locked?: boolean;

  // --- payload -------------------------------------------------------------
  quantity?: Quantity;
  style?: AnnotStyle;
  replies?: AnnotReply[];
  attachments?: AnnotAttachment[];
  links?: AnnotLinks;
  revision?: RevisionContext;
  provenance?: Provenance;
  /** Escape hatch for host-specific fields. Round-trips through every adapter untouched. */
  ext?: Record<string, unknown>;
}

/**
 * What a tool hands the store: geometry and a kind are required, everything else optional. The
 * store fills identity, authorship, timestamps and the derived `nx`/`ny` anchor.
 */
export type AnnotationDraft = Partial<Annotation> & Pick<Annotation, "kind" | "points" | "page">;

/** Per-page (or per-sheet) scale calibration. */
export interface Calibration {
  /** Real-world units per PDF point. Area scales by the square of this. */
  unitsPerPoint: number;
  /** Display unit for lengths (`m`, `ft`, `mm`, `in`). Areas render as `unit²`. */
  unit: string;
  /** Human label for the drawing scale, e.g. `1/8" = 1'-0"` or `1:100`. */
  label?: string;
  /** How it was set — a named preset is trustworthy, a hand-drawn line less so. */
  source: "preset" | "measured" | "imported" | "declared";
  /** Which page it applies to; `0` means "the document default". */
  page: number;
}

/** Sheet metadata — extracted from a title block, a plan register, or typed by a user. */
export interface SheetMeta {
  sheetId: string;
  page: number;
  number?: string;                // "A-201"
  title?: string;                 // "SECOND FLOOR PLAN"
  discipline?: Discipline;
  kind?: SheetKind;
  revision?: string;
  issueDate?: string;
  scaleLabel?: string;
  package?: string;               // bid package / document set
  provenance?: Provenance;
}

/** A saved viewer state a user can return to or share. */
export interface SavedView {
  id: string;
  name: string;
  page: number;
  zoom: number;
  /** Centre of the view in page space. */
  center: Pt;
  rotation: number;
  createdAt: string;
  author?: string;
  /** Markup filter active when the view was saved. */
  filter?: AnnotFilter;
}

/** The filter the markup list, the overlay and every export share. */
export interface AnnotFilter {
  kinds?: AnnotKind[];
  status?: AnnotStatus[];
  discipline?: Discipline[];
  authors?: string[];
  labels?: string[];
  pages?: number[];
  /** Substring match over subject / note / text / author. */
  query?: string;
  /** ISO timestamps. */
  since?: string;
  until?: string;
  /** Only markups linked to an issue (`true`) or only unlinked (`false`). */
  hasIssue?: boolean;
}

/** Colour presets by discipline — the redline convention, not decoration. */
export const DISCIPLINE_COLORS: Record<Discipline, string> = {
  general: "#e2554a",
  architectural: "#e2554a",
  structural: "#2f6fd0",
  civil: "#8a6d3b",
  mechanical: "#1f9e8f",
  electrical: "#d8a200",
  plumbing: "#1b7fc4",
  fire: "#c62828",
  landscape: "#4a9e3f",
  interiors: "#a24bd0",
  survey: "#5c6670",
  preservation: "#7a5230",
};

/** Status colours for the list and the pin badges. */
export const STATUS_COLORS: Record<AnnotStatus, string> = {
  open: "#e2554a",
  in_review: "#d8a200",
  accepted: "#33d17a",
  rejected: "#8a1f1f",
  resolved: "#2f9e5f",
  void: "#5c6670",
  info: "#4a8cff",
};
