/**
 * ESTIMATE-DARK — the button that makes `POST /projects/{pid}/cost/estimate` reachable, and the
 * editor that gives it rules to run.
 *
 * It sits in the budget panel's existing "📐 Estimate from the model" card, beside the two
 * estimates that were already there, and that placement is the argument for it: the conceptual
 * unit-rate estimate prices IFC classes off the cost database, the resource-based one builds each
 * class up from labour/material/equipment, and **neither lets a firm say what its own walls cost**.
 * This one runs the firm's selectors at the firm's rates. Three estimates of one model, with their
 * bases visibly different, is a comparison an estimator can actually use.
 *
 * **Filed Lane E in the roadmap and built in Lane B.** The entry said *"here because the
 * deliverable is the card"* and pointed at the viewer; the card belongs in the panel that already
 * holds its two siblings and the drawer they share. *Lanes go by the directory the work touches* —
 * the correction the lane table has now made for SITE-1, UX-3 and CAPTURE-SESSION, and this is a
 * fourth. It also keeps the editor out of the shell bundle, which had 1.9 KB of headroom.
 */
import type { CostRule, CostSov } from "../../api/cost";
import type { PanelContext } from "../panelContext";
import {
  deadRulesNote, estimateCoverage, estimateCoverageNote, estimateHeadline, estimateTone, gapGuids,
  gapPageNote, gapRows, linePageNote, lineRows, provenanceNote, sovBillableNotes, sovDriftNote,
  sovHeadline, sovItemRows, sovPageNote, sovTone, unchosenRatesNote, type EstimateRead,
} from "./costEstimateRead";

/** The two closed sets the server accepts, re-spelled here because no route publishes them.
 *
 *  A duplicated constant across the wire, and the drift is bounded in the one direction that
 *  matters: `fived.validate_rules` refuses an unknown basis with a 422 that NAMES the allowed list,
 *  and the editor renders that refusal verbatim — so a server that gained a basis leaves this
 *  picker merely incomplete, and one that lost a basis fails loudly at save rather than storing a
 *  rule that cannot price. *A re-spelled closed set needs a loud refusal behind it; this one has
 *  one, and that is why it is acceptable rather than merely convenient.* */
const BASES = ["area", "volume", "length", "weight", "count"];
const RATE_SOURCES = ["quoted", "vintage"];

const TONE_CSS: Record<string, string> = {
  "": "", ok: "var(--status-good)", warn: "var(--status-warn)", bad: "var(--status-crit)",
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = ""): HTMLElementTagNameMap[K] {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  return n;
}

function kv(rows: { k: string; v: string }[]): HTMLElement {
  const wrap = el("div");
  wrap.style.cssText = "overflow:auto;margin-top:4px";
  const t = el("table", "mini-table");
  t.style.width = "100%";
  const body = el("tbody");
  for (const r of rows) {
    const tr = el("tr");
    const a = el("td"); a.textContent = r.k;              // user-authored: textContent, never HTML
    const b = el("td"); b.textContent = r.v; b.style.textAlign = "right";
    tr.append(a, b); body.appendChild(tr);
  }
  t.appendChild(body); wrap.appendChild(t);
  return wrap;
}

function note(text: string, tone = ""): HTMLElement {
  const d = el("div", "meta");
  d.style.marginTop = "4px";
  if (TONE_CSS[tone]) d.style.color = TONE_CSS[tone];
  d.textContent = text;                                   // every note here carries server text
  return d;
}

/** The rule rows, as inputs. Element-based rather than an innerHTML template on purpose: a
 *  selector, a cost code and a description are all user-authored free text, and round-tripping them
 *  through markup is how one of them comes back with its quotes eaten. */
