"""R22-PHOTO-CV Tier 2 — what is IN the site photo, not just whether it is usable.

Tier 1 (`photo_cv`) answers "is this photo evidence at all" and "did anything change". Neither
question needs a model. This one does: *people, vehicles and plant in frame* is the first thing a
superintendent actually wants counted, and it is reachable with **COCO-pretrained weights and zero
labelling** — which is why it is the first target rather than defect detection, where this project has
no labelled data at all.

## Why ONNX Runtime and not torch

The service does inference only. `torch` + `torchvision` (both BSD-3) are used **once, offline**, by
`scripts/export_detector.py`, to fetch pretrained weights and export a single `.onnx` file. Only
`onnxruntime` (MIT, ~50 MB) is needed at runtime, against torch's 200 MB+ CPU build — so the training
framework never enters the deployed image. The AGPL trap in this space is Ultralytics YOLO; it is not
used here and must not be.

## Both dependencies are OPTIONAL at import time, deliberately

Neither `onnxruntime` nor the model file is required for this module to import, and **nothing here
raises into a request path**. `detect()` returns `available: False` with a reason instead.

That is not defensive habit, it is the lesson from v0.3.851: a photo-analysis gate that *refused* an
upload it could not handle would have discarded every iPhone HEIC photo. The upload is the user's
evidence; analysis is a bonus riding along with it. **Analysis that cannot run must degrade, never
fail the thing it is attached to.** A deployment with no model file gets photo storage plus quality
plus change detection, and simply no detections — which is exactly v0.3.855's behaviour, not a
regression.

The model is NOT committed. Weights are large binaries with their own licence terms; the export
script and its pinned source are committed instead, so anyone can reproduce the file. Point
`AEC_PHOTO_MODEL` at it.
"""
from __future__ import annotations

import os
import threading

import numpy as np

from . import photo_cv

#: Env var naming the exported .onnx detector. Absent -> detection reports unavailable.
MODEL_ENV = "AEC_PHOTO_MODEL"

#: Square input the exported graph expects. Must match `scripts/export_detector.py`.
INPUT_SIZE = 640

#: Below this score a detection is dropped. COCO detectors emit a long tail of low-confidence boxes;
#: surfacing them would make the count look precise and be wrong.
MIN_SCORE = 0.55

#: The COCO classes that mean something on a construction site, mapped to the vocabulary a
#: superintendent uses. COCO's 91-entry index is sparse — these are the ids that survive, and
#: everything else (sofa, toaster, zebra) is dropped rather than reported as noise.
SITE_CLASSES: dict[int, str] = {
    1: "person",
    2: "bicycle",
    3: "car",
    4: "motorcycle",
    6: "bus",
    7: "train",
    8: "truck",
}

#: Which of those count as plant/vehicle for the rollup. `person` is deliberately its own line:
#: headcount and equipment count answer different questions on a daily report.
VEHICLE_CLASSES = frozenset({"bicycle", "car", "motorcycle", "bus", "train", "truck"})

_session_lock = threading.Lock()
_session: object | None = None
_session_path: str | None = None


def _load_session(path: str):
    """Return a cached ONNX Runtime session for `path`, or None if it cannot be created.

    Cached because creating a session parses and optimises the whole graph — doing that per upload
    would dominate the request. Guarded by a lock: FastAPI serves requests on a thread pool, and two
    concurrent first-uploads would otherwise build two sessions and race on the assignment.
    """
    global _session, _session_path
    with _session_lock:
        if _session is not None and _session_path == path:
            return _session
        try:
            import onnxruntime as ort  # lazy — the service runs fine without it installed
        except ImportError:
            return None
        try:
            sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        except Exception:  # noqa: BLE001 — a corrupt or mismatched model must not take the route down
            return None
        _session, _session_path = sess, path
        return sess


def detector_status() -> dict:
    """Why detection is or is not available, in terms an operator can act on.

    Separate from `detect()` so `/health` and the ops UI can report the model's absence without
    pushing an image through it. The two reasons need different fixes — install a package versus
    export and mount a file — so they are reported separately rather than as one "unavailable".
    """
    try:
        import onnxruntime  # noqa: F401
        runtime = True
    except ImportError:
        runtime = False
    path = os.environ.get(MODEL_ENV) or ""
    have_model = bool(path) and os.path.isfile(path)
    reasons = []
    if not runtime:
        reasons.append("onnxruntime is not installed")
    if not path:
        reasons.append(f"{MODEL_ENV} is not set")
    elif not have_model:
        reasons.append(f"{MODEL_ENV} points at a file that does not exist")
    return {"available": runtime and have_model, "runtime": runtime,
            "model_path_set": bool(path), "model_present": have_model, "reasons": reasons}


def letterbox(w: int, h: int, size: int = INPUT_SIZE) -> tuple[float, int, int]:
    """Scale + padding that fits a `w`x`h` image into `size`x`size` **without distorting it**.

    Returns `(scale, pad_x, pad_y)`.

    This is the one place Tier 2 must NOT copy Tier 1. `photo_cv._gray` resizes to a square on
    purpose, squashing the aspect ratio, because it compares two frames cell against cell and only
    needs them to share a coordinate system. A detector trained on undistorted images and fed a
    squashed one produces boxes that are wrong in a way that still looks plausible — a person
    detected as short and wide. Fit-and-pad preserves the geometry; `unletterbox` undoes it exactly.
    """
    if w <= 0 or h <= 0:
        raise ValueError(f"bad image size {w}x{h}")
    scale = min(size / w, size / h)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    return scale, (size - new_w) // 2, (size - new_h) // 2


