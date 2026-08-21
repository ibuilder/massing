import * as THREE from "three";

import { type ApiClient } from "../../api/client";
import { enqueueAndWait } from "../../api/waitForJob";
import { LayerManager } from "../../tools/layers";
import { LogisticsOverlay } from "../draft/logisticsOverlay";
import { kvTable, resultNote, showResult } from "../../ui/result";
import { toast, withLoading } from "../../ui/feedback";
import { populate4dPanel } from "../fourD";
import type { LogisticsResource } from "../../api/client";

/**
 * R39-DECOMP-VIEWER — the code / cost / 4D analyse section, out of `app.ts`.
 *
 * `lastPoint` arrives as an ACCESSOR: it is a `let` in `app.ts` holding the last point clicked in the model, and every tool in here that places something reads it at CLICK time. A value would pin it to whatever was current when the panel was built.
 *
 * The body is byte-identical to what it replaced and deliberately NOT re-indented: re-indenting
 * risks silently changing the content of a multi-line template literal inside what is meant to be
 * a no-behaviour-change move. `tsc` is the parity gate for the threading; `toolsSplit.test.ts`,
 * which reads section SOURCE, is the gate for "no control was dropped" — this file is listed in
 * its `SECTION_SOURCES` for that reason.
 */

export interface AnalyseDeps {
  section: (key: string, title: string,
            opts?: { requires?: "project" | "sourceIfc"; tool?: boolean }) => HTMLElement | null;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  pid: string;
  projectId: string | null;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** ACCESSOR: `lastPoint` is a `let` in app.ts, read at click time by the placement tools. */
  lastPoint: () => THREE.Vector3 | null;
  /**
   * A REF, not an accessor — and the distinction is the point.
   *
   * The 4D playback teardown is the one piece of state this section **writes** as well as reads
   * (`fourD.dispose = populate4dPanel(...)`, then `dispose4d?.(); dispose4d = null` on close). A getter
   * cannot express a write, and moving the `let` into this module would change its lifetime: it
   * lives in the viewer-app closure and must survive `buildToolsPanel` running again on a persona
   * change. So ownership stays in `app.ts` and a mutable ref crosses the seam.
   *
   * **This is the only place the moved body is not byte-identical** — two lines now say
   * `fourD.dispose` where they said `dispose4d`. Stated rather than buried, because "verbatim move"
   * is a claim and this is its one exception.
   */
  fourD: { dispose: (() => void) | null };
  container: HTMLElement;
  logisticsOverlay: LogisticsOverlay;
  layerMgr: LayerManager;
  refreshIssues: () => Promise<void | boolean>;
}

