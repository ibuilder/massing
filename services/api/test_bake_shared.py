"""
Baked geometry shared across worker processes.

The byte budget bounds ONE worker. A server runs several, and a dict cannot span processes, so the
same model was tessellated once per worker — the most expensive operation in the system, paid N times
for nothing.

This is where `diskcache` earns its dependency: the store has to be correct when several processes
write the same key at once, and hand-rolling that over SQLite is the class of code that passes tests
and corrupts under load. `cachetools` was declined for the in-process half precisely because that
trade went the other way.
"""
import os
import sys
import tempfile

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def fresh(env_dir=None):
    """Re-import with a chosen environment — the module memoises its store deliberately.

    `importlib.reload`, NOT `sys.modules.pop` + `from aec_data import bake_shared`: the parent
    package keeps an attribute pointing at the old module object, so the plain import hands back the
    stale one and every assertion afterwards measures the previous environment. Cost me a full round
    of "the product is broken" before the product turned out to be fine.
    """
    import importlib

    if env_dir is None:
        os.environ.pop("AEC_BAKE_SHARE_DIR", None)
    else:
        os.environ["AEC_BAKE_SHARE_DIR"] = env_dir
    from aec_data import bake_shared
    return importlib.reload(bake_shared)


# --- off by default -------------------------------------------------------------------------------
bs = fresh(None)
check("sharing is OFF unless a directory is chosen", bs.enabled() is False,
      "a cache that silently writes gigabytes somewhere the operator did not pick is a surprise")
check("a read while disabled is a clean miss, not an error", bs.get("k") is None)
check("a write while disabled reports that it did not store", bs.put("k", [1]) is False)
check("stats say why it is off", bs.stats().get("enabled") is False and "reason" in bs.stats())

# --- on, and it actually round-trips ---------------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    bs = fresh(d)
    check("sharing is ON once a directory is set", bs.enabled() is True)
    check("a miss is None before anything is stored", bs.get("model-A") is None)

    payload = [("IfcWall", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], [[0, 1, 0]])]
    check("a store reports success", bs.put("model-A", payload) is True)
    got = bs.get("model-A")
    check("what comes back is what went in", got == payload)
    check("a different key is still a miss", bs.get("model-B") is None)

    store = bs._store()
    check("the on-disk codec is JSONDisk, not pickle Disk",
          store is not None and type(store.disk).__name__ == "JSONDisk",
          type(getattr(store, "disk", None)).__name__ if store else "no store")
    # POSIX mode bits, where they exist.
    #
    # On Windows this assertion is not merely likely to fail, it is UNSATISFIABLE: NTFS has no mode
    # bits, `os.chmod` toggles only the read-only flag, and `st_mode & 0o777` reports 0o777 no matter
    # what the ACL says. It failed on every local run for exactly that reason — and a suite that is
    # permanently red on the developer's own machine trains everyone to read red as normal, which
    # costs more than this one assertion is worth.
    #
    # So it is SKIPPED rather than softened, and the skip is printed rather than silent. The claim
    # itself is not weakened: CI runs on ubuntu, where this is a real check, and the container the
    # cache actually ships in is Linux. Windows is a dev box. Deliberately NOT `check(..., True)` on
    # Windows — a green line for a check that never ran is the failure mode this repo keeps writing
    # tests about.
    if os.name == "nt":
        print("SKIP  the cache directory is mode 0700 — NTFS has no POSIX mode bits, so "
              "st_mode is meaningless here; ubuntu CI is what holds this claim")
    else:
        mode = os.stat(d).st_mode & 0o777
        check("the cache directory is mode 0700 (owner-only)", mode == 0o700, oct(mode))

    four = [("2O2Fr$t4X7Zf8NOew3FNrX", "IfcWall",
             [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], [[0, 1, 0]])]
    check("a 4-tuple row (guid, class, verts, faces) round-trips",
          bs.put("model-4", four) is True and bs.get("model-4") == four)
    check("bytes in the mesh are refused rather than pickled",
          bs.put("model-bin", [("IfcWall", b"nope", [[0, 1, 0]])]) is False)

    st = bs.stats()
    check("the cache can be measured", st.get("enabled") and st.get("entries", 0) >= 1,
          f"entries={st.get('entries')} bytes={st.get('bytes')}")

    # --- a SECOND process must see the first one's work: the whole point --------------------------
    import subprocess
    code = (
        "import os,sys; os.environ['AEC_BAKE_SHARE_DIR']={!r}; sys.path.insert(0,{!r});"
        "from aec_data import bake_shared as b; v=b.get('model-A');"
        "print('HIT' if v=={!r} else 'MISS')".format(d, os.path.abspath("../data/src"), payload)
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    check("a SEPARATE PROCESS reads the same entry", "HIT" in out.stdout,
          (out.stdout + out.stderr).strip()[:160] or "no output")

    bs.close()      # Windows will not delete a directory whose SQLite file is still open

# --- an unusable directory must degrade, never break rendering ---------------------------------------
#
# The path must be invalid for OPENING while remaining an ordinary string. A null byte is not: on
# Linux `os.environ[...] = "\0..."` raises `ValueError: embedded null byte` at the ASSIGNMENT, before
# the code under test runs at all. The first version therefore tested the harness — it passed on
# Windows, which tolerates it, and failed on the Linux gate. Pointing a directory path *inside an
# existing file* fails identically on every platform, and fails for the reason we actually care about.
_blocker = tempfile.NamedTemporaryFile(delete=False)
_blocker.write(b"not a directory")
_blocker.close()

bs = fresh(os.path.join(_blocker.name, "cache"))
check("an unopenable cache degrades to no-sharing", bs.get("k") is None)
check("...and a write reports failure rather than raising", bs.put("k", [1]) is False)
check("...and stats explain it", bs.stats().get("enabled") is False)

os.environ.pop("AEC_BAKE_SHARE_DIR", None)
os.unlink(_blocker.name)

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_bake_shared OK")
