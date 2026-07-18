import * as THREE from "three";
import type { ApiClient } from "../api/client";
import { installPeerCursors } from "./peerCursors";
import { showQrModal } from "../ui/qr";

/** REL-4 leaf — COLLAB-1 live presence + shared viewpoints + the publish-reload banner.
 *
 *  Owns: the 👥 presence / ⤴ share-view / 📱 QR rail buttons, the 20 s presence heartbeat (which
 *  shares this client's live camera viewpoint — what feeds everyone else's peer cursors), the
 *  per-user 3D peer cursors, and the "a collaborator updated the model" reload banner driven by the
 *  model SSE stream. `captureViewpoint`/`jumpToViewpoint` are returned for the rest of the viewer
 *  (env tools, BCF viewpoints, share flows). */

export type Viewpoint = { position: THREE.Vector3Like; target: THREE.Vector3Like;
  projection?: string; fov?: number } | null;
type Peer = { user: string; seconds_ago: number; viewpoint: Viewpoint };

export interface CollabDeps {
  // OBC camera surface is loosely typed upstream; keep the leaf decoupled from OBC types
  viewer: { world: { camera: any; scene: { three: THREE.Scene } } };
  loader: { fragments: { core: { update(force: boolean): Promise<void> } } };
  api: ApiClient;
  container: HTMLElement;
  projectId: () => string | null;
  toolBtn: (glyph: string, title: string, onClick: (b: HTMLButtonElement) => void) => HTMLButtonElement;
  notify: (msg: string, kind: "info" | "success" | "error") => void;
  loadProjectModel: () => Promise<unknown>;
}

export interface CollabHandle {
  captureViewpoint(): NonNullable<Viewpoint>;
  jumpToViewpoint(vp: Viewpoint): void;
  /** Called after (re)loading the model: hide the reload banner + adopt the now-loaded version. */
  resync(): Promise<void>;
}

