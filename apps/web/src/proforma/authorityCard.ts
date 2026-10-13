/** The deal-room authority table — which document is *the* document for each fact, and whether the
 *  analysis downstream of it should run at all.
 *
 *  `services/api/src/aec_api/deal_authority.py` opens with the case for itself:
 *
 *  > A data room accumulates three offering memoranda, two rent rolls and a tax bill from the year
 *  > before the reassessment. Every one of them is a real file; only one of each is *authoritative*.
 *  > Analysis that reads whichever copy it happened to open is how a superseded number reaches a
 *  > committee.
 *
 *  THE FINDING IS SHARPER THAN "NOBODY CALLED IT", and the first draft of this comment got it wrong.
 *  `dealAuthority()` — the READ — has had a caller all along: `portal/panels/design.ts` renders the
 *  gate on its go/no-go card, and renders it well (missing, stale with `days_over`, and the
 *  `superseded_still_active` case *"nobody looks for, because the document exists and reads fine"*).
 *  What was callerless is `saveDealAuthority()` — the WRITE. **So the table could be seen and never
 *  declared**: the design panel could tell you "Source facts NOT current" and there was no screen
 *  anywhere in the product that could make them current. A gate you can read and cannot satisfy is a
 *  worse thing to ship than one nobody can see, because it is visibly unfinished and looks like a
 *  bug in the analysis rather than a missing surface. This card is the surface.
 *
 *  WHAT I CHECKED AND DID NOT FIND, recorded because a clean negative is worth as much as a finding
 *  ----------------------------------------------------------------------------------------------
 *  Four engines this session carried a verdict that went vacuous once nothing had been evaluated, so
 *  the first thing measured here was the empty table. It **fails closed**: `gate.passes` is
 *  `not blocking`, and with no entries the three required fact types — rent roll, operating
 *  statement, tax — are each missing, so the gate blocks. One fresh rent roll still blocks on the
 *  other two. `services/api/test_verdict_coverage.py` leaves it alone correctly, too: `not blocking`
 *  is not a verdict quantified over a subset, and the `bool(A)` guard that makes those dangerous is
 *  absent because there is no subset. *The engine is sound in the direction that matters, and saying
 *  so is part of the report.*
 *
 *  WHY THE FACT TYPES ARE MIRRORED HERE, AND WHAT STOPS THE MIRROR DRIFTING
 *  The GET returns declared rows plus the REQUIRED ones that are missing — so an optional fact type
 *  nobody has declared yet (a title commitment, a survey) appears in neither, and a card built only
 *  from the response could never offer to add one. The table is therefore mirrored, the way
 *  `ui/reportMoments.ts` mirrors `reports.py`, and `authorityCard.test.ts` reads
 *  `deal_authority.py` off disk and asserts every key, label, default freshness and required flag
 *  agrees. **The required flag is the load-bearing one**: if it drifts, this card shows a fact type
 *  as optional while the gate blocks on it, which is worse than not showing it at all.
 */
import type { ApiClient } from "../api/client";
import type { AuthorityAssessment, AuthorityEntryWire } from "../api/creDeal";
import { escapeHtml as esc } from "../ui/feedback";

type Authority = Awaited<ReturnType<ApiClient["dealAuthority"]>>;

/** `fact_type -> [label, default freshness days, required for underwriting]`, mirroring
 *  `deal_authority.FACT_TYPES`. Order is that file's order, which is the order of a diligence list
 *  rather than the alphabet. Pinned against the Python by `authorityCard.test.ts`. */
export const FACT_TYPES: readonly [string, string, number, boolean][] = [
  ["offering", "Offering package", 180, false],
  ["rent_roll", "Rent roll", 45, true],
  ["operating_statement", "Operating statement (T-12)", 60, true],
  ["tax", "Property tax bill", 365, true],
  ["insurance", "Insurance loss run / policy", 365, false],
  ["title", "Title commitment", 180, false],
  ["survey", "Survey", 730, false],
  ["environmental", "Environmental report", 730, false],
  ["appraisal", "Appraisal", 365, false],
  ["loan", "Loan documents", 3650, false],
];

