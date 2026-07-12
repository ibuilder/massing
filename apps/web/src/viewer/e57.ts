/**
 * E57 (ASTM E2807) reality-capture reader — in-browser, fully offline (no server round-trip, no WASM).
 *
 * E57 is the interoperable laser-scan exchange format. A `.e57` file is:
 *   1. a 48-byte header (signature, version, section offsets, page size);
 *   2. a **CRC-paged** physical layout — the file is cut into `pageSize` pages, the last 4 bytes of each
 *      page are a CRC, so a *logical* byte stream is the payload with the checksums stripped;
 *   3. an XML section describing each `Data3D` scan: a `CompressedVector` of points whose `prototype`
 *      names the fields (cartesianX/Y/Z, colorRed/Green/Blue) and their node types (Float or
 *      ScaledInteger with min/max/scale/offset);
 *   4. per-scan **binary sections** of bit-packed records.
 *
 * This decoder handles the encodings emitted by common scanners/exporters — Float (single/double) and
 * ScaledInteger XYZ with optional RGB, across one or more data packets. Anything it doesn't recognise
 * (exotic node types, index-only files, structure it can't parse) raises {@link E57Unsupported} so the
 * caller can fall back to the server-side `pye57` conversion. Coordinates are centred on the cloud bbox
 * midpoint and stride-decimated to the render budget, matching the LAS/LAZ path.
 */
import { MAX_POINTS, type PointCloud } from "./pointcloud";

/** Thrown when the file is valid E57 but uses an encoding this in-browser decoder doesn't cover — the
 *  caller should fall back to the server converter rather than treat the file as broken. */
export class E57Unsupported extends Error {
  constructor(message: string) { super(message); this.name = "E57Unsupported"; }
}

const SIGNATURE = "ASTM-E57";

interface E57Header { xmlOffsetPhys: number; xmlLength: number; pageSize: number; }

function parseHeader(dv: DataView): E57Header {
  let sig = "";
  for (let i = 0; i < 8; i++) sig += String.fromCharCode(dv.getUint8(i));
  if (sig !== SIGNATURE) throw new Error("Not an E57 file (missing ASTM-E57 signature).");
  const xmlOffsetPhys = Number(dv.getBigUint64(24, true));
  const xmlLength = Number(dv.getBigUint64(32, true));
  const pageSize = Number(dv.getBigUint64(40, true));
  if (!pageSize || pageSize <= 4) throw new E57Unsupported("E57 page size is invalid.");
  return { xmlOffsetPhys, xmlLength, pageSize };
}

/** Read `len` *logical* bytes (checksums stripped) starting at a *physical* file offset. */
function readLogical(bytes: Uint8Array, physOffset: number, len: number, pageSize: number): Uint8Array {
  const payload = pageSize - 4;                 // bytes of real data per page (last 4 are the CRC)
  const out = new Uint8Array(len);
  let written = 0;
  let phys = physOffset;
  while (written < len) {
    const page = Math.floor(phys / pageSize);
    const within = phys - page * pageSize;
    if (within >= payload) {                     // sitting in a CRC → jump to the next page's payload
      phys = (page + 1) * pageSize;
      continue;
    }
    const take = Math.min(payload - within, len - written, bytes.length - phys);
    if (take <= 0) throw new E57Unsupported("E57 section runs past end of file.");
    out.set(bytes.subarray(phys, phys + take), written);
    written += take;
    phys += take;
  }
  return out;
}

/** Convert a physical offset to its logical position (for offsets that the format stores as physical). */
function physToLogical(phys: number, pageSize: number): number {
  const page = Math.floor(phys / pageSize);
  return page * (pageSize - 4) + (phys - page * pageSize);
}

interface FieldDef {
  name: string;                                  // cartesianX | colorRed | …
  kind: "float" | "int";
  min: number; max: number; scale: number; offset: number; bits: number; precision: 4 | 8;
}
interface ScanDef { fields: FieldDef[]; recordCount: number; cvOffsetPhys: number; }

function intBits(min: number, max: number): number {
  const range = max - min;
  if (range <= 0) return 0;
  return Math.ceil(Math.log2(range + 1));
}

function fieldFromNode(name: string, el: Element): FieldDef | null {
  const type = el.getAttribute("type");
  if (type === "Float") {
    const prec = (el.getAttribute("precision") || "double") === "single" ? 4 : 8;
    return { name, kind: "float", min: 0, max: 0, scale: 1, offset: 0, bits: 0, precision: prec };
  }
  if (type === "Integer" || type === "ScaledInteger") {
    const num = (a: string, d: number) => { const v = el.getAttribute(a); return v == null ? d : Number(v); };
    const min = num("minimum", 0), max = num("maximum", 0);
    const scale = type === "ScaledInteger" ? num("scale", 1) : 1;
    const offset = type === "ScaledInteger" ? num("offset", 0) : 0;
    return { name, kind: "int", min, max, scale, offset, bits: intBits(min, max), precision: 8 };
  }
  return null;                                    // unknown node type
}

