/**
 * askText — a non-blocking text-input modal (a nicer replacement for window.prompt where the input
 * deserves a real field, e.g. multi-line descriptions). Resolves to the entered string, or null on
 * cancel / Esc / backdrop. Reuses the shared modal shell.
 */
import { modalShell } from "./modal";

export function askText(title: string, opts: {
  label?: string; value?: string; placeholder?: string; multiline?: boolean; okLabel?: string;
  password?: boolean;
} = {}): Promise<string | null> {
  return new Promise((resolve) => {
    const { card, ov } = modalShell(title, 380);
    let settled = false;
    const finish = (v: string | null) => { if (settled) return; settled = true; ov.remove(); resolve(v); };
    if (opts.label) card.append(Object.assign(document.createElement("div"), { className: "meta", textContent: opts.label }));
    const field = document.createElement(opts.multiline ? "textarea" : "input") as HTMLInputElement & HTMLTextAreaElement;
    field.className = "portal-filter"; field.value = opts.value ?? "";
    if (opts.password && !opts.multiline) field.type = "password";
    if (opts.placeholder) field.placeholder = opts.placeholder;
    field.style.width = "100%";
    if (opts.multiline) { field.rows = 5; field.style.resize = "vertical"; }
    else field.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); finish(field.value); } });
    card.append(field);
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:10px";
    const cancel = document.createElement("button"); cancel.className = "tool-btn"; cancel.textContent = "Cancel";
    cancel.onclick = () => finish(null);
    const ok = document.createElement("button"); ok.className = "file-btn"; ok.textContent = opts.okLabel ?? "OK";
    ok.onclick = () => finish(field.value);
    row.append(cancel, ok); card.append(row);
    // backdrop / Esc close → treat as cancel (modalShell removes the overlay; we resolve null once)
    ov.addEventListener("pointerdown", (e) => { if (e.target === ov) finish(null); });
    document.addEventListener("keydown", function esc(e) { if (e.key === "Escape") { document.removeEventListener("keydown", esc); finish(null); } });
    setTimeout(() => field.focus(), 0);
  });
}
