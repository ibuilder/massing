"""SEC-PLUGIN-SANDBOX step three — run one snippet in a dedicated child process, then exit.

    python -m aec_data.sandbox_child <workdir>

`<workdir>` holds `in.ifc` and `snippet.py`. On success this writes `out.ifc` and `result.json` and exits
0; on failure it writes the reason to stderr and exits non-zero. Nothing else is read or written, and
the process runs exactly one snippet before dying — a fresh interpreter per call is the cheapest way
to guarantee a snippet cannot leave state behind for the next one.

WHY A CHILD IS THE WHOLE POINT, and why the limits below could not be applied in the API process:

  * `RLIMIT_CPU` bounds **cumulative CPU since the process started**, not one call. Applied in a
    long-lived API worker it kills that worker after enough ordinary traffic, and `SIGXCPU` lands on
    the whole process — taking every concurrent request with it. In a process that exists to run one
    snippet and exit, "cumulative CPU" and "this snippet's CPU" are the same quantity.
  * `RLIMIT_AS` is process-wide too, so in-process it would cap unrelated threads. Here it caps the
    snippet.

That is the reason the roadmap refused `setrlimit` as originally specified: not that the limits are
wrong, but that the process they were to be applied to was.

NOT A SECOND IMPLEMENTATION. This calls `sandbox.execute_ifc_code` — the same AST allowlist, the same
trace hook, the same deadline as the in-process path. A child that re-implemented the checks would
drift from the parent silently, and the drift would be invisible precisely because both would keep
passing their own tests. The isolation is the only thing this file adds.

WINDOWS. `resource` is POSIX-only. On Windows the process boundary and the parent's wall-clock kill
still apply, but the CPU and memory ceilings do not — `limits_applied` in `result.json` says which
were actually set, so a caller is never told a limit is in force when it is not. Production is Linux
(`docker-compose.prod.yml`); local development on this machine is Windows, which is exactly the split
that would otherwise let an untested "it works here" claim through.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any

#: Seconds of CPU the snippet may burn. Distinct from the parent's wall-clock deadline: a snippet
#: blocked on nothing consumes no CPU, so a CPU limit alone would never fire on a sleep loop, and a
#: wall-clock limit alone is generous to a spin loop on a busy machine. Both, or neither is enough.
CPU_SECONDS = int(os.environ.get("AEC_IFC_CODE_CPU_SECONDS", "10"))

#: Address space ceiling. Generous, because ifcopenshell holds the whole model in memory and a large
#: IFC legitimately needs hundreds of MB — the limit exists to stop an allocation loop taking the host
#: down, not to be a tight quota. Too tight and the feature fails on real models, which gets it
#: switched off, which is the outcome the limit was meant to prevent.
ADDRESS_SPACE_MB = int(os.environ.get("AEC_IFC_CODE_MEMORY_MB", "2048"))


def apply_limits() -> dict[str, Any]:
    """Set the per-process ceilings. Returns what was actually applied, never what was intended."""
    # The pid is here so the caller can PROVE a separate process ran rather than take `isolated: True`
    # on trust. A flag the parent sets about itself is a self-report; a pid the parent can compare
    # against its own is evidence, and this is a security boundary — the difference matters.
    applied: dict[str, Any] = {"cpu_seconds": None, "address_space_mb": None,
                               "platform": sys.platform, "pid": os.getpid()}
    try:
        import resource  # noqa: PLC0415 — POSIX-only, by design
    except ImportError:
        applied["note"] = "resource unavailable (Windows): process isolation and the parent's " \
                          "wall-clock kill apply; CPU and memory ceilings do not"
        return applied

    # Soft limit below hard so the snippet gets SIGXCPU while the process can still report; setting
    # both equal makes the kill immediate and the failure indistinguishable from a crash.
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 2))
        applied["cpu_seconds"] = CPU_SECONDS
    except (ValueError, OSError) as e:                      # a container may already cap it lower
        applied["cpu_seconds_error"] = f"{type(e).__name__}: {e}"
    try:
        nbytes = ADDRESS_SPACE_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (nbytes, nbytes))
        applied["address_space_mb"] = ADDRESS_SPACE_MB
    except (ValueError, OSError) as e:
        applied["address_space_mb_error"] = f"{type(e).__name__}: {e}"
    return applied


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m aec_data.sandbox_child <workdir>", file=sys.stderr)
        return 2
    work = pathlib.Path(argv[1])
    src, code_path = work / "in.ifc", work / "snippet.py"
    if not src.is_file() or not code_path.is_file():
        print(f"workdir {work} must contain in.ifc and snippet.py", file=sys.stderr)
        return 2

    limits = apply_limits()

    # Imported AFTER the limits are set, so a hostile snippet cannot benefit from anything the import
    # itself allocates, and so an import failure is reported as an import failure rather than as a
    # memory error at some unrelated later point.
    from . import sandbox

    try:
        import ifcopenshell
        model = ifcopenshell.open(str(src))
    except Exception as e:                                  # noqa: BLE001 — the caller's bad model
        print(f"could not read the model: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    try:
        result = sandbox.execute_ifc_code(model, code_path.read_text(encoding="utf-8"))
    except PermissionError as e:
        # The flag is off in the child. Distinct exit code so the parent can re-raise the same type
        # rather than flattening a configuration refusal into a generic sandbox failure.
        print(str(e), file=sys.stderr)
        return 4
    except Exception as e:                                  # noqa: BLE001 — snippet errors are data
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 5

    model.write(str(work / "out.ifc"))
    (work / "result.json").write_text(
        json.dumps({**result, "limits_applied": limits}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
