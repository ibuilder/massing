"""CODE-1 jurisdiction code-context: the family/edition catalog is factual, and resolve() maps a
jurisdiction to adopted editions with a baseline fallback and a mandatory verify note.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_codes.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import codes  # noqa: E402

# --- families catalog: the I-Codes on their 3-year cycle -------------------------------------------
fam = codes.families()
assert "IBC" in fam["families"] and fam["families"]["IBC"]["name"].startswith("International Building")
assert 2021 in fam["families"]["IBC"]["editions"] and 2024 in fam["families"]["IBC"]["editions"]
assert fam["baseline"]["IBC"] == 2021

# --- a seeded jurisdiction resolves to its editions with an as-of year ------------------------------
ca = codes.resolve("ca")                       # case-insensitive
assert ca["jurisdiction"] == "CA" and ca["resolved"] is True and ca["as_of"], ca
ibc = next(c for c in ca["codes"] if c["family"] == "IBC")
assert ibc["edition"] == 2021 and ibc["source"] == "seed", ibc
assert ca["primary"]["IBC"] == 2021 and ca["primary"]["A117.1"] == 2017, ca["primary"]
assert ca["verify"], "must carry a verify-with-AHJ note"

# a partially-seeded state fills the rest from the baseline
il = codes.resolve("IL")
assert il["resolved"] and next(c for c in il["codes"] if c["family"] == "IBC")["source"] == "seed"
assert next(c for c in il["codes"] if c["family"] == "IECC")["source"] == "baseline", "unseeded family → baseline"

# --- an unseeded / empty jurisdiction falls back to the baseline, still with the verify note --------
zz = codes.resolve("ZZ")
assert zz["resolved"] is False and zz["as_of"] is None, zz
assert all(c["source"] == "baseline" for c in zz["codes"]) and zz["verify"], zz
base = codes.resolve(None)
assert base["jurisdiction"] is None and base["primary"]["IBC"] == 2021, base

assert "CA" in codes.seeded_jurisdictions() and "FL" in codes.seeded_jurisdictions()

# --- endpoints ------------------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite:///./_codes_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_codes")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

c = TestClient(app)
h = {"X-User": "tester"}
assert c.get("/codes/families", headers=h).json()["baseline"]["IBC"] == 2021
r = c.get("/codes/adoptions?jurisdiction=FL", headers=h).json()
assert r["resolved"] and r["primary"]["IBC"] == 2021 and r["verify"], r
assert "CA" in c.get("/codes/seeded", headers=h).json()["jurisdictions"]

print("CODES OK - CODE-1 catalog lists the I-Code families + editions and the baseline; resolve() maps a "
      "jurisdiction to adopted editions (seed vs baseline per family), falls back to the baseline when "
      "unseeded, always carries a verify-with-AHJ note; /codes/families, /codes/adoptions, /codes/seeded serve it.")
