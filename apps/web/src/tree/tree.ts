import type { ElementProps, SpatialNode } from "../api/client";

/**
 * Model browser (guide §6) — a Revit Project Browser / Bonsai spatial-decomposition style
 * tree built from the properties index (data, not geometry). Clicking a leaf selects by GUID
 * — the stable key — so the tree survives re-conversion.
 *
 * Group-by modes:
 *   • Spatial    — the server's REAL IFC decomposition (Site ▸ Building ▸ Storey ▸ Space ▸ class),
 *                  keyed on each node's GlobalId. Offered — and defaulted to — only when
 *                  `GET /projects/{pid}/spatial-tree` actually returned one; a project whose element
 *                  index predates `index_schema: 2` does not get the option at all.
 *   • Storey     — Storey ▸ IFC class ▸ Element, grouped on the storey's NAME. Kept because it is
 *                  the only mode a v1 index can support, but the name is not an identity: two
 *                  buildings each having a "Level 2" merge into one node here, silently.
 *   • Discipline — Discipline ▸ IFC class ▸ Element (A/S/M/P/E/FP, derived from the class)
 *   • Class      — IFC class ▸ Element
 *   • Type       — Type/family ▸ Element (instances grouped under their type)
 *
 * A search box filters leaves by name / GUID / class / type across every group; matching
 * branches auto-expand so hits are visible without hunting.
 */
export function buildTree(
  elements: ElementProps[],
  onSelect: (guid: string) => void,
  spatial?: SpatialNode | null,
): HTMLElement {
  // R43-VIEWER-CONFORMANCE. `spatial` is the server's real IFC decomposition. It is OPTIONAL and the
  // mode it enables is only offered when it arrived: a project whose element index predates
  // `index_schema: 2` gets a 422, and an empty "By spatial structure" that silently falls back to
  // grouping on the storey NAME would be indistinguishable from the real thing while merging every
  // same-named storey across buildings. Absent tree, absent mode.
  //
  // The shape is CHECKED, not trusted, and that is not defensive habit — the Pages/demo build has a
  // fixture layer (`demo/demoApi.ts`) that degrades an uncaptured GET to `[]` rather than throwing.
  // `[]` is truthy, so a bare `spatial ? …` would hand an array to the walk below, read `.children`
  // off it as `undefined`, and take the whole model browser down in the demo — the one build with no
  // backend to blame. A node is an object with a children array; anything else is "no tree".
  const spatialPaths = spatial && !Array.isArray(spatial) && Array.isArray(spatial.children)
    ? spatialPathIndex(spatial)
    : null;
  const wrap = document.createElement("div");
  wrap.className = "tree-wrap";

  // Toolbar: search + group-by
  const bar = document.createElement("div");
  bar.className = "tree-bar";

  const search = document.createElement("input");
  search.type = "search";
  search.className = "tree-search";
  search.placeholder = "Search elements…";
  search.setAttribute("aria-label", "Search model elements by name, GUID, class or type");

  const groupBy = document.createElement("select");
  groupBy.className = "tree-groupby";
  groupBy.setAttribute("aria-label", "Group the model browser by");
  const modes: [GroupMode, string][] = spatialPaths
    ? [["spatial", "By spatial structure"], ...GROUP_MODES]
    : [...GROUP_MODES];
  for (const [val, label] of modes) {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = label;
    groupBy.appendChild(opt);
  }

  bar.append(search, groupBy);
  wrap.appendChild(bar);

  const treeHost = document.createElement("div");
  treeHost.className = "tree-host";
  wrap.appendChild(treeHost);

  const rebuild = () => {
    const mode = groupBy.value as GroupMode;
    const q = search.value.trim().toLowerCase();
    const filtered = q ? elements.filter((el) => matches(el, q)) : elements;
    treeHost.replaceChildren(
      buildGrouped(filtered, mode, onSelect, q.length > 0, elements.length, spatialPaths));
  };

  groupBy.onchange = rebuild;
  let t: ReturnType<typeof setTimeout> | undefined;
  search.oninput = () => { if (t) clearTimeout(t); t = setTimeout(rebuild, 120); };

  rebuild();
  return wrap;
}

type GroupMode = "spatial" | "storey" | "discipline" | "class" | "type";
const GROUP_MODES: [GroupMode, string][] = [
  ["storey", "By level"],
  ["discipline", "By discipline"],
  ["class", "By IFC class"],
  ["type", "By type / family"],
];

function matches(el: ElementProps, q: string): boolean {
  return (el.name ?? "").toLowerCase().includes(q)
    || el.guid.toLowerCase().includes(q)
    || el.ifc_class.toLowerCase().includes(q)
    || (el.type_name ?? "").toLowerCase().includes(q)
    || disciplineOf(el).toLowerCase().includes(q);
}

