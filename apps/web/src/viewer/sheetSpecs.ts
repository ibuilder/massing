/**
 * R36 print slice 3 — build a sheet URL from what the viewer is currently showing.
 *
 * ── WHY THIS IS A MODULE AND NOT THREE INLINE `URLSearchParams` ──────────────────────────────────
 * It already was three inline builders in `app.ts`, and all three sent parameters the route does not
 * accept. Measured against the running API on 2026-08-09:
 *
 *     GET …/drawings/sheet.svg?number=A-999&title=TEST     ->  a sheet numbered **A-101**
 *
 * `sheet.svg|pdf|dxf` take `sheet`, `page`, `purpose`, `rev`, `storey`, `views`. The rail was sending
 * `number`, `title` and `scale`; FastAPI drops unknown query parameters, so all three vanished. The
 * bug was invisible because the rail's `number=A-101` happened to equal the route's default — the
 * label said A-101, the sheet said A-101, and the per-storey title the code carefully computed
 * (`LEVEL 2 PLAN`) never reached the paper. Same shape as the `api.publish` body that 422'd from the
 * day it was written: a caller speaking a dialect the callee does not.
 *
 * There is no `title` field in the titleblock at all — it carries project / sheet / purpose /
 * revision / date / drawn_by — so the per-storey description belongs in `purpose`, which is a real
 * field, rather than in an invented one.
 *
 * The defence is not "be careful": `sheetUrl` can only emit keys in `SHEET_PARAMS`, and a test
 * asserts that set against the route's own signature. A parameter that goes nowhere cannot be sent.
 */

/** Exactly the query parameters `sheet.svg` / `sheet.pdf` / `sheet.dxf` declare. */
export const SHEET_PARAMS = ["sheet", "page", "purpose", "rev", "storey", "views"] as const;
export type SheetParam = (typeof SHEET_PARAMS)[number];

/** A view the user can place. Mirrors `drawings.VIEW_KINDS` — the server refuses anything else. */
export type ViewKind = "plan" | "section" | "elevation" | "axon";

export type ViewSpec =
  | { kind: "plan"; elevation?: number }
  | { kind: "section"; axis: "x" | "y"; offset: number }
  | { kind: "elevation"; direction: "north" | "south" | "east" | "west" }
  | { kind: "axon"; azimuth?: number; elevationAngle?: number };

/**
 * Encode view specs into the compact `views=` grammar the route parses.
 *
 * Mirrors `drawings.parse_views` deliberately and minimally: this writes the string, the server
 * parses it, and `sheetSpecs.test.ts` round-trips every kind against the documented grammar. A
 * second, richer client-side model would be a second source of truth for what a view is — the exact
 * split that let `compose()` and `compose_viewports()` disagree about `axon` for five weeks.
 */
export function encodeViews(specs: ViewSpec[]): string {
  return specs.map((s) => {
    switch (s.kind) {
      case "plan":
        return s.elevation === undefined ? "plan" : `plan@${s.elevation}`;
      case "section":
        return `section:${s.axis}@${s.offset}`;
      case "elevation":
        return `elevation:${s.direction}`;
      case "axon":
        return s.azimuth === undefined || s.elevationAngle === undefined
          ? "axon"
          : `axon@${s.azimuth}x${s.elevationAngle}`;
    }
  }).join(",");
}

/** Same keys as `drawings.PAGES`, same order. `sheetSpecs.test.ts` asserts both sides. */
export const PAGE_KEYS = [
  "ARCH-C", "ARCH-D", "ARCH-B", "ARCH-A", "A0", "A1", "A2", "A3", "A4",
] as const;
export type SheetPage = (typeof PAGE_KEYS)[number];

const PAGE_SET = new Set<string>(PAGE_KEYS);

export function isSheetPage(v: string): v is SheetPage {
  return PAGE_SET.has(v);
}

/**
 * Construction paper, as the picker shows it.
 *
 * 24×18 in is **ARCH C**, not an ISO A size (A2 is 16.5×23.4 in). ARCH D is the usual US full-size
 * CD sheet (36×24). Half-size of D is ARCH B (18×12, 50% linear). The next ARCH step down is ARCH A
 * (12×9), commonly called quarter-size of D — it is half of C, not a uniform 25% of 24×36.
 * 11×17 (ANSI B) is a copier size, not half of 24×36, and is not in this list.
 */
