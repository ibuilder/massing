import { describe, expect, it, vi } from "vitest";

import type { DocCitation } from "../../api/client";
import { citationEl, openCitedSource } from "./citationControl";

const cite = (over: Partial<DocCitation> = {}): DocCitation => ({
  page: 12,
  snippet: "erected as required by the",
  doc: "spec.pdf",
  doc_id: "spec",
  openable: true,
  ...over,
});

describe("citationEl", () => {
  it("is a button only when the server says the source is openable", () => {
    const on = citationEl({} as never, "p1", cite());
    expect(on.querySelector("button")?.textContent).toContain("p.12");
    const off = citationEl({} as never, "p1", cite({ openable: false }));
    expect(off.querySelector("button")).toBeNull();
    expect(off.textContent).toContain("p.12");
  });

  it("writes the snippet with textContent, never innerHTML", () => {
    const el = citationEl({} as never, "p1", cite({ snippet: "<b>x</b>" }));
    expect(el.innerHTML).not.toContain("<b>x</b>");
    expect(el.textContent).toContain("<b>x</b>");
  });
});

describe("openCitedSource", () => {
  it("opens the in-app viewer with the page and snippet, not a blob tab", async () => {
    const openPdf = vi.fn().mockResolvedValue(undefined);
    const api = { doctextSource: vi.fn().mockResolvedValue(new Blob(["%PDF"], { type: "application/pdf" })) };
    await openCitedSource(api as never, "p1", cite(), openPdf);
    expect(api.doctextSource).toHaveBeenCalledWith("p1", "spec");
    expect(openPdf).toHaveBeenCalledTimes(1);
    const [file, opts] = openPdf.mock.calls[0] as [File, { cite: { page: number; snippet?: string; docId?: string } }];
    expect(file).toBeInstanceOf(File);
    expect(opts.cite).toEqual({ page: 12, snippet: "erected as required by the", docId: "spec" });
  });
});
