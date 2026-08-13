"""No test may crash on its own output — a suite whose exit code depends on the console lies.

`test_procurement.py` passed every assertion it makes and then died printing its success line:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2192'

The arrow in "rebar->BuildMart" was a U+2192, and Windows' default console encoding is cp1252, which
has no such character. **Exit code 1, zero failed assertions, and a traceback where the OK line
should be.** Run through `run_tests.py` it passed, because that runner sets `PYTHONUTF8=1` in the
child environment; run directly — which is how anyone debugging a single test runs it — it reported
failure while nothing had failed.

That is the worst shape a check can take. A false RED is not merely annoying: it sends someone to
debug a passing test, and the reflex it teaches is to distrust the runner.

**The same bug bit from the other side the same day.** A newly written gate put a U+2192 in its
FAILURE detail string. Every assertion passed, so nobody saw it — until a mutation made the check
fail, and instead of naming the unpinned action it raised UnicodeEncodeError. The exit code was 1
either way, so the mutation "worked"; the message identifying the culprit was destroyed. Reading the
output rather than the exit code is what caught it.

So the rule is narrow and mechanical: **characters inside a `print()` must survive cp1252.**

Docstrings, comments and assertion messages are NOT covered, deliberately. They are never written to
the console by a passing or failing test, this file's own docstring would fail such a rule, and a
gate broad enough to flag its own prose is one that gets switched off — a shape this repo has hit
five separate times. The check therefore walks the AST and looks only at string constants inside
`print(...)` calls, which is exactly the set that reaches the encoder.
"""
from __future__ import annotations

import ast
import pathlib
import sys
import unicodedata

HERE = pathlib.Path(__file__).parent

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def printed_text(tree: ast.AST) -> list[tuple[int, str]]:
    """(lineno, concatenated string constants) for every `print(...)` call."""
    out: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print":
            txt = "".join(c.value for c in ast.walk(n)
                          if isinstance(c, ast.Constant) and isinstance(c.value, str))
            if txt:
                out.append((n.lineno, txt))
    return out


files = sorted(HERE.glob("test_*.py"))

# Silence is not a signal: an empty glob, or an AST walk that stops matching `print`, satisfies the
# real assertion below while checking nothing at all.
check("the scan found the test files", len(files) >= 400, f"{len(files)} test_*.py")

scanned = 0
offenders: list[str] = []
for f in files:
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError as exc:                     # a broken test is a different failure
        offenders.append(f"{f.name}: unparseable ({exc.msg})")
        continue
    for lineno, txt in printed_text(tree):
        scanned += 1
        for ch in dict.fromkeys(txt):              # ordered, de-duplicated
            try:
                ch.encode("cp1252")
            except UnicodeEncodeError:
                offenders.append(
                    f"{f.name}:{lineno} U+{ord(ch):04X} {unicodedata.name(ch, '?')}")

# The second vacuity guard, and the one that matters more: if NO print() calls were found the loop
# above never executes and the check passes on an empty population.
check("...and found print() calls in them", scanned >= 500, f"{scanned} print() calls inspected")

check("no test prints a character cp1252 cannot encode", not offenders,
      "; ".join(offenders[:6]) + (f" (+{len(offenders) - 6} more)" if len(offenders) > 6 else "")
      if offenders else f"{scanned} print() calls clean")

# The twin. Everything above is a refusal test — it asserts an absence, which a predicate that
# answers "fine" to every input also satisfies. This proves the predicate can say NO, using the
# exact character that caused the incident.
def encodable(s: str) -> bool:
    try:
        s.encode("cp1252"); return True
    except UnicodeEncodeError:
        return False


_rejects = not encodable("rebar→BuildMart")
check("...and the check REJECTS the character that caused this", _rejects,
      "U+2192 correctly rejected" if _rejects else "U+2192 WRONGLY ACCEPTED")
check("...while accepting ordinary ASCII output",
      encodable("rebar->BuildMart  PROCUREMENT OK"))
# cp1252 is not ASCII — it carries the punctuation this repo's prose uses heavily. Asserting this
# keeps the rule honest about what it actually forbids, so nobody "fixes" an em dash that is fine.
check("...and accepting cp1252 punctuation, which is NOT forbidden",
      encodable("an em dash — an en dash – curly quotes “x” … all fine"))

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"test_output_encoding OK  ({scanned} print() calls across {len(files)} files)")
