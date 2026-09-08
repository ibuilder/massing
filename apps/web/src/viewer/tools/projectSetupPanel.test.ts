import { describe, expect, it, vi } from "vitest";

import { type ProjectSetupDeps, projectOriginButton, projectUnitsButton } from "./projectSetupPanel";
import type { ModelSetupFacts } from "../../api/model";

/**
 * MODEL-SETUP's two authoring panels, driven through the DOM they actually build.
 *
 * **What this exists for.** Both panels READ before they OFFER — that is the whole reason the
 * `GET /projects/{pid}/model/setup` route was written first, since *"convert to millimetres"* with
 * no statement of the present unit is a coin flip the user is asked to call. The half that was
 * missing from the first draft is the other end of that: after the edit lands, the figures on
 * screen describe a model that no longer exists.
 *
 * `rebase_origin` is the sharp one, because **it is not idempotent by point**. The form asks for a
 * point in the coordinates the model has NOW; rebase to (1000, 2000) and every one of those
 * coordinates changes. A second press against the same displayed distance moves the building a
 * second time — and the georeference carries the second offset too, so nothing looks wrong until
 * somebody opens the model against the survey.
 *
 * The first draft left the stale figures on screen and said in a comment that they were *"re-read
 * rather than reused after the edit lands"*. They were not. That is this session's own subject
 * arriving in its own diff — **a claim in a comment that the code does not back** — found by
 * re-reading the diff rather than by anything going red, which is exactly why it gets a behavioural
 * test instead of a better comment.
 */
const flush = () => new Promise((r) => setTimeout(r, 0));
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text))!;
const bodyText = () => (document.querySelector(".result-card") as HTMLElement).textContent ?? "";

const FACTS = (over: Partial<ModelSetupFacts> = {}): ModelSetupFacts => ({
  length_unit: "METRE", length_unit_metres: 1, convertible: true,
  unconvertible_reason: null,
  targets: ["CENTIMETRE", "METRE", "MILLIMETRE"],
  georeference: { eastings: 100, northings: 200, orthogonal_height: 0 },
  root_placements: 4, distance_from_origin: 9000, distance_from_origin_m: 9000,
  ...over,
});

/** `reads` records every `modelSetup` call, and `facts` is what the NEXT one answers with. */
function harness(first: ModelSetupFacts = FACTS()) {
  const calls: { reads: number; edited: { recipe: string; params: unknown }[] } =
    { reads: 0, edited: [] };
  let next = first;
  const deps: ProjectSetupDeps = {
    pid: "p1",
    api: {
      modelSetup: async () => { calls.reads++; return next; },
    } as unknown as ProjectSetupDeps["api"],
    toolBtn2: (label, onClick) => {
      const b = document.createElement("button");
      b.textContent = label; b.onclick = onClick; return b;
    },
    out: document.createElement("div"),
    container: document.createElement("div"),
    notify: vi.fn(),
    authorAndReload: vi.fn(async (recipe, params) => {
      calls.edited.push({ recipe, params });
      return { applied: true, refused: false };
    }),
  };
  return { deps, calls, answerNextWith: (f: ModelSetupFacts) => { next = f; } };
}

async function open(make: (d: ProjectSetupDeps) => HTMLButtonElement, deps: ProjectSetupDeps) {
  document.body.replaceChildren();
  const opener = make(deps);
  document.body.appendChild(opener);
  opener.click();
  await flush(); await flush();
}

