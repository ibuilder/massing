import { resolve } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

/**
 * RESPELLED-SHAPE — a wire type declared twice is invisible to every audit over the declarations.
 *
 * This exists because of a measured cost, not a style preference. `ClashResult.truncated` was
 * returned by the server and read by NOBODY for months, and the reason was not that anyone decided
 * to ignore it: `clashPanel.ts` re-spelled the response shape as an inline cast, so no property
 * access anywhere resolved to the DECLARED member. No type error, no lint, and neither the
 * identifier nor the type-aware unread-field derivation in `deadFieldTyped.test.ts` could see the
 * omission — they all start from `api/`'s interfaces and ask who reads them. *A re-spelled shape is
 * a field no derivation over declarations can see.*
 *
 * ### The rule is IDENTICAL NAME + IDENTICAL MEMBER SET, and the narrowness is the point
 *
 * A structural-subset rule ("this local shape is ⊆ an api interface") reports 20 matches here, and
 * 18 of them are noise or deliberate: `Vec3Like ⊆ Vec3` because both are three numbers;
 * `PairField ⊆ ModuleField` because a pure function takes the three fields it needs; three
 * `jurisdictionPacks` shapes are testable parameter types whose "dropped" fields are read elsewhere
 * in the same file. Gating that rule means an exemption list of five judgement calls — and *an
 * exemption list is where the next instance hides.*
 *
 * Same name AND same members is a different claim: not "these look alike" but "somebody wrote this
 * type out twice". It needs no exemptions, and it correctly ignores the four same-name collisions
 * under `vendor/` (`StampTemplate`, `SpecSection`, `MassingMetrics`, `Entry`), which are independent
 * packages whose members differ.
 *
 * ### Fail-closed on the derivation, not just on the verdict
 *
 * The population was 2 when this shipped and is 0 now. A check whose expected answer is zero is the
 * easiest kind to break silently — a walk that stops matching reports a clean tree in exactly the
 * words of a clean tree. So this asserts the walk still FINDS things before it is allowed to report
 * nothing, and re-runs its own predicate against the two shapes as they stood before the fix.
 */

const posix = (p: string) => p.replace(/\\/g, "/");
const WEB = posix(resolve(process.cwd(), "src"));
const API = `${WEB}/api`;

const isApiDecl = (f: string) =>
  f.startsWith(API) && !f.endsWith("schema.d.ts") && !f.endsWith(".test.ts");
const isTest = (f: string) => f.endsWith(".test.ts") || f.endsWith(".test.tsx");

const nameOf = (n: ts.PropertyName): string =>
  (ts.isIdentifier(n) || ts.isStringLiteral(n) || ts.isNumericLiteral(n)) ? n.text : "";

/** The member set of an interface, order-independent. Three or more, because a two-field shape is
 *  a coincidence rather than a copy. */
function memberKey(members: ts.NodeArray<ts.TypeElement>): string | null {
  const ms: string[] = [];
  for (const m of members) {
    if (!ts.isPropertySignature(m) || !m.name) continue;
    const k = nameOf(m.name);
    if (k) ms.push(k);
  }
  return ms.length >= 3 ? [...ms].sort().join(",") : null;
}

interface Decl { name: string; file: string; key: string }

/** Both populations in one pass over the TypeScript program: every exported-or-not interface in
 *  `api/` keyed by name, and every interface declared outside it. Built from the program rather than
 *  a filesystem walk so it sees exactly the files the compiler does — a walk and a `tsconfig` can
 *  disagree, and the half this check reads must be the half that ships. */
