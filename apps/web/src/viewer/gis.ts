/**
 * GIS / topography import → georeferenced THREE objects for the viewer (reference overlays).
 *
 *  - GeoJSON (vector): points / lines / polygons, draped on the ground plane. Lon/lat is projected
 *    to local metres (equirectangular about the data centroid); already-projected E/N passes through.
 *  - GeoTIFF (raster DEM): a hypsometric terrain mesh, displaced by elevation.
 *
 * Coordinates are centred on the data so the layer renders near the scene origin (float precision);
 * the per-model ⛭ transform + working origin align it to the building. Scene convention is Y-up with
 * North → −Z (matching OriginTool), so map (east, north) → (x = east, z = −north).
 */
import * as THREE from "three";
import earcut from "earcut";
import { fromArrayBuffer } from "geotiff";

export interface GisResult { object: THREE.Object3D; info: string; }

const MAX_TERRAIN_DIM = 256;       // decimate big DEM rasters to this many cells per side
const NODATA_LO = -1e4, NODATA_HI = 1e5;

// --- shared helpers ---------------------------------------------------------
interface Center { x: number; y: number; ll: boolean; }

/** Project a [lon/east, lat/north] pair to centred local metres. */
function project(p: number[], c: Center): [number, number] {
  const px = p[0] ?? 0, py = p[1] ?? 0;   // callers guard 2D-ness; default keeps the projection total
  if (c.ll) {
    const mLon = 111_320 * Math.cos((c.y * Math.PI) / 180), mLat = 110_540;
    return [(px - c.x) * mLon, (py - c.y) * mLat];
  }
  return [px - c.x, py - c.y];
}

/** A blue→green→yellow→brown→white hypsometric ramp for terrain elevation t∈[0,1]. */
function hypso(t: number): [number, number, number] {
  const stops: [number, [number, number, number]][] = [
    [0.0, [0.18, 0.40, 0.55]], [0.25, [0.30, 0.55, 0.35]], [0.5, [0.75, 0.73, 0.40]],
    [0.75, [0.55, 0.42, 0.30]], [1.0, [0.96, 0.96, 0.96]],
  ];
  for (let i = 1; i < stops.length; i++) {
    const cur = stops[i]!, prev = stops[i - 1]!;   // safe: 1 <= i < stops.length
    if (t <= cur[0]) {
      const [t0, a] = prev, [t1, b] = cur;
      const f = (t - t0) / (t1 - t0 || 1);
      return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
    }
  }
  return stops[stops.length - 1]![1];   // safe: stops is a non-empty literal
}

// --- GeoJSON (vector) -------------------------------------------------------
type Pos = number[];
function eachCoord(geom: { type: string; coordinates: unknown }, fn: (p: Pos) => void): void {
  const walk = (a: unknown, depth: number) => {
    if (!Array.isArray(a)) return;
    if (depth === 0) { fn(a as Pos); return; }
    for (const el of a) walk(el, depth - 1);
  };
  const depthByType: Record<string, number> = {
    Point: 0, MultiPoint: 1, LineString: 1, MultiLineString: 2, Polygon: 2, MultiPolygon: 3,
  };
  const d = depthByType[geom.type];
  if (d !== undefined) walk(geom.coordinates, d);
}

