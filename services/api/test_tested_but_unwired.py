"""A function with tests and no production caller is invisible to every other gate we have.

`test_dead_code_population.py` counts the test tree as callers **on purpose** — that is the 877 -> 13
correction its header describes, and it is right for the question it asks. The cost is that
*"tested, and wired to nothing"* cannot be seen by it: a function with thirteen tests and zero product
callers scores as thoroughly referenced. R37-TESTED-UNWIRED was created because three instances had
been found **by hand**, one at a time, and its own entry called three hand-finds "a population, not a
coincidence".

**That item closed on 2026-08-28. On 2026-08-29 the class recurred twice**, in code that merged the
same day: `asset_rights.verify_release` and `generate_seed` — the entire verification half of a signed
release manifest, built, tested, and reachable by nothing, while the sealing half shipped. R37's
twenty were a snapshot, not a population. A sweep that must be re-run by hand is one that will be
skipped, so this is the sweep as a ratchet.

WHAT IT MEASURES. Public, undecorated, module-level functions defined under `aec_api` — the same
population `test_dead_code_population` reports (1092), and decorated functions are excluded for the
same reason: a `@router.get` handler is called by the framework, never by name, so "no caller" is
its normal state. A function is flagged when it has **zero references in production source** and at
least one in the test tree.

TWO MEASUREMENT DECISIONS, both of which changed the answer by an order of magnitude:

  * **Comments and docstrings are stripped, and this is load-bearing rather than tidy.** A raw token
    count reported 7; the real number is 12. `verify_release` is named inside `verify_signature`'s
    own docstring, so a text scan reads the prose as a caller and the finding disappears. This repo
    has been bitten by the same thing repeatedly — a source-grep gate that flagged its own
    documentation, twice in one day. Assertion 3 below proves the stripping still does work rather
    than having quietly become a no-op.
  * **Only the definition line is subtracted, not the defining file.** Subtracting the whole file
    reported 147, because a function called by its own module's `main()` or by a sibling read as
    uncalled. Intra-module use is use.

THE FROZEN LIST IS NOT AN ALLOWLIST OF THINGS TO IGNORE. R37's archived entry is explicit: *"The
number is not the deliverable and must not be ratcheted before it is read... A population rule that
looks reasonable is wrong until you read what it selected"* — R37-TRIAGE deleted two candidates
unread and had to put them back. Every entry below was read on 2026-08-29 and carries why. Three of
them are open roadmap items, not exemptions.
"""
import ast
import re
import subprocess
import sys
import tokenize
from collections import Counter

HERE = __file__.replace("\\", "/").rsplit("/", 1)[0]
ROOT = HERE.rsplit("/services/api", 1)[0]
API = "services/api/src/aec_api/"
TOK = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: name -> why it is legitimately (or knowingly) test-only. READ, not assumed.
FROZEN: dict[str, str] = {
    # --- test-by-design: the gate IS the intended caller -------------------------------------
    "sbom": "supply-chain gate surface; R37 classified it as legitimately test-only",
    "is_dual_licensed": "supply-chain gate surface; R37 classified it as legitimately test-only",
    "unmapped_sections": "its own docstring: 'A non-empty result must fail a build, not warn'",
    "validate_dir": "module.json validator; called by test_module_config.py, which is its purpose",
    # --- refusal stubs: raise until a deployment wires the integration, never fabricate -------
    "sync_property": "energy-star refusal stub, already exempted in test_dead_code_population",
    "fetch_parcels": "parcels bridge: 'raises until one is wired (never fabricates data)'",
    "send_payment": "payments bridge: 'raises until a processor is wired (never fabricates a transfer)'",
    # --- OPEN ROADMAP ITEMS, not exemptions --------------------------------------------------
    "verify_release": "ASSET-VERIFY (Band 2) — the verification half of asset-rights has no caller",
    "generate_seed": "ASSET-VERIFY (Band 2) — no supported way to mint a signing key",
    "rule_for": "SOFT-CLASH-RULES (Band 2) — six of seven sourced clearances never evaluated",
    "cite_record": "no producer: cite_ifc/cite_rule/cite_doc are wired, the record builder is not",
    "owner_of": "docmanager.py reimplements its one-line body inline at 3 sites instead of calling it",
}

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + label + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    return [f for f in out.split("\n") if f.strip()]


