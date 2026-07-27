# Caching for a platform whose data is large and getting larger

Researched 2026-07-27 at v0.3.720, prompted by a simpler question — "shared cache or worker
affinity?" — that turned out to be the wrong first question.

## The headline: our caches bound the wrong quantity

```python
@lru_cache(maxsize=8)          # ifc_loader — 8 MODELS
_BAKE_CACHE_MAX = 4            # drawings   — 4 BAKED SETS
```

Both bound a **count**. Neither bounds **bytes**. An IFC model in this product might be 8 MB or
2 GB, so "8 models" is somewhere between 64 MB and 16 GB of resident memory for the same configured
value — and it is per worker, so multiply by `UVICORN_WORKERS`. The number in that decorator does not
mean anything you can plan capacity against.

This is the standard failure and the fix is standard too. [cachetools] exists precisely for it: a
cache's size is the **total size of its items**, with an item's size given by a `getsizeof` function,
and `maxsize` counting items only in the trivial case. Its own documentation makes the point that
`maxsize` "says nothing about payload weight — one entry could be tiny, another huge", which is
exactly our situation.

**Sizing was never the lever.** Raising `maxsize` (the performance report's advice) makes a
byte-unbounded cache hold more unbounded things. The lever is changing *what* is bounded.

## The two caches are not the same problem

| | holds | shareable across processes? | the real answer |
|---|---|---|---|
| `ifc_loader._open_cached` | `ifcopenshell.file` — a live C-extension handle over an open file | **No.** Not serialisable; sharing means a separate loader process answering queries over IPC | bound by **bytes**, hold **fewer**, and make re-opening cheap |
| `drawings._BAKE_CACHE` | `trimesh` meshes, keyed by `id(model)` | **Yes** — geometry serialises | bound by bytes **and** share it |

And the ordering insight, which is the thing worth taking away: **baking is the expensive half.**
Models are held open largely to avoid re-tessellating. Share the baked geometry and the pressure to
keep many models resident drops — the unshareable cache stops being the thing you have to solve.

That is why "bounded shared cache" is the better call: not because it beats affinity head-to-head,
but because it applies to the layer that actually costs, and shrinks the layer that cannot be shared.

Note the current bake key is `id(model)` — object identity, so inherently per-process. A shared cache
needs a **content key** (file hash + geometry-settings version). That is a real change, and an
improvement regardless: the existing key already needs an identity check to guard `id()` reuse.

## What upstream says about large IFC

There is no partial-parse switch to flip. The IfcOpenShell community's own position is that at
1 GB-plus, IFC wants treating **as a database** — portions queried rather than the file loaded — with
columnar/lazy/zero-copy work discussed rather than shipped, and a RocksDB storage backend alongside
in-memory. Their guidance on optimisation is about allocation size and frequency, contiguity and
delaying text-to-binary parsing.

The practical reading for us: **do not plan around holding many large models open.** Plan around
holding few, and around derived artifacts being cheap to produce or already computed. A model-level
`--purge`-style eviction under memory pressure is more useful than a bigger cache.

## Crossing the worker boundary

For the shareable half, the options in order of fit:

* **[diskcache]** — SQLite + memory-mapped files, multiprocess-safe, **no server process**, designed
  for gigabytes of binary blobs. This is the closest match: our deployments must run offline, and it
  adds no daemon.
* **Redis** — we already have `AEC_REDIS_URL` (the rate limiter uses it), so the config exists. But it
  is optional by design, requires serialisation over a socket, and making geometry depend on it would
  cost the single-binary desktop build.
* **`multiprocessing.shared_memory`** — zero-copy and stdlib, but you own the layout, the lifetime and
  the cleanup. Right for fixed-shape numeric buffers; wrong for a heterogeneous mesh set.
* **mmap of the artifact on disk** — worth remembering that if the derived form is written to a file,
  the OS page cache already shares it across workers for free.

**Recommendation: diskcache for shared derived geometry, keyed by content hash.** Redis stays what it
is now — an optional accelerator for counters, not a dependency the viewer needs.

## The rest of the data — and it is bigger in aggregate

Records, not models, are the larger total: 132 schema-driven modules × projects × history. It is JSON
over HTTP, which is a different cache with different tools.

**What we already do** (`vite.config.ts` Workbox): `CacheFirst` for the engine bundles, the WASM, and
`.frag` geometry. That is the binary half and it is correct — content-hashed, immutable, exactly what
`CacheFirst` is for.

**The gap is the JSON.** No runtime caching for API reads at all, so every panel refetches. The
research is unambiguous on the split:

* **Cache API** — keys are Requests, values are Responses; right for binary and content-addressed
  blobs. That is our `.frag` case, already done.
* **IndexedDB** — the workhorse for **app data**: large structured sets, complex queries,
  transactions. That is our records case, and the vendored kernel already ships `storage-browser`
  (IndexedDB) — so the mechanism is in the build and unused for this.
* **`stale-while-revalidate`** — serve the cached copy instantly, refresh in the background. The
  consensus default for API reads, and the right fit for a records list that is usually unchanged.
* **Cache the parsed object, not the string.** Re-parsing large JSON repeatedly is its own cost.

One caution that matters for us specifically: a cached record list must never be presented as
authoritative when it is stale — this codebase has spent a whole cycle on signals that measured
something other than what they claimed. Stale-while-revalidate is fine; stale-and-silent is not. Any
cached view needs to say it is cached.

## Recommendations, in order

1. **Make both server caches byte-bounded, with an explicit total budget** — `AEC_MODEL_CACHE_MB`,
   defaulting to something a small host survives. Capacity you can reason about, instead of a count
   that means nothing. *Needs `cachetools` — a new dependency, MIT, and your approval.*
2. **Re-key the bake cache by content** (file hash + settings version) rather than `id(model)`.
   Prerequisite for sharing, and removes the `id()`-reuse fragility either way.
3. **Share baked geometry across workers via diskcache.** *New dependency, Apache-2.0, your approval.*
4. **Add `stale-while-revalidate` + IndexedDB for module records**, using the kernel's
   `storage-browser` that is already vendored. Cached views must be visibly cached.
5. **Only then revisit worker affinity** — by that point it may not be worth doing, which is the best
   outcome available.

## What not to do

* **Do not raise `maxsize`.** It is the reflex, it is what the analyser advised, and it makes an
  unbounded cache hold more.
* **Do not preallocate a fixed arena up front.** Tempting given the sizes, but Python objects are not
  placed into arenas by us, and a fixed reservation would be idle memory on the small deployments this
  product also has to run on. The budget should be a *ceiling that evicts*, not a *block that is
  claimed*.
* **Do not make geometry depend on Redis.** It would cost the offline guarantee and the single-binary
  desktop build, for a benefit diskcache provides without a daemon.

## Sources

- [cachetools — size-aware caching](https://cachetools.readthedocs.io/en/latest/)
- [cachetools in production: policies, TTLs, keying](https://thelinuxcode.com/cachetools-module-in-python-practical-caching-policies-ttls-keying-and-production-patterns/)
- [Strategies for large IFC datasets (IfcOpenShell #2025)](https://github.com/IfcOpenShell/IfcOpenShell/issues/2025)
- [Addressing core IfcOpenShell issues — OSArch](https://community.osarch.org/discussion/3386/addressing-some-core-ifcopenshell-issues)
- [IFC file handling internals](https://deepwiki.com/IfcOpenShell/IfcOpenShell/2.1-ifc-file-handling)
- [Understanding Python multi-process memory management](https://luis-sena.medium.com/understanding-and-optimizing-python-multi-process-memory-management-24e1e5e79047)
- [Sharing state across gunicorn workers](https://github.com/benoitc/gunicorn/discussions/3017)
- [PWA offline storage: IndexedDB and Cache API](https://dev.to/tianyaschool/pwa-offline-storage-strategies-indexeddb-and-cache-api-3570)
- [Building offline-first web apps: service workers, IndexedDB, sync](https://letsbuildsolutions.com/blog/web-engineering/building-offline-first-web-applications-service-workers-indexeddb-and-sync-strategies-for-production/)
- [Configuring JavaScript caches — Datadog](https://www.datadoghq.com/blog/javascript-cache/)
- [Browser caches as a database — a decision guide](https://medium.com/@bhagyarana80/browser-caches-as-a-database-e74462c18284)

[cachetools]: https://cachetools.readthedocs.io/en/latest/
[diskcache]: https://grantjenks.com/docs/diskcache/
