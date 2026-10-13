import type { ViewTemplate, ViewTemplateDraft, ViewTemplateRule } from "../../api/model";
import { escapeHtml as esc, toast } from "../../ui/feedback";
import type { PanelContext } from "../panelContext";

/**
 * VIEW-TEMPLATES (R18 / R21-VG-OVERRIDES) — made authorable (VIEWTPL-DARK).
 *
 * `services/api/src/aec_api/view_templates.py` resolves a saved template against a model
 * deterministically: a class-visibility matrix, an optional QUERY-DSL isolate scope, stacked colour
 * rules, and — since R21 — per-category **object styles** whose cut side is heavier than its
 * projection side, which that module calls *"the single distinction that separates a drawing from a
 * dump"*.
 *
 * **Two screens consumed it and nothing could create one.** `qaSection.ts` lists templates and
 * APPLIES one, with a comment reading *"Both halves were unreachable… A saved view nobody can apply
 * is a stored preference with no effect"* — and ending *"unlike the template WRITE endpoints"*, so
 * the author knew. `standards.ts` reads `viewTemplateGraphics` for the first template. Both printed
 * the same sentence on every project that has ever existed: **"No view templates saved."**
 * `saveViewTemplates` had no caller anywhere in the app.
 *
 * ### What this owns, and what it carries through untouched
 *
 * It authors name, isolate, hide_classes and the colour rules (selector, colour, and the cut /
 * projection / both scope). It does **not** author `object_styles`, the per-IFC-class weight tables —
 * that is a second slice and saying so is cheaper than implying coverage.
 *
 * **But it must PRESERVE them, and that is the one defect this file could most easily have
 * shipped.** `save` replaces the whole list, so a template edited here is written back whole: build
 * the payload from a fresh object and every object style, every per-rule weight and pattern on every
 * template the user touched is silently deleted, while templates they left alone keep theirs. That
 * is the exact shape AUTHORITY-SUPERSEDE paid for — *"the worst available shape, because the loss is
 * proportional to how much they edited"*. Every draft here starts as a spread of the stored template
 * and only the fields this editor owns are replaced.
 */

/** The server refuses a template that sets nothing: *"a template needs at least one of hide_classes
 *  / isolate / rules / object_styles"*. Checked here so the editor can say which template, rather
 *  than the save failing on the first one and naming no index. */
export function isDeclared(t: Partial<ViewTemplate>): boolean {
  return !!(t.hide_classes?.length || (t.isolate ?? "").trim() || t.rules?.length
    || Object.keys(t.object_styles ?? {}).length);
}

const HEX = /^#[0-9a-fA-F]{6}$/;

/** Rule indexes whose colour is not `#rrggbb`. `color` is REQUIRED on every rule and the server's
 *  message quotes the bad value, so this marks the field rather than replacing that message. */
export function badColors(rules: readonly ViewTemplateRule[]): number[] {
  return rules.map((r, i) => (HEX.test((r.color ?? "").trim()) ? -1 : i)).filter((i) => i >= 0);
}

/** How many graphic facts a template carries that this editor does not author — object-style
 *  categories, plus rules with a weight, pattern or halftone override. Rendered, not hidden: a
 *  number a user can see is the only way they can tell a round trip preserved it. */
export function carriedThrough(t: ViewTemplate): { styles: number; overrides: number } {
  return {
    styles: Object.keys(t.object_styles ?? {}).length,
    overrides: (t.rules ?? []).filter(
      (r) => r.weight != null || r.pattern != null || r.halftone != null).length,
  };
}

/** One line describing what a template DOES, in the vocabulary the viewer's apply list uses. */
export function summarise(t: ViewTemplate): string {
  const bits = [
    (t.isolate ?? "").trim() ? `isolate ${t.isolate}` : "",
    t.hide_classes?.length ? `hides ${t.hide_classes.length}` : "",
    t.rules?.length ? `${t.rules.length} colour rule(s)` : "",
    Object.keys(t.object_styles ?? {}).length
      ? `${Object.keys(t.object_styles ?? {}).length} object style(s)` : "",
  ].filter(Boolean);
  return bits.length ? bits.join(" · ") : "sets nothing yet";
}

const APPLIES = ["both", "cut", "projection"] as const;

