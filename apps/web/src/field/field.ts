/**
 * Field capture — a mobile-first quick-capture flow for the jobsite: snap a photo and file it as a
 * punchlist item, safety observation, or progress photo in a couple taps. Works offline — captures
 * (including the photo) queue in localStorage and flush automatically when connectivity returns
 * (and on load). Pairs with the PWA/Capacitor build so it's usable as an installed app in the field.
 */
import type { ApiClient } from "../api/client";
import { toast } from "./../ui/feedback";

const QKEY = "aec-field-queue";

interface QueuedCapture {
  id: string;
  pid: string;
  module: string;
  data: Record<string, unknown>;
  photo?: string;      // dataURL
  filename?: string;
  label?: string;      // human type label, for the queue-review list
}

interface GeoFix { lat: number; lon: number; acc: number; }

/** One-shot GPS fix (best-effort; resolves null if denied/unavailable/slow). */
function getGeo(): Promise<GeoFix | null> {
  return new Promise((res) => {
    if (!navigator.geolocation) return res(null);
    navigator.geolocation.getCurrentPosition(
      (p) => res({ lat: +p.coords.latitude.toFixed(6), lon: +p.coords.longitude.toFixed(6), acc: Math.round(p.coords.accuracy) }),
      () => res(null), { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 });
  });
}

// each capture type → { module, label, extra fields merged into the record data }
const TYPES: Record<string, { module: string; label: string; extra: Record<string, unknown> }> = {
  punch: { module: "punchlist", label: "Punch item", extra: { severity: "Minor" } },
  observation: { module: "observation", label: "Safety observation", extra: { category: "Safety" } },
  photo: { module: "photo", label: "Progress photo", extra: {} },
};

function loadQueue(): QueuedCapture[] {
  try { return JSON.parse(localStorage.getItem(QKEY) || "[]"); } catch { return []; }
}
function saveQueue(q: QueuedCapture[]): void { localStorage.setItem(QKEY, JSON.stringify(q)); }

function dataUrlToFile(dataUrl: string, name: string): File {
  const [meta, b64] = dataUrl.split(",");
  const mime = /:(.*?);/.exec(meta ?? "")?.[1] || "image/jpeg";
  const bin = atob(b64 ?? "");
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new File([u8], name, { type: mime });
}
function fileToDataUrl(f: File): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result));
    r.onerror = rej;
    r.readAsDataURL(f);
  });
}

export class FieldCapture {
  private fab!: HTMLButtonElement;

  constructor(private api: ApiClient, private projectId: () => string | null) {}

  mount(): void {
    this.fab = document.createElement("button");
    this.fab.id = "field-fab";
    this.fab.title = "Field capture";
    this.fab.textContent = "📸";
    this.fab.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:160;width:52px;height:52px;"
      + "border-radius:50%;border:none;background:var(--accent,#4a8cff);color:#fff;font-size:22px;"
      + "box-shadow:0 6px 20px #0007;cursor:pointer;display:flex;align-items:center;justify-content:center";
    this.fab.onclick = () => this.openSheet();
    document.body.appendChild(this.fab);
    this.refreshBadge();
    // flush any queued captures now and whenever connectivity returns
    window.addEventListener("online", () => void this.flush());
    void this.flush();
  }

  private refreshBadge(): void {
    const n = loadQueue().length;
    let b = this.fab.querySelector(".fab-badge") as HTMLElement | null;
    if (!n) { b?.remove(); return; }
    if (!b) {
      b = document.createElement("span"); b.className = "fab-badge";
      b.style.cssText = "position:absolute;top:-4px;right:-4px;background:#e2554a;color:#fff;border-radius:10px;"
        + "min-width:18px;height:18px;font-size:11px;line-height:18px;text-align:center;padding:0 4px";
      this.fab.appendChild(b);
    }
    b.textContent = String(n);
    this.fab.title = `Field capture — ${n} queued offline`;
  }

