"""OAuth provider table — Autodesk added, and every provider is well-formed.

Social sign-in was already built (Google, Microsoft/Entra, Procore) with a full authorization-code
flow that mints the normal `aec_token`, so SSO users join the same identity and RBAC layer as
password accounts. The login UI reads `enabled_providers()` through `/capabilities`, so buttons
appear from configuration alone and the two lists cannot drift.

The gap was **Autodesk** — the identity behind Revit, ACC and BIM 360, and therefore the account most
of this product's users already have.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_oauth_providers.py
"""
from __future__ import annotations

import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import oauth  # noqa: E402


def test_autodesk_is_a_provider():
    assert "autodesk" in oauth.PROVIDERS


def test_every_provider_is_well_formed():
    for name, p in oauth.PROVIDERS.items():
        for field in ("label", "authorize", "token", "userinfo", "email"):
            assert p.get(field) is not None, f"{name} is missing {field}"
        assert callable(p["email"]), f"{name}'s email extractor must be callable"


def test_every_endpoint_is_https():
    # An OAuth flow over plaintext would leak the authorization code in transit.
    for name, p in oauth.PROVIDERS.items():
        for field in ("authorize", "token", "userinfo"):
            v = p[field]
            url = v() if callable(v) else v
            assert url.startswith("https://"), f"{name}.{field} is not https: {url}"


def test_autodesk_asks_for_SIGN_IN_only_not_model_access():
    # The scope this requests is the whole ethical question. Reading somebody's ACC hub is a separate
    # consent with separate scopes; bundling it into a "Sign in with Autodesk" button would ask for
    # far more than the button says. The optional RVT bridge stays separately authorised.
    scope = oauth.PROVIDERS["autodesk"]["scope"]
    assert scope == "openid email profile", scope
    assert "data:read" not in scope and "account:read" not in scope, scope


def test_autodesk_reads_the_email_from_either_shape():
    email = oauth.PROVIDERS["autodesk"]["email"]
    assert email({"email": "a@b.com"}) == "a@b.com"
    assert email({"emailId": "old@b.com"}) == "old@b.com"     # pre-v2 profile shape
    assert email({}) is None                                   # absent is None, never a guess


def test_a_provider_with_no_credentials_is_NOT_enabled():
    # The login UI renders from `enabled_providers()`, so an unconfigured provider must not appear —
    # a button that leads to a broken consent screen is worse than no button.
    for key in ("AEC_OAUTH_AUTODESK_CLIENT_ID", "AEC_OAUTH_AUTODESK_SECRET"):
        os.environ.pop(key, None)
    assert "autodesk" not in [p["id"] for p in oauth.enabled_providers()]


def test_the_provider_ids_are_stable_identifiers():
    # These appear in callback URLs registered with each vendor's developer console. Renaming one
    # silently breaks every existing registration, so this pins them.
    assert set(oauth.PROVIDERS) == {"google", "microsoft", "procore", "autodesk"}


for _n, _f in sorted(list(globals().items())):
    if _n.startswith("test_") and callable(_f):
        _f()

print("OAUTH-PROVIDERS OK - Autodesk added to the social sign-in table (Google, Microsoft/Entra, "
      "Procore already shipped). It is the identity behind Revit, ACC and BIM 360, so it is the "
      "account most of this product's users already have. Sign-in ONLY: the scope is "
      "`openid email profile` and asserted NOT to include data or account access - reading somebody's "
      "ACC hub is a separate consent with separate scopes, and bundling it into a 'Sign in with "
      "Autodesk' button would ask for far more than the button says. No UI change was needed: the "
      "login screen renders from `enabled_providers()` via /capabilities, so the button appears from "
      "configuration alone and the two lists cannot drift.")
