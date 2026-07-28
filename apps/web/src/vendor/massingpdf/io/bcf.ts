/**
 * BCF bridge — sheet pins as buildingSMART topics.
 *
 * Massing addresses model elements by IFC GlobalId and routes issues through BCF, so a pin dropped
 * on a drawing has to be able to become a topic that Solibri, BIMcollab or Revit can open. This maps
 * both directions against BCF 2.1/3.0's `markup.bcf` topic shape, keeping the sheet coordinates in
 * the topic so a round-tripped issue still knows where on the paper it came from.
 *
 * Emitting a full `.bcfzip` needs a zip writer and viewpoint snapshots, which is a host concern —
 * this produces the topic *records* and leaves packaging to the caller.
 */
import { zip, type ZipEntry } from "./zip";
import type { Annotation, AnnotationDraft, AnnotStatus, AnnotPriority } from "../core/types";

/** A BCF topic, in the JSON shape the BCF-API uses. */
export interface BcfTopic {
  guid: string;
  topic_type: string;
  topic_status: string;
  title: string;
  priority?: string;
  labels?: string[];
  creation_date: string;
  creation_author: string;
  modified_date?: string;
  modified_author?: string;
  assigned_to?: string;
  due_date?: string;
  description?: string;
  /** Reference back to the sheet the pin lives on. */
  reference_links?: string[];
  /** BCF 3.0 allows arbitrary document references; the sheet anchor rides here. */
  bim_snippet?: { snippet_type: string; is_external: boolean; reference: string; reference_schema: string };
}

export interface BcfComment {
  guid: string;
  date: string;
  author: string;
  comment: string;
  topic_guid: string;
}

export interface BcfExport {
  topic: BcfTopic;
  comments: BcfComment[];
}

/** BCF's `TopicStatus` vocabulary is project-defined; these are the common defaults. */
const STATUS_TO_BCF: Record<AnnotStatus, string> = {
  open: "Open",
  in_review: "In Progress",
  accepted: "Closed",
  rejected: "Closed",
  resolved: "Resolved",
  void: "Closed",
  info: "Open",
};

const BCF_TO_STATUS: Record<string, AnnotStatus> = {
  open: "open", active: "open", new: "open",
  "in progress": "in_review", inprogress: "in_review", assigned: "in_review",
  resolved: "resolved", closed: "accepted", reopened: "open",
};

const PRIORITY_TO_BCF: Record<AnnotPriority, string> = {
  low: "Low", normal: "Normal", high: "High", critical: "Critical",
};

/** Where on the sheet the topic came from, encoded so it survives a round trip. */
export interface SheetAnchor {
  sheetId: string;
  page: number;
  /** Page-normalised anchor, so it can be re-placed on a re-plotted sheet of any size. */
  nx: number;
  ny: number;
  document?: string;
}

const ANCHOR_PREFIX = "massing:sheet-anchor:";

export const encodeAnchor = (a: SheetAnchor): string => `${ANCHOR_PREFIX}${JSON.stringify(a)}`;

export function decodeAnchor(link: string): SheetAnchor | null {
  if (!link.startsWith(ANCHOR_PREFIX)) return null;
  try { return JSON.parse(link.slice(ANCHOR_PREFIX.length)) as SheetAnchor; }
  catch { return null; }
}

/** One markup → one BCF topic (plus its replies as comments). */
export function toBcfTopic(a: Annotation, opts: { documentName?: string } = {}): BcfExport {
  const anchor: SheetAnchor = {
    sheetId: a.sheetId,
    page: a.page,
    nx: a.nx ?? 0,
    ny: a.ny ?? 0,
    ...(opts.documentName ? { document: opts.documentName } : {}),
  };
  const issueType = a.ext?.["issueType"];

  const topic: BcfTopic = {
    guid: normaliseGuid(a.links?.issueId ?? a.id),
    topic_type: typeof issueType === "string" ? issueType : "Issue",
    topic_status: STATUS_TO_BCF[a.status],
    title: a.subject || a.text || a.note || `${a.kind} on ${a.sheetId}`,
    creation_date: a.createdAt,
    creation_author: a.author,
    reference_links: [encodeAnchor(anchor)],
    ...(a.priority ? { priority: PRIORITY_TO_BCF[a.priority] } : {}),
    ...(a.labels?.length ? { labels: a.labels } : {}),
    ...(a.updatedAt ? { modified_date: a.updatedAt } : {}),
    ...(a.note ? { description: describe(a) } : {}),
  };
  const assignee = a.ext?.["assignee"];
  if (typeof assignee === "string") topic.assigned_to = assignee;
  const due = a.ext?.["dueDate"];
  if (typeof due === "string") topic.due_date = due;

  const comments: BcfComment[] = (a.replies ?? []).map((rep) => ({
    guid: normaliseGuid(rep.id),
    date: rep.createdAt,
    author: rep.author,
    comment: rep.body,
    topic_guid: topic.guid,
  }));

  return { topic, comments };
}