def unletterbox(box: tuple[float, float, float, float], scale: float, pad_x: int,
                pad_y: int) -> tuple[float, float, float, float]:
    """Map a model-space box back to ORIGINAL pixel coordinates.

    Without this the boxes are in 640x640 padded space, which is meaningless to a caller holding a
    4032x3024 photo. Asserted as a round-trip in the tests, because an off-by-a-pad error draws every
    box slightly wrong and nothing else notices.
    """
    x0, y0, x1, y1 = box
    return ((x0 - pad_x) / scale, (y0 - pad_y) / scale,
            (x1 - pad_x) / scale, (y1 - pad_y) / scale)


def _preprocess(data: bytes) -> tuple[np.ndarray, float, int, int, int, int]:
    """Decode -> letterbox -> **CHW** float32 in [0,1], the layout the exported graph expects.

    **Three dimensions, not four.** torchvision's detection models take `List[Tensor]` of CHW images
    rather than a batched NCHW tensor, so the exported graph's input is `images: [3, 640, 640]`.
    Adding the batch axis here — the reflex, and what the first version did — fails at
    `sess.run` with a rank mismatch. Verified by asking the graph rather than assuming:

        [i.shape for i in ort.InferenceSession(model).get_inputs()]  ->  [[3, 640, 640]]
    """
    from PIL import Image  # pillow is a hard dep (photo_cv uses it); local import keeps this leaf tidy
    img = photo_cv._decode(data)          # noqa: SLF001 — same package, one decoder, one set of limits
    w, h = img.width, img.height
    scale, pad_x, pad_y = letterbox(w, h)
    resized = img.resize((int(round(w * scale)), int(round(h * scale))), Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (INPUT_SIZE, INPUT_SIZE), (114, 114, 114))
    canvas.paste(resized, (pad_x, pad_y))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    return np.transpose(arr, (2, 0, 1)), scale, pad_x, pad_y, w, h


def summarise(detections: list[dict]) -> dict:
    """Counts a daily report can use, rather than a list a person has to tally.

    `people` and `vehicles` are separate totals because they answer different questions — how many
    are on site, and what plant is here — and a single "objects" number answers neither.
    """
    by_class: dict[str, int] = {}
    for d in detections:
        by_class[d["label"]] = by_class.get(d["label"], 0) + 1
    return {"people": by_class.get("person", 0),
            "vehicles": sum(n for k, n in by_class.items() if k in VEHICLE_CLASSES),
            "by_class": by_class, "total": len(detections)}


def detect(data: bytes, *, min_score: float = MIN_SCORE, require_usable: bool = True) -> dict:
    """Detect site objects in a photo. **Never raises** — see the module docstring.

    `require_usable` runs Tier 1's quality gate first and skips inference on a photo that carries no
    evidence. A blurred or blown-out frame does not produce no detections, it produces *confident
    wrong* ones, and a headcount inferred from an unusable photo is worse than no headcount because
    it will be believed. The skip is reported, not silent.
    """
    status = detector_status()
    if not status["available"]:
        return {"available": False, "reasons": status["reasons"], "detections": [],
                "summary": summarise([])}

    if require_usable:
        try:
            q = photo_cv.photo_quality(data)
        except photo_cv.PhotoError as exc:
            return {"available": True, "ran": False,
                    "reasons": [f"photo could not be decoded: {exc.__class__.__name__}"],
                    "detections": [], "summary": summarise([])}
        if not q.get("usable"):
            return {"available": True, "ran": False,
                    "reasons": ["photo failed the quality gate: " + "; ".join(q.get("reasons") or [])],
                    "detections": [], "summary": summarise([])}

    sess = _load_session(os.environ[MODEL_ENV])
    if sess is None:
        return {"available": False, "reasons": ["the model file could not be loaded"],
                "detections": [], "summary": summarise([])}

    try:
        tensor, scale, pad_x, pad_y, w, h = _preprocess(data)
        outputs = sess.run(None, {sess.get_inputs()[0].name: tensor})
    except Exception as exc:  # noqa: BLE001 — inference failure must not fail the upload
        return {"available": True, "ran": False,
                "reasons": [f"inference failed: {exc.__class__.__name__}"],
                "detections": [], "summary": summarise([])}

    return {"available": True, "ran": True, "reasons": [],
            **_collect(outputs, scale, pad_x, pad_y, w, h, min_score)}


def _collect(outputs, scale, pad_x, pad_y, w, h, min_score) -> dict:
    """Turn raw graph outputs into clamped, named, original-space detections."""
    boxes, labels, scores = (np.asarray(o) for o in outputs[:3])
    out: list[dict] = []
    for box, label, score in zip(boxes.reshape(-1, 4), labels.reshape(-1),
                                 scores.reshape(-1), strict=False):
        if float(score) < min_score:
            continue
        name = SITE_CLASSES.get(int(label))
        if name is None:                       # not site-relevant — dropped, not reported as noise
            continue
        x0, y0, x1, y1 = unletterbox(tuple(float(v) for v in box), scale, pad_x, pad_y)
        # Clamp to the frame: padding means a box can legitimately resolve just outside it.
        x0, x1 = max(0.0, min(x0, w)), max(0.0, min(x1, w))
        y0, y1 = max(0.0, min(y0, h)), max(0.0, min(y1, h))
        if x1 - x0 < 1 or y1 - y0 < 1:
            continue
        out.append({"label": name, "score": round(float(score), 4),
                    "box": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]})
    out.sort(key=lambda d: d["score"], reverse=True)
    return {"detections": out, "summary": summarise(out)}
