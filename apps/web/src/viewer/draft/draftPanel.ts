/**
 * Draft panel — the family/element palette + parameter form in the Model workspace's tools rail.
 * Pick a discipline, choose an element or family, set its named parameters, then arm placement;
 * canvas clicks author real IFC server-side (via the `arm` callback → app.ts → the authoring
 * round-trip). Replaces the old prompt()-driven dimension entry. Grid/level snapping and the active
 * work-plane come from app.ts; richer disciplines (structural / MEP / architectural) extend the
 * catalog in draftCatalog.ts.
 */
import {
  contentToDraftElement, DISCIPLINES, DRAFT_ELEMENTS, familyToDraftElement,
  type ContentDef, type Discipline, type DraftElement, type FamilyDef, type ParamDef, type ParamValues,
} from "./draftCatalog";
import { draftGlyph, glyphElement, normaliseIfcClass } from "./draftGlyph";
import { previewElement, previewFor } from "./draftPreview";
import { setDraftDragKey } from "../railDrag";

export interface ArmedDraft {
  key: string;
  label: string;
  recipe: string;
  points: 1 | 2 | "poly";
  ifcClass: string;
  hint: string;
  /** Build the recipe params from clicked plan points ([E,N] metres); form values are baked in. */
  build: (planPts: [number, number][]) => Record<string, unknown>;
}

export interface DraftPanelDeps {
  body: HTMLElement;
  fetchFamilies: () => Promise<FamilyDef[]>;
  /** CONTENT-1 items, already flattened to [item, group] pairs — the catalog nests them by bucket. */
  fetchContent: () => Promise<[ContentDef, string][]>;
  arm: (a: ArmedDraft | null) => void;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  canAuthor: () => boolean;
}

export interface DraftPanelHandle {
  /** app.ts calls this when a placement completes / is cancelled, to clear the armed highlight. */
  onArmCleared: () => void;
  /** Keyboard shortcut (KEYS): select + arm a draft element by its catalog key, using default params.
   *  Returns the element label if armed, or null when the key is unknown / authoring isn't available. */
  armByKey: (key: string) => string | null;
}

