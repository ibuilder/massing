import type { ClausePosition } from "../../api/creDeal";
import { escapeHtml as esc } from "../../ui/feedback";
import { toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * CRE-CLAUSE — the clause-position playbook, made authorable (CLAUSE-DARK).
 *
 * `services/api/src/aec_api/clause_playbook.py` has shipped a complete, validated per-contract-type
 * registry since R20: for each clause that costs money, the position we **accept**, the position we
 * **negotiate**, the position we **refuse**, a severity and a fallback — plus ten curated starter
 * clauses and a review that reports every playbook clause a reading never addressed as
 * `not_reviewed` rather than assumed fine.
 *
 * **Nothing in this product could store one.** `reviewContractClauses` HAS a caller — the
 * "📕 Playbook positions" control on the contract-risk tab — so the review engine was reachable, and
 * `from_project` returns `verdict: "no_playbook"` whenever the store is empty. That was therefore
 * the ONLY answer that control could ever give, on every project that has ever existed, and the
 * refusal's own note names the remedy: *"Store a playbook first — reviewing without a written
 * standard is the problem this feature exists to fix."* Both client methods that could store one
 * (`clausePlaybook`, `saveClausePlaybook`) sat on `clientCallers.test.ts`'s unreachable list.
 *
 * *A refusal is only honest if its remedy is reachable* — which is why this editor lives in the same
 * panel as the control that refuses, one tab away, and why that control now names this tab.
 *
 * **Seeding is non-destructive, deliberately.** `seedFrom` adds only the starter clauses whose names
 * are not already present. A firm that has written down its own position on indemnity must not lose
 * it by clicking a button labelled "seed" — and the starter is explicitly *"a checklist shape, not a
 * position on your deal"*.
 *
 * **No completeness verdict is rendered, only coverage.** The temptation is a green "your standard
 * is complete" badge; there is no such property. What `coverage()` reports is counted facts — how
 * many clauses, how many carry a red line, how many are high severity — because a verdict over a
 * subset with no coverage beside it is the defect this repository has now found eighteen times.
 */

/** Clauses with no red line. The server REFUSES these, and this marks them before the round trip:
 *  `validate()` raises *"a clause with no red line is not a standard"* naming the first one, so a
 *  12-clause save with three gaps otherwise costs three attempts to find out. */
export function rowGaps(rows: readonly ClausePosition[]): string[] {
  return rows.filter((r) => !(r.refuse ?? "").trim()).map((r) => r.clause || "(unnamed)");
}

/** Counted facts about one contract type's standard. NOT a verdict — see the note above. */
export function coverage(rows: readonly ClausePosition[]): {
  clauses: number; red_lined: number; with_fallback: number; high: number; gaps: number;
} {
  return {
    clauses: rows.length,
    red_lined: rows.filter((r) => (r.refuse ?? "").trim()).length,
    with_fallback: rows.filter((r) => (r.fallback ?? "").trim()).length,
    high: rows.filter((r) => r.severity === "high").length,
    gaps: rowGaps(rows).length,
  };
}

/** The starter clauses this type does not already name, matched case-insensitively exactly as the
 *  server's `validate` dedupes (`name.lower() in seen`) — so seeding can never produce the duplicate
 *  it would then be refused for. */
export function seedFrom(starter: readonly ClausePosition[],
                         existing: readonly ClausePosition[]): ClausePosition[] {
  const have = new Set(existing.map((r) => (r.clause || "").trim().toLowerCase()));
  return starter.filter((s) => !have.has((s.clause || "").trim().toLowerCase()))
    .map((s) => ({ ...s }));
}

/** Contract types in a stored playbook, sorted — the same order `from_project` reports as
 *  `available_types` when it refuses, so the two screens name them the same way. */
export function typeNames(playbook: Record<string, ClausePosition[]> | undefined | null): string[] {
  return Object.keys(playbook ?? {}).sort();
}

const SEVERITIES = ["high", "medium", "low"] as const;

export async function renderClausePlaybook(ctx: PanelContext, body: HTMLElement,
                                           pid: string): Promise<void> {
  body.innerHTML = `<div class="meta">reading the playbook…</div>`;
  let wire: Awaited<ReturnType<typeof ctx.host.api.clausePlaybook>>;
  try {
    wire = await ctx.host.api.clausePlaybook(pid);
  } catch (e) {
    body.innerHTML = `<div class="meta">Playbook unavailable: ${esc((e as Error).message)}</div>`;
    return;
  }

  // The working copy. Every edit lands here and nothing is sent until Save, so a half-typed clause
  // never reaches a store the contract review reads.
  const draft: Record<string, ClausePosition[]> = {};
  for (const [k, v] of Object.entries(wire.playbook ?? {})) draft[k] = v.map((r) => ({ ...r }));
  let active = typeNames(draft)[0] ?? "subcontract";

  body.innerHTML = "";
  const intro = document.createElement("div"); intro.className = "meta";
  intro.style.marginBottom = "8px";
  intro.textContent = "Your firm's position on the clauses that cost money — what you accept, what "
    + "you negotiate, and the red line you refuse. The contract-risk tab scores a reading against "
    + "this; a clause with no stated position comes back as NOT REVIEWED, never as acceptable. "
    + "Not legal advice.";
  body.appendChild(intro);

  const typeRow = document.createElement("div");
  typeRow.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:8px";
  const sel = document.createElement("select"); sel.className = "portal-filter";
  const newName = document.createElement("input"); newName.className = "portal-filter";
  newName.placeholder = "new contract type (e.g. design services)";
  newName.style.cssText = "flex:1 1 180px;font-size:12px";
  newName.maxLength = 60;                                  // matches validate()'s `[:60]`
  const addType = document.createElement("button"); addType.className = "tool-btn";
  addType.textContent = "＋ type";
  typeRow.append(sel, newName, addType);
  body.appendChild(typeRow);

  const cov = document.createElement("div"); cov.className = "meta"; cov.style.margin = "2px 0 6px";
  const table = document.createElement("div");
  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:8px";
  const addRow = document.createElement("button"); addRow.className = "tool-btn";
  addRow.textContent = "＋ clause";
  const seed = document.createElement("button"); seed.className = "tool-btn";
  const save = document.createElement("button"); save.className = "tool-btn on";
  save.textContent = "Save playbook";
  const msg = document.createElement("div"); msg.className = "meta"; msg.style.marginTop = "6px";
  msg.setAttribute("role", "status");
  foot.append(addRow, seed, save);
  body.append(cov, table, foot, msg);

  const rows = () => (draft[active] ??= []);

  const paintTypes = () => {
    sel.innerHTML = "";
    for (const t of typeNames(draft)) {
      const o = document.createElement("option"); o.value = t; o.textContent = t;
      o.selected = t === active; sel.appendChild(o);
    }
    if (!sel.options.length) {
      const o = document.createElement("option"); o.value = active; o.textContent = active;
      sel.appendChild(o);
    }
  };

  const paint = () => {
    paintTypes();
    const c = coverage(rows());
    // A BOUND and counted facts, never a completeness claim. The gap count leads when it is
    // non-zero, because the server will refuse the save and this is the only screen that can say
    // which clause is missing its red line before the round trip.
    cov.textContent = `${c.clauses} clause${c.clauses === 1 ? "" : "s"} · ${c.red_lined} with a red `
      + `line · ${c.with_fallback} with a fallback · ${c.high} high severity`
      + (c.gaps ? ` · ⚠ ${c.gaps} with NO red line — a clause with no red line is not a standard` : "");
    const avail = seedFrom(wire.starter ?? [], rows());
    seed.textContent = `Seed ${avail.length} from the starter standard`;
    seed.disabled = avail.length === 0;
    seed.title = avail.length
      ? "Adds the curated money clauses this type does not already name. Never overwrites a position you have written."
      : "Every starter clause is already named in this type";

    table.innerHTML = "";
    if (!rows().length) {
      const empty = document.createElement("div"); empty.className = "meta";
      empty.textContent = "No clauses in this type yet. Seed the starter standard, or add one.";
      table.appendChild(empty);
      return;
    }
    rows().forEach((r, i) => {
      const card = document.createElement("div"); card.className = "dash-card";
      card.style.cssText = "margin:6px 0;padding:8px";
      const head = document.createElement("div");
      head.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
      const name = document.createElement("input"); name.className = "portal-filter";
      name.value = r.clause ?? ""; name.placeholder = "clause"; name.maxLength = 120;
      name.style.cssText = "flex:1 1 180px;font-weight:600";
      name.oninput = () => { r.clause = name.value; };
      const sev = document.createElement("select"); sev.className = "portal-filter";
      for (const s of SEVERITIES) {
        const o = document.createElement("option"); o.value = s; o.textContent = s;
        o.selected = (r.severity || "medium") === s; sev.appendChild(o);
      }
      sev.onchange = () => { r.severity = sev.value; paint(); };
      const del = document.createElement("button"); del.className = "selset-del";
      del.textContent = "✕"; del.title = "Remove this clause from the standard";
      del.onclick = () => { rows().splice(i, 1); paint(); };
      head.append(name, sev, del);
      card.appendChild(head);

      const field = (label: string, value: string, hint: string,
                     set: (v: string) => void, red = false) => {
        const l = document.createElement("label"); l.className = "meta";
        l.style.cssText = "display:block;margin-top:4px";
        l.textContent = label;
        const inp = document.createElement("input"); inp.className = "portal-filter";
        inp.value = value; inp.placeholder = hint; inp.maxLength = 400;
        inp.style.cssText = "width:100%;box-sizing:border-box;font-size:12px";
        if (red && !value.trim()) inp.style.borderColor = "var(--status-crit)";
        inp.oninput = () => { set(inp.value); if (red) paint(); };
        l.appendChild(inp);
        return l;
      };
      card.append(
        field("Accept", r.accept ?? "", "the position we sign without comment",
              (v) => { r.accept = v; }),
        field("Negotiate", r.negotiate ?? "", "the middle ground we will take",
              (v) => { r.negotiate = v; }),
        field("Refuse — the red line (required)", r.refuse ?? "",
              "the position we will not sign", (v) => { r.refuse = v; }, true),
        field("Fallback", r.fallback ?? "", "what we offer instead when they refuse ours",
              (v) => { r.fallback = v; }),
      );
      table.appendChild(card);
    });
  };

  sel.onchange = () => { active = sel.value; paint(); };
  addType.onclick = () => {
    const t = newName.value.trim().slice(0, 60);
    if (!t) { msg.textContent = "Name the contract type first."; return; }
    if (typeNames(draft).some((x) => x.toLowerCase() === t.toLowerCase())) {
      msg.textContent = `“${t}” already exists.`; active = t; paint(); return;
    }
    draft[t] = []; active = t; newName.value = ""; msg.textContent = ""; paint();
  };
  addRow.onclick = () => {
    rows().push({ clause: "", severity: "medium", accept: "", negotiate: "", refuse: "",
                  fallback: "" });
    paint();
  };
  seed.onclick = () => {
    const add = seedFrom(wire.starter ?? [], rows());
    rows().push(...add);
    msg.textContent = `Added ${add.length} starter clause${add.length === 1 ? "" : "s"} — review each `
      + "one against this deal before saving.";
    paint();
  };
  save.onclick = async () => {
    // Empty types are dropped rather than sent: `validate()` refuses a type with no clauses, and a
    // type somebody created and then emptied is not a standard anybody wants refused on their behalf.
    const payload: Record<string, ClausePosition[]> = {};
    for (const [k, v] of Object.entries(draft)) if (v.length) payload[k] = v;
    if (!Object.keys(payload).length) {
      msg.textContent = "Nothing to save — add at least one clause.";
      return;
    }
    save.disabled = true; msg.textContent = "saving…";
    try {
      const res = await ctx.host.api.saveClausePlaybook(pid, payload);
      for (const k of Object.keys(draft)) delete draft[k];
      for (const [k, v] of Object.entries(res.playbook ?? {})) draft[k] = v.map((r) => ({ ...r }));
      if (!typeNames(draft).includes(active)) active = typeNames(draft)[0] ?? active;
      msg.textContent = `Saved — ${typeNames(draft).length} contract type(s). The contract-risk tab `
        + "scores against this now.";
      toast("Clause playbook saved", "success");
      paint();
    } catch (e) {
      // The server's message names the contract type and the clause. Shown verbatim, because a
      // generic "save failed" would hide the one thing that says what to fix.
      msg.textContent = `Refused: ${(e as Error).message}`;
    } finally {
      save.disabled = false;
    }
  };

  paint();
}
