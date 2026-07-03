# External IFC family libraries (curated, free)

`library.ifc` (one level up) is the **generated** parametric core library that ships with the platform —
fully offline, our own content, no licensing constraints. This folder is for **curated free external
openBIM content** you can drop in and import.

Any `.ifc` file placed in this folder is listed by `GET /families/library` and can be imported into a
project via `POST /projects/{pid}/families/import` (which copies every `IfcTypeProduct` in, deduped by
class + name, and makes it placeable).

## Vetted free sources

| Source | Content | License | URL |
|---|---|---|---|
| buildingSMART sample files | Reference IFC models / components | Open (per file) | https://github.com/buildingSMART/Sample-Test-Files |
| opensourceBIM/IFC-files | Community IFC building models | CC BY-ND | https://github.com/opensourceBIM/IFC-files |
| NBS National BIM Library | ~5,000 generic + manufacturer objects (IFC) | Free account | https://www.nationalbimlibrary.com/ |
| buildingSMART Data Dictionary (bSDD) | Property/classification definitions (not geometry) | Free API | https://www.buildingsmart.org/users/services/buildingsmart-data-dictionary/ |
| FreeCAD BIM | Parametric door/window templates | LGPL | https://wiki.freecad.org/BIM_Workbench |

## Notes
- **Licensing:** verify each file's license before committing it here. NoDerivatives (ND) content may be
  redistributed with attribution but not modified; account-gated libraries (NBS) are per-user.
- To regenerate the core library after editing `families.CATALOG`:
  `PYTHONPATH=src ./.venv/Scripts/python.exe -m aec_data.build_family_library`
- Manufacturer content is mostly Revit-first; convert to IFC before importing.
