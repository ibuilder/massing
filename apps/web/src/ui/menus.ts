/**
 * Open / Save style dropdown menus — a small self-contained DOM helper extracted from main.ts as
 * part of breaking that file up. `buildMenu` mounts a button + panel into an element by id;
 * `closeMenus` hides any open panels (call it from global blur / Escape / outside-click handlers).
 */
export interface MenuItem {
  label: string;
  sep?: boolean;
  onClick?: () => void;
}

/**
 * The one event every popup in the app listens to.
 *
 * The Open and Save menus already dismissed each other, because both are `.menu-panel` and
 * `closeMenus` knew that class. The viewer's own `.vt-menu` is a separate system that neither knew
 * about — which is how two dropdowns ended up open at once, stacked over the model. Two popup
 * systems that cannot see each other will always produce that; a shared channel is the fix, not
 * another selector added to another querySelectorAll.
 */
export const CLOSE_POPUPS = "aec:close-popups";

/** Ask every popup in the app to close. `keep` survives, so a menu can dismiss its rivals. */
export function closeMenus(keep?: Element): void {
  document.querySelectorAll(".menu-panel").forEach((p) => {
    if (p !== keep) (p as HTMLElement).hidden = true;
  });
  // Anything not built by `buildMenu` — the viewer toolbar's More menu today — closes on the event.
  window.dispatchEvent(new CustomEvent(CLOSE_POPUPS, { detail: { keep } }));
}

export function buildMenu(mountId: string, label: string, items: MenuItem[], onOpen?: () => void): void {
  const mount = document.getElementById(mountId);
  if (!mount) return;
  const btn = document.createElement("button");
  btn.className = "file-btn menu-btn"; btn.textContent = label;
  btn.setAttribute("aria-haspopup", "true");
  const panel = document.createElement("div"); panel.className = "menu-panel"; panel.hidden = true;
  panel.setAttribute("role", "menu");
  for (const it of items) {
    if (it.sep) {
      const s = document.createElement("div"); s.className = "menu-sep"; s.textContent = it.label;
      panel.appendChild(s); continue;
    }
    const mi = document.createElement("button"); mi.className = "menu-item"; mi.textContent = it.label;
    mi.setAttribute("role", "menuitem");
    mi.onclick = () => { panel.hidden = true; it.onClick?.(); };
    panel.appendChild(mi);
  }
  const place = () => {
    const r = btn.getBoundingClientRect();
    panel.style.left = `${r.left}px`; panel.style.top = `${r.bottom + 4}px`;
  };
  btn.onclick = (e) => {
    e.stopPropagation(); closeMenus(panel);
    const open = panel.hidden;
    if (open) { place(); onOpen?.(); }
    panel.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
  };
  mount.append(btn, panel);
}