export function buildAnalyseSection(d: AnalyseDeps): void {
  const { section, toolBtn2, api, pid, projectId, notify, container, logisticsOverlay,
          layerMgr, refreshIssues, fourD } = d;
  // NOT a value. `d.lastPoint()` here would pin the point to whatever was current when the panel was
  // BUILT — which is null, because the panel is built before the user has clicked anything. Caught by
  // tools/accessorNotCollapsed.test.ts, which found this in three sections at once, each under a
  // docstring explaining why it could not happen.
  const lastPoint = () => d.lastPoint();
        const b = section("analyse", "Analyze & Coordinate · code, cost & 4D", { requires: "sourceIfc", tool: true });
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px";
        b.appendChild(toolBtn2("🏗 Site logistics (4D timeline)", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          let resources: LogisticsResource[];
          try { resources = (await api.getLogistics(pid)).resources; }
          catch { toast("Could not load logistics", "error"); return; }
          logisticsOverlay.render(resources); logisticsOverlay.showAll();
          showResult("Site logistics — time-phased on the 4D timeline", (body) => {
            body.appendChild(resultNote(`Temporary construction resources (cranes / laydown / gates / fencing / haul routes) placed in project coordinates with a schedule window — they show + hide as the timeline advances. Click in the model first to set a point, then add a resource there. <b>${resources.length}</b> placed.`, "ok"));
            const list = document.createElement("div"); list.style.margin = "6px 0";
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "6px";
            const draw = () => {
              list.innerHTML = "";
              resources.forEach((r, i) => {
                const row = document.createElement("div"); row.className = "selset-row";
                const s = document.createElement("span"); s.className = "selset-name"; s.style.cursor = "default";
                s.textContent = `${r.kind} · ${r.label || r.id}${r.start ? ` · ${r.start}→${r.end || "…"}` : ""}`;
                const del = document.createElement("button"); del.className = "selset-del"; del.textContent = "✕";
                del.onclick = () => { resources.splice(i, 1); logisticsOverlay.render(resources); draw(); };
                row.append(s, del); list.appendChild(row);
              });
              if (!resources.length) { const e = document.createElement("div"); e.className = "meta"; e.textContent = "No resources yet."; list.appendChild(e); }
            };
            draw(); body.appendChild(list);
            // add form
            const form = document.createElement("div"); form.style.cssText = "display:flex;flex-wrap:wrap;gap:2px;align-items:center;margin:6px 0";
            const kind = document.createElement("select"); kind.className = "portal-filter"; kind.style.cssText = "font-size:12px;margin:2px";
            for (const k of ["crane", "hoist", "laydown", "gate", "fence", "haul_route", "trailer", "parking"]) { const o = document.createElement("option"); o.value = k; o.textContent = k; kind.appendChild(o); }
            const mk = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "font-size:12px;margin:2px;flex:0 1 110px;min-width:0"; return i; };
            const label = mk("label"); const startI = mk("start YYYY-MM-DD"); const endI = mk("end YYYY-MM-DD");
            const add = document.createElement("button"); add.className = "mini-btn"; add.textContent = "＋ at last point";
            add.onclick = () => {
              const lp = lastPoint();
              if (!lp) { notify("click a point in the model first", "error"); return; }
              const id = `r${Date.now().toString(36)}`;
              const e = lp.x, n = -lp.z;                 // world (E, y, -N) → E, N
              const r: LogisticsResource = { id, kind: kind.value, label: label.value.trim() || kind.value, position: [e, 0, n], start: startI.value.trim() || undefined, end: endI.value.trim() || undefined };
              if (kind.value === "crane") r.radius = 25;
              resources.push(r); logisticsOverlay.render(resources); label.value = ""; draw();
              status.textContent = `added ${kind.value} at E ${e.toFixed(1)}, N ${n.toFixed(1)}`;
            };
            form.append(kind, label, startI, endI, add); body.appendChild(form);
            // time-phase + save
            const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center";
            const dateI = mk("show at date"); dateI.style.flex = "0 1 130px";
            const phase = document.createElement("button"); phase.className = "mini-btn"; phase.textContent = "⏱ Show at date";
            phase.onclick = async () => {
              try { const st = await api.putLogistics(pid, resources).then(() => api.logisticsState(pid, dateI.value.trim() || undefined));
                logisticsOverlay.showActive(new Set(st.active.map((x) => x.id)));
                status.textContent = `${st.active_count} of ${st.total} active${st.date ? ` on ${st.date}` : ""}`;
              } catch (e) { notify((e as Error).message, "error"); }
            };
            const showAll = document.createElement("button"); showAll.className = "mini-btn"; showAll.textContent = "👁 Show all";
            showAll.onclick = () => { logisticsOverlay.showAll(); status.textContent = ""; };
            const save = document.createElement("button"); save.className = "mini-btn on"; save.textContent = "💾 Save";
            save.onclick = async () => { try { await api.putLogistics(pid, resources); notify("logistics saved", "success"); } catch (e) { notify((e as Error).message, "error"); } };
            actions.append(dateI, phase, showAll, save); body.append(actions, status);
          });
        }));
        b.appendChild(toolBtn2("⏱ 4D construction sequence (playback)", () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          // teardown rides the modal's onClose (✕/Esc/backdrop/replaced) — stops the play timer and
          // restores visibility, so closing mid-play never leaves the model isolated (HARDEN-2 B5).
          showResult("4D construction sequence", (body) => {
            fourD.dispose = populate4dPanel(body, { api, pid, layers: layerMgr, notify });
          }, () => { fourD.dispose?.(); fourD.dispose = null; });
        }));
        b.appendChild(toolBtn2("🏛 Occupancy & egress (IBC pre-check)", () => withLoading(container, "Computing occupancy load + egress", async () => {
          let r;
          try { r = await api.codecheckEgress(pid); }
          catch { toast("Needs a source IFC with IfcSpaces", "error"); return; }
          const load = r.building.occupant_load;
          out.textContent = `${load} occ · egress ${r.egress.adequate === false ? "SHORT" : "ok"}`;
          showResult("Occupancy load & egress — IBC pre-check", (body) => {
            body.appendChild(resultNote(`Computed from <b>${r!.building.spaces}</b> spaces + doors — <b>${load}</b> total occupants over ${r!.building.area_ft2.toLocaleString()} ft². `
              + `Required egress width <b>${r!.egress.required_width_in} in</b> vs <b>${r!.egress.provided_width_in} in</b> provided → `
              + `<b>${r!.egress.adequate == null ? "n/a" : r!.egress.adequate ? "adequate" : "SHORT — add egress width"}</b>.`,
              r!.egress.adequate === false ? "bad" : "ok"));
            if (r!.building.spaces_missing_area) body.appendChild(resultNote(`${r!.building.spaces_missing_area} space(s) have no floor-area quantity and were skipped — add areas for a complete count.`, ""));
            if (r!.by_occupancy.length) body.appendChild(kvTable(r!.by_occupancy.map((o) => ({ k: `${o.occupancy} (1:${o.factor} ${o.basis})`, v: `${o.load} occ · ${o.spaces} space(s) · ${o.area_ft2.toLocaleString()} ft²` }))));
            if (r!.doors.below_min_32in) {
              body.appendChild(resultNote(`${r!.doors.below_min_32in} of ${r!.doors.checked} doors are below the 32 in (0.81 m) minimum clear width (IBC 1010.1.1).`, "bad"));
              body.appendChild(toolBtn2("◎ Isolate narrow doors in 3D", () => { void layerMgr.isolateGuids(r!.doors.fail_guids); }));
            }
            const twoExit = r!.spaces.filter((s) => s.needs_2_exits);
            if (twoExit.length) body.appendChild(resultNote(`${twoExit.length} space(s) exceed 49 occupants → two exits required (IBC 1006.2): ${twoExit.slice(0, 6).map((s) => s.name || "space").join(", ")}${twoExit.length > 6 ? "…" : ""}.`, ""));
            body.appendChild(resultNote(r!.disclaimer + " Cited: " + r!.citations.join("; ") + ".", ""));
            const nFindings = r!.doors.below_min_32in + (r!.egress.adequate === false ? 1 : 0) + r!.spaces.filter((s) => s.needs_2_exits).length;
            if (nFindings) {
              const bcf = toolBtn2(`📌 Promote ${nFindings} finding${nFindings === 1 ? "" : "s"} to BCF issues`, async () => {
                try { const res = await api.codecheckEgressBcf(pid); notify(`created ${res.created} BCF issue${res.created === 1 ? "" : "s"} — see the Issues panel`, "success"); await refreshIssues(); }
                catch (e) { notify((e as Error).message, "error"); }
              });
              bcf.title = "Create trackable BCF topics from the code findings (below-min doors, egress shortfall, two-exit spaces)";
              body.appendChild(bcf);
            }
          });
        })));
        const runCodeAnalysis = (jur: string) => withLoading(container, "Assembling the IBC code-analysis summary", async () => {
          let r;
          try { r = await api.codeAnalysis(pid, jur ? { jurisdiction: jur } : {}); }
          catch { toast("Needs a source IFC with IfcSpaces", "error"); return; }
          const ed = r.code_context.ibc_edition;
          out.textContent = `${r.occupancy.group} · ${r.construction_type.split(" ")[0]} · ${r.building.stories} st${ed ? ` · IBC ${ed}` : ""}`;
          showResult("Code analysis — permit-set G-series summary", (body) => {
            const cc = r!.code_context;
            body.appendChild(resultNote(`Code edition: <b>IBC ${cc.ibc_edition ?? "—"}</b> `
              + (cc.resolved ? `(${cc.jurisdiction} adoption, as-of ${cc.as_of})` : "(national baseline — enter your state below)")
              + `. <i>${cc.verify}</i>`, cc.resolved ? "ok" : ""));
            body.appendChild(resultNote(`The IBC <b>code-analysis summary</b> a permit set carries on its G-series code sheet, assembled from the model. `
              + `Verify allowable area/height against the actual Table 506.2 with the AHJ.`, "ok"));
            body.appendChild(kvTable([
              { k: "Occupancy group", v: `${r!.occupancy.group}${r!.occupancy.primary && r!.occupancy.primary !== "—" ? ` — ${r!.occupancy.primary}` : ""}` },
              { k: "Occupancy mix", v: r!.occupancy.mix.length ? r!.occupancy.mix.join(", ") : "—" },
              { k: "Construction type", v: r!.construction_type },
              { k: "Sprinklered (NFPA-13)", v: r!.sprinklered ? "yes" : "no" },
              { k: "Stories", v: String(r!.building.stories) },
              { k: "Gross area", v: `${r!.building.gross_area_ft2.toLocaleString()} ft²` },
              { k: "Computed occupant load", v: `${r!.building.occupant_load} occ` },
            ]));
            body.appendChild(resultNote(`Egress width required <b>${r!.egress.required_width_in} in</b> vs <b>${r!.egress.provided_width_in} in</b> provided → `
              + `<b>${r!.egress.adequate == null ? "n/a" : r!.egress.adequate ? "adequate" : "SHORT"}</b>. `
              + `Doors checked ${r!.doors.checked}${r!.doors.below_min_32in ? ` · ${r!.doors.below_min_32in} below 32 in` : ""}.`,
              r!.egress.adequate === false || r!.doors.below_min_32in ? "bad" : "ok"));
            if (r!.occupant_load_by_occupancy.length) body.appendChild(kvTable(r!.occupant_load_by_occupancy.map((o) => ({ k: o.occupancy, v: `${o.load} occ · ${o.area_ft2.toLocaleString()} ft²` }))));
            body.appendChild(resultNote(`<b>Allowable area & height</b> — ${r!.allowable.note} Sprinkler increase: <b>${r!.allowable.sprinkler_increase}</b>. `
              + `Governing sections: ${r!.allowable.sections.join("; ")}.`, ""));
            // CODE-1/3: set the jurisdiction → re-run the analysis edition-aware (cites the adopted IBC).
            const jurWrap = document.createElement("div"); jurWrap.style.cssText = "display:flex;gap:6px;align-items:center;margin:6px 0";
            const jurLbl = document.createElement("span"); jurLbl.className = "meta"; jurLbl.textContent = "Jurisdiction (US state):";
            const jurIn = document.createElement("input"); jurIn.className = "portal-filter"; jurIn.placeholder = "e.g. CA"; jurIn.maxLength = 2; jurIn.value = cc.jurisdiction || ""; jurIn.style.cssText = "width:80px;font-size:12px";
            const jurBtn = document.createElement("button"); jurBtn.className = "mini-btn"; jurBtn.textContent = "↻ Re-check for this state";
            jurBtn.onclick = () => { void runCodeAnalysis(jurIn.value.trim().toUpperCase()); };
            jurIn.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); void runCodeAnalysis(jurIn.value.trim().toUpperCase()); } };
            jurWrap.append(jurLbl, jurIn, jurBtn); body.appendChild(jurWrap);
            body.appendChild(resultNote(r!.disclaimer, ""));
          });
        });
        b.appendChild(toolBtn2("🏛 Code analysis (G-series summary)", () => { void runCodeAnalysis(""); }));
        // CODE-EBC — existing-building scope classifier (IEBC Work Area Method), inferred from phasing
        const runEbc = (jur: string) => withLoading(container, "Classifying the existing-building scope (IEBC)", async () => {
          let r;
          try { r = await api.ebcClassify(pid, { infer: true, ...(jur ? { jurisdiction: jur } : {}) }); }
          catch { toast("Needs a source IFC to infer scope from phasing", "error"); return; }
          out.textContent = r.classification ? `${r.classification}${r.code.edition ? ` · IEBC ${r.code.edition}` : ""}` : "no scope";
          showResult("Existing-building scope — IEBC Work Area Method", (body) => {
            body.appendChild(resultNote(`Inferred from the model's <b>phasing</b> (existing vs new/demolish). `
              + `The IEBC governs renovation/adaptive-reuse; this classifies the <b>scope of work</b> → which provisions apply.`, ""));
            if (!r!.ok) {
              body.appendChild(resultNote(r!.reason || "No scope classified.", "bad"));
            } else {
              body.appendChild(resultNote(`Classification: <b>${r!.classification}</b>`
                + (r!.work_area_pct != null ? ` · work area ≈ <b>${Math.round(r!.work_area_pct)}%</b>` : "")
                + `. <span class="meta">${r!.gist || ""}</span>`, "ok"));
              body.appendChild(resultNote(`Compliance method: <b>${r!.method}</b> (${r!.method_cite}). `
                + `Code edition: <b>IEBC ${r!.code.edition ?? "—"}</b> `
                + (r!.code.adoption_resolved ? `(${r!.code.jurisdiction} adoption)` : "(national baseline — set your state below)")
                + `.`, r!.code.adoption_resolved ? "ok" : ""));
              if (r!.applies?.length) body.appendChild(kvTable(r!.applies.map((a) => ({ k: a.classification, v: `${a.section} · ${a.requirements}` }))));
              if (r!.basis?.length) body.appendChild(resultNote(`<b>How this was inferred:</b> ${r!.basis.join(" ")}`, ""));
              if (r!.notes?.length) body.appendChild(resultNote(r!.notes.join(" "), ""));
            }
            // jurisdiction re-check (edition-aware) — mirror the code-analysis flow
            const jurWrap = document.createElement("div"); jurWrap.style.cssText = "display:flex;gap:6px;align-items:center;margin:6px 0";
            const jurLbl = document.createElement("span"); jurLbl.className = "meta"; jurLbl.textContent = "Jurisdiction (US state):";
            const jurIn = document.createElement("input"); jurIn.className = "portal-filter"; jurIn.placeholder = "e.g. CA"; jurIn.maxLength = 2; jurIn.value = r!.code.jurisdiction || ""; jurIn.style.cssText = "width:80px;font-size:12px";
            const jurBtn = document.createElement("button"); jurBtn.className = "mini-btn"; jurBtn.textContent = "↻ Re-check for this state";
            jurBtn.onclick = () => { void runEbc(jurIn.value.trim().toUpperCase()); };
            jurIn.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); void runEbc(jurIn.value.trim().toUpperCase()); } };
            jurWrap.append(jurLbl, jurIn, jurBtn); body.appendChild(jurWrap);
            body.appendChild(resultNote(r!.disclaimer, ""));
          });
        });
        b.appendChild(toolBtn2("🏚 Existing-building code (IEBC scope)", () => { void runEbc(""); }));
        // EST-1 — rough labour cost + duration from the model's quantities (productivity rates)
        b.appendChild(toolBtn2("💰 Cost estimate (labour · material · equipment)", () => withLoading(container, "Queueing cost estimate", async () => {
          let e;
          try {
            e = await enqueueAndWait(api, pid, "labor_estimate", {
              loading: "commercial", rate: 25, full: true,
            }) as Awaited<ReturnType<ApiClient["laborEstimate"]>>;
          }
          catch { toast("Needs a source IFC", "error"); return; }
          const grand = e.total_cost ?? e.total_labor_cost;
          out.textContent = `${e.total_man_hours.toLocaleString()} mh · $${Math.round(grand).toLocaleString()}`;
          showResult("Cost estimate — productivity rates", (body) => {
            body.appendChild(resultNote(`Rough <b>cost</b> takeoff from the model (${e!.line_count} activity(ies), `
              + `${e!.loading} loading ×${e!.loading_factor}, $${e!.hourly_rate}/hr labour): `
              + `<b>${e!.total_man_hours.toLocaleString()} man-hours</b>.`, e!.line_count ? "ok" : ""));
            if (!e!.line_count) body.appendChild(resultNote("No estimable quantities yet — author walls / slabs / columns.", ""));
            if (e!.has_material_equipment) {
              body.appendChild(kvTable([
                { k: "Labour", v: `$${Math.round(e!.total_labor_cost).toLocaleString()}` },
                { k: "Material", v: `$${Math.round(e!.total_material_cost ?? 0).toLocaleString()}` },
                { k: "Equipment", v: `$${Math.round(e!.total_equipment_cost ?? 0).toLocaleString()}` },
                { k: "Total (excl. overhead/profit)", v: `$${Math.round(e!.total_cost ?? 0).toLocaleString()}`, strong: true },
              ]));
            }
            if (e!.lines.length) {
              body.appendChild(kvTable(e!.lines.map((l) => ({
                k: `${l.activity.replace(/_/g, " ")} (${l.group})`,
                v: `${l.quantity} ${l.unit} → ${l.man_hours} mh · ${l.crew_days} cd`
                  + (l.line_total != null ? ` · $${Math.round(l.line_total).toLocaleString()}` : ` · $${Math.round(l.labor_cost).toLocaleString()}`) }))));
            }
            body.appendChild(resultNote(e!.note, ""));
          });
        })));
        b.appendChild(toolBtn2("⚡ Envelope energy (UA · EUI)", () => withLoading(container, "Queueing envelope energy", async () => {
          let e;
          try {
            e = await enqueueAndWait(api, pid, "energy_analyze") as Awaited<ReturnType<ApiClient["energy"]>>;
          }
          catch { toast("Needs a source IFC", "error"); return; }
          out.textContent = `EUI ${e.eui_kwh_m2_yr} kWh/m²·yr`;
          showResult("Envelope energy — UA + degree-day", (body) => {
            body.appendChild(resultNote(
              `Annual <b>${Math.round(e!.annual_kwh.total).toLocaleString()} kWh</b> · EUI <b>${e!.eui_kwh_m2_yr}</b> kWh/m²·yr.`,
              "ok"));
            body.appendChild(kvTable([
              { k: "Heating load", v: `${e!.loads.design_heating_kw} kW` },
              { k: "Cooling load", v: `${e!.loads.design_cooling_kw} kW` },
              { k: "Heating (annual)", v: `${Math.round(e!.annual_kwh.heating).toLocaleString()} kWh` },
              { k: "Cooling (annual)", v: `${Math.round(e!.annual_kwh.cooling).toLocaleString()} kWh` },
            ]));
          });
        })));
        // RFI-0 NL-QA — ask a plain-language question, get a cited answer from the model's own data
        const qaWrap = document.createElement("div");
        qaWrap.style.cssText = "display:flex;gap:4px;margin:4px 2px";
        const qaInput = document.createElement("input");
        qaInput.type = "text";
        qaInput.placeholder = "Ask: what governs <element>? · what's blocking approval?";
        qaInput.style.cssText = "flex:1;min-width:0;font-size:11px;padding:3px 6px";
        qaInput.setAttribute("aria-label", "Ask a question about the model");
        const qaBtn = document.createElement("button");
        qaBtn.className = "tool-btn"; qaBtn.textContent = "Ask"; qaBtn.style.cssText = "font-size:11px;padding:3px 10px";
        const askQa = () => {
          const q = qaInput.value.trim();
          if (!q) return;
          void withLoading(container, "Asking the model", async () => {
            let r;
            try { r = await api.rfiQa(pid, q); }
            catch { toast("Needs a source IFC", "error"); return; }
            out.textContent = r.answer.slice(0, 60);
            showResult("Ask the model — cited answer", (body) => {
              body.appendChild(resultNote(r!.answer, r!.ready === false ? "bad" : "ok"));
              if (r!.citations.length) {
                body.appendChild(kvTable(r!.citations.map((c) => ({ k: c.kind, v: c.ref }))));
                const guids = r!.citations.flatMap((c) => c.guids || []);
                if (guids.length) body.appendChild(toolBtn2(`◎ Isolate ${guids.length} cited element(s)`, () => { void layerMgr.isolateGuids(guids); }));
              }
              body.appendChild(resultNote(r!.disclaimer, ""));
            });
          });
        };
        qaBtn.onclick = askQa;
        qaInput.onkeydown = (e) => { if (e.key === "Enter") askQa(); };
        qaWrap.append(qaInput, qaBtn);
        b.appendChild(qaWrap);
        b.appendChild(out);
}
