/** MEP systems: summary, connectivity, sizing, sprinkler coverage, fittings, model extract.
 *
 *  SCALE-SEAM ⑲. Route-group `/projects/{pid}/mep`, taken out of `client.ts` by the route
 *  each method calls. Seven methods in **four** regions — summary/connectivity/sizing/sprinkler
 *  next to LOD-500 authoring, fittings after progress-actuals, a second `mep()` GET next to
 *  energy, model-extract next to LOD/envelope audits. `connectMep` / `addMepFitting` call
 *  `editIfc` (`/edit`) and stay.
 *
 *  Two methods hit GET `/mep` with different response types (`mepSummary` vs `mep`); both move.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

export function withMep<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Mep extends Base {
  /** First-pass MEP sizing. `kind`:
   *   - `duct` (flow = CFM, velocity = fpm) · `pipe` (flow = GPM, velocity = fps)
   *   - `cooling` — converts a load you already have (BTU/h) into tons
   *   - `block_cooling` — *estimates* the load from gross floor area, the earlier question, asked
   *     when no load exists yet. Omit `gfaSf` to have the server derive it from the loaded model.
   *   - `hanger` (hangerKind = duct | pipe_steel | pipe_copper, size = in)
   *
   *  The route has been complete since v0.3.1116 and had no caller in this app, which is what made
   *  `block_cooling` product-unreachable rather than merely unused. Lives here rather than in
   *  `client.ts` because the extraction ratchet in `services/api/test_file_sizes.py` asks the
   *  question a new endpoint should be asked — "should this be in a domain module?" — and for a
   *  `/projects/{pid}/mep` route the answer is yes.
   */
  mepSize(pid: string, kind: "duct" | "pipe" | "cooling" | "block_cooling" | "hanger",
          opts: { flow?: number; velocity?: number; load?: number; size?: number;
                  hangerKind?: string; gfaSf?: number; sfPerTon?: number } = {}) {
    const q = new URLSearchParams({ kind });
    if (opts.flow !== undefined) q.set("flow", String(opts.flow));
    if (opts.velocity !== undefined) q.set("velocity", String(opts.velocity));
    if (opts.load !== undefined) q.set("load", String(opts.load));
    if (opts.size !== undefined) q.set("size", String(opts.size));
    if (opts.hangerKind !== undefined) q.set("hanger_kind", opts.hangerKind);
    if (opts.gfaSf !== undefined) q.set("gfa_sf", String(opts.gfaSf));
    if (opts.sfPerTon !== undefined) q.set("sf_per_ton", String(opts.sfPerTon));
    return this.json<Record<string, unknown>>(`/projects/${pid}/mep/size?${q.toString()}`);
  }

  /** W11 B6 + MEP-FP: MEP system browser — systems (with discipline: hvac/plumbing/electrical/fire/comms)
   * with segment/fitting/terminal counts + connectivity signal, and a by-discipline rollup. */
  mepSummary(pid: string) {
    return this.json<{ total_systems: number; unassigned: { segments: number; fittings: number };
      has_fire_protection?: boolean; by_discipline?: Record<string, { systems: number; members: number }>;
      systems: { guid: string; name: string; discipline?: string; predefined_type?: string | null;
        members: number; segments: number; fittings: number;
        terminals: number; other: number; elements_with_open_ports: number }[] }>(`/projects/${pid}/mep`);
  }
  /** W10-4: MEP connectivity validation — ports connected/open, links, dangling (floating) elements. */
  mepConnectivity(pid: string) {
    return this.json<{ elements: number; ports_total: number; ports_connected: number; ports_open: number;
      connections: number; dangling_count: number; connected_pct: number;
      dangling: { guid: string; class: string; name: string | null }[] }>(`/projects/${pid}/mep/connectivity`);
  }
  /** MEP-SIZE: velocity/fill size checks over authored MEP (air/water velocity vs limits), pass/fail. */
  mepSizing(pid: string, opts?: { ductMaxFpm?: number; pipeMaxFps?: number }) {
    const q = new URLSearchParams();
    if (opts?.ductMaxFpm != null) q.set("duct_max_fpm", String(opts.ductMaxFpm));
    if (opts?.pipeMaxFps != null) q.set("pipe_max_fps", String(opts.pipeMaxFps));
    const qs = q.toString();
    return this.json<{
      checked: number; passed: number; failed: number; info: number; all_pass: boolean;
      limits: { duct_max_fpm: number; pipe_max_fps: number; tray_max_fill: number };
      checks: {
        guid: string; class: string; system: string | null; size_mm: number; shape: string;
        flow: number | null; flow_unit: string | null; parameter: string;
        value_fpm?: number; value_fps?: number; value?: number | null;
        limit_fpm?: number; limit_fps?: number; limit?: number;
        status: "pass" | "fail" | "info"; note: string;
      }[];
      disclaimer: string;
    }>(`/projects/${pid}/mep/sizing${qs ? `?${qs}` : ""}`);
  }
  /** MEP-FP: NFPA-13-informed sprinkler coverage pre-check (head count vs area ÷ max coverage per hazard). */
  sprinklerCoverage(pid: string, hazard = "light") {
    return this.json<{ hazard: string; sprinkler_heads: number; protected_area_m2: number; spaces_measured: number;
      max_coverage_m2_per_head: number; required_heads: number; adequate: boolean | null; shortfall: number | null;
      citation: string; note: string; verify: string }>(
      `/projects/${pid}/mep/sprinkler-coverage?hazard=${encodeURIComponent(hazard)}`);
  }
  /** MEP-FITTINGS: implied tee/cross/reducer/elbow over the port graph → QTO EA lines (deterministic, no CV). */
  mepFittings(pid: string) {
    return this.json<{
      element_count: number;
      fittings: { tee: number; cross: number; reducer: number; elbow: number };
      total_fittings: number;
      by_type: { type: string; count: number }[];
      qto_lines: { item: string; fitting: string; unit: string; qty: number }[];
      unknown_size_joints: number;
      details: { guid: string; ifc_class: string; fitting: string; count: number; reason: string }[];
      note: string;
    }>(`/projects/${pid}/mep/fittings`);
  }
  mep(pid: string) {
    return this.json<{ by_class: Record<string, number>; systems: Record<string, string>; total_distribution_elements: number }>(`/projects/${pid}/mep`);
  }
  mepModelExtract(pid: string) {
    return this.json<{ model_scored: boolean; mep_elements: number;
      by_class: { ifc_class: string; label: string; count: number }[] }>(
      `/projects/${pid}/mep/model-extract`);
  }
  /** Friction-loss screen over authored duct/pipe runs (empirical round-duct + Hazen-Williams). */
  mepPressureLoss(pid: string) {
    return this.json<{
      checked: number; failed: number;
      budgets: { duct_in_wg_per_100ft: number; pipe_ft_per_100ft: number; hazen_c: number };
      runs: { guid: string; class: string; kind: string; system: string | null; size_mm: number;
        flow: number; length_ft: number; friction_rate: number; rate_unit: string; loss: number;
        budget_rate: number; status: string }[];
      systems: { system: string; kind: string; runs: number; total_length_ft: number;
        total_loss: number; loss_unit: string;
        index_run: { guid: string; loss: number; friction_rate: number };
        all_within_budget: boolean }[];
      disclaimer: string;
    }>(`/projects/${pid}/mep/pressure-loss`);
  }
  /** NEC 392.22 cable-tray fill from authored conductors, not a supplied ratio. */
  mepTrayFill(pid: string) {
    return this.json<Record<string, unknown>>(`/projects/${pid}/mep/tray-fill`);
  }
  /** Space-by-space cooling-load screen vs the single-number block estimate. */
  mepThermalLoads(pid: string) {
    return this.json<{
      spaces: { guid: string; name: string | null; type: string; area_sf: number; people: number;
        total_btuh: number; tons: number }[];
      skipped_no_area: number; total_area_sf: number; total_btuh: number; tons: number;
      sf_per_ton: number | null; block_tons: number; delta_vs_block_pct: number | null;
      disclaimer?: string;
    }>(`/projects/${pid}/mep/thermal-loads`);
  }
  };
}
