# Licensing notes (third-party components)

> **This project's own code is MIT-licensed (see [`LICENSE`](LICENSE)).** The notes below cover
> the third-party components it composes and the distribution boundaries to keep.


This platform composes components under different licenses. The key rule: keep the **GPL**
desktop editor a separate process you *use*, not code you statically link into a proprietary
product.

> **This table is now checked, not just written.** `apps/web/scripts/check-licences.mjs` reads every
> npm package's **LICENSE file** — not its badge or its `package.json` field — and fails the build on
> a forbidden licence or on a package whose file disagrees with its declaration. That gate exists
> because this very table was wrong: it grouped `web-ifc` with the MIT `@thatopen/*` packages as
> "MIT-style", and `web-ifc` is **MPL-2.0**. A summary of a licence is not the licence.

| Component | License | Implication |
|---|---|---|
| Blender + Bonsai (desktop editor) | **GPL** | Run as a separate process/tool. Do not link its code into a closed product. Bonsai-MCP drives it over a socket — that boundary keeps it separate. |
| IfcOpenShell core | **LGPL** | Dynamic linking OK; keep it replaceable. Used in `services/data` and `apps/editor-bridge` recipes. |
| That Open Engine (`@thatopen/components`, `-front`, `fragments`, `ui`) | MIT | Permissive; fine in the web viewer and converter. Verified from each package's declared licence — none ships a LICENSE file. |
| **web-ifc** | **MPL-2.0** | **Weak (file-level) copyleft, NOT "MIT-style".** Using it unmodified — which is what we do, it is a vendored WASM build — carries no obligation beyond attribution. **Modifying an MPL file obliges you to publish that file's source.** So keep local patches out of it: fix upstream or wrap it. |
| Bonsai-MCP | MIT | Permissive. |
| xeokit SDK (if you switch viewers) | Custom | Check its own terms before use. |

Distribution model to confirm:
- Web viewer + services (permissive/LGPL) can ship as your product.
- The desktop editor (GPL) is installed and used by the firm, not redistributed inside your
  proprietary build.
- The optional Autodesk APS bridge is a paid cloud dependency — surface cost per translation
  in the UI; no source-license concern, but a commercial one.
