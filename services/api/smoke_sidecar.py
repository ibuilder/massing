"""Run the PACKAGED sidecar binary and prove it serves — the step the release pipeline never had.

`.github/workflows/desktop.yml` built the Tauri bundles, signed them and uploaded them, and no step
ever executed the result. DESKTOP-FROZEN was a startup crash on one of the three platforms it
publishes and **every check was green**, because every check read source. `repo_root()` counted
`parents[4]`; in a PyInstaller bundle `__file__` is `$TMPDIR/_MEIxxxxxx/aec_api/desktop.py`, which
under the default `TMPDIR=/tmp` has exactly four parents, so `aec-bim-server` raised `IndexError: 4`
and died before binding a port. Windows and macOS temp paths are eight parents deep, which is why it
was only ever seen on Linux, by users, after v0.3.1133 shipped.

**So this deliberately runs under a SHALLOW temp directory.** A smoke test on a deep temp path would
have passed against the broken binary — the depth IS the test, and `--shallow-tmp` (the default on
POSIX) is not a detail of the harness but the thing being asserted.

WHAT IT PROVES, and the boundary. The binary starts; `/health` answers, so the process bound a port
rather than dying during import; `/ready` answers, so the SQLite engine opened under a fresh data
directory; `/modules` returns a non-empty catalog, so the `datas` carrying `services/api/modules`
landed inside the bundle; and `/` serves HTML, so the bundled SPA did too. Those last two are the
ones source-level checks cannot make at all: they are questions about the ARCHIVE, not the tree.

WHAT IT DOES NOT PROVE. It never converts a model, so `aec_data.fragments` — and the `flatbuffers`
import inside `codec.py` — is not exercised: the only route that reaches it needs a project with an
uploaded source IFC, and `edit_preview` FAILS OPEN with a 503, so a smoke asserting it would pass
vacuously on a fresh install. That gap is filed as DESKTOP-SMOKE-CONVERT rather than papered over.

VACUITY GUARDS, because "the artifact was missing" and "the artifact is fine" must never look alike:

* a missing binary is a FAILURE, not a skip — the whole class this file exists for is a check that
  cannot see its own subject;
* the port is proven free before launch, so a response cannot have come from something else already
  listening;
* the child exiting before `/health` answers is a failure that prints what it said, since a frozen
  app's traceback is the only evidence of a frozen-path defect.

Run locally against a binary you built:
    python services/api/smoke_sidecar.py apps/web/src-tauri/binaries/aec-bim-server-<triple>
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # services/api
REPO = HERE.parents[1]
BINARIES = REPO / "apps" / "web" / "src-tauri" / "binaries"
CATALOG = HERE / "modules"                             # the module.json catalog the bundle carries

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(("PASS  " if ok else "FAIL  ") + label + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)
    return ok


def find_binary(explicit: str | None) -> Path | None:
    """The sidecar to run. An explicit path wins; otherwise the single one `build_sidecar.py` placed.

    Returns None rather than guessing when the directory holds none or several — a smoke test that
    picked the wrong file would report on something nobody shipped.
    """
    if explicit:
        return Path(explicit)
    if not BINARIES.is_dir():
        return None
    found = sorted(p for p in BINARIES.iterdir()
                   if p.is_file() and p.name.startswith("aec-bim-server-"))
    return found[0] if len(found) == 1 else None


def free_port() -> int:
    """A port nothing is listening on, proven by binding it. Released immediately, so this is a
    narrow race — but the alternative is a hardcoded 8765 that a leftover process may already own,
    which would let this file report on the WRONG server."""
    with contextlib.closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def port_is_free(port: int) -> bool:
    with contextlib.closing(socket.socket()) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def get(url: str, timeout: float = 10.0) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:      # noqa: S310 — fixed 127.0.0.1
            return r.status, r.read(), r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("content-type", "")
    except Exception:                                                # noqa: BLE001 — not up yet
        return 0, b"", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("binary", nargs="?", help="path to aec-bim-server-<triple>")
    ap.add_argument("--timeout", type=float, default=180.0,
                    help="seconds to wait for /health (onefile extraction + the API import are slow)")
    ap.add_argument("--deep-tmp", action="store_true",
                    help="use the default temp directory instead of a shallow one. This is the "
                         "configuration under which the DESKTOP-FROZEN crash did NOT reproduce, so "
                         "it exists to demonstrate that the shallow default is load-bearing")
    args = ap.parse_args()

    binary = find_binary(args.binary)
    # THE VACUITY GUARD. Everything below is a statement about a binary; without one there is no
    # population, and a pass would mean "did not look".
    if not check("a sidecar binary was found to run", bool(binary) and binary.is_file(),
                 str(binary) if binary else f"no single aec-bim-server-* in {BINARIES}"):
        print("\nFAILED:", ", ".join(FAILED))
        return 1
    print(f"  binary: {binary}  ({binary.stat().st_size // (1024 * 1024)} MB)")

    port = free_port()
    check("the chosen port is free before launch — otherwise a reply could come from another server",
          port_is_free(port), f"127.0.0.1:{port}")

    env = dict(os.environ)
    data_dir = tempfile.mkdtemp(prefix="aec-smoke-data-")
    env["AEC_DATA_DIR"] = data_dir
    env["AEC_HOST"] = "127.0.0.1"
    env["AEC_PORT"] = str(port)
    env["AEC_OPEN_BROWSER"] = "0"

    # The point of the exercise on POSIX. `/tmp` gives `_MEIxxxxxx/aec_api/desktop.py` exactly four
    # parents, which is what raised IndexError in the shipped v0.3.1133 AppImage. Windows has no
    # TMPDIR and its temp paths are deep anyway, so there is nothing to force there.
    shallow = os.name != "nt" and not args.deep_tmp
    if shallow:
        env["TMPDIR"] = "/tmp"
    print(f"  temp: {'SHALLOW /tmp (the configuration DESKTOP-FROZEN died under)' if shallow else 'default'}"
          f"   data: {data_dir}")

    log = Path(tempfile.mkstemp(prefix="aec-smoke-log-", suffix=".txt")[1])
    with log.open("wb") as sink:
        proc = subprocess.Popen([str(binary)], env=env, stdout=sink, stderr=subprocess.STDOUT,
                                cwd=str(REPO))

        def output() -> str:
            return log.read_text(encoding="utf-8", errors="replace").strip() or "(no output)"

        try:
            started = time.time()
            deadline = started + args.timeout
            status = 0
            while time.time() < deadline:
                if proc.poll() is not None:
                    check(f"the sidecar stayed up long enough to answer /health "
                          f"(it exited with {proc.returncode})", False,
                          "a frozen-path defect kills the process during import, before any port is "
                          "bound — the child's own traceback below is the only evidence there is")
                    print("\n---- sidecar output ----\n" + output() + "\n------------------------")
                    print("\nFAILED:", ", ".join(FAILED))
                    return 1
                status, _body, _ct = get(f"http://127.0.0.1:{port}/health", timeout=2.0)
                if status == 200:
                    break
                time.sleep(1.0)

            if not check("GET /health answers 200 — the packaged binary booted and bound a port",
                         status == 200,
                         f"last status {status} after {time.time() - started:.1f}s (bound {args.timeout:g}s)"):
                print("\n---- sidecar output ----\n" + output() + "\n------------------------")
                print("\nFAILED:", ", ".join(FAILED))
                return 1

            st, body, _ct = get(f"http://127.0.0.1:{port}/ready")
            check("GET /ready answers 200 — the SQLite engine opened under a fresh data directory",
                  st == 200, f"status {st}: {body[:200]!r}")

            # `datas` questions, which no source-level check can ask: these directories are inside
            # the archive or they are not, and the tree says nothing either way.
            st, body, _ct = get(f"http://127.0.0.1:{port}/modules")
            mods = []
            if st == 200:
                with contextlib.suppress(Exception):
                    mods = json.loads(body)
            served = len(mods) if isinstance(mods, list) else -1
            # DERIVED, not a floor. The tree is checked out beside the binary in CI, so the question
            # is answerable exactly: the bundle must serve every module the tree declares. A ">100"
            # threshold would pass a bundle that silently dropped thirty catalogs, which is the shape
            # of defect the `datas` list produces when a glob stops matching.
            declared = len(list(CATALOG.glob("*/module.json"))) if CATALOG.is_dir() else 0
            check("the module catalog in the tree is non-empty — otherwise the comparison below "
                  "compares nothing", declared > 0, f"{declared} module.json under {CATALOG}")
            check("GET /modules serves every module the tree declares — the bundled module.json "
                  "datas landed, all of them",
                  st == 200 and served == declared > 0,
                  f"status {st}, served {served}, declared {declared}")

            st, body, ct = get(f"http://127.0.0.1:{port}/")
            check("GET / serves the bundled SPA — the packaged web/ datas landed and are mounted",
                  st == 200 and "html" in ct.lower() and b"<" in body[:512],
                  f"status {st}, content-type {ct!r}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=20)

    if FAILED:
        print("\n---- sidecar output ----\n"
              + log.read_text(encoding="utf-8", errors="replace").strip() + "\n------------------------")
        print("\nFAILED:", ", ".join(FAILED))
        return 1
    print("\nsmoke_sidecar OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
