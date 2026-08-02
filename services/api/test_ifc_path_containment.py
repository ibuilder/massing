"""Nothing may build a path under `_IFC_DIR` without the containment barrier.

One site was fixed for a CodeQL HIGH. The same pattern then turned up at seven more that CodeQL had
never alerted on — **it flags what changed, not everything it matches**, so "CodeQL is clean" means
clean on recent diffs. That is the gate-scope lesson again, and the reason this check enumerates the
package instead of trusting an alert list.

Seven of the eight were defended in practice: they read `_IFC_DIR / safe_seg(pid) / …`, and
`safe_seg` rejects a traversing id. They were missing the belt, not the braces.

The eighth was not. `bundle.import_bundle` built its destination from `source_ifc` **read out of the
uploaded container's own project.json** — attacker-controlled, as is the zip entry name that must
match it — with no `safe_seg` anywhere:

    dest = _IFC_DIR / f"{new_pid}_{ifc_name}"
    dest.write_bytes(z.read(f"geometry/{ifc_name}"))

The `{new_pid}_` prefix looks protective and is not. It only makes the first `..` part of a literal
directory name; the segments after it still walk up, so a name carrying enough of them resolves
outside `_IFC_DIR` and the write lands there with attacker-chosen bytes. Prefixing changes the depth
required and nothing else. Confirmed end to end against the real function before fixing — the import
returned success while the file appeared outside the directory — and confirmed refused after.

**Why the barrier is resolve-then-test, not string inspection.** Whether a path escapes is a fact
about where it lands, and only resolution answers that. Every string-level rule (does it start with
`/`, does it contain `..`) is a proxy, and the prefix case above is exactly the input that makes a
plausible proxy wrong: the dangerous string does not begin with `..` and its first segment is not
`..` either.

Two rules, both mutation-verified:

  1. no module may join `_IFC_DIR` with anything except through `contained_path`/`_ifc_path`
     — the ninth site cannot appear quietly
  2. `contained_path` itself refuses an escape and permits a legitimate name — asserted at the
     boundary, including the prefixed shape, so the guard cannot be hollowed into a `..` substring
     test and still pass

Pure AST plus direct calls: no DB, no TestClient, no network, and no file is written outside a
temporary directory.
"""
import ast
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from aec_api import storage  # noqa: E402

SRC = pathlib.Path(__file__).parent / "src" / "aec_api"
SAFE_CALLS = {"contained_path", "_ifc_path"}
# reading the base itself is not building a path under it
SAFE_ATTRS = {"mkdir", "resolve", "exists", "is_dir", "iterdir", "glob", "rglob"}

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def raw_joins(sources: dict | None = None) -> list:
    """Sites that join `_IFC_DIR` without the barrier. Injectable so each rule can be driven red."""
    if sources is None:
        sources = {p.stem: p.read_text(encoding="utf-8", errors="replace")
                   for p in sorted(SRC.rglob("*.py"))}
    problems = []
    for mod, src in sources.items():
        if "_IFC_DIR" not in src:
            continue
        tree = ast.parse(src)
        # the helpers are allowed to touch it — they ARE the barrier
        helper_spans = {(f.lineno, f.end_lineno) for f in ast.walk(tree)
                        if isinstance(f, ast.FunctionDef) and f.name in SAFE_CALLS}

        def inside_helper(node, spans=helper_spans):   # bind per-iteration, not by closure (B023)
            ln = getattr(node, "lineno", None)
            return ln is not None and any(a <= ln <= b for a, b in spans)

        for node in ast.walk(tree):
            if inside_helper(node):
                continue
            # _IFC_DIR / <anything>
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
                    and isinstance(node.left, ast.Name) and node.left.id == "_IFC_DIR"):
                problems.append(f"{mod}:{node.lineno} joins _IFC_DIR with `/` — use the barrier")
            # _IFC_DIR.joinpath(...) and friends
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "_IFC_DIR"
                    and node.func.attr not in SAFE_ATTRS):
                problems.append(f"{mod}:{node.lineno} calls _IFC_DIR.{node.func.attr}() — use the barrier")
    return problems


live = raw_joins()
check("no module builds an _IFC_DIR path outside the barrier", not live, "; ".join(live))

# the query must actually be looking at something
corpus = [p for p in SRC.rglob("*.py") if "_IFC_DIR" in p.read_text(encoding="utf-8", errors="replace")]
check("and the scan reaches the modules that use _IFC_DIR", len(corpus) >= 3,
      ", ".join(sorted(p.stem for p in corpus)))

# --- rule 1 must go red -------------------------------------------------------------
check("fires on a `/` join", len(raw_joins({"m": 'p = _IFC_DIR / name\n'})) == 1)
check("fires on .joinpath()", len(raw_joins({"m": '_IFC_DIR.joinpath(name).mkdir()\n'})) == 1)
check("permits reading the base itself", raw_joins({"m": '_IFC_DIR.mkdir(parents=True)\n'}) == [])
check("permits the barrier call", raw_joins({"m": 'p = contained_path(_IFC_DIR, name)\n'}) == [])
check("permits the helper's own definition",
      raw_joins({"m": 'def _ifc_path(pid):\n    return _IFC_DIR / pid\n'}) == [])

# --- rule 2: the barrier's behaviour, at the boundary --------------------------------
base = pathlib.Path(tempfile.mkdtemp())
(base / "sub").mkdir()


def escapes(*parts) -> bool:
    try:
        storage.contained_path(base, *parts)
        return False
    except ValueError:
        return True


check("refuses a plainly traversing name", escapes("../../../x"))
check("refuses the PREFIXED shape — the one a `..`-substring test gets wrong",
      escapes("abc123_../../../x"),
      "first segment is a literal dir name, not '..'")
check("refuses an absolute path", escapes("/etc/passwd") or escapes("C:\\Windows\\win.ini"))
check("permits an ordinary name", not escapes("model.ifc"))
check("permits a nested legitimate path", not escapes("proj", "models", "a.ifc"))
check("permits a name that merely CONTAINS dots", not escapes("v1..2_model.ifc"))
check("returns a path inside the base",
      storage.contained_path(base, "sub", "a.ifc").is_relative_to(base.resolve()))

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"ifc_path_containment OK — {len(corpus)} module(s) scanned, 0 unguarded joins; "
      f"barrier verified at the boundary incl. the prefixed shape")