function loadGeoJson(text: string, name: string): GisResult {
  let gj: any;  // JSON.parse's natural type — the shape checks below do the narrowing
  try {
    gj = JSON.parse(text);
  } catch {
    throw new Error(`${name}: not valid JSON — expected a GeoJSON FeatureCollection/Feature/geometry`);
  }
  const features: { geometry: { type: string; coordinates: unknown } | null }[] =
    gj.type === "FeatureCollection" ? gj.features
      : gj.type === "Feature" ? [gj]
      : gj.type ? [{ geometry: gj }] : [];
  if (!features.length) throw new Error("not a GeoJSON FeatureCollection/Feature/geometry");

  // pass 1 — bbox + lon/lat detection
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, ll = true;
  const geoms = features.map((f) => f.geometry).filter((g): g is { type: string; coordinates: unknown } => !!g);
  for (const g of geoms) eachCoord(g, (p) => {
    const px = p[0], py = p[1];
    if (px === undefined || py === undefined) return;   // skip malformed coordinate
    minX = Math.min(minX, px); maxX = Math.max(maxX, px);
    minY = Math.min(minY, py); maxY = Math.max(maxY, py);
    if (Math.abs(px) > 180 || Math.abs(py) > 90) ll = false;
  });
  if (!isFinite(minX)) throw new Error("GeoJSON has no coordinates");
  const c: Center = { x: (minX + maxX) / 2, y: (minY + maxY) / 2, ll };
  const sc = (p: Pos): [number, number, number] => { const [x, y] = project(p, c); return [x, 0, -y]; };

  const group = new THREE.Group(); group.name = name;
  const linePts: number[] = [], fillPts: number[] = [], ptPts: number[] = [];
  let nFeat = 0;

  const ring2d = (ring: Pos[]) => { const flat: number[] = []; for (const p of ring) { const [x, y] = project(p, c); flat.push(x, y); } return flat; };
  const addPolygon = (rings: Pos[][]) => {
    const flat: number[] = []; const holes: number[] = [];
    rings.forEach((ring, i) => { if (i > 0) holes.push(flat.length / 2); flat.push(...ring2d(ring)); });
    const tris = earcut(flat, holes, 2);
    for (const idx of tris) {
      const fx = flat[idx * 2], fy = flat[idx * 2 + 1];
      if (fx === undefined || fy === undefined) continue;   // skip out-of-range triangle index
      fillPts.push(fx, 0.02, -fy);                          // lift fill slightly off ground
    }
    for (const ring of rings) for (let i = 0; i < ring.length - 1; i++) {           // outline
      const p0 = ring[i], p1 = ring[i + 1];
      if (!p0 || !p1) continue;                              // skip malformed ring vertex
      const a = sc(p0), b = sc(p1); linePts.push(...a, ...b);
    }
  };

  for (const g of geoms) {
    nFeat++;
    if (g.type === "Point") ptPts.push(...sc(g.coordinates as Pos));
    else if (g.type === "MultiPoint") (g.coordinates as Pos[]).forEach((p) => ptPts.push(...sc(p)));
    else if (g.type === "LineString") { const cs = g.coordinates as Pos[]; for (let i = 0; i < cs.length - 1; i++) { const p0 = cs[i], p1 = cs[i + 1]; if (!p0 || !p1) continue; linePts.push(...sc(p0), ...sc(p1)); } }
    else if (g.type === "MultiLineString") for (const cs of g.coordinates as Pos[][]) for (let i = 0; i < cs.length - 1; i++) { const p0 = cs[i], p1 = cs[i + 1]; if (!p0 || !p1) continue; linePts.push(...sc(p0), ...sc(p1)); }
    else if (g.type === "Polygon") addPolygon(g.coordinates as Pos[][]);
    else if (g.type === "MultiPolygon") for (const poly of g.coordinates as Pos[][][]) addPolygon(poly);
  }

  if (fillPts.length) {
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(fillPts, 3)); geo.computeVertexNormals();
    group.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0x3a6ea5, transparent: true, opacity: 0.45, side: THREE.DoubleSide, roughness: 1 })));
  }
  if (linePts.length) {
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(linePts, 3));
    group.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xffd479 })));
  }
  if (ptPts.length) {
    const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.Float32BufferAttribute(ptPts, 3));
    group.add(new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xe2554a, size: 6, sizeAttenuation: false })));
  }
  if (!group.children.length) throw new Error("GeoJSON had no drawable geometry");
  return { object: group, info: `${nFeat} feature${nFeat === 1 ? "" : "s"}${ll ? " (lon/lat)" : ""}` };
}

