/** Stakeholder analysis — who are the parties, and how does each need managing?
 *
 *  STAKEHOLDER-MEDIUM. Route-group `/projects/{pid}/stakeholders`, one method, and a file of its
 *  own on purpose.
 *
 *  **Why NOT `api/responsibility.ts`, which is the adjacent subject and the panel that hosts this
 *  card.** That file's own header states the reason it is a grouping at all: *"the backend agrees
 *  exactly: `aec_api/routers/responsibility.py` holds these four routes and nothing else. A 1:1
 *  correspondence with a router is the strongest corroboration available for a grouping."* This
 *  route is in `routers/construction.py`, so putting it there would break the one property that
 *  file cites as its justification — *a grouping rule you set aside for a convenient case was never
 *  a rule* — and the evidence it offers would quietly stop being true.
 *
 *  **Why not `api/client.ts`.** `services/api/test_file_sizes.py` says it in as many words: "a new
 *  endpoint added straight to `client.ts` will fail this, and that friction is the point."
 *
 *  A mixin, so every call site resolves unchanged.
 */
import type { HttpCore } from "./httpCore";
import type { StakeholderAnalysis } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withStakeholder<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Stakeholder extends Base {
  /**
   * The Mendelow power/interest grid over the stakeholder register, plus the blockers.
   *
   * Read `grid` before the quadrants: the register scores power and interest on THREE levels and
   * the grid splits at `High`, so a wall of "Monitor" may mean "everybody is Medium" rather than
   * "nobody matters" — and `quadrants.unassessed` is the parties the grid could not place at all.
   */
  stakeholderAnalysis(pid: string) {
    return this.json<StakeholderAnalysis>(`/projects/${pid}/stakeholders/analysis`);
  }
  };
}
