"""Every custom response header the web client READS must be exposed by CORS.

THE DEFECT THIS EXISTS FOR. A cross-origin `fetch` can only see the seven CORS-safelisted response
headers. Anything else — every `X-…` this API sets — is invisible to JavaScript unless the server
names it in `Access-Control-Expose-Headers`. The browser does not warn, does not throw, and does not
log: `res.headers.get("X-Whatever")` simply returns `null`.

Measured 2026-08-09 from a real cross-origin page (`:5183` → the API on `:8097`) against a route that
sets `X-Element-Guid`. The browser could see exactly::

    ["content-length", "content-type"]        # and X-Element-Guid was null

`expose_headers` listed only `Content-Disposition`, so THREE reads had been dead since the day they
were written:

* ``X-Element-Guid``    — ``|| ""`` swallowed it; the authored element's preview id fell back to a
  timestamp instead of the GUID, and nothing anywhere said so.
* ``X-Seal-Sealed``     — ``=== "true"`` against ``null`` is ``False``. A PDF genuinely sealed by a
  licensed PE/RA reported back to the UI as **not sealed**. Of the three this is the one that
  matters: it is a false negative about a professional engineer's seal.
* ``X-Seal-Compliance`` — ``|| ""`` again; the compliance note silently disappeared.

WHY A GATE RATHER THAN A LONGER LIST. Fixing the list fixes today. The failure mode is that the next
header is added to a route and read in the client by someone who has no reason to know this list
exists — the code works perfectly in same-origin tests and in every unit test, because
`Access-Control-Expose-Headers` is a *browser* rule that only bites in a browser, cross-origin. So
this test derives the population from the CLIENT (what does the web app actually read?) instead of
asking anyone to remember to update the server. See [[derive-the-population-and-the-reach]] — the
population here is "reads in the client", and the reach is "cross-origin, which is every deployment
where the app and API are not the same origin".

WHAT IS DELIBERATELY OUT OF SCOPE. `apps/web/src/vendor/` is third-party code talking to third-party
APIs (Azure's `Operation-Location`, which Azure exposes itself). Our CORS config has no bearing on
those, and listing them here would be a false claim about what this server controls.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MAIN = _ROOT / "services" / "api" / "src" / "aec_api" / "main.py"
_WEB = _ROOT / "apps" / "web" / "src"

#: The CORS-safelisted response headers, which are readable without being exposed.
#: https://fetch.spec.whatwg.org/#cors-safelisted-response-header-name
_SAFELISTED = {
    "cache-control", "content-language", "content-length", "content-type",
    "expires", "last-modified", "pragma",
}

#: Third-party code calling third-party APIs. Our CORS config does not govern those responses.
_EXCLUDED_DIRS = ("vendor",)

_READ = re.compile(r'headers\.get\(\s*"([^"]+)"\s*\)')


def _exposed() -> list[str]:
    """The `expose_headers=[...]` list, read from main.py's AST rather than by regex.

    AST because the value must be the one FastAPI actually receives. A regex over the source would
    happily match the same list inside a comment or a docstring — and this file's own docstring
    quotes those header names, which is exactly the trap.
    """
    tree = ast.parse(_MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "expose_headers" and isinstance(kw.value, ast.List):
                out = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
                if len(out) != len(kw.value.elts):
                    raise AssertionError(
                        "expose_headers holds a non-literal element; this gate can no longer read "
                        "the real list and would pass while measuring nothing")
                return out
    raise AssertionError("no expose_headers=[...] found in main.py — the CORS config moved")


def _client_reads() -> dict[str, list[str]]:
    """Header name (as written) -> the files that read it. Vendor trees excluded."""
    found: dict[str, list[str]] = {}
    for path in sorted(_WEB.rglob("*.ts")):
        rel = path.relative_to(_ROOT).as_posix()
        if any(f"/{d}/" in f"/{rel}" for d in _EXCLUDED_DIRS):
            continue
        for name in _READ.findall(path.read_text(encoding="utf-8")):
            if name.lower() in _SAFELISTED:
                continue
            found.setdefault(name, []).append(rel)
    return found


def test_every_header_the_client_reads_is_exposed() -> None:
    exposed_lower = {h.lower() for h in _exposed()}
    reads = _client_reads()
    assert reads, ("the scan found no custom header reads at all — either the client stopped using "
                   "them or this regex stopped matching, and a gate over an empty population "
                   "passes while proving nothing")

    missing = {n: f for n, f in reads.items() if n.lower() not in exposed_lower}
    assert not missing, (
        "these headers are read by the web client but NOT in expose_headers, so they read `null` in "
        "any cross-origin browser — silently, with no error:\n"
        + "\n".join(f"  {n}  <- {', '.join(files)}" for n, files in sorted(missing.items()))
        + "\nAdd them to expose_headers in services/api/src/aec_api/main.py."
    )
    print(f"PASS  every custom header the client reads is exposed   "
          f"{len(reads)} read: {', '.join(sorted(reads))}")


def test_the_named_headers_are_actually_set_by_a_route() -> None:
    """The twin. Without it, expose_headers could name anything and still 'pass'.

    A list that exposes headers no route emits is not harmful, but it is evidence the list is being
    maintained by guesswork — and a gate that cannot tell a real name from an invented one is not
    measuring the thing it claims to. Content-Disposition is exempt: Starlette's FileResponse sets
    it, so it never appears as a literal in our source.
    """
    src = "\n".join(p.read_text(encoding="utf-8")
                    for p in (_ROOT / "services" / "api" / "src" / "aec_api").rglob("*.py"))
    unset = [h for h in _exposed() if h != "Content-Disposition" and f'"{h}"' not in src]
    assert not unset, (
        f"expose_headers names headers no route sets: {unset}. Either a route was deleted and this "
        f"list was not, or the name is a typo — and a typo here fails exactly like the bug this "
        f"gate exists to catch, since the real header stays unexposed.")
    print(f"PASS  every exposed header is one a route really sets   {len(_exposed())} exposed")


if __name__ == "__main__":
    test_every_header_the_client_reads_is_exposed()
    test_the_named_headers_are_actually_set_by_a_route()
    print("test_cors_expose_headers OK")
