import { HttpError } from "../../api/httpCore";
import type { EffectiveRule } from "../../api/model";
import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * FIRM-RULES-OPTIONAL slice ② — the rule library could not be AUTHORED from the app at all.
 *
 * Slice ① made the firm's standards actually get evaluated and made a pass over the three sample
 * rules say that it was one. What it could not fix is why every project was on the samples in the
 * first place: `GET`/`PUT /projects/{pid}/rules` and `GET`/`PUT /firm/rules` had **no client method
 * between them**, so there was no way to write a rule from the product. The checks were real, the
 * validator was real, the override logic was real, and the library they all operated on could only
 * ever be the fallback.
 *
 * **Neither pair appeared in any list in `services/api/test_route_reachability.py`**, for two
 * different reasons, and that is the structural finding: the project pair is matched by the leaf
 * `rules` against the whole web blob, which `/projects/${pid}/rules/run` puts there — *one route's
 * URL vouching for another's* — and the firm pair sits in `LEAF_COLLISION_BLIND` because `rules`
 * collides. So nothing could have reported this, and the gate that exists to report exactly this
 * was structurally unable to.
 *
 * ## What this panel is careful about
 *
 * - **The sample fallback is named, not shown as a library.** `GET /projects/{pid}/rules` returns
 *   `seeded: true` with the three samples when nothing is saved; rendering them as "your rules"
 *   would be the same conflation slice ① removed from the check. Saving is what adopts them.
 * - **The firm save is platform-admin, and the refusal is explained before it happens.** That gate
 *   exists because `PUT /firm/rules` was once `require_role("admin")` on a path with no `{pid}`, so
 *   the caller chose which project's role was checked — any user could create a throwaway project
 *   and replace the firm's standards, which **also deleted them**. A disabled button with the reason
 *   beside it is better than a 403 after the typing.
 * - **A save REPLACES the library**, so the row count is shown against what was loaded and an empty
 *   save is refused rather than silently wiping a library.
 */

export interface LibraryReading {
  kind: "samples" | "empty" | "authored";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "";
}

/**
 * What a library card is looking at. Three states, because "nothing saved here" and "nothing saved
 * anywhere" lead to different next actions and neither is "a library with rules in it".
 */
export function libraryReading(scope: "firm" | "project", count: number,
                               seeded: boolean): LibraryReading {
  if (scope === "project" && seeded) {
    return {
      kind: "samples", tone: "warn",
      headline: `Nothing is saved for this project — these ${count} are the SAMPLE rules.`,
      detail: "They are what a rule check falls back to, and a clean result against them is not a "
        + "pass against anything anybody chose. Save to adopt them as this project's own, or edit "
        + "them first. Rules the firm has authored are inherited automatically and do not need "
        + "copying here.",
    };
  }
  if (!count) {
    return {
      kind: "empty", tone: "warn",
      headline: scope === "firm"
        ? "No firm standards are authored."
        : "This project has no rules of its own.",
      detail: scope === "firm"
        ? "Every project therefore falls back to its own library, or to the three sample rules when "
          + "it has none. A rule authored here is inherited by every project and can be overridden "
          + "on any one of them, visibly."
        : "The firm's standards apply unchanged. Add a rule here only to add to them, or to "
          + "override one by reusing its id.",
    };
  }
  return {
    kind: "authored", tone: "ok",
    headline: `${count} rule(s) authored at the ${scope === "firm" ? "firm" : "project"} level.`,
    detail: scope === "firm"
      ? "Inherited by every project. A project rule with the same id displaces one of these, and "
        + "says which it displaced."
      : "Layered over the firm's by rule id. Reusing a firm rule's id is an override — legitimate, "
        + "and recorded as one.",
  };
}

/** Why a save was refused, in the reader's terms rather than the status code's. */
export function saveRefusal(scope: "firm" | "project", err: unknown): string {
  const status = err instanceof HttpError ? err.status : 0;
  const msg = (err as Error)?.message || "unknown error";
  if (status === 403) {
    return scope === "firm"
      ? "Only a platform administrator can change the firm's standards. Overriding one on this "
        + "project is yours to do — add a rule below with the same id."
      : "You need the editor role on this project to change its rules.";
  }
  if (status === 422) {
    // The server validates both selectors with the same QUERY-DSL parser a check uses, so this is
    // the rule being unrunnable rather than a formatting preference. Its message names the rule.
    return `Rejected, and nothing was saved: ${msg}`;
  }
  return `Save failed: ${msg}`;
}

