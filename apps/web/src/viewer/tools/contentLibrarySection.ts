import type { ApiClient } from "../../api/client";
import { withLoading } from "../../ui/feedback";
import { askText } from "../../ui/prompt";
import { resultNote, showResult } from "../../ui/result";
import { type FamilyDef } from "../draft/draftCatalog";

/**
 * R39-DECOMP-VIEWER ⑮ — the **unified content & family library**, out of `app.ts`.
 *
 * One searchable palette over two catalogues that used to be separate screens: CONTENT-1 site
 * content (logistics, furniture, landscaping, each classified into its IFC class and phase, so
 * logistics time-phase on the 4D slider) and W10-1 family types. Search by name, IFC class or
 * category; click an item to place it at an E,N point.
 *
 * ## Checked before moving, because ⑭ was not this simple
 *
 * Slice ⑭ looked like a pure text move and was not: two `let`s sat OUTSIDE `buildToolsPanel` on
 * purpose, because it re-runs on every persona switch, and scoping them inside the extracted
 * builder stacked a `pointermove` listener per rebuild — invisible to `tsc` and to 619 viewer
 * tests. So this block was checked for the same shape FIRST: it assigns to nothing declared
 * outside itself and installs no listener, so there is no cross-rebuild state to strand. That
 * check is the reason this one is a text move and ⑭ was not.
 *
 * `lastPoint` still crosses as an ACCESSOR — `let` in `app.ts`, reassigned on every pick, and a
 * value copy would freeze it at panel-build time and place every item at the origin.
 */
export interface ContentLibraryDeps {
  /** A full-width tool button. Declared inside `buildToolsPanel`, handed over whole. */
  toolBtn2: (label: string, onClick: () => void) => HTMLButtonElement;
  api: ApiClient;
  projectId: string | null;
  container: HTMLElement;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
  reloadModelPins: () => Promise<void>;
  /** The REAL signature — `Promise<boolean>` says whether a model came back. */
  loadProjectModel: () => Promise<boolean>;
  waitForPublish: (pid: string, onTick?: (s: string) => void) => Promise<string>;
  /** **An accessor, never a value** — the last point picked in 3D, `let` in `app.ts`. */
  lastPoint: () => import("three").Vector3 | null;
}

