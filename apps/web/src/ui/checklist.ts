/**
 * Gamified "Getting started" checklist — a persistent, dismissible progress tracker that surfaces
 * the platform's breadth so users actually discover and try each pillar. Grounded in SaaS activation
 * research: a visible progress bar + the Zeigarnik pull of an unfinished list lifts completion
 * 15–25% and engagement ~48%. Each item navigates to the feature (via the `aec:workspace` event the
 * shell listens for) and auto-checks; 100% triggers a small celebration. State persists locally.
 */
const KEY = "aec-checklist";
const DISMISS = "aec-checklist-dismissed";

interface Item { id: string; icon: string; label: string; ws: string; scroll?: string; }

const ITEMS: Item[] = [
  { id: "model", icon: "🧊", label: "Explore a 3D model", ws: "model" },
  { id: "generate", icon: "🏗️", label: "Generate a building from zoning", ws: "finance", scroll: "pf-massing" },
  { id: "testfit", icon: "📐", label: "Compare unit-mix schemes (Test Fit)", ws: "finance", scroll: "pf-testfit" },
  { id: "budget", icon: "💲", label: "Build a cost budget", ws: "finance", scroll: "pf-budget" },
  { id: "project", icon: "📋", label: "Run a project — create an RFI", ws: "construction" },
  { id: "memo", icon: "📄", label: "Generate an investor memo", ws: "finance", scroll: "pf-budget" },
];

const load = (): Record<string, boolean> => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; } };
const save = (s: Record<string, boolean>) => localStorage.setItem(KEY, JSON.stringify(s));
export const markChecklist = (id: string) => { const s = load(); if (!s[id]) { s[id] = true; save(s); window.dispatchEvent(new Event("aec:checklist")); } };
export const resetChecklist = () => { localStorage.removeItem(KEY); localStorage.removeItem(DISMISS); };
/** Un-dismiss + re-show the checklist (keeps progress) — for the Help menu. */
export const reopenChecklist = () => { localStorage.removeItem(DISMISS); mountChecklist(); };

export function mountChecklist(): void {
  if (localStorage.getItem(DISMISS) === "1") return;
  document.querySelector(".aec-checklist")?.remove();
  const host = document.createElement("div");
  host.className = "aec-checklist";
  host.style.cssText = "position:fixed;left:16px;bottom:16px;z-index:150;font-size:13px";
  document.body.appendChild(host);

  let open = load().__open !== false && Object.keys(load()).length < ITEMS.length;
  const render = () => {
    const s = load();
    const done = ITEMS.filter((i) => s[i.id]).length;
    const pct = Math.round(done / ITEMS.length * 100);
    if (done >= ITEMS.length && s.__celebrated !== true) { s.__celebrated = true; save(s); celebrate(); }
    host.innerHTML = "";
    const pill = document.createElement("button");
    pill.style.cssText = "background:var(--panel,#1e1f22);color:var(--text,#e7e7e7);border:1px solid var(--line,#2b2d31);"
      + "border-radius:20px;padding:8px 14px;cursor:pointer;box-shadow:0 4px 16px #0007;display:flex;align-items:center;gap:8px";
    pill.innerHTML = `<span>✨ Getting started</span><b style="color:var(--accent,#4a8cff)">${done}/${ITEMS.length}</b>`;
    pill.onclick = () => { open = !open; render(); };
    if (!open) { host.appendChild(pill); return; }

    const card = document.createElement("div");
    card.style.cssText = "background:var(--panel,#1e1f22);border:1px solid var(--line,#2b2d31);border-radius:12px;"
      + "padding:14px;width:288px;box-shadow:0 12px 40px #0009;margin-bottom:8px";
    const head = document.createElement("div"); head.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-bottom:8px";
    head.innerHTML = `<b style="font-size:14px">✨ Getting started</b>`;
    const x = document.createElement("button"); x.textContent = "✕";
    x.style.cssText = "background:none;border:none;color:var(--muted,#9aa0a6);cursor:pointer;font-size:14px";
    x.title = "Dismiss (re-open from the ? menu)";
    x.onclick = () => { localStorage.setItem(DISMISS, "1"); host.remove(); };
    head.appendChild(x); card.appendChild(head);
    // progress bar
    const bar = document.createElement("div"); bar.style.cssText = "height:6px;background:var(--panel2,#25272b);border-radius:4px;overflow:hidden;margin-bottom:10px";
    bar.innerHTML = `<div style="height:100%;width:${pct}%;background:var(--accent,#4a8cff);transition:width .3s"></div>`;
    card.appendChild(bar);
    card.insertAdjacentHTML("beforeend", `<div class="meta" style="font-size:11px;margin:-4px 0 8px;color:var(--muted,#9aa0a6)">${pct}% — ${done === ITEMS.length ? "all done, nicely played 🎉" : "tick off the lifecycle"}</div>`);
    for (const it of ITEMS) {
      const row = document.createElement("button");
      const isDone = !!s[it.id];
      row.style.cssText = "display:flex;align-items:center;gap:9px;width:100%;text-align:left;background:none;border:none;"
        + "color:var(--text,#e7e7e7);padding:6px 4px;cursor:pointer;border-radius:6px;font-size:13px";
      row.onmouseenter = () => row.style.background = "var(--panel2,#25272b)";
      row.onmouseleave = () => row.style.background = "none";
      row.innerHTML = `<span style="width:18px;height:18px;border-radius:50%;border:1px solid ${isDone ? "var(--green,#33d17a)" : "var(--line,#2b2d31)"};`
        + `background:${isDone ? "var(--green,#33d17a)" : "transparent"};color:#16171a;font-size:11px;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto">${isDone ? "✓" : ""}</span>`
        + `<span style="opacity:${isDone ? .6 : 1};${isDone ? "text-decoration:line-through" : ""}">${it.icon} ${it.label}</span>`;
      row.onclick = () => {
        window.dispatchEvent(new CustomEvent("aec:workspace", { detail: it.ws }));
        if (it.scroll) setTimeout(() => document.getElementById(it.scroll!)?.scrollIntoView({ behavior: "smooth", block: "center" }), 450);
        markChecklist(it.id);
      };
      card.appendChild(row);
    }
    host.append(card, pill);
  };
  window.addEventListener("aec:checklist", render);
  render();
}

function celebrate(): void {
  // lightweight confetti — no dependency
  const c = document.createElement("div");
  c.style.cssText = "position:fixed;inset:0;z-index:400;pointer-events:none;overflow:hidden";
  const colors = ["#4a8cff", "#33d17a", "#ffd479", "#e2554a", "#b083d6"];
  for (let i = 0; i < 80; i++) {
    const p = document.createElement("div");
    const sz = 6 + Math.random() * 6;
    p.style.cssText = `position:absolute;top:-20px;left:${Math.random() * 100}%;width:${sz}px;height:${sz}px;`
      + `background:${colors[i % colors.length]};border-radius:2px;opacity:.9;`
      + `animation:aecfall ${1.6 + Math.random() * 1.6}s ${Math.random() * .4}s ease-in forwards;transform:rotate(${Math.random() * 360}deg)`;
    c.appendChild(p);
  }
  if (!document.getElementById("aec-confetti-kf")) {
    const st = document.createElement("style"); st.id = "aec-confetti-kf";
    st.textContent = "@keyframes aecfall{to{top:105%;transform:rotate(720deg)}}";
    document.head.appendChild(st);
  }
  document.body.appendChild(c);
  setTimeout(() => c.remove(), 3800);
}
