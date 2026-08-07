"""Reconcile `TESTS` / `DATA_TESTS` across a rebase or merge of `services/api/run_tests.py`.

WHY THIS EXISTS. That manifest is one packed line that every lane edits, and it is the worst shared
surface in the repo — see `services/api/test_manifest.py` and the roadmap's Lane J note. When two
branches both add an entry, git presents a conflict on a line carrying 200+ names, and resolving it by
reading is a coin flip. On 2026-08-07 a resolution looked like competing edits to one entry and was
actually main *repacking* the region onto a single line against a split version: 207 entries a side,
exactly one different.

WHAT `test_manifest.py` DOES NOT COVER. It catches an entry registered twice and an entry naming a
file that does not exist. It does not tell you whether a CONFLICT RESOLUTION silently dropped an
entry that should have survived, because a dropped entry is simply absent and absence is not an error
there — the suite just quietly stops running that file. This script answers that question, and
reports duplicates separately because a packed-line resolution can repeat an entry as easily as lose
one.

HOW TO USE IT, from the repo root, before staging the resolved file:

    git show $(git merge-base HEAD origin/main):services/api/run_tests.py > /tmp/base.py
    git show HEAD:services/api/run_tests.py                              > /tmp/mine.py
    git show origin/main:services/api/run_tests.py                       > /tmp/main.py
    cp services/api/run_tests.py                                           /tmp/after.py
    python scripts/reconcile_test_manifest.py /tmp/base.py /tmp/mine.py /tmp/main.py /tmp/after.py

Exit 0 means the entry sets reconcile exactly. Omit the fourth argument to see the expected result
before resolving.

TWO THINGS THAT MATTER MORE THAN THE CODE.

  1. **Derive the expected delta from the merge-base; never accept one that was handed to you.** The
     first use of this was prompted by a message saying main had added one entry. It had added two —
     the second came from a PR merged an hour earlier that the author had forgotten. Asserting the
     handed-over value would have gone red on a *correct* resolution, and the tempting repair for that
     is to delete the entry that "shouldn't" be there. A hand-supplied expected value is itself an
     unverified claim.

  2. **Run it twice on a rebase** — once at the conflict, and again after the remaining commits
     replay. A later commit in the same rebase can touch the same file, and the first run cannot see
     that.

AST, not regex: the manifest is packed, and a naive pattern over-counts by matching names in
comments and docstrings.
"""
import ast
import sys


def lists(path: str) -> dict[str, list[str]]:
    """Every string entry of the module-level TESTS / DATA_TESTS assignments."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ("TESTS", "DATA_TESTS"):
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        out[t.id] = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    return out


def main(argv: list[str]) -> int:
    if not 4 <= len(argv) <= 5:
        print(__doc__)
        return 2
    # argv[0] is this script. Slicing from 1 is not a detail: the first draft used `argv[:4]`, parsed
    # ITSELF as the base revision, and reported MANIFEST DAMAGED against a resolution already proven
    # correct. A checker that mis-reads its own inputs fails toward alarm, which at least is loud.
    base, mine, main_ = (lists(a) for a in argv[1:4])
    after = lists(argv[4]) if len(argv) == 5 else None

    ok = True
    for key in ("TESTS", "DATA_TESTS"):
        b, m, n = set(base.get(key, [])), set(mine.get(key, [])), set(main_.get(key, []))
        expected = (b | (m - b) | (n - b)) - ((b - m) | (b - n))
        print(f"\n=== {key} ===")
        print(f"  base           : {len(b)}")
        print(f"  mine adds      : {sorted(m - b) or '(none)'}")
        print(f"  main adds      : {sorted(n - b) or '(none)'}")
        print(f"  mine removes   : {sorted(b - m) or '(none)'}")
        print(f"  main removes   : {sorted(b - n) or '(none)'}")
        print(f"  EXPECTED after : {len(expected)}")
        if after is None:
            continue
        a = set(after.get(key, []))
        dropped, unexpected = expected - a, a - expected
        dupes = len(after.get(key, [])) - len(a)
        print(f"  ACTUAL after   : {len(a)}")
        print(f"  DROPPED        : {sorted(dropped) or '(none)'}")
        print(f"  UNEXPECTED     : {sorted(unexpected) or '(none)'}")
        print(f"  DUPLICATES     : {dupes}")
        if dropped or unexpected or dupes:
            ok = False

    if after is not None:
        print("\n" + ("RESULT: entry sets reconcile exactly" if ok else "RESULT: MANIFEST DAMAGED"))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