  private openSheet(): void {
    if (!this.projectId()) { toast("Open or create a project first", "error"); return; }
    document.querySelector(".field-sheet")?.remove();
    const ov = document.createElement("div");
    ov.className = "field-sheet";
    ov.style.cssText = "position:fixed;inset:0;z-index:320;background:#000a;display:flex;align-items:flex-end;justify-content:center";
    const card = document.createElement("div");
    card.style.cssText = "background:var(--panel,#1e1f22);color:var(--text,#e7e7e7);border:1px solid var(--line,#2b2d31);"
      + "border-radius:14px 14px 0 0;padding:18px;width:100%;max-width:520px;display:flex;flex-direction:column;gap:10px;max-height:92vh;overflow:auto";
    card.innerHTML = `<div style="font-weight:650;font-size:16px">📸 Field capture</div>`;

    const typeSel = document.createElement("select"); typeSel.className = "portal-filter";
    for (const [k, t] of Object.entries(TYPES)) typeSel.insertAdjacentHTML("beforeend", `<option value="${k}">${t.label}</option>`);

    const photoIn = document.createElement("input");
    photoIn.type = "file"; photoIn.accept = "image/*"; (photoIn as HTMLInputElement).setAttribute("capture", "environment");
    photoIn.className = "portal-filter";
    const preview = document.createElement("img");
    preview.style.cssText = "max-width:100%;max-height:200px;border-radius:8px;display:none;object-fit:cover";
    photoIn.onchange = () => {
      const f = photoIn.files?.[0];
      if (f) { preview.src = URL.createObjectURL(f); preview.style.display = "block"; }
    };

    const desc = document.createElement("textarea"); desc.className = "portal-filter";
    desc.placeholder = "Description / note"; desc.rows = 3;
    const loc = document.createElement("input"); loc.className = "portal-filter"; loc.placeholder = "Location (e.g. Level 3, Grid C)";

    // GPS geotag — best-effort one-shot fix stored on the record
    let geo: GeoFix | null = null;
    const geoBtn = document.createElement("button"); geoBtn.className = "tool-btn"; geoBtn.type = "button";
    geoBtn.textContent = "📍 Tag GPS location";
    const geoOut = document.createElement("span"); geoOut.className = "meta"; geoOut.style.marginLeft = "8px";
    geoBtn.onclick = async () => {
      geoBtn.disabled = true; geoOut.textContent = "locating…";
      geo = await getGeo();
      geoBtn.disabled = false;
      geoOut.textContent = geo ? `📍 ${geo.lat}, ${geo.lon} (±${geo.acc}m)` : "location unavailable";
    };
    const geoRow = document.createElement("div"); geoRow.style.cssText = "display:flex;align-items:center"; geoRow.append(geoBtn, geoOut);

    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:4px";
    const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel";
    cancel.onclick = () => ov.remove();
    const save = document.createElement("button"); save.className = "file-btn"; save.textContent = "Capture";
    save.onclick = async () => {
      if (!desc.value.trim()) { toast("Add a description", "error"); return; }
      save.disabled = true; save.textContent = "Saving…";
      await this.submit(typeSel.value, desc.value.trim(), loc.value.trim(), photoIn.files?.[0] || null, geo);
      ov.remove();
    };
    row.append(cancel, save);

    const qn = loadQueue().length;
    const review = document.createElement("button"); review.className = "tool-btn"; review.type = "button";
    review.style.cssText = "align-self:flex-start"; review.textContent = `🗂 Review offline queue (${qn})`;
    review.style.display = qn ? "block" : "none";
    review.onclick = () => { ov.remove(); this.openQueue(); };

    card.append(
      label("Type", typeSel), label("Photo", photoIn), preview,
      label("Description", desc), label("Location", loc), geoRow, row, review,
    );
    ov.append(card);
    ov.addEventListener("pointerdown", (e) => { if (e.target === ov) ov.remove(); });
    document.body.appendChild(ov);
    desc.focus();
  }

  private async submit(typeKey: string, description: string, location: string, photo: File | null, geo: GeoFix | null): Promise<void> {
    const pid = this.projectId()!;
    const t = TYPES[typeKey];
    if (!t) return;
    const data: Record<string, unknown> = { subject: description, ...t.extra };
    if (location) data.location = location;
    if (geo) { data.gps_lat = geo.lat; data.gps_lon = geo.lon; data.gps_accuracy_m = geo.acc; }
    const filename = photo ? `field_${Date.now()}.jpg` : undefined;

    if (navigator.onLine) {
      try {
        const rec = await this.api.createModuleRecord(pid, t.module, { data });
        if (photo) await this.api.uploadAttachment(pid, t.module, rec.id, photo);
        toast(`${t.label} captured (${rec.ref})${geo ? " · 📍 geotagged" : ""}`, "success");
        return;
      } catch { /* fall through to offline queue */ }
    }
    // offline (or the request failed) → queue with the photo inlined as a dataURL
    const item: QueuedCapture = { id: crypto.randomUUID(), pid, module: t.module, data, filename, label: t.label };
    if (photo) item.photo = await fileToDataUrl(photo);
    const q = loadQueue(); q.push(item); saveQueue(q);
    this.refreshBadge();
    toast(`${t.label} saved offline — will sync`, "info");
  }

