"""Where the app's files are — the ONE answer to "how many directories up is the repo root?"

**This exists because counting directories took the shipped Linux app down.** Modules here are
imported from two very different layouts:

    source checkout   services/api/src/aec_api/routers/authoring.py
    frozen bundle     $TMPDIR/_MEIxxxxxx/aec_api/routers/authoring.py

The frozen layout is SHALLOWER — `services/api/src/` collapses away — and on Linux `$TMPDIR`
defaults to `/tmp`, which is one directory below the filesystem root. So a count that is right in a
checkout can run off the top of the filesystem in a bundle, and `Path.parents[N]` does not clamp:
it raises `IndexError`. Three modules did exactly that, two of them at import time, and the
published AppImage and .deb could not start at all.

**A count is the wrong instrument, so nothing here counts.** `repo_root()` walks up looking for the
checkout's shape and returns None when there is not one — which is the honest answer inside a
bundle, where there is no checkout and the files it would have pointed at are packaged elsewhere.
An off-by-one becomes impossible rather than bounds-checked, and a file that moves between
directories keeps working.

**The dead-fallback trap this also closes.** Every caller guards with `.exists()` or `.is_dir()`,
so a wrong path does not raise — it silently returns "not found" and some other default takes over.
Two of the sites converted here had been wrong in the checkout for as long as they had existed
(`aec_api/package.py` asked for `services/api/data/src`; `desktop.py`'s `modules_dir()` asked for
`services/modules`), and nothing was ever red. **A path expression that cannot fail loudly must not
be written twice.**
"""
from __future__ import annotations

import sys
from pathlib import Path


def bundle_dir() -> Path | None:
    """The PyInstaller unpack directory (`sys._MEIPASS`), or None when not frozen.

    Both markers are checked: `sys.frozen` is what PyInstaller sets, `_MEIPASS` is where it
    unpacked. Either alone is enough to mean "there is no source checkout around this file".
    """
    mei = getattr(sys, "_MEIPASS", "")
    if mei:
        return Path(mei)
    return None


def is_frozen() -> bool:
    """Are we running from a packaged one-file build rather than a source checkout?"""
    return bool(getattr(sys, "frozen", False)) or bundle_dir() is not None


# What makes a directory "the root" — the layout every deployment of this code shares. It is
# deliberately NOT `apps/` + `services/`, which is what a checkout looks like: the production API
# image is `/app` holding `services/api/src`, `services/data/src` and `services/converter`, with no
# `apps/` at all. That marker would have returned None in production and quietly turned off IFC
# conversion, which is the sort of thing a directory count gets right by accident and a "better"
# rewrite gets wrong on purpose. Both layouts have this, and a PyInstaller bundle has neither.
_ROOT_MARKER = ("services", "api", "src")


def repo_root(start: str | Path | None = None) -> Path | None:
    """The root the app's sibling directories hang off, or **None** when there is not one.

    A source checkout and the production container image both qualify — see `_ROOT_MARKER`. The
    walk matches the layout's SHAPE rather than counting directories, so it survives a file moving
    between packages, which the counts it replaces did not.

    Returns None when frozen without even walking: inside a bundle every ancestor is a temporary
    directory, and an ancestor that happened to match would be a worse answer than "no root".
    """
    if is_frozen():
        return None
    here = Path(start or __file__).resolve()
    for d in here.parents:
        if d.joinpath(*_ROOT_MARKER).is_dir():
            return d
    return None


def data_src() -> Path | None:
    """`services/data/src` — the monorepo `aec_data` package, importable in a checkout.

    None when frozen: `aec_data` is packaged into the bundle directly, so there is nothing to add
    to `sys.path` and adding a guessed path would only mask that.
    """
    root = repo_root()
    return (root / "services" / "data" / "src") if root else None


def add_data_src_to_path() -> None:
    """Make `aec_data` importable from a checkout. A no-op in a bundle, where it already is.

    Every caller of this used to inline the same three lines with its own directory count, and the
    counts disagreed — which is how one of them ended up pointing at `services/api/data/src`.
    """
    d = data_src()
    if d and str(d) not in sys.path:
        sys.path.insert(0, str(d))


def converter_cli() -> Path | None:
    """`services/converter/src/cli.mjs` — the Node IFC→Fragments converter, or None.

    None means "this install cannot convert", which is the honest answer in a frozen desktop
    bundle: the converter is a Node script that is not packaged and there is no Node runtime to run
    it with. Callers must treat None as *refuse*, never as a path to hand to `subprocess` — a
    stringified None reaches `node` as the literal argument "None".
    """
    root = repo_root()
    return (root / "services" / "converter" / "src" / "cli.mjs") if root else None


def have_converter() -> bool:
    """Is the Node converter actually present? False in a bundle, and in a checkout without it."""
    c = converter_cli()
    return bool(c and c.exists())