/** One editable row's worth of inputs. Exported so the reader can be tested without the panel. */
export interface RuleRow {
  id: string;
  name: string;
  scope: string;
  require: string;
  severity: string;
}

/**
 * Read the rows back into rules, dropping the wholly-blank ones.
 *
 * Blank rows are dropped because the editor always shows one empty row to type into — sending it
 * would make every save a 422 on an empty selector. A row with ANY field filled is kept, so a
 * half-typed rule is refused by the validator with its own message instead of being silently
 * discarded. *Dropping something the user typed is worse than refusing it.*
 */
export function rulesFromRows(rows: RuleRow[]): RuleRow[] {
  return rows
    .map((r) => ({
      id: r.id.trim(), name: r.name.trim(), scope: r.scope.trim(),
      require: r.require.trim(), severity: r.severity.trim() || "medium",
    }))
    .filter((r) => r.id || r.name || r.scope || r.require);
}

/**
 * Rule ids that appear more than once, lowercased for comparison and sorted.
 *
 * **A duplicate id is an ambiguous override, not a cosmetic problem.** `rule_library._norm`
 * validates both selectors, caps their length and generates an id when none is given — and says
 * nothing about two rules sharing one. `firm_standards.effective_rules` matches a project rule onto
 * a firm rule BY ID, and `attach_provenance` maps results by id as well, so two project rows
 * carrying one firm rule's id both claim to override it and the last one silently wins. *That is
 * the "whose rule is this" ambiguity the override machinery exists to remove, arriving through the
 * door that authors them.*
 *
 * Refused here rather than in the validator: changing `_norm` would be a behaviour change for every
 * library already stored, and the ids are typed on this screen.
 *
 * Blank ids are NOT reported — the server generates one per rule, so several blanks are several
 * distinct rules, and flagging them would refuse the ordinary way of adding two rows at once.
 */
export function duplicateIds(rules: RuleRow[]): string[] {
  const seen = new Map<string, number>();
  for (const r of rules) {
    const k = r.id.trim().toLowerCase();
    if (!k) continue;
    seen.set(k, (seen.get(k) || 0) + 1);
  }
  return [...seen.entries()].filter(([, n]) => n > 1).map(([k]) => k).sort();
}

/** `true` when a save would REPLACE a non-empty library with nothing. */
export function wouldWipe(loaded: number, next: number): boolean {
  return loaded > 0 && next === 0;
}

const SEVERITIES = ["high", "medium", "low"];

/**
 * One library's card: the reading, an editable row per rule, and a Save that refuses rather than
 * guesses.
 *
 * **Exported for the test, and the reason is a survivor.** The two refusals — a duplicate id and a
 * save that would empty the library — were first covered by source pins asserting the guard was
 * *called*, and `if (false)` around the whole block passed both: the call was still there, still in
 * the right order, and doing nothing. *Asserting that a decision is computed is not asserting that
 * it is acted on*, and the only way to assert the second is to press the button. So the test drives
 * this function and reads what reached the `save` callback.
 */