  /** Open the capture sheet programmatically (PWA shortcut / ?capture deep link). */
  open(): void { this.openSheet(); }

  /** Review the offline queue: see pending captures, retry the sync, or discard an item. */
  private openQueue(): void {
    document.querySelector(".field-sheet")?.remove();
    const ov = document.createElement("div"); ov.className = "field-sheet";
    ov.style.cssText = "position:fixed;inset:0;z-index:320;background:#000a;display:flex;align-items:flex-end;justify-content:center";
    const card = document.createElement("div");
    card.style.cssText = "background:var(--panel,#1e1f22);color:var(--text,#e7e7e7);border:1px solid var(--line,#2b2d31);"
      + "border-radius:14px 14px 0 0;padding:18px;width:100%;max-width:520px;display:flex;flex-direction:column;gap:8px;max-height:92vh;overflow:auto";
    const render = () => {
      const q = loadQueue();
      card.innerHTML = `<div style="font-weight:650;font-size:16px">🗂 Offline queue — ${q.length} pending</div>`;
      if (!q.length) card.insertAdjacentHTML("beforeend", `<div class="meta">All caught up — nothing queued.</div>`);
      for (const it of q) {
        const rowEl = document.createElement("div");
        rowEl.style.cssText = "display:flex;align-items:center;gap:8px;border-top:1px solid var(--line,#2b2d31);padding:8px 0";
        const geo = it.data.gps_lat ? ` · 📍 ${it.data.gps_lat},${it.data.gps_lon}` : "";
        rowEl.innerHTML = `<span style="font-size:18px">${it.photo ? "🖼" : "📝"}</span>`
          + `<span style="flex:1;font-size:13px">${(it.label || it.module)} — ${String(it.data.subject || "").slice(0, 60)}${geo}</span>`;
        const del = document.createElement("button"); del.className = "tool-btn"; del.textContent = "✕"; del.title = "Discard";
        del.onclick = () => { saveQueue(loadQueue().filter((x) => x.id !== it.id)); this.refreshBadge(); render(); };
        rowEl.append(del); card.append(rowEl);
      }
      const actions = document.createElement("div"); actions.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:8px";
      const close = document.createElement("button"); close.className = "tool-btn"; close.textContent = "Close"; close.onclick = () => ov.remove();
      const sync = document.createElement("button"); sync.className = "file-btn"; sync.textContent = navigator.onLine ? "Sync now" : "Offline";
      sync.disabled = !navigator.onLine || !q.length;
      sync.onclick = async () => { sync.disabled = true; sync.textContent = "Syncing…"; await this.flush(); render(); };
      actions.append(close, sync); card.append(actions);
    };
    render();
    ov.append(card);
    ov.addEventListener("pointerdown", (e) => { if (e.target === ov) ov.remove(); });
    document.body.appendChild(ov);
  }

  /** Drain the offline queue; keep any items that still fail. */
  async flush(): Promise<void> {
    if (!navigator.onLine) return;
    const q = loadQueue();
    if (!q.length) return;
    const remaining: QueuedCapture[] = [];
    let synced = 0;
    for (const item of q) {
      try {
        const rec = await this.api.createModuleRecord(item.pid, item.module, { data: item.data });
        if (item.photo) await this.api.uploadAttachment(item.pid, item.module, rec.id,
          dataUrlToFile(item.photo, item.filename || "field.jpg"));
        synced++;
      } catch { remaining.push(item); }
    }
    saveQueue(remaining);
    this.refreshBadge();
    if (synced) toast(`Synced ${synced} field capture${synced > 1 ? "s" : ""}`, "success");
  }
}

function label(text: string, control: HTMLElement): HTMLElement {
  const w = document.createElement("label");
  w.style.cssText = "display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted,#9aa0a6)";
  w.append(text); control.style.width = "100%"; w.append(control);
  return w;
}
