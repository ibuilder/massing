# Module plugin system — rooms as directories, third-party registers

**Date:** 2026-07-30 · **Status:** PLAN. Nothing built. Every number below was read from the code, not
recalled. **Internal** — `docs/` is the Pages web root.

Goal, in the user's words: *a plugin system similar to WordPress and Joomla* — the file tree broken out
by room, so a user can drop a custom module into the appropriate room directory and the program
recognises it. Activation/deactivation is explicitly deferred to a later phase.

---

## 0. What already exists (verified, not assumed)

| Thing | State | Where |
|---|---|---|
| Plugin model for **authoring recipes** | **Built and mature** | `plugin_registry.py`, `plugins/example-wall-brand/` |
| Module (register) discovery | Flat, single directory, one level | `modules_registry.load_registry()` |
| Module dir override | `AEC_MODULES_DIR` (used by the frozen desktop build) | `modules_registry.py:26` |
| Room of a module | Derived from its **`section`**, via one table | `rooms.ROOM_OF_SECTION` |
| Plugin sandboxing | On the roadmap, unbuilt | `SEC-PLUGIN-SANDBOX`, Lane C |

**`plugin_registry.py` is the precedent to copy, not to reinvent.** It already solved the hard part for
recipes, and its three gates are exactly the ones a module pack needs:

1. **Opt-in.** Discovery is off unless `AEC_PLUGINS_ENABLED=1` — never on by default.
2. **API-version gate.** The manifest declares `api_version`; a MAJOR mismatch refuses the plugin with
   a reason rather than loading something built against a different contract.
3. **Namespace + collision refusal.** A key that already exists is *refused*, never silently
   overwritten, and refusals are returned **and** logged — a half-loaded set is visible, not silent.

A module pack differs from a recipe plugin in one important way: **it ships data, not code.** A
`module.json` is declarative, so the arbitrary-code risk that makes recipe plugins opt-in does not
apply. That argues for module packs being discoverable by default while *code* plugins stay gated —
but see §6, because "declarative" is doing real work in that sentence and deserves a check.

---

## 1. The decision everything else depends on

**Today a module's room comes from its `section`, through one table.** `rooms.py` states the reasoning
explicitly, and it is good reasoning: a room is a property of the section, not of each module, so one
readable table decides the allocation and an editing slip cannot put a module in two rooms.

**A directory-based tree contradicts that**, and the contradiction cannot be papered over — it would be
a *third* encoding of one fact (directory, `section`, `ROOM_OF_SECTION`), which is the drift shape this
repo has paid for repeatedly.

So one of them must become authoritative, and for a plugin system **the directory has to win**:

> A third-party module dropped into `modules/design/` must be reachable **without editing a core
> table**. If `ROOM_OF_SECTION` stays authoritative, every third-party module needs a line added to a
> file inside the product to appear at all — which is not a plugin system, it is a patch.

That is the decisive argument, and it inverts the R26 decision deliberately rather than by accident.
What changes:

- **The directory names the room.** `modules/<room>/<key>/module.json`.
- **`section` stays**, demoted to what it always described in practice: a **sub-group within a room**
  (Design → BIM · Engineering · Specifications …). It keeps its role in the rail and in future
  sub-rooms, and loses its role in room allocation.
- **`ROOM_OF_SECTION` is retired**, and `rooms.py` keeps `ROOMS` (the seven rooms, their labels and
  jobs) plus a new validator: every section appears under exactly one room directory. A section
  appearing under two rooms is now the failure mode, and it is the one worth a gate.

**The R26 argument survives the inversion.** Its real content was *"one canonical home per module,
derived from one place, never stored twice"* — that still holds; the one place is now the path. The
duplication it warned against would be reintroduced only if we kept both.

---

## 2. Layout

```
services/api/modules/                 ← core registers, shipped
  deal/          acquisition/ …       ← <room>/<key>/module.json
  design/
    rfi/module.json
    submittal/module.json
  planning/  schedule/  cost/  operate/  work/
  _shared/                            ← reserved: cross-room fragments, never a room

<user data dir>/modules/              ← third-party packs, discovered, never shipped
  design/
    acme-daily-brief/
      module.json
      pack.json                       ← optional manifest; see §3
```

`_shared/` is reserved from the start precisely so nobody later invents `common/` and `shared/` in
parallel. A directory whose name is not a known room id is a **refusal with a reason**, not a silent
skip — the same rule as an unmapped section today.

---

## 3. Manifest

A single `module.json` needs no manifest — the point is that dropping one file in a room directory
works. A **pack** (several modules shipped together, or anything wanting a version) adds `pack.json`,
mirroring `plugin.json`:

```jsonc
{
  "name": "acme-field-pack",
  "version": "1.2.0",
  "api_version": "1.0",        // MAJOR must match MODULE_API_VERSION, as plugin_registry does
  "modules": ["acme-daily-brief", "acme-toolbox"],
  "author": "Acme",
  "description": "Field registers for Acme's daily routine."
}
```

`MODULE_API_VERSION` is a **new constant, distinct from `PLUGIN_API_VERSION`**: the module-config
contract (field types, workflow shape, `tools`, `columns`) versions on its own schedule and pretending
otherwise would force a lockstep neither side wants.

---

## 4. Discovery

`load_registry()` becomes:

1. Walk `<root>/<room>/<key>/module.json` for each **known room id**, for each root in the search path.
2. Search path = core `MODULES_DIR`, then the user data dir, then `AEC_MODULES_DIR` if set.
3. **Later roots cannot override earlier ones.** A third-party module whose `key` collides with a core
   register is **refused with a reason**, exactly as `plugin_registry` refuses a recipe collision.
   Silent override is how a plugin quietly replaces the RFI register.
4. Every refusal is collected and exposed on `GET /modules/health` — not only logged. A half-loaded
   registry that looks complete is the failure this design most needs to avoid.

**Two things in the loader break and must change with it**, both verified:

- `validate_module(..., folder=mj.parent.name)` asserts `key == folder`. Still correct under the new
  layout — the folder is still the key — but `known_modules` is built from a one-level glob and must
  become the union across rooms and roots.
- `MODULES_DIR.glob("*/module.json")` appears in the **loader and in four test files**
  (`test_module_rooms`, `test_module_config`, `test_module_fields`, `test_module_tables`). Each reads
  the tree directly, on purpose — they are the gates that read reality rather than a copy. All four
  need the two-level walk, and that is a feature: they will fail loudly the moment the layout changes
  under them.

---

## 5. Activation / deactivation *(deferred, sketched so the data model does not preclude it)*

Deliberately **not** built now. The shape it must not preclude:

- Activation is **per project**, not global — one firm's projects legitimately differ.
- State lives in a table, not on disk: a module's presence is a *fact about the install*, its activation
  is a *fact about the project*.
- **Deactivation must never delete data.** A deactivated module's records stay; the register leaves the
  rail and its routes 404 with "deactivated", not "unknown".
- **A core register cannot be deactivated** while another module holds a `reference` to it — the
  reference graph already exists (`module_graph.build`) and is the check.

---

## 6. What this costs, honestly

- **133 modules move.** One mechanical commit, but it rewrites every path in the repo's most-read
  directory and will conflict with anything in flight touching `module.json`.
- **`ROOM_OF_SECTION` retires**, and `test_module_rooms.py` — which asserts the allocation by module
  name — becomes an assertion about *directories*. That gate was strengthened deliberately two days
  ago; it must be re-pointed, not weakened.
- **The demo capture regenerates** (`demoData.json` holds `/modules` and `/rooms`).
- **"Declarative" is doing real work.** A `module.json` is data, but it drives table creation
  (`mod_<key>`), FTS indexes, and a Postgres migration requirement. A third-party module therefore
  **creates a table at runtime**, which is the actual risk here — not code execution. It needs its own
  answer (a name prefix per pack, a row/table quota, or admin-gated install) and that answer is
  `SEC-PLUGIN-SANDBOX`'s sibling, not a footnote to it.

---

## 7. Sequencing, and a lane problem worth naming

The roadmap's lanes are disjoint **by path**. This work is not:

| Step | Touches | Lane |
|---|---|---|
| `R32-PLUGIN-DISCOVER` — two-level walk, search path, collision refusal, health surface | `modules_registry.py`, `rooms.py` | **C** |
| `R32-PLUGIN-TREE` — move 133 modules into room dirs; re-point the four gates | `services/api/modules/**`, the gates | **H** |
| `R32-PLUGIN-MANIFEST` — `pack.json`, `MODULE_API_VERSION`, refusal reasons | `modules_registry.py` | **C** |
| `R32-PLUGIN-TOGGLE` — per-project activation | new table, router, rail | **C + G + A** |

`R32-PLUGIN-DISCOVER` must land **before** `R32-PLUGIN-TREE` and must accept **both** layouts for one
release. Otherwise the move is a flag day: every gate fails at once and the only way through is a
single enormous commit — which is exactly the change nobody can review.

`R32-PLUGIN-TOGGLE` spans three lanes and should be split before it is scheduled, not while it is
being built.
