/**
 * First-run onboarding: a welcome modal with quick-start paths, and a skippable coach-mark tour.
 *
 * Shown once (tracked in localStorage) — new users can skip everything and dive in, or take a
 * ~60-second tour of the workspaces, Open menu, project switcher, tools rail and sign-in. Both
 * the welcome and the tour are relaunchable from the Help (?) menu.
 */
const KEY = "aec-onboarded";

export const onboardingDone = (): boolean => localStorage.getItem(KEY) === "1";
export const markOnboarded = (): void => localStorage.setItem(KEY, "1");
export const resetOnboarding = (): void => localStorage.removeItem(KEY);

export interface OnboardCtx {
  connected: boolean;
  newProject: () => void;        // create a blank project (GC portal + proforma)
  generate: () => void;          // Finance → generate a building from zoning
  openSample: () => void;        // load a sample model in the viewer
}

/** Show the welcome modal on first run only. */
export function maybeWelcome(ctx: OnboardCtx): void {
  if (!onboardingDone()) showWelcome(ctx);
}

function backdrop(): HTMLDivElement {
  const ov = document.createElement("div");
  ov.style.cssText = "position:fixed;inset:0;z-index:300;background:#000b;display:flex;"
    + "align-items:center;justify-content:center;padding:20px";
  return ov;
}

/** The welcome dialog: three quick-start cards + Take the tour / Skip. */
export function showWelcome(ctx: OnboardCtx): void {
  document.querySelector(".ob-welcome")?.remove();
  const ov = backdrop(); ov.className = "ob-welcome";
  const card = document.createElement("div");
  card.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:14px;"
    + "padding:26px;max-width:680px;width:100%;display:flex;flex-direction:column;gap:6px;box-shadow:0 18px 60px #000a";
  card.innerHTML =
    `<div style="font-size:22px;font-weight:650;letter-spacing:-.01em">Welcome to Massing 👋</div>`
    + `<div class="meta" style="margin-bottom:14px">A BIM viewer, a general-contracting portal, and a development`
    + ` proforma — one model, acquisition to turnover. Pick a starting point:</div>`;

  const grid = document.createElement("div");
  grid.style.cssText = "display:grid;grid-template-columns:repeat(3,1fr);gap:12px";
  const tile = (icon: string, title: string, desc: string, onClick: () => void, enabled = true) => {
    const b = document.createElement("button");
    b.type = "button";
    b.style.cssText = "text-align:left;background:var(--panel2,#25272b);border:1px solid var(--line);"
      + "border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:6px;cursor:pointer;"
      + "transition:border-color .12s,transform .12s;color:var(--text);min-height:128px";
    b.innerHTML = `<div style="font-size:22px">${icon}</div>`
      + `<div style="font-weight:600;font-size:14px">${title}</div>`
      + `<div class="meta" style="font-size:12.5px">${desc}</div>`;
    if (!enabled) { b.style.opacity = "0.5"; b.style.cursor = "not-allowed"; b.disabled = true; }
    else {
      b.onmouseenter = () => { b.style.borderColor = "var(--accent)"; b.style.transform = "translateY(-2px)"; };
      b.onmouseleave = () => { b.style.borderColor = "var(--line)"; b.style.transform = "none"; };
      b.onclick = () => { markOnboarded(); ov.remove(); onClick(); };
    }
    return b;
  };
  grid.append(
    tile("🧊", "Explore a sample model", "Load a real building and try the viewer, tree, sections & measure.", ctx.openSample),
    tile("🏗️", "Generate from zoning", "Turn a lot + FAR into a building model and an acquisition proforma.", ctx.generate, ctx.connected),
    tile("📋", "Start a project", "RFIs, costs, schedule, dashboards — works with no model loaded.", ctx.newProject, ctx.connected),
  );
  card.append(grid);

  if (!ctx.connected) {
    const note = document.createElement("div");
    note.className = "meta";
    note.style.cssText = "margin-top:10px;font-size:12px";
    note.textContent = "Backend not connected — the sample model works offline; connect the API to create projects.";
    card.append(note);
  }

  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;gap:10px;justify-content:flex-end;align-items:center;margin-top:18px";
  const guides = document.createElement("a");
  guides.href = "https://massing.build/guide.html"; guides.target = "_blank"; guides.rel = "noopener";
  guides.className = "tool-btn"; guides.textContent = "📚 Guides"; guides.style.cssText = "text-decoration:none;margin-right:auto";
  guides.title = "Open the step-by-step guides & glossary in a new tab";
  const skip = document.createElement("button");
  skip.className = "tool-btn"; skip.textContent = "Skip for now";
  skip.onclick = () => { markOnboarded(); ov.remove(); };
  const tour = document.createElement("button");
  tour.className = "file-btn"; tour.textContent = "Take a 60-second tour";
  tour.onclick = () => { ov.remove(); startTour(); };
  foot.append(guides, skip, tour);
  card.append(foot);

  ov.append(card);
  ov.addEventListener("pointerdown", (e) => { if (e.target === ov) { markOnboarded(); ov.remove(); } });
  document.body.appendChild(ov);
}