const WANTED = new Set(["cartesianX", "cartesianY", "cartesianZ", "colorRed", "colorGreen", "colorBlue"]);
// Canonicalise field tag names — some XML parsers lower-case element tags, so map back to the E57 spelling.
const CANON: Record<string, string> = {};
for (const nm of ["cartesianX", "cartesianY", "cartesianZ", "colorRed", "colorGreen", "colorBlue"]) CANON[nm.toLowerCase()] = nm;
const canonName = (tag: string): string => CANON[tag.toLowerCase()] ?? tag;

function parseXml(xml: string): ScanDef[] {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.getElementsByTagName("parsererror").length) throw new E57Unsupported("E57 XML section did not parse.");
  const scans: ScanDef[] = [];
  // getElementsByTagName is case-sensitive (XML) + namespace-tolerant. Each "points" node is a scan's
  // CompressedVector; its first "prototype" descendant names the record fields.
  const pointNodes = Array.from(doc.getElementsByTagName("points"));
  for (const cv of pointNodes) {
    const recordCount = Number(cv.getAttribute("recordCount") || 0);
    const cvOffsetPhys = Number(cv.getAttribute("fileOffset") || 0);
    const proto = cv.getElementsByTagName("prototype")[0];
    if (!proto || !cvOffsetPhys || !recordCount) continue;
    const fields: FieldDef[] = [];
    for (const child of Array.from(proto.children)) {
      const f = fieldFromNode(canonName(child.tagName), child);
      if (!f) throw new E57Unsupported(`E57 prototype field ${child.tagName} uses an unsupported node type.`);
      fields.push(f);
    }
    if (fields.length) scans.push({ fields, recordCount, cvOffsetPhys });
  }
  if (!scans.length) throw new E57Unsupported("No decodable Data3D point set found in the E57.");
  return scans;
}

/** Split the CompressedVector binary into one concatenated byte buffer per prototype field. */
function collectByteStreams(bytes: Uint8Array, scan: ScanDef, pageSize: number): Uint8Array[] {
  const nFields = scan.fields.length;
  // section header: uint8 id(==1) + 7 reserved + uint64 sectionLen + uint64 dataOffset + uint64 indexOffset
  const hdr = readLogical(bytes, scan.cvOffsetPhys, 32, pageSize);
  const hv = new DataView(hdr.buffer, hdr.byteOffset, hdr.byteLength);
  if (hv.getUint8(0) !== 1) throw new E57Unsupported("E57 CompressedVector section header not recognised.");
  const sectionLen = Number(hv.getBigUint64(8, true));
  const dataOffsetPhys = Number(hv.getBigUint64(16, true));
  const sectionEndLogical = physToLogical(scan.cvOffsetPhys, pageSize) + sectionLen;

  const buffers: number[][] = Array.from({ length: nFields }, () => []);
  let packetLogical = physToLogical(dataOffsetPhys, pageSize);
  let guard = 0;
  while (packetLogical < sectionEndLogical) {
    if (++guard > 5_000_000) throw new E57Unsupported("E57 packet stream did not terminate.");
    // logical→physical for readLogical (which expects a physical offset)
    const page = Math.floor(packetLogical / (pageSize - 4));
    const packetPhys = page * pageSize + (packetLogical - page * (pageSize - 4));
    const head = readLogical(bytes, packetPhys, 6, pageSize);
    const hd = new DataView(head.buffer, head.byteOffset, head.byteLength);
    const packetType = hd.getUint8(0);
    const packetLen = hd.getUint16(2, true) + 1;
    if (packetType === 1) {                        // data packet
      const bsCount = hd.getUint16(4, true);
      const full = readLogical(bytes, packetPhys, packetLen, pageSize);
      const fv = new DataView(full.buffer, full.byteOffset, full.byteLength);
      let p = 6;
      const lengths: number[] = [];
      for (let i = 0; i < bsCount; i++) { lengths.push(fv.getUint16(p, true)); p += 2; }
      for (let i = 0; i < bsCount; i++) {
        const buf = buffers[i];
        if (buf) for (let b = 0; b < lengths[i]!; b++) buf.push(full[p + b]!);
        p += lengths[i]!;
      }
    }
    packetLogical += packetLen;
  }
  return buffers.map((b) => Uint8Array.from(b));
}

