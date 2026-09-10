"""No shipped module may find its files by COUNTING directories up from `__file__`.

WHY THIS EXISTS
    The published v0.3.1133 AppImage and .deb could not start. `aec_api/desktop.py` asked for
    `Path(__file__).resolve().parents[4]` — right in a source checkout, and one past the end inside
    a PyInstaller bundle, where the file sits at `$TMPDIR/_MEIxxxxxx/aec_api/desktop.py` and the
    Linux default `TMPDIR=/tmp` leaves exactly four parents. `Path.parents` does not clamp; it
    raises `IndexError`, and `aec-bim-server` died before binding a port.

    Fixing that ONE file was not a fix. Run against `origin/main` at the time, this gate reports
    **16 sites across 12 files**: 3 that raise, 12 that quietly leave the bundle, 1 that is fine.
    Two of the three raisers do it at IMPORT rather than inside a function — so even with
    `desktop.py` corrected, the Linux app would have died one line later, in `routers/authoring.py`,
    with the same class of traceback under a different filename:

        aec_api/desktop.py:38                parents[4]  (max index 3)  function
        aec_api/plugin_registry.py:44        parents[4]  (max index 3)  function
        aec_api/routers/authoring.py:45      parents[5]  (max index 4)  MODULE LEVEL

    **A crash found by running the app tells you where it stopped, not how many places are wrong.**
    The first traceback is a sample of the population, and this gate is the population.

    *(The first draft of this docstring said "six sites in three files". That was measured against a
    half-converted working tree rather than against `main`, and it was wrong in the direction that
    made the sweep look smaller and tidier than it was. The numbers above come from running this
    file's own analyser over `git archive origin/main` — which is the only way to state them, and
    the reason they are stated with a ref attached.)*

WHAT IT CHECKS, AND WHY IT IS ABOUT SHAPE RATHER THAN DEPTH
    For every tracked `.py` under the roots the `.spec` files bundle, it walks the AST for
    `<...>.parents[N]`, maps the file to the path it would have inside a bundle, and sorts each site
    into one of three verdicts:

        raises    `N` is past the end. `IndexError`, no app.
        escapes   `N` is in range but reaches ABOVE the bundle root, so in a frozen build it names
                  whatever temporary directory the bundle happens to sit in.
        local     `N` stays within the bundle — the module's own directory, its package, or the
                  bundle root. Those exist in both layouts and mean the same thing in each, so this
                  one passes.

    `escapes` is the quiet half, and it was four times larger than the loud one. Every caller guards
    with `.exists()` / `.is_dir()`, so a wrong path does not raise — it returns "not found" and some
    other default answers instead. Two of the twelve had been wrong in the CHECKOUT for as long as
    they had existed:

        aec_api/package.py         parents[2] / "data" / "src"  ->  services/api/data/src
        aec_api/desktop.py         parents[3] / "modules"       ->  services/modules

    Neither directory has ever existed. Nothing was ever red, and one sat under a comment naming the
    path it did not build. **A path expression that cannot fail loudly is one that must not be
    written by hand**; `apppaths.repo_root()` finds the checkout by its shape and returns None when
    there is not one.

TWO THINGS THIS GATE DOES TO ITSELF
    1. **It runs against the pre-fix source before it may report anything.** `test_seeding_sweep`
       learned this the expensive way: its first draft derived a population, missed a known
       instance, and printed a clean tree. Six shipped shapes are embedded below as fixtures --
       three raisers, two escapers and one that is legitimately fine -- and the analyser must
       reach all six AND classify each the way the crash did, or this file fails without
       looking at the tree at all. The `local` fixture is there so no verdict is an untested
       branch: a classifier with an unreachable arm is one nobody has checked.
    2. **The verdict function is separate from the finder**, so a mutation can be aimed at the
       classification directly. `test_unique_read_guard`'s first draft asserted only that its
       analyser still REPORTED a site, so a mutation routing every site to "safe" passed. Reporting
       a site and judging it are different questions.

WHAT IT DOES NOT CHECK
    That the paths are *correct* — only that they are not computed by counting. `repo_root()`
    returning the wrong directory would pass here and fail in `test_desktop_paths.py`, which
    exercises the resolved values against a simulated frozen layout. Two gates, two questions.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

def _specs() -> tuple[str, ...]:
    """Every PyInstaller spec git tracks — **derived, because a listed pair is a population.**

    This was a literal two-tuple, which is precisely the shape that let a mutation past this file's
    other population check: a third spec (a new artifact, a platform variant) would bundle roots
    nobody here scans, and the gate would report a clean tree with no sign it had stopped looking.
    Returns exactly the same two files today; the difference is that adding a third changes it.
    """
    out = subprocess.run(["git", "ls-files", "*.spec"], cwd=REPO, capture_output=True, text=True,
                         check=True)
    found = tuple(sorted(p for p in out.stdout.split("\n") if p.strip()))
    if not found:
        raise AssertionError("no .spec files tracked; the bundled population cannot be derived")
    return found


def bundled_roots() -> tuple[str, ...]:
    """The source roots PyInstaller packages — **read out of the .spec files, not listed here.**

    A file under one of these lands in the bundle at its path relative to that root, so
    `services/api/src/aec_api/routers/x.py` becomes `<_MEIPASS>/aec_api/routers/x.py`. Confirmed
    against the shipped v0.3.1133 bundle, whose `_MEIPASS` holds `aec_api/` and `aec_data/` at the
    top level.

    **A hard-coded pair here was a live blind spot, and a mutation proved it.** Dropping
    `services/data/src/` from a literal tuple passed every assertion in this file, because that
    package happens to have no offending site today — the narrowed scan and the full scan agreed,
    so the narrowing was invisible in the output. Deriving from `pathex` means the population can
    only go stale by the BUILD changing, and then it changes here too. Same argument as
    `test_ruff_scope.py`, which parses `ci.yml` for the ruff command rather than restating it.
    """
    roots: list[str] = []
    for spec in _specs():
        path = REPO / spec
        if not path.is_file():
            raise AssertionError(f"{spec} is missing; the bundled population cannot be derived")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = _literal_paths(tree, path.parent)
        for node in ast.walk(tree):
            # (a) `pathex=[...]` -- the source roots PyInstaller searches
            if isinstance(node, ast.keyword) and node.arg == "pathex":
                for el in getattr(node.value, "elts", []):
                    resolved = _resolve(el, path.parent, names)
                    if resolved is None:
                        raise AssertionError(
                            f"{spec}: cannot resolve a pathex entry ({ast.dump(el)[:80]}). This "
                            "gate fails CLOSED rather than scanning a population it cannot vouch "
                            "for.")
                    roots.append(resolved.resolve().relative_to(REPO).as_posix() + "/")
            # (b) `collect_all("pkg")` / `collect_submodules("pkg")` -- a SECOND way in, and the
            #     one a mutation used to slip past this gate: dropping `aec_data` from `pathex`
            #     while `collect_submodules("aec_data")` kept bundling it narrowed the scan without
            #     narrowing the artifact. `pathex` alone is not what gets shipped.
            if isinstance(node, ast.Call):
                fn = node.func
                fname = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
                if fname in ("collect_all", "collect_submodules") and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        r = _first_party_root(arg.value)
                        if r:
                            roots.append(r)
    return tuple(sorted(set(roots)))


def _first_party_root(pkg: str) -> str | None:
    """The tracked source root holding `pkg`, or None when it is a third-party dependency.

    Third-party packages are bundled too, but they are somebody else's code: this gate is about
    what THIS repository writes, and a vendored dependency counting directories is not a defect we
    can fix here.
    """
    for candidate in sorted(REPO.glob("services/*/src")):
        if (candidate / pkg / "__init__.py").is_file():
            return candidate.relative_to(REPO).as_posix() + "/"
    return None


def _literal_paths(tree: ast.AST, spec_dir: Path) -> dict[str, Path]:
    """Module-level `NAME = os.path.join(...)` / string bindings a `pathex` entry may refer to."""
    out: dict[str, Path] = {"SPECPATH": spec_dir, "HERE": spec_dir}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        val = _resolve(node.value, spec_dir, out)
        if val is not None:
            out[node.targets[0].id] = val
    return out


def _resolve(node: ast.AST, spec_dir: Path, names: dict[str, Path]) -> Path | None:
    """A spec expression as a path, or None when it is not one this gate can vouch for."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return spec_dir / node.value
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Call):
        fn = node.func
        attr = fn.attr if isinstance(fn, ast.Attribute) else ""
        if attr in ("join", "abspath"):
            parts = [_resolve(a, spec_dir, names) if isinstance(a, ast.Name)
                     else (a.value if isinstance(a, ast.Constant) else None)
                     for a in node.args]
            if any(p is None for p in parts):
                return None
            base = parts[0] if isinstance(parts[0], Path) else spec_dir / str(parts[0])
            for p in parts[1:]:
                base = base / str(p)
            return base
    return None


