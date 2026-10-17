import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { buildRoomTabs, orderRoomTabs } from "./roomTabs";
import { personaRooms, preselectedRoom, ROOM_IDS } from "./spine";

/**
 * WS-BTN-DEAD's persona half — **an allowlist that has never had any effect, and the measurement
 * that says what to replace it with.**
 *
 * `applyPersona` hid any `.ws-btn` whose `data-ws` the open persona did not list. Nothing renders
 * that class and nothing in the tree SETS that attribute, so from the day the room spine landed
 * every persona's `ws` list was inert: every room showed to everyone.
 *
 * The roadmap left the remainder open as a product decision — *"which rooms does a subcontractor
 * see"* — and it is not one. **`orderRooms` had already answered it** in its own docstring:
 * *weighting rather than filtering*, because *"a room that disappears is a room the user has to
 * relearn where to find"*. This file's job is to make the two halves of that answer checkable: the
 * invariant (a persona can never shorten the strip) and the measurement that rules out the reading
 * a reader reaches for first (filtering).
 *
 * ### The lists are PARSED from `main.ts`, never copied here
 *
 * `PERSONAS` lives in the app entry, which a unit test cannot import. Retyping the seven lists into
 * this file would be the thing the `RAIL_ITEMS`/`SPLIT_RAIL` comment three lines above them already
 * names as the cause of that defect: *"a key list beside a key definition is a second source of
 * truth: when one grows, the other must."* So this reads the shipped literal, and asserts the parse
 * found something before ruling on it — a parse that silently matches nothing reports a clean tree
 * in the same words as a clean tree.
 */
const MAIN = readFileSync(resolve(__dirname, "../main.ts"), "utf8");

