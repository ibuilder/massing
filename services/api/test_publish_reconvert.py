"""R42 — `reconvert=false` skips the fragment convert, and until v0.3.906 it did not.

THE DEFECT. `POST /projects/{pid}/publish` has taken `reconvert: bool = Body(default=True)` since it
shipped, and `_publish(p, reconvert)` has honoured it. The two were never connected: `run_publish`
called `_publish(p)` and took the default, so **the route accepted a parameter nothing read**. Every
`reconvert=false` reconverted anyway.

Same family as the `lod_target` fields the matrix projection dropped and the four review keys
`modelVersions` discarded — a value a caller can set that no code consumes. It is worth its own test
rather than a quiet fix because the R42 ring turns on exactly this switch: an incremental commit
reindexes WITHOUT reconverting, and the switch for that was already here and disconnected.

WHY THE TEST PATCHES `subprocess.run` RATHER THAN TIMING THE CALL. A timing assertion would pass
vacuously wherever the converter is absent — which is most CI containers — and `_publish` skips the
convert when `_CONVERTER` does not exist. Asserting on the SUBPROCESS makes the claim regardless of
whether a converter is installed, and it is the actual thing being skipped.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_publish_reconvert.py
"""
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_publish_reconvert.db"
os.environ["STORAGE_DIR"] = "./test_storage_pubreconv"
os.environ["IFC_DIR"] = tempfile.mkdtemp(prefix="pubreconv_ifc_")
for _f in ("./test_publish_reconvert.db",):
    if os.path.exists(_f):
        os.remove(_f)

from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

from aec_api.routers import authoring  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


class FakeProject:
    """Only the two attributes `_publish` reads. A real Project would drag in the DB for a question
    that is purely about which subprocess runs."""

    id = "p-reconvert"
    source_ifc = ""


# A file that EXISTS — `_publish` skips the convert for a missing source, which would make the
# reconvert=True half pass for the wrong reason.
src = Path(os.environ["IFC_DIR"]) / "m.ifc"
src.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
proj = FakeProject()
proj.source_ifc = str(src)


def publish_with(reconvert: bool):
    """Run `_publish` with the converter present, counting node invocations."""
    calls = []

    def fake_run(cmd, *a, **kw):
        calls.append(cmd)
        # `_publish` reads the output file after a successful run; make one so the happy path is real.
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"FRAG")
        return mock.Mock(returncode=0, stdout=b"", stderr=b"")

    # `properties_index.index_file` on a stub IFC is the part under test least of all — stub it so a
    # parse failure cannot be mistaken for a convert decision.
    fake_idx = {"counts": {"elements": 0}, "elements": [], "facets": {}, "project": {}}
    with mock.patch.object(authoring.subprocess, "run", side_effect=fake_run), \
         mock.patch.object(authoring, "_CONVERTER", Path(__file__)), \
         mock.patch("aec_data.properties_index.index_file", return_value=dict(fake_idx)), \
         mock.patch.object(authoring.storage, "put", lambda *a, **k: None), \
         mock.patch.object(authoring.props_router, "_load", lambda *a, **k: None):
        out = authoring._publish(proj, reconvert=reconvert)
    return out, calls


# ---- the pair. Neither half means anything without the other. -----------------------------------
out_t, calls_t = publish_with(True)
check("reconvert=True runs the converter", len(calls_t) == 1, f"{len(calls_t)} subprocess call(s)")
check("...and reports that it reconverted", out_t.get("reconverted") is True, str(out_t))

out_f, calls_f = publish_with(False)
check("reconvert=False does NOT run the converter", calls_f == [], str(calls_f))
check("...and does not claim it reconverted", out_f.get("reconverted") is False, str(out_f))

# ---- the half that must still happen. A skip that skips EVERYTHING is not a partial publish. ----
check("reconvert=False still reindexes", "reindexed" in out_f, str(out_f))

# ---- the wiring itself: the flag must reach `_publish` from the pool, not just be accepted -------
# Asserting the signature is not enough — the defect was a CALL that omitted the argument, which no
# signature check can see. This drives `run_publish` and observes what `_publish` was handed.
seen = {}


def spy_publish(p, reconvert=True):
    seen["reconvert"] = reconvert
    return {"reconverted": False, "reindexed": 0}


class _DB:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, *_a):
        return proj


with mock.patch.object(authoring, "_publish", spy_publish), \
     mock.patch("aec_api.db.SessionLocal", lambda: _DB()), \
     mock.patch.object(authoring, "_set_pub_status", lambda *a, **k: None):
    authoring.run_publish("p-reconvert", reconvert=False)
check("run_publish HANDS the flag to _publish (the line that was wrong)",
      seen.get("reconvert") is False, str(seen))
with mock.patch.object(authoring, "_publish", spy_publish), \
     mock.patch("aec_api.db.SessionLocal", lambda: _DB()), \
     mock.patch.object(authoring, "_set_pub_status", lambda *a, **k: None):
    authoring.run_publish("p-reconvert")
check("...and still defaults to True when nobody asks", seen.get("reconvert") is True, str(seen))

print(f"\ntest_publish_reconvert {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
