import { type ApiClient, type PropLayer, type PropMapRule } from "../../api/client";
import { enqueueAndWait } from "../../api/waitForJob";

import type { ModelIdMap } from "../modelIds";
import { askText } from "../../ui/prompt";
import { confirmModal, promptModal } from "../../ui/modal";
import { kvTable, resultNote, showResult } from "../../ui/result";
import { guidsFromSample } from "../warningSample";
import { sharedParamsButton } from "./sharedParamsPanel";
import { projectModelsButton } from "./projectModelsPanel";
import { modelReviewButton } from "./modelReviewPanel";
import { runIdsValidate } from "./idsValidate";
import { escapeHtml, toast, withLoading } from "../../ui/feedback";
import { LayerManager } from "../../tools/layers";
import { ModelLoader } from "../loader";
import { SelectionSets } from "../selectionSets";

/**
 * R39-DECOMP-VIEWER ② — the clash / QA tool section, out of `app.ts`.
 *
 * 851 lines, the largest of the four `builders` in `buildToolsPanel` and the slice that actually
 * moves the number: `app.ts` 5,114 → 4,263.
 *
 * ## The gate, stated because it is not the obvious one
 *
 * **`tsc` is the parity gate for this move. The suite is NOT claimed as one** — nothing in it
 * imports `app.ts`, because `createViewerApp` needs a WebGL context and a Fragments worker. Every
 * dependency below is therefore an *explicit typed parameter*: a capture that fails to be threaded
 * is a compile error rather than a runtime surprise.
 *
 * ## The one thing `tsc` cannot see, and why `selectedGuid` is a function
 *
 * `app.ts` holds `selectedGuid` as a **`let`**. Passing it by value would compile cleanly and freeze
 * whatever it held when the panel was built — every handler in here would then act on a stale
 * selection, silently, forever. It arrives as `selectedGuid()` so that class of bug is impossible by
 * construction rather than by remembering. `pid` and `projectId` are `const` in `app.ts` and are
 * safe as values.
 *
 * ## The body is byte-identical and deliberately not re-indented
 *
 * It sits at its original depth so the diff reads as a pure move. Re-indenting 851 lines would risk
 * changing the content of any multi-line template literal among them — a silent, user-visible edit
 * inside what is supposed to be a no-behaviour-change extraction. Cosmetics are a later, separate,
 * checkable change.
 */

export interface QaDeps {
  section: (key: string, title: string,
            opts?: { requires?: "project" | "sourceIfc"; tool?: boolean }) => HTMLElement | null;
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  /** `const` in app.ts — safe by value. */
  pid: string;
  /** `const` in app.ts — safe by value. */
  projectId: string | null;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** ACCESSOR: `selectedGuid` is a `let` in app.ts. A value here would freeze at panel-build time. */
  selectedGuid: () => string | null;
  selectMap: (map: ModelIdMap | null, opts?: { guid?: string; fit?: boolean }) => Promise<void>;
  sets: SelectionSets;
  layerMgr: LayerManager;
  loader: ModelLoader;
  nextId: (label?: string) => string;
  refreshIssues: () => Promise<void | boolean>;
  /** The viewer's host element — several QA tools mount overlays onto it. */
  container: HTMLElement;
  reloadModelPins: () => Promise<void | boolean>;
  selectByGuid: (guid: string, fit?: boolean) => Promise<void | boolean>;
  waitForPublish: (pid: string, onTick?: (s: string) => void) => Promise<string>;
  refreshFederation: () => void;
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string,
                    previewId?: string | null) => Promise<{ applied: boolean; refused: boolean }>;
  fitToModels: () => void;
  loadProjectModel: () => Promise<boolean>;
}

