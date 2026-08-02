"""R28-ICDD — an ISO 21597-1 container, asserted against the standard's vocabulary and not my reader.

**A writer and a reader written by the same person will agree on the wrong format.** Round-tripping
proves the two halves are consistent with each other, which is exactly what a proprietary format
does too. So the conformance assertions below parse the emitted RDF with a **fresh rdflib graph** and
query the published ISO 21597-1 URIs directly — `ct:ContainerDescription`, `ct:containsDocument`,
`ls:Link`, `ls:StringBasedIdentifier`. If the writer drifted to a private vocabulary, the round-trip
would still pass and these would not.

The other assertions are the two ways an ICDD is valid RDF and useless:

1. **a link naming a document the container does not hold** — the consumer resolves it and finds
   nothing. Refused at write time, naming the document;
2. **an empty element identifier** — resolves to every element or to none depending on the reader.

Plus zip-slip: a payload name is flattened, never escaped, because a container entry that writes
outside its own directory is the whole of that vulnerability class.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_icdd.py
"""
import os
import sys
import zipfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import icdd  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except icdd.IcddError as e:
        return str(e)
    except Exception as e:                    # noqa: BLE001 — wrong exception type is also a failure
        return f"__WRONG_TYPE__ {type(e).__name__}: {e}"


TMP = os.path.join(os.path.dirname(__file__), "_icdd_test.icdd")
# Clear artefacts from any previous run BEFORE asserting anything. The "nothing was written" checks
# below assert a file's ABSENCE, which a leftover from an earlier run turns into a spurious failure —
# a test whose result depends on the state the last run left behind is not measuring the code.
for _stale in (TMP, TMP + ".bad", TMP + ".bad2", TMP + ".bad3", TMP + ".b4", TMP + ".b5"):
    if os.path.exists(_stale):
        os.remove(_stale)
GUID_A = "2m4vrPBn1138pCMrdNYYM$"
GUID_B = "1owMJoFO9FS8X8BVDTH$Fg"

DOCS = [{"name": "model.ifc", "data": b"ISO-10303-21;\nENDSEC;\n", "format": "application/x-step"},
        {"name": "survey.pdf", "data": b"%PDF-1.7\n", "format": "application/pdf"},
        {"name": "schedule.json", "data": b'{"tasks":[]}', "format": "application/json"}]
LINKS = [{"name": "wall documented by survey",
          "elements": [{"document": "model.ifc", "identifier": GUID_A},
                       {"document": "survey.pdf"}]},
         {"name": "slab scheduled",
          "elements": [{"document": "model.ifc", "identifier": GUID_B},
                       {"document": "schedule.json"}]}]

res = icdd.write_container(TMP, DOCS, LINKS, description="R28 test container")
check("a container is written", os.path.exists(TMP) and res["links"] == 2, res)

# --- 1. THE ZIP USES THE STANDARD'S OWN DIRECTORY NAMES --------------------------------------------
with zipfile.ZipFile(TMP) as z:
    entries = set(z.namelist())
check("Index.rdf sits at the container root", "Index.rdf" in entries, sorted(entries))
check("payloads live in 'Payload documents/'",
      {"Payload documents/model.ifc", "Payload documents/survey.pdf"} <= entries, sorted(entries))
check("linksets live in 'Payload triples/'", "Payload triples/links.rdf" in entries, sorted(entries))
check("no ISO ontology files are redistributed",
      not any(e.startswith("Ontology resources/") for e in entries),
      [e for e in entries if e.startswith("Ontology")])

# --- 2. CONFORMANCE, ASSERTED AGAINST THE ISO VOCABULARY BY A GRAPH I DID NOT WRITE -----------------
from rdflib import RDF, Graph, Namespace  # noqa: E402

CT, LS = Namespace(icdd.CT), Namespace(icdd.LS)
with zipfile.ZipFile(TMP) as z:
    gi = Graph()
    gi.parse(data=z.read("Index.rdf"), format="xml")
    gl = Graph()
    gl.parse(data=z.read("Payload triples/links.rdf"), format="xml")

roots = list(gi.subjects(RDF.type, CT.ContainerDescription))
check("Index.rdf declares exactly one ct:ContainerDescription", len(roots) == 1, roots)
root = roots[0]
check("  it states a conformance indicator",
      str(next(gi.objects(root, CT.conformanceIndicator), "")) == icdd.CONFORMANCE)
check("  and a creation date and creator",
      bool(str(next(gi.objects(root, CT.creationDate), "")))
      and bool(str(next(gi.objects(root, CT.createdBy), ""))))

declared = {str(next(gi.objects(d, CT.filename), "")) for d in gi.objects(root, CT.containsDocument)}
check("ct:containsDocument names EVERY payload — set equality, both directions",
      declared == {f"Payload documents/{d['name']}" for d in DOCS}, sorted(declared))
check("  each is typed ct:InternalDocument",
      all((d, RDF.type, CT.InternalDocument) in gi for d in gi.objects(root, CT.containsDocument)))
check("ct:containsLinkset names the linkset, typed ct:Linkset",
      [str(next(gi.objects(x, CT.filename), "")) for x in gi.objects(root, CT.containsLinkset)]
      == ["Payload triples/links.rdf"])

# A trap worth a standing assertion rather than a comment: rdflib's Namespace subclasses `str`, so
# attribute access for a vocabulary word that collides with a string method returns the METHOD.
# `ct.format` is `str.format`, and adding it as a predicate raises. Item access is the only form
# safe for arbitrary vocabulary — this fails loudly if someone "tidies" the writer back to dots.
from rdflib import URIRef  # noqa: E402

