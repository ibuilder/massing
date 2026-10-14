/** Design options: generate + score envelope variants, and the stored options as ONE record.
 *
 *  Route-group `/projects/{pid}/design/*` — widened from `/design/options/*` on 2026-10-13 when
 *  DESIGN-STD-DARK added `/design/standards` and `/design/standards/check`. They are a sibling group
 *  under the same prefix and both were dark, so they belong with the design reads rather than in a
 *  two-method mixin of their own; no gate pins a mixin's prefix (checked — those lines are prose),
 *  which is why this is a header correction rather than a new file. Taken out of `client.ts` because the size ratchet
 *  in `services/api/test_file_sizes.py` says so in as many words — "a new endpoint added straight to
 *  `client.ts` will fail this, and that friction is the point." Adding `designOptionsRecord` there
 *  put the file 11 lines over its pin, so the group moved instead of the pin moving.
 *
 *  **`designOptionsRecord` is new, and it exists because the endpoint was unreachable.** It is not
 *  alone: `/design/options/{compare,carbon,economics}` have no client caller either, and no panel
 *  references the `design_option` register at all — the whole stored-option family was server-only.
 *  R22-OPTION-OBJECT's thesis is that no massing should be evaluated without its returns, which
 *  requires a human to see it, so a record nothing can fetch does not close the ring.
 *
 *  It is deliberately the ONLY one of the four wired: the record IS the join over the other three,
 *  so calling it replaces reconciling three screens by eye rather than adding a fourth.
 *
 *  Note `test_route_reachability` never flagged any of this. Its rule fires when a route's last
 *  static segment appears nowhere in the web source; `record` appears everywhere (`ModuleRecord`,
 *  `records`), so the route sits squarely in that gate's own documented false-negative class. The
 *  gate is honest about the blind spot — this is what falling into it looks like.
 *
 *  A mixin, so every call site resolves unchanged.
 */
import { HttpCore } from "./httpCore";
import type { DesignStandardCheck, OptionRecordSet } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withDesignOptions<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class DesignOptions extends Base {
  designOptionsGenerate(pid: string, base: Record<string, unknown>, types?: string[]) {
    return this.json<{ options: Record<string, unknown>[] }>(
      `/projects/${pid}/design/options/generate`,
      { method: "POST", body: JSON.stringify({ base, ...(types ? { types } : {}) }) });
  }
  designOptionsScore(pid: string, options: Record<string, unknown>[], weights?: Record<string, number>) {
    return this.json<{
      options: { label: string; building_type: string; composite: number; compliant: boolean;
        violations: string[]; cost_total: number; cost_per_sf: number | null;
        carbon_total_tco2e: number; carbon_intensity_kgco2e_m2: number;
        yield_net_sellable_m2: number; scores: Record<string, number>;
        massing: { floors: number; building_height_m: number; buildable_gfa_sf: number; units: number | null } }[];
      weights: Record<string, number>; recommended: string | null; note: string;
    }>(`/projects/${pid}/design/options/score`,
      { method: "POST", body: JSON.stringify({ options, ...(weights ? { weights } : {}) }) });
  }
  /**
   * The design options as one comparable record — geometry, unit mix, cost, carbon, returns.
   *
   * This is the join over `/design/options/{compare,carbon,economics}`, which is why the UI calls
   * this rather than those three: reconciling three screens by eye is how a massing gets evaluated
   * without its returns, one screen at a time. It re-derives nothing — every number comes from the
   * engine that owns it — so it cannot disagree with a screen opened beside it.
   */
  // --- design standards: the ruleset a firm standardises on, and the model against it -----------
  /**
   * DESIGN-STD-DARK — the loaded model audited against the firm's design standards: prohibited
   * matches, and (only when an approved set is declared) elements matching nothing approved.
   *
   * The ruleset is **already authorable**: `design_standards.ruleset` reads the `design_standard`
   * module register, so a firm records approved / preferred / prohibited assemblies through the
   * generic register UI today. What was missing was anything that READ them.
   *
   * **There is deliberately NO `designStandards()` method for the sibling `/design/standards`**, and
   * dropping it is this file's own rule working. `check()` returns `"ruleset": rs` — the whole
   * ruleset, as the standalone route would serve it — so a method for that route would have had no
   * caller the moment it was written, which is precisely what
   * `apps/web/src/api/clientCallers.test.ts` exists to catch. *A route whose payload is a strict
   * subset of another route's is not a second capability.* It stays frozen in
   * `test_route_reachability.UNREACHABLE_ROUTES` with that reason recorded there.
   *
   * Read `coverage` on every answer, not just the counts. `model_scored: false` returns two zeros
   * that read as a clean audit; `approved_declared: 0` makes `unapproved` count nothing; and the
   * violation LIST is capped while the counts stay complete, so `coverage.flagged` is the total and
   * `violations.length` is a page.
   */
  designStandardsCheck(pid: string) {
    return this.json<DesignStandardCheck>(`/projects/${pid}/design/standards/check`);
  }
  designOptionsRecord(pid: string) {
    return this.json<OptionRecordSet>(`/projects/${pid}/design/options/record`);
  }
  };
}
