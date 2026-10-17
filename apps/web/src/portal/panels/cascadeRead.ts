/** CASCADE-DARK — a card named "Requirement flow-down" that shows no flow, over a percentage that
 *  could never reach 100%.
 *
 *  ## The tree was unreachable
 *
 *  `cde.cascade` builds the whole ISO 19650 flow-down — OIR → PIR/AIR → EIR → MIDP/TIDP, every
 *  requirement as a tiered node and every parent→child edge — and `nodes` and `children` were both
 *  undeclared on the client type, so no TypeScript could reach either. The card rendered:
 *
 *  > `Requirement flow-down · 5/7 linked · 71% · ⏳ 2 not traced up: EIR IR-003, AIR IR-006`
 *
 *  A count and a list of failures. **The question the standard asks is "does this exchange
 *  requirement trace to organizational intent, and through what?"** and the "through what" — the
 *  only part that tells anybody where to look — was computed on every call and discarded. `roots`
 *  was declared and unread too, so *"✅ every requirement traces up to organizational intent"*
 *  printed without ever naming the intent.
 *
 *  ## A root is not a coverage failure
 *
 *  `coverage_pct` was `linked / total`, and the engine's own comment calls OIRs *"legitimately
 *  unlinked"* two lines before putting them in that denominator. Measured against a live route:
 *
 *  | register | as shipped | now |
 *  |---|---|---|
 *  | 1 OIR, nothing else | **0.0%**, with zero orphans | `null` — nothing is expected to trace up |
 *  | a textbook 1 OIR → 1 PIR → 1 EIR | **66.7%** | 100.0% |
 *
 *  So the number had a permanent ceiling below 100 on every well-formed cascade, and the one-OIR
 *  case printed **`0/1 linked · 0%` beside `✅ every requirement traces up to organizational
 *  intent`, in the same box.** `expected` is the population that must link and the percentage is
 *  over it; `null` is the honest answer where the population is empty, because `0` reads as a
 *  failure.
 *
 *  ## And "never linked" is not "linked to something that is gone"
 *
 *  `derives_from` is a reference field and the parent can be deleted under it. Both arrived in one
 *  undifferentiated `orphans` list, so a requirement somebody HAD linked — whose link was then
 *  silently undone — rendered character-for-character like one nobody has touched. Measured: a
 *  deleted intermediate PIR put its child in `orphans` beside a never-linked AIR, four identical
 *  keys each. Two repairs: make a first link, or re-point a broken reference. *The fact that
 *  separates them was already in the response* — `nodes` carries the stored `derives_from` — in one
 *  of the two keys nobody had declared.
 */
import type { CascadeBrief, CascadeDangling, CascadeNode, InfoRequirementsCascade } from "../../api/types";

export type { Tone } from "./statedBasis";
import type { Tone } from "./statedBasis";

/** The coverage headline, over the population that is actually expected to trace up.
 *
 *  Four states, and the first two are the ones that did not exist: a register with nothing BELOW
 *  the top tier has no coverage question, and that is different from failing one. */
export function cascadeHeadline(c: InfoRequirementsCascade): { text: string; tone: Tone } {
  if (c.total === 0) return { tone: "", text: "No information requirements registered yet." };
  if (c.expected === 0) {
    return {
      tone: "",
      text: `${c.total} requirement(s), all at the top of the cascade — nothing is expected to trace `
        + "up yet. Add a PIR, AIR or EIR beneath one and the flow-down becomes measurable.",
    };
  }
  const pct = c.coverage_pct == null ? "" : ` (${c.coverage_pct}%)`;
  const missing = c.expected - c.linked;
  const roots = c.roots.length
    ? ` ${c.roots.length} root requirement(s) sit above the cascade and are outside it.`
    : "";
  return {
    tone: missing ? (c.dangling_count ? "crit" : "warn") : "good",
    text: `${c.linked}/${c.expected} of the requirements that should trace up do${pct}.${roots}`,
  };
}

/** The two ways an expected link is missing, counted separately because the repairs differ.
 *
 *  A dangling reference is listed first and worded as the sharper finding: somebody did the work
 *  and it was undone, which no amount of looking at the register reveals. */
export function missingLinkNotes(c: InfoRequirementsCascade): { text: string; tone: Tone }[] {
  const out: { text: string; tone: Tone }[] = [];
  if (c.dangling_count) {
    const refs = c.dangling.slice(0, 6).map((d) => `${d.type} ${d.ref ?? d.id}`).join(", ");
    out.push({
      tone: "crit",
      text: `${c.dangling_count} requirement(s) point at a parent that no longer exists — these were `
        + `linked and the link was undone, so they need re-pointing rather than a first link: ${refs}`
        + `${c.dangling.length < c.dangling_count ? " …" : ""}`,
    });
  }
  if (c.orphan_count) {
    const refs = c.orphans.slice(0, 6).map((o) => `${o.type} ${o.ref ?? o.id}`).join(", ");
    out.push({
      tone: "warn",
      text: `${c.orphan_count} requirement(s) have never been linked to a higher-level one: ${refs}`
        + `${c.orphans.length < c.orphan_count ? " …" : ""}`,
    });
  }
  if (c.misdirected.length) {
    out.push({
      tone: "warn",
      text: `${c.misdirected.length} link(s) point the wrong way, at an equal or lower tier: `
        + c.misdirected.slice(0, 6).map((m) => `${m.type}→${m.parent_type}`).join(", "),
    });
  }
  return out;
}

