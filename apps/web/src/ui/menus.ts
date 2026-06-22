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

export function closeMenus(keep?: Element): void {
  document.querySelectorAll(".menu-panel").forEach((p) => {
    if (p !== keep) (p as HTMLElement).hidden = true;
  });
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
