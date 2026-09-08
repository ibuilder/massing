import type { ResponsibilityMatrix, RespRow } from "../../api/client";
import { MAX_ROLES, orphanedRoles, validateMatrix } from "./raciValidation";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import { confirmModal, promptModal } from "../../ui/modal";
import { noProjectHtml } from "../../ui/empty";
import type { PanelContext } from "../panelContext";

/**
 * Responsibility matrix (RACI / DACI) — the Responsibility Assignment Matrix the PMBOK references and
 * ISO 19650 needs for its MIDP/TIDP. One row per deliverable/decision, one column per project role,
 * each cell an assignment letter. Editable grid with live validation (exactly one Accountable, at
 * least one Responsible), starter templates, and a RACI↔DACI toggle. Backed by the `responsibility`
 * module records + engine (responsibility.py). Extracted panel; uses the PanelContext seam.
 */

const PHASES = ["Pre-Design", "Design", "Preconstruction", "Procurement", "Construction",
                "Commissioning", "Closeout", "Operations"];

function letterColor(letter: string, doer: string): string {
  if (letter === "A") return "var(--accent)";
  if (letter === doer) return "var(--status-good)";
  if (letter === "C") return "var(--status-warn)";
  if (letter === "I") return "var(--muted)";
  return "var(--muted)";
}

