# Massing for Revit (pyRevit extension)

A free, open **Revit → Massing** bridge — publish the active Revit model into Massing in one click,
**without the paid Autodesk APS bridge**. It uses Revit's built-in IFC exporter and Massing's REST
API, so your model flows straight into the Massing BIM viewer / GC portal / proforma.

Built on the [pyRevit StarterKit](https://www.learnrevitapi.com/) conventions, so it's familiar to the
LearnRevitAPI community.

## What's in the `Massing` tab

| Button | What it does |
|--------|--------------|
| **Publish to Massing** | Exports the active document to IFC (built-in exporter), uploads it, runs the server-side Fragments conversion, then offers to open it in the web viewer. Re-publishing the same project name updates it. |
| **Open in Massing** | Opens the current model's Massing project in the web viewer. |
| **Sync Issues (BCF)** | Round-trips RFIs / clashes / punch pins with Massing over the open **BCF** standard (download a `.bcfzip` or upload one). Issues are keyed by IFC GlobalId, so pins land on the right elements both ways. |
| **Settings** | Stores the Massing **API URL**, **web app URL**, **API key**, and a default project name (per-user, in pyRevit config). |

## Install

1. Install [pyRevit](https://github.com/eirannejad/pyRevit) (free).
2. Register this extension folder:
   ```
   pyrevit extend ui Massing "<path-to>/integrations/pyrevit/Massing.extension"
   ```
   …or drop `Massing.extension/` into a folder on your pyRevit *Extensions* search path and reload.
3. Reload pyRevit → a **Massing** tab appears.

## Configure

Click **Massing ▸ Settings** and enter:
- **API URL** — your Massing API, e.g. `https://your-host/api` (or `https://massing.build/api`).
- **App URL** — the web app origin for "Open in Massing" links, e.g. `https://massing.build`.
- **API key** — a Massing bearer token. **REST API access is a Commercial-plan (and up) entitlement**
  — see Settings ▸ Massing licence in the web app, or massing.cloud/docs.

The manual path (export IFC from Revit → upload in the web app) stays free on any plan; this one-click
bridge uses the API and therefore needs a Commercial licence.

## Notes
- Engine-agnostic: works on pyRevit's IronPython 2.7 and CPython 3 engines (std-lib only — no `requests`).
- The bridge never reads `.rvt` directly; it exports IFC via Revit, honoring Massing's "IFC is the
  source of truth" model.
- Client code: `Massing.extension/lib/massing_api.py` (covered by `services/api/test_revit_bridge.py`).
