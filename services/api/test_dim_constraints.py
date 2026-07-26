"""W10-9 / R23-CONSTRAINTS — dimensional locks, and saying so when they cannot all hold.

This item sat gated for months behind "planegcs, LGPL". The roadmap unblocked it by taking a
`kiwisolver` dependency, on the reasoning that Cassowary's inequalities-and-strengths model fits BIM
locks. That reasoning is right about the shape and wrong about the need: numpy and scipy are already
here, and this shape is linear least-squares with priority tiers — `lstsq`'s **rank** is the degrees
of freedom and its **residual** is whether a tier is satisfiable, which are the two numbers the UX
needs. No dependency was added. The wheel downloads fine; checking whether it was necessary first is
the same habit that has caught six wrong premises today.

What is tested here is mostly *what the solver refuses to do quietly*.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_dim_constraints.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_dim_constraints.db"
os.environ["STORAGE_DIR"] = "./test_storage_dim_constraints"
if os.path.exists("./test_dim_constraints.db"):
    os.remove("./test_dim_constraints.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import dim_constraints as dc  # noqa: E402

# ---- the ordinary case: a wall locked 3000 off a grid ---------------------------------------------
r = dc.solve({"grid": 0.0, "wall": 1234.0},
             [{"id": "L1", "kind": "fix", "a": "grid", "value": 0.0},
              {"id": "L2", "kind": "distance", "a": "grid", "b": "wall", "distance": 3000.0}])
assert r["solved"] and not r["conflicts"], r
assert abs(r["values"]["wall"] - 3000.0) < 1e-6, r["values"]
assert r["dof"] == 0, r["dof"]

# ---- UNDER-constrained is reported, not defaulted --------------------------------------------------
# A system with freedom left has infinitely many solutions. Picking one quietly is how a "solved"
# sketch drifts on the next edit.
u = dc.solve({"a": 0.0, "b": 0.0, "c": 0.0},
             [{"kind": "fix", "a": "a", "value": 100.0}])
assert u["solved"], u
assert u["dof"] == 2, u["dof"]                 # b and c are free and the result says so
assert "under-constrained" in u["note"]

# ---- OVER-constrained NAMES the conflict -----------------------------------------------------------
# Two required locks that cannot both hold are a modelling error. Satisfying whichever the solver
# reached first produces geometry that looks deliberate and is not.
o = dc.solve({"a": 0.0, "b": 0.0},
             [{"id": "keep-3000", "kind": "distance", "a": "a", "b": "b", "distance": 3000.0},
              {"id": "keep-4000", "kind": "distance", "a": "a", "b": "b", "distance": 4000.0}])
assert not o["solved"], o
assert o["conflicts"], o
assert {c["id"] for c in o["conflicts"]} & {"keep-3000", "keep-4000"}, o["conflicts"]
assert all(c["strength"] == "required" for c in o["conflicts"]), o["conflicts"]

# ---- strength is a TIER, not a weight ---------------------------------------------------------------
# A `required` lock is not "a very heavy soft constraint". If strengths were blended, a strong
# preference could bend a hard lock by a millimetre — the failure that makes people stop trusting
# locks entirely.
t = dc.solve({"a": 0.0, "b": 0.0},
             [{"id": "hard", "kind": "distance", "a": "a", "b": "b", "distance": 3000.0},
              {"id": "fix-a", "kind": "fix", "a": "a", "value": 0.0},
              {"id": "prefer", "kind": "fix", "a": "b", "value": 9999.0, "strength": "strong"}])
assert abs(t["values"]["b"] - 3000.0) < 1e-6, t["values"]      # not 3000-and-a-bit, and not 9999
assert abs(t["values"]["a"]) < 1e-6, t["values"]
assert [c["id"] for c in t["conflicts"]] == ["prefer"], t["conflicts"]
assert t["solved"], "a preference yielding is the system working, not a failure"

# ...and a weaker tier still uses whatever freedom the stronger ones left
w = dc.solve({"a": 0.0, "b": 0.0, "c": 0.0},
             [{"kind": "fix", "a": "a", "value": 0.0},
              {"kind": "distance", "a": "a", "b": "b", "distance": 3000.0},
              {"id": "c-pref", "kind": "fix", "a": "c", "value": 7500.0, "strength": "weak"}])
assert abs(w["values"]["c"] - 7500.0) < 1e-6, w["values"]      # c was free, so the preference holds
assert not w["conflicts"] and w["dof"] == 0, w

# ---- equal spacing says "evenly", not "at this pitch" ----------------------------------------------
# Pinning the pitch as well would make "evenly spaced" silently mean something stronger than asked.
e = dc.solve({"g1": 0.0, "g2": 100.0, "g3": 900.0, "g4": 1000.0},
             [{"kind": "fix", "a": "g1", "value": 0.0},
              {"kind": "fix", "a": "g4", "value": 9000.0},
              {"kind": "equal_spacing", "vars": ["g1", "g2", "g3", "g4"]}])
assert e["solved"] and e["dof"] == 0, e
sp = [e["values"]["g2"] - e["values"]["g1"], e["values"]["g3"] - e["values"]["g2"],
      e["values"]["g4"] - e["values"]["g3"]]
assert all(abs(s - 3000.0) < 1e-6 for s in sp), sp
# on its own it leaves the pitch free — that is a separate lock's job
free = dc.solve({"g1": 0.0, "g2": 1.0, "g3": 2.0},
                [{"kind": "equal_spacing", "vars": ["g1", "g2", "g3"]}])
assert free["dof"] == 2, free["dof"]

# ---- clearances are CHECKED, never enforced ---------------------------------------------------------
# Sliding geometry to satisfy a code minimum would move a wall somebody placed on purpose.
cl = dc.solve({"a": 0.0, "b": 800.0},
              [{"kind": "fix", "a": "a", "value": 0.0},
               {"kind": "fix", "a": "b", "value": 800.0},
               {"id": "egress", "kind": "min_clearance", "a": "a", "b": "b", "min": 1200.0}])
assert not cl["solved"], cl
assert cl["violations"] == [{"id": "egress", "a": "a", "b": "b", "min": 1200.0,
                             "actual": 800.0, "short_by": 400.0}], cl["violations"]
assert abs(cl["values"]["b"] - 800.0) < 1e-6, "the geometry was NOT moved to satisfy the minimum"
ok = dc.solve({"a": 0.0, "b": 1500.0},
              [{"kind": "fix", "a": "a", "value": 0.0}, {"kind": "fix", "a": "b", "value": 1500.0},
               {"kind": "min_clearance", "a": "a", "b": "b", "min": 1200.0}])
assert ok["solved"] and not ok["violations"], ok

# ---- a conflicted row is NOT frozen into the weaker tiers -------------------------------------------
# Freezing one would propagate a single modelling error into every tier below it as a phantom lock.
p = dc.solve({"a": 0.0, "b": 0.0, "c": 0.0},
             [{"id": "x", "kind": "distance", "a": "a", "b": "b", "distance": 3000.0},
              {"id": "y", "kind": "distance", "a": "a", "b": "b", "distance": 4000.0},
              {"id": "z", "kind": "fix", "a": "c", "value": 500.0, "strength": "medium"}])
assert abs(p["values"]["c"] - 500.0) < 1e-6, p["values"]   # the unrelated tier still solves
assert p["conflicts"], p

# ---- malformed input is REFUSED, not dropped --------------------------------------------------------
# A lock nobody applied is worse than an error: the model looks constrained and is not.
for bad in ([{"kind": "nope", "a": "a"}],
            [{"kind": "distance", "a": "a", "b": "missing", "distance": 1.0}],
            [{"kind": "distance", "a": "a", "b": "a"}],                 # no distance given
            [{"kind": "equal_spacing", "vars": ["a"]}],
            [{"kind": "fix", "a": "a", "value": 0.0, "strength": "sorta"}],
            ["not an object"]):
    try:
        dc.solve({"a": 0.0}, bad)
        raise AssertionError(f"accepted {bad!r}")
    except dc.ConstraintError:
        pass

# every kind and strength is documented, so a UI need not invent the explanation
assert set(dc.KINDS) == {"fix", "equal", "distance", "offset", "equal_spacing", "min_clearance"}
for k, v in dc.KINDS.items():
    assert len(v) > 15, k
assert dc.STRENGTHS[0] == "required", dc.STRENGTHS

# ---- degenerate inputs are answers ------------------------------------------------------------------
empty = dc.solve({}, [])
assert empty["solved"] and empty["dof"] == 0 and empty["values"] == {}
none = dc.solve({"a": 42.0}, [])
assert none["dof"] == 1 and abs(none["values"]["a"] - 42.0) < 1e-6, none   # untouched, and free

print("W10-9 / R23-CONSTRAINTS OK - dimensional locks solve as a linear system with priority tiers, "
      "and NO new dependency was added. The roadmap unblocked this by taking kiwisolver on the "
      "reasoning that Cassowary's inequalities-and-strengths model fits BIM locks; that is right about "
      "the shape and wrong about the need, because numpy and scipy are already here and lstsq's RANK "
      "is the degrees of freedom while its RESIDUAL is whether a tier is satisfiable - the two numbers "
      "the UX actually wants. Three refusals make it trustworthy. An OVER-constrained system NAMES the "
      "constraints that cannot hold, because satisfying whichever the solver reached first produces "
      "geometry that looks deliberate and is not. STRENGTH IS A TIER, NOT A WEIGHT - blending them "
      "would let a strong preference bend a hard lock by a millimetre, which is what makes people stop "
      "trusting locks - so each tier is satisfied exactly, frozen, and the next may only move what is "
      "left free, and a CONFLICTED row is never frozen because that would propagate one modelling "
      "error into every weaker tier as a phantom lock. UNDER-constrained is reported rather than "
      "defaulted, since picking one of infinitely many solutions quietly is how a solved sketch drifts "
      "on the next edit. And clearances are CHECKED, never enforced: sliding geometry to satisfy a "
      "code minimum would move something somebody placed on purpose.")
