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
  if (c.ll) {
    const mLon = 111_320 * Math.cos((c.y * Math.PI) / 180), mLat = 110_540;
    return [(p[0] - c.x) * mLon, (p[1] - c.y) * mLat];
  }
  return [p[0] - c.x, p[1] - c.y];
}

/** A blue→green→yellow→brown→white hypsometric ramp for terrain elevation t∈[0,1]. */
function hypso(t: number): [number, number, number] {
  const stops: [number, [number, number, number]][] = [
    [0.0, [0.18, 0.40, 0.55]], [0.25, [0.30, 0.55, 0.35]], [0.5, [0.75, 0.73, 0.40]],
    [0.75, [0.55, 0.42, 0.30]], [1.0, [0.96, 0.96, 0.96]],
  ];
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) {
      const [t0, a] = stops[i - 1], [t1, b] = stops[i];
      const f = (t - t0) / (t1 - t0 || 1);
      return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
    }
  }
  return stops[stops.length - 1][1];
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
  const gj = JSON.parse(text);
  const features: { geometry: { type: string; coordinates: unknown } | null }[] =
    gj.type === "FeatureCollection" ? gj.features
      : gj.type === "Feature" ? [gj]
      : gj.type ? [{ geometry: gj }] : [];
  if (!features.length) throw new Error("not a GeoJSON FeatureCollection/Feature/geometry");

  // pass 1 — bbox + lon/lat detection
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, ll = true;
  const geoms = features.map((f) => f.geometry).filter((g): g is { type: string; coordinates: unknown } => !!g);
  for (const g of geoms) eachCoord(g, (p) => {
    minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0]);
    minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]);
    if (Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90) ll = false;
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
    for (const idx of tris) fillPts.push(flat[idx * 2], 0.02, -flat[idx * 2 + 1]);  // lift fill slightly off ground
    for (const ring of rings) for (let i = 0; i < ring.length - 1; i++) {           // outline
      const a = sc(ring[i]), b = sc(ring[i + 1]); linePts.push(...a, ...b);
    }
  };

  for (const g of geoms) {
    nFeat++;
    if (g.type === "Point") ptPts.push(...sc(g.coordinates as Pos));
    else if (g.type === "MultiPoint") (g.coordinates as Pos[]).forEach((p) => ptPts.push(...sc(p)));
    else if (g.type === "LineString") { const cs = g.coordinates as Pos[]; for (let i = 0; i < cs.length - 1; i++) linePts.push(...sc(cs[i]), ...sc(cs[i + 1])); }
    else if (g.type === "MultiLineString") for (const cs of g.coordinates as Pos[][]) for (let i = 0; i < cs.length - 1; i++) linePts.push(...sc(cs[i]), ...sc(cs[i + 1]));
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

  let extentX = Math.abs(bbox[2] - bbox[0]), extentY = Math.abs(bbox[3] - bbox[1]);
  // geographic (degrees) vs projected (metres): trust GTModelTypeGeoKey (2=geographic, 1=projected)
  // when present, else fall back to a magnitude heuristic.
  const gkey = (image as unknown as { geoKeys?: { GTModelTypeGeoKey?: number } }).geoKeys?.GTModelTypeGeoKey;
  const ll = gkey === 2 || (gkey !== 1 && Math.abs(bbox[0]) <= 180 && Math.abs(bbox[2]) <= 180
    && Math.abs(bbox[1]) <= 90 && Math.abs(bbox[3]) <= 90);
  if (ll) { const latc = (bbox[1] + bbox[3]) / 2; extentX *= 111_320 * Math.cos((latc * Math.PI) / 180); extentY *= 110_540; }

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
    const e = elev[k];
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
