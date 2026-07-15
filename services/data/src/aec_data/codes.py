"""CODE-1 — jurisdiction-aware code context (adoption facts).

The copyright-safe strategy: own the *facts* (which code family, which edition, which jurisdiction adopted
it) and deep-link out for the copyrighted prose. This module encodes only facts of law + published-edition
metadata — the model-code **families** and their **editions** (the I-Codes publish on a fixed 3-year cycle,
which is a fact), plus a resolver that maps a jurisdiction to its adopted editions. It ships a small,
clearly-dated reference seed and always defaults to a documented national baseline; the seed is a starting
point, never an authority — every result carries a "verify with the AHJ" note because adoptions change.

This is the substrate CODE-2/3 build on (thread an edition-scoped `code_ctx` through the checks so an
exterior window cites the project's *actually adopted* section, not a generic latest).
"""
from __future__ import annotations

from typing import Any

# The model-code families we reason about, with their published editions (I-Codes are on a 3-year cycle).
CODE_FAMILIES: dict[str, dict[str, Any]] = {
    "IBC": {"name": "International Building Code", "editions": [2012, 2015, 2018, 2021, 2024]},
    "IRC": {"name": "International Residential Code", "editions": [2012, 2015, 2018, 2021, 2024]},
    "IECC": {"name": "International Energy Conservation Code", "editions": [2012, 2015, 2018, 2021, 2024]},
    "IFC": {"name": "International Fire Code", "editions": [2012, 2015, 2018, 2021, 2024]},
    "IPC": {"name": "International Plumbing Code", "editions": [2012, 2015, 2018, 2021, 2024]},
    "IMC": {"name": "International Mechanical Code", "editions": [2012, 2015, 2018, 2021, 2024]},
    "IEBC": {"name": "International Existing Building Code", "editions": [2012, 2015, 2018, 2021, 2024]},
    "IgCC": {"name": "International Green Construction Code", "editions": [2012, 2015, 2018, 2021]},
    "A117.1": {"name": "ICC A117.1 Accessible and Usable Buildings and Facilities",
               "editions": [2009, 2017]},
}

# A documented national baseline — the most-widely-adopted editions as a *default* when a project has no
# jurisdiction set. NOT a claim about any specific jurisdiction; the resolver always says "verify."
BASELINE = {"IBC": 2021, "IRC": 2021, "IECC": 2021, "IFC": 2021, "IPC": 2021, "IMC": 2021,
            "IEBC": 2021, "A117.1": 2017}

# A small, explicitly-dated reference seed (as-of 2024). Statewide adoption facts change on each cycle and
# vary by local amendment — this is a starting point to extend from authoritative sources, never authority.
# Keyed by USPS state code. Only well-established statewide baselines are seeded; everything else resolves
# to BASELINE with a verify note.
_SEED_ASOF = 2024
_ADOPTIONS: dict[str, dict[str, int]] = {
    "FL": {"IBC": 2021, "IRC": 2021, "IECC": 2021, "IFC": 2021},   # Florida Building Code (7th ed., 2020→2021 base)
    "CA": {"IBC": 2021, "IRC": 2021, "IECC": 2021, "IFC": 2021},   # California Building Standards (Title 24, 2022 cycle)
    "TX": {"IBC": 2015, "IRC": 2015, "IECC": 2015},                # statewide minimums; municipalities adopt newer
    "NY": {"IBC": 2018, "IRC": 2018, "IECC": 2018},                # NYS Uniform Code (NYC has its own)
    "WA": {"IBC": 2021, "IRC": 2021, "IECC": 2021},
    "IL": {"IBC": 2021},                                            # no statewide building code; home-rule adopts
}

_VERIFY = ("Adoption facts change each code cycle and are overridden by local amendments — confirm the "
           "edition in force with the Authority Having Jurisdiction (AHJ).")


def families() -> dict[str, Any]:
    """The code-family + edition catalog (facts), plus the documented baseline."""
    return {"families": CODE_FAMILIES, "baseline": BASELINE,
            "note": "I-Codes publish on a 3-year cycle; the baseline is the common default, not a "
                    "jurisdiction-specific adoption."}


def resolve(jurisdiction: str | None = None) -> dict[str, Any]:
    """Resolve a jurisdiction (USPS state code, e.g. 'CA') to its adopted code editions. Falls back to the
    national BASELINE when the jurisdiction isn't in the seed (nothing breaks). Always carries a verify note
    and, when seeded, the as-of year — so a result is never mistaken for an authoritative current fact."""
    juris = (jurisdiction or "").strip().upper()
    seeded = _ADOPTIONS.get(juris)
    adopted = {**BASELINE, **(seeded or {})}
    codes = [{"family": fam, "edition": ed, "name": CODE_FAMILIES.get(fam, {}).get("name", fam),
              "source": "seed" if seeded and fam in seeded else "baseline"}
             for fam, ed in sorted(adopted.items())]
    return {
        "jurisdiction": juris or None,
        "resolved": bool(seeded),
        "as_of": _SEED_ASOF if seeded else None,
        "codes": codes,
        "primary": {"IBC": adopted.get("IBC"), "IECC": adopted.get("IECC"), "A117.1": adopted.get("A117.1")},
        "verify": _VERIFY,
    }


def seeded_jurisdictions() -> list[str]:
    """The USPS codes present in the reference seed (so a UI can show which have specifics vs baseline)."""
    return sorted(_ADOPTIONS)
