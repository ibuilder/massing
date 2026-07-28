"""Regression tests for the 2026-07 security audit (branch security/audit-2026-07).

Each block pins a fix to the concrete escape it closes, so a later refactor that reopens one fails
here rather than in production.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_security_audit.py
"""
import os
import sys
import urllib.request

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

os.environ["AEC_ALLOW_IFC_CODE"] = "1"

from aec_data import massing, sandbox  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_secaudit_test.ifc")
massing.generate_blank_ifc(TMP, name="Sec Audit", storeys=1, storey_height=3.0, ground_size=20.0)


def rejected(code: str) -> bool:
    try:
        sandbox.execute_ifc_code(open_model(TMP), code)
        return False
    except sandbox.SandboxError:
        return True


# --- A1: `model` exposes ifcopenshell.file's own IO surface ---------------------------------------
# `open` is absent from the namespace, but model.write() was an arbitrary-file-write primitive that
# bypassed the builtins denylist entirely. Regression: it must be rejected before it runs.
_escape_target = os.path.join(os.path.dirname(__file__), "_secaudit_should_not_exist.ifc")
if os.path.exists(_escape_target):
    os.remove(_escape_target)
assert rejected(f"model.write({_escape_target!r})"), "model.write must be denied"
assert not os.path.exists(_escape_target), "sandbox wrote a file to an arbitrary path"
for attr in ("from_string", "from_pointer", "assign_header_from", "storage"):
    assert rejected(f"model.{attr}('x')"), f"model.{attr} must be denied"

# --- A2: banning `while` does not bound execution -------------------------------------------------
# `for` over a huge range is the same unbounded loop, and `9**9**9` is a single uninterruptible op.
assert rejected("x = 9**9**9"), "chained ** must be rejected"
assert rejected("x = 2**999999"), "huge constant exponent must be rejected"
sandbox._MAX_SECONDS = 1.0   # keep the test fast; the guard itself is what's under test
assert rejected("s=0\nfor i in range(10**9):\n    s=s+1"), "runaway loop must hit the deadline"

# legitimate authoring must still work after all of the above
_res = sandbox.execute_ifc_code(
    open_model(TMP), "w = ifcopenshell.api.run('root.create_entity', model, ifc_class='IfcWall')")
assert _res["ok"] and _res["created"] >= 1, "legitimate authoring broke"

# --- B: SSRF guard must cover redirects, not just the first URL ------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from aec_api.net import _ValidatingRedirectHandler, validate_outbound_url  # noqa: E402

# the initial-URL check still works
for bad in ("file:///etc/passwd", "gopher://x/", "ftp://x/"):
    try:
        validate_outbound_url(bad, label="t")
        raise AssertionError(f"{bad} should be refused")
    except ValueError:
        pass

# a 302 to a private/metadata address must be refused by the redirect handler when allow_private=False
_h = _ValidatingRedirectHandler(require_https=False, allow_private=False, label="t")
_req = urllib.request.Request("https://example.com/")
for target in ("http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:8000/admin",
               "file:///etc/passwd"):
    try:
        _h.redirect_request(_req, None, 302, "Found", {}, target)
        raise AssertionError(f"redirect to {target} should be refused")
    except ValueError:
        pass

# and the scheme check applies to redirects even when private targets are allowed (on-prem default)
_h_open = _ValidatingRedirectHandler(require_https=False, allow_private=True, label="t")
try:
    _h_open.redirect_request(_req, None, 302, "Found", {}, "file:///etc/passwd")
    raise AssertionError("redirect to file:// should be refused")
except ValueError:
    pass
# a legitimate redirect still passes
assert _h_open.redirect_request(_req, None, 302, "Found", {}, "https://example.org/next") is not None

# every outbound bridge must route through safe_urlopen rather than bare urlopen
_SRC = os.path.join(os.path.dirname(__file__), "src", "aec_api")
for mod in ("webhooks.py", "esign_bridge.py", "re_bridge.py", "securities_bridge.py",
            "license_cloud.py"):
    body = open(os.path.join(_SRC, mod), encoding="utf-8").read()
    assert "safe_urlopen(" in body, f"{mod} must use safe_urlopen"
    assert "urllib.request.urlopen(" not in body, f"{mod} still calls urlopen directly"

# --- C: security decisions key off the routed path, not the reconstructed URL ----------------------
_main = open(os.path.join(_SRC, "main.py"), encoding="utf-8").read()
assert "_routed_path(request).startswith(_PROTECTED_PREFIXES)" in _main, \
    "the RBAC gate must use the routed path (CVE-2026-48710 bug class)"
assert "request.url.path.startswith(_PROTECTED_PREFIXES)" not in _main
for mod in ("routers/bim.py", "routers/realestate.py"):
    body = open(os.path.join(_SRC, *mod.split("/")), encoding="utf-8").read()
    assert "verify_path(request.url.path" not in body, f"{mod} signed-URL check must use scope path"

# --- D: signed share links must not be mintable as effectively-permanent --------------------------
_re = open(os.path.join(_SRC, "routers", "realestate.py"), encoding="utf-8").read()
assert _re.count("le=365 * 24 * 3600") == 2, "both share endpoints must cap the TTL"

os.remove(TMP)
print("SECURITY AUDIT OK — sandbox IO/DoS escapes closed, SSRF redirects validated, auth gate keyed "
      "to the routed path, share TTLs bounded.")
