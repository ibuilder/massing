"""The recovered `.frag` layout still matches the `@thatopen/fragments` release we pin.

`aec_data/fragments/schema.py` holds vtable slots and struct strides that were **read out of the
generated FlatBuffers accessors** in the installed package, because no `.fbs` schema ships with it.
That makes the Python converter coupled to a version in a way nothing else here is: a major bump can
move a field and every offset silently addresses the wrong bytes. The file would still be produced,
still decompress, still parse -- and describe a different model.

**CLAUDE.md names this exact coupling** ("@thatopen/components and @thatopen/fragments version
coupling -- pin a compatible pair"), so this re-derives the slots from whatever is installed and
compares them against what the converter believes.

**It fails CLOSED on absence in one direction only, and that asymmetry is deliberate.** The package
lives in `node_modules`, which the API test job does not install -- so "not installed" cannot be a
failure or the gate would red every CI run. What it must never do is *pass quietly*: an absent
package prints a SKIP that names what was not checked. What it does fail on is the pinned VERSION
moving in `apps/web/package.json` while `schema.py` still claims the old one, because that check
needs no `node_modules` at all and is where a drift becomes visible first.

**Mutation-testing this gate needs `PYTHONDONTWRITEBYTECODE=1`, and finding that out cost an hour.**
A mutation of `schema.py` was applied, the gate correctly went red, the file was restored -- and the
gate stayed red, reporting a slot the restored file plainly did not contain. Nothing was wrong with
the restore. CPython validates a cached `.pyc` by comparing the source's mtime **truncated to whole
seconds** and its **byte size**; `"meshes": 18` -> `"meshes": 16` changes neither, and the restore
landed inside the same second as the mutated compile, so the stale bytecode was judged valid and
kept being imported. The file on disk and the imported module genuinely disagreed.

The consequence is not specific to this gate: **a same-second, same-length edit can make a mutation
run lie in either direction** -- a mutation that never loaded reads as a kill, a restore that never
loaded reads as a survivor -- and the false *kill* is the dangerous one, because it is the answer
you were hoping for. Mutate with `PYTHONDONTWRITEBYTECODE=1`, or delete `__pycache__` between runs;
never conclude from a mutation result that the source and the module agreed.

Run: `PYTHONPATH=src:../data/src python test_fragments_schema.py`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(f"{label} — {detail}" if detail else label)


from aec_data.fragments import schema as S  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# --- 1. the pin and the recovered schema name the same release ------------------------------------
pkg_json = REPO / "apps" / "web" / "package.json"
check("apps/web/package.json is readable", pkg_json.exists(), str(pkg_json))
if pkg_json.exists():
    deps = json.loads(pkg_json.read_text())
    pinned = (deps.get("dependencies", {}) | deps.get("devDependencies", {})).get(
        "@thatopen/fragments")
    check("@thatopen/fragments is pinned to an exact version",
          bool(pinned) and re.fullmatch(r"\d+\.\d+\.\d+", pinned or "") is not None,
          f"pinned={pinned!r} — a range makes the schema this converter targets unknowable")
    check("THE PIN AND THE RECOVERED SCHEMA AGREE ON THE VERSION",
          pinned == S.FRAGMENTS_VERSION,
          f"package.json pins {pinned!r}, schema.py was read from {S.FRAGMENTS_VERSION!r} — "
          f"re-derive the slots against the new release before moving this constant, because a "
          f"moved field addresses the wrong bytes and still produces a file that parses")

# --- 2. internal consistency the derivation must satisfy ------------------------------------------
# Cheap, and it catches a fat-fingered edit that no amount of `node_modules` would.
for name, table, count in (("MODEL", S.MODEL, S.MODEL_FIELDS),
                           ("MESHES", S.MESHES, S.MESHES_FIELDS),
                           ("SHELL", S.SHELL, S.SHELL_FIELDS)):
    slots = sorted(table.values())
    check(f"{name}: slots are the FlatBuffers sequence 4, 6, 8, ...",
          slots == list(range(4, 4 + 2 * len(slots), 2)),
          f"{slots} — a vtable slot is `4 + 2*field_index`; a gap means a field was missed and "
          f"every field after it is read from the wrong offset")
    check(f"{name}: the declared field count covers every slot",
          count >= len(table),
          f"{count} declared vs {len(table)} slots — `startObject` must cover them all")

check("struct strides are large enough for their fields",
      S.SAMPLE_STRIDE >= max(S.SAMPLE.values()) + 4
      and S.REPRESENTATION_STRIDE >= S.REPRESENTATION["representation_class"] + 1
      and S.TRANSFORM_STRIDE >= S.TRANSFORM["y_direction"] + S.FLOAT_VECTOR_STRIDE
      and S.MATERIAL_STRIDE >= max(S.MATERIAL.values()) + 1,
      "a stride shorter than its own fields overlaps the next struct in the vector")
check("the shell index ceiling is what a uint16 can address", S.MAX_SHELL_POINTS == 1 << 16,
      f"{S.MAX_SHELL_POINTS} — `ShellProfile.indices` is uint16")

# --- 3. RE-DERIVE from the installed package ------------------------------------------------------
dist = REPO / "node_modules" / "@thatopen" / "fragments" / "dist" / "index.mjs"
if not dist.exists():
    print(f"SKIP  re-derivation from the installed package — {dist} is absent")
    print("      (the version check above still holds; this half needs `node_modules`)")
else:
    src = dist.read_text(encoding="utf8", errors="replace")

    def _slots(cls: str) -> dict[str, int]:
        """Read `name() { ... __offset(this.bb_pos, N) ... }` accessors out of one class body."""
        m = re.search(rf"\nclass {cls} \{{(.*?)\n\}}", src, re.S)
        if not m:
            return {}
        body, out = m.group(1), {}
        for acc in re.finditer(r"\n  ([a-zA-Z][A-Za-z0-9_]*)\((?:[^)]*)\) \{(.*?)\n  \}", body, re.S):
            name, code = acc.group(1), acc.group(2)
            off = re.search(r"__offset\(this\.bb_pos, (\d+)\)", code)
            if off and not name.endswith("Length") and not name.endswith("Array"):
                out.setdefault(name, int(off.group(1)))
        return out

    def _camel(name: str) -> str:
        return re.sub(r"_([a-z])", lambda mm: mm.group(1).upper(), name)

    for cls, table in (("Model", S.MODEL), ("Meshes", S.MESHES), ("Shell", S.SHELL)):
        found = _slots(cls)
        check(f"{cls}: accessors were readable from the installed package", bool(found),
              "no accessors parsed — the package layout changed and this gate is now blind")
        drift = {k: (v, found.get(_camel(k))) for k, v in table.items()
                 if _camel(k) in found and found[_camel(k)] != v}
        check(f"{cls}: EVERY RECOVERED SLOT MATCHES THE INSTALLED PACKAGE", not drift,
              f"{drift} — (ours, theirs); a moved field means the converter writes to the wrong "
              f"offset and produces a file that parses into a different model")
        missing = [k for k in table if _camel(k) not in found]
        check(f"{cls}: every field we rely on still exists", not missing,
              f"gone from the package: {missing}")

if FAILED:
    print("FAIL test_fragments_schema")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
_where = "re-derived against the installed package" if dist.exists() else "package absent — version check only"
print(f"test_fragments_schema OK  (schema recovered from @thatopen/fragments "
      f"{S.FRAGMENTS_VERSION}; {_where})")
