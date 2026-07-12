/**
 * LAS / LAZ point-cloud reader → flat XYZ + RGB arrays for a THREE.Points geometry.
 *
 * LAS is an uncompressed binary point format; LAZ is the LASZip-compressed variant. In BOTH the
 * public header + VLRs stay uncompressed at the start of the file, so we parse the header ourselves
 * (scale/offset/format/count) and only need laz-perf to decode the compressed *point records* for
 * .laz. laz-perf's WASM is vendored into public/wasm/ (offline — CLAUDE.md non-negotiable).
 *
 * Big clouds are stride-decimated to a render budget so the browser stays responsive; coordinates
 * are centred on the header bbox midpoint (LAS coords are often huge UTM values that wreck float32
 * precision if rendered raw).
 */
import createLazPerf from "laz-perf";

export interface PointCloud {
  positions: Float32Array;        // xyz triples, centred on the cloud's midpoint
  colors: Float32Array;           // rgb triples 0..1 (RGB if present, else intensity grayscale)
  count: number;                  // points actually loaded (after decimation)
  sourceCount: number;            // points in the file
  decimated: boolean;
}

/** Keep the browser responsive: cap rendered points and stride-sample beyond this. */
export const MAX_POINTS = 5_000_000;

interface LasHeader {
  pointDataOffset: number; pointFormat: number; pointLength: number; count: number;
  scaleX: number; scaleY: number; scaleZ: number; offX: number; offY: number; offZ: number;
  cx: number; cy: number; cz: number;     // bbox-midpoint centre (subtracted from every point)
}

function parseHeader(dv: DataView): LasHeader {
  const sig = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
  if (sig !== "LASF") throw new Error("Not a LAS/LAZ file (missing LASF signature).");
  const versionMinor = dv.getUint8(25);
  const pointDataOffset = dv.getUint32(96, true);
  const pointFormat = dv.getUint8(104) & 0b0011_1111;       // strip the LAZ compression bit (0x80)
  const pointLength = dv.getUint16(105, true);
  let count = dv.getUint32(107, true);                       // legacy point count
  const scaleX = dv.getFloat64(131, true), scaleY = dv.getFloat64(139, true), scaleZ = dv.getFloat64(147, true);
  const offX = dv.getFloat64(155, true), offY = dv.getFloat64(163, true), offZ = dv.getFloat64(171, true);
  const maxX = dv.getFloat64(179, true), minX = dv.getFloat64(187, true);
  const maxY = dv.getFloat64(195, true), minY = dv.getFloat64(203, true);
  const maxZ = dv.getFloat64(211, true), minZ = dv.getFloat64(219, true);
  if (count === 0 && versionMinor >= 4) count = Number(dv.getBigUint64(247, true)); // LAS 1.4 extended count
  return {
    pointDataOffset, pointFormat, pointLength, count,
    scaleX, scaleY, scaleZ, offX, offY, offZ,
    cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, cz: (minZ + maxZ) / 2,
  };
}

/** Byte offset of the RGB uint16 triplet within a point record for a given format, or -1 if none. */
function rgbOffset(fmt: number): number {
  if (fmt === 2) return 20;              // fmt0(20) + RGB
  if (fmt === 3 || fmt === 5) return 28; // fmt1(28, +GPS) + RGB
  if (fmt === 7 || fmt === 8 || fmt === 10) return 30; // LAS 1.4 base(30) + RGB
  return -1;
}

interface Sink { pos: Float32Array; col: Float32Array; colOff: number; recLen: number; max: number; }

/** Write point `w` from one LAS point record into the output arrays; track the max raw colour. */
function emit(dv: DataView, h: LasHeader, s: Sink, w: number): void {
  s.pos[w * 3] = dv.getInt32(0, true) * h.scaleX + h.offX - h.cx;
  s.pos[w * 3 + 1] = dv.getInt32(4, true) * h.scaleY + h.offY - h.cy;
  s.pos[w * 3 + 2] = dv.getInt32(8, true) * h.scaleZ + h.offZ - h.cz;
  if (s.colOff >= 0 && s.colOff + 6 <= s.recLen) {
    const r = dv.getUint16(s.colOff, true), g = dv.getUint16(s.colOff + 2, true), b = dv.getUint16(s.colOff + 4, true);
    s.col[w * 3] = r; s.col[w * 3 + 1] = g; s.col[w * 3 + 2] = b;
    if (r > s.max) s.max = r; if (g > s.max) s.max = g; if (b > s.max) s.max = b;
  } else {
    const it = dv.getUint16(12, true) / 65535;              // intensity → grayscale
    s.col[w * 3] = it; s.col[w * 3 + 1] = it; s.col[w * 3 + 2] = it;
  }
}