check("rdflib Namespace attribute access is UNSAFE for a word like 'format' (it is str.format)",
      not isinstance(getattr(CT, "format", None), URIRef), type(getattr(CT, "format", None)))
check("  so the container must still emit the real …Container#format predicate",
      any(str(p) == icdd.CT + "format" for p in gi.predicates()),
      sorted({str(p) for p in gi.predicates()}))

# every document the index declares must actually be in the zip — the index is a claim about the zip
check("EVERY DECLARED DOCUMENT IS REALLY PRESENT in the archive", declared <= entries,
      sorted(declared - entries))

links = list(gl.subjects(RDF.type, LS.Link))
check("the linkset declares ls:Link for each link", len(links) == 2, len(links))
els = [e for lk in links for e in gl.objects(lk, LS.hasLinkElement)]
check("  every link element is typed ls:LinkElement",
      all((e, RDF.type, LS.LinkElement) in gl for e in els) and len(els) == 4, len(els))
idents = set()
for e in els:
    for iu in gl.objects(e, LS.hasIdentifier):
        check_type = (iu, RDF.type, LS.StringBasedIdentifier) in gl
        check("  an identifier is a ls:StringBasedIdentifier", check_type)
        idents.add(str(next(gl.objects(iu, LS.identifier), "")))
check("THE IDENTIFIERS ARE THE IFC GlobalIds", idents == {GUID_A, GUID_B}, sorted(idents))
check("  and the identifier field is named GlobalId, not left to the reader to guess",
      {str(o) for iu in gl.subjects(RDF.type, LS.StringBasedIdentifier)
       for o in gl.objects(iu, LS.identifierField)} == {"GlobalId"})

# --- 3. THE ROUND TRIP (necessary, but not what proves conformance) --------------------------------
back = icdd.read_container(TMP)
check("read_container returns every document", {d["name"] for d in back["documents"]}
      == {d["name"] for d in DOCS}, back["documents"])
check("  with nothing reported missing", back["missing_documents"] == [], back["missing_documents"])
check("  formats survive", {d["name"]: d["format"] for d in back["documents"]}
      == {d["name"]: d["format"] for d in DOCS})
check("  the description survives", back["description"] == "R28 test container", back["description"])
got = {(tuple(sorted((e["document"], e["identifier"] or "") for e in lk["elements"])))
       for lk in back["links"]}
want = {(tuple(sorted((e["document"], e.get("identifier") or "") for e in lk["elements"])))
        for lk in LINKS}
check("LINKS ROUND-TRIP EXACTLY — set equality both ways", got == want, (got, want))
check("payload bytes come back unchanged",
      icdd.extract_document(TMP, "model.ifc") == DOCS[0]["data"])

# --- 4. THE REFUSALS -------------------------------------------------------------------------------
msg = raises(icdd.write_container, TMP + ".bad", DOCS,
             [{"elements": [{"document": "model.ifc"}, {"document": "nope.pdf"}]}])
check("a link naming an ABSENT document is refused", bool(msg) and "not in the container" in (msg or ""),
      msg)
check("  and the refusal explains it would be valid RDF and useless",
      "valid RDF and useless" in (msg or ""), msg)
check("  nothing was written", not os.path.exists(TMP + ".bad"))

msg = raises(icdd.write_container, TMP + ".bad2", DOCS,
             [{"elements": [{"document": "model.ifc", "identifier": "  "},
                            {"document": "survey.pdf"}]}])
check("an EMPTY identifier is refused", bool(msg) and "EMPTY identifier" in (msg or ""), msg)

msg = raises(icdd.write_container, TMP + ".bad3", DOCS,
             [{"elements": [{"document": "model.ifc", "identifier": GUID_A}]}])
check("a 'link' relating ONE thing is refused — that is not a link", bool(msg)
      and "at least two" in (msg or ""), msg)

check("a container with no documents is refused", bool(raises(icdd.write_container, TMP + ".b4", [])))
check("a document with no data is refused",
      bool(raises(icdd.write_container, TMP + ".b5", [{"name": "x.txt"}])))

# --- 5. ZIP-SLIP: the name is FLATTENED, never escaped ---------------------------------------------
SLIP = os.path.join(os.path.dirname(__file__), "_icdd_slip.icdd")
icdd.write_container(SLIP, [{"name": "../../../../etc/passwd", "data": b"x"}])
with zipfile.ZipFile(SLIP) as z:
    payload = [e for e in z.namelist() if e.startswith("Payload documents/")]
check("a traversing filename is flattened to a bare name",
      payload == ["Payload documents/etc/passwd"] or payload == ["Payload documents/passwd"],
      payload)
check("  and no entry escapes the payload directory",
      all(".." not in e for e in zipfile.ZipFile(SLIP).namelist()),
      zipfile.ZipFile(SLIP).namelist())

# --- 6. NOT AN ICDD ---------------------------------------------------------------------------------
NOT = os.path.join(os.path.dirname(__file__), "_icdd_not.zip")
with zipfile.ZipFile(NOT, "w") as z:
    z.writestr("hello.txt", "not a container")
check("a zip with no Index.rdf is refused, not silently read as empty",
      "not an ICDD container" in (raises(icdd.read_container, NOT) or ""),
      raises(icdd.read_container, NOT))

for f in (TMP, SLIP, NOT):
    if os.path.exists(f):
        os.remove(f)

print()
if FAILED:
    print(f"icdd: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("icdd: all checks passed")
