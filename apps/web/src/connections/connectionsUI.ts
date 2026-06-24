/**
 * Data-connections admin UI (Postgres/Supabase/Procore/ACC/QuickBooks/Sage/Viewpoint): the
 * connections list + add form, the Procore auto-sync schedules + field-mapping editors, and a
 * read-only SQL browser. Extracted from main.ts and **lazily imported** (admin-only, rarely opened)
 * so this ~240-line surface stays out of the initial bundle. All interpolated values that originate
 * from user input or a remote DB are escaped (escapeHtml) — these modals render arbitrary names,
 * IDs and query cells, so HTML injection would otherwise be a stored-XSS vector.
 */
import type { ApiClient, ConnectionItem, SyncScheduleItem } from "../api/client";
import { modalShell } from "../ui/modal";
import { escapeHtml, toast } from "../ui/feedback";

type GetPid = () => string | null;

const TYPE_FIELDS: Record<string, { key: string; label: string; secret?: boolean; placeholder?: string }[]> = {
  postgres: [{ key: "dsn", label: "Connection string", secret: true, placeholder: "postgresql://user:pass@host:5432/db" }],
  supabase: [{ key: "dsn", label: "Supabase DB URL", secret: true, placeholder: "postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres" }],
  procore: [{ key: "access_token", label: "Access token", secret: true, placeholder: "Procore OAuth access token" }],
  acc: [{ key: "access_token", label: "Access token", secret: true, placeholder: "Autodesk (APS) 3-legged OAuth token" },
        { key: "account_id", label: "Account ID", placeholder: "ACC account / hub GUID (to list projects)" }],
  quickbooks: [{ key: "access_token", label: "Access token", secret: true, placeholder: "QuickBooks Online OAuth access token" },
               { key: "realm_id", label: "Realm / Company ID", placeholder: "QuickBooks company (realm) id" }],
  sage: [{ key: "access_token", label: "Access token", secret: true, placeholder: "Sage API token" },
         { key: "base_url", label: "API base URL", placeholder: "https://api.your-sage-tenant.com" }],
  viewpoint: [{ key: "access_token", label: "Access token", secret: true, placeholder: "Viewpoint (Trimble) API token" },
              { key: "base_url", label: "API base URL", placeholder: "https://api.your-viewpoint-tenant.com" }],
};

function schedulesModal(api: ApiClient, getPid: GetPid, connectionId: string) {
  const pid = getPid(); if (!pid) return;
  const { card, msg } = modalShell("Auto-sync schedules", 500);
  msg.style.color = "#e2554a";
  const list = document.createElement("div"); card.appendChild(list);
  const render = async () => {
    list.textContent = "";
    let scheds: SyncScheduleItem[] = [];
    try { scheds = (await api.syncSchedules(pid)).filter((s) => s.connection_id === connectionId); }
    catch { list.innerHTML = `<div class="meta">admin only.</div>`; return; }
    if (!scheds.length) { const e = document.createElement("div"); e.className = "empty-state"; e.innerHTML = `No schedules yet<span class="es-hint">Add one below to auto-sync from Procore.</span>`; list.appendChild(e); }
    const act = (label: string, fn: () => Promise<unknown>) => { const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label; b.onclick = async () => { try { await fn(); await render(); } catch { msg.textContent = "action failed"; } }; return b; };
    for (const s of scheds) {
      const row = document.createElement("div"); row.style.cssText = "border:1px solid var(--line);border-radius:8px;padding:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px";
      const info = document.createElement("span"); info.className = "meta"; info.style.flex = "1";
      const lr = s.last_run ? new Date(s.last_run).toLocaleString() : "never";
      const tail = s.last_result?.imported_total != null ? ` (+${s.last_result.imported_total})` : s.last_result?.error ? " (error)" : "";
      info.innerHTML = `Procore #${escapeHtml(s.procore_project_id)} · every ${s.interval_minutes}m · ${escapeHtml(s.kinds.join("/"))}${s.push ? " · two-way ⇄" : ""}`
        + `<br><span style="font-size:11px">${s.enabled ? "enabled" : "disabled"} · last: ${escapeHtml(lr)}${escapeHtml(tail)}</span>`;
      row.append(info,
        act(s.enabled ? "Disable" : "Enable", () => api.updateSyncSchedule(pid, s.id, { enabled: !s.enabled })),
        act(s.push ? "Two-way ✓" : "Two-way", () => api.updateSyncSchedule(pid, s.id, { push: !s.push })),
        act("Run now", async () => { const r = await api.runSyncSchedule(pid, s.id); toast(r.error ? `error: ${r.error}` : `imported ${r.imported_total ?? 0}`, "info"); }),
        act("Delete", () => api.deleteSyncSchedule(pid, s.id)));
      list.appendChild(row);
    }
    const form = document.createElement("div"); form.style.cssText = "border:1px dashed var(--line);border-radius:8px;padding:10px;margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center";
    const pp = document.createElement("input"); pp.placeholder = "Procore project ID"; pp.className = "portal-filter"; pp.style.flex = "1";
    const iv = document.createElement("input"); iv.type = "number"; iv.value = "60"; iv.title = "interval (minutes, min 5)"; iv.className = "portal-filter"; iv.style.width = "80px";
    const tw = document.createElement("input"); tw.type = "checkbox"; tw.id = "sched-twoway";
    const twl = document.createElement("label"); twl.htmlFor = "sched-twoway"; twl.textContent = "two-way"; twl.className = "meta"; twl.style.fontSize = "12px";
    const add = document.createElement("button"); add.className = "file-btn"; add.textContent = "Add schedule";
    add.onclick = async () => {
      if (!pp.value.trim()) { msg.textContent = "Procore project ID required"; return; }
      try { await api.createSyncSchedule(pid, { connection_id: connectionId, procore_project_id: pp.value.trim(), interval_minutes: Math.max(5, parseInt(iv.value) || 60), push: tw.checked }); pp.value = ""; tw.checked = false; await render(); }
      catch { msg.textContent = "could not add schedule"; }
    };
    form.append(pp, iv, tw, twl, add); list.appendChild(form);
  };
  card.appendChild(msg); void render();
}

