import { noProjectHtml } from "../../ui/empty";
import { escapeHtml as esc } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";
import type { PrefabKit } from "../../api/prefab";
import {
  blockerLabel, driftLine, freezeConfirm, freezeGate, freezeSummary, modelCaveat, registerHeadline,
  scopeNote,
} from "./prefabKits";

/**
 * R23-PREFAB-KIT — the prefabrication-kit register, and the write that turns a kit into a document.
 *
 * The presentation rules are in `prefabKits.ts` and tested there; this file is the DOM and the two
 * network calls. Kits arrive worst-first from the server — a kit whose released scope has DRIFTED
 * outranks one that is merely late, because a late kit is a known problem and a drifted one is an
 * unknown wrong one.
 */
export async function renderPrefabKits(ctx: PanelContext) {
  const root = ctx.root; root.innerHTML = "";
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  root.appendChild(ctx.bar("🧰 Prefab Kits", () => {
    ctx.activeKey = null; void ctx.renderHome(); ctx.buildNav();
  }));
  const pid = ctx.host.projectId();
  if (!pid) { root.insertAdjacentHTML("beforeend", noProjectHtml("Prefab Kits")); return; }

  const intro = el("div", "meta"); intro.style.marginBottom = "8px";
  intro.innerHTML = "A kit's scope is a <b>selector</b> until it is written down, and a <b>frozen "
    + "GlobalId list</b> afterwards. Writing the scope is what makes a released kit a document rather "
    + "than a live query — from there the shop builds that list, and any later divergence is reported "
    + "here instead of silently changing what is being fabricated. Writing a scope needs the "
    + "<b>editor</b> role.";
  root.appendChild(intro);

  const body = el("div"); body.style.marginTop = "8px"; body.textContent = "loading…";
  root.appendChild(body);

  const draw = async () => {
    body.textContent = "loading…";
    let reg;
    try { reg = await ctx.host.api.prefabRegister(pid); }
    catch (e) { body.textContent = `failed: ${(e as Error).message}`; return; }
    body.innerHTML = "";

    const head = el("div"); head.style.marginBottom = "6px";
    head.innerHTML = `<b>${esc(registerHeadline(reg))}</b>`;
    body.appendChild(head);

    const caveat = modelCaveat(reg);
    if (caveat) {
      const c = el("div", "dash-card");
      c.style.cssText = "margin-bottom:8px;border-left:3px solid var(--status-warn)";
      c.innerHTML = `<span class="meta">${esc(caveat)}</span>`;
      body.appendChild(c);
    }
    if (!reg.total) return;

    for (const kit of reg.kits) body.appendChild(kitCard(kit, reg.model_loaded));
  };

  const kitCard = (kit: PrefabKit, modelLoaded: boolean) => {
    const tone = kit.ready ? "var(--status-good)"
      : kit.blockers.some((b) => b.code === "released_without_freezing" || b.code === "scope_drift")
        ? "var(--status-crit)" : "var(--status-warn)";
    const card = el("div", "dash-card");
    card.style.cssText = `margin-bottom:8px;border-left:3px solid ${tone}`;
    const title = [kit.ref, kit.name].filter(Boolean).join(" · ") || "(unnamed kit)";
    const meta = [kit.trade, kit.fabricator, kit.state].filter(Boolean).join(" · ");
    card.innerHTML = `<div><b>${esc(title)}</b> <span class="meta">${esc(meta)}</span></div>`
      + `<div class="meta" style="margin-top:4px">${esc(scopeNote(kit))}</div>`;

    const drift = driftLine(kit);
    if (drift) {
      card.insertAdjacentHTML("beforeend",
        `<div class="meta" style="margin-top:4px;color:var(--status-crit)">${esc(drift)}</div>`);
    }
    if (kit.blockers.length) {
      card.insertAdjacentHTML("beforeend",
        `<ul class="meta" style="margin:4px 0 0 16px;padding:0">`
        + kit.blockers.map((b) => `<li>${esc(blockerLabel(b.code))} <span style="opacity:.7">`
          + `— ${esc(b.detail)}</span></li>`).join("") + `</ul>`);
    }
    if (kit.bom.lines.length) {
      const rows = kit.bom.lines.slice(0, 12).map((l) =>
        `<tr><td>${esc(l.type_name || l.ifc_class || l.key)}</td>`
        + `<td style="text-align:right">${l.count}</td></tr>`).join("");
      card.insertAdjacentHTML("beforeend",
        `<table class="portal-table" style="width:100%;font-size:12px;margin-top:6px"><tbody>${rows}`
        + `</tbody></table>`
        + (kit.bom.lines.length > 12
          ? `<div class="meta">${kit.bom.lines.length - 12} more type(s) not shown</div>` : ""));
    }

    const gate = freezeGate(kit, modelLoaded);
    const act = el("div"); act.style.marginTop = "6px";
    // `rid` in the route is the record's ID -- `modules.get_record` filters on `t.c.id`. There is no
    // ref fallback on purpose: a kit whose id did not arrive would 404 on a path built from its ref,
    // and a write that fails on a wrong key looks exactly like one the server refused on the merits.
    if (gate.can && kit.id != null && kit.id !== "") {
      const btn = el("button", "portal-btn") as HTMLButtonElement;
      btn.textContent = kit.frozen_count ? "✎ Re-write the scope" : "✎ Write the scope";
      btn.onclick = async () => {
        if (!window.confirm(freezeConfirm(kit))) return;
        btn.disabled = true;
        let written;
        try {
          written = await ctx.host.api.prefabFreeze(pid, String(kit.id));
        } catch (e) {
          btn.disabled = false;
          // The server answers a refusal with its own fixed literal -- show that, not a generic
          // failure, because it names which of the four refusals applied.
          ctx.host.setStatus(`could not write the scope: ${(e as Error).message}`);
          return;
        }
        ctx.host.setStatus(freezeSummary(written));
        // The re-read is SEPARATE from the write on purpose. Folding both into one try would let a
        // failed refresh report "could not write the scope" about a write that succeeded -- a false
        // statement about a record the shop builds from, and the reader's next move would be to
        // write it again. A stale card is a much smaller wrong than a phantom failure.
        //
        // Re-reading THIS kit rather than the register also skips re-resolving every other kit's
        // selector against the model index, and keeps the reader's position in a list they are
        // working down. The detail route returns the same assessment shape, so the replacement card
        // is built by the same function.
        try {
          card.replaceWith(kitCard(await ctx.host.api.prefabKit(pid, String(kit.id)), modelLoaded));
        } catch {
          btn.disabled = true;
          btn.textContent = "✓ scope written — reopen to refresh";
        }
      };
      act.appendChild(btn);
    } else {
      const why = gate.can ? "this kit record carries no id" : gate.why;
      act.innerHTML = `<span class="meta">Scope cannot be written — ${esc(why)}.</span>`;
    }

    // Highlighting needs the GlobalIds themselves, and only the SELECTOR side returns them: the
    // register reports a frozen kit's scope as a count, never as a list. So the button is absent
    // with a reason rather than present and inert -- `panelContext.hasDest` states the same rule for
    // rail destinations, and a button that silently does nothing is worse than an absent one.
    const guids = kit.scope_source === "frozen" ? [] : kit.selector.guids;
    if (guids.length) {
      const show = el("button", "portal-btn") as HTMLButtonElement;
      show.textContent = "◉ Show in 3D"; show.style.marginLeft = "6px";
      show.onclick = () => ctx.host.onSelectGuids(guids);
      act.appendChild(show);
    } else if (kit.scope_source === "frozen") {
      act.insertAdjacentHTML("beforeend",
        `<span class="meta" style="margin-left:6px">The frozen list is not returned by the register, `
        + `so it cannot be highlighted from here.</span>`);
    }
    card.appendChild(act);
    return card;
  };

  await draw();
}
