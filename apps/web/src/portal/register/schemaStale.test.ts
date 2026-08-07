import { describe, expect, it } from "vitest";

import { type SchemaStatus, schemaStaleBanner } from "./schemaStale";

/**
 * R41-SCHEMA-STALE, the reader's half.
 *
 * The server can detect that a record predates a schema change perfectly and it changes nothing if
 * the person reading the record still sees an empty field. So these assert the *rendering*, not the
 * flag: the orphaned key and, crucially, **its value** must be present in what the reader sees. An
 * orphaned value is by definition unreachable from the form — this banner is the only place it can
 * still be read, so "the banner appeared" is not the property worth protecting.
 *
 * The severity split is asserted here too, in both directions, because the backend and the UI can
 * disagree about it independently: a banner that renders whenever `changed` is true would train
 * everyone to ignore it within a week, after which the real one is invisible.
 */
const OK: SchemaStatus = {
  version: "0:aaa", stored: "0:aaa", changed: false, epoch_behind: false,
  orphaned: [], mistyped: [], stale: false,
};

describe("schemaStaleBanner", () => {
  it("renders nothing for a healthy record", () => {
    expect(schemaStaleBanner(OK, { cause: "burst riser" })).toBeNull();
  });

  it("renders nothing when the signature merely CHANGED (a field was added)", () => {
    // The whole severity argument in one assertion. If this ever renders, every historical record
    // in the register grows a warning the moment someone adds a field.
    const changed = { ...OK, version: "0:bbb", changed: true };
    expect(schemaStaleBanner(changed, { cause: "burst riser" })).toBeNull();
  });

  it("names the orphaned field AND shows its value, which is the whole point", () => {
    const st = { ...OK, changed: true, orphaned: ["cause"], stale: true };
    const el = schemaStaleBanner(st, { cause: "burst riser at L12" });
    expect(el).not.toBeNull();
    const text = el!.textContent ?? "";
    expect(text).toContain("cause");
    // The value. Without this the reader is told data is missing and given no way to see it.
    expect(text).toContain("burst riser at L12");
  });

  it("escapes an orphaned value — a register is where someone pastes a supplier's HTML", () => {
    const st = { ...OK, orphaned: ["note"], stale: true };
    const el = schemaStaleBanner(st, { note: "<img src=x onerror=alert(1)>" });
    expect(el!.querySelector("img")).toBeNull();
    expect(el!.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("escapes an orphaned KEY too — the field name is authored in module.json", () => {
    const st = { ...OK, orphaned: ["<script>x</script>"], stale: true };
    const el = schemaStaleBanner(st, { "<script>x</script>": "v" });
    expect(el!.querySelector("script")).toBeNull();
  });

  it("reports a mistyped field by name", () => {
    const st = { ...OK, mistyped: ["cost"], stale: true };
    expect(schemaStaleBanner(st, { cost: "not a number" })!.textContent).toContain("cost");
  });

  it("explains an epoch bump, which has no key to name", () => {
    const st = { ...OK, epoch_behind: true, stale: true };
    const text = schemaStaleBanner(st, { area: 1200 })!.textContent ?? "";
    expect(text).toMatch(/meaning/i);
    // It must not claim a field is missing — nothing is orphaned in this case.
    expect(text).not.toMatch(/no longer in this register/i);
  });

  it("survives an orphaned key with no value in data", () => {
    // `schema_status` only reports keys whose value is not None, but the two sides can drift; the
    // banner must not throw and blank the whole record detail over it.
    const st = { ...OK, orphaned: ["gone"], stale: true };
    expect(() => schemaStaleBanner(st, {})).not.toThrow();
    expect(schemaStaleBanner(st, {})!.textContent).toContain("gone");
  });

  it("is announced to assistive tech", () => {
    const st = { ...OK, orphaned: ["cause"], stale: true };
    expect(schemaStaleBanner(st, { cause: "x" })!.getAttribute("role")).toBe("status");
  });

  it("tolerates a record from a server that does not send the block at all", () => {
    expect(schemaStaleBanner(undefined, { a: 1 })).toBeNull();
    expect(schemaStaleBanner(null, null)).toBeNull();
  });
});
