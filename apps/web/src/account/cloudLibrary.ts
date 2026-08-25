/** CLOUD-LIBRARY browser — the user's massing.cloud project vault, inside the app.
 *
 *  Two levels: the vaults (projects) they own, and the models inside one. Opening a model resolves
 *  its signed `download_url` server-side and fetches the bytes straight from massing.cloud — see
 *  `api/cloud.ts` for why that fetch carries no Authorization header.
 *
 *  **Refusals are rendered, not swallowed.** A free plan gets an upgrade link, an unlinked account
 *  gets a connect prompt, and a plan limit shows the site's own message. An empty library and an
 *  ungranted one look completely different here, which is the whole reason the server distinguishes
 *  402 / 403 / 200-with-`[]` instead of returning an empty list for all three.
 */
import { modalShell } from "../ui/modal";
import { escapeHtml, toast } from "../ui/feedback";
import type { ApiClient } from "../api/client";
import {
  CloudError, cloudProjects, cloudProject, cloudModel, formatBytes,
  type CloudProject,
} from "../api/cloud";

export interface LibraryDeps {
  api: ApiClient;
  siteUrl: string;
  /** Hand the downloaded `.mass`/IFC bytes to the app. Returning false means "not handled". */
  onOpenModel: (blob: Blob, name: string) => Promise<boolean> | boolean;
  connectCloud: () => void;
}

function empty(msg: string, actionLabel?: string, onClick?: () => void): HTMLElement {
  const el = document.createElement("div");
  el.style.cssText = "display:flex;flex-direction:column;align-items:flex-start;gap:8px;padding:18px 4px";
  const t = document.createElement("div");
  t.className = "meta"; t.innerHTML = escapeHtml(msg);
  el.append(t);
  if (actionLabel && onClick) {
    const b = document.createElement("button");
    b.className = "file-btn"; b.textContent = actionLabel; b.onclick = onClick;
    el.append(b);
  }
  return el;
}

/** Turn a thrown CloudError into the right piece of UI, or null if it is not one we explain. */
function refusalView(e: unknown, deps: LibraryDeps): HTMLElement | null {
  if (!(e instanceof CloudError)) return null;
  if (e.needsUpgrade) {
    return empty("The cloud project library is included with any paid Massing plan. "
      + "Your massing.cloud account is on the Free plan.",
      "See plans", () => window.open(`${deps.siteUrl}/pricing/`, "_blank", "noopener"));
  }
  if (e.notLinked) {
    return empty("This account is not connected to massing.cloud yet.",
      "Connect massing.cloud", deps.connectCloud);
  }
  return empty(e.message);
}

export function openCloudLibrary(deps: LibraryDeps): void {
  const { card, msg, close, ready } = modalShell("My massing.cloud projects", 560);
  msg.style.color = "var(--err)";
  const crumbs = document.createElement("div");
  crumbs.style.cssText = "display:flex;align-items:center;gap:6px;min-height:24px";
  const list = document.createElement("div");
  list.style.cssText = "display:flex;flex-direction:column;gap:6px;max-height:56vh;overflow:auto";
  card.append(crumbs, list, msg);

  const spinner = () => { list.textContent = ""; list.append(empty("Loading…")); };

  const showProjects = async () => {
    crumbs.textContent = "";
    spinner();
    let projects: CloudProject[];
    try {
      projects = await cloudProjects(deps.api);
    } catch (e) {
      const view = refusalView(e, deps);
      list.textContent = "";
      list.append(view || empty("Could not reach your massing.cloud library."));
      return;
    }
    list.textContent = "";
    if (!projects.length) {
      list.append(empty("No projects in your cloud library yet. Projects you save to massing.cloud "
        + "will appear here.", "Open massing.cloud",
        () => window.open(`${deps.siteUrl}/my-account/vaults/`, "_blank", "noopener")));
      return;
    }
    for (const p of projects) list.append(projectRow(p));
  };

  const projectRow = (p: CloudProject) => {
    const el = document.createElement("button");
    el.className = "tool-btn";
    el.style.cssText = "display:flex;align-items:center;gap:10px;width:100%;text-align:left;padding:9px 10px";
    const col = document.createElement("div");
    col.style.cssText = "display:flex;flex-direction:column;gap:2px;flex:1;min-width:0";
    const t = document.createElement("span"); t.textContent = p.title;
    const d = document.createElement("span"); d.className = "meta";
    d.textContent = `${p.model_count} model${p.model_count === 1 ? "" : "s"}`
      + (p.updated ? ` · updated ${new Date(p.updated).toLocaleDateString()}` : "");
    col.append(t, d);
    const chev = document.createElement("span"); chev.textContent = "›"; chev.style.opacity = ".6";
    el.append(col, chev);
    el.onclick = () => void showProject(p);
    return el;
  };

  const showProject = async (p: CloudProject) => {
    crumbs.textContent = "";
    const back = document.createElement("button");
    back.className = "tool-btn"; back.textContent = "‹ All projects";
    back.onclick = () => void showProjects();
    const here = document.createElement("span");
    here.className = "meta"; here.textContent = p.title;
    crumbs.append(back, here);
    spinner();

    // The vault list gives a model COUNT but not the model records; `GET /projects/{id}` is what
    // carries them. A site that returns the count only still renders — as "no models listed" —
    // rather than throwing, because the count is not a promise about the payload shape.
    let models: unknown[];
    try {
      const full = await cloudProject(deps.api, p.id) as CloudProject & { models?: unknown[] };
      models = Array.isArray(full.models) ? full.models : [];
    } catch (e) {
      const view = refusalView(e, deps);
      list.textContent = "";
      list.append(view || empty("Could not open that project."));
      return;
    }
    list.textContent = "";
    if (!models.length) {
      list.append(empty("No models in this project yet."));
      return;
    }
    for (const raw of models) {
      const m = raw as { id: number | string; title?: string; size_bytes?: number; version?: number };
      list.append(modelRow(m));
    }
  };

  const modelRow = (m: { id: number | string; title?: string; size_bytes?: number; version?: number }) => {
    const el = document.createElement("div");
    el.style.cssText = "display:flex;align-items:center;gap:10px;padding:9px 10px;border:1px solid var(--line);"
      + "border-radius:7px";
    const col = document.createElement("div");
    col.style.cssText = "display:flex;flex-direction:column;gap:2px;flex:1;min-width:0";
    const t = document.createElement("span"); t.textContent = m.title || "Untitled model";
    const d = document.createElement("span"); d.className = "meta";
    d.textContent = [formatBytes(m.size_bytes || 0), m.version ? `v${m.version}` : ""]
      .filter(Boolean).join(" · ");
    col.append(t, d);
    const open = document.createElement("button");
    open.className = "file-btn"; open.textContent = "Open";
    open.onclick = async () => {
      open.disabled = true; open.textContent = "Opening…";
      try {
        const rec = await cloudModel(deps.api, m.id);
        const { openModelBytes } = await import("../api/cloud");
        const blob = await openModelBytes(rec);
        const handled = await deps.onOpenModel(blob, rec.title || "model");
        if (handled) { close(); toast(`Opened “${rec.title}” from massing.cloud`, "info"); }
        else toast("This model type can't be opened here yet", "error");
      } catch (e) {
        msg.textContent = e instanceof CloudError ? e.message : "could not open that model";
      } finally { open.disabled = false; open.textContent = "Open"; }
    };
    el.append(col, open);
    return el;
  };

  void showProjects();
  ready?.();
}
