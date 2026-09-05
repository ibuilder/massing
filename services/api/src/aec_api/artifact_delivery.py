"""Mailing a finished job's artifact — the part both the route and the worker need.

R24-REPORTS-BY-MOMENT. `POST /projects/{pid}/jobs/{job_id}/deliver` has done this since v0.3.1144,
and every line of it lived INSIDE the route function: the recipient normalisation, the two caps, the
size-before-read, the message build, the per-recipient status map and the audit record. That is fine
while a person clicking **Send** is the only way an artifact leaves.

It stopped being fine when routines learned to schedule a report package. A scheduled package is
assembled by the worker and then sits in the job tray, and *the whole point of scheduling the owner's
monthly package is that nobody has to remember it*. The worker cannot call a FastAPI route function:
it has no request, no `Depends`, and raising `HTTPException` from a background thread converts a
delivery problem into a 500 nobody sees. So the reusable half moves here and the route keeps only the
half that is genuinely about HTTP.

**What stayed in the route, deliberately.** The "is this artifact ready" refusals — 404 for a job in
another project, 409 while it is queued or running, 404 when it produced no artifact — are answers to
a question only an outside caller asks. The worker is holding the job it just ran; it knows.

**Refusals are raised, not returned.** `DeliveryRefused` carries the status the route already used,
so the HTTP behaviour is unchanged and `test_artifact_deliver.py` — which drives the real route —
is what proves the extraction did not alter it. The worker catches the same exception and records it
on the job row instead.
"""
from __future__ import annotations

from typing import Any

#: A synchronous SMTP conversation per recipient with a 15-second timeout, so an unbounded list is a
#: request that occupies a worker for hours. The cap is a REFUSAL, not a silent trim: quietly
#: dropping recipients is the failure an empty-list refusal exists to avoid, one level up.
MAX_RECIPIENTS = 25

#: Checked BEFORE the object is read. `storage.get` materialises the whole thing, so checking
#: `len(data)` afterwards spends the memory on exactly the payload being refused — and concurrent
#: callers multiply it.
MAX_BYTES = 15 * 1024 * 1024


class DeliveryRefused(Exception):
    """A refusal with the HTTP status the route has always used for it.

    Carrying the status here rather than raising `HTTPException` is what lets the worker share this
    code: it catches the same exception and writes `detail` onto the job row, where a scheduled
    delivery's failure is visible without anyone watching a response.
    """

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


def recipients(to: Any) -> list[str]:
    """Normalise, de-duplicate and cap a recipient list, or raise `DeliveryRefused`.

    De-duplication is case-insensitive on the whole address: SMTP domains are not case-sensitive and
    the local part is not worth guessing at. The caller's order is preserved so a response reads the
    way the request was written.
    """
    addrs = list(dict.fromkeys(a.strip() for a in (to or []) if isinstance(a, str) and a.strip()))
    seen: set[str] = set()
    addrs = [a for a in addrs if not (a.lower() in seen or seen.add(a.lower()))]
    if not addrs:
        raise DeliveryRefused(422, "at least one recipient is required")
    if len(addrs) > MAX_RECIPIENTS:
        raise DeliveryRefused(422, f"at most {MAX_RECIPIENTS} recipients per delivery "
                                   f"({len(addrs)} given)")
    return addrs


def artifact_in(result: Any) -> tuple[str, str, str]:
    """`(storage key, filename, media type)` from a job result, or raise `DeliveryRefused`.

    Reads the RESULT rather than the Job row on purpose. The worker delivers while the row is still
    `running` — the heartbeat that holds its claim is scoped to that state — so a check against
    `state == "done"` would refuse every scheduled delivery. The route checks the state itself,
    before calling this.
    """
    res = result if isinstance(result, dict) else {}
    key = res.get("artifact_key")
    if not key:
        raise DeliveryRefused(404, "job has no artifact")
    return (str(key), str(res.get("filename") or "artifact.bin"),
            str(res.get("media_type") or "application/octet-stream"))


def send(db, *, job_id: str, kind: str, project_id: str, result: Any, addrs: list[str],
         actor: str, intro: str, note: str = "", path: str = "") -> dict[str, Any]:
    """Mail one job's artifact to `addrs`; returns the per-recipient status map, and audits the send.

    `intro` is the first line of the body and is the caller's, because *who sent this* differs: a
    person clicking Send is "alice@… sent you", a routine firing on its cadence is "the monthly
    routine produced". Neither is a good default for the other, and a body that says a person sent
    something they did not is worse than a plain one.

    A file leaving the system is what an audit log is for, so the audit is written here rather than
    left to each caller to remember.
    """
    from . import audit, mailer, storage

    key, fname, media = artifact_in(result)
    if not storage.exists(key):
        raise DeliveryRefused(404, "job has no artifact")
    nbytes = storage.size(key)
    if nbytes > MAX_BYTES:
        raise DeliveryRefused(413, f"artifact is {nbytes} bytes; the delivery cap is {MAX_BYTES}")
    data = storage.get(key)

    subject = f"{kind.replace('_', ' ')}: {fname}"
    body = (f"{intro}\n\n" + (note.strip() + "\n\n" if note.strip() else "")
            + f"Generated by job {job_id} ({kind}).\n")
    att = [(fname, data, media)]
    results: dict[str, list[str]] = {}
    for addr in addrs:
        results.setdefault(mailer.send_email(addr, subject, body, None, att), []).append(addr)
    audit.record(db, action="job.artifact.deliver", actor=actor, method="POST",
                 path=path or f"/projects/{project_id}/jobs/{job_id}/deliver",
                 detail={"kind": kind, "filename": fname, "bytes": len(data),
                         "recipients": len(addrs)})
    return {"smtp_configured": mailer.smtp_configured(), "filename": fname,
            "bytes": len(data), "results": results}
