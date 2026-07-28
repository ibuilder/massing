/**
 * Photos, files and voice notes pinned to a markup.
 *
 * The bytes are the host's problem, not the viewer's. A construction photo is 3–8 MB; putting a few
 * of those inside an annotation record would make every markup save a multi-megabyte round trip and
 * would blow past the storage quota of any browser-side adapter. So the schema stores a *reference*
 * and this plugin asks the host to upload.
 *
 * Without an `upload` hook it still works, but only for files small enough to inline as a data URL —
 * and it says so rather than silently dropping the big ones.
 */
import { definePlugin } from "../core/plugin";
import { activate } from "../core/a11y";
import { safeMediaUrl, safeNavigableUrl } from "../core/url";
import { makeId } from "../core/store";
import type { AnnotAttachment } from "../core/types";
import type { Viewer } from "../core/viewer";

/** Inline ceiling when no upload hook is configured. Roughly a compressed screenshot. */
const INLINE_LIMIT = 256 * 1024;

export interface AttachmentOptions {
  /**
   * Store the bytes and return a durable URL. Without this, only files under 256 KB can be kept,
   * inlined as data URLs.
   */
  upload?: (file: File, context: { annotId: string; viewer: Viewer }) => Promise<{ url: string; id?: string }>;
  /** Open an attachment. Defaults to a new tab. */
  open?: (attachment: AnnotAttachment) => void;
  accept?: string;
  side?: "left" | "right";
  /** Offer voice capture. Needs a secure context and microphone permission. */
  voice?: boolean;
}

const kindOf = (mime: string): NonNullable<AnnotAttachment["kind"]> =>
  mime.startsWith("image/") ? "photo"
  : mime.startsWith("video/") ? "video"
  : mime.startsWith("audio/") ? "audio"
  : "file";

const readDataUrl = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error ?? new Error("could not read file"));
    r.readAsDataURL(file);
  });

export function attachmentsPlugin(options: AttachmentOptions = {}) {
  return definePlugin({
    id: "attachments",
    order: 75,
    setup(ctx) {
      const attach = async (v: Viewer, annotId: string, files: FileList | File[]): Promise<void> => {
        const annot = v.store.get(annotId);
        if (!annot) return;
        const added: AnnotAttachment[] = [];

        for (const file of Array.from(files)) {
          try {
            let url: string;
            let id = makeId("att");
            if (options.upload) {
              const result = await options.upload(file, { annotId, viewer: v });
              url = result.url;
              if (result.id) id = result.id;
            } else if (file.size <= INLINE_LIMIT) {
              url = await readDataUrl(file);
            } else {
              v.bus.emit("notice", {
                level: "error",
                message: `${file.name} is ${(file.size / 1024 / 1024).toFixed(1)} MB — too large to store without an upload handler.`,
              });
              continue;
            }
            added.push({
              id, url, name: file.name, mime: file.type || "application/octet-stream",
              size: file.size, kind: kindOf(file.type),
            });
          } catch (e) {
            v.bus.emit("notice", { level: "error", message: `${file.name}: ${(e as Error).message}` });
          }
        }

        if (!added.length) return;
        v.store.update(annotId, { attachments: [...(annot.attachments ?? []), ...added] });
        v.bus.emit("notice", {
          level: "success",
          message: `Attached ${added.length} file${added.length === 1 ? "" : "s"}.`,
        });
      };

      ctx.registerAction({
        id: "attachments.add", label: "Attach photo or file", icon: "📎", group: "review",
        enabled: (v) => v.store.selectedIds().length === 1,
        async run(v) {
          const [a] = v.store.selected();
          if (!a) return;
          const files = await pickFiles(options.accept ?? "image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx");
          if (files?.length) await attach(v, a.id, files);
        },
      });

      if (options.voice !== false) {
        ctx.registerAction({
          id: "attachments.voice", label: "Record a voice note", icon: "🎙", group: "review",
          enabled: (v) => v.store.selectedIds().length === 1 && voiceSupported(),
          async run(v) {
            const [a] = v.store.selected();
            if (!a) return;
            try {
              const file = await recordVoiceNote(v);
              if (file) await attach(v, a.id, [file]);
            } catch (e) {
              v.bus.emit("notice", { level: "error", message: `Recording failed: ${(e as Error).message}` });
            }
          },
        });
      }

      ctx.registerPanel({
        id: "attachments", title: "Attachments", side: options.side ?? "right", order: 35,
        mount: (host, v) => mountPanel(host, v, attach, options),
      });

      ctx.viewer.attachments = {
        attach: (annotId, files) => attach(ctx.viewer, annotId, files),
        remove(annotId, attachmentId) {
          const a = ctx.store.get(annotId);
          if (!a?.attachments) return false;
          const next = a.attachments.filter((x) => x.id !== attachmentId);
          if (next.length === a.attachments.length) return false;
          ctx.store.update(annotId, { attachments: next });
          return true;
        },
      };
    },
  });
}

