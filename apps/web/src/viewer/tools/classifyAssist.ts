import type { ClassifyCoverage, ClassifyPlan, ClassifyProposals, ProposalRow }
  from "../../api/classificationRef";

/**
 * CLASSIFY-DARK, the screen half — the `/classify/*` capability had no door in the app.
 *
 * **Why the engine is careful and why a consumer can still get it wrong.**
 * `classify_assist.propose()` returns three counts that only mean something together: `declared`
 * (the model asserts a code), `proposable` (`keyword` + `class_map`, derived from evidence) and
 * `unmapped` (no code at all). `classified_pct` counts the first ONLY. Render the percentage alone
 * and the remainder reads as one undifferentiated backlog — but accepting every proposal on offer
 * still leaves `unmapped` untouched, and those are the elements an estimate prices in the default
 * bucket while reporting a complete takeoff. *The verdict is about a subset and the subset is in a
 * different field*, which is the eighteenth gate's shape (`test_verdict_coverage.py`).
 *
 * Three further distinctions this file is built to keep:
 *
 *  * `rows` is a PAGE and `matching` is the total. Printing `rows.length` as the total is
 *    TRUNC-COUNTED exactly; and when a `basis` filter is applied, `matching` counts what matched the
 *    FILTER, not what is in the model, so the wording has to change with it (the ELEMENTS-SILENT
 *    lesson: a bound reported in the wrong units is worse than no bound).
 *  * `keyword` and `class_map` are both "proposable" and are not equally trustworthy. A keyword hit
 *    is a claim about THIS element; a class-map hit is true of the CLASS, so it is identical for
 *    every element of that class — including the ones it is wrong for. Merging them into one number
 *    hides that the second kind is reviewed as a group.
 *  * `apply_plan` returns `count` AND `skipped`. `count` is a verdict about a subset of what the
 *    user ticked, and the engine's own docstring says why: *a plan that silently covers 40 of the 60
 *    elements somebody ticked is worse than one that refuses, because the other 20 look done.*
 *
 * Nothing here applies anything. The plan comes back as ordinary GUID-stable `set_classification`
 * recipe steps and the caller applies them through the authoring path, so a classification always
 * has an author — a code that appeared because somebody opened a report is indistinguishable a week
 * later from one a quantity surveyor decided.
 */

