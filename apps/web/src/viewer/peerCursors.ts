import * as THREE from "three";

/** COLLAB-CURSORS — per-user 3D presence cursors (the COLLAB-1 remainder).
 *
 *  Every peer whose presence heartbeat carries a camera viewpoint renders as a small colored
 *  view-cone at their camera position, aimed at their look-target, with a floating name tag — so a
 *  team sees *where everyone is looking* live. Pure viewer-side: rides the existing presence roster
 *  (no protocol change; the heartbeat already accepts a viewpoint). Colors are stable per user
 *  (name-hash → hue). Built as its own leaf from day one (REL-4 discipline). */

type Vec3Like = { x: number; y: number; z: number };
type PeerVp = { position: Vec3Like; target: Vec3Like } | null | undefined;
export type PresencePeer = { user: string; viewpoint?: PeerVp };

function colorFor(user: string): THREE.Color {
  let h = 0;
  for (let i = 0; i < user.length; i++) h = (h * 31 + user.charCodeAt(i)) >>> 0;
  return new THREE.Color().setHSL((h % 360) / 360, 0.75, 0.55);
}

function nameSprite(user: string, color: THREE.Color): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = 256; c.height = 64;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(15,23,42,.85)";
  g.roundRect(4, 8, 248, 48, 10); g.fill();
  g.strokeStyle = `#${color.getHexString()}`; g.lineWidth = 3; g.stroke();
  g.fillStyle = "#e2e8f0"; g.font = "bold 26px system-ui, sans-serif";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(user.slice(0, 16), 128, 33);
  const tex = new THREE.CanvasTexture(c);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }));
  sp.scale.set(3.2, 0.8, 1);
  sp.position.y = 1.1;
  return sp;
}

function cursorGroup(user: string): THREE.Group {
  const color = colorFor(user);
  const grp = new THREE.Group();
  grp.name = `peer-cursor-${user}`;
  // a view-cone: apex at the camera position, opening toward the look target
  const cone = new THREE.Mesh(
    new THREE.ConeGeometry(0.45, 1.4, 12, 1, true),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, side: THREE.DoubleSide }));
  cone.rotation.x = -Math.PI / 2;                  // cone axis (+Y) → -Z (three's camera forward)
  cone.position.z = -0.7;                          // apex sits at the group origin (camera position)
  const dot = new THREE.Mesh(new THREE.SphereGeometry(0.14, 10, 10),
                             new THREE.MeshBasicMaterial({ color }));
  grp.add(cone, dot, nameSprite(user, color));
  return grp;
}

export function installPeerCursors(scene: THREE.Scene) {
  const cursors = new Map<string, THREE.Group>();

  /** Reconcile the rendered cursors with the current roster. `self` is never rendered. Returns the
   *  number of visible peer cursors (handy for status text + tests). */
  function sync(peers: PresencePeer[], self?: string | null): number {
    const want = new Map<string, PeerVp>();
    for (const p of peers || []) {
      if (!p.user || p.user === self || !p.viewpoint) continue;
      want.set(p.user, p.viewpoint);
    }
    for (const [user, grp] of cursors) {           // remove departed / viewpoint-less peers
      if (!want.has(user)) { scene.remove(grp); cursors.delete(user); }
    }
    for (const [user, vp] of want) {               // upsert the rest
      let grp = cursors.get(user);
      if (!grp) { grp = cursorGroup(user); cursors.set(user, grp); scene.add(grp); }
      const p = vp!.position, t = vp!.target;
      grp.position.set(p.x, p.y, p.z);
      grp.lookAt(t.x, t.y, t.z);                   // -Z toward the target = the cone opens that way
    }
    return cursors.size;
  }

  function dispose() {
    for (const grp of cursors.values()) scene.remove(grp);
    cursors.clear();
  }

  return { sync, dispose, count: () => cursors.size };
}
