"""SCAN-TRUNC — is a deviation figure ever computed against a MODEL THAT WAS CUT SHORT?

`scan_deviation.model_surface_points` caps the reference at 200,000 surface vertices, and it reaches
that cap by BREAKING out of the element iterator. So hitting it does not thin the reference evenly —
it drops whole elements, in whatever order ifcopenshell happened to yield them. Every scan point over
a dropped element is then measured against the nearest surface that remains, which can be metres away.

**That is not a loss of precision, it is a fabricated defect.** Measured on a two-wing model built
exactly to design, and reproduced by `test_truncation_biases_toward_failure` below:

    full reference                 within_pct 100.0 ·   0 out of tolerance · max  0.004 m
    reference truncated to wing A  within_pct  50.0 · 500 out of tolerance · max 50.0   m

On a QA/QC as-built check that sends a crew to re-survey a wing that is fine. It is the opposite sign
from CLASH-TRUNC, where truncation made a partial matrix read CLEAN — *the direction a silent bound
pushes the answer is a property of the bound, not of truncation*, so neither case predicts the other
and both have to be measured.

**The two caps are treated differently on purpose, and the asymmetry is the load-bearing decision.**
A truncated SCAN is a coverage claim: every point that was read is still measured correctly, so the
verdict is true of the part examined and is reported beside its coverage, the way this repository
handles `skipped_count` everywhere else. A truncated REFERENCE is a correctness claim: there is no
population the figure is true of, so `within_pct` and the histogram are withheld rather than
qualified. *A caveat is for a number that means something.*

This gate runs the real engine rather than inspecting source, because the defect is entirely in what
the numbers come out as — a static check that the flags are threaded through would pass a version
that threaded them through and ignored them, which is how `test_pin_pgnull`'s first draft failed.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_scan_trunc.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_scan_trunc")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import numpy as np  # noqa: E402

from aec_api import scan_deviation as sd  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('   ' + detail) if detail else ''}")
    if not ok:
        FAILURES.append(name)


def two_wing_scan():
    """A scan of a building in two wings, 50 m apart, built exactly to design."""
    rng = np.random.default_rng(0)
    return np.vstack([rng.normal(0, 0.001, (500, 3)),
                      rng.normal(0, 0.001, (500, 3)) + [50.0, 0.0, 0.0]])


def two_wing_reference():
    return np.vstack([np.zeros((300, 3)), np.tile([50.0, 0.0, 0.0], (300, 1))])


# --------------------------------------------------------------------------------------------
# THE CLAIM, REPRODUCED. Without this the entry above is an assertion; with it, deleting the
# refusal below re-creates the shipped defect and this file says so in numbers.
# --------------------------------------------------------------------------------------------
scan, full = two_wing_scan(), two_wing_reference()
wing_a = full[:300]

sound = sd.analyze(scan, full, 0.05)
check("a correct building reads as correct against the FULL reference",
      sound["within_pct"] == 100.0 and sound["out_of_tolerance"] == 0,
      f"within_pct={sound['within_pct']} out={sound['out_of_tolerance']}")

# The pre-fix behaviour: the same scan, the same model, the reference cut short and nothing said.
unflagged = sd.analyze(scan, wing_a, 0.05)
check("truncation BIASES TOWARD FAILURE — this is what shipped",
      unflagged["within_pct"] == 50.0 and unflagged["out_of_tolerance"] == 500
      and unflagged["max_deviation"] > 49.0,
      f"within_pct={unflagged['within_pct']} out={unflagged['out_of_tolerance']} "
      f"max={unflagged['max_deviation']}")

# --------------------------------------------------------------------------------------------
# THE REFUSAL
# --------------------------------------------------------------------------------------------
refused = sd.analyze(scan, wing_a, 0.05, reference_truncated=True)
check("a truncated reference produces NO deviation figure",
      refused["within_pct"] is None, f"within_pct={refused['within_pct']!r}")
check("...and no out-of-tolerance count to quote out of context",
      "out_of_tolerance" not in refused and "histogram" not in refused,
      f"keys={sorted(k for k in refused if k in ('out_of_tolerance', 'histogram'))}")
check("...and says why, naming the cap rather than reporting a generic error",
      "capped at" in refused.get("error", "") and refused.get("reference_truncated") is True)
check("...and points at the route that does NOT truncate the model",
      "verify-lod500" in refused.get("note", ""))

# --------------------------------------------------------------------------------------------
# THE COVERAGE — the other cap, handled the other way ON PURPOSE
# --------------------------------------------------------------------------------------------
partial = sd.analyze(scan[:300], np.zeros((300, 3)), 0.05, points_total=1000)
check("a truncated SCAN keeps its verdict — the points read were read correctly",
      partial["within_pct"] is not None, f"within_pct={partial['within_pct']}")
check("...and reports the coverage beside it",
      partial["points_truncated"] is True and partial["point_count"] == 300
      and partial["points_total"] == 1000,
      f"{partial['point_count']} of {partial['points_total']}")
check("...and says a prefix of a scan file is a REGION, not a sample",
      "REGION" in partial["note"])

untruncated = sd.analyze(scan, full, 0.05, points_total=len(scan))
check("an untruncated scan claims no truncation",
      untruncated["points_truncated"] is False and untruncated["reference_truncated"] is False)
check("...and defaults to the same when no total is supplied — silence is not a claim",
      sd.analyze(scan, full, 0.05)["points_truncated"] is False)

# --------------------------------------------------------------------------------------------
# THE PRODUCERS. A flag the caller can never learn is a flag that is never set, so the two
# functions that DO the truncating have to be able to say so.
# --------------------------------------------------------------------------------------------
text = "\n".join(f"{i * 0.001} 0 0" for i in range(1200))
kept, total = sd.parse_point_cloud_counted(text, max_points=1000)
check("parse_point_cloud_counted reports the readable total, not the capped one",
      len(kept) == 1000 and total == 1200, f"kept {len(kept)} of {total}")
check("...and counts an exactly-full file as untruncated",
      sd.parse_point_cloud_counted("\n".join(f"{i} 0 0" for i in range(1000)),
                                   max_points=1000)[1] == 1000)
check("the legacy array-only form still works, for callers that want no metadata",
      sd.parse_point_cloud("0 0 0\n1 1 1\n").shape == (2, 3))

# --------------------------------------------------------------------------------------------
# CAN THE FLAG EVER BE SET? — the hole the first draft of this file had, found by mutation.
#
# Everything above tests what `analyze` DOES with `reference_truncated=True`. Nothing tested that
# anything ever passes it True. Both mutations "the producer never reports its cap" (return False
# unconditionally) and "the route stops threading the flag" left this file reporting a clean tree —
# so the refusal could have been dead code, correct and unreachable, and the gate would have agreed
# with itself. *Verifying a refusal is not verifying that anything can reach it.*
#
# The producer is exercised against a FAKE geometry iterator rather than a real IFC, because what is
# under test is the cap arithmetic and not ifcopenshell. Both functions it reaches for are imported
# inside the function body, so they can be substituted here.
# --------------------------------------------------------------------------------------------
import types  # noqa: E402


class _FakeShape:
    def __init__(self, n):
        self.geometry = types.SimpleNamespace(verts=[0.0] * (3 * n))


class _FakeIterator:
    """Yields `chunks` elements of `per` vertices each."""

    def __init__(self, chunks, per):
        self._left, self._per = chunks, per

    def initialize(self):
        return self._left > 0

    def get(self):
        return _FakeShape(self._per)

    def next(self):
        self._left -= 1
        return self._left > 0


def _with_fake_geometry(chunks, per, max_points):
    """Run `model_surface_points_capped` against a fake iterator of known size."""
    fake_geom = types.ModuleType("ifcopenshell.geom")
    fake_geom.settings = lambda: None
    fake_ifc = types.ModuleType("ifcopenshell")
    fake_ifc.geom = fake_geom
    fake_geomconf = types.ModuleType("aec_data.geomconf")
    fake_geomconf.bounded_iterator = lambda *a, **k: _FakeIterator(chunks, per)
    saved = {k: sys.modules.get(k) for k in
             ("ifcopenshell", "ifcopenshell.geom", "aec_data.geomconf")}
    sys.modules.update({"ifcopenshell": fake_ifc, "ifcopenshell.geom": fake_geom,
                        "aec_data.geomconf": fake_geomconf})
    try:
        return sd.model_surface_points_capped(object(), max_points=max_points)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


over_verts, over_flag = _with_fake_geometry(chunks=10, per=100, max_points=250)
check("the producer SETS the flag when the cap is reached — without this the refusal is dead code",
      over_flag is True, f"truncated={over_flag} verts={len(over_verts)}")
check("...and caps the array it returns",
      len(over_verts) == 250, f"{len(over_verts)} vertices")

under_verts, under_flag = _with_fake_geometry(chunks=3, per=100, max_points=100000)
check("...and does NOT claim truncation on a model that fits",
      under_flag is False, f"truncated={under_flag} verts={len(under_verts)}")

# --------------------------------------------------------------------------------------------
# IS THE FLAG THREADED THROUGH THE ROUTE? — the second half of the same hole.
#
# This one is read from the source rather than exercised, and the limit is stated rather than
# glossed: driving `/scan/deviation` needs a project with an uploaded source IFC and a real
# tessellation, which this gate deliberately does not build. So it asserts the CALL — both keywords
# present, and each fed from the capped/counted producer rather than from a literal, which is the
# form the mutation took. `test_pin_pgnull`'s lesson (asserting the statement is not asserting the
# behaviour) applies to the arithmetic, and the arithmetic is exercised above; what is left here is
# wiring, which is exactly what source can answer.
# --------------------------------------------------------------------------------------------
import ast  # noqa: E402
from pathlib import Path  # noqa: E402

ROUTE = Path(__file__).resolve().parent / "src" / "aec_api" / "routers" / "analysis.py"
_tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
_fn = next((n for n in ast.walk(_tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "scan_deviation"), None)
check("PRECONDITION: the scan_deviation route function was found",
      _fn is not None, str(ROUTE))

_calls = [c for c in ast.walk(_fn)
          if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
          and c.func.attr == "analyze"] if _fn else []
check("PRECONDITION: the route still calls analyze exactly once",
      len(_calls) == 1, f"{len(_calls)} call(s)")

if _calls:
    _kw = {k.arg: k.value for k in _calls[0].keywords}
    check("the route passes reference_truncated", "reference_truncated" in _kw)
    check("the route passes points_total", "points_total" in _kw)
    # A literal would satisfy "passes it" while meaning the producer is ignored — which is what the
    # mutation did by dropping the keyword entirely, and what a lazier fix would do by hardcoding.
    check("...and neither is a hardcoded constant",
          all(not isinstance(v, ast.Constant) for v in
              (_kw.get("reference_truncated"), _kw.get("points_total")) if v is not None),
          f"{ {k: type(v).__name__ for k, v in _kw.items()} }")

_src = ROUTE.read_text(encoding="utf-8")
check("the route uses the producers that CAN report a cap",
      "model_surface_points_capped" in _src and "parse_point_cloud_counted" in _src)

# --------------------------------------------------------------------------------------------
# PRECONDITIONS — a suite of `check`s over a module that failed to import would print nothing
# and exit 0, and the caps must be what this file claims they are.
# --------------------------------------------------------------------------------------------
import inspect  # noqa: E402

check("PRECONDITION: the reference cap is still the value this file reasons about",
      inspect.signature(sd.model_surface_points_capped).parameters["max_points"].default == 200000)
check("PRECONDITION: the scan cap is still the value this file reasons about",
      inspect.signature(sd.parse_point_cloud_counted).parameters["max_points"].default == 500000)
check("PRECONDITION: the reference cap still BREAKS the element loop, which is why it drops "
      "whole elements rather than thinning evenly",
      "break" in inspect.getsource(sd.model_surface_points_capped))

print()
if FAILURES:
    print(f"scan_trunc: {len(FAILURES)} FAILED — {FAILURES}")
    sys.exit(1)
print("scan_trunc: all checks passed — a deviation figure is never computed against a model that "
      "was cut short; a truncated scan keeps its verdict and reports its coverage.")
