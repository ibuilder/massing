"""3rd-party e-signature bridge — OPTIONAL, feature-flagged (off unless ESIGN_PROVIDER + creds set).

Self-hosted PAdES (esign.py) already covers tamper-evident execution at no cost / fully offline. This
bridge is for *legally-binding, multi-party* signing workflows, via a self-hosted open-source platform
(DocuSeal / Documenso) or a SaaS (DocuSign / Adobe Acrobat Sign / Dropbox Sign).

**DocuSeal** (self-hosted OSS) is implemented end-to-end here over its REST API (stdlib urllib, no SDK):
create a template from the rendered PDF, then create a submission with the signers; we return the
per-signer signing URLs and the submission id. Completion is reflected via POST /esign/webhook.
Other providers raise an actionable error until their credentialed flow is wired per deployment.
See docs/esign-options.md.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Any

from .net import validate_outbound_url

_PROVIDERS = {
    "docuseal": "DocuSeal (self-hosted)",
    "documenso": "Documenso (self-hosted)",
    "docusign": "DocuSign",
    "adobe": "Adobe Acrobat Sign",
    "dropbox": "Dropbox Sign",
}
_IMPLEMENTED = ("docuseal",)
_TIMEOUT = 30


def provider() -> str | None:
    p = os.environ.get("ESIGN_PROVIDER", "").strip().lower()
    return p or None


def base_url() -> str:
    return os.environ.get("ESIGN_BASE_URL", "").rstrip("/")


def is_enabled() -> bool:
    """A provider is configured with at least an API key or a self-hosted base URL."""
    return bool(provider() in _PROVIDERS and (os.environ.get("ESIGN_API_KEY") or os.environ.get("ESIGN_BASE_URL")))


def status() -> dict[str, Any]:
    p = provider()
    return {
        "enabled": is_enabled(),
        "provider": _PROVIDERS.get(p or "", None),
        "implemented": (p in _IMPLEMENTED) if p else False,
        "providers_supported": list(_PROVIDERS.values()),
        "message": (f"{_PROVIDERS[p]} bridge configured." if is_enabled() else
                    "3rd-party e-signature bridge not configured. Self-hosted PAdES digital signatures "
                    "are available now; set ESIGN_PROVIDER (+ ESIGN_API_KEY / ESIGN_BASE_URL) to route "
                    "legally-binding multi-party signing through DocuSeal / Documenso / DocuSign / etc."),
    }


# --- transport seam (monkeypatched in tests) --------------------------------
def _http_json(method: str, url: str, headers: dict[str, str], payload: dict | None) -> Any:
    validate_outbound_url(url, label="ESIGN_BASE_URL")  # block file://etc on the operator-set endpoint
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 — operator URL, scheme-validated
        body = resp.read().decode() or "{}"
    return json.loads(body)


# overridable hook so the send flow is testable without a live server
def post_json(url: str, headers: dict[str, str], payload: dict) -> Any:
    return _http_json("POST", url, headers, payload)


def _docuseal_send(pdf: bytes, signers: list[dict], subject: str) -> dict[str, Any]:
    """DocuSeal flow: create a template from the PDF, then a submission with the signers.
    Returns submission id + per-signer signing URLs. Docs: docuseal.com/docs/api."""
    base = base_url() or "https://api.docuseal.com"
    key = os.environ.get("ESIGN_API_KEY", "")
    headers = {"X-Auth-Token": key}
    b64 = base64.b64encode(pdf).decode()
    tmpl = post_json(f"{base}/api/templates/pdf", headers,
                     {"name": subject, "documents": [{"name": subject, "file": b64}]})
    template_id = tmpl.get("id") if isinstance(tmpl, dict) else None
    if not template_id:
        raise RuntimeError(f"DocuSeal template creation returned no id: {tmpl}")
    submitters = [{"role": s.get("role") or s.get("party") or "Signer",
                   "email": s["email"], "name": s.get("name")} for s in signers if s.get("email")]
    if not submitters:
        raise RuntimeError("at least one signer with an email is required")
    sub = post_json(f"{base}/api/submissions", headers,
                    {"template_id": template_id, "send_email": True, "submitters": submitters})
    # DocuSeal returns a list of submitters (with slugs) or an object with id; normalize.
    rows = sub if isinstance(sub, list) else (sub.get("submitters") or [])
    sub_id = (rows[0].get("submission_id") if rows and isinstance(rows[0], dict) else None)
    if sub_id is None and isinstance(sub, dict):
        sub_id = sub.get("id")
    signing = [{"email": r.get("email"), "role": r.get("role"),
                "url": (f"{base}/s/{r.get('slug')}" if r.get("slug") else r.get("embed_src"))}
               for r in rows if isinstance(r, dict)]
    return {"provider": "DocuSeal (self-hosted)", "template_id": template_id,
            "submission_id": sub_id, "signers": signing, "status": "sent"}


def send_for_signature(pdf: bytes, signers: list[dict], subject: str) -> dict[str, Any]:
    """Send a document for signature through the configured provider. DocuSeal is implemented; other
    providers raise an actionable error until their credentialed flow is wired per deployment."""
    if not is_enabled():
        raise RuntimeError("No e-signature provider configured (set ESIGN_PROVIDER + credentials).")
    p = provider()
    if p == "docuseal":
        return _docuseal_send(pdf, signers, subject)
    raise NotImplementedError(
        f"The {_PROVIDERS[p]} signing flow runs in a credentialed deployment; wire its "
        "envelope/submission API in esign_bridge.py. The DocuSeal (self-hosted) flow is implemented, "
        "and built-in PAdES digital signatures are available now.")


def parse_completion(payload: dict) -> dict[str, Any]:
    """Normalize a provider completion webhook into {submission_id, event, completed, signer}.
    DocuSeal posts {event_type: 'form.completed'|'submission.completed', data: {...}}."""
    ev = payload.get("event_type") or payload.get("event") or ""
    data = payload.get("data") or payload
    return {
        "submission_id": data.get("submission_id") or data.get("id"),
        "event": ev,
        "completed": ev in ("submission.completed", "form.completed") or bool(data.get("completed_at")),
        "signer": data.get("email"),
    }
