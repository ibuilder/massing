// SNAP-KIT phase 2 — dynamic-input constraint capture (pure, unit-tested).
//
// While a draw tool is armed, the drafter TYPES the constraint mid-draw — "6" (distance), "<30"
// (angle°), "6<30" (both) — and the next click is constrained through `applyDynamicInput`. This module
// is the pure half: an append/backspace keystroke buffer and its parser. The viewer owns only the HUD
// element and the keydown wiring.

export type DynConstraint = { distance?: number; angle?: number };

/** Parse a typed buffer into a constraint. Grammar (AutoCAD-familiar):
 *  `6` → distance 6 m · `<30` → bearing 30° (CCW from east) · `6<30` → both.
 *  Empty/partial-but-invalid → null (the HUD shows the raw buffer until it parses). Strict like the
 *  CAD command line: exactly one `<`, both present sides numeric, distance > 0. */
export function parseDynConstraint(buf: string): DynConstraint | null {
  const s = (buf || "").trim();
  if (!s) return null;
  const i = s.indexOf("<");
  if (i !== s.lastIndexOf("<")) return null;                  // more than one '<'
  const dPart = i >= 0 ? s.slice(0, i) : s;
  const aPart = i >= 0 ? s.slice(i + 1) : "";
  const out: DynConstraint = {};
  if (dPart !== "") {
    const d = Number(dPart);
    if (!Number.isFinite(d) || d <= 0) return null;
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

/** Is this keystroke part of the dynamic-input grammar? (digits, '.', '-', '<') */
export function isDynKey(key: string): boolean {
  return /^[0-9.<-]$/.test(key);
}

/** Apply one keystroke to the buffer. Returns the new buffer (Backspace trims; dyn keys append;
 *  anything else leaves it unchanged — the caller decides what clears it). */
export function dynKeystroke(buf: string, key: string): string {
  if (key === "Backspace") return buf.slice(0, -1);
  if (isDynKey(key)) return buf + key;
  return buf;
}
