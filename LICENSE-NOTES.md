# Licensing notes (confirm with counsel before distributing)

This platform composes components under different licenses. The key rule: keep the **GPL**
desktop editor a separate process you *use*, not code you statically link into a proprietary
product.

| Component | License | Implication |
|---|---|---|
| Blender + Bonsai (desktop editor) | **GPL** | Run as a separate process/tool. Do not link its code into a closed product. Bonsai-MCP drives it over a socket — that boundary keeps it separate. |
| IfcOpenShell core | **LGPL** | Dynamic linking OK; keep it replaceable. Used in `services/data` and `apps/editor-bridge` recipes. |
| That Open Engine (`@thatopen/*`, web-ifc) | MIT-style | Permissive; fine in the web viewer and converter. |
| Bonsai-MCP | MIT | Permissive. |
| xeokit SDK (if you switch viewers) | Custom | Check its own terms before use. |

Distribution model to confirm:
- Web viewer + services (permissive/LGPL) can ship as your product.
- The desktop editor (GPL) is installed and used by the firm, not redistributed inside your
  proprietary build.
- The optional Autodesk APS bridge is a paid cloud dependency — surface cost per translation
  in the UI; no source-license concern, but a commercial one.