def _read(f: str) -> str:
    return open(f"{ROOT}/{f}", encoding="utf-8", errors="replace").read()


def code_names(f: str) -> list[str]:
    """Identifiers in CODE only — comments and string literals, docstrings above all, dropped."""
    if f.endswith(".py"):
        try:
            with open(f"{ROOT}/{f}", "rb") as fh:
                return [t.string for t in tokenize.tokenize(fh.readline)
                        if t.type == tokenize.NAME]
        except Exception:                                    # noqa: BLE001 — fall back to regex
            pass
    src = re.sub(r"/\*.*?\*/", " ", _read(f), flags=re.S)
    return TOK.findall(re.sub(r"(?m)//.*$", " ", src))


def unwired(strip_comments: bool = True) -> tuple[dict[str, str], int, int]:
    files = _tracked()
    api_py = [f for f in files if f.startswith(API) and f.endswith(".py")]
    tests = [f for f in files if re.match(r"services/(api|data)/test_[a-z0-9_]+\.py$", f)]
    prod = [f for f in files
            if (f.startswith("services/api/src/") or f.startswith("services/data/src/")
                or f.startswith("apps/web/src/")) and f.endswith((".py", ".ts"))]

    defs: dict[str, set[str]] = {}
    for f in api_py:
        try:
            tree = ast.parse(_read(f))
        except SyntaxError:
            continue
        for n in tree.body:
            if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not n.name.startswith("_") and not n.decorator_list):
                defs.setdefault(n.name, set()).add(f)

    names = code_names if strip_comments else (lambda f: TOK.findall(_read(f)))
    prod_tok: Counter = Counter()
    test_tok: Counter = Counter()
    for f in prod:
        prod_tok.update(names(f))
    for f in tests:
        test_tok.update(names(f))

    found = {}
    for name, where in defs.items():
        ndef = sum(1 for f in where for ln in open(f"{ROOT}/{f}", encoding="utf-8",
                                                      errors="replace")
                   if ln.lstrip().startswith((f"def {name}(", f"async def {name}(")))
        if prod_tok[name] - ndef <= 0 and test_tok[name] > 0:
            found[name] = sorted(where)[0].replace(API, "")
    return found, len(defs), len(tests)


FOUND, _POP, _NTEST = unwired()
print(f"  population {_POP} public undecorated fns · {_NTEST} test files · "
      f"{len(FOUND)} referenced only by tests")

# 1 — vacuity: a rule that selected nothing would pass every assertion below
check("the population and the test tree are real", _POP > 500 and _NTEST > 100,
      f"{_POP} functions, {_NTEST} test files")

# 2 — the ratchet
new = sorted(set(FOUND) - set(FROZEN))
check("NO NEW tested-but-unwired function", not new,
      ", ".join(f"{n} ({FOUND[n]})" for n in new) + " — built and tested with no production "
      "caller. Read it before freezing it: wire it, delete it, or add it to FROZEN with why"
      if new else f"all {len(FOUND)} are known")

# 3 — the comment-stripping is still doing work (see the header). A differential, because a
#     stripping step that silently became a no-op would leave every other assertion passing.
raw, _, _ = unwired(strip_comments=False)
check("stripping comments/docstrings still changes the answer",
      len(FOUND) > len(raw),
      f"stripped {len(FOUND)} vs raw {len(raw)} — no difference means the tokenizer stopped "
      f"excluding prose, and names mentioned in docstrings are being read as callers")

# 4 — the frozen list cannot rot
stale = sorted(set(FROZEN) - set(FOUND))
check("every frozen entry is still unwired", not stale,
      ", ".join(stale) + " — now has a production caller (or was renamed/deleted). Remove the "
      "entry: a kept name that no longer means anything pre-authorises whatever reuses it"
      if stale else f"all {len(FROZEN)} still apply")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_tested_but_unwired OK")