function mappingModal(api: ApiClient, connectionId: string, name: string) {
  const { card, msg } = modalShell(`Field mapping — ${name}`, 560);
  msg.style.color = "#e2554a";
  const intro = document.createElement("div"); intro.className = "meta"; intro.style.marginBottom = "8px";
  intro.textContent = "Map each module field to a Procore source path (dotted, e.g. questions.0.body). Leave blank to use the default.";
  card.appendChild(intro);
  const body = document.createElement("div"); card.appendChild(body);
  const inputs: { kind: string; field: string; def: string; el: HTMLInputElement }[] = [];
  const render = async () => {
    body.textContent = ""; inputs.length = 0;
    let data: Awaited<ReturnType<typeof api.connectionMappings>>;
    try { data = await api.connectionMappings(connectionId); } catch { msg.textContent = "admin only — could not load mapping"; return; }
    for (const [kind, m] of Object.entries(data.mappings)) {
      const sec = document.createElement("div"); sec.style.cssText = "border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px";
      sec.innerHTML = `<div class="meta" style="font-weight:600;color:var(--text);margin-bottom:6px">${escapeHtml(kind)} <span style="font-weight:400">→ ${escapeHtml(m.module)}</span></div>`;
      for (const f of m.fields) {
        const r = document.createElement("div"); r.style.cssText = "display:flex;align-items:center;gap:8px;margin-bottom:4px";
        const lab = document.createElement("span"); lab.className = "meta"; lab.style.cssText = "width:130px;font-size:12px"; lab.textContent = f.label;
        const inp = document.createElement("input"); inp.className = "portal-filter"; inp.style.cssText = "flex:1;font-family:ui-monospace,monospace;font-size:12px";
        inp.placeholder = f.default; if (f.path !== f.default) inp.value = f.path;
        inputs.push({ kind, field: f.field, def: f.default, el: inp });
        r.append(lab, inp); sec.appendChild(r);
      }
      body.appendChild(sec);
    }
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:8px;margin-top:4px";
    const save = document.createElement("button"); save.className = "file-btn"; save.textContent = "Save mapping";
    save.onclick = async () => {
      const out: Record<string, Record<string, string>> = {};
      for (const i of inputs) { const v = i.el.value.trim(); if (v && v !== i.def) (out[i.kind] ||= {})[i.field] = v; }
      try { await api.saveConnectionMappings(connectionId, out); toast("Field mapping saved", "info"); await render(); }
      catch { msg.textContent = "could not save mapping"; }
    };
    const reset = document.createElement("button"); reset.className = "tool-btn"; reset.textContent = "Reset to defaults";
    reset.onclick = async () => { try { await api.saveConnectionMappings(connectionId, {}); toast("Mapping reset to defaults", "info"); await render(); } catch { msg.textContent = "could not reset"; } };
    bar.append(save, reset); body.appendChild(bar);
  };
  card.appendChild(msg); void render();
}

/** Read-only data browser for a SQL connection (local / Postgres / Supabase): table list +
 *  a SELECT console with a results grid. Closes the interoperability gap — data, not just config. */
