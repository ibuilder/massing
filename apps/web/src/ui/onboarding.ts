/**
 * First-run onboarding: a welcome modal with quick-start paths, and a skippable coach-mark tour.
 *
 * Shown once (tracked in localStorage) — new users can skip everything and dive in, or take a
 * ~60-second tour of the workspaces, Open menu, project switcher, tools rail and sign-in. Both
 * the welcome and the tour are relaunchable from the Help (?) menu.
 */
const KEY = "aec-onboarded";
const TOUR_AFTER_SIGNIN = "aec-tour-after-signin";

export const onboardingDone = (): boolean => localStorage.getItem(KEY) === "1";
export const markOnboarded = (): void => localStorage.setItem(KEY, "1");
export const resetOnboarding = (): void => localStorage.removeItem(KEY);

/** B2: sign-in → tour. Signing in reloads the page (token/SSO), so the welcome flow leaves a flag
 *  and the next boot resumes straight into the coach-mark tour instead of dropping the new user. */
export const queueTourAfterSignIn = (): void => localStorage.setItem(TOUR_AFTER_SIGNIN, "1");

/** Call once on boot after the chrome exists: consumes the flag and runs the tour (first-run only).
 *  Returns true when the tour was resumed — the caller then skips the welcome modal. */
export function maybeResumeTour(): boolean {
  if (localStorage.getItem(TOUR_AFTER_SIGNIN) !== "1") return false;
  localStorage.removeItem(TOUR_AFTER_SIGNIN);
  if (onboardingDone()) return false;
  startTour();
  return true;
}

export interface OnboardCtx {
  /** B1: signed-in state + the sign-in opener — the welcome LEADS with sign-in, never walls on it. */
  signedIn?: boolean;
  signIn?: () => void;
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

