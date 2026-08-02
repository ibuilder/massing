"""Both storage backends must refuse the SAME SET of keys.

The key guard lived inside `LocalBackend._p`, so the two shipped backends disagreed about the same
input: `../../etc/x` raised on local and was accepted by S3. Neither is a traversal on S3 — an object
key containing dots is just a name — and that is exactly why it survived. There was no exploit to
find, only a divergence: a defence-in-depth control applied to whichever half of the deployments
happened to be running the filesystem backend, with nothing anywhere to say which half you were on.
A key written under one profile could not be read back under the other.

Asserted as **set-equality in both directions**, not as "each backend refuses something". A
per-backend checklist could not have caught this, because S3's entry would simply never have been
written — the same failure shape as a gate that lists its adopters and therefore cannot see a
non-adopter. Set-equality is the property that stops the third backend from diverging quietly too:
it fails for a key S3 wrongly accepts *and* for one it wrongly refuses, and the second direction is
the one a hand-written list never covers.

The second half is structural: every key-taking method on every backend must route through
`validate_key` (directly, or via `_p` which calls it). A new method — or a new backend class — that
takes a key and forgets is caught by AST rather than by whoever reviews it. `S3Backend.version` and
`delete_prefix` are not on the `Backend` Protocol at all, so "it implements the interface" would not
have covered them either.

No network and no boto3: the S3 client is a stub, and the backend is built with `object.__new__` so
`__init__` (which reaches for a live endpoint and creates a bucket) never runs.
"""
import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from aec_api import storage  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


class _StubS3:
    """Answers every call the backend makes; records nothing. Reaching it means the key was allowed."""

    def put_object(self, **kw): return {}
    def get_object(self, **kw): return {"Body": _Body()}
    def head_object(self, **kw): return {"ContentLength": 1, "ETag": '"abc"'}
    def delete_object(self, **kw): return {}
    def list_objects_v2(self, **kw): return {"Contents": [], "IsTruncated": False}
    def delete_objects(self, **kw): return {}


class _Body:
    def read(self): return b""


KEYS = [
    "p1/model.ifc",                  # ordinary
    "p1/sub/dir/a.frag",             # nested
    "p1/a file with spaces.pdf",     # attachment filenames are user-supplied
    "p1/../p2/secret.ifc",           # traversal, mid-key
    "../../etc/passwd",              # traversal, leading
    "..",                            # bare
    "/etc/passwd",                   # absolute posix
    "\\windows\\win.ini",            # absolute windows
    "p1/model\x00.ifc",              # NUL
    "",                              # empty
    "p1/..\\p2/x",                   # backslash traversal
]


def _refused(backend, key) -> bool:
    """True when the backend refuses the key. Only ValueError counts as a refusal — a stub raising
    KeyError/TypeError would otherwise read as a guard that is not there."""
    try:
        backend.get(key)
        return False
    except ValueError:
        return True
    except Exception:
        return False


import tempfile  # noqa: E402

local = storage.LocalBackend(tempfile.mkdtemp())
s3 = object.__new__(storage.S3Backend)      # skip __init__: it needs a live endpoint
s3.bucket, s3.client = "test", _StubS3()

local_refused = {k for k in KEYS if _refused(local, k)}
s3_refused = {k for k in KEYS if _refused(s3, k)}

check("the two backends refuse exactly the same keys",
      local_refused == s3_refused,
      f"local-only={sorted(local_refused - s3_refused)!r} s3-only={sorted(s3_refused - local_refused)!r}")
check("and it is a real set, not both-refuse-nothing", len(local_refused) >= 6,
      f"{len(local_refused)} of {len(KEYS)} refused")
check("ordinary keys still pass both", not ({"p1/model.ifc", "p1/sub/dir/a.frag"} & local_refused)
      and not ({"p1/model.ifc", "p1/sub/dir/a.frag"} & s3_refused))

# The parity assertion must be able to go red — a stub that refuses nothing would satisfy
# "both refuse the same" only if local also refused nothing, so drive the asymmetric case directly.
class _Unguarded:
    def get(self, key): return b""


check("parity check fires when one side stops refusing",
      {k for k in KEYS if _refused(local, k)} != {k for k in KEYS if _refused(_Unguarded(), k)})

# --- structural: no key-taking backend method may skip the guard ----------------------
tree = ast.parse((pathlib.Path(__file__).parent / "src" / "aec_api" / "storage.py")
                 .read_text(encoding="utf-8"))
missing = []
for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name != "Backend"]:
    for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
        if fn.name.startswith("__") or not any(
                a.arg in ("key", "prefix") for a in fn.args.args):
            continue
        calls = {c.func.id for c in ast.walk(fn)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        calls |= {c.func.attr for c in ast.walk(fn)
                  if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
        if not ({"validate_key", "_p"} & calls):
            missing.append(f"{cls.name}.{fn.name}")

check("every key-taking backend method routes through the guard", not missing, ", ".join(missing))

# and that check must itself be able to fail
SYNTH = ("class Fake:\n"
         "    def get(self, key: str) -> bytes:\n"
         "        return self.client.get_object(Key=key)\n")
synth_missing = []
for cls in [n for n in ast.walk(ast.parse(SYNTH)) if isinstance(n, ast.ClassDef)]:
    for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
        if any(a.arg in ("key", "prefix") for a in fn.args.args):
            calls = {c.func.attr for c in ast.walk(fn)
                     if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
            if not ({"validate_key", "_p"} & calls):
                synth_missing.append(f"{cls.name}.{fn.name}")
check("the structural check fires on a backend that forgets", synth_missing == ["Fake.get"])

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"storage_key_parity OK — {len(local_refused)}/{len(KEYS)} keys refused identically by both "
      f"backends; every key-taking method guarded")
