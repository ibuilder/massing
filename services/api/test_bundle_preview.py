"""R28-BUNDLE — what a container holds, without importing it.

Export has always stated what it leaves behind (`manifest.excluded`). Import had no counterpart: the
only way to discover a bundle's contents was to import it, which creates a project. "Open it to find
out what is in it" is not a choice a user can decline.

The assertions that matter are the two refusals:

1. **an unreadable container is an ERROR, never an empty preview.** "Contains nothing" and "could not
   be read" render identically to someone about to click Import, and only one is safe to proceed from;
2. **a container from a newer build is refused HERE**, before the user commits — not at import, after
   they believe they have their data. The preview reuses the importer's validation deliberately, so a
   bundle that previews cleanly is one that will import; looser rules would be a promise the importer
   breaks.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_bundle_preview.py
"""
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, "src")

os.environ["DATABASE_URL"] = "sqlite:///./test_bundle_preview.db"
os.environ["STORAGE_DIR"] = "./test_storage_bundle_preview"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_bundle_preview.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import bundle  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def make_bundle(fmt=bundle.FORMAT, version=bundle.VERSION, with_project=True, entries=None,
                excluded=True):
    """A minimal container shaped like a real one."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        # Shape copied from a REAL export, not invented: entries carry path+bytes only, row counts
        # live in a top-level `tables` map, and the project name is on the manifest. The first
        # version of this fixture invented `role`/`rows` keys, and the reader agreed with it — so
        # both were wrong together and a real bundle reported "0 tables".
        man = {"format": fmt, "version": version, "has_frag": True,
               "project": {"id": "abc", "name": "Preview Test"},
               "tables": {"topics": 3, "mod_rfi": 7},
               "entries": entries if entries is not None else
               [{"path": "README.txt", "bytes": 1386},
                {"path": "data/topics.json", "bytes": 215},
                {"path": "project.json", "bytes": 98}]}
        if excluded:
            man["excluded"] = {"tables": sorted(bundle._SKIP_TABLES), "why": "installation-specific"}
        z.writestr("manifest.json", json.dumps(man))
        if with_project:
            z.writestr("project.json", json.dumps({"name": "Preview Test", "source_ifc": "model.ifc"}))
    return buf.getvalue()


# --- 1. an ordinary container previews without importing ------------------------------------------
p = bundle.preview_bundle(make_bundle())
check("a valid container is readable", p["readable"] is True, p)
check("  and importable by this build", p["importable"] is True, p)
check("  it names the project without creating one", p["project_name"] == "Preview Test",
      p["project_name"])
check("  reports the table and row counts from the manifest's own tables map",
      p["table_count"] == 2 and p["row_count"] == 10, p)
check("  and that geometry travels", p["has_geometry"] is True, p)

# THE POINT OF THE FEATURE: what will NOT arrive, stated before the decision.
check("the preview repeats what is EXCLUDED, before the user commits",
      "users" in p["excluded"]["tables"] and "audit_log" in p["excluded"]["tables"],
      p["excluded"])
check("  with the reason, not just the list", len(p["excluded"].get("why", "")) > 20, p["excluded"])
check("  and it falls back to the known skip list if a manifest omits it",
      "users" in bundle.preview_bundle(make_bundle(excluded=False))["excluded"]["tables"])

# --- 2. a NEWER container is refused here, not at import ---------------------------------------------
future = bundle.preview_bundle(make_bundle(version=bundle.VERSION + 5))
check("a container from a newer build previews as NOT importable",
      future["importable"] is False, future)
check("  and says why, in terms of the risk rather than the version alone",
      "half-read" in future["reason"] or "misinterpret" in future["reason"], future["reason"])
check("  but is still READABLE — we can say what it claims to be",
      future["readable"] is True and future["version"] == bundle.VERSION + 5, future)
check("  and states the version this build tops out at",
      future["reads_up_to"] == bundle.VERSION, future)

# --- 3. the legacy format still previews ---------------------------------------------------------------
legacy = bundle.preview_bundle(make_bundle(fmt=bundle.LEGACY_FORMAT, version=1))
check("a legacy .mmproj container previews and is importable",
      legacy["legacy"] is True and legacy["importable"] is True, legacy)

# --- 4. UNREADABLE IS AN ERROR, NEVER AN EMPTY PREVIEW ---------------------------------------------------
for bad, why in ((b"not a zip at all", "a non-zip must not read as an empty bundle"),
                 (b"", "an empty upload is not an empty container")):
    try:
        bundle.preview_bundle(bad)
        check(f"{why}", False, "returned a preview instead of raising")
    except HTTPException as e:
        check(f"{why} — {e.status_code}", e.status_code == 400, e.detail)

nomani = io.BytesIO()
with zipfile.ZipFile(nomani, "w") as z:
    z.writestr("something.txt", "hello")
try:
    bundle.preview_bundle(nomani.getvalue())
    check("a zip with no manifest is refused", False, "previewed a non-container")
except HTTPException as e:
    check("a zip with no manifest is refused rather than previewed as empty", e.status_code == 400)

badfmt = io.BytesIO()
with zipfile.ZipFile(badfmt, "w") as z:
    z.writestr("manifest.json", json.dumps({"format": "SomethingElse", "version": 1}))
try:
    bundle.preview_bundle(badfmt.getvalue())
    check("an unknown format is refused", False, "previewed an unknown format")
except HTTPException as e:
    check("an unknown container format is refused", e.status_code == 400, e.detail)

# --- 5. the preview and the importer agree — a clean preview must not be a broken import -------------------
# If these ever diverge the preview becomes a promise the importer breaks, which is worse than no
# preview: the user was told it was fine.
for fmt, ver, importable in ((bundle.FORMAT, bundle.VERSION, True),
                             (bundle.FORMAT, bundle.VERSION + 1, False),
                             (bundle.LEGACY_FORMAT, 1, True)):
    prev = bundle.preview_bundle(make_bundle(fmt=fmt, version=ver))
    check(f"preview({fmt}, v{ver}).importable == {importable}", prev["importable"] is importable, prev)

# --- 6. over HTTP ---------------------------------------------------------------------------------------
with TestClient(app) as c:
    c.headers.update({"X-User": "prev@test"})
    r = c.post("/projects/preview-bundle",
               files={"file": ("x.mass", make_bundle(), "application/zip")})
    check("the preview route answers 200", r.status_code == 200, r.text[:160])
    j = r.json()
    check("  and returns the same verdict as the engine", j["importable"] is True and j["readable"] is True, j)
    check("  naming the excluded tables over the wire", "users" in j["excluded"]["tables"], j["excluded"])

    bad = c.post("/projects/preview-bundle",
                 files={"file": ("x.mass", b"nope", "application/zip")})
    check("an unreadable upload is a 400, not a 200 with an empty body",
          bad.status_code == 400, bad.status_code)

    before = len(c.get("/projects").json())
    c.post("/projects/preview-bundle", files={"file": ("x.mass", make_bundle(), "application/zip")})
    after = len(c.get("/projects").json())
    check("PREVIEWING CREATES NOTHING — the whole point of not importing", before == after,
          f"{before} -> {after}")

print()
if FAILED:
    print(f"bundle_preview: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("bundle_preview: all checks passed")