/** Prefer the server-computed discipline; fall back to deriving it from the IFC class. */
function disciplineOf(el: ElementProps): string {
  return el.discipline || discipline(el.ifc_class);
}

/**
 * storeyGuid -> the labels of every spatial ancestor below the project, outermost first.
 *
 * Built once per render from the server's tree, so grouping an element is a Map lookup on its
 * `storey_guid` rather than a walk. The project itself is dropped: it is the root of everything and
 * a node every element sits under is a level of indentation that says nothing.
 *
 * **Siblings that share a name are disambiguated here rather than left to collide.** The whole point
 * of grouping on the GUID is that "Level 2" in Tower A and "Level 2" in Tower B are two places; if
 * their parents also share a name the label path would merge them again, and the tree would be
 * exactly as wrong as the string-grouped one it replaces — while looking like it had been fixed. Six
 * characters of GlobalId is enough to separate them and short enough to read.
 */
function spatialPathIndex(root: SpatialNode): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const walk = (node: SpatialNode, prefix: string[]) => {
    const seen = new Map<string, number>();
    for (const child of node.children) {
      seen.set(child.name, (seen.get(child.name) ?? 0) + 1);
    }
    for (const child of node.children) {
      const label = (seen.get(child.name) ?? 0) > 1
        ? `${child.name} · ${child.ref.guid.slice(0, 6)}`
        : child.name;
      const path = [...prefix, label];
      out.set(child.ref.guid, path);
      walk(child, path);
    }
  };
  walk(root, []);
  return out;
}

/** The hierarchy path above each element for a given group mode. */
function pathFor(el: ElementProps, mode: GroupMode, spatialPaths?: Map<string, string[]> | null): string[] {
  const cls = el.ifc_class;
  switch (mode) {
    case "spatial": {
      // No `storey_guid`, or a guid the tree does not contain, means the element is not placed in
      // the spatial structure — a real and common condition (site-level equipment, an element whose
      // containment the authoring tool never wrote). It gets its own bucket rather than being filed
      // under a guessed storey, because "we do not know where this is" is the answer.
      const path = el.storey_guid ? spatialPaths?.get(el.storey_guid) : undefined;
      return path ? [...path, cls] : ["(not placed)", cls];
    }
    case "storey": return [el.storey ?? "(unassigned)", cls];
    case "discipline": return [disciplineOf(el), cls];
    case "class": return [cls];
    case "type": return [el.type_name ?? "(no type)"];
  }
}

function buildGrouped(
  elements: ElementProps[],
  mode: GroupMode,
  onSelect: (guid: string) => void,
  expand: boolean,
  totalCount: number,
  spatialPaths?: Map<string, string[]> | null,
): HTMLElement {
  if (elements.length === 0) {
    const empty = document.createElement("div");
    empty.className = "meta tree-empty";
    empty.textContent = totalCount === 0 ? "No elements in this model." : "No elements match your search.";
    return empty;
  }

  // Build a nested Map tree keyed by the path.
  type Group = Map<string, Group | ElementProps[]>;
  const rootMap: Group = new Map();
  for (const el of elements) {
    const path = pathFor(el, mode, spatialPaths);
    let cursor = rootMap;
    for (let i = 0; i < path.length - 1; i++) {
      const key = path[i] as string;
      let next = cursor.get(key);
      if (!(next instanceof Map)) { next = new Map(); cursor.set(key, next); }
      cursor = next;
    }
    const leafKey = path[path.length - 1] as string;
    let bucket = cursor.get(leafKey);
    if (!Array.isArray(bucket)) { bucket = []; cursor.set(leafKey, bucket); }
    bucket.push(el);
  }

  const root = document.createElement("ul");
  root.className = "tree";
  for (const [key, value] of sortedEntries(rootMap)) {
    root.appendChild(renderGroup(key, value, onSelect, expand));
  }
  return root;
}

function renderGroup(
  label: string,
  value: Map<string, unknown> | ElementProps[],
  onSelect: (guid: string) => void,
  expand: boolean,
): HTMLLIElement {
  if (Array.isArray(value)) {
    // Leaf group: a bucket of elements.
    return node(`${label} (${value.length})`, () => {
      const elList = document.createElement("ul");
      for (const el of value) {
        const li = document.createElement("li");
        li.textContent = el.name ?? el.guid;
        li.title = `${el.ifc_class}${el.type_name ? ` · ${el.type_name}` : ""}`;
        li.className = "tree-leaf";
        li.onclick = (e) => { e.stopPropagation(); onSelect(el.guid); };
        elList.appendChild(li);
      }
      return elList;
    }, expand);
  }
  // Intermediate group: sum descendant elements for the count.
  const count = countLeaves(value);
  return node(`${label} (${count})`, () => {
    const childList = document.createElement("ul");
    for (const [key, child] of sortedEntries(value as Map<string, Map<string, unknown> | ElementProps[]>)) {
      childList.appendChild(renderGroup(key, child, onSelect, expand));
    }
    return childList;
  }, expand);
}