BUNDLED_ROOTS = bundled_roots()

# The shallowest real frozen layout: Linux's default TMPDIR is /tmp, one directory below the root.
# macOS (/var/folders/xx/yyyy/T) and Windows (C:\Users\...\AppData\Local\Temp) are eight deep, which
# is exactly why this shipped — the two platforms anyone tested on could not reproduce it.
SHALLOWEST_TMPDIR = "/tmp"

# **There is no exemption list, and there was no need for one.** An earlier draft exempted
# `apppaths.py` as "the module allowed to reason about layout" -- but it reasons by WALKING
# (`for d in here.parents`), which is not a subscript and which this finder therefore never saw.
# The exemption excluded nothing, and a standing exemption for a file that needs none is an
# invitation: it would have let `apppaths` itself start counting, silently, in the one module whose
# entire purpose is not to.


def _tracked_py() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO, capture_output=True, text=True,
                         check=True)
    return [p for p in out.stdout.split("\n") if p.startswith(BUNDLED_ROOTS)]


def frozen_path(repo_rel: str) -> str | None:
    """Where `repo_rel` lives inside a one-file bundle unpacked under the shallowest TMPDIR."""
    for root in BUNDLED_ROOTS:
        if repo_rel.startswith(root):
            return f"{SHALLOWEST_TMPDIR}/_MEI123456/{repo_rel[len(root):]}"
    return None


