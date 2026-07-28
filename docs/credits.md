# Credits

Massing is built on open-source work. This page exists because we turned off one library's in-app
attribution mark, and an attribution you remove from the screen you owe somewhere else.

## That Open Company — the viewer stack

[`@thatopen/components`](https://github.com/ThatOpen/engine_components),
[`@thatopen/fragments`](https://github.com/ThatOpen/engine_fragments),
`@thatopen/components-front`, `@thatopen/ui` — Apache-2.0 / MIT.

**This is the engine under the 3D viewer.** Fragments is the streaming geometry format the whole
"never parse IFC in the browser" architecture depends on; components provides the world, camera,
culling and highlighting. Without it there is no viewer.

`@thatopen/components` shows a small That Open Company logo in the corner of the renderer by default
(`renderer.showLogo`). We set it to `false` in `apps/web/src/viewer/world.ts` — the library's own
documentation names "white-label embed, customer-branded surface" as a legitimate reason, and that is
this case. The docs also ask you to consider leaving it on, because the mark is how the team behind a
free stack gets found. That is a fair ask, and this page is the answer to it: the credit moved, it
did not vanish.

If you build on Massing, or on this stack directly, go and look at what they publish. It is
genuinely good engineering and it is given away.

## Also relied on

- **[web-ifc](https://github.com/ThatOpen/engine_web-ifc)** (MPL-2.0) — the WASM IFC parser behind
  server-side conversion.
- **[IfcOpenShell](https://ifcopenshell.org/)** (LGPL-3.0) — the IFC toolkit the Python services are
  built around: authoring recipes, QTO, validation, drawings.
- **[three.js](https://threejs.org/)** (MIT) — the renderer.
- **[pdf.js](https://mozilla.github.io/pdf.js/)** (Apache-2.0) and **[pdf-lib](https://pdf-lib.js.org/)**
  (MIT) — 2D sheet viewing and markup flattening.
- **[FastAPI](https://fastapi.tiangolo.com/)**, **[SQLAlchemy](https://www.sqlalchemy.org/)**,
  **[Alembic](https://alembic.sqlalchemy.org/)** (MIT / BSD) — the API and its migrations.
- **[Vite](https://vitejs.dev/)** and **[TypeScript](https://www.typescriptlang.org/)** (MIT /
  Apache-2.0) — the web build.

Licence texts travel with each package in `node_modules/` and the Python environments; nothing here
replaces them. This is the human-readable half.
