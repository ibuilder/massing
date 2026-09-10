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

import os
import shutil
import subprocess
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


import test_frozen_paths as _frozen_gate  # noqa: E402
from aec_api import apppaths, desktop  # noqa: E402

REPO = _frozen_gate.REPO

REAL_FILE = desktop.__file__
REAL_APPPATHS = apppaths.__file__

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
# `repo_root()` had two protections: it returned None when frozen, and it bounds-checked the index.
# Against the frozen fixture above, removing EITHER still passed — the frozen guard short-circuits
# before the index, and the index was out of range anyway, so each covered for the other and a
# mutation of one proved nothing. Mutation testing said so: both mutants survived.
#
# **The count is now gone entirely**, which is the better answer to that: `apppaths.repo_root()`
# walks up to the repository's SHAPE (an ancestor holding both `apps/` and `services/`) and there is
# no index left to be off by one. So the case below no longer asks "is the index bounds-checked" —
# it asks the question that survives the rewrite: *outside a checkout, does it say so?* A walk that
# finds nothing must report nothing rather than returning the last directory it looked at.
#
# It patches `apppaths.__file__`, not `desktop.__file__`: the walk starts from the module that owns
# the answer, so every caller in the package gets ONE root instead of each deriving its own. That
# consolidation is the point, and a test that patched the caller would be testing the old design.
try:
    apppaths.__file__ = "/x/apppaths.py"        # 2 parents: /x, /  — no apps/ + services/ above
    raised3 = None
    try:
        root_shallow = desktop.repo_root()
    except IndexError as e:
        raised3, root_shallow = e, "raised"
    check("repo_root() does not raise when there is no checkout above it",
          raised3 is None,
          f"IndexError: {raised3} — a path expression that raises is exactly what took the shipped "
          f"app down; walking off the top must be an answer, not an exception")
    check("...and it reports 'no checkout' rather than inventing a path",
          root_shallow is None, f"got {root_shallow!r}")
finally:
    apppaths.__file__ = REAL_APPPATHS

# --- THE WHOLE APP, IMPORTED FROM A SIMULATED BUNDLE ------------------------------------------------
# Everything above tests path helpers. This tests the thing anyone actually cares about: **does the
# packaged application import at all?** The static gate (`test_frozen_paths.py`) forbids the one
# expression that broke it, which is a ratchet, not a proof -- an import-time crash can come from
# anything, and the first two came from a shape nobody had thought to forbid either.
#
# So: copy the source roots the `.spec` files bundle into a directory named like a PyInstaller
# unpack dir, set `sys.frozen` + `sys._MEIPASS` the way PyInstaller does, and import `aec_api.main`
# in a subprocess. 618 files, ~15 MB, ~6 s.
#
# Measured against `git archive origin/main`, this fixture reproduces the SECOND crash exactly --
#
#     File "aec_api/routers/authoring.py", line 45, in <module>
#         _REPO = Path(__file__).resolve().parents[5]
#     IndexError: 5
#
# -- which is the one that would have been left behind by fixing `desktop.py` alone, and which no
# amount of testing `desktop.py` could have found.
_CHILD = r"""
import os, sys, traceback
MEI = sys.argv[1]
sys.frozen = True                       # what PyInstaller sets
sys._MEIPASS = MEI                      # where it unpacked
sys.path.insert(0, MEI)
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(MEI, "sim.db")
os.environ["STORAGE_DIR"] = os.path.join(MEI, "storage")
os.environ["IFC_DIR"] = os.path.join(MEI, "ifc")
os.environ["AEC_LOCAL_MODE"] = "1"
os.environ["AEC_MODULES_DIR"] = os.path.join(MEI, "modules")
try:
    import aec_api.main                 # noqa: F401
except Exception:
    traceback.print_exc()
    sys.exit(1)
sys.exit(0)
"""

