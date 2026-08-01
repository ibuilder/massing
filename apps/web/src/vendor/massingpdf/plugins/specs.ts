/**
 * The specifications workspace.
 *
 * Most drawing viewers treat specs as an attachment — a PDF you can open, scroll, and not much
 * else. But field coordination lives in the specs: a note on a drawing saying "firestop per spec"
 * is only actionable if you can get to 07 84 00 and read what it actually requires.
 *
 * This parses a CSI-formatted spec book into addressable sections and clauses, so a markup can cite
 * `07 84 00 §3.1.A` as a *link* rather than as a string somebody typed, and so the submittal
 * requirements buried in Part 1 can be pulled out into a checklist.
 */
import { definePlugin } from "../core/plugin";
import { activate, refreshRovingTabstops, rovingFocus } from "../core/a11y";
import { splitWords, unionBox, type Word } from "../core/textLayer";
import type { Box } from "../core/types";
import type { Viewer } from "../core/viewer";

/** One clause within a section — the citable unit. */
export interface SpecClause {
  /** Dotted reference within the section, e.g. `3.1.A`. */
  ref: string;
  /** Nesting depth: PART = 0, article = 1, paragraph = 2, subparagraph = 3. */
  depth: number;
  text: string;
  page: number;
  box: Box;
}

export interface SpecSection {
  /** Normalised CSI number, spaced: `07 84 00`. */
  number: string;
  title: string;
  page: number;
  /** Division number derived from the section, e.g. `07`. */
  division: string;
  clauses: SpecClause[];
}

/** A requirement extracted from a section — the thing somebody has to actually do. */
export interface SpecRequirement {
  section: string;
  clause: string;
  kind: "submittal" | "quality" | "warranty" | "closeout" | "other";
  text: string;
  page: number;
}

export interface SpecsOptions {
  /** Supply sections from the host instead of parsing — a project with a spec register should win. */
  sections?: (viewer: Viewer) => Promise<SpecSection[]>;
  /** Skip scanning the drawings for callouts naming a section. */
  scanReferences?: boolean;
  side?: "left" | "right";
  /** Skip parsing entirely (this document is a drawing set, not a spec book). */
  parse?: boolean;
}

// `SECTION 07 84 00 — FIRESTOPPING`, `07 84 00 FIRESTOPPING`, `078400 FIRESTOPPING`
const SECTION_HEADING = /^(?:SECTION\s+)?(\d{2})\s?(\d{2})\s?(\d{2}(?:\.\d{2})?)\s*[-–—:]?\s*(.{0,80})$/i;
// `PART 1 - GENERAL`
const PART_HEADING = /^PART\s+(\d)\s*[-–—:]?\s*(.{0,60})$/i;
// `1.1`, `2.03` — an article
const ARTICLE = /^(\d{1,2})\.(\d{1,2})\s+(.{0,120})$/;
// `A.`, `B.` — a paragraph
const PARAGRAPH = /^([A-Z])\.\s+(.{0,200})$/;
// `1.`, `2.` — a subparagraph
const SUBPARAGRAPH = /^(\d{1,2})\.\s+(.{0,200})$/;

/**
 * Spec language is inflected — "Qualifications", "complying", "certified" — so these match on word
 * *stems* with a trailing `\w*` rather than on whole words. A `\b`-terminated stem like `\bqualif\b`
 * matches nothing at all, which is the sort of bug that silently empties a checklist.
 */
const REQUIREMENT_PATTERNS: [RegExp, SpecRequirement["kind"]][] = [
  [/\b(?:submit\w*|shop\s+drawings?|product\s+data|samples?|mock-?ups?)\b/i, "submittal"],
  [/\b(?:test\w*|inspect\w*|certif\w*|qualif\w*|compl(?:y|ies|ying|iance|iant)\w*|conform\w*)\b/i, "quality"],
  [/\b(?:warrant\w*|guarantee\w*)\b/i, "warranty"],
  [/\b(?:closeout|record\s+documents?|as-?builts?|o&m|operation\s+and\s+maintenance|training)\b/i, "closeout"],
];

