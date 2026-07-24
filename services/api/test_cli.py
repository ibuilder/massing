"""The headless ``massing`` CLI — new (blank model), run (edit recipe), and the check CI gate
(exit 1 on constraint errors with --gate), plus the pre-existing export commands still working.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cli.py"""
import contextlib
import io
import json
import tempfile
from pathlib import Path

from aec_data import cli
from aec_data.ifc_loader import open_model

TMP = Path(tempfile.gettempdir())
model = TMP / "cli_model.ifc"
for f in (model, TMP / "cli_model_edited.ifc", TMP / "cli_props.json"):
    if f.exists():
        f.unlink()


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


# --- new: a blank authoring model with the requested levels ----------------------------------------
code, out = run_cli("new", str(model), "--storeys", "2", "--height", "3.2", "--name", "CLI Test")
assert code == 0 and "2 storeys @ 3.2 m" in out, (code, out)
m = open_model(str(model))
assert len(m.by_type("IfcBuildingStorey")) == 2
assert m.by_type("IfcProject")[0].Name == "CLI Test"

# --- run: apply a GUID-stable recipe headlessly ----------------------------------------------------
code, out = run_cli("run", str(model), "--recipe", "add_wall",
                    "--params", json.dumps({"start": [0, 0], "end": [8, 0], "height": 3.0,
                                            "storey": "Level 1"}))
assert code == 0 and "_edited.ifc" in out, (code, out)
edited = TMP / "cli_model_edited.ifc"
assert edited.exists() and len(open_model(str(edited)).by_type("IfcWall")) == 1

# unknown recipe / bad JSON → exit 2 with a useful stderr, nothing written
err = io.StringIO()
with contextlib.redirect_stderr(err):
    assert run_cli("run", str(model), "--recipe", "nope")[0] == 2
    assert run_cli("run", str(model), "--recipe", "add_wall", "--params", "{bad")[0] == 2
assert "unknown recipe" in err.getvalue() and "not valid JSON" in err.getvalue(), err.getvalue()

# --- check: healthy model passes; a broken one fails ONLY with --gate ------------------------------
code, out = run_cli("check", str(edited))
assert code == 0 and "0 error(s)" in out, (code, out)

# break it: cut an opening then delete the host wall → orphan_opening ERROR
from aec_data import edit  # noqa: E402

m2 = open_model(str(edited))
wall_guid = m2.by_type("IfcWall")[0].GlobalId
edit.add_opening(m2, wall_guid, width=0.9, height=2.1, kind="door")
m2.remove(m2.by_type("IfcWall")[0])
broken = TMP / "cli_broken.ifc"
m2.write(str(broken))
code, out = run_cli("check", str(broken))                      # report-only: exit 0, errors listed
assert code == 0 and "orphan_opening" in out, (code, out)
code, _ = run_cli("check", str(broken), "--gate")              # the CI gate: exit 1 on errors
assert code == 1
code, out = run_cli("check", str(broken), "--json")            # machine-readable report
assert code == 0 and json.loads(out)["errors"] >= 1

# --- the pre-existing export surface still works under the subparser rewrite -----------------------
code, out = run_cli("index", str(edited), str(TMP / "cli_props.json"))
assert code == 0 and (TMP / "cli_props.json").exists(), (code, out)

for f in (model, edited, broken, TMP / "cli_props.json"):
    if f.exists():
        f.unlink()

print("MASSING-CLI OK - `new` writes a blank 2-storey model (project name honored); `run` applies "
      "add_wall headlessly into <stem>_edited.ifc (unknown recipe / bad JSON exit 2 with stderr help); "
      "`check` reports a healthy model clean, lists an orphan_opening error report-only, fails (exit 1) "
      "only with --gate, and --json emits the machine-readable report; the pre-existing export commands "
      "(index) survive the subparser rewrite unchanged.")
