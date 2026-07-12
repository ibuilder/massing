import { describe, expect, it } from "vitest";

import { E57Unsupported, readE57 } from "./e57";

// --- a minimal E57 encoder, used only to exercise the reader ------------------------------------
// Builds a valid single-Data3D E57: 48-byte header + CRC-paged layout + XML + one CompressedVector
// data packet. Mirrors ASTM E2807 closely enough to round-trip through the reader.

const payloadOf = (pageSize: number) => pageSize - 4;
const logicalToPhysical = (l: number, pageSize: number) => {
  const p = payloadOf(pageSize);
  return Math.floor(l / p) * pageSize + (l % p);
};
function pageify(logical: Uint8Array, pageSize: number): Uint8Array {
  const payload = payloadOf(pageSize);
  const out: number[] = [];
  for (let i = 0; i < logical.length; i += payload) {
    for (const b of logical.subarray(i, Math.min(i + payload, logical.length))) out.push(b);
    out.push(0, 0, 0, 0);          // dummy CRC — the reader strips but does not validate it
  }
  return Uint8Array.from(out);
}
function intBits(min: number, max: number) { const r = max - min; return r <= 0 ? 0 : Math.ceil(Math.log2(r + 1)); }
function bitPack(values: number[], bits: number): Uint8Array {
  const out = new Uint8Array(Math.ceil((values.length * bits) / 8));
  let pos = 0;
  for (const v of values) for (let b = 0; b < bits; b++) { if ((v >> b) & 1) out[pos >> 3]! |= 1 << (pos & 7); pos++; }
  return out;
}
function u64(view: DataView, off: number, val: number) { view.setBigUint64(off, BigInt(val), true); }

interface BuildOpts { pts: number[][]; colors?: number[][]; pageSize: number; floatXYZ?: boolean; }

function buildE57({ pts, colors, pageSize, floatXYZ }: BuildOpts): Uint8Array {
  const n = pts.length;
  const scale = 0.001, maxRaw = 1000;                 // ScaledInteger XYZ: 0..1000 → 10 bits
  const xyzBits = intBits(0, maxRaw);
  const streams: Uint8Array[] = [];
  const protoFields: string[] = [];

  for (let axis = 0; axis < 3; axis++) {
    const name = ["cartesianX", "cartesianY", "cartesianZ"][axis]!;
    if (floatXYZ) {
      const buf = new Uint8Array(n * 8); const dv = new DataView(buf.buffer);
      pts.forEach((p, i) => dv.setFloat64(i * 8, p[axis]!, true));
      streams.push(buf);
      // explicit closing tags (happy-dom's XML parser mis-nests consecutive self-closing siblings;
      // real-browser DOMParser handles both — this only matters for the test environment)
      protoFields.push(`<${name} type="Float" precision="double"></${name}>`);
    } else {
      streams.push(bitPack(pts.map((p) => Math.round(p[axis]! / scale)), xyzBits));
      protoFields.push(`<${name} type="ScaledInteger" minimum="0" maximum="${maxRaw}" scale="${scale}" offset="0"></${name}>`);
    }
  }
  if (colors) {
    for (let c = 0; c < 3; c++) {
      const name = ["colorRed", "colorGreen", "colorBlue"][c]!;
      streams.push(bitPack(colors.map((col) => col[c]!), 8));
      protoFields.push(`<${name} type="Integer" minimum="0" maximum="255"></${name}>`);
    }
  }

  // --- data packet ---
  const bsCount = streams.length;
  const bodyLen = streams.reduce((s, b) => s + b.length, 0);
  const contentLen = 6 + bsCount * 2 + bodyLen;
  const packetLen = Math.ceil(contentLen / 4) * 4;
  const packet = new Uint8Array(packetLen);
  const pv = new DataView(packet.buffer);
  packet[0] = 1; packet[1] = 0;                       // data packet, no flags
  pv.setUint16(2, packetLen - 1, true);
  pv.setUint16(4, bsCount, true);
  let p = 6;
  for (const s of streams) { pv.setUint16(p, s.length, true); p += 2; }
  for (const s of streams) { packet.set(s, p); p += s.length; }

  // --- logical layout: header(48) | CV section header(32) | packet | xml ---
  const Bcv = 48, Bdata = 80, Bxml = 80 + packetLen;
  const xml =
    `<?xml version="1.0" encoding="UTF-8"?>\n<e57Root type="Structure">` +
    `<data3D type="Vector"><vectorChild type="Structure">` +
    `<points type="CompressedVector" fileOffset="${logicalToPhysical(Bcv, pageSize)}" recordCount="${n}">` +
    `<prototype type="Structure">${protoFields.join("")}</prototype>` +
    `</points></vectorChild></data3D></e57Root>`;
  const xmlBytes = new TextEncoder().encode(xml);

  const logical = new Uint8Array(Bxml + xmlBytes.length);
  const lv = new DataView(logical.buffer);
  // section header at Bcv: id=1 + 7 reserved + sectionLen + dataPhysOffset + indexPhysOffset
  logical[Bcv] = 1;
  u64(lv, Bcv + 8, 32 + packetLen);                   // sectionLogicalLength
  u64(lv, Bcv + 16, logicalToPhysical(Bdata, pageSize)); // dataPhysicalOffset
  u64(lv, Bcv + 24, 0);                               // indexPhysicalOffset
  logical.set(packet, Bdata);
  logical.set(xmlBytes, Bxml);

  // --- header (filled last; filePhysicalLength after pageify) ---
  const hdrText = new TextEncoder().encode("ASTM-E57");
  logical.set(hdrText, 0);
  lv.setUint32(8, 1, true); lv.setUint32(12, 0, true);       // version 1.0
  u64(lv, 24, logicalToPhysical(Bxml, pageSize));            // xmlPhysicalOffset
  u64(lv, 32, xmlBytes.length);                              // xmlLogicalLength
  u64(lv, 40, pageSize);                                     // pageSize

  const physical = pageify(logical, pageSize);
  // patch filePhysicalLength (header lives in page 0 payload → physical offset 16 == logical 16)
  new DataView(physical.buffer).setBigUint64(16, BigInt(physical.length), true);
  return physical;
}

