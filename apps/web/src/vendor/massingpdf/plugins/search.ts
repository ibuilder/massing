/**
 * Document-wide search across sheet text, sheet metadata and markup content.
 *
 * The spec's requirement is a faceted, spatially-aware search: "all unresolved firestopping
 * comments on Level 4". That means searching three things at once and keeping them distinguishable
 * in the results — sheet text tells you where a keynote is, markup text tells you what someone said
 * about it, and the sheet register tells you which drawing you are on.
 */
import { definePlugin } from "../core/plugin";
import { activate, refreshRovingTabstops, rovingFocus } from "../core/a11y";
import { splitWords, unionBox, type Word } from "../core/textLayer";
import type { Box } from "../core/types";
import type { Viewer } from "../core/viewer";

export interface SearchOptions {
  side?: "left" | "right";
}

export type HitSource = "text" | "markup" | "sheet";

export interface SearchHit {
  source: HitSource;
  page: number;
  /** The matched text, with a little surrounding context. */
  snippet: string;
  /** Where on the page, when known. */
  box?: Box;
  /** For markup hits. */
  annotId?: string;
}

/** Per-page word index, built lazily. */
class TextIndex {
  private pages = new Map<number, Word[]>();

  constructor(private viewer: Viewer) {}

  clear(): void { this.pages.clear(); }

  async words(page: number): Promise<Word[]> {
    const hit = this.pages.get(page);
    if (hit) return hit;
    if (!this.viewer.doc) return [];
    // Via the kernel, so a scanned page served by OCR is searchable too.
    const words = splitWords(await this.viewer.pageText(page));
    this.pages.set(page, words);
    return words;
  }

  async find(page: number, query: string, limit: number): Promise<SearchHit[]> {
    return findInWords(await this.words(page), query, page, limit);
  }
}

/**
 * Find `query` among a page's words.
 *
 * Matching runs over the *joined* word stream rather than word-by-word, so a multi-word phrase
 * whose words came from different text items still matches — which is the normal case in a PDF,
 * where a single visual line is often several separate runs.
 */
export function findInWords(
  words: readonly Word[],
  query: string,
  page: number,
  limit = 25,
): SearchHit[] {
  if (!words.length || !query) return [];
  const q = query.toLowerCase();
  const out: SearchHit[] = [];

  // Build the haystack and remember which word each character came from.
  let hay = "";
  const owner: number[] = [];
  words.forEach((w, i) => {
    if (hay) { hay += " "; owner.push(i); }
    for (let c = 0; c < w.str.length; c++) owner.push(i);
    hay += w.str;
  });
  const lower = hay.toLowerCase();

  let from = 0;
  while (out.length < limit) {
    const at = lower.indexOf(q, from);
    if (at < 0) break;
    from = at + Math.max(1, q.length);
    const first = owner[at] ?? 0;
    const last = owner[Math.min(at + q.length - 1, owner.length - 1)] ?? first;
    out.push({
      source: "text",
      page,
      snippet: context(hay, at, q.length),
      box: unionBox(words.slice(first, last + 1)),
    });
  }
  return out;
}

/** ~30 characters either side, trimmed to word boundaries where convenient. */
function context(hay: string, at: number, len: number): string {
  const start = Math.max(0, at - 30);
  const end = Math.min(hay.length, at + len + 30);
  return `${start > 0 ? "…" : ""}${hay.slice(start, end).trim()}${end < hay.length ? "…" : ""}`;
}

export function searchPlugin(options: SearchOptions = {}) {
  return definePlugin({
    id: "search",
    order: 55,
    setup(ctx) {
      const index = new TextIndex(ctx.viewer);
      ctx.bus.on("doc:loaded", () => index.clear());

      ctx.registerPanel({
        id: "search",
        title: "Search",
        side: options.side ?? "left",
        order: 5,
        mount: (host, v) => mount(host, v, index),
      });

      ctx.registerAction({
        id: "search.focus", label: "Search", icon: "⌕", group: "view", shortcut: "/",
        run(v) {
          const input = v.el.root.querySelector<HTMLInputElement>(".mpdf-search-input");
          input?.focus();
          input?.select();
        },
      });
    },
  });
}

