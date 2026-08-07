"""SEC-PLUGIN-SANDBOX step 1 — the sandbox gains a bytes-in/bytes-out contract.

WHY THIS EXISTS, AND WHAT IT IS NOT. It is **not** isolation. `execute_ifc_bytes` runs in the same
process as everything else and is no safer today than `execute_ifc_code`. What it changes is the
*contract*, and the contract was the actual blocker:

`execute_ifc_code(model, code)` takes a live in-memory `ifcopenshell.file` and the snippet mutates it
**in place**; the caller keeps using that object afterwards. A child process cannot share an
in-memory object, so running the snippet elsewhere means serialise → run → serialise back → reload —
handing the caller a NEW object and breaking every one of them. **That is an API contract change at
the call site, not a deployment choice**, which is why R35-SANDBOX-ISOLATION kept being filed as
"needs a decision about the deployment shape" while the real obstacle sat in this function's
signature. With a `bytes -> bytes` callee, moving execution to a subprocess or a container is a
change to one function body and to nothing else.

WHAT THIS ASSERTS
  * the round trip preserves the model — the elements that went in come back, by GlobalId, because
    "it returned some bytes" is not evidence that a model survived;
  * a snippet's edit is visible in the RETURNED bytes, not merely in a discarded in-memory object;
  * the feature flag gates this door too — a gate only the neighbouring entry point carries is not
    a gate, which is the shape this repo has shipped twice;
  * the AST sandbox still applies (a new door must not be a way around the checks);
  * **nothing is left in the temp directory**, including when the snippet raises. A sandbox that
    leaves the model it was handed lying on disk has undone part of the point of having one.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_sandbox_bytes.py
"""
import glob
import os
import shutil
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_sandbox_bytes.db"
os.environ["STORAGE_DIR"] = "./test_storage_sandbox_bytes"
os.environ["AEC_ALLOW_IFC_CODE"] = "1"
for _f in ("./test_sandbox_bytes.db",):
    if os.path.exists(_f):
        os.remove(_f)

import ifcopenshell  # noqa: E402

from aec_data import sandbox  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def sample_ifc() -> bytes:
    """A minimal but real IFC: a project with two walls carrying stable GlobalIds."""
    m = ifcopenshell.file(schema="IFC4")
    m.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Sandbox Fixture")
    for n in ("Wall A", "Wall B"):
        m.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name=n)
    d = tempfile.mkdtemp(prefix="fixture_")
    p = os.path.join(d, "f.ifc")
    m.write(p)
    with open(p, "rb") as fh:
        return fh.read()


IFC = sample_ifc()
guids_in = {w.GlobalId for w in ifcopenshell.file.from_string(IFC.decode("utf-8", "replace"))
            .by_type("IfcWall")}
check("the fixture really has two walls", len(guids_in) == 2, str(len(guids_in)))


def walls_of(data: bytes):
    m = ifcopenshell.file.from_string(data.decode("utf-8", "replace"))
    return {w.GlobalId: w.Name for w in m.by_type("IfcWall")}


# --------------------------------------------------------------------------------------------
# 1) The round trip preserves the model.
# --------------------------------------------------------------------------------------------
out, res = sandbox.execute_ifc_bytes(IFC, "pass")
check("a no-op snippet returns a readable model", bool(out) and len(walls_of(out)) == 2,
      f"{len(out)} bytes, {len(walls_of(out))} walls")
check("...with the SAME GlobalIds — GUID stability survives the round trip",
      set(walls_of(out)) == guids_in,
      f"in={sorted(guids_in)} out={sorted(walls_of(out))}")
check("the delta reports no net change", res["created"] == 0 and res["deleted"] == 0, str(res))
check("the result says it round-tripped, so a caller need not guess",
      res.get("round_tripped") is True and res.get("bytes_out"), str(res))

# --------------------------------------------------------------------------------------------
# 2) An edit is visible in the RETURNED bytes. This is the assertion the contract exists for:
#    under the in-place API the mutation lived in an object the caller already held, and a
#    bytes-out API that forgot to re-serialise would look identical from the delta alone.
# --------------------------------------------------------------------------------------------
ADD = ('model.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="Wall C")\n')
out2, res2 = sandbox.execute_ifc_bytes(IFC, ADD)
names = set(walls_of(out2).values())
check("a snippet's new element is present in the returned bytes", "Wall C" in names,
      f"walls out: {sorted(names)} — the edit did not reach the serialisation")
check("...and the delta counts it", res2["created"] >= 1, str(res2))
check("the input bytes are untouched — the caller's copy is not mutated under it",
      len(walls_of(IFC)) == 2, "the fixture changed, so this is not a value-in/value-out contract")

# --------------------------------------------------------------------------------------------
# 3) The gate is on THIS door too.
# --------------------------------------------------------------------------------------------
os.environ["AEC_ALLOW_IFC_CODE"] = "0"
try:
    sandbox.execute_ifc_bytes(IFC, "pass")
    check("the feature flag gates the bytes entry point", False, "it ran with the flag off")
