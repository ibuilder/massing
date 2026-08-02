"""Every outbound fetch of a non-literal host must go through `net.safe_urlopen`.

`net.py` has said so in prose since it was written ("Every outbound fetch of a settable URL should
pass through `validate_outbound_url` first"), and prose does not fail a build. Five modules had
adopted it and five had not, which is the `_PROTECTED_PREFIXES` shape again: a control that is real
where it was applied and absent where nobody remembered.

Two of the five were live defects, both measured rather than argued:

  * `connectors_vendors._erp_get` took the ERP `base_url` straight from operator config into
    `urlopen`. `urlopen` honours **any** scheme, so `base_url = file:///…` returned the file's bytes
    as the ERP payload — a config field promoted to an arbitrary local-file read.
  * `speckle_bridge._graphql` validated its URL and then handed it to plain `urlopen`, which follows
    3xx. Hop zero cleared the guard; hops one and up cleared nothing. In a differential probe against
    a local server answering `302 -> ftp://…`, plain `urlopen` reached the redirect target and
    `safe_urlopen` refused it.

The second is the one to remember, because `net.py` itself had blessed that module as "keeps its own
(stricter, https-only) guard". It did — on hop zero. **A scheme/host check is a property of a hop,
not of a URL**, so a check that runs once and an opener that follows redirects are not the same
control, and the module documented as already-guarded is the one nobody re-reads.

What this asserts, per function that fetches:

  raw `urlopen`  -> every request URL in that function must carry a **literal** scheme+host, either
                    spelled in the source (`f"https://api.procore.com{path}"`) or via a module-level
                    string constant (`f"{APS_BASE}/…"`). A host assembled from a parameter or a
                    settings value is not literal, whatever the `# noqa: S310` comment claims — the
                    comment on the ERP call site named the risk ("operator-supplied tenant host") and
                    waved it through anyway.
  `safe_urlopen` -> anything, that is the point of it.

It also asserts `safe_urlopen` still builds its opener with the validating redirect handler, so the
guard cannot be quietly hollowed out into a hop-zero check — which is precisely the bug above.

This is derived rather than listed, and that difference is the whole reason it exists.
`test_security_audit` already asserted "every outbound bridge must route through safe_urlopen" — over
a hardcoded tuple naming the five modules that had **already** adopted it. Such a list can only catch
an adopter regressing; a sixth module that never adopted was outside what the check could see, and
five of them were. The scope of a gate is part of its claim, so this one enumerates the package and
lets the exemptions be a property of the code (a literal host) rather than a name someone remembered
to add.

`guard_problems()` takes injectable sources so each rule can be driven with a synthetic violation and
shown to go red. A gate asserted only against the passing case is indistinguishable from `return []`.
Run against the pre-fix tree it reports six call sites, including both live defects — the check was
watched failing on the real bugs, not only on synthetic ones.
Pure AST: no DB, no TestClient, no network.
"""
import ast
import pathlib
import sys
import urllib.request

SRC = pathlib.Path(__file__).parent / "src" / "aec_api"
GUARD = "safe_urlopen"
# net.py defines the guard; it is the one place a raw urlopen is the implementation, not a bypass.
EXEMPT_MODULES = {"net"}

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# --- the analyzer ------------------------------------------------------------------
def _has_host(s) -> bool:
    """True when `s` pins scheme AND host — `https://` alone does not, the host is the whole point."""
    if not isinstance(s, str):
        return False
    for scheme in ("https://", "http://"):
        if s.startswith(scheme):
            rest = s[len(scheme):]
            return bool(rest) and rest[0] not in "{/"
    return False


def _module_consts(tree) -> dict:
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value.value, str):
                    out[t.id] = node.value.value
    return out


def _literal_host(expr, consts) -> bool:
    if isinstance(expr, ast.Constant):
        return _has_host(expr.value)
    if isinstance(expr, ast.Name):
        return _has_host(consts.get(expr.id))
    if isinstance(expr, ast.JoinedStr) and expr.values:
        first = expr.values[0]
        if isinstance(first, ast.Constant):
            return _has_host(first.value)
        if isinstance(first, ast.FormattedValue) and isinstance(first.value, ast.Name):
            return _has_host(consts.get(first.value.id))
    return False


