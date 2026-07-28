/**
 * REST adapter, shaped for Massing's existing markup endpoints.
 *
 * Massing already stores drawing markups (`GET/POST /projects/{pid}/drawings/markup`, a bulk save,
 * an SSE change stream, and a promote-to-RFI call). Rather than invent a new contract and require a
 * server change before this is usable, the default paths and payload mapping target that API — and
 * every path is overridable so another backend only has to supply its own URLs.
 */
import { ConflictError, type LoadResult, type Mutation, type StorageAdapter, type StoreKey } from "./types";
import type { Annotation, Calibration, SheetMeta } from "../core/types";

export interface RestPaths {
  list(key: StoreKey): string;
  bulk(key: StoreKey): string;
  remove(key: StoreKey, id: string): string;
  stream?(key: StoreKey): string;
}

export interface RestOptions {
  baseUrl: string;
  /** Auth headers etc. Called per request so a rotating token stays fresh. */
  headers?: () => Record<string, string>;
  paths?: Partial<RestPaths>;
  /** Replace the caller's own prior markups for the sheet on each bulk save. */
  replaceOnSave?: boolean;
  fetchImpl?: typeof fetch;
}

/** The wire shape Massing's `drawing_markups` table uses. */
interface WireMarkup {
  id: string;
  sheet_id: string;
  x: number;
  y: number;
  note: string | null;
  author: string | null;
  topic_id: string | null;
  kind?: string;
  created_at?: string;
  data?: Record<string, unknown> | null;
}

const defaultPaths = (base: string): RestPaths => ({
  list: (k) => `${base}/projects/${k.projectId}/drawings/markup?sheet=${encodeURIComponent(k.documentId)}`,
  bulk: (k) => `${base}/projects/${k.projectId}/drawings/markup/bulk`,
  remove: (k, id) => `${base}/projects/${k.projectId}/drawings/markup/${id}`,
  stream: (k) => `${base}/projects/${k.projectId}/drawings/markup/stream`,
});

export class RestAdapter implements StorageAdapter {
  readonly id = "rest";
  private paths: RestPaths;
  private fetch: typeof fetch;

