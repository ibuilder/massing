"""
The baked-geometry cache is bounded by BYTES, not by a count of models.

A cap of four was never a size. Four small houses are a few megabytes; four towers are several
gigabytes, and a count reports "4" for both. A limit that cannot tell those apart is not bounding
anything — it is a number that happens to be small most of the time.

Built on the standard library on purpose. `cachetools` would have saved about twenty lines and cost a
dependency plus a lockfile round trip; the cross-worker half of this work still wants `diskcache`,
where writing a lock-correct disk cache by hand is the worse trade.
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

import numpy as np  # noqa: E402

from aec_data import drawings as d  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


class Mesh:
    def __init__(self, n):
        self.vertices = np.zeros((n, 3))                    # 24 bytes/vertex
        self.faces = np.zeros((max(1, n // 2), 3), np.int32)  # 12 bytes/face


def meshes(n):
    return [("g", "e", Mesh(n))]


def reset():
    d._BAKE_CACHE.clear()


def put(key, n):
    m = meshes(n)
    d._BAKE_CACHE[key] = (object(), m, d._mesh_bytes(m))
    d._evict_to_budget()


# --- measurement ----------------------------------------------------------------------------------
check("a bigger mesh measures bigger", d._mesh_bytes(meshes(1000)) > d._mesh_bytes(meshes(10)))
check("an empty set measures zero", d._mesh_bytes([]) == 0)
check("a mesh with no arrays does not crash the budget",
      d._mesh_bytes([("g", "x", object())]) == 0, "an unmeasurable entry counts as 0, never as an error")

# --- the byte budget actually evicts ----------------------------------------------------------------
reset()
d._BAKE_CACHE_BYTES, saved_b = 10_000, d._BAKE_CACHE_BYTES
d._BAKE_CACHE_MAX, saved_c = 99, d._BAKE_CACHE_MAX
for i in range(6):
    put(f"k{i}", 100)                       # ~3.6 KB each
check("byte budget evicts before the count cap does",
      len(d._BAKE_CACHE) < 6 and sum(e[2] for e in d._BAKE_CACHE.values()) <= 10_000,
      f"kept {len(d._BAKE_CACHE)} entries")
check("eviction is oldest-first", "k0" not in d._BAKE_CACHE and "k5" in d._BAKE_CACHE)

# --- the count cap still applies for many tiny models ------------------------------------------------
reset()
d._BAKE_CACHE_BYTES, d._BAKE_CACHE_MAX = 10**9, 3
for i in range(8):
    put(f"t{i}", 2)
check("a huge byte budget does not let tiny entries accumulate forever",
      len(d._BAKE_CACHE) <= 3, f"kept {len(d._BAKE_CACHE)}")

# --- the refusal that keeps a cache from becoming a tax ------------------------------------------------
reset()
d._BAKE_CACHE_BYTES, d._BAKE_CACHE_MAX = 1_000, 4
put("huge", 5000)                            # far over the whole budget on its own
check("a model bigger than the entire budget is still SERVED", len(d._BAKE_CACHE) == 1,
      "evicting it immediately would re-tessellate on every view — a cache that costs instead of saves")

# --- observability ------------------------------------------------------------------------------------
d._BAKE_CACHE_BYTES, d._BAKE_CACHE_MAX = saved_b, saved_c
st = d.bake_cache_stats()
check("the cache can be measured, not just assumed",
      {"entries", "bytes", "budget_bytes", "max_entries"} <= set(st))
reset()

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_bake_budget OK")
