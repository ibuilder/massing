"""Export a COCO-pretrained detector to ONNX for `aec_api.photo_detect`. Run ONCE, offline.

    python scripts/export_detector.py --out /srv/models/site-detector.onnx
    export AEC_PHOTO_MODEL=/srv/models/site-detector.onnx

**This is the only place torch is used, and it never runs in the service.** `torch` and
`torchvision` are BSD-3 but large (200 MB+ for the CPU build); the API image needs only
`onnxruntime` (MIT, ~50 MB) to run the exported graph. Keeping the export here is what makes that
split possible — see `services/api/src/aec_api/photo_detect.py`.

**The .onnx is deliberately NOT committed.** Weights are large binaries carrying their own licence
terms, and a repo is a bad place for both. This script plus its pinned weights enum is the
reproducible recipe instead: anyone can regenerate a byte-comparable model and mount it.

**Licence note, and it is the one that matters in this space.** The weights below are
torchvision's, BSD-3, downloaded from download.pytorch.org. Do NOT swap in Ultralytics YOLO — it is
**AGPL**, it is what nearly every tutorial reaches for, and it would relicense anything it touches.
That is the actual trap; the frameworks themselves (torch, torchvision, OpenCV, scikit-*) are all
permissive.

Install (in a THROWAWAY venv, not the service venv — these must never reach requirements.in):

    python -m venv .venv-export
    .venv-export/Scripts/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    .venv-export/Scripts/pip install onnx

**Two export gotchas, recorded because both cost a cycle and neither is obvious.**

1. **`dynamo=False` is load-bearing.** torch >= 2.6 defaults `torch.onnx.export` to the dynamo
   exporter, and dynamo **cannot** trace Faster R-CNN: the number of proposals surviving NMS depends
   on the pixel data, so `torch.export` raises a data-dependent-shape error. torchvision's detection
   models are exportable only through the legacy TorchScript path. The failure is loud but its
   message is three frames deep.

2. **Run it with `PYTHONUTF8=1` on Windows.** When the export fails, torch prints its progress
   markers (`❌`) to stderr, and on a cp1252 console *the error reporting itself* dies with
   `UnicodeEncodeError` — masking the real error entirely. The first failure here looked like a
   Unicode bug and was actually the data-dependent-shape one above.

    PYTHONUTF8=1 python scripts/export_detector.py --out <path>
"""
from __future__ import annotations

import argparse
import sys

# Must match photo_detect.INPUT_SIZE. Stated as a literal rather than imported so this script has no
# dependency on the service package and can run in a bare venv.
INPUT_SIZE = 640


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="path to write the .onnx to")
    ap.add_argument("--opset", type=int, default=17)
    args = ap.parse_args()

    try:
        import torch
        from torchvision.models.detection import (
            FasterRCNN_MobileNet_V3_Large_FPN_Weights,
            fasterrcnn_mobilenet_v3_large_fpn,
        )
    except ImportError:
        print("torch + torchvision are required to EXPORT (never to run):\n"
              "  python -m venv .venv-export && .venv-export/Scripts/pip install torch torchvision",
              file=sys.stderr)
        return 2

    # MobileNetV3-Large FPN rather than a ResNet backbone: ~3x faster on CPU at a small accuracy cost,
    # and the question here is "is there a person / a truck in frame", not fine-grained localisation.
    # The API service has no GPU, so CPU inference time is the binding constraint.
    weights = FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1
    model = fasterrcnn_mobilenet_v3_large_fpn(weights=weights, box_score_thresh=0.30)
    model.eval()

    # box_score_thresh is BAKED INTO THE GRAPH — it is part of the model's own postprocessing, not
    # something the runtime can undo. So 0.30 here is a hard FLOOR: `photo_detect.MIN_SCORE` (0.55)
    # can only tighten it further, and setting MIN_SCORE below 0.30 changes nothing because those
    # boxes were discarded before the graph ever emitted them.
    #
    # Stated plainly because the first draft of this comment claimed the threshold was "set low and
    # filtered properly at call time", which is only half true and is exactly the kind of note that
    # sends someone hunting for a runtime bug that is really an export-time constant. If you need
    # detections below 0.30, re-export — do not touch MIN_SCORE.
    # torchvision detection models take List[Tensor] of CHW images, not a batched NCHW tensor. The
    # trailing comma matters: it makes this the single positional argument `images`, so the exported
    # graph's input is one 3-D tensor. photo_detect._preprocess must therefore feed CHW, not NCHW.
    dummy = torch.zeros(3, INPUT_SIZE, INPUT_SIZE, dtype=torch.float32)
    torch.onnx.export(
        model, ([dummy],), args.out,
        input_names=["images"], output_names=["boxes", "labels", "scores"],
        opset_version=args.opset,
        # See gotcha 1 in the module docstring: the dynamo exporter cannot trace this model at all.
        dynamo=False,
        # Batch stays 1 (one photo per upload) but detection COUNT varies per image, so the output
        # dim must be dynamic or the graph silently truncates to whatever the dummy produced.
        dynamic_axes={"boxes": {0: "n"}, "labels": {0: "n"}, "scores": {0: "n"}},
    )
    print(f"wrote {args.out}\n"
          f"  weights : {weights}  (BSD-3, torchvision)\n"
          f"  input   : 1x3x{INPUT_SIZE}x{INPUT_SIZE} float32, RGB, [0,1], letterboxed\n"
          f"  set     : AEC_PHOTO_MODEL={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
