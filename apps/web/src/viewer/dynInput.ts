// SNAP-KIT phase 2 + R38-DIM-INPUT — dynamic-input constraint capture (pure, unit-tested).
//
// While a draw tool is armed, the drafter TYPES the constraint mid-draw — "6" (distance), "<30"
// (angle°), "6<30" (both) — and the next click is constrained through `applyDynamicInput`. This module
// is the pure half: an append/backspace keystroke buffer and its parser. The viewer owns only the HUD
// element and the keydown wiring.

export type DynConstraint = { distance?: number; angle?: number };

const FT = 0.3048;

/** Parse the distance part: metric decimal ("6", "2.5") OR imperial ("12'6", "12'6.5", "12'", '30"').
 *  Imperial converts to metres — the model is metric; the KEYBOARD is whatever the drafter thinks in.
 *  Returns metres, or null when the text is not a well-formed positive length. */
function parseDistance(s: string): number | null {
  const imp = /^(\d+(?:\.\d+)?)'(\d+(?:\.\d+)?)?"?$/.exec(s);   // 12'6 · 12'6.5 · 12' · 12'6"
  if (imp) {
    const feet = Number(imp[1]);
    const inches = imp[2] !== undefined ? Number(imp[2]) : 0;
    if (!Number.isFinite(feet) || !Number.isFinite(inches) || inches >= 12) return null;
    const m = (feet + inches / 12) * FT;
    return m > 0 ? m : null;
  }
  const inch = /^(\d+(?:\.\d+)?)"$/.exec(s);                    // 30" — inches only
  if (inch) {
    const m = (Number(inch[1]) / 12) * FT;
    return Number.isFinite(m) && m > 0 ? m : null;
  }
  const d = Number(s);
  return Number.isFinite(d) && d > 0 ? d : null;
}

/** Parse a typed buffer into a constraint. Grammar (CAD-familiar):
 *  `6` → distance 6 m · `12'6` → 12 ft 6 in, converted to metres · `<30` → bearing 30° (CCW from
 *  east) · `6<30` / `12'6<30` → both.
 *  Empty/partial-but-invalid → null (the HUD shows the raw buffer until it parses). Strict like the
 *  CAD command line: exactly one `<`, both present sides well-formed, distance > 0, inches < 12. */
export function parseDynConstraint(buf: string): DynConstraint | null {
  const s = (buf || "").trim();
  if (!s) return null;
  const i = s.indexOf("<");
  if (i !== s.lastIndexOf("<")) return null;                  // more than one '<'
  const dPart = i >= 0 ? s.slice(0, i) : s;
  const aPart = i >= 0 ? s.slice(i + 1) : "";
  const out: DynConstraint = {};
  if (dPart !== "") {
    const d = parseDistance(dPart);
    if (d === null) return null;
    out.distance = d;
  }
  if (i >= 0) {
    if (aPart === "") return null;                            // "6<" — angle started but missing
    const a = Number(aPart);
    if (!Number.isFinite(a)) return null;
    out.angle = a;
  }
  return out.distance === undefined && out.angle === undefined ? null : out;
}

/** Is this keystroke part of the dynamic-input grammar? (digits, '.', '-', '<', feet/inch marks) */
export function isDynKey(key: string): boolean {
  return /^[0-9.<'"-]$/.test(key);
}

/** Apply one keystroke to the buffer. Returns the new buffer (Backspace trims; dyn keys append;
 *  anything else leaves it unchanged — the caller decides what clears it). */
export function dynKeystroke(buf: string, key: string): string {
  if (key === "Backspace") return buf.slice(0, -1);
  if (isDynKey(key)) return buf + key;
  return buf;
}

/** Human echo of a parsed constraint for the HUD: always metres (the model's unit), so a typed
 *  "12'6" answers back "3.81 m" and the conversion is visible before the click commits it. */
export function formatDynConstraint(c: DynConstraint): string {
  const d = c.distance !== undefined ? `${+c.distance.toFixed(3)} m` : "";
  const a = c.angle !== undefined ? `${d ? " @ " : "@ "}${c.angle}°` : "";
  return `${d}${a}`;
}