function browseConnection(api: ApiClient, id: string, name: string) {
  const { card, msg } = modalShell(`Browse — ${name}`, 720);
  msg.style.color = "#e2554a";
  const tablesBox = document.createElement("div"); tablesBox.className = "meta"; tablesBox.textContent = "loading tables…";
  const sql = document.createElement("textarea"); sql.className = "portal-filter";
  sql.style.cssText = "width:100%;height:60px;font-family:ui-monospace,monospace;margin:8px 0";
  sql.placeholder = "SELECT … (read-only; SELECT/WITH only)";
  const runRow = document.createElement("div"); runRow.style.cssText = "display:flex;gap:8px;align-items:center";
  const run = document.createElement("button"); run.className = "file-btn"; run.textContent = "Run";
  const info = document.createElement("span"); info.className = "meta";
  runRow.append(run, info);
  const grid = document.createElement("div"); grid.style.cssText = "overflow:auto;max-height:46vh;margin-top:8px";

  const renderGrid = (cols: string[], rows: unknown[][]) => {
    if (!cols.length) { grid.innerHTML = `<div class="meta">no columns</div>`; return; }
    // escape column names + cell values — arbitrary DB content must never render as HTML (XSS)
    const th = cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
    const tr = rows.map((r) => `<tr>${r.map((v) => `<td>${v == null ? "<span class='meta'>null</span>" : escapeHtml(String(v).slice(0, 120))}</td>`).join("")}</tr>`).join("");
    grid.innerHTML = `<table class="portal-table"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
  };
  const runSql = async (q: string) => {
    sql.value = q; msg.textContent = ""; info.textContent = "running…";
    const r = await api.connectionQuery(id, q, 200);
    if (r.error) { info.textContent = ""; msg.textContent = r.error; grid.innerHTML = ""; return; }
    info.textContent = `${r.row_count} row${r.row_count === 1 ? "" : "s"}`;
    renderGrid(r.columns ?? [], r.rows ?? []);
  };
  run.onclick = () => { if (sql.value.trim()) void runSql(sql.value.trim()); };

  void api.connectionTables(id).then((t) => {
    if (t.error) { tablesBox.textContent = ""; msg.textContent = t.error; return; }
    const names = t.tables ?? [];
    tablesBox.textContent = "";
    const label = document.createElement("span"); label.className = "meta"; label.textContent = `${names.length} tables — click to preview: `;
    tablesBox.appendChild(label);
    for (const n of names) {
      const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = n; b.style.margin = "2px";
      b.onclick = () => void runSql(`SELECT * FROM "${n}"`);
      tablesBox.appendChild(b);
    }
  }).catch(() => { tablesBox.textContent = "could not list tables"; });

  card.append(tablesBox, sql, runRow, grid, msg);
}

/** The Data-connections admin modal (entry point). `getPid` reads the live current project id. */
export function openConnectionsModal(api: ApiClient, getPid: GetPid) {
  const { card, msg } = modalShell("Data connections", 560);
  msg.style.color = "#e2554a";
  const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:8px";
  card.appendChild(list);

  const render = async () => {
    list.textContent = "";
    let data: { types: string[]; connections: ConnectionItem[] };
    try { data = await api.connections(); } catch { msg.textContent = "sign in as an admin to manage connections"; return; }
    for (const cx of data.connections) {
      const row = document.createElement("div");
      row.style.cssText = "border:1px solid var(--line);border-radius:8px;padding:8px 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap";
      const dot = document.createElement("span"); dot.className = "conn-dot";
      const badge = (ok?: boolean) => { dot.style.background = ok === undefined ? "#9aa0a6" : ok ? "#33d17a" : "#e2554a"; };
      badge(cx.status?.ok);
      const nm = document.createElement("span"); nm.innerHTML = `<b>${escapeHtml(cx.name)}</b> <span class="meta">${escapeHtml(cx.type)}${cx.builtin ? " · built-in" : ""}</span>`;
      const detail = document.createElement("span"); detail.className = "meta"; detail.style.cssText = "flex:1;min-width:140px;font-size:11px";
      detail.textContent = cx.status?.detail ?? (cx.builtin ? "" : "not tested");
      const act = (label: string, fn: () => Promise<unknown>) => { const b = document.createElement("button"); b.className = "tool-btn"; b.textContent = label; b.onclick = async () => { try { await fn(); } catch { msg.textContent = `action failed`; } }; return b; };
      row.append(dot, nm, detail);
      if (["local", "postgres", "supabase"].includes(cx.type)) {
        row.append(act("Browse", async () => browseConnection(api, cx.id, cx.name)));
      }
      if (cx.type === "procore") {
        row.append(act("Sync now", async () => {
          const pid = getPid(); if (!pid) { msg.textContent = "open a project first to import into it"; return; }
          const pp = prompt("Procore project ID to import from (RFIs, submittals, change events):");
          if (!pp || !pp.trim()) return;
          const r = await api.syncProcore(pid, cx.id, pp.trim());
          const by = Object.entries(r.results).map(([k, v]) => `${v.imported} ${k}`).join(", ");
          toast(`Procore: imported ${r.imported_total} record(s) (${by})`, "info");
        }));
        row.append(act("Push", async () => {
          const pid = getPid(); if (!pid) { msg.textContent = "open a project first"; return; }
          const pp = prompt("Procore project ID to push resolved RFIs (answer + status) to:");
          if (!pp || !pp.trim()) return;
          const r = await api.pushProcore(pid, cx.id, pp.trim());
          toast(`Pushed ${r.pushed_total} RFI(s) back to Procore`, "info");
        }));
        row.append(act("Schedules", async () => {
          if (!getPid()) { msg.textContent = "open a project first to schedule auto-sync"; return; }
          schedulesModal(api, getPid, cx.id);
        }));
        row.append(act("Mapping", async () => mappingModal(api, cx.id, cx.name)));
      }
      if (cx.type === "acc") {
        row.append(act("Issues", async () => {
          const pp = prompt("ACC project ID to list issues from:");
          if (!pp || !pp.trim()) return;
          const r = await api.accIssues(cx.id, pp.trim());
          if (r.error) { msg.textContent = `ACC: ${r.error}`; return; }
          toast(`ACC: ${r.count ?? 0} issue(s) on project ${pp.trim()}`, "info");
        }));
      }
      if (!cx.builtin) {
        row.append(
          act("Test", async () => { detail.textContent = "testing…"; const r = await api.testConnection(cx.id); badge(r.status.ok); detail.textContent = r.status.detail + (r.info.project_count ? ` · ${r.info.project_count} projects` : ""); }),
          act("Delete", async () => { if (confirm(`Delete connection “${cx.name}”?`)) { await api.deleteConnection(cx.id); await render(); } }));
      }
      list.appendChild(row);
    }
    // --- add form ---
    const form = document.createElement("div"); form.style.cssText = "border:1px dashed var(--line);border-radius:8px;padding:10px;margin-top:6px";
    form.innerHTML = `<div class="meta" style="font-weight:600;color:var(--text);margin-bottom:6px">Add connection</div>`;
    const nu = document.createElement("input"); nu.placeholder = "name"; nu.className = "portal-filter"; nu.style.cssText = "width:100%;margin-bottom:6px";
    const ty = document.createElement("select"); ty.className = "portal-filter"; ty.style.cssText = "width:100%;margin-bottom:6px";
    for (const t of ["postgres", "supabase", "procore", "acc", "quickbooks", "sage", "viewpoint"]) { const o = document.createElement("option"); o.value = o.textContent = t; ty.appendChild(o); }
    const fields = document.createElement("div");
    const inputs: Record<string, HTMLInputElement> = {};
    const renderFields = () => {
      fields.textContent = ""; for (const k of Object.keys(inputs)) delete inputs[k];
      for (const f of TYPE_FIELDS[ty.value] || []) {
        const inp = document.createElement("input"); inp.className = "portal-filter"; inp.style.cssText = "width:100%;margin-bottom:6px";
        inp.placeholder = f.placeholder || f.label; if (f.secret) inp.type = "password";
        inputs[f.key] = inp; fields.appendChild(inp);
      }
    };
    ty.onchange = renderFields; renderFields();
    const cfg = () => Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value]));
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:6px";
    const testBtn = document.createElement("button"); testBtn.className = "tool-btn"; testBtn.textContent = "Test";
    const testOut = document.createElement("span"); testOut.className = "meta"; testOut.style.fontSize = "11px";
    testBtn.onclick = async () => { testOut.textContent = "testing…"; try { const r = await api.testConnectionConfig(ty.value, cfg()); testOut.style.color = r.ok ? "#33d17a" : "#e2554a"; testOut.textContent = r.detail; } catch { testOut.textContent = "test failed"; } };
    const saveBtn = document.createElement("button"); saveBtn.className = "file-btn"; saveBtn.textContent = "Add";
    saveBtn.onclick = async () => { msg.textContent = ""; if (!nu.value.trim()) { msg.textContent = "name required"; return; } try { await api.createConnection(nu.value.trim(), ty.value, cfg()); nu.value = ""; renderFields(); await render(); } catch { msg.textContent = "could not add connection"; } };
    bar.append(testBtn, saveBtn, testOut);
    form.append(nu, ty, fields, bar);
    list.appendChild(form);
  };
  card.appendChild(msg);
  void render();
}
