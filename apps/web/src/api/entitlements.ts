import { HttpCore } from "./httpCore";
import type { EntitlementConditions, ReviewCycles } from "./types";

/**
 * Entitlements — the `/projects/{pid}/entitlements/…` route group.
 *
 * SCALE-SEAM ㉑, forced rather than chosen: adding `entitlementConditions` put `client.ts` at 3,136
 * against a 3,129 ratchet. That pin's own comment says the friction should buy a cluster out of the
 * file instead of buying the pin a higher number, and `/entitlements` is a clean route group — the
 * rule ⑫–⑳ used, applied to two methods rather than seven.
 *
 * Both answer R22-ENTITLEMENT's question — the hole between "we underwrite the deal" and "we build
 * it" — from opposite ends: `entitlementReviewCycles` measures the time an application has already
 * spent and whose court held it; `entitlementConditions` tracks what an approval obliges us to do
 * afterwards. Neither ever reports a condition satisfied or a round scored on incomplete data.
 */
type Ctor<T> = new (...args: any[]) => T;

export function withEntitlements<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Entitlements extends Base {
  /** R22-ENTITLEMENT review rounds, split by whose court held them. See {@link ReviewCycles}. */
  entitlementReviewCycles(pid: string, application?: string) {
    return this.json<ReviewCycles>(`/projects/${pid}/entitlements/review-cycles`
      + (application ? `?application=${encodeURIComponent(application)}` : ""));
  }

  /** R22-ENTITLEMENT — an approval's conditions as tracked items rather than one paragraph.
   *  Nothing is ever reported satisfied: a condition whose topic and quantity cannot be read is
   *  `unparsed`, because an approval condition silently treated as met is a building put up out of
   *  compliance while the report said it was fine. */
  entitlementConditions(pid: string) {
    return this.json<EntitlementConditions>(`/projects/${pid}/entitlements/conditions`);
  }

  /** R22-ENTITLEMENT ② — approval conditions checked against the model (height max, parking min).
   *  Anything unevaluable is `not_checkable`, never a pass. Refused entitlements are listed, not scored. */
  entitlementConditionChecks(pid: string) {
    return this.json<{
      project_id: string;
      model_facts: { height_m: number | null; storeys: number | null; parking_spaces: number | null };
      entitlements: {
        entitlement_id: string; ref: string | null; workflow_state: string; refused: boolean;
        exceeds_count: number; not_checkable_count: number; checked_count?: number;
        exceeds?: { topic: string; note?: string }[];
        not_checkable?: { topic: string; reason?: string }[];
      }[];
      in_force_count: number;
      refused: { ref: string | null; workflow_state: string }[];
      total_exceeds: number; total_not_checkable: number; note: string;
    }>(`/projects/${pid}/entitlements/condition-checks`);
  }
  };
}
