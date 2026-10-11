/** R23-PREFAB-KIT — the prefabrication-kit register, and the one write that makes a kit a document.
 *
 *  Added 2026-09-11 because **all three routes had no client caller at all**. The server side has
 *  been complete since R23: selector resolution against the model index, a BOM, scope-drift
 *  detection, and an eleven-code blocker severity order. None of it was reachable.
 *
 *  Two of the three could not even be *reported* dark: their leaf is `kits`, five characters, and
 *  `services/api/test_route_reachability.py` does not assess a leaf shorter than `MIN_SEGMENT`. The
 *  third, `freeze`, only became visible when that gate stopped letting English prose vouch for a
 *  route — *"…out of the wet/freeze season"* was the sentence standing in for it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

/** One line of a kit's bill of materials: a type, how many, and the quantities that rolled up. */
export interface PrefabBomLine {
  key: string;
  ifc_class: string | null;
  type_name: string | null;
  count: number;
  quantities: Record<string, number>;
}

/** What is stopping this kit. `code` orders the register; `detail` is what a person acts on. */
export interface PrefabBlocker { code: string; detail: string }

/** One kit, resolved against the model. */
export interface PrefabKit {
  id: string | number | null;
  ref: string | null;
  name: string | null;
  trade: string | null;
  fabricator: string | null;
  /** Workflow state. Which list IS the kit depends on it — see `scope_source`. */
  state: string;
  /**
   * `"selector"` before release, `"frozen"` after. This is not cosmetic: a released kit whose
   * scope still comes from the selector is a live query the shop is building against.
   */
  scope_source: "selector" | "frozen";
  /**
   * PREFAB-FREEZE-RACE — the token `prefabFreeze` must echo back, **opaque by contract.**
   *
   * The server composes it from the model version and the record's own `modified_at`, so it moves
   * when either half of the kit's scope moves. Nothing here may parse it or compare its parts: the
   * only operation is handing back the exact string this read returned. It is readable rather than
   * hashed so an operator can see which half moved in a log — a convenience for them, not a format
   * for us.
   */
  scope_version: string;
  selector: { selector: string; guids: string[]; matched: number; truncated?: boolean; error?: string };
  frozen_count: number;
  elements: number;
  bom: { lines: PrefabBomLine[]; totals: Record<string, number>; unresolved: string[] };
  /** Frozen scope vs what the selector matches NOW. `null` until the kit is frozen. */
  drift: { drifted: boolean; added: string[]; removed: string[]; means: string } | null;
  blockers: PrefabBlocker[];
  ready: boolean;
  as_of: string;
  needed_on_site?: string | null;
  pull_task?: { id: string | number | null; ref: string | null; state: string | null;
                open_constraints?: number } | null;
  delivery?: { id: string | number | null; ref: string | null; promised?: string | null } | null;
}

/** The register: every kit, worst first. */
export interface PrefabRegister {
  kits: PrefabKit[];
  total: number;
  ready: number;
  blocked: number;
  blocker_counts: Record<string, number>;
  as_of: string;
  /** False when no model is loaded — every scope figure below is then unverifiable, not zero. */
  model_loaded: boolean;
}

/** What freezing wrote. `frozen` is the count the shop will build against. */
export interface PrefabFreezeResult {
  ref: string | null;
  matched: number;
  selector: string;
  frozen: number;
  /** The token the NEXT write must echo — the write bumped the record, so the one just sent is
   *  spent. Handed back so a second freeze needs no extra read. */
  scope_version: string;
  note: string;
}

export function withPrefab<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class extends Base {
    /** Every prefab kit on the project, worst blocker first. */
    prefabRegister(pid: string, asOf?: string) {
      const q = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
      return this.json<PrefabRegister>(`/projects/${encodeURIComponent(pid)}/prefab/kits${q}`);
    }
    /** One kit, fully resolved: scope, BOM, drift, installing task and blockers. */
    prefabKit(pid: string, rid: string, asOf?: string) {
      const q = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
      return this.json<PrefabKit>(
        `/projects/${encodeURIComponent(pid)}/prefab/kits/${encodeURIComponent(rid)}${q}`);
    }
    /**
     * Freeze the kit's scope: resolve the selector once and write the GlobalId list onto the record.
     *
     * The server refuses an empty, erroring or truncated result with a 422 carrying a fixed literal
     * — a released kit with nothing frozen is indistinguishable from a correct one on every screen,
     * which is the failure the whole mechanism exists to prevent.
     *
     * **`scopeVersion` is required by the route, and it is a parameter rather than a default so
     * this method cannot be called without one.** PREFAB-FREEZE-RACE: the server re-resolves the
     * selector at write time, so without the token a model republished or a selector edited while
     * the confirmation dialog was open writes a GlobalId list the person never saw. Pass the
     * `scope_version` from the read the reader is looking at — not a fresh one, which would be a
     * token for numbers nobody has seen and would defeat the whole precondition.
     *
     * Three refusals, three codes: **400** no token sent, **409** the scope moved since that read,
     * **422** the scope itself cannot be frozen. A caller recovering from 409 re-reads the kit and
     * asks again against the new numbers.
     */
    prefabFreeze(pid: string, rid: string, scopeVersion: string) {
      const q = `?if_scope_version=${encodeURIComponent(scopeVersion)}`;
      return this.json<PrefabFreezeResult>(
        `/projects/${encodeURIComponent(pid)}/prefab/kits/${encodeURIComponent(rid)}/freeze${q}`,
        { method: "POST" });
    }
  };
}
