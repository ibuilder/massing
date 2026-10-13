import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { ApiClient } from "../api/client";
import {
  FACT_TYPES, day, entriesFromRead, renderAuthority, renderAuthorityCard, type SupersedeBaseline,
  withoutSupersede, withSupersede,
} from "./authorityCard";

/**
 * CRE-AUTHORITY could be **read and never declared**.
 *
 * `portal/panels/design.ts` has rendered this gate on its go/no-go card all along — so the product
 * could tell you *"Source facts NOT current"* — and `saveDealAuthority()` had no caller anywhere, so
 * nothing in the product could make them current. A gate you can read and cannot satisfy looks like a
 * bug in the analysis rather than a missing surface.
 *
 * The load-bearing test here is the **tripwire**, not the rendering: `FACT_TYPES` is mirrored from
 * Python because the GET returns declared rows plus the *required* missing ones, so an optional fact
 * type nobody has declared yet appears in neither and a card built from the response alone could never
 * offer to add one. Two tables encoding one fact drift — this repo has the scars — and the `required`
 * flag is the one that matters: if it drifts, this card shows a fact type as optional while the gate
 * blocks on it. Same technique as `ui/reportMoments.test.ts` against `reports.py`.
 */

const DEAL_AUTHORITY_PY = resolve(
  __dirname, "../../../../services/api/src/aec_api/deal_authority.py");

type Assessment = Awaited<ReturnType<ApiClient["dealAuthority"]>>;

const ROW = (over: Partial<Assessment["table"][number]> = {}) => ({
  fact_type: "rent_roll", label: "Rent roll", document: "RR 2026-08.xlsx", as_of: "2026-09-01",
  age_days: 24, freshness_days: 45, fresh: true, reviewer: null, required: true,
  supersedes: [], ...over,
});

const ENTRY = (over: Partial<Assessment["entries"][number]> = {}) => ({
  fact_type: "rent_roll", document: "RR 2026-08.xlsx", as_of: "2026-09-01",
  freshness_days: 45, authoritative: true, supersedes: [], reviewer: null, ...over,
});

const ASSESS = (over: Partial<Assessment> = {}): Assessment => ({
  as_of: "2026-09-25", table: [ROW()], entries: [ENTRY()],
  missing: [], stale: [], superseded_still_active: [],
  gate: { passes: true, blocking: [], advisory: [] },
  counts: { declared: 1, missing: 0, stale: 0, blocking: 0, advisory: 0 },
  note: "Authority is declared per fact type, not per file.",
  ...over,
} as Assessment);

const mount = () => {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
};

describe("the mirrored fact-type table", () => {
  /** `FACT_TYPES: dict[str, tuple[label, days, required]]` as the Python declares it, in file order. */
  function pythonFactTypes(): [string, string, number, boolean][] {
    const src = readFileSync(DEAL_AUTHORITY_PY, "utf-8");
    const block = /FACT_TYPES: dict\[str, tuple\[str, int, bool\]\] = \{([\s\S]*?)\n\}/.exec(src);
    expect(block, "FACT_TYPES not found in deal_authority.py — the mirror below cannot be checked, "
      + "which is exactly the state this test exists to prevent").toBeTruthy();
    const out: [string, string, number, boolean][] = [];
    for (const m of block![1]!.matchAll(/"(\w+)":\s*\("([^"]+)",\s*(\d+),\s*(True|False)\)/g)) {
      out.push([m[1]!, m[2]!, Number(m[3]), m[4] === "True"]);
    }
    return out;
  }

  it("parsed the Python at all — a short list would make every assertion below vacuous", () => {
    expect(pythonFactTypes().length).toBeGreaterThanOrEqual(8);
  });

  it("matches key, label, default freshness and required flag, in order", () => {
    // `required` is the load-bearing column: a drift there shows a fact type as optional on this card
    // while `assess()` blocks on it, which is worse than not showing the fact type at all.
    expect(FACT_TYPES.map((f) => [...f])).toEqual(pythonFactTypes().map((f) => [...f]));
  });

  it("agrees with the engine about which types are required", () => {
    expect(FACT_TYPES.filter(([, , , r]) => r).map(([k]) => k))
      .toEqual(["rent_roll", "operating_statement", "tax"]);
  });
});