const meta = (html: string, colour?: string) =>
  `<div class="meta" style="margin-top:4px${colour ? `;color:${colour}` : ""}">${html}</div>`;

/** `2026-09-17` → `17 Sep 2026`, from a fixed table rather than `toLocaleDateString`, whose `en-GB`
 *  short month is "Sept" on this Node's ICU and "Sep" on another — see `proforma/covenantCard.ts`. */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function day(iso?: string | null): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  const month = m ? MONTHS[Number(m[2]) - 1] : undefined;
  return m && month ? `${Number(m[3])} ${month} ${m[1]}` : iso;
}

/** Render one assessment. */
// Takes the ASSESSMENT, not the whole read. Both routes produce one — the GET inline and the PUT
// under `assessment` — and widening this to the GET's type made the post-save repaint stop
// typechecking, which is the signal that the entries are an editor concern and not a render one.
export function renderAuthority(host: HTMLElement, a: AuthorityAssessment): HTMLElement {
  const el = document.createElement("div");
  el.style.marginTop = "8px";
  const gate = a.gate;
  const blocking = gate.blocking ?? [];
  const advisory = gate.advisory ?? [];

  // THE GATE LEADS. Its purpose is "to stop the work, not to annotate it after the fact", so it is
  // the first thing on the card rather than a footnote under the table.
  el.insertAdjacentHTML("beforeend",
    gate.passes
      ? `<div style="font-weight:600;color:var(--status-good)">Authority is sufficient to underwrite</div>`
        + meta(`Every required fact type has a fresh, authoritative document.`)
      : `<div style="font-weight:600;color:var(--status-crit)">`
        + `Blocked — ${blocking.length} required fact type(s)</div>`
        + `<table class="fin-table" style="margin-top:6px">`
        + `<tr class="fin-sub"><td>Fact type</td><td>why it blocks</td></tr>`
        + blocking.map((b) => `<tr><td>${esc(label(b.fact_type))}</td>`
            + `<td>${esc(b.why)}</td></tr>`).join("")
        + `</table>`
        + meta(`Required fact types that are missing, stale or superseded-but-active stop downstream `
               + `analysis rather than being annotated afterwards.`));

  // ADVISORY IS RENDERED APART. A stale offering package is not a stale tax bill; one list would
  // make the required ones look negotiable and the optional ones look alarming.
  if (advisory.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Advisory — stale, not required</td><td>why</td></tr>`
      + advisory.map((x) => `<tr><td>${esc(label(x.fact_type))}</td><td>${esc(x.why)}</td></tr>`).join("")
      + `</table>`);
  }

  // The engine's own named failure: an older file left marked active. It is the one row type a
  // reader cannot derive from the others, because nothing about it looks wrong in isolation.
  if (a.superseded_still_active?.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:6px">`
      + `<tr class="fin-sub"><td>Superseded, still active</td><td>document</td><td>issue</td></tr>`
      + a.superseded_still_active.map((s) => `<tr><td>${esc(label(s.fact_type))}</td>`
          + `<td>${esc(s.document)}</td><td>${esc(s.issue)}</td></tr>`).join("")
      + `</table>`
      + meta(`A file that has been superseded and is still marked authoritative is how a stale number `
             + `reaches a committee — the case this table exists to prevent.`, "var(--status-warn)"));
  }

  // The table shows AGE AGAINST THRESHOLD rather than a bare "stale", because a tax bill and an
  // offering package go stale on different clocks and the verdict is only checkable with both.
  if (a.table.length) {
    el.insertAdjacentHTML("beforeend",
      `<table class="fin-table" style="margin-top:8px">`
      + `<tr class="fin-sub"><td>Declared</td><td>document</td><td>as of</td>`
      + `<td class="num">age / limit</td></tr>`
      + a.table.map((r) => {
          const over = r.age_days != null && r.age_days > r.freshness_days;
          return `<tr><td>${esc(r.label)}${r.required ? ` <span class="meta">required</span>` : ""}</td>`
            + `<td>${esc(r.document)}</td><td>${day(r.as_of)}</td>`
            + `<td class="num"${over ? ' style="color:var(--status-crit)"' : ""}>`
            + `${r.age_days ?? "—"} / ${r.freshness_days}d</td></tr>`;
        }).join("")
      + `</table>`);
  }

  const undeclared = FACT_TYPES.filter(([k]) => !a.table.some((r) => r.fact_type === k));
  if (undeclared.length) {
    el.insertAdjacentHTML("beforeend", meta(
      `Not declared: ${undeclared.map(([, l, , req]) => esc(l) + (req ? " (required)" : "")).join(" · ")}.`));
  }

  el.insertAdjacentHTML("beforeend", meta(esc(a.note)));
  host.appendChild(el);
  return el;
}

