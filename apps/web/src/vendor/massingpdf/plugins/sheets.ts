/**
 * Sheet intelligence: thumbnails, the sheet register, and title-block extraction.
 *
 * A 400-page plan set navigated by page number is unusable; a superintendent looks for "A-201", not
 * "page 137". This reads the title block region of each page's text layer to recover the sheet
 * number, title and discipline, so the register is populated automatically for CAD/BIM-exported
 * sets and typed by hand only for scans.
 */
import { definePlugin } from "../core/plugin";
import { activate, refreshRovingTabstops, rovingFocus } from "../core/a11y";
import type { Discipline, SheetKind, SheetMeta } from "../core/types";
import type { Viewer } from "../core/viewer";
import type { TextItem } from "../core/document";

export interface SheetsOptions {
  /**
   * Supply the register from the host instead of extracting it — a project that already knows its
   * drawing list should not have it guessed.
   */
  register?: (viewer: Viewer) => Promise<SheetMeta[]>;
  /** Skip title-block extraction (scanned sets have no text layer; it would just be empty). */
  extract?: boolean;
  /** Thumbnail width in CSS px. */
  thumbWidth?: number;
}

/** Discipline from the leading letter(s) of a sheet number — the US National CAD Standard order. */
const DISCIPLINE_BY_PREFIX: Record<string, Discipline> = {
  G: "general", A: "architectural", S: "structural", C: "civil", L: "landscape",
  I: "interiors", M: "mechanical", E: "electrical", P: "plumbing", F: "fire",
  V: "survey", H: "preservation", T: "general", Q: "general",
};

/** Sheet kind from words in the title — good enough to drive tool presets and filters. */
const KIND_PATTERNS: [RegExp, SheetKind][] = [
  [/\bREFLECTED\s+CEILING\b|\bRCP\b/i, "ceiling_plan"],
  [/\bSITE\s+PLAN\b|\bCIVIL\s+PLAN\b/i, "site_plan"],
  [/\bELEVATION/i, "elevation"],
  [/\bSECTION/i, "section"],
  [/\bDETAIL/i, "detail"],
  [/\bSCHEDULE/i, "schedule"],
  [/\bSPECIFICATION|\bSPEC\b/i, "spec"],
  [/\bSHOP\s+DRAWING/i, "shop_drawing"],
  [/\bPLAN\b/i, "plan"],
];

/** `A-201`, `A201`, `A2.01`, `S-1.1`, `M-101A`. */
const SHEET_NUMBER = /^([A-Z]{1,2})[-\s.]?(\d{1,3}(?:\.\d{1,2})?[A-Z]?)$/;

export function sheetsPlugin(options: SheetsOptions = {}) {
  return definePlugin({
    id: "sheets",
    order: 15,
    setup(ctx) {
      const { viewer } = ctx;

      ctx.bus.on("doc:loaded", () => { void populate(viewer, options); });

      ctx.registerPanel({
        id: "sheet-index", title: "Sheets", side: "left", order: 10,
        mount: (host, v) => mountIndex(host, v, options),
      });

      ctx.registerAction({
        id: "sheets.rescan", label: "Re-read title blocks", icon: "⟲", group: "view",
        run: (v) => populate(v, { ...options, extract: true }),
      });
    },
  });
}

/** Fill the store's sheet register, from the host if it supplies one, otherwise by extraction. */
async function populate(v: Viewer, options: SheetsOptions): Promise<void> {
  const doc = v.doc;
  if (!doc) return;
  if (options.register) {
    try {
      for (const meta of await options.register(v)) v.store.setSheet(meta);
      return;
    } catch (e) {
      v.bus.emit("notice", { level: "warn", message: `Drawing register unavailable: ${(e as Error).message}` });
    }
  }
  if (options.extract === false) return;
  for (let p = 1; p <= doc.numPages; p++) {
    const meta = await extractSheetMeta(v, p).catch(() => null);
    if (meta) v.store.setSheet(meta);
  }
}

/**
 * Read a page's title block. Title blocks live in the right-hand strip or the bottom band; the
 * sheet number is the largest text in that region matching a sheet-number pattern, and the title is
 * the largest text near it that isn't the number.
 */