# **The bundle directory goes straight into the system temp root, NOT inside a TemporaryDirectory.**
# `tempfile.mkdtemp()` hands back `/tmp/tmpXXXXXX`, so a bundle nested inside it sits one level
# deeper than a real one -- and one level is the entire defect. The FIRST draft of this fixture did
# exactly that, and the self-test below caught it: the shipped `parents[5]` was still in range, so a
# mutation that should have reproduced the crash imported cleanly. That is the third time this trap
# has appeared in this file's history; it is not subtle in hindsight and it is invisible in the
# moment, because a passing test and a test that cannot fail look identical.
_tmproot = Path(tempfile.gettempdir())
mei = _tmproot / f"_MEI{os.getpid():06d}"
shutil.rmtree(mei, ignore_errors=True)
mei.mkdir(parents=True)
try:
    for root in _frozen_gate.BUNDLED_ROOTS:          # derived from the .spec files, not listed here
        src = REPO / root
        if src.is_dir():
            shutil.copytree(src, mei, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    mods = REPO / "services" / "api" / "modules"
    if mods.is_dir():
        shutil.copytree(mods, mei / "modules", dirs_exist_ok=True)

    # The fixture is only meaningful if NO ancestor looks like a checkout -- otherwise `repo_root()`
    # would find one and the frozen path would never be taken. Assert it rather than assume it.
    rooted = [d for d in mei.parents if (d / "services" / "api" / "src").is_dir()]
    check("the simulated bundle has no checkout above it", not rooted,
          f"an ancestor looks like a source root: {rooted[:1]}")

    script = mei.parent / f"boot{os.getpid()}.py"
    script.write_text(_CHILD, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script), str(mei)],
                          capture_output=True, text=True, timeout=300)
    check("the whole app imports from a frozen bundle layout", proc.returncode == 0,
          "\n      " + "\n      ".join((proc.stderr or "").strip().splitlines()[-6:]))
    # Depth is what made the shipped crash reachable, so report the depth of the MODULE, not of
    # the bundle directory. The wrong version of this line printed the directory's depth, which is
    # right by one and reads as correct -- the number that decides the outcome is this one.
    _probe = mei / "aec_api" / "routers" / "authoring.py"
    print(f"      (deepest module has {len(_probe.parents) - 1} parent indices; "
          f"the shipped Linux layout has 4, and the expression that crashed asked for [5])")

    # **And prove the fixture can FAIL.** A green import proves nothing unless this arrangement is
    # capable of catching the defect it was built for -- the mistake `test_seeding_sweep` made when
    # its first draft derived a population and reported a clean tree. So put the shipped expression
    # back, into the COPY, and require the import to break. Done inside the fixture rather than
    # against `origin/main` so it needs no git ref and works in a shallow CI clone.
    # **INJECT the shipped shape; do not replace an existing line.** The first version of this
    # mutation swapped out `_REPO = repo_root()` in the copied file -- and the very next commit
    # deleted that constant as dead, so the anchor vanished and this self-test reported itself
    # blind. It failed loudly, which is the design, but an anchor that is any particular line of
    # production code is an anchor that ordinary refactoring removes. A self-contained statement
    # inserted at module level depends on nothing but the module being imported at all.
    victim = mei / "aec_api" / "routers" / "authoring.py"
    good = victim.read_text(encoding="utf-8")
    lines = good.splitlines(keepends=True)
    at = next((i + 1 for i, ln in enumerate(lines) if ln.startswith("from __future__")), 0)
    shipped_shape = ("import pathlib as _mut_pathlib\n"
                     "_MUT_REPO = _mut_pathlib.Path(__file__).resolve().parents[5]\n")
    victim.write_text("".join(lines[:at]) + shipped_shape + "".join(lines[at:]), encoding="utf-8")
    broke = subprocess.run([sys.executable, str(script), str(mei)],
                           capture_output=True, text=True, timeout=300)
    check("...and the same fixture catches the shipped defect when it is put back",
          broke.returncode != 0 and "IndexError" in (broke.stderr or ""),
          f"exit={broke.returncode}; the fixture imported an app whose module level asks for "
          f"parents[5] -- it is not deep enough, or not frozen enough, to reproduce what shipped")
    victim.write_text(good, encoding="utf-8")
finally:
    shutil.rmtree(mei, ignore_errors=True)
    (_tmproot / f"boot{os.getpid()}.py").unlink(missing_ok=True)