function ruleEditor(host: HTMLElement, rules: CostRule[],
                    onSave: (rules: CostRule[]) => Promise<void>, onCancel: () => void): void {
  host.innerHTML = "";
  const working: CostRule[] = rules.map((r) => ({ ...r }));
  const list = el("div");
  host.appendChild(list);

  const draw = () => {
    list.innerHTML = "";
    working.forEach((r, i) => {
      const row = el("div");
      row.style.cssText = "display:flex;gap:4px;flex-wrap:wrap;align-items:center;margin-bottom:4px";
      const sel = el("input"); sel.value = r.selector; sel.placeholder = "IfcWall & storey=L1";
      sel.style.cssText = "flex:2;min-width:140px";
      sel.title = "QUERY-DSL selector — which elements this rule prices";
      sel.oninput = () => { working[i]!.selector = sel.value; };
      const code = el("input"); code.value = r.code; code.placeholder = "03 30 00";
      code.style.cssText = "flex:1;min-width:80px";
      code.oninput = () => { working[i]!.code = code.value; };
      const basis = el("select");
      for (const b of BASES) {
        const o = el("option"); o.value = b; o.textContent = b; basis.appendChild(o);
      }
      basis.value = BASES.includes(r.basis) ? r.basis : "area";
      basis.onchange = () => { working[i]!.basis = basis.value; };
      const from = el("select");
      for (const s of RATE_SOURCES) {
        const o = el("option"); o.value = s;
        o.textContent = s === "vintage" ? "cost DB" : "quoted";
        from.appendChild(o);
      }
      from.value = RATE_SOURCES.includes(r.rate_from) ? r.rate_from : "quoted";
      const rate = el("input"); rate.type = "number"; rate.min = "0"; rate.step = "0.01";
      rate.value = String(r.unit_cost ?? 0);
      rate.style.cssText = "width:88px";
      rate.title = "Unit cost — ignored when the rate comes from the cost database";
      rate.oninput = () => { working[i]!.unit_cost = Number(rate.value) || 0; };
      const syncRate = () => {
        // A `vintage` rule's own number is not a fallback — `fived.validate_rules` ignores it and
        // the element lands in `no_rate` when the database has no rate for its class. Disabling the
        // box says so, rather than leaving a number on screen that will not be used.
        working[i]!.rate_from = from.value;
        rate.disabled = from.value === "vintage";
        rate.title = rate.disabled
          ? "The rate comes from the project's pinned cost database — this number is not used"
          : "Unit cost per unit of the chosen basis";
      };
      from.onchange = syncRate;
      syncRate();
      const desc = el("input"); desc.value = r.description; desc.placeholder = "description";
      desc.style.cssText = "flex:2;min-width:120px";
      desc.oninput = () => { working[i]!.description = desc.value; };
      const del = el("button", "tool-btn"); del.textContent = "✕";
      del.title = "Remove this rule";
      del.onclick = () => { working.splice(i, 1); draw(); };
      row.append(sel, code, basis, from, rate, desc, del);
      list.appendChild(row);
    });
  };
  draw();

  const bar = el("div");
  bar.style.cssText = "display:flex;gap:6px;margin-top:6px;flex-wrap:wrap";
  const add = el("button", "tool-btn"); add.textContent = "+ Add rule";
  add.onclick = () => {
    working.push({ selector: "", code: "", basis: "area", unit_cost: 0,
                   rate_from: "quoted", description: "" });
    draw();
  };
  const save = el("button", "tool-btn"); save.textContent = "Save rules";
  const cancel = el("button", "tool-btn"); cancel.textContent = "Cancel";
  cancel.onclick = onCancel;
  const err = el("div", "meta");
  save.onclick = async () => {
    save.disabled = true;
    err.textContent = "";
    try {
      await onSave(working);
    } catch (e) {
      // The server validates every selector through the SAME function the estimate runs, so a 422
      // here is the real refusal rather than a client guess at one — rendered verbatim, because it
      // names the rule index and what was wrong with it.
      err.textContent = `Not saved: ${(e as Error).message}`;
      save.disabled = false;
    }
  };
  bar.append(add, save, cancel);
  host.append(bar, err);
}

/** Render the estimate into the drawer. Exported for the panel; the readings it uses are pure and
 *  asserted in `apps/web/src/portal/panels/costEstimateRead.test.ts`. */
