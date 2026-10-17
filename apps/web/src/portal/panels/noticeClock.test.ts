import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { NoticeItem, NoticeRegister } from "../../api/contracts";
import { itemLine, registerNotes, statusCounts, statusMeta } from "./noticeClock";

/**
 * NOTICE-CLOCK — the register, and the five refusals a screen could have thrown away.
 *
 * `notice_clock` counts the days a contract gives you to notify the other party of an event before
 * the right to time or money for it is lost. It is one of the most careful engines in the tree, and
 * every piece of that care is a thing a consumer can drop:
 *
 *  - it refuses to pick a contract family, returning `adopted: false` and a reason — which looks
 *    exactly like an empty register unless the screen reads it;
 *  - the scan now reports `complete` and `coverage`, because it used to be computed over the OLDEST
 *    500 records of each source and "0 expired" was a statement about the wrong half of the project;
 *  - `indeterminate` is a clock nobody can start, NOT a milder `open`;
 *  - a business-day count with no holiday list is short by every public holiday, which moves the
 *    real deadline EARLIER than the one shown, and the engine flags it per clock;
 *  - an `override` is a what-if under a contract the project is not on.
 */

const reg = (o: Partial<NoticeRegister> = {}): NoticeRegister => ({
  family: o.family ?? "aia_a201_2017",
  family_label: o.family_label ?? "AIA A201-2017",
  adopted: o.adopted ?? true,
  counts: o.counts ?? {},
  items: o.items ?? [],
  complete: o.complete ?? true,
  coverage: o.coverage ?? "every record in the field register was scanned (3 daily reports)",
  verify: o.verify ?? "these are the standard provisions of the unamended form",
  ...o,
});

const item = (o: Partial<NoticeItem> = {}): NoticeItem => ({
  event: { type: o.event?.type ?? "weather_delay", date: o.event?.date ?? "2026-03-02",
           date_basis: o.event?.date_basis ?? "occurred", ...o.event },
  clause: o.clause === undefined
    ? { id: "c1", reference: "§15.1.3.1", days: 21, basis: "calendar days",
        starts_on: "later of occurrence and recognition", consequence: "express_time_bar",
        citation: "AIA A201-2017 §15.1.3.1" }
    : o.clause,
  status: o.status ?? "open",
  days_remaining: o.days_remaining ?? 9,
  due_on: o.due_on ?? "2026-03-23",
  ...o,
});

describe("registerNotes — the qualifications come before the numbers", () => {
  it("reports NO FAMILY as the whole answer, not as an empty register", () => {
    const n = registerNotes(reg({ adopted: false, family: null,
                                  why: "notice periods cannot be inferred" }));
    expect(n).toHaveLength(1);
    expect(n[0]!.kind).toBe("no-family");
    expect(n[0]!.detail).toContain("cannot be inferred");
  });

  it("does NOT stack a coverage note under the no-family note", () => {
    // That would imply there was a register to be incomplete. With nothing adopted there is not.
    const n = registerNotes(reg({ adopted: false, complete: false, coverage: "only 2 of 3" }));
    expect(n.map((x) => x.kind)).toEqual(["no-family"]);
  });

  it("reports an incomplete scan, and passes the coverage sentence through", () => {
    const n = registerNotes(reg({ complete: false,
                                  coverage: "only the most recent 2 record(s) of daily report" }));
    const c = n.find((x) => x.kind === "coverage")!;
    expect(c).toBeTruthy();
    expect(c.tone).toBe("warn");
    expect(c.detail).toContain("most recent 2");
    expect(c.detail, "an empty register and nothing due are different claims")
      .toContain("not the same as nothing due");
  });

  it("says nothing about coverage when the scan was complete", () => {
    expect(registerNotes(reg()).some((x) => x.kind === "coverage")).toBe(false);
  });

  it("treats `complete: undefined` as not-a-claim rather than as incomplete", () => {
    // An older server, or a cached response. Warning on a register that never said it was partial
    // would train the reader to ignore the warning that matters.
    expect(registerNotes(reg({ complete: undefined })).some((x) => x.kind === "coverage"))
      .toBe(false);
  });

  it("labels an OVERRIDE as a what-if", () => {
    const n = registerNotes(reg({
      override: { family: "fidic_red_2017", note: "this is a what-if, not the project's position" },
    }));
    const o = n.find((x) => x.kind === "override")!;
    expect(o.headline).toContain("NOT the adopted family");
    expect(o.detail).toContain("what-if");
  });

  it("flags business-day clocks counted with NO holiday list, and says which way it errs", () => {
    const n = registerNotes(reg({
      items: [item({ holidays_supplied: false }), item({ holidays_supplied: true }),
              item({ holidays_supplied: false })],
    }));
    const h = n.find((x) => x.kind === "holidays")!;
    expect(h.headline).toContain("2 clock(s)");
    expect(h.detail, "a short count moves the deadline earlier, not later").toContain("EARLIER");
  });

  it("does not flag holidays when every clock had a list", () => {
    expect(registerNotes(reg({ items: [item({ holidays_supplied: true })] }))
      .some((x) => x.kind === "holidays")).toBe(false);
  });

  it("stacks all three qualifications when all three hold", () => {
    // They are independent facts and collapsing to the worst one drops two the reader needs.
    const n = registerNotes(reg({
      complete: false, override: { family: "nec4", note: "what-if" },
      items: [item({ holidays_supplied: false })],
    }));
    expect(n.map((x) => x.kind)).toEqual(["override", "coverage", "holidays", "verify"]);
  });

  it("carries the engine's own verify warning rather than restating it", () => {
    const v = registerNotes(reg({ verify: "verify against the executed contract" }))
      .find((x) => x.kind === "verify")!;
    expect(v.detail).toBe("verify against the executed contract");
  });
});