# --- EVERY DEPLOYMENT LAYOUT, not just the two anyone was thinking about ---------------------------
# `repo_root()` matches the layout's shape, and the FIRST shape chosen was `apps/` + `services/` --
# what a git checkout looks like. The production API image is not a checkout: `services/api/Dockerfile`
# copies `services/api/src`, `services/data/src`, `services/api/modules` and `services/converter` into
# `/app`, and copies no `apps/` at all. That marker would have returned None there and silently turned
# OFF IFC->Fragments conversion, because `converter_cli()` answers None when there is no root.
#
# **The directory count it replaced got that case right by accident** -- `parents[4]` from
# `/app/services/api/src/aec_api/routers/convert.py` is `/app` -- so the "better" rewrite would have
# been a production regression the original bug never was. A rewrite has to clear the bar the thing it
# replaces already cleared, including the parts nobody wrote down.
#
# So both real layouts are asserted here, built as directory trees rather than described in prose.
for label, marker_dirs, expect_root in (
    ("a git checkout", ("apps/web", "services/api/src/aec_api", "services/data/src", "docs"), True),
    ("the production API image", ("services/api/src/aec_api", "services/data/src",
                                  "services/converter/src", "services/api/modules"), True),
    ("neither (a bare package copy)", ("aec_api",), False),
):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "root"
        for d in marker_dirs:
            (root / d).mkdir(parents=True, exist_ok=True)
        probe = root / "services" / "api" / "src" / "aec_api" / "apppaths.py"
        if not probe.parent.is_dir():
            probe = root / "aec_api" / "apppaths.py"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("", encoding="utf-8")
        got = apppaths.repo_root(probe)
        check(f"repo_root() finds the root in {label}",
              (got == root) if expect_root else (got is None),
              f"got {got!r}, expected {root if expect_root else None}")

# --- THE SECOND ROOT-FINDER MUST AGREE WITH THE FIRST -----------------------------------------------
# `aec_data.build_family_library._checkout_root` is a deliberate small duplicate of
# `apppaths.repo_root`: `aec_data` must not import `aec_api`, and a shared helper would invert the
# layering to save six lines. A duplicate is fine; a duplicate that DRIFTS is not, and this one
# drifted the moment it was written -- its first draft matched `apps/` + `services/` (a git
# checkout) while `apppaths` deliberately does not, because the production API image is `/app` with
# `services/` and no `apps/`. Both docstrings said they agreed. Only one of them was right.
#
# So the agreement is asserted rather than described, over the same layouts as above.
from aec_data import build_family_library as _bfl  # noqa: E402

for _label, _dirs in (
    ("a git checkout", ("apps/web", "services/api/src/aec_api", "services/data/src", "docs")),
    ("the production API image", ("services/api/src/aec_api", "services/data/src",
                                  "services/converter/src", "services/api/modules")),
    ("neither (a bare package copy)", ("aec_data",)),
):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "root"
        for d in _dirs:
            (root / d).mkdir(parents=True, exist_ok=True)
        a_probe = root / "services" / "api" / "src" / "aec_api" / "apppaths.py"
        b_probe = root / "services" / "data" / "src" / "aec_data" / "build_family_library.py"
        for probe in (a_probe, b_probe):
            probe.parent.mkdir(parents=True, exist_ok=True)
            probe.write_text("", encoding="utf-8")
        a = apppaths.repo_root(a_probe)
        # `_checkout_root` takes no argument, so exercise its RULE against the same tree the way it
        # walks -- reading the rule out of the function keeps this from re-stating it a third time.
        b = next((d for d in b_probe.resolve().parents if (d / "services" / "api" / "src").is_dir()),
                 None)
        check(f"both root-finders agree in {_label}", a == b, f"apppaths={a!r} vs aec_data={b!r}")

# ...and that the rule asserted just above is the one `_checkout_root` actually runs. Reading the
# source is the only way to check a zero-argument function's marker without a checkout to move.
_bfl_src = Path(_bfl.__file__).read_text(encoding="utf-8")
check("...and aec_data's own marker is `services/api/src`, not the checkout-only one",
      '(d / "services" / "api" / "src").is_dir()' in _bfl_src
      and '(d / "apps").is_dir()' not in _bfl_src,
      "build_family_library._checkout_root no longer matches apppaths._ROOT_MARKER; the two "
      "root-finders have drifted apart again")

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
