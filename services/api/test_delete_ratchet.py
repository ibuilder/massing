"""R41-DELETE-RATCHET — an extraction sticks, or the god-file quietly re-absorbs what left it.

Several lanes ship to main at once and nothing stopped one of them re-adding a method that another
lane had just extracted. `test_file_sizes.py` covers half of this already, and nobody had labelled it
as such: its `PER_FILE` ceilings mean a decomposed file cannot grow *back* past its pin. That is a
real delete ratchet and it is live — `client.ts` is pinned at 3,780 after the design-options
extraction, mutation-checked.

**A size ceiling cannot see the failure that actually happens here.** Re-adding one method to
`client.ts` while the mixin still defines it costs a handful of lines, passes the pin comfortably, and
produces a *shadow*: two definitions of the same name, where the one that wins is decided by the mixin
composition order in `class ApiClient extends withAuth(withProforma(withDesignOptions(...)))`. Every
call site still resolves, nothing fails to compile, and the extraction is silently undone. That is the
"re-export that reads as a dead import" the entry names.

**Derived, not enumerated.** There is no list of protected symbols here, because a list only protects
what someone remembered to add — and the next extraction is the one at risk, not the last one. The
assertion is a property of the whole surface: *no API method name is defined in more than one file*.
It needs no exemption list, which is the signal the population is right.

THE FILE HALF IS ALREADY SHIPPED, BY SOMEONE ELSE, AND THIS IS THE OTHER HALF
    `apps/web/src/tooling/deleteRatchet.test.ts` ratchets eight deleted **documents** — load-bearing
    because `docs/` is the Pages web root, so re-adding one republishes a superseded planning page.
    That pass **deliberately skipped symbols**, and the reasoning is worth repeating because it is why
    this file is shaped the way it is. Three symbol candidates were tried and all three failed:
    `"classic"` still lives as a run label; `"more"` appears in prose *describing its own removal*, so
    the gate would fire on its own documentation; and `renderRegister`/`registerBoard` were **guessed
    names that never existed at any commit** — an assertion that would have passed forever and read as
    coverage.

    Every one of those is a **string-matching** problem, and this gate has none of them. It never
    searches for a name: it parses *definition sites* (`^  name(` at class indent, in `api/*.ts`) and
    asserts a derived property over whatever it finds. There is no list to guess wrong, prose cannot
    match a definition site, and a name with a legitimate other life is irrelevant — a second
    *definition* is the defect no matter what else the word means elsewhere.

    Scope note, because it is easy to over-read: no `.py`/`.ts`/`.tsx` file has ever been deleted on
    `main` (`git log --diff-filter=D`, 400 commits, zero). That is why the path ratchet lives over
    `docs/` and why this one is about definitions rather than deletions — in source, things here get
    *extracted*, not removed.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_delete_ratchet.py
"""
import collections
import glob
import os
import re
import sys

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


API_DIR = os.path.join("..", "..", "apps", "web", "src", "api")

#: Files in `api/` that are not part of the method surface: the type modules declare no methods, and
#: `*.test.ts` legitimately repeats names it is testing.
_NOT_SURFACE = {"types.ts", "schema.d.ts", "openapiTypes.ts"}

#: A class method at mixin/class indent. Deliberately anchored at exactly two spaces: nested
#: functions sit deeper and control-flow keywords are excluded below.
_METHOD = re.compile(r"^  ([a-zA-Z_][A-Za-z0-9_]*)\s*\(")
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "constructor", "function"}


def method_owners() -> dict[str, list[str]]:
    """name -> the api/*.ts files that DEFINE it."""
    owners: dict[str, set] = collections.defaultdict(set)
    for path in sorted(glob.glob(os.path.join(API_DIR, "*.ts"))):
        base = os.path.basename(path)
        if base.endswith(".test.ts") or base in _NOT_SURFACE:
            continue
        for line in open(path, encoding="utf-8"):
            m = _METHOD.match(line.rstrip("\n"))
            if m and m.group(1) not in _KEYWORDS:
                owners[m.group(1)].add(base)
    return {k: sorted(v) for k, v in owners.items()}


owners = method_owners()

# --- the population has to be real before the assertion over it means anything -------------------
check("the API surface is actually being read — hundreds of methods, not zero",
      len(owners) > 400, len(owners))
check("  across the extracted mixins, not just client.ts",
      len({f for v in owners.values() for f in v}) >= 5,
      sorted({f for v in owners.values() for f in v}))
check("  and client.ts is among them, so a shadow there is visible to this reader",
      any("client.ts" in v for v in owners.values()))

# --- THE RATCHET ----------------------------------------------------------------------------------
dupes = {k: v for k, v in owners.items() if len(v) > 1}
check("NO API METHOD IS DEFINED IN TWO FILES — an extraction cannot be quietly re-absorbed",
      not dupes,
      "; ".join(f"{k} in {'+'.join(v)}" for k, v in sorted(dupes.items())[:8]))

# --- the extractions that have actually happened, named so the failure reads usefully -------------
# Not the gate — the gate above is derived and needs no list. These are spot-checks that the reader
# is pointed at the right files at all, so a bug in the regex cannot pass as "no duplicates".
for name, expected in (("solveProforma", "proforma.ts"),
                       ("designOptionsRecord", "designOptions.ts"),
                       ("designOptionsScore", "designOptions.ts")):
    check(f"  {name} is found, and in {expected}",
          owners.get(name) == [expected], owners.get(name, "NOT FOUND"))

check("  and none of them is ALSO in client.ts — which is what being extracted means",
      all("client.ts" not in owners.get(n, [])
          for n in ("solveProforma", "designOptionsRecord", "designOptionsScore")))

print()
if FAILED:
    print(f"delete_ratchet: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"delete_ratchet: all checks passed ({len(owners)} methods, "
      f"{len({f for v in owners.values() for f in v})} files, no shadowed definitions)")
