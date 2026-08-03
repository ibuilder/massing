"""R28-ICDD — ISO 21597-1 Information Container for linked Document Delivery.

A standards-conformant *envelope*: a zip whose payload documents are ordinary files and whose
relationships between them are RDF, so another tool can open the container and follow the links
without knowing anything about this application. `.mass` can then simply **be** an ICDD container
carrying our extension — the branding without the lock-in.

The shape (ISO 21597-1):

    Index.rdf                  the container description — what documents are inside
    Payload documents/         the files themselves (IFC, PDF, images, our own JSON)
    Payload triples/           linksets: RDF naming relationships BETWEEN documents
    Ontology resources/        (see below — deliberately empty)

**We do not redistribute ISO specification text or the ISO ontology files.** The `Ontology
resources/` directory is left out and the container references the published ontology **URIs**,
which are public identifiers rather than specification content. This is implemented from the
published standard; see ATTRIBUTIONS.md.

Two refusals, both about containers that are broken while still parsing cleanly:

1. **a link may not name a document the container does not hold.** A linkset pointing at an absent
   document is the single most common way an ICDD is technically valid RDF and useless in practice —
   the consumer resolves the link and finds nothing. Refused at write time, naming the document;
2. **an element identifier must be non-empty.** A `ls:StringBasedIdentifier` carrying `""` links a
   document to *every* element or to none depending on the reader, and it costs nothing to reject.

Identity is the IFC **GlobalId**, never a viewer id or a row id — the same rule the rest of the
product runs on, expressed here as `ls:StringBasedIdentifier`.
"""
from __future__ import annotations

import posixpath
import zipfile
from datetime import datetime, timezone
from typing import Any

#: Published ISO 21597-1 vocabulary URIs. These are identifiers, not specification text.
CT = "https://standards.iso.org/iso/21597/-1/ed-1/en/Container#"
LS = "https://standards.iso.org/iso/21597/-1/ed-1/en/Linkset#"

INDEX_NAME = "Index.rdf"
PAYLOAD_DIR = "Payload documents"
TRIPLES_DIR = "Payload triples"

#: Conformance level this writer claims. ISO 21597-1 defines the container; part 2 adds extended
#: link types we do not emit, so claiming anything else would be a false statement about the file.
CONFORMANCE = "ICDD-Part1-Container"


class IcddError(ValueError):
    """A container that would be malformed — raised at write time, never written."""


def _graph():
    from rdflib import Graph, Namespace
    g = Graph()
    g.bind("ct", Namespace(CT))
    g.bind("ls", Namespace(LS))
    return g


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _doc_uri(name: str) -> str:
    return f"urn:massing:document:{name}"


def _safe_name(name: str) -> str:
    """A payload filename, flattened. Path separators and traversal are stripped rather than
    escaped: a container entry that writes outside its own directory is a zip-slip, and the only
    safe answer is for the name never to contain a path at all."""
    base = posixpath.basename(str(name or "").replace("\\", "/")).strip()
    base = base.replace("..", "").lstrip(".")
    if not base:
        raise IcddError("a payload document needs a filename")
    return base


def build_index(documents: list[dict], linksets: list[str], *, creator: str = "Massing",
                description: str = "", version: str = "1.0") -> str:
    """The container description — Index.rdf as Turtle-in-RDF/XML."""
    from rdflib import RDF, Literal, Namespace, URIRef

    ct = Namespace(CT)
    g = _graph()
    root = URIRef("urn:massing:container")
    g.add((root, RDF.type, ct.ContainerDescription))
    g.add((root, ct.conformanceIndicator, Literal(CONFORMANCE)))
    g.add((root, ct.createdBy, Literal(creator)))
    g.add((root, ct.creationDate, Literal(_now())))
    g.add((root, ct.versionID, Literal(str(version))))
    if description:
        g.add((root, ct.description, Literal(description)))

    for d in documents:
        u = URIRef(_doc_uri(d["name"]))
        g.add((u, RDF.type, ct.InternalDocument))
        g.add((u, ct.filename, Literal(f"{PAYLOAD_DIR}/{d['name']}")))
        if d.get("format"):
            # `ct.format` would return str.format — Namespace subclasses str, so a vocabulary word
            # that collides with a string method resolves to the METHOD, not a term. Item access
            # is the only form that is safe for arbitrary vocabulary.
            g.add((u, ct["format"], Literal(d["format"])))
        if d.get("description"):
            g.add((u, ct.description, Literal(d["description"])))
        g.add((root, ct.containsDocument, u))

    for name in linksets:
        u = URIRef(_doc_uri(name))
        g.add((u, RDF.type, ct.Linkset))
        g.add((u, ct.filename, Literal(f"{TRIPLES_DIR}/{name}")))
        g.add((root, ct.containsLinkset, u))
    return g.serialize(format="xml")