export async function extractSheetMeta(viewer: Viewer, page: number): Promise<SheetMeta | null> {
  const info = await viewer.doc!.pageInfo(page);
  // Through the kernel, so OCR output on a scanned sheet fills the register too.
  const items = await viewer.pageText(page);
  if (!items.length) return { sheetId: String(page), page };

  // The title-block strip: right 22% or bottom 18% — the two conventional placements.
  const inBlock = (t: TextItem) => t.x > info.width * 0.78 || t.y > info.height * 0.82;
  const block = items.filter(inBlock);
  const pool = block.length > 3 ? block : items;

  let number: string | undefined;
  let numberItem: TextItem | undefined;
  for (const t of [...pool].sort((a, b) => b.h - a.h)) {
    const cleaned = t.str.trim().toUpperCase();
    if (SHEET_NUMBER.test(cleaned)) { number = cleaned; numberItem = t; break; }
  }

  const candidates = pool
    .filter((t) => t !== numberItem && t.str.trim().length > 3 && /[A-Za-z]/.test(t.str))
    .sort((a, b) => b.h - a.h);
  // Prefer an all-caps line near the number — the drawing title, by convention.
  const near = numberItem
    ? candidates.find((t) => Math.abs(t.y - numberItem.y) < numberItem.h * 6 && t.str === t.str.toUpperCase())
    : undefined;
  const title = (near ?? candidates[0])?.str.trim();

  const prefix = number?.match(/^([A-Z]{1,2})/)?.[1]?.[0];
  const discipline = prefix ? DISCIPLINE_BY_PREFIX[prefix] : undefined;
  const kind = title ? KIND_PATTERNS.find(([re]) => re.test(title))?.[1] : undefined;
  // Imperial scales may carry a whole number before the fraction (`1 1/2" = 1'-0"`); without the
  // optional leading group that reads as `1/2"` — a wrong scale, which is worse than none.
  const scaleLabel = pool.map((t) => t.str).join(" ")
    .match(/\b(?:\d+\s+)?\d+\/\d+"\s*=\s*\d+'-?\d*"?|\b\d+"\s*=\s*\d+'-?\d*"?|\b1\s*:\s*\d+\b/)?.[0];

  return {
    sheetId: number ?? String(page),
    page,
    ...(number ? { number } : {}),
    ...(title ? { title } : {}),
    ...(discipline ? { discipline } : {}),
    ...(kind ? { kind } : {}),
    ...(scaleLabel ? { scaleLabel } : {}),
  };
}

/** The sheet index: a thumbnail strip that reads as a drawing register. */
function mountIndex(host: HTMLElement, v: Viewer, options: SheetsOptions): () => void {
  const width = options.thumbWidth ?? 132;
  const search = document.createElement("input");
  search.type = "search";
  search.className = "mpdf-input";
  search.placeholder = "Sheet number or title…";
  const list = document.createElement("div");
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", "Sheets");
  list.className = "mpdf-sheet-list";
  host.append(search, list);

  const cards = new Map<number, HTMLElement>();
  const observer = typeof IntersectionObserver !== "undefined"
    ? new IntersectionObserver((entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          observer!.unobserve(e.target);
          void paintThumb(e.target as HTMLElement, v, width);
        }
      }, { root: list, rootMargin: "200px" })
    : null;

  const render = () => {
    const q = search.value.trim().toLowerCase();
    list.innerHTML = "";
    cards.clear();
    for (let p = 1; p <= v.numPages; p++) {
      const meta = v.store.sheet(p);
      const label = meta?.number ?? `Page ${p}`;
      const title = meta?.title ?? "";
      if (q && !`${label} ${title}`.toLowerCase().includes(q)) continue;

      const card = document.createElement("button");
      card.type = "button";
      card.className = "mpdf-sheet-card";
      card.dataset.page = String(p);
      if (p === v.page) card.classList.add("is-current");

      const thumb = document.createElement("div");
      thumb.className = "mpdf-sheet-thumb";
      thumb.style.width = `${width}px`;
      const cap = document.createElement("div");
      cap.className = "mpdf-sheet-cap";
      const num = document.createElement("strong");
      num.textContent = label;
      const ttl = document.createElement("span");
      ttl.textContent = title;
      cap.append(num, ttl);
      if (meta?.discipline) {
        const tag = document.createElement("em");
        tag.className = "mpdf-sheet-tag";
        tag.textContent = meta.discipline;
        cap.appendChild(tag);
      }
      // Count of markups on the page — the "where is the work" cue when scanning a set.
      const n = v.store.onPage(p).length;
      if (n) {
        const badge = document.createElement("span");
        badge.className = "mpdf-sheet-badge";
        badge.textContent = String(n);
        card.appendChild(badge);
      }
      card.append(thumb, cap);
      activate(card, () => void v.goToPage(p), {
        role: "option",
        current: v.page === p,
        label: `Sheet ${meta?.number ?? p}${meta?.title ? `, ${meta.title}` : ""}, page ${p}`,
        roving: true,
      });
      list.appendChild(card);
      cards.set(p, thumb);
      observer?.observe(thumb);
      if (!observer) void paintThumb(thumb, v, width);
    }
    refreshRovingTabstops(list, '[role="option"]');
  };

  search.oninput = render;
  const offs = [
    v.on("doc:loaded", render), v.on("sheet:changed", render),
    v.on("annot:added", render), v.on("annot:removed", render),
    v.on("page:changed", ({ page }) => {
      for (const card of list.querySelectorAll(".mpdf-sheet-card")) {
        card.classList.toggle("is-current", Number((card as HTMLElement).dataset.page) === page);
      }
    }),
  ];
  render();
  const stopRoving = rovingFocus(list, '[role="option"]');
  return () => { offs.forEach((off) => off()); stopRoving(); observer?.disconnect(); };
}

/** Rasterise a small preview into a thumbnail slot, once it scrolls into view. */
async function paintThumb(host: HTMLElement, v: Viewer, width: number): Promise<void> {
  const page = Number((host.parentElement as HTMLElement | null)?.dataset.page);
  const doc = v.doc;
  if (!doc || !page) return;
  try {
    const info = await doc.pageInfo(page);
    const scale = width / info.width;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(info.width * scale);
    canvas.height = Math.round(info.height * scale);
    host.style.height = `${canvas.height}px`;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const pg = await doc.page(page);
    await pg.render({ canvas, canvasContext: ctx, viewport: pg.getViewport({ scale }) }).promise;
    host.innerHTML = "";
    host.appendChild(canvas);
  } catch {
    // A thumbnail that fails to paint is cosmetic; the card still navigates.
  }
}