export function ruleEditor(host: HTMLElement, initial: EffectiveRule[],
                    opts: { scope: "firm" | "project"; seeded: boolean; canSave: boolean;
                            whyNot: string; save: (rules: RuleRow[]) => Promise<void>;
                            saved: (msg: string) => void }): void {
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  const read = libraryReading(opts.scope, initial.length, opts.seeded);
  const card = el("div", "dash-card"); card.style.marginBottom = "10px";
  const title = opts.scope === "firm" ? "🏛 Firm standards" : "📁 This project's rules";
  // textContent for all three, not innerHTML: the title is a constant and the reading is built
  // here, but a card that interpolates even one of them teaches the next editor that this is where
  // strings go — and the next string will be a rule name off the wire. The tone becomes a style on
  // an element rather than a CSS variable spliced into markup, which is also what keeps
  // `ruleStandards.test.ts`'s escaping rule free of exemptions.
  const head = el("div"); head.innerHTML = "<b></b>";
  (head.firstElementChild as HTMLElement).textContent = title;
  const line = el("div", "meta"); line.style.marginTop = "2px";
  line.style.color = `var(${read.tone === "warn" ? "--status-warn" : "--muted"})`;
  line.textContent = read.headline;
  const why = el("div", "meta"); why.style.marginTop = "2px"; why.textContent = read.detail;
  card.append(head, line, why);

  const table = el("table", "fin-table");
  table.style.cssText = "width:100%;font-size:12px;margin-top:8px";
  // An explicit <thead>, not a bare <tr>: assigning a header row through `innerHTML` makes the
  // browser wrap it in an implicit <tbody>, so `tbody tr` then matches the header as well as the
  // rules. Harmless on screen and not harmless to a test that counts rows — the behavioural test
  // below found it by trying to click a delete button the header does not have.
  table.innerHTML = `<thead><tr><th>id</th><th>name</th><th>scope selector</th>`
    + `<th>require selector</th><th>severity</th><th></th></tr></thead>`;
  const rowsBody = el("tbody"); table.appendChild(rowsBody);

  const inputs: { row: HTMLElement; get: () => RuleRow }[] = [];
  const addRow = (r?: EffectiveRule) => {
    const tr = el("tr");
    const mk = (v: string, ph: string, w: string) => {
      const td = el("td"); const i = el("input") as HTMLInputElement;
      i.className = "mini-input"; i.value = v; i.placeholder = ph;
      i.style.cssText = `width:${w};font-size:11.5px`;
      td.appendChild(i); tr.appendChild(td); return i;
    };
    const id = mk(r?.id || "", "fire-door-rating", "100%");
    const name = mk(r?.name || "", "Fire doors carry a rating", "100%");
    const scope = mk(r?.scope || "", "IfcDoor & Pset_DoorCommon.IsExternal=true", "100%");
    const req = mk(r?.require || "", "Pset_DoorCommon.FireRating", "100%");
    const sevTd = el("td"); const sev = el("select") as HTMLSelectElement;
    sev.className = "mini-select";
    sev.innerHTML = SEVERITIES.map((s) => `<option value="${esc(s)}">${esc(s)}`
      + `</option>`).join("");
    sev.value = r?.severity && SEVERITIES.includes(r.severity) ? r.severity : "medium";
    sevTd.appendChild(sev); tr.appendChild(sevTd);
    const delTd = el("td"); const del = el("button"); del.className = "mini-btn";
    del.textContent = "✕"; del.title = "Remove this rule from the library";
    del.onclick = () => {
      tr.remove();
      const i = inputs.findIndex((x) => x.row === tr);
      if (i >= 0) inputs.splice(i, 1);
    };
    delTd.appendChild(del); tr.appendChild(delTd);
    rowsBody.appendChild(tr);
    inputs.push({ row: tr, get: () => ({
      id: id.value, name: name.value, scope: scope.value, require: req.value, severity: sev.value }) });
  };
  for (const r of initial) addRow(r);
  addRow();                                   // one blank row to type into
  card.appendChild(table);

  const bar = el("div"); bar.style.cssText = "display:flex;gap:6px;margin-top:8px;align-items:center;flex-wrap:wrap";
  const add = el("button"); add.className = "mini-btn"; add.textContent = "+ rule";
  add.onclick = () => addRow();
  const saveBtn = el("button") as HTMLButtonElement; saveBtn.className = "mini-btn on";
  saveBtn.textContent = opts.seeded ? "Save (adopt these as this project's)" : "Save library";
  const status = el("span", "meta");
  if (!opts.canSave) {
    saveBtn.disabled = true;
    saveBtn.title = opts.whyNot;
    status.textContent = opts.whyNot;
  }
  saveBtn.onclick = () => void (async () => {
    const next = rulesFromRows(inputs.map((x) => x.get()));
    const dups = duplicateIds(next);
    if (dups.length) {
      status.textContent = `Two or more rules share an id (${dups.join(", ")}). An id is what an `
        + "override is matched on, so duplicates make it ambiguous which rule is in force — the "
        + "server would store both and the last one would quietly win. Give each rule its own id, "
        + "or leave the id blank and one will be generated.";
      return;
    }
    if (wouldWipe(initial.length, next.length)) {
      // A save REPLACES the library. Deleting every row and pressing Save is a plausible thing to
      // do by accident and is indistinguishable from meaning it, so it is refused rather than
      // guessed at — `rbac.py` records what losing the firm library cost the last time.
      status.textContent = "A save replaces the whole library, and this would leave it empty. "
        + "Remove the rules you mean to remove and keep at least one, or ask an administrator to "
        + "clear it deliberately.";
      return;
    }
    saveBtn.disabled = true; status.textContent = "saving…";
    try {
      await opts.save(next);
      toast(`${opts.scope === "firm" ? "Firm" : "Project"} rule library saved`, "success");
      // Re-read rather than patch the card in place. A project that has just saved its first
      // library is no longer `seeded`, and what APPLIES to it has changed too — leaving the
      // "these are the SAMPLE rules" line above a library the user just authored would be the
      // same stale-verdict defect this whole item is about, one screen later.
      opts.saved(`saved ${next.length} rule(s) — this is now what a check evaluates`);
    } catch (e) {
      status.textContent = saveRefusal(opts.scope, e);
      saveBtn.disabled = !opts.canSave;
    }
  })();
  bar.append(add, saveBtn, status);
  card.appendChild(bar);
  host.appendChild(card);
}