function mountPanel(
  host: HTMLElement,
  v: Viewer,
  attach: (v: Viewer, annotId: string, files: FileList | File[]) => Promise<void>,
  options: AttachmentOptions,
): () => void {
  const body = document.createElement("div");
  body.className = "mpdf-attachments";
  host.appendChild(body);

  const open = options.open ?? ((att: AnnotAttachment) => {
    // Vetted, not trusted: this URL came off a markup record, and records arrive from other people.
    const href = safeNavigableUrl(att.url);
    if (href) window.open(href, "_blank", "noopener,noreferrer");
    else if (att.url) {
      v.bus.emit("notice", {
        level: "warn",
        message: `Refused to open "${att.name}": its link does not use a safe scheme.`,
      });
    }
  });

  const render = () => {
    body.innerHTML = "";
    const selected = v.store.selected();
    if (selected.length !== 1) {
      const p = document.createElement("p");
      p.className = "mpdf-empty";
      p.textContent = "Select a single markup to attach a photo, a document or a voice note to it.";
      body.appendChild(p);
      return;
    }
    const a = selected[0]!;

    const drop = document.createElement("div");
    drop.className = "mpdf-dropzone";
    drop.textContent = "Drop files here, or click to browse";
    activate(drop, async () => {
      const files = await pickFiles(options.accept ?? "image/*,video/*,audio/*");
      if (files?.length) await attach(v, a.id, files);
    });
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("is-over"); };
    drop.ondragleave = () => drop.classList.remove("is-over");
    drop.ondrop = (e) => {
      e.preventDefault();
      drop.classList.remove("is-over");
      if (e.dataTransfer?.files.length) void attach(v, a.id, e.dataTransfer.files);
    };
    body.appendChild(drop);

    const list = document.createElement("div");
    list.className = "mpdf-attach-list";
    for (const att of a.attachments ?? []) {
      const item = document.createElement("div");
      item.className = "mpdf-attach";

      const mediaSrc = safeMediaUrl(att.url);
      if (att.kind === "photo" && mediaSrc) {
        const img = document.createElement("img");
        img.className = "mpdf-attach-thumb";
        img.src = mediaSrc;
        img.alt = att.name;
        item.appendChild(img);
      } else if (att.kind === "audio" && mediaSrc) {
        // A voice note is worth playing in place — opening it in a tab to hear ten seconds of
        // someone describing a wall is not a workflow.
        const audio = document.createElement("audio");
        audio.controls = true;
        audio.preload = "none";
        audio.src = mediaSrc;
        audio.className = "mpdf-attach-audio";
        audio.onclick = (e) => e.stopPropagation();
        item.appendChild(audio);
      } else {
        const glyph = document.createElement("span");
        glyph.className = "mpdf-attach-glyph";
        glyph.textContent = att.kind === "audio" ? "🎙" : att.kind === "video" ? "🎬" : "📄";
        item.appendChild(glyph);
      }

      const main = document.createElement("div");
      main.className = "mpdf-row-main";
      const name = document.createElement("div");
      name.className = "mpdf-row-title";
      name.textContent = att.name;
      const meta = document.createElement("div");
      meta.className = "mpdf-row-meta";
      meta.textContent = [att.kind, att.size ? `${Math.max(1, Math.round(att.size / 1024))} KB` : null]
        .filter(Boolean).join(" · ");
      main.append(name, meta);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "mpdf-icon-btn";
      del.textContent = "✕";
      del.title = "Remove attachment";
      del.onclick = (e) => { e.stopPropagation(); v.attachments?.remove(a.id, att.id); };

      item.append(main, del);
      activate(item, () => open(att), { label: `Open attachment ${att.name}` });
      list.appendChild(item);
    }
    if (!(a.attachments ?? []).length) {
      const p = document.createElement("p");
      p.className = "mpdf-empty";
      p.textContent = "No attachments on this markup.";
      list.appendChild(p);
    }
    body.appendChild(list);
  };

  const offs = [
    v.on("annot:selected", render), v.on("annot:updated", render), v.on("annot:reset", render),
  ];
  render();
  return () => offs.forEach((off) => off());
}