  constructor(private o: RestOptions) {
    const base = o.baseUrl.replace(/\/$/, "");
    this.paths = { ...defaultPaths(base), ...o.paths };
    this.fetch = o.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  private headers(): Record<string, string> {
    return { "Content-Type": "application/json", ...(this.o.headers?.() ?? {}) };
  }

  async load(key: StoreKey): Promise<LoadResult> {
    const res = await this.fetch(this.paths.list(key), { headers: this.headers() });
    if (!res.ok) throw new Error(`load failed: HTTP ${res.status}`);
    const rows = (await res.json()) as WireMarkup[];
    const annotations: Annotation[] = [];
    const calibrations: Calibration[] = [];
    const sheets: SheetMeta[] = [];
    for (const row of rows) {
      // Calibration and sheet metadata ride in the same table under reserved kinds, so a host
      // doesn't need new tables to adopt this.
      if (row.kind === "__calibration" && row.data) { calibrations.push(row.data as unknown as Calibration); continue; }
      if (row.kind === "__sheet" && row.data) { sheets.push(row.data as unknown as SheetMeta); continue; }
      annotations.push(fromWire(row));
    }
    return { annotations, calibrations, sheets };
  }

  async save(key: StoreKey, mutations: Mutation[]): Promise<void> {
    const upserts = mutations.filter((m): m is Extract<Mutation, { op: "upsert" }> => m.op === "upsert");
    const removals = mutations.filter((m): m is Extract<Mutation, { op: "remove" }> => m.op === "remove");
    const cals = mutations.filter((m): m is Extract<Mutation, { op: "calibration" }> => m.op === "calibration");
    const sheets = mutations.filter((m): m is Extract<Mutation, { op: "sheet" }> => m.op === "sheet");

    // Deletes first: a bulk save with `replace` would otherwise resurrect a markup deleted in the
    // same batch, since the batch body is the new truth for the sheet.
    for (const m of removals) {
      const url = m.baseVersion === undefined
        ? this.paths.remove(key, m.id)
        : `${this.paths.remove(key, m.id)}${this.paths.remove(key, m.id).includes("?") ? "&" : "?"}base_version=${m.baseVersion}`;
      const res = await this.fetch(url, { method: "DELETE", headers: this.headers() });
      if (res.status === 409) throw await this.conflictFrom(res, [{ id: m.id }]);
      if (!res.ok && res.status !== 404) throw new Error(`delete failed: HTTP ${res.status}`);
    }

    const markups = [
      ...upserts.map((m) => ({
        ...toWire(m.annot),
        // The version this edit was made against. A server that enforces it answers 409 with the
        // rows that moved on; one that ignores it behaves exactly as before.
        ...(m.baseVersion === undefined ? {} : { base_version: m.baseVersion }),
      })),
      ...cals.filter((m) => m.calibration).map((m) => ({
        x: 0, y: 0, kind: "__calibration", note: null, data: m.calibration as unknown as Record<string, unknown>,
      })),
      ...sheets.map((m) => ({
        x: 0, y: 0, kind: "__sheet", note: null, data: m.sheet as unknown as Record<string, unknown>,
      })),
    ];
    if (!markups.length) return;

    const res = await this.fetch(this.paths.bulk(key), {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        sheet_id: key.documentId,
        replace: this.o.replaceOnSave ?? true,
        markups,
      }),
    });
    if (res.status === 409) {
      throw await this.conflictFrom(res, upserts.map((m) => ({ id: m.annot.id, mine: m.annot })));
    }
    if (!res.ok) throw new Error(`save failed: HTTP ${res.status}`);
  }

  /**
   * Build a `ConflictError` from a 409.
   *
   * The body is expected to carry the rows the server actually holds, as
   * `{ conflicts: [ <row> ] }` or a bare array — so the caller can show both sides rather than only
   * being told it failed. A server that answers 409 with nothing useful still produces a usable
   * error, just without `theirs`.
   */
  private async conflictFrom(
    res: Response,
    attempted: { id: string; mine?: Annotation }[],
  ): Promise<ConflictError> {
    let rows: WireMarkup[] = [];
    try {
      const body = await res.json() as { conflicts?: WireMarkup[] } | WireMarkup[];
      rows = Array.isArray(body) ? body : body.conflicts ?? [];
    } catch { /* no body, or not JSON — the ids alone still make a usable error */ }

    const theirs = new Map(rows.map((r) => [r.id, fromWire(r)]));
    // If the server named the rows, trust that list; otherwise assume the whole batch was rejected.
    const ids = theirs.size ? [...theirs.keys()] : attempted.map((a) => a.id);
    const mine = new Map(attempted.map((a) => [a.id, a.mine]));
    return new ConflictError(ids.map((id) => ({
      id,
      ...(mine.get(id) ? { mine: mine.get(id)! } : {}),
      ...(theirs.get(id) ? { theirs: theirs.get(id)! } : {}),
    })));
  }

  /**
   * Massing's stream emits a cheap change signature rather than the changed rows, so a signal is
   * turned into a re-load. Coarse, but it means live co-markup needs no new server work.
   */
  subscribe(key: StoreKey, onChange: (result: LoadResult) => void): () => void {
    const url = this.paths.stream?.(key);
    if (!url || typeof EventSource === "undefined") return () => {};
    const es = new EventSource(url, { withCredentials: true });
    let first = true;
    es.onmessage = () => {
      // The first event is the current snapshot; acting on it would double-load what `load` just did.
      if (first) { first = false; return; }
      void this.load(key).then(onChange).catch(() => { /* a dropped refresh is not fatal */ });
    };
    return () => es.close();
  }

  online(): boolean {
    return typeof navigator === "undefined" || navigator.onLine !== false;
  }
}

/**
 * Annotation → Massing's row shape. The anchor goes in `x`/`y` so the existing SVG sheet viewer can
 * place a pin for it without understanding the richer geometry, and the full record goes in `data`.
 */
