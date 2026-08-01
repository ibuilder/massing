/**
 * Permissions and the audit trail.
 *
 * Two things an enterprise deployment needs that a viewer cannot supply on its own, because both
 * are answered by the host's own identity and compliance systems. What this module provides is the
 * *seam*: a single place every mutation passes through, so a host can say no, and a single record
 * of what happened, so a host can prove what was done and by whom.
 *
 * ## Why this is enforced and not merely displayed
 *
 * Hiding a button is not a permission. The store is scriptable, the viewer is on `window` in most
 * integrations, and markups also arrive over the wire. A check that lives in the toolbar stops an
 * honest user from making a mistake and stops nobody else. This one sits in the store, which every
 * path — tool, keyboard, import, adapter, host script — has to go through.
 *
 * It is still *client-side*, and client-side checks are advisory: they cannot bind an attacker who
 * controls the browser. The server remains the authority. What this buys is that the client agrees
 * with the server rather than presenting an interface that lets people do things their role
 * forbids, and that every attempt is recorded either way.
 */
import type { Annotation } from "./types";

/**
 * Something a user may or may not be allowed to do.
 *
 * Deliberately about *acts*, not about UI. `markup:editOthers` is separate from `markup:edit`
 * because "may annotate" and "may change someone else's annotation" are genuinely different
 * permissions on a review, and conflating them is how a subcontractor ends up able to silently
 * reword the architect's comment.
 */
export type Capability =
  | "markup:create"
  | "markup:edit"
  | "markup:editOthers"
  | "markup:delete"
  | "markup:deleteOthers"
  | "markup:status"
  | "calibrate"
  | "sheet:edit"
  | "export"
  | "import";

/** What is being attempted, for a host that decides per-record rather than per-role. */
export interface PermissionRequest {
  capability: Capability;
  /** The record being acted on, when there is one. */
  annot?: Annotation;
  /** Who is acting, as the viewer knows them. */
  actor: string;
  page?: number;
}

/**
 * A host's answer. `true` allows; `false` or a string denies, and a string is shown to the user.
 *
 * Returning a reason matters: "you can't do that" with no explanation generates a support ticket,
 * and on a construction review the reason is usually specific and knowable ("the drawing is issued
 * for construction and is locked").
 */
export type PermissionDecision = boolean | string;

/** Decide whether an act is allowed. Absent means everything is allowed. */
export type PermissionCheck = (request: PermissionRequest) => PermissionDecision;

/**
 * One line of the audit trail.
 *
 * Shaped to be written straight to a log pipeline: flat, serialisable, and carrying the identifiers
 * needed to correlate it with the server's own record. Construction markups become contract
 * evidence, so who-changed-what-when is not telemetry — it is often the point of the system.
 */
export interface AuditEvent {
  /** ISO-8601, UTC. */
  at: string;
  actor: string;
  /** What was attempted, e.g. `markup:create`, or `export:xfdf`. */
  action: string;
  /** Whether it went ahead. A denial is as worth recording as a success. */
  allowed: boolean;
  /** Why it was denied, when the host gave a reason. */
  reason?: string;
  annotId?: string;
  annotKind?: string;
  page?: number;
  documentId?: string;
  /** Whatever else is worth keeping for this action — kept loose on purpose. */
  detail?: Record<string, unknown>;
}

/** Receives every audited act. Must not throw; a logging failure cannot be allowed to block work. */
export type AuditSink = (event: AuditEvent) => void;

/**
 * Enforces {@link PermissionCheck} and records to {@link AuditSink}.
 *
 * Constructed with no check and no sink by default, which is what a standalone or single-user
 * deployment wants: everything allowed, nothing recorded, no overhead.
 */
export class Policy {
  constructor(
    private readonly opts: {
      check?: PermissionCheck;
      audit?: AuditSink;
      actor: () => string;
      documentId?: () => string | undefined;
      /**
       * Called when something is refused, with the reason.
       *
       * A refusal the user cannot see is indistinguishable from a bug: they drew a cloud, nothing
       * appeared, and no explanation was offered. The viewer wires this to a notice.
       */
      onDeny?: (reason: string, capability: Capability) => void;
    },
  ) {}

  /** Whether anything is being enforced or recorded. Lets hot paths skip the work entirely. */
  get active(): boolean {
    return Boolean(this.opts.check || this.opts.audit);
  }

