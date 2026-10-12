import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { HttpError } from "../../api/httpCore";
import type { EffectiveRule } from "../../api/model";
import {
  duplicateIds, libraryReading, ruleEditor, rulesFromRows, saveRefusal, wouldWipe,
} from "./ruleStandards";

/**
 * FIRM-RULES-OPTIONAL slice ② — the rule library could not be AUTHORED from the app.
 *
 * Slice ① made the firm's standards get evaluated and made a clean run over the three sample rules
 * say that it was one. It could not fix why every project was on the samples: `GET`/`PUT
 * /projects/{pid}/rules` and `GET`/`PUT /firm/rules` had **no client method between them**, so
 * there was no way to write a rule from the product at all.
 *
 * What this file holds:
 *
 *  - **`seeded` is rendered as the samples, not as a library.** Showing three sample rules under
 *    "your rules" is the conflation slice ① removed one layer down; saving is what adopts them.
 *  - **"nothing here" and "nothing anywhere" are different states** with different next actions.
 *  - **A save REPLACES the library**, so an all-rows-deleted save is refused rather than guessed
 *    at — `rbac.py` records what losing the firm library cost the last time.
 *  - **A blank row is dropped; a half-typed one is not.** The editor always shows an empty row, and
 *    dropping something the user typed is worse than letting the validator refuse it by name.
 */

describe("libraryReading — the samples are not this project's library", () => {
  it("names the sample fallback and does not tone it as a library", () => {
    const r = libraryReading("project", 3, true);
    expect(r.kind).toBe("samples");
    expect(r.tone).toBe("warn");
    expect(r.headline).toContain("SAMPLE");
    expect(r.detail).toContain("not a pass");
  });

  it("tells the reader that saving is what adopts them", () => {
    expect(libraryReading("project", 3, true).detail).toContain("Save to adopt");
  });

  it("says firm rules need no copying — that is what inheritance is for", () => {
    // Without this the obvious reaction to the samples card is to paste the firm's rules into the
    // project, which creates an override of every one of them and makes the firm's library
    // unchangeable in practice.
    expect(libraryReading("project", 3, true).detail).toContain("inherited automatically");
  });

  it("distinguishes an EMPTY project library from the sample fallback", () => {
    // Both have nothing authored for the project. One is falling back to examples, the other is
    // inheriting the firm's — opposite situations with the same row count.
    const empty = libraryReading("project", 0, false);
    expect(empty.kind).toBe("empty");
    expect(empty.detail).toContain("firm's standards apply");
    expect(empty.headline).not.toContain("SAMPLE");
  });

  it("says what an empty FIRM library costs every project", () => {
    const r = libraryReading("firm", 0, false);
    expect(r.kind).toBe("empty");
    expect(r.tone).toBe("warn");
    expect(r.detail).toContain("sample rules");
  });

  it("reports an authored library plainly, and names the override rule", () => {
    expect(libraryReading("firm", 4, false).kind).toBe("authored");
    expect(libraryReading("firm", 4, false).tone).toBe("ok");
    expect(libraryReading("project", 2, false).detail).toContain("override");
  });

  it("never reports the sample state for the FIRM scope — there is no fallback there", () => {
    // `seeded` is a property of the project route. Passing it through for the firm card would
    // claim a fallback that does not exist at that level.
    expect(libraryReading("firm", 3, true).kind).not.toBe("samples");
  });
});

describe("saveRefusal — the gate explained, not the status code", () => {
  it("explains the platform-admin gate on the FIRM library, and the way round it", () => {
    const m = saveRefusal("firm", new HttpError("forbidden", 403));
    expect(m).toContain("platform administrator");
    expect(m, "the reader can still override on their own project").toContain("same id");
  });

  it("gives the project refusal its own reason — a different role entirely", () => {
    expect(saveRefusal("project", new HttpError("forbidden", 403))).toContain("editor role");
  });

  it("passes a 422 through with the server's message AND says nothing was saved", () => {
    const m = saveRefusal("project", new HttpError("rule 'fire90': bad selector", 422));
    expect(m).toContain("bad selector");
    expect(m).toContain("nothing was saved");
  });

  it("does not claim to know why on an unexpected status", () => {
    const m = saveRefusal("project", new HttpError("gateway timeout", 504));
    expect(m).toContain("gateway timeout");
    expect(m).not.toContain("platform administrator");
  });

  it("survives a non-HttpError", () => {
    expect(saveRefusal("project", new Error("network down"))).toContain("network down");
  });
});

