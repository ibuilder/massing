"""Run the site-photo detector against a real image, from the command line.

    set AEC_PHOTO_MODEL=C:\\path\\to\\site-detector.onnx
    python scripts/try_detect.py C:\\path\\to\\site-photo.jpg

**This script exists because the repo contains no photograph.** Everything under `docs/img/` is a
rendered drawing — plans, elevations, a gantt — and a COCO-trained detector will correctly find
nothing in a line drawing. The unit suite therefore covers the transform maths, the degradation
paths and the output mapping, and *cannot* answer "does it actually find a person on a job site".
Only a real photo answers that, so this makes asking cheap.

What to expect, so a true negative is not mistaken for a broken pipeline:

  * `available: false`  -> onnxruntime or the model is missing; the reasons say which.
  * `ran: false`        -> the photo failed the quality gate (blurred, blown out, unreadable). The
                           gate is deliberate: a detector fed an unusable frame returns confident
                           nonsense, and a headcount nobody can challenge is worse than none.
  * `ran: true` with 0 detections -> the pipeline worked and found nothing above the threshold.
                           On a photo with clearly visible people this means something IS wrong;
                           on an empty formwork shot it is the correct answer.

`--min-score 0` shows everything the graph emitted. Note it cannot go below the 0.30 floor baked
into the exported graph by `box_score_thresh` — see `scripts/export_detector.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="path to a real photograph (jpg/png)")
    ap.add_argument("--min-score", type=float, default=None,
                    help="override the score floor; 0 shows everything the graph emitted")
    ap.add_argument("--no-quality-gate", action="store_true",
                    help="run inference even on a photo that fails the quality check")
    ap.add_argument("--json", action="store_true", help="print the raw result dict")
    args = ap.parse_args()

    from aec_api import photo_cv, photo_detect

    status = photo_detect.detector_status()
    print(f"detector: {'READY' if status['available'] else 'UNAVAILABLE'}")
    for r in status["reasons"]:
        print(f"  - {r}")
    if not status["available"]:
        print("\nSet AEC_PHOTO_MODEL to an exported .onnx (see scripts/export_detector.py).")
        return 2

    try:
        data = open(args.image, "rb").read()
    except OSError as exc:
        print(f"cannot read {args.image}: {exc}")
        return 2

    # Report quality first: it explains a `ran: false` before the user has to ask why.
    try:
        q = photo_cv.photo_quality(data)
        print(f"\nphoto: {q['width']}x{q['height']}  sharpness={q['sharpness']}  "
              f"usable={q['usable']}")
        for r in q["reasons"]:
            print(f"  ! {r}")
    except photo_cv.PhotoError as exc:
        print(f"\nphoto could not be decoded ({exc}) — it is still storable, just not analysable")

    kw = {"require_usable": not args.no_quality_gate}
    if args.min_score is not None:
        kw["min_score"] = args.min_score
    t = time.time()
    res = photo_detect.detect(data, **kw)
    dt = time.time() - t

    if args.json:
        print(json.dumps(res, indent=2))
        return 0

    print(f"\nran={res.get('ran')}  {dt:.2f}s")
    for r in res.get("reasons") or []:
        print(f"  - {r}")
    s = res["summary"]
    print(f"\npeople: {s['people']}    vehicles/plant: {s['vehicles']}    total: {s['total']}")
    for d in res["detections"][:25]:
        x0, y0, x1, y1 = d["box"]
        print(f"  {d['label']:<12} {d['score']:.2f}  "
              f"[{x0:.0f},{y0:.0f} -> {x1:.0f},{y1:.0f}]  {x1 - x0:.0f}x{y1 - y0:.0f}px")
    if res.get("ran") and not res["detections"]:
        print("  (nothing above the score floor — correct for an empty scene, "
              "suspicious if people are clearly visible)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
