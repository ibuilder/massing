import type { ApiClient } from "../../api/client";
import { askText } from "../../ui/prompt";
import { kvTable, resultNote, showResult } from "../../ui/result";

/**
 * R39-DECOMP-VIEWER ⑯ — **detailing**, out of `app.ts`.
 *
 * The two tools that attach code/spec/detail carriers to elements: the manual panel (W11 Track D —
 * classification codes and detail/instruction documents on the selected element, which is what
 * keynotes, schedules and the spec/drawing generators read downstream) and the rule-driven pass
 * (condition→content rules over the whole model — exterior openings get IBC/ASTM flashing details
 * and specs, rated walls get assembly keynotes; the same rules validate as IDS QA).
 *
 * ## The ⑭ check, done first
 *
 * ⑭ looked like a text move and was not — state that sat outside `buildToolsPanel` on purpose
 * (because it re-runs on every persona switch) stacked a listener per rebuild when scoped inside
 * the extracted builder. So this block was checked for that shape before anything moved: it
 * assigns to nothing declared outside itself and installs no listener. Two slices running, the
 * check is cheap and it is the difference between a text move and a leak.
 *
 * `selectedGuid` crosses as an ACCESSOR. Both tools are selection-gated, so collapsing it would not
 * fail loudly — both would answer *"select an element to detail"* for the life of the session,
 * which is the exact shape `qaSection.ts` shipped once and `accessorNotCollapsed.test.ts` guards.
 */
export interface DetailingDeps {
  /** A full-width tool button. Declared inside `buildToolsPanel`, handed over whole. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  /** The project id, non-null-asserted by the caller inside its project gate. */
  pid: string;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  /** **An accessor, never a value** — `let` in `app.ts`, changes with every click in 3D. */
  selectedGuid: () => string | null;
  /**
   * Runs an edit recipe and republishes. The REAL signature, `{applied, refused}` included — a
   * narrowed `Promise<void>` would let a caller here treat a REFUSED edit as a successful one.
   */
  authorAndReload: (recipe: string, params: Record<string, unknown>, label: string,
                    previewId?: string | null, previewGuid?: string)
                   => Promise<{ applied: boolean; refused: boolean }>;
}

export function buildDetailingSection(d: DetailingDeps) {
    // W11 Track D: attach code/spec/detail carriers to the selected element (classification codes +
    // detail/instruction documents) — what keynotes, schedules and the spec/drawing generators read.
    const openDetailingPanel = async () => {
      // Read once, INSIDE the handler and BEFORE the guard, so the guard narrows it. The original
      // `if (!selectedGuid) ...; const guid = selectedGuid;` narrowed for free off the `let`; two
      // accessor calls do not, and could return different elements if the selection changes between.
      const guid = d.selectedGuid();
      if (!guid) { d.notify("select an element to detail", "error"); return; }
      let det;
      try { det = await d.api.elementDetailing(d.pid, guid); }
      catch (e) { d.notify(`detailing failed: ${(e as Error).message}`, "error"); return; }
      showResult(`Detailing — ${det.name}`, (body) => {
        body.appendChild(kvTable(det.classifications.length
          ? det.classifications.map((c) => ({ k: c.system || "code", v: `${c.code ?? ""}${c.title ? " · " + c.title : ""}` }))
          : [{ k: "Classifications", v: "none" }]));
        body.appendChild(resultNote(det.documents.length
          ? "<b>Documents</b>: " + det.documents.map((d) => `${d.identification ?? ""} ${d.name ?? ""}`.trim()).join(" · ")
          : "No details/instructions attached.", ""));
        const reopen = () => openDetailingPanel();
        const CLS = [["MasterFormat", "spec section, e.g. 08 51 00"], ["UniFormat", "element/keynote, e.g. B2020"],
          ["OmniClass", "product, e.g. 23-17 11 11"], ["Uniclass", "e.g. SS_25_10"]] as const;
        for (const [sys, hint] of CLS) {
          body.appendChild(d.toolBtn2(`＋ ${sys} code`, async () => {
            const code = await askText(`${sys} code`, { label: hint, value: "" }); if (!code) return;
            const title = await askText(`${sys} code`, { label: "Title (optional)", value: "" });
            await d.authorAndReload("classify", { guids: [guid], system: sys, code: code.trim(), name: title?.trim() || undefined }, `${sys} ${code.trim()}`);
            await reopen();
          }));
        }
        body.appendChild(d.toolBtn2("📎 Attach detail / instruction", async () => {
          const name = await askText("Attach document", { label: "Document name", value: "Flashing detail" }); if (!name) return;
          const ident = await askText("Attach document", { label: "Detail no. / key (e.g. A-541/3)", value: "" });
          const loc = await askText("Attach document", { label: "Location (URI — SVG/PDF)", value: "" });
          await d.authorAndReload("attach_document",
            { guids: [guid], name: name.trim(), identification: ident?.trim() || undefined, location: loc?.trim() || undefined },
            `document ${name.trim()}`);
          await reopen();
        }));
      });
    };
    const detailBtn = d.toolBtn2("🏷 Detailing (codes & documents)", openDetailingPanel);
    detailBtn.title = "Attach keynote/spec codes (UniFormat/MasterFormat/OmniClass) and detail/instruction "
      + "documents to the selected element — IFC-native carriers that feed keynotes, schedules & the spec/drawing set";

    // W11 D3: auto-detail the whole model from the rule library + an IDS-style missing-keynote pre-flight.
    const openAutoDetail = async () => {
      let val;
      try { val = await d.api.validateDetailing(d.pid); }
      catch (e) { d.notify(`validate failed: ${(e as Error).message}`, "error"); return; }
      showResult("Auto-detail (code / spec / detail rules)", (body) => {
        body.appendChild(resultNote(val.gaps
          ? `<b>${val.gaps}</b> element(s) match a rule but are <b>missing</b> their keynote/spec — e.g. an `
            + `exterior window with no flashing detail. Run auto-detail to attach them.`
          : "Every rule-covered element already carries its code & detail. ✓", val.gaps ? "bad" : "ok"));
        if (val.gaps) {
          body.appendChild(kvTable(val.elements.slice(0, 12).map((g) => ({ k: g.name, v: g.missing }))));
        }
        const run = d.toolBtn2("✨ Auto-detail model (apply rules)", async () => {
          await d.authorAndReload("apply_detailing_rules", {}, "auto-detail");
          await openAutoDetail();
        });
        run.title = "Attach the code/spec/detail bundle to every element a rule matches — e.g. exterior "
          + "window → IBC §1404.4 / ASTM E2112 flashing detail + install instruction + spec 08 51 00. GUID-stable.";
        body.appendChild(run);
      });
    };
    const autoDetailBtn = d.toolBtn2("✨ Auto-detail (rules)", openAutoDetail);
    autoDetailBtn.title = "Run the condition→content rule library over the model — exterior windows/doors get "
      + "IBC/ASTM flashing details + specs, rated walls get assembly keynotes. Same rules validate as IDS QA.";


  return { detailBtn, autoDetailBtn };
}