describe("statusMeta / statusCounts — indeterminate is not a milder open", () => {
  it("gives indeterminate its own label and tone", () => {
    expect(statusMeta("indeterminate").label).not.toBe(statusMeta("open").label);
    expect(statusMeta("indeterminate").tone).toBe("warn");
    expect(statusMeta("open").tone).toBe("ok");
  });

  it("tones an elapsed period as the worst thing on the screen", () => {
    expect(statusMeta("expired").tone).toBe("bad");
  });

  it("counts in the engine's ranking, not alphabetically", () => {
    const rows = statusCounts(reg({
      counts: { open: 2, expired: 1, no_clause: 4, due_soon: 3, indeterminate: 5 },
    }));
    expect(rows.map(([s]) => s)).toEqual(["expired", "due_soon", "open", "indeterminate", "no_clause"]);
  });

  it("omits zero counts rather than printing a row of noughts", () => {
    expect(statusCounts(reg({ counts: { open: 0, expired: 2 } })).map(([s]) => s))
      .toEqual(["expired"]);
  });

  it("APPENDS a status it does not know rather than dropping it", () => {
    // The engine may grow one. Dropping it would make the counts disagree with the item list, and a
    // total that cannot be reconciled is the defect this branch keeps finding.
    const rows = statusCounts(reg({ counts: { expired: 1, waived: 2 } }));
    expect(rows).toEqual([["expired", 1], ["waived", 2]]);
  });

  it("falls back to the raw status name instead of inventing a label", () => {
    expect(statusMeta("waived").label).toBe("waived");
  });
});

describe("itemLine — what happened, under which clause, by when", () => {
  it("names the clause, the period and its basis", () => {
    const h = itemLine(item());
    expect(h).toContain("§15.1.3.1");
    expect(h).toContain("21 calendar days");
    expect(h).toContain("2026-03-23");
  });

  it("says when a date is a PROXY rather than a recorded fact", () => {
    // An RFI has only a created timestamp — when somebody wrote it down. The engine labels that and
    // a screen that hides the label presents the proxy as the occurrence.
    expect(itemLine(item({ event: { type: "rfi_cost_impact", date: "2026-03-05",
                                    date_basis: "reported" } })))
      .toContain("not when it occurred");
  });

  it("does not add that caveat to a recorded occurrence", () => {
    expect(itemLine(item())).not.toContain("not when it occurred");
  });

  it("names the MISSING field on an indeterminate clock", () => {
    const h = itemLine(item({ status: "indeterminate", days_remaining: null, due_on: null,
                              missing: ["became_aware_on"],
                              why: "FIDIC runs from awareness and none is recorded" }));
    expect(h).toContain("became_aware_on");
    expect(h).toContain("runs from awareness");
    expect(h).not.toContain("day(s) left");
  });

  it("escapes the engine's free text", () => {
    const h = itemLine(item({ why: "<img src=x onerror=alert(1)>" }));
    expect(h).not.toContain("<img src=x");
    expect(h).toContain("&lt;img");
  });

  it("renders a no_clause item without pretending there is a deadline", () => {
    const h = itemLine(item({ clause: null, status: "no_clause", days_remaining: null,
                              due_on: null, why: "no notice provision for this event type" }));
    expect(h).toContain("no provision in this library");
    expect(h).not.toContain("due ");
  });
});

/** The pins: three routes that had no client method, and the way in. */
const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "../../api/contracts.ts"), "utf8");
const panel = readFileSync(resolve(here, "noticeClock.ts"), "utf8");
const schedule = readFileSync(resolve(here, "schedule.ts"), "utf8");

describe("the three notice routes are reachable", () => {
  it("declares a client method for each", () => {
    for (const m of ["notices(pid: string", "noticeClauses(pid: string", "draftNotice(pid: string"]) {
      expect(client, `no client method for ${m}`).toContain(m);
    }
    expect(client).toContain("/notices/clauses");
    expect(client).toContain("/notices/draft");
  });

  it("posts the draft item as the body, not wrapped — the route takes a bare Body", () => {
    const d = client.split("draftNotice(pid: string")[1]!.slice(0, 700);
    expect(d).toContain('method: "POST"');
    expect(d).toContain("JSON.stringify(item)");
    expect(d, "a wrapped item is a 422 the panel would report as a draft failure")
      .not.toContain("JSON.stringify({ item");
  });

  it("the panel reads the register, the library and the drafter", () => {
    expect(panel).toMatch(/api\.notices\(pid\)/);
    expect(panel).toMatch(/api\.noticeClauses\(pid/);
    expect(panel).toMatch(/api\.draftNotice\(pid, i\)/);
  });

  it("renders the notes BEFORE the counts, and stops when nothing is adopted", () => {
    // Ordering is the assertion twice over: the coverage sentence has to be read before the number
    // it qualifies, and a register with no family must not fall through to a count table.
    const notesAt = panel.indexOf("for (const n of registerNotes(reg))");
    const stopAt = panel.indexOf("if (!reg.adopted) return;");
    const countsAt = panel.indexOf("const counts = statusCounts(reg);");
    expect(notesAt).toBeGreaterThan(0);
    expect(stopAt).toBeGreaterThan(notesAt);
    expect(countsAt).toBeGreaterThan(stopAt);
  });

  it("is reachable from the schedule panel, lazily, and by a BUTTON", () => {
    // A card that fetched on render would fire a whole-field-record scan every time somebody opened
    // the schedule — which that file's own comment says is how a panel gets avoided.
    expect(schedule).toContain("Notice clock");
    expect(schedule).toMatch(/await import\("\.\/noticeClock"\)/);
    expect(schedule).toMatch(/noticeBtn\.onclick/);
  });
});