describe("dates", () => {
  it("formats from a fixed table, not the host's ICU", () => expect(day("2026-09-01")).toBe("1 Sep 2026"));
  it("returns an unparsable value unchanged", () => expect(day("whenever")).toBe("whenever"));
  it("renders an absent date as a dash", () => expect(day(null)).toBe("—"));
});

describe("the gate", () => {
  it("leads with the block and the engine's own reason for each fact type", () => {
    const el = renderAuthority(mount(), ASSESS({
      gate: { passes: false, advisory: [], blocking: [
        { fact_type: "operating_statement",
          why: "authoritative document is 87 day(s) past its 60-day freshness limit" },
        { fact_type: "tax", why: "no authoritative document declared" }] },
    }));
    expect(el.textContent).toContain("Blocked — 2 required fact type(s)");
    // Scoped to the blocking TABLE. Asserting the label against the whole card passes on the
    // "Not declared" line, which is rendered straight from FACT_TYPES and not through `label()` —
    // so the raw-key mutation satisfied it via a path the test is not about.
    const blockRows = [...el.querySelectorAll("table")][0]!.querySelectorAll("tr");
    const cells = [...blockRows].slice(1).map((tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent));
    expect(cells).toEqual([
      ["Operating statement (T-12)", "authoritative document is 87 day(s) past its 60-day freshness limit"],
      ["Property tax bill", "no authoritative document declared"],
    ]);
  });

  it("says plainly when it passes", () => {
    expect(renderAuthority(mount(), ASSESS()).textContent)
      .toContain("Authority is sufficient to underwrite");
  });

  // A stale offering package is not a stale tax bill. One list would make the required ones look
  // negotiable and the optional ones look alarming.
  it("keeps advisory apart from blocking", () => {
    const t = renderAuthority(mount(), ASSESS({
      gate: { passes: true, blocking: [],
              advisory: [{ fact_type: "offering", why: "stale (not required)" }] },
    })).textContent ?? "";
    expect(t).toContain("Advisory — stale, not required");
    expect(t).toContain("Offering package");
    expect(t).not.toContain("Blocked");
  });

  it("renders the case nobody looks for: superseded and still relied on", () => {
    const t = renderAuthority(mount(), ASSESS({
      superseded_still_active: [{ fact_type: "tax", document: "Tax bill 2024.pdf",
                                  issue: "superseded by Tax bill 2025.pdf and still authoritative" }],
    })).textContent ?? "";
    expect(t).toContain("Superseded, still active");
    expect(t).toContain("Tax bill 2024.pdf");
    expect(t).toContain("how a stale number reaches a committee");
  });
});

describe("the declared table", () => {
  // A tax bill and an offering package go stale on different clocks, so "stale" alone is not
  // checkable — the age against its own limit is.
  it("shows age against the fact type's own freshness limit", () => {
    const t = renderAuthority(mount(), ASSESS({
      table: [ROW({ age_days: 147, freshness_days: 60, fresh: false })],
    })).textContent ?? "";
    expect(t).toContain("147 / 60d");
  });

  it("names what has not been declared, required ones marked", () => {
    const t = renderAuthority(mount(), ASSESS()).textContent ?? "";
    expect(t).toContain("Not declared:");
    expect(t).toContain("Operating statement (T-12) (required)");
    expect(t).toContain("Property tax bill (required)");
    expect(t).not.toContain("Rent roll (required)");        // it IS declared
  });

  it("marks a required row as required", () => {
    expect(renderAuthority(mount(), ASSESS()).textContent).toContain("required");
  });
});