/**
 * Group a page's words into lines, so headings can be matched against whole lines rather than
 * against the arbitrary text runs pdf.js reports.
 */
async function pageLines(viewer: Viewer, page: number): Promise<{ text: string; box: Box }[]> {
  // Through the kernel, so a scanned spec book served by OCR parses the same way.
  const words = splitWords(await viewer.pageText(page));
  if (!words.length) return [];
  const sorted = [...words].sort((a, b) => a.y - b.y || a.x - b.x);
  const lines: { words: typeof words; y: number }[] = [];
  for (const w of sorted) {
    const last = lines[lines.length - 1];
    // Same line when the vertical centres are within half a line height.
    if (last && Math.abs(w.y + w.h / 2 - (last.y)) < w.h * 0.6) {
      last.words.push(w);
      last.y = (last.y * (last.words.length - 1) + (w.y + w.h / 2)) / last.words.length;
    } else {
      lines.push({ words: [w], y: w.y + w.h / 2 });
    }
  }
  return lines.map((l) => ({
    text: l.words.sort((a, b) => a.x - b.x).map((w) => w.str).join(" ").replace(/\s+/g, " ").trim(),
    box: unionBox(l.words),
  }));
}

/** A line of a spec book, with where it sits. The unit `parseSpecLines` works in. */
export interface SpecLine { text: string; box: Box; page: number }

/**
 * Parse spec lines into sections and clauses.
 *
 * Deliberately heuristic and forgiving: spec formatting varies enough between offices that anything
 * stricter would fail on half of real projects. A section with no recognisable clauses is still
 * returned — being able to jump to `07 84 00` is most of the value even without clause anchors.
 *
 * Kept free of pdf.js so the heuristics can be exercised directly against sample text.
 */
export function parseSpecLines(lines: readonly SpecLine[]): SpecSection[] {
  const sections: SpecSection[] = [];
  let current: SpecSection | null = null;
  let article = "";

  for (const line of lines) {
    const { text, page } = line;
    if (!text || text.length > 220) continue;

    const sec = SECTION_HEADING.exec(text);
    // Guard against matching a stray dimension string: a real section heading has a title.
    if (sec && sec[4] && /[A-Za-z]{3}/.test(sec[4])) {
      const number = `${sec[1]} ${sec[2]} ${sec[3]}`;
      current = {
        number,
        title: sec[4].trim().replace(/\.+$/, ""),
        page,
        division: sec[1]!,
        clauses: [],
      };
      sections.push(current);
      article = "";
      continue;
    }
    if (!current) continue;

    const partM = PART_HEADING.exec(text);
    if (partM) {
      // Scoped here deliberately: an article's ref already carries its part number (`3.1`), so
      // nothing downstream needs to remember which PART we are inside.
      const part = partM[1]!;
      article = "";
      current.clauses.push({ ref: `PART ${part}`, depth: 0, text: partM[2]?.trim() || `PART ${part}`, page, box: line.box });
      continue;
    }

    const art = ARTICLE.exec(text);
    if (art) {
      article = `${art[1]}.${art[2]}`;
      current.clauses.push({ ref: article, depth: 1, text: art[3]!.trim(), page, box: line.box });
      continue;
    }

    const para = PARAGRAPH.exec(text);
    if (para && article) {
      current.clauses.push({ ref: `${article}.${para[1]}`, depth: 2, text: para[2]!.trim(), page, box: line.box });
      continue;
    }

    const sub = SUBPARAGRAPH.exec(text);
    if (sub && article) {
      // A subparagraph belongs to the paragraph above it, so its ref extends that one.
      const parent = current.clauses.filter((c) => c.depth === 2).pop();
      if (parent) {
        current.clauses.push({ ref: `${parent.ref}.${sub[1]}`, depth: 3, text: sub[2]!.trim(), page, box: line.box });
      }
    }
  }
  return sections;
}

