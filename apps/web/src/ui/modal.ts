/**
 * Shared modal shell — a centered dialog over a dimmed backdrop. Extracted from main.ts so every
 * modal (auth, settings, members, connections, password…) gets the same behavior and a11y in one
 * place: backdrop-click + Esc to close, dialog role/aria-modal, autofocus on open, and focus
 * restored to the previously-focused element on close.
 */
export interface ModalHandle {
  ov: HTMLDivElement;
  card: HTMLDivElement;
  msg: HTMLDivElement;
  close: () => void;
}

export function modalShell(titleText: string, minWidth = 280): ModalHandle {
  const prevFocus = document.activeElement as HTMLElement | null;
  const ov = document.createElement("div");
  ov.style.cssText = "position:fixed;inset:0;z-index:201;background:#000a;display:flex;align-items:center;justify-content:center";
  const card = document.createElement("div");
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-modal", "true");
  card.setAttribute("aria-label", titleText);
  card.tabIndex = -1;
  card.style.cssText = `background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px;`
    + `min-width:${minWidth}px;max-height:80vh;overflow:auto;display:flex;flex-direction:column;gap:10px`;
  const title = document.createElement("strong"); title.textContent = titleText; title.style.fontSize = "15px";
  const msg = document.createElement("div"); msg.className = "meta";
  card.append(title); ov.append(card);

  const close = () => {
    ov.remove();
    document.removeEventListener("keydown", onKey);
    prevFocus?.focus?.();
  };
  const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  function onKey(e: KeyboardEvent) {
    if (!document.body.contains(ov)) { document.removeEventListener("keydown", onKey); return; }  // caller closed it directly
    if (e.key === "Escape") { close(); return; }
    if (e.key === "Tab") {                    // trap focus within the dialog
      const items = [...card.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      const active = document.activeElement as HTMLElement;
      if (e.shiftKey && (active === first || !card.contains(active))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
    }
  }
  ov.addEventListener("pointerdown", (e) => { if (e.target === ov) close(); });
  document.addEventListener("keydown", onKey);
  document.body.appendChild(ov);
  // focus the first field if there is one, else the dialog itself (so Esc/Tab work)
  setTimeout(() => ((card.querySelector("input,select,textarea,button") as HTMLElement) || card).focus(), 0);
  return { ov, card, msg, close };
}
