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

AND IT CONVERTS A MODEL, which is the half none of that reaches. `aec_data.fragments` is imported
lazily inside `fragconvert.convert_ifc`, and `codec.py` imports `flatbuffers` at module scope — so a
build that packaged neither BOOTS PERFECTLY and fails the first time a user publishes. The check
authors a blank model through `POST /projects/{pid}/model/blank` (generated server-side by
`aec_data.massing`, so no IFC fixture has to be tracked), publishes it, and requires the published
fragment back. It also asserts WHICH converter ran: a bundle carries no Node runtime, so it must be
the Python one, and accepting either would let this pass on any runner with Node installed without
touching the code under test.

The obvious version of that check would have been worthless: `edit_preview` FAILS OPEN with a 503, so
a fresh install answers 503 whether the frozen import works or not. Publish is the path that reports
the failure instead of swallowing it — `convert_ifc` raising is recorded as `reconvert_error` and
turns the publish state to `error`, carrying the exception.

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
import zlib
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
    """Re-check the port `free_port` picked, after it released the socket.

    Two functions rather than one because they answer different questions at different moments:
    `free_port` chooses, this confirms the choice still holds at launch. The gap between them is the
    race, and it is narrow but real — which is why the confirmation is an assertion the reader can
    see fail rather than an assumption folded into the picking.
    """
    with contextlib.closing(socket.socket()) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def get(url: str, timeout: float = 10.0) -> tuple[int, bytes, str]:
    """GET `url`, returning (status, body, content-type) — and status **0** when nothing answered.

    The 0 is load-bearing, not a shortcut. While the sidecar is still starting there is no listener,
    so a connection error is the expected reading and the poll loop must be able to tell it apart
    from a real reply; raising would make "not up yet" and "up and broken" the same event. An HTTP
    error status is NOT collapsed into it — a 500 is an answer, and comes back as 500.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:      # noqa: S310 — fixed 127.0.0.1
            return r.status, r.read(), r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("content-type", "")
    except Exception:                                                # noqa: BLE001 — not up yet
        return 0, b"", ""


def post(url: str, payload: dict, timeout: float = 300.0) -> tuple[int, bytes]:
    """POST `payload` as JSON, returning (status, body) — and status **0** when nothing answered.

    Same 0 convention as `get`, for the same reason: the caller has to tell a dead server apart from
    one that answered badly. The timeout is generous because the call this drives runs a whole
    IFC->Fragments conversion on the server before it returns a status.
    """
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:                  # noqa: S310
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:                                                # noqa: BLE001 — not up / refused
        return 0, b""


def convert_a_model(port: int, expect: str, timeout: float) -> None:
    """Author a model and publish it, so the CONVERTER runs inside the artifact under test.

    This is the half `/health` and `/modules` cannot reach. `aec_data.fragments` is imported lazily,
    inside `fragconvert.convert_ifc`, so nothing on the boot path touches it — and `codec.py` imports
    `flatbuffers` at module scope, which PyInstaller's analysis *should* follow. "Should" was doing
    real work in that sentence until this existed.

    **No IFC fixture is tracked, deliberately.** `POST /projects/{pid}/model/blank` generates one
    server-side through `aec_data.massing`, so the model is authored by the artifact rather than
    handed to it — which exercises more of the bundle and cannot drift from a checked-in file.

    **Why this is not vacuous.** A converter that raises is caught in `authoring._publish`, recorded
    as `reconvert_error`, and `run_publish` turns that into publish state `error` — so a missing
    `flatbuffers` surfaces here as a named failure rather than a quiet skip. The obvious alternative
    check would have been vacuous: `edit_preview` FAILS OPEN with a 503, so a fresh install answers
    503 whether the frozen import works or not.

    **And it asserts WHICH converter ran.** Publish reports `node` or `python`. The bundle carries no
    Node runtime, so it must report `python` — the path that needs `flatbuffers`. Accepting either
    would let this pass for the wrong reason on a machine where Node happens to be reachable, which
    is every CI runner this workflow uses. `expect` is declared by the caller rather than guessed
    from the environment, because a check that infers what it should require can infer wrongly and
    still look green.
    """
    base = f"http://127.0.0.1:{port}"

    st, body = post(f"{base}/projects", {"name": "smoke-convert"})
    pid = ""
    if st in (200, 201):
        with contextlib.suppress(Exception):
            pid = str(json.loads(body).get("id") or "")
    if not check("POST /projects creates a project — the model has to hang off something",
                 bool(pid), f"status {st}: {body[:200]!r}"):
        return

    st, body = post(f"{base}/projects/{pid}/model/blank", {"name": "Smoke", "storeys": 1})
    if not check("POST /projects/{id}/model/blank authors an IFC inside the artifact — "
                 "`aec_data.massing` runs in the bundle, so no fixture has to be shipped",
                 st == 200, f"status {st}: {body[:300]!r}"):
        return

    # Publish is off-thread; the client polls. `error` is the state a failed convert produces, and it
    # carries the exception — which for a missing frozen import is the whole diagnosis.
    started = time.time()
    deadline = started + timeout
    state, detail = "", {}
    while time.time() < deadline:
        st, body, _ct = get(f"{base}/projects/{pid}/publish/status")
        if st == 200:
            with contextlib.suppress(Exception):
                s = json.loads(body)
                state, detail = str(s.get("state") or ""), s.get("detail") or {}
        if state not in ("", "idle", "running"):
            break
        time.sleep(1.0)

    if not check("the publish finished, and the CONVERSION inside it did not fail — a frozen build "
                 "missing `flatbuffers` raises here and is recorded as `reconvert_error`",
                 state == "done",
                 f"publish state {state!r} after {time.time() - started:.1f}s (bound {timeout:g}s); "
                 f"detail {json.dumps(detail)[:400]}"):
        return

    ran = str(detail.get("converter") or "")
    check(f"the {expect!r} converter is the one that ran — otherwise this passed without "
          f"exercising the path it exists to test",
          ran == expect, f"publish reports converter {ran!r}, expected {expect!r}")

    st, frag, _ct = get(f"{base}/projects/{pid}/model.frag", timeout=60.0)
    if not check("GET /model.frag serves the converted geometry the viewer would draw",
                 st == 200 and len(frag) > 0, f"status {st}, {len(frag)} bytes"):
        return

    # `.frag` is zlib(flatbuffers). Decompressing proves real content rather than a stub, and the
    # flatbuffer root offset has to land inside the buffer — a cheap structural check that a
    # truncated or empty write fails. Not a size floor: a floor is a number, this is a property.
    raw, why = b"", ""
    try:
        raw = zlib.decompress(frag)
    except Exception as e:                                           # noqa: BLE001 — reported below
        why = f"{type(e).__name__}: {e}"
    root = int.from_bytes(raw[:4], "little") if len(raw) >= 4 else -1
    check("the served bytes are a real fragment — zlib-compressed flatbuffers whose root offset "
          "lands inside the buffer",
          bool(raw) and 4 <= root < len(raw),
          f"{len(frag)} compressed -> {len(raw)} bytes, root offset {root}"
          + (f"; zlib {why}" if why else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("binary", nargs="?", help="path to aec-bim-server-<triple>")
    ap.add_argument("--timeout", type=float, default=180.0,
                    help="seconds to wait for /health (onefile extraction + the API import are slow)")
    ap.add_argument("--expect-converter", default="python", choices=("node", "python"),
                    help="which converter the publish must report having used. Defaults to `python` "
                         "because that is what the packaged bundle has to use — it carries no Node "
                         "runtime — and it is the path that needs `flatbuffers` to survive freezing. "
                         "Pass `node` when running against a source checkout, where Node is present "
                         "and IS the right answer. Declared rather than inferred: a check that "
                         "guesses what it should require can guess wrong and still look green.")
    ap.add_argument("--convert-timeout", type=float, default=300.0,
                    help="seconds to wait for the publish to leave `running`")
    ap.add_argument("--skip-convert", action="store_true",
                    help="boot checks only. For diagnosing a sidecar that will not start — NOT for "
                         "getting a red build green, which is how the gap this closes stayed open")
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
            # Every entry must BE a module before its key can be compared to anything. An earlier
            # draft read `m.get("key")` and then dropped `None` out of the difference — which made a
            # response of all 139 valid entries PLUS a bare `{}` pass: nothing missing, nothing
            # extra, no duplicates. **A filter that decides what to LOOK at is the fail-open shape**,
            # and it hid a malformed catalog behind a correct one. Malformed entries are now counted
            # and named rather than skipped. (Found in review of this file, which is fitting: the
            # assertion exists because a check that cannot see its subject reports success.)
            served: list[str] = []
            malformed = 0
            for m in mods if isinstance(mods, list) else []:
                k = m.get("key") if isinstance(m, dict) else None
                if isinstance(k, str) and k:
                    served.append(k)
                else:
                    malformed += 1

            # DERIVED, and by IDENTITY rather than by count. The tree is checked out beside the
            # binary in CI, so the question is answerable exactly: which modules does the bundle
            # serve, and are they the ones the tree declares? A `>100` floor passes a bundle that
            # silently dropped thirty catalogs — the shape of defect a `datas` glob produces when it
            # stops matching — and a count comparison still passes one that dropped a module and
            # double-loaded another. Comparing sets names WHICH module went missing, which is the
            # difference between a failure you can act on and a number that went down.
            #
            # The declared id is read from each `module.json`'s `key`, not from its directory name.
            # They agree today, all 139 of them, and that is exactly why the field is the right one:
            # `key` is what the route serves, and a check should compare the thing itself rather than
            # a proxy that happens to match.
            #
            # The same shape rule applies to THIS side. A `module.json` with no `key` would otherwise
            # put `None` into `declared`, which then reports as a missing module named `None` — and
            # `sorted()` over a set mixing `None` with strings raises, so the harness would die
            # rather than report. Both sides are validated, and the counts are compared, so a
            # catalog file the tree cannot parse is a failure here rather than a silent shortfall.
            catalogs = sorted(CATALOG.glob("*/module.json")) if CATALOG.is_dir() else []
            declared = set()
            for mj in catalogs:
                with contextlib.suppress(Exception):
                    k = json.loads(mj.read_text(encoding="utf-8")).get("key")
                    if isinstance(k, str) and k:
                        declared.add(k)
            check("the module catalog in the tree is non-empty — otherwise the comparison below "
                  "compares nothing", bool(declared), f"{len(declared)} module.json under {CATALOG}")
            check("every module.json in the tree declares a distinct non-empty `key` — otherwise "
                  "the set below is smaller than the catalog and the shortfall is invisible",
                  len(declared) == len(catalogs),
                  f"{len(declared)} usable keys from {len(catalogs)} catalog file(s)")

            missing = sorted(k for k in declared if k not in served)
            extra = sorted(set(served) - declared)
            # Duplicate-aware: two entries for one key is not "the right modules". A bundle carrying
            # a stale copy of a catalog alongside the current one would serve the same key twice, and
            # a set comparison alone would call that correct.
            dupes = sorted({k for k in served if served.count(k) > 1})
            check("GET /modules serves exactly the modules the tree declares, once each — the "
                  "bundled module.json datas landed, all of them and nothing else",
                  st == 200 and bool(declared) and not missing and not extra and not dupes
                  and not malformed,
                  f"status {st}, served {len(served)} of {len(declared)} declared"
                  + (f", {malformed} MALFORMED entr{'y' if malformed == 1 else 'ies'} "
                     f"(not an object with a non-empty string `key`)" if malformed else "")
                  + (f", MISSING {missing[:8]}" if missing else "")
                  + (f", UNEXPECTED {extra[:8]}" if extra else "")
                  + (f", DUPLICATED {dupes[:8]}" if dupes else ""))

            st, body, ct = get(f"http://127.0.0.1:{port}/")
            check("GET / serves the bundled SPA — the packaged web/ datas landed and are mounted",
                  st == 200 and "html" in ct.lower() and b"<" in body[:512],
                  f"status {st}, content-type {ct!r}")

            # The half the boot checks cannot reach: run the converter inside the artifact.
            if args.skip_convert:
                print("  SKIPPED the conversion checks (--skip-convert) — this run does NOT show "
                      "that model conversion survives packaging")
            else:
                convert_a_model(port, args.expect_converter, args.convert_timeout)
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