describe("round-tripping into the editor", () => {
  it("opens on what is already declared rather than a blank form", () => {
    expect(entriesFromRead(ASSESS())).toEqual([{
      fact_type: "rent_roll", document: "RR 2026-08.xlsx", as_of: "2026-09-01",
      freshness_days: 45, authoritative: true, supersedes: [], reviewer: null,
    }]);
  });

  it("carries a supersedes chain through", () => {
    const [e] = entriesFromRead(ASSESS({
      entries: [ENTRY({ supersedes: ["RR 2026-06.xlsx"] })] }));
    expect(e!.supersedes).toEqual(["RR 2026-06.xlsx"]);
  });

  // THE DEFECT. The editor's body used to be built from `assessment.table`, which is the
  // AUTHORITATIVE view — archival rows are absent from it by design — while the PUT replaces the
  // whole stored blob. So one save deleted the history the gate's `superseded_still_active` check
  // reads, and nothing anywhere went red: the response still reported a passing gate.
  it("THE DEFECT: an archival row survives a round-trip", () => {
    const read = ASSESS({
      entries: [
        ENTRY({ supersedes: ["RR 2026-06.xlsx"] }),
        ENTRY({ document: "RR 2026-06.xlsx", as_of: "2026-07-01", authoritative: false }),
      ],
    });
    const back = entriesFromRead(read);
    expect(back).toHaveLength(2);
    expect(back.filter((r) => r.authoritative === false).map((r) => r.document))
      .toEqual(["RR 2026-06.xlsx"]);
    // and it is the STORED row, not one reconstructed from the authoritative view
    expect(back[0]!.supersedes).toEqual(["RR 2026-06.xlsx"]);
  });

  it("carries the reviewer, which no screen could set and every save erased", () => {
    const [e] = entriesFromRead(ASSESS({ entries: [ENTRY({ reviewer: "K. Oyelaran" })] }));
    expect(e!.reviewer).toBe("K. Oyelaran");
  });

  it("refuses to invent entries from the assessment when the server sent none", () => {
    // No fallback to `a.table` ON PURPOSE: that fallback IS the defect. An empty list here makes
    // the card fail closed rather than silently round-trip a lossy reconstruction.
    expect(entriesFromRead({ ...ASSESS(), entries: undefined } as unknown as Assessment))
      .toEqual([]);
  });
});

/**
 * AUTHORITY-SUPERSEDE — a chain could only ever be built through the raw PUT.
 *
 * `deal_authority.py`'s premise is that *"an older file is archived rather than merely older"*, and
 * `assess()` computes `superseded_still_active` from the union of every row's `supersedes` lists —
 * **the CHAIN, not the archival rows** — flagging any row that is authoritative and named in it.
 * That is the check which catches a superseded document still being underwritten from, and the
 * first version of this file said the archival row was what it read. *If the chain is decorative,
 * pruning it looks free*, which is how an undo came to be written as a sweep over the whole table.
 * The editor preserved a chain it was handed
 * (the round-trip tests above) and could never CREATE one, which is the same class `reviewer` was in
 * before it got an input: a field only the API could write, behind a gate the product can read.
 *
 * **The implicit form was declined on the merits, and the reason is why this is a checkbox.** Review
 * proposed archiving the loaded row whenever its document name changes. A typo correction would then
 * permanently record a prior document that never existed, in a table an investment committee reads —
 * and `superseded_still_active` would report a finding about a file nobody ever held. *A fabricated
 * supersession is worse than an absent one*, because the absent one is silent and the fabricated one
 * is evidence. So the user states it.
 */
