/**
 * A minimal ZIP writer — enough to build a `.bcfzip`, and nothing more.
 *
 * Pulling in a compression library to package a few kilobytes of XML would be a poor trade, so this
 * writes **stored** (uncompressed) entries only. That is a fully conformant ZIP: the format has
 * always allowed method 0, and every reader — including every BCF tool — handles it. BCF payloads
 * are small XML files and a handful of PNG snapshots, and PNGs are already compressed, so deflating
 * would save very little anyway.
 *
 * What it does not do: compression, ZIP64 (so no archive over 4 GB or 65 535 entries), encryption,
 * or reading. If you need any of those, use a real library.
 */

export interface ZipEntry {
  /** Path within the archive. Forward slashes; no leading slash. */
  name: string;
  data: Uint8Array | string;
  /** Modification time. Defaults to the epoch so archives are byte-reproducible. */
  date?: Date;
}

/** CRC-32 (IEEE 802.3), table built once on first use. */
let crcTable: Uint32Array | null = null;

function crc32(bytes: Uint8Array): number {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
      let c = i;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crcTable[i] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) crc = crcTable[(crc ^ bytes[i]!) & 0xff]! ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

/** MS-DOS date/time, as the ZIP header wants it. */
function dosDateTime(d: Date): { date: number; time: number } {
  // The DOS epoch is 1980; anything earlier clamps rather than wrapping into a nonsense year.
  const year = Math.max(1980, d.getFullYear());
  return {
    date: ((year - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate(),
    time: (d.getHours() << 11) | (d.getMinutes() << 5) | Math.floor(d.getSeconds() / 2),
  };
}

/** Little-endian writer over a growable buffer. */
class ByteWriter {
  private buf = new Uint8Array(1024);
  private len = 0;

  private need(n: number): void {
    if (this.len + n <= this.buf.length) return;
    let size = this.buf.length * 2;
    while (size < this.len + n) size *= 2;
    const next = new Uint8Array(size);
    next.set(this.buf.subarray(0, this.len));
    this.buf = next;
  }

  u16(v: number): this { this.need(2); this.buf[this.len++] = v & 0xff; this.buf[this.len++] = (v >>> 8) & 0xff; return this; }
  u32(v: number): this {
    this.need(4);
    this.buf[this.len++] = v & 0xff;
    this.buf[this.len++] = (v >>> 8) & 0xff;
    this.buf[this.len++] = (v >>> 16) & 0xff;
    this.buf[this.len++] = (v >>> 24) & 0xff;
    return this;
  }
  bytes(b: Uint8Array): this { this.need(b.length); this.buf.set(b, this.len); this.len += b.length; return this; }

  get offset(): number { return this.len; }
  finish(): Uint8Array { return this.buf.slice(0, this.len); }
}

const utf8 = (s: string): Uint8Array => new TextEncoder().encode(s);

/** Build a ZIP archive from a list of entries. */
export function zip(entries: readonly ZipEntry[]): Uint8Array {
  const w = new ByteWriter();
  const central: { name: Uint8Array; crc: number; size: number; offset: number; date: number; time: number }[] = [];

  for (const entry of entries) {
    const name = utf8(entry.name);
    const data = typeof entry.data === "string" ? utf8(entry.data) : entry.data;
    const crc = crc32(data);
    const { date, time } = dosDateTime(entry.date ?? new Date(1980, 0, 1));
    const offset = w.offset;

    // Local file header.
    w.u32(0x04034b50);
    w.u16(20);              // version needed
    w.u16(0x0800);          // flags: UTF-8 names
    w.u16(0);               // method: stored
    w.u16(time).u16(date);
    w.u32(crc).u32(data.length).u32(data.length);
    w.u16(name.length).u16(0);
    w.bytes(name).bytes(data);

    central.push({ name, crc, size: data.length, offset, date, time });
  }

  const centralStart = w.offset;
  for (const e of central) {
    w.u32(0x02014b50);
    w.u16(20).u16(20);      // version made by / needed
    w.u16(0x0800).u16(0);   // flags / method
    w.u16(e.time).u16(e.date);
    w.u32(e.crc).u32(e.size).u32(e.size);
    w.u16(e.name.length).u16(0).u16(0);
    w.u16(0).u16(0).u32(0); // disk, internal attrs, external attrs
    w.u32(e.offset);
    w.bytes(e.name);
  }
  const centralSize = w.offset - centralStart;

  // End of central directory.
  w.u32(0x06054b50);
  w.u16(0).u16(0);
  w.u16(central.length).u16(central.length);
  w.u32(centralSize).u32(centralStart);
  w.u16(0);

  return w.finish();
}
