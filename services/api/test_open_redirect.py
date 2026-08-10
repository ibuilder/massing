"""The SAML RelayState guard must refuse the BYTES, not the spelling, of an off-site redirect.

WHAT WAS WRONG, MEASURED AGAINST THE REAL FUNCTION
--------------------------------------------------
`_safe_relay` rejected `//host` and `/\\host` — the two forms a browser resolves to another origin —
and admitted five more that resolve exactly the same way::

    /<TAB>evil.example.com     ADMITTED
    /<CR>evil.example.com      ADMITTED
    /<LF>//evil.example.com    ADMITTED
    /<TAB>/evil.example.com    ADMITTED
    /x:y/evil                  ADMITTED

**A browser strips TAB, CR and LF before resolving a URL.** So `/<TAB>/evil.example.com` becomes
`//evil.example.com` — protocol-relative, off-site — and the guard never saw a string beginning `//`.
Rejecting the two literal prefixes rejected the *spelling* of the attack, not the attack: the guard
cannot see the form the browser will act on, so it has to refuse the bytes that produce it.

HOW IT WAS FOUND, WHICH IS THE PART WORTH KEEPING
--------------------------------------------------
Not from our own review. MassingCloud/massingplan shipped an adversarial suite that caught the same
class from the other side: its guard was `startswith("/") and not startswith("//")`, and
`/\\evil.example.com` walked straight through. Reading their commit prompted probing ours.

We already had the backslash they were missing. They had the control characters we were missing.
**Two codebases, one bug class, neither complete alone** — which is the argument for reading a
sibling's security fixes as a checklist against your own code rather than as news about theirs.

The colon rule is the same shape: `/x:y` is read as a scheme by some resolvers, so a colon in the
first path segment is refused.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from aec_api.routers.saml import _safe_relay  # noqa: E402  — the real function, never a copy

#: Every one of these resolves off-site in a browser. Each MUST be refused.
OFF_SITE = [
    ("//evil.example.com", "protocol-relative"),
    ("/\\evil.example.com", "backslash authority"),
    ("/\\\\evil.example.com", "double backslash"),
    ("/\tevil.example.com", "TAB then host — stripped before resolution"),
    ("/\revil.example.com", "CR then host"),
    ("/\nevil.example.com", "LF then host"),
    ("/\t/evil.example.com", "TAB then slash — becomes // after stripping"),
    ("/\r\n//evil.example.com", "CRLF then protocol-relative"),
    ("/\x00//evil.example.com", "NUL then protocol-relative"),
    ("/\x7f//evil.example.com", "DEL then protocol-relative"),
    ("/x:y/evil", "colon in the first path segment reads as a scheme"),
    ("https://evil.example.com", "absolute URL"),
    ("javascript:alert(1)", "javascript scheme"),
    ("", "empty"),
    ("dashboard", "no leading slash — relative, resolves against the current page"),
]

#: Real destinations the product uses. Each MUST be allowed, or the guard breaks login.
SAME_SITE = [
    "/",
    "/dashboard",
    "/projects/abc123",
    "/projects/abc123?tab=drawings",
    "/projects/abc123#pin-7",
    "/a/b/c:d",            # a colon deeper in the path is fine — only the FIRST segment is a scheme risk
    "/search?q=a:b",       # and in a query string
]


def test_every_off_site_form_is_refused() -> None:
    admitted = [(t, why) for t, why in OFF_SITE if _safe_relay(t)]
    assert not admitted, (
        "these targets redirect off-site and were admitted:\n  "
        + "\n  ".join(f"{t!r} — {why}" for t, why in admitted))
    print(f"PASS  every off-site form is refused   {len(OFF_SITE)} variants")


def test_real_destinations_still_work() -> None:
    """The twin. A guard that refuses everything passes the test above and breaks the product —
    and an SSO return-URL that silently drops you on `/` is the kind of bug users report as
    'it logged me in but lost my place', which nobody traces back to a security fix."""
    refused = [t for t in SAME_SITE if not _safe_relay(t)]
    assert not refused, f"legitimate same-site destinations were refused: {refused}"
    print(f"PASS  real destinations still work   {len(SAME_SITE)} paths")


def test_control_characters_are_refused_wherever_they_sit() -> None:
    """Position is the attacker's choice, not a property to rely on.

    A browser removes a stripped character wherever it appears, so guarding only the prefix leaves
    `/foo/<TAB>//evil.example.com` — which is why the check scans the whole string.
    """
    for ch in ("\t", "\r", "\n", "\x00", "\x0b", "\x1f", "\x7f"):
        assert not _safe_relay(f"/ok{ch}//evil.example.com"), f"control char {ch!r} admitted mid-string"
        assert not _safe_relay(f"/{ch}ok"), f"control char {ch!r} admitted at the front"
    print("PASS  control characters refused at any position   7 code points x 2 placements")


def test_the_guard_is_what_the_route_actually_calls() -> None:
    """A hardened function nothing calls is the defect this repo keeps finding.

    Asserts the redirect site still routes its target through `_safe_relay` rather than using
    `RelayState` directly — the fix is worthless if a later edit inlines the redirect.
    """
    src_path = os.path.join(os.path.dirname(__file__), "src", "aec_api", "routers", "saml.py")
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "_safe_relay(RelayState)" in code, (
        "the ACS route no longer guards RelayState through _safe_relay — the hardening is bypassed")
    print("PASS  the ACS route still routes RelayState through the guard")


if __name__ == "__main__":
    test_every_off_site_form_is_refused()
    test_real_destinations_still_work()
    test_control_characters_are_refused_wherever_they_sit()
    test_the_guard_is_what_the_route_actually_calls()
    print("test_open_redirect OK")