export async function renderResponsibility(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const api = ctx.host.api;
  root.appendChild(ctx.bar("🧭 Responsibility (RACI)", () => {
    ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav();
  }));
  const pidOrNull = ctx.host.projectId();
  if (!pidOrNull) { root.insertAdjacentHTML("beforeend", noProjectHtml("the Responsibility matrix")); return; }
  const pid = pidOrNull;   // narrowed to string for the closures below

  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };

  // explanation — always visible so the grid is self-teaching
  const intro = el("div", "dash-card"); intro.style.marginBottom = "8px";
  root.appendChild(intro);

  const body = el("div"); body.textContent = "loading…"; root.appendChild(body);

  const load = async () => {
    let m: ResponsibilityMatrix;
    try { m = await api.responsibilityMatrix(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    // normalize a possibly-partial payload (e.g. the offline demo snapshot lacks this endpoint) so
    // the grid always renders a clean RACI empty state rather than "undefined".
    m.mode = m.mode === "DACI" ? "DACI" : "RACI";
    m.roles = m.roles || [];
    m.rows = m.rows || [];
    m.letters = m.letters?.length ? m.letters : (m.mode === "DACI" ? ["D", "A", "C", "I"] : ["R", "A", "C", "I"]);
    m.doer = m.doer || (m.mode === "DACI" ? "D" : "R");
    render(m);
  };

  // patch one record's assignments (a cell edit). The banner repaints from `validateMatrix`
  // rather than a round-trip, which is why that rule exists client-side at all — see
  // `raciValidation.ts` for why it is a shared-fixture parity problem rather than duplication.
  const saveCell = async (row: RespRow, role: string, letter: string) => {
    if (letter) row.assignments[role] = letter; else delete row.assignments[role];
    try { await api.updateModuleRecord(pid, "responsibility", row.id, { assignments: row.assignments }); }
    catch { toast("Couldn't save that change", "error"); }
  };

  function render(m: ResponsibilityMatrix) {
    const isRaci = m.mode === "RACI";
    intro.innerHTML = `<b>Responsibility matrix — ${m.mode}</b>`
      + `<div class="meta" style="margin-top:3px">`
      + (isRaci
          ? "One row per deliverable or decision. <b>R</b>esponsible does the work (≥1), "
            + "<b>A</b>ccountable owns the outcome (exactly one), <b>C</b>onsulted gives input, "
            + "<b>I</b>nformed is kept in the loop."
          : "One row per decision. <b>D</b>river coordinates it (≥1), <b>A</b>pprover makes the final "
            + "call (exactly one), <b>C</b>ontributor adds expertise, <b>I</b>nformed is notified.")
      + " Click a cell to set its letter. Rows and roles map to the ISO 19650 task-team / MIDP responsibility view."
      + `</div>`;

    body.innerHTML = "";

    // --- toolbar --------------------------------------------------------------------------------
    const tb = el("div"); tb.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px";
    // mode toggle
    const modeBtn = el("button", "tool-btn") as HTMLButtonElement;
    modeBtn.textContent = isRaci ? "Switch to DACI" : "Switch to RACI";
    modeBtn.title = "RACI is task-ownership; DACI is decision-making. The doer letter (R↔D) is remapped for you.";
    modeBtn.onclick = async () => {
      const to = isRaci ? "DACI" : "RACI";
      const from = m.doer, toDoer = to === "DACI" ? "D" : "R";
      // remap the doer letter across all rows so the matrix stays valid across the switch
      for (const r of m.rows) {
        let changed = false;
        for (const k of Object.keys(r.assignments)) {
          if (r.assignments[k] === from) { r.assignments[k] = toDoer; changed = true; }
        }
        if (changed) await api.updateModuleRecord(pid, "responsibility", r.id, { assignments: r.assignments });
      }
      await api.setResponsibilityConfig(pid, m.roles, to);
      toast(`Switched to ${to}`, "info"); void load();
    };
    tb.append(modeBtn);

    // template loader
    const tsel = el("select", "sb-sel") as HTMLSelectElement;
    tsel.innerHTML = `<option value="">Load starter template…</option>`;
    void api.responsibilityTemplates(pid).then((t) => {
      for (const tp of t.templates) {
        const o = document.createElement("option"); o.value = tp.key;
        o.textContent = `${tp.name} (${tp.rows} rows)`; tsel.append(o);
      }
    }).catch(() => {
      // surface the failure instead of a silently-empty dropdown
      tsel.innerHTML = `<option value="">Templates unavailable — retry later</option>`;
    });
    tsel.onchange = async () => {
      if (!tsel.value) return;
      const key = tsel.value; tsel.value = "";
      if (m.rows.length && !(await confirmModal(
        "Add this template's rows to the current matrix?", "Existing rows are kept."))) return;
      try { const r = await api.applyResponsibilityTemplate(pid, key, m.mode);
        toast(`Added ${r.created} activities`, "info"); void load(); }
      catch { toast("Couldn't load template", "error"); }
    };
    tb.append(tsel);

    // add activity
    const addAct = el("button", "tool-btn") as HTMLButtonElement; addAct.textContent = "＋ Activity";
    addAct.dataset.cap = "edit";
    addAct.onclick = async () => {
      const res = await promptModal("Add activity", [
        { name: "activity", label: "Activity / deliverable", required: true, placeholder: "e.g. Foundation design" },
        { name: "phase", label: "Phase (optional)", placeholder: PHASES.join(" · ") },
      ]);
      const name = res?.activity?.trim();
      if (!name) return;
      try {
        await api.createModuleRecord(pid, "responsibility",
          { data: { activity: name, phase: res?.phase?.trim() || undefined, assignments: {} } });
        void load();
      } catch { toast("Couldn't add activity", "error"); }
    };
    tb.append(addAct);

    // add role column
    const addRole = el("button", "tool-btn") as HTMLButtonElement; addRole.textContent = "＋ Role";
    addRole.dataset.cap = "edit";
    addRole.onclick = async () => {
      const res = await promptModal("Add role column",
        [{ name: "role", label: "Role", required: true, placeholder: "e.g. Commissioning Agent" }]);
      const name = res?.role?.trim();
      if (!name || m.roles.includes(name)) return;
      await api.setResponsibilityConfig(pid, [...m.roles, name], m.mode);
      void load();
    };
    tb.append(addRole);

    // export CSV
    const csvBtn = el("button", "tool-btn") as HTMLButtonElement; csvBtn.textContent = "⬇ CSV";
    csvBtn.onclick = () => exportCsv(m);
    tb.append(csvBtn);
    body.append(tb);

    // --- RESP-ORPHAN repair ----------------------------------------------------------------------
    // Two ways out, and restoring is offered first because it is the non-destructive one: the
    // letters are still on the records, so bringing the columns back makes them visible again with
    // nothing lost. Clearing is the deliberate discard, and it says how many it will drop.
    function orphanRepair(m: ResponsibilityMatrix, orphans: string[]): HTMLElement {
      const row = el("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px";
      const restore = el("button", "tool-btn") as HTMLButtonElement;
      restore.textContent = `↩ Restore ${orphans.length} column(s)`;
      restore.title = `Add ${orphans.join(", ")} back as columns so their assignments show again`;
      // REFUSE RATHER THAN OVERFLOW. `set_config` TRUNCATES a longer list and returns 200, and the
      // visible roles go first — so an over-long restore drops the orphans off the tail, reloads
      // clean, and leaves the assignments exactly as stranded as before. That is this whole item's
      // defect arriving through its own repair button; the server-side merge in `apply_template`
      // refuses for the same reason. Raised in review.
      const fits = m.roles.length + orphans.length <= MAX_ROLES;
      restore.disabled = !fits;
      restore.title = fits
        ? `Add ${orphans.join(", ")} back as columns so their assignments show again`
        : `Restoring ${orphans.length} column(s) would need ${m.roles.length + orphans.length} of a `
          + `${MAX_ROLES}-column limit — remove unused columns first, or clear these assignments.`;
      restore.onclick = async () => {
        if (!fits) return;
        restore.disabled = true;
        try { await api.setResponsibilityConfig(pid, [...m.roles, ...orphans], m.mode); void load(); }
        catch { toast("Couldn't restore those columns", "error"); restore.disabled = false; }
      };
      const clear = el("button", "tool-btn") as HTMLButtonElement;
      clear.textContent = "🗑 Clear them";
      clear.title = "Delete the assignments on those columns from every row";
      clear.onclick = async () => {
        if (!(await confirmModal(`Clear assignments on ${orphans.length} removed column(s)?`,
          "The letters on those columns are deleted from every row. This cannot be undone."))) return;
        clear.disabled = true;
        try {
          for (const r of m.rows) {
            const keep = Object.fromEntries(
              Object.entries(r.assignments).filter(([role]) => !orphans.includes(role)));
            if (Object.keys(keep).length !== Object.keys(r.assignments).length) {
              r.assignments = keep;
              await api.updateModuleRecord(pid, "responsibility", r.id, { assignments: keep });
            }
          }
          void load();
        } catch {
          // Each row is its own PATCH, so a failure part-way leaves earlier rows cleared. Re-read
          // rather than leaving the panel showing in-memory state the server never accepted: the
          // banner then reports what is actually still stranded, and clearing again is idempotent.
          // Raised in review — see the reply for why this is not a transactional bulk endpoint.
          toast("Couldn't clear all of those — reloading to show what remains", "error");
          void load();
        }
      };
      row.append(restore, clear);
      return row;
    }

    // --- validation banner ----------------------------------------------------------------------
    const banner = el("div"); banner.id = "resp-banner"; body.append(banner);
    const paintBanner = () => {
      const v = validateMatrix(m);
      const orphans = orphanedRoles(v);
      // The ✅ has to answer for the orphans too. A row can satisfy the rule on its visible cells
      // and still carry letters on columns that are gone; calling that "complete" without saying so
      // is the same silence the count itself used to keep.
      if (v.clean && !orphans.length) {
        banner.className = "meta"; banner.style.cssText = "margin-bottom:8px;color:var(--status-good)";
        banner.textContent = m.rows.length ? "✅ Every activity has exactly one Accountable and at least one Responsible."
          : "";
        return;
      }
      banner.className = "dash-card"; banner.style.cssText = "border-left:3px solid var(--status-warn);margin-bottom:8px";
      const parts: string[] = [];
      const dup = v.missing.filter((x) => x.count > 1).map((x) => esc(x.activity));
      const none = v.missing.filter((x) => x.count === 0).map((x) => esc(x.activity));
      if (none.length) parts.push(`<div>⚠️ <b>No ${isRaci ? "Accountable" : "Approver"}</b> — every row needs exactly one: ${none.join(", ")}</div>`);
      if (dup.length) parts.push(`<div>⚠️ <b>More than one ${isRaci ? "Accountable" : "Approver"}</b>: ${dup.join(", ")}</div>`);
      if (v.noR.length) parts.push(`<div>⚠️ <b>No ${isRaci ? "Responsible" : "Driver"}</b> — needs at least one doer: ${v.noR.map((x) => esc(x.activity)).join(", ")}</div>`);
      // RESP-ORPHAN — the finding that explains a blank row. Without it the grid shows an empty
      // line and nothing anywhere says the letters still exist.
      if (orphans.length) {
        parts.push(`<div>⚠️ <b>${v.unknown.length} assignment(s) on ${orphans.length} column(s) `
          + `this matrix no longer has</b> — they are stored but cannot be shown: `
          + `${orphans.map(esc).join(", ")}. Restore the columns to see them, or clear them to drop `
          + `them for good.</div>`);
      }
      banner.innerHTML = `<div class="meta" style="font-size:12px">${parts.join("")}</div>`;
      if (orphans.length) banner.appendChild(orphanRepair(m, orphans));
    };
    paintBanner();

    if (!m.rows.length) {
      const none = el("div", "empty-state");
      none.innerHTML = `No responsibilities yet<span class="es-hint">Load a starter template above (design delivery, buyout, construction, closeout) or add an activity, then click cells to assign R/A/C/I.</span>`;
      body.append(none); return;
    }

    // --- the grid -------------------------------------------------------------------------------
    const wrap = el("div"); wrap.style.cssText = "overflow-x:auto";
    const t = el("table", "portal-table") as HTMLTableElement;
    t.style.cssText = "font-size:12px;border-collapse:collapse;min-width:520px";
    // header
    const thead = el("thead"); const htr = el("tr");
    const h0 = el("th"); h0.textContent = "Activity";
    h0.style.cssText = "text-align:left;position:sticky;left:0;background:var(--panel);min-width:190px;z-index:1";
    htr.append(h0);
    for (const role of m.roles) {
      const th = el("th"); th.style.cssText = "min-width:64px;text-align:center;white-space:nowrap";
      const span = el("span"); span.textContent = role; span.style.cursor = "pointer";
      span.title = "Click to rename; ✕ removes the column";
      span.onclick = async () => {
        const res = await promptModal("Rename role",
          [{ name: "role", label: "Role name", value: role, required: true }]);
        const nn = res?.role?.trim();
        if (!nn || nn === role || m.roles.includes(nn)) return;
        // remap assignments old→new across all rows, then update the role list
        for (const r of m.rows) {
          if (r.assignments[role] != null) {
            r.assignments[nn] = r.assignments[role]; delete r.assignments[role];
            await api.updateModuleRecord(pid, "responsibility", r.id, { assignments: r.assignments });
          }
        }
        await api.setResponsibilityConfig(pid, m.roles.map((x) => x === role ? nn : x), m.mode);
        void load();
      };
      const x = el("span"); x.textContent = " ✕"; x.style.cssText = "cursor:pointer;color:var(--muted)";
      x.title = `Remove ${role}`;
      x.onclick = async () => {
        if (!(await confirmModal(`Remove the “${role}” column?`, "Its assignments are cleared from every row."))) return;
        for (const r of m.rows) {
          if (r.assignments[role] != null) {
            delete r.assignments[role];
            await api.updateModuleRecord(pid, "responsibility", r.id, { assignments: r.assignments });
          }
        }
        await api.setResponsibilityConfig(pid, m.roles.filter((x2) => x2 !== role), m.mode);
        void load();
      };
      th.append(span, x); htr.append(th);
    }
    const hx = el("th"); hx.style.width = "24px"; htr.append(hx);
    thead.append(htr); t.append(thead);

    // body
    const tb2 = el("tbody");
    for (const r of m.rows) {
      const tr = el("tr");
      const c0 = el("td");
      c0.style.cssText = "position:sticky;left:0;background:var(--panel)";
      const title = el("div"); title.textContent = r.activity; title.style.fontWeight = "600";
      const sub = el("div", "meta"); sub.style.fontSize = "10px";
      sub.textContent = [r.phase, r.category, r.milestone].filter(Boolean).join(" · ");
      c0.append(title); if (sub.textContent) c0.append(sub);
      tr.append(c0);
      for (const role of m.roles) {
        const td = el("td"); td.style.textAlign = "center";
        const sel = el("select") as HTMLSelectElement;
        sel.style.cssText = "border:none;background:transparent;font-weight:700;cursor:pointer;text-align:center;"
          + "font-size:12px;padding:2px 4px;border-radius:4px";
        sel.dataset.cap = "edit";
        const opts = ["", ...m.letters];
        for (const o of opts) {
          const op = document.createElement("option"); op.value = o; op.textContent = o || "·"; sel.append(op);
        }
        const cur = r.assignments[role] || "";
        sel.value = cur;
        sel.style.color = cur ? letterColor(cur, m.doer) : "var(--line)";
        sel.title = `${r.activity} · ${role}`;
        sel.onchange = () => {
          const v = sel.value;
          sel.style.color = v ? letterColor(v, m.doer) : "var(--line)";
          void saveCell(r, role, v);
          paintBanner();
        };
        td.append(sel); tr.append(td);
      }
      const cx = el("td"); cx.style.textAlign = "center";
      const del = el("button") as HTMLButtonElement;
      del.textContent = "🗑"; del.title = "Delete this activity";
      del.style.cssText = "border:none;background:transparent;cursor:pointer;opacity:.55";
      del.dataset.cap = "edit";
      del.onclick = async () => {
        if (!(await confirmModal(`Delete “${r.activity}”?`, ""))) return;
        try { await api.deleteModuleRecord(pid, "responsibility", r.id); void load(); }
        catch { toast("Couldn't delete", "error"); }
      };
      cx.append(del); tr.append(cx);
      tb2.append(tr);
    }
    t.append(tb2); wrap.append(t); body.append(wrap);

    // legend
    const legend = el("div", "meta"); legend.style.cssText = "margin-top:8px;display:flex;gap:14px;flex-wrap:wrap;font-size:11px";
    const chip = (l: string, label: string) =>
      `<span><b style="color:${letterColor(l, m.doer)}">${l}</b> ${label}</span>`;
    legend.innerHTML = isRaci
      ? chip("R", "Responsible") + chip("A", "Accountable") + chip("C", "Consulted") + chip("I", "Informed")
      : chip("D", "Driver") + chip("A", "Approver") + chip("C", "Contributor") + chip("I", "Informed");
    body.append(legend);
  }

  function exportCsv(m: ResponsibilityMatrix) {
    const esc2 = (s: string) => `"${(s || "").replace(/"/g, '""')}"`;
    const head = ["Activity", "Phase", "Category", "Milestone", ...m.roles];
    const lines = [head.map(esc2).join(",")];
    for (const r of m.rows) {
      lines.push([r.activity, r.phase || "", r.category || "", r.milestone || "",
        ...m.roles.map((role) => r.assignments[role] || "")].map(esc2).join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `responsibility-${m.mode.toLowerCase()}.csv`; a.click(); URL.revokeObjectURL(a.href);
  }

  await load();
}