/** Fold the measured quantity and IFC links into the topic description — the fields BCF has no slot for. */
function describe(a: Annotation): string {
  const lines = [a.note ?? ""];
  if (a.quantity) lines.push(`Measured: ${a.quantity.value.toFixed(3)} ${a.quantity.unit}`);
  if (a.discipline) lines.push(`Discipline: ${a.discipline}`);
  if (a.links?.spec) lines.push(`Spec: ${a.links.spec.section}${a.links.spec.clause ? ` §${a.links.spec.clause}` : ""}`);
  if (a.links?.ifcGuids?.length) lines.push(`IFC: ${a.links.ifcGuids.join(", ")}`);
  if (a.revision?.rev) lines.push(`Sheet revision: ${a.revision.rev}`);
  return lines.filter(Boolean).join("\n");
}

/** A BCF topic → a pin draft, placed from its sheet anchor. */
export function fromBcfTopic(
  topic: BcfTopic,
  comments: BcfComment[] = [],
  pageSize?: (page: number) => { width: number; height: number } | undefined,
): AnnotationDraft | null {
  const anchor = (topic.reference_links ?? []).map(decodeAnchor).find(Boolean);
  if (!anchor) return null;
  const size = pageSize?.(anchor.page);
  const points = [{
    x: anchor.nx * (size?.width ?? 1),
    y: anchor.ny * (size?.height ?? 1),
  }];
  return {
    kind: "pin",
    page: anchor.page,
    sheetId: anchor.sheetId,
    points,
    author: topic.creation_author,
    createdAt: topic.creation_date,
    ...(topic.modified_date ? { updatedAt: topic.modified_date } : {}),
    subject: topic.title,
    ...(topic.description ? { note: topic.description } : {}),
    status: BCF_TO_STATUS[topic.topic_status.toLowerCase()] ?? "open",
    ...(topic.priority ? { priority: topic.priority.toLowerCase() as AnnotPriority } : {}),
    ...(topic.labels?.length ? { labels: topic.labels } : {}),
    links: { issueId: topic.guid },
    ext: {
      issueType: topic.topic_type,
      ...(topic.assigned_to ? { assignee: topic.assigned_to } : {}),
      ...(topic.due_date ? { dueDate: topic.due_date } : {}),
    },
    replies: comments
      .filter((c) => c.topic_guid === topic.guid)
      .map((c) => ({ id: c.guid, author: c.author, body: c.comment, createdAt: c.date })),
  };
}

/** Export a whole markup set as topics. Non-pin markups become topics too — a clouded issue is an issue. */
export function toBcfTopics(annots: readonly Annotation[], opts: { documentName?: string; onlyPins?: boolean } = {}): BcfExport[] {
  return annots
    .filter((a) => (opts.onlyPins ? a.kind === "pin" : a.kind === "pin" || a.status !== "info"))
    .map((a) => toBcfTopic(a, opts));
}

// ---- .bcfzip packaging -----------------------------------------------------

const esc = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const el = (tag: string, text: string | undefined): string =>
  text ? `<${tag}>${esc(text)}</${tag}>` : "";

