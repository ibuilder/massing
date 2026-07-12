"""Decimal-precise money helpers (P6).

Float arithmetic drifts at the cent boundary — `round(2.675, 2)` is `2.67` (float repr), and splitting
$100 three ways with `round(x, 2)` yields 33.33 + 33.33 + 33.33 = 99.99, losing a penny. These helpers
use `Decimal` with round-half-up (the money convention) plus a penny-accurate allocator, and return
plain `float`/`int` so existing call sites can adopt them incrementally without signature churn.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def _d(x: float | int | str | Decimal) -> Decimal:
    # str() first so we quantize the *decimal* value the caller meant, not the float's binary noise
    # (Decimal(0.1) == 0.1000000000000000055…, but Decimal(str(0.1)) == Decimal("0.1")).
    return x if isinstance(x, Decimal) else Decimal(str(x))


def q2(x: float | int | str | Decimal) -> float:
    """Round to cents, half-up (2.675 → 2.68) — the money-correct rounding, unlike float `round`."""
    return float(_d(x).quantize(_CENT, rounding=ROUND_HALF_UP))


def to_cents(x: float | int | str | Decimal) -> int:
    """Integer cents (half-up). Store/compare money as ints to sidestep float drift entirely."""
    return int((_d(x) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def allocate(total: float | int | str | Decimal, weights: list[float]) -> list[float]:
    """Split `total` across `weights` so the parts sum to exactly `total` to the cent.

    Distributes the leftover cents (largest-remainder method) to the shares with the biggest
    fractional parts, so a $100 three-way split is [33.34, 33.33, 33.33] — never 99.99.
    """
    n = len(weights)
    if n == 0:
        return []
    tc = to_cents(total)
    sw = sum(weights)
    if sw <= 0:
        return [0.0] * n
    raw = [tc * w / sw for w in weights]
    floors = [math.floor(r) for r in raw]
    remainder = tc - sum(floors)
    # hand out the remaining cents to the largest fractional parts, tie-broken by original order
    order = sorted(range(n), key=lambda i: (raw[i] - floors[i], -i), reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return [c / 100 for c in floors]
