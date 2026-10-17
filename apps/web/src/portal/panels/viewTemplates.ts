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
 *  number a user can see is the only way they can tell a round trip preserved it.
 *
 *  **`styles` is no longer one of them, and the shape keeps it on purpose.** VG-STYLES made the
 *  object-style table authorable, so counting it as *preserved but not authored* became false the
 *  moment the editor grew a form for it — and a note that says "preserved unchanged" over a field
 *  the user just edited is worse than no note. `styles` is still returned because it is the number
 *  `summarise` and the section heading both want; what changed is `unauthored`, which is the one the
 *  preservation note reads and which now counts rule-level overrides alone. *A count does not become
 *  wrong when the product changes — the SENTENCE it was feeding does.* */
export function carriedThrough(t: ViewTemplate): {
  styles: number; overrides: number; unauthored: number;
} {
  const overrides = (t.rules ?? []).filter(
    (r) => r.weight != null || r.pattern != null || r.halftone != null).length;
  return { styles: Object.keys(t.object_styles ?? {}).length, overrides, unauthored: overrides };
}

/** The server's bounds on an object style, restated so the editor can name the CLASS that failed.
 *  `view_templates` refuses the whole save on the first bad entry and its message names the class
 *  and side — these mirror those checks so a user sees every problem at once rather than one per
 *  round trip, which is the same reason `isDeclared` exists. */
export const MAX_STYLES = 60;
export const MIN_WEIGHT = 0.05;
export const MAX_WEIGHT = 4.0;
export const LINE_PATTERNS = ["solid", "dashed", "dotted", "dash_dot", "hidden", "center"] as const;
export const SIDES = ["cut", "projection"] as const;

export type StyleTable = NonNullable<ViewTemplate["object_styles"]>;

/** Every problem the server would refuse this table for, as sentences naming the class and side.
 *
 *  Order is class then side, so two runs over the same table read the same — a list whose order
 *  depends on object-key iteration is a list a user cannot re-find their place in. */
export function styleIssues(styles: StyleTable | undefined): string[] {
  const table = styles ?? {};
  const out: string[] = [];
  const classes = Object.keys(table).sort();
  if (classes.length > MAX_STYLES) {
    out.push(`${classes.length} object-style categories — the server accepts at most ${MAX_STYLES}.`);
  }
  for (const cls of classes) {
    if (!cls.trim()) {
      out.push("An object style with no IFC class name — the server requires one.");
      continue;
    }
    const entry = table[cls] ?? {};
    const sides = SIDES.filter((sd) => entry[sd] != null);
    if (!sides.length) {
      out.push(`${cls} sets neither side — give it a cut or a projection override, or remove it.`);
      continue;
    }
    for (const sd of sides) {
      const o = entry[sd]!;
      const set = (["color", "weight", "pattern", "halftone"] as const)
        .filter((k) => o[k] !== undefined && o[k] !== null);
      if (!set.length) {
        out.push(`${cls}.${sd} sets nothing — the server refuses an empty override rather than `
          + "storing one that does nothing.");
        continue;
      }
      if (o.color != null && !HEX.test(o.color.trim())) {
        out.push(`${cls}.${sd} colour "${o.color}" is not #rrggbb.`);
      }
      if (o.weight != null && !(o.weight >= MIN_WEIGHT && o.weight <= MAX_WEIGHT)) {
        out.push(`${cls}.${sd} weight ${o.weight} is outside ${MIN_WEIGHT}–${MAX_WEIGHT} mm.`);
      }
      if (o.pattern != null && !(LINE_PATTERNS as readonly string[]).includes(o.pattern)) {
        out.push(`${cls}.${sd} pattern "${o.pattern}" is not one of ${LINE_PATTERNS.join(", ")}.`);
      }
    }
  }
  return out;
}

/** Categories whose cut side is not heavier than their projection side.
 *
 *  Not an error — the server stores it and a drafter may mean it — but it is the thing this whole
 *  feature exists to express, so an editor that lets somebody flatten it in silence is the defect
 *  `_norm_override` was written to avoid, arriving through the front door instead. Only ruled on
 *  where BOTH weights are set: a cut override over a default projection is the normal case and the
 *  default is always lighter. */
