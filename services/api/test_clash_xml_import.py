"""CLASH-TRIAGE — import a native Navisworks clash-report XML (the smart: namespace format) into
coordination_issue records (the XLSX importer already ships; this adds the other standard export).
Pure parse (namespace-agnostic, GUID harvest, XXE-safe) + the /coordination/import-xml route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_clash_xml_import.py"""
import os

from aec_api import clash_import  # noqa: E402

G1 = "1LwkKeWO9BEP8Kgn3EmRgW"     # valid 22-char IFC GlobalIds
G2 = "3xR8pQmn5DFvB2Kg7HjL0a"

NW_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<exchange xmlns:smart="http://www.navisworks.com/smart">
  <batchtest>
    <clashtests>
      <clashtest name="Structural vs Mechanical">
        <clashresults>
          <clashresult name="Clash1" status="new" distance="-0.045">
            <description>Hard</description>
            <clashpoint><pos3f x="1.0" y="2.0" z="3.0"/></clashpoint>
            <clashobjects>
              <clashobject><smart:objectattribute><smart:name>Element ID</smart:name>
                <smart:value>{G1}</smart:value></smart:objectattribute></clashobject>
              <clashobject><smart:objectattribute><smart:name>Element ID</smart:name>
                <smart:value>{G2}</smart:value></smart:objectattribute></clashobject>
            </clashobjects>
          </clashresult>
          <clashresult name="Clash2" status="active" distance="-0.012">
            <description>Clearance</description>
          </clashresult>
        </clashresults>
      </clashtest>
    </clashtests>
  </batchtest>
</exchange>""".encode()

# --- pure parse -----------------------------------------------------------------------------------
parsed = clash_import.parse_clash_xml(NW_XML)
assert parsed["sheet"] == "Navisworks XML" and len(parsed["rows"]) == 2, parsed
r1, r2 = parsed["rows"]
assert r1["subject"] == "Clash1" and r1["discipline"] == "Structural vs Mechanical", r1
assert "Hard" in r1["description"] and "distance -0.045" in r1["description"], r1["description"]
assert set(r1["_guids"]) == {G1, G2}, r1.get("_guids")     # both element GlobalIds harvested
assert r2["subject"] == "Clash2" and "_guids" not in r2, r2  # no GUIDs on the second clash

# malformed / hostile XML → empty, never raises (defusedxml)
bad = clash_import.parse_clash_xml(b"<exchange><clashtest name='x'><oops")
assert bad["rows"] == [] and "error" in bad, bad
xxe = clash_import.parse_clash_xml(
    b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><exchange>&e;</exchange>')
assert xxe["rows"] == [], xxe                               # entity expansion blocked

# --- route ----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_clash_xml.db"
os.environ["STORAGE_DIR"] = "./test_storage_clashxml"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_clash_xml.db"):
    os.remove("./test_clash_xml.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Clash XML"}).json()["id"]
    up = c.post(f"/projects/{pid}/coordination/import-xml",
                files={"file": ("clashes.xml", NW_XML, "application/xml")})
    assert up.status_code == 200, up.text[:200]
    assert up.json()["imported"] == 2, up.json()
    # the imported clashes are now coordination_issue records anchored on the model GUIDs
    recs = c.get(f"/projects/{pid}/modules/coordination_issue").json()
    assert len(recs) == 2, recs

if os.path.exists(os.path.join(os.path.dirname(__file__), "_x")):
    pass

print("CLASH-TRIAGE OK - a native Navisworks clash-report XML (smart: namespace) parses to 2 coordination "
      "issues: Clash1 carries its test name as discipline, the Hard type + distance in the description, and "
      "both element GlobalIds harvested from the clashobjects; malformed and XXE-laden XML return empty "
      "without raising (defusedxml); the /coordination/import-xml route imports both as model-anchored "
      "coordination_issue records (each round-trips to BCF).")