/**
 * The authoring surface: the firm's library, this project's, and what the two come to.
 *
 * Reached from the CDE / Standards panel, the way the jurisdiction packs are — a portal panel, so
 * it is lazily loaded by construction and costs the eager shell nothing. That matters here: the
 * viewer rail's eager chunk was five bytes from its budget when slice ① landed.
 */
export async function renderRuleStandards(ctx: PanelContext, flash = ""): Promise<void> {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("⚖ Rule standards (firm + project)", () => {
    void (async () => { await (await import("./standards")).renderStandards(ctx); })();
  }));
  const api = ctx.host.api;
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Rule standards")); return; }

  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.textContent = "A rule is a scope selector, a require selector and a severity: \"every "
    + "external door carries a fire rating\". Rules authored at the firm level outlive the project "
    + "and are inherited by all of them; a project rule with the same id overrides one, visibly. "
    + "Both are checked by Review → Rule check and by Model CI.";
  root.appendChild(intro);

  if (flash) {
    const f = el("div", "dash-card");
    f.style.cssText = "margin-bottom:10px;border-left:3px solid var(--status-good)";
    f.textContent = flash;
    root.appendChild(f);
  }

  const slot = el("div"); root.appendChild(slot);
  slot.innerHTML = `<div class="meta">loading…</div>`;

  let loaded: { firm: EffectiveRule[]; own: EffectiveRule[]; seeded: boolean;
                admin: boolean; effNote: string };
  try {
    const [f, o, me, eff] = await Promise.all([
      api.firmRules().catch(() => ({ rules: [] as EffectiveRule[] })),
      api.rulesLibrary(pid),
      api.me().catch(() => ({ platform_admin: false })),
      api.rulesEffective(pid).catch(() => null),
    ]);
    loaded = { firm: f.rules, own: o.rules, seeded: o.seeded,
               admin: !!me.platform_admin, effNote: eff?.note || "" };
  } catch (e) {
    slot.innerHTML = `<div class="meta">could not read the rule libraries: ${esc((e as Error).message)}</div>`;
    return;
  }
  if (!slot.isConnected) return;              // the reader moved on while this was in flight
  slot.innerHTML = "";

  if (loaded.effNote) {
    const sum = el("div", "dash-card"); sum.style.marginBottom = "10px";
    sum.innerHTML = `<div><b>What applies to this project</b></div>`
      + `<div class="meta" style="margin-top:2px">${esc(loaded.effNote)}</div>`;
    slot.appendChild(sum);
  }

  const reload = (msg: string) => void renderRuleStandards(ctx, msg);
  ruleEditor(slot, loaded.firm, {
    scope: "firm", seeded: false, canSave: loaded.admin,
    whyNot: "Only a platform administrator can change the firm's standards — overriding one on this "
      + "project is yours to do, below.",
    save: async (rules) => { await api.saveFirmRules(rules); }, saved: reload,
  });
  ruleEditor(slot, loaded.own, {
    scope: "project", seeded: loaded.seeded, canSave: true, whyNot: "",
    save: async (rules) => { await api.saveRules(pid, rules); }, saved: reload,
  });
}
