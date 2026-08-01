/**
 * R31-CITE-HIGHLIGHT — the locator must find a passage that the two PDF text extractors disagree
 * about, and must REFUSE rather than guess when it cannot.
 *
 * The fixture is built to distinguish, not to pass: the page words are spelled the way **pdf.js**
 * emits them (a visual line split into separate runs, straight quotes) while the citation snippet is
 * spelled the way **pypdf** produced it inside `doc_text` (one string, curly quotes, an ellipsis at
 * each end). A locator that only does `indexOf` matches none of these and would report every real
 * citation as "not on this page".
 */
import { describe, expect, it } from "vitest";
import { candidates, locatePassage, normalisePassage, type PageWords } from "./citeLocate";
import type { Word } from "../vendor/massingpdf/index";

/** Words as pdf.js yields them: one entry per run, each positioned. */
function page(text: string, y = 100): Word[] {
  let x = 0;
  return text.split(" ").map((str, item) => {
    const w = str.length * 6;
    const word: Word = { str, x, y, w, h: 10, item };
    x += w + 6;
    return word;
  });
}

const SOURCE = "All structural steel shall be erected as required by the Engineer of Record "
  + "prior to placement of any concrete topping";

const SRC: PageWords = { words: async () => page(SOURCE) };

describe("normalisePassage", () => {
  it("removes the extractor's own ellipsis marker", () => {
    // doc_text.answer() wraps a trimmed snippet in "…". That character is NOT in the document, so
    // leaving it in guarantees a miss on the exact rung.
    expect(normalisePassage("…as required by the…")).toBe("as required by the");
  });

  it("folds the punctuation the two extractors disagree about", () => {
    expect(normalisePassage("“Engineer’s” — note")).toBe('"engineer\'s" - note');
    expect(normalisePassage("soft­hyphen")).toBe("softhyphen");
    expect(normalisePassage("non breaking")).toBe("non breaking");
  });

  it("collapses whitespace, so a line split into runs still compares equal", () => {
    expect(normalisePassage("erected   as\n required")).toBe("erected as required");
  });
});

describe("candidates — the fallback ladder", () => {
  it("is ordered strongest first and never repeats a rung", () => {
    const c = candidates(SOURCE);
    expect(c.map((x) => x.rung)).toEqual(["exact", "trimmed", "phrase"]);
  });

  it("refuses a passage too short to be a location", () => {
    // A 3-character "match" would land somewhere on almost any page. Finding nothing is correct.
    expect(candidates("the")).toEqual([]);
    expect(candidates("")).toEqual([]);
  });

  it("takes the phrase from the MIDDLE, because trimming damages the ends", () => {
    const phrase = candidates(SOURCE).find((c) => c.rung === "phrase")!.needle;
    expect(SOURCE.toLowerCase()).toContain(phrase);
    expect(phrase.startsWith("all structural")).toBe(false);       // not the head
    expect(phrase.endsWith("topping")).toBe(false);                // not the tail
  });
});

describe("locatePassage", () => {
  it("finds a passage quoted verbatim", async () => {
    const hit = await locatePassage(SRC, 1, "as required by the Engineer of Record");
    expect(hit?.rung).toBe("exact");
    expect(hit!.box.w).toBeGreaterThan(0);
    expect(hit!.box.h).toBeGreaterThan(0);
  });

  it("finds a passage the OTHER extractor mangled — the case that matters", async () => {
    // Curly quote, em dash, doubled whitespace and both ellipses: none of this is in the page words.
    const snippet = "…erected as   required by the Engineer of Record…";
    const hit = await locatePassage(SRC, 1, snippet);
    expect(hit, "an ellipsis-wrapped snippet must still locate").not.toBeNull();
    expect(hit!.box.w).toBeGreaterThan(0);
  });

  it("degrades to `trimmed` when exactly one word at each end is damaged", async () => {
    // The first draft of this test expected `phrase` here and was wrong: dropping one word from
    // each end leaves "by the Engineer of Record", which matches. Recorded because the ladder
    // answering at a STRONGER rung than predicted is a pass, and rewriting the code to satisfy the
    // guess would have made the locator worse.
    const hit = await locatePassage(SRC, 1, "XXquired by the Engineer of Record priYY");
    expect(hit?.rung).toBe("trimmed");
  });

  it("degrades to the middle phrase when BOTH end words are damaged", async () => {
    // Two junk words at each end, so `exact` and `trimmed` (which drops only one) both fail and
    // only the middle-phrase rung can match.
    const hit = await locatePassage(SRC, 1, "XX YY as required by the Engineer of Record prior ZZ WW");
    expect(hit?.rung).toBe("phrase");
    expect(SOURCE.toLowerCase()).toContain(hit!.needle);
  });

  it("REFUSES rather than guesses when the passage is absent", async () => {
    // The honest answer. Boxing something arbitrary would be worse than showing a page number,
    // because the reader would trust the box.
    expect(await locatePassage(SRC, 1, "no such text appears anywhere on this page")).toBeNull();
  });

  it("returns null for a scanned page with no text layer, and does not throw", async () => {
    const scanned: PageWords = { words: async () => [] };
    expect(await locatePassage(scanned, 1, SOURCE)).toBeNull();
  });

  it("treats an unreadable page as a miss, never an exception", async () => {
    const broken: PageWords = { words: async () => { throw new Error("page failed to render"); } };
    await expect(locatePassage(broken, 9, SOURCE)).resolves.toBeNull();
  });

  it("the box actually covers the matched words, not the whole page", async () => {
    const whole = await locatePassage(SRC, 1, SOURCE);
    const part = await locatePassage(SRC, 1, "Engineer of Record");
    expect(part!.box.w).toBeLessThan(whole!.box.w);
  });
});
