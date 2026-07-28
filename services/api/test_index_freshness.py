"""
The element index must be able to say it has gone behind the model.

Found live: `/elements` returned 2 for a house the takeoff counted as 7. Neither number was wrong —
`/elements` reads a `props.json` snapshot written at publish time, the takeoff reads the IFC on disk,
and authoring edits move the IFC without rebuilding the snapshot. After a republish `/elements` went
2 → 7 and matched exactly.

So the defect was never the count. It was that a stale snapshot and a current one look identical from
the outside. This pins the three-way distinction that fixes it: current, behind, and *unknown* — and
that the third is never quietly reported as the first.
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# The comparison the endpoint makes, stated as a function of its two inputs.
def staleness(built_from, current):
    return None if (not built_from or not current) else (built_from != current)


check("same fingerprint means current", staleness("k1", "k1") is False)
check("different fingerprint means BEHIND", staleness("k1", "k2") is True)
check("no stamp on the index is UNKNOWN, not current", staleness(None, "k2") is None,
      "an index written before stamping cannot claim to be fresh")
check("no reachable model is UNKNOWN, not current", staleness("k1", None) is None)
check("neither side known is UNKNOWN", staleness(None, None) is None)

# The distinction that matters: unknown must not collapse into false.
check("UNKNOWN is not the same value as CURRENT", staleness(None, "k") is not False,
      "conflating them is how a stale list gets presented as a smaller building")

# --- the fingerprint itself ---------------------------------------------------------------------
from aec_data.ifc_loader import content_key  # noqa: E402

a = content_key("/tmp/model.ifc", (1000, 500))
b = content_key("/tmp/model.ifc", (1001, 500))   # rewritten: mtime moves
c = content_key("/tmp/model.ifc", (1000, 501))   # rewritten: size moves
check("a rewritten file changes the key (mtime)", a != b)
check("a rewritten file changes the key (size)", a != c)
check("an untouched file keeps its key", a == content_key("/tmp/model.ifc", (1000, 500)),
      "otherwise every read would report a false 'behind'")
check("a file with no stat is not silently equal to one with",
      content_key("/tmp/model.ifc", None) != a)

# --- the endpoint exists and is registered ahead of /elements/{guid} -------------------------------
from aec_api.routers import properties  # noqa: E402

paths = [r.path for r in properties.router.routes]
fresh = "/projects/{pid}/elements/freshness"
check("the freshness route is registered", fresh in paths)
guid_route = "/projects/{pid}/elements/{guid}"
if guid_route in paths:
    check("...and BEFORE /elements/{guid}, or FastAPI matches it as a guid",
          paths.index(fresh) < paths.index(guid_route))

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_index_freshness OK")
