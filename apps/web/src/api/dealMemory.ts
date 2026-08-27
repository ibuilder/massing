/** R35-DEAL-MEMORY: this firm's own realised $/SF, beside the hard cost being underwritten.
 *
 *  A new file rather than methods in `client.ts`, per the extraction rule in `test_file_sizes.py`:
 *  a *field* folds onto an existing line, a *feature* moves to a domain module. **Deliberately NOT
 *  labelled SCALE-SEAM ㉘** — a seam slice EXTRACTS an existing group and shrinks `client.ts`, and
 *  this adds a feature that was never in it. The ratchet said so before I did: the one import line
 *  took the file 2,837 → 2,838 and failed, which is a slice claim failing its own definition.
 *
 *  **`deal_memory.beside()` — the function whose own docstring says it is "the shape the underwriting
 *  screen wants" — had no caller anywhere**, server or client, while `deal_memory.comps` had been
 *  routed since the engine shipped. So `test_reachable` passed: the MODULE is imported, by the
 *  portfolio route. *A module can be reachable and its whole reason for existing still be
 *  unreachable* — `read_p6xml_all` was the same shape one ring over.
 *
 *  **Both methods are here, and the second one is here because two gates argued about it.**
 *  `portfolioDealMemory` was written, then removed when `clientCallers.test.ts` failed on it — no
 *  screen, so a typed method for it would exist only to satisfy a gate. Then
 *  `test_route_reachability` failed the other way: adding `/projects/{pid}/deal-memory/beside` put
 *  the substring `deal-memory` into the web source, so its frozen entry for `/portfolio/deal-memory`
 *  read as "quietly became called" when nothing had called it.
 *
 *  Neither gate was wrong and neither could be satisfied by wording. What settled it was re-reading
 *  the roadmap item, which asks for realised outcomes *"(exit cap achieved vs assumed, actual
 *  lease-up months, **cost/SF by vintage**)"* — and `comps` returns `vintage` per project. The comp
 *  list was part of the item all along; wiring only the summary comparison was the half-build, and
 *  the gate collision is what made that visible.
 *
 *  A mixin, so every call site resolves unchanged. `api/surface.test.ts` is what proves it.
 */
import { HttpCore } from "./httpCore";

type Ctor<T> = new (...args: any[]) => T;

/** `beside()`'s answer: where an entered number sits against the firm's own history. */
export interface DealMemoryBeside {
  metric: string;
  /** `no_gfa` is the route's own, and is NOT a `beside()` status — see the method's comment. */
  status: "ok" | "insufficient_history" | "no_recorded_source" | "unknown_metric" | "not_a_number"
    | "no_gfa";
  entered: number | null;
  median?: number; p25?: number; p75?: number; count?: number;
  position?: "below_p25" | "within_iqr" | "above_p75";
  comparison?: null;
  note?: string;
  gfa_sf?: number;
  hard_cost?: number;
}

/** One metric's realised distribution across the caller's own closed projects. */
export interface DealMemoryMetric {
  status: "ok" | "insufficient_history" | "no_recorded_source";
  count?: number;
  median?: number; p25?: number; p75?: number; min?: number; max?: number;
  note?: string;
}

/** One closed project as it contributes to the comp set. */
export interface DealMemoryProject {
  id: string; name: string; vintage: number | null;
  budget: number | null; actual: number | null; gfa_sf: number | null;
  cost_variance_pct: number | null; cost_per_sf: number | null;
  schedule_variance_days: number | null;
}

export function withDealMemory<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class DealMemory extends Base {
  /** The closed projects behind the comparison — the "by vintage" half of the roadmap item.
   *
   *  `exit_cap_achieved` and `lease_up_months` come back as `no_recorded_source` and are never
   *  computed: nothing records a realised exit cap or a lease-up actual, and reading either off the
   *  latest scenario would compare an assumption to itself and report perfect underwriting accuracy
   *  forever. Render the refusal — it is the honest half of the payload.
   *
   *  `excluded` is not noise either: a project with no actual spend is excluded rather than counted
   *  as zero variance, and showing the count is what stops a small comp set looking like a complete
   *  one. */
  portfolioDealMemory() {
    return this.json<{
      project_count: number;
      metrics: Record<string, DealMemoryMetric>;
      projects: DealMemoryProject[];
      excluded: { id: string; name: string; reason: string; note: string }[];
      excluded_count: number; min_samples: number; note: string;
    }>("/portfolio/deal-memory");
  }

  /** This firm's own realised $/SF, beside the hard cost being underwritten.
   *
   *  `hard_cost` is dollars, not $/SF: the server divides by the project's GFA because
   *  `energy.project_gfa_sf` is the one definition of GFA and deriving it here would make a second.
   *  A project whose properties index is not loaded answers `no_gfa` — a real and common outcome,
   *  and deliberately distinct from `insufficient_history`: one means "we cannot express your number
   *  in this metric's units", the other means "we have no history to compare it against", and they
   *  send a reader looking in different places. */
  dealMemoryBeside(pid: string, hardCost: number) {
    return this.json<DealMemoryBeside>(
      `/projects/${pid}/deal-memory/beside?hard_cost=${encodeURIComponent(String(hardCost))}`);
  }
  };
}