/** Read a spec book out of the open document and parse it. */
export async function parseSpecs(
  viewer: Viewer,
  onProgress?: (page: number, total: number) => void,
): Promise<SpecSection[]> {
  const lines: SpecLine[] = [];
  for (let page = 1; page <= viewer.numPages; page++) {
    onProgress?.(page, viewer.numPages);
    for (const line of await pageLines(viewer, page).catch(() => [])) {
      lines.push({ ...line, page });
    }
  }
  return parseSpecLines(lines);
}

/** A mention of a spec section found on a drawing sheet. */
export interface SpecReference {
  /** Normalised section number, matching a parsed `SpecSection.number`. */
  section: string;
  page: number;
  box: Box;
  /** The text as it appears on the sheet, e.g. `SEE SPEC 07 84 00`. */
  text: string;
}

/**
 * `07 84 00`, `07 8400`, `078400`.
 *
 * The word boundaries at both ends are load-bearing: without them this matches the first six
 * digits of any longer number, so a dimension string or a phone number in a title block would
 * read as a spec reference.
 */
const SECTION_MENTION = /\b(\d{2})[\s-]?(\d{2})[\s-]?(\d{2})\b/g;

/**
 * Find mentions of known spec sections in a page's words.
 *
 * Matched against the *parsed section list* rather than against the pattern alone: on a drawing,
 * six digits in a row is far more often a dimension, a door number or a date than a section
 * reference, and only cross-checking against sections that actually exist keeps the noise down.
 */