def parent_index_sites(src: str) -> list[tuple[int, int | None]]:
    """Every `<...>.parents[i]` in `src`, as (line, index) — **`None` index means unresolved.**

    Structural rather than textual: a regex would also match the prose in this file's own
    docstring, which is how a doc gate in this repository failed once.

    **Three shapes were invisible to the first version, and invisible reads as clean** — the same
    defect this whole change is about, one level up, in the instrument built to forbid it:

        ps = p.parents; ps[5]      an ALIAS. The subscript's value is a Name, not `.parents`.
        p.parents[N]               a NON-LITERAL index. Skipped silently, while the docstring
                                   claimed this gate fails closed.
        p.parents[-1]              a NEGATIVE literal. Python parses `-1` as
                                   `UnaryOp(USub, Constant(1))`, NOT `Constant(-1)`, so an
                                   `isinstance(idx, ast.Constant)` test does not match it.

    That last one is worth its own sentence: it was predicted to be CAUGHT, by reasoning about
    what `parents[-1]` resolves to, and measurement said otherwise. The prediction was about the
    runtime value; the bug was in the parse. **Reasoning about behaviour cannot find a hole in the
    thing that decides what you look at** — only running the analyser over the shape can.

    Unresolvable indexes are now returned as `None` and classified as `unknown`, which fails the
    build. A site this analyser cannot read is not a site it may wave through.
    """
    tree = ast.parse(src)

    # `x = <anything>.parents` -- the alias form. Collected first so a later subscript on `x`
    # resolves, regardless of statement order within the module.
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) \
                and node.value.attr == "parents":
            aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
            aliases.add(node.target.id)

    found: list[tuple[int, int | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        val = node.value
        is_parents = (isinstance(val, ast.Attribute) and val.attr == "parents") \
            or (isinstance(val, ast.Name) and val.id in aliases)
        if not is_parents:
            continue
        found.append((node.lineno, _index_of(node.slice)))
    return found


def _index_of(idx: ast.AST) -> int | None:
    """The integer a subscript names, or None when this analyser cannot say.

    Handles the negative literal explicitly, because the AST does not: `-1` is a `UnaryOp` wrapping
    `Constant(1)`. A slice, a variable, an expression -- anything else -- is None, and None fails.
    """
    if isinstance(idx, ast.Constant) and isinstance(idx.value, int) \
            and not isinstance(idx.value, bool):
        return idx.value
    if isinstance(idx, ast.UnaryOp) and isinstance(idx.op, ast.USub) \
            and isinstance(idx.operand, ast.Constant) and isinstance(idx.operand.value, int):
        return -idx.operand.value
    return None


def verdict(repo_rel: str, n: int | None) -> str:
    """`raises` | `escapes` | `local` | `unknown` — SEPARATE from the finder so a mutation can
    target the classification directly.

    The rule is derived from the module's own position, not from a list of allowed files:

        local     `n` stays within the bundle — the module's own directory, its package, or the
                  bundle root. Those exist in both layouts and mean the same thing in each.
        escapes   `n` is in range but reaches ABOVE the bundle root, so in a frozen build it names
                  whatever temporary directory the bundle happens to sit in. Harmless-looking
                  (every caller guards with `.exists()`) and therefore the quiet half of this
                  defect: it silently finds nothing, and some other default answers instead.
        raises    `n` is past the end of `parents` entirely. `IndexError`, no app.
        unknown   this analyser could not read the index. **Fails the build**, because the
                  alternative is a site nobody looked at being reported as a site that is fine.

    A NEGATIVE index counts from the filesystem root rather than from the file, so it names a
    different directory in each layout by construction — never in-bundle, hence `escapes`.

    Severity runs `local` < `escapes` < `raises`, but the FIX is the same for the last two, which
    is why both fail: a directory count that is right in a checkout is not right in a bundle, and
    guarding it only converts a crash into a silence.
    """
    if n is None:
        return "unknown"
    fp = frozen_path(repo_rel)
    if fp is None:
        return "escapes"
    parents = Path(fp).parents
    if n < 0:
        return "escapes"
    if n > len(parents) - 1:
        return "raises"
    # The bundle root is `<...>/_MEI123456`; anything at or below it is in-bundle.
    return "local" if str(parents[n]).count("_MEI123456") else "escapes"


# --- the analyser must find the real defects before it may report on the tree ------------------
# Verbatim shapes from the three files as they stood at v0.3.1133, with the path each was in.
_PRE_FIX = [
    ("services/api/src/aec_api/desktop.py",
     'candidates.append(Path(__file__).resolve().parents[4] / "apps" / "web" / "dist")', "raises"),
    ("services/api/src/aec_api/plugin_registry.py",
     'default = Path(__file__).resolve().parents[4] / "plugins"', "raises"),
    ("services/api/src/aec_api/routers/authoring.py",
     '_REPO = Path(__file__).resolve().parents[5]', "raises"),
    # **The three shapes the first version could not see at all**, each reported as no site rather
    # than as a site -- which is why they are fixtures and not a comment. Found by review, then
    # confirmed by running the analyser over them: `parent_index_sites` returned `[]` for all three.
    ("services/api/src/aec_api/routers/authoring.py",
     "ps = Path(__file__).resolve().parents\nps[5]", "raises"),          # alias
    ("services/api/src/aec_api/routers/authoring.py",
     "N = 5\nPath(__file__).resolve().parents[N]", "unknown"),           # non-literal -> FAILS
    ("services/api/src/aec_api/routers/authoring.py",
     "Path(__file__).resolve().parents[-1]", "escapes"),                 # negative literal
    # In range in a bundle, and WRONG in the checkout it was written for -- the quiet half.
    ("services/api/src/aec_api/package.py",
     '_DS = Path(__file__).resolve().parents[2] / "data" / "src"', "escapes"),
    ("services/api/src/aec_api/routers/exports.py",
     '_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"', "escapes"),
    # And one that is FINE, so the third verdict is not an untested branch: the plugin host is
    # spawned with the package's parent as cwd, which is `src/` in a checkout and the bundle root
    # in a frozen build -- the same directory by meaning in both.
    ("services/api/src/aec_api/plugin_registry.py",
     'cwd=str(Path(__file__).resolve().parents[1])', "local"),
]

FAILURES: list[str] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    # 1. self-test: the analyser sees the shipped defects, at the right severity
    seen = []
    for rel, snippet, want in _PRE_FIX:
        sites = parent_index_sites(snippet)
        if len(sites) != 1:
            check(False, "the analyser parses each pre-fix shape", f"{rel}: {snippet!r} -> {sites}")
            continue
        got = verdict(rel, sites[0][1])
        seen.append((rel, sites[0][1], got, want))
    check(len(seen) == len(_PRE_FIX), "the analyser reaches every pre-fix shape",
          f"{len(seen)} of {len(_PRE_FIX)}")
    wrong = [s for s in seen if s[2] != s[3]]
    check(not wrong, "...and classifies each one the way the crash did",
          "; ".join(f"{r} parents[{n}] -> {g}, expected {w}" for r, n, g, w in wrong)
          or ", ".join(f"{v}={sum(1 for s in seen if s[2] == v)}"
                       for v in ("raises", "escapes", "local", "unknown")))
    if FAILURES:
        print("\nThe analyser cannot see its own motivating defects, so its verdict on the tree "
              "means nothing. Refusing to report.")
        return 1

    # 2. the tree
    files = _tracked_py()
    check(len(files) > 200, "the scan found the bundled source", f"{len(files)} tracked .py")

    # ...and that it reaches EVERY bundled root, not just the one that happened to be broken.
    # A mutation dropping `services/data/src/` from BUNDLED_ROOTS passed every other assertion here,
    # because the tree has no offending site in that package TODAY -- so the narrowed scan and the
    # full scan agreed, and the narrowing was invisible in the output. That is this file's own
    # subject matter one level up: a predicate deciding what to LOOK at hides its own misses, and
    # "no findings" is exactly what a scan of nothing reports.
    per_root = {r: sum(1 for f in files if f.startswith(r)) for r in BUNDLED_ROOTS}
    empty = [r for r, c in per_root.items() if c == 0]
    check(not empty, "...and every root the .spec files bundle contributes files",
          f"no tracked .py under {empty}" if empty
          else " · ".join(f"{r}={c}" for r, c in per_root.items()))

    raises, escapes, local, unknown = [], [], [], []
    buckets = {"raises": raises, "escapes": escapes, "local": local, "unknown": unknown}
    for rel in files:
        src = (REPO / rel).read_text(encoding="utf-8")
        for line, n in parent_index_sites(src):
            shown = "?" if n is None else n
            buckets[verdict(rel, n)].append(f"{rel}:{line} parents[{shown}]")

    check(not raises, "no shipped module indexes past the end in a frozen bundle",
          "\n      " + "\n      ".join(raises) if raises
          else f"checked {len(files)} file(s)")
    check(not unknown, "...and every parents[] index is one this analyser can actually read",
          "\n      " + "\n      ".join(unknown)
          + "\n      An index this gate cannot resolve is not an index it may wave through: the "
            "site would be reported as absent, which is indistinguishable from being fine. Use a "
            "literal, or aec_api.apppaths."
          if unknown else "0 unresolvable indexes")

    check(not escapes, "...and none reaches above the bundle root to find repo files",
          "\n      " + "\n      ".join(escapes)
          + "\n      Use aec_api.apppaths (repo_root / data_src / bundle_dir / converter_cli): it "
            "matches the checkout's SHAPE, so it cannot be off by one, it survives a file move, "
            "and it answers None in a bundle instead of naming a temp directory."
          if escapes else f"{len(local)} in-bundle parents[] use(s), 0 escaping, 0 exemptions")

    print("\ntest_frozen_paths " + ("OK" if not FAILURES else "FAILED"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