describe("declaring a supersession", () => {
  const live = (doc: string, over: Partial<Assessment["entries"][number]> = {}) =>
    ENTRY({ document: doc, ...over });
  const archival = (doc: string, over: Partial<Assessment["entries"][number]> = {}) =>
    ENTRY({ document: doc, authoritative: false, ...over });
  const BASE = (doc: string, over: Partial<SupersedeBaseline> = {}): SupersedeBaseline =>
    ({ document: doc, as_of: "2026-08-02", freshness_days: null, reviewer: null, ...over });

  it("records BOTH halves — the chain the GATE reads and the archival row that keeps the file", () => {
    const out = withSupersede([live("RR 2026-09.xlsx")], "rent_roll", BASE("RR 2026-08.xlsx"));
    const l = out.find((r) => r.authoritative !== false)!;
    // `assess()` computes `superseded_still_active` from the union of every row's `supersedes` and
    // flags any AUTHORITATIVE row whose document is in it. So the chain is the only half the gate
    // can see — the comment in this file used to say the opposite, and that inversion is what made
    // an over-reaching undo look free.
    expect(l.supersedes).toEqual(["RR 2026-08.xlsx"]);
    const a = out.filter((r) => r.authoritative === false);
    expect(a.map((r) => r.document)).toEqual(["RR 2026-08.xlsx"]);
    expect(a[0]!.supersedes).toEqual([]);          // and cannot itself trip the check
  });

  it("archives the superseded document's OWN date, reviewer and freshness", () => {
    // From the BASELINE, not from `rows`. The editor rewrites the live row with the new name before
    // calling this, so a lookup for the old document finds nothing — the shipped version therefore
    // took the REPLACEMENT's date with a null reviewer, and two tests asserted otherwise while
    // passing on a fixture that never changed the date field.
    const out = withSupersede(
      [live("RR 2026-09.xlsx", { as_of: "2026-09-25", reviewer: "new", freshness_days: 45 })],
      "rent_roll",
      BASE("RR 2026-08.xlsx", { as_of: "2026-08-02", reviewer: "K. Oyelaran", freshness_days: 30 }));
    const a = out.find((r) => r.authoritative === false)!;
    expect(a.as_of).toBe("2026-08-02");
    expect(a.reviewer).toBe("K. Oyelaran");
    expect(a.freshness_days).toBe(30);
  });

  it("falls back to the live row's date only when the baseline carries none", () => {
    const out = withSupersede([live("RR 2026-09.xlsx", { as_of: "2026-09-25" })],
                              "rent_roll", BASE("RR 2026-08.xlsx", { as_of: "" }));
    expect(out.find((r) => r.authoritative === false)!.as_of).toBe("2026-09-25");
  });

  it("is idempotent — `sync()` runs on every keystroke", () => {
    const once = withSupersede([live("RR 2026-09.xlsx")], "rent_roll", BASE("RR 2026-08.xlsx"));
    const twice = withSupersede(once, "rent_roll", BASE("RR 2026-08.xlsx"));
    expect(twice.filter((r) => r.authoritative === false)).toHaveLength(1);
    expect(twice.find((r) => r.authoritative !== false)!.supersedes).toEqual(["RR 2026-08.xlsx"]);
  });

  it("supersedes nothing when there is nothing to supersede, or the name has not changed", () => {
    const first = withSupersede([live("RR 2026-09.xlsx")], "rent_roll", BASE(""));
    expect(first.some((r) => r.authoritative === false)).toBe(false);
    expect(first.find((r) => r.authoritative !== false)!.supersedes).toEqual([]);
    const same = withSupersede([live("RR 2026-08.xlsx")], "rent_roll", BASE("RR 2026-08.xlsx"));
    expect(same.some((r) => r.authoritative === false)).toBe(false);
  });

  it("touches only the fact type it was asked about", () => {
    const rows = [live("RR 2026-09.xlsx"), ENTRY({ fact_type: "tax", document: "TB 2026.pdf" })];
    const out = withSupersede(rows, "rent_roll", BASE("RR 2026-08.xlsx"));
    expect(out.find((r) => r.fact_type === "tax")!.supersedes).toEqual([]);
    expect(out.filter((r) => r.fact_type === "tax")).toHaveLength(1);
  });

  it("does not mutate its input — the editor hands `rows` straight to the PUT", () => {
    const rows = [live("RR 2026-09.xlsx")];
    withSupersede(rows, "rent_roll", BASE("RR 2026-08.xlsx"));
    expect(rows).toHaveLength(1);
    expect(rows[0]!.supersedes).toEqual([]);
  });

  it("does nothing at all when the fact type has no authoritative row", () => {
    const out = withSupersede([archival("RR 2026-08.xlsx")], "rent_roll", BASE("RR 2026-08.xlsx"));
    expect(out).toHaveLength(1);
  });

  it("REVERSES — unticking removes the archival row and the chain entry", () => {
    const on = withSupersede([live("RR 2026-09.xlsx")], "rent_roll", BASE("RR 2026-08.xlsx"));
    const off = withoutSupersede(on, "rent_roll", "RR 2026-08.xlsx");
    expect(off.some((r) => r.authoritative === false)).toBe(false);
    expect(off.find((r) => r.authoritative !== false)!.supersedes).toEqual([]);
  });

  it("...and leaves an unrelated chain entry on the SAME row alone", () => {
    const rows = [live("RR 2026-09.xlsx", { supersedes: ["RR 2026-05.xlsx"] }),
                  archival("RR 2026-05.xlsx")];
    const on = withSupersede(rows, "rent_roll", BASE("RR 2026-08.xlsx"));
    expect(on.find((r) => r.authoritative !== false)!.supersedes)
      .toEqual(["RR 2026-05.xlsx", "RR 2026-08.xlsx"]);
    const off = withoutSupersede(on, "rent_roll", "RR 2026-08.xlsx");
    expect(off.find((r) => r.authoritative !== false)!.supersedes).toEqual(["RR 2026-05.xlsx"]);
    expect(off.filter((r) => r.authoritative === false).map((r) => r.document))
      .toEqual(["RR 2026-05.xlsx"]);
  });

  it("...and ANOTHER FACT TYPE's chain alone, even for the same document name", () => {
    // The shipped `filter` was fact-type scoped and the `map` beside it was not, so undoing one
    // row's supersession cleared that document name from every other fact type's chain. Two
    // documents in a data room really can share a name — "Appraisal.pdf" under appraisal and loan.
    const rows = [live("RR 2026-09.xlsx"),
                  ENTRY({ fact_type: "tax", document: "TB 2026.pdf",
                          supersedes: ["Shared name.pdf"] })];
    const off = withoutSupersede(rows, "rent_roll", "Shared name.pdf");
    expect(off.find((r) => r.fact_type === "tax")!.supersedes).toEqual(["Shared name.pdf"]);
  });

  it("...and is a no-op for an empty document name", () => {
    const rows = [live("RR 2026-09.xlsx", { supersedes: ["RR 2026-08.xlsx"] })];
    expect(withoutSupersede(rows, "rent_roll", "")).toEqual(rows);
  });
});

