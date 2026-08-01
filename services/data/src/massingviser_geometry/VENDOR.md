# Vendored: `bvh.py` from `MassingCloud/massingviser`

`src/massingviser/geometry/bvh.py`, copied **verbatim** at commit
`fec3854ccacdcd09d8a2583cbdbf972804016026` (2026-08-01). **MIT** — `LICENSE` in this directory.

Self-contained: stdlib plus `numpy`, which this service already depends on. **No new dependency.**

## What it is

A bounding-volume hierarchy — median split on the longest axis — so the *server* can answer spatial
questions. Three operations, one tree descent each:

| | |
|---|---|
| `query_aabb` / `raycast` | picking — what is under this ray |
| `query_frustum` | culling — what is inside this camera |
| `overlapping_pairs` | broad-phase clash between two sets, by dual-tree descent |

All three return **labels**, and we build it with GlobalIds as the labels — so an answer is already in
the identity that markup, cost and coordination key on, with no lookup table in between. That is the
reason this file was worth taking rather than writing: it agrees with the project's first
non-negotiable by construction.

## Why only this one file

The rest of `massingviser/geometry/` is **not** vendored, and one omission is deliberate rather than
incidental: `payload.py` defines a flat binary mesh format of its own ("MVMS"). Adopting it would put a
second geometry format beside Fragments, which is this platform's format end to end. The sibling
project `massingifc` reached the same conclusion from the other direction — its engine bridge carries
`.frag` bytes rather than re-encoding, because re-encoding means decoding geometry the engine decodes
better and discarding the per-element addressing Fragments already has. A spatial index is a real gain;
a competing binary format is a cost with no matching benefit.

`lod.py` (vertex-clustering decimation) is a genuine gap here and is tracked separately — it needs a
serving tier and a client swap, not just a library.

## Where it is used, and the rule for using it

`aec_data/clash.py` builds the broad-phase candidate set. The old path built a full N×M boolean matrix
over both sides: correct, numpy-fast at a few thousand elements, and 2.5 × 10⁹ booleans at 50k × 50k
before the narrow phase runs at all.

**A BVH is not free.** Building the tree costs more than the matrix for small inputs, so `clash.py`
keeps both and picks by size. The threshold is a measured number, not a guess — see
`test_clash_bvh.py`, which asserts the two paths return the **same clash set** (as a set, not a count)
and records the crossover.

## Re-syncing

```
git clone https://github.com/MassingCloud/massingviser
cp massingviser/src/massingviser/geometry/bvh.py services/data/src/massingviser_geometry/bvh.py
```
then update the SHA above and run `test_clash` and `test_clash_bvh`.

## Local deviations from upstream — NONE

`__init__.py` here is ours (upstream's `geometry/__init__.py` re-exports modules we did not take).
`bvh.py` itself is untouched, and is excluded from our `ruff` config for the same reason the other
vendored trees are: judging someone else's code by our house rules turns a verbatim copy into a fork.
