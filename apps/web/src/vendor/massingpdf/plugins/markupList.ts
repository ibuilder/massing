/**
 * The markup list — the panel that makes markups feel like data.
 *
 * A list like this is what separates a review tool from an annotator: every markup is a row with
 * author, date, status, discipline and measurement, sortable, filterable and exportable. Faceted
 * filtering is wired to the same predicate the overlay uses, so "hide everything except open
 * structural comments" hides them on the sheet too.
 */
import { definePlugin } from "../core/plugin";
import { activate, refreshRovingTabstops, rovingFocus } from "../core/a11y";
import { facets, isEmptyFilter } from "../core/filter";
import { formatQuantity } from "../core/units";
import { STATUS_COLORS, type Annotation, type AnnotFilter, type AnnotStatus } from "../core/types";
import type { Viewer } from "../core/viewer";

type SortKey = "created" | "page" | "author" | "kind" | "status" | "quantity";

export interface MarkupListOptions {
  /** Which side to dock on. */
  side?: "left" | "right";
  /** Group rows under a heading. */
  groupBy?: "none" | "page" | "status" | "discipline" | "author";
}

export function markupListPlugin(options: MarkupListOptions = {}) {
  return definePlugin({
    id: "markup-list",
    order: 50,
    setup(ctx) {
      ctx.registerPanel({
        id: "markups",
        title: "Markups",
        side: options.side ?? "right",
        order: 30,
        mount: (host, v) => mount(host, v, options),
      });
    },
  });
}

function mount(host: HTMLElement, v: Viewer, options: MarkupListOptions): () => void {
  let sort: SortKey = "created";
  let asc = true;
  let group = options.groupBy ?? "none";

  const search = document.createElement("input");
  search.type = "search";
  search.className = "mpdf-input";
  search.placeholder = "Search markups…";

  const controls = document.createElement("div");
  controls.className = "mpdf-list-controls";
  const sortSel = selectOf<SortKey>(
    [["created", "Newest"], ["page", "Page"], ["author", "Author"], ["kind", "Type"], ["status", "Status"], ["quantity", "Quantity"]],
    (val) => { sort = val; render(); },
  );
  const groupSel = selectOf<NonNullable<MarkupListOptions["groupBy"]>>(
    [["none", "No grouping"], ["page", "By page"], ["status", "By status"], ["discipline", "By discipline"], ["author", "By author"]],
    (val) => { group = val; render(); },
  );
  groupSel.value = group;
  const dirBtn = document.createElement("button");
  dirBtn.type = "button";
  dirBtn.className = "mpdf-icon-btn";
  dirBtn.title = "Reverse order";
  dirBtn.textContent = "↓";
  dirBtn.onclick = () => { asc = !asc; dirBtn.textContent = asc ? "↓" : "↑"; render(); };
  controls.append(sortSel, groupSel, dirBtn);

  const chips = document.createElement("div");
  chips.className = "mpdf-chips";
  const rows = document.createElement("div");
  rows.className = "mpdf-list";
  // A listbox, so a screen reader announces position and count, and arrows move within it — two
  // hundred markups should be one stop in the tab order, not two hundred.
  rows.setAttribute("role", "listbox");
  rows.setAttribute("aria-label", "Markups");
  rows.setAttribute("aria-multiselectable", "true");
  const summary = document.createElement("div");
  summary.className = "mpdf-list-summary";

  host.append(search, controls, chips, summary, rows);

  // --- filtering ------------------------------------------------------------

  const setFilter = (patch: Partial<AnnotFilter>) => {
    v.store.setFilter({ ...v.store.getFilter(), ...patch });
  };

  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  search.oninput = () => {
    clearTimeout(searchTimer);
    // Debounced: each keystroke re-filters and repaints every overlay, which is not free on a set
    // with thousands of markups.
    searchTimer = setTimeout(() => setFilter({ query: search.value.trim() || undefined }), 150);
  };

  const renderChips = () => {
    chips.innerHTML = "";
    const f = v.store.getFilter();
    const all = v.store.all();
    const fa = facets(all);

    const chipGroup = <T extends string | number>(
      label: string,
      entries: [T, number][],
      active: T[] | undefined,
      apply: (next: T[] | undefined) => void,
      color?: (val: T) => string,
    ) => {
      if (entries.length < 2) return;
      const wrap = document.createElement("div");
      wrap.className = "mpdf-chip-group";
      const h = document.createElement("span");
      h.className = "mpdf-chip-label";
      h.textContent = label;
      wrap.appendChild(h);
      for (const [val, n] of entries.slice(0, 8)) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "mpdf-chip";
        const on = active?.includes(val) ?? false;
        if (on) b.classList.add("is-on");
        if (color) b.style.setProperty("--chip-color", color(val));
        b.textContent = `${val} ${n}`;
        b.onclick = () => {
          const cur = active ?? [];
          const next = on ? cur.filter((x) => x !== val) : [...cur, val];
          apply(next.length ? next : undefined);
        };
        wrap.appendChild(b);
      }
      chips.appendChild(wrap);
    };

    chipGroup("Status", fa.status, f.status, (next) => setFilter({ status: next }), (s) => STATUS_COLORS[s as AnnotStatus]);
    chipGroup("Type", fa.kinds, f.kinds, (next) => setFilter({ kinds: next }));
    chipGroup("Discipline", fa.discipline, f.discipline, (next) => setFilter({ discipline: next }));
    chipGroup("Author", fa.authors, f.authors, (next) => setFilter({ authors: next }));

    if (!isEmptyFilter(f)) {
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "mpdf-chip mpdf-chip-clear";
      clear.textContent = "Clear filters";
      clear.onclick = () => { search.value = ""; v.store.setFilter({}); };
      chips.appendChild(clear);
    }
  };

  // --- rows -----------------------------------------------------------------

  const render = () => {
    renderChips();
    const visible = v.store.visible();
    const total = v.store.size;
    summary.textContent = visible.length === total
      ? `${total} markup${total === 1 ? "" : "s"}`
      : `${visible.length} of ${total} markups`;

    const sorted = [...visible].sort((a, b) => cmp(a, b, sort) * (asc ? 1 : -1));
    rows.innerHTML = "";
    if (!sorted.length) {
      const p = document.createElement("p");
      p.className = "mpdf-empty";
      p.textContent = total ? "No markups match the filter." : "No markups yet.";
      rows.appendChild(p);
      return;
    }

    let lastGroup: string | null = null;
    for (const a of sorted) {
      const key = groupKey(a, group);
      if (key !== null && key !== lastGroup) {
        lastGroup = key;
        const h = document.createElement("div");
        h.className = "mpdf-list-group";
        h.textContent = key;
        rows.appendChild(h);
      }
      rows.appendChild(rowFor(a, v));
    }
    // Rebuilding the rows throws away the previous tabindex state; put a single tab stop back.
    refreshRovingTabstops(rows, '[role="option"]');
  };

  const offs = [
    v.on("annot:added", render), v.on("annot:updated", render), v.on("annot:removed", render),
    v.on("annot:reset", render), v.on("annot:selected", render), v.on("filter:changed", render),
  ];
  const stopRoving = rovingFocus(rows, '[role="option"]');
  render();
  return () => { offs.forEach((off) => off()); stopRoving(); clearTimeout(searchTimer); };
}

