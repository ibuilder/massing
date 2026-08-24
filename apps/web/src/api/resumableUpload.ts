/**
 * R41-UPLOAD-WARK — the client half of the resumable upload handshake.
 *
 * An IFC revision is large and mostly identical to the one before it. A single multipart POST pays the
 * full transfer every time and loses everything if the connection drops at 90%. This walks the
 * three-request protocol in `services/api/src/aec_api/routers/uploads.py`:
 *
 *   1. hash each chunk locally and hand the server the manifest;
 *   2. PUT only the chunks it says it still needs;
 *   3. ask it to assemble.
 *
 * **Resuming is not a separate call.** Calling this again with the same file after a failure produces
 * the same manifest, therefore the same upload id, therefore a shorter `need` list. An unchanged
 * re-upload gets `need: []` and transfers nothing at all.
 *
 * ## THE CHUNK SIZE IS COMPUTED IN TWO LANGUAGES, AND THEY MUST AGREE
 *
 * The server rejects a manifest whose chunk count does not match its own plan for that file size, so
 * `planChunkSize` below is a port of `resumable.plan_chunk_size` and the constants are a port of its
 * constants. That is a real duplication and the obvious way for this to break silently later — a
 * change on one side turns every upload into a 422 that names neither side. `resumableUpload.test.ts`
 * reads the Python source and asserts the four constants still match, so the drift fails a build
 * instead of a user's upload.
 */

/** Ported from `resumable.py`. The test pins these against the Python source. */
export const MAX_CHUNKS = 64;
export const MIN_CHUNK = 1 << 20;
export const CHUNK_GRANULARITY = 1 << 20;

/**
 * The chunk size for a file of `size` bytes: the smallest that keeps the count within `MAX_CHUNKS`.
 *
 * The count is bounded rather than the size, so the manifest stays roughly constant however large the
 * file is — a fixed part size would make a 4 GiB upload declare hundreds of hashes, on every resume.
 */
export function planChunkSize(size: number): number {
  if (size <= 0) return MIN_CHUNK;
  const needed = Math.ceil(size / MAX_CHUNKS);
  return Math.ceil(Math.max(needed, MIN_CHUNK) / CHUNK_GRANULARITY) * CHUNK_GRANULARITY;
}

/** How many chunks a file splits into. Zero bytes is ONE empty chunk — see the Python twin. */
export function chunkCount(size: number, chunk: number): number {
  return Math.max(1, Math.ceil(size / chunk));
}

export interface HandshakeReply {
  readonly upload_id: string;
  readonly chunk_size: number;
  readonly chunks: number;
  readonly need: readonly number[];
  readonly complete: boolean;
  readonly already?: boolean;
}

export interface ResumableDeps {
  /** POST JSON, returning the parsed body. */
  readonly postJson: (path: string, body: unknown) => Promise<unknown>;
  /** PUT raw bytes with headers. */
  readonly putBytes: (path: string, body: ArrayBuffer, headers: Record<string, string>) => Promise<unknown>;
  /** sha256 hex of a byte range. Injected because `crypto.subtle` is unavailable in some test DOMs. */
  readonly sha256: (data: ArrayBuffer) => Promise<string>;
  /** Called after each chunk with bytes transferred and the total that will be. */
  readonly onProgress?: (sent: number, total: number) => void;
}

/** Browser sha256, hex — the production `sha256` dependency. */
export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export interface UploadResult {
  readonly key: string;
  readonly bytes: number;
  /** True when the server already held this exact file and nothing was transferred. */
  readonly deduplicated: boolean;
  /** How many chunks were actually sent — 0 on a full deduplication. */
  readonly sent: number;
}

/**
 * Upload `file` to a project, resuming and deduplicating automatically.
 *
 * Chunks are hashed one at a time rather than all up front: hashing a 200 MB file before showing any
 * progress looks like a hang, and holding every chunk's bytes at once defeats the point of chunking.
 */
export async function uploadResumable(
  pid: string, file: Blob, deps: ResumableDeps,
): Promise<UploadResult> {
  const size = file.size;
  const chunk = planChunkSize(size);
  const count = chunkCount(size, chunk);

  const buffers: ArrayBuffer[] = [];
  const hashes: string[] = [];
  for (let i = 0; i < count; i++) {
    const buf = await file.slice(i * chunk, Math.min((i + 1) * chunk, size)).arrayBuffer();
    buffers.push(buf);
    hashes.push(await deps.sha256(buf));
  }

  const hs = await deps.postJson(`/projects/${pid}/uploads/handshake`,
    { size, chunk_hashes: hashes }) as HandshakeReply;

  const need = hs.need ?? [];
  const total = need.reduce((n, i) => n + buffers[i]!.byteLength, 0);
  let sent = 0;
  for (const i of need) {
    await deps.putBytes(`/projects/${pid}/uploads/${hs.upload_id}/chunk/${i}`, buffers[i]!,
      { "X-Chunk-Sha256": hashes[i]!, "Content-Type": "application/octet-stream" });
    sent += buffers[i]!.byteLength;
    deps.onProgress?.(sent, total);
  }

  const done = await deps.postJson(`/projects/${pid}/uploads/${hs.upload_id}/complete`,
    { chunks: count }) as { key: string; bytes: number };
  return { key: done.key, bytes: done.bytes, deduplicated: need.length === 0, sent: need.length };
}