export function flattenedCategories(styles: StyleTable | undefined): string[] {
  const table = styles ?? {};
  return Object.keys(table).sort().filter((cls) => {
    const c = table[cls]?.cut?.weight;
    const p = table[cls]?.projection?.weight;
    return c != null && p != null && c <= p;
  });
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

    // ── VG-STYLES: the per-category weight table, authorable ────────────────────────────────────
    // The second slice VIEWTPL-DARK named rather than implied. The data path already existed and was
    // already PRESERVED on every round trip — this is a form over a validated field, which is why
    // nothing below touches `saveViewTemplates`.
    const stylesHead = document.createElement("div"); stylesHead.className = "meta";
    stylesHead.style.cssText = "margin-top:14px;font-weight:600";
    stylesHead.textContent = "Object styles — per IFC class, cut vs projection";
    editor.appendChild(stylesHead);
    const stylesIntro = document.createElement("div"); stylesIntro.className = "meta";
    stylesIntro.style.cssText = "opacity:.85;margin-bottom:4px";
    stylesIntro.textContent = `Weights are millimetres ON THE SHEET (${MIN_WEIGHT}–${MAX_WEIGHT}), so `
      + "a wall reads the same at 1:100 and 1:10. Leave a field blank to keep the category default. "
      + "An override is a PARTIAL: setting a colour here does not touch the weight beneath it.";
    editor.appendChild(stylesIntro);

    const table: StyleTable = (t.object_styles ??= {});
    const flat = new Set(flattenedCategories(table));
    for (const cls of Object.keys(table).sort()) {
      const card = document.createElement("div"); card.className = "dash-card";
      card.style.cssText = "margin:6px 0;padding:8px";
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
      const clsName = document.createElement("input"); clsName.className = "portal-filter";
      clsName.value = cls; clsName.placeholder = "IfcWall"; clsName.maxLength = 80;
      clsName.style.cssText = "flex:1 1 150px;font-family:monospace";
      clsName.onchange = () => {
        // Rename by moving the entry: the server keys on the lowercased class name, so a rename is
        // a delete plus an insert and doing it any other way leaves the old key behind.
        const next = clsName.value.trim().toLowerCase();
        const entry = table[cls];
        delete table[cls];
        if (next && entry) table[next] = entry;
        paint();
      };
      const sdel = document.createElement("button"); sdel.className = "selset-del";
      sdel.textContent = "✕"; sdel.title = `Remove the ${cls} object style`;
      sdel.onclick = () => { delete table[cls]; paint(); };
      row.append(clsName, sdel);
      card.appendChild(row);

      for (const sd of SIDES) {
        const side = document.createElement("div");
        side.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:6px";
        const lab = document.createElement("span"); lab.className = "meta";
        lab.style.cssText = "flex:0 0 76px;font-weight:600";
        lab.textContent = sd;
        const on = document.createElement("input"); on.type = "checkbox";
        on.checked = table[cls]?.[sd] != null;
        on.title = `Override the ${sd} side for ${cls}`;
        on.onchange = () => {
          const e = table[cls] ?? (table[cls] = {});
          if (on.checked) e[sd] = { weight: undefined };
          else delete e[sd];
          paint();
        };
        side.append(lab, on);
        const o = table[cls]?.[sd];
        if (o) {
          // The native constraints are a hint, not the guard: `styleIssues` names the class and side
          // of a bad weight before the save, and the server refuses it after. They are set anyway
          // because a spinner that steps in 0.05 mm is how a drafter expects to pick a pen weight.
          const w = document.createElement("input"); w.className = "portal-filter";
          w.type = "number"; w.step = "0.05"; w.min = String(MIN_WEIGHT); w.max = String(MAX_WEIGHT);
          w.value = o.weight == null ? "" : String(o.weight);
          w.placeholder = `weight mm (${MIN_WEIGHT}–${MAX_WEIGHT})`;
          w.style.cssText = "flex:0 0 130px";
          w.oninput = () => {
            const v = w.value.trim();
            // `Number("")` is 0, which is a legal-looking weight the server refuses — so a blank
            // DELETES the key rather than writing a zero.
            if (!v) delete o.weight; else o.weight = Number(v);
            summary.textContent = summarise(t);
          };
          const c = document.createElement("input"); c.className = "portal-filter";
          c.value = o.color ?? ""; c.placeholder = "#rrggbb"; c.maxLength = 7;
          c.style.cssText = "flex:0 0 100px;font-family:monospace";
          c.oninput = () => {
            const v = c.value.trim();
            if (!v) delete o.color; else o.color = v;
          };
          const pat = document.createElement("select"); pat.className = "portal-filter";
          pat.style.cssText = "flex:0 0 110px;font-size:12px";
          for (const pv of ["", ...LINE_PATTERNS]) {
            const op = document.createElement("option");
            op.value = pv; op.textContent = pv || "(default)";
            pat.appendChild(op);
          }
          // `select.value`, never `option.selected` — the happy-dom off-by-one the colour rule's
          // dropdown above records in full.
          pat.value = o.pattern ?? "";
          pat.onchange = () => {
            if (!pat.value) delete o.pattern; else o.pattern = pat.value;
          };
          const ht = document.createElement("label"); ht.className = "meta";
          const htBox = document.createElement("input"); htBox.type = "checkbox";
          htBox.checked = o.halftone === true;
          htBox.onchange = () => {
            // `false` is a stored decision, not an absence — `_norm_override` keeps `halftone`
            // whenever it is not None, so unticking must write `false` rather than delete the key.
            o.halftone = htBox.checked;
          };
          ht.append(htBox, document.createTextNode(" halftone"));
          side.append(w, c, pat, ht);
        }
        card.appendChild(side);
      }
      if (flat.has(cls)) {
        const warn = document.createElement("div"); warn.className = "meta";
        warn.style.cssText = "margin-top:4px;color:var(--status-warn)";
        warn.textContent = "⚠ The cut side is no heavier than the projection side — on a sheet this "
          + "category loses the depth cue entirely. Stored as written; this is a warning, not a "
          + "refusal.";
        card.appendChild(warn);
      }
      editor.appendChild(card);
    }
    const addStyle = document.createElement("button"); addStyle.className = "tool-btn";
    addStyle.textContent = "＋ object style";
    addStyle.onclick = () => {
      if (Object.keys(table).length >= MAX_STYLES) {
        msg.textContent = `The server accepts at most ${MAX_STYLES} object-style categories.`;
        return;
      }
      let name = "ifcwall";
      for (let i = 2; table[name] != null; i++) name = `ifcwall${i}`;
      table[name] = { cut: { weight: 0.5 } };
      paint();
    };
    editor.appendChild(addStyle);
    const styleProblems = styleIssues(table);
    if (styleProblems.length) {
      const bad = document.createElement("div"); bad.className = "meta";
      bad.style.cssText = "margin-top:6px;color:var(--status-crit)";
      bad.textContent = `The server will refuse this save: ${styleProblems.join(" ")}`;
      editor.appendChild(bad);
    }

    // What this editor preserves but does not author, COUNTED on screen. A round trip that silently
    // dropped these would look identical to one that kept them. `styles` left this count when
    // VG-STYLES made the table authorable: a note reading "preserved unchanged" over a field the
    // user just edited is worse than no note at all.
    const carried = carriedThrough(t);
    if (carried.unauthored) {
      const note = document.createElement("div"); note.className = "meta";
      note.style.cssText = "margin-top:8px;opacity:.85";
      note.textContent = `Preserved unchanged by this editor: ${carried.unauthored} rule-level `
        + "weight/pattern/halftone override(s) on the colour rules above. Those are set per "
        + "SELECTOR rather than per class, and authoring them is a separate control.";
      editor.appendChild(note);
    }
  };

  save.onclick = async () => {
    // Every object-style problem, named by class and side, before the round trip — the server
    // refuses the whole save on the FIRST bad entry, so one bad weight on template 3 hides a bad
    // colour on template 1 until the user fixes and resubmits. Same reasoning as `isDeclared`.
    const styleProblems = templates.flatMap((t, i) => styleIssues(t.object_styles)
      .map((p) => `${t.name || `#${i + 1}`}: ${p}`));
    if (styleProblems.length) {
      msg.textContent = `Refused locally: ${styleProblems.join(" ")}`;
      return;
    }
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
