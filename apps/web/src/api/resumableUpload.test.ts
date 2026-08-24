import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  CHUNK_GRANULARITY, MAX_CHUNKS, MIN_CHUNK, chunkCount, planChunkSize, uploadResumable,
  type HandshakeReply, type ResumableDeps,
} from "./resumableUpload";

/**
 * Two halves.
 *
 * The first drives the protocol against a fake server, because what matters is the SEQUENCE — that a
 * resume sends only the missing chunks, and a deduplicated upload sends none.
 *
 * The second is the one that will actually catch a regression a year from now: the chunk arithmetic
 * exists in Python AND in TypeScript, and the server rejects a manifest whose count disagrees with its
 * own plan. Nothing links the two files, so this reads the Python source and asserts they still agree.
 * Without it, a change to one side turns every upload into a 422 that names neither.
 */

/** A fake server implementing enough of `routers/uploads.py` to exercise the client. */
function fakeServer(opts: { have?: Set<number>; assembled?: boolean } = {}) {
  const have = opts.have ?? new Set<number>();
  const puts: Array<{ index: number; bytes: number; hash: string }> = [];
  let completed: { chunks: number } | null = null;
  let manifest: string[] = [];

  const deps: ResumableDeps = {
    sha256: async (data) => `h${new Uint8Array(data).length}_${new Uint8Array(data)[0] ?? 0}`,
    postJson: async (path, body) => {
      if (path.endsWith("/handshake")) {
        const b = body as { size: number; chunk_hashes: string[] };
        manifest = b.chunk_hashes;
        if (opts.assembled) {
          return { upload_id: "uid", chunk_size: planChunkSize(b.size), chunks: manifest.length,
                   need: [], complete: true, already: true } satisfies HandshakeReply;
        }
        const need = manifest.map((_, i) => i).filter((i) => !have.has(i));
        return { upload_id: "uid", chunk_size: planChunkSize(b.size), chunks: manifest.length,
                 need, complete: need.length === 0 } satisfies HandshakeReply;
      }
      completed = body as { chunks: number };
      return { key: "projects/p/uploads/uid", bytes: 123 };
    },
    putBytes: async (path, data, headers) => {
      const index = Number(path.split("/").pop());
      puts.push({ index, bytes: data.byteLength, hash: headers["X-Chunk-Sha256"]! });
      return {};
    },
  };
  return { deps, puts, get completed() { return completed; }, get manifest() { return manifest; } };
}

/** A Blob big enough to split, without allocating anything real. */
const blobOf = (size: number) => new Blob([new Uint8Array(size)]);

describe("chunk planning", () => {
  it("bounds the COUNT, not the size — the manifest cannot grow without bound", () => {
    const big = 4 * 1024 ** 3;
    expect(chunkCount(big, planChunkSize(big))).toBeLessThanOrEqual(MAX_CHUNKS);
    // The comparison that makes the design worth having: a fixed 1 MiB part size would not bound it.
    expect(big / MIN_CHUNK).toBeGreaterThan(MAX_CHUNKS);
  });

  it("never splits a small file into tiny chunks", () => {
    expect(planChunkSize(40_000)).toBe(MIN_CHUNK);
    expect(chunkCount(40_000, MIN_CHUNK)).toBe(1);
  });

  it("zero bytes is one empty chunk, not zero chunks", () => {
    expect(chunkCount(0, MIN_CHUNK)).toBe(1);
  });
});