  // B1: sign-in-first — the panel LEADS with sign-in (Google · Microsoft · Procore via the server's
  // configured providers), but never walls: every start path below works signed-out.
  if (!ctx.signedIn && ctx.signIn) {
    const si = document.createElement("div");
    si.style.cssText = "display:flex;align-items:center;gap:10px;background:var(--panel2,#25272b);"
      + "border:1px solid var(--accent,#4a8cff);border-radius:10px;padding:12px 14px;margin-bottom:12px";
    si.innerHTML = `<div style="font-size:20px">🔐</div>`
      + `<div style="flex:1"><div style="font-weight:600;font-size:13.5px">Sign in to sync your projects</div>`
      + `<div class="meta" style="font-size:12px">Google · Microsoft · Procore single sign-on, or a username — `
      + `everything below also works without an account.</div></div>`;
    const btn = document.createElement("button");
    btn.className = "file-btn"; btn.textContent = "Sign in";
    btn.onclick = () => { ov.remove(); queueTourAfterSignIn(); ctx.signIn?.(); };
    si.append(btn);
    card.append(si);
  }

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

// --- B3: role self-selection after sign-in -----------------------------------
const ROLE_PROMPTED = "aec-role-prompted";

/** B3: on the first signed-in boot (and only when no persona was ever picked manually), offer the
 *  role list so the workspace tailors itself immediately. One-shot; picking or dismissing marks it. */
export function maybeRolePrompt(opts: {
  authed: boolean;
  roles: { id: string; label: string }[];
  apply: (id: string) => void;
}): void {
  if (!opts.authed || !opts.roles.length) return;
  if (localStorage.getItem(ROLE_PROMPTED) === "1" || localStorage.getItem("persona-manual") === "1") return;
  if (document.querySelector(".ob-welcome, .ob-tour")) return;   // don't stack on the welcome/tour
  localStorage.setItem(ROLE_PROMPTED, "1");
  const ov = backdrop(); ov.className = "ob-role";
  const card = document.createElement("div");
  card.style.cssText = "background:var(--panel);border:1px solid var(--line);border-radius:14px;"
    + "padding:22px;max-width:440px;width:100%;display:flex;flex-direction:column;gap:10px;box-shadow:0 18px 60px #000a";
  card.innerHTML = `<div style="font-size:17px;font-weight:650">What's your role?</div>`
    + `<div class="meta" style="font-size:12.5px">Massing tailors the workspaces and tools to how you `
    + `work. You can change this any time from the role picker (top right).</div>`;
  const list = document.createElement("div");
  list.style.cssText = "display:flex;flex-direction:column;gap:6px;max-height:300px;overflow:auto";
  for (const r of opts.roles) {
    const b = document.createElement("button"); b.className = "tool-btn";
    b.style.cssText = "text-align:left;padding:9px 12px";
    b.textContent = r.label;
    b.onclick = () => { ov.remove(); opts.apply(r.id); };
    list.appendChild(b);
  }
  const skip = document.createElement("button"); skip.className = "meta";
  skip.style.cssText = "background:none;border:none;cursor:pointer;font-size:12px;align-self:flex-end";
  skip.textContent = "Skip — show me everything";
  skip.onclick = () => ov.remove();
  card.append(list, skip);
  ov.append(card);
  ov.addEventListener("pointerdown", (e) => { if (e.target === ov) ov.remove(); });
  document.body.appendChild(ov);
}

// --- C2: value-moment sign-in nudge ------------------------------------------
const C2_SHOWN = "aec-c2-shown";

/** C2: the first time a signed-out user creates something worth keeping (a project, a published
 *  model edit), nudge — once, dismissible, never a wall. */
export function valueMomentPrompt(signIn: () => void): void {
  if (localStorage.getItem(C2_SHOWN) === "1" || document.querySelector(".ob-c2")) return;
  localStorage.setItem(C2_SHOWN, "1");
  const bar = document.createElement("div");
  bar.className = "ob-c2";
  bar.style.cssText = "position:fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:290;"
    + "display:flex;align-items:center;gap:12px;background:var(--panel);border:1px solid var(--accent,#4a8cff);"
    + "border-radius:12px;padding:10px 14px;box-shadow:0 10px 36px #000a;max-width:92vw";
  bar.innerHTML = `<span style="font-size:16px">💾</span>`
    + `<span style="font-size:13px">Nice — <strong>sign in to save your work</strong> and pick it up on any device.</span>`;
  const go = document.createElement("button"); go.className = "file-btn"; go.textContent = "Sign in";
  go.onclick = () => { bar.remove(); signIn(); };
  const later = document.createElement("button"); later.className = "tool-btn"; later.textContent = "Later";
  later.onclick = () => bar.remove();
  bar.append(go, later);
  document.body.appendChild(bar);
  setTimeout(() => bar.remove(), 30000);   // never lingers
}

// --- coach-mark tour ---------------------------------------------------------
interface Step { sel: string; title: string; body: string; }

const STEPS: Step[] = [
  { sel: "#workspaces", title: "Three workspaces, one model",
    body: "Switch between the 3D Model, the Construction portal (RFIs, costs, schedule), and Finance (development proforma). They all share the same project." },
  { sel: "#open-menu", title: "Open a model",
    body: "Load an IFC or Fragments file, try a bundled sample, or import a Revit file (via the paid bridge). You can also overlay a point cloud, GIS context, or a photoreal reality-capture (Gaussian-splat) scene. IFC stays the source of truth." },
  { sel: "[data-tour=\"projects\"]", title: "Projects",
    body: "Switch projects here, or ＋ New to start a blank one. The portal and proforma work even with no model loaded." },
  { sel: "#rail", title: "Tools & analysis",
    body: "Spatial tree, layers, issues/RFIs, and the Tools panel — exports, drawings, cost, energy, authoring, plus the field toolkit: coordinate clashes into grouped BCF issues, export field-layout setout (CSV/DXF), and a preliminary load takedown." },
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
