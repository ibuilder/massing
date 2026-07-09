/**
 * Draft catalog — the parametric element types you can draw in the Model workspace's Draft panel,
 * plus the family catalog fetched from the server (`/families/catalog`). Each entry declares its
 * discipline, IFC class, how many plan points it needs, its named parameters, and how those
 * (points + parameter values) map to an `edit.py` authoring recipe. This is the single source of
 * truth for the Draft palette; disciplines fill out across P4 (structural) / P5 (MEP) / P3 (arch).
 *
 * Plan points are `[E, N]` (East, North) in metres — the convention `authorAndReload` expects
 * (E = world x, N = -world z). The server authors real IFC from the recipe and re-streams fragments.
 */

export type Discipline = "Architectural" | "Structural" | "MEP" | "Site";
export type ParamType = "length" | "number" | "text";

export interface ParamDef {
  key: string;
  label: string;
  type: ParamType;
  default: number | string;
  unit?: string;      // shown after the field ("m", "mm", …)
  min?: number;
  step?: number;
}

export interface DraftElement {
  key: string;
  label: string;
  discipline: Discipline;
  ifcClass: string;       // the IFC entity authored (for the badge + standards)
  recipe: string;         // edit.py recipe key
  points: 1 | 2 | "poly"; // plan points to click (poly = click N, double-click to close)
  params: ParamDef[];
  hint: string;
  /** Build the recipe param object from clicked plan points + the form values. */
  build: (pts: [number, number][], v: Record<string, number>) => Record<string, unknown>;
}

/** The built-in parametric elements (primitives). Families come from the server catalog. */
export const DRAFT_ELEMENTS: DraftElement[] = [
  // --- Architectural ---
  {
    key: "wall", label: "Wall", discipline: "Architectural", ifcClass: "IfcWall",
    recipe: "add_wall", points: 2,
    params: [
      { key: "height", label: "Height", type: "length", default: 3.0, unit: "m", min: 0.1, step: 0.1 },
      { key: "thickness", label: "Thickness", type: "length", default: 0.2, unit: "m", min: 0.05, step: 0.05 },
    ],
    hint: "Click the start and end points along the wall centreline.",
    build: (pts, v) => ({ start: pts[0], end: pts[1], height: v.height, thickness: v.thickness }),
  },
  {
    key: "slab", label: "Slab / floor", discipline: "Architectural", ifcClass: "IfcSlab",
    recipe: "add_slab", points: "poly",
    params: [{ key: "thickness", label: "Thickness", type: "length", default: 0.2, unit: "m", min: 0.05, step: 0.05 }],
    hint: "Click the slab outline corners; double-click to close the polygon.",
    build: (pts, v) => ({ points: pts, thickness: v.thickness }),
  },
  {
    key: "roof", label: "Roof", discipline: "Architectural", ifcClass: "IfcRoof",
    recipe: "add_roof", points: "poly",
    params: [{ key: "thickness", label: "Thickness", type: "length", default: 0.3, unit: "m", min: 0.05, step: 0.05 }],
    hint: "Click the roof outline corners; double-click to close.",
    build: (pts, v) => ({ points: pts, thickness: v.thickness }),
  },
  // --- Structural ---
  {
    key: "column", label: "Column", discipline: "Structural", ifcClass: "IfcColumn",
    recipe: "add_column", points: 1,
    params: [
      { key: "height", label: "Height", type: "length", default: 3.0, unit: "m", min: 0.1, step: 0.1 },
      { key: "width", label: "Width", type: "length", default: 0.4, unit: "m", min: 0.05, step: 0.05 },
      { key: "depth", label: "Depth", type: "length", default: 0.4, unit: "m", min: 0.05, step: 0.05 },
    ],
    hint: "Click the column location.",
    build: (pts, v) => ({ point: pts[0], height: v.height, width: v.width, depth: v.depth }),
  },
  {
    key: "beam", label: "Beam", discipline: "Structural", ifcClass: "IfcBeam",
    recipe: "add_beam", points: 2,
    params: [
      { key: "width", label: "Width", type: "length", default: 0.3, unit: "m", min: 0.05, step: 0.05 },
      { key: "depth", label: "Depth", type: "length", default: 0.5, unit: "m", min: 0.05, step: 0.05 },
    ],
    hint: "Click the start and end of the beam.",
    build: (pts, v) => ({ start: pts[0], end: pts[1], width: v.width, depth: v.depth }),
  },
];

/** A family from the server catalog (`/families/catalog`), rendered as a 1-point draft element. */
export interface FamilyDef {
  key: string;
  label: string;
  ifc_class: string;
  category: string;
  dims: [number, number, number];
}

const DISCIPLINE_BY_CATEGORY: Record<string, Discipline> = {
  Furniture: "Architectural", Sanitary: "MEP", Appliance: "Architectural", Lighting: "MEP",
  MEP: "MEP", Openings: "Architectural", Enclosure: "Architectural", Structural: "Structural",
  Transport: "Architectural", Plant: "Site",
};

/** Map a server family into a placeable DraftElement (1 point, `add_family` recipe with dims). */
export function familyToDraftElement(f: FamilyDef): DraftElement {
  const [w, d, h] = f.dims;
  return {
    key: `family:${f.key}`, label: f.label,
    discipline: DISCIPLINE_BY_CATEGORY[f.category] ?? "Architectural",
    ifcClass: f.ifc_class, recipe: "add_family", points: 1,
    params: [
      { key: "width", label: "Width", type: "length", default: w, unit: "m", min: 0.05, step: 0.05 },
      { key: "depth", label: "Depth", type: "length", default: d, unit: "m", min: 0.05, step: 0.05 },
      { key: "height", label: "Height", type: "length", default: h, unit: "m", min: 0.05, step: 0.05 },
    ],
    hint: `Click where to place the ${f.label.toLowerCase()}.`,
    build: (pts, v) => ({ family: f.key, position: pts[0], dims: [v.width, v.depth, v.height] }),
  };
}

export const DISCIPLINES: Discipline[] = ["Architectural", "Structural", "MEP", "Site"];
