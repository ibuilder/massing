import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { FALLBACK_ROOMS, ROOM_IDS } from "./spine";

/**
 * ROOM-NAMING — the rooms carry **professional** labels, and both sides of the wire agree on them.
 *
 * The prototype named the rooms in plain language: Building · Budget · Timeline · Money · My to-do.
 * We ship the professional terms — **Deal · Design · Planning · Schedule · Cost · Work · Operate** —
 * and as of 2026-07-29 that is a settled decision rather than an open question. The reasoning, so a
 * future reader does not reopen it by accident:
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

type Room = [id: string, label: string, job: string];

/**
 * `{"id": "design", "label": "Design", "job": "…"}` → `[["design", "Design", "…"], …]`, in file order.
 *
 * **Why `job` is parsed and not just the label.** The first version of this test stopped at ids and
 * labels while the `job` strings sat in the same literal, duplicated across the same language
 * boundary, guarded by nothing. Within a day they drifted: Approvals moved into Planning, `rooms.py`
 * widened Planning's job to "…contract it and get it approved", and `FALLBACK_ROOMS` still said
 * "…buy it out and contract it". The test was green throughout. That is the recurring shape here — a
 * gate measures exactly what it was written for and is silent about the thing beside it — and the
 * fallback is what renders when `/rooms` fails, so the drift would have shown a user one description
 * of a room normally and a different one during an outage.
 */
function pythonRooms(): Room[] {
  const src = readFileSync(ROOMS_PY, "utf8");
  const block = src.slice(src.indexOf("ROOMS: list"), src.indexOf("ROOM_IDS ="));
  expect(block.length, "could not locate the ROOMS table — rooms.py was restructured").toBeGreaterThan(100);
  const rooms = [...block.matchAll(/\{"id":\s*"([^"]+)",\s*"label":\s*"([^"]+)",\s*"job":\s*"([^"]+)"/g)]
    .map((m) => [m[1]!, m[2]!, m[3]!] as Room);
  // A regex that silently matches nothing would make every assertion below vacuously pass — the
  // failure mode a parser-backed test is most prone to.
  expect(rooms.length, "parsed no rooms from rooms.py — the literal's shape changed").toBeGreaterThan(3);
  return rooms;
}

/** The settled answer. Spelled out here so changing it is a deliberate edit to a test, not a drift. */
// The ORDER is asserted with toEqual, deliberately: it is a user decision (2026-07-29), the deal
// first because it authorizes everything after it and the finished asset last because operating it is
// the longest phase. Note this is the *unweighted* order — `orderRooms()` promotes a workspace's own
// room to the front, so a Construction user still opens on Schedule. That is the weighting working.
const PROFESSIONAL: Room[] = [
  ["deal", "Deal", "Underwrite it, fund it, lease it and dispose of it"],
  ["design", "Design", "Model it, draw it, specify it — the architect's and engineer's room"],
  ["planning", "Planning", "Take it off, estimate it, bid it, buy it out, contract it and get it approved"],
  // R41-WORK-FIELD, 2026-08-02. Schedule's job said "run the field", and Work's said "whatever is in
  // your court right now" — which is precisely why Work held ZERO registers while Schedule held 38.
  // "Work" was read by the code as *my* work (an inbox) and by every user as *the* work (the
  // jobsite). Settling it the users' way splits the two jobs onto the two people who actually do
  // them: the planner keeps the CPM, the crews and the controls; the superintendent gets the day,
  // the safety programme, the progress, the deliveries and the punch. Closeout went to Operate in
  // the same change — an as-built is read by whoever runs the building, not by whoever filed it.
  ["schedule", "Schedule", "Sequence it, resource it and control it — the plan for time"],
  ["cost", "Cost", "Budget it, change it, bill it and account for it"],
  ["work", "Work", "Run the field — your court today, the log, safety, progress and the punch"],
  // R30, 2026-07-29. Facilities management had no room: it was sectioned "Operations" and therefore
  // filed under Deal, so a technician logging a work order opened a tab labelled "underwrite it, fund
  // it, lease it and dispose of it". "Operate" is the professional term for the phase.
  ["operate", "Operate", "Hand it over, maintain it, meter it and plan its renewal"],
];

describe("the rooms are named in professional terms", () => {
  it("the server's table is exactly the settled set, in order", () => {
    expect(pythonRooms()).toEqual(PROFESSIONAL);
  });

  it("the web's fallback agrees with the server — id, label AND job", () => {
    // Not just the ids — `spine.test` already covers those. The label is what a user reads on the
    // tab and the job is what they read under it; both were duplicated across a language boundary
    // with nothing asserting they matched, and the job half drifted within a day of the label half
    // being guarded. The fallback is what renders when `/rooms` fails, so a divergence would rename
    // or re-describe a room at the exact moment the app is already misbehaving.
    expect(FALLBACK_ROOMS.map((r) => [r.id, r.label, r.job])).toEqual(pythonRooms());
  });

  it("no room carries a plain-language name from the prototype", () => {
    // The specific reversal this records. If one of these ever appears, it is a decision being
    // re-made — which is fine, but it should not happen by someone copying an old mock.
    const PROTOTYPE = ["building", "budget", "timeline", "money", "my to-do", "todo"];
    for (const [, label] of pythonRooms()) {
      expect(PROTOTYPE, `"${label}" is a prototype name; ROOM-NAMING settled on professional terms`)
        .not.toContain(label.toLowerCase());
    }
  });

  it("every id in the spine is one of the seven", () => {
    expect([...ROOM_IDS].sort()).toEqual(PROFESSIONAL.map(([id]) => id).sort());
  });

  it("every room states what it is for", () => {
    // `test_module_rooms.py` asserts the same minimum server-side. Both sides, because a room whose
    // job is a placeholder is a tab nobody can decide whether to open.
    for (const [id, , job] of pythonRooms()) {
      expect(job.length, `${id} needs a plain statement of what it is for`).toBeGreaterThan(25);
    }
  });
});
