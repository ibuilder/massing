/**
 * Load a reference/context model into the viewer as a view-only overlay (IFC stays the source of
 * truth). Meshes and common point clouds use three's bundled addon loaders; LAS/LAZ lidar clouds
 * use the local pointcloud reader. Returns a THREE.Object3D ready to add to the scene.
 *
 *   meshes      .obj .stl .ply(faces) .gltf .glb
 *   pointclouds .ply(no faces) .pcd .xyz .las .laz
 */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";
import { PCDLoader } from "three/addons/loaders/PCDLoader.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { XYZLoader } from "three/addons/loaders/XYZLoader.js";
import { readPointCloud, type PointCloud } from "./pointcloud";
import { loadGisFile } from "./gis";
import { loadSplatScene, isSplatPly } from "./splat";

export interface RefResult {
  object: THREE.Object3D;
  kind: "mesh" | "points" | "gis" | "splat";
  info: string;                   // short human note (point/vertex count, decimation)
  dispose?: () => void;           // extra teardown beyond geometry/material disposal (e.g. splat worker)
}

export const REF_EXTENSIONS = ["obj", "stl", "ply", "gltf", "glb", "pcd", "xyz", "las", "laz", "e57",
                               "geojson", "json", "tif", "tiff", "gml", "citygml", "splat", "ksplat"] as const;

function meshFromGeometry(geo: THREE.BufferGeometry, name: string): THREE.Object3D {
  if (!geo.getAttribute("normal")) geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ color: 0x9aa6b2, metalness: 0, roughness: 0.85, side: THREE.DoubleSide });
  const m = new THREE.Mesh(geo, mat); m.name = name; return m;
}

function pointsFromGeometry(geo: THREE.BufferGeometry, name: string): THREE.Object3D {
  const hasColor = !!geo.getAttribute("color");
  // screen-space point size (sizeAttenuation off) so dots stay legible at any model scale
  const mat = new THREE.PointsMaterial({ size: 1.6, sizeAttenuation: false, vertexColors: hasColor, color: hasColor ? 0xffffff : 0x88aabb });
  const p = new THREE.Points(geo, mat); p.name = name; return p;
}

function cloudGeometry(pc: PointCloud): THREE.BufferGeometry {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pc.positions, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(pc.colors, 3));
  return geo;
}

function vertexCount(geo: THREE.BufferGeometry): number {
  return geo.getAttribute("position")?.count ?? 0;
}

function parseGltf(buf: ArrayBuffer): Promise<THREE.Object3D> {
  return new Promise((resolve, reject) =>
    new GLTFLoader().parse(buf, "", (g) => resolve(g.scene), reject));
}

export async function loadReferenceModel(file: File): Promise<RefResult> {
  const name = file.name;
  const ext = name.toLowerCase().split(".").pop() || "";
  const pts = (geo: THREE.BufferGeometry): RefResult =>
    ({ object: pointsFromGeometry(geo, name), kind: "points", info: `${vertexCount(geo).toLocaleString()} pts` });
  const mesh = (geo: THREE.BufferGeometry): RefResult =>
    ({ object: meshFromGeometry(geo, name), kind: "mesh", info: `${vertexCount(geo).toLocaleString()} verts` });

  switch (ext) {
    case "obj": {
      const g = new OBJLoader().parse(await file.text()); g.name = name;
      return { object: g, kind: "mesh", info: "OBJ" };
    }
    case "stl":
      return mesh(new STLLoader().parse(await file.arrayBuffer()));
    case "ply": {
      // A PLY can be a plain mesh/cloud OR a Gaussian-splat capture — tell them apart by the header.
      const header = await file.slice(0, 4096).text();
      if (isSplatPly(header)) return { kind: "splat", ...(await loadSplatScene(file)) };
      const g = new PLYLoader().parse(await file.arrayBuffer());
      return g.index && g.index.count > 0 ? mesh(g) : pts(g);   // faces → mesh, else point cloud
    }
    case "splat": case "ksplat":
      return { kind: "splat", ...(await loadSplatScene(file)) };
    case "gltf": case "glb": {
      const obj = await parseGltf(await file.arrayBuffer()); obj.name = name;
      return { object: obj, kind: "mesh", info: ext.toUpperCase() };
    }
    case "pcd":
      return pts((new PCDLoader().parse(await file.arrayBuffer()) as THREE.Points).geometry as THREE.BufferGeometry);
    case "xyz": {
      // three 0.184's XYZLoader.parse(text) RETURNS the geometry; @types/three still declares the
      // older callback form, so cast to the real runtime signature (verified live).
      const parse = new XYZLoader().parse as unknown as (t: string) => THREE.BufferGeometry;
      return pts(parse(await file.text()));
    }
    case "las": case "laz": {
      const pc = await readPointCloud(new Uint8Array(await file.arrayBuffer()), name);
      const info = `${pc.count.toLocaleString()} pts${pc.decimated ? ` (decimated from ${pc.sourceCount.toLocaleString()})` : ""}`;
      return { object: pointsFromGeometry(cloudGeometry(pc), name), kind: "points", info };
    }
    case "e57": {
      // In-browser E57 (offline). Common Float / ScaledInteger encodings decode here; anything else
      // throws E57Unsupported so the caller can fall back to the server-side pye57 conversion.
      const { readE57 } = await import("./e57");
      const pc = readE57(new Uint8Array(await file.arrayBuffer()));
      const info = `${pc.count.toLocaleString()} pts${pc.decimated ? ` (decimated from ${pc.sourceCount.toLocaleString()})` : ""}`;
      return { object: pointsFromGeometry(cloudGeometry(pc), name), kind: "points", info };
    }
    case "geojson": case "json": case "tif": case "tiff": {
      const g = await loadGisFile(file);                 // GeoJSON vectors or a GeoTIFF DEM terrain
      return { object: g.object, kind: "gis", info: g.info };
    }
    default:
      throw new Error(`unsupported model format ".${ext}"`);
  }
}