def build_linkset(links: list[dict]) -> str:
    """A linkset: relationships between documents, keyed by IFC GlobalId where an element is named.

    Each link is `{"elements": [{"document": <payload name>, "identifier": <GlobalId or None>}, …],
    "name": optional}`. Two or more elements per link — a link to one thing is not a link.
    """
    from rdflib import RDF, BNode, Literal, Namespace, URIRef

    ls = Namespace(LS)
    g = _graph()
    for n, link in enumerate(links):
        elements = link.get("elements") or []
        if len(elements) < 2:
            raise IcddError(f"link {n} has {len(elements)} element(s); a link relates at least two")
        lu = URIRef(f"urn:massing:link:{n}")
        g.add((lu, RDF.type, ls.Link))
        if link.get("name"):
            g.add((lu, ls.name, Literal(link["name"])))
        for el in elements:
            eu = BNode()
            g.add((lu, ls.hasLinkElement, eu))
            g.add((eu, RDF.type, ls.LinkElement))
            g.add((eu, ls.hasDocument, URIRef(_doc_uri(el["document"]))))
            ident = el.get("identifier")
            if ident is not None:
                if not str(ident).strip():
                    raise IcddError(
                        f"link {n} names an EMPTY identifier for {el['document']!r}; an empty "
                        "identifier resolves to every element or to none depending on the reader")
                iu = BNode()
                g.add((eu, ls.hasIdentifier, iu))
                g.add((iu, RDF.type, ls.StringBasedIdentifier))
                g.add((iu, ls.identifier, Literal(str(ident))))
                g.add((iu, ls.identifierField, Literal("GlobalId")))
    return g.serialize(format="xml")


def write_container(path: str, documents: list[dict], links: list[dict] | None = None, *,
                    creator: str = "Massing", description: str = "",
                    linkset_name: str = "links.rdf") -> dict[str, Any]:
    """Write an ISO 21597-1 container.

    `documents` is `[{"name", "data": bytes, "format"?, "description"?}]`. `links` is passed to
    `build_linkset`. Every document a link names must be present — see the module docstring.
    """
    docs = []
    for d in documents or []:
        name = _safe_name(d.get("name"))
        if d.get("data") is None:
            raise IcddError(f"document {name!r} has no data")
        docs.append({**d, "name": name})
    if not docs:
        raise IcddError("a container needs at least one payload document")

    names = {d["name"] for d in docs}
    dupes = len(docs) - len(names)
    if dupes:
        raise IcddError("two payload documents share a filename; the second would overwrite the first")

    links = list(links or [])
    for n, link in enumerate(links):
        for el in link.get("elements") or []:
            if el.get("document") not in names:
                raise IcddError(
                    f"link {n} references document {el.get('document')!r}, which is not in the "
                    f"container. A linkset that names an absent document parses cleanly and "
                    f"resolves to nothing — the container would be valid RDF and useless.")

    linksets = [linkset_name] if links else []
    index = build_index(docs, linksets, creator=creator, description=description)
    # Serialise the linkset BEFORE the archive is opened.
    #
    # It used to be built on the last line INSIDE the `with`, so any refusal `build_linkset` raises
    # (a link relating fewer than two elements, a malformed element reference) fired with the zip
    # already created and the index and every payload already written. The caller saw the exception
    # and reasonably assumed nothing had been written — but a truncated container was sitting on
    # disk, indistinguishable from a real one to anything that only checks for the file. **A refusal
    # that leaves a partial artefact is worse than no refusal**, because it converts a loud failure
    # into a quiet corruption.
    #
    # Everything that can refuse now refuses while `path` is still untouched.
    linkset_body = build_linkset(links) if links else None
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(INDEX_NAME, index)
        for d in docs:
            data = d["data"]
            z.writestr(f"{PAYLOAD_DIR}/{d['name']}",
                       data if isinstance(data, bytes) else str(data).encode("utf-8"))
        if linkset_body is not None:
            z.writestr(f"{TRIPLES_DIR}/{linkset_name}", linkset_body)
    return {"path": path, "documents": [d["name"] for d in docs],
            "linksets": linksets, "links": len(links), "conformance": CONFORMANCE}


