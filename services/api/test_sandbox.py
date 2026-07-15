"""A1 sandboxed execute_ifc_code: the AST allowlist rejects imports / dunder / reflection / IO before
running; the flag gates it off by default; a whitelisted ifcopenshell snippet authors into the model.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sandbox.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import massing, sandbox  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_sandbox_test.ifc")
massing.generate_blank_ifc(TMP, name="Sandbox Test", storeys=1, storey_height=3.0, ground_size=20.0)


def rejected(code: str) -> bool:
    try:
        sandbox.execute_ifc_code(open_model(TMP), code)
        return False
    except sandbox.SandboxError:
        return True


# --- flag gates it OFF by default -----------------------------------------------------------------
os.environ.pop("AEC_ALLOW_IFC_CODE", None)
assert not sandbox.enabled()
try:
    sandbox.execute_ifc_code(open_model(TMP), "x = 1")
    raise AssertionError("should raise PermissionError when disabled")
except PermissionError:
    pass

# enable for the rest of the test
os.environ["AEC_ALLOW_IFC_CODE"] = "1"
assert sandbox.enabled()

# --- the AST allowlist rejects the dangerous stuff ------------------------------------------------
assert rejected("import os"), "import must be rejected"
assert rejected("from os import system"), "from-import rejected"
assert rejected("open('/etc/passwd')"), "open() rejected"
assert rejected("eval('1+1')"), "eval rejected"
assert rejected("exec('x=1')"), "exec rejected"
assert rejected("__import__('os')"), "__import__ rejected"
assert rejected("getattr(model, 'by_type')"), "getattr rejected"
assert rejected("().__class__.__bases__"), "dunder attribute rejected"
assert rejected("model.__class__"), "dunder attribute on model rejected"
assert rejected("x = __builtins__"), "dunder name rejected"
assert rejected("def f():\n  return 1"), "def rejected"
assert rejected("lambda: 1"), "lambda rejected"
assert rejected("class C:\n  pass"), "class rejected"
assert rejected("while True:\n  pass"), "while (infinite loop) rejected"
assert rejected("with open('x') as f:\n  pass"), "with rejected"
assert rejected("del model"), "del rejected"
assert rejected("type('X', (), {})"), "type() class-creation rejected"
assert rejected("(1"), "syntax error surfaces as SandboxError"
assert rejected(""), "empty rejected"

# --- red-team: the module-attribute RCE escapes a security review found MUST all be blocked ---------
assert rejected("ifcopenshell.os.system('echo hi')"), "ifcopenshell.os.* RCE must be blocked"
assert rejected("ifcopenshell.sys.modules"), "ifcopenshell.sys must be blocked"
assert rejected("ifcopenshell.express.subprocess.check_output(['whoami'])"), "subprocess chain blocked"
assert rejected("ifcopenshell.api.importlib.import_module('subprocess')"), "importlib chain blocked"
assert rejected("ifcopenshell.api.inspect.builtins.eval('6*7')"), "inspect.builtins chain blocked"
assert rejected("ifcopenshell.zipfile.io.open('x','w')"), "zipfile.io.open chain blocked"
assert rejected("ifcopenshell.os.environ.get('PATH')"), "environ leak blocked"
assert rejected("ifcopenshell.tempfile"), "tempfile attr blocked"
assert rejected("'{0.__class__}'.format(())"), "str.format dunder-read bypass blocked"
assert rejected("'{0}'.format(model).format_map({})"), "format_map blocked"
# the facade exposes ONLY the intended authoring callables — reaching anything else raises
assert rejected("ifcopenshell.express"), "non-exposed subpackage blocked"
assert rejected("model.wrapped_data"), "model.wrapped_data blocked"

# --- a whitelisted ifcopenshell snippet authors into the model ------------------------------------
m = open_model(TMP)
n0 = len(m.by_type("IfcWall"))
# create a couple of walls via the ifcopenshell API (no imports needed — ifcopenshell is in scope)
code = (
    "for i in range(3):\n"
    "    ifcopenshell.api.run('root.create_entity', model, ifc_class='IfcWall', name='w' + str(i))\n"
)
res = sandbox.execute_ifc_code(m, code)
assert res["ok"] and res["created"] >= 3, res
assert len(m.by_type("IfcWall")) == n0 + 3, "the snippet created 3 walls"

# a snippet that raises at runtime is reported as a SandboxError, not a traceback
assert rejected("model.by_type('IfcWall')[999999]"), "runtime IndexError → SandboxError"

if os.path.exists(TMP):
    os.remove(TMP)

print("SANDBOX OK - execute_ifc_code is OFF unless AEC_ALLOW_IFC_CODE=1 (PermissionError); the AST allowlist "
      "rejects import/from-import/open/eval/exec/__import__/getattr/dunder-access/def/lambda/class/while/with/"
      "del/type()-class-creation/syntax-errors/empty; and a whitelisted ifcopenshell.api snippet authors 3 "
      "walls into the model (runtime errors surface as SandboxError, not tracebacks).")
