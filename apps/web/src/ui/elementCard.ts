/**
 * R24-ELEMENT-CARD ② — the same card wherever an element is named.
 *
 * The audit's finding 06, and the one it calls the unfair advantage: a slab's GlobalId is the same
 * key in geometry, BCF, the cost code, the schedule activity and the field verification. **No
 * competitor can answer "where did this number come from" in one hop.** The engine has been able to
 * for a while — `GET /projects/{pid}/elements/{guid}/lifecycle` returns all six states — and
 * `buildLifecycleStrip` has rendered them correctly since R26-INSPECTOR.
 *
 * It rendered them from **exactly one call site**: the 3D viewer's inspector (`viewer/app.ts`). So
 * the one genuinely unusual thing about this product was visible only to somebody already looking at
 * the model — which is the person who needs it least. An estimator reading a cost trace, or a PM
 * reading an RFI, saw a GlobalId and nothing else.
 *
 * **The extraction this needed turned out not to exist.** The plan was to pull the strip out of
 * `viewer/` so other surfaces could use it without dragging in three.js. On opening the file:
 * `lifecycleStrip.ts` imports **one type** and nothing else. It was already portable and merely
 * *filed* under `viewer/`. Moved to `ui/`, two import lines updated, done — another item whose
 * estimate came from where a file sat rather than what it contained.
 *
 * So this module is small on purpose. It is the card's *frame* — identity line plus strip — and a
 * loader that any surface can call with a GlobalId. The strip itself is unchanged.
 */
import type { ApiClient } from "../api/client";
import type { LifecycleStrip } from "../api/types";

import { buildLifecycleStrip } from "./lifecycleStrip";

/** Shorten a GlobalId for display without hiding it: `1kP9x…7Qa`. The full value stays in `title`. */
export function shortGuid(guid: string): string {
  const g = String(guid ?? "");
  return g.length <= 12 ? g : `${g.slice(0, 5)}…${g.slice(-3)}`;
}

/**
 * The identity line: what this element is, and its key.
 *
 * The GlobalId is rendered in a mono face because it is machine-produced — the audit's "two faces,
 * no exceptions" rule, applied where it costs nothing. It is also the one string on the card a user
 * might need to copy verbatim, so it is never truncated in the DOM, only visually.
 */
export function buildIdentityLine(guid: string, label?: string | null): HTMLElement {
  const row = document.createElement("div");
  row.style.cssText = "display:flex;align-items:baseline;gap:8px;flex-wrap:wrap";

  if (label) {
    const name = document.createElement("span");
    name.style.cssText = "font-size:12px";
    name.textContent = label;                       // textContent: server-supplied
    row.appendChild(name);
  }

  const key = document.createElement("span");
  key.className = "meta";
  key.style.cssText = "font-family:var(--mono);font-size:10.5px";
  key.textContent = shortGuid(guid);
  key.title = guid;                                 // the full key, one hover away
  row.appendChild(key);

  return row;
}

/**
 * Render the card into `host`, replacing its contents.
 *
 * `strip === null` renders **nothing at all** rather than an empty six-state skeleton. A strip of six
 * blank cells is a claim that six things were checked and none passed, which is a different and much
 * worse statement than "we have not asked". The strip's own renderer already distinguishes `unknown`
 * from `none` for the same reason; this is that rule one level up.
 */
export function renderElementCard(
  host: HTMLElement,
  el: { guid: string; label?: string | null; strip: LifecycleStrip | null },
): void {
  host.innerHTML = "";
  host.appendChild(buildIdentityLine(el.guid, el.label));
  if (el.strip) host.appendChild(buildLifecycleStrip(el.strip));
}

/**
 * Fetch a lifecycle and render, tolerating the fetch failing.
 *
 * A failed lookup renders the identity line **without** a strip — the element still exists and its
 * key is still worth showing. Throwing here would take out whatever panel hosts the card, and a cost
 * trace losing its whole table because one lifecycle request 500'd is a bad trade.
 */
export async function mountElementCard(
  host: HTMLElement,
  api: Pick<ApiClient, "elementLifecycle">,
  pid: string,
  guid: string,
  label?: string | null,
): Promise<void> {
  let strip: LifecycleStrip | null;
  try { strip = await api.elementLifecycle(pid, guid); } catch { strip = null; }
  renderElementCard(host, { guid, label, strip });
}