function label(factType: string): string {
  return FACT_TYPES.find(([k]) => k === factType)?.[1] ?? factType;
}

/** The entries the editor opens on, and the entries it sends back.
 *
 *  **THIS FUNCTION USED TO BUILD THE SAVE BODY FROM `a.table`, AND THAT IS A DATA-LOSS DEFECT.**
 *  `table` is the AUTHORITATIVE view — archival rows (`authoritative: false`) and their supersedes
 *  chains are deliberately absent from it, because the table exists to name the one document to
 *  underwrite from. The PUT *replaces the whole stored blob*. So saving round-tripped the
 *  authoritative rows and **permanently deleted every archival entry, every supersedes chain on a
 *  row the editor rebuilt, and the `reviewer` on all of them** — and `assess()` reads
 *  `superseded_still_active` out of exactly those deleted rows, so the check that catches a
 *  resurrected superseded document stopped being able to fire. *A lossy read and a replacing write
 *  are each defensible; together they are a delete button labelled "Save".*
 *
 *  The GET now returns `entries`, the stored table verbatim, and this hands it through unchanged
 *  apart from filling the two fields `validate()` treats as optional. There is deliberately **no
 *  fallback to `a.table`**: that fallback IS the defect, and a path that silently discards history
 *  is worse than one that refuses. */
export function entriesFromRead(a: Authority): AuthorityEntryWire[] {
  return (a.entries ?? []).map((r) => ({
    ...r,
    supersedes: r.supersedes ?? [],
    authoritative: r.authoritative ?? true,
  }));
}

/** What a row was LOADED with — the baseline the control compares against and archives from. */
export interface SupersedeBaseline {
  document: string;
  as_of: string;
  freshness_days: number | null;
  reviewer: string | null;
}

/**
 * Record that `base.document` has been superseded by the authoritative row's new document.
 *
 * **THE CHAIN IS THE RECORD, and the first version of this file said the opposite.** `assess()`
 * computes `superseded_still_active` as
 * `{name for r in rows for name in r["supersedes"]}` and then flags any row that is
 * `authoritative` and whose document is in that set — so it reads the **`supersedes` lists** and
 * never looks at the archival rows at all. The comment here claimed *"the archival row is what
 * `assess()` actually reads"*, which is inverted, and that inversion is why the undo below was
 * written to over-reach: *if the chain is decorative, pruning it looks free.* It is not decorative;
 * it is the only thing the gate can see.
 *
 * The archival row is the ARCHIVE — `deal_authority.py`'s own premise, *"an older file is archived
 * rather than merely older"* — so the superseded document survives in the stored table with its own
 * date instead of vanishing when its name is overwritten. It carries `authoritative: false` so it
 * cannot itself trip the check it exists beside.
 *
 * **A chain could only ever be built through the raw PUT.** The editor preserved one it was handed
 * and never created one — the same class `reviewer` was in before it got an input. Review proposed
 * inferring it, archiving the loaded row whenever its document name changes, and that was declined
 * on the merits: a typo correction would permanently record a prior document that never existed, in
 * a table an investment committee reads, and `superseded_still_active` would then report a finding
 * about a file nobody ever held. *A fabricated supersession is worse than an absent one, because
 * the absent one is silent and the fabricated one is evidence.* So the user STATES it.
 *
 * It takes the paint-time BASELINE rather than looking the old row up in `rows`, because by the time
 * the editor calls this the live row has already been rewritten with the new name — so a lookup for
 * the old document finds nothing and the archival row silently inherits the REPLACEMENT's date,
 * with no reviewer and no freshness override. That was the shipped behaviour and two tests asserted
 * the opposite, passing only because their fixture left the date field untouched. *A test that
 * supplies the thing under test cannot notice that the caller never supplies it.*
 */
