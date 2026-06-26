/**
 * "Share via QR" — render a scannable QR of a deep link (project + viewpoint) so a phone/tablet can
 * jump straight to the same view. Pure-client (qrcode lib), works offline. Reuses the shared modal.
 */
import QRCode from "qrcode";

import { toast } from "./feedback";
import { modalShell } from "./modal";

export async function showQrModal(url: string, title = "Share via QR"): Promise<void> {
  const { card } = modalShell(title, 300);

  const canvas = document.createElement("canvas");
  canvas.style.cssText = "align-self:center;background:#fff;border-radius:8px;padding:8px";
  card.appendChild(canvas);
  try {
    await QRCode.toCanvas(canvas, url, { width: 240, margin: 1 });
  } catch {
    const err = document.createElement("div"); err.className = "meta";
    err.textContent = "Couldn't render the QR code.";
    card.appendChild(err);
  }

  const link = document.createElement("div");
  link.className = "meta";
  link.style.cssText = "word-break:break-all;text-align:center;max-width:260px";
  link.textContent = url;

  const copy = document.createElement("button");
  copy.className = "file-btn"; copy.textContent = "Copy link";
  copy.style.alignSelf = "center";
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(url); toast("link copied", "success"); }
    catch { toast("copy failed — select and copy the link below", "error"); }
  };

  card.append(link, copy);
}
