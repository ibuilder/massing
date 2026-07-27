import { KernelError } from "./errors.js";
import { err, ok, type Result } from "./result.js";

export interface Identity {
  readonly id: string;
  readonly displayName?: string;
  readonly roles: readonly string[];
  readonly attributes?: Readonly<Record<string, unknown>>;
}

/** The anonymous subject used before a host installs a real identity. */
export const ANONYMOUS_IDENTITY: Identity = Object.freeze({
  id: "anonymous",
  displayName: "Anonymous",
  roles: Object.freeze([]) as readonly string[],
});

export interface PermissionRequest {
  /** Dotted verb, e.g. `"massing.story.edit"` or `"markup.issue.assign"`. */
  readonly action: string;
  /** Optional target — a model id, project id, or record id. */
  readonly resource?: string;
  readonly context?: Readonly<Record<string, unknown>>;
}

export interface PermissionEvaluator {
  evaluate(identity: Identity, request: PermissionRequest): boolean | Promise<boolean>;
}

/**
 * Default posture: permit everything.
 *
 * The kernel ships permission *hooks*, not a policy. A standalone desktop session has no
 * meaningful authorization boundary, and a kernel that denied by default would force every host to
 * write a policy before the first command could run. Hosts that need enforcement install their own
 * evaluator; the enforcement path is identical either way, so it is exercised from day one.
 */
export const ALLOW_ALL: PermissionEvaluator = Object.freeze({
  evaluate: () => true,
});

/** Grants an action if the identity holds any role listed for it (exact match or `*` wildcard). */
export function createRoleEvaluator(
  grants: Readonly<Record<string, readonly string[]>>,
): PermissionEvaluator {
  return {
    evaluate(identity, request) {
      const allowed = grants[request.action] ?? grants["*"];
      if (!allowed) return false;
      return allowed.some((role) => role === "*" || identity.roles.includes(role));
    },
  };
}

export class PermissionService {
  #identity: Identity = ANONYMOUS_IDENTITY;
  #evaluator: PermissionEvaluator = ALLOW_ALL;

  get identity(): Identity {
    return this.#identity;
  }

  setIdentity(identity: Identity): void {
    this.#identity = identity;
  }

  setEvaluator(evaluator: PermissionEvaluator): void {
    this.#evaluator = evaluator;
  }

  /**
   * Never throws and never propagates an evaluator failure as an allow.
   *
   * A policy that throws is an *indeterminate* answer, and the only safe reading of indeterminate
   * in an authorization check is "no" — failing open here would turn a bug in a host's policy into
   * a silent privilege escalation.
   */
  async can(request: PermissionRequest): Promise<boolean> {
    try {
      return await this.#evaluator.evaluate(this.#identity, request);
    } catch {
      return false;
    }
  }

  async require(request: PermissionRequest): Promise<Result<void>> {
    if (await this.can(request)) return ok(undefined);
    return err(
      new KernelError("PERMISSION_DENIED", `Identity "${this.#identity.id}" may not "${request.action}".`, {
        action: request.action,
        identity: this.#identity.id,
        ...(request.resource === undefined ? {} : { resource: request.resource }),
      }),
    );
  }
}
