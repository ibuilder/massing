import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The `/projects/{pid}/model/grid` levels contract, asserted against the SERVER rather than against
 * itself.
 *
 * The defect this locks out is not a wrong value — it is a client type NARROWER than the response.
 * `levels` was declared `{name, elevation}` while the server had always sent `{name, elevation,
 * guid}`. Nothing failed. No test went red. The field was simply unreachable, and R36 slice 6 got
 * scoped as needing a server change to carry level identity down to the plan cut. It did not.
 *
 * **Third instance of this exact shape in this codebase**: the sheet routes were SENT keys they
 * ignored, the spec manual's `elements` were IGNORED though sent, and this. A response type narrower
 * than the response is invisible from both ends — the server sees a well-formed request, the client
 * sees a well-formed object, and the capability quietly does not exist.
 *
 * So this reads the Python that actually builds the payload and requires the TS declaration to name
 * every key it emits. Asserting the TS type against a hand-written list would just restate the
 * client's belief; the server is the authority and the test has to go and ask it.
 */
const repoRoot = resolve(__dirname, "../../../..");
const py = readFileSync(
  resolve(repoRoot, "services/data/src/aec_data/drawings.py"), "utf8");
const ts = readFileSync(resolve(__dirname, "authoring.ts"), "utf8");

/** The dict literal `storey_elevations` appends — the single source of the levels payload. */
function serverLevelKeys(): string[] {
  const fn = py.slice(py.indexOf("def storey_elevations"));
  const body = fn.slice(0, fn.indexOf("\ndef ", 1));
  const inner = /out\.append\(\{([^}]*)\}\)/s.exec(body)?.[1];
  if (!inner) throw new Error("could not locate the out.append({...}) in storey_elevations");
  return [...inner.matchAll(/"([a-z_]+)"\s*:/g)].map((m) => m[1] ?? "").sort();
}

/** The body of the `levels:` member declaration in authoring.ts. */
function levelsDecl(): string {
  const inner = /levels:\s*\{([^}]*)\}\[\];/s.exec(ts)?.[1];
  if (!inner) throw new Error("could not locate the levels declaration in authoring.ts");
  return inner;
}

/** The `levels:` member of the grid response type in authoring.ts. */
function clientLevelKeys(): string[] {
  const inner = levelsDecl();
  return [...inner.matchAll(/([a-zA-Z_]+)\s*\??\s*:/g)].map((m) => m[1] ?? "").sort();
}

describe("the grid route's levels contract", () => {
  it("finds both declarations — otherwise every assertion below is vacuous", () => {
    expect(serverLevelKeys().length, "server key extraction returned nothing").toBeGreaterThan(0);
    expect(clientLevelKeys().length, "client key extraction returned nothing").toBeGreaterThan(0);
  });

  it("declares client-side EXACTLY the keys the server sends — no more, no fewer", () => {
    // Set equality in both directions on purpose. A subset check passes on the very defect this
    // exists to catch (client narrower than server); a superset check passes on a client that
    // invents fields the server never sends and will read as undefined at runtime.
    expect(clientLevelKeys(),
      "the client type and the server payload have diverged. A client type NARROWER than the " +
      "response makes a served field unreachable and nothing fails — that is how the storey guid " +
      "went unused for months. Update authoring.ts to name every key storey_elevations emits.")
      .toEqual(serverLevelKeys());
  });

  it("carries the storey guid, and requires it rather than marking it optional", () => {
    expect(serverLevelKeys(), "the server must send guid — this is the identity the whole " +
      "storey-keyed feature set hangs on").toContain("guid");
    // Verified end to end against samples/school_str.ifc: all five levels carry a non-empty guid,
    // so `guid?:` would understate the contract. An optional field pushes every caller into a
    // defensive branch for a case that cannot occur, and that branch is where a `?? level.name`
    // fallback gets written — reintroducing the silent orphan-on-rename this field prevents.
    const decl = levelsDecl();
    expect(decl, "guid must be required, not optional — levels are renameable and anything keyed " +
      "on the name orphans silently on rename").not.toMatch(/guid\s*\?\s*:/);
    expect(decl).toMatch(/guid\s*:\s*string/);
  });
});