export async function renderViewTemplates(ctx: PanelContext, host: HTMLElement,
                                          pid: string): Promise<void> {
  host.innerHTML = `<div class="meta">reading view templates…</div>`;
  let templates: ViewTemplate[];
  try {
    templates = (await ctx.host.api.viewTemplates(pid)).templates.map((t) => ({ ...t }));
  } catch (e) {
    host.innerHTML = `<div class="meta">View templates unavailable: ${esc((e as Error).message)}</div>`;
    return;
  }

  let active = 0;
  host.innerHTML = "";
  const intro = document.createElement("div"); intro.className = "meta";
  intro.style.marginBottom = "8px";
  intro.textContent = "A saved view: what to isolate, which classes to hide, and which selectors get "
    + "which colour — resolved deterministically against whatever model is loaded. Apply one from the "
    + "viewer's QA section.";
  host.appendChild(intro);

  const tabs = document.createElement("div");
  tabs.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px";
  const editor = document.createElement("div");
  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:8px";
  const save = document.createElement("button"); save.className = "tool-btn on";
  save.textContent = "Save templates";
  const msg = document.createElement("div"); msg.className = "meta"; msg.style.marginTop = "6px";
  msg.setAttribute("role", "status");
  foot.appendChild(save);
  host.append(tabs, editor, foot, msg);

  const field = (label: string, value: string, hint: string, set: (v: string) => void,
                 bad = false) => {
    const l = document.createElement("label"); l.className = "meta";
    l.style.cssText = "display:block;margin-top:6px";
    l.textContent = label;
    const inp = document.createElement("input"); inp.className = "portal-filter";
    inp.value = value; inp.placeholder = hint; inp.maxLength = 500;
    inp.style.cssText = "width:100%;box-sizing:border-box;font-size:12px";
    if (bad) inp.style.borderColor = "var(--status-crit)";
    inp.oninput = () => set(inp.value);
    l.appendChild(inp);
    return l;
  };

  const paintTabs = () => {
    tabs.innerHTML = "";
    templates.forEach((t, i) => {
      const b = document.createElement("button");
      b.className = i === active ? "tool-btn on" : "tool-btn";
      b.textContent = t.name || "(unnamed)";
      b.onclick = () => { active = i; paint(); };
      tabs.appendChild(b);
    });
    const add = document.createElement("button"); add.className = "tool-btn";
    add.textContent = "＋ template";
    add.onclick = () => {
      templates.push({ id: "", name: `Template ${templates.length + 1}`, hide_classes: [],
                       isolate: null, rules: [] });
      active = templates.length - 1; paint();
    };
    tabs.appendChild(add);
  };

  const paint = () => {
    paintTabs();
    editor.innerHTML = "";
    const t = templates[active];
    if (!t) {
      const empty = document.createElement("div"); empty.className = "meta";
      empty.textContent = "No view templates saved. Add one — a template needs at least an isolate "
        + "selector, a hidden class or a colour rule.";
      editor.appendChild(empty);
      return;
    }
    const head = document.createElement("div");
    head.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
    const name = document.createElement("input"); name.className = "portal-filter";
    name.value = t.name ?? ""; name.maxLength = 120; name.placeholder = "template name";
    name.style.cssText = "flex:1 1 180px;font-weight:600";
    name.oninput = () => { t.name = name.value; paintTabs(); };
    const del = document.createElement("button"); del.className = "selset-del";
    del.textContent = "✕ delete"; del.title = "Remove this template from the project";
    del.onclick = () => {
      templates.splice(active, 1);
      active = Math.max(0, Math.min(active, templates.length - 1));
      paint();
    };
    head.append(name, del);
    editor.appendChild(head);

    const summary = document.createElement("div"); summary.className = "meta";
    summary.style.margin = "4px 0";
    summary.textContent = summarise(t);
    editor.appendChild(summary);
    if (!isDeclared(t)) {
      const warn = document.createElement("div"); warn.className = "meta";
      warn.style.color = "var(--status-crit)";
      warn.textContent = "⚠ This template sets nothing — the server refuses a template with no "
        + "isolate, no hidden class, no colour rule and no object style.";
      editor.appendChild(warn);
    }

    editor.appendChild(field("Isolate — a QUERY-DSL selector, or blank for the whole model",
      t.isolate ?? "", 'e.g. ifc_class = IfcWall and Pset_WallCommon.FireRating != ""',
      (v) => { t.isolate = v.trim() || null; summary.textContent = summarise(t); }));
    editor.appendChild(field("Hide classes — comma separated IFC class names",
      (t.hide_classes ?? []).join(", "), "IfcFurnishingElement, IfcSpace",
      (v) => {
        t.hide_classes = v.split(",").map((x) => x.trim()).filter(Boolean);
        summary.textContent = summarise(t);
      }));

    const rulesHead = document.createElement("div"); rulesHead.className = "meta";
    rulesHead.style.cssText = "margin-top:10px;font-weight:600";
    rulesHead.textContent = "Colour rules — later rules win";
    editor.appendChild(rulesHead);
    const bad = new Set(badColors(t.rules ?? []));
    (t.rules ?? []).forEach((r, i) => {
      const card = document.createElement("div"); card.className = "dash-card";
      card.style.cssText = "margin:6px 0;padding:8px";
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
      const colour = document.createElement("input"); colour.className = "portal-filter";
      colour.value = r.color ?? ""; colour.placeholder = "#rrggbb"; colour.maxLength = 7;
      colour.style.cssText = "flex:0 0 100px;font-family:monospace";
      if (bad.has(i)) colour.style.borderColor = "var(--status-crit)";
      colour.oninput = () => { r.color = colour.value; paint(); };
      const swatch = document.createElement("span");
      swatch.style.cssText = "flex:0 0 18px;height:18px;border-radius:4px;border:1px solid var(--line)";
      if (HEX.test((r.color ?? "").trim())) swatch.style.background = r.color!.trim();
      // The cut/projection scope. This is the axis R21-VG-OVERRIDES exists for, and the client type
      // did not declare it until VIEWTPL-DARK — so no editor could have offered it and no reader
      // could have seen it, whatever the server stored.
      const app = document.createElement("select"); app.className = "portal-filter";
      app.style.cssText = "flex:0 0 110px;font-size:12px";
      app.title = "Which side of the view plane this rule colours: the cut face, what is seen "
        + "beyond it, or both";
      // SET `select.value`, NEVER `option.selected`, and this was MEASURED rather than preferred:
      // in happy-dom, assigning `o.selected` inside an append loop lands on `selectedIndex` ONE
      // BEFORE the intended option (probed directly: marking index 2 yields index 1). A real
      // browser follows the spec and would be right, so this may cost nothing in production — but
      // every test in this repo runs in happy-dom, so a dropdown asserted that way is asserted
      // against the wrong value, and `select.value` is unambiguous in both. *The pattern was already
      // in three files and only one test asserted the property, which is why two of them shipped.*
      for (const a of APPLIES) {
        const o = document.createElement("option"); o.value = a; o.textContent = a;
        app.appendChild(o);
      }
      app.value = r.applies ?? "both";
      app.onchange = () => { r.applies = app.value as ViewTemplateRule["applies"]; };
      const rdel = document.createElement("button"); rdel.className = "selset-del";
      rdel.textContent = "✕";
      rdel.onclick = () => { (t.rules ?? []).splice(i, 1); paint(); };
      row.append(swatch, colour, app, rdel);
      card.appendChild(row);
      card.appendChild(field("Selector", r.selector ?? "",
        'e.g. ifc_class = IfcDoor', (v) => { r.selector = v; }));
      if (r.weight != null || r.pattern != null || r.halftone != null) {
        const kept = document.createElement("div"); kept.className = "meta";
        kept.style.cssText = "margin-top:4px;opacity:.8";
        kept.textContent = "Carried through unchanged: "
          + [r.weight != null ? `${r.weight} mm` : "", r.pattern ?? "",
             r.halftone ? "halftone" : ""].filter(Boolean).join(" · ");
        card.appendChild(kept);
      }
      editor.appendChild(card);
    });
    const addRule = document.createElement("button"); addRule.className = "tool-btn";
    addRule.textContent = "＋ colour rule";
    addRule.onclick = () => {
      t.rules.push({ selector: "", color: "#2563eb", applies: "both" });
      paint();
    };
    editor.appendChild(addRule);

    // What this editor preserves but does not author, COUNTED on screen. A round trip that silently
    // dropped these would look identical to one that kept them.
    const carried = carriedThrough(t);
    if (carried.styles || carried.overrides) {
      const note = document.createElement("div"); note.className = "meta";
      note.style.cssText = "margin-top:8px;opacity:.85";
      note.textContent = `Preserved unchanged by this editor: ${carried.styles} object-style `
        + `categor${carried.styles === 1 ? "y" : "ies"} and ${carried.overrides} rule-level `
        + "weight/pattern override(s). Authoring those is a separate control.";
      editor.appendChild(note);
    }
  };

  save.onclick = async () => {
    const undeclared = templates.map((t, i) => (isDeclared(t) ? -1 : i)).filter((i) => i >= 0);
    if (undeclared.length) {
      msg.textContent = `Refused locally: ${undeclared.map((i) => templates[i]!.name || `#${i + 1}`)
        .join(", ")} set nothing. The server rejects the whole save for one bad template, so the `
        + "name is more use than its message here.";
      return;
    }
    save.disabled = true; msg.textContent = "saving…";
    try {
      // The STORED template spread first, so object styles and rule-level overrides this editor
      // does not author survive the round trip. `id` is omitted when blank: the server assigns one.
      const payload: ViewTemplateDraft[] = templates.map((t) => {
        const { id, ...rest } = t;
        return id ? { id, ...rest } : rest;
      });
      const res = await ctx.host.api.saveViewTemplates(pid, payload);
      templates = res.templates.map((t) => ({ ...t }));
      active = Math.max(0, Math.min(active, templates.length - 1));
      msg.textContent = `Saved ${res.saved} template(s). The viewer's QA section can apply them now.`;
      toast("View templates saved", "success");
      paint();
    } catch (e) {
      // Shown verbatim: the server's QueryError names the selector or the colour that failed to
      // parse, which is the only thing that says what to fix.
      msg.textContent = `Refused: ${(e as Error).message}`;
    } finally {
      save.disabled = false;
    }
  };

  paint();
}
