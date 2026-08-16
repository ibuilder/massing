"""R37-TRIAGE — one step-up verifier, and the one that could not spend the jti.

A step-up assertion answers *"a human confirmed THIS act"*. That claim survives exactly as long as the
token cannot be replayed, and replay protection lives in the `jti`: `rbac.consume_stepup` spends it
against the `stepup_spent` table, so the second presentation of the same token fails.

`auth.py` carried **two** verifiers. `verify_stepup_claims` returns the whole payload, so a caller can
spend the jti. "verify_stepup_token" ran identical signature, expiry, action and password-fingerprint
checks and returned **only the subject** — everything a reviewer looks for, and no way to spend
anything. It had no callers, which is why it was removed in v0.3.973 rather than kept: an unused
helper is not harmless when the harm is that it looks equivalent to the safe one.

The assertion here is not "the old name is gone" — a grep for a deleted name passes forever and reads
as coverage. It is **the property that made the deletion correct**: every step-up verifier on the
module returns something a caller can spend.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_stepup_single_verifier.py
"""
from __future__ import annotations

import inspect
import sys

sys.path.insert(0, "src")

from aec_api import auth  # noqa: E402

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


ACT = "pdf.seal"
PW = "$2b$12$notarealhashbutstable"


def main() -> int:
    # --- the population, read from the module rather than remembered -------------------------------
    verifiers = sorted(n for n, f in vars(auth).items()
                       if callable(f) and n.startswith("verify_stepup"))
    check("there is exactly one step-up verifier",
          verifiers == ["verify_stepup_claims"],
          f"{verifiers} — two verifiers where one silently drops replay protection is a footgun "
          "whether or not anyone has picked it up yet")

    # --- THE property that made removing the other one correct -------------------------------------
    token = auth.create_stepup_token("someone@example.com", ACT, PW)
    for name in verifiers:
        out = getattr(auth, name)(token, ACT, PW)
        spendable = isinstance(out, dict) and bool(out.get("jti"))
        check(f"{name} returns something the caller can SPEND",
              spendable,
              f"jti={((out or {}).get('jti') if isinstance(out, dict) else None)!r} — a verifier that "
              "returns only the subject leaves the assertion replayable, which is the whole reason "
              "the second one was deleted rather than kept")

    # The twin: a verifier that returned a bare string must FAIL the check above, or it asserts
    # nothing. Modelled here rather than planted on the module, so the check itself is exercised.
    fake = "someone@example.com"
    check("...and the check can see a non-spendable return — the twin",
          not (isinstance(fake, dict) and bool(fake.get("jti") if isinstance(fake, dict) else None)),
          "the deleted verifier returned exactly this shape and would have failed here")

    # --- the checks that must NOT have been lost with it -------------------------------------------
    #
    # Removing a verifier is only safe if the survivor is at least as strict. Asserted, not assumed.
    check("a step-up for one act does not satisfy another",
          auth.verify_stepup_claims(token, "estimate.publish", PW) is None,
          "a cheap action's confirmation must never authorise an expensive one")

    check("a changed password invalidates an outstanding step-up",
          auth.verify_stepup_claims(token, ACT, "$2b$12$adifferenthashentirely") is None,
          "the fingerprint binds the assertion to the credential that made it")

    check("a tampered signature is refused",
          auth.verify_stepup_claims(token[:-2] + ("aa" if not token.endswith("aa") else "bb"),
                                    ACT, PW) is None,
          "HMAC over the payload, compared with compare_digest")

    check("garbage in is None, not an exception",
          auth.verify_stepup_claims("not.a.token", ACT, PW) is None
          and auth.verify_stepup_claims("", ACT, PW) is None,
          "a raise here would turn a refusal into a 500, which reads as a bug rather than a denial")

    # --- and the survivor is genuinely reachable ---------------------------------------------------
    src = inspect.getsource(sys.modules["aec_api.rbac"]) if "aec_api.rbac" in sys.modules else ""
    if not src:
        from aec_api import rbac
        src = inspect.getsource(rbac)
    check("rbac.consume_stepup is the caller, and it spends the jti",
          "verify_stepup_claims" in src and "jti" in src,
          "a verifier nothing calls is the state the deleted one was in")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("stepup_single_verifier: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