export function installDraftPanel(deps: DraftPanelDeps): DraftPanelHandle {
  const { body } = deps;
  const el = (t: string, c = "") => { const e = document.createElement(t); if (c) e.className = c; return e; };
  let discipline: Discipline = "Architectural";
  let selected: DraftElement | null = null;
  let armedKey: string | null = null;
  let families: DraftElement[] = [];
  let content: DraftElement[] = [];
  // BOTH catalogs, tracked separately, because they settle independently on purpose (see the
  // fetch pair at the bottom) — and because the empty state makes a DEFINITE claim. Saying
  // "nothing matches" while a third of the catalog is still in flight is a wrong answer, not a
  // slow one: search for a content item before /content/catalog answers and the panel denies it
  // exists. This is the same defect the cross-discipline fix in this change was about, one layer
  // down, and a review bot found it rather than the author.
  let familiesLoaded = false;
  let contentLoaded = false;

  const intro = el("div", "meta");
  intro.textContent = "Pick an element, set its parameters, then Place and click in the model. "
    + "Elements are authored as real IFC on the server and streamed back.";
  intro.style.marginBottom = "6px";
  body.appendChild(intro);

  // discipline chips
  const chips = el("div"); chips.style.cssText = "display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px";
  const chipBtns: Partial<Record<Discipline, HTMLButtonElement>> = {};
  for (const d of DISCIPLINES) {
    const b = el("button", "tool-btn") as HTMLButtonElement;
    b.textContent = d; b.style.padding = "2px 8px"; b.style.fontSize = "11px";
    b.onclick = () => { discipline = d; renderList(); };
    chipBtns[d] = b; chips.appendChild(b);
  }
  body.appendChild(chips);

  // search
  const search = el("input", "portal-filter") as HTMLInputElement;
  search.type = "search"; search.placeholder = "Filter elements…"; search.setAttribute("aria-label", "Filter draft elements");
  search.style.cssText = "width:100%;margin-bottom:6px";
  search.oninput = () => renderList();
  // Type a few letters, press Enter, click in the model. Without this the filter box narrows 90 rows
  // to one and then makes you reach for the mouse anyway — and `armByKey` already exists for the
  // KEYS shortcuts, so the arming path is shared rather than reimplemented here.
  search.onkeydown = (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const first = listed[0];
    if (!first) {
      // Same rule as the empty state: while a catalog is still arriving, "no element matches" is a
      // claim this code cannot make. Report waiting, not absence.
      deps.notify(catalogsSettled() ? "no element matches that filter" : "still loading the catalog…",
                  catalogsSettled() ? "error" : "info");
      return;
    }
    handle.armByKey(first.key);      // handles canAuthor(), the notify and the form/selection state
  };
  body.appendChild(search);

  const list = el("div"); list.style.cssText = "max-height:220px;overflow:auto;margin-bottom:6px";
  body.appendChild(list);

  const form = el("div"); form.style.marginTop = "4px";   // parameter form + Place button
  body.appendChild(form);

  // One list, reached by the row buttons, the search box, the discipline chips AND `armByKey` — which
  // is what the viewport's drop handler calls. Adding content here makes it click- and drag-placeable
  // in the same edit, rather than by two implementations that can disagree.
  function allElements(): DraftElement[] { return [...DRAFT_ELEMENTS, ...families, ...content]; }

  /** True once BOTH server catalogs have settled — resolved or failed. Only then can "nothing
   *  matches" be asserted rather than guessed. A failed fetch counts as settled: the built-ins are
   *  all there will be, so the answer is final even though it is incomplete. */
  function catalogsSettled(): boolean { return familiesLoaded && contentLoaded; }

  /** What `renderList` last drew, in order. Enter in the filter box arms `listed[0]` — it is read
   *  from the render rather than recomputed, so the key press cannot act on a different list from
   *  the one on screen. */
  let listed: DraftElement[] = [];

  function renderList() {
    for (const d of DISCIPLINES) chipBtns[d]?.classList.toggle("on", d === discipline);
    const q = search.value.trim().toLowerCase();
    // A QUERY SPANS EVERY DISCIPLINE; the chips are for browsing. Until this changed, typing "door"
    // while the Structural chip was active answered "No elements for this discipline yet." — a wrong
    // answer rather than a slow one, because there IS a door and the palette said there was not. The
    // discipline of each hit is shown on the row below, so a cross-discipline result is readable.
    const matches = (e: DraftElement) =>
      e.label.toLowerCase().includes(q) || e.ifcClass.toLowerCase().includes(q);
    const items = q ? allElements().filter(matches)
                    : allElements().filter((e) => e.discipline === discipline);
    list.innerHTML = "";
    listed = items;
    if (!items.length) {
      const n = el("div", "meta");
      n.textContent = !catalogsSettled() ? "loading the catalog…"
        : q ? `Nothing matches “${search.value.trim()}” in any discipline.`
            : "No elements for this discipline yet.";
      list.appendChild(n); return;
    }
    for (const item of items) {
      const row = el("button", "tool-btn") as HTMLButtonElement;
      row.style.cssText = "display:flex;gap:6px;align-items:center;width:100%;text-align:left;margin:2px 0";
      row.classList.toggle("on", selected?.key === item.key);
      // UX-3 — glyph, label, class badge. Built as NODES, not as an innerHTML string: `item.label`
      // and `item.ifcClass` come from the server for families and content, and a palette designed to
      // grow with server-supplied content should not be one route-change away from parsing a name as
      // markup. See draftGlyph.ts for why this is a latent hardening rather than a live fix.
      row.appendChild(glyphElement(draftGlyph(item.ifcClass)));
      const name = el("span"); name.textContent = item.label; name.style.flex = "1";
      const badge = el("span", "meta"); badge.style.fontSize = "10px";
      // While searching the list is cross-discipline, so the row has to say which one it came from —
      // otherwise "Column" appearing under the MEP chip reads as a bug in the filter.
      badge.textContent = q && item.discipline !== discipline
        ? `${item.discipline} · ${normaliseIfcClass(item.ifcClass)}`
        : normaliseIfcClass(item.ifcClass);
      row.append(name, badge);
      row.onclick = () => { selected = item; renderList(); renderForm(); };
      // RAIL-DRAG — the same row is also a drag source. Dragging selects it too, so the parameter
      // form below matches what is being dragged: a drag that placed an element while the form showed
      // a different one would make the form a lie about the last thing authored.
      row.draggable = true;
      row.ondragstart = (e) => {
        selected = item; renderList(); renderForm();
        setDraftDragKey(e.dataTransfer, item.key);
      };
      list.appendChild(row);
    }
  }

  function fieldRow(p: ParamDef, onChange: () => void): { row: HTMLElement; get: () => number | string } {
    const row = el("label", "layer-row"); row.style.cssText = "display:flex;align-items:center;gap:6px;margin:2px 0";
    const name = el("span", "name"); name.textContent = p.label; name.style.flex = "1";
    if (p.type === "select") {
      const sel = el("select", "portal-filter") as HTMLSelectElement; sel.style.width = "110px";
      for (const o of p.options ?? []) { const opt = document.createElement("option"); opt.value = o; opt.textContent = o; sel.appendChild(opt); }
      sel.value = String(p.default); sel.setAttribute("aria-label", p.label);
      sel.onchange = onChange;
      row.append(name, sel);
      return { row, get: () => sel.value };
    }
    const inp = el("input", "portal-filter") as HTMLInputElement;
    inp.type = "number"; inp.value = String(p.default); inp.style.width = "80px";
    if (p.min != null) inp.min = String(p.min);
    if (p.step != null) inp.step = String(p.step);
    inp.setAttribute("aria-label", `${p.label}${p.unit ? " (" + p.unit + ")" : ""}`);
    inp.oninput = onChange;
    const unit = el("span", "meta"); unit.textContent = p.unit ?? ""; unit.style.width = "20px";
    row.append(name, inp, unit);
    return { row, get: () => Number(inp.value) || Number(p.default) };
  }

  function renderForm() {
    form.innerHTML = "";
    if (!selected) return;
    const s = selected;
    const head = el("div"); head.style.cssText = "font-weight:600;margin:4px 0 2px";
    head.textContent = s.label;
    form.appendChild(head);
    const badge = el("div", "meta"); badge.style.marginBottom = "4px";
    badge.textContent = `${s.ifcClass} · ${s.hint}`;
    form.appendChild(badge);
    const getters: (() => number | string)[] = [];
    const keys = s.params.map((p) => p.key);
    const readValues = (): ParamValues => {
      const v: ParamValues = {};
      keys.forEach((k, i) => { const g = getters[i]; if (g) v[k] = g(); });
      return v;
    };

    // The preview sits ABOVE the fields and is rebuilt on every keystroke, because its whole job is
    // to answer "is the number I just typed the number I meant". One drawn when the form opens would
    // show the defaults, and the defaults are never the values anyone gets wrong.
    const preview = el("div");
    preview.style.cssText = "display:flex;align-items:center;gap:8px;margin:4px 0";
    const drawPreview = () => {
      preview.replaceChildren();
      const pv = previewFor(s, readValues());
      if (!pv) return;                                    // NO_PREVIEW — see draftPreview.ts
      preview.appendChild(previewElement(pv));
      const cap = el("div", "meta");
      cap.style.lineHeight = "1.35";
      // textContent per node, never innerHTML: the caption carries numbers the user typed, and the
      // palette row next door had exactly that latent hole until it was rebuilt with createElement.
      const dims = el("div"); dims.textContent = pv.caption;
      const scale = el("div"); scale.textContent = `frame ${pv.viewMetres} m`; scale.style.opacity = "0.7";
      cap.append(dims, scale);
      // Two different wrongnesses, two different sentences. A base offset of -2 m is not "larger
      // than this element usually is", and saying so would be a false statement from the one
      // control whose job is to tell the truth about what was typed.
      const warning = pv.oversize ? "larger than this element usually is"
        : pv.belowFrame ? "base is below the frame — the shape is drawn off the bottom"
        : "";
      if (warning) {
        const warn = el("div");
        warn.textContent = warning;
        warn.style.color = "var(--warn,#e0a030)";
        cap.appendChild(warn);
      }
      preview.appendChild(cap);
    };
    form.appendChild(preview);

    for (const p of s.params) { const f = fieldRow(p, drawPreview); form.appendChild(f.row); getters.push(f.get); }
    drawPreview();

    const btnRow = el("div"); btnRow.style.cssText = "display:flex;gap:6px;margin-top:6px";
    const place = el("button", "tool-btn") as HTMLButtonElement;
    place.textContent = armedKey === s.key ? "◼ Placing… (click model)" : "▶ Place";
    place.classList.toggle("on", armedKey === s.key);
    place.onclick = () => {
      if (armedKey === s.key) { arm(null); return; }
      if (!deps.canAuthor()) { deps.notify("connect a project with a source IFC to draft", "error"); return; }
      const vals = readValues();
      const armed: ArmedDraft = {
        key: s.key, label: s.label, recipe: s.recipe, points: s.points, ifcClass: s.ifcClass, hint: s.hint,
        build: (pts) => s.build(pts, vals),
      };
      arm(armed);
    };
    btnRow.appendChild(place);
    form.appendChild(btnRow);
  }

  function arm(a: ArmedDraft | null) {
    armedKey = a?.key ?? null;
    deps.arm(a);
    if (a) deps.notify(`${a.label}: ${a.hint}`, "info");
    renderForm();
  }

  // initial paint; families and content load lazily. Settled independently on purpose: a content
  // catalog that 404s on an older server must not take the families down with it, and vice versa.
  renderList();
  void deps.fetchFamilies().then((fs) => {
    families = fs.map(familyToDraftElement);
    familiesLoaded = true;
    renderList();
  }).catch(() => { familiesLoaded = true; renderList(); });
  void deps.fetchContent().then((cs) => {
    content = cs.map(([c, group]) => contentToDraftElement(c, group));
    contentLoaded = true;
    renderList();
  }).catch(() => { contentLoaded = true; renderList(); });   // unavailable is still SETTLED

  const handle: DraftPanelHandle = {
    onArmCleared() { if (armedKey) { armedKey = null; renderForm(); } },
    armByKey(key: string): string | null {
      const s = allElements().find((e) => e.key === key);
      if (!s) return null;
      discipline = s.discipline;      // switch to its discipline so the list/form reflect the pick
      selected = s;
      renderList();
      renderForm();
      if (!deps.canAuthor()) { deps.notify("connect a project with a source IFC to draft", "error"); return null; }
      const vals: ParamValues = {};
      for (const p of s.params) vals[p.key] = p.default;   // arm straight with defaults (keyboard flow)
      arm({ key: s.key, label: s.label, recipe: s.recipe, points: s.points, ifcClass: s.ifcClass,
            hint: s.hint, build: (pts) => s.build(pts, vals) });
      return s.label;
    },
  };
  return handle;
}
