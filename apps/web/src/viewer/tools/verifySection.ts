import type { ApiClient } from "../../api/client";
import { photoVerdict, photoVerdictSummary } from "../../ui/photoVerdict";

/**
 * R39-DECOMP-VIEWER ⑰ — **field verification**, out of `app.ts`.
 *
 * The three status buttons a person standing at an element presses (installed / verified /
 * deviation) plus the element-attached field photo and the verdict its analysis returns.
 *
 * ## Chosen by measurement, and it was the only one that measured clean
 *
 * `app.ts` is not a class, so REL-4's "grep the `this.` refs first" rule has no `this.` to grep:
 * the whole file is **one 2,445-line function**, `initViewerApp`, and everything inside it is a
 * nested closure over shared state. The equivalent measurement is *how many sibling functions does
 * the candidate close over* — a sibling reference is the thing that turns an extraction into a
 * callback bag. Run over all 54 nested declarations, for the fourteen candidates of 25 lines or
 * more:
 *
 *   | candidate | lines | siblings closed over |
 *   |---|---|---|
 *   | `buildToolsPanel` | 696 | 14 |
 *   | `renderProps` | 167 | 2 |
 *   | `toolDivider` | 161 | 5 |
 *   | `disarmDraft` | 111 | 5 |
 *   | `selectByGuids` | 95 | 6 |
 *   | **`renderVerify`** | **67** | **0** |
 *   | `handleKey` | 80 | 12 |
 *
 * **One candidate in fourteen closes over nothing.** That is the same shape REL-4 recorded for
 * `portal.ts` — *"the two persona homes … are named alike, take the same four arguments, and only
 * one of them is a leaf"* — arrived at from the other direction, in a file with no methods to grep.
 *
 * Its five free variables are all data or a single reporter, and four of the five already travel on
 * the typed `ViewerCtx`: `api`, `connected`, `projectId`, `setStatus`, plus the `propsVerify` DOM
 * node. So the dependency object below is not a bag invented to make the move possible — it is the
 * context that was already there, narrowed to what this one function reads.
 *
 * `photoVerdict` / `photoVerdictSummary` are module imports and travel with the code rather than
 * crossing the seam.
 *
 * ## The ⑭ check
 *
 * ⑯ records that ⑭ looked like a text move and was not: state deliberately scoped outside
 * `buildToolsPanel` stacked a listener per rebuild once it moved inside. Checked here before
 * anything moved — this block **assigns to nothing declared outside itself**, and its only
 * listeners (`onclick`, `onchange`) are on elements it creates fresh on every call, which it
 * already clears with `innerHTML = ""` on entry. A per-call listener on a per-call element cannot
 * accumulate.
 */
export type VerifySectionDeps = {
  api: ApiClient;
  connected: boolean;
  projectId: string | null;
  setStatus: (msg: string) => void;
  /** The panel this section owns and clears on every render. */
  host: HTMLElement;
};

export function makeVerifySection(d: VerifySectionDeps) {
  return async function renderVerify(guid: string) {
    d.host.innerHTML = "";
    if (!d.connected || !d.projectId || !guid) return;
    const setBtn = (label: string, status: string, color: string) => {
      const b = document.createElement("button");
      b.className = "file-btn"; b.textContent = label;
      b.style.cssText = `font-size:11px;padding:2px 8px;border-color:${color}`;
      b.onclick = async () => {
        try {
          await d.api.setVerification(d.projectId!, guid, { status });
          lbl.textContent = ` ${label}`; lbl.style.color = color;
          d.setStatus(`element marked ${status}`);
        } catch (e) { d.setStatus("verify failed: " + (e as Error).message); }
      };
      return b;
    };
    const row = document.createElement("div");
    row.style.cssText = "border-top:1px solid var(--line);padding-top:6px";
    row.innerHTML = `<div style="font-weight:700">Field verification</div>`;
    const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:4px;align-items:center;flex-wrap:wrap;margin-top:3px";
    bar.append(setBtn("Installed", "installed", "#4a8cff"), setBtn("Verified", "verified", "#33d17a"),
               setBtn("Deviation", "deviation", "#e2554a"));
    const lbl = document.createElement("span"); lbl.className = "meta";
    bar.appendChild(lbl);

    // R22-PHOTO-CV — the front door for element-attached photos. The upload endpoint and its whole
    // analysis stack (quality gate, change screening, detection) previously had NO caller in this
    // app: reachable by API, unreachable by a person. `capture="environment"` makes a phone open the
    // rear camera directly rather than the gallery, which is what someone standing at the element
    // wants.
    const photoIn = document.createElement("input");
    photoIn.type = "file"; photoIn.accept = "image/*"; photoIn.hidden = true;
    photoIn.setAttribute("capture", "environment");
    const photoBtn = document.createElement("button");
    photoBtn.className = "file-btn"; photoBtn.textContent = "\u{1F4F7} Photo";
    photoBtn.style.cssText = "font-size:11px;padding:2px 8px";
    photoBtn.title = "Attach a field photo to this element";
    photoBtn.onclick = () => photoIn.click();
    const verdict = document.createElement("div");
    verdict.className = "meta"; verdict.style.cssText = "margin-top:4px;line-height:1.45";
    photoIn.onchange = async () => {
      const f = photoIn.files?.[0]; if (!f) return;
      photoIn.value = "";                       // so re-picking the SAME file fires change again
      verdict.textContent = "uploading…";
      photoBtn.disabled = true;
      try {
        const res = await d.api.uploadVerificationPhoto(d.projectId!, guid, f, f.name || "photo.jpg");
        verdict.textContent = "";
        const lines = photoVerdict(res);
        if (!lines.length) verdict.textContent = "photo attached";
        for (const ln of lines) {
          const el = document.createElement("div");
          // textContent, never innerHTML: these strings carry server-derived text.
          el.textContent = (ln.tone === "warn" ? "⚠ " : ln.tone === "ok" ? "✓ " : "· ") + ln.text;
          if (ln.tone === "warn") el.style.color = "#e2554a";
          verdict.appendChild(el);
        }
        d.setStatus(photoVerdictSummary(res) || "photo attached");
      } catch (e) {
        verdict.textContent = "upload failed: " + (e as Error).message;
        verdict.style.color = "#e2554a";
      } finally { photoBtn.disabled = false; }
    };
    bar.append(photoBtn, photoIn);
    row.appendChild(bar); row.appendChild(verdict); d.host.appendChild(row);
  };
}