/** `MediaRecorder` and `getUserMedia`, both of which need a secure context. */
export const voiceSupported = (): boolean =>
  typeof MediaRecorder !== "undefined"
  && typeof navigator !== "undefined"
  && Boolean(navigator.mediaDevices?.getUserMedia);

/**
 * Record until the user stops.
 *
 * The stop control is a plain overlay rather than a modal, because the point of a field voice note
 * is that it takes one tap to start and one to finish while you are looking at the wall, not the
 * screen. The microphone track is stopped explicitly on the way out — leaving it live keeps the
 * browser's recording indicator on and is the kind of thing that gets an app uninstalled.
 */
export async function recordVoiceNote(v: Viewer): Promise<File | null> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const chunks: BlobPart[] = [];
  const recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };

  const bar = document.createElement("div");
  bar.className = "mpdf-recording";
  const dot = document.createElement("span");
  dot.className = "mpdf-recording-dot";
  const time = document.createElement("span");
  time.className = "mpdf-recording-time";
  time.textContent = "0:00";
  const stop = document.createElement("button");
  stop.type = "button";
  stop.className = "mpdf-chest-tool";
  stop.textContent = "Stop";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "mpdf-chest-tool";
  cancel.textContent = "Cancel";
  bar.append(dot, time, stop, cancel);
  v.el.root.appendChild(bar);

  const started = Date.now();
  const tick = setInterval(() => {
    const s = Math.floor((Date.now() - started) / 1000);
    time.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }, 500);

  const cleanup = () => {
    clearInterval(tick);
    bar.remove();
    for (const track of stream.getTracks()) track.stop();
  };

  return new Promise<File | null>((resolve) => {
    let cancelled = false;
    recorder.onstop = () => {
      cleanup();
      if (cancelled || !chunks.length) { resolve(null); return; }
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      resolve(new File([blob], `voice-note-${stamp}.webm`, { type: blob.type }));
    };
    stop.onclick = () => recorder.stop();
    cancel.onclick = () => { cancelled = true; recorder.stop(); };
    recorder.start();
  });
}

function pickFiles(accept: string): Promise<FileList | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.accept = accept;
    input.onchange = () => resolve(input.files);
    input.oncancel = () => resolve(null);
    input.click();
  });
}

declare module "../core/viewer" {
  interface Viewer {
    /** Present once the attachments plugin is installed. */
    attachments?: {
      attach(annotId: string, files: FileList | File[]): Promise<void>;
      remove(annotId: string, attachmentId: string): boolean;
    };
  }
}
