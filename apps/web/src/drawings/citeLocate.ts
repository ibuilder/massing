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
 *   * `doc_text.answer()` trims context and prepends/appends an ellipsis ("…as required by the
 *     Engineer of Record…"), so the stored text is not even a substring of the source;
 *   * ligatures, soft hyphens and non-breaking spaces survive one extractor and not the other.
 *
 * An exact `indexOf` therefore fails on ordinary input while looking like "the passage isn't on this
 * page" — a silent miss that is indistinguishable from a wrong page number. So matching degrades on
 * purpose, longest-first, and REPORTS which rung matched: an exact hit and a three-word fallback are
 * both "found", but they do not deserve equal confidence and the caller may want to say so.
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
}

/** The minimum a page source must provide. Structural, so a test needs no PDF and no viewer. */
export interface PageWords {
  /** Words for a 1-based page number, already positioned. */
  words(page: number): Promise<readonly Word[]>;
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
 * The middle rung drops the first and last word, because an ellipsis-trimmed snippet very often
 * starts or ends mid-word ("…quired by the Engineer…"). The last rung takes the longest run of
 * `PHRASE_WORDS` words — long enough to be distinctive, short enough to survive re-flowing.
 */
const PHRASE_WORDS = 6;
const MIN_CHARS = 12;                              // below this a "match" is noise, not a location

export function candidates(passage: string): { needle: string; rung: MatchRung }[] {
  const norm = normalisePassage(passage);
  if (norm.length < MIN_CHARS) return [];
  const out: { needle: string; rung: MatchRung }[] = [{ needle: norm, rung: "exact" }];

  const words = norm.split(" ");
  if (words.length > 2) {
    const trimmed = words.slice(1, -1).join(" ");
    if (trimmed.length >= MIN_CHARS) out.push({ needle: trimmed, rung: "trimmed" });
  }
  if (words.length > PHRASE_WORDS) {
    // Take from the MIDDLE: the ends are where trimming damage lives.
    const start = Math.max(0, Math.floor((words.length - PHRASE_WORDS) / 2));
    const phrase = words.slice(start, start + PHRASE_WORDS).join(" ");
    if (phrase.length >= MIN_CHARS) out.push({ needle: phrase, rung: "phrase" });
  }
  return out;
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

  for (const { needle, rung } of tries) {
    const hits = findInWords(words, needle, page, 1);
    const box = hits[0]?.box;
    if (box) return { box, rung, needle };
  }
  return null;
}

/**
 * Adapt a live viewer to `PageWords`. Kept separate so `locatePassage` stays testable without one —
 * and so the vendor import surface used here is exactly two public names.
 */
export function viewerWords(viewer: { pageText(page: number): Promise<Parameters<typeof splitWords>[0]> }): PageWords {
  const cache = new Map<number, readonly Word[]>();
  return {
    async words(page: number) {
      const got = cache.get(page);
      if (got) return got;
      const w = splitWords(await viewer.pageText(page));
      cache.set(page, w);
      return w;
    },
  };
}