export function buildContentLibrarySection(d: ContentLibraryDeps) {
    // CONTENT-1 — site content library: place logistics / furniture / landscaping, each classified into
    // the right IFC class + phase (logistics = temporary, time-phases on the 4D slider).
    // UX-3: one unified, searchable Library palette — content parts (CONTENT-1) + family types (W10-1)
    // in a single filterable list; click an item to place it at an E,N point; import detailed meshes.
    const contentBtn = d.toolBtn2("📚 Content & family library", () => withLoading(d.container, "Loading the library", async () => {
      let cat, fams;
      try {
        [cat, fams] = await Promise.all([
          d.api.contentCatalog(),
          d.api.familyCatalog().catch(() => ({ count: 0, categories: {} as Record<string, FamilyDef[]> })),
        ]);
      } catch (e) { d.notify(`library failed: ${(e as Error).message}`, "error"); return; }

      const placeAt = (label: string, fn: (e: number, n: number) => Promise<unknown>) => async () => {
        // Read once, INSIDE the handler — at click time. The ternary form was three separate calls
    // TS cannot narrow, and three chances to read a different point if the user clicks mid-await.
    const at = d.lastPoint();
    const dflt = at ? `${at.x.toFixed(1)}, ${(-at.z).toFixed(1)}` : "0, 0";
        const v = await askText(`Place ${label}`, { label: "Location E, N (metres):", value: dflt });
        if (!v) return;
        const parts = v.split(",").map((s) => parseFloat(s.trim()));
        if (parts.length < 2 || parts.some((n) => !isFinite(n))) { d.notify("enter E, N", "error"); return; }
        await withLoading(d.container, `placing ${label} + republishing`, async () => {
          try {
            await fn(parts[0]!, parts[1]!);
            const state = await d.waitForPublish(d.projectId!);
            if (state === "done") { await d.loadProjectModel(); d.notify(`placed ${label}`, "success"); }
            else d.notify(`placed — publish ${state}`, state === "error" ? "error" : "info");
            await d.reloadModelPins();
          } catch (e) { d.notify(`place failed: ${(e as Error).message}`, "error"); }
        });
      };

      type LibItem = { key: string; label: string; sub: string; cls: string; cat: string;
                       kind: "content" | "type"; search: string; onPlace: () => Promise<void> };
      const items: LibItem[] = [];
      for (const [group, gitems] of Object.entries(cat!.groups)) {
        for (const it of gitems) {
          const nm = it.key.replace(/_/g, " ");
          items.push({ key: `content:${it.key}`, label: nm + (it.phase === "temporary" ? " ⏱" : ""),
            sub: `${it.ifc_class.replace("Ifc", "")} · ${group}${it.phase ? ` · ${it.phase}` : ""}`,
            cls: it.ifc_class.toLowerCase(), cat: group.toLowerCase(), kind: "content",
            search: `${nm} ${it.ifc_class} ${it.classification} ${it.phase || ""} ${group} content`.toLowerCase(),
            onPlace: placeAt(nm, (e, n) => d.api.placeContent(d.projectId!, it.key, [e, n], undefined, true)) });
        }
      }
      for (const f of Object.values(fams!.categories).flat() as FamilyDef[]) {
        items.push({ key: `type:${f.key}`, label: f.label,
          sub: `${f.ifc_class.replace("Ifc", "")} · ${f.category} · type`,
          cls: f.ifc_class.toLowerCase(), cat: f.category.toLowerCase(), kind: "type",
          search: `${f.label} ${f.key} ${f.ifc_class} ${f.category} family type`.toLowerCase(),
          onPlace: placeAt(f.label, (e, n) => d.api.placeFamily(d.projectId!, f.key, [e, n])) });
      }
      // UX-3: a Recent bucket — the last handful of placed items, most-recent first (per-project)
      const RECENT_KEY = `lib-recent:${d.projectId}`;
      const readRecent = (): string[] => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; } };
      const pushRecent = (k: string) => {
        const r = [k, ...readRecent().filter((x) => x !== k)].slice(0, 6);
        try { localStorage.setItem(RECENT_KEY, JSON.stringify(r)); } catch { /* quota */ }
      };
      for (const it of items) { const orig = it.onPlace; it.onPlace = async () => { pushRecent(it.key); await orig(); }; }

      showResult("📚 Library", (body) => {
        body.appendChild(resultNote(`<b>${items.length}</b> library items — content parts + family types. `
          + `Search, then click to place at an E,N point (defaults to the last picked point). Import a `
          + `detailed mesh (glTF/OBJ/STL) below to place it auto-classified as the right IFC.`, ""));
        // import a detailed mesh → auto-detect category → placed as the right IFC
        const imp = document.createElement("div"); imp.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 8px";
        const impLbl = document.createElement("span"); impLbl.className = "meta"; impLbl.textContent = "⬆ Import mesh (auto-classified):";
        const catIn = document.createElement("input"); catIn.className = "portal-filter"; catIn.placeholder = "category (auto)"; catIn.style.cssText = "width:110px;font-size:11px";
        const fileIn = document.createElement("input"); fileIn.type = "file"; fileIn.accept = ".glb,.gltf,.obj,.stl,.ply"; fileIn.style.fontSize = "11px";
        fileIn.onchange = async () => {
          const f = fileIn.files?.[0]; if (!f) return;
          const at = d.lastPoint();                       // read once, at change time
      const eN = at ? at.x : 0, nN = at ? -at.z : 0;
          await withLoading(d.container, `importing ${f.name} + republishing`, async () => {
            try {
              const res = await d.api.importContent(d.projectId!, f, { category: catIn.value.trim() || undefined, e: eN, n: nN });
              const state = await d.waitForPublish(d.projectId!);
              if (state === "done") { await d.loadProjectModel(); d.notify(`imported as ${res.category} (${res.ifc_class}, ${res.faces} faces)`, "success"); }
              else d.notify(`imported — publish ${state}`, state === "error" ? "error" : "info");
              await d.reloadModelPins();
            } catch (err) { d.notify(`import failed: ${(err as Error).message}`, "error"); }
            finally { fileIn.value = ""; }
          });
        };
        imp.append(impLbl, catIn, fileIn); body.appendChild(imp);

        // searchable unified list — supports `type:` / `class:` / `category:` / `discipline:` operators
        const search = document.createElement("input"); search.className = "portal-filter";
        search.placeholder = "Search — or type:wall · class:ifccolumn · category:furniture · discipline:…";
        search.style.cssText = "width:100%;margin:2px 0 6px;font-size:12px";
        const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:3px;max-height:340px;overflow:auto";
        const mkBtn = (it: LibItem) => {
          const b2 = document.createElement("button"); b2.className = "mini-btn";
          b2.style.cssText = "text-align:left;width:100%";
          b2.innerHTML = `${it.label} <span class="meta" style="font-size:10px">— ${it.sub}</span>`;
          b2.onclick = () => { void it.onPlace().then(() => draw(search.value)); };
          return b2;
        };
        // parse a query into free terms + field:value operators (type→label/key, class→ifc class,
        // category→group, discipline→best-effort over the full search string)
        const matches = (it: LibItem, q: string): boolean => {
          for (const tok of q.trim().toLowerCase().split(/\s+/).filter(Boolean)) {
            const m = /^(type|class|category|cat|discipline|disc|tag):(.+)$/.exec(tok);
            if (m) {
              const [, op, val] = m;
              const ok = op === "type" ? (it.label.toLowerCase().includes(val!) || it.key.includes(val!))
                : op === "class" ? it.cls.includes(val!)
                : (op === "category" || op === "cat") ? it.cat.includes(val!)
                : it.search.includes(val!);            // discipline/tag → full-text fallback
              if (!ok) return false;
            } else if (!it.search.includes(tok)) return false;
          }
          return true;
        };
        const draw = (q: string) => {
          list.innerHTML = "";
          const ql = q.trim();
          if (!ql) {
            const recentKeys = readRecent();
            const recent = recentKeys.map((k) => items.find((it) => it.key === k)).filter(Boolean) as LibItem[];
            if (recent.length) {
              const h = document.createElement("div"); h.className = "meta"; h.style.cssText = "font-size:10px;opacity:.7;margin-top:2px";
              h.textContent = "RECENT"; list.appendChild(h);
              for (const it of recent) list.appendChild(mkBtn(it));
              const sep = document.createElement("div"); sep.className = "meta"; sep.style.cssText = "font-size:10px;opacity:.7;margin-top:4px";
              sep.textContent = "ALL"; list.appendChild(sep);
            }
          }
          const shown = items.filter((it) => !ql || matches(it, ql));
          for (const it of shown) list.appendChild(mkBtn(it));
          if (!shown.length) { const n = document.createElement("div"); n.className = "meta"; n.textContent = "No items match."; list.appendChild(n); }
        };
        search.oninput = () => draw(search.value);
        body.append(search, list);
        draw("");
      });
    }));
    contentBtn.title = "Browse + place the unified library — content parts (site logistics / furniture / "
      + "landscaping) and family types — search by name, IFC class, or category, then click to place at an "
      + "E,N point. Logistics time-phase on the 4D slider.";

  return { contentBtn };
}