/** `name → ws allowlist`, from the shipped `PERSONAS` literal. `null` for the `all` persona. */
function shippedPersonas(): Map<string, string[] | null> {
  const start = MAIN.indexOf("const PERSONAS: Record<string, PersonaCfg> = {");
  expect(start, "PERSONAS literal not found — has it been renamed?").toBeGreaterThan(0);
  const body = MAIN.slice(start, MAIN.indexOf("\n};", start));
  const out = new Map<string, string[] | null>();
  for (const m of body.matchAll(/^ {2}([a-z_]+):\s*\{\s*ws:\s*(null|\[[^\]]*\])/gm)) {
    const [, name, ws] = m as unknown as [string, string, string];
    out.set(name, ws === "null" ? null
      : [...ws.matchAll(/"([^"]+)"/g)].map((q) => q[1] as string));
  }
  return out;
}

describe("a persona weights the room strip; it cannot shorten it", () => {
  const personas = shippedPersonas();
  const listed = [...personas].filter(([, ws]) => ws?.length);

  it("parsed the shipped lists — the population is derived, not retyped", () => {
    // Eight personas today, seven declaring a list. Floored rather than pinned so adding a role is
    // not a failure, but a parse that stopped matching IS.
    expect(personas.size).toBeGreaterThanOrEqual(8);
    expect(personas.get("all")).toBeNull();
    expect(listed.length).toBeGreaterThanOrEqual(7);
    // Three documents said "all ten personas" — this docstring's subject, WS-BTN-DEAD's roadmap
    // entry and NOTIF-BADGE-DEAD's. There were eight, and seven with a list. *A number nobody
    // measures is a number that propagates; agreement between copies is not evidence.*
    expect(personas.size).toBeLessThan(10);
    for (const [, ws] of listed) expect(ws!.every((w) => typeof w === "string" && w)).toBe(true);
  });

  it("gives EVERY persona every room — the invariant worth more than the ordering", () => {
    for (const [name, ws] of personas) {
      expect([...personaRooms(ws)].sort(), name).toEqual([...ROOM_IDS].sort());
    }
    expect(personaRooms(null)).toEqual(ROOM_IDS);
    expect(personaRooms([])).toEqual(ROOM_IDS);
    expect(personaRooms(undefined)).toEqual(ROOM_IDS);
  });

  it("puts the persona's own rooms first, in canonical order", () => {
    for (const [name, ws] of listed) {
      const seated = new Set(ws!.map(preselectedRoom));
      const order = personaRooms(ws);
      const head = order.slice(0, seated.size);
      expect([...head].sort(), name).toEqual([...seated].sort());
      // canonical within each half, so two personas seated in the same rooms get the same strip
      expect(head, name).toEqual(ROOM_IDS.filter((r) => seated.has(r)));
    }
    // a subcontractor is seated in construction + the model, so Schedule leads and Design follows
    expect(personaRooms(["construction", "model", "drawings"]).slice(0, 2)).toEqual(["design", "schedule"]);
  });

  it("MEASURES why this weights instead of filtering — 3 of 7 rooms, and no Work for anybody", () => {
    // This is the whole argument, as an assertion rather than a paragraph. Had `applyPersona`'s
    // filter ever run against the rendered strip, these are the rooms it would have removed.
    const seatedAnywhere = new Set(listed.flatMap(([, ws]) => ws!.map(preselectedRoom)));
    expect([...seatedAnywhere].sort()).toEqual(["deal", "design", "schedule"]);
    expect(ROOM_IDS.filter((r) => !seatedAnywhere.has(r)))
      .toEqual(["planning", "cost", "work", "operate"]);
    // Work is the only room that carries a count — the design's "a badge on one is a summons" —
    // and a filter derived from this table hides it from every role in the product.
    expect(seatedAnywhere.has("work")).toBe(false);
    // and the narrowest case: an engineer would see one room of seven
    const eng = personas.get("engineer");
    expect(eng, "the engineer persona is the measurement's witness").toBeTruthy();
    expect(new Set(eng!.map(preselectedRoom)).size).toBe(1);
  });

  it("orderRoomTabs is total — it reorders, it never drops or duplicates", () => {
    const tabs = buildRoomTabs(null, 6, null);
    for (const [, ws] of personas) {
      const out = orderRoomTabs(tabs, personaRooms(ws));
      expect(out).toHaveLength(tabs.length);
      expect(out.map((t) => t.id).sort()).toEqual(tabs.map((t) => t.id).sort());
      expect(out.find((t) => t.id === "work")?.count).toBe(6);   // the badge survives the reorder
    }
    // an order that mentions nothing, or one id, still yields the whole strip with the rest stable
    expect(orderRoomTabs(tabs, []).map((t) => t.id)).toEqual(tabs.map((t) => t.id));
    expect(orderRoomTabs(tabs, ["work"]).map((t) => t.id))
      .toEqual(["work", ...tabs.map((t) => t.id).filter((i) => i !== "work")]);
    // an order naming a room the strip does not have must not invent a tab
    expect(orderRoomTabs(tabs, ["nonsense", "cost"]).map((t) => t.id))
      .toEqual(["cost", ...tabs.map((t) => t.id).filter((i) => i !== "cost")]);
  });

  it("main.ts really wires it — the reproduction above is not the evidence", () => {
    // Source-level, the same bargain `clientCallers.test.ts` and `test_route_reachability` make:
    // this cannot see a wiring disabled at runtime, and the DOM behaviour is `roomMarking.test.ts`'s.
    const fn = MAIN.slice(MAIN.indexOf("function applyPersona("));
    const body = fn.slice(0, fn.indexOf("\n}\n"));
    expect(body).toContain("personaRoomOrder = personaRooms(cfg.ws)");
    expect(body).toContain("paintRoomTabs()");
    // and the dead filter is gone, not merely unused — CODE lines only, because the replacement
    // carries a comment quoting the line it replaced. This assertion red on that comment on its
    // first run, which is the lesson `roomMarking.test.ts` recorded in this same directory
    // (*"a check that cannot tell an explanation from the thing it explains reds hardest on the
    // commit that fixes the defect"*) arriving for the THIRD time in one change — it also red
    // `wsBtnGone.test.ts` on a `style.css` comment. *A lesson written down next to the check that
    // learned it is not transferred to the next check by being true.*
    const code = body.split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");
    expect(code).not.toContain(".ws-btn");
    const paint = MAIN.slice(MAIN.indexOf("function paintRoomTabs("));
    expect(paint.slice(0, paint.indexOf("\n}\n"))).toContain("orderRoomTabs(tabs, personaRoomOrder)");
  });
});
