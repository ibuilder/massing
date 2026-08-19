import type { ModuleDef, ModuleRecord, RecordBrief } from "../../api/client";
import type { ModuleFilterOp } from "../../api/types";
import { money as usd } from "../../ui/charts";
import { statusChip } from "../../ui/chips";
import { type RegisterEmptyKind, registerEmptyEl } from "../../ui/empty";
import { emptyHint } from "../../ui/emptyGuide";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import { confidenceReading } from "../../ui/confidenceReading";
import { confirmModal, modalShell, promptModal } from "../../ui/modal";
import { allQueued, dequeue, enqueueUpload, queuedCountForRecord } from "../offlineQueue";
import type { PanelContext } from "../panelContext";
import { pushRecent } from "../prefs";
import { schemaStaleBanner } from "./schemaStale";
import { appendRecordElementTies } from "./elementTies";

/**
 * How many records of a referenced module are fetched to build the id→label map for a table.
 *
 * A bound is necessary — a reference column must not pull an unbounded register to render one page —
 * but the bound is also a correctness boundary, so it is named rather than buried as a literal. Past
 * this many records the tail of the target module is genuinely unresolvable from the client, and
 * `refCell` is required to SAY so instead of inventing a label. See MOD-SWEEP below.
 */
const REF_RESOLVE_LIMIT = 500;

/** A record id is a `uuid.uuid4()` string server-side, so this distinguishes an id from free text. */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * MOD-FILTER — everything currently narrowing a register view.
 *
 * `q` and `state` were the whole vocabulary; `fields` is the per-field half. It is threaded through
 * `openModule` rather than held on the instance so that every re-render — a saved view, a page step,
 * an inline edit — either passes the filters on deliberately or drops them visibly. A filter
 * surviving in hidden state while the controls show something else is the worst of both.
 */
/**
 * MOD-PERCENT — the field types that hold a MAGNITUDE, named once.
 *
 * The form layer asked `f.type === "number" || f.type === "currency"` in three separate places, and
 * `percent` was in none of them. That was survivable while two fields in the whole system were typed
 * `percent`; the field sweep converted 21 more across 16 registers — every retainage, fee, overhead
 * and contingency percentage — and each of the three sites failed differently and quietly:
 *
 * 1. `EDITABLE` omitted it, so those fields stopped being inline-editable. A capability removed with
 *    no error and no visible cause.
 * 2. The record form rendered `<input type="text">` — no numeric keyboard on a phone, no step, no
 *    browser validation.
 * 3. The save path skipped `Number(v)`, storing the STRING "5". `validate_record` calls `float(value)`
 *    so it passes, and every consumer coerces, so nothing ever failed — the column just accumulated a
 *    mixture of `5` and `"5"` depending on which form last touched the record. That is the worst of
 *    the three precisely because it never surfaces.
 *
 * One list, referenced three times, so adding the next numeric type is one edit rather than three
 * that can be done two-thirds of the way. `test_module_fields.py` could not have caught any of this:
 * it reads config shape and says nothing about whether the UI can render it.
 */
export const NUMERIC_FIELD_TYPES = ["number", "currency", "percent"] as const;
const isNumericField = (t: string) => (NUMERIC_FIELD_TYPES as readonly string[]).includes(t);

/**
 * Field types the table can edit IN PLACE. Hoisted out of the row loop and exported so a test can
 * compare it against the types the shipped modules actually declare — the check that would have
 * caught `percent` missing here, and the one that catches the NEXT type rather than this one.
 *
 * A type absent from both this list and `READ_ONLY_FIELD_TYPES` is a type the form silently cannot
 * handle, which is exactly how `percent` went unnoticed: nothing errored, a capability just stopped
 * existing for 21 fields.
 */
export const EDITABLE_FIELD_TYPES = [
  "text", "textarea", ...NUMERIC_FIELD_TYPES, "date", "select", "checkbox", "email", "phone",
] as const;

/** Types deliberately NOT inline-editable, each for a stated reason — so "not editable" is a
 *  decision on the record rather than an omission nobody noticed. */
export const READ_ONLY_FIELD_TYPES = [
  "rollup",      // computed from other records; editing it would be editing a derived value
  "signature",   // captured through the signing flow, which carries the attestation
  "file",        // needs an upload control, not a cell
  "reference",   // edited through the record picker (`inlineRefCell`), not as free text
  "multiselect", // needs a multi-choice control a table cell has no room for
  // MOD-TABLE. A line-item grid has no cell-sized inline editor: its value is an array of objects,
  // and a register cell shows the summary ("3 lines · $118,260") instead. Edited in the record form
  // via `tableEditor`, which is where a grid has room to exist.
  //
  // This entry is the gate working as designed. `fieldTypeCoverage.test.ts` was written one PR ago to
  // catch a type added to `FIELD_TYPES` without a renderer classification — and the very next PR to
  // add a type was this one. It failed until the type was classified, which is exactly the outcome
  // that was wanted: the cost of a new type is one deliberate line saying how it renders.
  "table",
] as const;

export interface RegisterFilter {
  q?: string;
  state?: string;
  offset?: number;
  /** field name -> {op, value}. Sent as `f.<field>[.<op>]`; the server 400s on an unknown field. */
  fields?: Record<string, { op: ModuleFilterOp; value: string }>;
}
interface Conversion {
  to: string;                                          // target module key
  label: string;                                       // button text (target name)
  back?: string;                                       // reference field on the target pointing back to the source
  when?: (d: Record<string, unknown>) => boolean;      // only offer when this holds (else fall through)
  map: (d: Record<string, unknown>) => Record<string, unknown>;  // copy source fields → new record
}

// C1 — one-click cross-module conversions (Procore "convert RFI to PCO" etc.). The new record is
// pre-filled from the source and linked back (via a reference field when one exists, else an explicit link).
const CONVERSIONS: Record<string, Conversion[]> = {
  cor: [
    { to: "sov", label: "SOV line", back: "cor",
      map: (d) => ({ item_no: "CO", description: d.subject, scheduled_value: d.amount, cost_code: d.cost_code }) },
  ],
  bid_submission: [
    { to: "subcontract", label: "Award → Subcontract", back: "bid_submission",
      map: (d) => ({ vendor: d.bidder, value: d.amount }) },
  ],
  rfi: [
    { to: "change_event", label: "Change Event", back: "source_rfi",
      map: (d) => ({ subject: d.subject, cost_code: d.cost_code }) },
    { to: "pco_request", label: "PCO", back: "source_rfi",
      map: (d) => ({ subject: d.subject, description: d.question, origin: "RFI", cost_code: d.cost_code }) },
  ],
  observation: [
    { to: "ncr", label: "NCR",
      map: (d) => ({ subject: d.description, description: d.corrective_action, severity: d.severity }) },
    { to: "punchlist", label: "Punch item", back: "observation",
      map: (d) => ({ description: d.description, location: d.location, trade: d.trade }) },
  ],
  inspection: [
    { to: "deficiency", label: "Deficiency", back: "inspection",
      when: (d) => d.result === "Fail" || d.result === "Conditional",
      map: (d) => ({ description: d.subject, location: d.location, trade: d.inspection_type }) },
    { to: "ncr", label: "NCR", back: "inspection",
      when: (d) => d.result === "Fail" || d.result === "Conditional",
      map: (d) => ({ subject: d.subject, description: d.spec_section }) },
  ],
  deficiency: [
    { to: "punchlist", label: "Punch item",
      map: (d) => ({ description: d.description, location: d.location, trade: d.trade }) },
  ],
};

/**
 * The generic register renderer — list, filters, sortable table, inline edit, form, record page and
 * board, driven entirely by a module's `module.json`. No per-module code: the same views render RFIs,
 * change orders, spec sections and the other ~130 registers.
 *
 * **Why this is its own file, and its own lane.** It lived inside `PortalUI` until v0.3.850, which
 * made `portal/portal.ts` two jobs in one file: the shell (nav rail, room spine, dashboards) and this.
 * The lane table gave that file to Lane A · Shell & IA, so every register-shaped item — and they are
 * all filed in Lane B · UI & panels, because a register is a data surface — had to reach into a
 * Lane A file to do its work. Three did: `R36-EMPTY-STATE` shipped that way (v0.3.849) and missed a
 * collision only because the Lane A session happened to be elsewhere; `R24-MONO-DATA` gave up and
 * left an allowance in `ui/monoData.test.ts` recording that the file was held by someone else;
 * `R24-DENSITY` is aimed straight here and had the same collision waiting for it.
 *
 * `roadmapLanes.test.ts` asserts lanes are disjoint **by path**, so it could not see any of this: the
 * paths were disjoint and the *work* was not. A boundary that exists only in prose is not a boundary
 * (`docs/roadmap-directions.md` §4), and the only way to state this one at file granularity was to
 * make the register renderer a file. That is what this is — `portal/register/` belongs to Lane B.
 *
 * It is a class rather than free `render*(ctx)` functions (the idiom `portal/panels/*` uses) purely
 * so the move could be mechanical and behaviour-preserving: the ~90 internal `this.method()` calls
 * between these pieces are unchanged, and only the references to *shell* state became `this.ctx.*`.
 * Splitting it further by concern is `REL-4`, and stays inside this directory either way.
 */
export class RegisterUI {
  constructor(private ctx: PanelContext) {}

  // field/offline: uploads attempted while offline are persisted in IndexedDB (offlineQueue) so they
  // survive a reload, and flushed on reconnect / next launch.
  private onlineHooked = false;

  // --- record list (sortable / filterable data table + bulk actions) ---------
  /** Sort state per module. Public because the dashboard's saved-view links set it before opening
   *  the register — one of the four things the shell still reaches in here to do. */
  sort: Record<string, { col: string; dir: 1 | -1 } | undefined> = {};
  // per-module inline-edit toggle: when on, data cells become autosaving inputs (bulk data entry)
  private editInline: Record<string, boolean> = {};

  /** An inline-editable table cell that autosaves the field on change/blur (no form round-trip).
   *  Used only in inline-edit mode; reference/multiselect/other types stay read-only for now. */
  private inlineCell(pid: string, m: ModuleDef, r: ModuleRecord, c: ModuleDef["fields"][number]): HTMLTableCellElement {
    const td = document.createElement("td");
    td.onclick = (e) => e.stopPropagation();          // editing a cell must not open the record
    const save = async (v: unknown) => {
      try { await this.ctx.host.api.updateModuleRecord(pid, m.key, r.id, { [c.name]: v }); r.data[c.name] = v; td.classList.add("saved"); setTimeout(() => td.classList.remove("saved"), 700); }
      catch (e) { toast(`Couldn't save ${c.label}: ${(e as Error).message}`, "error"); }
    };
    if (c.type === "select") {
      const sel = document.createElement("select"); sel.className = "cell-input";
      const blank = document.createElement("option"); blank.value = ""; blank.textContent = "—"; sel.append(blank);
      for (const o of (c.options ?? [])) { const op = document.createElement("option"); op.value = op.textContent = o; sel.append(op); }
      sel.value = (r.data[c.name] as string) ?? "";
      sel.onchange = () => void save(sel.value);
      td.append(sel);
    } else if (c.type === "checkbox") {
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = !!r.data[c.name];
      cb.onchange = () => void save(cb.checked);
      td.append(cb);
    } else {
      const inp = document.createElement("input"); inp.className = "cell-input";
      inp.type = (c.type === "number" || c.type === "currency") ? "number" : c.type === "date" ? "date" : "text";
      inp.value = r.data[c.name] == null ? "" : String(r.data[c.name]);
      let orig = inp.value;
      inp.onblur = () => {
        if (inp.value === orig) return;
        orig = inp.value;
        const num = c.type === "number" || c.type === "currency";
        void save(inp.value === "" ? "" : num ? Number(inp.value) : inp.value);
      };
      inp.onkeydown = (e) => { if (e.key === "Enter") inp.blur(); };
      td.append(inp);
    }
    return td;
  }

  /** Inline reference picker for edit mode — set/change which record a reference field points at,
   *  straight in the grid. Options come from the reference column's pre-fetched map (no extra fetch);
   *  each reads as "ref · title". Saves the linked record's id; a current value outside the fetched
   *  window (>500) is preserved as its own option so toggling edit mode never drops a link. */
  private inlineRefCell(pid: string, m: ModuleDef, r: ModuleRecord, c: ModuleDef["fields"][number],
                        map: Map<string, { ref: string; title: string | null }> | undefined): HTMLTableCellElement {
    const td = document.createElement("td");
    td.onclick = (e) => e.stopPropagation();
    const sel = document.createElement("select"); sel.className = "cell-input";
    const blank = document.createElement("option"); blank.value = ""; blank.textContent = "—"; sel.append(blank);
    const entries = map ? [...map.entries()].sort((a, b) => a[1].ref.localeCompare(b[1].ref)) : [];
    for (const [id, info] of entries) {
      const op = document.createElement("option"); op.value = id;
      op.textContent = info.title ? `${info.ref} · ${info.title}` : info.ref;
      sel.append(op);
    }
    const cur = r.data[c.name] == null ? "" : String(r.data[c.name]);
    if (cur && !map?.has(cur)) { const op = document.createElement("option"); op.value = cur; op.textContent = cur.slice(0, 8); sel.append(op); }
    sel.value = cur;
    sel.onchange = async () => {
      try { await this.ctx.host.api.updateModuleRecord(pid, m.key, r.id, { [c.name]: sel.value }); r.data[c.name] = sel.value; td.classList.add("saved"); setTimeout(() => td.classList.remove("saved"), 700); }
      catch (e) { toast(`Couldn't link ${c.label}: ${(e as Error).message}`, "error"); }
    };
    td.append(sel);
    return td;
  }

