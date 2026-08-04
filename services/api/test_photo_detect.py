"""R22-PHOTO-CV Tier 2 — the parts that can be tested WITHOUT the model, which is most of them.

## What this suite deliberately does NOT cover, stated up front

**Real inference is not exercised here.** The `.onnx` is not in the repo (weights are large binaries
with their own licence terms — see `services/api/scripts/export_detector.py`), so no test in this file
runs a detector. Claiming otherwise would be the exact failure this project keeps re-learning: a
suite that passes while the thing it names never ran.

What IS covered is everything around the model, and that is where the bugs live:

  * **the letterbox transform and its inverse** — pure arithmetic, and the single easiest thing to get
    quietly wrong. A wrong pad draws every box slightly off and nothing else notices;
  * **graceful degradation** — with no runtime and no model, `detect()` must return a reason, not
    raise. This is the v0.3.851 lesson carried forward: analysis that cannot run must never fail the
    upload it is attached to;
  * **output mapping** — `_collect` is fed synthetic graph outputs, which tests the score threshold,
    the site-class filter, the clamp and the ordering without needing a graph;
  * **the summary** — people and vehicles counted separately.

The one thing a real model would add is whether the *graph* matches the preprocessing contract, and
that is what `export_detector.py` pins.
"""
from __future__ import annotations

import io
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, "src")
from aec_api import photo_detect as pd  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        FAILS.append(f"{name}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL {name}  {detail}")


def png(w: int, h: int, colour=(120, 90, 60)) -> bytes:
    b = io.BytesIO()
    # Structured noise, not flat colour: a flat image has zero Laplacian variance and fails the
    # quality gate, which would make the require_usable tests below pass for the wrong reason.
    rng = np.random.default_rng(11)
    arr = np.clip(rng.integers(0, 90, (h, w, 3)) + np.array(colour), 0, 255).astype("uint8")
    Image.fromarray(arr, "RGB").save(b, "PNG")
    return b.getvalue()


# --- 1. letterbox: geometry is preserved, and the inverse is exact -------------------------------
print("letterbox")
for w, h in ((640, 640), (4032, 3024), (3024, 4032), (1000, 100), (100, 1000)):
    scale, px, py = pd.letterbox(w, h)
    check(f"{w}x{h} fits inside the input square",
          round(w * scale) + 2 * px <= pd.INPUT_SIZE + 1 and round(h * scale) + 2 * py <= pd.INPUT_SIZE + 1,
          f"scale={scale:.4f} pad=({px},{py})")
    # A square image needs no padding; a wide one pads vertically only. If BOTH are padded on a
    # non-square image the fit used the wrong axis.
    if w == h:
        check("a square image needs no padding", px == 0 and py == 0, f"pad=({px},{py})")
    elif w > h:
        check(f"{w}x{h} (wide) pads vertically, not horizontally", px == 0 and py > 0, f"pad=({px},{py})")

# The round-trip is the assertion that matters: model-space -> original must land where it started.
print("letterbox round-trip")
for w, h in ((4032, 3024), (800, 1200), (640, 640)):
    scale, px, py = pd.letterbox(w, h)
    for orig in ((0.0, 0.0, float(w), float(h)), (10.0, 20.0, 110.0, 220.0)):
        fwd = tuple(v * scale + (px if i % 2 == 0 else py) for i, v in enumerate(orig))
        back = pd.unletterbox(fwd, scale, px, py)
        check(f"round-trip {w}x{h} {orig[:2]}",
              all(abs(a - b) < 0.01 for a, b in zip(orig, back, strict=True)),
              f"got {tuple(round(v, 2) for v in back)}")

# A degenerate size must raise rather than divide by zero. Written as an explicit try/except: the
# first draft of this check was `... if False else True`, which could not fail under any behaviour —
# the exact shape this repo has a standing rule against, committed by the person who wrote the rule.
try:
    pd.letterbox(0, 100)
    check("letterbox(0, …) raises rather than dividing by zero", False, "it returned instead")
except ValueError:
    check("letterbox(0, …) raises rather than dividing by zero", True)
except ZeroDivisionError:
    check("letterbox(0, …) raises rather than dividing by zero", False, "raised ZeroDivisionError")

# --- 2. degradation: no runtime / no model must REPORT, never raise -------------------------------
print("degradation")
os.environ.pop(pd.MODEL_ENV, None)
st = pd.detector_status()
check("status is unavailable with no model configured", st["available"] is False)
check("...and says WHY", bool(st["reasons"]), f"reasons={st['reasons']}")
check("the two causes are reported separately",
      "model_path_set" in st and "runtime" in st, f"keys={sorted(st)}")

