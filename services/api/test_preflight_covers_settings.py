"""Every operator setting SECURITY.md documents must be checked by the production preflight.

`scripts/validate_prod_config.py` is the documented go/no-go gate — the checklist points at it and it
exits 1 on hard failures. `SECURITY.md` is where an operator learns which knobs exist. Nothing kept
the two in step, and they had drifted badly: **13 of the 22 documented `AEC_*` settings were validated
by nothing at all.**

Two of those were not tuning knobs:

    AEC_ALLOW_IFC_CODE=1      executes caller-supplied Python against the model — arbitrary code
                              execution inside the API process on an exposed deployment
    AEC_SEAL_ALLOW_PROFILE=1  restores the caller-supplied seal identity, so an authenticated user
                              can seal under another person's name and licence number

Measured before the fix: a config with **both** set, plus a real Postgres DSN and a strong secret,
produced `0 failure(s)` and exit 0 — the preflight said *safe to expose*. That is the same shape as
every other finding this sprint: the check ran, answered a narrower question than the one being asked
of it, and the narrow answer was read as the broad one.

This test is the ratchet, not the six checks that came with it. A setting can be documented and
deliberately not preflighted — but the exemption has to be written down with a reason, so the next
person inherits a decision instead of an omission.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_preflight_covers_settings.py
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))

SECURITY_MD = os.path.join(_ROOT, "SECURITY.md")
PREFLIGHT = os.path.join(_ROOT, "scripts", "validate_prod_config.py")

#: Documented but deliberately NOT preflighted, each with the reason. An entry here is a decision;
#: an absence is an oversight. Every key is asserted to still be documented below — a stale exemption
#: silently pre-approves the next setting that reuses the name, which is the dead-referent trap this
#: repo has now hit in three separate gates.
EXEMPT = {
    "AEC_API_KEY": "optional automation bearer; presence is a deployment choice and the preflight "
                   "cannot judge a secret's quality beyond length. A length check here would be a "
                   "reasonable future addition.",
    "AEC_IFC_CODE_TIMEOUT": "only meaningful when AEC_ALLOW_IFC_CODE=1, which the preflight now "
                            "FAILs outright — checking the timeout of a refused feature is noise.",
    "AEC_LOCAL_MODE": "single-operator desktop build; running a PRODUCTION preflight already implies "
                      "this is not that deployment.",
    "AEC_LOGIN_MAX_FAILS": "brute-force lockout tuning with a safe default (8).",
    "AEC_LOGIN_WINDOW_SEC": "brute-force lockout tuning with a safe default (5 min).",
    "AEC_MAX_UPLOAD_MB": "body-size cap tuning with a safe default (1 GB); oversized uploads 413.",
    "AEC_SIGNED_URL_TTL": "signed-download lifetime tuning with a safe default (1 h).",
}

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if (detail != '' and not ok) else ''}")
    if not ok:
        FAILED.append(label)


security = open(SECURITY_MD, encoding="utf-8").read()
preflight = open(PREFLIGHT, encoding="utf-8").read()

documented = set(re.findall(r"`(AEC_[A-Z0-9_]+)", security))
checked = set(re.findall("AEC_[A-Z0-9_]+", preflight))

# A discovery step that silently finds nothing turns this whole file into a no-op that prints OK.
check("SECURITY.md yielded a real corpus of settings", len(documented) > 15, len(documented))
check("the preflight yielded a real corpus of checks", len(checked) > 8, len(checked))
check("the preflight file was actually found", len(preflight) > 2000, len(preflight))

unvalidated = sorted(documented - checked - set(EXEMPT))
check("every documented setting is preflighted or explicitly exempted",
      not unvalidated,
      f"{unvalidated} — add a check to scripts/validate_prod_config.py, or an EXEMPT entry with a "
      f"reason here")

# The mirror. Without it EXEMPT rots into a list of names that pre-approve whatever reuses them.
stale = sorted(k for k in EXEMPT if k not in documented)
check("no EXEMPT entry has lost its referent in SECURITY.md",
      not stale,
      f"{stale} — no longer documented; delete the exemption rather than leaving it to match a "
      f"future setting of the same name")

# The two that mattered must be FAIL-severity, not warnings: both are remote code execution or
# credential forgery, and a warning does not stop a go-live.
def _guard_block(src: str, var: str) -> str:
    """The body of the `if env("VAR")…:` guard, up to the next top-level `if env(`.

    Slicing a fixed window after the first mention of the name does NOT work: the name also appears
    in a comment, so the window started in prose and ran far enough to reach the NEXT check's
    FAIL.append. That version passed while the guard under test had been demoted to a warning —
    caught by mutation, not by reading."""
    needle = f'if env("{var}")'
    if needle not in src:
        return ""
    start = src.index(needle)
    rest = src[start + len(needle):]
    # Delimit on ANY top-level `if`, not `if env(`: the guard after this one begins
    # `if not env(`, so the narrower delimiter over-ran into the NEXT check's WARN and
    # reported a false positive. Caught because the failure named a guard I had just written
    # as a FAIL.
    nxt = rest.find(chr(10) + 'if ')
    return rest[:nxt if nxt != -1 else len(rest)]


for var in ("AEC_ALLOW_IFC_CODE", "AEC_SEAL_ALLOW_PROFILE"):
    seg = _guard_block(preflight, var)
    check(f"{var} has a guard at all", bool(seg), "no `if env(...)` guard found")
    check(f"{var} is a hard FAIL, not a warning",
          "FAIL.append" in seg and "WARN.append" not in seg,
          "its guard raises only a WARN — a warning does not stop a go-live")

print()
if FAILED:
    print(f"preflight_covers_settings: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"preflight_covers_settings: all checks passed — {len(documented)} documented settings, "
      f"{len(documented - set(EXEMPT))} preflighted, {len(EXEMPT)} exempted with a stated reason and "
      f"every exemption still documented.")