export const PAGE_CATALOG: readonly { key: SheetPage; label: string }[] = [
  { key: "ARCH-C", label: "ARCH C · 24×18 in (issue)" },
  { key: "ARCH-D", label: "ARCH D · 36×24 in (full size)" },
  { key: "ARCH-B", label: "ARCH B · 18×12 in (half of D)" },
  { key: "ARCH-A", label: "ARCH A · 12×9 in (quarter of D)" },
  { key: "A0", label: "ISO A0 · 1189×841 mm (site)" },
  { key: "A1", label: "ISO A1 · 841×594 mm (issue)" },
  { key: "A2", label: "ISO A2 · 594×420 mm" },
  { key: "A3", label: "ISO A3 · 420×297 mm (check print)" },
  { key: "A4", label: "ISO A4 · 297×210 mm" },
];

/** Operator default: 24×18 in. Omitting `page` on the API still composes A3. */
export const DEFAULT_SHEET_PAGE: SheetPage = "ARCH-C";
export const SHEET_PAGE_STORAGE_KEY = "aec:sheetPage";

export function readSheetPage(): SheetPage {
  try {
    const v = localStorage.getItem(SHEET_PAGE_STORAGE_KEY);
    if (v && isSheetPage(v)) return v;
  } catch { /* private mode / node without storage */ }
  return DEFAULT_SHEET_PAGE;
}

export function writeSheetPage(page: SheetPage): void {
  try { localStorage.setItem(SHEET_PAGE_STORAGE_KEY, page); }
  catch { /* ignore quota / private mode */ }
}

export type SheetOptions = {
  /** The sheet NUMBER, e.g. "A-101". The route calls this `sheet`; the rail used to call it `number`. */
  sheet?: string;
  page?: SheetPage;
  /** Titleblock purpose line — where a per-level description belongs, since there is no title field. */
  purpose?: string;
  rev?: string;
  /** Restrict the automatic key-plan to one named level. Ignored when `views` is given. */
  storey?: string | null;
  /** Explicit viewports. When present the server composes these instead of choosing for you. */
  views?: ViewSpec[];
};

/**
 * The query string for a sheet request — containing only parameters the route accepts.
 *
 * Empty and nullish values are dropped rather than sent blank: `purpose=` would overwrite a
 * meaningful default with nothing, and "sent an empty string" is not the same request as "did not
 * mention it".
 */
export function sheetQuery(o: SheetOptions): URLSearchParams {
  const q = new URLSearchParams();
  const put = (k: SheetParam, v: string | null | undefined) => {
    if (v !== null && v !== undefined && v !== "") q.set(k, v);
  };
  put("sheet", o.sheet);
  put("page", o.page);
  put("purpose", o.purpose);
  put("rev", o.rev);
  // `views` wins over `storey`: naming the viewports explicitly and ALSO asking the server to pick a
  // level is a contradiction, and the server would silently honour only one. Say one thing.
  if (o.views && o.views.length) put("views", encodeViews(o.views));
  else put("storey", o.storey);
  return q;
}

/** `…/drawings/sheet.<fmt>?<query>` — the path a caller opens. */
export function sheetPath(pid: string, fmt: "svg" | "pdf" | "dxf", o: SheetOptions): string {
  const q = sheetQuery(o).toString();
  return `/projects/${pid}/drawings/sheet.${fmt}${q ? `?${q}` : ""}`;
}

/**
 * What "place what I am looking at" means, per canvas mode.
 *
 * 2D shows a level, so it places that level's plan. 3D has no single correct answer — a perspective
 * camera and a parallel projection are not the same view — so it places a true isometric rather than
 * pretending to match the camera. Matching the live camera is a real future ask and a genuinely
 * harder question; it is deliberately not guessed at here.
 */
export function viewsForCanvas(mode: "2d" | "3d", storeyElevation: number | null): ViewSpec[] {
  if (mode === "3d") return [{ kind: "axon" }];
  return [storeyElevation === null ? { kind: "plan" } : { kind: "plan", elevation: storeyElevation }];
}

/**
 * The rail's sheet options for the level currently being worked in.
 *
 * `page` is the picker's value (default **ARCH-C** / 24×18 in). Omitting it used to fall through
 * to `compose()`'s **A3** while the buttons said A-101 and the hover said ARCH-D. Unknown sizes
 * are refused on the server; they are never substituted.
 */
export function railSheetOptions(storey: string | null, views?: ViewSpec[]): SheetOptions {
  return {
    sheet: "A-101",
    page: readSheetPage(),
    storey,
    views,
    purpose: storey ? `${storey.toUpperCase()} PLAN` : "FLOOR PLAN",
  };
}