describe("the supersede control in the editor", () => {
  const sent: Assessment["entries"][] = [];
  const api = (entries: Assessment["entries"]) => ({
    dealAuthority: async () => ASSESS({ entries }),
    saveDealAuthority: async (_pid: string, rows: Assessment["entries"]) => {
      sent.push(rows.map((r) => ({ ...r })));
      return { assessment: ASSESS({ entries: rows }) };
    },
  } as unknown as ApiClient);

  const open = async (entries: Assessment["entries"]) => {
    const host = mount();
    renderAuthorityCard(host, { api: api(entries), projectId: () => "p1", setStatus: () => {} });
    // The card fetches in a `void …then()`, so the editor paints a microtask later. Flushed here
    // rather than slept on: a timer would make this test's pass depend on how fast the box is.
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    return host;
  };

  // Scoped to the rent_roll ROW, not to the first matching input in the table. The first draft took
  // `querySelectorAll(...).find(placeholder === "document name")` and typed into `offering`'s box —
  // `rent_roll` is the SECOND of ten fact types — so all three DOM tests failed identically while
  // the code was correct. *A selector that is merely plausible fails as a defect report*: the
  // message was "expected true to be false" about the control, not "you are editing another row".
  const supBox = (host: HTMLElement) =>
    host.querySelector<HTMLInputElement>('input[data-supersede="rent_roll"]')!;
  const docInput = (host: HTMLElement) =>
    [...supBox(host).closest("tr")!.querySelectorAll<HTMLInputElement>("input.portal-filter")]
      .find((i) => i.placeholder === "document name")!;

  it("is HIDDEN until the typed name differs from the loaded one", async () => {
    const host = await open([ENTRY({ document: "RR 2026-08.xlsx" })]);
    const box = supBox(host);
    expect(box.closest("label")!.hidden).toBe(true);
    const doc = docInput(host);
    doc.value = "RR 2026-09.xlsx";
    doc.dispatchEvent(new Event("input"));
    expect(box.closest("label")!.hidden).toBe(false);
  });

  it("stays hidden for a FIRST declaration — nothing is being superseded", async () => {
    const host = await open([]);
    const doc = docInput(host);
    doc.value = "RR 2026-09.xlsx";
    doc.dispatchEvent(new Event("input"));
    expect(supBox(host).closest("label")!.hidden).toBe(true);
  });

  it("un-ticks itself when the name is typed back to the loaded one", async () => {
    // Otherwise a ticked-but-hidden box would apply a supersession the person can no longer see.
    const host = await open([ENTRY({ document: "RR 2026-08.xlsx" })]);
    const doc = docInput(host), box = supBox(host);
    doc.value = "RR 2026-09.xlsx"; doc.dispatchEvent(new Event("input"));
    box.checked = true;
    doc.value = "RR 2026-08.xlsx"; doc.dispatchEvent(new Event("input"));
    expect(box.checked).toBe(false);
    expect(box.closest("label")!.hidden).toBe(true);
  });

  it("REACHES THE SAVE BODY — the pure rule, the checkbox and sync composing into one PUT", async () => {
    // The assertion that matters. Every test above this one exercises a part: `withSupersede` over
    // an array, the checkbox's visibility, the tooltip's words. None of them would notice `sync()`
    // forgetting to call the rule, which is the whole mechanism — and a card that offers a control
    // and sends nothing is this item's own defect wearing a new face.
    sent.length = 0;
    const host = await open([ENTRY({ document: "RR 2026-08.xlsx", as_of: "2026-08-02" })]);
    const doc = docInput(host), box = supBox(host);
    doc.value = "RR 2026-09.xlsx";
    doc.dispatchEvent(new Event("input"));
    doc.dispatchEvent(new Event("change"));
    box.checked = true;
    box.dispatchEvent(new Event("change"));
    const save = [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => b.textContent === "Save authority table")!;
    save.click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    expect(sent, "nothing was PUT").toHaveLength(1);
    const body = sent[0]!;
    const liveRow = body.find((r) => r.fact_type === "rent_roll" && r.authoritative !== false)!;
    expect(liveRow.document).toBe("RR 2026-09.xlsx");
    expect(liveRow.supersedes).toEqual(["RR 2026-08.xlsx"]);
    const arch = body.filter((r) => r.fact_type === "rent_roll" && r.authoritative === false);
    expect(arch.map((r) => r.document)).toEqual(["RR 2026-08.xlsx"]);
    expect(arch[0]!.as_of).toBe("2026-08-02");     // the superseded document's own date
  });

  it("...and sends NOTHING extra when the box is left unticked — a rename is not a supersession",
     async () => {
    sent.length = 0;
    const host = await open([ENTRY({ document: "RR 2026-08.xlsx", as_of: "2026-08-02" })]);
    const doc = docInput(host);
    doc.value = "RR 2026-09.xlsx";
    doc.dispatchEvent(new Event("input"));
    doc.dispatchEvent(new Event("change"));
    [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => b.textContent === "Save authority table")!.click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    const body = sent[0]!;
    expect(body.some((r) => r.authoritative === false)).toBe(false);
    expect(body.find((r) => r.fact_type === "rent_roll")!.supersedes).toEqual([]);
  });

  it("HIGH: editing an UNRELATED field prunes no chain — the shipped undo ran on every pass", async () => {
    // The worst of the six review findings. `sync()` called the undo whenever the box was unticked,
    // including when nothing had been renamed, and the undo stripped the loaded document name from
    // every chain in the table. On a project already in the `superseded_still_active` state that
    // name IS the blocking finding — `assess()` reads chains — so typing a reviewer and pressing
    // Save turned a blocked gate green with a superseded document still authoritative.
    //
    // **The first draft of this test passed when the defect was reinstated**, and that is the
    // sharper finding. It put the chain on a DIFFERENT fact type's row — so once the undo was
    // scoped to one fact type (review finding 5), the unconditional call stopped losing anything in
    // that scenario and this test went green on the broken code. *A regression test written against
    // one defect can be satisfied by the fix for another, and then it is testing nothing.* The loss
    // has to be inside the fact type being edited, which is also the realistic shape: a document
    // superseded earlier and since re-declared authoritative, with the chain naming it sitting on
    // the archival row it replaced.
    sent.length = 0;
    const host = await open([
      // the blocked shape, WITHIN rent_roll: "RR 2026-08.xlsx" is authoritative and is named as
      // superseded by the archival row below it
      ENTRY({ document: "RR 2026-08.xlsx" }),
      ENTRY({ document: "RR 2026-07.xlsx", authoritative: false,
              supersedes: ["RR 2026-08.xlsx"] }),
      // and a second arm one fact type over, so the scoping fix is exercised here too
      ENTRY({ fact_type: "tax", document: "TB 2026.pdf", supersedes: ["RR 2026-08.xlsx"] }),
    ]);
    const rev = [...supBox(host).closest("tr")!.querySelectorAll<HTMLInputElement>("input.portal-filter")]
      .find((i) => i.placeholder === "reviewed by")!;
    rev.value = "K. Oyelaran";
    rev.dispatchEvent(new Event("change"));
    [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => b.textContent === "Save authority table")!.click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    const body = sent[0]!;
    const archival = body.find((r) => r.fact_type === "rent_roll" && r.authoritative === false)!;
    expect(archival, "the archival row was deleted").toBeTruthy();
    expect(archival.supersedes, "the finding was pruned inside the fact type")
      .toEqual(["RR 2026-08.xlsx"]);
    expect(body.find((r) => r.fact_type === "tax")!.supersedes, "pruned across fact types")
      .toEqual(["RR 2026-08.xlsx"]);
    expect(body.find((r) => r.fact_type === "rent_roll" && r.authoritative !== false)!.reviewer)
      .toBe("K. Oyelaran");
  });

  it("HIGH: the archival row carries the SUPERSEDED document's date, through the real editor",
     async () => {
    // Driven end to end, because the pure-rule test for this passed on the shipped code: the
    // editor renames the live row before calling the rule, so the rule's own lookup for the old
    // document found nothing — and the test's fixture left the date untouched, so the replacement's
    // date happened to equal the right answer. Here the date IS changed, which is what a person
    // replacing a document does.
    sent.length = 0;
    const host = await open([ENTRY({ document: "RR 2026-08.xlsx", as_of: "2026-08-02",
                                     reviewer: "K. Oyelaran", freshness_days: 30 })]);
    const row = supBox(host).closest("tr")!;
    const doc = docInput(host);
    const date = row.querySelector<HTMLInputElement>('input[type="date"]')!;
    doc.value = "RR 2026-09.xlsx"; doc.dispatchEvent(new Event("input"));
    date.value = "2026-09-25"; date.dispatchEvent(new Event("change"));
    doc.dispatchEvent(new Event("change"));
    const box = supBox(host); box.checked = true; box.dispatchEvent(new Event("change"));
    [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => b.textContent === "Save authority table")!.click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    const a = sent[0]!.find((r) => r.authoritative === false)!;
    expect(a.document).toBe("RR 2026-08.xlsx");
    expect(a.as_of, "took the replacement's date").toBe("2026-08-02");
    expect(a.reviewer).toBe("K. Oyelaran");
    expect(a.freshness_days).toBe(30);
  });

  it("MEDIUM: clearing the document with ✕ after ticking leaves no cancelled supersession",
     async () => {
    // `sync()` returned early on an empty document, before the undo — so a ticked-then-cleared row
    // stored an archival entry the form no longer showed and could not remove. A fabricated prior
    // document is the one outcome this control exists not to produce.
    sent.length = 0;
    const host = await open([ENTRY({ document: "RR 2026-08.xlsx" })]);
    const doc = docInput(host), box = supBox(host);
    doc.value = "RR 2026-09.xlsx"; doc.dispatchEvent(new Event("input"));
    doc.dispatchEvent(new Event("change"));
    box.checked = true; box.dispatchEvent(new Event("change"));
    supBox(host).closest("tr")!.querySelector<HTMLButtonElement>("button.tool-btn")!.click();
    [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => b.textContent === "Save authority table")!.click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    expect(sent[0]!.filter((r) => r.fact_type === "rent_roll")).toEqual([]);
  });

  it("MEDIUM: a SECOND rename in the same session supersedes the document it replaced", async () => {
    // `was` is captured at paint and the editor was never repainted after Save, so A→B then B→C
    // stored "C supersedes A" and lost B — with the box still showing ticked. Saving now re-anchors
    // the baseline from what was actually PUT.
    sent.length = 0;
    const host = await open([ENTRY({ document: "A.pdf", as_of: "2026-01-01" })]);
    const saveBtn = () => [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => b.textContent === "Save authority table")!;
    const rename = async (to: string) => {
      const doc = docInput(host), box = supBox(host);
      doc.value = to; doc.dispatchEvent(new Event("input")); doc.dispatchEvent(new Event("change"));
      box.checked = true; box.dispatchEvent(new Event("change"));
      saveBtn().click();
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
      await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    };
    await rename("B.pdf");
    await rename("C.pdf");
    const body = sent[sent.length - 1]!;
    const l = body.find((r) => r.fact_type === "rent_roll" && r.authoritative !== false)!;
    expect(l.document).toBe("C.pdf");
    expect([...l.supersedes!].sort(), "B.pdf was lost").toEqual(["A.pdf", "B.pdf"]);
    expect(body.filter((r) => r.authoritative === false).map((r) => r.document).sort())
      .toEqual(["A.pdf", "B.pdf"]);
    // and the box is no longer ticked against a name that is now the stored one
    expect(supBox(host).checked).toBe(false);
  });

  it("says in the tooltip what ticking it will record, and that a typo is not a supersession",
     async () => {
    const host = await open([ENTRY({ document: "RR 2026-08.xlsx" })]);
    const doc = docInput(host);
    doc.value = "RR 2026-09.xlsx"; doc.dispatchEvent(new Event("input"));
    const title = supBox(host).closest("label")!.title;
    expect(title).toContain("RR 2026-08.xlsx");
    expect(title).toContain("RR 2026-09.xlsx");
    expect(title).toContain("typo");
  });
});
