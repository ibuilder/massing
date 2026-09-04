"""Email sending — stdlib smtplib only, no deps. Configured via env; a no-op (logged) when
unconfigured so digests degrade gracefully in dev / unconfigured deployments.

Env:
  AEC_SMTP_HOST            enable sending (unset → disabled, send_email returns "disabled")
  AEC_SMTP_PORT            default 587
  AEC_SMTP_USER / _PASSWORD   optional SMTP auth
  AEC_SMTP_FROM            From address (default no-reply@<host>)
  AEC_SMTP_TLS             "1" (default) → STARTTLS; "0" → plain
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from . import settings_store

_log = logging.getLogger("aec.mail")


def smtp_configured() -> bool:
    return bool(settings_store.get("AEC_SMTP_HOST"))


def _from_addr() -> str:
    return settings_store.get("AEC_SMTP_FROM") or f"no-reply@{settings_store.get('AEC_SMTP_HOST', 'localhost')}"


def smtp_test() -> dict:
    """Liveness check for the Settings 'Test connection' button: connect + STARTTLS + login (no send)."""
    if not smtp_configured():
        return {"ok": False, "message": "SMTP host not set."}
    host = settings_store.get("AEC_SMTP_HOST")
    port = int(settings_store.get("AEC_SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            if settings_store.get("AEC_SMTP_TLS", "1") == "1":
                s.starttls(context=ssl.create_default_context())   # verified — see send_email
            user, pw = settings_store.get("AEC_SMTP_USER"), settings_store.get("AEC_SMTP_PASSWORD")
            if user and pw:
                s.login(user, pw)
        return {"ok": True, "message": f"Connected to {host}:{port}."}
    except Exception as e:                               # noqa: BLE001
        return {"ok": False, "message": f"SMTP failed: {str(e)[:140]}"}


def build_message(to: str, subject: str, body_text: str, body_html: str | None = None,
                  attachments: list[tuple[str, bytes, str]] | None = None) -> EmailMessage:
    """Construct a well-formed (optionally multipart) message — pure, no I/O (testable).

    `attachments` are `(filename, data, mime)` triples. Order matters: `add_alternative` must run
    BEFORE `add_attachment`, or the html alternative lands inside the mixed part and clients show
    the attachment where the body should be.
    """
    msg = EmailMessage()
    msg["From"] = _from_addr()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    for filename, data, mime in attachments or []:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(data, maintype=maintype or "application",
                           subtype=subtype or "octet-stream", filename=filename)
    return msg


def send_email(to: str, subject: str, body_text: str, body_html: str | None = None,
               attachments: list[tuple[str, bytes, str]] | None = None) -> str:
    """Send one message. Returns "sent" | "disabled" | "error". Never raises (so a digest
    run can't be broken by one bad address / transient SMTP failure)."""
    if not smtp_configured():
        # Still built, so an unconfigured deployment fails on a malformed address the same way a
        # configured one does — a bad recipient must not become visible only in production.
        try:
            build_message(to, subject, body_text, body_html, attachments)
        except Exception as e:                           # noqa: BLE001
            # %r, not %s: `to` is attacker-influenced and a CR/LF in it writes literal newlines
            # into the log stream, so a recipient can forge whole log lines (CWE-117). repr escapes
            # them. Same at the send handler below.
            _log.warning("email not built for %r: %s", to, e)
            return "error"
        _log.info("email disabled (no AEC_SMTP_HOST) — would send %r to %r", subject, to)
        return "disabled"
    try:
        # EVERYTHING that can raise belongs inside this boundary, not just the message build. The
        # first fix moved `build_message` in and left `int(AEC_SMTP_PORT)` outside — and settings are
        # stored as arbitrary strings (`settings_store.set_value(db, k, str(v))`, no numeric check),
        # so a mistyped port raised ValueError one line above the guard that exists to prevent
        # exactly that. Treating the instance rather than the class is what left it; the rule is that
        # this function returns a status for ANY input, configuration included.
        host = settings_store.get("AEC_SMTP_HOST")
        port = int(settings_store.get("AEC_SMTP_PORT", "587"))
        msg = build_message(to, subject, body_text, body_html, attachments)
        with smtplib.SMTP(host, port, timeout=15) as s:
            if settings_store.get("AEC_SMTP_TLS", "1") == "1":
                # An explicit verified context. `starttls()` with no argument uses
                # `ssl._create_stdlib_context()`, which on this interpreter reports
                # verify_mode=0 / check_hostname=False — no certificate check at all, so the
                # artifact and the SMTP credentials go up unauthenticated.
                s.starttls(context=ssl.create_default_context())
            user, pw = settings_store.get("AEC_SMTP_USER"), settings_store.get("AEC_SMTP_PASSWORD")
            if user and pw:
                if settings_store.get("AEC_SMTP_TLS", "1") != "1":
                    # Deliberately a loud warning, not a refusal. `AEC_SMTP_TLS=0` is a documented
                    # deployment choice for a self-hosted product relaying through localhost or a
                    # trusted internal MTA, where cleartext is not an exposure; hard-refusing would
                    # break those installs to protect against a risk they do not have. What is not
                    # defensible is doing it SILENTLY, so the operator is told each time.
                    _log.warning("SMTP auth over cleartext: AEC_SMTP_TLS=0 and a password is set, "
                                 "so the credential leaves this host unprotected. Set AEC_SMTP_TLS=1 "
                                 "unless the relay is local or on a trusted network.")
                s.login(user, pw)
            s.send_message(msg)
        return "sent"
    except Exception as e:           # noqa: BLE001 — one bad send must not abort a batch
        _log.warning("email send failed to %r: %s", to, e)
        return "error"