except PermissionError:
    check("the feature flag gates the bytes entry point", True)
except Exception as e:  # noqa: BLE001
    check("the feature flag gates the bytes entry point", False, f"wrong error: {type(e).__name__}")

# ...and it refuses BEFORE doing any work, which is the part the check above cannot see.
#
# `execute_ifc_code` checks the flag too, so deleting the check from THIS function still produces a
# PermissionError — an equivalent mutant, and it survived the first version of this file. The
# difference is *when*: with the outer check gone, the bytes are written to a temp directory and
# handed to `ifcopenshell.open` first, so unreadable input fails as a parse error before the flag is
# ever consulted. Garbage bytes with the flag off therefore separate the two arrangements exactly —
# PermissionError means refused at the door, SandboxError means it read the file first.
#
# This matters beyond tidiness: once execution moves out of process, the inner check is running
# somewhere else, and a door that relies on its callee's gate has no gate of its own.
try:
    sandbox.execute_ifc_bytes(b"this is not an IFC file", "pass")
    check("the flag is checked BEFORE the model is read", False, "it ran with the flag off")
except PermissionError:
    check("the flag is checked BEFORE the model is read", True)
except sandbox.SandboxError as e:
    check("the flag is checked BEFORE the model is read", False,
          f"it parsed the input before checking the flag: {e}")
os.environ["AEC_ALLOW_IFC_CODE"] = "1"

# --------------------------------------------------------------------------------------------
# 4) The AST sandbox still applies — a new door must not route around the checks.
# --------------------------------------------------------------------------------------------
for hostile, label in [
    ("import os\nos.system('echo hi')", "import"),
    ("ifcopenshell.os.system('echo hi')", "module attribute walk"),
    ("__import__('os').system('echo hi')", "dunder import"),
    ("open('/etc/passwd').read()", "file open"),
]:
    try:
        sandbox.execute_ifc_bytes(IFC, hostile)
        check(f"the bytes door still refuses: {label}", False, "it ran")
    except sandbox.SandboxError:
        check(f"the bytes door still refuses: {label}", True)
    except Exception as e:  # noqa: BLE001
        check(f"the bytes door still refuses: {label}", False, f"wrong error: {type(e).__name__}")

# --------------------------------------------------------------------------------------------
# 5) No temp residue — including on the failure path.
# --------------------------------------------------------------------------------------------
# THE POPULATION HAS TO BE THIS TEST'S OWN DIRECTORIES, not every `ifc_sandbox_*` on the machine.
#
# This globbed the SHARED temp dir, which was survivable while `execute_ifc_bytes` ran in-process and
# held its directory for milliseconds. Step three moved execution into a child, so each call now holds
# one for ~0.7s (interpreter start + ifcopenshell import) — and `run_tests.py` runs three suites in
# parallel, five of which use the sandbox. Instrumenting a single call observed **19** live
# `ifc_sandbox_*` directories at once, all belonging to other suites.
#
# The `before` snapshot does not save it: a sibling's directory created AFTER that snapshot and still
# alive at the end appears in `new` and fails a test whose own cleanup was perfect. That is the same
# defect `test_sweep_guard` was cut down for — an assertion whose answer depends on scheduling — and it
# is worth noticing that isolation did not introduce the race, it made a latent one observable by
# widening the window a thousandfold.
#
# So: point `tempfile` at a private root for this section. `mkdtemp` inside the sandbox reads
# `tempfile.gettempdir()`, so the sandbox's own directories land here and nobody else's do. The
# assertion then means what it says — *this* test leaked nothing — rather than "no suite anywhere is
# mid-flight".
_shared_tmp = tempfile.tempdir
_own_tmp = tempfile.mkdtemp(prefix="sandbox_bytes_residue_")
tempfile.tempdir = _own_tmp


def leftovers() -> list[str]:
    return glob.glob(os.path.join(tempfile.gettempdir(), "ifc_sandbox_*"))


before = set(leftovers())
sandbox.execute_ifc_bytes(IFC, "pass")
try:
    sandbox.execute_ifc_bytes(IFC, "raise ValueError('boom')")
except sandbox.SandboxError:
    pass
try:
    sandbox.execute_ifc_bytes(b"not an ifc file at all", "pass")
except sandbox.SandboxError:
    pass
new = set(leftovers()) - before
check("no temp directory survives a success, a raising snippet, or an unreadable model",
      not new, f"left behind: {sorted(new)}")
# Non-vacuity: if the private root were never used, `leftovers()` would be empty for a reason that has
# nothing to do with cleanup, and the check above would pass on an empty directory forever. Assert the
# sandbox actually wrote here — a residue check that cannot see the residue is not a check.
check("...and the sandbox really did use this test's private temp root",
      os.path.isdir(_own_tmp) and _shared_tmp != _own_tmp,
      f"private root {_own_tmp!r} — the residue assertion above would be vacuous")
tempfile.tempdir = _shared_tmp
shutil.rmtree(_own_tmp, ignore_errors=True)

print(f"\ntest_sandbox_bytes {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