// --- GeoTIFF (raster DEM) ---------------------------------------------------
async function loadGeoTiff(buf: ArrayBuffer, name: string): Promise<GisResult> {
  const tiff = await fromArrayBuffer(buf);
  const image = await tiff.getImage();
  const w = image.getWidth(), h = image.getHeight();
  const bbox = image.getBoundingBox();                 // [minX, minY, maxX, maxY] in the tiff CRS
  const rasters = await image.readRasters({ interleave: false });
  const band = rasters[0] as ArrayLike<number>;

  const [bx0, by0, bx1, by1] = bbox;
  if (bx0 === undefined || by0 === undefined || bx1 === undefined || by1 === undefined)
    throw new Error("GeoTIFF has no bounding box");
  let extentX = Math.abs(bx1 - bx0), extentY = Math.abs(by1 - by0);
  // geographic (degrees) vs projected (metres): trust GTModelTypeGeoKey (2=geographic, 1=projected)
  // when present, else fall back to a magnitude heuristic.
  const gkey = (image as unknown as { geoKeys?: { GTModelTypeGeoKey?: number } }).geoKeys?.GTModelTypeGeoKey;
  const ll = gkey === 2 || (gkey !== 1 && Math.abs(bx0) <= 180 && Math.abs(bx1) <= 180
    && Math.abs(by0) <= 90 && Math.abs(by1) <= 90);
  if (ll) { const latc = (by0 + by1) / 2; extentX *= 111_320 * Math.cos((latc * Math.PI) / 180); extentY *= 110_540; }

  const sx = Math.max(1, Math.ceil(w / MAX_TERRAIN_DIM)), sy = Math.max(1, Math.ceil(h / MAX_TERRAIN_DIM));
  const gw = Math.floor(w / sx), gh = Math.floor(h / sy);
  const elev = new Float32Array(gw * gh);
  let minE = Infinity, maxE = -Infinity;
  for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
    let v = Number(band[(j * sy) * w + i * sx]);
    if (!isFinite(v) || v < NODATA_LO || v > NODATA_HI) v = NaN;
    elev[j * gw + i] = v;
    if (!isNaN(v)) { if (v < minE) minE = v; if (v > maxE) maxE = v; }
  }
  if (!isFinite(minE)) throw new Error("DEM has no valid elevation samples");
  const span = Math.max(1, maxE - minE);

  const geo = new THREE.PlaneGeometry(extentX, extentY, gw - 1, gh - 1);
  geo.rotateX(-Math.PI / 2);                            // XY plane → ground (XZ), Y up
  const pos = geo.attributes.position as THREE.BufferAttribute;
  const colors = new Float32Array(pos.count * 3);
  for (let k = 0; k < pos.count; k++) {
    const e = elev[k] ?? NaN;   // out-of-range → NaN → clamps to minE below (matches nodata handling)
    const ee = isNaN(e) ? minE : e;
    pos.setY(k, ee - minE);                             // height relative to the low point
    const [r, g, b] = hypso((ee - minE) / span);
    colors[k * 3] = r; colors[k * 3 + 1] = g; colors[k * 3 + 2] = b;
  }
  pos.needsUpdate = true;
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 0, side: THREE.DoubleSide }));
  mesh.name = name;
  const decim = sx > 1 || sy > 1;
  return { object: mesh, info: `DEM ${gw}×${gh}${decim ? ` (from ${w}×${h})` : ""} · Δz ${(maxE - minE).toFixed(1)}m` };
}

/** Load a GIS file (.geojson/.json vector or .tif/.tiff DEM) into a georeferenced THREE object. */
export async function loadGisFile(file: File): Promise<GisResult> {
  const ext = file.name.toLowerCase().split(".").pop() || "";
  if (ext === "tif" || ext === "tiff") return loadGeoTiff(await file.arrayBuffer(), file.name);
  return loadGeoJson(await file.text(), file.name);    // geojson / json
}