function renderEstimate(host: HTMLElement, e: EstimateRead, onEdit: () => void,
                        onSov?: (markupPct: number) => void): void {
  host.innerHTML = "";
  const head = el("div");
  head.style.cssText = "font-weight:600;margin-bottom:2px";
  const tone = estimateTone(e);
  if (TONE_CSS[tone]) head.style.color = TONE_CSS[tone];
  head.textContent = `Rules-based estimate — ${estimateHeadline(e)}`;
  host.appendChild(head);

  // The rate axis first: a reader who sees the placeholder caveat goes and edits the rules, and a
  // reader who sees the total first forwards it.
  const unchosen = unchosenRatesNote(e);
  if (unchosen) host.appendChild(note(unchosen, "warn"));
  const cover = estimateCoverageNote(e);
  if (cover) host.appendChild(note(cover, e.line_count ? "" : "bad"));
  // A rule that produced nothing. No save-time check can catch it — the selector grammar refuses
  // an empty query and little else — so the estimate is the only place a typo'd property name
  // shows up, and only if somebody says so.
  const dead = deadRulesNote(e);
  if (dead) host.appendChild(note(dead, "warn"));
  const prov = provenanceNote(e);
  if (prov) host.appendChild(note(prov));

  if (e.line_count) {
    host.appendChild(kv(lineRows(e)));
    const page = linePageNote(e);
    if (page) host.appendChild(note(page));
  }
  const gaps = gapRows(e);
  if (gaps.length) {
    host.appendChild(note("Outside the total — each row names which gap it is in:"));
    host.appendChild(kv(gaps));
    const gp = gapPageNote(e);
    if (gp) host.appendChild(note(gp));
    // No isolate here: this is the portal, which has no viewport to isolate INTO. What the reader
    // can do with the list is take it somewhere that has one — the viewer's selector box, a
    // coordination issue, an email to the modeller — so the affordance is a copy, not a dead
    // button. *An action a screen cannot perform is worse offered than withheld.*
    const guids = gapGuids(e);
    if (guids.length) {
      const copy = el("button", "tool-btn");
      copy.textContent = `⧉ Copy ${guids.length} GlobalId(s)`;
      copy.title = "Copy the unpriced elements' GlobalIds — paste them into the viewer to isolate "
        + "them, or into an issue for the modeller";
      copy.onclick = () => {
        void navigator.clipboard?.writeText(guids.join("\n"))
          .then(() => { copy.textContent = `⧉ Copied ${guids.length} GlobalId(s)`; })
          // A denied clipboard permission is an ordinary outcome in a browser, not an error worth a
          // status toast — but it must not leave the button claiming it copied.
          .catch(() => { copy.textContent = "⧉ Copy blocked by the browser"; });
      };
      host.appendChild(copy);
    }
  }
  const bar = el("div");
  bar.style.cssText = "display:flex;gap:6px;margin-top:6px;flex-wrap:wrap;align-items:center";
  const edit = el("button", "tool-btn");
  edit.textContent = e.rules_seeded ? "✎ Edit the starter rules" : "✎ Edit cost rules";
  edit.onclick = onEdit;
  bar.appendChild(edit);
  if (onSov && e.line_count && !estimateCoverage(e).noModelIndex) {
    const markup = el("input"); markup.type = "number"; markup.min = "0"; markup.step = "0.5";
    markup.value = "0"; markup.style.width = "72px";
    markup.title = "Markup %, applied to the subtotal";
    const mLabel = el("span", "meta"); mLabel.textContent = "markup %";
    const sov = el("button", "tool-btn"); sov.textContent = "Σ Schedule of values";
    sov.title = "The SOV built from THIS estimate — `/cost/sov` shares `_run_estimate` with "
      + "`/cost/estimate`, so the billed number cannot come from a different estimate than the "
      + "priced one";
    sov.onclick = () => onSov(Number(markup.value) || 0);
    bar.append(markup, mLabel, sov);
  }
  host.appendChild(bar);
}

/** The schedule of values, with the three preconditions its own route asks a caller to read.
 *
 *  **The estimate's caveats are re-rendered here too**, because this view replaces the estimate in
 *  the drawer: an SOV is the document a GC bills against, so a reader who arrives from a
 *  placeholder-rate estimate and sees only line values has lost the one fact that matters about
 *  them. The response carries `estimate_total` rather than the estimate, which is enough to notice
 *  that the rule set moved in between — see `sovDriftNote`. */
function renderSov(host: HTMLElement, sov: CostSov, read: EstimateRead, back: () => void): void {
  host.innerHTML = "";
  const head = el("div");
  head.style.cssText = "font-weight:600;margin-bottom:2px";
  const tone = sovTone(sov);
  if (TONE_CSS[tone]) head.style.color = TONE_CSS[tone];
  head.textContent = `Schedule of values — ${sovHeadline(sov)}`;
  host.appendChild(head);

  const drift = sovDriftNote(sov, read.total);
  if (drift) host.appendChild(note(drift, "bad"));
  for (const n of sovBillableNotes(sov)) {
    host.appendChild(note(n, n.startsWith("AT COST") ? "" : "warn"));
  }
  // The rate axis again. It is a fact about the estimate under this schedule, and it does not stop
  // being true because the reader navigated.
  const unchosen = unchosenRatesNote(read);
  if (unchosen) host.appendChild(note(unchosen, "warn"));

  if (sov.items.length) {
    host.appendChild(kv(sovItemRows(sov)));
    const page = sovPageNote(sov);
    if (page) host.appendChild(note(page));
  }
  if (sov.excluded.length) {
    host.appendChild(kv(sov.excluded.map((x) => ({
      k: `excluded — ${x.reason}`,
      v: `${x.count} element(s)${x.guids.length < x.count ? ` (${x.guids.length} listed)` : ""}`,
    }))));
  }
  host.appendChild(note(sov.note));
  const bk = el("button", "tool-btn"); bk.textContent = "← Back to the estimate";
  bk.onclick = back;
  host.appendChild(bk);
}

