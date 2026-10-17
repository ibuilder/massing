import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";
import { describe, expect, it } from "vitest";

/**
 * Does every live-stream subscriber ask to be told when the stream is REFUSED?
 *
 * **The hole this closes is one the code names.** `HttpCore.liveStream` classifies a fatal SSE close
 * and can stop retrying — but only `if (why && onStatus)`, and the comment above that line says why:
 *
 * > A REFUSAL NOBODY CAN SEE IS WORSE THAN A RETRY LOOP. Three callers hold their handle privately
 * > and pass no `onStatus` … so refusing would stop them permanently and SILENTLY where the old loop
 * > at least kept trying.
 *
 * That default is right and it is not a resting place. For those three callers the whole of slice ⑥
 * was inert: a stream the server will never serve them again backed off to the 60-second ceiling and
 * retried for ever, exactly as before, while the screen went on asserting it was live. *A guard
 * disabled for the callers that need it is a guard with a population of zero.*
 *
 * **Why a derived gate rather than three fixes.** The three were found by reading, and a fourth
 * subscriber added tomorrow re-opens the hole with no test going red — the same reason the backend
 * walks its seeding doors by AST instead of listing them. So the population is derived twice over:
 * the stream METHODS from the client (whatever returns `this.liveStream(...)`), and their CALL SITES
 * from the app.
 *
 * **It reads the AST, not the text.** An argument list cannot be split on commas: `pid, (d) => {
 * f(1, 2); }, cb` has three arguments and five commas. A hand-rolled scanner is how this file would
 * have produced a confident wrong number, which is the failure its neighbours keep paying for — so
 * it uses the compiler's own parser and counts `CallExpression.arguments`.
 *
 * **It fails CLOSED.** A subscriber reached by computed dispatch — a stream method named as a string
 * literal rather than called — cannot be checked by argument count, so it is reported UNKNOWN and
 * reds the build rather than being passed over. `clientCallers.test.ts` paid for that exact blind
 * spot: its first draft matched only `.foo(` and reported a method unreachable while `portal.ts`
 * dispatched it by name on every load.
 */

// Anchored on THIS FILE, not on the working directory. `clientCallers.test.ts` uses
// `process.cwd()`, which is correct only because vitest's root happens to be `apps/web` — and the
// backend learned the cost of that twice (`test_scratch_ignored`, `test_schema_types_agree`):
// *a relative path is a question about where somebody stood*, and `rglob` over a missing directory
// yields nothing and raises nothing, so it reports a clean tree.
const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "..");
const API = join(SRC, "api");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) { if (name !== "vendor") walk(p, out); }
    else if (name.endsWith(".ts") && !name.endsWith(".d.ts")) out.push(p);
  }
  return out;
}

const parse = (file: string, text?: string) =>
  ts.createSourceFile(file, text ?? readFileSync(file, "utf8"), ts.ScriptTarget.ESNext, true);

/** Names of client methods whose body returns `this.liveStream(...)`. */
export function streamMethods(files: { file: string; text?: string }[]): Set<string> {
  const found = new Set<string>();
  for (const { file, text } of files) {
    const sf = parse(file, text);
    const visit = (node: ts.Node, method: string | null) => {
      let m = method;
      if (ts.isMethodDeclaration(node) && ts.isIdentifier(node.name)) m = node.name.text;
      if (m && ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
          && node.expression.name.text === "liveStream"
          && node.expression.expression.kind === ts.SyntaxKind.ThisKeyword) {
        found.add(m);
      }
      ts.forEachChild(node, (c) => visit(c, m));
    };
    visit(sf, null);
  }
  return found;
}

export interface Site { file: string; line: number; method: string; args: number | null }

/** Every call of a stream method, with its argument COUNT from the AST — plus every place one is
 *  named as a string literal, which cannot be counted and so comes back `args: null`. */
export function callSites(files: { file: string; text?: string }[], methods: Set<string>): Site[] {
  const sites: Site[] = [];
  for (const { file, text } of files) {
    const sf = parse(file, text);
    const at = (n: ts.Node) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
          && methods.has(node.expression.name.text)) {
        sites.push({ file, line: at(node), method: node.expression.name.text,
                     args: node.arguments.length });
      } else if (ts.isStringLiteralLike(node) && methods.has(node.text)) {
        // Computed dispatch, or a label that looks like one. Either way the argument list is not
        // here to count, so this is UNKNOWN and not a pass.
        sites.push({ file, line: at(node), method: node.text, args: null });
      }
      ts.forEachChild(node, visit);
    };
    visit(sf);
  }
  return sites;
}

/** The verdict, separate from the reporting so a mutation can hit it directly —
 *  `test_unique_read_guard`'s first draft asserted that its analyser still REPORTED a site, so a
 *  mutation routing every unresolvable one to "safe" passed. *Reporting a site and classifying it
 *  are two different questions.* */
export function verdictOf(site: Site): "ok" | "silent" | "unknown" {
  if (site.args === null) return "unknown";
  return site.args >= 3 ? "ok" : "silent";
}