// --- coach-mark tour ---------------------------------------------------------
interface Step { sel: string; title: string; body: string; }

const STEPS: Step[] = [
  { sel: "#workspaces", title: "Three workspaces, one model",
    body: "Switch between the 3D Model, the Construction portal (RFIs, costs, schedule), and Finance (development proforma). They all share the same project." },
  { sel: "#open-menu", title: "Open a model",
    body: "Load an IFC or Fragments file, try a bundled sample, or import a Revit file (via the paid bridge). IFC is the source of truth." },
  { sel: "[data-tour=\"projects\"]", title: "Projects",
    body: "Switch projects here, or ＋ New to start a blank one. The portal and proforma work even with no model loaded." },
  { sel: "#rail", title: "Tools & analysis",
    body: "Spatial tree, layers, issues/RFIs, and the Tools panel — exports, drawings, cost, energy, clash and authoring." },
  { sel: "[data-tour=\"account\"]", title: "Sign in & your role",
    body: "Sign in with Google, Microsoft or Procore. Pick your role (top-right) to tailor which tools show first." },
];

/** Run the skippable coach-mark tour. Steps whose target is missing are skipped gracefully. */
export function startTour(): void {
  document.querySelector(".ob-tour")?.remove();
  const steps = STEPS.filter((s) => {
    const el = document.querySelector(s.sel) as HTMLElement | null;
    return el && el.offsetParent !== null;   // present + visible
  });
  if (!steps.length) { markOnboarded(); return; }

  const ov = document.createElement("div");
  ov.className = "ob-tour";
  ov.style.cssText = "position:fixed;inset:0;z-index:300";
  const spot = document.createElement("div");
  spot.style.cssText = "position:fixed;border-radius:8px;box-shadow:0 0 0 9999px #000a;"
    + "border:2px solid var(--accent);transition:all .2s ease;pointer-events:none";
  const tip = document.createElement("div");
  tip.style.cssText = "position:fixed;background:var(--panel);border:1px solid var(--line);border-radius:10px;"
    + "padding:14px 16px;max-width:320px;box-shadow:0 12px 40px #000a;display:flex;flex-direction:column;gap:8px";
  ov.append(spot, tip);
  document.body.appendChild(ov);

  let i = 0;
  const finish = () => { markOnboarded(); ov.remove(); };
  const render = () => {
    const s = steps[i];
    if (!s) return;
    const el = document.querySelector(s.sel) as HTMLElement;
    const r = el.getBoundingClientRect();
    const pad = 6;
    spot.style.left = `${r.left - pad}px`; spot.style.top = `${r.top - pad}px`;
    spot.style.width = `${r.width + pad * 2}px`; spot.style.height = `${r.height + pad * 2}px`;
    tip.innerHTML = `<div style="font-weight:650;font-size:14px">${s.title}</div>`
      + `<div class="meta" style="font-size:13px;line-height:1.5">${s.body}</div>`;
    const nav = document.createElement("div");
    nav.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-top:4px";
    const count = document.createElement("span");
    count.className = "meta"; count.style.fontSize = "12px"; count.textContent = `${i + 1} / ${steps.length}`;
    const btns = document.createElement("div"); btns.style.cssText = "display:flex;gap:6px";
    const skip = document.createElement("button"); skip.className = "tool-btn"; skip.textContent = "Skip"; skip.onclick = finish;
    const next = document.createElement("button"); next.className = "file-btn";
    next.textContent = i === steps.length - 1 ? "Done" : "Next";
    next.onclick = () => { if (i === steps.length - 1) finish(); else { i++; render(); } };
    btns.append(skip, next); nav.append(count, btns); tip.append(nav);
    // position the tooltip below the target, or above if it would overflow
    const below = r.bottom + 12;
    const tipTop = below + 160 > window.innerHeight ? Math.max(12, r.top - 12 - 160) : below;
    tip.style.top = `${tipTop}px`;
    tip.style.left = `${Math.min(Math.max(12, r.left), window.innerWidth - 340)}px`;
  };
  render();
  ov.addEventListener("pointerdown", (e) => { if (e.target === ov) finish(); });
  window.addEventListener("resize", render);
}
