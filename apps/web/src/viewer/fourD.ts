import type { ApiClient } from "../api/client";
import type { LayerManager } from "../tools/layers";

/**
 * FOURD-SIM — a time-phased construction playback over the (already server-computed + tested)
 * `/schedule/4d` timeline. Scrub or auto-play through construction days: every element built up to
 * the current day is shown, everything not yet built is hidden, and the elements *completing on the
 * current day* flash amber — so the model assembles itself as the sequence advances (the Navisworks
 * TimeLiner / SYNCHRO core). Consumes `api.schedule4d`; drives visibility through the `LayerManager`.
 */
type Timeline = Awaited<ReturnType<ApiClient["schedule4d"]>>;

const BUILT_TODAY = "#ff8c1a";   // amber — elements completing on the current day
const LATE = "#e05555";          // FOURD-SIM-2: activity finished after plan (actual > planned)
const EARLY = "#33d17a";         //              activity finished ahead of plan
const PLAY_MS = 650;             // per-frame dwell during auto-play (isolate is the cost, keep it slow)

export interface FourDDeps {
  api: ApiClient;
  pid: string;
  layers: LayerManager;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
}

/** Populate a result-panel `body` with the 4D playback controls. Returns a disposer that stops the
 *  timer and restores full visibility (call it when the panel closes / the tool is re-opened). */
export function populate4dPanel(body: HTMLElement, deps: FourDDeps): () => void {
  const { api, pid, layers, notify } = deps;

  const intro = document.createElement("div"); intro.className = "meta"; intro.style.marginBottom = "6px";
  intro.innerHTML = "Play the construction sequence: elements built up to the day are shown, the rest hidden, "
    + "the day's completions flash <b style='color:#ff8c1a'>amber</b>. Uses the schedule's element↔activity ties "
    + "(hard-tied first, then by trade + floor).";
  body.appendChild(intro);

  const bar = document.createElement("div"); bar.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:4px 0";
  const srcSel = document.createElement("select"); srcSel.className = "portal-filter"; srcSel.style.cssText = "font-size:12px;margin:2px";
  for (const [v, t] of [["", "Auto source"], ["gc", "GC schedule"], ["takt", "Takt plan"]] as const) {
    const o = document.createElement("option"); o.value = v; o.textContent = t; srcSel.appendChild(o);
  }
  const loadBtn = document.createElement("button"); loadBtn.className = "mini-btn on"; loadBtn.textContent = "⤓ Load timeline";
  bar.append(srcSel, loadBtn); body.appendChild(bar);

  const controls = document.createElement("div"); controls.style.cssText = "display:none;flex-direction:column;gap:6px;margin-top:6px";
  const readout = document.createElement("div"); readout.className = "meta";
  const slider = document.createElement("input"); slider.type = "range"; slider.min = "0"; slider.value = "0"; slider.style.width = "100%";
  const btns = document.createElement("div"); btns.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
  const playBtn = document.createElement("button"); playBtn.className = "mini-btn"; playBtn.textContent = "▶ Play";
  const stepB = document.createElement("button"); stepB.className = "mini-btn"; stepB.textContent = "⏭ Step";
  const resetB = document.createElement("button"); resetB.className = "mini-btn"; resetB.textContent = "⤾ Reset";
  const showAllB = document.createElement("button"); showAllB.className = "mini-btn"; showAllB.textContent = "👁 Show all";
  btns.append(playBtn, stepB, resetB, showAllB);
  controls.append(readout, slider, btns); body.appendChild(controls);

  let timeline: Timeline | null = null;
  let cumulative: string[][] = [];   // union of new_guids from frame 0..i
  let idx = 0;
  let timer: number | null = null;

  const stop = () => { if (timer !== null) { clearInterval(timer); timer = null; } playBtn.textContent = "▶ Play"; };

  const seek = async (i: number) => {
    if (!timeline || !timeline.frames.length) return;   // HARDEN-2 (B4): never index an empty timeline
    idx = Math.max(0, Math.min(i, timeline.frames.length - 1));
    slider.value = String(idx);
    const f = timeline.frames[idx]!;
    const total = timeline.element_count || 0;
    readout.innerHTML = `<b>Day ${f.day}</b>${f.date ? ` · ${f.date}` : ""} — ${f.pct}% · `
      + `${f.completed_cumulative}/${total} built · +${f.new} today`
      + (f.late ? ` · <span style="color:${LATE}">${f.late} late</span>` : "")
      + (f.early ? ` · <span style="color:${EARLY}">${f.early} early</span>` : "");
    const built = cumulative[idx] ?? [];
    await layers.resetColors();
    if (built.length) await layers.isolateGuids(built);
    else await layers.showAll();
    if (f.new_guids.length) await layers.colorGuids(f.new_guids, BUILT_TODAY);
    // FOURD-SIM-2: planned-vs-actual tint overrides the amber for slipped / ahead work
    if (f.late_guids?.length) await layers.colorGuids(f.late_guids, LATE);
    if (f.early_guids?.length) await layers.colorGuids(f.early_guids, EARLY);
  };

  const load = async () => {
    stop();
    loadBtn.textContent = "⏳ Loading…"; loadBtn.disabled = true;
    try {
      const src = srcSel.value as "gc" | "takt" | "";
      const tl = await api.schedule4d(pid, src || undefined);
      if (!tl.frames.length) {
        // HARDEN-2 (B4): an empty source must fully reset the player — the old code kept the prior
        // timeline's controls live over frames:[], so slider/step threw on frames[0].
        timeline = null; cumulative = []; idx = 0; controls.style.display = "none";
        notify("no schedule to sequence — import a P6 file or add activities", "error"); return;
      }
      timeline = tl;
      // precompute cumulative built-guid sets (dedup as we go)
      cumulative = [];
      const acc = new Set<string>();
      for (const f of timeline.frames) { for (const g of f.new_guids) acc.add(g); cumulative.push([...acc]); }
      slider.max = String(timeline.frames.length - 1);
      controls.style.display = "flex";
      notify(`4D loaded — ${timeline.frames.length} day-steps · source ${timeline.source}`, "success");
      await seek(0);
    } catch (e) { notify(`4D load failed: ${(e as Error).message}`, "error"); }
    finally { loadBtn.textContent = "⤓ Load timeline"; loadBtn.disabled = false; }
  };

  const play = () => {
    if (!timeline) return;
    if (timer !== null) { stop(); return; }
    playBtn.textContent = "⏸ Pause";
    timer = window.setInterval(() => {
      if (!timeline || idx >= timeline.frames.length - 1) { stop(); return; }
      void seek(idx + 1);
    }, PLAY_MS);
  };

  loadBtn.onclick = () => void load();
  slider.oninput = () => { stop(); void seek(Number(slider.value)); };
  playBtn.onclick = play;
  stepB.onclick = () => { stop(); void seek(idx + 1); };
  resetB.onclick = () => { stop(); void seek(0); };
  showAllB.onclick = () => { stop(); void layers.resetColors().then(() => layers.showAll()); };

  return () => { stop(); void layers.resetColors().then(() => layers.showAll()); };
}
