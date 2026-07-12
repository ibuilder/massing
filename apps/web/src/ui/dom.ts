/** Tiny typed DOM helpers (T4). `document.createElement(...)` + a handful of property assignments is
 *  the single most-repeated pattern in the UI code (hundreds of sites); `el()` collapses the common
 *  case into one typed call while staying a thin, dependency-free wrapper over the platform. */

export type ElProps<K extends keyof HTMLElementTagNameMap> =
  Partial<Omit<HTMLElementTagNameMap[K], "style" | "className" | "children" | "dataset">> & {
    /** Sets `className` (aliased to the HTML attribute name for readability). */
    class?: string;
    /** Sets `textContent`. Mutually exclusive with passing children. */
    text?: string;
    /** Inline styles — a CSS string (`"width:100%"`) or a partial style object. */
    style?: string | Partial<CSSStyleDeclaration>;
    /** `data-*` attributes. */
    dataset?: Record<string, string>;
  };

/**
 * Create an element with typed props and children in one call.
 *
 * `el("button", { class: "btn", text: "Save", onclick: fn })`
 * `el("div", { class: "row" }, [icon, el("span", { text: name })])`
 *
 * Unknown props are assigned as element properties (so `onclick`, `value`, `type`, `href`, `disabled`
 * etc. all work and stay type-checked). `null`/`undefined` prop values are skipped.
 */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: ElProps<K> = {},
  children: (Node | string)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null) continue;
    if (k === "class") node.className = v as string;
    else if (k === "text") node.textContent = v as string;
    else if (k === "dataset") Object.assign(node.dataset, v as Record<string, string>);
    else if (k === "style") {
      if (typeof v === "string") node.style.cssText = v;
      else Object.assign(node.style, v);
    } else {
      (node as Record<string, unknown>)[k] = v;
    }
  }
  for (const c of children) node.append(c);
  return node;
}

/** A DocumentFragment holding the given nodes/strings — for batching appends. */
export function frag(...children: (Node | string)[]): DocumentFragment {
  const f = document.createDocumentFragment();
  for (const c of children) f.append(c);
  return f;
}

/** Remove all children of a node (cheaper + clearer than `innerHTML = ""`). */
export function clear(node: Element): void {
  node.replaceChildren();
}

/**
 * Read a form's named controls into a typed plain object, keyed by `name`.
 * `const { title, amount } = readForm<{ title: string; amount: string }>(formEl)`.
 * Checkboxes yield `"on"`/`""`; everything else yields its string value.
 */
export function readForm<T extends Record<string, string>>(form: HTMLFormElement): T {
  const out: Record<string, string> = {};
  for (const c of Array.from(form.elements)) {
    const ctl = c as HTMLInputElement;
    if (!ctl.name) continue;
    out[ctl.name] = ctl.type === "checkbox" ? (ctl.checked ? "on" : "") : (ctl.value ?? "");
  }
  return out as T;
}