// --- SITE-1: open-geodata site context (OSM buildings/roads/landuse) --------
interface SiteFeature { properties: Record<string, unknown>; geometry: { type: string; coordinates: unknown } }

/**
 * Build the extruded site-context layer from the server's normalized GeoJSON (see /site-context):
 * buildings become height-extruded prisms (tagged height, else levels×3 m, else 6 m), roads become
 * ground-level lines, land-use parcels a translucent fill. Projection is centred on the FETCH
 * anchor (`centerLat/centerLon`) — the same point the model is georeferenced to — so the context
 * lands in the model's frame, not the data centroid's. OSM data is ODbL; show `attribution`.
 */
export function buildSiteContext(gj: { features: SiteFeature[] }, centerLat: number, centerLon: number): GisResult {
  const c: Center = { x: centerLon, y: centerLat, ll: true };
  const group = new THREE.Group(); group.name = "site-context";
  const wallPts: number[] = [], roofPts: number[] = [], roadPts: number[] = [], usePts: number[] = [];
  let nB = 0, nR = 0, nU = 0;

  const prism = (ring: Pos[], h: number) => {
    const flat: number[] = []; const pts: [number, number][] = [];
    for (const p of ring) { const [x, y] = project(p, c); flat.push(x, y); pts.push([x, y]); }
    const tris = earcut(flat, [], 2);
    for (const idx of tris) {
      const fx = flat[idx * 2], fy = flat[idx * 2 + 1];
      if (fx === undefined || fy === undefined) continue;
      roofPts.push(fx, h, -fy);                                  // roof cap at height
    }
    for (let i = 0; i < pts.length - 1; i++) {                   // side walls (two tris per edge)
      const a = pts[i], b = pts[i + 1];
      if (!a || !b) continue;
      wallPts.push(a[0], 0, -a[1], b[0], 0, -b[1], b[0], h, -b[1]);
      wallPts.push(a[0], 0, -a[1], b[0], h, -b[1], a[0], h, -a[1]);
    }
  };

  for (const f of gj.features || []) {
    const kind = f.properties?.kind;
    if (kind === "building" && f.geometry.type === "Polygon") {
      const rings = f.geometry.coordinates as Pos[][];
      const ring = rings[0];
      if (!ring || ring.length < 4) continue;
      const h = Number(f.properties.height) || 6.0;
      prism(ring, h); nB++;
    } else if (kind === "road" && f.geometry.type === "LineString") {
      const cs = f.geometry.coordinates as Pos[];
      for (let i = 0; i < cs.length - 1; i++) {
        const p0 = cs[i], p1 = cs[i + 1];
        if (!p0 || !p1) continue;
        const [x0, y0] = project(p0, c), [x1, y1] = project(p1, c);
        roadPts.push(x0, 0.05, -y0, x1, 0.05, -y1);
      }
      nR++;
    } else if (kind === "landuse" && f.geometry.type === "Polygon") {
      const rings = f.geometry.coordinates as Pos[][];
      const ring = rings[0];
      if (!ring || ring.length < 4) continue;
      const flat: number[] = [];
      for (const p of ring) { const [x, y] = project(p, c); flat.push(x, y); }
      for (const idx of earcut(flat, [], 2)) {
        const fx = flat[idx * 2], fy = flat[idx * 2 + 1];
        if (fx === undefined || fy === undefined) continue;
        usePts.push(fx, 0.01, -fy);
      }
      nU++;
    }
  }

  const mesh = (pts: number[], mat: THREE.Material) => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    geo.computeVertexNormals();
    return new THREE.Mesh(geo, mat);
  };
  if (usePts.length) group.add(mesh(usePts, new THREE.MeshStandardMaterial({
    color: 0x4a6b4f, transparent: true, opacity: 0.30, side: THREE.DoubleSide, roughness: 1 })));
  if (wallPts.length) group.add(mesh(wallPts, new THREE.MeshStandardMaterial({
    color: 0x9aa3ad, transparent: true, opacity: 0.85, side: THREE.DoubleSide, roughness: 0.95 })));
  if (roofPts.length) group.add(mesh(roofPts, new THREE.MeshStandardMaterial({
    color: 0xb8bfc7, transparent: true, opacity: 0.9, side: THREE.DoubleSide, roughness: 1 })));
  if (roadPts.length) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(roadPts, 3));
    group.add(new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0x5c6570 })));
  }
  if (!group.children.length) throw new Error("no site features in range — try a larger radius");
  return { object: group, info: `${nB} buildings · ${nR} roads · ${nU} parcels` };
}