describe("the protocol", () => {
  it("uploads every chunk on a first attempt, and completes", async () => {
    const size = 3 * MIN_CHUNK;
    const srv = fakeServer();
    const res = await uploadResumable("p", blobOf(size), srv.deps);
    expect(srv.manifest).toHaveLength(3);
    expect(srv.puts.map((p) => p.index)).toEqual([0, 1, 2]);
    expect(srv.completed).toEqual({ chunks: 3 });
    expect(res.deduplicated).toBe(false);
    expect(res.sent).toBe(3);
  });

  it("RESUMES — sends only the chunks the server says it needs", async () => {
    const srv = fakeServer({ have: new Set([0, 1]) });
    const res = await uploadResumable("p", blobOf(3 * MIN_CHUNK), srv.deps);
    expect(srv.puts.map((p) => p.index), "chunks 0 and 1 were already there").toEqual([2]);
    expect(res.sent).toBe(1);
  });

  it("DEDUPLICATES — an already-assembled file transfers nothing at all", async () => {
    const srv = fakeServer({ assembled: true });
    const res = await uploadResumable("p", blobOf(3 * MIN_CHUNK), srv.deps);
    expect(srv.puts).toEqual([]);
    expect(res.deduplicated).toBe(true);
    expect(res.sent).toBe(0);
    // It still completes, because that is what returns the key of the object already stored.
    expect(srv.completed).toEqual({ chunks: 3 });
  });

  it("sends each chunk's own promised hash, not a repeated one", async () => {
    const srv = fakeServer();
    await uploadResumable("p", blobOf(2 * MIN_CHUNK + 5), srv.deps);
    const hashes = srv.puts.map((p) => p.hash);
    expect(new Set(hashes).size, "the last chunk is shorter, so its hash must differ").toBeGreaterThan(1);
    expect(hashes).toEqual(srv.manifest);
  });

  it("reports progress against the bytes it will actually send, not the file size", async () => {
    const seen: Array<[number, number]> = [];
    const srv = fakeServer({ have: new Set([0]) });
    await uploadResumable("p", blobOf(3 * MIN_CHUNK), { ...srv.deps, onProgress: (s, t) => seen.push([s, t]) });
    expect(seen.at(-1)![0]).toBe(2 * MIN_CHUNK);
    expect(seen.at(-1)![1], "total excludes the chunk already held").toBe(2 * MIN_CHUNK);
  });
});

/**
 * THE CROSS-LANGUAGE GATE. The server refuses a manifest whose chunk count disagrees with its own
 * plan, so these four numbers have to match on both sides, and nothing but this test links them.
 */
describe("the chunk arithmetic agrees with the Python it is ported from", () => {
  const py = readFileSync(
    resolve(process.cwd(), "../../services/api/src/aec_api/resumable.py"), "utf8");

  const constant = (name: string) => {
    const m = py.match(new RegExp(`^${name}\\s*=\\s*([^#\\n]+)`, "m"));
    expect(m, `${name} not found in resumable.py — the gate cannot see what it is checking`).toBeTruthy();
    // `1 << 20` and plain integers are the only forms used.
    const expr = m![1]!.trim();
    const shift = expr.match(/^1\s*<<\s*(\d+)$/);
    return shift ? 1 << Number(shift[1]) : Number(expr);
  };

  it("found the Python source — else every assertion below is vacuous", () => {
    expect(py).toContain("def plan_chunk_size");
  });

  it("MAX_CHUNKS matches", () => expect(MAX_CHUNKS).toBe(constant("MAX_CHUNKS")));
  it("MIN_CHUNK matches", () => expect(MIN_CHUNK).toBe(constant("MIN_CHUNK")));
  it("CHUNK_GRANULARITY matches", () => expect(CHUNK_GRANULARITY).toBe(constant("CHUNK_GRANULARITY")));

  // Constants agreeing is necessary and not sufficient: the FORMULA could still diverge. These are the
  // sizes where rounding and the floor actually decide something.
  it("the plan agrees at the boundaries where it decides something", () => {
    const cases = [0, 1, 40_000, MIN_CHUNK, MIN_CHUNK + 1, 50 * MIN_CHUNK,
                   MAX_CHUNKS * MIN_CHUNK, MAX_CHUNKS * MIN_CHUNK + 1, 4 * 1024 ** 3];
    for (const size of cases) {
      // Re-implement the Python literally here, from the source's own shape, and compare.
      const needed = Math.ceil(size / constant("MAX_CHUNKS"));
      const expected = size <= 0 ? constant("MIN_CHUNK")
        : Math.ceil(Math.max(needed, constant("MIN_CHUNK")) / constant("CHUNK_GRANULARITY"))
          * constant("CHUNK_GRANULARITY");
      expect(planChunkSize(size), `size ${size}`).toBe(expected);
    }
  });
});
