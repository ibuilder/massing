"""FOLDER-OWNER — one accessor for a folder's owning role, and the invariant that lets it collapse
three call sites into one.

`folder_template.owner_of` had ZERO callers while `docmanager.py` reimplemented its one-line body at
three sites. Nothing was broken — the owner role reached the client from all three — but three copies
of an accessor do not follow the accessor when its semantics change, which is the whole reason the
accessor exists. R37-CONSOLIDATE shipped this same fix three times on 2026-08-28.

The three were NOT identical, and that is the part worth a test rather than a commit message:

* `list_folder`  — `node["owner_role"] if node else None`.   Exactly `owner_of`.
* `upload`       — `node.get("owner_role")`, with no None-guard at all. Safe only because
                   `is_valid()` raises immediately above it; the guard was structural, not local.
* `move`         — `node.get("owner_role") if node else f.get("owner_role")`. **Different rule**: it
                   keeps the file's EXISTING owner when the destination folder is off-taxonomy,
                   where `owner_of` would answer None.

`move`'s extra branch turned out to be DEAD, and finding that out is the useful part. The first
rewrite preserved it as `owner_of(new_folder) or f.get("owner_role")` and asserted the fallback with
`(owner_of("99-NOT-A-FOLDER") or "KEPT-OLD") == "KEPT-OLD"` — which tests the `or` operator, not
`docmanager`. The mutation check caught it: deleting the fallback from `move` broke no test. It could
not, because `move` raises `ValueError` on an invalid destination in its first two lines, so the
folder is always in the taxonomy by the time the owner is read. All three sites are now identical.

*An unreachable branch and a well-guarded one look the same from the call site; only the mutation
tells them apart.* The same reasoning deleted a redundant entitlement filter earlier in this series.

The `STANDARD_TREE` invariant is still asserted below, on narrower grounds: three call sites now
report `owner_of` directly, so a node with a null owner would surface as "this folder has no owner"
in the file list, on upload, and after a move.

Run: PYTHONPATH="src:../data/src" ./.venv/bin/python test_folder_owner.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_folder_owner.db"
os.environ.setdefault("STORAGE_DIR", "./test_storage_folder_owner")
os.environ.pop("AEC_RBAC", None)

from aec_api import folder_template as ft  # noqa: E402

_fail = 0


def check(cond, msg):
    global _fail
    if not cond:
        _fail += 1
        print(f"FAIL  {msg}")
    else:
        print(f"PASS  {msg}")


# --- THE INVARIANT the `move` rewrite rests on -----------------------------------------------------
missing = [n["path"] for n in ft.STANDARD_TREE if "owner_role" not in n]
nulls = [n["path"] for n in ft.STANDARD_TREE if n.get("owner_role") is None]
check(not missing, f"every STANDARD_TREE node declares an owner_role (missing: {missing})")
check(not nulls, f"no STANDARD_TREE node has a null owner_role (null: {nulls})")
check(len(ft.STANDARD_TREE) > 0, "STANDARD_TREE is not empty — an empty tree satisfies the two "
                                 "checks above vacuously and would prove nothing")

# ...therefore: owner_of answers None IFF the path is unknown. This is the equivalence `move` uses.
bad_paths = [n["path"] for n in ft.STANDARD_TREE if ft.owner_of(n["path"]) is None]
check(not bad_paths, f"owner_of is non-None for EVERY valid path (None for: {bad_paths})")
check(ft.owner_of("99-NOT-A-FOLDER") is None, "owner_of is None for an unknown path")
check(not ft.is_valid("99-NOT-A-FOLDER"), "...and that path really is invalid (positive control: the "
                                          "None above is unknown-path, not a null owner)")

# --- the accessor is REACHED, not merely defined ---------------------------------------------------
# The defect being fixed was an accessor with no callers. A test that only exercises `owner_of`
# directly would still pass if docmanager kept its three inline copies, so assert the call sites.
import inspect  # noqa: E402

from aec_api import docmanager  # noqa: E402

src = inspect.getsource(docmanager)
check(src.count("folder_template.owner_of(") == 3,
      f"docmanager routes all three owner lookups through owner_of "
      f"(found {src.count('folder_template.owner_of(')})")
check('node["owner_role"]' not in src and 'node.get("owner_role")' not in src,
      "no inline copy of the accessor's body survives in docmanager")

# --- why `move` needs no fallback: the guard is structural, and it is a REAL guard ------------------
# Asserted through the function, not by re-evaluating the expression it uses. `move` refusing an
# off-taxonomy destination is the whole reason `owner_of` there can never answer None.
try:
    docmanager.move("p-folder-owner", "nope", "99-NOT-A-FOLDER", "tester")
    check(False, "move must refuse an off-taxonomy destination")
except ValueError:
    check(True, "move refuses an off-taxonomy destination (so owner_of can never be None there)")
except KeyError:
    check(False, "move reached the file lookup — the folder guard did NOT fire first")

# Positive control: a VALID destination must get past the folder guard, otherwise the check above
# would pass on a `move` that rejects everything.
try:
    docmanager.move("p-folder-owner", "no-such-file", ft.STANDARD_TREE[0]["path"], "tester")
    check(False, "unreachable: there is no such file")
except KeyError:
    check(True, "a valid destination passes the folder guard and fails later, on the missing file")
except ValueError as exc:
    check(False, f"a valid destination was rejected by the folder guard: {exc}")

print()
if _fail:
    raise SystemExit(f"folder_owner: {_fail} check(s) failed")
print("folder_owner: all checks passed — one accessor reached from all three call sites, no inline "
      "copy left, and `move`'s folder guard proven to be the reason its owner lookup needs no "
      "fallback (the branch it used to carry was unreachable).")