// --- slippy-map basemap (opt-in, self-hosted tiles) -------------------------
export interface BasemapOpts { template: string; lat: number; lon: number; zoom?: number; radius?: number; }

/** Web-Mercator tile coords for a lon/lat at zoom z (fractional). */
function lonLatToTile(lon: number, lat: number, z: number): [number, number] {
  const n = 2 ** z;
  const x = ((lon + 180) / 360) * n;
  const latRad = (lat * Math.PI) / 180;
  const y = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  return [x, y];
}

/**
 * Build a ground-plane basemap from an XYZ raster tile server, georeferenced about (lat,lon).
 * OFF by default and offline-first: nothing loads unless the operator supplies a tile-URL `template`
 * (e.g. their own/self-hosted `https://tiles.internal/{z}/{x}/{y}.png`), honoring CLAUDE.md's
 * "self-hosted tiles" rule. A (2·radius+1)² grid of 256-px tiles is laid as textured planes at the
 * tiles' projected metric positions (Y-up, North → −Z), centred near the scene origin.
 */
export async function loadBasemap(opts: BasemapOpts): Promise<GisResult> {
  const z = Math.max(0, Math.min(22, Math.floor(opts.zoom ?? 17)));
  const radius = Math.max(0, Math.min(6, Math.floor(opts.radius ?? 3)));
  const [cx, cy] = lonLatToTile(opts.lon, opts.lat, z);
  const ctx = Math.floor(cx), cty = Math.floor(cy);
  // ground metres per tile at this latitude/zoom
  const mPerTile = (40_075_016.686 * Math.cos((opts.lat * Math.PI) / 180)) / 2 ** z;
  const group = new THREE.Group(); group.name = `basemap z${z}`;
  const loader = new THREE.TextureLoader(); loader.crossOrigin = "anonymous";
  const url = (x: number, y: number) =>
    opts.template.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
  const load = (u: string) => new Promise<THREE.Texture | null>((res) =>
    loader.load(u, (t) => res(t), undefined, () => res(null)));
  let ok = 0;
  for (let dy = -radius; dy <= radius; dy++) {
    for (let dx = -radius; dx <= radius; dx++) {
      const tx = ctx + dx, ty = cty + dy;
      const tex = await load(url(tx, ty));
      if (!tex) continue;
      ok++;
      tex.colorSpace = THREE.SRGBColorSpace;
      const geo = new THREE.PlaneGeometry(mPerTile, mPerTile);
      geo.rotateX(-Math.PI / 2);                          // lay flat on the ground (XZ)
      const mat = new THREE.MeshBasicMaterial({ map: tex, depthWrite: false });
      const plane = new THREE.Mesh(geo, mat);
      // tile centre offset from the focus tile, in metres; +x = east, +z = south (north → −z)
      plane.position.set((tx - cx + 0.5) * mPerTile, -0.05, (ty - cy + 0.5) * mPerTile);
      group.add(plane);
    }
  }
  if (!ok) throw new Error("no tiles loaded — check the tile URL template / server");
  return { object: group, info: `basemap ${ok} tiles · z${z}` };
}
