/**
 * R31-CITE-HIGHLIGHT — the locator must find a passage the two PDF text extractors disagree about,
 * and must REFUSE rather than guess when it cannot.
 *
 * THE FIXTURE CARRIES THE PUNCTUATION IT CLAIMS TO TEST. The first version of this file described
 * curly quotes, em dashes and soft hyphens in its header and then used a plain-ASCII source string,
 * so it was structurally unable to see the defect it was written for: normalisation was applied to
 * the NEEDLE only, while `findInWords` searched the raw page words, which meant folding a curly
 * apostrophe in the query could only ever LOSE a match. A test whose fixture lacks the input class
 * it names is not a weak test, it is a different test.
 *
 * The page words are spelled as **pdf.js** yields them (one visual line as several positioned runs,
 * punctuation preserved); the citation snippets are spelled as **pypdf** produced them inside
 * `doc_text` — including its plain-prefix truncation, which damages the TAIL and never the head.
 */
import { describe, expect, it } from "vitest";
import { candidates, documentWords, locatePassage, normalisePassage, paintCiteBox, viewerWords, type PageWords } from "./citeLocate";
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

const SOURCE = "All structural steel shall be erected as required by the Engineer’s written instruction — including the anchor­bolt survey “as built” — prior to placement of any concrete topping";

const SRC: PageWords = { words: async () => page(SOURCE) };

describe("normalisePassage", () => {
  it("folds the punctuation the two extractors disagree about", () => {
    expect(normalisePassage("Engineer’s")).toBe("engineer's");
    expect(normalisePassage("“as built”")).toBe('"as built"');
    expect(normalisePassage("anchor­bolt")).toBe("anchorbolt");
    expect(normalisePassage("a — b")).toBe("a - b");
  });

  it("collapses whitespace, so a line split into runs still compares equal", () => {
    expect(normalisePassage("erected   as" + String.fromCharCode(10) + " required")).toBe("erected as required");
  });
});

describe("candidates - the fallback ladder", () => {
  it("is ordered strongest first", () => {
    expect(candidates(SOURCE).map((x) => x.rung)).toEqual(["exact", "trimmed", "phrase"]);
  });

  it("refuses a passage too short to be a location", () => {
    expect(candidates("the")).toEqual([]);
    expect(candidates("")).toEqual([]);
  });

  it("trims the TAIL and samples the HEAD, because truncation damages only the tail", () => {
    const c = candidates(SOURCE);
    const norm = normalisePassage(SOURCE);
    const trimmed = c.find((x) => x.rung === "trimmed")!.needle;
    const phrase = c.find((x) => x.rung === "phrase")!.needle;
    expect(norm.startsWith(trimmed), "trimmed must keep the head").toBe(true);
    expect(norm.endsWith(trimmed), "trimmed must drop the tail").toBe(false);
    expect(norm.startsWith(phrase), "the phrase must come from the head").toBe(true);
  });

  it("never offers the same needle at two rungs", () => {
    const n = candidates(SOURCE).map((c) => c.needle);
    expect(new Set(n).size).toBe(n.length);
  });
});

