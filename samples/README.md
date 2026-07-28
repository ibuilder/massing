# Sample library

Showcase projects, each a **`.mass` container** — the same portable format the product exports and
imports (`services/api/src/aec_api/bundle.py`). A `.mass` is a ZIP holding the geometry, every data
table, and the blobs; it documents itself with a `manifest.json` and a README inside.

## Why containers and not `.ifc` / `.frag`

"Load a sample" used to mean one of three bare `.frag` files. You could orbit the model, and that was
the entire demonstration — no estimate, no schedule, no RFIs, no drawings. Every number this product
exists to produce was missing from the thing meant to show it off.

A container carries all of it, so a sample now opens as a *project*, not a mesh.

## How a sample is served

`GET /samples` lists this directory, describing each container **from its own manifest** — there is
no separate catalog file to maintain, because a catalog beside the artifacts is a promise while the
manifest is a measurement. `POST /samples/{id}/open` opens one as a new project through
`bundle.import_bundle`, the identical path a user's own `.mass` takes. A demo that ran through its
own private code path would, sooner or later, demonstrate behaviour the product does not have.

Point the library elsewhere with `AEC_SAMPLES_DIR`.

## Adding one

```bash
cd services/api && ./.venv/Scripts/python.exe build_samples.py --project <pid> --out ../../samples
```

Then confirm it lists correctly — the catalog reads the real file, so a mis-packaged container shows
up as `readable: false` rather than silently looking fine:

```bash
cd services/api && PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe -X utf8 test_samples.py
```

## Conventions

- **Filename is the id.** Keep it lowercase, `-` or `_` separated, ending `.mass`.
- **The display name comes from the manifest**, not the filename, so renaming a file never renames
  the project a visitor sees.
- **Keep them small.** These are checked in and downloaded by first-time visitors; containers above
  a few MB belong in release assets instead. Anything over 256 MB is refused outright as a packaging
  mistake.
- **No client data.** Everything here is public the moment it is committed — this repo is public.
  Samples must be synthetic or genuinely open, and must not carry a real address, a real party name,
  or a real contract value.