  /** Immediate loading placeholder so a click gives feedback before the fetch returns. */
  private skeleton(label: string) {
    this.ctx.root.innerHTML = `<div class="section-title">${esc(label)}</div>`
      + `<div>${'<div class="skel-row"></div>'.repeat(6)}</div>`;
  }
  async openModule(m: ModuleDef, filter: RegisterFilter = {}) {
    const pid = this.ctx.host.projectId()!;
    pushRecent(m.key);
    this.skeleton(`Loading ${m.name}…`);
    const PAGE = 100, offset = filter.offset ?? 0;          // page large modules so they never render 1000s of rows
    // MOD-FILTER — per-field filters and the sort go to the SERVER, so both apply to the whole
    // register rather than to the hundred rows that happen to be on this page.
    const sortState = this.sort[m.key];
    const sortField = sortState ? this.serverSortField(m, sortState.col) : null;
    // A range puts TWO clauses on one field (`amount.gte` and `amount.lte`). The controls key
    // themselves `<field>__<op>` so both can coexist in the state map; the suffix is stripped here,
    // into a LIST, which is the shape that can actually carry both. Flattening to a field-keyed map
    // instead would drop one clause and turn a range into a single bound — a narrower result that
    // looks entirely correct on screen.
    const wireFilters = Object.entries(filter.fields ?? {}).map(([k, v]) => ({
      field: k.includes("__") ? k.slice(0, k.lastIndexOf("__")) : k, op: v.op, value: v.value,
    }));
    // R36-EMPTY-STATE — this was the ONE unguarded `await` in the method. Its two neighbours
    // (`listViews`, `templates`) both `.catch`; this one let a rejection escape through the
    // `void this.openModule(...)` call sites, so a 500 or a dropped connection left the "Loading …"
    // skeleton on screen permanently. A dead screen and an empty register then looked identical,
    // which is exactly the confusion this item is named for — so the failure gets its own state.
    let page: ModuleRecord[];
    try {
      page = await this.ctx.host.api.moduleRecordsFiltered(pid, m.key, {
        q: filter.q, state: filter.state, limit: PAGE + 1, offset,
        filters: wireFilters,
        ...(sortField ? { sort: sortField, sortDir: sortState!.dir === -1 ? "desc" : "asc" } : {}),
      });
    } catch (e) {
      // The bar stays so the reader can leave; the toolbar does NOT — a full set of controls around
      // a register that was never fetched is the "complete surface wrapped around nothing" defect.
      this.ctx.root.innerHTML = "";
      this.ctx.root.appendChild(this.ctx.bar(m.name, () => this.ctx.renderHome()));
      this.ctx.root.appendChild(registerEmptyEl(
        { kind: "failed", name: m.name, reason: (e as Error).message },
        () => void this.openModule(m, filter),
      ));
      return;
    }
    const hasMore = page.length > PAGE;
    const records = hasMore ? page.slice(0, PAGE) : page;
    const editing = !!this.editInline[m.key];              // inline-edit mode: data cells become inputs
    this.ctx.root.innerHTML = "";
    this.ctx.root.appendChild(this.ctx.bar(m.name, () => this.ctx.renderHome()));

    const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;margin:6px 0;flex-wrap:wrap;align-items:center";
    const newBtn = document.createElement("button"); newBtn.className = "tool-btn"; newBtn.dataset.cap = "review"; newBtn.textContent = "+ New";
    newBtn.onclick = () => this.renderForm(m);
    const boardBtn = document.createElement("button"); boardBtn.className = "tool-btn"; boardBtn.textContent = "▦ Board";
    boardBtn.onclick = () => this.renderBoard(m);
    const csvBtn = document.createElement("button"); csvBtn.className = "tool-btn"; csvBtn.textContent = "↓ CSV";
    csvBtn.onclick = () => window.open(this.ctx.host.api.url(`/projects/${pid}/modules/${m.key}/export.csv`), "_blank");
    // filter box + state dropdown
    const fbox = document.createElement("input"); fbox.type = "search"; fbox.placeholder = "filter…";
    fbox.value = filter.q ?? ""; fbox.className = "portal-filter";
    fbox.onkeydown = (e) => { if (e.key === "Enter") void this.openModule(m, { ...filter, q: fbox.value || undefined }); };
    const stateSel = document.createElement("select"); stateSel.className = "sb-sel";
    const anyOpt = document.createElement("option"); anyOpt.value = ""; anyOpt.textContent = "any state"; stateSel.appendChild(anyOpt);
    for (const s of m.workflow.states ?? []) { const o = document.createElement("option"); o.value = o.textContent = s; stateSel.appendChild(o); }
    stateSel.value = filter.state ?? "";
    stateSel.onchange = () => this.openModule(m, { ...filter, state: stateSel.value || undefined });
    // saved views (server-side, per user+module; falls back to empty if offline)
    const views = await this.ctx.host.api.listViews(pid, m.key).catch(() => []);
    const viewSel = document.createElement("select"); viewSel.className = "sb-sel"; viewSel.title = "Saved views";
    const vNone = document.createElement("option"); vNone.value = ""; vNone.textContent = "views…"; viewSel.appendChild(vNone);
    for (const v of views) { const o = document.createElement("option"); o.value = v.id; o.textContent = v.name; viewSel.appendChild(o); }
    viewSel.onchange = () => { const v = views.find((x) => x.id === viewSel.value); if (v) { this.sort[m.key] = v.config.sort; void this.ctx.host.api.markViewSeen(pid, m.key, v.id).catch(() => {}); void this.openModule(m, { q: v.config.q, state: v.config.state }); } };
    const saveView = document.createElement("button"); saveView.className = "tool-btn"; saveView.textContent = "＋view";
    saveView.title = "Save current filter/sort as a view (synced to your account)";
    saveView.onclick = async () => {
      const v = await promptModal("Save view", [{ name: "name", label: "View name", required: true }], "Save");
      if (!v) return;
      await this.ctx.host.api.saveView(pid, m.key, v.name ?? "", { q: filter.q, state: filter.state, sort: this.sort[m.key] });
      void this.openModule(m, filter);
    };
    // R41-REACH-WRITES — retire a saved view. Views could be created and applied since they shipped
    // and never removed, so a mistyped one stayed in the dropdown of whoever made it forever.
    //
    // WHY A PICK-THEN-CONFIRM AND NOT AN ✕ ON THE SELECT. `viewSel.onchange` applies the view and
    // re-renders this whole toolbar, so the select never HOLDS a selection — a "delete the selected
    // one" button would have nothing to read. The number-pick matches the Templates control beside
    // it, and the confirm step is what turns a number back into a name: agreeing to delete "3" is
    // not consent, agreeing to delete "Overdue — mine" is.
    //
    // AND IT READS THE `deleted` FLAG RATHER THAN ASSUMING. This is the endpoint that returned
    // "deleted": true for a row it had not touched until v0.3.892; the reason it is safe to wire now
    // is that the flag became true only when the delete happened, and a UI that ignored it would put
    // that defect straight back on the screen.
    const delView = document.createElement("button"); delView.className = "tool-btn";
    delView.textContent = "🗑 view"; delView.dataset.cap = "editor";
    delView.title = views.length ? "Delete one of your saved views" : "No saved views to delete";
    delView.disabled = !views.length;
    delView.onclick = async () => {
      const picked = await promptModal("Delete a saved view",
        [{ name: "pick", label: "View # to delete", required: true }], "Next",
        views.map((v, i) => `${i + 1}. ${v.name}`).join("\n"));
      if (!picked) return;
      // `parseInt` returns NaN for "abc" and 3 for "3abc"; both must be refused rather than
      // silently deleting the third view because the string happened to start with a digit.
      const n = Number((picked.pick ?? "").trim());
      const target = Number.isInteger(n) ? views[n - 1] : undefined;
      if (!target) { toast(`No view numbered "${picked.pick}" — nothing deleted.`, "error"); return; }
      const ok = await confirmModal(`Delete the view "${target.name}"?`,
        "Saved views are yours alone, so this removes it only for you. The records it filters are "
        + "not touched.\n\nThere is no undo — the filter and sort would have to be set up again.",
        "Delete view", true);
      if (!ok) return;
      let res: { deleted: boolean };
      try {
        res = await this.ctx.host.api.deleteView(pid, m.key, target.id);
      } catch (e) { toast(`Not deleted: ${(e as Error).message}`, "error"); return; }
      // A false here is not an error — the row was already gone, which is what a second tab or an
      // earlier click leaves behind. Saying "deleted" anyway is how a stale dropdown starts looking
      // like a server that lost the write.
      if (!res.deleted) toast(`"${target.name}" was already gone — refreshing the list.`, "info");
      else toast(`Deleted view "${target.name}"`, "success");
      void this.openModule(m, filter);
    };
    // reusable templates: apply a saved set of records, or save the current ones as a template
    const tplBtn = document.createElement("button"); tplBtn.className = "tool-btn"; tplBtn.dataset.cap = "review"; tplBtn.textContent = "⌹ Templates";
    tplBtn.title = "Apply or save a reusable template for this module";
    tplBtn.onclick = async () => {
      const tpls = await this.ctx.host.api.templates(m.key).catch(() => []);
      let pick = "";
      if (tpls.length) {
        const v = await promptModal(`${m.name} templates`,
          [{ name: "pick", label: "Template # to apply (blank = save current as new)" }], "Apply",
          tpls.map((t, i) => `${i + 1}. ${t.name} (${t.item_count})`).join("\n"));
        if (!v) return;
        pick = v.pick ?? "";
      } else {
        toast(`No ${m.name} templates yet — saving the current records as one.`, "info");
      }
      if (pick && pick.trim()) {
        const t = tpls[parseInt(pick) - 1];
        if (!t) return;
        const r = await this.ctx.host.api.applyTemplate(pid, m.key, t.id);
        this.ctx.host.setStatus(`applied "${r.applied}" — ${r.created} record(s)`);
        void this.openModule(m, filter);
      } else {
        const nv = await promptModal("Save template",
          [{ name: "name", label: "Template name", required: true }], "Save");
        if (!nv) return;
        try { const s = await this.ctx.host.api.saveTemplate(pid, m.key, nv.name ?? ""); this.ctx.host.setStatus(`saved template (${s.item_count} items)`); }
        catch (e) { this.ctx.host.setStatus(`couldn't save: ${(e as Error).message}`); }
      }
    };
    // generic Excel/CSV import (any module): pick a file -> map columns -> preview -> import
    const impBtn = document.createElement("button"); impBtn.className = "tool-btn"; impBtn.dataset.cap = "review";
    impBtn.textContent = "⤓ Import"; impBtn.title = "Import records from an Excel (.xlsx) or CSV file with column mapping";
    const impFile = document.createElement("input"); impFile.type = "file"; impFile.accept = ".xlsx,.xlsm,.csv"; impFile.style.display = "none";
    impFile.onchange = () => { const f = impFile.files?.[0]; if (f) void this.renderImport(m, f); impFile.value = ""; };
    impBtn.onclick = () => impFile.click();
    // paste-from-spreadsheet — Ctrl-V a block of Excel/Sheets cells to bulk-add without a file
    const pasteBtn = document.createElement("button"); pasteBtn.className = "tool-btn"; pasteBtn.dataset.cap = "review";
    pasteBtn.textContent = "⎘ Paste"; pasteBtn.title = "Paste rows copied from Excel or Google Sheets to bulk-add records";
    pasteBtn.onclick = () => this.pasteRows(m);
    // inline-edit toggle — turn the data cells into autosaving inputs for fast multi-record entry
    const editBtn = document.createElement("button"); editBtn.className = "tool-btn"; editBtn.dataset.cap = "editor";
    editBtn.textContent = editing ? "✓ Editing (done)" : "✎ Edit inline";
    if (editing) editBtn.classList.add("on");
    editBtn.title = "Edit cells directly in the table — type across many records; changes save automatically";
    editBtn.onclick = () => { this.editInline[m.key] = !editing; void this.openModule(m, filter); };
    // column chooser — pick which fields show as columns in wide modules (personal, persisted)
    const colBtn = document.createElement("button"); colBtn.className = "tool-btn";
    colBtn.textContent = "⚙ Columns"; colBtn.title = "Choose which fields show as columns";
    if (this.readColPrefs(m.key)) colBtn.classList.add("on");   // signal a non-default column set is active
    colBtn.onclick = () => this.columnPicker(m, colNames, filter);
    actions.append(newBtn, boardBtn, csvBtn, impBtn, impFile, pasteBtn, editBtn, tplBtn, colBtn, fbox, stateSel, viewSel, saveView, delView);
    // R30-TOOLS — the tools this register declares, rendered from `module.json` rather than hardcoded.
    //
    // The audit's finding was that every optional key a module could carry was presentation — icon,
    // columns, pinnable — and none said what the register could *do*. So a register rendered as a
    // table, a form and a status chip, which is exactly a paper form, while `bid_leveling.py`,
    // `schedule_cpm.py` and `fca.py` sat one unlinked screen away. `tools[]` is that link, and the
    // hardcoded `schedule_activity` "Views" button that used to live here is the reason it is
    // declarative now: one register got a door because someone remembered to write the branch.
    //
    // An unknown dest renders nothing rather than a dead button — `navigate` no-ops on a key it does
    // not know, and a button that silently does nothing is worse than an absent one.
    //
    // This used to hoist `destDispatch()` out of the loop ("built once, not once per declared tool")
    // and now asks the shell per tool instead, because the dispatch map is the shell's and the seam
    // hands over the question rather than the map. Stated rather than quietly dropped: it is a
    // ~50-entry object literal built once per *tool* on a register that declares any, against a
    // shell that already rebuilds it on every `buildNav()` and every navigation. If that ever shows
    // up in a measurement, cache it in `PortalUI` — do not widen this seam to pass the map through.
    for (const t of m.tools ?? []) {
      if ((t.scope ?? "register") !== "register") continue;   // record-scoped tools render on the record
      if (!this.ctx.hasDest(t.dest)) continue;
      const tb = document.createElement("button"); tb.className = "tool-btn"; tb.dataset.dest = t.dest;
      tb.textContent = `⚙ ${t.label}`;
      tb.title = `Open ${t.label} — the tool that works on these ${m.name.toLowerCase()}`;
      tb.onclick = () => this.ctx.navigate(t.dest);
      actions.append(tb);
    }
    // coordination issues round-trip via BCF with other BIM tools (Solibri/ACC/BIMcollab)
    if (m.key === "coordination_issue") {
      const exp = document.createElement("button"); exp.className = "tool-btn"; exp.textContent = "⬇ BCF";
      exp.title = "Export these coordination issues as a BCF .bcfzip";
      exp.onclick = async () => {
        try {
          const blob = await this.ctx.host.api.downloadModuleBcf(pid, m.key);
          const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
          a.download = "coordination_issues.bcfzip"; a.click(); URL.revokeObjectURL(a.href);
          this.ctx.host.setStatus("exported BCF");
        } catch (e) { this.ctx.host.setStatus(`BCF export failed: ${(e as Error).message}`); }
      };
      const impInput = document.createElement("input"); impInput.type = "file"; impInput.accept = ".bcfzip,.bcf,application/zip";
      impInput.style.display = "none";
      impInput.onchange = async () => {
        const f = impInput.files?.[0]; if (!f) return;
        try { const r = await this.ctx.host.api.importModuleBcf(pid, m.key, f);
          this.ctx.host.setStatus(`imported ${r.count} BCF issue${r.count === 1 ? "" : "s"}`); void this.openModule(m); }
        catch (e) { this.ctx.host.setStatus(`BCF import failed: ${(e as Error).message}`); }
      };
      const imp = document.createElement("button"); imp.className = "tool-btn"; imp.dataset.cap = "review";
      imp.textContent = "⬆ Import BCF"; imp.title = "Import a BCF .bcfzip from another BIM tool";
      imp.onclick = () => impInput.click();
      actions.append(exp, imp, impInput);
    }
    // permits seed from municipal open data (NYC/SF/Chicago/LA/Austin… interchangeable cities)
    if (m.key === "permit") {
      const imp = document.createElement("button"); imp.className = "tool-btn"; imp.dataset.cap = "review";
      imp.textContent = "🏛 Import from city open data";
      imp.title = "Pull issued/filed permits for the site from a city's open data and add them to this log";
      imp.onclick = () => void this.openPermitImport(m);
      actions.append(imp);
    }
    this.ctx.root.appendChild(actions);
    this.ctx.root.appendChild(this.filterRow(m, filter));

    if (!records.length) {
      // R24-EMPTY-GUIDE ② — an empty register says where its rows come from. "Use + New" restates a
      // button three inches away; what the user cannot see is that an RFI is asked against a drawing
      // and a submittal is driven by a spec section. Curated per module, generic where it is not —
      // an invented upstream would be a confident wrong answer somewhere nobody can check it.
      //
      // R36-EMPTY-STATE — but only if nothing is being HIDDEN. The old test was `filter.q ||
      // filter.state`, which is the two-control half of the filter vocabulary; `filter.fields` — the
      // ⧧ Filter panel, and the one most likely to be narrowing a register to nothing — was invisible
      // here, so a filtered-out register claimed nothing had ever been created and then offered
      // curated advice about where those records come from. Counting all three clauses is the fix,
      // and the count is worth having: "3 filters are narrowing this" is a different sentence from
      // "a filter is".
      const narrowing = Object.keys(filter.fields ?? {}).length + (filter.q ? 1 : 0) + (filter.state ? 1 : 0);
      const kind: RegisterEmptyKind = narrowing ? "filtered" : "none";
      this.ctx.root.appendChild(registerEmptyEl(
        { kind, name: m.name, hint: emptyHint(m.key), filterCount: narrowing },
        // Clearing drops q, state and fields together — a "clear filters" that left one clause behind
        // would land the reader back on this same screen with no way to tell it had done anything.
        kind === "filtered" ? () => void this.openModule(m, { offset: 0 }) : () => this.renderForm(m),
      ));
      return;
    }

    // columns: a saved per-user choice (⚙ Columns) wins; else module.json list_columns, else first 2
    // input fields. Ref/Title/Assignee/Ball/Status always frame the row regardless.
    const inputFields = m.fields.filter((f) => f.type !== "rollup" && f.type !== "signature");
    const defaultColNames = (m.list_columns ?? inputFields.slice(0, 2).map((f) => f.name));
    const colNames = this.readColPrefs(m.key) ?? defaultColNames;
    // O(1) field lookup by name (was O(colNames × fields) via .find per column) — REL-4 hotspot fix
    const fieldByName = new Map(m.fields.map((f) => [f.name, f]));
    const cols = colNames
      .map((name) => fieldByName.get(name)).filter(Boolean) as ModuleDef["fields"];

    // sort
    const sort = this.sort[m.key];
    const val = (r: ModuleRecord, col: string) => col === "ref" ? r.ref : col === "status" ? r.workflow_state
      : col === "assignee" ? (r.assignee ?? "") : col === "title" ? (r.title ?? "") : (r.data[col] ?? "");
    // Type-aware comparator: numeric fields compare as numbers ("10" after "9", not before), blanks
    // group at the end regardless of direction. `5 < ""` and `5 > ""` are both false, so the old raw
    // </>` compare scattered blank-valued rows randomly through a numeric sort.
    const cmp = (x: unknown, y: unknown): number => {
      const xe = x === "" || x == null, ye = y === "" || y == null;
      if (xe || ye) return xe && ye ? 0 : xe ? 1 : -1;             // blanks last (direction-independent)
      const xn = Number(x), yn = Number(y);
      if (Number.isFinite(xn) && Number.isFinite(yn)) return xn - yn;
      return String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: "base" });
    };
    // MOD-FILTER — the server sorted the whole register, so re-sorting here would be a no-op at best.
    //
    // This comparator is correct and stays, but only for a column the server cannot order (see
    // `serverSortField`). The distinction matters: sorting in the browser orders **the fetched page**,
    // so "sort by amount" on a 500-row register ordered 200 rows and presented the top of that as the
    // largest values in the register. Nothing was wrong on screen; it was the wrong 200 rows.
    if (sort && !this.serverSortField(m, sort.col)) records.sort((a, b) => {
      const x = val(a, sort.col), y = val(b, sort.col);
      const xe = x === "" || x == null, ye = y === "" || y == null;
      if (xe || ye) return xe && ye ? 0 : xe ? 1 : -1;             // blanks stay last even when descending
      return cmp(x, y) * sort.dir;
    });

    // bulk action bar
    const selected = new Set<string>();
    const bulkBar = document.createElement("div"); bulkBar.className = "bulk-bar"; bulkBar.hidden = true;
    const bulkCount = document.createElement("span"); bulkCount.className = "meta";
    const syncBulk = () => { bulkBar.hidden = selected.size === 0; bulkCount.textContent = `${selected.size} selected`; };
    // apply a bulk action to the selection, then toast + reload (no more raw prompt() pickers)
    const runBulk = async (action: "assign" | "transition" | "delete", verb: string, value?: string) => {
      const n = selected.size; if (!n) return;
      try {
        await this.ctx.host.api.bulkAction(pid, m.key, [...selected], action, value);
        toast(`${verb} ${n} ${m.name.toLowerCase()} record${n === 1 ? "" : "s"}`, "info");
        void this.openModule(m, filter);
      } catch (e) { this.ctx.host.setStatus(`bulk action failed: ${(e as Error).message}`); }
    };
    bulkBar.append(bulkCount);
    // Transition: a dropdown of valid workflow actions + Apply
    const txActions = [...new Set((m.workflow.transitions ?? []).map((t) => t.action))];
    if (txActions.length) {
      const txSel = document.createElement("select"); txSel.className = "sb-sel";
      const d = document.createElement("option"); d.value = ""; d.textContent = "Transition…"; txSel.appendChild(d);
      for (const a of txActions) { const o = document.createElement("option"); o.value = o.textContent = a; txSel.appendChild(o); }
      const txBtn = document.createElement("button"); txBtn.className = "tool-btn"; txBtn.textContent = "Apply";
      txBtn.onclick = () => { if (txSel.value) void runBulk("transition", "Transitioned", txSel.value); };
      bulkBar.append(txSel, txBtn);
    }
    // Assign: an input + Assign
    const asgIn = document.createElement("input"); asgIn.type = "text"; asgIn.placeholder = "assign to…"; asgIn.className = "portal-filter"; asgIn.style.maxWidth = "140px";
    const asgBtn = document.createElement("button"); asgBtn.className = "tool-btn"; asgBtn.textContent = "Assign";
    asgBtn.onclick = () => void runBulk("assign", "Assigned", asgIn.value.trim());
    // Delete (kept behind a confirm)
    const delBtn = document.createElement("button"); delBtn.className = "tool-btn"; delBtn.textContent = "Delete";
    delBtn.onclick = async () => { if (await confirmModal(`Delete ${selected.size} record(s)? This cannot be undone.`, "", "Delete", true)) void runBulk("delete", "Deleted"); };
    bulkBar.append(asgIn, asgBtn, delBtn);
    this.ctx.root.appendChild(bulkBar);

    const rowCbs: HTMLInputElement[] = [];
    const table = document.createElement("table"); table.className = "portal-table";
    const headRow = document.createElement("tr");
    const selAllTh = document.createElement("th");      // select-all (builders act in batches)
    const selAll = document.createElement("input"); selAll.type = "checkbox"; selAll.title = "Select all";
    selAll.onclick = (e) => {
      e.stopPropagation();
      for (const r of records) { if (selAll.checked) selected.add(r.id); else selected.delete(r.id); }
      for (const cb of rowCbs) cb.checked = selAll.checked;
      syncBulk();
    };
    selAllTh.appendChild(selAll); headRow.appendChild(selAllTh);
    const th = (label: string, col: string) => {
      const h = document.createElement("th"); h.textContent = label + (sort?.col === col ? (sort.dir === 1 ? " ▲" : " ▼") : "");
      h.style.cursor = "pointer";
      h.onclick = () => { const cur = this.sort[m.key]; this.sort[m.key] = { col, dir: cur?.col === col && cur.dir === 1 ? -1 : 1 }; void this.openModule(m, filter); };
      headRow.appendChild(h);
    };
    th("Ref", "ref"); th("Title", "title");
    for (const c of cols) th(c.label, c.name);
    th("Assignee", "assignee"); th("Ball", ""); th("Status", "status");
    const thead = document.createElement("thead"); thead.appendChild(headRow); table.appendChild(thead);

    // Relational cells: resolve each reference column's ids → {ref,title} once (one fetch per
    // referenced module, not per cell), so a reference reads as the linked record and navigates on
    // click instead of showing a raw id.
    //
    // The fetch is BOUNDED, and that bound is the reason `refCell` exists rather than an inline
    // fallback: past 500 records of the target module the tail is simply not in the map, and the old
    // code rendered any unresolved value as a link labelled `String(v).slice(0, 8)`. On a project with
    // 600 companies, company #550 therefore drew a clickable link showing eight characters of its own
    // id, opening nothing — a control that looks resolved and is not. See `refCell`.
    const refCols = cols.filter((c) => c.type === "reference" && c.module);
    const refMaps: Record<string, Map<string, { ref: string; title: string | null }>> = {};
    if (refCols.length) {
      await Promise.all(refCols.map(async (c) => {
        try {
          const recs = await this.ctx.host.api.moduleRecordsFiltered(pid, c.module!, { limit: REF_RESOLVE_LIMIT });
          const map = new Map<string, { ref: string; title: string | null }>();
          for (const rr of recs) map.set(rr.id, { ref: rr.ref, title: rr.title });
          refMaps[c.name] = map;
        } catch { /* leave unresolved — refCell states so rather than faking a link */ }
      }));
    }

    const tb = document.createElement("tbody");
    for (const r of records) {
      const tr = document.createElement("tr");
      const cbTd = document.createElement("td");
      const cb = document.createElement("input"); cb.type = "checkbox"; rowCbs.push(cb);
      cb.onclick = (e) => { e.stopPropagation(); if (cb.checked) selected.add(r.id); else selected.delete(r.id); selAll.checked = selected.size === records.length; syncBulk(); };
      cbTd.appendChild(cb); cbTd.onclick = (e) => e.stopPropagation(); tr.appendChild(cbTd);
      // textContent, not innerHTML: titles/field values are user data (stored-XSS guard)
      const cell = (text: string) => { const td = document.createElement("td"); td.textContent = text; tr.appendChild(td); };
      cell(r.ref); cell(r.title ?? "");
      // MOD-PERCENT: `percent` was absent from this list, so the 21 fields the sweep converted from
      // `number` stopped being inline-editable overnight — a capability removed with no error to
      // notice. Now module-scope and exported, so `fieldTypeCoverage.test.ts` can hold it against the
      // types the shipped modules actually declare.
      const EDITABLE = EDITABLE_FIELD_TYPES as readonly string[];
      for (const c of cols) {
        const v = r.data[c.name];
        if (editing && c.type === "reference" && c.module) {
          tr.appendChild(this.inlineRefCell(pid, m, r, c, refMaps[c.name]));
        } else if (editing && EDITABLE.includes(c.type)) {
          tr.appendChild(this.inlineCell(pid, m, r, c));
        } else if (c.type === "reference" && c.module && v) {
          tr.appendChild(this.refCell(String(v), c, refMaps[c.name]));
        } else {
          cell(this.fmtCell(c, v));
        }
      }
      tr.appendChild(this.assigneeCell(pid, m, r));   // inline-editable
      tr.appendChild(this.ballCell(m, r));            // ball-in-court party (who owes the next move)
      tr.appendChild(this.statusCell(pid, m, r));     // inline workflow transition
      tr.onclick = () => this.openRecord(m, r.id);
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    this.ctx.root.appendChild(table);

    // pager — only shown when the list spills past one page (keeps large modules snappy)
    if (offset > 0 || hasMore) {
      const pager = document.createElement("div");
      pager.style.cssText = "display:flex;gap:8px;align-items:center;margin:8px 0";
      const prev = document.createElement("button"); prev.className = "tool-btn"; prev.textContent = "‹ Prev";
      prev.disabled = offset === 0;
      prev.onclick = () => this.openModule(m, { ...filter, offset: Math.max(0, offset - PAGE) });
      const next = document.createElement("button"); next.className = "tool-btn"; next.textContent = "Next ›";
      next.disabled = !hasMore;
      next.onclick = () => this.openModule(m, { ...filter, offset: offset + PAGE });
      const lbl = document.createElement("span"); lbl.className = "meta";
      lbl.textContent = `${offset + 1}–${offset + records.length}${hasMore ? "+" : ""}`;
      pager.append(prev, lbl, next); this.ctx.root.appendChild(pager);
    }
  }

  /** Ball-in-court: which party(ies) own the next action from the current state, read straight from
   *  the workflow transitions. The "who owes the next move" signal both supers and PMs scan for. */
  private ballInCourt(m: ModuleDef, state: string): string[] {
    const parties = new Set<string>();
    for (const t of m.workflow?.transitions ?? []) {
      if (t.from === state) (t.party ?? []).forEach((p) => p && parties.add(p));
    }
    return [...parties];
  }
  private ballCell(m: ModuleDef, r: ModuleRecord): HTMLTableCellElement {
    const td = document.createElement("td");
    const parties = this.ballInCourt(m, r.workflow_state);
    td.innerHTML = parties.length
      ? parties.map((p) => `<span class="ball-badge">${p}</span>`).join(" ")
      : `<span class="meta">—</span>`;
    return td;
  }

  /** C1 — create a pre-filled, linked record in another module (e.g. RFI → Change Event). */
  private async convert(m: ModuleDef, r: ModuleRecord, c: Conversion) {
    const pid = this.ctx.host.projectId()!;
    const tgt = this.ctx.mods.find((x) => x.key === c.to);
    if (!tgt) return;
    if (!(await confirmModal(`Create a ${tgt.name} from ${r.ref}? It will be pre-filled and linked back to ${r.ref}.`, ""))) return;
    try {
      const data = c.map(r.data);
      if (c.back) data[c.back] = r.id;                 // back-reference field on the new record → this record
      for (const k of Object.keys(data)) if (data[k] === undefined || data[k] === "") delete data[k];
      const nv = await this.ctx.host.api.createModuleRecord(pid, c.to, { data });
      if (!c.back) await this.ctx.host.api.linkRecord(pid, m.key, r.id, c.to, nv.id);  // else use an explicit link
      toast(`Created ${nv.ref} from ${r.ref}`, "info");
      this.ctx.host.onPinsChanged();
      void this.openRecord(tgt, nv.id);
    } catch (e) { toast(`convert failed: ${(e as Error).message}`, "error"); }
  }

  /**
   * MOD-SWEEP — a reference cell that never pretends to have resolved.
   *
   * The old inline version rendered EVERY non-empty reference as a clickable link labelled
   * `String(v).slice(0, 8)`, falling back to those eight characters whenever the id was not in the
   * resolved map. Three different values took that path and all three looked identical to a working
   * link: a record deleted since it was referenced, a record past `REF_RESOLVE_LIMIT` in a large
   * register, and — the one that matters for the field sweep — a **legacy free-text value** in a field
   * that used to be `text`. Converting `coi.vendor` from text to reference would have turned
   * "Acme Electrical Inc" into a link reading `Acme Ele` that opens nothing.
   *
   * So the three cases are now distinguished, because they call for different things from the user:
   *
   * - **resolved** → the link, labelled `REF-001 · Title`, navigating on click.
   * - **an id we could not resolve** (UUID-shaped, absent from the map) → the short id, NOT a link,
   *   marked as unresolved. The record may be deleted or beyond the fetch bound; either way clicking
   *   is not the answer and offering it is a lie.
   * - **not an id at all** → the value verbatim, full length, marked as unlinked text. This is what a
   *   pre-conversion value looks like, and showing it whole is what lets someone re-link it by hand.
   *
   * Truncating to 8 characters was the specific harm in every case: it is short enough to look like an
   * id and long enough to look deliberate.
   */
  private refCell(
    v: string,
    c: ModuleDef["fields"][number],
    map: Map<string, { ref: string; title: string | null }> | undefined,
  ): HTMLElement {
    const td = document.createElement("td");
    const info = map?.get(v);
    const target = String(c.module ?? "record").replace(/_/g, " ");
    if (info) {
      const a = document.createElement("a"); a.href = "#"; a.className = "ref-link";
      a.textContent = info.title ? `${info.ref} · ${info.title}` : info.ref;
      a.title = `Open linked ${target} ${info.ref}`;
      a.onclick = (e) => { e.preventDefault(); e.stopPropagation(); this.openByBrief(c.module!, v); };
      td.appendChild(a);
      return td;
    }
    const span = document.createElement("span");
    if (UUID_RE.test(v)) {
      span.className = "ref-unresolved";
      span.textContent = `${v.slice(0, 8)}…`;
      span.title = `This ${target} could not be resolved — it may have been deleted, or lie beyond `
        + `the first ${REF_RESOLVE_LIMIT} records of ${target}. Not a working link.`;
    } else {
      span.className = "ref-unlinked";
      span.textContent = v;                        // in full: it is the only handle for re-linking
      span.title = `Plain text, not a link to a ${target} record. Edit the field to pick the `
        + `${target} it refers to.`;
    }
    td.appendChild(span);
    return td;
  }

  /**
   * MOD-FILTER — the per-field filter bar.
   *
   * One control per field, chosen by type, because the useful question differs by type and offering a
   * single text box for all of them is how you end up with a filter nobody uses:
   *
   * - **select / multiselect** → a dropdown of the declared options. The only exact-match control that
   *   cannot be mistyped, and the options are already in the schema.
   * - **date** → from / to, i.e. `gte` + `lte`. A single date is almost never the question; a range is.
   * - **number / currency / percent** → min / max, compared numerically by the server.
   * - **reference** → a dropdown of the target register's records, so you filter by the record rather
   *   than by remembering its id.
   * - **everything else** → `contains`, case-insensitive.
   *
   * Collapsed by default and summarised when active ("3 filters"), so a register does not open behind
   * a wall of controls, and an active filter can never be invisible — a page showing a subset while
   * looking unfiltered is indistinguishable from missing data.
   */
  private filterRow(m: ModuleDef, filter: RegisterFilter): HTMLElement {
    const active = filter.fields ?? {};
    const wrap = document.createElement("div"); wrap.className = "filter-row";
    const count = Object.keys(active).length;

    const toggle = document.createElement("button");
    toggle.className = "tool-btn" + (count ? " on" : "");
    toggle.textContent = count ? `⧧ ${count} filter${count === 1 ? "" : "s"}` : "⧧ Filter";
    toggle.title = "Filter this register by any field — applied by the server, so it narrows every "
      + "record, not just the page on screen";
    const body = document.createElement("div"); body.className = "filter-body";
    body.hidden = count === 0;                       // open when something is already filtered
    toggle.onclick = () => { body.hidden = !body.hidden; };
    wrap.append(toggle, body);

    const next: Record<string, { op: ModuleFilterOp; value: string }> = { ...active };
    const apply = () => {
      for (const k of Object.keys(next)) {
        const v = next[k]!;
        if (v.op !== "empty" && v.op !== "nonempty" && !v.value) delete next[k];
      }
      void this.openModule(m, { ...filter, offset: 0, fields: { ...next } });
    };
    const label = (f: ModuleDef["fields"][number], node: HTMLElement, suffix = "") => {
      const cell = document.createElement("label"); cell.className = "filter-cell";
      const t = document.createElement("span"); t.className = "meta";
      t.textContent = (f.label || f.name) + suffix;
      cell.append(t, node); body.appendChild(cell);
    };
    const setOn = (name: string, op: ModuleFilterOp, value: string) => {
      if (value) next[name] = { op, value }; else delete next[name];
      apply();
    };

    for (const f of this.filterableFields(m)) {
      if (f.type === "select" || f.type === "multiselect") {
        const s = document.createElement("select"); s.className = "sb-sel";
        const any = document.createElement("option"); any.value = ""; any.textContent = "any";
        s.appendChild(any);
        for (const o of f.options ?? []) {
          const opt = document.createElement("option"); opt.value = opt.textContent = o; s.appendChild(opt);
        }
        s.value = active[f.name]?.value ?? "";
        s.onchange = () => setOn(f.name, "eq", s.value);
        label(f, s);
      } else if (f.type === "date") {
        for (const [op, suffix] of [["gte", " from"], ["lte", " to"]] as const) {
          const i = document.createElement("input"); i.type = "date"; i.className = "portal-filter";
          const key = `${f.name}__${op}`;
          i.value = active[key]?.value ?? "";
          // A range needs two independent clauses on ONE field, so the second cannot overwrite the
          // first in a field-keyed map. The `__op` suffix keys them apart here and is stripped when
          // the request is built, which is why `fields` is keyed by control rather than by field.
          i.onchange = () => { if (i.value) next[key] = { op, value: i.value }; else delete next[key]; apply(); };
          label(f, i, suffix);
        }
      } else if (f.type === "number" || f.type === "currency" || f.type === "percent") {
        for (const [op, suffix] of [["gte", " min"], ["lte", " max"]] as const) {
          const i = document.createElement("input"); i.type = "number"; i.className = "portal-filter";
          const key = `${f.name}__${op}`;
          i.value = active[key]?.value ?? "";
          i.onchange = () => { if (i.value) next[key] = { op, value: i.value }; else delete next[key]; apply(); };
          // The declared `unit` would belong in this label ("Amount min ($/day)"), but `unit` arrives
          // with the field sweep on a separate branch. Deliberately not duplicated here: two branches
          // adding the same schema key is a merge conflict for a label suffix.
          label(f, i, suffix);
        }
      } else if (f.type === "reference" && f.module) {
        const s = document.createElement("select"); s.className = "sb-sel";
        const any = document.createElement("option"); any.value = ""; any.textContent = "any";
        s.appendChild(any);
        s.onchange = () => setOn(f.name, "eq", s.value);
        label(f, s);
        // populated lazily: a register with six reference columns would otherwise fire six fetches
        // before the user has expressed any interest in filtering at all
        toggle.addEventListener("click", () => {
          if (s.dataset.loaded) return;
          s.dataset.loaded = "1";
          void this.ctx.host.api.moduleRecordsFiltered(this.ctx.host.projectId()!, f.module!, { limit: 200 })
            .then((rs) => {
              for (const r of rs) {
                const o = document.createElement("option");
                o.value = r.id; o.textContent = r.title ? `${r.ref} · ${r.title}` : r.ref;
                s.appendChild(o);
              }
              s.value = active[f.name]?.value ?? "";
            }).catch(() => { /* leave it as "any" — a filter you cannot populate is not an error */ });
        }, { once: false });
      } else {
        const i = document.createElement("input"); i.type = "search"; i.className = "portal-filter";
        i.placeholder = "contains…";
        i.value = active[f.name]?.value ?? "";
        i.onchange = () => setOn(f.name, "contains", i.value);
        label(f, i);
      }
    }

    if (count) {
      const clear = document.createElement("button"); clear.className = "tool-btn";
      clear.textContent = "✕ Clear filters";
      clear.onclick = () => void this.openModule(m, { ...filter, offset: 0, fields: {} });
      body.appendChild(clear);
    }
    return wrap;
  }

  /**
   * MOD-FILTER — the server-side field name for a table column, or null if the server cannot sort it.
   *
   * The table shows four pseudo-columns that are not module fields: `ref` and `assignee` are real row
   * columns, `status` is the row's `workflow_state` under a friendlier heading, and `title` is whatever
   * the module nominated as its `title_field`. Mapping them here is what lets a header click order the
   * whole register instead of the fetched page. A column with no mapping falls back to the in-browser
   * comparator rather than sending a name the server would (correctly) reject with a 400.
   */
  private serverSortField(m: ModuleDef, col: string): string | null {
    if (col === "status") return "workflow_state";
    if (col === "title") return m.title_field ?? null;
    if (col === "ref" || col === "assignee") return col;
    return m.fields.some((f) => f.name === col && f.type !== "rollup" && f.type !== "signature")
      ? col : null;
  }

  /** Fields worth offering a filter control for — everything a value can be narrowed by. */
  private filterableFields(m: ModuleDef): ModuleDef["fields"] {
    return m.fields.filter((f) => !["rollup", "signature", "file", "textarea"].includes(f.type));
  }

  /**
   * MOD-TABLE — the line-item grid for a `table` field.
   *
   * The sweep found 22 places a LIST had been flattened into one textarea, and the deeper version of
   * the same gap: `sov` is one record *per line* with no parent document, and `estimate` is a single
   * `amount`. A schedule of values, a bid, an estimate and a daily manpower log are all line-item
   * documents; the config had no way to say so and the form had no way to draw one.
   *
   * **A legacy string is shown, not discarded.** Those 22 fields were textareas, so live records hold
   * prose where rows are now expected. It is rendered above the grid, verbatim and read-only, because
   * it is the only copy of that information — dropping it on first save would destroy data the config
   * change never intended to touch, and silently, since nothing else records what was there.
   */
  private tableEditor(
    f: ModuleDef["fields"][number],
    value: unknown,
    store: Record<string, Record<string, unknown>[]>,
    refOpts?: Record<string, { id: string; label: string }[]>,
  ): HTMLElement {
    const cols = f.columns ?? [];
    const wrap = document.createElement("div"); wrap.className = "tbl-field";

    if (typeof value === "string" && value.trim()) {
      const legacy = document.createElement("pre"); legacy.className = "tbl-legacy";
      legacy.textContent = value;
      legacy.title = "This field held free text before it became a line-item table. It is kept "
        + "verbatim until the lines are entered below — it is the only copy.";
      const note = document.createElement("div"); note.className = "meta";
      note.textContent = "Previous free-text entry (kept until itemised):";
      wrap.append(note, legacy);
    }

    const rows: Record<string, unknown>[] = Array.isArray(value)
      ? (value as Record<string, unknown>[]).map((r) => ({ ...r })) : [];
    store[f.name] = rows;

    const table = document.createElement("table"); table.className = "tbl-grid";
    const thead = document.createElement("thead"); const htr = document.createElement("tr");
    for (const c of cols) {
      const th = document.createElement("th");
      th.textContent = (c.label || c.name) + (c.unit ? ` (${c.unit})` : "");
      if (c.width) th.style.width = c.width;
      htr.appendChild(th);
    }
    htr.appendChild(document.createElement("th"));          // row-remove column
    thead.appendChild(htr); table.appendChild(thead);
    const tbody = document.createElement("tbody"); table.appendChild(tbody);

    const foot = document.createElement("div"); foot.className = "tbl-total";
    const isNum = (t: string) => t === "number" || t === "currency" || t === "percent";
    const retotal = () => {
      if (!f.total_column) return;
      const col = cols.find((c) => c.name === f.total_column);
      const sum = rows.reduce((n, r) => n + (Number(r[f.total_column!]) || 0), 0);
      // Currency is formatted as currency; a bare count is not dressed up as money.
      foot.textContent = `${cols.find((c) => c.name === f.total_column)?.label ?? f.total_column}: `
        + (col?.type === "currency"
          ? `$${sum.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
          : sum.toLocaleString(undefined, { maximumFractionDigits: 2 }))
        + (col?.unit ? ` ${col.unit}` : "");
    };

    const drawRow = (row: Record<string, unknown>) => {
      const tr = document.createElement("tr");
      for (const c of cols) {
        const td = document.createElement("td");
        let inp: HTMLInputElement | HTMLSelectElement;
        if (c.type === "reference") {
          // MOD-TABLEREF. The hazard `TABLE_COLUMN_TYPES` excluded this type over was "unresolvable
          // ids in rows" — and inside a <select> that is worse than a bad label, it is SILENT DATA
          // LOSS: a stored value absent from the options list leaves the control showing the blank
          // option, and the next save writes the blank over a link somebody made. The row would come
          // back empty with nothing having reported an error.
          //
          // So a stored value that no option matches gets an option of its own, marked, and stays
          // selected. Same three-way shape as `refCell`: resolved reads as the record, an unresolved
          // id is shown as an id and never as a working choice, and free text is kept in full
          // because it is the only handle anyone has for re-linking it.
          inp = document.createElement("select");
          const blank = document.createElement("option"); blank.value = ""; blank.textContent = "—";
          inp.appendChild(blank);
          const opts = refOpts?.[c.name] ?? [];
          for (const o of opts) {
            const op = document.createElement("option"); op.value = o.id; op.textContent = o.label;
            inp.appendChild(op);
          }
          const stored = row[c.name] == null ? "" : String(row[c.name]);
          if (stored && !opts.some((o) => o.id === stored)) {
            const keep = document.createElement("option");
            keep.value = stored;
            keep.textContent = UUID_RE.test(stored)
              ? `${stored.slice(0, 8)}… (not found)`
              : `${stored} (not linked)`;
            keep.title = UUID_RE.test(stored)
              ? `This ${String(c.module).replace(/_/g, " ")} could not be resolved — it may have been `
                + `deleted, or lie beyond the first ${REF_RESOLVE_LIMIT} records. Kept so saving this `
                + "row cannot erase it."
              : "Free text from before this column became a reference. Kept verbatim — pick a record "
                + "to link it, or leave it as it is.";
            inp.insertBefore(keep, inp.firstChild!.nextSibling);
          }
          inp.value = stored;
        } else if (c.type === "select") {
          inp = document.createElement("select");
          const blank = document.createElement("option"); blank.value = ""; blank.textContent = "—";
          inp.appendChild(blank);
          for (const o of c.options ?? []) {
            const opt = document.createElement("option"); opt.value = opt.textContent = o;
            inp.appendChild(opt);
          }
        } else {
          inp = document.createElement("input");
          const i = inp as HTMLInputElement;
          i.type = c.type === "checkbox" ? "checkbox" : isNum(c.type) ? "number" : c.type === "date" ? "date" : "text";
          if (c.type === "currency" || c.type === "percent") i.step = "0.01";
        }
        inp.className = "tbl-cell";
        if (c.type === "checkbox") (inp as HTMLInputElement).checked = !!row[c.name];
        else inp.value = String(row[c.name] ?? "");
        inp.oninput = () => {
          // Numbers are stored as NUMBERS, not the input's string. Storing "5" here is what makes a
          // SQL comparison go lexicographic later ('9' >= 10 is true), and it is the same defect the
          // record form had for `percent` fields.
          row[c.name] = c.type === "checkbox" ? (inp as HTMLInputElement).checked
            : isNum(c.type) ? (inp.value === "" ? "" : Number(inp.value))
            : inp.value;
          retotal();
        };
        td.appendChild(inp); tr.appendChild(td);
      }
      const rm = document.createElement("td");
      const del = document.createElement("button"); del.type = "button"; del.className = "tbl-del";
      del.textContent = "✕"; del.title = "Remove this line";
      del.onclick = () => {
        const i = rows.indexOf(row);
        if (i >= 0) rows.splice(i, 1);
        tr.remove(); retotal();
      };
      rm.appendChild(del); tr.appendChild(rm);
      tbody.appendChild(tr);
    };

    for (const r of rows) drawRow(r);

    const add = document.createElement("button"); add.type = "button"; add.className = "tool-btn";
    add.textContent = "+ Add line";
    add.onclick = () => { const r: Record<string, unknown> = {}; rows.push(r); drawRow(r); retotal(); };

    wrap.append(table, add);
    if (f.total_column) { wrap.appendChild(foot); retotal(); }
    return wrap;
  }

  /** Format a field value for a compact table cell. */
  private fmtCell(f: ModuleDef["fields"][number], v: unknown): string {
    if (v == null || v === "") return "";
    if (f.type === "currency") return `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
    if (f.type === "percent") return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
    if (f.type === "multiselect" && Array.isArray(v)) return (v as string[]).join(", ");
    // MOD-TABLE: a cell has no room for a grid, so it carries the two facts worth scanning — how many
    // lines, and the total if the field declares one. `String(v)` on an array of objects renders
    // "[object Object]" per row, which is the kind of output that looks like a rendering bug and is
    // actually a missing branch. A legacy string still shows as text (see `tableEditor`).
    if (f.type === "table") {
      if (typeof v === "string") return v.slice(0, 40);
      if (!Array.isArray(v)) return "";
      const n = v.length;
      const label = `${n} line${n === 1 ? "" : "s"}`;
      if (!f.total_column || !n) return label;
      const col = f.columns?.find((c) => c.name === f.total_column);
      const sum = (v as Record<string, unknown>[]).reduce((t, r) => t + (Number(r[f.total_column!]) || 0), 0);
      const shown = col?.type === "currency"
        ? `$${sum.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
        : sum.toLocaleString(undefined, { maximumFractionDigits: 2 });
      return `${label} · ${shown}`;
    }
    // Same defect as the old refCell fallback, in the path taken when a reference is NOT a resolved
    // column: eight characters of a value, indistinguishable from a resolved label. A UUID at least
    // announces itself as an id; anything else is shown as the text it is.
    if (f.type === "reference") return UUID_RE.test(String(v)) ? `${String(v).slice(0, 8)}…` : String(v);
    if (f.unit) return `${String(v)} ${f.unit}`;
    return String(v).slice(0, 40);
  }

  /** Inline-editable assignee cell — click to reassign without opening the record.
   *  Mutates r in place + persists via the assign endpoint (server still gates by role). */
  private assigneeCell(pid: string, m: ModuleDef, r: ModuleRecord): HTMLTableCellElement {
    const td = document.createElement("td"); td.className = "editable"; td.title = "Click to reassign";
    const show = () => { td.textContent = r.assignee ?? "—"; };
    show();
    td.onclick = (e) => {
      e.stopPropagation();
      if (td.querySelector("input")) return;
      const inp = document.createElement("input"); inp.className = "portal-filter";
      inp.value = r.assignee ?? ""; inp.style.width = "110px"; inp.placeholder = "user";
      td.textContent = ""; td.appendChild(inp); inp.focus();
      inp.onclick = (ev) => ev.stopPropagation();
      inp.onkeydown = (ev) => { if (ev.key === "Enter") inp.blur(); else if (ev.key === "Escape") { inp.value = r.assignee ?? ""; inp.blur(); } };
      inp.onblur = async () => {
        const v = inp.value.trim();
        if (v === (r.assignee ?? "")) { show(); return; }
        try { const u = await this.ctx.host.api.assignRecord(pid, m.key, r.id, v || null); r.assignee = u.assignee ?? null; this.ctx.host.setStatus(`${r.ref} assigned → ${r.assignee ?? "unassigned"}`); }
        catch (err) { this.ctx.host.setStatus(`assign blocked: ${(err as Error).message}`); }
        show();
      };
    };
    return td;
  }

  /** Inline status cell — a dropdown of the workflow transitions valid from the current state
   *  (terminal states stay read-only). Selecting one calls /transition; party gates apply server-side. */
  private statusCell(pid: string, m: ModuleDef, r: ModuleRecord): HTMLTableCellElement {
    const td = document.createElement("td");
    // UX-CHIPS — one tone vocabulary for every module's lifecycle, so "approved" reads the same
    // green in the drawing register (DRAW-STATUS), the submittal log and the RFI list. This is the
    // single widest-reach chip site: every module record grid renders its state through here.
    const render = () => { td.innerHTML = statusChip(r.workflow_state); };
    render();
    const nexts = (m.workflow.transitions ?? []).filter((t) => t.from === r.workflow_state);
    if (!nexts.length) return td;          // terminal — nothing to transition to
    td.className = "editable"; td.title = "Click to change status";
    td.onclick = (e) => {
      e.stopPropagation();
      if (td.querySelector("select")) return;
      const sel = document.createElement("select"); sel.className = "sb-sel";
      const cur = document.createElement("option"); cur.value = ""; cur.textContent = r.workflow_state; sel.appendChild(cur);
      // MOD-COMPLETE ②: mark the transitions the server will REFUSE without evidence. The rule is
      // enforced in `modules.py` (entering one of these states with zero attachments is a 400), and
      // #151 made `GET /modules` serve it — but nothing read it, so a user still learned the rule by
      // having the transition rejected. Saying it in the option is the point of serving the key.
      const needsEvidence = new Set(m.close_requires_attachment ?? []);
      for (const t of nexts) {
        const o = document.createElement("option"); o.value = t.action;
        o.textContent = needsEvidence.has(t.to)
          ? `${t.action} → ${t.to}  (needs an attachment)` : `${t.action} → ${t.to}`;
        sel.appendChild(o);
      }
      td.textContent = ""; td.appendChild(sel); sel.focus();
      sel.onclick = (ev) => ev.stopPropagation();
      sel.onblur = () => render();
      sel.onchange = async () => {
        if (!sel.value) { render(); return; }
        try { const u = await this.ctx.host.api.transitionRecord(pid, m.key, r.id, sel.value); r.workflow_state = u.workflow_state; this.ctx.host.setStatus(`${r.ref} → ${r.workflow_state}`); }
        catch (err) { this.ctx.host.setStatus(`transition blocked: ${(err as Error).message}`); }
        render();
      };
    };
    return td;
  }

  /** Per-module column choice (localStorage). null = use the module's default columns. */
  private readColPrefs(key: string): string[] | null {
    try { const s = localStorage.getItem(`portal-cols:${key}`); const a = s ? JSON.parse(s) : null; return Array.isArray(a) ? a as string[] : null; }
    catch { return null; }
  }

  /** Column chooser — pick which fields render as columns in a wide module. Personal + persisted;
   *  Ref / Title / Assignee / Ball / Status always frame the row, so only data fields are offered.
   *  Reset clears the choice and falls back to the module's default columns. */
  private columnPicker(m: ModuleDef, current: string[], filter: { q?: string; state?: string; offset?: number }) {
    const fields = m.fields.filter((f) => f.type !== "rollup" && f.type !== "signature");
    const dlg = modalShell(`Columns — ${m.name}`, 360);
    const help = document.createElement("div"); help.className = "meta";
    help.textContent = "Choose which fields show as columns. Ref, Title, Assignee, Ball-in-court and Status always show.";
    const list = document.createElement("div");
    list.style.cssText = "display:flex;flex-direction:column;gap:6px;max-height:44vh;overflow:auto;margin:8px 0";
    const boxes = new Map<string, HTMLInputElement>();
    for (const f of fields) {
      const lab = document.createElement("label"); lab.style.cssText = "display:flex;gap:8px;align-items:center;font-size:13px;cursor:pointer";
      const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = current.includes(f.name);
      lab.append(cb, document.createTextNode(f.label)); list.appendChild(lab); boxes.set(f.name, cb);
    }
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:4px";
    const reset = document.createElement("button"); reset.textContent = "Reset to default"; reset.className = "file-btn"; reset.style.marginRight = "auto";
    reset.onclick = () => { localStorage.removeItem(`portal-cols:${m.key}`); dlg.close(); void this.openModule(m, filter); };
    const cancel = document.createElement("button"); cancel.textContent = "Cancel"; cancel.className = "file-btn"; cancel.onclick = () => dlg.close();
    const ok = document.createElement("button"); ok.textContent = "Apply"; ok.className = "file-btn"; ok.style.fontWeight = "600";
    ok.onclick = () => {
      const names = fields.filter((f) => boxes.get(f.name)?.checked).map((f) => f.name);   // preserve field order
      localStorage.setItem(`portal-cols:${m.key}`, JSON.stringify(names));
      dlg.close(); void this.openModule(m, filter);
    };
    row.append(reset, cancel, ok);
    dlg.card.append(help, list, dlg.msg, row);
  }

  /** Paste-from-spreadsheet bulk entry — Ctrl-V a block of cells copied from Excel/Google Sheets
   *  (tab-separated) straight in, no file needed. The pasted table is converted to CSV and handed to
   *  the same import flow (preview + column mapping + commit), so paste and file import share one
   *  robust, validated server path rather than a second bespoke bulk-create loop. */
  private pasteRows(m: ModuleDef) {
    const dlg = modalShell(`Paste ${m.name} rows`, 460);
    const help = document.createElement("div");
    help.className = "meta";
    help.textContent = "Copy a block of cells from Excel or Google Sheets and paste below — keep the header row. "
      + "The next step lets you map each column to a field before anything is created.";
    const ta = document.createElement("textarea");
    ta.placeholder = "name\tstatus\tamount\nFooting F-1\topen\t1200\n…";
    ta.setAttribute("aria-label", "Pasted spreadsheet rows");
    ta.style.cssText = "width:100%;min-height:150px;margin:8px 0;padding:8px;border:1px solid var(--line);"
      + "border-radius:6px;background:var(--bg);color:inherit;font-family:ui-monospace,monospace;font-size:12px;white-space:pre;overflow:auto";
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:4px";
    const cancel = document.createElement("button"); cancel.textContent = "Cancel"; cancel.className = "file-btn";
    cancel.onclick = () => dlg.close();
    const ok = document.createElement("button"); ok.textContent = "Continue →"; ok.className = "file-btn"; ok.style.fontWeight = "600";
    ok.onclick = () => {
      const text = ta.value.replace(/\r\n?/g, "\n").replace(/\n+$/, "");
      if (!text.trim()) { dlg.msg.textContent = "Nothing pasted yet."; return; }
      // TSV → CSV: quote every cell (doubling internal quotes) so tabs/commas survive the round-trip.
      const csv = text.split("\n")
        .map((line) => line.split("\t").map((cell) => `"${cell.replace(/"/g, '""')}"`).join(","))
        .join("\n");
      const file = new File([csv], "pasted.csv", { type: "text/csv" });
      dlg.close();
      void this.renderImport(m, file);
    };
    row.append(cancel, ok);
    dlg.card.append(help, ta, dlg.msg, row);
    setTimeout(() => ta.focus(), 0);
  }

  // --- generic Excel/CSV import: map columns -> fields, preview, import -------
  private async renderImport(m: ModuleDef, file: File) {
    const pid = this.ctx.host.projectId()!;
    this.ctx.root.innerHTML = "";
    this.ctx.root.appendChild(this.ctx.bar(`Import ${m.name}`, () => this.openModule(m)));
    const wrap = document.createElement("div"); wrap.className = "portal-form"; this.ctx.root.appendChild(wrap);
    const status = document.createElement("div"); status.className = "meta"; status.textContent = `Reading ${file.name}…`;
    wrap.appendChild(status);
    let pv: Awaited<ReturnType<typeof this.ctx.host.api.importPreview>>;
    try { pv = await this.ctx.host.api.importPreview(pid, m.key, file); }
    catch (e) { status.textContent = `Couldn't read the file: ${(e as Error).message}`; return; }

    status.textContent = `${pv.row_count} row(s) found in ${file.name}. Map each spreadsheet column to a field, then import.`;
    const tmpl = document.createElement("a"); tmpl.href = this.ctx.host.api.importTemplateUrl(pid, m.key);
    tmpl.textContent = "↓ download a blank template"; tmpl.style.cssText = "font-size:12px;margin-left:8px"; tmpl.target = "_blank";
    status.appendChild(tmpl);

    // mapping table: one row per source column -> a field <select>
    const selects: { header: string; sel: HTMLSelectElement }[] = [];
    const tbl = document.createElement("table"); tbl.className = "portal-table"; tbl.style.marginTop = "8px";
    const thead = document.createElement("tr");
    for (const h of ["Spreadsheet column", "→ Field", "Sample"]) { const th = document.createElement("th"); th.textContent = h; thead.appendChild(th); }
    tbl.appendChild(thead);
    for (const h of pv.headers) {
      const tr = document.createElement("tr");
      const c1 = document.createElement("td"); c1.textContent = h; c1.style.fontFamily = "monospace";
      const c2 = document.createElement("td");
      const sel = document.createElement("select"); sel.className = "sb-sel";
      const skip = document.createElement("option"); skip.value = ""; skip.textContent = "— skip —"; sel.appendChild(skip);
      for (const f of pv.fields) {
        const o = document.createElement("option"); o.value = f.name; o.textContent = f.label + (f.required ? " *" : ""); sel.appendChild(o);
      }
      sel.value = pv.suggested_mapping[h] ?? "";
      selects.push({ header: h, sel }); c2.appendChild(sel);
      const c3 = document.createElement("td"); c3.style.color = "var(--muted)";
      const fld = pv.suggested_mapping[h];
      c3.textContent = fld && pv.sample[0] ? String(pv.sample[0][fld] ?? "") : "";
      tr.append(c1, c2, c3); tbl.appendChild(tr);
    }
    wrap.appendChild(tbl);

    const req = pv.fields.filter((f) => f.required).map((f) => f.name);
    const warn = document.createElement("div"); warn.className = "meta"; warn.style.color = "var(--warn, #c60)"; wrap.appendChild(warn);
    const importBtn = document.createElement("button"); importBtn.className = "tool-btn"; importBtn.textContent = `Import ${pv.row_count} row(s)`;
    importBtn.style.marginTop = "8px";
    const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "8px";
    const checkReq = () => {
      const mapped = new Set(selects.map((s) => s.sel.value).filter(Boolean));
      const missing = req.filter((r) => !mapped.has(r));
      warn.textContent = missing.length ? `⚠ Required field(s) not mapped: ${missing.map((n) => pv.fields.find((f) => f.name === n)?.label ?? n).join(", ")}` : "";
      importBtn.disabled = missing.length > 0;
    };
    for (const s of selects) s.sel.onchange = checkReq;
    checkReq();
    importBtn.onclick = async () => {
      const mapping: Record<string, string> = {};
      for (const s of selects) if (s.sel.value) mapping[s.header] = s.sel.value;
      importBtn.disabled = true; out.textContent = "Importing…";
      try {
        const r = await this.ctx.host.api.importModuleRecords(pid, m.key, file, mapping);
        out.innerHTML = "";
        const ok = document.createElement("div");
        ok.textContent = `✓ Imported ${r.imported} record(s)${r.error_count ? ` · ${r.error_count} row(s) skipped` : ""}${r.truncated ? " · file truncated at the row cap" : ""}.`;
        out.appendChild(ok);
        for (const er of r.errors.slice(0, 10)) { const e = document.createElement("div"); e.style.color = "var(--warn,#c60)"; e.textContent = `Row ${er.row}: ${er.error}`; out.appendChild(e); }
        const done = document.createElement("button"); done.className = "tool-btn"; done.style.marginTop = "6px"; done.textContent = "← Back to the list";
        done.onclick = () => this.openModule(m); out.appendChild(done);
        this.ctx.host.setStatus(`imported ${r.imported} ${m.name} record(s)`);
      } catch (e) { out.textContent = `Import failed: ${(e as Error).message}`; importBtn.disabled = false; }
    };
    wrap.append(importBtn, out);
  }

  // --- create / edit form (fields from module.json) --------------------------
  private async renderForm(m: ModuleDef, existing?: ModuleRecord) {
    const pid = this.ctx.host.projectId()!;
    const editing = !!existing;
    // reference fields need their target module's records as options — fetch up front
    const refOpts = new Map<string, { id: string; label: string }[]>();
    await Promise.all(m.fields.filter((f) => f.type === "reference" && f.module).map(async (f) => {
      const recs = await this.ctx.host.api.moduleRecords(pid, f.module!);
      refOpts.set(f.name, recs.map((r) => ({ id: r.id, label: `${r.ref} — ${r.title ?? ""}` })));
    }));
    // MOD-TABLEREF: the same fetch for a `reference` COLUMN inside a table field. Keyed
    // `<field>.<column>` so a picker in one grid cannot be fed another's options — and deduped by
    // target module, because two columns pointing at the same register are one request, not two.
    const colTargets = new Map<string, string>();          // "field.column" -> module
    for (const f of m.fields) {
      for (const c of f.columns ?? []) {
        if (c.type === "reference" && c.module) colTargets.set(`${f.name}.${c.name}`, c.module);
      }
    }
    const byTarget = new Map<string, { id: string; label: string }[]>();
    await Promise.all([...new Set(colTargets.values())].map(async (mod) => {
      const recs = await this.ctx.host.api.moduleRecords(pid, mod);
      byTarget.set(mod, recs.map((r) => ({ id: r.id, label: `${r.ref} — ${r.title ?? ""}` })));
    }));
    const tableRefOpts: Record<string, Record<string, { id: string; label: string }[]>> = {};
    for (const [k, mod] of colTargets) {
      const dot = k.indexOf(".");
      const fname = k.slice(0, dot), cname = k.slice(dot + 1);
      (tableRefOpts[fname] ??= {})[cname] = byTarget.get(mod) ?? [];
    }
    // E1 — project-level custom select options, merged into the module.json options below
    const custom = await this.ctx.host.api.enumOptions(pid).catch(() => ({} as Record<string, Record<string, string[]>>));
    const optsFor = (f: ModuleDef["fields"][number]) => [...(f.options ?? []), ...((custom[m.key]?.[f.name]) ?? [])];
    // "＋ option" button: add a new enum value to a select/multiselect without editing JSON
    const addOptBtn = (f: ModuleDef["fields"][number], selEl: HTMLSelectElement) => {
      const b = document.createElement("button"); b.type = "button"; b.className = "pf-addopt";
      b.textContent = "＋ option"; b.title = `Add a new ${f.label} option`;
      b.onclick = async () => {
        const v = await promptModal(`Add ${f.label} option`,
          [{ name: "val", label: `New ${f.label} option`, required: true }], "Add");
        if (!v) return;
        const val = v.val ?? "";
        try {
          const res = await this.ctx.host.api.addEnumOption(pid, m.key, f.name, val.trim());
          let opt = [...selEl.options].find((o) => o.value === res.value);
          if (!opt) { opt = document.createElement("option"); opt.value = opt.textContent = res.value; selEl.appendChild(opt); }
          if (selEl.multiple) opt.selected = true; else selEl.value = res.value;
          toast(`Added ${f.label}: ${res.value}`, "info");
        } catch (e) { toast(`could not add option: ${(e as Error).message}`, "error"); }
      };
      return b;
    };

    this.ctx.root.innerHTML = "";
    this.ctx.root.appendChild(this.ctx.bar(`${editing ? "Edit" : "New"} ${m.name}`,
      () => (editing ? this.openRecord(m, existing!.id) : this.openModule(m))));
    const inputs: Record<string, HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement> = {};
    const sigs: Record<string, () => string> = {};   // signature field getters (data-URI)
    // MOD-TABLE: live rows per table field. Held apart from `inputs` because a table's value is an
    // array of objects, not an `el.value` string — the shape the rest of the form assumes.
    const tableRows: Record<string, Record<string, unknown>[]> = {};
    const cur = (n: string) => (existing?.data?.[n] as string | number | string[] | undefined);
    let curFieldset: string | undefined;   // F1 — emit a labeled header when the fieldset changes
    for (const f of m.fields) {
      if (f.type === "rollup") continue;   // computed, not user-entered
      if (f.fieldset && f.fieldset !== curFieldset) {
        curFieldset = f.fieldset;
        const h = document.createElement("div"); h.className = "portal-fieldset-head"; h.textContent = f.fieldset;
        this.ctx.root.appendChild(h);
      }
      const wrap = document.createElement("label"); wrap.className = "portal-field";
      wrap.textContent = f.label + (f.required ? " *" : "");
      if (f.type === "signature") {
        sigs[f.name] = this.signaturePad(wrap);
        this.ctx.root.appendChild(wrap);
        continue;
      }
      let el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
      if (f.type === "textarea") { el = document.createElement("textarea"); el.value = String(cur(f.name) ?? ""); }
      else if (f.type === "select") {
        el = document.createElement("select");
        const blank = document.createElement("option"); blank.value = ""; blank.textContent = "— select —"; el.appendChild(blank);
        for (const o of optsFor(f)) { const opt = document.createElement("option"); opt.value = opt.textContent = o; el.appendChild(opt); }
        if (cur(f.name) != null) el.value = String(cur(f.name));
      } else if (f.type === "multiselect") {
        const opts = optsFor(f);
        el = document.createElement("select"); el.multiple = true; el.size = Math.min(opts.length, 5);
        const chosen = new Set(Array.isArray(cur(f.name)) ? (cur(f.name) as string[]) : []);
        for (const o of opts) { const opt = document.createElement("option"); opt.value = opt.textContent = o; opt.selected = chosen.has(o); el.appendChild(opt); }
      } else if (f.type === "reference") {
        const sel = document.createElement("select"); el = sel;
        const none = document.createElement("option"); none.value = ""; none.textContent = `— none —`; sel.appendChild(none);
        for (const o of refOpts.get(f.name) ?? []) { const opt = document.createElement("option"); opt.value = o.id; opt.textContent = o.label; sel.appendChild(opt); }
        // D1: inline "add new" — create the referenced record (e.g. a cost code) without leaving the form
        const tgt = this.ctx.mods.find((x) => x.key === f.module);
        const addOpt = document.createElement("option"); addOpt.value = "__new__";
        addOpt.textContent = `＋ Add new ${tgt?.name ?? f.module}…`; sel.appendChild(addOpt);
        if (cur(f.name) != null) sel.value = String(cur(f.name));
        // searchable picker: for long lists, a type-to-filter box hides non-matching options
        if ((refOpts.get(f.name) ?? []).length > 8) {
          const fx = document.createElement("input"); fx.type = "search";
          fx.placeholder = `filter ${tgt?.name ?? "records"}…`; fx.className = "portal-filter";
          fx.style.cssText = "display:block;margin-bottom:4px;width:100%";
          fx.oninput = () => {
            const q = fx.value.trim().toLowerCase();
            for (const o of [...sel.options]) {
              if (o.value === "" || o.value === "__new__") continue;
              o.hidden = !!q && !(o.textContent ?? "").toLowerCase().includes(q);
            }
          };
          wrap.appendChild(fx);
        }
        sel.addEventListener("change", async () => {
          if (sel.value !== "__new__") return;
          // the field to set on the new record: the module's title_field, else its first required
          // (or first) field — so e.g. a Cost Code gets `code`, not a non-existent `title`.
          const tgtFields = (tgt?.fields ?? []).filter((x) => x.type !== "rollup");
          const tf = tgt?.title_field || tgtFields.find((x) => x.required)?.name || tgtFields[0]?.name || "title";
          const nv = await promptModal(`New ${tgt?.name ?? f.module}`,
            [{ name: "val", label: tf, required: true }], "Create");
          const val = nv?.val;
          sel.value = String(cur(f.name) ?? "");
          if (!val || !val.trim()) return;
          try {
            const rec = await this.ctx.host.api.createModuleRecord(pid, f.module!, { data: { [tf]: val.trim() } });
            const opt = document.createElement("option"); opt.value = rec.id; opt.textContent = `${rec.ref} — ${val.trim()}`;
            sel.insertBefore(opt, addOpt); sel.value = rec.id;
            toast(`Added ${tgt?.name ?? f.module}: ${val.trim()}`, "info");
          } catch { toast(`could not create ${tgt?.name ?? f.module}`, "error"); }
        });
      } else if (f.type === "table") {
        // MOD-TABLE: a line-item grid is NOT one of the form's three input elements, and it is
        // deliberately not registered in `inputs` — its value is an array of objects rather than an
        // `el.value` string, so every consumer of `inputs` (the required check, the save loop, the
        // invalid-marker) would read it wrongly. `tableRows` holds the live rows; the save path reads
        // from there. Appending it here and `continue`-ing keeps `el` honestly typed as an input.
        wrap.appendChild(this.tableEditor(f, cur(f.name), tableRows, tableRefOpts[f.name]));
        this.ctx.root.appendChild(wrap);
        continue;
            } else {
        el = document.createElement("input");
        const inp = el as HTMLInputElement;
        // MOD-PERCENT: a percent field rendered as `type="text"` — no numeric keypad on a phone, no
        // step, no browser validation. It is a magnitude like the other two.
        inp.type = isNumericField(f.type) ? "number" : f.type === "date" ? "date" : "text";
        if (f.type === "currency" || f.type === "percent") inp.step = "0.01";
        // The declared unit is shown beside the input, not only in table cells. A unit that renders in
        // one place and not the other is half of what declaring it was for: the moment it matters most
        // is while somebody is TYPING the number.
        //
        // Read structurally rather than via `ModuleField.unit`. `unit` is declared on that interface by
        // the field-sweep branch, which is merged to `main` but not into this one — and it cannot be
        // merged in right now without git overwriting two files another session is holding dirty. A
        // local structural read is correct on both sides of that merge and costs nothing once it lands.
        const unit = f.unit;
        // MOD-FIELDATTRS: an explicit placeholder wins over the unit hint — the unit was only ever a
        // fallback for "this box has no guidance at all".
        if (f.placeholder) inp.placeholder = f.placeholder;
        else if (unit) inp.placeholder = unit;
        if (unit) inp.setAttribute("aria-description", `in ${unit}`);
        if (f.min != null) inp.min = String(f.min);
        if (f.max != null) inp.max = String(f.max);
        // A default is for a NEW record. On an edit, an absent value is a value the user cleared.
        const existing = cur(f.name);
        // `@today` is resolved on both sides: the form shows the date the user is about to save, and
        // the server fills it for any caller that never opened a form (import, integration, script).
        const dflt = f.default === "@today" ? new Date().toISOString().slice(0, 10) : f.default;
        inp.value = String(existing ?? (editing ? "" : (dflt ?? "")));
      }
      inputs[f.name] = el; wrap.appendChild(el);
      if (f.type === "select" || f.type === "multiselect") wrap.appendChild(addOptBtn(f, el as HTMLSelectElement));
      this.ctx.root.appendChild(wrap);
    }
    // assignee (drives the cross-module "My work" queue) — set at creation
    const asg = document.createElement("input"); asg.type = "text"; asg.placeholder = "user id";
    if (!editing) {
      const asgWrap = document.createElement("label"); asgWrap.className = "portal-field";
      asgWrap.textContent = "Assignee";
      asgWrap.appendChild(asg); this.ctx.root.appendChild(asgWrap);
    }

    // pin-to-model option (create only)
    const pinCb = document.createElement("input"); pinCb.type = "checkbox"; pinCb.checked = m.pinnable;
    if (m.pinnable && !editing) {
      const pinLabel = document.createElement("label"); pinLabel.className = "portal-field";
      pinLabel.append(pinCb, document.createTextNode(" Pin to last-clicked model point"));
      this.ctx.root.appendChild(pinLabel);
    }

    // field-level validation: outline offending inputs + focus the first (no more silent 422s)
    const labelOf = (n: string) => m.fields.find((f) => f.name === n)?.label ?? n;
    const markInvalid = (names: string[]) => {
      for (const f of m.fields) { const el = inputs[f.name]; if (el) el.style.borderColor = ""; }
      for (const n of names) { const el = inputs[n]; if (el) el.style.borderColor = "var(--err, #d9534f)"; }
      const first = names.map((n) => inputs[n]).find(Boolean); if (first) first.focus();
    };
    const isEmpty = (f: ModuleDef["fields"][number]): boolean => {
      // MOD-TABLE: checked BEFORE the `!el` guard, because a table is deliberately absent from
      // `inputs` — and `!el → return false` means "not empty", so a `required` table with zero rows
      // would have sailed through the check. None of the eight tables shipped here is required, so
      // this is a hole rather than a bug today; it is the same "plausible answer for the missing
      // case" shape that keeps costing this codebase, so it is closed at the point it was created.
      if (f.type === "table") {
        return !(tableRows[f.name] ?? []).some(
          (row) => Object.values(row).some((x) => x !== "" && x != null));
      }
      const el = inputs[f.name]; if (!el) return false;
      if (f.type === "signature") return !sigs[f.name]?.();
      if (f.type === "multiselect") return [...(el as HTMLSelectElement).selectedOptions].length === 0;
      return !String((el as HTMLInputElement).value || "").trim();
    };
    const save = document.createElement("button");
    save.className = "file-btn"; save.textContent = editing ? "Save" : "Create"; save.style.marginTop = "8px";
    save.onclick = async () => {
      // client-side required check before hitting the server
      const missing = m.fields.filter((f) => f.required && f.type !== "rollup" && isEmpty(f)).map((f) => f.name);
      if (missing.length) {
        markInvalid(missing);
        this.ctx.host.setStatus(`Please fill required field(s): ${missing.map(labelOf).join(", ")}`);
        return;
      }
      markInvalid([]);
      const data: Record<string, unknown> = {};
      for (const f of m.fields) {
        if (f.type === "rollup") continue;
        if (f.type === "signature") { const s = sigs[f.name]?.(); if (s) data[f.name] = s; continue; }
        const el = inputs[f.name];
        if (!el) continue;
        if (f.type === "multiselect") { data[f.name] = [...(el as HTMLSelectElement).selectedOptions].map((o) => o.value); continue; }
        // MOD-PERCENT: the quietest of the three. Without `percent` here a percentage saved as the
        // STRING "5"; `validate_record` does `float(value)` so it passed, and every consumer coerces,
        // so nothing ever failed — the column simply accumulated a mix of 5 and "5" depending on which
        // form last touched the record. Numbers stored as text are also what makes SQL comparison go
        // lexicographic, which is the bug MOD-FILTER's cast exists to survive.
        const v = el.value; if (v) data[f.name] = isNumericField(f.type) ? Number(v) : v;
      }
      // MOD-TABLE: rows come from their own state, and are written even when EMPTY — unlike a text
      // field, "the user deleted every line" is a real edit that must persist. Skipping empty here
      // would make clearing a schedule of values silently impossible.
      for (const f of m.fields) {
        if (f.type !== "table" || !(f.name in tableRows)) continue;
        data[f.name] = tableRows[f.name]!.filter(
          (row) => Object.values(row).some((x) => x !== "" && x != null));
      }
      try {
        if (editing) {
          // optimistic lock: send the modified_at we loaded; a concurrent edit 409s rather than
          // silently overwriting the other person's change (real-time collaboration safety).
          await this.ctx.host.api.updateModuleRecord(pid, m.key, existing!.id, data, existing!.modified_at);
          this.ctx.host.setStatus(`saved ${existing!.ref}`);
          void this.openRecord(m, existing!.id);
        } else {
          const body: Record<string, unknown> = { data };
          if (asg.value.trim()) body.assignee = asg.value.trim();
          if (m.pinnable && pinCb.checked) {
            body.anchor = this.ctx.host.anchorPoint();
            const g = this.ctx.host.selectedGuid(); if (g) body.element_guids = [g];
          }
          const rec = await this.ctx.host.api.createModuleRecord(pid, m.key, body);
          this.ctx.host.setStatus(`created ${rec.ref}`);
          if (body.anchor) this.ctx.host.onPinsChanged();
          void this.openRecord(m, rec.id);
        }
      } catch (e) {
        const msg = (e as Error).message;
        if (/-> 409$/.test(msg) && editing) {          // optimistic-lock conflict — someone edited first
          this.ctx.host.setStatus("Someone else changed this record while you had it open — reloading the latest; re-apply your edit.");
          void this.openRecord(m, existing!.id);
          return;
        }
        const mm = /missing required field\(s\):\s*([^"}]+)/i.exec(msg);   // server-side required rules
        if (mm) { const names = (mm[1] ?? "").split(",").map((s) => s.trim()).filter(Boolean); markInvalid(names); }
        this.ctx.host.setStatus(`error: ${msg}`);
      }
    };
    this.ctx.root.appendChild(save);
  }

  /** Compact workflow state diagram — states left→right in declared order, current one highlighted,
   *  with reachable next states shown as arrows. Reads the module's workflow (no server call). */
  private workflowMap(m: ModuleDef, current: string): HTMLElement {
    const states = m.workflow.states ?? [];
    const wrap = document.createElement("div"); wrap.className = "wf-map";
    wrap.style.cssText = "display:flex;align-items:center;flex-wrap:wrap;gap:2px;margin:4px 0 8px;font-size:11px";
    const nexts = new Set((m.workflow.transitions ?? []).filter((t) => t.from === current).map((t) => t.to));
    states.forEach((s, i) => {
      if (i) { const arr = document.createElement("span"); arr.textContent = "→"; arr.style.opacity = "0.4"; wrap.appendChild(arr); }
      const node = document.createElement("span");
      const isCur = s === current, isNext = nexts.has(s);
      node.textContent = s.replace(/_/g, " ");
      node.style.cssText = "padding:2px 7px;border-radius:10px;white-space:nowrap;border:1px solid var(--border,#3a4654);"
        + (isCur ? "background:var(--accent,#4a8cff);color:#fff;font-weight:700;"
                 : isNext ? "background:rgba(74,140,255,0.16);" : "opacity:0.55;");
      wrap.appendChild(node);
    });
    return wrap;
  }

  // --- record detail + workflow actions + activity ---------------------------
  // contract modules → the document they generate, and whether an Exhibit A applies
  private static CONTRACT_DOCS: Record<string, { doc: string; label: string; exhibit: boolean }> = {
    prime_contract: { doc: "prime", label: "Prime Contract", exhibit: false },
    subcontract: { doc: "agreement", label: "Subcontract", exhibit: true },
    commitment: { doc: "agreement", label: "Agreement", exhibit: true },
    cor: { doc: "co", label: "Change Order", exhibit: false },
  };

  /** Contract lifecycle actions on a contract/CO record: generate the document, compose Exhibit A,
   *  open it with redline/markup tools, and capture signatures — with a signed-by status line. */
  private contractActions(m: ModuleDef, r: ModuleRecord, rid: string, tools: HTMLElement) {
    const spec = RegisterUI.CONTRACT_DOCS[m.key];
    if (!spec) return;
    const pid = this.ctx.host.projectId()!;
    const api = this.ctx.host.api;
    const btn = (label: string, title: string, fn: () => void) => {
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label; b.title = title; b.onclick = fn; tools.appendChild(b);
    };
    btn(`📄 Generate ${spec.label}`, "Generate the contract document (PDF)",
        () => window.open(api.contractDocUrl(pid, m.key, rid, spec.doc), "_blank"));
    if (spec.exhibit) btn("📐 Compose Exhibit A", "Build the scope-of-work exhibit from the clause library", () => void this.composeExhibit(m, r, rid));
    btn("🖊 View & markup", "Open the document with redline / markup tools (save annotations back as an attachment)", async () => {
      const { openPdfUrl } = await import("../../drawings/openPdf");
      await openPdfUrl(api, api.contractDocUrl(pid, m.key, rid, spec.doc), `${spec.doc}-${r.ref}.pdf`, {
        saveLabel: "Attach marked-up copy",
        onSave: async (blob, name) => { await api.uploadAttachment(pid, m.key, rid, new File([blob], name.replace(/\.pdf$/i, "") + "-markup.pdf", { type: "application/pdf" })); },
      });
    });
    btn("✍ Sign", "Record a party's signature", () => void this.signContract(m, r, rid));
    btn("🔏 Digitally sign", "Apply a tamper-evident PAdES digital signature to the document", async () => {
      try {
        const res = await api.digitalSignContract(pid, m.key, rid);
        toast(`digitally signed (${res.kind}) · cert ${res.fingerprint.slice(0, 8)}…`, "success");
        void this.openRecord(m, rid);
      } catch (e) { toast(`digital sign failed: ${(e as Error).message}`, "error"); }
    });
    btn("📨 Send for signature", "Route through the configured e-signature provider (DocuSeal etc.)", async () => {
      try {
        const st = await api.esignStatus();
        if (!st.bridge.enabled) { toast(st.bridge.message, "info"); return; }
        const v = await promptModal("Send for signature",
          [{ name: "emails", label: "Signer email(s), comma-separated", required: true }], "Send");
        if (!v) return;
        const signers = (v.emails ?? "").split(",").map((e) => ({ email: e.trim() })).filter((s) => s.email);
        if (!signers.length) return;
        const res = await api.sendForSignature(pid, m.key, rid, signers);
        toast(`sent via ${res.provider} · submission ${res.submission_id ?? "?"}`, "success");
        void this.openRecord(m, rid);
      } catch (e) { toast(`send for signature failed: ${(e as Error).message}`, "error"); }
    });
    const sigs = (r.data?.signatures as { party: string; name: string }[] | undefined) ?? [];
    const dsigs = (r.data?.digital_signatures as { signer: string; fingerprint: string }[] | undefined) ?? [];
    if (sigs.length || dsigs.length) {
      const s = document.createElement("span"); s.className = "meta"; s.style.marginLeft = "6px";
      const parts = [];
      if (sigs.length) parts.push("✓ signed: " + sigs.map((x) => `${x.party} (${x.name})`).join(", "));
      if (dsigs.length) parts.push("🔏 digitally signed (" + dsigs.length + ")");
      s.textContent = parts.join(" · ");
      tools.appendChild(s);
    }
  }

  /**
   * Compose Exhibit A — pick clauses, preview the assembled exhibit, then generate the PDF.
   *
   * NARROW BY TRADE, BECAUSE THE CATALOG OUTGREW THE PICKER
   *     The library is 249 clauses across 21 MasterFormat divisions. This used to load all of them
   *     into one flat 300px-tall checkbox list, which asks somebody to assemble a plumbing
   *     subcontract from a list where the overwhelming majority of entries belong to other trades.
   *     Passing the record's trade narrows it server-side — 249 -> 85 for plumbing — and the header
   *     says which division it narrowed to, so a wrong trade on the record is visible rather than
   *     silently producing a short exhibit.
   *
   * THE INITIAL SELECTION COMES FROM THE SERVER, WHICH IS THE BUG THIS REPLACES
   *     The previous default was computed here:
   *         `cb.checked = cl.category !== "Scope" || !trade || (cl.trade ?? "").toLowerCase() === trade`
   *     The imported clauses carry no `trade` key at all — only body/category/default/division/id/
   *     position/title — so that comparison was false for every one of the 242 imported clauses. The
   *     dialog therefore opened with **every exclusion and every conditions clause ticked and almost
   *     no scope clauses**, which is close to the opposite of a sensible subcontract exhibit. It was
   *     a second selection rule that disagreed with the server's `default_ids`. Now there is one
   *     rule: `scopeExhibit({trade})` returns the default selection and the boxes start there.
   *
   * EXCLUSIONS ARE AS PROMINENT AS INCLUSIONS
   *     The point of the library gaining exclusions (69 of them) is that a subcontract can state what
   *     is NOT included — that is where scope gaps come from. So the picker groups by category rather
   *     than running them together, and the preview leads with the counts.
   */
  /**
   * `estimate.basis` -> the phase key `est_confidence._PHASE_CONF` scores against.
   *
   * **Explicit, because lowercasing is wrong for two of the five and wrong in the flattering
   * direction.** The register offers `Conceptual · Schematic · DD · CD · GMP`; the scorer keys on
   * `concept · sd · dd · cd · gmp`. `DD`/`CD`/`GMP` survive a `.toLowerCase()`, but `"conceptual"`
   * and `"schematic"` match nothing and fall to the unspecified default of **0.6** — which scores a
   * concept estimate (0.45) as *more* confident than a schematic one (0.6), and rates the roughest
   * estimates in the system above what they are. A silent default that flatters is worse than one
   * that fails.
   */
  private static PHASE_FROM_BASIS: Record<string, string> = {
    Conceptual: "concept", Schematic: "sd", DD: "dd", CD: "cd", GMP: "gmp",
  };

  /**
   * EST-REACH — the estimate register's line items had analyses built for them and no way in.
   *
   * `line_items` carries `code · description · qty · unit · unit_cost · amount · source · quote_ref
   * · basis_date`, and its `source` options are `allowance / parametric / historical / quote` —
   * every one a key in the confidence scorer's own source table. The data model and the endpoints
   * were built for each other; only the UI between them was missing.
   *
   * **A Basis-of-Estimate view was here and was deliberately removed.** `budget.ts` already reads
   * every estimate record project-wide and calls `estimateBoe`, mapping `code -> cost_code` and
   * `amount -> total` — the seam `commercial_drift.ESTIMATE_TO_BOE` documents server-side. Adding a
   * per-record view meant a SECOND copy of that mapping on the client, and a duplicated mapping is
   * the defect this whole ring exists to remove, not a feature. "Is *this* estimate defensible" is a
   * real and different question from "is our estimating defensible", but if it earns a view it
   * should call that same seam rather than re-derive it.
   *
   * Deliberately reads the record's OWN line items rather than offering a paste box. A caller that
   * needs the user to hand-assemble its input is a caller in name only.
   */
  private estimateActions(m: ModuleDef, r: ModuleRecord, tools: HTMLElement) {
    if (m.key !== "estimate") return;
    const pid = this.ctx.host.projectId()!;
    const api = this.ctx.host.api;
    const rows = (r.data?.line_items as Record<string, unknown>[] | undefined) ?? [];
    const basis = String(r.data?.basis ?? "");
    const phase = RegisterUI.PHASE_FROM_BASIS[basis] ?? "";

    // Column names to what the endpoints read. `amount` is the table's total column, and the scorer
    // takes `cost` OR `total` OR qty x unit_cost — sending both names costs nothing and means a row
    // with only a computed amount is still weighted rather than silently counting as zero.
    const lines = rows.map((row) => ({
      cost_code: row.code ?? null, description: row.description ?? "",
      qty: row.qty ?? null, unit: row.unit ?? null, unit_cost: row.unit_cost ?? null,
      cost: row.amount ?? null, total: row.amount ?? null,
      source: row.source ?? "", phase,
      quote_ref: row.quote_ref ?? null, basis_date: row.basis_date ?? null,
    }));

    const btn = (label: string, title: string, fn: () => void) => {
      const b = document.createElement("button");
      b.className = "tool-btn"; b.textContent = label; b.title = title; b.onclick = fn;
      tools.appendChild(b);
    };
    const guard = () => {
      if (!lines.length) { toast("this estimate has no line items yet", "error"); return false; }
      return true;
    };

    btn("◎ Confidence", "Score each line's maturity from its source and the estimate basis — and how much of the budget is still assumption-based", () => {
      if (!guard()) return;
      void this.estimateConfidenceView(pid, lines, basis, phase);
    });
    // Priced from the space-program register, not from this record's lines — a concept budget exists
    // precisely for the stage BEFORE there are line items, so it must not be gated on `guard()`.
    btn("◫ Concept budget", "Price the space program by use against a $/area rate — before there are line items", () => {
      void this.conceptBudgetView(pid);
    });
    void api;      // the views resolve the client off `this.ctx.host.api` themselves
  }

  /**
   * Concept budget: the space-program register priced by use.
   *
   * The endpoint wants `program: [{use, gfa, stories?}]`, and the `space_program` register already
   * holds exactly that in another shape — `space_type` with `target_area_sf` per unit and a
   * `quantity`. Aggregating by type is the whole mapping; there was never any missing data, only a
   * missing path between two registers.
   *
   * `history` is deliberately not sent. The endpoint derives per-type rates from a firm's completed
   * projects, and this codebase has no completed-project cost history to draw on — inventing one to
   * make the call look richer would price a real budget off fabricated comparables. Without it the
   * endpoint prices at `default_rate` and **surfaces what it could not price rather than guessing**,
   * which is the honest behaviour and the one worth surfacing in the UI.
   */
  private async conceptBudgetView(pid: string) {
    let recs;
    try { recs = await this.ctx.host.api.moduleRecords(pid, "space_program"); }
    catch (e) { toast(`could not read the space program: ${(e as Error).message}`, "error"); return; }
    const byUse = new Map<string, number>();
    for (const rec of recs) {
      const d = (rec.data ?? {}) as Record<string, unknown>;
      const use = String(d.space_type ?? "").trim();
      if (!use) continue;
      const each = Number(d.target_area_sf ?? 0) || 0;
      const qty = Number(d.quantity ?? 1) || 1;
      if (each <= 0) continue;
      byUse.set(use, (byUse.get(use) ?? 0) + each * qty);
    }
    const program = [...byUse].map(([use, gfa]) => ({ use, gfa }));
    if (!program.length) {
      toast("the space program register has no sized spaces yet — add Type and Target Area", "error");
      return;
    }
    const v = await promptModal("Concept budget", [
      { name: "rate", label: `$/sf where a use has no rate (${program.length} uses, ${usd([...byUse.values()].reduce((a, b) => a + b, 0))} sf)`, required: true },
      { name: "contingency", label: "Contingency %" },
    ], "Price");
    if (!v) return;
    const rate = Number(v.rate);
    if (!Number.isFinite(rate) || rate <= 0) { toast("rate must be a positive number", "error"); return; }
    let b;
    try {
      b = await this.ctx.host.api.estimateConceptBudget(pid, {
        program, default_rate: rate, contingency_pct: Number(v.contingency) || 0,
      });
    } catch (e) { toast(`concept budget failed: ${(e as Error).message}`, "error"); return; }

    const { card } = modalShell("Concept budget", 480);
    const head = document.createElement("div");
    head.style.cssText = "font-weight:600;font-size:14px";
    head.textContent = usd(b.total);
    const sub = document.createElement("div"); sub.className = "meta";
    sub.textContent = `${b.line_count} uses · subtotal ${usd(b.subtotal)}`
      + (b.contingency ? ` + ${b.contingency_pct}% contingency ${usd(b.contingency)}` : "");
    card.append(head, sub);

    // `unpriced` is a COUNT, and it is the number that matters: a total computed over a program the
    // endpoint could not fully price is not a budget, it is a partial one, and it must not read as
    // complete. Verified against the endpoint — with no default rate all three lines come back
    // unpriced with `total = 0`, which would otherwise render as a confident "$0".
    if (b.unpriced > 0) {
      const warn = document.createElement("div"); warn.className = "meta";
      warn.style.cssText = "margin-top:4px;font-weight:600";
      warn.textContent = `${b.unpriced} of ${b.line_count} uses could not be priced — the total below excludes them`;
      card.appendChild(warn);
    }

    for (const l of b.lines) {
      const row = document.createElement("div"); row.className = "meta";
      row.style.cssText = "display:flex;gap:8px;border-top:1px solid var(--line);padding:4px 0";
      row.append(
        Object.assign(document.createElement("span"), { textContent: l.use, style: "flex:1" }),
        Object.assign(document.createElement("span"), { textContent: `${Math.round(l.gfa).toLocaleString()} sf` }),
        // The endpoint says WHY a line is unpriced; passing that through beats rendering a blank.
        Object.assign(document.createElement("span"), { textContent: l.source, style: "flex:1;text-align:right" }),
        Object.assign(document.createElement("span"), {
          textContent: l.cost == null ? "—" : usd(l.cost),
          style: l.cost == null ? "color:var(--muted)" : "",
        }),
      );
      card.appendChild(row);
    }
  }

  /** Confidence rollup: project score, how much is still assumption-based, and the softest lines. */
  private async estimateConfidenceView(pid: string, lines: Record<string, unknown>[], basis: string, phase: string) {
    let c;
    try { c = await this.ctx.host.api.estimateConfidence(pid, lines); }
    catch (e) { toast(`confidence failed: ${(e as Error).message}`, "error"); return; }
    const { card } = modalShell("Estimate confidence", 460);
    const head = document.createElement("div");
    head.style.cssText = "font-weight:600;font-size:14px";
    head.textContent = `${confidenceReading(c).confidencePct}% confidence · ${c.band}`;
    const sub = document.createElement("div"); sub.className = "meta";
    // The phase is stated, not assumed. An unmapped basis scores against the scorer's neutral
    // default, and saying so is the difference between a number and a number you can act on.
    sub.textContent = `${c.line_count} lines · ${usd(c.total_cost)} · `
      + (phase ? `basis “${basis}” → phase ${phase}` : `basis “${basis || "unset"}” — phase unspecified, scored at the neutral default`);
    card.append(head, sub);

    const kpi = document.createElement("div"); kpi.className = "meta"; kpi.style.marginTop = "6px";
    // BOE-MAPPING-DEDUP: the units are applied ONCE, in `ui/confidenceReading.ts`, and asserted by
    // `confidenceReading.test.ts`. They are not consistent across this one response —
    // `pct_assumption_based` is a fraction despite the name, `avg_contingency_pct` is already a
    // percentage — and that knowledge used to live as a comment here AND in the budget panel, where
    // the copy dropped the scaling and rendered "1%" for a 72%-unsupported budget.
    const cr = confidenceReading(c);
    kpi.innerHTML = `<b>${cr.assumptionBasedPct}%</b> of budget still assumption-based `
      + `(${esc(usd(cr.assumptionBasedCost))}) · avg contingency ${cr.avgContingencyPct}%`;
    card.appendChild(kpi);

    const soft = c.worst_lines;
    if (soft.length) {
      const h = document.createElement("div");
      h.style.cssText = "font-weight:600;margin-top:8px;font-size:12.5px";
      h.textContent = "Least grounded, by value";
      card.appendChild(h);
      for (const l of soft.slice(0, 10)) {
        const row = document.createElement("div"); row.className = "meta";
        row.style.cssText = "display:flex;gap:8px;border-top:1px solid var(--line);padding:4px 0";
        row.append(
          Object.assign(document.createElement("span"), { textContent: l.description || "(no description)", style: "flex:1" }),
          Object.assign(document.createElement("span"), { textContent: l.source }),
          Object.assign(document.createElement("span"), { textContent: usd(l.cost) }),
        );
        card.appendChild(row);
      }
    }
  }


  private async composeExhibit(m: ModuleDef, r: ModuleRecord, rid: string) {
    const pid = this.ctx.host.projectId()!;
    const api = this.ctx.host.api;
    const trade = (r.data?.trade as string | undefined)?.trim() || undefined;

    let lib: Awaited<ReturnType<typeof api.scopeLibrary>>;
    let def: Awaited<ReturnType<typeof api.scopeExhibit>>;
    try {
      // Both narrowed by the same trade. The catalog fills the picker; the exhibit supplies which
      // boxes start ticked, so the default cannot disagree with what the document would render.
      [lib, def] = await Promise.all([api.scopeLibrary({ trade }), api.scopeExhibit({ trade })]);
    } catch { toast("couldn't load scope library", "error"); return; }

    const { card } = modalShell("Compose Exhibit A — Scope of Work", 460);
    // OFFER ONLY WHAT EXHIBIT A CAN HOLD, using the server's own definition.
    //
    // `library(division)` returns clauses whose division matches **or is None**, and every `gc-*` /
    // `sc-*` conditions clause has division None — so even a narrowed catalog contains clauses the
    // exhibit renderer drops. Listing them gives the user a tick that silently does nothing, which is
    // a worse failure than a wrong document: it teaches them the control is broken.
    //
    // Filtered by `lib.exhibit_categories` rather than a literal here. Hardcoding
    // {"Scope","Exclusions","Clarifications"} would be a second copy of the rule, and a second copy
    // of *this exact rule* is what let the preview and the PDF disagree by 20 clauses.
    const offerable = lib.clauses.filter((c) => lib.exhibit_categories.includes(c.category));

    const scope = document.createElement("div"); scope.className = "meta";
    scope.textContent = lib.division
      ? `${offerable.length} clauses · Division ${lib.division} — ${lib.division_name ?? ""} (from trade “${trade}”)`
      : `${offerable.length} clauses · whole catalog — no division for ${trade ? `trade “${trade}”` : "an unset trade"}`;
    card.appendChild(scope);

    const preselected = new Set(def.clauses.map((c) => c.id));
    const boxes: Record<string, HTMLInputElement> = {};
    const list = document.createElement("div");
    list.style.cssText = "max-height:300px;overflow:auto;display:flex;flex-direction:column;gap:2px;margin:6px 0";


    // Grouped, with Exclusions given the same standing as Scope rather than being buried mid-list.
    const byCat = new Map<string, typeof lib.clauses>();
    for (const cl of offerable) {
      const bucket = byCat.get(cl.category);
      if (bucket) bucket.push(cl); else byCat.set(cl.category, [cl]);
    }
    const CAT_ORDER = ["Scope", "Exclusions", "Clarifications"];
    const cats = [...byCat.keys()].sort((a, b) => {
      const ia = CAT_ORDER.indexOf(a), ib = CAT_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    });
    for (const cat of cats) {
      const items = byCat.get(cat)!;
      const head = document.createElement("div");
      head.style.cssText = "display:flex;align-items:center;gap:6px;margin-top:6px;font-weight:600;font-size:12px";
      const all = document.createElement("input"); all.type = "checkbox"; all.title = `Select all ${cat}`;
      head.append(all, Object.assign(document.createElement("span"), { textContent: `${cat} (${items.length})` }));
      list.appendChild(head);
      const mine: HTMLInputElement[] = [];
      for (const cl of items) {
        const row = document.createElement("label");
        row.style.cssText = "display:flex;gap:6px;align-items:flex-start;font-size:12.5px;padding-left:14px";
        const cb = document.createElement("input"); cb.type = "checkbox";
        cb.checked = preselected.has(cl.id);
        boxes[cl.id] = cb; mine.push(cb);
        row.append(cb, Object.assign(document.createElement("span"), { textContent: cl.title }));
        list.appendChild(row);
      }
      const sync = () => { all.checked = mine.every((c) => c.checked); all.indeterminate = !all.checked && mine.some((c) => c.checked); };
      all.onclick = () => { for (const c of mine) c.checked = all.checked; };
      for (const c of mine) c.addEventListener("change", sync);
      sync();
    }
    card.appendChild(list);

    const picked = () => Object.entries(boxes).filter(([, b]) => b.checked).map(([id]) => id);
    const out = document.createElement("div");
    out.style.cssText = "max-height:260px;overflow:auto;border-top:1px solid var(--line);margin-top:6px;padding-top:6px;display:none";
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;align-items:center;margin-top:4px";

    const prev = document.createElement("button"); prev.className = "file-btn"; prev.textContent = "Preview exhibit";
    prev.onclick = async () => {
      const ids = picked();
      if (!ids.length) { toast("select at least one clause", "error"); return; }
      let ex: Awaited<ReturnType<typeof api.scopeExhibit>>;
      try { ex = await api.scopeExhibit({ trade, clauses: ids }); }
      catch (e) { toast(`preview failed: ${(e as Error).message}`, "error"); return; }
      out.textContent = ""; out.style.display = "block";
      const counts = document.createElement("div"); counts.className = "meta"; counts.style.marginBottom = "4px";
      // Exclusions called out by name: "12 clauses" hides whether any exclusion survived the picking.
      counts.textContent = Object.entries(ex.counts).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(" · ")
        || "nothing to render";
      counts.style.fontWeight = "600";
      out.appendChild(counts);
      for (const c of ex.clauses) {
        const h = document.createElement("div");
        h.style.cssText = "font-weight:600;font-size:12.5px;margin-top:6px";
        h.textContent = `${c.number} ${c.title}`;
        const b = document.createElement("div");
        b.style.cssText = "font-size:12px;white-space:pre-wrap;color:var(--muted)";
        b.textContent = c.body;
        out.append(h, b);
      }
    };

    const open = document.createElement("button"); open.className = "file-btn"; open.textContent = "Generate PDF";
    open.onclick = () => {
      const ids = picked();
      if (!ids.length) { toast("select at least one clause", "error"); return; }
      window.open(api.contractDocUrl(pid, m.key, rid, "exhibit", ids.join(",")), "_blank");
    };
    // The Word copy sits beside the PDF because they are two halves of one exchange, not two
    // features: the PDF is the instrument you sign, the .docx is the one a subcontractor strikes
    // through and sends back. Offering only the PDF pushes the sub into retyping the exhibit, which
    // is where clauses go missing.
    const docx = document.createElement("button");
    docx.className = "file-btn";
    docx.textContent = "Word copy";
    docx.title = "Exhibit A as an editable .docx — the copy a subcontractor redlines and returns";
    docx.onclick = () => {
      const ids = picked();
      if (!ids.length) { toast("select at least one clause", "error"); return; }
      window.open(api.exhibitDocxUrl(pid, m.key, rid, ids.join(",")), "_blank");
    };
    row.append(prev, open, docx);
    card.append(row, out);
  }

  private async signContract(m: ModuleDef, r: ModuleRecord, rid: string) {
    const pid = this.ctx.host.projectId()!;
    const { card, close } = modalShell("Sign " + r.ref, 300);
    const party = document.createElement("select"); party.className = "portal-filter";
    for (const p of ["GC", "Owner", "OwnersRep", "Consultant", "Subcontractor"]) party.appendChild(Object.assign(document.createElement("option"), { value: p, textContent: p }));
    const name = document.createElement("input"); name.className = "portal-filter"; name.placeholder = "Full name";
    const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Sign";
    go.onclick = async () => {
      if (!name.value.trim()) { toast("enter a name", "error"); return; }
      try { await this.ctx.host.api.signContract(pid, m.key, rid, party.value, name.value.trim()); close(); toast("signed", "success"); void this.openRecord(m, rid); }
      catch (e) { toast(`sign failed: ${(e as Error).message}`, "error"); }
    };
    card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: "Record a typed signature:" }), party, name, go);
  }

  private async rfiTriage(rid: string) {
    const pid = this.ctx.host.projectId()!;
    let t;
    try { t = await this.ctx.host.api.triageRfi(pid, rid); }
    catch (e) { toast(`triage failed: ${(e as Error).message}`, "error"); return; }
    const { card } = modalShell("RFI triage (AI)", 360);
    if (!t.ai_enabled) card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: "AI not configured — showing a template suggestion." }));
    const kv = (k: string, v: string) => { const d = document.createElement("div"); d.className = "meta"; d.innerHTML = `<b>${k}:</b> `; d.append(v); card.appendChild(d); };
    kv("Discipline", t.discipline); kv("Category", t.category); kv("Urgency", t.urgency); kv("Ball-in-court", t.ball_in_court);
    const h = document.createElement("div"); h.className = "meta"; h.style.marginTop = "6px"; h.innerHTML = "<b>Draft response:</b>"; card.appendChild(h);
    const body = document.createElement("div"); body.style.cssText = "white-space:pre-wrap;font-size:12.5px"; body.textContent = t.draft_response; card.appendChild(body);
  }

  private async openPermitImport(m: ModuleDef) {
    const pid = this.ctx.host.projectId()!;
    const { card } = modalShell("Import permits from city open data", 420);
    const note = (t: string) => card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: t }));
    note("Pull a city's building-permit filings for the site and add them to this log (source-tagged, deduped on re-import).");
    const sel = document.createElement("select"); sel.className = "portal-filter"; sel.style.width = "100%";
    sel.innerHTML = `<option value="">Loading cities…</option>`;
    card.appendChild(sel);
    const field = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "width:100%;margin-top:6px"; card.appendChild(i); return i; };
    const addr = field("Address or keyword (e.g. street name) — optional");
    const geoRow = document.createElement("div"); geoRow.style.cssText = "display:flex;gap:6px;margin-top:6px"; card.appendChild(geoRow);
    const lat = Object.assign(document.createElement("input"), { className: "portal-filter", placeholder: "lat (optional)" });
    const lon = Object.assign(document.createElement("input"), { className: "portal-filter", placeholder: "lon (optional)" });
    const rad = Object.assign(document.createElement("input"), { className: "portal-filter", placeholder: "radius m", value: "1500" });
    for (const el of [lat, lon, rad]) { el.style.flex = "1"; geoRow.appendChild(el); }
    const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "8px"; card.appendChild(out);
    let cities: { id: string; label: string; geo: boolean }[] = [];
    try { cities = (await this.ctx.host.api.permitCities()).cities; }
    catch (e) { out.textContent = `Could not load cities: ${(e as Error).message}`; }
    sel.innerHTML = cities.map((c) => `<option value="${esc(c.id)}">${esc(c.label)}${c.geo ? "" : " (text search only)"}</option>`).join("");
    const opts = () => ({
      city: sel.value, address: addr.value.trim() || undefined,
      lat: lat.value ? Number(lat.value) : undefined, lon: lon.value ? Number(lon.value) : undefined,
      radius: rad.value ? Number(rad.value) : undefined,
    });
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:10px";
    const preview = document.createElement("button"); preview.className = "tool-btn"; preview.textContent = "Preview";
    preview.onclick = async () => {
      out.textContent = "searching…";
      try { const r = await this.ctx.host.api.opendataPermits(pid, { ...opts(), limit: 50 });
        out.textContent = r.count ? `${r.count} filing(s) found — first: ${r.permits[0]?.address ?? r.permits[0]?.permit_number}` : "No filings found — try an address/keyword or coordinates.";
      } catch (e) { out.textContent = `Search failed: ${(e as Error).message}`; }
    };
    const imp = document.createElement("button"); imp.className = "file-btn"; imp.textContent = "Import";
    imp.onclick = async () => {
      out.textContent = "importing…";
      try { const r = await this.ctx.host.api.importOpendataPermits(pid, { ...opts(), max: 50 });
        toast(`Imported ${r.imported} permit(s)${r.skipped ? `, skipped ${r.skipped} duplicate(s)` : ""}`, "success");
        void this.openModule(m);
      } catch (e) { out.textContent = `Import failed: ${(e as Error).message}`; }
    };
    row.append(preview, imp); card.appendChild(row);
  }

  async openRecord(m: ModuleDef, rid: string) {
    const pid = this.ctx.host.projectId()!;
    const r = await this.ctx.host.api.moduleRecord(pid, m.key, rid);
    this.ctx.root.innerHTML = "";
    this.ctx.root.appendChild(this.ctx.bar(`${r.ref}`, () => this.openModule(m)));

    const head = document.createElement("div");
    const ball = this.ballInCourt(m, r.workflow_state);
    head.innerHTML = `<div class="portal-rec-title">${esc(r.title ?? r.ref)}</div>` +
      `<div class="meta">status <span class="badge">${esc(r.workflow_state)}</span> · ${esc(r.party_owner ?? "")}` +
      (ball.length ? ` · ball-in-court ${ball.map((p) => `<span class="ball-badge">${esc(p)}</span>`).join(" ")}` : "") +
      `</div>`;
    // revision chain: this record's number + links to prior / superseding revision
    if (r.revision && (r.revision.number || r.revision.revises || r.revision.superseded_by)) {
      const rev = document.createElement("div"); rev.className = "meta";
      rev.append(`Revision ${r.revision.number}`);
      const link = (label: string, b: RecordBrief | null) => {
        if (!b) return;
        rev.append(` · ${label} `);
        const a = document.createElement("a"); a.href = "#"; a.className = "ref-link"; a.textContent = b.ref;
        a.onclick = (e) => { e.preventDefault(); this.openByBrief(b.module, b.id); };
        rev.append(a);
      };
      link("supersedes", r.revision.revises);
      link("superseded by", r.revision.superseded_by);
      head.appendChild(rev);
    }
    // R41-SCHEMA-STALE: this record's payload no longer means what the register's current schema
    // says. Named here rather than left to the field list, because the field list is exactly where
    // the failure HIDES — an orphaned value renders as an empty field, indistinguishable from one
    // nobody filled in. The banner itself is a pure function so it can be tested on its rendering.
    const staleWarn = schemaStaleBanner(r.schema, r.data);
    if (staleWarn) head.appendChild(staleWarn);
    this.ctx.root.appendChild(head);

    const tools = document.createElement("div"); tools.style.cssText = "display:flex;gap:6px;margin:4px 0;flex-wrap:wrap";
    const editBtn = document.createElement("button");
    editBtn.className = "tool-btn"; editBtn.textContent = "✎ Edit";
    editBtn.onclick = () => this.renderForm(m, r);
    const delBtn = document.createElement("button");
    delBtn.className = "tool-btn"; delBtn.textContent = "🗑 Delete";
    delBtn.onclick = async () => {
      if (!(await confirmModal(`Delete ${r.ref}? This cannot be undone.`, "", "Delete", true))) return;
      try { await this.ctx.host.api.deleteModuleRecord(pid, m.key, rid); this.ctx.host.setStatus(`deleted ${r.ref}`); this.ctx.host.onPinsChanged(); void this.openModule(m); }
      catch (e) { this.ctx.host.setStatus(`error: ${(e as Error).message}`); }
    };
    const pdfBtn = document.createElement("button");
    pdfBtn.className = "tool-btn"; pdfBtn.textContent = "↓ PDF";
    pdfBtn.onclick = () => window.open(this.ctx.host.api.url(`/projects/${pid}/modules/${m.key}/${rid}/pdf`), "_blank");
    const pdfMk = document.createElement("button");
    pdfMk.className = "tool-btn"; pdfMk.textContent = "🖊 Markup";
    pdfMk.title = "Open the record PDF in the in-app viewer to mark up (saves back as an attachment)";
    pdfMk.onclick = async () => {
      const { openPdfUrl } = await import("../../drawings/openPdf");
      await openPdfUrl(this.ctx.host.api, this.ctx.host.api.url(`/projects/${pid}/modules/${m.key}/${rid}/pdf`), `${r.ref}.pdf`, {
        saveLabel: "Attach marked-up copy",
        onSave: async (blob, name) => { await this.ctx.host.api.uploadAttachment(pid, m.key, rid, new File([blob], name.replace(/\.pdf$/i, "") + "-markup.pdf", { type: "application/pdf" })); void this.openRecord(m, rid); },
      });
    };
    tools.append(editBtn, delBtn, pdfBtn, pdfMk);
    if (m.revisable) {
      const reviseBtn = document.createElement("button");
      reviseBtn.className = "tool-btn"; reviseBtn.dataset.cap = "review";
      const superseded = !!r.revision?.superseded_by;
      reviseBtn.textContent = "⎘ Revise"; reviseBtn.disabled = superseded;
      reviseBtn.title = superseded ? "Already revised" : "Create a tracked revision (re-opens the workflow)";
      reviseBtn.onclick = async () => {
        if (!(await confirmModal(`Create a revision of ${r.ref}? It re-opens the workflow as a new record (${r.ref}.${(r.revision?.number ?? 0) + 1}).`, ""))) return;
        try { const nv = await this.ctx.host.api.reviseRecord(pid, m.key, rid); this.ctx.host.setStatus(`created ${nv.ref}`); void this.openRecord(m, nv.id); }
        catch (e) { this.ctx.host.setStatus(`revise failed: ${(e as Error).message}`); }
      };
      tools.append(reviseBtn);
    }
    // C1 — convert-to buttons (offered when the source state/data warrants it)
    for (const c of CONVERSIONS[m.key] ?? []) {
      if (c.when && !c.when(r.data)) continue;
      const tgt = this.ctx.mods.find((x) => x.key === c.to); if (!tgt) continue;
      const cb = document.createElement("button");
      cb.className = "tool-btn"; cb.textContent = `⤳ ${c.label}`;
      cb.title = `Create a ${tgt.name} from this ${m.name}, linked back`;
      cb.onclick = () => this.convert(m, r, c);
      tools.append(cb);
    }
    this.contractActions(m, r, rid, tools);
    this.estimateActions(m, r, tools);
    if (m.key === "rfi") {
      const tb = document.createElement("button");
      tb.className = "tool-btn"; tb.textContent = "✨ Triage (AI)"; tb.title = "AI: categorize + ball-in-court + draft response";
      tb.onclick = () => void this.rfiTriage(rid);
      tools.appendChild(tb);
    }
    this.ctx.root.appendChild(tools);

    // photo-heavy field modules put photos up top (the super's first action on the record)
    const photoFirst = ["daily_report", "punchlist", "inspection", "observation", "incident"].includes(m.key);
    if (photoFirst) this.renderAttachments(m, r, rid);

    // fields (reference fields render as clickable links to the target record)
    const fields = document.createElement("div"); fields.className = "portal-kv";
    for (const f of m.fields) {
      const v = r.data[f.name];
      if (v === undefined || v === "") continue;
      if (f.type === "reference") {
        const ref = r.data_refs?.[f.name];
        const k = document.createElement("div"); k.className = "k"; k.textContent = f.label;
        const vd = document.createElement("div"); vd.className = "v";
        if (ref) {
          const a = document.createElement("a"); a.href = "#"; a.className = "ref-link";
          a.textContent = `${ref.ref} — ${ref.title ?? ""}`;
          a.onclick = (e) => { e.preventDefault(); this.openByBrief(ref.module, ref.id); };
          vd.appendChild(a);
        } else vd.textContent = String(v);
        fields.append(k, vd);
      } else if (f.type === "signature") {
        fields.insertAdjacentHTML("beforeend",
          `<div class="k">${esc(f.label)}</div><div class="v"><img src="${esc(v)}" style="max-width:200px;border:1px solid var(--line);background:#fff"/></div>`);
      } else {
        // field values are user data — escape everything interpolated into HTML (stored-XSS guard)
        let disp = esc(v);
        if (f.type === "currency") disp = `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
        else if (f.type === "multiselect" && Array.isArray(v)) disp = (v as string[]).map((x) => `<span class="chip">${esc(x)}</span>`).join(" ");
        else if (f.type === "rollup") disp = `<span class="computed">${Number(v).toLocaleString()}</span>`;
        fields.insertAdjacentHTML("beforeend", `<div class="k">${esc(f.label)}</div><div class="v">${disp}</div>`);
      }
    }
    this.ctx.root.appendChild(fields);

    // assignee + reassign
    const asgRow = document.createElement("div"); asgRow.className = "meta"; asgRow.style.margin = "4px 0";
    asgRow.innerHTML = `Assignee: <b>${r.assignee ?? "—"}</b> `;
    const reassign = document.createElement("button"); reassign.className = "tool-btn"; reassign.textContent = "Reassign";
    reassign.style.marginLeft = "6px";
    reassign.onclick = async () => {
      const v = await promptModal("Reassign record",
        [{ name: "who", label: "Assign to (user id, blank to clear)", value: r.assignee ?? "" }]);
      if (!v) return;
      try { await this.ctx.host.api.assignRecord(pid, m.key, rid, v.who?.trim() || null); void this.openRecord(m, rid); }
      catch (e) { this.ctx.host.setStatus(`error: ${(e as Error).message}`); }
    };
    asgRow.appendChild(reassign);
    this.ctx.root.appendChild(asgRow);

    // attachments (files in object storage)
    if (!photoFirst) this.renderAttachments(m, r, rid);

    // related records (outgoing references + incoming records that point here)
    const relatedBox = document.createElement("div");
    this.ctx.root.appendChild(relatedBox);
    void this.renderRelated(relatedBox, m.key, rid);

    appendRecordElementTies(this.ctx.root, this.ctx.host, m, r, rid, () => void this.openRecord(m, rid));

    // workflow actions (server-gated by party)
    const acts = r.available_actions ?? [];
    if (acts.length) {
      const ad = document.createElement("div"); ad.className = "section-title"; ad.textContent = "Workflow";
      this.ctx.root.appendChild(ad);
      this.ctx.root.appendChild(this.workflowMap(m, r.workflow_state));   // visual state diagram
      const labelOf = (f: string) => m.fields.find((x) => x.name === f)?.label ?? f;
      for (const a of acts) {
        // transition field-gate: which required fields are still empty on this record
        const missing = (a.requires ?? []).filter((f) => {
          const v = (r.data ?? {})[f]; return v === undefined || v === null || v === "";
        });
        const b = document.createElement("button"); b.className = "tool-btn";
        b.textContent = `${a.action} → ${a.to}` + (missing.length ? ` (needs ${missing.map(labelOf).join(", ")})` : "");
        b.style.cssText = "display:block;margin:3px 0;width:100%;text-align:left";
        b.disabled = missing.length > 0;
        if (missing.length) b.title = `Fill ${missing.map(labelOf).join(", ")} before ${a.action}`;
        b.onclick = async () => {
          try { await this.ctx.host.api.transitionRecord(pid, m.key, rid, a.action); void this.openRecord(m, rid); }
          catch (e) { this.ctx.host.setStatus(`blocked: ${(e as Error).message}`); }
        };
        this.ctx.root.appendChild(b);
      }
    }

    // linked records (change-order chain)
    if (r.links?.length) {
      const ld = document.createElement("div"); ld.className = "section-title"; ld.textContent = "Linked";
      this.ctx.root.appendChild(ld);
      for (const l of r.links) {
        const e = document.createElement("div"); e.className = "meta"; e.textContent = `${l.module}: ${l.ref}`;
        this.ctx.root.appendChild(e);
      }
    }

    // comments
    const cd = document.createElement("div"); cd.className = "section-title"; cd.textContent = "Comments";
    this.ctx.root.appendChild(cd);
    for (const cm of r.comments ?? []) {
      const e = document.createElement("div"); e.className = "portal-act";
      e.textContent = `${cm.author ?? ""}: ${cm.text}`;
      this.ctx.root.appendChild(e);
    }
    const ta = document.createElement("textarea");
    ta.className = "portal-field"; ta.placeholder = "Add a comment…"; ta.style.width = "100%";
    const addBtn = document.createElement("button");
    addBtn.className = "tool-btn"; addBtn.textContent = "Comment"; addBtn.style.margin = "4px 0";
    addBtn.onclick = async () => {
      if (!ta.value.trim()) return;
      await this.ctx.host.api.addComment(pid, m.key, rid, ta.value.trim());
      void this.openRecord(m, rid);
    };
    this.ctx.root.append(ta, addBtn);

    // activity timeline
    const td = document.createElement("div"); td.className = "section-title"; td.textContent = "Activity";
    this.ctx.root.appendChild(td);
    for (const a of r.activity ?? []) {
      const e = document.createElement("div"); e.className = "portal-act";
      e.textContent = `${(a.ts || "").slice(0, 16).replace("T", " ")} · ${a.actor ?? ""} · ${a.action}`;
      this.ctx.root.appendChild(e);
    }
  }

  /** Open a record given a module key + id (used by reference + related links). */
  openByBrief(moduleKey: string, id: string) {
    const m = this.ctx.mods.find((x) => x.key === moduleKey);
    if (m) void this.openRecord(m, id);
  }
  /** Render the outgoing/incoming relation graph for a record into `box`. */
  private async renderRelated(box: HTMLElement, key: string, rid: string) {
    const pid = this.ctx.host.projectId()!;
    let rel;
    try { rel = await this.ctx.host.api.relatedRecords(pid, key, rid); }
    catch { return; }
    if (!rel.outgoing.length && !rel.incoming.length) return;
    box.innerHTML = "";
    type Brief = { module: string; module_name: string; id: string; ref: string; title: string | null; state: string; label?: string | null };
    // Two labelled, counted directions so "what this record points to" reads distinctly from "what
    // points back at it" (the incoming side is the dependency signal — e.g. the change orders raised
    // against this budget line). textContent/esc throughout: ref+title are user data (stored-XSS guard).
    const group = (title: string, caption: string, icon: string, items: Brief[], labelOf: (b: Brief) => string) => {
      if (!items.length) return;
      const h = document.createElement("div"); h.className = "section-title"; h.textContent = `${title} (${items.length})`;
      box.appendChild(h);
      const cap = document.createElement("div"); cap.className = "meta"; cap.textContent = caption; box.appendChild(cap);
      for (const b of items) {
        const row = document.createElement("button"); row.className = "portal-mod";
        row.innerHTML = `<span class="ic">${icon}</span> <b>${esc(labelOf(b))}</b> ${esc(b.ref)} ${esc(b.title ?? "")} ${statusChip(b.state)}`;
        row.onclick = () => this.openByBrief(b.module, b.id);
        box.appendChild(row);
      }
    };
    group("References", "Records this one points to.", "↳", rel.outgoing, (b) => b.label ?? b.module_name);
    group("Referenced by", "Records that point to this one — its dependents.", "↰", rel.incoming, (b) => b.module_name);
  }

  /** Attachments section: image thumbnails + file links, with multi-file (bulk) + drag-drop upload —
   *  the field reality is a batch of site photos, not one file at a time. */
  private renderAttachments(m: ModuleDef, r: ModuleRecord, rid: string) {
    const pid = this.ctx.host.projectId()!;
    const atts = r.attachments ?? [];
    const t = document.createElement("div"); t.className = "section-title";
    t.textContent = `Attachments${atts.length ? ` (${atts.length})` : ""}`;
    this.ctx.root.appendChild(t);

    if (atts.length) {
      const gallery = document.createElement("div"); gallery.className = "att-gallery";
      for (const a of atts) {
        const isImg = (a.content_type || "").startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp)$/i.test(a.filename);
        const isPdf = (a.content_type || "").includes("pdf") || /\.pdf$/i.test(a.filename);
        const url = this.ctx.host.api.attachmentUrl(a.id);
        const kb = a.size > 1024 * 1024 ? `${(a.size / 1048576).toFixed(1)} MB` : a.size > 1024 ? `${Math.round(a.size / 1024)} KB` : `${a.size} B`;
        if (isPdf) {
          // open in the in-app viewer for markup; saving posts a marked-up copy back as a new attachment
          const pc = document.createElement("button"); pc.className = "att-cell att-file"; pc.title = `${a.filename} · ${kb} — open in viewer / mark up`;
          pc.innerHTML = `<span class="att-ic">📄</span><span class="att-name">${a.filename}</span>`;
          pc.onclick = async () => {
            const { openPdfUrl } = await import("../../drawings/openPdf");
            await openPdfUrl(this.ctx.host.api, url, a.filename, {
              saveLabel: "Save marked-up copy back",
              onSave: async (blob, nm) => {
                await this.ctx.host.api.uploadAttachment(pid, m.key, rid, new File([blob], nm.replace(/\.pdf$/i, "") + "-markup.pdf", { type: "application/pdf" }));
                void this.openRecord(m, rid);
              },
            });
          };
          gallery.appendChild(pc); continue;
        }
        const cell = document.createElement("a"); cell.className = "att-cell"; cell.href = url; cell.target = "_blank"; cell.title = `${a.filename} · ${kb}`;
        if (isImg) {
          const img = document.createElement("img"); img.src = url; img.loading = "lazy"; img.alt = a.filename; cell.appendChild(img);
        } else {
          cell.classList.add("att-file"); cell.innerHTML = `<span class="att-ic">📎</span><span class="att-name">${a.filename}</span>`;
        }
        gallery.appendChild(cell);
      }
      this.ctx.root.appendChild(gallery);
    }

    const file = document.createElement("input"); file.type = "file"; file.multiple = true;
    file.accept = "image/*,application/pdf,.dwg,.doc,.docx,.xls,.xlsx";
    file.style.display = "none";
    // camera capture — on a phone this opens the camera directly (field photo in one tap)
    const cam = document.createElement("input"); cam.type = "file"; cam.accept = "image/*";
    cam.setAttribute("capture", "environment"); cam.style.display = "none";
    const drop = document.createElement("div"); drop.className = "att-drop";
    drop.innerHTML = `<b>＋ Add photos / files</b><span class="meta">drag &amp; drop a batch, or click to pick multiple</span>`;
    drop.onclick = () => file.click();
    const doUpload = async (files: FileList | File[]) => {
      const list = Array.from(files); if (!list.length) return;
      if (!navigator.onLine) { await this.queueUpload(pid, m.key, rid, list); void this.openRecord(m, rid); return; }
      drop.classList.add("busy"); drop.querySelector("b")!.textContent = `Uploading ${list.length} file${list.length > 1 ? "s" : ""}…`;
      try {
        if (list.length === 1) await this.ctx.host.api.uploadAttachment(pid, m.key, rid, list[0]!); // safe: list.length === 1 checked
        else await this.ctx.host.api.uploadAttachmentsBulk(pid, m.key, rid, list);
        this.ctx.host.setStatus(`attached ${list.length} file${list.length > 1 ? "s" : ""}`); void this.openRecord(m, rid);
      } catch (e) {
        if (!navigator.onLine) { await this.queueUpload(pid, m.key, rid, list); void this.openRecord(m, rid); return; }
        this.ctx.host.setStatus(`upload failed: ${(e as Error).message}`); drop.classList.remove("busy");
      }
    };
    file.onchange = () => { if (file.files) void doUpload(file.files); };
    cam.onchange = () => { if (cam.files) void doUpload(cam.files); };
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer?.files) void doUpload(e.dataTransfer.files); };
    const camBtn = document.createElement("button"); camBtn.className = "tool-btn"; camBtn.textContent = "📷 Take photo";
    camBtn.style.marginTop = "4px"; camBtn.onclick = () => cam.click();
    this.ctx.root.append(file, cam, drop, camBtn);
    const qWarn = document.createElement("div"); qWarn.className = "meta"; qWarn.style.cssText = "color:var(--status-warn);margin-top:3px";
    this.ctx.root.appendChild(qWarn);
    void queuedCountForRecord(rid).then((queued) => {
      qWarn.textContent = queued
        ? `⏳ ${queued} file${queued > 1 ? "s" : ""} queued (offline) — will upload when back online` : "";
    });
  }

  /** Persist an upload that couldn't go out (offline) and flush when the connection returns. */
  private async queueUpload(pid: string, key: string, rid: string, files: File[]) {
    await enqueueUpload({ pid, key, rid, files });
    this.ctx.host.setStatus(`offline — ${files.length} file${files.length > 1 ? "s" : ""} queued, will upload on reconnect`);
    this.hookOnline();
  }

  /** Register the reconnect flush once (also called at startup to drain a prior session's queue). */
  hookOnline() {
    if (this.onlineHooked) return;
    this.onlineHooked = true;
    window.addEventListener("online", () => void this.flushUploads());
  }

  async flushUploads() {
    if (!navigator.onLine) return;
    let done = 0;
    for (const q of await allQueued()) {
      try {
        if (q.files.length === 1) await this.ctx.host.api.uploadAttachment(q.pid, q.key, q.rid, q.files[0]!); // safe: q.files.length === 1 checked
        else await this.ctx.host.api.uploadAttachmentsBulk(q.pid, q.key, q.rid, q.files);
        await dequeue(q.id); done += q.files.length;
      } catch { /* leave it queued for the next reconnect */ }
    }
    if (done) { this.ctx.host.setStatus(`back online — uploaded ${done} queued file${done > 1 ? "s" : ""}`); this.ctx.host.onPinsChanged(); }
  }

  // --- kanban / "scrum" board: columns by workflow state, drag to transition --
  private async renderBoard(m: ModuleDef) {
    const pid = this.ctx.host.projectId()!;
    this.skeleton(`Loading ${m.name} board…`);
    const data = await this.ctx.host.api.moduleBoard(pid, m.key);
    this.ctx.root.innerHTML = "";
    this.ctx.root.appendChild(this.ctx.bar(`${m.name} — board`, () => this.openModule(m)));
    const board = document.createElement("div"); board.className = "kanban";
    for (const state of data.states) {
      const col = document.createElement("div"); col.className = "kan-col"; col.dataset.state = state;
      col.innerHTML = `<div class="kan-head">${state} <span class="count">${(data.columns[state] ?? []).length}</span></div>`;
      // drop target: on drop, find a transition from the card's state -> this column's state
      col.ondragover = (e) => { e.preventDefault(); col.classList.add("over"); };
      col.ondragleave = () => col.classList.remove("over");
      col.ondrop = async (e) => {
        e.preventDefault(); col.classList.remove("over");
        const rid = e.dataTransfer?.getData("rid"); const from = e.dataTransfer?.getData("from");
        if (!rid || from === state) return;
        const tr = data.transitions.find((t) => t.from === from && t.to === state);
        if (!tr) { this.ctx.host.setStatus(`no direct transition ${from} → ${state}`); return; }
        try { await this.ctx.host.api.transitionRecord(pid, m.key, rid, tr.action); void this.renderBoard(m); }
        catch (err) { this.ctx.host.setStatus(`blocked: ${(err as Error).message}`); }
      };
      for (const c of data.columns[state] ?? []) {
        const card = document.createElement("div"); card.className = "kan-card"; card.draggable = true;
        card.innerHTML = `<div class="kc-ref">${c.ref}</div><div class="kc-title">${c.title ?? ""}</div>` +
          (c.assignee ? `<div class="kc-asg">@${c.assignee}</div>` : "");
        card.ondragstart = (e) => { e.dataTransfer?.setData("rid", c.id); e.dataTransfer?.setData("from", state); };
        card.onclick = () => this.openRecord(m, c.id);
        col.appendChild(card);
      }
      board.appendChild(col);
    }
    this.ctx.root.appendChild(board);
  }

  /** Draw-to-sign canvas pad; returns a getter for the signature data-URI ("" if blank). */
  private signaturePad(wrap: HTMLElement): () => string {
    const cv = document.createElement("canvas");
    cv.width = 240; cv.height = 90;
    cv.style.cssText = "display:block;margin-top:4px;border:1px solid var(--line);background:#fff;border-radius:4px;touch-action:none";
    const ctx = cv.getContext("2d")!;
    ctx.strokeStyle = "#111"; ctx.lineWidth = 2; ctx.lineCap = "round";
    let drawing = false, dirty = false;
    cv.onpointerdown = (e) => { drawing = true; ctx.beginPath(); ctx.moveTo(e.offsetX, e.offsetY); };
    cv.onpointermove = (e) => { if (drawing) { ctx.lineTo(e.offsetX, e.offsetY); ctx.stroke(); dirty = true; } };
    cv.onpointerup = () => (drawing = false);
    cv.onpointerleave = () => (drawing = false);
    const clear = document.createElement("button");
    clear.type = "button"; clear.className = "tool-btn"; clear.textContent = "Clear"; clear.style.marginTop = "4px";
    clear.onclick = () => { ctx.clearRect(0, 0, cv.width, cv.height); dirty = false; };
    wrap.append(cv, clear);
    return () => (dirty ? cv.toDataURL("image/png") : "");
  }

}
