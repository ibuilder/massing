"""Market Intelligence & cost escalation (Track M) + AI concept-render bridge (Track V).

Track M: the region/labour/location table, the warm/cold sector signal, escalation to the construction
midpoint, and the project market context read from a market_assumption record. Track V: the feature-
flagged render bridge builds a grounded prompt and no-ops (fabricates nothing) when disabled.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_market.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_market.db"
os.environ["STORAGE_DIR"] = "./test_storage_market"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_RENDER_BRIDGE", None)             # bridge OFF by default for this run
for _f in ("./test_market.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import market_intelligence as mi  # noqa: E402
from aec_api.main import app  # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


# --- engine unit checks (no HTTP) -------------------------------------------------------------
# escalate 1.0 to the midpoint of an 18-month build starting 2028: midpoint year = 2028 + 0.75 = 2028.75,
# years from BASE_YEAR 2026 = 2.75; NA rate 4.6% -> factor (1.046)**2.75
na_rate = mi.REGIONS["north_america"]["escalation_pct"] / 100.0
factor_full = (1 + na_rate) ** 2.75                   # unrounded factor the engine multiplies by
expect = round(factor_full, 4)                         # the reported (4-dp) escalation factor
esc = mi.escalate(1.0, "north_america", start_year=2028, duration_months=18)
assert esc["midpoint_year"] == 2028.75, esc["midpoint_year"]
assert esc["escalation_factor"] == expect, (esc["escalation_factor"], expect)
# no timeline -> no escalation (factor 1.0)
assert mi.escalate(1000.0, "europe")["escalation_factor"] == 1.0
# a rate override wins over the region default
assert mi.escalate(1.0, "asia", to_year=2027, rate_pct=10.0)["annual_rate_pct"] == 10.0
# sector temperature: data centres hot, residential cold, unknown -> neutral
assert mi.sector_temp("data_center")["temperature"] == "hot"
assert mi.sector_temp("residential")["temperature"] == "cold"
assert mi.sector_temp("llama_farm")["temperature"] == "neutral"
# unknown region falls back to the global average (never KeyErrors)
assert mi.region_data("atlantis")["region"] == "global_average"

with TestClient(app) as c:
    # snapshot: all regions + a two-speed signal
    snap = c.get("/market/snapshot").json()
    assert snap["base_year"] == 2026, snap["base_year"]
    assert {r["key"] for r in snap["regions"]} >= {"north_america", "europe", "asia"}, snap["regions"]
    assert "data_center" in snap["market_signal"]["hot"], snap["market_signal"]
    assert "residential" in snap["market_signal"]["cold"], snap["market_signal"]

    pid = c.post("/projects", json={"name": "Escalation Tower"}).json()["id"]

    # context with no assumption yet -> defaults, from_assumption False, factor 1.0 (no timeline)
    ctx0 = c.get(f"/projects/{pid}/market/context").json()
    assert ctx0["from_assumption"] is False, ctx0
    assert ctx0["escalation_factor"] == 1.0, ctx0

    # adopt a market assumption: NA data centre, 18-month build starting 2028
    a = _create(c, pid, "market_assumption", {"name": "Base case", "region": "north_america",
        "sector": "data_center", "construction_start_year": 2028, "duration_months": 18})
    c.post(f"/projects/{pid}/modules/market_assumption/{a['id']}/transition", json={"action": "adopt"})

    ctx = c.get(f"/projects/{pid}/market/context").json()
    assert ctx["from_assumption"] is True, ctx
    assert ctx["region"]["region"] == "north_america", ctx["region"]
    assert ctx["sector"]["temperature"] == "hot", ctx["sector"]
    assert ctx["escalation_factor"] == expect, (ctx["escalation_factor"], expect)

    # escalate a real amount through the project (reads the adopted assumption)
    e = c.get(f"/projects/{pid}/market/escalate", params={"amount": 1_000_000}).json()
    assert e["escalated_amount"] == round(1_000_000 * factor_full, 2), e
    assert e["midpoint_year"] == 2028.75, e

    # query params override the stored assumption
    eo = c.get(f"/projects/{pid}/market/escalate",
               params={"amount": 1_000_000, "rate_pct": 0}).json()
    assert eo["escalated_amount"] == 1_000_000, eo    # 0% -> no escalation

    # conceptual estimate now carries a market block
    ce = c.post(f"/projects/{pid}/estimate/conceptual",
                json={"building_type": "office", "gfa_sf": 50000, "region": "north_america"}).json()
    assert "market" in ce, list(ce.keys())
    assert ce["market"]["labour_usd_hr"] == mi.REGIONS["north_america"]["labour_usd_hr"], ce["market"]

    # the market-intelligence report renders
    rep = c.get(f"/projects/{pid}/reports/market_intelligence.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", (rep.status_code, rep.content[:8])

    # --- Track V: concept-render bridge, OFF by default ---------------------------------------
    st = c.get(f"/projects/{pid}/concept-render/status").json()
    assert st["enabled"] is False, st
    # request builds nothing (accepted False) while disabled
    req = c.post(f"/projects/{pid}/concept-render/request",
                 json={"style": "photoreal", "prompt": "dusk"}).json()
    assert req["accepted"] is False, req
    # ingest is a no-op while disabled — no record created
    ing = c.post(f"/projects/{pid}/concept-render/ingest",
                 json={"image_url": "https://example.com/x.png"}).json()
    assert ing["accepted"] is False, ing
    n = c.get(f"/projects/{pid}/modules/concept_render").json()
    assert isinstance(n, list) and len(n) == 0, n           # no record created while bridge is off

# --- Track V: bridge ON — prompt is grounded, ingest stores a record --------------------------
os.environ["AEC_RENDER_BRIDGE"] = "1"
import importlib  # noqa: E402

from aec_api import render_bridge  # noqa: E402

importlib.reload(render_bridge)
assert render_bridge.enabled() is True
prompt = render_bridge.build_prompt(
    {"use_mix": {"office": 0.7, "retail": 0.3}}, {"metrics": {"floors": 12, "use": "office", "gross_area_sf": 200000}},
    extra="golden hour", style="photoreal")
assert "office" in prompt and "12-storey" in prompt and "golden hour" in prompt, prompt
r = render_bridge.request({"variations": 20, "style": "massing"}, program={"uses": ["lab", "office"]})
assert r["accepted"] is True and r["variations"] == 8, r        # clamped 1..8
assert render_bridge.validate_ingest({"image_url": "https://cdn/x.png"})["accepted"] is True
assert render_bridge.validate_ingest({})["accepted"] is False   # image_url required

print("MARKET OK - escalation to construction midpoint (NA 4.6%/yr, factor "
      f"{expect}); warm/cold sector signal (data_center hot / residential cold); market_assumption "
      "drives project context + escalate; conceptual estimate carries a market block; report PDF "
      "served. RENDER BRIDGE OK - off by default fabricates nothing; on, builds a grounded prompt "
      "(clamped 1-8) and requires image_url to ingest.")