/**
 * The button, wired to the drawer the card already shares.
 *
 * One flow with two states — read the estimate, edit the rules — because they are the same task:
 * every number on the estimate is a consequence of a rule, and a reader who disagrees with a total
 * wants the rule that produced it, not a second screen.
 */
export function pricedEstimateButton(ctx: PanelContext, pid: string,
                                     drawer: HTMLElement): HTMLButtonElement {
  const api = ctx.host.api;
  const btn = el("button", "tool-btn");
  btn.textContent = "🧾 Rules-based (your cost rules)";
  btn.title = "Price the model with the project's own cost rules — a QUERY-DSL selector, a cost "
    + "code, a basis and a rate";

  const run = async () => {
    drawer.innerHTML = `<div class="meta">Pricing the model from the project's cost rules…</div>`;
    let set, est;
    try {
      // Both calls, and for different things. The ESTIMATE carries `rules_seeded` itself — the
      // route puts it there precisely so a reader cannot lose it — so the rule set is fetched only
      // to populate the EDITOR, never to qualify the total.
      [set, est] = await Promise.all([api.costRules(pid), api.costEstimate(pid)]);
    } catch (err) {
      drawer.innerHTML = "";
      drawer.appendChild(note(`Estimate unavailable: ${(err as Error).message}`));
      return;
    }
    // The status line names the COVERAGE, not just the total — it is the one line a reader sees
    // after a slow call, and `unpriced_count` is the single most useful fact about a priced model:
    // how much of it the rules did not reach. `complete` alone would read as a finished estimate.
    ctx.host.setStatus(est.unpriced_count
      ? `estimate: ${est.line_count} line(s), ${est.unpriced_count} element(s) unpriced`
      : `estimate: ${est.line_count} line(s), every element matched`);
    // Passed through UNCHANGED, not re-wrapped. An earlier draft built `{...est, rules_seeded:
    // set.seeded}` from the rule call, which was a client-side guess at a server fact AND broke
    // `test_verdict_coverage`'s delegation hop — it follows the response holder into an imported
    // reader, and a spread into a fresh object is no longer that holder. *A re-wrapped response is
    // invisible to any derivation that tracks the original*, which is the same lesson
    // `noRespelledShapes` records one level up, at the type.
    renderEstimate(drawer, est, () => edit(set!.rules),
                   (markupPct) => void sov(est!, markupPct));
  };

  const sov = async (read: EstimateRead, markupPct: number) => {
    drawer.innerHTML = `<div class="meta">Building the schedule of values…</div>`;
    try {
      const s = await api.costSov(pid, { markup_pct: markupPct });
      renderSov(drawer, s, read, () => void run());
    } catch (err) {
      drawer.innerHTML = "";
      drawer.appendChild(note(`Schedule of values unavailable: ${(err as Error).message}`));
    }
  };

  const edit = (rules: CostRule[]) => {
    drawer.innerHTML = "";
    const head = el("div");
    head.style.cssText = "font-weight:600;margin-bottom:4px";
    head.textContent = "Cost rules — a selector, a cost code, a basis and a rate";
    const why = note("Saved through the same validator the estimate runs, so a set that saves is a "
      + "set that prices — but that only checks a selector is WELL-FORMED, never that it matches "
      + "anything, so run the estimate and read which rules priced nothing. Later rules win, which "
      + "is how estimates are actually built: price every wall, then override the shear walls.");
    drawer.append(head, why);
    const host = el("div");
    drawer.appendChild(host);
    ruleEditor(host, rules, async (next) => {
      const r = await api.saveCostRules(pid, next);
      ctx.host.setStatus(`cost rules saved (${r.saved})`);
      await run();
    }, () => void run());
  };

  btn.onclick = () => {
    void (async () => {
      btn.disabled = true;
      try { await run(); } finally { btn.disabled = false; }
    })();
  };
  return btn;
}
