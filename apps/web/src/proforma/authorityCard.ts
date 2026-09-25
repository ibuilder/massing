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
export function renderAuthority(host: HTMLElement, a: Authority): HTMLElement {
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

/** One row of the editable table, as the PUT wants it. */
export interface AuthorityEntry {
  fact_type: string;
  document: string;
  as_of: string;
  freshness_days?: number | null;
  authoritative?: boolean;
  supersedes?: string[];
}

/** The entries a saved assessment implies, so the editor opens on what is already declared rather
 *  than on a blank form. Superseded rows are not returned by the GET — it reports the authoritative
 *  view — so this round-trips what IS authoritative and leaves archival history to the server. */
export function entriesFromAssessment(a: Authority): AuthorityEntry[] {
  return a.table.map((r) => ({
    fact_type: r.fact_type, document: r.document, as_of: r.as_of,
    freshness_days: r.freshness_days, authoritative: true,
    supersedes: r.supersedes ?? [],
  }));
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

  const rows: AuthorityEntry[] = [];

  const paint = () => {
    editor.replaceChildren();
    const table = document.createElement("table"); table.className = "fin-table";
    table.innerHTML = `<tr class="fin-sub"><td>Fact type</td><td>document</td><td>as of</td>`
      + `<td class="num">freshness</td><td></td></tr>`;
    for (const [key, lab, days, required] of FACT_TYPES) {
      const row = rows.find((r) => r.fact_type === key);
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
      const clearCell = document.createElement("td");
      const clear = document.createElement("button");
      clear.className = "tool-btn"; clear.textContent = "✕"; clear.title = "Remove this declaration";
      clear.onclick = () => { doc.value = ""; date.value = ""; fresh.value = ""; };
      clearCell.appendChild(clear);

      const sync = () => {
        const i = rows.findIndex((r) => r.fact_type === key);
        // A row with no document is not declared at all — sending an empty one would be refused by
        // `validate()`, which requires a document name and a real date on every entry.
        if (!doc.value.trim()) { if (i >= 0) rows.splice(i, 1); return; }
        const entry: AuthorityEntry = {
          fact_type: key, document: doc.value.trim(), as_of: date.value,
          freshness_days: fresh.value.trim() === "" ? null : Number(fresh.value),
          authoritative: true,
        };
        if (i >= 0) rows[i] = entry; else rows.push(entry);
      };
      for (const input of [doc, date, fresh]) input.onchange = sync;
      clear.addEventListener("click", sync);

      tr.append(name, docCell, dateCell, freshCell, clearCell);
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
      + `entry without a date, because an undated document cannot be judged fresh or stale.`));

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
    rows.splice(0, rows.length, ...entriesFromAssessment(a));
    paint();
  }).catch((e: Error) => {
    out.innerHTML = meta(esc(e.message), "var(--status-crit)");
    paint();
  });
  return host;
}
