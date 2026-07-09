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
export type ParamType = "length" | "number" | "text" | "select";

export interface ParamDef {
  key: string;
  label: string;
  type: ParamType;
  default: number | string;
  unit?: string;         // shown after the field ("m", "mm", …)
  min?: number;
  step?: number;
  options?: string[];    // for type "select"
}

export type ParamValues = Record<string, number | string>;

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
  build: (pts: [number, number][], v: ParamValues) => Record<string, unknown>;
}

// AISC W-shapes + US rebar sizes — kept in sync with services/data/.../steel.py.
const W_SHAPES = ["W8x31", "W10x33", "W12x26", "W14x30", "W16x40", "W18x50", "W21x62", "W24x76"];
const REBAR_SIZES = ["#3", "#4", "#5", "#6", "#7", "#8", "#9", "#10", "#11"];

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
    key: "beam", label: "Beam (concrete)", discipline: "Structural", ifcClass: "IfcBeam",
    recipe: "add_beam", points: 2,
    params: [
      { key: "width", label: "Width", type: "length", default: 0.3, unit: "m", min: 0.05, step: 0.05 },
      { key: "depth", label: "Depth", type: "length", default: 0.5, unit: "m", min: 0.05, step: 0.05 },
    ],
    hint: "Click the start and end of the beam.",
    build: (pts, v) => ({ start: pts[0], end: pts[1], width: v.width, depth: v.depth }),
  },
  {
    key: "steel_column", label: "Steel column (W-shape)", discipline: "Structural", ifcClass: "IfcColumn",
    recipe: "add_steel_column", points: 1,
    params: [
      { key: "section", label: "Section", type: "select", default: "W12x26", options: W_SHAPES },
      { key: "height", label: "Height", type: "length", default: 3.6, unit: "m", min: 0.1, step: 0.1 },
    ],
    hint: "Click the column location — a native AISC W-shape.",
    build: (pts, v) => ({ point: pts[0], section: v.section, height: v.height }),
  },
  {
    key: "steel_beam", label: "Steel beam (W-shape)", discipline: "Structural", ifcClass: "IfcBeam",
    recipe: "add_steel_beam", points: 2,
    params: [{ key: "section", label: "Section", type: "select", default: "W16x40", options: W_SHAPES }],
    hint: "Click the start and end — a native AISC W-shape.",
    build: (pts, v) => ({ start: pts[0], end: pts[1], section: v.section }),
  },
  {
    key: "rebar", label: "Rebar (straight)", discipline: "Structural", ifcClass: "IfcReinforcingBar",
    recipe: "add_rebar", points: 2,
    params: [{ key: "size", label: "Bar size", type: "select", default: "#5", options: REBAR_SIZES }],
    hint: "Click the start and end of the bar.",
    build: (pts, v) => ({ start: pts[0], end: pts[1], size: v.size }),
  },
  {
    key: "footing", label: "Pad footing", discipline: "Structural", ifcClass: "IfcFooting",
    recipe: "add_footing", points: 1,
    params: [
      { key: "width", label: "Width", type: "length", default: 1.5, unit: "m", min: 0.2, step: 0.1 },
      { key: "length", label: "Length", type: "length", default: 1.5, unit: "m", min: 0.2, step: 0.1 },
      { key: "thickness", label: "Thickness", type: "length", default: 0.4, unit: "m", min: 0.1, step: 0.05 },
    ],
    hint: "Click the footing location.",
    build: (pts, v) => ({ point: pts[0], width: v.width, length: v.length, thickness: v.thickness }),
  },
  // --- MEP: distribution runs (draw a segment) --------------------------------------------------
  {
    key: "duct", label: "HVAC duct", discipline: "MEP", ifcClass: "IfcDuctSegment",
    recipe: "add_duct", points: 2,
    params: [{ key: "size", label: "Diameter", type: "length", default: 0.3, unit: "m", min: 0.05, step: 0.05 }],
    hint: "Click the duct run start and end (adds ports + HVAC Supply system).",
    build: (pts, v) => ({ start: pts[0], end: pts[1], size: v.size }),
  },
  {
    key: "pipe", label: "Pipe", discipline: "MEP", ifcClass: "IfcPipeSegment",
    recipe: "add_pipe", points: 2,
    params: [{ key: "size", label: "Diameter", type: "length", default: 0.05, unit: "m", min: 0.01, step: 0.01 }],
    hint: "Click the pipe run start and end (adds ports + Domestic Water system).",
    build: (pts, v) => ({ start: pts[0], end: pts[1], size: v.size }),
  },
  {
    key: "cable_tray", label: "Cable tray / conduit", discipline: "MEP", ifcClass: "IfcCableCarrierSegment",
    recipe: "add_cable_tray", points: 2,
    params: [{ key: "size", label: "Width", type: "length", default: 0.3, unit: "m", min: 0.05, step: 0.05 }],
    hint: "Click the tray run start and end (Power system).",
    build: (pts, v) => ({ start: pts[0], end: pts[1], size: v.size }),
  },
  {
    key: "wire", label: "Cable / wire", discipline: "MEP", ifcClass: "IfcCableSegment",
    recipe: "add_wire", points: 2,
    params: [{ key: "size", label: "Diameter", type: "length", default: 0.02, unit: "m", min: 0.005, step: 0.005 }],
    hint: "Click the cable run start and end (Power system).",
    build: (pts, v) => ({ start: pts[0], end: pts[1], size: v.size }),
  },
  // --- MEP: point equipment (click to place) ---------------------------------------------------
  ...mepTerminal("panel", "Electrical panel", "IfcElectricDistributionBoard", null, [0.6, 0.2, 1.0]),
  ...mepTerminal("outlet", "Power outlet", "IfcOutlet", "POWEROUTLET", [0.1, 0.05, 0.1]),
  ...mepTerminal("light", "Light fixture", "IfcLightFixture", null, [0.6, 0.6, 0.1]),
  ...mepTerminal("diffuser", "Air diffuser", "IfcAirTerminal", "DIFFUSER", [0.6, 0.6, 0.2]),
  ...mepTerminal("floor_drain", "Floor drain", "IfcWasteTerminal", "FLOORTRAP", [0.15, 0.15, 0.1]),
  ...mepTerminal("fixture", "Plumbing fixture", "IfcSanitaryTerminal", null, [0.5, 0.5, 0.8]),
  ...mepTerminal("fire_alarm", "Fire alarm", "IfcAlarm", "BELL", [0.15, 0.1, 0.15]),
  ...mepTerminal("smoke_detector", "Smoke detector", "IfcSensor", "SMOKESENSOR", [0.15, 0.15, 0.05]),
  ...mepTerminal("data_outlet", "Data / telecom outlet", "IfcCommunicationsAppliance", null, [0.1, 0.05, 0.1]),
];

/** A 1-point MEP terminal draft element with the IFC class + optional predefined type baked in. */
function mepTerminal(key: string, label: string, ifcClass: string, predefined: string | null,
                     dims: [number, number, number]): [DraftElement] {
  const [w, d, h] = dims;
  return [{
    key: `mep:${key}`, label, discipline: "MEP", ifcClass, recipe: "add_mep_terminal", points: 1,
    params: [], hint: `Click where to place the ${label.toLowerCase()}.`,
    build: (pts) => ({ ifc_class: ifcClass, point: pts[0], width: w, depth: d, height: h,
                       ...(predefined ? { predefined } : {}) }),
  }];
}

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
