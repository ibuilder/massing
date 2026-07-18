# Massing plugins — server-side authoring recipes

A plugin adds **namespaced, GUID-stable authoring recipes** to the platform. Once loaded, a plugin
recipe (`<plugin>.<recipe>`) is drivable from every authoring surface — `POST /projects/{pid}/edit`,
the CAD command line, the AI command bar, MCP `run_recipe` — and appears in the
[authoring matrix](../docs/authoring-matrix.md) automatically.

## Enable

Plugins execute Python at load, so discovery is **off by default**:

```bash
AEC_PLUGINS_ENABLED=1          # opt in
AEC_PLUGINS_DIR=/path/to/plugins   # optional; defaults to this directory
```

`GET /plugins` shows what loaded and what was refused (with reasons). `POST /plugins/reload`
(platform-admin) re-discovers without a restart.

## Write one

Copy [`example-wall-brand/`](example-wall-brand/). A plugin is a directory with:

- **`plugin.json`** — the manifest. Required: `name` (alphanumeric + `-`/`_`), `version`, and
  `api_version` whose **major** must match the host's `PLUGIN_API_VERSION` (currently `1.0`) — a
  mismatch refuses the plugin with a clear reason rather than loading against the wrong contract.
- **`plugin.py`** (or `entry` in the manifest) — exposes `register(api)`:

```python
def my_recipe(model, params):
    ...                        # mutate the open ifcopenshell model IN PLACE (GUID-stable)
    return {"changed": 1}      # a summary, same contract as every core recipe

def register(api):
    api.register_recipe("my_recipe", my_recipe, category="properties", produces="IfcPropertySet")
```

Rules the loader enforces:
- recipes are namespaced `<plugin>.<name>`; a key collision is **refused, never overwritten**;
- a broken plugin is refused with its error and rolled back — it never blocks the others;
- reload is idempotent — the previous load's registrations are replaced.

Your recipe's params go through the same authoring guardrails (`aec_data.guards.precheck`) as core
recipes: coordinates must be finite `[E, N]` metres, dimensions positive, etc. Build on the host's
primitives (`from aec_data import edit`, `edit_core`) rather than re-inventing IFC plumbing.
