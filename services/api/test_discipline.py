"""Discipline quantity roll-up (rebar tonnage / MEP runs / structural volume) — deterministic test
with a fake model + stubbed quantity reader (no IFC fixture; restores globals so it's process-safe).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_discipline.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from aec_data import qto   # noqa: E402


class FakeModel:
    def __init__(self, by):
        self._by = by

    def by_type(self, cls):
        return self._by.get(cls, [])


_orig_q, _orig_geom = qto._quantities, qto._GEOM_OK
try:
    qto._quantities = lambda el: el          # a "quantities" dict IS the element here
    qto._GEOM_OK = False                       # no geometry fallback in the test
    model = FakeModel({
        "IfcReinforcingBar": [{"weight": 200.0}, {"weight": 300.0}],   # 500 kg = 0.5 t
        "IfcDuctSegment": [{"length": 5.0}, {"length": 3.0}],           # 8 m, 2 seg
        "IfcPipeSegment": [{"length": 10.0}],                           # 10 m, 1 seg
        "IfcBeam": [{"volume": 2.0}], "IfcColumn": [{"volume": 1.0}],   # 3 m3
    })
    d = qto.discipline_summary(model, settings=None)
    assert d["rebar"]["weight_kg"] == 500.0 and d["rebar"]["tonnes"] == 0.5, d["rebar"]
    assert d["rebar"]["estimated"] is False, d["rebar"]            # weights modelled -> not estimated
    assert d["mep"]["duct_m"] == 8.0 and d["mep"]["pipe_m"] == 10.0, d["mep"]
    assert d["mep"]["counts"]["duct"] == 2 and d["mep"]["counts"]["pipe"] == 1, d["mep"]["counts"]
    assert d["structure"]["element_volume_m3"] == 3.0, d["structure"]

    # rebar with no NetWeight -> estimated from volume x steel density (7850)
    model2 = FakeModel({"IfcReinforcingBar": [{"volume": 0.1}]})       # 0.1 m3 * 7850 = 785 kg
    d2 = qto.discipline_summary(model2, settings=None)
    assert d2["rebar"]["weight_kg"] == 785.0 and d2["rebar"]["estimated"] is True, d2["rebar"]
finally:
    qto._quantities, qto._GEOM_OK = _orig_q, _orig_geom

print("DISCIPLINE OK - rebar 0.5 t from NetWeight (estimated=False); MEP duct 8 m/2 seg + pipe 10 m/1 "
      "seg; structural volume 3.0 m3; rebar-without-weight estimated 785 kg from volume x 7850 (estimated=True)")