function mount(host: HTMLElement, v: Viewer, index: TextIndex): () => void {
  const input = document.createElement("input");
  input.type = "search";
  input.className = "mpdf-input mpdf-search-input";
  input.placeholder = "Search sheets and markups…";

  const scopeRow = document.createElement("div");
  scopeRow.className = "mpdf-chip-group";
  const scopes: Record<HitSource, boolean> = { text: true, markup: true, sheet: true };
  for (const [key, label] of [["text", "Sheet text"], ["markup", "Markups"], ["sheet", "Sheet index"]] as [HitSource, string][]) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mpdf-chip is-on";
    b.textContent = label;
    b.onclick = () => {
      scopes[key] = !scopes[key];
      b.classList.toggle("is-on", scopes[key]);
      void run();
    };
    scopeRow.appendChild(b);
  }

  const summary = document.createElement("div");
  summary.className = "mpdf-list-summary";
  const results = document.createElement("div");
  results.setAttribute("role", "listbox");
  results.setAttribute("aria-label", "Search results");
  results.className = "mpdf-list mpdf-search-results";
  host.append(input, scopeRow, summary, results);

  let token = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const run = async () => {
    const query = input.value.trim();
    // Each run gets a token; a slow page read from an abandoned query is discarded rather than
    // painting stale results over a newer search.
    const mine = ++token;
    results.innerHTML = "";
    if (query.length < 2) {
      summary.textContent = query ? "Type at least two characters." : "";
      return;
    }
    summary.textContent = "Searching…";
    const hits: SearchHit[] = [];

    if (scopes.markup) {
      const q = query.toLowerCase();
      for (const a of v.store.all()) {
        const body = [a.subject, a.note, a.text].filter(Boolean).join(" ");
        if (body.toLowerCase().includes(q)) {
          hits.push({ source: "markup", page: a.page, snippet: body.slice(0, 120), annotId: a.id });
        }
      }
    }

    if (scopes.sheet) {
      const q = query.toLowerCase();
      for (const meta of v.store.allSheets()) {
        const body = [meta.number, meta.title, meta.discipline].filter(Boolean).join(" — ");
        if (body.toLowerCase().includes(q)) hits.push({ source: "sheet", page: meta.page, snippet: body });
      }
    }

    if (scopes.text && v.doc) {
      // Start with the current page so the first results are the ones under the user's nose.
      const order = [v.page, ...range(1, v.numPages).filter((p) => p !== v.page)];
      for (const page of order) {
        if (mine !== token) return;
        const found = await index.find(page, query, 25);
        hits.push(...found);
        if (hits.length > 300) break;
        // Yield between pages so a long document doesn't lock the UI while indexing.
        if (page % 8 === 0) await new Promise((r) => setTimeout(r, 0));
      }
    }

    if (mine !== token) return;
    render(hits, query);
  };

  const render = (hits: SearchHit[], query: string) => {
    results.innerHTML = "";
    summary.textContent = hits.length
      ? `${hits.length} result${hits.length === 1 ? "" : "s"} for “${query}”`
      : `No results for “${query}”`;

    for (const hit of hits.slice(0, 300)) {
      const row = document.createElement("article");
      row.className = "mpdf-row mpdf-search-hit";

      const badge = document.createElement("span");
      badge.className = "mpdf-hit-source";
      badge.dataset.source = hit.source;
      badge.textContent = hit.source === "text" ? "sheet" : hit.source === "markup" ? "markup" : "index";

      const main = document.createElement("div");
      main.className = "mpdf-row-main";
      const title = document.createElement("div");
      title.className = "mpdf-row-title";
      title.append(...highlightMatch(hit.snippet, query));
      const meta = document.createElement("div");
      meta.className = "mpdf-row-meta";
      meta.textContent = v.store.sheet(hit.page)?.number ?? `Page ${hit.page}`;
      main.append(title, meta);

      row.append(badge, main);
      activate(row, () => {
        if (hit.annotId) {
          const a = v.store.get(hit.annotId);
          if (a) { v.store.select(a.id); void v.goToAnnotation(a, { zoom: false }); return; }
        }
        void v.goToPage(hit.page);
        if (hit.box) flash(v, hit.page, hit.box);
      }, { role: "option", label: `${hit.source} hit on page ${hit.page}: ${hit.snippet}`, roving: true });
      results.appendChild(row);
    }
    refreshRovingTabstops(results, '[role="option"]');
  };

  input.oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(() => void run(), 220);
  };
  input.onkeydown = (e) => { if (e.key === "Enter") { clearTimeout(timer); void run(); } };

  const offs = [v.on("doc:loaded", () => { results.innerHTML = ""; summary.textContent = ""; })];
  const stopRoving = rovingFocus(results, '[role="option"]');
  return () => { offs.forEach((off) => off()); stopRoving(); clearTimeout(timer); };
}

/** Split a snippet around the match so the hit is visible without innerHTML. */
function highlightMatch(snippet: string, query: string): (string | HTMLElement)[] {
  const at = snippet.toLowerCase().indexOf(query.toLowerCase());
  if (at < 0) return [snippet];
  const mark = document.createElement("mark");
  mark.className = "mpdf-hit-mark";
  mark.textContent = snippet.slice(at, at + query.length);
  return [snippet.slice(0, at), mark, snippet.slice(at + query.length)];
}

/**
 * Briefly outline a hit on the sheet. A transient DOM flourish rather than a markup — a search
 * result is not something anyone wants persisted or exported.
 */
function flash(v: Viewer, page: number, box: Box): void {
  const wrap = v.el.pages.querySelector<HTMLElement>(`.mpdf-page-wrap[data-page="${page}"]`);
  if (!wrap) return;
  const marker = document.createElement("div");
  marker.className = "mpdf-search-flash";
  marker.style.cssText =
    `position:absolute;left:${box.x * v.zoom}px;top:${box.y * v.zoom}px;` +
    `width:${box.w * v.zoom}px;height:${box.h * v.zoom}px;` +
    `z-index:4;pointer-events:none;`;
  wrap.appendChild(marker);
  setTimeout(() => marker.remove(), 2200);

  // Centre it, so a hit near the bottom of a large sheet isn't off screen.
  const s = v.el.scroll;
  s.scrollTop = wrap.offsetTop + box.y * v.zoom - s.clientHeight / 2;
  s.scrollLeft = wrap.offsetLeft + box.x * v.zoom - s.clientWidth / 2;
}

const range = (a: number, b: number): number[] =>
  Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => a + i);