export function findSpecReferences(
  words: readonly Word[],
  sections: readonly SpecSection[],
  page: number,
): SpecReference[] {
  if (!words.length || !sections.length) return [];
  const known = new Set(sections.map((s) => s.number));

  // Join into a character stream with an owner map, so a section number split across words
  // ("07", "84", "00") is still found.
  let hay = "";
  const owner: number[] = [];
  words.forEach((w, i) => {
    if (hay) { hay += " "; owner.push(i); }
    for (let c = 0; c < w.str.length; c++) owner.push(i);
    hay += w.str;
  });

  const out: SpecReference[] = [];
  const seen = new Set<string>();
  SECTION_MENTION.lastIndex = 0;
  for (let m = SECTION_MENTION.exec(hay); m; m = SECTION_MENTION.exec(hay)) {
    const number = `${m[1]} ${m[2]} ${m[3]}`;
    if (!known.has(number)) continue;
    const key = `${number}@${m.index}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const first = owner[m.index] ?? 0;
    const last = owner[Math.min(m.index + m[0].length - 1, owner.length - 1)] ?? first;
    out.push({
      section: number,
      page,
      box: unionBox(words.slice(first, last + 1)),
      text: hay.slice(Math.max(0, m.index - 24), m.index + m[0].length + 12).trim(),
    });
  }
  return out;
}

/** Scan every page of the open document for mentions of the parsed sections. */
export async function scanSpecReferences(
  viewer: Viewer,
  sections: readonly SpecSection[],
): Promise<SpecReference[]> {
  const out: SpecReference[] = [];
  // Skip the pages the sections were parsed *from* — a spec book mentions its own number on every
  // page, and those are not drawing callouts.
  const specPages = new Set(sections.flatMap((s) => s.clauses.map((c) => c.page).concat(s.page)));
  for (let page = 1; page <= viewer.numPages; page++) {
    if (specPages.has(page)) continue;
    const words = splitWords(await viewer.pageText(page).catch(() => []));
    out.push(...findSpecReferences(words, sections, page));
  }
  return out;
}

/** Pull the actionable requirements out of parsed sections. */
export function extractRequirements(sections: readonly SpecSection[]): SpecRequirement[] {
  const out: SpecRequirement[] = [];
  for (const section of sections) {
    for (const clause of section.clauses) {
      // Headings aren't requirements; the text under them is.
      if (clause.depth < 2 || clause.text.length < 12) continue;
      const kind = REQUIREMENT_PATTERNS.find(([re]) => re.test(clause.text))?.[1];
      if (!kind) continue;
      out.push({ section: section.number, clause: clause.ref, kind, text: clause.text, page: clause.page });
    }
  }
  return out;
}

export function specsPlugin(options: SpecsOptions = {}) {
  return definePlugin({
    id: "specs",
    order: 45,
    setup(ctx) {
      let sections: SpecSection[] = [];
      let references: SpecReference[] = [];
      let parsed = false;
      let parsing = false;

      const load = async (v: Viewer): Promise<SpecSection[]> => {
        if (parsed || parsing) return sections;
        parsing = true;
        try {
          if (options.sections) {
            sections = await options.sections(v);
          } else if (options.parse !== false && v.doc) {
            v.bus.emit("notice", { level: "info", message: "Reading specification sections…" });
            sections = await parseSpecs(v);
          }
          parsed = true;
          // Once sections are known, look for callouts naming them on the drawing sheets.
          references = sections.length && options.scanReferences !== false
            ? await scanSpecReferences(v, sections).catch(() => [])
            : [];
          v.bus.emit("notice", {
            level: sections.length ? "success" : "info",
            message: sections.length
              ? `Found ${sections.length} specification section${sections.length === 1 ? "" : "s"}`
                + (references.length ? `, referenced ${references.length} time${references.length === 1 ? "" : "s"} on the drawings.` : ".")
              : "No CSI specification sections found in this document.",
          });
        } catch (e) {
          v.bus.emit("notice", { level: "error", message: `Spec parse failed: ${(e as Error).message}` });
        } finally {
          parsing = false;
        }
        return sections;
      };

      ctx.bus.on("doc:loaded", () => { sections = []; references = []; parsed = false; });

      ctx.registerPanel({
        id: "specs", title: "Specifications", side: options.side ?? "left", order: 40,
        mount: (host, v) => mountSpecs(host, v, () => sections, () => references, () => load(v)),
      });

      /**
       * Cite the section a nearby drawing callout names. This is the pay-off for scanning
       * references: a markup dropped next to "SEE SPEC 07 84 00" can cite it without anyone typing
       * a section number.
       */
      ctx.registerAction({
        id: "specs.citeNearest", label: "Cite the spec called out here", icon: "🔗", group: "review",
        enabled: (v) => v.store.selectedIds().length > 0,
        async run(v) {
          await load(v);
          const selected = v.store.selected();
          let linked = 0;
          for (const a of selected) {
            const anchor = a.points[0];
            if (!anchor) continue;
            const onPage = references.filter((r) => r.page === a.page);
            if (!onPage.length) continue;
            // Nearest by centre-to-centre distance; a callout more than a third of the page away
            // is not what this markup is about.
            const info = v.doc?.pageInfoSync(a.page);
            const limit = info ? Math.max(info.width, info.height) / 3 : Infinity;
            let best: SpecReference | null = null;
            let bestD = limit;
            for (const r of onPage) {
              const d = Math.hypot(r.box.x + r.box.w / 2 - anchor.x, r.box.y + r.box.h / 2 - anchor.y);
              if (d < bestD) { bestD = d; best = r; }
            }
            if (!best) continue;
            v.store.update(a.id, { links: { ...a.links, spec: { section: best.section } } });
            linked++;
          }
          v.bus.emit("notice", {
            level: linked ? "success" : "warn",
            message: linked
              ? `Cited the nearest spec callout on ${linked} markup${linked === 1 ? "" : "s"}.`
              : "No spec callout found near the selection on this sheet.",
          });
        },
      });

      ctx.registerAction({
        id: "specs.parse", label: "Read specification sections", icon: "§", group: "view",
        run: (v) => load(v).then(() => v.redraw()),
      });

      ctx.viewer.specs = {
        sections: () => sections,
        references: () => references,
        load: () => load(ctx.viewer),
        requirements: () => extractRequirements(sections),
        /** Cite a clause on a markup — the link that makes a spec reference navigable. */
        cite(annotId: string, section: string, clause?: string) {
          const a = ctx.store.get(annotId);
          if (!a) return false;
          ctx.store.update(annotId, {
            links: { ...a.links, spec: { section, ...(clause ? { clause } : {}) } },
          });
          return true;
        },
      };
    },
  });
}

function mountSpecs(
  host: HTMLElement,
  v: Viewer,
  get: () => SpecSection[],
  getRefs: () => SpecReference[],
  load: () => Promise<SpecSection[]>,
): () => void {
  const search = document.createElement("input");
  search.type = "search";
  search.className = "mpdf-input";
  search.placeholder = "Section number, title or keyword…";

  const tabs = document.createElement("div");
  tabs.className = "mpdf-chip-group";
  let mode: "sections" | "requirements" = "sections";
  const tabBtns: Record<string, HTMLButtonElement> = {};
  for (const [key, label] of [["sections", "Sections"], ["requirements", "Requirements"]] as const) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mpdf-chip" + (key === mode ? " is-on" : "");
    b.textContent = label;
    b.onclick = () => {
      mode = key;
      for (const k in tabBtns) tabBtns[k]!.classList.toggle("is-on", k === mode);
      render();
    };
    tabBtns[key] = b;
    tabs.appendChild(b);
  }

  const body = document.createElement("div");
  body.setAttribute("aria-label", "Specification sections");
  body.className = "mpdf-list mpdf-spec-list";
  host.append(search, tabs, body);

  const empty = (msg: string, withButton = false) => {
    body.innerHTML = "";
    queueMicrotask(() => refreshRovingTabstops(body, '[role="button"]'));
    const p = document.createElement("p");
    p.className = "mpdf-empty";
    p.textContent = msg;
    body.appendChild(p);
    if (withButton) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "mpdf-chest-tool";
      b.textContent = "Read specification sections";
      b.onclick = async () => { b.disabled = true; b.textContent = "Reading…"; await load(); render(); };
      body.appendChild(b);
    }
  };

  const render = () => {
    const sections = get();
    if (!sections.length) {
      empty("No sections read yet. Specs are parsed on demand — a 900-page book is not something to index before anyone asks.", true);
      return;
    }
    const q = search.value.trim().toLowerCase();
    body.innerHTML = "";
    queueMicrotask(() => refreshRovingTabstops(body, '[role="button"]'));

    if (mode === "requirements") {
      const reqs = extractRequirements(sections)
        .filter((r) => !q || `${r.section} ${r.clause} ${r.text}`.toLowerCase().includes(q));
      if (!reqs.length) { empty(q ? "No matching requirements." : "No requirements extracted."); return; }
      for (const r of reqs.slice(0, 400)) {
        const row = document.createElement("article");
        row.className = "mpdf-row";
        const badge = document.createElement("span");
        badge.className = "mpdf-hit-source";
        badge.dataset.source = r.kind;
        badge.textContent = r.kind;
        const main = document.createElement("div");
        main.className = "mpdf-row-main";
        const title = document.createElement("div");
        title.className = "mpdf-row-title";
        title.textContent = r.text;
        const meta = document.createElement("div");
        meta.className = "mpdf-row-meta";
        meta.textContent = `${r.section} §${r.clause} · p.${r.page}`;
        main.append(title, meta);
        row.append(badge, main);
        activate(row, () => void v.goToPage(r.page), {
          // Includes the row's own text: `aria-label` overrides content rather than adding to it,
          // so a bare "Go to page 12" would suppress the reference and read identically for every
          // row on that page.
          label: `${r.text} — ${r.section} clause ${r.clause}, page ${r.page}`,
          roving: true,
        });
        body.appendChild(row);
      }
      return;
    }

    const matching = sections.filter((s) =>
      !q || `${s.number} ${s.title}`.toLowerCase().includes(q)
      || s.clauses.some((c) => c.text.toLowerCase().includes(q)));
    if (!matching.length) { empty("No matching sections."); return; }

    for (const section of matching) {
      const details = document.createElement("details");
      details.className = "mpdf-spec-section";
      // Auto-open when the search matched inside the section rather than in its heading.
      if (q && !`${section.number} ${section.title}`.toLowerCase().includes(q)) details.open = true;

      const summary = document.createElement("summary");
      summary.className = "mpdf-spec-heading";
      const num = document.createElement("strong");
      num.textContent = section.number;
      const ttl = document.createElement("span");
      ttl.textContent = section.title;
      summary.append(num, ttl);
      // Where this section is called out on the drawings — the cross-link the spec asks for.
      const refs = getRefs().filter((r) => r.section === section.number);
      if (refs.length) {
        const where = document.createElement("em");
        where.className = "mpdf-spec-refs";
        const sheets = [...new Set(refs.map((r) => v.store.sheet(r.page)?.number ?? `p.${r.page}`))];
        where.textContent = `on ${sheets.slice(0, 3).join(", ")}${sheets.length > 3 ? "…" : ""}`;
        where.title = "Referenced on these sheets — click to jump";
        where.onclick = (e) => { e.stopPropagation(); void v.goToPage(refs[0]!.page); };
        summary.appendChild(where);
      }
      summary.onclick = (e) => {
        // Let the disclosure toggle, but also navigate to the section.
        if ((e.target as HTMLElement).tagName !== "SUMMARY") return;
        void v.goToPage(section.page);
      };
      details.appendChild(summary);

      for (const clause of section.clauses) {
        if (q && !clause.text.toLowerCase().includes(q) && !`${section.number} ${section.title}`.toLowerCase().includes(q)) continue;
        const row = document.createElement("div");
        row.className = "mpdf-spec-clause";
        row.dataset.depth = String(clause.depth);
        const ref = document.createElement("span");
        ref.className = "mpdf-spec-ref";
        ref.textContent = clause.ref;
        const txt = document.createElement("span");
        txt.textContent = clause.text;
        row.append(ref, txt);
        activate(row, () => void v.goToPage(clause.page), {
          // The clause text is the whole point of this panel; labelling the row "Go to page 12"
          // would hide it from exactly the people who cannot read it off the screen.
          label: `${clause.ref} ${clause.text}, page ${clause.page}`,
          roving: true,
        });

        // Cite: attach this clause to whatever markup is selected.
        const cite = document.createElement("button");
        cite.type = "button";
        cite.className = "mpdf-icon-btn";
        cite.textContent = "🔗";
        cite.title = "Cite this clause on the selected markup";
        cite.onclick = (e) => {
          e.stopPropagation();
          const selected = v.store.selectedIds();
          if (!selected.length) {
            v.bus.emit("notice", { level: "warn", message: "Select a markup first, then cite a clause." });
            return;
          }
          for (const id of selected) v.specs?.cite(id, section.number, clause.ref);
          v.bus.emit("notice", {
            level: "success",
            message: `Cited ${section.number} §${clause.ref} on ${selected.length} markup${selected.length === 1 ? "" : "s"}.`,
          });
        };
        row.appendChild(cite);
        details.appendChild(row);
      }
      body.appendChild(details);
    }
  };

  search.oninput = render;
  const offs = [v.on("doc:loaded", render), v.on("annot:selected", () => { /* cite button state is read live */ })];
  render();
  const stopRoving = rovingFocus(body, '[role="button"]');
  return () => { offs.forEach((off) => off()); stopRoving(); };
}

declare module "../core/viewer" {
  interface Viewer {
    /** Present once the specs plugin is installed. */
    specs?: {
      sections(): SpecSection[];
      references(): SpecReference[];
      load(): Promise<SpecSection[]>;
      requirements(): SpecRequirement[];
      cite(annotId: string, section: string, clause?: string): boolean;
    };
  }
}