/** One topic's `markup.bcf` document. */
export function topicMarkupXml(entry: BcfExport): string {
  const { topic, comments } = entry;
  return [
    `<?xml version="1.0" encoding="UTF-8"?>`,
    `<Markup>`,
    `  <Topic Guid="${esc(topic.guid)}" TopicType="${esc(topic.topic_type)}" TopicStatus="${esc(topic.topic_status)}">`,
    `    ${el("Title", topic.title)}`,
    topic.priority ? `    ${el("Priority", topic.priority)}` : "",
    `    ${el("CreationDate", topic.creation_date)}`,
    `    ${el("CreationAuthor", topic.creation_author)}`,
    topic.modified_date ? `    ${el("ModifiedDate", topic.modified_date)}` : "",
    topic.assigned_to ? `    ${el("AssignedTo", topic.assigned_to)}` : "",
    topic.due_date ? `    ${el("DueDate", topic.due_date)}` : "",
    topic.description ? `    ${el("Description", topic.description)}` : "",
    ...(topic.labels ?? []).map((l) => `    ${el("Labels", l)}`),
    // The sheet anchor rides in a reference link, which is how it survives a round trip.
    ...(topic.reference_links ?? []).map((r) => `    ${el("ReferenceLink", r)}`),
    `  </Topic>`,
    ...comments.map((c) => [
      `  <Comment Guid="${esc(c.guid)}">`,
      `    ${el("Date", c.date)}`,
      `    ${el("Author", c.author)}`,
      `    ${el("Comment", c.comment)}`,
      `    <TopicGuid>${esc(c.topic_guid)}</TopicGuid>`,
      `  </Comment>`,
    ].join("\n")),
    `</Markup>`,
  ].filter(Boolean).join("\n");
}

/** The archive-level `bcf.version` file. */
const VERSION_XML = [
  `<?xml version="1.0" encoding="UTF-8"?>`,
  `<Version VersionId="2.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">`,
  `  <DetailedVersion>2.1</DetailedVersion>`,
  `</Version>`,
].join("\n");

export interface BcfZipOptions {
  /** Project name written into `project.bcfp`. */
  projectName?: string;
  projectId?: string;
  /** Timestamp for the archive entries. Defaults to a fixed date for reproducible output. */
  date?: Date;
}

/**
 * Package topics as a `.bcfzip` — one folder per topic, each with its `markup.bcf`.
 *
 * BCF 2.1 layout, which is what the widest set of tools reads. Viewpoints are omitted: a viewpoint
 * requires a 3D camera, and a markup on a sheet has a 2D anchor instead — inventing a camera to
 * satisfy the schema would put a wrong number in a file other people's software trusts.
 */
export function toBcfZip(topics: readonly BcfExport[], options: BcfZipOptions = {}): Uint8Array {
  const date = options.date ?? new Date(1980, 0, 1);
  const entries: ZipEntry[] = [{ name: "bcf.version", data: VERSION_XML, date }];

  if (options.projectName || options.projectId) {
    entries.push({
      name: "project.bcfp",
      date,
      data: [
        `<?xml version="1.0" encoding="UTF-8"?>`,
        `<ProjectExtension>`,
        `  <Project ProjectId="${esc(options.projectId ?? "massing")}">`,
        `    ${el("Name", options.projectName)}`,
        `  </Project>`,
        `</ProjectExtension>`,
      ].join("\n"),
    });
  }

  for (const entry of topics) {
    entries.push({ name: `${entry.topic.guid}/markup.bcf`, data: topicMarkupXml(entry), date });
  }
  return zip(entries);
}

/**
 * BCF GUIDs are canonical UUIDs. Ids minted here are prefixed (`an_…`), and hosts may use anything,
 * so derive a stable v4-shaped GUID by hashing rather than rejecting the id.
 */
export function normaliseGuid(id: string): string {
  const bare = id.replace(/^[a-z]+_/, "");
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(bare)) return bare.toLowerCase();
  // FNV-1a over four offset seeds → 128 deterministic bits.
  const words = [0, 1, 2, 3].map((seed) => {
    let h = 0x811c9dc5 ^ seed;
    for (let i = 0; i < id.length; i++) {
      h ^= id.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h.toString(16).padStart(8, "0");
  });
  const [a, b, c, d] = words as [string, string, string, string];
  // Force version 4 and the RFC 4122 variant so consumers validating the shape accept it.
  return `${a}-${b.slice(0, 4)}-4${b.slice(5, 8)}-a${c.slice(1, 4)}-${c.slice(4)}${d}`;
}
