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
      const first = items[0]!, last = items[items.length - 1]!; // safe: items.length checked above
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

/** Accessible replacement for window.confirm(): a modalShell dialog with a message + Confirm/Cancel.
 *  Resolves true on confirm, false on cancel/Esc/backdrop. `danger` styles the confirm button red. */
export function confirmModal(title: string, body: string, okLabel = "Confirm",
                             danger = false): Promise<boolean> {
  return new Promise((resolve) => {
    const m = modalShell(title, 340);
    const b = document.createElement("div");
    b.className = "meta"; b.style.whiteSpace = "pre-line"; b.textContent = body;
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:4px";
    const cancel = document.createElement("button"); cancel.textContent = "Cancel"; cancel.className = "file-btn";
    const ok = document.createElement("button"); ok.textContent = okLabel; ok.className = "file-btn";
    ok.style.fontWeight = "600";
    if (danger) ok.style.color = "#dc2626";
    row.append(cancel, ok); m.card.append(b, row);
    let settled = false;
    const done = (v: boolean) => { if (settled) return; settled = true; m.close(); resolve(v); };
    cancel.onclick = () => done(false);
    ok.onclick = () => done(true);
    const mo = new MutationObserver(() => {
      if (!document.body.contains(m.ov)) { mo.disconnect(); done(false); }   // Esc / backdrop
    });
    mo.observe(document.body, { childList: true });
  });
}

export interface PromptField {
  name: string;
  label: string;
  value?: string;
  placeholder?: string;
  required?: boolean;
}

/** Accessible replacement for window.prompt(): a modalShell dialog with labeled inputs and
 *  OK/Cancel. Resolves the entered values, or null on cancel/Esc. One field renders like a classic
 *  prompt; several make a small form. */
export function promptModal(title: string, fields: PromptField[], okLabel = "OK",
                            body?: string): Promise<Record<string, string> | null> {
  return new Promise((resolve) => {
    const m = modalShell(title, 340);
    if (body) {
      const b = document.createElement("div");
      b.className = "meta"; b.style.whiteSpace = "pre-line"; b.textContent = body;
      m.card.appendChild(b);
    }
    const inputs = new Map<string, HTMLInputElement>();
    for (const f of fields) {
      const lab = document.createElement("label");
      lab.style.cssText = "display:flex;flex-direction:column;gap:4px;font-size:12px";
      lab.textContent = f.label + (f.required ? " *" : "");
      const inp = document.createElement("input");
      inp.type = "text"; inp.value = f.value ?? ""; inp.placeholder = f.placeholder ?? "";
      inp.style.cssText = "padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:inherit";
      lab.appendChild(inp); m.card.appendChild(lab); inputs.set(f.name, inp);
    }
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:4px";
    const cancel = document.createElement("button"); cancel.textContent = "Cancel"; cancel.className = "file-btn";
    const ok = document.createElement("button"); ok.textContent = okLabel; ok.className = "file-btn";
    ok.style.fontWeight = "600";
    row.append(cancel, ok); m.card.append(m.msg, row);
    const done = (v: Record<string, string> | null) => { m.close(); resolve(v); };
    cancel.onclick = () => done(null);
    ok.onclick = () => {
      const out: Record<string, string> = {};
      for (const f of fields) {
        const v = (inputs.get(f.name)?.value ?? "").trim();
        if (f.required && !v) { m.msg.textContent = `${f.label} is required.`; inputs.get(f.name)?.focus(); return; }
        out[f.name] = v;
      }
      done(out);
    };
    // Enter submits from any field; Esc is handled by modalShell (resolves null via close → but we
    // must also resolve): watch removal of the overlay to resolve null on Esc/backdrop close.
    for (const inp of inputs.values()) {
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") ok.click(); });
    }
    const mo = new MutationObserver(() => {
      if (!document.body.contains(m.ov)) { mo.disconnect(); resolve(null); }
    });
    mo.observe(document.body, { childList: true });
  });
}
