"""R22-PHOTO-CV Tier 1 — the missing CONSUMER for element-attached site photos.

`routers/verification.py` has been attaching field photos to IFC GlobalIds for months and **nothing
has ever read one**. The data lands and no consumer exists, so this closes the reach gap rather than
adding a capability: the photos are already keyed by GUID, already stored, already survive
re-conversion.

**No new dependency.** numpy and pillow are in both lockfiles already (pillow arrived as reportlab's
image dep). Everything here is classical image processing — there is no learned model, no weights
file, and nothing to license. That is deliberate: a trained model needs labelled construction photos,
of which this project has zero, and the honest cost of acquiring them is months of human labelling,
not a sprint. See the roadmap entry, where the defect-detection half is refused in place for exactly
that reason.

## The asymmetry that governs this module's API

Classical CV is **reliable when it says two photos are the SAME and unreliable when it says they
differ.** Two shots of one wall taken a week apart differ in exposure, white balance, and camera
position by far more than the newly-built formwork does. So:

  * `near_identical=True` is a **strong** claim — the pixels line up after normalisation, so nothing
    of consequence changed. This is what makes it useful: it retires the "has anything happened
    here?" question cheaply and correctly.
  * A high `change_score` is a **screening signal only** — it means *look at this*, never *this
    changed*. It cannot separate "the slab got poured" from "the photographer stood somewhere else".

The functions therefore return scores and evidence rather than a confident verdict, and the
docstrings say which direction each one can be trusted in. A module that returned a bare
`changed: bool` would be making a claim the mathematics does not support, and would be believed.

All functions are pure over `bytes` — no I/O, no database, no storage handles — so the router layer
stays the only thing that knows where a photo lives.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageOps

# A field photo that fails to decode within these bounds is refused rather than resized: an image
# claiming 40000x40000 is not a site photo, and Pillow will happily allocate it. Pillow's own
# MAX_IMAGE_PIXELS warns at ~89M and does not stop a decode, so the check is made here and enforced.
MAX_PIXELS = 64_000_000          # ~64 MP — comfortably above any phone camera
MAX_BYTES = 40 * 1024 * 1024     # 40 MB encoded

# Working size for every comparison. Small enough that a compare is sub-millisecond, large enough
# that a 300 mm feature in a room-sized frame survives the downsample.
_WORK = 256

# dHash uses a 9x8 grid: 8 comparisons per row x 8 rows = 64 bits.
_HASH_W, _HASH_H = 9, 8


class PhotoError(ValueError):
    """A photo that cannot be read as an image, or is implausibly large for a field photo."""


def _decode(data: bytes) -> Image.Image:
    """Decode to a normalised RGB image, refusing anything that is not plausibly a field photo.

    `ImageOps.exif_transpose` is not cosmetic here — a phone photo carries its rotation in EXIF
    rather than in the pixel order, so two shots of the same wall taken in portrait and landscape
    would otherwise compare as completely different images while looking identical to the person who
    took them.
    """
    if not data:
        raise PhotoError("empty photo")
    if len(data) > MAX_BYTES:
        raise PhotoError(f"photo is {len(data)} bytes, over the {MAX_BYTES} limit")
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w * h > MAX_PIXELS:
            raise PhotoError(f"photo is {w}x{h} = {w * h} pixels, over the {MAX_PIXELS} limit")
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")
    except PhotoError:
        raise
    except Exception as exc:  # Pillow raises a wide family: UnidentifiedImageError, OSError, ...
        raise PhotoError(f"not a readable image: {exc}") from exc


def _gray(img: Image.Image, size: int = _WORK) -> np.ndarray:
    """Square-resampled greyscale as float in [0, 1].

    Deliberately NOT aspect-preserving: two photos of one element are compared cell against cell, so
    they must share a coordinate system. A letterboxed fit would put the padding in the comparison.
    """
    g = img.convert("L").resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(g, dtype=np.float64) / 255.0


def _laplacian_variance(g: np.ndarray) -> float:
    """Variance of the Laplacian — the standard focus measure.

    A sharp photo has strong second derivatives at every edge; a blurred one has them smeared away,
    so the variance collapses. Written as four shifted slices rather than a convolution so this needs
    no scipy: the 4-neighbour Laplacian is `4*centre - up - down - left - right`.
    """
    c = g[1:-1, 1:-1]
    lap = 4.0 * c - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def photo_quality(data: bytes) -> dict:
    """Is this photo usable as evidence at all?

    This is the half of the module that is unambiguous. Blur and exposure clipping are properties of
    the image itself, not inferences about the world, so a verdict here is safe in both directions —
    unlike change detection below.

    Returns `sharpness` (Laplacian variance, higher is sharper), `clipped_dark`/`clipped_bright` as
    the fraction of pixels pinned at either end of the range, `mean_luma`, and a `usable` verdict
    with the reasons that decided it.

    Thresholds are stated as constants rather than tuned against a corpus this project does not have.
    They are set to catch the unarguable cases — a photo of a pocket, a photo into the sun, a photo
    taken while walking — and to stay quiet otherwise. A gate that fires on marginal photos would be
    switched off within a week.
    """
    img = _decode(data)
    g = _gray(img)
    sharp = _laplacian_variance(g)
    dark = float((g <= 0.02).mean())
    bright = float((g >= 0.98).mean())
    luma = float(g.mean())

    reasons: list[str] = []
    if sharp < 0.0008:
        reasons.append("out of focus or taken while moving")
    if dark > 0.60:
        reasons.append("mostly black — lens covered, or shot with no light")
    if bright > 0.45:
        reasons.append("blown out — shot into a light source")
    if luma < 0.06:
        reasons.append("underexposed to the point of carrying no detail")

    return {
        "width": img.width, "height": img.height,
        "sharpness": round(sharp, 6),
        "clipped_dark": round(dark, 4), "clipped_bright": round(bright, 4),
        "mean_luma": round(luma, 4),
        "usable": not reasons,
        "reasons": reasons,
    }


def perceptual_hash(data: bytes) -> int:
    """64-bit dHash — a fingerprint that survives re-encoding, resizing and mild recompression.

    Each bit records whether a pixel is brighter than the one to its right. Because it stores
    *relations* rather than values, a JPEG re-save or a thumbnail keeps the same hash, while a
    genuinely different scene does not. Compare two with `hamming`.
    """
    img = _decode(data)
    g = img.convert("L").resize((_HASH_W, _HASH_H), Image.Resampling.BILINEAR)
    a = np.asarray(g, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    out = 0
    for b in bits:
        out = (out << 1) | int(b)
    return out


def hamming(a: int, b: int) -> int:
    """Differing-bit count between two perceptual hashes. 0 = indistinguishable, 64 = unrelated."""
    return int(bin(a ^ b).count("1"))


def _normalise(g: np.ndarray) -> np.ndarray:
    """Zero-mean, unit-variance — the step that makes a comparison about CONTENT, not daylight.

    Without it, the same wall photographed at 9am and 4pm differs enormously in absolute pixel value
    and the comparison measures the weather. A flat image (zero variance) is returned as zeros rather
    than dividing by ~0.
    """
    sd = float(g.std())
    if sd < 1e-6:
        return np.zeros_like(g)
    return (g - float(g.mean())) / sd


def compare_photos(before: bytes, after: bytes, *, cells: int = 8) -> dict:
    """Screen two photos of the same element for whether anything happened.

    **Read the direction of confidence before using this.** `near_identical=True` is a strong claim:
    after exposure normalisation the two frames line up, so nothing of consequence changed. A large
    `change_score` is a screening signal that means *a person should look*, and specifically does NOT
    mean the element changed — a two-metre step to the left produces a larger score than a newly
    poured slab.

    Three independent measures, because each is blind to something the others catch:

      * `hash_distance` — dHash Hamming. Robust to re-encoding; blind to anything subtle.
      * `luma_corr` — Pearson correlation of the normalised frames. Catches global restructuring;
        blind to a small change in a large frame.
      * `cell_changes` — the same correlation computed per cell on a `cells`x`cells` grid, counting
        cells that decorrelate. This is what sees a change confined to one corner, which is the
        normal case on site and the one a whole-frame measure misses entirely.

    `change_score` in [0, 1] fuses them. The cell term dominates deliberately: localised change is
    the signal worth surfacing, and whole-frame measures wash it out.
    """
    ga, gb = _gray(_decode(before)), _gray(_decode(after))
    na, nb = _normalise(ga), _normalise(gb)

    denom = float(np.sqrt((na * na).sum() * (nb * nb).sum()))
    corr = float((na * nb).sum() / denom) if denom > 1e-9 else 0.0
    corr = max(-1.0, min(1.0, corr))

    step = _WORK // cells
    changed_cells: list[tuple[int, int]] = []
    for r in range(cells):
        for c in range(cells):
            ca = _normalise(ga[r * step:(r + 1) * step, c * step:(c + 1) * step])
            cb = _normalise(gb[r * step:(r + 1) * step, c * step:(c + 1) * step])
            d = float(np.sqrt((ca * ca).sum() * (cb * cb).sum()))
            cc = float((ca * cb).sum() / d) if d > 1e-9 else 0.0
            if cc < 0.55:
                changed_cells.append((r, c))

    n_cells = cells * cells
    cell_frac = len(changed_cells) / n_cells
    hd = hamming(perceptual_hash(before), perceptual_hash(after))

    # `near_identical` rests on the NORMALISED measures, and takes only a loose sanity bound from the
    # hash. That split is not tuning — the three measures have different invariances and ANDing tight
    # bounds lets the least invariant one veto the other two:
    #
    #   corr / cell_frac  are exposure-invariant BY CONSTRUCTION (see `_normalise`).
    #   hash_distance     is invariant to re-encoding and resizing, but NOT to exposure, because
    #                     any shift that CLIPS highlights flattens the local pixel ordering dHash
    #                     records, and flipped orderings are flipped bits.
    #
    # Found by the exposure test rather than by reasoning: a brightened frame scored corr=0.98 with
    # zero changed cells — unchanged by every measure that claims exposure-invariance — and was still
    # rejected on a hash distance of 5. Since a real 4pm photo clips exactly this way, a tight hash
    # bound here would report "changed" for most unchanged elements, which is the failure mode that
    # gets a monitoring feature switched off. 12 of 64 bits still separates a different scene.
    near = bool(corr >= 0.92 and cell_frac <= 0.05 and hd <= 12)

    # Weighted toward the localised measure — see the docstring. hash_distance saturates at 32 of 64
    # bits, which is already "unrelated scene" territory.
    score = 0.6 * cell_frac + 0.25 * (1.0 - (corr + 1.0) / 2.0) + 0.15 * min(1.0, hd / 32.0)
    score = max(0.0, min(1.0, score))

    return {
        "change_score": round(score, 4),
        "near_identical": near,
        "hash_distance": hd,
        "luma_corr": round(corr, 4),
        "changed_cells": len(changed_cells),
        "total_cells": n_cells,
        "changed_regions": [{"row": r, "col": c} for r, c in changed_cells[:24]],
        # Stated on every result so a caller cannot read the score as a verdict without seeing it.
        # Derived from `near` rather than restating the condition: the two were written out twice in
        # the first draft, which is how a verdict and its stated confidence quietly stop agreeing.
        "confidence": ("high — the frames match after normalisation" if near
                       else "screening only — a camera move scores higher than most real change"),
    }


def duplicate_of(candidate: bytes, known: dict[str, int], *, threshold: int = 6) -> str | None:
    """Return the key whose photo is the same shot as `candidate`, or None.

    The case this exists for: one photo uploaded against thirty elements to clear a checklist. That
    is not a rare abuse, it is the path of least resistance for someone under time pressure, and it
    silently destroys the evidence value of the whole verification set.

    `known` maps an identifying key to a hash from `perceptual_hash`. The nearest match within
    `threshold` bits wins; 6 of 64 tolerates re-encoding without merging genuinely different frames.
    """
    h = perceptual_hash(candidate)
    best, best_d = None, math.inf
    for key, kh in known.items():
        d = hamming(h, kh)
        if d < best_d:
            best, best_d = key, d
    return best if best_d <= threshold else None