export function installCollabPresence(d: CollabDeps): CollabHandle {
  const { viewer, loader, api, container, notify } = d;
  let peers: Peer[] = [];
  // the model version this client currently has loaded; the banner raises only when a HIGHER
  // version is published by someone else (loadProjectModel → resync keeps our own publishes quiet)
  let collabKnownVersion = -1;
  let bannerEl: HTMLElement | null = null;

  function captureViewpoint() {
    const p = new THREE.Vector3(), t = new THREE.Vector3();
    viewer.world.camera.controls.getPosition(p); viewer.world.camera.controls.getTarget(t);
    // carry the projection + FOV so a section/elevation (orthographic) view restores faithfully and
    // round-trips through BCF (a viewpoint that only stored position/target lost the actual view).
    const proj = String(viewer.world.camera.projection.current || "Perspective");
    const cam = viewer.world.camera.three as THREE.PerspectiveCamera;
    return { position: { x: p.x, y: p.y, z: p.z }, target: { x: t.x, y: t.y, z: t.z },
             projection: proj, fov: typeof cam.fov === "number" ? cam.fov : undefined };
  }
  function jumpToViewpoint(vp: Viewpoint) {
    if (!vp) return;
    if (vp.projection && String(viewer.world.camera.projection.current) !== vp.projection)
      void viewer.world.camera.projection.set(vp.projection as "Perspective" | "Orthographic");
    void viewer.world.camera.controls.setLookAt(
      vp.position.x, vp.position.y, vp.position.z, vp.target.x, vp.target.y, vp.target.z, true);
  }

  // COLLAB-CURSORS: per-user 3D view-cones + name tags for every peer sharing a viewpoint
  const peerCursors = installPeerCursors(viewer.world.scene.three);
  let selfUser: string | null = null;
  function updatePresence(active: Peer[]) {
    peers = active || [];
    const shown = peerCursors.sync(peers, selfUser);
    if (shown) void loader.fragments.core.update(true);
    presenceBtn.textContent = peers.length ? `👥 ${peers.length}` : "👥";
    presenceBtn.title = peers.length
      ? `Viewing: ${peers.map((p) => p.user).join(", ")} — click to jump to a shared view`
      : "Live presence — no one else viewing";
    presenceBtn.classList.toggle("on", peers.length > 0);
  }
  const presenceBtn = d.toolBtn("👥", "Live presence", () => {
    const shared = peers.find((p) => p.viewpoint);
    if (shared) { jumpToViewpoint(shared.viewpoint); notify(`jumped to ${shared.user}'s shared view`, "info"); }
    else notify(peers.length ? `Viewing: ${peers.map((p) => p.user).join(", ")}` : "no one else viewing this model", "info");
  });
  d.toolBtn("⤴", "Share your current view with everyone", async () => {
    const pid = d.projectId();
    if (!pid) { notify("connect a project to share views", "error"); return; }
    try { const r = await api.presence(pid, captureViewpoint()); updatePresence(r.active); notify("view shared with peers", "success"); }
    catch { notify("could not share view", "error"); }
  });
  d.toolBtn("📱", "Share via QR — open this project on a phone or tablet", () => {
    const pid = d.projectId();
    const base = location.origin + import.meta.env.BASE_URL;
    void showQrModal(pid ? `${base}?project=${pid}` : base, "Share via QR");
  });

  const pid0 = d.projectId();
  if (pid0) {
    const beat = async () => {
      try {
        const r = await api.presence(pid0, captureViewpoint());   // share our view each tick
        selfUser = r.user;
        updatePresence(r.active);
      } catch { /* offline */ }
    };
    void beat();
    window.setInterval(beat, 20000);   // heartbeat keeps presence live while the tab is open

    // COLLAB-1: a reload banner shown when another user publishes a new model version
    const banner = document.createElement("div");
    banner.className = "collab-reload-banner";
    banner.style.cssText = "position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:40;"
      + "display:none;gap:8px;align-items:center;background:var(--panel,#1e293b);color:var(--fg,#e2e8f0);"
      + "border:1px solid var(--border,#334155);border-radius:8px;padding:6px 12px;font-size:12px;"
      + "box-shadow:0 2px 12px rgba(0,0,0,.35)";
    const bMsg = document.createElement("span"); bMsg.textContent = "👥 A collaborator updated the model.";
    const bReload = document.createElement("button"); bReload.className = "tool-btn"; bReload.textContent = "Reload";
    bReload.style.cssText = "font-size:11px;padding:2px 10px";
    bReload.onclick = () => { banner.style.display = "none"; void d.loadProjectModel(); };
    const bDismiss = document.createElement("button"); bDismiss.className = "tool-btn"; bDismiss.textContent = "✕";
    bDismiss.style.cssText = "font-size:11px;padding:2px 6px"; bDismiss.title = "Dismiss";
    bDismiss.onclick = () => { banner.style.display = "none"; };
    banner.append(bMsg, bReload, bDismiss);
    container.appendChild(banner);
    bannerEl = banner;

    // subscribe to the model-edit SSE stream: refresh presence instantly + raise the banner when the
    // published version climbs past what we have loaded (a collaborator's edit, not our own)
    try {
      const es = api.modelStream(pid0, (raw) => {
        const snap = raw as { model?: { version?: number }; editors?: Peer[] };
        if (snap.editors) updatePresence(snap.editors);
        const v = snap.model?.version;
        if (typeof v === "number") {
          if (collabKnownVersion < 0) collabKnownVersion = v;
          else if (v > collabKnownVersion) { collabKnownVersion = v; banner.style.display = "flex"; }
        }
      });
      window.addEventListener("beforeunload", () => es.close());
    } catch { /* EventSource unsupported / offline — presence still polls */ }
  }

  return {
    captureViewpoint,
    jumpToViewpoint,
    async resync() {
      if (bannerEl) bannerEl.style.display = "none";
      const pid = d.projectId();
      if (!pid) return;
      try { collabKnownVersion = (await api.collabSnapshot(pid)).model.version; } catch { /* offline */ }
    },
  };
}
