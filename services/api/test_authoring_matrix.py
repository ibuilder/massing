"""AUTHOR-MATRIX: the authoring-coverage matrix is derived live from edit.RECIPES, fully categorized,
renders to markdown, and served at /reference/authoring-matrix. A completeness guard fails when a new
recipe is added without a category (so the coverage doc can't silently drift).
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_authoring_matrix.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_authmatrix_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_authmatrix")
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_authmatrix_test.db"):
    os.remove("./_authmatrix_test.db")

from aec_api import authoring_matrix as AM  # noqa: E402
from aec_data import edit  # noqa: E402

m = AM.matrix()

# every recipe in the live registry appears exactly once, across the categories
flat = [r["recipe"] for cat in m["by_category"].values() for r in cat["recipes"]]
assert sorted(flat) == sorted(edit.RECIPES.keys()), "matrix must cover every RECIPES entry exactly once"
assert m["recipe_count"] == len(edit.RECIPES), (m["recipe_count"], len(edit.RECIPES))
assert len(flat) == len(set(flat)), "no recipe listed twice"

# COMPLETENESS GUARD: no uncategorized recipes — a newly-added recipe must be mapped in authoring_matrix.
assert m["uncategorized"] == [], (
    f"{len(m['uncategorized'])} recipe(s) missing a category in authoring_matrix._MAP: "
    f"{m['uncategorized']} — add them so docs/authoring-matrix.md stays complete")

# category rollups are self-consistent; the big authoring families are present
counts = {c: d["count"] for c, d in m["by_category"].items()}
assert sum(counts.values()) == m["recipe_count"]
for expected in ("create-structure", "create-mep", "annotate", "edit", "data"):
    assert counts.get(expected, 0) > 0, f"expected the '{expected}' category to be populated"
# every create-* row names an IFC output (not blank)
for cat, d in m["by_category"].items():
    if cat.startswith("create-"):
        assert all(r["produces"] for r in d["recipes"]), f"{cat} rows must name an IFC output"

# markdown renders and matches the live matrix (the committed doc is generated from this)
md = AM.to_markdown()
assert md.startswith("# Authoring coverage matrix")
assert f"**{m['recipe_count']} authoring recipes**" in md
assert "| `add_wall` | IfcWall |" in md and "### create-structure" in md
assert "⚠ Uncategorized" not in md, "the rendered doc must have no uncategorized warning"

# endpoint serves it
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    r = c.get("/reference/authoring-matrix")
    assert r.status_code == 200, r.text[:160]
    body = r.json()
    assert body["recipe_count"] == m["recipe_count"] and body["uncategorized"] == []

print(f"AUTHORING-MATRIX OK - {m['recipe_count']} recipes across {m['category_count']} categories, all "
      "mapped (completeness guard green — a new recipe without a category fails this test); create-* rows "
      "name their IFC output; markdown renders with no uncategorized warning; /reference/authoring-matrix "
      "serves the live matrix.")