export function withSupersede(rows: readonly AuthorityEntryWire[], factType: string,
                              base: SupersedeBaseline): AuthorityEntryWire[] {
  const out = rows.map((r) => ({ ...r, supersedes: [...(r.supersedes ?? [])] }));
  const live = out.find((r) => r.fact_type === factType && r.authoritative !== false);
  if (!live || !base.document || live.document === base.document) return out;
  if (!live.supersedes.includes(base.document)) live.supersedes.push(base.document);
  // Deduped so the stored table does not grow a row per keystroke — `sync()` runs on every input
  // event. NOT because a duplicate would be "counted twice": `superseded_names` is a set, so it
  // could not be. That rationale was impossible and it was the tell for the inversion above.
  const already = out.some((r) => r.fact_type === factType && r.authoritative === false
    && r.document === base.document);
  if (!already) {
    out.push({
      fact_type: factType, document: base.document,
      as_of: base.as_of || live.as_of,
      freshness_days: base.freshness_days,
      authoritative: false, supersedes: [],
      reviewer: base.reviewer,
    });
  }
  return out;
}

/**
 * Undo `withSupersede` for `document` on ONE fact type.
 *
 * **Scoped to `factType` on both halves, and only ever called for a supersession this session
 * declared.** The first version was neither, and both gaps were real:
 *
 *   * its `map` stripped the name from EVERY row's chain while its `filter` was fact-type scoped, so
 *     undoing the rent roll's supersession of a document also cleared that name from the tax row's
 *     chain;
 *   * and the editor called it on every unticked `sync()`, including when nothing had been renamed —
 *     so on a table already in the `superseded_still_active` state, typing a **reviewer name** and
 *     saving pruned the chain that carried the finding, and the gate went green with a superseded
 *     document still authoritative. *An undo that runs when nothing was done is a delete.*
 */
export function withoutSupersede(rows: readonly AuthorityEntryWire[], factType: string,
                                 document: string): AuthorityEntryWire[] {
  if (!document) return rows.map((r) => ({ ...r, supersedes: [...(r.supersedes ?? [])] }));
  return rows
    .filter((r) => !(r.fact_type === factType && r.authoritative === false
      && r.document === document))
    .map((r) => (r.fact_type === factType
      ? { ...r, supersedes: (r.supersedes ?? []).filter((x) => x !== document) }
      : { ...r, supersedes: [...(r.supersedes ?? [])] }));
}

export interface AuthorityCtx {
  api: ApiClient;
  projectId: () => string | null | undefined;
  setStatus: (m: string) => void;
}

