import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { FALLBACK_ROOMS, ROOM_IDS } from "./spine";

/**
 * ROOM-NAMING — the six rooms carry **professional** labels, and both sides of the wire agree on them.
 *
 * The prototype named the rooms in plain language: Building · Budget · Timeline · Money · My to-do.
 * We ship the professional terms — **Design · Planning · Cost · Schedule · Deal · Work** — and as of
 * 2026-07-29 that is a settled decision rather than an open question. The reasoning, so a future
 * reader does not reopen it by accident:
 *
 * *These are the words the work already has.* An architect issues a **design**; a contractor runs a
 * **schedule** and reports **cost**; a developer works a **deal**. Plain-language labels read as
 * friendlier right up until someone has to map "Money" onto whether they mean the budget, the
 * commitment, the pay application or the equity draw — at which point the friendly word is a second
 * vocabulary to learn on top of the real one. A tool for professionals that renames their own domain
 * makes itself harder to use in exactly the situations that matter.
 *
 * **What is actually tested here is not the taste, it is the drift.** The labels live in two places —
 * `rooms.ROOMS` (Python, the source `/rooms` serves) and `FALLBACK_ROOMS` (TypeScript, what renders
 * when that request fails). Two tables encoding one decision WILL diverge; this repo has the scars.
 * With the classic shell deleted the fallback is load-bearing, so a divergence would mean the rail
 * silently renames itself the moment the API hiccups — the worst possible moment to change the words
 * on someone's screen.
 */

const ROOMS_PY = resolve(__dirname, "../../../../services/api/src/aec_api/rooms.py");

/** `{"id": "design", "label": "Design", …}` → `[["design", "Design"], …]`, in file order. */
function pythonRoomLabels(): Array<[string, string]> {
  const src = readFileSync(ROOMS_PY, "utf8");
  const block = src.slice(src.indexOf("ROOMS: list"), src.indexOf("ROOM_IDS ="));
  expect(block.length, "could not locate the ROOMS table — rooms.py was restructured").toBeGreaterThan(100);
  return [...block.matchAll(/\{"id":\s*"([^"]+)",\s*"label":\s*"([^"]+)"/g)]
    .map((m) => [m[1]!, m[2]!] as [string, string]);
}

/** The settled answer. Spelled out here so changing it is a deliberate edit to a test, not a drift. */
const PROFESSIONAL: Array<[string, string]> = [
  ["design", "Design"],
  ["planning", "Planning"],
  ["cost", "Cost"],
  ["schedule", "Schedule"],
  ["deal", "Deal"],
  ["work", "Work"],
];

describe("the rooms are named in professional terms", () => {
  it("the server's table is exactly the settled set, in order", () => {
    expect(pythonRoomLabels()).toEqual(PROFESSIONAL);
  });

  it("the web's fallback agrees with the server, label for label", () => {
    // Not just the ids — `spine.test` already covers those. The LABELS are the thing a user reads,
    // and they were duplicated across a language boundary with nothing asserting they matched.
    expect(FALLBACK_ROOMS.map((r) => [r.id, r.label])).toEqual(pythonRoomLabels());
  });

  it("no room carries a plain-language name from the prototype", () => {
    // The specific reversal this records. If one of these ever appears, it is a decision being
    // re-made — which is fine, but it should not happen by someone copying an old mock.
    const PROTOTYPE = ["building", "budget", "timeline", "money", "my to-do", "todo"];
    for (const [, label] of pythonRoomLabels()) {
      expect(PROTOTYPE, `"${label}" is a prototype name; ROOM-NAMING settled on professional terms`)
        .not.toContain(label.toLowerCase());
    }
  });

  it("every id in the spine is one of the six", () => {
    expect([...ROOM_IDS].sort()).toEqual(PROFESSIONAL.map(([id]) => id).sort());
  });
});
