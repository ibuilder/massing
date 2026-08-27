import { describe, expect, it } from "vitest";

import { parseQuoteText } from "./analytics";

/**
 * QTO-TRADE — pasted supplier quotes must reach the leveling engine in ITS column order.
 *
 * `procurement.level_quotes` and `POST /procurement/level-quotes` shipped and were tested months
 * ago with NO caller, while the price-ledger card in the same panel rendered the sentence
 * "quote leveling with 'record' feeds this ledger" — the UI advertised a tool there was no way to
 * invoke. This covers the wiring that closes that.
 *
 * WHY THE PARSER AND NOT THE PANEL. The mapping is the part that can be silently wrong: a buyer
 * pastes `item, qty, unit, unit price` and the engine reads `{item, qty, unit, unit_price}`, so a
 * transposed column would price the job off the wrong number and still render a confident,
 * well-formatted grid. Asserting on the rendered HTML would prove two strings are spelled
 * differently, not that the right value landed in the right key — the reason `budget.test.ts` gives
 * for testing the decision function rather than the markup.
 *
 * This does NOT prove the panel calls the engine; `clientCallers` covers reachability. It proves
 * that when it does, the payload means what the buyer typed.
 */
describe("parseQuoteText maps pasted quotes into the engine's shape", () => {
  const SAMPLE = [
    "Acme Supply",
    "2x4 stud, 500, EA, 4.25",
    '1/2" drywall, 200, SHT, 12.90',
    "",
    "Builders Depot",
    "2x4 stud, 500, EA, 4.10",
  ].join("\n");

  it("groups priced lines under the supplier header above them", () => {
    const q = parseQuoteText(SAMPLE);
    expect(q.map((x) => x.supplier)).toEqual(["Acme Supply", "Builders Depot"]);
    expect(q[0]?.lines).toHaveLength(2);
    expect(q[1]?.lines).toHaveLength(1);
  });

  it("puts each cell in the key the engine reads — the transposition this exists to catch", () => {
    // Column order is the whole risk. qty=500 and unit_price=4.25 are NOT interchangeable, and a
    // swap produces a plausible grid rather than an error.
    expect(parseQuoteText(SAMPLE)[0]?.lines[0])
      .toEqual({ item: "2x4 stud", qty: 500, unit: "EA", unit_price: 4.25 });
  });

  it("strips currency punctuation rather than reading a pasted $1,250.00 as zero", () => {
    const q = parseQuoteText("S\nrebar, 10, TON, $1,250.00");
    expect(q[0]?.lines[0]?.unit_price).toBe(1250);
  });

  it("drops a supplier header carrying no priced lines — that is not a quote", () => {
    // Without this, a trailing name typed on its own would level as a supplier quoting nothing and
    // win every line at $0.
    expect(parseQuoteText("Acme Supply\nBuilders Depot")).toEqual([]);
  });

  it("keeps a priced line that arrives before any header, rather than discarding it", () => {
    const q = parseQuoteText("2x4 stud, 500, EA, 4.25");
    expect(q).toHaveLength(1);
    expect(q[0]?.supplier).toBe("Supplier 1");
  });

  it("tolerates CRLF, because a quote pasted from email or Excel carries it", () => {
    expect(parseQuoteText("Acme\r\nrebar, 10, TON, 1250\r\n")[0]?.lines).toHaveLength(1);
  });

  it("reads a non-numeric qty or price as 0 instead of NaN", () => {
    // NaN would render as "$NaN" across the grid and poison supplier_totals server-side.
    const line = parseQuoteText("S\nwidget, n/a, EA, TBD")[0]?.lines[0];
    expect(line?.qty).toBe(0);
    expect(line?.unit_price).toBe(0);
  });
});