/** Build the "Analyze & Coordinate · clash / QA" section. No-op when its gate refuses. */
export function buildQaSection(d: QaDeps): void {
  const { section, toolBtn2, api, pid, projectId, notify, selectMap, sets, layerMgr, loader,
          nextId, refreshIssues, container, reloadModelPins, selectByGuid, waitForPublish,
          refreshFederation, authorAndReload, fitToModels, loadProjectModel } = d;
  // NOT `const selectedGuid = d.selectedGuid()`. That is what this file used to do, and it is the
  // exact bug the docstring above says is impossible by construction: the accessor was threaded
  // correctly through the seam and then collapsed to a value on arrival. The panel is built at app
  // init, before anything is selected, so the captured value was `null` FOREVER — "Related elements"
  // and the layer override button answered "select an element in 3D first" no matter what was
  // selected. Two dead tools, on main, under a comment explaining why they could not be.
  const selectedGuid = () => d.selectedGuid();
        const b = section("qa", "Analyze & Coordinate · clash / QA", { requires: "sourceIfc", tool: true });
        if (!b) return;
        const out = document.createElement("div"); out.className = "meta"; out.style.marginTop = "4px";
        b.appendChild(toolBtn2("⚡ Run clash (struct)", () => withLoading(container, "Queueing clash detection", async () => {
          const r = await enqueueAndWait(api, pid, "clash_detect", {
            a: "IfcBeam,IfcSlab", b: "IfcColumn", min_volume: 0.05, create_topics: true,
          }) as { count: number; created_topics?: number };
          out.textContent = `${r.count} clashes · ${r.created_topics ?? 0} topics`;
          toast(`Clash: ${r.count} found, ${r.created_topics ?? 0} topics created`, r.count ? "info" : "success");
          await refreshIssues(); await reloadModelPins();
          showResult("Clash detection", (body) => {
            body.appendChild(resultNote(`<b>${r.count}</b> clashes found · <b>${r.created_topics}</b> RFI topics created.`, r.count ? "bad" : "ok"));
            body.appendChild(toolBtn2("Open Issues panel", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
          });
        })));
        // A4: a compact scene digest — what's in the model, one glance (also grounds the AI command bar)
        b.appendChild(toolBtn2("🔎 Model digest (what's in the model)", () => withLoading(container, "Summarising the model", async () => {
          let d;
          try { d = await api.sceneDigest(pid); }
          catch { toast("Needs a source IFC", "error"); return; }
          out.textContent = `${d.totals.elements} elts · ${d.totals.storeys} storey(s)`;
          showResult("Model digest", (body) => {
            body.appendChild(resultNote(d!.prose, ""));
            const top = Object.entries(d!.by_class).slice(0, 10);
            if (top.length) body.appendChild(kvTable(top.map(([c, n]) => ({ k: c.replace(/^Ifc/, ""), v: String(n) }))));
            if (d!.mep.systems) body.appendChild(resultNote(`<b>MEP</b> — ${d!.mep.systems} system(s); `
              + Object.entries(d!.mep.by_discipline).map(([k, v]) => `${k} (${v.systems})`).join(", ")
              + (d!.mep.has_fire_protection ? " · fire-protection present" : ""), ""));
            const phased = Object.entries(d!.phasing).filter(([k, v]) => v && k !== "UNSET");
            if (phased.length) body.appendChild(resultNote(`<b>Phasing</b> — ` + phased.map(([k, v]) => `${v} ${k.toLowerCase()}`).join(", "), ""));
            if (d!.hygiene.issues) body.appendChild(resultNote(`<b>${d!.hygiene.issues}</b> model-hygiene issue(s) — see Model Health.`, "bad"));
          });
        })));
        // VIEW-TEMPLATES — saved view definitions, listed and APPLIED. Both halves were unreachable:
        // `viewTemplates` (the list) and `resolveViewTemplate` (what it resolves to on THIS model).
        // A saved view nobody can apply is a stored preference with no effect.
        //
        // Applying is reversible — it isolates and colours, it does not edit the model — which is why
        // this is safe to wire without a confirmation step, unlike the template WRITE endpoints.
        b.appendChild(toolBtn2("👁 View templates (apply a saved view)", () => withLoading(container, "Reading view templates", async () => {
          let r;
          try { r = await api.viewTemplates(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = `${r.templates.length} template(s)`;
          showResult("View templates", (body) => {
            if (!r!.templates.length) {
              body.appendChild(resultNote("No view templates saved for this project.", ""));
              return;
            }
            for (const t of r!.templates) {
              const row = document.createElement("div");
              row.className = "meta";
              row.style.cssText = "padding:3px 0;border-bottom:1px solid var(--border-subtle);cursor:pointer";
              row.innerHTML = `<b>${escapeHtml(t.name)}</b>`
                + (t.isolate ? ` · isolate ${escapeHtml(t.isolate)}` : "")
                + (t.hide_classes?.length ? ` · hides ${t.hide_classes.length}` : "")
                + (t.rules?.length ? ` · ${t.rules.length} colour rule(s)` : "");
              row.title = "Resolve against this model and apply";
              row.onclick = async () => {
                let v;
                try { v = await api.resolveViewTemplate(pid, t.id); }
                catch (e) { toast((e as Error).message, "error"); return; }
                // Resolve first, report second, apply third. A template that resolves to NOTHING on
                // this model would otherwise isolate an empty set and read as "the model vanished".
                if (!v.visible.length) {
                  notify(`"${t.name}" matches no elements in this model — nothing applied`, "info");
                  return;
                }
                await layerMgr.isolateGuids(v.visible.slice(0, 5000));
                notify(`Applied "${t.name}" — ${v.visible_count} visible, ${v.hidden_count} hidden`
                  + (v.colored_count ? `, ${v.colored_count} coloured` : ""), "success");
              };
              body.appendChild(row);
            }
            body.appendChild(resultNote("Applying isolates and colours — it does not change the model.", ""));
          });
        })));

        // CLASH-IMPORT — bring in clash results authored elsewhere (Navisworks and friends). Additive:
        // it imports findings, it does not modify geometry.
        const clashXml = document.createElement("input");
        clashXml.type = "file"; clashXml.accept = ".xml"; clashXml.style.display = "none";
        clashXml.onchange = async () => {
          const f = clashXml.files?.[0];
          if (!f) return;
          await withLoading(container, "Importing clash XML", async () => {
            try {
              const res = await api.importClashXml(pid, f);
              notify(`Imported ${res.imported ?? 0} clash result(s) from ${f.name}`, "success");
              await refreshIssues();
            } catch (e) { toast((e as Error).message, "error"); }
          });
          clashXml.value = "";        // so re-picking the same file fires change again
        };
        b.appendChild(clashXml);
        b.appendChild(toolBtn2("📥 Import clash XML (from another tool)", () => clashXml.click()));

        // ENVELOPE-R — assembly build-ups with R/U values. Each assembly carries its GUIDs, so the
        // list selects; a thermal report you cannot point at in the model is a spreadsheet.
        b.appendChild(toolBtn2("🧱 Envelope assemblies (R / U values)", () => withLoading(container, "Reading assemblies", async () => {
          let r;
          try { r = await api.modelAssemblyThermal(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          const list = r.assemblies || [];
          out.textContent = `${list.length} assembly(ies)`;
          showResult("Envelope assemblies", (body) => {
            if (!list.length) { body.appendChild(resultNote("No layered assemblies found in this model.", "")); return; }
            for (const a of list) {
              const row = document.createElement("div");
              row.className = "meta";
              row.style.cssText = "padding:3px 0;border-bottom:1px solid var(--border-subtle)";
              row.innerHTML = `<b>${escapeHtml(a.name || "unnamed")}</b> · ${a.element_count} element(s) · `
                + `${a.thickness_m}m · R ${a.r_value} (${a.r_value_imperial} imp)`;
              if (a.guids?.length) {
                row.style.cursor = "pointer"; row.title = `Select ${a.guids.length} element(s)`;
                row.onclick = async () => { await selectMap(await sets.fromGuids(a.guids.slice(0, 200))); };
              }
              body.appendChild(row);
              if (a.layers?.length) {
                body.appendChild(kvTable(a.layers.map((l) => ({
                  k: `· ${escapeHtml(l.name)}`, v: `${l.thickness_m}m · R ${l.r_value}`,
                }))));
              }
            }
          });
        })));

        // Shared parameters live in their own module: the retire flow is a PUT that replaces the
        // whole registry, and it took this file past the size pin that exists to force that move.
        b.appendChild(sharedParamsButton({ api, pid, out, container, toolBtn2 }));

        // WIP-PROGRESS — installed vs total. `available` is a real answer: without verified progress
        // there is nothing to report, and rendering 0% would assert that nothing is installed.
        b.appendChild(toolBtn2("📈 Model progress (installed vs total)", () => withLoading(container, "Reading progress", async () => {
          let r;
          try { r = await api.wipModelProgress(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          if (!r.available) {
            out.textContent = "no progress data";
            showResult("Model progress", (body) => body.appendChild(resultNote(
              escapeHtml(r!.note || "No verified progress recorded yet.")
              + " — that is not the same as 0% complete.", "")));
            return;
          }
          out.textContent = `${r.percent_complete ?? r.percent_complete_count ?? 0}% complete`;
          showResult("Model progress", (body) => {
            body.appendChild(resultNote(`<b>${r!.installed_elements ?? 0}</b> of <b>${r!.total_elements ?? 0}</b> `
              + `element(s) installed · <b>${r!.percent_complete_count ?? 0}%</b> by count`
              + (r!.method ? ` · method: ${escapeHtml(r!.method)}` : ""), ""));
            if (r!.quantity) {
              body.appendChild(kvTable([
                { k: "Quantity basis", v: escapeHtml(r!.quantity) },
                { k: "Elements with quantity", v: String(r!.elements_with_quantity ?? 0) },
                { k: "Installed / total", v: `${r!.installed_quantity ?? 0} / ${r!.total_quantity ?? 0}` },
                { k: "Percent by quantity", v: `${r!.percent_complete_quantity ?? 0}%` },
              ]));
            }
            if (r!.note) body.appendChild(resultNote(escapeHtml(r!.note), ""));
          });
        })));

        // Registered models live in their own module: the remove flow is destructive and its
        // confirmation has to predict whether federated clash survives, which is real logic.
        b.appendChild(projectModelsButton({ api, pid, out, container, toolBtn2 }));

        // MODEL REVIEW — the publish history's review gate. Its own module for the same reason as
        // the two above: `approve` is a TERMINAL transition, so the confirmation has to say so, and
        // the client type first had to stop discarding the four review keys the server already sent.
        b.appendChild(modelReviewButton({ api, pid, out, container, toolBtn2 }));

        // FILL-MATRIX — property completeness by class, with the worst gaps named. The data-quality
        // question every IDS / COBie handover turns on, computed and unreachable.
        b.appendChild(toolBtn2("📊 Property fill matrix (completeness by class)", () => withLoading(container, "Measuring property fill", async () => {
          let r;
          try { r = await api.modelFillMatrix(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = `${r.class_count} class(es) · ${r.element_count} element(s)`;
          showResult("Property fill matrix", (body) => {
            body.appendChild(resultNote(`<b>${r!.element_count}</b> element(s) across <b>${r!.class_count}</b> class(es).`
              + (r!.note ? ` ${escapeHtml(r!.note)}` : ""), ""));
            if (r!.worst_gaps.length) {
              // Worst gaps first: a fill matrix nobody can act on is a spreadsheet. The gaps are the
              // actionable end of it.
              body.appendChild(resultNote("<b>Worst gaps</b> — lowest fill rate first:", ""));
              body.appendChild(kvTable(r!.worst_gaps.slice(0, 25).map((g) => ({
                k: `${escapeHtml(g.ifc_class)} · ${escapeHtml(g.pset)}.${escapeHtml(g.prop)}`,
                v: `${Math.round(g.fill_rate * 100)}% filled · ${g.blank} blank`,
              }))));
            } else {
              body.appendChild(resultNote("No property gaps at the reporting threshold.", "ok"));
            }
          });
        })));

        // SPLIT-PLAN — how this model would federate by storey, and what is UNASSIGNED. The
        // unassigned list is the point: an element in no storey is invisible to every storey filter.
        b.appendChild(toolBtn2("🗂 Split plan (federation by storey)", () => withLoading(container, "Planning split", async () => {
          let r;
          try { r = await api.modelSplitPlan(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = `${Object.keys(r.counts).length} storey(s) · ${r.unassigned_count} unassigned`;
          showResult("Split plan", (body) => {
            body.appendChild(resultNote(r!.unassigned_count
              ? `<b>${r!.unassigned_count}</b> element(s) belong to no storey — they are invisible to every storey filter.`
              : "Every element is assigned to a storey.", r!.unassigned_count ? "" : "ok"));
            body.appendChild(kvTable(Object.entries(r!.counts).map(([st, n]) => ({ k: escapeHtml(st), v: `${n} element(s)` }))));
            if (r!.unassigned.length) {
              const row = document.createElement("div");
              row.className = "meta"; row.style.cssText = "margin-top:4px;cursor:pointer";
              row.innerHTML = `<b>Select the ${r!.unassigned.length} unassigned</b>`;
              row.onclick = async () => { await selectMap(await sets.fromGuids(r!.unassigned.slice(0, 200))); };
              body.appendChild(row);
            }
            if (r!.note) body.appendChild(resultNote(escapeHtml(r!.note), ""));
          });
        })));

        // CONNECTIONS — the authored connection graph plus its size. Two endpoints, one readout:
        // the stats alone (nodes/edges) answer nothing a person asks, but they frame the list.
        b.appendChild(toolBtn2("🧩 Connections (authored joins + graph size)", () => withLoading(container, "Reading connections", async () => {
          let r, g;
          try { [r, g] = await Promise.all([api.elementConnections(pid), api.modelGraphStats(pid)]); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = `${r.count} connection(s)`;
          showResult("Connections", (body) => {
            body.appendChild(resultNote(`<b>${r!.count}</b> authored connection(s) across `
              + `<b>${r!.elements_connected}</b> element(s); busiest element has <b>${r!.max_degree}</b>. `
              + `Model graph: ${g!.nodes} node(s), ${g!.edges} edge(s).`, ""));
            if (Object.keys(g!.by_rel).length) {
              body.appendChild(resultNote("<b>Relationships by kind</b>", ""));
              body.appendChild(kvTable(Object.entries(g!.by_rel).map(([k, v]) => ({ k: escapeHtml(k), v: String(v) }))));
            }
            for (const c of r!.connections.slice(0, 50)) {
              const row = document.createElement("div");
              row.className = "meta";
              row.style.cssText = "padding:2px 0;border-bottom:1px solid var(--border-subtle);cursor:pointer";
              row.innerHTML = `${escapeHtml(c.a_class)} ↔ ${escapeHtml(c.b_class)}`
                + (c.description ? ` · ${escapeHtml(c.description)}` : "");
              row.title = "Select both ends";
              row.onclick = async () => { await selectMap(await sets.fromGuids([c.a, c.b])); };
              body.appendChild(row);
            }
          });
        })));

        // INTEROP-RT — the round-trip verdict, which nothing could show. It serialises the model,
        // re-parses it and compares GUID stability, class, name, containment, type and psets.
        // **GUID stability is a project non-negotiable** and the whole edit-recipe architecture rests
        // on it; this endpoint checks it and had no client caller, so the promise was unverifiable
        // from the product. Distinct from `roundtripDiff`, which compares a file YOU bring back —
        // this one asks whether OUR OWN export is lossless.
        b.appendChild(toolBtn2("🔁 Round-trip fidelity (is our export lossless?)", () => withLoading(container, "Serialising and re-parsing", async () => {
          let r;
          try { r = await api.modelRoundtrip(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = r.fidelity_ok ? "round-trip clean" : `${r.counts.missing + r.counts.added + r.counts.changed} discrepancy(ies)`;
          showResult("Round-trip fidelity", (body) => {
            body.appendChild(resultNote(r!.fidelity_ok
              ? `<b>Lossless</b> — all ${r!.element_count} elements survived serialise → re-parse with GUID, class, name, containment, type and psets intact.`
              : `<b>Not lossless</b> — ${r!.counts.missing} missing · ${r!.counts.added} added · ${r!.counts.changed} changed, of ${r!.element_count} elements.`,
              r!.fidelity_ok ? "ok" : "bad"));
            // MISSING is the one that matters most: an element that does not survive our own export
            // is data loss, and GUID stability is what every recipe and every pin depends on.
            for (const [label, guids] of [["Missing after round-trip", r!.missing], ["Appeared after round-trip", r!.added]] as const) {
              if (!guids.length) continue;
              const row = document.createElement("div");
              row.className = "meta"; row.style.cssText = "margin-top:4px;cursor:pointer";
              row.innerHTML = `<b>${label}</b>: ${guids.length}`;
              row.title = "Select these elements";
              row.onclick = async () => { await selectMap(await sets.fromGuids(guids.slice(0, 200))); };
              body.appendChild(row);
            }
            if (r!.changed.length) {
              body.appendChild(resultNote("<b>Changed</b> — survived, but an aspect differs:", ""));
              body.appendChild(kvTable(r!.changed.slice(0, 50).map((c) => ({
                k: escapeHtml(c.class), v: escapeHtml(c.aspects.join(", ")),
              }))));
            }
          });
        })));

        // AUTH-CONSTRAINTS — the model's OWN constraint graph: broken RelVoids/RelFills hosts,
        // dangling fills, storey-containment disagreements. Errors and warnings on the model's
        // internal consistency, with no way to see them until now.
        b.appendChild(toolBtn2("🔗 Constraint graph (hosts, fills, containment)", () => withLoading(container, "Validating constraint graph", async () => {
          let r;
          try { r = await api.modelConstraints(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = r.issue_count ? `${r.errors} error(s) · ${r.warnings} warning(s)` : "constraint graph clean";
          showResult("Constraint graph", (body) => {
            body.appendChild(resultNote(r!.issue_count
              ? `<b>${r!.errors}</b> error(s) · <b>${r!.warnings}</b> warning(s) across `
                + `${r!.checked.openings} opening(s), ${r!.checked.elements_level_checked} element(s), ${r!.checked.storeys} storey(s).`
              : `No broken hosts, dangling fills or containment disagreements — `
                + `${r!.checked.openings} opening(s) and ${r!.checked.storeys} storey(s) checked.`,
              r!.errors ? "bad" : r!.warnings ? "" : "ok"));
            // The note carries what was SKIPPED as unmeasurable. Dropping it would turn "we could not
            // check these" into "these are fine", which is the difference the route is careful about.
            if (r!.note) body.appendChild(resultNote(escapeHtml(r!.note), ""));
            for (const i of r!.issues.slice(0, 100)) {
              const row = document.createElement("div");
              row.className = "meta";
              row.style.cssText = "padding:3px 0;border-bottom:1px solid var(--border-subtle);cursor:pointer";
              row.innerHTML = `${i.severity === "error" ? "🔴" : "🟡"} <b>${escapeHtml(i.name || i.guid)}</b> `
                + `· ${escapeHtml(i.ifc_class)} — ${escapeHtml(i.detail)}`;
              row.title = "Select this element";
              row.onclick = () => { void selectByGuid(i.guid, true); };
              body.appendChild(row);
            }
          });
        })));
        // SOURCES-1 — what governs the selected element. `elementSources` had no client caller, so
        // the answer to "why is this wall like this?" existed server-side and nowhere else.
        b.appendChild(toolBtn2("🔎 Element sources (what governs this?)", () => withLoading(container, "Reading provenance", async () => {
          const guid = selectedGuid();
          if (!guid) { toast("Select an element first", "info"); return; }
          let r;
          try { r = await api.elementSources(pid, guid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          // `found: false` is a real answer and not an empty one. Rendering blank sections for an
          // element the graph has never heard of reads as "nothing governs this", which is a
          // different claim from "this element is not in the document graph".
          if (!r.found) {
            out.textContent = "no provenance";
            showResult("Element sources", (body) => body.appendChild(resultNote(
              "This element is not in the document graph — no spec sections, documents or "
              + "container are recorded for it. That is not the same as nothing governing it.", "")));
            return;
          }
          out.textContent = `${r.citations.length} citation(s)`;
          showResult("Element sources", (body) => {
            body.appendChild(resultNote(`<b>${escapeHtml(r!.name || guid)}</b>`
              + (r!.class ? ` · ${escapeHtml(r!.class)}` : ""), ""));
            const specs = r!.spec_sections || [];
            const docs = r!.documents || [];
            if (specs.length) {
              body.appendChild(resultNote("<b>Governing spec sections</b>", ""));
              body.appendChild(kvTable(specs.map((x) => ({
                k: `${x.system ? escapeHtml(x.system) + " " : ""}${escapeHtml(x.code)}`, v: escapeHtml(x.title),
              }))));
            }
            if (docs.length) {
              body.appendChild(resultNote("<b>Attached documents</b>", ""));
              body.appendChild(kvTable(docs.map((x) => ({ k: escapeHtml(x.name), v: x.sheet ? `sheet ${escapeHtml(x.sheet)}` : "" }))));
            }
            if (r!.container) {
              const c = r!.container;
              const row = document.createElement("div");
              row.className = "meta"; row.style.cssText = "margin-top:4px";
              row.innerHTML = `Container: <b>${escapeHtml(c.name || c.guid || "—")}</b> · ${escapeHtml(c.class)}`;
              // Only offer the jump when there is somewhere to jump to.
              if (c.guid) {
                row.style.cursor = "pointer"; row.title = "Select the container";
                row.onclick = () => { void selectByGuid(c.guid!, true); };
              }
              body.appendChild(row);
            }
            if (!specs.length && !docs.length && !r!.container) {
              body.appendChild(resultNote("In the graph, but nothing cites it yet.", ""));
            }
          });
        })));
        // GEOREF-1 — the survey basis, which nothing could show. `georef.py` reports a BSI LoGeoRef
        // level (0/10/20/40/50) "so a coordinator can see at a glance how well-georeferenced a model
        // is", and it had no client caller: the project non-negotiable is to preserve real
        // coordinates for export, and there was no way to find out whether they were there.
        b.appendChild(toolBtn2("🌍 Georeferencing (survey basis / LoGeoRef)", () => withLoading(container, "Reading survey basis", async () => {
          let r;
          try { r = await api.modelGeoreferencing(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = r.level_label;
          showResult("Georeferencing", (body) => {
            // The level IS the verdict — a bare "georeferenced: true" hides the difference between an
            // elevation-only model and a projected CRS, and those export very differently.
            body.appendChild(resultNote(
              `<b>${escapeHtml(r!.level_label)}</b>${r!.note ? " — " + escapeHtml(r!.note) : ""}`,
              r!.level >= 40 ? "ok" : r!.level === 0 ? "bad" : ""));
            const rows: { k: string; v: string }[] = [];
            const mc = r!.map_conversion, crs = r!.crs, site = r!.site;
            // Every field is rendered as "not set" rather than omitted when absent. An absent row and
            // a zero row look identical once one is missing, and eastings of 0 is a real value.
            const num = (v: number | null | undefined) => (typeof v === "number" ? String(v) : "not set");
            if (mc) {
              rows.push({ k: "Eastings", v: num(mc.eastings) }, { k: "Northings", v: num(mc.northings) },
                { k: "Orthogonal height", v: num(mc.orthogonal_height) },
                { k: "True north bearing", v: mc.true_north_bearing_deg == null ? "not set" : `${mc.true_north_bearing_deg}°` },
                { k: "Scale", v: num(mc.scale) });
            }
            if (crs) {
              rows.push({ k: "CRS", v: crs.name || "not set" }, { k: "Geodetic datum", v: crs.geodetic_datum || "not set" },
                { k: "Vertical datum", v: crs.vertical_datum || "not set" },
                { k: "Map projection", v: crs.map_projection || "not set" }, { k: "Map zone", v: crs.map_zone || "not set" });
            }
            if (site) {
              const dms = (v: number[] | null) => (Array.isArray(v) && v.length ? v.join("° ") : "not set");
              rows.push({ k: "Site latitude", v: dms(site.ref_latitude) }, { k: "Site longitude", v: dms(site.ref_longitude) },
                { k: "Site elevation", v: num(site.ref_elevation) });
            }
            if (!rows.length) {
              body.appendChild(resultNote("No IfcMapConversion, projected CRS or IfcSite reference — "
                + "the model carries no survey basis at all.", "bad"));
              return;
            }
            body.appendChild(kvTable(rows));
          });
        })));
        // WARN-1 — the punch list BEHIND the health badge. `modelHealth` above scores the model and
        // says "warn"; until now nothing could answer "warn about what, and where?". The feed's own
        // words: "Where the model-CI badge says pass/warn/fail, this is the actionable list behind
        // it." It shipped with no client caller at all.
        b.appendChild(toolBtn2("⚠ Warnings (the punch list behind the score)", () => withLoading(container, "Collecting warnings", async () => {
          let r;
          try { r = await api.modelWarnings(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = r.clean ? "no warnings" : `${r.total} warning(s)`;
          const sev: Record<string, string> = { fail: "🔴", warn: "🟡", info: "⚪" };
          showResult("Model warnings", (body) => {
            body.appendChild(resultNote(r!.clean
              ? "No hygiene or conformance defects found."
              : `<b>${r!.by_severity.fail}</b> fail · <b>${r!.by_severity.warn}</b> warn · `
                + `<b>${r!.by_severity.info}</b> info — worst first.`, r!.clean ? "ok" : r!.by_severity.fail ? "bad" : ""));
            for (const w of r!.warnings) {
              const guids = guidsFromSample(w.sample);
              const row = document.createElement("div");
              row.className = "meta";
              row.style.cssText = "padding:3px 0;border-bottom:1px solid var(--border-subtle)";
              row.innerHTML = `${sev[w.severity] || "⚪"} <b>${escapeHtml(w.label)}</b> · ${w.count}`
                + (w.note ? ` <span class="meta">${escapeHtml(w.note)}</span>` : "");
              // Only rows that CAN be zoomed to get the affordance. `overlapping_duplicates` groups
              // are keyed by class+location and carry no GUID, so a blanket click handler there would
              // be a control that does nothing — the silent-failure shape, in a panel about defects.
              if (guids.length) {
                row.style.cursor = "pointer";
                row.title = `Select ${guids.length} offending element(s)`;
                // `sets.fromGuids` is async. The first version of this line cast the Promise away
                // with `as never` to satisfy tsc — which is how a type error becomes a runtime one.
                row.onclick = async () => { await selectMap(await sets.fromGuids(guids.slice(0, 200))); };
              } else {
                row.title = "This check identifies groups by location, not by element — nothing to select";
              }
              body.appendChild(row);
            }
          });
        })));
        b.appendChild(toolBtn2("🩺 Model Health (all checks, one score)", () => withLoading(container, "Scoring model health", async () => {
          let r;
          try { r = await api.modelHealth(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = r.overall_score != null ? `health ${r.overall_score} · ${r.band}` : "no model data";
          const dot: Record<string, string> = { good: "🟢", warn: "🟡", poor: "🔴", na: "⚪" };
          showResult("Model Health", (body) => {
            const tone = r!.overall_score == null ? "" : r!.overall_score >= 80 ? "ok" : r!.overall_score < 50 ? "bad" : "";
            body.appendChild(resultNote(r!.overall_score != null
              ? `Composite <b>${r!.overall_score}/100</b> — <b>${r!.band}</b> (${r!.scored_lenses} of ${r!.lenses.length} checks scored).`
              : "No model-quality inputs yet — load a model and log coordination / verification to score.", tone));
            body.appendChild(kvTable(r!.lenses.map((l) => ({
              k: `${dot[l.status] || "⚪"} ${l.label}`,
              v: `${l.score != null ? `${l.score}/100` : "n/a"} — ${l.headline}`,
            }))));
            const note = document.createElement("div"); note.className = "meta";
            note.style.cssText = "margin-top:8px;font-size:11px";
            note.textContent = "One score over integrity/hygiene (Model QA), ISO 19650 KPIs (BIM scorecard), "
              + "clash coordination, and verified-as-built. Each lens has its own tool in this rail (or the Report Center) to act on it.";
            body.appendChild(note);
          });
        })));
        b.appendChild(toolBtn2("📋 Normative validation (openBIM conformance)", () => withLoading(container, "Running normative validation", async () => {
          let r;
          try { r = await api.normValid(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = r.passed ? `norm-valid ✓ (${r.schema})` : `norm-valid ✗ ${r.summary.fail} fail`;
          const dot: Record<string, string> = { pass: "🟢", warn: "🟡", fail: "🔴" };
          showResult("Normative validation — openBIM conformance", (body) => {
            body.appendChild(resultNote(r!.passed
              ? `<b>${r!.schema}</b> — conforms: <b>${r!.summary.pass}</b> pass · ${r!.summary.warn} warn · 0 fail.`
              : `<b>${r!.schema}</b> — <b>${r!.summary.fail}</b> check(s) failed (${r!.summary.pass} pass · ${r!.summary.warn} warn).`,
              r!.passed ? "ok" : "bad"));
            body.appendChild(kvTable(r!.checks.map((c) => ({
              k: `${dot[c.status] || "⚪"} ${c.label}`,
              v: c.count ? `${c.count} — ${escapeHtml(c.note || c.category)}` : escapeHtml(c.note || c.category),
            }))));
            const note = document.createElement("div"); note.className = "meta";
            note.style.cssText = "margin-top:8px;font-size:11px";
            note.textContent = "Header + schema + IFC implementer-agreement rules (buildingSMART-style). "
              + "Complements Model QA (authoring quality) and IDS (data completeness). Warnings don't block; only fails do.";
            body.appendChild(note);
          });
        })));
        // SURF-4: element data-QA (`/elements/qa`) was backed but unsurfaced — the per-rule
        // required-property completeness check (missing GUIDs are click-to-select).
        b.appendChild(toolBtn2("🔍 Data QA (required-property completeness)", () => withLoading(container, "Checking element data quality", async () => {
          let r;
          try { r = await api.dataQa(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = `data QA ${r.compliant_pct}% (${r.compliant}/${r.total})`;
          showResult("Element data QA", (body) => {
            const tone = r!.compliant_pct >= 90 ? "ok" : r!.compliant_pct < 60 ? "bad" : "";
            body.appendChild(resultNote(`<b>${r!.compliant_pct}%</b> of ${r!.total} elements carry their required properties `
              + `(${r!.noncompliant} non-compliant).`, tone));
            for (const rule of r!.rules) {
              // HARDEN-2 (B6): /elements/qa severities are "required"/"recommended" — the old
              // high/medium/low map never matched, so every row fell back to "•".
              const sev: Record<string, string> = { required: "🔴", recommended: "🟡" };
              const line = resultNote(`${sev[rule.severity] || "•"} <b>${rule.label}</b> — ${rule.present} present · <b>${rule.missing}</b> missing`,
                rule.missing ? "" : "ok");
              if (rule.missing && rule.missing_guids.length) {
                const pick = document.createElement("a"); pick.href = "#"; pick.textContent = " select missing";
                pick.style.cssText = "font-size:11px;margin-left:6px";
                pick.onclick = async (e) => { e.preventDefault(); await selectMap(await sets.fromGuids(rule.missing_guids.slice(0, 200))); };
                line.appendChild(pick);
              }
              body.appendChild(line);
            }
          });
        })));
        b.appendChild(toolBtn2("🔎 Query-select (filter language)", () => {
          showResult("Query-select — selector language", (body) => {
            body.appendChild(resultNote("Select elements by a selector string, then isolate them in 3D. "
              + "Combine terms with <b>&amp;</b>: <code>IfcWall &amp; Pset_WallCommon.FireRating=2HR &amp; storey=L3</code>. "
              + "Operators: <code>= != &gt;= &lt;= &gt; &lt; ~</code> (contains); a bare <code>Pset.Prop</code> tests existence.", ""));
            const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:6px 0";
            const inp = document.createElement("input"); inp.className = "portal-filter"; inp.style.cssText = "flex:1 1 240px;min-width:0;font-size:12px";
            inp.placeholder = "IfcWall & storey=L3"; inp.value = "IfcWall";
            const run = document.createElement("button"); run.className = "mini-btn on"; run.textContent = "Run";
            const dl = document.createElement("button"); dl.className = "mini-btn"; dl.textContent = "⬇ IFC";
            dl.title = "Download an IFC of just the matching elements (spatial skeleton preserved) — the discipline/scope slice you hand a consultant";
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "4px";
            row.append(inp, run, dl); body.append(row, status);
            const exec = async () => {
              const query = inp.value.trim(); if (!query) return;
              status.textContent = "querying…";
              try {
                const r = await api.modelSelect(pid, query);
                status.innerHTML = `<b>${r.matched}</b> matched${r.truncated ? " (showing first " + r.guids.length + ")" : ""}`;
                if (r.guids.length) await layerMgr.isolateGuids(r.guids);
                else { await layerMgr.showAll(); notify("no elements matched", "info"); }
              } catch (e) { status.textContent = `query error: ${(e as Error).message}`; }
            };
            run.onclick = () => void exec();
            dl.onclick = () => {
              const query = inp.value.trim(); if (!query) { notify("enter a selector first", "info"); return; }
              window.open(api.subsetIfcUrl(pid, query), "_blank");
            };
            inp.onkeydown = (e) => { if (e.key === "Enter") void exec(); };
          });
        }));
        b.appendChild(toolBtn2("★ Smart views (saved presets)", () => {
          showResult("Smart views — saved property-driven presets", (body) => {
            body.appendChild(resultNote("Save a QUERY-DSL selector as a reusable view — <b>isolate</b>, "
              + "<b>colour</b>, or <b>hide</b> the matching elements. Presets persist with the project so the "
              + "whole team re-applies the same coordination views.", ""));
            const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:4px;margin:6px 0";
            body.appendChild(list);
            const apply = async (v: { id?: string }) => {
              if (!v.id) return;
              try {
                const r = await api.smartViewRun(pid, v.id);
                if (r.error) { notify(`selector error: ${r.error}`, "error"); return; }
                if (!r.guids.length) { await layerMgr.showAll(); notify("no elements matched", "info"); return; }
                if (r.mode === "color") { await layerMgr.colorGuids(r.guids, r.color || "#ffb020"); }
                else if (r.mode === "hide") { const ly = await layerMgr.addGuidLayer(`hide:${r.name}`, r.guids); await layerMgr.setVisible(ly.id, false); }
                else { await layerMgr.isolateGuids(r.guids); }
                notify(`${r.name}: ${r.matched} element(s) · ${r.mode}`, "success");
              } catch (e) { notify((e as Error).message, "error"); }
            };
            const refresh = async () => {
              list.textContent = "loading…";
              let views: { id?: string; name: string; selector: string; mode: string; color?: string | null }[] = [];
              try { views = (await api.smartViews(pid)).views; }
              catch (e) { list.textContent = `failed: ${(e as Error).message}`; return; }
              list.innerHTML = "";
              if (!views.length) { list.appendChild(resultNote("No saved views yet — add one below.", "")); }
              for (const v of views) {
                const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;align-items:center";
                const dot = v.mode === "color" ? `<span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${escapeHtml(v.color || "#ffb020")};margin-right:4px"></span>` : "";
                const label = document.createElement("span"); label.style.cssText = "flex:1;font-size:12px";
                label.innerHTML = `${dot}<b>${escapeHtml(v.name)}</b> <span class="meta">${escapeHtml(v.mode)} · ${escapeHtml(v.selector)}</span>`;
                const go = document.createElement("button"); go.className = "mini-btn on"; go.textContent = "Apply"; go.onclick = () => void apply(v);
                const del = document.createElement("button"); del.className = "mini-btn"; del.textContent = "✕"; del.title = "delete";
                del.onclick = async () => {
                  try { await api.smartViewsSave(pid, views.filter((x) => x.id !== v.id) as never); await refresh(); }
                  catch (e) { notify((e as Error).message, "error"); }
                };
                row.append(label, go, del); list.appendChild(row);
              }
            };
            // add-new row: name + selector + mode (+ colour when mode=color)
            const add = document.createElement("div"); add.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px;border-top:1px solid var(--line,#3a3f47);padding-top:8px";
            const nameI = document.createElement("input"); nameI.className = "portal-filter"; nameI.placeholder = "view name"; nameI.style.cssText = "flex:1 1 120px;min-width:0;font-size:12px";
            const selI = document.createElement("input"); selI.className = "portal-filter"; selI.placeholder = "IfcDuctSegment & storey=L3"; selI.style.cssText = "flex:2 1 200px;min-width:0;font-size:12px";
            const modeS = document.createElement("select"); modeS.className = "portal-filter"; modeS.style.fontSize = "12px";
            for (const m of ["isolate", "color", "hide"]) { const o = document.createElement("option"); o.value = m; o.textContent = m; modeS.appendChild(o); }
            const colorI = document.createElement("input"); colorI.type = "color"; colorI.value = "#ffb020"; colorI.style.display = "none";
            modeS.onchange = () => { colorI.style.display = modeS.value === "color" ? "" : "none"; };
            const save = document.createElement("button"); save.className = "mini-btn on"; save.textContent = "＋ Save view";
            save.onclick = async () => {
              const name = nameI.value.trim(), selector = selI.value.trim();
              if (!name || !selector) { notify("name + selector required", "error"); return; }
              try {
                const cur = (await api.smartViews(pid)).views;
                const nv = { name, selector, mode: modeS.value as "isolate" | "color" | "hide",
                  ...(modeS.value === "color" ? { color: colorI.value } : {}) };
                await api.smartViewsSave(pid, [...cur, nv] as never);
                nameI.value = ""; selI.value = ""; await refresh();
                notify("view saved", "success");
              } catch (e) { notify((e as Error).message, "error"); }
            };
            add.append(nameI, selI, modeS, colorI, save); body.appendChild(add);
            void refresh();
          });
        }));
        b.appendChild(toolBtn2("🧹 Model cleanup (maintenance)", () => {
          showResult("Model cleanup — maintenance recipes", (body) => {
            body.appendChild(resultNote("Remove dead data an IFC accumulates over its life. A dry-run scan "
              + "shows what each recipe would drop; running it republishes the model (element GUIDs are "
              + "preserved, so pins / RFIs / clashes survive).", ""));
            const out = document.createElement("div"); body.appendChild(out);
            const refresh = async () => {
              out.innerHTML = "<div class=\"meta\">scanning…</div>";
              let s; try { s = await api.modelMaintenance(pid); }
              catch (e) { out.innerHTML = ""; out.appendChild(resultNote(`scan failed: ${escapeHtml((e as Error).message)}`, "")); return; }
              out.innerHTML = "";
              out.appendChild(resultNote(`<b>${s.cleanable}</b> cleanable entity(ies) across ${s.total_entities} total`, s.cleanable ? "" : "ok"));
              for (const r of s.recipes) {
                const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;align-items:center;margin:3px 0";
                const label = document.createElement("span"); label.style.cssText = "flex:1;font-size:12px";
                label.innerHTML = `<b>${escapeHtml(r.label)}</b> — ${r.removable} removable`
                  + (r.sample.length ? ` <span class="meta">(${r.sample.slice(0, 5).map(escapeHtml).join(", ")}${r.sample.length > 5 ? "…" : ""})</span>` : "");
                const run = document.createElement("button"); run.className = "mini-btn on"; run.textContent = "Purge"; run.disabled = r.removable === 0;
                run.onclick = async () => {
                  run.disabled = true; run.textContent = "purging…";
                  try {
                    const res = await api.editIfc(pid, r.recipe, {}, true);
                    notify(`removed ${res.changed} — model republishing, reload to see it`, "success");
                    await refresh();
                  } catch (e) { notify((e as Error).message, "error"); run.disabled = false; run.textContent = "Purge"; }
                };
                row.append(label, run); out.appendChild(row);
              }
            };
            void refresh();
          });
        }));
        b.appendChild(toolBtn2("⇄ Property round-trip (CSV/XLSX)", () => {
          showResult("Property round-trip — export · edit · re-import", (body) => {
            body.appendChild(resultNote("The daily openBIM workflow: export a GUID-keyed property table, edit it in "
              + "Excel/Sheets, upload it back — a <b>dry-run diff</b> shows exactly what would change before anything "
              + "is written (GUID-stable <code>set_props_by_guid</code> recipe + republish).", ""));
            const row = document.createElement("div"); row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:6px 0";
            const propsI = document.createElement("input"); propsI.className = "portal-filter"; propsI.style.cssText = "flex:1 1 260px;min-width:0;font-size:12px";
            propsI.placeholder = "Pset_WallCommon.FireRating, Pset_WallCommon.LoadBearing"; propsI.value = "Pset_WallCommon.FireRating";
            const exp = document.createElement("button"); exp.className = "mini-btn on"; exp.textContent = "⤓ Export CSV";
            const upLabel = document.createElement("label"); upLabel.className = "mini-btn"; upLabel.textContent = "⇪ Upload edited"; upLabel.style.cursor = "pointer";
            const upInput = document.createElement("input"); upInput.type = "file"; upInput.accept = ".csv,.xlsx"; upInput.style.display = "none";
            upLabel.appendChild(upInput);
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "4px";
            const diffBox = document.createElement("div"); diffBox.style.cssText = "margin-top:6px;max-height:40vh;overflow:auto";
            row.append(propsI, exp, upLabel); body.append(row, status, diffBox);
            exp.onclick = async () => {
              const props = propsI.value.split(",").map((s) => s.trim()).filter(Boolean);
              if (!props.length) { notify("name at least one Pset.Prop column", "error"); return; }
              try { await api.roundtripExport(pid, props); status.textContent = "exported — edit the CSV, then upload it back"; }
              catch (e) { status.textContent = `export failed: ${(e as Error).message}`; }
            };
            upInput.onchange = async () => {
              const f = upInput.files?.[0]; if (!f) return;
              status.textContent = "computing dry-run diff…"; diffBox.replaceChildren();
              try {
                const d = await api.roundtripDiff(pid, f);
                status.innerHTML = `<b>${d.changes.length}</b> change(s) across ${d.checked} rows`
                  + (d.unknown_guids.length ? ` · <b>${d.unknown_guids.length}</b> unknown GUID(s) skipped` : "")
                  + ` · ${d.unchanged} unchanged`;
                if (!d.changes.length) return;
                const tbl = document.createElement("table"); tbl.className = "result-table";
                for (const c of d.changes.slice(0, 300)) {
                  const tr = document.createElement("tr");
                  tr.innerHTML = `<td class="k">${escapeHtml(c.guid.slice(0, 8))}… ${escapeHtml(c.pset)}.${escapeHtml(c.prop)}</td>`
                    + `<td class="v">${escapeHtml(c.old ?? "—")} → <b>${escapeHtml(c.new)}</b></td>`;
                  tbl.appendChild(tr);
                }
                diffBox.appendChild(tbl);
                const apply = document.createElement("button"); apply.className = "mini-btn on"; apply.style.marginTop = "6px";
                apply.textContent = `✓ Apply ${d.changes.length} change(s) + republish`;
                apply.onclick = async () => {
                  apply.disabled = true; status.textContent = "applying via set_props_by_guid…";
                  try {
                    const r = await api.editIfc(pid, "set_props_by_guid", { changes: d.changes });
                    status.textContent = `applied ${r.changed} change(s) — model republishing`;
                    notify("properties applied — reload the model to see them", "success");
                  } catch (e) { status.textContent = `apply failed: ${(e as Error).message}`; apply.disabled = false; }
                };
                diffBox.appendChild(apply);
              } catch (e) { status.textContent = `diff failed: ${(e as Error).message}`; }
              finally { upInput.value = ""; }
            };
          });
        }));
        b.appendChild(toolBtn2("✔ Rule check (rule library)", () => withLoading(container, "Checking the rule library", async () => {
          let r;
          try { r = await api.rulesRun(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          if (!r.model_scored) { toast(r.note || "no model loaded", "info"); return; }
          out.textContent = `rules: ${r.failing_rules ?? 0}/${r.total_rules} failing`;
          showResult("Rule library check", (body) => {
            const bySev = r!.by_severity || {};
            body.appendChild(resultNote(`<b>${r!.failing_rules ?? 0}</b> of ${r!.total_rules} rules failing · `
              + `${r!.total_violations ?? 0} violations` + (bySev.high ? ` · 🔴 ${bySev.high} high` : "")
              + (bySev.medium ? ` · 🟡 ${bySev.medium} medium` : "") + (bySev.low ? ` · ⚪ ${bySev.low} low` : ""),
            (r!.failing_rules ?? 0) ? "" : "ok"));
            const sev: Record<string, string> = { high: "🔴", medium: "🟡", low: "⚪" };
            for (const rule of r!.rules) {
              const icon = rule.status === "pass" ? "✅" : rule.status === "n/a" ? "➖" : (sev[rule.severity] || "•");
              const line = resultNote(`${icon} <b>${escapeHtml(rule.name)}</b> — ${rule.passed}/${rule.scoped} pass`
                + (rule.failed ? ` · <b>${rule.failed}</b> fail` : ""), rule.status === "fail" ? "" : "ok");
              if (rule.failed && rule.fail_guids.length) {
                const pick = document.createElement("a"); pick.href = "#"; pick.textContent = " isolate failures";
                pick.style.cssText = "font-size:11px;margin-left:6px";
                pick.onclick = (e) => { e.preventDefault(); void layerMgr.isolateGuids(rule.fail_guids.slice(0, 500)); };
                line.appendChild(pick);
              }
              body.appendChild(line);
            }
          });
        })));
        b.appendChild(toolBtn2("⛶ Geometry check (clearance/egress)", () => withLoading(container, "Running geometric checks", async () => {
          let r;
          try { r = await api.rulesGeometryRun(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          out.textContent = `geometry: ${r.violation_total} violation(s)`;
          showResult("Geometric rule check", (body) => {
            const bySev = r!.by_severity || {};
            body.appendChild(resultNote(`<b>${r!.violation_total}</b> violation(s)`
              + (bySev.high ? ` · 🔴 ${bySev.high} high` : "") + (bySev.medium ? ` · 🟡 ${bySev.medium} medium` : "")
              + (bySev.low ? ` · ⚪ ${bySev.low} low` : ""), r!.violation_total ? "" : "ok"));
            for (const chk of r!.results) {
              const line = resultNote(`${chk.passed ? "✅" : "🔴"} <b>${escapeHtml(chk.name)}</b> — `
                + `${chk.checked} checked, ${chk.violations.length} violation(s)`
                + (chk.note ? ` · ${escapeHtml(chk.note)}` : ""), chk.passed ? "ok" : "");
              if (chk.violations.length) {
                const pick = document.createElement("a"); pick.href = "#"; pick.textContent = " isolate";
                pick.style.cssText = "font-size:11px;margin-left:6px";
                const guids = chk.violations.map((v) => v.guid);
                pick.onclick = (e) => { e.preventDefault(); void layerMgr.isolateGuids(guids.slice(0, 500)); };
                line.appendChild(pick);
              }
              body.appendChild(line);
              for (const v of chk.violations.slice(0, 12)) {
                body.appendChild(resultNote(`&nbsp;&nbsp;${escapeHtml(v.name || v.guid.slice(0, 8) + "…")} — ${escapeHtml(v.detail)}`, ""));
              }
            }
            body.appendChild(resultNote("AABB-level checks on the clash geometry path: door/equipment approach clearance, straight-line egress distance, accessible clear width. Property rules live in ✔ Rule check.", ""));
          });
        })));
        b.appendChild(toolBtn2("▢ Model CI (quality gate)", () => withLoading(container, "Running model CI checks", async () => {
          let r;
          try { r = await api.ciRun(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          const mark: Record<string, string> = { pass: "✅", warn: "🟡", fail: "🔴", skip: "➖", none: "➖" };
          out.textContent = `CI: ${r.badge}`;
          showResult("Model CI — quality gate", (body) => {
            body.appendChild(resultNote(`Overall <b>${mark[r!.overall] || ""} ${escapeHtml(r!.badge)}</b>`
              + (r!.ran_at ? ` · ${escapeHtml(r!.ran_at)}` : "")
              + ` · ${r!.passed ?? 0}/${r!.total_checks ?? r!.checks.length} passed`,
            r!.overall === "fail" ? "bad" : r!.overall === "pass" ? "ok" : ""));
            for (const chk of r!.checks) {
              body.appendChild(resultNote(`${mark[chk.status] || "•"} <b>${escapeHtml(chk.label)}</b> — ${escapeHtml(chk.summary)}`,
                chk.status === "fail" ? "" : "ok"));
            }
            body.appendChild(resultNote("Checks compose the rule library + data-completeness gates; the badge is stored so every model version carries a quality gate. Add rules via the ✔ Rule check tool.", ""));
          });
        })));
        b.appendChild(toolBtn2("🔗 Coordinate clashes (grouped issues)", () => withLoading(container, "Queueing federated clash + coordination", async () => {
          let r;
          try {
            r = await enqueueAndWait(api, pid, "clash_federated", { coordinate: true }) as {
              count: number; disciplines: string[];
              coordination: { group_count: number; reduction: number; new: number; active: number;
                resolved: number; reappeared: number; by_severity: Record<string, number>;
                by_discipline: Record<string, number> } | null;
            };
          }
          catch { toast("Federated clash needs ≥2 models — add one with “＋ Add discipline IFC”", "error"); return; }
          const co = r.coordination;
          out.textContent = co ? `${r.count} clashes → ${co.group_count} issues (${co.reduction}× reduction)` : `${r.count} clashes`;
          toast(co ? `${co.new} new · ${co.active} active · ${co.resolved} resolved · ${co.reappeared} reappeared` : "no clashes", r.count ? "info" : "success");
          await refreshIssues(); await reloadModelPins();
          showResult("Clash coordination", (body) => {
            if (!co) { body.appendChild(resultNote(`<b>${r!.count}</b> cross-model clashes.`, r!.count ? "bad" : "ok")); return; }
            body.appendChild(resultNote(`<b>${r!.count}</b> raw clashes grouped into <b>${co.group_count}</b> tracked coordination issues `
              + `(<b>${co.reduction}×</b> reduction) across <b>${r!.disciplines.join(" × ")}</b>.`, co.group_count ? "bad" : "ok"));
            body.appendChild(kvTable([
              { k: "New", v: String(co.new) }, { k: "Active (carried forward)", v: String(co.active) },
              { k: "Resolved (auto)", v: String(co.resolved) }, { k: "Reappeared (reopened)", v: String(co.reappeared) },
            ]));
            if (Object.keys(co.by_severity).length) {
              const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "By severity"; body.appendChild(h);
              body.appendChild(kvTable(Object.entries(co.by_severity).map(([k, v]) => ({ k, v: String(v) }))));
            }
            if (Object.keys(co.by_discipline).length) {
              const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "By discipline pair"; body.appendChild(h);
              body.appendChild(kvTable(Object.entries(co.by_discipline).map(([k, v]) => ({ k, v: String(v) }))));
            }
            body.appendChild(toolBtn2("📊 Coordination KPIs", () => withLoading(container, "Loading clash KPIs", async () => {
              const m = await api.clashMetrics(pid);
              showResult("Clash coordination KPIs", (kb) => {
                kb.appendChild(resultNote(`<b>${m.open}</b> open · <b>${m.closed}</b> closed · <b>${m.resolution_rate}%</b> resolved · `
                  + `reappearance <b>${m.reappearance_rate}%</b> over <b>${m.runs}</b> run(s).`, m.open ? "bad" : "ok"));
                kb.appendChild(kvTable([
                  { k: "Open aging 0–7d", v: String(m.aging["0-7"] ?? 0) }, { k: "8–14d", v: String(m.aging["8-14"] ?? 0) },
                  { k: "15–30d", v: String(m.aging["15-30"] ?? 0) }, { k: "30d+", v: String(m.aging["30+"] ?? 0) },
                ]));
                if (m.burn_down.length) {
                  const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-weight:700;margin:8px 0 2px"; h.textContent = "Run burn-down"; kb.appendChild(h);
                  kb.appendChild(kvTable(m.burn_down.map((x) => ({ k: x.run, v: `+${x.new} / −${x.resolved}${x.reappeared ? ` / ↻${x.reappeared}` : ""}` }))));
                }
              });
            })));
            body.appendChild(toolBtn2("Open Issues panel", () => (document.querySelector('.rail-btn[data-rail="issues"]') as HTMLElement)?.click()));
          });
        })));
        b.appendChild(toolBtn2("📍 Field layout (points CSV / DXF)", () => withLoading(container, "Extracting layout setout points", async () => {
          let r;
          try { r = await api.layoutPoints(pid); }
          catch { toast("Field layout needs a source IFC with columns/grids", "error"); return; }
          out.textContent = `${r.count} setout points`;
          toast(r.count ? `${r.count} layout points ready to stake` : "no setout points found", r.count ? "info" : "success");
          showResult("Model → field layout", (body) => {
            body.appendChild(resultNote(`<b>${r!.count}</b> georeferenced setout points (grids + column/footing/`
              + `opening/wall) — E/N/Z with the IFC GlobalId in each Description, ready for total stations, `
              + `marking robots and floor printers.`, r!.count ? "ok" : "bad"));
            if (Object.keys(r!.by_class).length) body.appendChild(kvTable(Object.entries(r!.by_class).map(([k, v]) => ({ k: k.replace("Ifc", ""), v: String(v) }))));
            const dl = (label: string, href: string) => { const a = document.createElement("a"); a.className = "file-btn"; a.textContent = label; a.href = href; a.target = "_blank"; a.rel = "noopener"; a.style.marginRight = "6px"; return a; };
            const row = document.createElement("div"); row.style.margin = "8px 0";
            row.append(dl("⬇ PENZD CSV", api.layoutCsvUrl(pid, "PENZD")), dl("⬇ PNEZD CSV", api.layoutCsvUrl(pid, "PNEZD")), dl("⬇ DXF (printers)", api.layoutDxfUrl(pid)));
            body.appendChild(row);
            body.appendChild(resultNote("Field round-trip: stake/print these, shoot the as-installed positions "
              + "with a total station, then upload that CSV to verify deviation by point number.", "ok"));
          });
        })));
        b.appendChild(toolBtn2("🕸 Related elements (model graph)", () => withLoading(container, "Building model graph", async () => {
          const guid = selectedGuid();
          if (!guid) { notify("select an element in 3D first", "error"); return; }
          let r;
          try { r = await api.graphNeighbors(pid, guid, 2); }
          catch { toast("Needs a source IFC", "error"); return; }
          if (!r.found) { toast("Element not in the graph", "error"); return; }
          out.textContent = `${r.neighbor_count ?? 0} related`;
          const relLabel: Record<string, string> = { contained_in: "is in", aggregates: "contains", bounds: "bounds", has_opening: "has opening", fills: "fills", serves: "serves" };
          showResult("Related elements — model graph (IFC relationships)", (body) => {
            body.appendChild(resultNote(`Multi-hop relationships from the selected element, straight from the model's IFC structure — every hop is cited by relationship. <b>${r!.neighbor_count ?? 0}</b> related element(s) within 2 hops.`, "ok"));
            if (!r!.paths.length) { body.appendChild(resultNote("This element has no modelled relationships (no spatial containment, openings, or boundaries).", "")); return; }
            for (const p of r!.paths.slice(0, 40)) {
              const row = document.createElement("div"); row.className = "tree-leaf"; row.style.cssText = "cursor:pointer;padding:3px 6px;font-size:12px";
              const chain = p.path.map((s) => `${s.dir === "out" ? "→" : "←"} ${relLabel[s.rel] || s.rel}`).join(" ");
              row.innerHTML = `<b>${escapeHtml((p.name || p.class.replace("Ifc", "")))}</b> <span class="meta">${escapeHtml(p.class.replace("Ifc", ""))}</span> <span class="meta">${escapeHtml(chain)}</span>`;
              row.title = "Select this element in 3D";
              row.onclick = () => { void selectByGuid(p.guid, true); };
              body.appendChild(row);
            }
          });
        })));
        b.appendChild(toolBtn2("🧬 Property layers (IFC5 overlays)", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          let stack: PropLayer[];
          try { stack = (await api.getLayers(pid)).layers; }
          catch { toast("Could not load layers", "error"); return; }
          showResult("Property-override layers — IFC5 composition", (body) => {
            body.appendChild(resultNote(`Non-destructive <b>overlay layers</b> that compose over the model (IFC5-style) — the strongest enabled layer wins, disagreements surface as <b>conflicts</b>, and nothing touches the IFC until you <b>bake</b>. Layers are ordered base → strongest.`, "ok"));
            const list = document.createElement("div"); list.style.margin = "6px 0";
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "6px";
            const draw = () => {
              list.innerHTML = "";
              stack.forEach((L, i) => {
                const row = document.createElement("div"); row.className = "level-row";
                const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = L.enabled !== false;
                cb.onchange = () => { L.enabled = cb.checked; };
                const nm = document.createElement("span"); nm.style.flex = "1"; nm.style.fontSize = "12px";
                nm.textContent = `${i + 1}. ${L.name} `; const badge = document.createElement("span"); badge.className = "meta"; badge.textContent = `(${L.overrides.length} override${L.overrides.length === 1 ? "" : "s"})`; nm.appendChild(badge);
                const del = document.createElement("button"); del.className = "selset-del"; del.textContent = "✕";
                del.onclick = () => { stack.splice(i, 1); draw(); };
                row.append(cb, nm, del); list.appendChild(row);
              });
              if (!stack.length) { const e = document.createElement("div"); e.className = "meta"; e.textContent = "No layers yet — add one, then add overrides from a selected element."; list.appendChild(e); }
            };
            draw(); body.appendChild(list);
            // add-layer + add-override-from-selection
            const addL = document.createElement("button"); addL.className = "mini-btn"; addL.textContent = "＋ Layer";
            const ovForm = document.createElement("div"); ovForm.style.cssText = "display:flex;flex-wrap:wrap;gap:2px;align-items:center;margin:6px 0";
            const mk = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "font-size:12px;margin:2px;flex:1 1 80px;min-width:0"; return i; };
            const psetI = mk("Pset"), propI = mk("Prop"), valI = mk("value");
            const layerSel = document.createElement("select"); layerSel.className = "portal-filter"; layerSel.style.cssText = "font-size:12px;margin:2px";
            const drawSel = () => { layerSel.innerHTML = ""; stack.forEach((L, i) => { const o = document.createElement("option"); o.value = String(i); o.textContent = L.name; layerSel.appendChild(o); }); };
            const addOv = document.createElement("button"); addOv.className = "mini-btn"; addOv.textContent = "＋ override (selected element)";
            addOv.onclick = () => {
              const g = selectedGuid();
              if (!g) { notify("select an element in 3D first", "error"); return; }
              if (!psetI.value.trim() || !propI.value.trim() || !stack.length) { notify("need a layer + Pset + Prop", "error"); return; }
              const L = stack[Number(layerSel.value) || 0]; if (!L) { notify("add a layer first", "error"); return; }
              L.overrides.push({ guid: g, pset: psetI.value.trim(), prop: propI.value.trim(), value: valI.value });
              propI.value = ""; valI.value = ""; draw(); status.textContent = `added override on ${g.slice(0, 8)}… to “${L.name}”`;
            };
            addL.onclick = async () => { const n = await askText("New layer", { label: "Layer name (e.g. Fire coordination):", value: "" }); if (!n) return; stack.push({ name: n, enabled: true, overrides: [] }); draw(); drawSel(); };
            drawSel();
            body.append(addL, ovForm); ovForm.append(document.createTextNode("to "), layerSel, psetI, propI, valI, addOv);
            const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;margin-top:6px;flex-wrap:wrap";
            const save = document.createElement("button"); save.className = "mini-btn"; save.textContent = "💾 Save layers";
            save.onclick = async () => { try { await api.putLayers(pid, stack); notify("layers saved", "success"); } catch (e) { notify((e as Error).message, "error"); } };
            const resolve = document.createElement("button"); resolve.className = "mini-btn"; resolve.textContent = "🔍 Resolve + conflicts";
            resolve.onclick = async () => {
              try { await api.putLayers(pid, stack); const r = await api.resolveLayers(pid);
                status.innerHTML = `<b>${r.effective_count}</b> effective override(s) · <b>${r.conflict_count}</b> conflict(s)`
                  + (r.conflicts.length ? "<br>" + r.conflicts.slice(0, 6).map((c) => `⚠ ${escapeHtml(c.pset)}.${escapeHtml(c.prop)}: ${c.values.map((v) => `${escapeHtml(String(v.value))} (${escapeHtml(v.layer)})`).join(" vs ")} → wins <b>${escapeHtml(c.winning_layer)}</b>`).join("<br>") : "");
              } catch (e) { notify((e as Error).message, "error"); }
            };
            const bake = document.createElement("button"); bake.className = "mini-btn on"; bake.textContent = "🔥 Bake to IFC";
            bake.onclick = async () => {
              if (!(await confirmModal("Bake the composed layers into the IFC? This writes the effective values as a new model version (GUID-stable).", "", "Bake", false))) return;
              await api.putLayers(pid, stack).catch(() => {});
              await withLoading(container, "Baking layers + republishing", async () => {
                try { const r = await api.bakeLayers(pid); notify(`baked ${r.baked} override(s) — converting…`, "info"); await waitForPublish(pid); await loadProjectModel(); notify("layers baked into the model", "success"); }
                catch (e) { notify((e as Error).message, "error"); }
              });
            };
            actions.append(save, resolve, bake); body.append(actions, status);
          });
        }));
        // W11 D8: plan-reviewer approvability pre-flight
        // RFI-0 — decision-readiness audit: the information gaps a builder would ask about, ranked
        b.appendChild(toolBtn2("🚫 Decision-readiness (RFI-prevention)", () => withLoading(container, "Auditing decision-readiness", async () => {
          let r;
          try { r = await api.rfiReadiness(projectId!); }
          catch { toast("Needs a source IFC", "error"); return; }
          out.textContent = r.ready ? "decision-ready" : `${r.total_gaps} gap(s) · ${r.high_severity} high`;
          showResult("Decision-readiness — RFI prevention", (body) => {
            body.appendChild(resultNote(r!.ready
              ? "<b>Decision-ready</b> — no obvious information gaps a builder would have to ask about."
              : `<b>${r!.total_gaps} information gap(s)</b> a builder would have to ask about `
                + `(<b>${r!.high_severity}</b> high-severity). Resolve before issuing to cut RFIs.`,
              r!.ready ? "ok" : "bad"));
            const icon = (s: string) => s === "high" ? "🔴" : s === "medium" ? "🟠" : "🟡";
            for (const g of r!.gaps) {
              body.appendChild(kvTable([
                { k: `${icon(g.severity)} ${g.title}`, v: `${g.detail}${g.citation ? " · " + g.citation : ""}`, strong: true },
                { k: "  fix", v: g.fix },
              ]));
              if (g.guids && g.guids.length) {
                const iso = toolBtn2(`◎ Isolate ${g.guids.length} element(s)`, () => { void layerMgr.isolateGuids(g.guids!); });
                body.appendChild(iso);
              }
            }
            if (r!.total_gaps) {
              const bcf = toolBtn2(`📌 Promote ${r!.total_gaps} gap${r!.total_gaps === 1 ? "" : "s"} to BCF issues`, async () => {
                try { const res = await api.rfiReadinessBcf(projectId!); notify(`created ${res.created} BCF issue${res.created === 1 ? "" : "s"} — see the Issues panel`, "success"); await refreshIssues(); }
                catch (e) { notify((e as Error).message, "error"); }
              });
              bcf.title = "Create trackable, GUID-anchored BCF topics from the readiness gaps so they round-trip with clashes/RFIs";
              body.appendChild(bcf);
            }
            body.appendChild(resultNote(r!.disclaimer, ""));
          });
        })));
        // W10-7 structural analytical model — derived from the physical frame
        b.appendChild(toolBtn2("🏗 Structural analytical model", () => withLoading(container, "Reading the analytical model", async () => {
          let s;
          try { s = await api.analyticalSummary(pid); }
          catch { toast("Needs a source IFC", "error"); return; }
          out.textContent = s.has_model ? `${s.curve_members} members · ${s.point_connections} nodes` : "not derived";
          showResult("Structural analytical model", (body) => {
            if (!s!.has_model) {
              body.appendChild(resultNote("No analytical model yet. Derive one to idealise the physical frame — "
                + "columns/beams → curve members, slabs → surface members, tied at shared nodes with a self-weight load case.", ""));
            } else {
              body.appendChild(resultNote(`<b>${s!.curve_members}</b> curve members · <b>${s!.surface_members}</b> surface members`
                + ` · <b>${s!.point_connections}</b> nodes · load case: ${s!.load_cases.filter(Boolean).join(", ") || "—"}`
                + (s!.load_actions ? ` · <b>${s!.load_actions}</b> member load action(s)` : "")
                + (s!.supports ? ` · <b>${s!.supports}</b> support(s)` : "")
                + (s!.load_actions && s!.supports ? " — solver-ready" : ""), "ok"));
            }
            const derive = toolBtn2(s!.has_model ? "↻ Re-derive from the physical model" : "⚙ Derive from the physical model",
              () => withLoading(container, "Deriving the analytical model", async () => {
                try {
                  await api.editIfc(pid, "derive_analytical", {}, false);
                  const s2 = await api.analyticalSummary(pid);
                  notify(`Analytical model derived — ${s2.curve_members} curve, ${s2.surface_members} surface members, ${s2.point_connections} nodes`, "success");
                } catch (e) { notify((e as Error).message, "error"); }
              }));
            derive.title = "Build/refresh the IfcStructuralAnalysisModel alongside the physical model (GUID-stable, idempotent)";
            body.appendChild(derive);
            if (s!.has_model && s!.curve_members > 0) {
              const loads = toolBtn2("⬇ Write member loads (solver-ready IFC)",
                () => withLoading(container, "Writing structural load actions", async () => {
                  try {
                    const res = await api.editIfc(pid, "apply_structural_loads", { dead_klf: 1.0, live_klf: 0.5 }, false);
                    const applied = (res as { changed?: { applied?: number } })?.changed?.applied ?? 0;
                    notify(`Wrote ${applied} member load action(s) — the analytical IFC is now loaded (D+L) and solver-ready`, "success");
                  } catch (e) { notify((e as Error).message, "error"); }
                }));
              loads.title = "Write IfcStructuralLinearAction (D+L) onto every analytical member so a solver (SAP2000/RISA/Robot) imports the loads with the geometry";
              body.appendChild(loads);
              const sup = toolBtn2("⏚ Add base supports (pinned)",
                () => withLoading(container, "Adding base supports", async () => {
                  try {
                    const res = await api.editIfc(pid, "apply_structural_supports", { kind: "pinned" }, false);
                    const n = (res as { changed?: { supported?: number } })?.changed?.supported ?? 0;
                    notify(`Added ${n} pinned base support(s) — the analytical model is now statically stable`, "success");
                  } catch (e) { notify((e as Error).message, "error"); }
                }));
              sup.title = "Fix the base analytical nodes as pinned IfcBoundaryNodeCondition supports so the model is solvable";
              body.appendChild(sup);
            }
            if (s!.has_model && s!.curve_members > 0) {
              const solve = toolBtn2("📐 Apply loads + solve statics", () => withLoading(container, "Applying gravity loads + solving statics", async () => {
                let r;
                try { r = await api.structureSolve(pid, { liveOccupancy: "office" }); }
                catch (e) { notify((e as Error).message, "error"); return; }
                showResult("Structural statics — gravity load solve", (sb) => {
                  if (!r!.has_analytical) { sb.appendChild(resultNote(r!.message || "No analytical model.", "bad")); return; }
                  const lc = r!.load_case!, c = r!.counts!;
                  sb.appendChild(resultNote(`Load case <b>${lc.name}</b> — dead <b>${lc.dead_klf}</b> + live <b>${lc.live_klf}</b> = <b>${lc.service_klf} klf</b> service`
                    + ` · factored <b>${lc.factored_lrfd_klf} klf</b> (${lc.governing_combo}). Solved <b>${c.beams}</b> beam(s) + <b>${c.columns}</b> column(s) as determinate members.`, "ok"));
                  const gb = r!.governing_beam;
                  if (gb) {
                    const sv = gb.service;
                    sb.appendChild(resultNote(`<b>Governing beam</b> — ${gb.length_ft} ft span · reaction <b>${sv.reaction_kip} kip</b> · Vmax <b>${sv.shear_max_kip} kip</b> · Mmax <b>${sv.moment_max_kipft} kip·ft</b>`
                      + ` · deflection <b>${sv.deflection_in}"</b> vs L/360 limit ${sv.deflection_limit_in}" (${sv.deflection_ok ? "✅ OK" : "⚠ exceeds"})`, sv.deflection_ok ? "ok" : "bad"));
                    // mini shear (blue) + moment (orange) diagrams over the span
                    const W = 260, H = 60;
                    const dg = sv.diagram;
                    const maxX = Math.max(1, ...dg.map((d) => d.x_ft));
                    const px = (x: number) => 4 + (x / maxX) * (W - 8);
                    const band = (val: (d: typeof dg[number]) => number, color: string, label: string) => {
                      const mx = Math.max(1, ...dg.map((d) => Math.abs(val(d))));
                      const mid = H / 2;
                      const pts = dg.map((d) => `${px(d.x_ft).toFixed(1)},${(mid - (val(d) / mx) * (mid - 6)).toFixed(1)}`).join(" ");
                      return `<div class="meta" style="margin-top:6px">${label}</div>`
                        + `<svg width="${W}" height="${H}" style="background:var(--panel);border:1px solid var(--line);border-radius:4px">`
                        + `<line x1="4" y1="${mid}" x2="${W - 4}" y2="${mid}" stroke="var(--line)"/>`
                        + `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/></svg>`;
                    };
                    const svg = document.createElement("div");
                    svg.innerHTML = band((d) => d.shear_kip, "#4c8bf5", "Shear (kip)")
                      + band((d) => d.moment_kipft, "#f5a24c", "Moment (kip·ft)");
                    sb.appendChild(svg);
                  }
                  if (r!.columns_axial) {
                    const ca = r!.columns_axial;
                    sb.appendChild(resultNote(`<b>Column axial</b> (tributary takedown) — service <b>${ca.service_total_kip} kip</b> · factored <b>${ca.factored_lrfd_kip} kip</b> over ${ca.storeys} storey(s). <span class="meta">${ca.note}</span>`, ""));
                  }
                  sb.appendChild(resultNote(r!.disclaimer || "", ""));
                });
              }));
              solve.title = "Apply an ASCE 7 gravity load case to the analytical members and solve determinate statics (reactions, shear/moment/deflection)";
              body.appendChild(solve);
              const fem = toolBtn2("⬇ Export OpenSees (.tcl)", () => {
                window.open(api.openseesTclUrl(pid), "_blank");
              });
              fem.title = "Download the analytical frame as an OpenSees .tcl model (nodes, base restraints, one elasticBeamColumn per member, nominal sections) so an engineer can independently verify the solver in a third-party FE solver";
              body.appendChild(fem);
              const femA = toolBtn2("⬇ Export Code_Aster (.mail)", () => {
                window.open(api.codeAsterMailUrl(pid), "_blank");
              });
              femA.title = "Download the analytical frame as a Code_Aster mesh (.mail, ASTER text, SI metres): COOR_3D nodes, SEG2 elements, a BASE support group + a FRAME element group — a second independent solver exchange beside the OpenSees export";
              body.appendChild(femA);
            }
            const lat = toolBtn2("🌪 Lateral (wind + seismic base shear)", () => withLoading(container, "Running ASCE 7 lateral analysis", async () => {
              let lr;
              try { lr = await api.structureLateral(pid, {}); }
              catch (e) { notify((e as Error).message, "error"); return; }
              showResult("Structural lateral — ASCE 7 wind + seismic", (sb) => {
                const g = lr!.governing, se = lr!.seismic, wi = lr!.wind;
                sb.appendChild(resultNote(`<b>Governing: ${g.system}</b> — base shear <b>${g.base_shear_kip} kip</b>`
                  + ` over ${lr!.story_count} stor${lr!.story_count === 1 ? "y" : "ies"} (est. weight ${se.seismic_weight_kip} kip).`, "ok"));
                sb.appendChild(kvTable([
                  { k: "🌎 Seismic (ELF §12.8)", v: `V = ${se.base_shear_kip} kip · Cs ${se.Cs} · T ${se.period_s}s · OTM ${se.overturning_kipft.toLocaleString()} k·ft`, strong: true },
                  { k: "🌬 Wind (MWFRS)", v: `V = ${wi.base_shear_kip} kip · qh ${wi.qh_psf} psf · OTM ${wi.overturning_kipft.toLocaleString()} k·ft`, strong: true },
                ]));
                const govStories = g.system === "seismic" ? se.stories : wi.stories;
                sb.appendChild(resultNote(`Story forces (${g.system}):`, ""));
                sb.appendChild(kvTable(govStories.slice().reverse().map((s) => ({
                  k: `Level ${s.level} @ ${s.height_ft} ft`, v: `F = ${s.force_kip} kip · V = ${s.shear_kip} kip`,
                }))));
                sb.appendChild(resultNote(lr!.disclaimer, ""));
              });
            }));
            lat.title = "ASCE 7 Equivalent Lateral Force (seismic) + simplified MWFRS (wind) → base shear + story forces; preliminary, not a stamped design";
            body.appendChild(lat);
          });
        })));
        b.appendChild(toolBtn2("✅ Approvability pre-flight (permit-readiness)", () => withLoading(container, "Running the plan-reviewer pre-flight", async () => {
          let a;
          try { a = await api.approvability(projectId!); }
          catch { toast("Needs a source IFC", "error"); return; }
          const s = a.summary;
          out.textContent = `${s.passed}/${s.gating} checks · ${s.ready ? "ready" : `${s.failed} to fix`}`;
          showResult("Approvability pre-flight — permit-readiness", (body) => {
            body.appendChild(resultNote(s.ready
              ? `<b>Ready for review</b> — all ${s.gating} gating check(s) pass${s.score_pct !== null ? ` (${s.score_pct}%)` : ""}.`
              : `<b>${s.failed} check(s) need attention</b> before review${s.score_pct !== null ? ` — ${s.score_pct}% passing` : ""}.`,
              s.ready ? "ok" : "bad"));
            const icon = (st: string) => st === "pass" ? "✅" : st === "fail" ? "❌" : st === "info" ? "ℹ️" : "—";
            body.appendChild(kvTable(a!.checks.map((c) => ({ k: `${icon(c.status)} ${c.check}`, v: `${c.detail} · ${c.citation}` }))));
            const failing = a!.checks.filter((c) => c.status === "fail" && c.guids && c.guids.length);
            if (failing.length) {
              const iso = toolBtn2("◎ Isolate flagged elements in 3D", () => { void layerMgr.isolateGuids(failing.flatMap((c) => c.guids || [])); });
              body.appendChild(iso);
            }
            body.appendChild(resultNote(a!.disclaimer, ""));
          });
        })));
        b.appendChild(toolBtn2("🔧 Normalize properties (IDS-ready)", async () => {
          if (!projectId) { notify("connect a project first", "error"); return; }
          let det;
          try { det = await api.propmapDetect(pid); }
          catch { toast("Property normalization needs a source IFC", "error"); return; }
          showResult("Normalize properties → standard structure", (body) => {
            body.appendChild(resultNote(`Remap this model's property names onto a standard (IDS / employer) structure — the <b>transform</b> step between IDS validation and COBie/export. Each rule moves a source <i>Pset.Property</i> to a target across every element, GUID-stable. Model has <b>${det!.element_count}</b> elements.`, "ok"));
            const rules: PropMapRule[] = [];
            const mk = (ph: string) => { const i = document.createElement("input"); i.className = "portal-filter"; i.placeholder = ph; i.style.cssText = "font-size:12px;margin:2px;flex:1 1 90px;min-width:0"; return i; };
            const fromPset = mk("from Pset"), fromProp = mk("from Prop"), toPset = mk("to Pset (blank = same)"), toProp = mk("to Prop");
            const cast = document.createElement("select"); cast.className = "portal-filter"; cast.style.cssText = "font-size:12px;margin:2px";
            for (const c of ["string", "number", "bool"]) { const o = document.createElement("option"); o.value = c; o.textContent = c; cast.appendChild(o); }
            const lbl = document.createElement("div"); lbl.className = "meta"; lbl.style.marginTop = "6px"; lbl.textContent = "Detected properties (click to use as source):";
            const detWrap = document.createElement("div"); detWrap.style.cssText = "max-height:130px;overflow:auto;margin:4px 0;border:1px solid var(--line);border-radius:6px";
            for (const p of det!.properties.slice(0, 80)) {
              const row = document.createElement("div"); row.className = "tree-leaf"; row.style.cssText = "padding:3px 8px;cursor:pointer;font-size:12px";
              row.textContent = `${p.pset}.${p.prop}  ·  ${p.count}×  ·  e.g. ${p.sample}`;
              row.onclick = () => { fromPset.value = p.pset; fromProp.value = p.prop; };
              detWrap.appendChild(row);
            }
            body.append(lbl, detWrap);
            const form = document.createElement("div"); form.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:2px;margin:4px 0";
            const arrow = document.createElement("span"); arrow.textContent = "→"; arrow.style.margin = "0 2px";
            const addBtn = document.createElement("button"); addBtn.className = "mini-btn"; addBtn.textContent = "+ rule";
            form.append(fromPset, fromProp, arrow, toPset, toProp, cast, addBtn);
            body.appendChild(form);
            const ruleList = document.createElement("div"); ruleList.style.margin = "6px 0"; body.appendChild(ruleList);
            const status = document.createElement("div"); status.className = "meta"; status.style.marginTop = "6px";
            const drawRules = () => {
              ruleList.innerHTML = "";
              rules.forEach((r, i) => {
                const row = document.createElement("div"); row.className = "selset-row";
                row.innerHTML = `<span class="selset-name" style="cursor:default">${escapeHtml(r.from_pset)}.${escapeHtml(r.from_prop)} → ${escapeHtml(r.to_pset || r.from_pset)}.${escapeHtml(r.to_prop)} <span class="meta">(${r.cast})</span></span>`;
                const del = document.createElement("button"); del.className = "selset-del"; del.textContent = "✕";
                del.onclick = () => { rules.splice(i, 1); drawRules(); };
                row.appendChild(del); ruleList.appendChild(row);
              });
            };
            addBtn.onclick = () => {
              if (!fromPset.value.trim() || !fromProp.value.trim() || !toProp.value.trim()) { notify("need from Pset + from Prop + to Prop", "error"); return; }
              rules.push({ from_pset: fromPset.value.trim(), from_prop: fromProp.value.trim(), to_pset: toPset.value.trim() || undefined, to_prop: toProp.value.trim(), cast: cast.value as PropMapRule["cast"] });
              fromProp.value = ""; toProp.value = ""; status.textContent = ""; drawRules();
            };
            const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:6px;margin-top:4px";
            const preview = document.createElement("button"); preview.className = "mini-btn"; preview.textContent = "👁 Preview";
            preview.onclick = async () => {
              if (!rules.length) { notify("add a rule first", "error"); return; }
              try { const pl = await api.propmapPlan(pid, rules); status.textContent = `${pl.changed} value(s) would change — ` + pl.rules.map((r) => `${r.to}: ${r.matched}`).join(" · "); }
              catch (e) { notify((e as Error).message, "error"); }
            };
            const apply = document.createElement("button"); apply.className = "mini-btn"; apply.textContent = "✔ Apply + republish";
            apply.onclick = async () => {
              if (!rules.length) { notify("add a rule first", "error"); return; }
              await authorAndReload("map_properties", { rules }, `normalize ${rules.length} propert${rules.length === 1 ? "y" : "ies"}`);
            };
            actions.append(preview, apply); body.append(actions, status);
          });
        }));
        b.appendChild(toolBtn2("🏛 Load takedown (preliminary)", async () => {
          let d; try { d = await api.loadsDefaults(pid); } catch { d = { storey_count: 0, column_count: 0, storey_names: [] }; }
          const v = await promptModal("Preliminary gravity load takedown",
            [{ name: "area", label: "Typical floor area (ft²)", value: "10000", required: true },
             { name: "storeys", label: "Storeys", value: String(d.storey_count || 5) },
             { name: "columns", label: "Interior columns / floor", value: String(d.column_count || 12) },
             { name: "occ", label: "Occupancy (office/residential/retail/parking…)", value: "office" }],
            "Compute",
            `Tributary-area gravity estimate + ASCE 7 combinations — PRELIMINARY only, not a substitute for a licensed engineer. Model has ${d.storey_count} storeys · ${d.column_count} columns.`);
          if (!v) return;
          await withLoading(container, "Running load takedown", async () => {
            let r;
            try { r = await api.loadsTakedown(pid, { floor_area_sf: Number(v.area), storey_count: Number(v.storeys) || undefined, column_count: Number(v.columns) || undefined, occupancy: v.occ || "office" }); }
            catch (e) { toast((e as Error).message, "error"); return; }
            out.textContent = `col ${r.column.factored_lrfd_kip}k (LRFD)`;
            showResult("Preliminary load takedown", (body) => {
              body.appendChild(resultNote(`Typical interior column — service <b>${r!.column.service_total_kip} kip</b> `
                + `(D ${r!.column.service_dead_kip} + L ${r!.column.service_live_kip}); factored <b>${r!.column.factored_lrfd_kip} kip</b> `
                + `LRFD / <b>${r!.column.factored_asd_kip} kip</b> ASD. Footing service ${r!.footing.service_total_kip} kip.`, "ok"));
              body.appendChild(kvTable([
                { k: "Governing LRFD", v: `${r!.combinations.governing_lrfd.combo} = ${r!.combinations.governing_lrfd.kips}k` },
                { k: "Governing ASD", v: `${r!.combinations.governing_asd.combo} = ${r!.combinations.governing_asd.kips}k` },
                { k: "Dead load", v: `${r!.assumptions.dead_psf} psf (slab ${r!.assumptions.slab_self_weight_psf} + SDL ${r!.assumptions.superimposed_dead_psf})` },
                { k: "Live reduction", v: `×${r!.assumptions.live_reduction_factor}` },
              ]));
              const warn = document.createElement("div"); warn.className = "meta";
              warn.style.cssText = "margin-top:8px;font-size:11px;border-left:3px solid var(--status-warn,#ffd479);padding-left:8px";
              warn.textContent = r!.disclaimer; body.appendChild(warn);
            });
          });
        }));
        b.appendChild(toolBtn2("✅ Verified-as-built progress", () => withLoading(container, "Rolling up verified progress", async () => {
          let r;
          try { r = await api.verifiedProgress(pid); }
          catch (e) { toast((e as Error).message, "error"); return; }
          if (!r.elements_total) {
            toast("No verified elements yet — run the layout check or log Field Verification records", "info");
            out.textContent = "no verified elements"; return;
          }
          out.textContent = `verified ${r.verified_pct}% · gap ${r.trust_gap}`;
          showResult("Verified-as-built progress", (body) => {
            const tone = r!.trust_gap > 10 ? "bad" : r!.trust_gap <= 0 ? "ok" : "";
            body.appendChild(resultNote(`<b>${r!.verified_pct}%</b> verified in place vs <b>${r!.claimed_pct}%</b> `
              + `claimed — trust gap <b>${r!.trust_gap} pts</b>. ${r!.elements_verified}/${r!.elements_total} elements `
              + `verified, ${r!.elements_deviated} deviated (coverage ${r!.coverage_pct}%).`, tone));
            body.appendChild(kvTable(r!.activities.slice(0, 12).map((a) => ({
              k: `${a.activity}${a.trade ? ` · ${a.trade}` : ""}`,
              v: `verified ${a.verified_pct}% / claimed ${a.planned_pct ?? 0}% · gap ${a.trust_gap} (${a.verified}/${a.elements}${a.deviated ? `, ${a.deviated} dev` : ""})`,
            }))));
            const note = document.createElement("div"); note.className = "meta";
            note.style.cssText = "margin-top:8px;font-size:11px";
            note.textContent = "Trust gap = claimed − verified %. Verified from Field Verification records (or the "
              + "layout as-installed check), rolled up to each schedule activity by GlobalId. Full report: Report Center → Verified-as-built Progress.";
            body.appendChild(note);
          });
        })));
        b.appendChild(toolBtn2("📐 Alignment check (storey + origin)", () => withLoading(container, "Checking model alignment", async () => {
          let r;
          try { r = await api.modelAlignment(pid); }
          catch { toast("Alignment needs ≥2 models — add one with “＋ Add discipline IFC”", "error"); return; }
          out.textContent = r.aligned ? "Models aligned ✓" : `${r.issues.length} alignment issue(s)`;
          toast(r.message, r.aligned ? "success" : "info");
          const tone: Record<string, string> = { high: "var(--status-crit,#e2554a)", medium: "var(--status-warn,#ffd479)", low: "var(--muted)" };
          showResult("Model alignment", (body) => {
            body.appendChild(resultNote(r!.message, r!.aligned ? "ok" : "bad"));
            body.appendChild(kvTable(r!.models.map((m) => ({ k: m.name, v: m.error ? `error: ${m.error}` : `${m.storey_count} storeys${m.georef ? " · georef" : ""}` }))));
            for (const i of r!.issues) {
              const d = document.createElement("div"); d.style.cssText = `font-size:12px;margin:3px 0;border-left:3px solid ${tone[i.severity] || "var(--muted)"};padding-left:6px`;
              d.innerHTML = `<b>${i.model}</b> — ${i.detail}`;
              body.appendChild(d);
            }
          });
        })));
        b.appendChild(toolBtn2("＋ Add discipline IFC…", () => {
          const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".ifc";
          inp.onchange = async () => {
            const file = inp.files?.[0]; if (!file) return;
            const disc = ((await askText("Add discipline IFC", { label: "Discipline (e.g. STR, MEP, ARCH):",
              value: file.name.replace(/\.ifc$/i, "").slice(0, 16) })) || "").trim();
            if (!disc) return;
            await withLoading(container, "adding discipline model", async () => {
              await api.addProjectModel(pid, file, disc);                                 // register server-side (for clash)
              await loader.loadIfc(new Uint8Array(await file.arrayBuffer()), nextId(disc)); // view it layered
              await fitToModels(); refreshFederation();
              toast(`added ${disc} discipline model — now in federated clash`, "success");
            });
          };
          inp.click();
        }));
        b.appendChild(toolBtn2("✓ Validate (IDS)", () => withLoading(container, "Queueing IDS validation",
          () => runIdsValidate({ api, pid, out, toolBtn2, selectMap, sets }))));
        b.appendChild(out);
}
