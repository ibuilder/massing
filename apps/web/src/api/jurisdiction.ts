/** R23-JURISDICTION-PACKS — data requirements that belong to an authority, and the client that
 *  could not reach any of them.
 *
 *  Added 2026-09-11. All **five** routes of this feature had no client caller: the library, the
 *  import and the delete (admin-gated), and the two that CONSUME a pack —
 *  `/projects/{pid}/jurisdiction/requirements` and `/projects/{pid}/jurisdiction/check`. The server
 *  side has been complete since R23: validation that refuses an uncited pack, selector parsing with
 *  the same parser that evaluates it, and a check that carries its own attribution.
 *
 *  The frozen three were visible to `services/api/test_route_reachability.py`. The two consumers
 *  were not, for two different reasons recorded in that file: `check` shares its last segment with
 *  `/projects/{pid}/standards/check`, which the client genuinely calls, and `requirements` collides
 *  with unrelated text. **A leaf is not a name** — which is why the feature read as three-fifths
 *  dark rather than dark.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

/** One requirement inside a pack — `rule_library`-shaped, and evaluated by that same engine. */
export interface PackRequirement {
  id: string;
  name: string;
  /** Which elements the requirement is about. */
  scope: string;
  /** What must hold for them. */
  require: string;
  severity: string;
}

/**
 * A data-requirement pack: a named, versioned, ATTRIBUTED set of requirements keyed to a place.
 *
 * `authority`, `edition` and `source` are required by the server, and the reason is the whole point
 * of the feature: this pack will be used to fail somebody else's model, and they have to be able to
 * go and read the rule. A requirement nobody can trace is a house rule wearing a regulator's name.
 */
export interface JurisdictionPack {
  id: string;
  jurisdiction: string;
  authority: string;
  name: string;
  edition: string;
  source: string;
  /** True only for the built-in `example`, which asserts nothing about any real place. */
  is_example?: boolean;
  requirements: PackRequirement[];
}

/** The library: every pack available, optionally narrowed to one jurisdiction. */
export interface PackLibrary { packs: JurisdictionPack[]; count: number; note?: string }

/** Which packs apply to a project, and — when none do — why. */
export interface ProjectRequirements {
  jurisdiction: string | null;
  packs: JurisdictionPack[];
  adopted: boolean;
  /** Set when nothing applies. Null when packs resolved normally. */
  why?: string | null;
  /** True when a pack was applied by id rather than resolved from the project's jurisdiction. */
  explicit?: boolean;
  note?: string;
}

/** One pack's result, carrying the authority whose rules produced the number. */
export interface PackResult {
  id: string | null;
  name: string | null;
  authority: string | null;
  edition: string | null;
  source: string | null;
  is_example: boolean;
  total_rules: number;
  failing_rules: number;
  total_violations: number;
  rules?: { id: string; name?: string; severity?: string; matched?: number; violations?: number }[];
}

/**
 * The check. `model_scored` false means no model was loaded — every figure below is then absent,
 * not zero, and a client that renders 0/0 as "compliant" says the opposite of what happened.
 */
export interface JurisdictionCheck {
  jurisdiction: string | null;
  adopted?: boolean;
  why?: string | null;
  explicit?: boolean;
  model_scored: boolean;
  packs: PackResult[];
  total_requirements: number;
  failing_requirements?: number;
  total_violations?: number;
  satisfied?: boolean;
  attribution?: { pack: string | null; authority: string | null; edition: string | null;
                  is_example: boolean }[];
  note?: string;
}

/** What a delete removed. */
export interface PackDeleted { deleted: string }

export function withJurisdiction<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class extends Base {
    /** Every data-requirement pack available, optionally filtered to one jurisdiction. */
    jurisdictionPacks(jurisdiction?: string) {
      const q = jurisdiction ? `?jurisdiction=${encodeURIComponent(jurisdiction)}` : "";
      return this.json<PackLibrary>(`/jurisdiction/packs${q}`);
    }
    /**
     * Import a pack from an authority. Admin-only, and refused with a 422 whose `detail` names the
     * missing citation field or the unparseable selector — surface it verbatim rather than a
     * generic failure, because the refusal is the instruction.
     */
    jurisdictionImportPack(pack: unknown) {
      return this.json<JurisdictionPack>("/jurisdiction/packs",
        { method: "POST", body: JSON.stringify(pack) });
    }
    /** Remove an imported pack. The built-in example cannot be deleted (404). */
    jurisdictionDeletePack(packId: string) {
      return this.json<PackDeleted>(`/jurisdiction/packs/${encodeURIComponent(packId)}`,
        { method: "DELETE" });
    }
    /** The packs that apply to this project — resolved from its jurisdiction, or one by id. */
    projectRequirements(pid: string, pack?: string) {
      const q = pack ? `?pack=${encodeURIComponent(pack)}` : "";
      return this.json<ProjectRequirements>(
        `/projects/${encodeURIComponent(pid)}/jurisdiction/requirements${q}`);
    }
    /** Check the project's model against those requirements. */
    jurisdictionCheck(pid: string, pack?: string) {
      const q = pack ? `?pack=${encodeURIComponent(pack)}` : "";
      return this.json<JurisdictionCheck>(
        `/projects/${encodeURIComponent(pid)}/jurisdiction/check${q}`);
    }
  };
}
