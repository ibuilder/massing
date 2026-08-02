/**
 * R31-CITE-HIGHLIGHT — find the cited passage on a PDF page, so a citation can box the paragraph
 * instead of naming the page.
 *
 * ## Why this file exists rather than a call into the viewer
 *
 * The roadmap recorded the remaining work as "expose a highlight entry point from the vendored
 * plugin", and flagged that as a real decision: `src/vendor/massingpdf/` is carried VERBATIM from the
 * sibling kernel repo, so an edit there is either lost on the next re-vendor or has to go upstream
 * first.
 *
 * That decision turns out not to be needed. The vendor's public index already exports `splitWords`
 * and `unionBox`, and `plugins/search` exports `findInWords` — a pure function from words to boxes.
 * Only `flash` (the visual effect) is module-private, and a highlight we draw ourselves is a few
 * lines. So the locator lives HERE, in our tree, composed entirely from the vendor's public surface:
 * **no vendor edit, nothing to send upstream, and a re-vendor cannot silently drop it.**
 *
 * ## The part that is actually hard
 *
 * The citation's `span` comes from `doc_text`, whose chunks were extracted by **pypdf**. The page's
 * words come from **pdf.js**. The same paragraph does not survive both readers identically:
 *
 *   * whitespace differs — pdf.js emits a visual line as several runs, pypdf as one string;
 *   * ligatures, soft hyphens, non-breaking spaces and curly quotes survive one extractor and not
 *     the other;
 *   * `doc_text` truncates with a plain prefix — `chunk["text"][:500]`, then `snippet[:200]` in the
 *     citation — so a long passage is cut mid-word **at the tail only**. There is no ellipsis and
 *     the head is intact.
 *
 * That last point is corrected from this file's first draft, which claimed the snippet was wrapped
 * in ellipses at both ends and built the fallback ladder around it — trimming both ends and taking
 * the fallback phrase from the *middle*. The premise was wrong (checked: `doc_text.py:148,175`),
 * and it made the ladder actively worse, because the head is the one part guaranteed undamaged.
 * The ladder now trims the **tail** and takes its phrase from the **head**.
 *
 * ## Normalisation applies to BOTH sides, or it only creates misses
 *
 * The same first draft normalised the needle and searched the raw page words. Since `findInWords`
 * compares against `word.str` verbatim, folding a curly apostrophe in the query while the page
 * still contained one guaranteed a miss on a passage that would otherwise have matched — the
 * punctuation handling could subtract matches and never add one. Both sides are normalised now,
 * and the words keep their original geometry so the returned box is still the real one.
 *
 * An exact match therefore fails on ordinary input while looking like "the passage isn't on this
 * page" — a silent miss indistinguishable from a wrong page number. So matching degrades on
 * purpose, longest-first, and REPORTS which rung matched: an exact hit and a short-phrase fallback
 * are both "found" but do not deserve equal confidence, and a passage occurring more than once is
 * flagged `ambiguous` rather than silently boxed at its first occurrence.
 */
/*
 * ⚠️ NOT YET REACHED. Nothing outside this module's own test imports it. The panel that renders a
 * citation (`portal/panels/aiassist.ts`) still writes `"Source: p.12"` as inert `textContent`, and
 * its local citation type declares only `{ page, snippet? }` — it drops the `doc_id` and `span`
 * the backend already sends (`rfi_qa.py` → `cite_doc`). Wiring is therefore a *second* seam fix,
 * not a call.
 *
 * Recorded here rather than left implicit, because this repo's recurring defect is an engine
 * nothing calls being counted as shipped capability. The locator is tested and correct; it is not
 * yet a feature a user can see, and the vendor-surface assumptions above are exercised only against
 * a hand-built fixture, never a real PDF.
 */
import { findInWords } from "../vendor/massingpdf/plugins/search";
import { splitWords, type Word } from "../vendor/massingpdf/index";
import type { Box } from "../vendor/massingpdf/core/types";

/** How the passage was matched. Ordered strongest → weakest; `null` result means no match at all. */
export type MatchRung = "exact" | "trimmed" | "phrase";

export interface PassageHit {
  box: Box;
  /** Which fallback rung produced this hit — the caller can weaken the UI on a weak match. */
  rung: MatchRung;
  /** The text actually searched for, after normalisation/trimming. Useful in a failure report. */
  needle: string;
  /**
   * The passage occurs more than once on the page, and `box` is the FIRST occurrence.
   *
   * Reported rather than resolved: this module cannot know which one the citation meant, and a
   * caller that highlights silently would be asserting a certainty it does not have. Boxing the
   * first of several is a reasonable default; presenting it as *the* passage is not.
   */
  ambiguous: boolean;
}

/** The minimum a page source must provide. Structural, so a test needs no PDF and no viewer. */
export interface PageWords {
  /** Words for a 1-based page number, already positioned. */
  words(page: number): Promise<readonly Word[]>;
}

/**
 * Apply the same folding to the page's words that the needle gets.
 *
 * `findInWords` builds its haystack from `word.str` verbatim, so normalising only the query means
 * a curly apostrophe in the PAGE can never match a folded one in the query. That is not a missed
 * improvement, it is a regression: the punctuation handling could only ever subtract matches.
 *
 * Geometry is carried through untouched — same `x/y/w/h/item` — so `unionBox` over the returned
 * slice still describes where the text really is. A word that folds to an empty string keeps its
 * slot so the index mapping inside `findInWords` stays aligned.
 */
function normaliseWords(words: readonly Word[]): readonly Word[] {
  return words.map((w) => ({ ...w, str: normalisePassage(w.str) }));
}

