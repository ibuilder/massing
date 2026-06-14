import type { ElementProps } from "../api/client";

/**
 * Spatial + classification tree (guide §6). Built from the properties index (data, not
 * geometry): Storey ▸ IFC class ▸ Element. Clicking a node selects by GUID — the stable
 * key — so the tree survives re-conversion. A full spatial tree (Project ▸ Site ▸ Building
 * ▸ Storey ▸ Space ▸ Element) is a superset once the index carries site/building.
 */
export function buildTree(
  elements: ElementProps[],
  onSelect: (guid: string) => void,
): HTMLElement {
  const byStorey = new Map<string, Map<string, ElementProps[]>>();
  for (const el of elements) {
    const storey = el.storey ?? "(unassigned)";
    const cls = el.ifc_class;
    const classes = byStorey.get(storey) ?? new Map<string, ElementProps[]>();
    const list = classes.get(cls) ?? [];
    list.push(el);
    classes.set(cls, list);
    byStorey.set(storey, classes);
  }

  const root = document.createElement("ul");
  root.className = "tree";

  for (const [storey, classes] of byStorey) {
    root.appendChild(
      node(storey, () => {
        const classList = document.createElement("ul");
        for (const [cls, els] of classes) {
          classList.appendChild(
            node(`${cls} (${els.length})`, () => {
              const elList = document.createElement("ul");
              for (const el of els) {
                const li = document.createElement("li");
                li.textContent = el.name ?? el.guid;
                li.className = "tree-leaf";
                li.onclick = (e) => { e.stopPropagation(); onSelect(el.guid); };
                elList.appendChild(li);
              }
              return elList;
            }),
          );
        }
        return classList;
      }),
    );
  }
  return root;
}

/** A collapsible tree node; `childrenFactory` builds children lazily on first expand. */
function node(label: string, childrenFactory: () => HTMLElement): HTMLLIElement {
  const li = document.createElement("li");
  const header = document.createElement("div");
  header.className = "tree-node";
  header.textContent = "▸ " + label;
  let expanded = false;
  let children: HTMLElement | null = null;
  header.onclick = (e) => {
    e.stopPropagation();
    expanded = !expanded;
    header.textContent = (expanded ? "▾ " : "▸ ") + label;
    if (expanded && !children) {
      children = childrenFactory();
      li.appendChild(children);
    } else if (children) {
      children.style.display = expanded ? "" : "none";
    }
  };
  li.appendChild(header);
  return li;
}