export interface CoverageReading {
  kind: "empty" | "floor" | "unmapped" | "proposable" | "full";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/** The pct, the split, and — first — whether the engine had the evidence to compute it at all. */
export function coverageReading(c: ClassifyCoverage): CoverageReading {
  const sys = c.system_name || c.system;
  const pct = c.classified_pct == null ? "—" : `${c.classified_pct.toFixed(1)}%`;
  // The split is stated in EVERY branch. `declared + proposable + unmapped === total` by
  // construction, so a reader who is given only the percentage cannot recover it.
  const split = `${c.declared} declared · ${c.proposable} proposable · ${c.unmapped} unmapped`;

  if (!c.total) {
    return { kind: "empty", tone: "",
             headline: "No elements to classify",
             detail: `This model carries no physical elements for ${sys} to be about. Openings are `
                   + "excluded on purpose, so that this denominator is the same one the takeoff "
                   + "prices." };
  }
  // RANKS FIRST among the non-empty readings. `declared_supplied: false` means the engine was fed
  // the property index, which carries no classification associations at all — so a 0% figure then
  // means "nobody looked", not "nothing is classified", and the two are opposite instructions.
  if (!c.declared_supplied) {
    return { kind: "floor", tone: "",
             headline: `${pct} is a FLOOR, not a reading — the declared codes were not supplied`,
             detail: `The classification associations were not read for this run, so every element `
                   + `counts as undeclared. ${split} of ${c.total}. Re-run against the source file `
                   + "before treating this number as the state of the model." };
  }
  if (c.unmapped) {
    return { kind: "unmapped", tone: "bad",
             headline: `${pct} of ${c.total} element(s) carry a ${c.system} code — and ${c.unmapped} `
                     + "cannot be proposed one at all",
             detail: (c.unmapped_warning ? `${c.unmapped_warning}. ` : "")
                   + `Those ${c.unmapped} would price as ${c.default_bucket.code} `
                   + `"${c.default_bucket.title}" — the default bucket, which is not a `
                   + `classification of them. Accepting every proposal on offer still leaves them: `
                   + `${split}.` };
  }
  if (c.declared >= c.total) {
    return { kind: "full", tone: "ok",
             headline: `Fully classified in the model — all ${c.total} element(s) carry a ${c.system} code`,
             detail: `${c.counts_only_declared}. Nothing here is a guess.` };
  }
  return { kind: "proposable", tone: "warn",
           headline: `${pct} of ${c.total} element(s) carry a ${c.system} code — ${c.proposable} can be proposed one`,
           detail: `${c.counts_only_declared}. Every proposable element has evidence attached; `
                 + `review and accept them to raise the figure. ${split}.` };
}

/** The four bases kept as four rows. `keyword` and `class_map` are NOT summed. */
export function coverageRows(c: ClassifyCoverage): { k: string; v: string; strong?: boolean }[] {
  const b = c.by_basis || {};
  const n = (k: string) => String(b[k] ?? 0);
  return [
    { k: "Elements", v: String(c.total), strong: true },
    { k: "Declared in the model", v: n("declared") },
    { k: "Proposable — the element's own name", v: n("keyword") },
    { k: "Proposable — its IFC class", v: n("class_map") },
    { k: "No code available", v: n("unmapped") },
    { k: "Default bucket (what unmapped prices as)",
      v: `${c.default_bucket.code} ${c.default_bucket.title}` },
    { k: "System", v: `${c.system_name} (${c.system})` },
  ];
}

export interface ProposalReading {
  kind: "none" | "page" | "all";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * What the row list is a list OF.
 *
 * **`basis` is REQUIRED, and that is a correctness fix rather than an API preference.** `propose()`
 * sorts its rows `declared` first (most authoritative first, which is right for a report), and the
 * route pages the sorted list — so an UNFILTERED request on a model with more elements than the
 * page size returns the declared rows and truncates away *exactly* the ones a reviewer can act on.
 * A 5,000-element model with 2,000 declared would have reported "Showing 2000 of 5000" above an
 * empty tick list. *A cap applied after a sort is a cap on whichever end the sort put last* — the
 * `order_by(asc).limit()` defect, arriving through a sort nobody chose for that reason. Filtering
 * makes `matching` the reviewable count itself, so the page can only ever cut reviewable rows at
 * the far end of a set that is entirely reviewable, and the cap is then reported in its own units.
 */
export function proposalReading(p: ClassifyProposals, basis: ProposalRow["basis"]):
    ProposalReading {
  const of = `with basis \`${basis}\``;
  if (!p.matching) {
    return { kind: "none", tone: "",
             headline: `No element ${of}`,
             detail: `Nothing matched that basis. The model's split is ${p.declared} declared · `
                   + `${p.proposable} proposable · ${p.unmapped} unmapped.` };
  }
  if (p.truncated) {
    return { kind: "page", tone: "warn",
             headline: `Showing ${p.returned} of ${p.matching} element(s) ${of}`,
             detail: (p.truncation_note || "Further rows matched and are not shown")
                   + ". A tick list that stops at the limit without saying so reads as the whole "
                   + "set, and the whole set is what a coverage exercise needs." };
  }
  return { kind: "all", tone: "ok",
           headline: `All ${p.matching} element(s) ${of}`,
           detail: "Every matching row is shown — this list is the whole set." };
}

/** Rows worth a human's attention first: the ones with no code, then the class-wide guesses, then
 *  the element-specific ones. Declared rows are not proposals and never appear. */
export function reviewRows(p: ClassifyProposals): ProposalRow[] {
  const rank: Record<string, number> = { unmapped: 0, class_map: 1, keyword: 2 };
  return (p.rows || [])
    .filter((r) => r.basis !== "declared")
    .slice()
    .sort((a, b) => (rank[a.basis] ?? 9) - (rank[b.basis] ?? 9)
                 || (a.ifc_class || "").localeCompare(b.ifc_class || "")
                 || (a.name || "").localeCompare(b.name || ""));
}

/** The GUIDs nothing can price — the set worth isolating in 3D, because seeing them is what tells
 *  you whether they are a real gap or an export artifact. */
export function unmappedGuids(p: ClassifyProposals): string[] {
  return (p.rows || []).filter((r) => r.basis === "unmapped" && r.guid).map((r) => r.guid);
}

/** A tickable row's label and why it says what it says. */
export function rowLabel(r: ProposalRow): { label: string; code: string; detail: string } {
  return {
    label: r.name || r.guid,
    code: r.code ? `${r.code}${r.title ? ` ${r.title}` : ""}` : "— no code",
    detail: `${r.ifc_class || "(no class)"}${r.type_name ? ` · type ${r.type_name}` : ""}`
          + `${r.confidence ? ` · ${r.confidence} confidence` : ""} — ${r.evidence}`,
  };
}

export interface PlanReading {
  kind: "unaccounted" | "nothing" | "partial" | "all";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
  /** Skipped GUIDs collapsed by reason: sixty identical refusals are one line with a count. */
  refusals: { reason: string; count: number }[];
}

/**
 * `count` is a verdict about a SUBSET of what was ticked, and `skipped` is the rest.
 *
 * `accepted` is the number of GUIDs handed to the route. The server dedupes before planning, so the
 * caller must dedupe too or the accounting check below fires on a double-tick.
 */
export function planReading(plan: ClassifyPlan, accepted: number): PlanReading {
  const skipped = plan.skipped || [];
  const byReason = new Map<string, number>();
  for (const s of skipped) byReason.set(s.reason, (byReason.get(s.reason) ?? 0) + 1);
  const refusals = [...byReason.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count);
  const seen = plan.count + skipped.length;

  // RANKS FIRST. Every accepted GUID is either a step or a refusal; if the two do not add up, the
  // plan's own bookkeeping cannot be trusted and the missing ones are invisible in both columns —
  // which reads as an ordinary partial plan, the one outcome this must never be mistaken for.
  if (accepted > 0 && seen !== accepted) {
    return { kind: "unaccounted", tone: "bad", refusals,
             headline: `${accepted} element(s) accepted but only ${seen} accounted for`,
             detail: `${plan.count} step(s) prepared and ${skipped.length} refused with a reason `
                   + `leaves ${accepted - seen} unaccounted for. Do not apply this plan: the `
                   + "missing elements appear in neither column, so applying it would leave them "
                   + "looking done." };
  }
  if (!plan.count) {
    return { kind: "nothing", tone: "bad", refusals,
             headline: `Nothing can be applied — all ${skipped.length} element(s) were refused`,
             detail: "The plan is empty. Each refusal carries its reason below." };
  }
  if (skipped.length) {
    return { kind: "partial", tone: "warn", refusals,
             headline: `${plan.count} step(s) prepared — ${skipped.length} element(s) refused`,
             detail: `Applying this covers ${plan.count} of the ${accepted} you ticked. The other `
                   + `${skipped.length} are listed below with the reason, rather than being dropped: `
                   + "they would otherwise look done." };
  }
  return { kind: "all", tone: "ok", refusals,
           headline: `${plan.count} step(s) prepared — every accepted element is covered`,
           detail: `${plan.note} Nothing is applied until you say so; the steps are ordinary `
                 + "GUID-stable edit recipes, so the classification has an author." };
}

/** What the card needs from the host. The DOM is built HERE rather than in `analyseSection.ts`
 *  because that file is in the eager chunk and the card body is what the bundle budget refuses —
 *  deferring the reading and keeping the rendering is half a lazy module. */
export interface ClassifyCardDeps {
  showResult: (title: string, render: (body: HTMLElement) => void) => void;
  resultNote: (html: string, kind?: "ok" | "warn" | "bad" | "") => HTMLElement;
  kvTable: (rows: { k: string; v: string; strong?: boolean }[]) => HTMLElement;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  esc: (v: unknown) => string;
  /** Show only these GUIDs in the 3D view. */
  isolate: (guids: string[]) => void;
  proposals: (system: string, basis: ProposalRow["basis"]) => Promise<ClassifyProposals>;
  plan: (accept: string[], system: string) => Promise<ClassifyPlan>;
  apply: (steps: { recipe: string; params: Record<string, unknown> }[]) => Promise<void>;
  reload: (system: string) => void;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
}

/** Longest tick list rendered at once. The page from the route may be larger; the reading always
 *  states which bound the reader is looking at, and the two are deliberately different numbers so
 *  neither can be mistaken for the total. */
export const REVIEW_ROW_CAP = 150;

export function renderClassifyCard(c: ClassifyCoverage, d: ClassifyCardDeps): void {
  const r = coverageReading(c);
  d.showResult("Classification coverage — can a cost exercise start?", (body) => {
    body.appendChild(d.resultNote(`<b>${d.esc(r.headline)}</b><br>${d.esc(r.detail)}`, r.tone));
    body.appendChild(d.kvTable(coverageRows(c)));

    // Switching system is not cosmetic: MasterFormat, DIN 276 and NRM 1 have different class maps,
    // so the SPLIT changes with it — an element unmapped under one may be mapped under another.
    const sysWrap = document.createElement("div");
    sysWrap.style.cssText = "display:flex;gap:6px;align-items:center;margin:6px 0";
    const sysLbl = document.createElement("span");
    sysLbl.className = "meta"; sysLbl.textContent = "Classification system:";
    const sysSel = document.createElement("select");
    sysSel.className = "portal-filter"; sysSel.style.cssText = "font-size:12px";
    // PINNED AGAINST THE SERVER by `classifyAssist.test.ts`, which reads `classification.py` for
    // the keys of `CLASSIFICATIONS`. A hardcoded list of someone else's enum is a drift waiting for
    // a fourth system: it would be served, proposable, and unofferable, with nothing going red.
    for (const opt of [["masterformat", "CSI MasterFormat (US/CA)"],
                       ["din276", "DIN 276 (DACH)"],
                       ["nrm1", "RICS NRM 1 (UK)"]]) {
      const o = document.createElement("option");
      o.value = opt[0]!; o.textContent = opt[1]!; sysSel.appendChild(o);
    }
    sysSel.value = c.system;
    sysSel.onchange = () => { d.reload(sysSel.value); };
    sysWrap.append(sysLbl, sysSel); body.appendChild(sysWrap);

    const list = document.createElement("div");
    const actions = document.createElement("div");
    actions.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin:6px 0";

    const review = (basis: ProposalRow["basis"]) => {
      list.textContent = "";
      void d.proposals(c.system, basis).then((p) => {
        renderReview(p, basis, list, d);
      }).catch((e: unknown) => { d.notify((e as Error).message, "error"); });
    };

    // ONE BUTTON PER BASIS, and no "review everything" button — see `proposalReading` for why an
    // unfiltered page is the wrong request to make. It also happens to be the better screen: the
    // three kinds of claim are reviewed differently, and the class-wide one is reviewed as a GROUP
    // because every element of that class got the same code and they are right or wrong together.
    // Every count here reads `by_basis`, including `unmapped` — which is also a top-level field of
    // the same value. *Two sources for one number is where a drift hides*, and the guard below
    // reads `by_basis`, so a label fed from the other field could offer a button for zero.
    const BY_BASIS: [ProposalRow["basis"], string][] = [
      ["keyword", `🏷 ${c.by_basis?.keyword ?? 0} named by the element's own name`],
      ["class_map", `🧱 ${c.by_basis?.class_map ?? 0} class-wide guesses`],
      ["unmapped", `⚠ ${c.by_basis?.unmapped ?? 0} with no code at all`],
    ];
    for (const entry of BY_BASIS) {
      if (!c.by_basis?.[entry[0]]) continue;
      actions.appendChild(d.toolBtn2(entry[1], () => { review(entry[0]); }));
    }
    body.append(actions, list);
  });
}

function renderReview(p: ClassifyProposals, basis: ProposalRow["basis"],
                      host: HTMLElement, d: ClassifyCardDeps): void {
  const pr = proposalReading(p, basis);
  host.appendChild(d.resultNote(`<b>${d.esc(pr.headline)}</b><br>${d.esc(pr.detail)}`, pr.tone));

  const rows = reviewRows(p);
  const shown = rows.slice(0, REVIEW_ROW_CAP);
  if (shown.length < rows.length) {
    host.appendChild(d.resultNote(
      `Ticking is limited to the first ${d.esc(REVIEW_ROW_CAP)} of these `
      + `${d.esc(rows.length)} row(s). Narrow by basis, or accept in batches — this bound is the `
      + "tick list's, not the model's.", "warn"));
  }

  const gaps = unmappedGuids(p);
  if (gaps.length) {
    host.appendChild(d.toolBtn2(`👁 Isolate the ${gaps.length} with no code in 3D`,
                                () => { d.isolate(gaps); }));
  }

  const ticked = new Set<string>();
  // Declared BEFORE the loop that closes over it: a `const` referenced from a handler defined
  // earlier in the same scope is legal and runs fine, and is also exactly the shape lint flags.
  const count = document.createElement("span");
  count.className = "meta"; count.textContent = "none ticked";
  const table = document.createElement("div");
  table.style.cssText = "max-height:320px;overflow:auto;margin:6px 0";
  for (const row of shown) {
    const lab = rowLabel(row);
    const line = document.createElement("label");
    line.style.cssText = "display:flex;gap:6px;align-items:flex-start;padding:3px 0;font-size:12px";
    const box = document.createElement("input");
    box.type = "checkbox";
    // An unmapped row has no code to apply; the route would refuse it WITH a reason, which is
    // correct but wastes a round trip and reads as a refusal of the user's judgement rather than a
    // statement that there is nothing to accept.
    box.disabled = row.basis === "unmapped";
    box.onchange = () => {
      if (box.checked) ticked.add(row.guid); else ticked.delete(row.guid);
      count.textContent = ticked.size ? `${ticked.size} ticked` : "none ticked";
    };
    const text = document.createElement("span");
    text.innerHTML = `<b>${d.esc(lab.label)}</b> — ${d.esc(lab.code)}`
                   + `<br><span class="meta">${d.esc(lab.detail)}</span>`;
    line.append(box, text);
    table.appendChild(line);
  }
  host.appendChild(table);

  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0";
  const planOut = document.createElement("div");
  bar.append(count, d.toolBtn2("📋 Prepare a plan for the ticked", () => {
    const accept = [...ticked];
    if (!accept.length) { d.notify("tick at least one element first", "error"); return; }
    planOut.textContent = "";
    void d.plan(accept, p.system).then((plan) => {
      renderPlan(plan, accept.length, planOut, d);
    }).catch((e: unknown) => { d.notify((e as Error).message, "error"); });
  }));
  host.append(bar, planOut);
}

function renderPlan(plan: ClassifyPlan, accepted: number, host: HTMLElement,
                    d: ClassifyCardDeps): void {
  const pl = planReading(plan, accepted);
  host.appendChild(d.resultNote(`<b>${d.esc(pl.headline)}</b><br>${d.esc(pl.detail)}`, pl.tone));
  if (pl.refusals.length) {
    host.appendChild(d.kvTable(pl.refusals.map((f) => ({
      k: `${f.count} element(s)`, v: f.reason }))));
  }
  // `unaccounted` is the one reading that withholds the apply button: the plan's own arithmetic
  // disagrees with itself, so applying it would leave elements looking done in both columns.
  if (plan.count && pl.kind !== "unaccounted") {
    host.appendChild(d.toolBtn2(`✅ Apply ${plan.count} classification(s)`, () => {
      void d.apply(plan.steps)
        .then(() => { d.notify(`applied ${plan.count} classification(s)`, "success"); })
        .catch((e: unknown) => { d.notify((e as Error).message, "error"); });
    }));
  }
}