function alloc(h: LasHeader, recLen: number): { sink: Sink; stride: number; n: number } {
  const stride = h.count > MAX_POINTS ? Math.ceil(h.count / MAX_POINTS) : 1;
  const n = Math.floor((h.count + stride - 1) / stride);
  return { sink: { pos: new Float32Array(n * 3), col: new Float32Array(n * 3), colOff: rgbOffset(h.pointFormat), recLen, max: 0 }, stride, n };
}

function finish(h: LasHeader, s: Sink, w: number): PointCloud {
  if (s.colOff >= 0 && s.max > 0) {                         // normalise RGB to 0..1 (8- or 16-bit packed)
    const div = s.max > 255 ? 65535 : 255;
    for (let i = 0; i < w * 3; i++) { const c = s.col[i]; if (c !== undefined && c > 1) s.col[i] = c / div; }
  }
  return { positions: s.pos.subarray(0, w * 3), colors: s.col.subarray(0, w * 3), count: w, sourceCount: h.count, decimated: w < h.count };
}

/** Parse an uncompressed .las file. */
function readLas(bytes: Uint8Array): PointCloud {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const h = parseHeader(dv);
  const { sink, stride } = alloc(h, h.pointLength);
  let w = 0;
  for (let i = 0; i < h.count; i += stride) {
    const rec = new DataView(bytes.buffer, bytes.byteOffset + h.pointDataOffset + i * h.pointLength, h.pointLength);
    emit(rec, h, sink, w++);
  }
  return finish(h, sink, w);
}

let lazModule: Promise<LazPerfModule> | null = null;
interface LazPerfModule {
  _malloc(n: number): number; _free(p: number): void; HEAPU8: Uint8Array;
  LASZip: new () => { open(p: number, len: number): void; getPoint(p: number): void;
    getPointLength(): number; getCount(): number; delete(): void };
}
function laz(): Promise<LazPerfModule> {
  if (!lazModule) {
    lazModule = (createLazPerf as unknown as (o: object) => Promise<LazPerfModule>)({
      locateFile: (f: string) => import.meta.env.BASE_URL + "wasm/" + f,
    });
  }
  return lazModule;
}

/** Decode a LAZ file via laz-perf, reading records sequentially and keeping the strided ones. */
async function readLaz(bytes: Uint8Array): Promise<PointCloud> {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const h = parseHeader(dv);
  const M = await laz();
  const filePtr = M._malloc(bytes.length);
  M.HEAPU8.set(bytes, filePtr);
  const zip = new M.LASZip();
  let ptr = 0;
  try {
    zip.open(filePtr, bytes.length);
    const recLen = zip.getPointLength() || h.pointLength;
    ptr = M._malloc(recLen);
    const { sink, stride } = alloc(h, recLen);
    const rec = new DataView(M.HEAPU8.buffer, ptr, recLen);  // fixed window — getPoint() overwrites it
    let w = 0, nextWanted = 0;
    for (let i = 0; i < h.count; i++) {
      zip.getPoint(ptr);                                     // must decode every record in order
      if (i === nextWanted) { emit(rec, h, sink, w++); nextWanted += stride; }
    }
    return finish(h, sink, w);
  } finally {
    if (ptr) M._free(ptr);
    M._free(filePtr);
    zip.delete();
  }
}

/** Read a .las or .laz file into flat point arrays. */
export async function readPointCloud(bytes: Uint8Array, name: string): Promise<PointCloud> {
  return name.toLowerCase().endsWith(".laz") ? readLaz(bytes) : readLas(bytes);
}