describe("rulesFromRows — drop the blank row, keep the half-typed one", () => {
  const row = (o: Partial<Record<string, string>> = {}) => ({
    id: o.id ?? "", name: o.name ?? "", scope: o.scope ?? "",
    require: o.require ?? "", severity: o.severity ?? "",
  });

  it("drops a wholly blank row — the editor always shows one", () => {
    expect(rulesFromRows([row({ id: "a", scope: "IfcWall", require: "name" }), row()]))
      .toHaveLength(1);
  });

  it("KEEPS a half-typed row so the validator refuses it by name", () => {
    // Dropping it silently would make "save" look successful while losing what was typed.
    expect(rulesFromRows([row({ name: "half a rule" })])).toHaveLength(1);
  });

  it("trims, because a trailing space in a selector is a parse error nobody can see", () => {
    expect(rulesFromRows([row({ id: " a ", scope: " IfcWall ", require: " name " })])[0])
      .toMatchObject({ id: "a", scope: "IfcWall", require: "name" });
  });

  it("defaults the severity rather than sending an empty one", () => {
    expect(rulesFromRows([row({ id: "a" })])[0]!.severity).toBe("medium");
  });

  it("keeps a row whose ONLY content is whitespace out", () => {
    expect(rulesFromRows([row({ id: "   ", name: "  " })])).toHaveLength(0);
  });
});

describe("duplicateIds — a duplicate id is an ambiguous override", () => {
  const row = (id: string) => ({ id, name: "", scope: "IfcWall", require: "name", severity: "low" });

  it("reports an id used twice", () => {
    expect(duplicateIds([row("fire90"), row("other"), row("fire90")])).toEqual(["fire90"]);
  });

  it("compares case-insensitively — the server stores the id verbatim and matches on it", () => {
    expect(duplicateIds([row("Fire90"), row("fire90")])).toEqual(["fire90"]);
  });

  it("ignores blank ids, because the server generates one per rule", () => {
    // Several blank rows are several distinct rules. Flagging them would refuse the ordinary way
    // of adding two at once.
    expect(duplicateIds([row(""), row(""), row("  ")])).toEqual([]);
  });

  it("says nothing about a clean library", () => {
    expect(duplicateIds([row("a"), row("b")])).toEqual([]);
  });

  it("reports every duplicate, not the first", () => {
    expect(duplicateIds([row("a"), row("a"), row("b"), row("b")])).toEqual(["a", "b"]);
  });
});

describe("wouldWipe — a save replaces the library", () => {
  it("refuses to turn a library into nothing", () => {
    expect(wouldWipe(4, 0)).toBe(true);
  });

  it("allows an empty save when it was already empty — nothing is lost", () => {
    expect(wouldWipe(0, 0)).toBe(false);
  });

  it("allows a shrink that is not a wipe", () => {
    expect(wouldWipe(4, 1)).toBe(false);
  });
});

/** The pins: four routes that had no client method, and the way in. */
const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "../../api/model.ts"), "utf8");
const panel = readFileSync(resolve(here, "ruleStandards.ts"), "utf8");
const standards = readFileSync(resolve(here, "standards.ts"), "utf8");

describe("the four routes have client methods, and the panel uses them", () => {
  it("declares all four", () => {
    for (const m of ["rulesLibrary(pid: string)", "saveRules(pid: string",
                     "firmRules()", "saveFirmRules(rules:"]) {
      expect(client, `no client method for ${m}`).toContain(m);
    }
    expect(client).toContain("`/firm/rules`");
  });

  it("sends both writes as PUT with an embedded `rules` body", () => {
    // `Body(..., embed=True)` on both routes: a bare array is a 422 the panel would report as a
    // bad selector.
    const saves = client.split("saveRules(pid: string")[1]!.slice(0, 1200);
    expect(saves).toContain('method: "PUT"');
    expect(saves).toContain('JSON.stringify({ rules })');
  });

  it("the panel reads and writes both levels", () => {
    expect(panel).toMatch(/api\.firmRules\(\)/);
    expect(panel).toMatch(/api\.rulesLibrary\(pid\)/);
    expect(panel).toMatch(/api\.saveFirmRules\(rules\)/);
    expect(panel).toMatch(/api\.saveRules\(pid, rules\)/);
  });

  it("asks who the user is before offering the firm save, rather than after", () => {
    expect(panel).toMatch(/api\.me\(\)/);
    expect(panel).toContain("canSave: loaded.admin");
  });

  it("re-reads after a save instead of patching the card", () => {
    // A project that has just saved its first library is no longer `seeded`, and what APPLIES to
    // it changed too. Leaving "these are the SAMPLE rules" above a library the user just authored
    // is the same stale-verdict defect as the one this item started from.
    expect(panel).toMatch(/const reload = \(msg: string\) => void renderRuleStandards\(ctx, msg\)/);
    expect(panel).toContain("saved: reload");
  });

  it("is reachable — the CDE / Standards panel opens it, lazily", () => {
    expect(standards).toContain("Rule standards (firm + project)");
    expect(standards).toMatch(/await import\("\.\/ruleStandards"\)/);
  });

  it("escapes every interpolation it puts into innerHTML", () => {
    // The population is the `innerHTML` assignments, not every template literal in the file: the
    // first draft scanned all of them and came back with six "findings" — a URL path parameter, two
    // numbers, a word and a status message — none of which reach HTML. *A rule applied outside the
    // population it was reasoned about produces confident findings about code it has no view of*,
    // and the exemption list it then needs is where the real instance hides. With the right
    // population this needs NO exemptions: the one legitimate unescaped value, a severity label
    // from a module constant, was wrapped rather than carved out.
    const sites = [...panel.matchAll(/innerHTML\s*=\s*([\s\S]*?);\n/g)].map((m) => m[1]!);
    expect(sites.length, "the scan found no innerHTML sites — it would pass vacuously")
      .toBeGreaterThan(3);
    const bad = sites.flatMap((site) => [...site.matchAll(/\$\{([\s\S]*?)\}/g)]
      .map((m) => m[1]!.trim())
      .filter((x) => !x.startsWith("esc(")));
    expect(bad, `unescaped interpolation(s) in innerHTML: ${bad.join(" | ")}`).toEqual([]);
  });
});

