/**
 * R28-UNIFY ① — opening a model and opening a project are the same act.
 *
 * The app has treated these as two things, and the seam has been visible to users: a model renders in
 * the viewer while every data panel reports "No project open", because `openModelFile` ends at
 * `viewer.openFile(...)` and never touches the project. Two shipped bugs in v0.3.703 were instances of
 * that split rather than causes of their own.
 *
 * **The decision is the part worth testing, so it lives here as a pure function.** Whether to mint a
 * project, attach to an existing one, or stay in the viewer depends on connectivity, on what is
 * already open, and on whether the server already holds this model — and getting *that* wrong is how
 * you either strand a user in a viewer or silently create server records they never asked for. The
 * wiring in `main.ts` is then trivial and hard to get wrong.
 *
 * **Three rules the decisions obey.**
 *
 * *Offline never creates.* With no API reachable, opening an IFC is a pure viewing act. Minting a
 * project would be a promise we cannot keep, and the user gets told why rather than left wondering
 * where their data panels went.
 *
 * *An existing project is joined, not duplicated.* "Open a model that the server already has" must
 * land in that project with its RFIs, costs and schedule attached — that is the entire point of tying
 * the two. A second project for the same model splits the record in half.
 *
 * *Creating is proposed, never silent.* A new project is a durable, shared, server-side object. The
 * decision returns `create` with a suggested name; the caller confirms. Auto-creating on every stray
 * file a user previews would fill the register with junk nobody meant to make.
 */

/** What should happen when a model file is opened. */
export type ModelOpenIntent =
  /** No API: render locally, create nothing, and say so. */
  | "viewer-only"
  /** A project is already open — load into it rather than minting a rival. */
  | "load-into-open"
  /** The server already holds this model: join that project and its data. */
  | "attach-existing"
  /** Nothing matches: propose a new project (the caller confirms). */
  | "create";

/** What should happen when a project is opened. */
export type ProjectOpenIntent =
  /** The project has a model — load it. */
  | "load-model"
  /** The project has none: offer a blank, authorable model so work can start immediately. */
  | "offer-blank-model";

export interface ModelOpenContext {
  /** Is the API reachable? */
  connected: boolean;
  /** The project already open, if any. */
  openProjectId: string | null;
  /** The file the user chose. */
  fileName: string;
  /** Projects the server knows, with whatever identifies their model. */
  projects: { id: string; name: string; source_ifc?: string | null }[];
}

export interface ModelOpenDecision {
  intent: ModelOpenIntent;
  /** The project to join, when `attach-existing` or `load-into-open`. */
  projectId: string | null;
  /** Suggested name for `create` — the caller confirms it. */
  suggestedName: string | null;
  /** How a match was made, or why none was. Shown to the user; never inferred silently. */
  reason: string;
  /** How confident the match is. `filename` is a WEAK basis and says so. */
  matchedOn: "none" | "filename" | "open-project";
}

/** Trailing path segment, lowercased, extension stripped — the comparable part of a file reference. */
export function baseName(pathOrName: string): string {
  const tail = String(pathOrName || "").split(/[\\/]/).pop() || "";
  return tail.replace(/\.[^.]+$/, "").trim().toLowerCase();
}

/** A readable project name from a file name: keep the author's words, drop the extension. */
export function nameFromFile(fileName: string): string {
  const tail = String(fileName || "").split(/[\\/]/).pop() || "";
  const stem = tail.replace(/\.[^.]+$/, "").trim();
  return stem || "Untitled project";
}

/**
 * Decide what opening this model means.
 *
 * Matching is by file name, which is **weak** — two firms' `Building.ifc` are not the same building —
 * so the basis is reported in `matchedOn` and the reason names it. A stronger key (the IfcProject
 * GlobalId, or a content hash) belongs here later; what must not happen is a weak match presented as
 * a certain one.
 */
export function decideModelOpen(ctx: ModelOpenContext): ModelOpenDecision {
  if (!ctx.connected) {
    return { intent: "viewer-only", projectId: null, suggestedName: null, matchedOn: "none",
             reason: "no API reachable — the model renders locally and no project is created" };
  }
  if (ctx.openProjectId) {
    return { intent: "load-into-open", projectId: ctx.openProjectId, suggestedName: null,
             matchedOn: "open-project",
             reason: "a project is already open — the model loads into it rather than starting a rival" };
  }
  const want = baseName(ctx.fileName);
  // Only match when the stem is meaningful. An empty or one-character stem would match half a register.
  const hit = want.length >= 2
    ? (ctx.projects || []).find((p) => p.source_ifc && baseName(p.source_ifc) === want)
    : undefined;
  if (hit) {
    return { intent: "attach-existing", projectId: hit.id, suggestedName: null, matchedOn: "filename",
             reason: `“${hit.name}” already holds a model with this file name — opening it brings its `
                   + "data with it. Matched on FILE NAME only, so check it is the same building" };
  }
  return { intent: "create", projectId: null, suggestedName: nameFromFile(ctx.fileName),
           matchedOn: "none",
           reason: "no project on the server holds a model with this file name — a new project will be "
                 + "proposed so the model has somewhere to keep its data" };
}

/**
 * Decide what opening this project means.
 *
 * A project with no model is the mirror of the bug above: the user lands in an empty viewer with no
 * way forward. Offering a blank, authorable model turns a dead end into the start of a drawing —
 * which is what the platform is for.
 */
export function decideProjectOpen(project: { source_ifc?: string | null;
                                             model_kind?: string | null }): ProjectOpenIntent {
  return project?.source_ifc || project?.model_kind ? "load-model" : "offer-blank-model";
}
