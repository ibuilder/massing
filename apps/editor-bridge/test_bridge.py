"""Bonsai bridge safety gating (no Blender needed) — save-first, chunking, confirm gate, dry-run.
Run: python test_bridge.py"""
from bridge import BonsaiBridge, ExecutionResult, Plan

b = BonsaiBridge()

# small edit: one save step + one execute step; snippet calls the recipe and saves
p = b.plan("set_pset", {"ifc_class": "IfcSlab", "pset": "Pset_SlabCommon", "prop": "LoadBearing", "value": True})
assert isinstance(p, Plan), type(p)
assert p.steps[0].op == "save", p.steps                          # save BEFORE execute
assert p.chunks == 1 and p.steps[1].op == "execute"
assert "recipes.set_pset(model" in p.steps[1].code and "tool.Ifc.save()" in p.steps[1].code
assert p.confirm_required is True

# large selection chunks to max_elements_per_call (config default 200)
cap = int(b.safety.get("max_elements_per_call", 200))
big = b.plan("batch_tag", {"ifc_class": "IfcWall", "label": "x"}, element_count=cap * 2 + 1)
exec_steps = [s for s in big.steps if s.op == "execute"]
assert big.chunks == 3 and len(exec_steps) == 3, big.chunks      # ceil((2*cap+1)/cap) = 3

# dry-run is the default and never connects
d = b.execute("set_pset", {"ifc_class": "IfcSlab"})
assert isinstance(d, ExecutionResult), type(d)
assert d.dry_run is True and d.plan.chunks == 1 and d.results == []

# live execute without confirm is blocked (arbitrary-Python gate)
try:
    b.execute("set_pset", {"ifc_class": "IfcSlab"}, confirm=False, dry_run=False)
    raise AssertionError("expected the confirm gate to block")
except PermissionError as e:
    assert "gated" in str(e)

print("BRIDGE OK - save-first, chunk to cap (3 chunks), dry-run default, confirm gate blocks arbitrary "
      "code; plan/execute return typed Plan/ExecutionResult dataclasses")