def _callee(node) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def guard_problems(sources: dict | None = None) -> list:
    """Return human-readable problems; empty when every fetch is guarded or literal-hosted."""
    if sources is None:
        sources = {p.stem: p.read_text(encoding="utf-8") for p in sorted(SRC.rglob("*.py"))
                   if p.stem not in EXEMPT_MODULES}
    problems = []
    for mod, src in sources.items():
        tree = ast.parse(src)
        consts = _module_consts(tree)
        for fn in [n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
            raw = [c for c in calls if _callee(c) == "urlopen"]
            if not raw or any(_callee(c) == GUARD for c in calls):
                continue
            urls = [c.args[0] for c in calls if _callee(c) == "Request" and c.args]
            if not urls:                      # urlopen("…") with no Request wrapper
                urls = [c.args[0] for c in raw if c.args]
            for u in urls:
                if not _literal_host(u, consts):
                    problems.append(
                        f"{mod}.{fn.name}: raw urlopen on a host that is not a literal — route it "
                        f"through net.{GUARD}(), or pin scheme+host as a literal/module constant")
    return problems


# --- 1. the live package ------------------------------------------------------------
live = guard_problems()
check("every outbound fetch in aec_api is guarded or literal-hosted", not live,
      "; ".join(live) if live else f"{len(list(SRC.rglob('*.py')))} modules scanned")

# --- 2. each rule must be able to go red --------------------------------------------
SETTABLE = ('import urllib.request\n'
            'def f(base_url, path):\n'
            '    req = urllib.request.Request(f"{base_url}{path}")\n'
            '    return urllib.request.urlopen(req, timeout=8)\n')
check("fires on a host built from a parameter (the _erp_get shape)",
      len(guard_problems({"m": SETTABLE})) == 1, guard_problems({"m": SETTABLE}))

SCHEME_ONLY = SETTABLE.replace('f"{base_url}{path}"', 'f"https://{base_url}{path}"')
check("fires when only the SCHEME is literal — a pinned scheme is not a pinned host",
      len(guard_problems({"m": SCHEME_ONLY})) == 1)

LITERAL = SETTABLE.replace('f"{base_url}{path}"', 'f"https://api.procore.com{path}"')
check("passes a literal scheme+host (the Procore shape stays raw, no churn)",
      guard_problems({"m": LITERAL}) == [])

CONSTANT = ('import urllib.request\n'
            'BASE = "https://developer.api.autodesk.com"\n'
            'def f(path):\n'
            '    req = urllib.request.Request(f"{BASE}{path}")\n'
            '    return urllib.request.urlopen(req, timeout=8)\n')
check("passes a module-level constant host (the APS_BASE shape)",
      guard_problems({"m": CONSTANT}) == [])

GUARDED = ('from .net import safe_urlopen\n'
           'import urllib.request\n'
           'def f(base_url, path):\n'
           '    req = urllib.request.Request(f"{base_url}{path}")\n'
           '    return safe_urlopen(req, timeout=8, label="x")\n')
check("passes any host once routed through the guard", guard_problems({"m": GUARDED}) == [])

# A near-miss worth pinning: the guard imported but not actually used for THIS fetch. Whole-module
# matching ("does this file mention safe_urlopen?") would wave it through; the check is per function.
IMPORTED_UNUSED = GUARDED.replace('return safe_urlopen(req, timeout=8, label="x")',
                                  'return urllib.request.urlopen(req, timeout=8)')
check("fires when the guard is imported but not used for that fetch",
      len(guard_problems({"m": IMPORTED_UNUSED})) == 1)

# --- 3. the guard itself must still validate every hop -------------------------------
net_src = (SRC / "net.py").read_text(encoding="utf-8")
check("safe_urlopen still builds its opener with the validating redirect handler",
      "build_opener" in net_src and "_ValidatingRedirectHandler" in net_src
      and net_src.index("_ValidatingRedirectHandler") < net_src.rindex("build_opener"))


def _refuses_redirect_to(newurl: str) -> bool:
    from aec_api import net
    handler = net._ValidatingRedirectHandler(require_https=True, allow_private=False, label="T")
    try:
        handler.redirect_request(urllib.request.Request("https://ok.example"), None, 302, "Found",
                                 {}, newurl)
        return False
    except ValueError:
        return True


sys.path.insert(0, str(SRC.parent))
check("a redirect to a non-http scheme is refused", _refuses_redirect_to("ftp://127.0.0.1/x"))
check("a redirect to plain http is refused when https was required",
      _refuses_redirect_to("http://example.com/x"))
check("a redirect to a loopback host is refused when private was disallowed",
      _refuses_redirect_to("https://127.0.0.1/x"))

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"outbound_fetch_guard OK — {len(list(SRC.rglob('*.py')))} modules, "
      f"{len(guard_problems({'m': SETTABLE}))} synthetic rule(s) verified red")