/** The organizational intent the whole cascade is supposed to trace to, named rather than asserted.
 *  Empty is a finding of its own: a register with requirements and no OIR has nothing at the top. */
export function rootNote(c: InfoRequirementsCascade): { text: string; tone: Tone } | null {
  if (!c.total) return null;
  if (!c.roots.length) {
    return {
      tone: "warn",
      text: "No top-level requirement (OIR) is registered, so nothing in this cascade traces to "
        + "organizational intent — every link below is relative to a missing top.",
    };
  }
  return {
    tone: "",
    text: `Organizational intent: ${c.roots.map((r) => `${r.ref ?? r.type} ${r.title ?? ""}`.trim())
      .join(" · ")}`,
  };
}

/** The engine's statement of what the percentage is over. Verbatim. */
export function coverageBasis(c: InfoRequirementsCascade): string {
  return c.coverage_basis;
}

export interface FlowRow {
  /** Indent depth in the tree, 0 for a root. */
  depth: number;
  ref: string;
  type: string;
  title: string;
  state: string;
  /** What this requirement derives from, by ref — the "through what" the card never showed. */
  parent: string;
  status: "linked" | "root" | "orphan" | "dangling" | "misdirected";
}

const STATUS_TONE: Record<FlowRow["status"], Tone> = {
  linked: "", root: "", orphan: "warn", dangling: "crit", misdirected: "warn",
};

export function rowTone(r: FlowRow): Tone {
  return STATUS_TONE[r.status];
}

/** The flow-down as indented rows, depth-first from each root, then everything the tree could not
 *  reach.
 *
 *  **Cycle-safe, and that is not hypothetical**: `derives_from` is a free reference with no
 *  acyclicity check anywhere, so two requirements naming each other would recurse for ever here.
 *  A node is emitted once; anything a walk reaches twice is left to the unreachable pass below,
 *  where its status still describes it. */
export function flowRows(c: InfoRequirementsCascade): FlowRow[] {
  const byId = new Map(c.nodes.map((n) => [n.id, n]));
  const misdirectedIds = new Set(c.misdirected.map((m) => m.id));
  const danglingIds = new Set(c.dangling.map((d) => d.id));
  const orphanIds = new Set(c.orphans.map((o) => o.id));
  const rootIds = new Set(c.roots.map((r) => r.id));
  const seen = new Set<string>();

  const status = (n: CascadeNode): FlowRow["status"] =>
    danglingIds.has(n.id) ? "dangling"
      : orphanIds.has(n.id) ? "orphan"
        : misdirectedIds.has(n.id) ? "misdirected"
          : rootIds.has(n.id) ? "root" : "linked";

  const row = (n: CascadeNode, depth: number): FlowRow => {
    const p = n.derives_from ? byId.get(n.derives_from) : undefined;
    return {
      depth,
      ref: n.ref ?? n.id.slice(0, 8),
      type: n.type,
      title: n.title ?? "(untitled)",
      state: n.state ?? "—",
      parent: p ? (p.ref ?? p.type) : n.derives_from ? "(deleted)" : "—",
      status: status(n),
    };
  };

  const out: FlowRow[] = [];
  const walk = (id: string, depth: number) => {
    const n = byId.get(id);
    if (!n || seen.has(id)) return;
    seen.add(id);
    out.push(row(n, depth));
    for (const kid of c.children[id] ?? []) walk(kid, depth + 1);
  };
  for (const r of c.roots) walk(r.id, 0);
  // Everything no root reaches: a sub-tree hanging off an orphan, a dangling reference, or a node a
  // cycle made unreachable. Rendered at depth 0 rather than dropped — a row missing from a tree is
  // indistinguishable from a row that does not exist.
  for (const n of c.nodes) {
    if (!seen.has(n.id)) walk(n.id, 0);
  }
  return out;
}

/** `showing N of M` when the node list is capped. The counts above are over the FULL population, so
 *  this is the only place the cap is visible (TRUNC-COUNTED). */
export function nodePageNote(c: InfoRequirementsCascade): string | null {
  if (!c.nodes_truncated) return null;
  return `Showing ${c.nodes.length.toLocaleString()} of ${c.total.toLocaleString()} requirement(s) — `
    + `the server caps the tree at ${c.max_nodes.toLocaleString()}. Every count above is over all `
    + `${c.total.toLocaleString()}.`;
}

/** The brief lists as table rows, for the two findings that have their own sections. */
export function danglingRows(c: InfoRequirementsCascade): CascadeDangling[] {
  return c.dangling;
}

export function orphanRows(c: InfoRequirementsCascade): CascadeBrief[] {
  return c.orphans;
}
