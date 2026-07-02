"""Connection tests for the Settings ▸ Integrations panel — the "Test connection" button gives a
non-technical admin instant ✓/✗ feedback that a key actually works, instead of finding out later.

Each tester is lightweight and safe (catches everything → {ok, message}); the AI test costs ~1 token.
SSO can only be fully verified with a browser redirect, so it reports credential presence + guidance."""
from __future__ import annotations

from . import settings_store


def _test_ai() -> dict:
    if not settings_store.get("ANTHROPIC_API_KEY"):
        return {"ok": False, "message": "No Anthropic API key set."}
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
        client.messages.create(model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"),
                               max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        return {"ok": True, "message": "Anthropic key valid — AI assist is ready."}
    except Exception as e:                               # noqa: BLE001
        msg = str(e)
        if "401" in msg or "authentication" in msg.lower() or "invalid x-api-key" in msg.lower():
            return {"ok": False, "message": "Invalid Anthropic API key."}
        return {"ok": False, "message": f"AI test failed: {msg[:140]}"}


def _test_speckle() -> dict:
    from . import speckle_bridge
    st = speckle_bridge.status()
    return {"ok": bool(st.get("connected")), "message": st.get("message", "")}


def _test_aps() -> dict:
    from . import aps
    if not aps.is_enabled():
        return {"ok": False, "message": "APS client id/secret not set."}
    try:
        aps.oauth_token()
        return {"ok": True, "message": "APS credentials valid."}
    except Exception as e:                               # noqa: BLE001
        return {"ok": False, "message": f"APS auth failed: {str(e)[:140]}"}


def _test_smtp() -> dict:
    from . import mailer
    return mailer.smtp_test()


def _test_sso(provider: str) -> dict:
    keymap = {
        "google": ("AEC_OAUTH_GOOGLE_CLIENT_ID", "AEC_OAUTH_GOOGLE_CLIENT_SECRET"),
        "microsoft": ("AEC_OAUTH_MICROSOFT_CLIENT_ID", "AEC_OAUTH_MICROSOFT_CLIENT_SECRET"),
        "procore": ("AEC_OAUTH_PROCORE_CLIENT_ID", "AEC_OAUTH_PROCORE_CLIENT_SECRET"),
    }
    cid, csec = keymap[provider]
    if settings_store.get(cid) and settings_store.get(csec):
        return {"ok": True, "message": f"{provider.title()} credentials present — finish by signing in from the login page."}
    return {"ok": False, "message": f"{provider.title()} client id/secret not fully set."}


def _test_license() -> dict:
    from . import licensing
    key = settings_store.get("MASSING_LICENSE_KEY")
    if not key:
        return {"ok": True, "message": "Open mode — a licence key is optional."}
    return ({"ok": True, "message": "Licence key format is valid."} if licensing.valid_key_format(key)
            else {"ok": False, "message": "Licence key format invalid — expected MASS-XXXX-XXXX-XXXX-XXXX."})


def test_group(group: str) -> dict:
    """Dispatch a connection test by catalog group name (as shown in the Settings UI)."""
    g = (group or "").lower()
    if g.startswith("ai"):
        return _test_ai()
    if g.startswith("email"):
        return _test_smtp()
    if g.startswith("speckle"):
        return _test_speckle()
    if g.startswith("autodesk aps"):
        return _test_aps()
    if g.startswith("massing licence"):
        return _test_license()
    if g.startswith("sso"):
        for prov in ("google", "microsoft", "procore"):
            if prov in g:
                return _test_sso(prov)
    return {"ok": False, "message": "No connection test available for this integration."}
