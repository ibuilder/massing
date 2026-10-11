/** AUTHORITY-DOWNSTREAM — the gate that exists to block, reaching the cards it was written for.
 *
 *  `services/api/src/aec_api/deal_authority.py` is explicit about its purpose: *"Required fact types
 *  that are missing, stale, or superseded-but-still-active BLOCK downstream analysis — the point is
 *  to stop the work, not to annotate it after the fact."* Every CRE card on this tab computed
 *  regardless. If the authority table said the rent roll was 87 days past its freshness limit, the
 *  net-effective-rent card valued it and said nothing.
 *
 *  **WHAT "BLOCK" MEANS HERE, decided rather than split.** Refusing to compute makes the tab
 *  unusable during exactly the phase when facts are legitimately stale; annotating and carrying on
 *  makes the gate decorative. Neither is what the engine asks for. The card computes, renders every
 *  input and intermediate figure, and **withholds only the conclusion** — the NER figure, the scrub
 *  verdict, the tie-out result, the covenant verdict — replacing it with which fact is blocking and
 *  why. That is the pattern four cards on this branch already use for a different reason
 *  (`supplyCard.isVacuous`, `rentRollQuality`'s coverage headline, `decisionGateCard.coverageOf`,
 *  `scanVerifyView.refused`): *show the working, withhold the verdict, say what is missing.*
 *
 *  **AN UNDECLARED TABLE IS NOT A BLOCKED ONE, and conflating them is the trap.** `assess()` lists
 *  every required fact type as `missing` when the table is empty, so a project nobody has declared
 *  anything for produces a full set of blocking entries. Withholding on that would make a fresh
 *  project look like a governed one that failed — *the same empty-versus-zero confusion this whole
 *  group of cards exists to refuse, one level up, applied to the gate itself.* A table with no
 *  entries has no opinion: the verdict shows, with one line saying it is ungoverned.
 *
 *  **The dependency map is the part that can drift, so it is pinned.** `authorityGate.test.ts`
 *  asserts every fact type named below exists in `FACT_TYPES`, which is itself pinned against the
 *  Python by `authorityCard.test.ts`. Without that, renaming a fact type on the engine would
 *  silently stop blocking the card that depends on it, and the card would look wired.
 */
import { FACT_TYPES } from "./authorityCard";

/** Which deal-room facts each card's CONCLUSION rests on.
 *
 *  Derived from what each card actually reads, not from the tab it sits on:
 *
 *  * `net_effective_rent` and `rent_roll_scrub` call routes that read the PROJECT's rent roll, so
 *    the gate's verdict on `rent_roll` applies to them directly.
 *  * `t12` and `covenants` are handed a document by the person. The gate governs *which document is
 *    the one to underwrite from*, so the statement here is about the FACT rather than about the
 *    paste: a normalised NOI or a covenant verdict is not underwritable while the authority for the
 *    operating statement is blocked, whichever file the figures came from.
 *
 *  **`residual_land` is deliberately absent, and the roadmap entry that listed it was wrong.**
 *  `POST /proforma/residual-land` takes `Assumptions` and nothing else — no project id, no rent
 *  roll, no operating statement — so it consumes no governed fact. Wiring the gate into it would be
 *  inventing a dependency, which is worse than the omission: a block nobody can act on teaches the
 *  reader to dismiss the ones they can. */
export const FACT_DEPENDENCIES: Record<string, readonly string[]> = {
  net_effective_rent: ["rent_roll"],
  rent_roll_scrub: ["rent_roll"],
  t12: ["operating_statement"],
  covenants: ["operating_statement", "loan"],
};

export interface AuthorityBlock { fact_type: string; why: string }

/** What the gate has to say about one card. Four states, because three of them are not "fine":
 *  `clear` is governed and passing, `undeclared` is ungoverned, `unknown` is a gate that could not
 *  be read, and only `blocked` withholds. */
export type GateState =
  | { kind: "clear" }
  | { kind: "undeclared" }
  | { kind: "unknown"; why: string }
  | { kind: "blocked"; blocks: AuthorityBlock[] };

interface AuthorityLike {
  entries?: unknown;
  gate?: { blocking?: unknown } | null;
}

/** The gate's state for one consumer, from the deal-authority READ.
 *
 *  Pass `null` for a read that failed and the state is `unknown`, not `clear` — a gate that could
 *  not be consulted has not approved anything. It does not withhold either, because an API outage
 *  is not a diligence finding; it says so on the card instead. */
export function gateFor(read: AuthorityLike | null | undefined,
                        consumer: string | readonly string[]): GateState {
  if (!read) return { kind: "unknown", why: "the authority table could not be read" };
  const facts = typeof consumer === "string" ? (FACT_DEPENDENCIES[consumer] ?? []) : consumer;
  if (!Array.isArray(read.entries)) {
    return { kind: "unknown", why: "this server did not return the stored authority table" };
  }
  if (read.entries.length === 0) return { kind: "undeclared" };
  const blocking = read.gate?.blocking;
  if (!Array.isArray(blocking)) {
    return { kind: "unknown", why: "the authority table carried no gate" };
  }
  const blocks = (blocking as AuthorityBlock[])
    .filter((b) => b && typeof b.fact_type === "string" && facts.includes(b.fact_type));
  return blocks.length ? { kind: "blocked", blocks } : { kind: "clear" };
}

/** True when the card must NOT print its conclusion. Only `blocked` does. */
export function withholds(state: GateState): boolean {
  return state.kind === "blocked";
}

function label(factType: string): string {
  return FACT_TYPES.find(([k]) => k === factType)?.[1] ?? factType;
}

/** The line that replaces a withheld verdict, or sits under a shown one. `null` on `clear`,
 *  because a governed, passing fact needs no sentence — a card that narrates its own compliance
 *  trains the reader to skip the one that does not. */
export function gateNote(state: GateState): { text: string; tone: string } | null {
  if (state.kind === "clear") return null;
  if (state.kind === "undeclared") {
    return {
      text: "No deal-room authority table is declared for this project, so these figures are not "
        + "governed by a source of record. Declare one on the Deal-room authority card.",
      tone: "",
    };
  }
  if (state.kind === "unknown") {
    return { text: `${state.why}, so these figures are ungoverned.`, tone: "" };
  }
  const which = state.blocks
    .map((b) => `${label(b.fact_type)} — ${b.why}`)
    .join("; ");
  return {
    text: `Withheld: the deal-room authority gate blocks this fact. ${which}. Everything above is `
      + "computed and shown; the conclusion is not stated, because it would be an opinion drawn "
      + "from a document the authority table says not to underwrite from.",
    tone: "var(--status-crit)",
  };
}

/** Every fact type the map depends on, for the pin in `authorityGate.test.ts`. */
export function declaredFacts(): string[] {
  return [...new Set(Object.values(FACT_DEPENDENCIES).flat())].sort();
}