r = pd.detect(png(200, 150))
check("detect() returns rather than raising when unavailable", r["available"] is False)
check("...with an empty detection list, not a missing key", r["detections"] == [])
check("...and a well-formed summary anyway", r["summary"]["total"] == 0 and r["summary"]["people"] == 0)

os.environ[pd.MODEL_ENV] = "C:/nope/definitely-not-a-model.onnx"
st2 = pd.detector_status()
check("a path pointing at nothing is distinguished from an unset path",
      st2["model_path_set"] is True and st2["model_present"] is False, f"{st2}")
check("detect() still degrades with a bad path", pd.detect(png(120, 120))["available"] is False)
os.environ.pop(pd.MODEL_ENV, None)

# --- 3. the quality pre-filter -------------------------------------------------------------------
# A blurred frame does not produce NO detections, it produces confident WRONG ones. The skip must be
# reported. (Runs through the unavailable path here, which is why the assertion is on the contract
# shape rather than on inference having been skipped.)
print("quality pre-filter contract")
flat = io.BytesIO(); Image.new("RGB", (300, 300), (0, 0, 0)).save(flat, "PNG")
res = pd.detect(flat.getvalue())
check("an unusable photo yields no detections and a stated reason",
      res["detections"] == [] and bool(res["reasons"]), f"{res}")

# --- 4. output mapping, with synthetic graph outputs ---------------------------------------------
print("_collect")
W, H = 1000, 500
scale, px, py = pd.letterbox(W, H)


def model_box(x0, y0, x1, y1):
    """An original-space box expressed the way the graph would emit it."""
    return [x0 * scale + px, y0 * scale + py, x1 * scale + px, y1 * scale + py]


boxes = np.array([
    model_box(100, 50, 200, 300),    # person, high score      -> kept
    model_box(400, 100, 700, 400),   # truck, high score       -> kept
    model_box(10, 10, 60, 60),       # person, BELOW threshold -> dropped
    model_box(0, 0, 50, 50),         # zebra (id 24)           -> dropped, not site-relevant
], dtype=np.float32)
labels = np.array([1, 8, 1, 24], dtype=np.int64)
scores = np.array([0.95, 0.80, 0.10, 0.99], dtype=np.float32)

got = pd._collect((boxes, labels, scores), scale, px, py, W, H, pd.MIN_SCORE)
dets = got["detections"]
check("low-confidence and non-site classes are both dropped", len(dets) == 2,
      f"got {[(d['label'], d['score']) for d in dets]}")
check("a high-scoring NON-site class is dropped even at 0.99",
      all(d["label"] != "zebra" for d in dets))
check("labels are mapped to site vocabulary", {d["label"] for d in dets} == {"person", "truck"},
      f"{[d['label'] for d in dets]}")
check("sorted by score, highest first", [d["score"] for d in dets] == sorted((d["score"] for d in dets), reverse=True))
check("boxes come back in ORIGINAL pixel space",
      all(abs(a - b) < 1.0 for a, b in zip(dets[0]["box"], [100, 50, 200, 300], strict=True)),
      f"got {dets[0]['box']}")
check("every box lies inside the frame",
      all(0 <= d["box"][0] <= W and 0 <= d["box"][1] <= H and
          0 <= d["box"][2] <= W and 0 <= d["box"][3] <= H for d in dets),
      f"{[d['box'] for d in dets]}")

# a box the model places outside the frame (legal — padding) must be clamped, not emitted raw
out_of_frame = np.array([[-40.0, -40.0, 60.0, 60.0]], dtype=np.float32)
cl = pd._collect((out_of_frame, np.array([1]), np.array([0.9])), scale, px, py, W, H, pd.MIN_SCORE)
check("an out-of-frame box is clamped rather than emitted negative",
      not cl["detections"] or cl["detections"][0]["box"][0] >= 0,
      f"{cl['detections']}")

# --- 5. the summary answers the two questions separately ------------------------------------------
print("summarise")
s = pd.summarise([{"label": "person"}, {"label": "person"}, {"label": "truck"}, {"label": "car"}])
check("people are counted on their own line", s["people"] == 2, f"{s}")
check("vehicles aggregate across classes", s["vehicles"] == 2, f"{s}")
check("a person is NOT counted as a vehicle", s["people"] + s["vehicles"] == s["total"], f"{s}")
check("the per-class breakdown survives", s["by_class"] == {"person": 2, "truck": 1, "car": 1}, f"{s}")
check("an empty set summarises to zeros, not to missing keys",
      pd.summarise([]) == {"people": 0, "vehicles": 0, "by_class": {}, "total": 0})

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s)")
    for f in FAILS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_photo_detect OK")