const appFiles = walk(SRC)
  .filter((f) => !f.startsWith(API + "/") && !f.endsWith(".test.ts"));
const apiFiles = walk(API).filter((f) => !f.endsWith(".test.ts"));

describe("every live-stream subscriber hears about a refusal", () => {
  const methods = streamMethods(apiFiles.map((file) => ({ file })));

  it("the derivation reaches the client's stream methods at all", () => {
    // A check whose expected answer is zero is the easiest kind to break silently. If this walk
    // stops finding the methods, every call site below is invisible and the file reports a clean
    // tree in exactly the same words as a clean tree.
    expect([...methods].sort(), "the four SSE subscriptions").toEqual(
      ["markupStream", "modelStream", "notificationStream", "pullPlanStream"]);
  });

  it("the derivation reaches the app's call sites at all", () => {
    expect(appFiles.length, "app files scanned").toBeGreaterThan(200);
    expect(callSites(appFiles.map((file) => ({ file })), methods).length,
           "call sites found").toBeGreaterThanOrEqual(4);
  });

  it("THE POINT: no subscriber is left to retry a refusal for ever in silence", () => {
    const bad = callSites(appFiles.map((file) => ({ file })), methods)
      .filter((s) => verdictOf(s) !== "ok")
      .map((s) => `${s.file.slice(SRC.length + 1)}:${s.line} ${s.method} `
                  + `(${verdictOf(s)}: ${s.args ?? "named, not called"} args)`);
    expect(bad, "each of these subscribes and asks for no status, so slice ⑥'s classification "
                + "cannot take effect: the stream retries for ever and the screen keeps saying live")
      .toEqual([]);
  });
});

describe("the analyser itself", () => {
  const F = "/synth/x.ts";
  const run = (text: string, methods = new Set(["modelStream"])) =>
    callSites([{ file: F, text }], methods);

  it("counts arguments from the AST, not from commas", () => {
    // Five commas, three arguments. A text split on commas calls this compliant at 6 and the
    // version below it non-compliant — both confidently.
    const s = run(`api.modelStream(pid, (d) => { f(1, 2); g(3, 4); }, (st, why) => h(st, why));`);
    expect(s.map((x) => x.args)).toEqual([3]);
  });

  it("is not fooled by commas inside strings or template literals", () => {
    const s = run("api.modelStream(`a,${f(1,2)}`, (d) => d);");
    expect(s.map((x) => x.args)).toEqual([2]);
    expect(s.map(verdictOf)).toEqual(["silent"]);
  });

  it("reports a two-argument subscription as silent", () => {
    expect(run(`api.modelStream(pid, (d) => void d);`).map(verdictOf)).toEqual(["silent"]);
  });

  it("reports a three-argument subscription as ok", () => {
    expect(run(`api.modelStream(pid, (d) => void d, (s) => void s);`).map(verdictOf)).toEqual(["ok"]);
  });

  it("FAILS CLOSED on computed dispatch — a name is not an argument list", () => {
    const s = run(`const k = "modelStream"; (api as any)[k](pid, cb);`);
    expect(s.map(verdictOf)).toContain("unknown");
  });

  it("ignores a same-named method on something that is not a stream", () => {
    // The population is the client's OWN stream methods; a name outside that set is not a subject.
    expect(run(`api.somethingElse(pid, cb);`)).toEqual([]);
  });

  it("the stream-method derivation reads `return this.liveStream(...)`", () => {
    const m = streamMethods([{ file: F, text:
      `class C {\n  aStream(p: string) { return this.liveStream("/" + p, () => {}); }\n`
      + `  notAStream(p: string) { return this.json("/" + p); }\n}` }]);
    expect([...m]).toEqual(["aStream"]);
  });

  it("...and does NOT credit a `liveStream` call on something other than `this`", () => {
    const m = streamMethods([{ file: F, text:
      `class C {\n  bStream(p: string) { return other.liveStream(p, () => {}); }\n}` }]);
    expect([...m]).toEqual([]);
  });

  it("PROOF OF REACH: it re-finds the three subscribers as slice ⑥ left them", () => {
    // Frozen, not fetched: the three call sites in the shape the comment in `httpCore.ts` names.
    // A proof-of-reach that reads today's tree proves nothing once today's tree is fixed.
    const shipped = [
      { file: "/frozen/schedule.ts", text:
        `const es = ctx.host.api.pullPlanStream(pid, (d) => { if (d.count) loadPull(); });` },
      { file: "/frozen/collabPresence.ts", text:
        `const es = api.modelStream(pid0, (raw) => { updatePresence(raw.editors); });` },
      { file: "/frozen/drawings.ts", text:
        `this.markupSub = this.host_.api.markupStream(pid, () => { void this.loadPins(); });` },
    ];
    const ms = new Set(["pullPlanStream", "modelStream", "markupStream", "notificationStream"]);
    const found = callSites(shipped, ms);
    expect(found.length, "all three frozen subscribers are seen").toBe(3);
    expect(found.map(verdictOf), "and all three are silent").toEqual(["silent", "silent", "silent"]);
  });
});
