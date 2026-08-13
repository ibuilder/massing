import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The document-QA citation contract, asserted against the SERVER rather than against itself.
 *
 * **Fourth instance of the "response type narrower than the response" shape** in this codebase, and
 * the most expensive so far. `doc_text.answer()` has emitted seven keys per citation since v0.3.877
 * — `doc`, `doc_id`, `section`, `title`, `openable`, `page`, `snippet`. Both panels that render
 * citations declared their own inline `{ page, snippet }` and dropped the other five.
 *
 * What that cost is the point. `doc_id` and `openable` are exactly the two fields the "make the
 * citation a control" work needs, so with them dropped the feature looked *blocked on a backend
 * change that had already shipped*. A comment in `aiassist.ts` said so in as many words — "there is
 * nothing to open" — and the roadmap carried the item as blocked. The server had been sending the
 * answer the whole time. A narrow client type does not merely hide a field; it produces confident,
 * documented, wrong claims about what the system can do.
 *
 * So: read the Python that builds the payload, and require the shared `DocCitation` type to name
 * every key it emits. Asserting against a hand-written list would restate the client's belief, which
 * is the thing that was wrong.
 */
const repoRoot = resolve(__dirname, "../../../..");
const py = readFileSync(
  resolve(repoRoot, "services/api/src/aec_api/doc_text.py"), "utf8");
const ts = readFileSync(resolve(__dirname, "types.ts"), "utf8");

/** The dict literal inside `"citations": [...]` — the single source of the citation payload. */
function serverCitationKeys(): string[] {
  const inner = /"citations":\s*\[\{(.*?)\}\s*for\s/s.exec(py)?.[1];
  if (!inner) throw new Error("could not locate the citations list-comprehension in doc_text.py");
  return [...inner.matchAll(/"([a-z_]+)"\s*:/g)].map((m) => m[1] ?? "").sort();
}

/** The body of the exported `DocCitation` interface. */
function citationDecl(): string {
  const inner = /export interface DocCitation \{(.*?)\n\}/s.exec(ts)?.[1];
  if (!inner) throw new Error("could not locate the DocCitation interface in types.ts");
  return inner;
}

function clientCitationKeys(): string[] {
  // Strip comments first: this interface is documented, and a doc line mentioning `openable:`
  // would otherwise be counted as a declared member. A source-scanning check that reads its own
  // documentation has bitten this repo four separate times; not doing it a fifth.
  const body = citationDecl()
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n").filter((l) => !l.trim().startsWith("*") && !l.trim().startsWith("//")).join("\n");
  return [...body.matchAll(/^\s*([a-z_]+)\s*\??\s*:/gm)].map((m) => m[1] ?? "").sort();
}

describe("the document-QA citation contract", () => {
  it("finds both declarations — otherwise every assertion below is vacuous", () => {
    expect(serverCitationKeys().length, "server key extraction returned nothing").toBeGreaterThan(0);
    expect(clientCitationKeys().length, "client key extraction returned nothing").toBeGreaterThan(0);
  });

  it("declares client-side EXACTLY the keys the server sends — no more, no fewer", () => {
    // Set equality in both directions. A subset check passes on the very defect this exists to
    // catch; a superset check passes on a client inventing fields that read as undefined at runtime.
    expect(clientCitationKeys(),
      "DocCitation and the doc_text.py citation payload have diverged. A client type NARROWER than " +
      "the response makes a served field unreachable while nothing fails — that is how `doc_id` and " +
      "`openable` sat unused, with a code comment and a roadmap entry both asserting the feature " +
      "was blocked on a backend change that had already shipped.")
      .toEqual(serverCitationKeys());
  });

  it("carries doc_id and openable — the two fields the citation control depends on", () => {
    const server = serverCitationKeys();
    expect(server, "doc_id is the resolvable identity; the display name is not unique").toContain("doc_id");
    expect(server, "openable answers 'should this citation be a link?' server-side, so three " +
      "callers cannot re-derive it three different ways").toContain("openable");
  });
});
