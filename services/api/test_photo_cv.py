"""R22-PHOTO-CV Tier 1 — the photo consumer, asserted in BOTH directions.

`photo_cv` is mostly a set of gates, and a gate suite is the exact shape that
[[refusal-tests-need-their-twin]] warns about: assert only that bad photos are refused and the file
passes just as well against a function that refuses EVERYTHING. So every refusal below is paired with
the acceptance it is carved out of — a blurred photo is rejected AND a sharp one is accepted; a
duplicate is found AND a non-duplicate returns None.

The claim that carries the most weight is the **exposure-invariance** one. Change detection is only
worth having if two photos of an unchanged wall at 9am and 4pm read as unchanged; without that it
reports the weather and every element looks like it moved. That test is what makes the rest useful,
and it fails loudly if `_normalise` is ever removed as a "simplification".
"""
from __future__ import annotations

import io
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, "src")
from aec_api.photo_cv import (  # noqa: E402
    PhotoError,
    compare_photos,
    duplicate_of,
    hamming,
    perceptual_hash,
    photo_quality,
)

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        FAILS.append(f"{name}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL {name}  {detail}")


def enc(img: Image.Image, fmt: str = "PNG", **kw) -> bytes:
    b = io.BytesIO()
    img.save(b, fmt, **kw)
    return b.getvalue()


# A deterministic pseudo-photo: broadband noise has the edge content a real site photo has, so the
# focus measure behaves as it would on real input. A flat or gradient fixture would read as blurred
# no matter how sharp it is, and would make the blur test pass for the wrong reason.
RNG = np.random.default_rng(20260803)
SCENE = Image.fromarray(RNG.integers(40, 200, (400, 400, 3)).astype("uint8"), "RGB")
SHARP = enc(SCENE)


# --- 1. the quality gate, both directions ---------------------------------------------------------
print("photo_quality")
q_ok = photo_quality(SHARP)
check("a sharp photo is USABLE — the twin, without which every refusal below is free",
      q_ok["usable"] is True, f"reasons={q_ok['reasons']}")
check("it reports the real pixel dimensions", (q_ok["width"], q_ok["height"]) == (400, 400))

q_blur = photo_quality(enc(SCENE.filter(ImageFilter.GaussianBlur(6))))
check("a blurred photo is refused", q_blur["usable"] is False)
check("...and says WHY, so the person retaking it knows what to fix",
      any("focus" in r for r in q_blur["reasons"]), f"reasons={q_blur['reasons']}")
check("blur actually lowers the sharpness score", q_blur["sharpness"] < q_ok["sharpness"],
      f"{q_blur['sharpness']} vs {q_ok['sharpness']}")

q_dark = photo_quality(enc(Image.new("RGB", (300, 300), (2, 2, 2))))
check("a photo of the inside of a pocket is refused", q_dark["usable"] is False)
check("...as mostly-black, not merely as blurred",
      any("black" in r or "underexposed" in r for r in q_dark["reasons"]), f"{q_dark['reasons']}")

q_blown = photo_quality(enc(Image.new("RGB", (300, 300), (254, 254, 254))))
check("a blown-out photo is refused", q_blown["usable"] is False)
check("...as over-exposed", any("blown" in r for r in q_blown["reasons"]), f"{q_blown['reasons']}")

# A mid-grey frame is dull but correctly exposed. It must NOT trip the exposure rules — otherwise the
# gate is really measuring "is this interesting", which is not its job.
q_grey = photo_quality(enc(Image.new("RGB", (300, 300), (128, 128, 128))))
check("a correctly-exposed frame is not refused FOR EXPOSURE",
      not any("blown" in r or "black" in r or "underexposed" in r for r in q_grey["reasons"]),
      f"{q_grey['reasons']}")


# --- 2. perceptual hash -----------------------------------------------------------------------
print("perceptual_hash")
h_sharp = perceptual_hash(SHARP)
check("the same bytes hash identically", perceptual_hash(SHARP) == h_sharp)
check("hamming of a hash with itself is 0", hamming(h_sharp, h_sharp) == 0)

h_jpeg = perceptual_hash(enc(SCENE, "JPEG", quality=60))
check("a JPEG re-encode keeps the hash — the property the whole thing rests on",
      hamming(h_sharp, h_jpeg) <= 4, f"distance={hamming(h_sharp, h_jpeg)}")