export function toWire(a: Annotation): Omit<WireMarkup, "id" | "author" | "topic_id" | "created_at"> & { id?: string } {
  const anchor = a.points[0] ?? { x: 0, y: 0 };
  return {
    id: a.id,
    sheet_id: a.sheetId,
    x: anchor.x,
    y: anchor.y,
    note: a.note ?? a.text ?? a.subject ?? null,
    kind: a.kind,
    data: {
      // `pts`/`value`/`unit`/`page`/`nx`/`ny` keep the field names Massing's existing readers expect.
      pts: a.points,
      value: a.quantity?.value ?? 0,
      unit: a.quantity?.unit ?? "",
      page: a.page,
      text: a.text,
      nx: a.nx,
      ny: a.ny,
      rev: a.revision?.rev,
      carried_from: a.revision?.carriedFrom,
      // Everything the legacy shape has no slot for.
      record: {
        subject: a.subject, status: a.status, priority: a.priority, discipline: a.discipline,
        trade: a.trade, labels: a.labels, style: a.style, quantity: a.quantity, links: a.links,
        provenance: a.provenance, replies: a.replies, attachments: a.attachments,
        version: a.version, createdAt: a.createdAt, updatedAt: a.updatedAt, org: a.org,
        rotation: a.rotation, ext: a.ext,
      },
    },
  };
}

/** Massing's row shape → Annotation. Tolerates rows written before the `record` payload existed. */
export function fromWire(row: WireMarkup): Annotation {
  const d = (row.data ?? {}) as Record<string, unknown>;
  const rec = (d["record"] ?? {}) as Record<string, unknown>;
  const pts = Array.isArray(d["pts"]) && (d["pts"] as unknown[]).length
    ? (d["pts"] as { x: number; y: number }[])
    : [{ x: row.x, y: row.y }];
  return {
    id: row.id,
    kind: (row.kind as Annotation["kind"]) || "pin",
    sheetId: row.sheet_id,
    page: typeof d["page"] === "number" ? d["page"] : 1,
    points: pts.map((p) => ({ x: p.x, y: p.y })),
    author: row.author ?? (rec["org"] as string) ?? "unknown",
    createdAt: (rec["createdAt"] as string) ?? row.created_at ?? new Date().toISOString(),
    version: typeof rec["version"] === "number" ? rec["version"] : 1,
    status: (rec["status"] as Annotation["status"]) ?? "open",
    note: row.note ?? undefined,
    text: typeof d["text"] === "string" ? d["text"] : undefined,
    nx: typeof d["nx"] === "number" ? d["nx"] : undefined,
    ny: typeof d["ny"] === "number" ? d["ny"] : undefined,
    subject: rec["subject"] as string | undefined,
    priority: rec["priority"] as Annotation["priority"],
    discipline: rec["discipline"] as Annotation["discipline"],
    trade: rec["trade"] as string | undefined,
    labels: rec["labels"] as string[] | undefined,
    style: rec["style"] as Annotation["style"],
    quantity: (rec["quantity"] as Annotation["quantity"]) ?? quantityFromLegacy(d),
    links: {
      ...(rec["links"] as Annotation["links"] ?? {}),
      ...(row.topic_id ? { issueId: row.topic_id } : {}),
    },
    revision: {
      ...(typeof d["rev"] === "string" ? { rev: d["rev"] } : {}),
      ...(typeof d["carried_from"] === "string" ? { carriedFrom: d["carried_from"] } : {}),
    },
    provenance: rec["provenance"] as Annotation["provenance"],
    replies: rec["replies"] as Annotation["replies"],
    attachments: rec["attachments"] as Annotation["attachments"],
    updatedAt: rec["updatedAt"] as string | undefined,
    org: rec["org"] as string | undefined,
    rotation: rec["rotation"] as number | undefined,
    ext: rec["ext"] as Record<string, unknown> | undefined,
  };
}

/** Rows written by the original takeoff editor carry a bare value/unit pair. */
function quantityFromLegacy(d: Record<string, unknown>): Annotation["quantity"] {
  const value = d["value"];
  const unit = d["unit"];
  if (typeof value !== "number" || !value || typeof unit !== "string" || !unit) return undefined;
  return { value, unit };
}