/**
 * The Save button, driven rather than pinned.
 *
 * Both refusals were first covered by source pins asserting the guard was CALLED — and wrapping the
 * whole block in `if (false)` passed them, because the call was still there and still in the right
 * order while doing nothing. *Asserting that a decision is computed is not asserting that it is
 * acted on.*
 */
describe("the Save button refuses rather than guessing", () => {
  const rule = (id: string, scope = "IfcWall"): EffectiveRule => ({
    id, name: `rule ${id}`, scope, require: "name", severity: "low",
  });

  function mount(initial: EffectiveRule[], over: Partial<Parameters<typeof ruleEditor>[2]> = {}) {
    const host = document.createElement("div");
    const sent: unknown[][] = [];
    const saved: string[] = [];
    ruleEditor(host, initial, {
      scope: "project", seeded: false, canSave: true, whyNot: "",
      save: async (rules) => { sent.push(rules); },
      saved: (m) => saved.push(m),
      ...over,
    });
    const rows = () => [...host.querySelectorAll("tbody tr")];
    const save = () => host.querySelector("button.mini-btn.on") as HTMLButtonElement;
    const idInput = (i: number) =>
      rows()[i]!.querySelector("input") as HTMLInputElement;
    const status = () => host.querySelector("span.meta")!.textContent || "";
    return { host, sent, saved, rows, save, idInput, status };
  }

  it("renders a row per rule plus one blank to type into", () => {
    expect(mount([rule("a"), rule("b")]).rows()).toHaveLength(3);
  });

  it("REFUSES a duplicate id and does not call save", async () => {
    const m = mount([rule("fire90"), rule("other")]);
    m.idInput(1).value = "fire90";
    m.save().click();
    await Promise.resolve();
    expect(m.sent, "a duplicate id must never reach the server").toHaveLength(0);
    expect(m.status()).toContain("fire90");
    expect(m.status()).toContain("override");
  });

  it("REFUSES a save that would empty a non-empty library", async () => {
    const m = mount([rule("a")]);
    for (const tr of m.rows()) (tr.querySelector("button") as HTMLButtonElement).click();
    m.save().click();
    await Promise.resolve();
    expect(m.sent).toHaveLength(0);
    expect(m.status()).toContain("replaces the whole library");
  });

  it("saves a clean library, and hands back exactly the rows", async () => {
    const m = mount([rule("a"), rule("b")]);
    m.save().click();
    await Promise.resolve(); await Promise.resolve();
    expect(m.sent).toHaveLength(1);
    expect((m.sent[0] as { id: string }[]).map((r) => r.id)).toEqual(["a", "b"]);
    expect(m.saved[0]).toContain("2 rule(s)");
  });

  it("disables Save and says why when the caller cannot write", () => {
    const m = mount([rule("a")], { canSave: false, whyNot: "platform administrators only" });
    expect(m.save().disabled).toBe(true);
    expect(m.status()).toContain("platform administrators only");
  });

  it("reports a server refusal against the button instead of re-reading", async () => {
    const m = mount([rule("a")], {
      save: async () => { throw new HttpError("bad selector on 'a'", 422); },
    });
    m.save().click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    expect(m.saved, "a failed save must not re-render as if it worked").toHaveLength(0);
    expect(m.status()).toContain("bad selector");
    expect(m.save().disabled).toBe(false);
  });
});
