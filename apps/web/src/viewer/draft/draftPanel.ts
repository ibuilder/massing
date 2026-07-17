/**
 * Draft panel — the family/element palette + parameter form in the Model workspace's tools rail.
 * Pick a discipline, choose an element or family, set its named parameters, then arm placement;
 * canvas clicks author real IFC server-side (via the `arm` callback → app.ts → the authoring
 * round-trip). Replaces the old prompt()-driven dimension entry. Grid/level snapping and the active
 * work-plane come from app.ts; richer disciplines (structural / MEP / architectural) extend the
 * catalog in draftCatalog.ts.
 */
import {
  DISCIPLINES, DRAFT_ELEMENTS, familyToDraftElement,
  type Discipline, type DraftElement, type FamilyDef, type ParamDef, type ParamValues,
} from "./draftCatalog";

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
  let familiesLoaded = false;

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
  body.appendChild(search);

  const list = el("div"); list.style.cssText = "max-height:220px;overflow:auto;margin-bottom:6px";
  body.appendChild(list);

  const form = el("div"); form.style.marginTop = "4px";   // parameter form + Place button
  body.appendChild(form);

  function allElements(): DraftElement[] { return [...DRAFT_ELEMENTS, ...families]; }

  function renderList() {
    for (const d of DISCIPLINES) chipBtns[d]?.classList.toggle("on", d === discipline);
    const q = search.value.trim().toLowerCase();
    const items = allElements().filter((e) => e.discipline === discipline
      && (!q || e.label.toLowerCase().includes(q) || e.ifcClass.toLowerCase().includes(q)));
    list.innerHTML = "";
    if (!items.length) {
      const n = el("div", "meta"); n.textContent = familiesLoaded ? "No elements for this discipline yet." : "loading families…";
      list.appendChild(n); return;
    }
    for (const item of items) {
      const row = el("button", "tool-btn") as HTMLButtonElement;
      row.style.cssText = "display:flex;justify-content:space-between;align-items:center;width:100%;text-align:left;margin:2px 0";
      row.classList.toggle("on", selected?.key === item.key);
      row.innerHTML = `<span>${item.label}</span>`
        + `<span class="meta" style="font-size:10px">${item.ifcClass.replace("Ifc", "").replace("Type", "")}</span>`;
      row.onclick = () => { selected = item; renderList(); renderForm(); };
      list.appendChild(row);
    }
  }

  function fieldRow(p: ParamDef): { row: HTMLElement; get: () => number | string } {
    const row = el("label", "layer-row"); row.style.cssText = "display:flex;align-items:center;gap:6px;margin:2px 0";
    const name = el("span", "name"); name.textContent = p.label; name.style.flex = "1";
    if (p.type === "select") {
      const sel = el("select", "portal-filter") as HTMLSelectElement; sel.style.width = "110px";
      for (const o of p.options ?? []) { const opt = document.createElement("option"); opt.value = o; opt.textContent = o; sel.appendChild(opt); }
      sel.value = String(p.default); sel.setAttribute("aria-label", p.label);
      row.append(name, sel);
      return { row, get: () => sel.value };
    }
    const inp = el("input", "portal-filter") as HTMLInputElement;
    inp.type = "number"; inp.value = String(p.default); inp.style.width = "80px";
    if (p.min != null) inp.min = String(p.min);
    if (p.step != null) inp.step = String(p.step);
    inp.setAttribute("aria-label", `${p.label}${p.unit ? " (" + p.unit + ")" : ""}`);
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
    for (const p of s.params) { const f = fieldRow(p); form.appendChild(f.row); getters.push(f.get); }

    const btnRow = el("div"); btnRow.style.cssText = "display:flex;gap:6px;margin-top:6px";
    const place = el("button", "tool-btn") as HTMLButtonElement;
    place.textContent = armedKey === s.key ? "◼ Placing… (click model)" : "▶ Place";
    place.classList.toggle("on", armedKey === s.key);
    place.onclick = () => {
      if (armedKey === s.key) { arm(null); return; }
      if (!deps.canAuthor()) { deps.notify("connect a project with a source IFC to draft", "error"); return; }
      const vals: ParamValues = {};
      keys.forEach((k, i) => { const g = getters[i]; if (g) vals[k] = g(); });
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

  // initial paint; families load lazily
  renderList();
  void deps.fetchFamilies().then((fs) => {
    families = fs.map(familyToDraftElement);
    familiesLoaded = true;
    renderList();
  }).catch(() => { familiesLoaded = true; renderList(); });

  return {
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
}
