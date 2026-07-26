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

/**
 * A yes/no confirm. Returns true only on the affirmative button — backdrop, Esc and Cancel all
 * resolve `false`.
 *
 * Exists because R28-UNIFY needs to *propose* creating a project rather than minting one silently:
 * a project is a durable, shared, server-side object, and auto-creating one for every stray file a
 * user previews fills the register with records nobody meant to make. `askText` was the nearest
 * existing surface and is the wrong one here — it offers an editable field where there is nothing to
 * edit, which reads as "change this" when the only real choices are yes and no.
 */
export function askConfirm(title: string, opts: {
  body?: string; okLabel?: string; cancelLabel?: string;
} = {}): Promise<boolean> {
  return new Promise((resolve) => {
    const { card, ov } = modalShell(title, 420);
    let settled = false;
    const finish = (v: boolean) => { if (settled) return; settled = true; ov.remove(); resolve(v); };
    if (opts.body) {
      const p = document.createElement("div");
      p.className = "meta"; p.style.cssText = "line-height:1.5;white-space:pre-wrap";
      p.textContent = opts.body;                       // textContent: the body carries server text
      card.append(p);
    }
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;justify-content:flex-end;margin-top:12px";
    const cancel = document.createElement("button");
    cancel.className = "tool-btn"; cancel.textContent = opts.cancelLabel ?? "Cancel";
    cancel.onclick = () => finish(false);
    const ok = document.createElement("button");
    ok.className = "file-btn"; ok.textContent = opts.okLabel ?? "OK";
    ok.onclick = () => finish(true);
    row.append(cancel, ok); card.append(row);
    ov.addEventListener("pointerdown", (e) => { if (e.target === ov) finish(false); });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { document.removeEventListener("keydown", esc); finish(false); }
    });
    setTimeout(() => ok.focus(), 0);
  });
}