describe("project units: the panel names the unit the project reads in NOW", () => {
  it("reads before it offers, and offers only the server's own list", async () => {
    const { deps, calls } = harness();
    await open(projectUnitsButton, deps);
    expect(calls.reads, "the unit is read, never assumed").toBe(1);
    expect(bodyText()).toContain("METRE");
    const opts = [...document.querySelectorAll("option")].map((o) => o.value);
    expect(opts, "the dropdown is the server's `targets`, not a client-side list").toEqual(
      ["CENTIMETRE", "METRE", "MILLIMETRE"]);
    const current = [...document.querySelectorAll("option")].find((o) => o.value === "METRE")!;
    expect(current.disabled, "converting to the unit it already reads in is not an option").toBe(true);
  });

  it("RE-READS after a conversion instead of leaving the old unit on screen", async () => {
    // The regression. Without the re-read the panel still says METRE while the project is in
    // millimetres, and a second conversion is offered against a source unit that is no longer true.
    const { deps, calls, answerNextWith } = harness();
    await open(projectUnitsButton, deps);
    expect(calls.reads).toBe(1);

    (document.querySelector("select") as HTMLSelectElement).value = "MILLIMETRE";
    answerNextWith(FACTS({ length_unit: "MILLIMETRE", length_unit_metres: 0.001 }));
    btn("Convert").click();
    await flush(); await flush();

    expect(calls.edited).toEqual([{ recipe: "convert_length_unit", params: { to: "MILLIMETRE" } }]);
    expect(calls.reads, "the applied edit is followed by a fresh measurement").toBe(2);
    expect(bodyText(), "the panel states the unit the project reads in now").toContain("MILLIMETRE");
    const stillCurrent = [...document.querySelectorAll("option")].find((o) => o.value === "MILLIMETRE")!;
    expect(stillCurrent.disabled, "and the new current unit is the one now disabled").toBe(true);
  });

  it("does not re-read, and puts the control back, when the edit was REFUSED", async () => {
    const { deps, calls } = harness();
    (deps.authorAndReload as ReturnType<typeof vi.fn>).mockResolvedValue(
      { applied: false, refused: true });
    await open(projectUnitsButton, deps);
    btn("Convert").click();
    await flush(); await flush();
    expect(calls.reads, "nothing changed, so there is nothing to re-measure").toBe(1);
    expect(btn("Convert").disabled, "the control is usable again after a refusal").toBe(false);
  });

  it("offers nothing at all when the file carries no LENGTHUNIT", async () => {
    const { deps } = harness(FACTS({ length_unit: null, convertible: false }));
    await open(projectUnitsButton, deps);
    expect(document.querySelector("select"), "no dropdown when there is nothing to convert from")
      .toBeNull();
    expect(bodyText()).toContain("no LENGTHUNIT assignment");
  });

  it("names the REASON for a unit it cannot convert, rather than claiming there is none", async () => {
    // A foot-based model (an `IfcConversionBasedUnit`, ordinary in a US survey file) HAS a length
    // unit — the recipe simply cannot rewrite it, and converting anyway rescales the geometry while
    // leaving the declared unit in place. Two different files reach the not-convertible branch and
    // the original text asserted "no LENGTHUNIT assignment" for both, which is false for this one.
    const { deps } = harness(FACTS({
      length_unit: "FOOT", length_unit_metres: 0.3048, convertible: false,
      unconvertible_reason: "conversion-based unit (e.g. feet) — this recipe rewrites SI assignments only",
    }));
    await open(projectUnitsButton, deps);
    expect(document.querySelector("select"), "still no dropdown — it cannot be converted").toBeNull();
    expect(bodyText(), "the server's reason is shown").toContain("conversion-based unit");
    expect(bodyText(), "and the false claim is not").not.toContain("no LENGTHUNIT assignment");
    expect(bodyText(), "the unit is still named honestly").toContain("FOOT");
  });
});

describe("project origin: rebasing is not idempotent by point", () => {
  it("reports the measured distance before offering the repair", async () => {
    const { deps, calls } = harness();
    await open(projectOriginButton, deps);
    expect(calls.reads).toBe(1);
    expect(bodyText()).toContain("9000.0");
    expect(bodyText()).toContain("4 root placements");
  });

  it("refuses a point that is already the origin rather than sending a no-op edit", async () => {
    const { deps, calls } = harness();
    await open(projectOriginButton, deps);
    btn("Rebase").click();
    await flush();
    expect(calls.edited, "(0, 0, 0) moves nothing and is not worth republishing for").toEqual([]);
  });

  it("RE-MEASURES after a rebase, so a second press cannot act on the old frame", async () => {
    // The regression, and the one that damages a model rather than merely confusing a reader: the
    // point is in CURRENT model coordinates, so pressing Rebase twice against one reading moves the
    // building twice — and the map conversion absorbs the second offset too.
    const { deps, calls, answerNextWith } = harness();
    await open(projectOriginButton, deps);

    const [xi, yi] = [...document.querySelectorAll("input[type=number]")] as HTMLInputElement[];
    xi!.value = "9000"; yi!.value = "0";
    answerNextWith(FACTS({ distance_from_origin: 0, distance_from_origin_m: 0 }));
    btn("Rebase").click();
    await flush(); await flush();

    expect(calls.edited).toEqual([{ recipe: "rebase_origin", params: { point: [9000, 0, 0] } }]);
    expect(calls.reads, "the applied rebase is followed by a fresh measurement").toBe(2);
    expect(bodyText(), "the distance shown is the one measured AFTER the move").toContain("0.0");
    const fresh = [...document.querySelectorAll("input[type=number]")] as HTMLInputElement[];
    expect(fresh[0]!.value, "and the form is reset, not left holding a point in the old frame")
      .toBe("0");
  });

  it("says the survey basis is missing rather than implying the offset is carried", async () => {
    const { deps } = harness(FACTS({ georeference: null }));
    await open(projectOriginButton, deps);
    expect(bodyText()).toContain("no IfcMapConversion");
  });
});
