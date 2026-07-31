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