function countLeaves(value: Map<string, unknown> | ElementProps[]): number {
  if (Array.isArray(value)) return value.length;
  let n = 0;
  for (const child of value.values()) n += countLeaves(child as Map<string, unknown> | ElementProps[]);
  return n;
}

/** Sort a group map: "(unassigned)"/"(no type)" sink to the bottom, otherwise alphabetical. */
function sortedEntries<T>(m: Map<string, T>): [string, T][] {
  return [...m.entries()].sort((a, b) => {
    const pa = a[0].startsWith("(") ? 1 : 0;
    const pb = b[0].startsWith("(") ? 1 : 0;
    return pa - pb || a[0].localeCompare(b[0]);
  });
}

/** A collapsible tree node; `childrenFactory` builds children lazily on first expand. */
function node(label: string, childrenFactory: () => HTMLElement, startExpanded = false): HTMLLIElement {
  const li = document.createElement("li");
  const header = document.createElement("div");
  header.className = "tree-node";
  let expanded = false;
  let children: HTMLElement | null = null;
  const paint = () => { header.textContent = (expanded ? "▾ " : "▸ ") + label; };
  const toggle = () => {
    expanded = !expanded;
    paint();
    if (expanded && !children) {
      children = childrenFactory();
      li.appendChild(children);
    } else if (children) {
      children.style.display = expanded ? "" : "none";
    }
  };
  header.onclick = (e) => { e.stopPropagation(); toggle(); };
  paint();
  li.appendChild(header);
  if (startExpanded) toggle();
  return li;
}

// Served IFC-class→discipline vocabulary (from the unified discipline tree, `GET /reference/disciplines`).
// When present it is authoritative and replaces the local regex below — the viewer injects it once so the
// browser and the model share one discipline mapping instead of drifting apart.
let _servedClassDisc: Record<string, string> | null = null;   // ifc class → discipline CODE (e.g. "M")
let _servedCodeName: Record<string, string> | null = null;    // discipline code → name (e.g. "Mechanical")

/** Inject the served discipline vocabulary so `discipline()` stops guessing from a regex. */
export function setDisciplineLookup(classToCode: Record<string, string>, codeToName: Record<string, string>): void {
  _servedClassDisc = classToCode;
  _servedCodeName = codeToName;
}

/**
 * Best-effort discipline bucket from the IFC class. Prefers the served discipline tree (authoritative);
 * otherwise falls back to the standard A/S/M/P/E/FP regex split used by coordination tools. Ambiguous
 * shared elements (slabs, plates) land in a reasonable default.
 */
function discipline(ifcClass: string): string {
  const code = _servedClassDisc?.[ifcClass];
  if (code) return _servedCodeName?.[code] ?? code;
  const c = ifcClass.replace(/^Ifc/, "");
  if (/Duct|AirTerminal|Fan|Boiler|Chiller|Coil|HeatExchanger|HeatRecovery|UnitaryEquipment|CompressedAir|Damper|AirToAir/i.test(c)) return "Mechanical (HVAC)";
  if (/Pipe|SanitaryTerminal|WasteTerminal|Valve|Pump|Tank|Interceptor|StackTerminal|MedicalDevice/i.test(c)) return "Plumbing";
  if (/Cable|LightFixture|Outlet|SwitchingDevice|ElectricAppliance|DistributionBoard|Transformer|JunctionBox|Motor|Generator|ProtectiveDevice|ElectricFlow|Lamp/i.test(c)) return "Electrical";
  if (/FireSuppression|Sprinkler|Alarm/i.test(c)) return "Fire protection";
  if (/Column|Beam|Member|Footing|Pile|ReinforcingBar|ReinforcingMesh|Tendon|StructuralCurve|StructuralSurface|StructuralMember/i.test(c)) return "Structural";
  if (/Wall|Door|Window|Roof|Covering|CurtainWall|Stair|Ramp|Railing|Furnishing|Furniture|Space|Ceiling|Slab|Plate/i.test(c)) return "Architectural";
  if (/Site|Geographic|Bridge|Road|Rail|Alignment|Pavement|Earthworks|Course/i.test(c)) return "Site / infrastructure";
  if (/Distribution|Flow|Energy|System|Port/i.test(c)) return "MEP (general)";
  return "Other";
}
