"""SEC-PLUGIN-SANDBOX step three — the snippet runs in a different process, and that is PROVEN.

Steps one and two moved the contract: `execute_ifc_bytes` is `bytes -> bytes`, and `edit.RECIPES`
adopted it. Neither was isolation and neither claimed to be. This is the isolation.

WHY A CHILD PROCESS IS THE WHOLE POINT. The roadmap refused `setrlimit` as originally specified, and
was right to: `RLIMIT_CPU` bounds **cumulative CPU since process start**, so in a long-lived API
worker it kills that worker after enough ordinary traffic, and `SIGXCPU` lands on the whole process,
taking every concurrent request with it. `RLIMIT_AS` is process-wide too. The limits were never
wrong — the process they were to be applied to was. In a process that exists to run one snippet and
exit, "cumulative CPU" and "this snippet's CPU" are the same quantity.

THE ASSERTION THAT MATTERS IS THE PID. `result["isolated"] = True` is set by the parent, about
itself — a self-report, and worth nothing as evidence. `limits_applied["pid"]` is written by
`sandbox_child` into `result.json`; the parent never touches it. Comparing it to `os.getpid()` is the
difference between "we believe a child ran" and "a different process produced this file". For a
security boundary that difference is the entire claim, so this file asserts the pid and treats the
flag as decoration.

WHAT THIS DOES **NOT** CLAIM, stated because a sandbox that oversells itself is how people stop
reading the caveats:
  * On **Windows there are no CPU or memory ceilings** — `resource` is POSIX-only. The process
    boundary and the parent's wall-clock kill still apply. `limits_applied` reports what was actually
    set rather than what was intended, and this suite asserts that honesty rather than asserting the
    limits exist, because on this machine they do not.
  * A native call reached through an allowed binding is still bounded by that library, not by the
    trace hook. Unchanged from before, and still recorded in `sandbox.py`.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_sandbox_isolated.py
"""
import os
import subprocess
import sys

os.environ["AEC_ALLOW_IFC_CODE"] = "1"
os.environ.pop("AEC_SANDBOX_INPROC", None)

import ifcopenshell  # noqa: E402

from aec_data import sandbox  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def model_bytes(name: str = "Before") -> bytes:
    m = ifcopenshell.file(schema="IFC4")
    m.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name=name)
    return m.to_string().encode("utf-8")


RENAME = "model.by_type('IfcProject')[0].Name = 'AFTER'"

# --- isolation is the DEFAULT, not an opt-in ------------------------------------------------------
check("isolation is ON unless explicitly disabled", sandbox.isolate(),
      "a security control defaulted off is the built-but-unreachable shape — shipped, and never "
      "exercised by anyone")

out, res = sandbox.execute_ifc_bytes(model_bytes(), RENAME)

# --- the pid: evidence, not self-report -----------------------------------------------------------
child_pid = (res.get("limits_applied") or {}).get("pid")
check("the snippet ran in a DIFFERENT process — asserted by pid, not by a flag",
      isinstance(child_pid, int) and child_pid != os.getpid(),
      f"child pid {child_pid!r} vs this process {os.getpid()} — if these match, nothing was isolated "
      f"no matter what `isolated` says")
check("...and the result carries the child's own limit report",
      "limits_applied" in res and "platform" in res["limits_applied"],
      "result.json is written by the child; its absence means the parent fabricated the result")

# --- and it still does the work -------------------------------------------------------------------
back = ifcopenshell.file.from_string(out.decode("utf-8"))
check("the isolated run returns the mutated model",
      back.by_type("IfcProject")[0].Name == "AFTER",
      f"got {back.by_type('IfcProject')[0].Name!r}")
check("the delta still comes back", res.get("ok") is True and res.get("round_tripped") is True,
      str({k: res.get(k) for k in ("ok", "round_tripped")}))