h_half = perceptual_hash(enc(SCENE.resize((200, 200))))
check("a resize keeps the hash", hamming(h_sharp, h_half) <= 6,
      f"distance={hamming(h_sharp, h_half)}")

other = Image.fromarray(RNG.integers(0, 255, (400, 400, 3)).astype("uint8"), "RGB")
check("an unrelated scene does NOT — the twin for the three above",
      hamming(h_sharp, perceptual_hash(enc(other))) > 12,
      f"distance={hamming(h_sharp, perceptual_hash(enc(other)))}")
check("a hash is 64 bits", 0 <= h_sharp < (1 << 64))


# --- 3. change detection, and the asymmetry it promises -------------------------------------------
print("compare_photos")
same = compare_photos(SHARP, enc(SCENE, "JPEG", quality=60))
check("a re-encode of the same shot reads NEAR-IDENTICAL", same["near_identical"] is True,
      f"score={same['change_score']} corr={same['luma_corr']} cells={same['changed_cells']}")
check("...with a low change score", same["change_score"] < 0.10, f"{same['change_score']}")
check("...and says its confidence is HIGH", "high" in same["confidence"])

# THE test. Same wall, different time of day. If this fails the module measures daylight.
brighter = SCENE.point(lambda v: min(255, int(v * 1.45) + 20))
expo = compare_photos(SHARP, enc(brighter))
check("an EXPOSURE change alone does not read as a change — the claim that makes this useful",
      expo["near_identical"] is True,
      f"score={expo['change_score']} corr={expo['luma_corr']} cells={expo['changed_cells']}")

# A localised change — the normal case on site, and the one a whole-frame measure cannot see.
patched = SCENE.copy()
ImageDraw.Draw(patched).rectangle([20, 20, 150, 150], fill=(255, 255, 255))
local = compare_photos(SHARP, enc(patched))
check("a change confined to one corner IS surfaced", local["near_identical"] is False,
      f"score={local['change_score']} cells={local['changed_cells']}")
check("...and the changed cells are LOCATED, not just counted",
      0 < local["changed_cells"] < local["total_cells"] and len(local["changed_regions"]) > 0,
      f"{local['changed_cells']}/{local['total_cells']}")
check("...in the corner that actually changed",
      all(r["row"] < 4 and r["col"] < 4 for r in local["changed_regions"]),
      f"regions={local['changed_regions'][:6]}")
check("a screening result does NOT claim high confidence — the honesty guard",
      "screening" in local["confidence"], f"{local['confidence']}")
check("localised change scores higher than an exposure shift",
      local["change_score"] > expo["change_score"],
      f"{local['change_score']} vs {expo['change_score']}")
check("change_score stays in [0,1]", all(0.0 <= r["change_score"] <= 1.0
                                         for r in (same, expo, local)))


# --- 4. duplicate detection, both directions ------------------------------------------------------
print("duplicate_of")
known = {"GUID-A": perceptual_hash(SHARP), "GUID-B": perceptual_hash(enc(other))}
check("the same photo uploaded against a second element is caught",
      duplicate_of(enc(SCENE, "JPEG", quality=70), known) == "GUID-A")
third = Image.fromarray(RNG.integers(0, 255, (400, 400, 3)).astype("uint8"), "RGB")
check("a genuinely new photo is NOT flagged — the twin", duplicate_of(enc(third), known) is None)
check("an empty known-set flags nothing", duplicate_of(SHARP, {}) is None)


# --- 5. refusals, and that they are refusals rather than crashes ----------------------------------
print("input refusal")
for label, payload in (("empty bytes", b""),
                       ("not an image", b"this is a submittal, not a photo" * 40),
                       ("a truncated header", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)):
    try:
        photo_quality(payload)
        check(f"{label} is refused", False, "no exception raised")
    except PhotoError:
        check(f"{label} is refused as PhotoError", True)
    except Exception as exc:  # noqa: BLE001
        check(f"{label} is refused as PhotoError", False, f"raised {type(exc).__name__}: {exc}")

# EXIF: a portrait phone photo carries rotation in metadata, not pixel order. Two shots of one wall
# must not compare as different scenes just because the phone was held differently.
rot = SCENE.transpose(Image.Transpose.ROTATE_90)
check("a rotated scene is NOT silently treated as the same shot",
      not compare_photos(SHARP, enc(rot))["near_identical"])

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s)")
    for f in FAILS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_photo_cv OK")