  /**
   * Ask whether an act is allowed, and record the answer.
   *
   * A check that throws denies. A host's permission logic reaching out to a stale cache and
   * failing should not silently grant everything — failing closed is the only safe direction here.
   */
  allows(capability: Capability, annot?: Annotation, detail?: Record<string, unknown>): boolean {
    const actor = this.opts.actor();
    let decision: PermissionDecision = true;
    if (this.opts.check) {
      try {
        decision = this.opts.check({
          capability,
          actor,
          ...(annot ? { annot } : {}),
          ...(annot?.page !== undefined ? { page: annot.page } : {}),
        });
      } catch {
        decision = "The permission check failed, so the action was refused.";
      }
    }
    const allowed = decision === true;
    if (!allowed) {
      const reason = typeof decision === "string"
        ? decision
        : `You do not have permission for ${describe(capability)}.`;
      this.opts.onDeny?.(reason, capability);
    }
    this.record(capability, allowed, {
      ...(typeof decision === "string" ? { reason: decision } : {}),
      ...(annot ? { annot } : {}),
      ...(detail ? { detail } : {}),
    });
    return allowed;
  }

  /** Record something that is not gated — an export that happened, a document that was opened. */
  record(
    action: string,
    allowed: boolean,
    extra: { reason?: string; annot?: Annotation; detail?: Record<string, unknown> } = {},
  ): void {
    const sink = this.opts.audit;
    if (!sink) return;
    const doc = this.opts.documentId?.();
    const event: AuditEvent = {
      at: new Date().toISOString(),
      actor: this.opts.actor(),
      action,
      allowed,
      ...(extra.reason ? { reason: extra.reason } : {}),
      ...(extra.annot ? { annotId: extra.annot.id, annotKind: extra.annot.kind, page: extra.annot.page } : {}),
      ...(doc ? { documentId: doc } : {}),
      ...(extra.detail ? { detail: extra.detail } : {}),
    };
    try {
      sink(event);
    } catch (e) {
      // The audit sink is the host's code. A broken logger must not stop someone marking up a
      // drawing, but it must not disappear either.
      console.error("[massing-pdf] audit sink threw", e);
    }
  }
}

/**
 * A ready-made check for the common shape: a set of granted capabilities, plus ownership.
 *
 * Most hosts want "this role may do these things, and may only touch its own markups" — which is
 * fiddly enough to get subtly wrong that it is worth providing rather than describing.
 */
export function capabilityCheck(options: {
  granted: readonly Capability[];
  /** Identify the current user, to compare against a markup's author. Defaults to the actor. */
  isOwner?: (annot: Annotation, actor: string) => boolean;
}): PermissionCheck {
  const granted = new Set(options.granted);
  const owns = options.isOwner ?? ((annot: Annotation, actor: string) => annot.author === actor);

  return ({ capability, annot, actor }) => {
    if (!granted.has(capability)) return `Your role does not allow ${describe(capability)}.`;
    // Editing or deleting someone else's markup needs the "others" capability as well as the base
    // one — holding `markup:edit` alone means you may edit your own.
    //
    // `markup:status` is deliberately not in this list: closing an issue someone else raised is the
    // normal review workflow, so the capability means "may move anyone's issue along". It is only a
    // coherent grant because the store checks every capability a patch implies — a patch bundling
    // a status change with a reworded subject needs `markup:edit` too.
    if (annot && (capability === "markup:edit" || capability === "markup:delete") && !owns(annot, actor)) {
      const escalated = capability === "markup:edit" ? "markup:editOthers" : "markup:deleteOthers";
      if (!granted.has(escalated)) {
        return `This markup belongs to ${annot.author}, and your role does not allow changing other people's markups.`;
      }
    }
    return true;
  };
}

const LABELS: Record<Capability, string> = {
  "markup:create": "creating markups",
  "markup:edit": "editing markups",
  "markup:editOthers": "editing other people's markups",
  "markup:delete": "deleting markups",
  "markup:deleteOthers": "deleting other people's markups",
  "markup:status": "changing a markup's status",
  calibrate: "setting the drawing scale",
  "sheet:edit": "editing sheet details",
  export: "exporting",
  import: "importing",
};

const describe = (c: Capability): string => LABELS[c] ?? c;

/**
 * Thrown when a host's scripting call is refused.
 *
 * Only for the explicit API surface. An interactive gesture that a policy declines is not
 * exceptional — the user simply may not do that — and throwing there would turn a routine refusal
 * into an unhandled rejection in the pointer loop.
 */
export class PermissionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PermissionError";
  }
}