function derive() {
  const cfgPath = ts.findConfigFile(process.cwd(), ts.sys.fileExists, "tsconfig.json");
  if (!cfgPath) throw new Error("no tsconfig.json — the derivation cannot run, which is not 'clean'");
  const parsed = ts.parseJsonConfigFileContent(
    ts.readConfigFile(cfgPath, ts.sys.readFile).config, ts.sys, process.cwd());
  const program = ts.createProgram(parsed.fileNames, parsed.options);

  const api = new Map<string, Decl>();
  const local: Decl[] = [];
  for (const sf of program.getSourceFiles()) {
    const f = posix(sf.fileName);
    if (!f.startsWith(WEB) || f.includes("node_modules") || isTest(f)) continue;
    const visit = (n: ts.Node): void => {
      if (ts.isInterfaceDeclaration(n)) {
        const key = memberKey(n.members);
        if (key) {
          const d: Decl = { name: n.name.text, file: f, key };
          if (isApiDecl(f)) { if (!api.has(d.name)) api.set(d.name, d); }
          else local.push(d);
        }
      }
      ts.forEachChild(n, visit);
    };
    visit(sf);
  }
  return { api, local };
}

/** THE predicate, separate so a mutation can be aimed at it directly. The self-test below asserts
 *  what it CLASSIFIES, not merely that it was reached — `test_unique_read_guard`'s first draft
 *  asserted the analyser still reported a site, so a mutation routing everything to "safe" passed.
 *  Reporting a site and ruling on it are two different questions. */
export function isRespelled(local: Decl, api: Map<string, Decl>): boolean {
  const a = api.get(local.name);
  return !!a && a.key === local.key;
}

const { api, local } = derive();

describe("RESPELLED-SHAPE: no module re-declares an api/ wire type", () => {
  it("the walk still finds declarations on both sides — a silent empty walk reports a clean tree", () => {
    // Floors, not pins: ordinary work adds interfaces. What these catch is the derivation breaking,
    // which on a zero-expected check is indistinguishable from success.
    expect(api.size, "no api/ interfaces found — the walk or the api/ path test is broken")
      .toBeGreaterThan(100);
    expect(local.length, "no non-api interfaces found — the walk is not reaching the app")
      .toBeGreaterThan(100);
    expect([...api.values()].some((d) => d.file.endsWith("/api/types.ts")),
      "api/types.ts contributed nothing, so the file both known instances came from is unread")
      .toBe(true);
  });

  it("RE-FINDS both shipped instances when they are put back — proof of reach", () => {
    // The two duplicates as they stood before this change, byte-identical to `api/types.ts`.
    // Frozen here rather than fetched from git: a proof-of-reach that depends on the depth of
    // somebody's clone is a dependency on an environment nobody controls, which is how
    // `test_gap_records.py` failed closed on every CI build.
    const preFix: Decl[] = [
      { name: "Vital", file: `${WEB}/shell/vitalsBar.ts`, key: ["value", "unit", "note", "band"].sort().join(",") },
      { name: "LogisticsResource", file: `${WEB}/viewer/draft/logisticsOverlay.ts`,
        key: ["id", "kind", "label", "position", "polygon", "radius", "start", "end"].sort().join(",") },
    ];
    for (const d of preFix) {
      expect(api.has(d.name), `${d.name} is no longer declared in api/ — re-derive before trusting this`)
        .toBe(true);
      expect(isRespelled(d, api),
        `the predicate no longer recognises the ${d.name} duplicate this gate was built from`).toBe(true);
    }
  });

  it("does NOT flag a same-name shape whose members differ — the vendor collisions stay clean", () => {
    // Four interfaces under vendor/ share a name with an api/ one and are unrelated packages. If the
    // rule ever widens to name-only, they become four false findings and the gate grows an exemption
    // list — which is the failure mode this file's docstring exists to refuse.
    const probe: Decl = { name: "Vital", file: `${WEB}/vendor/made/up.ts`, key: "alpha,beta,gamma" };
    expect(isRespelled(probe, api),
      "the predicate ignored the member set, so it is matching on name alone").toBe(false);
  });

  it("no module outside api/ re-declares an api/ wire type", () => {
    const hits = local.filter((d) => isRespelled(d, api));
    expect(hits.map((d) => `${d.name} in ${d.file.split("/src/")[1]}`), [
      "A wire type declared twice cannot be seen by any audit over the declarations — that is how",
      "ClashResult.truncated stayed unread for months. Import the type from api/ (re-export it if",
      "this module's importers rely on the local spelling) rather than writing it out again.",
    ].join(" ")).toEqual([]);
  });
});