function rowFor(a: Annotation, v: Viewer): HTMLElement {
  const row = document.createElement("article");
  row.className = "mpdf-row";
  row.dataset.annot = a.id;
  if (v.store.isSelected(a.id)) row.classList.add("is-selected");

  const swatch = document.createElement("span");
  swatch.className = "mpdf-row-swatch";
  swatch.style.background = a.style?.color ?? STATUS_COLORS[a.status];
  swatch.title = a.status;

  const main = document.createElement("div");
  main.className = "mpdf-row-main";

  const title = document.createElement("div");
  title.className = "mpdf-row-title";
  title.textContent = a.subject || a.text || a.note || a.kind;

  const meta = document.createElement("div");
  meta.className = "mpdf-row-meta";
  meta.textContent = [
    `p.${a.page}`,
    a.kind,
    a.discipline,
    a.author,
    shortDate(a.createdAt),
    a.links?.issueId ? "linked" : null,
  ].filter(Boolean).join(" · ");

  main.append(title, meta);
  if (a.note && a.note !== a.subject) {
    const note = document.createElement("div");
    note.className = "mpdf-row-note";
    note.textContent = a.note;
    main.appendChild(note);
  }
  if (a.replies?.length) {
    const r = document.createElement("div");
    r.className = "mpdf-row-replies";
    r.textContent = `${a.replies.length} repl${a.replies.length === 1 ? "y" : "ies"}`;
    main.appendChild(r);
  }

  const qty = document.createElement("div");
  qty.className = "mpdf-row-qty";
  qty.textContent = formatQuantity(a.quantity, { feetInches: v.feetInches });

  row.append(swatch, main, qty);
  activate(row, (e) => {
    v.store.select(a.id, (e as MouseEvent).shiftKey === true);
    void v.goToAnnotation(a, { zoom: false });
  }, {
    role: "option",
    selected: v.store.isSelected(a.id),
    // The swatch carries status as colour alone, which fails on its own; say it instead.
    label: `${a.kind} on page ${a.page}, ${a.status}${a.subject ? `: ${a.subject}` : ""}, by ${a.author}`,
    roving: true,
  });
  row.ondblclick = () => v.bus.emit("annot:activated", { annot: a });
  return row;
}

function cmp(a: Annotation, b: Annotation, key: SortKey): number {
  switch (key) {
    case "page": return a.page - b.page || a.createdAt.localeCompare(b.createdAt);
    case "author": return a.author.localeCompare(b.author);
    case "kind": return a.kind.localeCompare(b.kind);
    case "status": return a.status.localeCompare(b.status);
    case "quantity": return (b.quantity?.value ?? -Infinity) - (a.quantity?.value ?? -Infinity);
    default: return b.createdAt.localeCompare(a.createdAt);
  }
}

function groupKey(a: Annotation, group: MarkupListOptions["groupBy"]): string | null {
  switch (group) {
    case "page": return `Page ${a.page}`;
    case "status": return a.status;
    case "discipline": return a.discipline ?? "unclassified";
    case "author": return a.author;
    default: return null;
  }
}

function selectOf<T extends string>(opts: [T, string][], onChange: (v: T) => void): HTMLSelectElement {
  const s = document.createElement("select");
  s.className = "mpdf-select";
  for (const [value, label] of opts) {
    const o = document.createElement("option");
    o.value = value; o.textContent = label;
    s.appendChild(o);
  }
  s.onchange = () => onChange(s.value as T);
  return s;
}

const shortDate = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
};