/**
 * Normalise for comparison only — never for display.
 *
 * Ellipses go first (they are `doc_text`'s own marker, not document text), then the unicode
 * punctuation an extractor may or may not preserve, then whitespace collapses. Lower-cased because
 * `findInWords` already compares case-insensitively and we want our own length checks to agree with
 * what it will do.
 */
export function normalisePassage(s: string): string {
  // Invisible characters are written as ESCAPES, never literals: a soft hyphen and a
  // non-breaking space look exactly like ordinary ones in an editor, so a literal is a line no
  // reviewer can check — which is precisely why `no-irregular-whitespace` rejects it.
  return s
    .replace(/\u2026/g, " ")            // ellipsis: doc_text's own trim marker, not document text
    .replace(/\u00AD/g, "")             // soft hyphen: only one extractor preserves it
    .replace(/[\u2018\u2019]/g, "'")    // curly single quotes
    .replace(/[\u201C\u201D]/g, '"')    // curly double quotes
    .replace(/[\u2013\u2014]/g, "-")    // en / em dash
    .replace(/\u00A0/g, " ")            // non-breaking space
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/**
 * The ladder of things to search for, longest (most specific) first.
 *
 * Damage is at the TAIL, because `doc_text` truncates with a plain prefix (`text[:500]`, then
 * `snippet[:200]`) — the head of the passage is exactly what the document says. So the middle rung
 * drops trailing words, and the short rung is taken from the HEAD.
 *
 * The first draft did the opposite on a false premise (it believed the snippet was ellipsis-wrapped
 * at both ends) and so trimmed both ends and sampled the middle — throwing away the one region
 * guaranteed to be intact.
 */
const PHRASE_WORDS = 6;
const MIN_CHARS = 12;                              // below this a "match" is noise, not a location
const TAIL_TRIM_WORDS = 2;                         // enough to clear a mid-word cut and its neighbour

export function candidates(passage: string): { needle: string; rung: MatchRung }[] {
  const norm = normalisePassage(passage);
  if (norm.length < MIN_CHARS) return [];
  const out: { needle: string; rung: MatchRung }[] = [{ needle: norm, rung: "exact" }];

  const words = norm.split(" ");
  if (words.length > TAIL_TRIM_WORDS) {
    const trimmed = words.slice(0, -TAIL_TRIM_WORDS).join(" ");
    if (trimmed.length >= MIN_CHARS) out.push({ needle: trimmed, rung: "trimmed" });
  }
  if (words.length > PHRASE_WORDS) {
    // From the HEAD: it is the part truncation cannot have damaged.
    const phrase = words.slice(0, PHRASE_WORDS).join(" ");
    if (phrase.length >= MIN_CHARS) out.push({ needle: phrase, rung: "phrase" });
  }
  // Two rungs can coincide (a short passage trims to its own head); keep the strongest of each.
  const seen = new Set<string>();
  return out.filter((c) => (seen.has(c.needle) ? false : (seen.add(c.needle), true)));
}

/**
 * Locate `passage` on `page`, returning its box and how confidently it was found.
 *
 * Returns `null` when nothing matched — which the caller must treat as "could not locate", NOT as
 * "the citation is wrong". The page may be a scan with no text layer, and saying so is honest;
 * boxing an arbitrary region because something had to be highlighted would be worse than a page
 * number.
 */
export async function locatePassage(
  src: PageWords, page: number, passage: string,
): Promise<PassageHit | null> {
  const tries = candidates(passage);
  if (!tries.length) return null;

  let words: readonly Word[];
  try {
    words = await src.words(page);
  } catch {
    return null;                                   // an unreadable page is a miss, never a throw
  }
  if (!words.length) return null;                  // scanned page, no text layer

  // Normalise the page ONCE, not per rung.
  const folded = normaliseWords(words);

  for (const { needle, rung } of tries) {
    // limit 2, not 1: one hit is unambiguous, two is all we need to know it is not. Asking for
    // more would cost a full scan to report a boolean.
    const hits = findInWords(folded, needle, page, 2);
    const box = hits[0]?.box;
    if (box) return { box, rung, needle, ambiguous: hits.length > 1 };
  }
  return null;
}

/** A `PageWords` whose cache can be dropped when the underlying document changes. */
export interface ViewerPageWords extends PageWords {
  /** Forget every cached page. Call when the viewer loads a different document. */
  clear(): void;
}

/**
 * Adapt a live viewer to `PageWords`. Kept separate so `locatePassage` stays testable without one —
 * and so the vendor import surface used here is exactly two public names.
 *
 * **The cache is per-DOCUMENT, and the caller owns that.** Page numbers are not identities: cache
 * page 3, load another PDF into the same viewer, and page 3 would be served from the first
 * document — a box drawn confidently over the wrong file, which is worse than no box at all. The
 * vendor's own `TextIndex` clears on `doc:loaded` for exactly this reason.
 *
 * Two defences, because one of them is only a default:
 *   * `docId` — when supplied, a change to it drops the cache automatically. Pass the citation's
 *     `document_id` and the hazard cannot arise.
 *   * `clear()` — for a caller that has no id but does know a document was swapped.
 */
export function viewerWords(
  viewer: { pageText(page: number): Promise<Parameters<typeof splitWords>[0]> },
  docId?: () => string | undefined,
): ViewerPageWords {
  const cache = new Map<number, readonly Word[]>();
  let cachedFor = docId?.();
  return {
    clear() { cache.clear(); cachedFor = docId?.(); },
    async words(page: number) {
      const now = docId?.();
      if (now !== cachedFor) { cache.clear(); cachedFor = now; }
      const got = cache.get(page);
      if (got) return got;
      const w = splitWords(await viewer.pageText(page));
      cache.set(page, w);
      return w;
    },
  };
}