describe("locatePassage", () => {
  it("finds a passage quoted verbatim", async () => {
    const hit = await locatePassage(SRC, 1, "erected as required by the");
    expect(hit?.rung).toBe("exact");
    expect(hit!.box.w).toBeGreaterThan(0);
  });

  it("finds a passage whose CURLY APOSTROPHE the page also has", async () => {
    // The defect this fixture exists for: normalising the needle only meant folding the query's
    // apostrophe while the page kept its own, so a byte-identical passage could not match.
    const hit = await locatePassage(SRC, 1, "the Engineer’s written instruction");
    expect(hit, "a curly apostrophe must not cost a match").not.toBeNull();
  });

  it("finds a passage containing an EM DASH and a SOFT HYPHEN", async () => {
    const hit = await locatePassage(SRC, 1, "instruction — including the anchor­bolt survey");
    expect(hit, "em dash + soft hyphen must not cost a match").not.toBeNull();
  });

  it("finds a passage across a NON-BREAKING SPACE", async () => {
    const hit = await locatePassage(SRC, 1, "“as built” — prior to placement");
    expect(hit, "an nbsp must not cost a match").not.toBeNull();
  });

  it("matches a query typed with PLAIN punctuation against a curly page", async () => {
    // The other direction, and the one a human hits: straight quote in, curly on the page.
    const hit = await locatePassage(SRC, 1, "the Engineer's written instruction");
    expect(hit, "plain-typed punctuation must reach curly page text").not.toBeNull();
  });

  it("degrades to a shorter rung when the TAIL is truncated mid-word", async () => {
    const cut = normalisePassage(SOURCE).slice(0, 46);       // plain prefix, ends mid-word
    const hit = await locatePassage(SRC, 1, cut);
    expect(hit, "a prefix-truncated snippet must still locate").not.toBeNull();
  });

  it("REFUSES rather than guesses when the passage is absent", async () => {
    expect(await locatePassage(SRC, 1, "no such text appears anywhere on this page")).toBeNull();
  });

  it("returns null for a scanned page with no text layer, and does not throw", async () => {
    expect(await locatePassage({ words: async () => [] }, 1, SOURCE)).toBeNull();
  });

  it("treats an unreadable page as a miss, never an exception", async () => {
    const broken: PageWords = { words: async () => { throw new Error("page failed to render"); } };
    await expect(locatePassage(broken, 9, SOURCE)).resolves.toBeNull();
  });

  it("flags a repeated passage as AMBIGUOUS instead of silently boxing the first", async () => {
    const twice: PageWords = { words: async () => page("alpha bravo charlie alpha bravo charlie") };
    const hit = await locatePassage(twice, 1, "alpha bravo charlie");
    expect(hit).not.toBeNull();
    expect(hit!.ambiguous, "two occurrences must be reported, not hidden").toBe(true);
  });

  it("does not flag a single occurrence as ambiguous", async () => {
    const hit = await locatePassage(SRC, 1, "concrete topping");
    expect(hit!.ambiguous).toBe(false);
  });

  it("the box covers the matched words, not the whole page", async () => {
    const whole = await locatePassage(SRC, 1, SOURCE);
    const part = await locatePassage(SRC, 1, "concrete topping");
    expect(part!.box.w).toBeLessThan(whole!.box.w);
  });
});

describe("viewerWords - the cache is per-DOCUMENT", () => {
  function fakeViewer() {
    return {
      calls: 0,
      async pageText(): Promise<never> {
        this.calls++;
        return [{ str: "alpha beta gamma", transform: [1, 0, 0, 1, 0, 0], width: 10, height: 10 }] as never;
      },
    };
  }

  it("caches within one document", async () => {
    const v = fakeViewer();
    const src = viewerWords(v);
    await src.words(1); await src.words(1);
    expect(v.calls, "a second read of the same page should be cached").toBe(1);
  });

  it("drops the cache when the document id changes", async () => {
    // Page numbers are not identities. Without this, page 3 of a newly loaded PDF is served from
    // the previous one — a box drawn confidently over the wrong file.
    const v = fakeViewer();
    let doc = "doc-A";
    const src = viewerWords(v, () => doc);
    await src.words(3);
    doc = "doc-B";
    await src.words(3);
    expect(v.calls, "a new document must not be answered from the old cache").toBe(2);
  });

  it("clear() forces a re-read for a caller with no document id", async () => {
    const v = fakeViewer();
    const src = viewerWords(v);
    await src.words(1);
    src.clear();
    await src.words(1);
    expect(v.calls).toBe(2);
  });
});

describe("documentWords + paintCiteBox — the PageWords bridge", () => {
  it("reads PdfDocument.textItems through the same cache as viewerWords", async () => {
    let n = 0;
    const doc = {
      async textItems(): Promise<{ str: string; x: number; y: number; w: number; h: number }[]> {
        n++;
        return [{ str: "erected as required by the engineer", x: 10, y: 20, w: 200, h: 12 }];
      },
    };
    const src = documentWords(doc);
    await src.words(1);
    await src.words(1);
    expect(n).toBe(1);
  });

  it("paints a scaled rect and marks an ambiguous hit", () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const r = paintCiteBox(svg, { x: 10, y: 20, w: 40, h: 8 }, 2, true);
    expect(r.getAttribute("data-cite-highlight")).toBe("ambiguous");
    expect(r.getAttribute("x")).toBe("20");
    expect(r.getAttribute("y")).toBe("40");
    expect(r.getAttribute("width")).toBe("80");
    expect(r.getAttribute("stroke-dasharray")).toBe("5 4");
    expect(svg.querySelector("[data-cite-highlight]")).toBe(r);
  });
});