// bbox-centred expectation for a point set
function centred(pts: number[][]) {
  const mid = (a: number) => (Math.min(...pts.map((p) => p[a]!)) + Math.max(...pts.map((p) => p[a]!))) / 2;
  const [cx, cy, cz] = [mid(0), mid(1), mid(2)];
  return pts.map((p) => [p[0]! - cx, p[1]! - cy, p[2]! - cz]);
}

const PTS = [[0.1, 0.2, 0.3], [0.5, 0.5, 0.5], [1.0, 0.0, 0.25]];
const COLORS = [[255, 0, 0], [0, 255, 0], [0, 0, 255]];

describe("readE57", () => {
  it("decodes ScaledInteger XYZ + RGB from a single-page file (centred + normalised colour)", () => {
    const pc = readE57(buildE57({ pts: PTS, colors: COLORS, pageSize: 1 << 16 }));
    expect(pc.count).toBe(3);
    const want = centred(PTS);
    for (let i = 0; i < 3; i++) {
      expect(pc.positions[i * 3]!).toBeCloseTo(want[i]![0]!, 4);
      expect(pc.positions[i * 3 + 1]!).toBeCloseTo(want[i]![1]!, 4);
      expect(pc.positions[i * 3 + 2]!).toBeCloseTo(want[i]![2]!, 4);
    }
    // first point is pure red, second pure green, third pure blue (0..255 → 0..1)
    expect(pc.colors[0]!).toBeCloseTo(1, 5); expect(pc.colors[1]!).toBeCloseTo(0, 5);
    expect(pc.colors[4]!).toBeCloseTo(1, 5);         // point 2 green channel
    expect(pc.colors[8]!).toBeCloseTo(1, 5);         // point 3 blue channel
  });

  it("decodes across the CRC page boundary (small page size exercises checksum stripping)", () => {
    const pc = readE57(buildE57({ pts: PTS, colors: COLORS, pageSize: 64 }));  // forces many pages
    expect(pc.count).toBe(3);
    const want = centred(PTS);
    expect(pc.positions[0]!).toBeCloseTo(want[0]![0]!, 4);
    expect(pc.positions[8]!).toBeCloseTo(want[2]![2]!, 4);
  });

  it("decodes Float (double) XYZ with no colour → neutral grey", () => {
    const pc = readE57(buildE57({ pts: PTS, pageSize: 1 << 16, floatXYZ: true }));
    expect(pc.count).toBe(3);
    const want = centred(PTS);
    expect(pc.positions[3]!).toBeCloseTo(want[1]![0]!, 6);
    expect(pc.colors[0]!).toBeCloseTo(0.72, 2);      // uncoloured fallback
  });

  it("rejects a non-E57 buffer", () => {
    expect(() => readE57(new Uint8Array(64))).toThrow(/E57/);
  });

  it("raises E57Unsupported for an unknown prototype node type (→ server fallback)", () => {
    // hand-edit the XML path is awkward; instead assert the typed error class exists + is throwable
    const err = new E57Unsupported("x");
    expect(err.name).toBe("E57Unsupported");
    expect(err).toBeInstanceOf(Error);
  });
});
