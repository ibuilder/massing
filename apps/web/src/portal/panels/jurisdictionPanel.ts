import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";
import type { JurisdictionPack, JurisdictionCheck, ProjectRequirements } from "../../api/jurisdiction";
import {
  adoptionLine, attributionLine, checkGate, checkSummary, deleteConfirm, exampleCaveat,
  importRefusal, outcomeLine, packHeadline,
} from "./jurisdictionPacks";

/**
 * R23-JURISDICTION-PACKS — data requirements published by an authority, and the screen that reaches
 * them. All five of this feature's routes had no client caller until this panel existed.
 *
 * The presentation rules live in `jurisdictionPacks.ts` and are tested there; this file is the DOM
 * and the five network calls. Three sections, in the order a person needs them: what applies here,
 * what the model does against it, and the shared library the packs come from.
 */
export async function renderJurisdiction(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("⚖️ Data Requirements", () => {
    ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav();
  }));
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Data Requirements")); return; }

  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.innerHTML = "A <b>pack</b> is a set of data requirements published by an authority for a "
    + "jurisdiction, and it is used to fail a submitted model — so every pack must carry its "
    + "<b>authority, edition and source</b>, and every result says whose rules produced it. Packs "
    + "resolve from this project's jurisdiction; a project with none gets no requirements rather "
    + "than a default, because requirements from the wrong authority are a different answer that "
    + "looks exactly like the right one. Importing and deleting need <b>admin</b>.";
  root.appendChild(intro);

  const applies = el("div"); applies.style.marginTop = "8px"; applies.textContent = "loading…";
  const results = el("div"); results.style.marginTop = "12px";
  const library = el("div"); library.style.marginTop = "16px";
  root.append(applies, results, library);

  /** Section 1 + 2: what applies here, and what the model does against it. */
  const drawProject = async () => {
    applies.textContent = "loading…"; results.innerHTML = "";
    let req: ProjectRequirements;
    try { req = await ctx.host.api.projectRequirements(pid); }
    catch (e) { applies.textContent = `requirements failed: ${(e as Error).message}`; return; }

    applies.innerHTML = `<div><b>${esc(adoptionLine(req))}</b></div>`;
    for (const p of req.packs) {
      const card = el("div", "dash-card"); card.style.cssText = "margin-top:6px";
      card.innerHTML = `<div>${esc(packHeadline(p))}</div>`
        + `<div class="meta" style="margin-top:2px">source: ${esc(p.source)}</div>`;
      const caveat = exampleCaveat(p);
      if (caveat) {
        card.style.borderLeft = "3px solid var(--status-warn)";
        card.insertAdjacentHTML("beforeend",
          `<div class="meta" style="margin-top:4px">${esc(caveat)}</div>`);
      }
      applies.appendChild(card);
    }
    if (!req.adopted && !req.explicit) return;    // nothing to check against

    await drawCheck(req);
  };

  const drawCheck = async (req: ProjectRequirements) => {
    results.innerHTML = "<span class='meta'>checking the model…</span>";
    let r: JurisdictionCheck;
    try { r = await ctx.host.api.jurisdictionCheck(pid); }
    catch (e) { results.textContent = `check failed: ${(e as Error).message}`; return; }
    results.innerHTML = "";

    const head = el("div");
    head.innerHTML = `<b>${esc(checkSummary(r))}</b>`;
    results.appendChild(head);

    // The example pack's caveat rides with the RESULT, not only with the pack above: a reader who
    // scrolled to the number is the one who needs it.
    if (r.packs.some((p) => p.is_example)) {
      const c = el("div", "dash-card");
      c.style.cssText = "margin-top:6px;border-left:3px solid var(--status-warn)";
      c.innerHTML = `<span class="meta">${esc(exampleCaveat({ is_example: true }))}</span>`;
      results.appendChild(c);
    }

    for (const p of r.packs) {
      const row = el("div", "meta"); row.style.marginTop = "4px";
      row.textContent = outcomeLine(p);
      results.appendChild(row);
    }
    if (r.packs.length) {
      const attr = el("div", "meta"); attr.style.marginTop = "6px";
      attr.textContent = `Measured against: ${attributionLine(r.packs)}`;
      results.appendChild(attr);
    }

    // `model_scored` from the run we just did is what says whether a re-run can mean anything --
    // the same reason `checkGate` takes it rather than assuming. A button that will certainly come
    // back empty is the offered-and-refused shape this codebase keeps removing.
    const gate = checkGate(req, r.model_scored);
    const act = el("div"); act.style.marginTop = "8px";
    if (gate.can) {
      const btn = el("button", "mini-btn") as HTMLButtonElement;
      btn.textContent = "↻ Re-check the model";
      btn.onclick = () => { void drawCheck(req); };
      act.appendChild(btn);
    } else {
      act.innerHTML = `<span class="meta">Cannot check — ${esc(gate.why)}</span>`;
    }
    results.appendChild(act);
  };

  /** Section 3: the shared library, and the two writes that maintain it. */
  const drawLibrary = async () => {
    library.innerHTML = "<span class='meta'>loading the pack library…</span>";
    let lib;
    try { lib = await ctx.host.api.jurisdictionPacks(); }
    catch (e) { library.textContent = `library failed: ${(e as Error).message}`; return; }
    library.innerHTML = `<div style="margin-bottom:6px"><b>Pack library — ${lib.count} pack`
      + `${lib.count === 1 ? "" : "s"}</b> <span class="meta">shared across every project</span></div>`;

    for (const p of lib.packs) library.appendChild(libraryRow(p));
    library.appendChild(importBox());
  };

  const libraryRow = (p: JurisdictionPack) => {
    const card = el("div", "dash-card"); card.style.cssText = "margin-bottom:6px";
    card.innerHTML = `<div>${esc(packHeadline(p))}</div>`
      + `<div class="meta" style="margin-top:2px">source: ${esc(p.source)}</div>`;
    if (p.is_example) {
      card.style.borderLeft = "3px solid var(--status-warn)";
      card.insertAdjacentHTML("beforeend",
        `<div class="meta" style="margin-top:4px">${esc(exampleCaveat(p))} It cannot be deleted.`
        + `</div>`);
      return card;
    }
    const btn = el("button", "mini-btn") as HTMLButtonElement;
    btn.textContent = "🗑 Delete"; btn.style.marginTop = "6px";
    btn.onclick = async () => {
      if (!window.confirm(deleteConfirm(p))) return;
      btn.disabled = true;
      try { await ctx.host.api.jurisdictionDeletePack(p.id); }
      catch (e) {
        btn.disabled = false;
        // The server's own text distinguishes "not yours to delete" (403) from "no such imported
        // pack" (404) -- a generic failure would hide which.
        ctx.host.setStatus(`could not delete the pack: ${(e as Error).message}`);
        return;
      }
      ctx.host.setStatus(`Deleted the pack "${p.name}".`);
      // Deleting changes what resolves for this project too, so both halves are re-read. They are
      // separate awaits from the delete above on purpose: a failed refresh must not report a
      // failed delete.
      void drawLibrary(); void drawProject();
    };
    card.appendChild(btn);
    return card;
  };

  const importBox = () => {
    const box = el("div", "dash-card"); box.style.marginTop = "10px";
    box.innerHTML = "<div><b>Import a pack</b></div>"
      + `<div class="meta" style="margin-top:2px">Paste the pack JSON from the authority. It is `
      + `refused unless it carries an <b>id, jurisdiction, authority, name, edition and source</b>, `
      + `and every selector is parsed with the engine that will evaluate it — so a rule that would `
      + `silently match nothing is refused rather than stored.</div>`;
    const ta = el("textarea", "portal-filter") as HTMLTextAreaElement;
    ta.rows = 6; ta.style.cssText = "width:100%;margin-top:6px;font-family:monospace;font-size:12px";
    ta.placeholder = '{"id": "tx-austin-2026", "jurisdiction": "TX", "authority": "…", '
      + '"name": "…", "edition": "…", "source": "…", "requirements": [{"scope": "…", "require": "…"}]}';
    const btn = el("button", "mini-btn") as HTMLButtonElement;
    btn.textContent = "⬆ Import"; btn.style.marginTop = "6px";
    btn.onclick = async () => {
      let parsed: unknown;
      // A malformed paste is the USER's error and gets its own message: `importRefusal` is for what
      // the server said, and attributing a JSON syntax error to the server would send the reader to
      // look at their requirements when the problem is a missing brace.
      try { parsed = JSON.parse(ta.value); }
      catch (e) {
        ctx.host.setStatus(`That is not valid JSON: ${(e as Error).message}`);
        return;
      }
      btn.disabled = true;
      let stored;
      try { stored = await ctx.host.api.jurisdictionImportPack(parsed); }
      catch (e) {
        btn.disabled = false;
        ctx.host.setStatus(importRefusal((e as Error).message));
        return;
      }
      btn.disabled = false; ta.value = "";
      ctx.host.setStatus(`Imported "${stored.name}" (${stored.authority}, ${stored.edition}) for `
        + `${stored.jurisdiction}.`);
      void drawLibrary(); void drawProject();
    };
    box.append(ta, btn);
    return box;
  };

  // Concurrent, not sequential: the two sections share no state, and `drawProject` waits on a model
  // check that can take seconds. Awaiting it first left the pack library -- and the import box, the
  // only way to fix "no pack has been imported for TX" -- blank until that check settled. Found in
  // review on PR #527. Each half already catches its own failure, so neither can reject here.
  await Promise.all([drawProject(), drawLibrary()]);
}
