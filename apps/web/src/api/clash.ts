/** Clash coordination: hard clash, federated, metrics, the sourced clearance table, the matrix.
 *
 *  SCALE-SEAM — `/projects/{pid}/clash`. Taken out of `client.ts` because that file is at its
 *  extraction pin: adding `clashClearanceRules` / `clashMatrix` there would have raised it.
 *  Existing `runClash` / `clashFederated` / `clashMetrics` travel with the group.
 */
import { HttpCore } from "./httpCore";
import type { Vec3 } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export interface ClashResult {
  count: number;
  created_topics: number;
  truncated: boolean;
  clashes: { a_guid: string; a_class: string; b_guid: string; b_class: string; volume: number;
    method: "mesh" | "aabb"; point: Vec3 }[];
}

export type ClearanceRule = {
  ifc_class: string; distance_m: number; label: string; basis: string; why: string;
};

export type ClashMatrix = {
  disciplines: string[]; pair_count: number; coverage_pct: number; coordinated: boolean;
  note: string;
  counts: { clashes: number; clean: number; untested: number };
  cells: { a: string; b: string; state: "clashes" | "clean" | "untested"; count: number }[];
};

export function withClash<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Clash extends Base {
  runClash(pid: string, opts: { a?: string; b?: string; min_volume?: number; create_topics?: boolean } = {}) {
    const q = new URLSearchParams({ create_topics: "true", ...(opts as Record<string, string>) }).toString();
    return this.json<ClashResult>(`/projects/${pid}/clash?${q}`, { method: "POST" });
  }
  /** Federated (cross-discipline) clash across the project's layered models — primary source IFC +
   *  any appended discipline models. 409 if fewer than 2 are available. */
  clashFederated(pid: string, opts: { create_topics?: boolean; coordinate?: boolean; min_volume?: number; limit?: number } = {}) {
    const q = new URLSearchParams({ create_topics: String(opts.create_topics ?? true),
      ...(opts.coordinate != null ? { coordinate: String(opts.coordinate) } : {}),
      ...(opts.min_volume != null ? { min_volume: String(opts.min_volume) } : {}),
      ...(opts.limit != null ? { limit: String(opts.limit) } : {}) }).toString();
    return this.json<{ disciplines: string[]; count: number; created_topics: number; truncated: boolean;
      coordination: { run: string; new: number; active: number; resolved: number; reappeared: number;
        clash_count: number; group_count: number; reduction: number;
        by_discipline: Record<string, number>; by_severity: Record<string, number>; note: string } | null;
      clashes: { a_model: string; a_class: string; a_guid: string; b_model: string; b_class: string;
        b_guid: string; volume: number; method: "mesh" | "aabb"; point: Vec3 }[] }>(
      `/projects/${pid}/clash/federated?${q}`, { method: "POST" });
  }
  /** Clash coordination KPIs — status mix, worst discipline pairs, severity, aging, run burn-down. */
  clashMetrics(pid: string) {
    return this.json<{ total_issues: number; open: number; closed: number; resolution_rate: number;
      by_status: Record<string, number>; by_discipline: Record<string, number>;
      by_severity: Record<string, number>; aging: Record<string, number>; runs: number;
      reappearance_rate: number;
      burn_down: { run: string; new: number; resolved: number; reappeared: number; issues: number }[];
      note: string }>(`/projects/${pid}/clash/metrics`);
  }
  /** Sourced soft-clash clearance table — each distance carries its code or manufacturer basis. */
  clashClearanceRules(pid: string) {
    return this.json<{ rules: Record<string, ClearanceRule>; classes: string[]; note: string }>(
      `/projects/${pid}/clash/clearance-rules`);
  }
  /** Discipline-pair matrix: every pair is clashes, clean, or untested — never silently clean. */
  clashMatrix(pid: string, body: {
    disciplines?: string[];
    tested_pairs?: [string, string][];
    findings?: { discipline_a: string; discipline_b: string }[];
  } = {}) {
    return this.json<ClashMatrix>(
      `/projects/${pid}/clash/matrix`, { method: "POST", body: JSON.stringify(body) });
  }
  };
}
