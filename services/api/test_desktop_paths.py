"""DESKTOP-FROZEN — the shipped desktop app must be able to find its own files.

## What this is about

`aec_api.desktop` locates the bundled web build and module catalog by walking UP from `__file__`
with hard-coded `parents[N]` indices. That works in a source checkout and is **wrong in the frozen
build**, which is the only place it actually matters.

In a PyInstaller one-file bundle `__file__` is `$TMPDIR/_MEIxxxxxx/aec_api/desktop.py`. With the
default `TMPDIR=/tmp` on Linux that path has exactly FOUR parents:

    parents[0] /tmp/_MEIxxxxxx/aec_api
    parents[1] /tmp/_MEIxxxxxx
    parents[2] /tmp
    parents[3] /
    parents[4] IndexError

`web_dist()` asked for `parents[4]`, **unconditionally** — the list of candidates is built eagerly,
so it raised before the loop could reach the bundled copy it appends first. The desktop app died on
startup, before binding a port:

    File "aec_api/desktop.py", line 38, in web_dist
    File "pathlib.py", line 282, in __getitem__
    IndexError: 4
    [PYI-827:ERROR] Failed to execute script 'desktop_entry'

**Measured against the published v0.3.1133 AppImage**, not reasoned about: with `TMPDIR=/tmp` it
crashed every time; with a deeper `TMPDIR` the same binary started, bound 127.0.0.1:8765, served
`/health`, the embedded frontend and `/modules`. The only variable was how deep the temp directory
was.

**Which is why it shipped.** Windows (`C:\\Users\\…\\AppData\\Local\\Temp\\_MEI…`) and macOS
(`/var/folders/xx/yyyy/T/_MEI…`) temp paths are eight parents deep. Only Linux — the AppImage and the
.deb — is shallow enough to break, so any test on the developer's own machine passed.

## The second one, which is NOT fatal and is recorded so nobody "fixes" it twice

`modules_dir()` asks for `parents[3] / "modules"` under a comment that says `# services/api/modules`.
`parents[3]` is `services`, so the path it builds is `services/modules`, which does not exist. It is
guarded by `is_dir()`, so it silently returns None instead of raising — and nothing breaks, because
`modules_registry.MODULES_DIR` has its own correct default (`parents[2] / "modules"`). So this is a
DEAD fallback masked by a working one, not a live defect. It is fixed here because its comment
documents an intent the code does not implement, and because it sits one index away from the class
that took the app down.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_desktop_paths.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(f"{label} — {detail}" if detail else label)


from aec_api import desktop  # noqa: E402

REAL_FILE = desktop.__file__

# --- the blast radius, computed rather than asserted from memory ---------------------------------
# A frozen `__file__` under each platform's default temp directory. This is the whole reason the
# defect reached users: only one of these is shallow enough to break.
LAYOUTS = {
    "linux /tmp":      PurePosixPath("/tmp/_MEI123456/aec_api/desktop.py"),
    "linux /var/tmp":  PurePosixPath("/var/tmp/_MEI123456/aec_api/desktop.py"),
    "macos":           PurePosixPath("/var/folders/qr/8mz1_1/T/_MEI123456/aec_api/desktop.py"),
    "windows":         PureWindowsPath(r"C:\Users\me\AppData\Local\Temp\_MEI123456\aec_api\desktop.py"),
}
check("the linux default temp layout really is too shallow for parents[4]",
      len(LAYOUTS["linux /tmp"].parents) == 4,
      f"{len(LAYOUTS['linux /tmp'].parents)} parents — if this changes the bug's shape changed too")
check("...and every other platform is deep enough, which is why it shipped",
      all(len(p.parents) > 4 for k, p in LAYOUTS.items() if k != "linux /tmp"),
      {k: len(p.parents) for k, p in LAYOUTS.items()})

# --- THE DEFECT: a frozen, shallow layout must not raise -------------------------------------------
with tempfile.TemporaryDirectory() as td:
    meipass = Path(td) / "_MEI123456"
    (meipass / "web").mkdir(parents=True)
    (meipass / "web" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (meipass / "modules").mkdir()
    try:
        # Both halves of the frozen environment: the extracted-bundle marker AND a `__file__` that
        # sits inside it. Setting only `_MEIPASS` would leave `__file__` in the source tree, where
        # `parents[4]` resolves fine — the test would pass while exercising nothing.
        # **The depth IS the defect, so the simulated `__file__` must have the REAL depth.** The
        # first draft used the `tempfile` directory itself, which is `/tmp/tmpXXXXXX/_MEI…` — one
        # level deeper than a real bundle, so `parents[4]` resolved to `/` and THE TEST PASSED
        # AGAINST THE UNFIXED CODE. Nothing on this path is opened: `web_dist` only calls
        # `is_dir()` / `exists()`, which are safe on a path that does not exist. So the depth is
        # simulated exactly and the bundle CONTENTS come from the real temp dir via `_MEIPASS`.
        desktop.__file__ = "/tmp/_MEI123456/aec_api/desktop.py"
        sys._MEIPASS = str(meipass)          # noqa: SLF001 — this is what PyInstaller sets
        sys.frozen = True                    # type: ignore[attr-defined]

        raised = None
        try:
            got = desktop.web_dist()
        except IndexError as e:
            raised, got = e, None
        check("web_dist() does not raise in a frozen shallow layout", raised is None,
              f"IndexError: {raised} — this is the crash that stopped the Linux app booting")
        check("...and it returns the BUNDLED web directory", got == str(meipass / "web"),
              f"got {got!r}, wanted {meipass / 'web'}")

        raised2 = None
        try:
            gotm = desktop.modules_dir()
        except IndexError as e:
            raised2, gotm = e, None
        check("modules_dir() does not raise in a frozen shallow layout", raised2 is None,
              f"IndexError: {raised2}")
        check("...and it returns the BUNDLED module catalog", gotm == str(meipass / "modules"),
              f"got {gotm!r}, wanted {meipass / 'modules'}")
    finally:
        desktop.__file__ = REAL_FILE
        for attr in ("_MEIPASS", "frozen"):
            if hasattr(sys, attr):
                delattr(sys, attr)

# --- EACH GUARD SEPARATELY, because either one alone hides the other --------------------------------
# `repo_root()` has two protections: it returns None when frozen, and it bounds-checks the index.
# Against the frozen fixture above, removing EITHER still passes — the frozen guard short-circuits
# before the index, and the index is out of range anyway, so each covers for the other and a mutation
# of one proves nothing. Mutation testing said so: both mutants survived.
#
# So the bounds check gets its own case: NOT frozen, but a `__file__` too shallow for parents[4].
# That is the only configuration where the index is both reached and out of range.
try:
    desktop.__file__ = "/x/desktop.py"          # 2 parents: /x, /
    raised3 = None
    try:
        root_shallow = desktop.repo_root()
    except IndexError as e:
        raised3, root_shallow = e, "raised"
    check("repo_root() bounds-checks the index when NOT frozen and the path is shallow",
          raised3 is None,
          f"IndexError: {raised3} — the frozen guard cannot help here, so the bounds check is the "
          f"only thing standing between a moved file and the crash")
    check("...and it reports 'no checkout' rather than inventing a path",
          root_shallow is None, f"got {root_shallow!r}")
finally:
    desktop.__file__ = REAL_FILE

# --- the source checkout still works: the fix must not trade one break for another -----------------
here = Path(REAL_FILE).resolve()
check("the source checkout is deep enough for the repo-relative walk", len(here.parents) > 4)
check("modules_dir() finds the REAL catalog from a checkout", desktop.modules_dir() is not None,
      "returned None while services/api/modules exists — the repo fallback its docstring "
      "promises does not work, which is the off-by-one recorded above")
md = desktop.modules_dir()
check("...and it is services/api/modules, the path its own comment names",
      md is not None and Path(md).is_dir() and (Path(md) / "rfi" / "module.json").exists(),
      f"got {md!r}")

if FAILED:
    print("\nFAIL test_desktop_paths")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print("test_desktop_paths OK  (frozen shallow layout resolves without raising; source checkout "
      "still finds both trees)")