export function renderAuthorityCard(root: HTMLElement, ctx: AuthorityCtx): HTMLElement {
  const host = document.createElement("div");
  host.id = "pf-authority";
  host.className = "fin-card";
  host.style.marginTop = "10px";
  host.innerHTML = `<div class="section-title">Deal-room authority</div>`
    + `<div class="meta">One authoritative document per fact, with its date. A data room holds three `
    + `offering memoranda and a tax bill from before the reassessment; every one is a real file and `
    + `only one of each is the one to underwrite from.</div>`;

  const out = document.createElement("div"); host.appendChild(out);
  const editor = document.createElement("div"); editor.style.marginTop = "8px"; host.appendChild(editor);
  root.appendChild(host);

  // The WHOLE stored table, archival rows included. The editor only ever touches the authoritative
  // row for each fact type; everything else rides through the save untouched, which is the only
  // way a replacing PUT can be driven from a form without destroying history.
  const rows: AuthorityEntryWire[] = [];

  const paint = () => {
    editor.replaceChildren();
    const table = document.createElement("table"); table.className = "fin-table";
    table.innerHTML = `<tr class="fin-sub"><td>Fact type</td><td>document</td><td>as of</td>`
      + `<td class="num">freshness</td><td>reviewed by</td><td></td><td></td></tr>`;
    for (const [key, lab, days, required] of FACT_TYPES) {
      // `authoritative !== false`, not just `fact_type` — an archival row for a fact whose
      // authoritative document has been removed would otherwise be loaded into the form and then
      // saved back as authoritative, which is the `superseded_still_active` state the gate blocks.
      const row = rows.find((r) => r.fact_type === key && r.authoritative !== false);
      // Captured at PAINT, from the stored row — not read back off the input. The control's whole
      // job is comparing what is typed against what was LOADED, and an input's value is the first
      // thing to stop being that. The DATE, REVIEWER and FRESHNESS come with it, because the
      // archival row has to carry the superseded document's own, and by the time `sync()` runs the
      // live row has already been rewritten with the new name.
      const base: SupersedeBaseline = {
        document: row?.document ?? "",
        as_of: row?.as_of ?? "",
        freshness_days: row?.freshness_days ?? null,
        reviewer: row?.reviewer ?? null,
      };
      const was = base.document;
      // Has THIS control written a supersession into `rows`? The undo may remove only what the
      // control added — a chain entry and an archival row loaded from the server belong to whoever
      // declared them, and unticking a box the person only just ticked must not reach them.
      let declaredHere = false;
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      name.innerHTML = `${esc(lab)}${required ? ` <span class="meta">required</span>` : ""}`;
      const docCell = document.createElement("td");
      const doc = document.createElement("input");
      doc.className = "portal-filter"; doc.style.width = "100%";
      doc.placeholder = "document name"; doc.value = row?.document ?? "";
      docCell.appendChild(doc);
      const dateCell = document.createElement("td");
      const date = document.createElement("input");
      date.type = "date"; date.className = "portal-filter"; date.value = row?.as_of ?? "";
      dateCell.appendChild(date);
      const freshCell = document.createElement("td"); freshCell.className = "num";
      const fresh = document.createElement("input");
      fresh.type = "number"; fresh.className = "portal-filter"; fresh.style.width = "72px";
      fresh.placeholder = String(days);
      fresh.title = `Default ${days} days. A tax bill goes stale on a different clock from an offering package.`;
      fresh.value = row?.freshness_days != null && row.freshness_days !== days
        ? String(row.freshness_days) : "";
      freshCell.appendChild(fresh);
      const revCell = document.createElement("td");
      const rev = document.createElement("input");
      rev.className = "portal-filter"; rev.style.width = "100%";
      // `reviewer` round-tripped through the engine, was surfaced on the assessment, and NO SCREEN
      // could set it or show it — a field only the raw API could write. Preserving it on save was
      // the defect's fix; giving it an input is what makes the preservation visible to the person
      // doing the preserving.
      rev.placeholder = "reviewed by"; rev.value = row?.reviewer ?? "";
      revCell.appendChild(rev);
      // AUTHORITY-SUPERSEDE — the explicit control. It appears only once the typed name differs
      // from a non-empty loaded one, because a first declaration supersedes nothing and a typo
      // correction must not be offered as a supersession at all.
      const supCell = document.createElement("td");
      const sup = document.createElement("input");
      sup.type = "checkbox";
      sup.dataset.supersede = key;
      const supLabel = document.createElement("label");
      supLabel.className = "meta";
      supLabel.style.whiteSpace = "nowrap";
      supLabel.append(sup, document.createTextNode(" supersedes"));
      supCell.appendChild(supLabel);
      const refreshSup = () => {
        const typed = doc.value.trim();
        const offerable = !!was && !!typed && typed !== was;
        supLabel.hidden = !offerable;
        if (!offerable && sup.checked) sup.checked = false;
        supLabel.title = offerable
          ? `Record “${was}” as superseded by “${typed}”. It is archived rather than deleted, which `
            + `is what the gate above reads to catch a superseded document still being `
            + `underwritten from. Leave this unticked if you are correcting a typo.`
          : "";
      };
      const clearCell = document.createElement("td");
      const clear = document.createElement("button");
      clear.className = "tool-btn"; clear.textContent = "✕"; clear.title = "Remove this declaration";
      // ONE handler, and that is a correctness fix rather than tidying. This was
      // `clear.onclick = (wipe the inputs)` plus a separate `clear.addEventListener("click", sync)`,
      // which depends on the two firing in registration order — and **happy-dom fires the
      // addEventListener listener BEFORE `onclick`**, the reverse of what the DOM spec's
      // "event handlers are listeners registered at assignment time" rule gives. So the sync ran
      // against the values the person was clearing and nothing synced after they were cleared: the
      // ✕ re-applied the supersession it was cancelling. *Two handlers on one click is an ordering
      // assumption, and this one was wrong in the environment the tests run in.*
      clear.onclick = () => {
        doc.value = ""; date.value = ""; fresh.value = ""; rev.value = "";
        refreshSup();
        sync();
      };
      clearCell.appendChild(clear);

      const sync = () => {
        const i = rows.findIndex((r) => r.fact_type === key && r.authoritative !== false);
        const prev = i >= 0 ? rows[i] : undefined;
        const typed = doc.value.trim();
        // A row with no document is not declared at all — sending an empty one would be refused by
        // `validate()`, which requires a document name and a real date on every entry. Removing it
        // drops ONLY the authoritative row; archival rows for the same fact type stay, which is
        // what "this document is no longer the one to underwrite from" should mean.
        //
        // **It no longer RETURNS here**, and that was a defect: clearing the document with ✕ after
        // ticking the box skipped the bookkeeping below, so a cancelled supersession persisted as an
        // archival row that was no longer visible in the form and could not be removed from it. *An
        // early return past the undo leaves exactly the fabricated record this control exists not to
        // create.*
        if (!typed) {
          if (i >= 0) rows.splice(i, 1);
        } else {
          const entry: AuthorityEntryWire = {
            fact_type: key, document: typed, as_of: date.value,
            freshness_days: fresh.value.trim() === "" ? null : Number(fresh.value),
            authoritative: true,
            // CARRIED THROUGH, not rebuilt. `sync()` constructed a fresh object, so `supersedes` was
            // dropped from every row the person touched while rows they left alone kept theirs — the
            // worst available shape, because the loss is proportional to how much they edited.
            supersedes: prev?.supersedes ?? [],
            reviewer: rev.value.trim() || null,
          };
          if (i >= 0) rows[i] = entry; else rows.push(entry);
        }

        // Applied AFTER the live row is in place, because `withSupersede` reads it to decide.
        //
        // **The undo runs ONLY when this control had declared something.** It used to run on every
        // unticked pass, which meant editing an unrelated field — a reviewer name — pruned the
        // chain for the loaded document from the whole table. On a project already in the
        // `superseded_still_active` state that is the blocking finding itself, since `assess()`
        // reads chains: the gate went green with a superseded document still authoritative. *The
        // two directions are not symmetric, and writing them as if they were is what made an edit
        // into a delete.*
        const renamed = !!was && !!typed && typed !== was;
        if (renamed && sup.checked) {
          rows.splice(0, rows.length, ...withSupersede(rows, key, base));
          declaredHere = true;
        } else if (declaredHere) {
          rows.splice(0, rows.length, ...withoutSupersede(rows, key, was));
          declaredHere = false;
        }
      };
      refreshSup();
      doc.addEventListener("input", refreshSup);
      sup.addEventListener("change", sync);
      for (const input of [doc, date, fresh, rev]) input.onchange = sync;

      tr.append(name, docCell, dateCell, freshCell, revCell, supCell, clearCell);
      table.appendChild(tr);
    }
    editor.appendChild(table);

    const actions = document.createElement("div"); actions.style.marginTop = "6px";
    const save = document.createElement("button");
    save.className = "file-btn"; save.textContent = "Save authority table";
    actions.appendChild(save);
    editor.appendChild(actions);
    editor.insertAdjacentHTML("beforeend", meta(
      `Exactly one authoritative document per fact type — the server refuses two, and refuses any `
      + `entry without a date, because an undated document cannot be judged fresh or stale. `
      + `<strong>supersedes</strong> appears when you replace a document's name: tick it to archive `
      + `the old one as superseded, which is what the gate above reads to catch a superseded `
      + `document still being underwritten from. Leave it unticked when you are fixing a typo — a `
      + `supersession this table records is a prior document a committee will believe existed.`));

    save.onclick = async () => {
      const pid = ctx.projectId();
      if (!pid) { out.innerHTML = meta("Open a project first."); return; }
      const undated = rows.filter((r) => !r.as_of);
      if (undated.length) {
        // Caught here rather than sent, because the server's 422 names one entry by index and the
        // person is looking at a table of labels.
        out.innerHTML = meta(
          `${undated.map((r) => esc(label(r.fact_type))).join(", ")} `
          + `${undated.length === 1 ? "has" : "have"} a document but no date. An undated document `
          + `cannot be judged fresh or stale, so the table will not save.`, "var(--status-crit)");
        return;
      }
      save.disabled = true;
      ctx.setStatus("saving the authority table…");
      try {
        const res = await ctx.api.saveDealAuthority(pid, rows);
        out.replaceChildren();
        // The PUT returns the REASSESSMENT, so the gate on screen is the gate for what was just
        // saved. Re-fetching would race the write and could show the previous verdict.
        renderAuthority(out, res.assessment);
        // RE-ANCHOR THE EDITOR on what was actually stored. `was` and `base` are captured when a
        // row is painted, and nothing repainted after a save — so a SECOND rename in the same
        // session still compared against the document loaded at open: A→B then B→C stored
        // "C supersedes A" and lost B entirely, with the box still showing ticked against a name
        // that was now the stored one. `rows` IS what was just PUT, so repainting from it is both
        // correct and free, and it resets each row's `declaredHere` so the undo cannot reach a
        // supersession this save has made permanent.
        paint();
        ctx.setStatus(res.assessment.gate.passes
          ? "authority sufficient to underwrite" : "authority blocked");
      } catch (e) {
        out.innerHTML = meta(esc((e as Error).message), "var(--status-crit)");
        ctx.setStatus("authority table not saved");
      } finally {
        save.disabled = false;
      }
    };
  };

  const pid = ctx.projectId();
  if (!pid) {
    out.innerHTML = meta("Open a project to declare its authority table.");
    return host;
  }
  out.innerHTML = meta("loading…");
  void ctx.api.dealAuthority(pid).then((a) => {
    out.replaceChildren();
    renderAuthority(out, a);
    if (!Array.isArray(a.entries)) {
      // FAIL CLOSED. Without the stored table there is nothing to round-trip, and an editor that
      // opened anyway would save the authoritative view over the archival history. Refusing to
      // open is a visible problem; opening is a silent delete the next time somebody presses Save.
      editor.innerHTML = meta(
        `This server did not return the stored authority table, so the editor cannot save without `
        + `discarding archival rows and supersedes chains. The gate above is still accurate.`,
        "var(--status-crit)");
      return;
    }
    rows.splice(0, rows.length, ...entriesFromRead(a));
    paint();
  }).catch((e: Error) => {
    // ALSO FAIL CLOSED, and this arm is the MORE destructive of the two. `paint()` here opened the
    // editor over an empty `rows`, the undated pre-check passed trivially because there is nothing
    // to check, and Save then PUT `{entries: []}` over the whole stored blob — archival rows,
    // supersedes chains and reviewers gone, from a card that had just told the reader it could not
    // read the table. The branch above refuses to open for the *lesser* case, which is how review
    // found this one: *a fail-closed guard beside a fail-open neighbour reads as coverage.*
    out.innerHTML = meta(
      `${esc(e.message)} — the authority table could not be read, so the editor will not open: `
      + `saving from a blank form would replace the stored table with nothing.`,
      "var(--status-crit)");
  });
  return host;
}
