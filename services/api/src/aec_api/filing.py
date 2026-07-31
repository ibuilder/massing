"""R32 — file the platform's OWN output into the controlled document tree.

Everything the document layer already implements — revision, supersession, standard naming, CDE state,
an audit trail — was unavailable to exactly the artefacts the platform itself produces. The model lived
at ``{pid}/source.ifc`` and the documents at ``{pid}/docs/<folder>/``: two parallel stores, so the one
artefact everything else derives from had no revision and did not appear in the file manager at all.
Generated sheets and specs were produced, returned to the caller, and never filed.

This module is the missing caller. It owns **no** storage logic of its own — `docmanager.upload()`
already does naming, supersession and the index write under the per-project lock. What was missing was
something that called it.

## Two rules this module exists to keep

**1. File on PUBLISH, never on save.** ``source.ifc`` is rewritten by every edit recipe. Filing on each
write would produce a revision per keystroke and make the revision chain meaningless — a document
revision has to correspond to a deliberate act. So the trigger is issuance, or an explicit request, and
never the storage write itself.

**2. File by KIND, into the folder that kind already uses.** A generated drawing goes to
``02_Drawings/<discipline>`` beside the hand-uploaded ones, and a generated spec to
``01_Contract Documents/Specifications``. There is deliberately no "Generated Drawings" folder: a
separate silo for generated output would rebuild the same two-parallel-stores problem this work exists
to remove, and would split "the current drawing set" across two places again — which is precisely what
R32-CURRENT-SET then has to reconcile.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from . import docmanager, storage

#: Where the authored/as-issued model is filed. Its sibling `12_Model/Federated` holds combined
#: coordination models, which are produced elsewhere and are not this function's business.
MODEL_FOLDER = "12_Model/IFC"

#: The source model's storage key, matching what the authoring and generate routers write.
MODEL_KEY = "{pid}/source.ifc"


class NothingToFile(ValueError):
    """The artefact asked for does not exist yet — reported, never silently treated as 'filed nothing'."""


def model_key(pid: str) -> str:
    return MODEL_KEY.format(pid=storage.safe_seg(pid))


def has_model(pid: str) -> bool:
    return storage.exists(model_key(pid))


def file_model(pid: str, actor: str, *, title: str = "Federated Model",
               discipline: str | None = None, cde_state: str = "published",
               when: datetime | None = None) -> dict[str, Any]:
    """File the project's current ``source.ifc`` into ``12_Model/IFC`` as a new revision.

    Returns `docmanager.upload()`'s result — the new entry, the naming verdict, and the id of the
    revision it superseded (``None`` on the first issue). Raises `NothingToFile` when the project has
    no model, rather than filing an empty document: a zero-byte IFC that supersedes a real one is a
    far worse outcome than a refusal, and a caller that ignores the error still gets no phantom entry.

    `title` is what makes supersession work — `docmanager` matches a prior revision on (folder, title),
    so re-filing under the same title supersedes rather than accumulating. Callers that file per
    discipline must vary the title, not the folder.
    """
    key = model_key(pid)
    if not storage.exists(key):
        raise NothingToFile(
            f"project {pid} has no model at {key} — author or upload one before filing it")
    data = storage.get(key)
    if not data:
        raise NothingToFile(f"the model at {key} is empty — refusing to file a zero-byte revision")
    return docmanager.upload(
        pid, MODEL_FOLDER, "source.ifc", data, actor,
        title=title, discipline=discipline, doc_type="MODEL", cde_state=cde_state, when=when)


# --- R32-FILE-GENERATED: the drawings the platform produces enter the same tree ---------------------
#: Generated sheets file where drawings already live. See rule 2 in the module docstring — there is no
#: `Generated Drawings` folder, and `test_filed_output` asserts none exists.
DRAWINGS_FOLDER = "02_Drawings"

#: The set's title is CONSTANT on purpose. `docmanager` supersedes on (folder, title), so every issue of
#: the set becomes the next revision of one document — P01, P02, … — which is what makes "the current
#: set" answerable from the document tree instead of from a second register. A transmittal, by contrast,
#: is titled per issuance: it records one release and must never supersede the release before it.
SET_TITLE = "Drawing Set"


def file_transmittal(db, pid: str, issuance_id: str, project_name: str, actor: str,
                     *, when: datetime | None = None) -> dict[str, Any]:
    """File one issuance's transmittal — the record of exactly what was released, and to whom.

    Cheap: `issuance.transmittal_pdf` renders from the stored snapshot and needs no model, so this can
    run on every issue. Titled with the issuance number so each release is its own document; a
    transmittal that superseded its predecessor would destroy the very history it exists to provide.
    """
    from . import issuance  # local: issuance imports filing back for the hook
    iss = next((i for i in issuance._issuances(db, pid) if i["id"] == issuance_id), None)
    if not iss:
        raise NothingToFile(f"issuance {issuance_id} not found on project {pid}")
    pdf = issuance.transmittal_pdf(db, pid, issuance_id, project_name)
    title = f"Transmittal {iss.get('number') or issuance_id}"
    return docmanager.upload(pid, DRAWINGS_FOLDER, f"{title}.pdf", pdf, actor,
                             title=title, doc_type="TRANSMTL", cde_state="published", when=when)


def file_drawing_set(pid: str, source_ifc: str, project_name: str, actor: str,
                     *, scale: int = 200, max_sheets: int = 16,
                     when: datetime | None = None) -> dict[str, Any]:
    """Compile the current drawing set to one PDF and file it as the next revision of `SET_TITLE`.

    Expensive — `compiled_set_pdf` renders every sheet and merges them — so this is a deliberate act,
    never a side effect of issuing. Kept separate from `file_transmittal` for exactly that reason: the
    cheap record of a release should not be hostage to a slow render.
    """
    from . import drawingset
    if not source_ifc:
        raise NothingToFile("no source model supplied — a drawing set is rendered FROM the model")
    pdf = drawingset.compiled_set_pdf(source_ifc, project_name, scale=scale, max_sheets=max_sheets)
    if not pdf:
        raise NothingToFile("the compiled set came back empty — refusing to file a zero-page set")
    return docmanager.upload(pid, DRAWINGS_FOLDER, "drawing-set.pdf", pdf, actor,
                             title=SET_TITLE, doc_type="DWGSET", cde_state="published", when=when)


def filed_model_history(pid: str) -> list[dict[str, Any]]:
    """Every revision of the model ever filed, newest first — superseded ones included.

    Deliberately includes superseded entries: the point of filing the model is that the *as-issued*
    version is recoverable, so a history that showed only the current one would answer the easy
    question and lose the reason for doing this at all.

    Ordered by the index sequence, **not** by `uploaded_at`. That timestamp is written to
    second resolution, so two revisions filed in the same second compare equal and the order becomes
    whatever the sort happened to do — which is exactly what a republish-then-refile does, and what the
    test caught. `id` is `f<seq>` from a monotonic counter, so it is the real insertion order; it is
    parsed as an int because string ordering puts `f10` before `f9`.
    """
    idx = docmanager.list_folder(pid, MODEL_FOLDER, include_superseded=True)
    files = [f for f in (idx.get("files") or []) if not f.get("deleted")]

    def _seq(f: dict[str, Any]) -> int:
        try:
            return int(str(f.get("id") or "f0")[1:])
        except ValueError:                       # an id that is not f<n> sorts oldest, never crashes
            return 0
    return sorted(files, key=_seq, reverse=True)