/** Decode one field's concatenated byte buffer into `count` numeric values. */
function decodeField(buf: Uint8Array, f: FieldDef, count: number): Float64Array {
  const out = new Float64Array(count);
  if (f.kind === "float") {
    const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
    for (let i = 0; i < count; i++) {
      const off = i * f.precision;
      if (off + f.precision > buf.length) throw new E57Unsupported("E57 float stream shorter than record count.");
      out[i] = f.precision === 4 ? dv.getFloat32(off, true) : dv.getFloat64(off, true);
    }
    return out;
  }
  if (f.bits === 0) { out.fill(f.offset + f.scale * f.min); return out; }   // constant field
  let bitPos = 0;
  for (let i = 0; i < count; i++) {
    let raw = 0;
    for (let b = 0; b < f.bits; b++) {                     // LSB-first bit unpack across the byte stream
      const byteIdx = bitPos >> 3;
      if (byteIdx >= buf.length) throw new E57Unsupported("E57 packed stream shorter than record count.");
      const bit = (buf[byteIdx]! >> (bitPos & 7)) & 1;
      raw |= bit << b;
      bitPos++;
    }
    out[i] = f.offset + f.scale * (f.min + raw);
  }
  return out;
}

/** Parse an E57 file into flat point arrays. Throws {@link E57Unsupported} for encodings to defer to the
 *  server. Reads every Data3D scan and merges them into one decimated cloud. */
export function readE57(bytes: Uint8Array): PointCloud {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const h = parseHeader(dv);
  const xml = new TextDecoder().decode(readLogical(bytes, h.xmlOffsetPhys, h.xmlLength, h.pageSize));
  const scans = parseXml(xml);

  // decode every scan's fields, tracking totals + bbox for centring
  const decoded = scans.map((scan) => {
    const streams = collectByteStreams(bytes, scan, h.pageSize);
    const cols: Record<string, Float64Array> = {};
    scan.fields.forEach((f, i) => {
      if (WANTED.has(f.name)) cols[f.name] = decodeField(streams[i]!, f, scan.recordCount);
    });
    if (!cols.cartesianX || !cols.cartesianY || !cols.cartesianZ)
      throw new E57Unsupported("E57 scan has no cartesian XYZ (spherical-only not supported in-browser).");
    return { count: scan.recordCount, cols, hasColor: !!(cols.colorRed && cols.colorGreen && cols.colorBlue) };
  });

  const total = decoded.reduce((s, d) => s + d.count, 0);
  if (!total) throw new E57Unsupported("E57 decoded to zero points.");
  // bbox for centring
  let minX = Infinity, minY = Infinity, minZ = Infinity, maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  let maxColor = 0;
  for (const d of decoded) {
    const { cartesianX: X, cartesianY: Y, cartesianZ: Z } = d.cols;
    for (let i = 0; i < d.count; i++) {
      if (X![i]! < minX) minX = X![i]!; if (X![i]! > maxX) maxX = X![i]!;
      if (Y![i]! < minY) minY = Y![i]!; if (Y![i]! > maxY) maxY = Y![i]!;
      if (Z![i]! < minZ) minZ = Z![i]!; if (Z![i]! > maxZ) maxZ = Z![i]!;
    }
    if (d.hasColor) for (const k of ["colorRed", "colorGreen", "colorBlue"]) {
      const c = d.cols[k]!; for (let i = 0; i < d.count; i++) if (c[i]! > maxColor) maxColor = c[i]!;
    }
  }
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2, cz = (minZ + maxZ) / 2;
  const stride = total > MAX_POINTS ? Math.ceil(total / MAX_POINTS) : 1;
  const n = Math.floor((total + stride - 1) / stride);
  const pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
  const cdiv = maxColor > 255 ? 65535 : (maxColor > 1 ? 255 : 1);

  let w = 0, seen = 0;
  for (const d of decoded) {
    const { cartesianX: X, cartesianY: Y, cartesianZ: Z, colorRed: R, colorGreen: G, colorBlue: B } = d.cols;
    for (let i = 0; i < d.count; i++, seen++) {
      if (seen % stride !== 0) continue;
      pos[w * 3] = X![i]! - cx; pos[w * 3 + 1] = Y![i]! - cy; pos[w * 3 + 2] = Z![i]! - cz;
      if (d.hasColor) { col[w * 3] = R![i]! / cdiv; col[w * 3 + 1] = G![i]! / cdiv; col[w * 3 + 2] = B![i]! / cdiv; }
      else { col[w * 3] = col[w * 3 + 1] = col[w * 3 + 2] = 0.72; }   // uncoloured → neutral grey
      w++;
    }
  }
  return { positions: pos.subarray(0, w * 3), colors: col.subarray(0, w * 3), count: w, sourceCount: total, decimated: w < total };
}
