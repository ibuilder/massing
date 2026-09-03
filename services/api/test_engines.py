"""Focused unit tests for small pure engines that had no coverage: entitlements (tier gating) and
dev_property (acquisition/tax summary, incl. divide-by-zero guards).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_engines.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from aec_api import dev_property as dp  # noqa: E402
from aec_api import tiers as ent  # noqa: E402

# --- entitlements ------------------------------------------------------------
assert ent.normalize(None) == "free"
assert ent.normalize("bogus") == "free"
assert ent.normalize("enterprise") == "enterprise"
# free unlocks everything today (product decision) — every tier returns the full feature set
for tier in (None, "free", "pro", "enterprise"):
    feats = ent.features_for(tier)
    assert feats and all(feats.values()), (tier, feats)
    assert ent.allows(tier, "ai") and ent.allows(tier, "viewer"), tier
# unknown feature is denied, never KeyError
assert ent.allows("free", "nonexistent_feature") is False

# --- dev_property ------------------------------------------------------------
s = dp.summarize({
    "purchase_price": 5_000_000, "land_sf": 40_000, "building_sf": 25_000, "parking_sf": 10_000,
    "taxes": {"school": 60_000, "county": 20_000, "town": 15_000, "fire": 5_000}})
assert s["total_taxes"] == 100_000.0, s
assert s["purchase_price"] == 5_000_000, s
assert s["price_per_building_sf"] == 200.0, s            # 5M / 25k
assert s["price_per_land_sf"] == 125.0, s                # 5M / 40k
assert s["tax_per_building_sf"] == 4.0, s                # 100k / 25k
assert s["far_existing"] == 0.62, s                      # 25k / 40k
# proforma wiring: taxes -> opex, price -> acquisition
assert s["deltas"]["opex_annual_add"] == 100_000.0, s
assert s["deltas"]["acquisition_amount"] == 5_000_000, s

# divide-by-zero guards: an empty/starter property never raises and yields zeroed ratios
z = dp.summarize(dp.starter())
assert z["total_taxes"] == 0.0 and z["purchase_price"] == 0, z
assert z["price_per_building_sf"] == 0.0 and z["far_existing"] == 0.0, z
# missing keys entirely (not even the starter shape) still degrade gracefully
assert dp.summarize({})["total_taxes"] == 0.0

print("ENGINES OK - entitlements tiers gate (free unlocks all, unknown feature denied, bad tier -> free); "
      "dev_property summarize computes taxes/per-SF/FAR + proforma deltas and guards divide-by-zero")
