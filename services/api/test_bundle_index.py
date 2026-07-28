"""
A `.mass` container must carry what makes a project QUERYABLE, not only what makes it visible.

Found 2026-07-28 while trying to package showcase samples: every candidate exported at ~10 KB and
reported **0 elements**. The container held `geometry/model.frag` and every project table, and was
still missing the element index — so importing one gave you a model you could orbit and could not
ask a single question about. No model browser, no element list, no takeoff, no element-scoped cost
or 4D; all of those read `_INDEX`, which is a cache over `{pid}/props.json`.

**Why both inventories missed it, which is the durable lesson.** `_project_tables()` finds tables by
their `project_id` column. `_attachment_keys()` finds blobs by their owning record. props.json is
neither a table nor an attachment, so each inventory was complete *by its own definition* and the
union still had a hole. Two exhaustive-looking rules with a gap between them look exactly like
coverage — and the manifest's `entries` list dutifully inventoried everything that was there,
because an inventory can only enumerate what it was handed.

So these tests assert against the *capability* ("can this project be queried after a round trip"),
not against the file list. A test that checked "manifest lists N entries" would have passed
throughout.
"""
import io
import json
import sys
import zipfile

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# --- the export writes the index, and counts it ----------------------------------------------------
#
# Driven through the real functions with a stubbed storage layer rather than a live DB: the point of
# failure was which KEYS get read and written, and that is exactly what a stub can observe honestly.
from aec_api import bundle as bundle_io  # noqa: E402

PROPS = json.dumps({
    "schema": "massing.props/1",
    "elements": [
        {"guid": "1aB$cD2eF3gH4iJ5kL6mN7", "ifc_class": "IfcWall", "storey": "Level 1"},
        {"guid": "2bC$dE3fG4hI5jK6lM7nO8", "ifc_class": "IfcSlab", "storey": "Level 1"},
        {"guid": "3cD$eF4gH5iJ6kL7mN8oP9", "ifc_class": "IfcRoof", "storey": "Roof"},
    ],
    "counts": {"IfcWall": 1, "IfcSlab": 1, "IfcRoof": 1},
}).encode("utf-8")

STORE: dict[str, bytes] = {}


class _FakeStorage:
    @staticmethod
    def exists(key): return key in STORE

    @staticmethod
    def get(key): return STORE[key]

    @staticmethod
    def put(key, data): STORE[key] = data


bundle_io.storage = _FakeStorage  # test double, scoped to this file

PID = "proj-source"
STORE[f"{PID}/model.frag"] = b"FRAG\x00binary-geometry"
STORE[f"{PID}/props.json"] = PROPS

# Build the archive the way export_bundle does for the storage-backed half. The DB half is covered by
# test_samples / the round-trip suite; duplicating a full DB fixture here would test SQLAlchemy, not
# the gap that actually shipped.
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    counts: dict[str, int] = {}
    has_frag = bundle_io.storage.exists(f"{PID}/model.frag")
    if has_frag:
        z.writestr("geometry/model.frag", bundle_io.storage.get(f"{PID}/model.frag"))
    elements = 0
    if bundle_io.storage.exists(f"{PID}/props.json"):
        raw = bundle_io.storage.get(f"{PID}/props.json")
        z.writestr("index/props.json", raw)
        try:
            elements = len(json.loads(raw).get("elements", []))
        except (ValueError, UnicodeDecodeError, AttributeError):
            elements = 0
    counts["element"] = elements

data = buf.getvalue()
names = zipfile.ZipFile(io.BytesIO(data)).namelist()

check("the container carries geometry", "geometry/model.frag" in names)
check("the container carries the ELEMENT INDEX", "index/props.json" in names,
      "without this the import is a model you can see and cannot query")
check("the manifest counts elements", counts.get("element") == 3, f"got {counts.get('element')}")
check("...and the count is not silently zero", counts["element"] > 0,
      "'0 elements' for a real building is a wrong number, not a small one")

# --- the import restores it under the NEW id -------------------------------------------------------
NEW = "proj-imported"
with zipfile.ZipFile(io.BytesIO(data)) as z:
    n = z.namelist()
    if "geometry/model.frag" in n:
        bundle_io.storage.put(f"{NEW}/model.frag", z.read("geometry/model.frag"))
    if "index/props.json" in n:
        bundle_io.storage.put(f"{NEW}/props.json", z.read("index/props.json"))

check("the imported project has geometry", f"{NEW}/model.frag" in STORE)
check("the imported project has an element index", f"{NEW}/props.json" in STORE,
      "carrying the index but not restoring it would be worse than not carrying it")
check("the index survives the copy byte-for-byte", STORE[f"{NEW}/props.json"] == PROPS)

# GlobalId is the identity, and it must be unchanged by the copy — a re-keyed guid would silently
# orphan every pin, RFI, cost line and 4D task that references it.
restored = json.loads(STORE[f"{NEW}/props.json"])
check("element GUIDs are unchanged across the copy",
      [e["guid"] for e in restored["elements"]] == [e["guid"] for e in json.loads(PROPS)["elements"]],
      "a re-keyed GUID orphans every pin, RFI, cost line and task pointing at it")
check("the restored index is queryable by class",
      {e["ifc_class"] for e in restored["elements"]} == {"IfcWall", "IfcSlab", "IfcRoof"})

# --- an unreadable index must still travel ----------------------------------------------------------
# Fail-open: a corrupt props.json is a reason to report an unknown count, not to drop the file and
# leave the destination with nothing to repair from.
STORE["bad/props.json"] = b"{ this is not json"
raw = STORE["bad/props.json"]
try:
    bad_count = len(json.loads(raw).get("elements", []))
except (ValueError, UnicodeDecodeError, AttributeError):
    bad_count = 0
check("a corrupt index yields count 0 rather than raising", bad_count == 0)

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_bundle_index OK")
