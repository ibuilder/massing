/** Code compliance: IBC code analysis, egress/occupant load, IEBC existing-building classification,
 *  adopted code editions, and the plan-reviewer approvability pre-flight.
 *
 *  SCALE-SEAM ㉖. Grouped by what the methods ANSWER rather than by a single route prefix, which is
 *  a departure from ㉔ and ㉕ and is deliberate: the group spans `/projects/{pid}/codecheck`,
 *  `/codes/adoptions` and `/codes/ebc/pathways`, and splitting it on the prefix would have put
 *  `ebcClassify` and `ebcPathways` — two halves of one screen — in two files. **The route prefix was
 *  never the point; it was a cheap proxy for "one feature", and here it stops being one.**
 *
 *  Two RFI methods sat INSIDE this run in `client.ts` (`rfiReadiness`, `rfiReadinessBcf`) and did not
 *  come with it. Adjacency in a file is not a relationship — the same lesson ㉕ recorded about
 *  `MaterialEntry`, met a second time and acted on the same way.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withCodeCheck<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class CodeCheck extends Base {
  // W9-2 computed occupancy load (IBC 1004) + egress capacity (IBC 1005) — pre-check assist
  codecheckEgress(pid: string) {
    return this.json<{
      building: { occupant_load: number; area_ft2: number; spaces: number; spaces_missing_area: number };
      egress: { required_width_in: number; provided_width_in: number; adequate: boolean | null; factor_in_per_occ: number; code: string };
      doors: { checked: number; below_min_32in: number; fail_guids: string[]; min_clear_m: number; code: string };
      by_occupancy: { occupancy: string; factor: number; basis: string; spaces: number; area_ft2: number; load: number }[];
      spaces: { guid: string; name: string | null; occupancy: string; area_ft2: number | null; load: number | null; needs_2_exits?: boolean; note?: string }[];
      citations: string[]; disclaimer: string;
    }>(`/projects/${pid}/codecheck/egress`);
  }

  /** W11 D1: the IBC code-analysis summary (occupancy, construction type, area/stories, occupant load,
   *  egress, governing sections) for the G-series code sheet. */
  codeAnalysis(pid: string, opts: { occupancy_group?: string; construction_type?: string; sprinklered?: boolean; jurisdiction?: string } = {}) {
    const q = new URLSearchParams();
    if (opts.occupancy_group) q.set("occupancy_group", opts.occupancy_group);
    if (opts.construction_type) q.set("construction_type", opts.construction_type);
    if (opts.sprinklered) q.set("sprinklered", "true");
    if (opts.jurisdiction) q.set("jurisdiction", opts.jurisdiction);
    return this.json<{ code_context: { jurisdiction: string | null; ibc_edition: number | null; resolved: boolean; as_of: number | null; verify: string };
      occupancy: { group: string; primary: string; mix: string[] };
      construction_type: string; sprinklered: boolean;
      building: { gross_area_ft2: number; stories: number; occupant_load: number };
      occupant_load_by_occupancy: { occupancy: string; load: number; area_ft2: number }[];
      egress: { required_width_in: number; provided_width_in: number; adequate: boolean | null };
      doors: { checked: number; below_min_32in: number };
      allowable: { note: string; sections: string[]; sprinkler_increase: string };
      citations: string[]; disclaimer: string }>(`/projects/${pid}/codecheck/analysis?${q.toString()}`);
  }

  /** CODE-1: resolve a jurisdiction (USPS state code) to its adopted code editions (baseline fallback). */
  codeAdoptions(jurisdiction: string) {
    return this.json<{ jurisdiction: string | null; resolved: boolean; as_of: number | null;
      codes: { family: string; edition: number; name: string; source: string }[];
      primary: { IBC: number | null; IECC: number | null; "A117.1": number | null }; verify: string }>(
      `/codes/adoptions?jurisdiction=${encodeURIComponent(jurisdiction)}`);
  }

  /** CODE-EBC: classify an existing-building scope under the IEBC Work Area Method. `infer` first-guesses
   * the scope from the model's phasing (existing vs new/demolish); explicit flags override the guess. */
  ebcClassify(pid: string, opts: { jurisdiction?: string; infer?: boolean; adds_area?: boolean;
    changes_occupancy?: boolean; reconfigures_space?: boolean; alters_openings?: boolean;
    alters_systems?: boolean; adds_equipment?: boolean; replaces_same_purpose?: boolean;
    repair_only?: boolean; work_area_pct?: number } = {}) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
    return this.json<{ ok: boolean; classification: string | null; classification_key?: string;
      method?: string; method_cite?: string; gist?: string; reason?: string;
      work_area_pct?: number | null; triggers?: string[];
      code: { family: string; edition: number | null; name?: string; jurisdiction: string | null; adoption_resolved?: boolean };
      applies?: { classification: string; section: string; requirements: string }[];
      citations?: { classification: string; section: string; requirements: string }[];
      methods: { key: string; name: string; cite: string; gist: string }[];
      notes?: string[]; inferred?: Record<string, unknown>; basis?: string[];
      phase_counts?: Record<string, number>; verify: string; disclaimer: string }>(
      `/projects/${pid}/codecheck/ebc?${q.toString()}`);
  }

  /** CODE-EBC: the IEBC reference catalog — compliance methods + Work-Area classifications with citations. */
  ebcPathways() {
    return this.json<{ code: { family: string; name: string };
      methods: { key: string; name: string; cite: string; gist: string }[];
      classifications: { key: string; label: string; class_cite: string; req_cite: string; gist: string }[];
      work_area_threshold_pct: number; verify: string; disclaimer: string }>(`/codes/ebc/pathways`);
  }

  /** W11 D8: plan-reviewer approvability pre-flight (egress, door widths, occupancy, rated assemblies). */
  approvability(pid: string) {
    return this.json<{ checks: { check: string; citation: string; status: string; detail: string; guids?: string[] }[];
      summary: { passed: number; failed: number; gating: number; ready: boolean; score_pct: number | null };
      disclaimer: string }>(`/projects/${pid}/codecheck/approvability`);
  }

  codecheckEgressBcf(pid: string) {
    return this.json<{ created: number; topics: string[] }>(`/projects/${pid}/codecheck/egress/bcf`, { method: "POST", body: "{}" });
  }

  codeComplianceCheck(pid: string, description: string, context?: string) {
    return this.json<{ topics: { code: string; section: string; title: string; requirement: string }[];
      detected?: { occupancy?: { group: string; label: string } | null; area_sf?: number | null;
      stories?: number | null }; source: string; message?: string }>(
      `/projects/${pid}/codecheck`, { method: "POST", body: JSON.stringify({ description, context }) });
  }

  /** GOLDEN-THREAD — requirement → evidence → sign-off rollup, plus the broken-thread list. */
  goldenThread(pid: string) {
    return this.json<{
      total: number; signed_off: number; evidenced: number;
      completeness_pct: number; evidenced_pct: number;
      by_outcome: Record<string, number>; by_category: Record<string, number>;
      broken_count: number;
      broken_thread: { ref: string; requirement: string; category: string; outcome: string;
        state: string; has_evidence: boolean; risk: string }[];
      note: string;
    }>(`/projects/${pid}/golden-thread`);
  }
  };
}