# --- honesty about limits, rather than a claim they exist -----------------------------------------
lim = res["limits_applied"]
if sys.platform == "win32":
    check("on Windows the report says the ceilings are ABSENT rather than claiming them",
          lim.get("cpu_seconds") is None and lim.get("address_space_mb") is None
          and "note" in lim,
          f"{lim} — reporting a limit that was never set is worse than reporting none")
else:
    check("on POSIX the CPU and memory ceilings are actually applied",
          isinstance(lim.get("cpu_seconds"), int) and isinstance(lim.get("address_space_mb"), int),
          str(lim))

# --- the gate still holds through the child -------------------------------------------------------
os.environ["AEC_ALLOW_IFC_CODE"] = "0"
try:
    sandbox.execute_ifc_bytes(model_bytes(), RENAME)
    check("the disabled flag still refuses through the isolated path", False,
          "isolation widened the reach of a gated escape hatch")
except PermissionError:
    check("the disabled flag still refuses through the isolated path", True)
except Exception as e:  # noqa: BLE001
    check("the disabled flag still refuses through the isolated path", False,
          f"refused with {type(e).__name__}, not PermissionError — the child's exit code 4 must map "
          f"back to the same type the in-process path raises: {e}")
finally:
    os.environ["AEC_ALLOW_IFC_CODE"] = "1"

# --- a hostile snippet is still rejected, and rejected the same way --------------------------------
try:
    sandbox.execute_ifc_bytes(model_bytes(), "import os")
    check("the AST allowlist still rejects an import inside the child", False,
          "the child re-implemented or skipped the check")
except Exception as e:  # noqa: BLE001
    check("the AST allowlist still rejects an import inside the child",
          isinstance(e, sandbox.SandboxError), f"got {type(e).__name__}: {e}")

# --- FAIL CLOSED: an unlaunchable child must raise, never silently run here ------------------------
_real = sys.executable
try:
    sys.executable = os.path.join(os.path.dirname(_real), "no_such_python_binary.exe")
    try:
        sandbox.execute_ifc_bytes(model_bytes(), RENAME)
        check("an unlaunchable child FAILS CLOSED rather than running in this process", False,
              "the snippet ran in the API process with no boundary and no error — a sandbox that "
              "degrades to no sandbox is worse than none, because the caller never learns")
    except sandbox.SandboxError as e:
        check("an unlaunchable child FAILS CLOSED rather than running in this process",
              "sandbox child" in str(e).lower() or "could not start" in str(e).lower(), str(e)[:120])
    except Exception as e:  # noqa: BLE001
        check("an unlaunchable child FAILS CLOSED rather than running in this process", False,
              f"raised {type(e).__name__} instead of SandboxError: {e}")
finally:
    sys.executable = _real

# --- the opt-out exists, is explicit, and is visible in the result --------------------------------
os.environ["AEC_SANDBOX_INPROC"] = "1"
try:
    check("the escape hatch turns isolation off", not sandbox.isolate())
    _o, r2 = sandbox.execute_ifc_bytes(model_bytes(), RENAME)
    check("...and an in-process run does not pretend to be isolated",
          not r2.get("isolated") and "limits_applied" not in r2,
          f"{ {k: r2.get(k) for k in ('isolated', 'limits_applied')} } — claiming isolation while "
          f"running in-process is the one failure mode worse than not isolating")
finally:
    os.environ.pop("AEC_SANDBOX_INPROC", None)

# --- the child is a real module, invocable as documented ------------------------------------------
proc = subprocess.run([sys.executable, "-m", "aec_data.sandbox_child"],
                      capture_output=True, text=True, check=False,
                      env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path[:3])})
check("`python -m aec_data.sandbox_child` exists and refuses a missing workdir",
      proc.returncode == 2 and "usage" in (proc.stderr or "").lower(),
      f"exit {proc.returncode}: {(proc.stderr or proc.stdout)[:120]}")

print(f"\ntest_sandbox_isolated {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