def read_container(path: str) -> dict[str, Any]:
    """Read an ISO 21597-1 container back: its description, documents and resolved links.

    Parsed out of the RDF with rdflib rather than out of the zip's directory listing — a reader that
    trusts filenames is not reading the container, it is guessing at it, and would happily "read" a
    container whose Index.rdf says something entirely different from what the zip holds.
    """
    from rdflib import RDF, Namespace

    ct, ls = Namespace(CT), Namespace(LS)
    out: dict[str, Any] = {"documents": [], "links": [], "linksets": []}
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if INDEX_NAME not in names:
            raise IcddError(f"not an ICDD container: no {INDEX_NAME}")
        g = _graph()
        g.parse(data=z.read(INDEX_NAME), format="xml")

        root = next(g.subjects(RDF.type, ct.ContainerDescription), None)
        if root is None:
            raise IcddError("Index.rdf declares no ct:ContainerDescription")
        out["conformance"] = str(next(g.objects(root, ct.conformanceIndicator), "") or "")
        out["created_by"] = str(next(g.objects(root, ct.createdBy), "") or "")
        out["created"] = str(next(g.objects(root, ct.creationDate), "") or "")
        out["description"] = str(next(g.objects(root, ct.description), "") or "")

        by_uri: dict[str, str] = {}
        for d in g.objects(root, ct.containsDocument):
            fn = str(next(g.objects(d, ct.filename), "") or "")
            rec = {"uri": str(d), "filename": fn,
                   "name": posixpath.basename(fn),
                   "format": str(next(g.objects(d, ct["format"]), "") or ""),
                   "present": fn in names,
                   "size": z.getinfo(fn).file_size if fn in names else None}
            by_uri[str(d)] = rec["name"]
            out["documents"].append(rec)

        for lsdoc in g.objects(root, ct.containsLinkset):
            fn = str(next(g.objects(lsdoc, ct.filename), "") or "")
            out["linksets"].append(fn)
            if fn not in names:
                continue
            lg = _graph()
            lg.parse(data=z.read(fn), format="xml")
            for link in lg.subjects(RDF.type, ls.Link):
                els = []
                for el in lg.objects(link, ls.hasLinkElement):
                    doc = next(lg.objects(el, ls.hasDocument), None)
                    ident = None
                    for iu in lg.objects(el, ls.hasIdentifier):
                        ident = str(next(lg.objects(iu, ls.identifier), "") or "") or None
                    els.append({"document": by_uri.get(str(doc), str(doc)), "identifier": ident})
                els.sort(key=lambda e: (e["document"], e["identifier"] or ""))
                out["links"].append({"name": str(next(lg.objects(link, ls.name), "") or "") or None,
                                     "elements": els})
    out["links"].sort(key=lambda x: [(e["document"], e["identifier"] or "") for e in x["elements"]])
    out["document_count"] = len(out["documents"])
    out["missing_documents"] = [d["name"] for d in out["documents"] if not d["present"]]
    return out


def extract_document(path: str, name: str) -> bytes:
    """The bytes of one payload document, by its filename."""
    with zipfile.ZipFile(path) as z:
        return z.read(f"{PAYLOAD_DIR}/{_safe_name(name)}")
