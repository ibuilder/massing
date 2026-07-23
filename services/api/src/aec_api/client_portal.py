"""CLIENT-PORTAL (SPRINT D phase-1) — a tokenized, read-only project digest for external stakeholders.

An owner/GC mints a **share token** (a strong random secret) for a project; anyone holding the token can
read a *curated* digest — high-level project readiness only, **no record-level data, no GUIDs, no
financial detail, no PII**. The token is the credential (no login), soft-revocable, and scoped to exactly
one project. This is the deliberate, hard-railed public surface (per the build-doctrine): the digest is
strictly read-only and exposes only what's safe to share, so a leaked token can't do more than reveal a
readiness summary.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

_TOKEN_BYTES = 24          # ~32-char url-safe secret — unguessable
_MAX_TOKENS = 50           # per-project cap on live tokens (bounded stored data)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(db: Session, pid: str, label: str | None, actor: str | None,
                 show_payments: bool = False) -> dict[str, Any]:
    """Mint a new read-only share token for a project. Bounded per project. `show_payments` is the
    explicit OPT-IN that lets THIS token's digest carry the owner-invoice payment schedule — the default
    digest exposes no financials."""
    from .models import ShareToken

    live = db.execute(select(ShareToken).where(
        ShareToken.project_id == pid, ShareToken.revoked == False)).scalars().all()  # noqa: E712
    if len(live) >= _MAX_TOKENS:
        raise ValueError(f"too many live share tokens (max {_MAX_TOKENS}); revoke one first")
    tok = secrets.token_urlsafe(_TOKEN_BYTES)
    row = ShareToken(token=tok, project_id=pid, label=(label or "").strip()[:120] or None,
                     revoked=False, created_by=actor, created_at=_now(), view_count=0,
                     show_payments=bool(show_payments))
    db.add(row)
    db.commit()
    return _public_row(row)


def _payment_schedule(db: Session, pid: str) -> dict[str, Any] | None:
    """PORTAL-TXN phase 2: the client-facing payment SCHEDULE (display only — no payment rail): the
    project's owner invoices as milestones with amount + status, plus billed/paid/outstanding totals."""
    from . import modules as me

    if "owner_invoice" not in me.TABLES:
        return None
    rows = me.list_records(db, "owner_invoice", pid, limit=500)
    items = []
    billed = paid = 0.0
    for r in rows:
        d = r.get("data") or {}
        try:
            amt = float(str(d.get("amount") or 0).replace(",", "").replace("$", ""))
        except (TypeError, ValueError):
            amt = 0.0
        status = str(d.get("status") or "draft")
        items.append({"number": d.get("number"), "period": d.get("period"),
                      "amount": round(amt, 2), "status": status})
        billed += amt
        if status == "paid":
            paid += amt
    if not items:
        return None
    return {"items": items, "billed": round(billed, 2), "paid": round(paid, 2),
            "outstanding": round(billed - paid, 2),
            "note": "Payment schedule (display only — payments are handled outside this page)."}


def list_tokens(db: Session, pid: str) -> list[dict[str, Any]]:
    """List a project's share tokens (the token strings ARE shown to the owner so they can share them)."""
    from .models import ShareToken

    rows = db.execute(select(ShareToken).where(ShareToken.project_id == pid)
                      .order_by(ShareToken.created_at.desc())).scalars().all()
    return [_public_row(r) for r in rows]


def revoke(db: Session, pid: str, token: str) -> bool:
    """Soft-revoke a token (immediately stops digest access). Returns True if a live token was revoked."""
    from .models import ShareToken

    row = db.get(ShareToken, token)
    if row is None or row.project_id != pid or row.revoked:
        return False
    row.revoked = True
    db.commit()
    return True


def digest(db: Session, token: str) -> dict[str, Any]:
    """Resolve a token → its project → a curated, read-only readiness digest. Raises KeyError for an
    unknown or revoked token (the public route maps that to 404 — no enumeration signal). Records a view.

    SAFETY: only high-level readiness is exposed — the project name, the overall readiness score, and each
    protocol step's title + status. No findings detail, no record contents, no GUIDs, no PII. Financials
    (the owner-invoice payment schedule) appear ONLY on a token minted with the explicit show_payments
    opt-in; the default stays financials-free.
    """
    from . import master_builder
    from .models import ShareToken

    row = db.get(ShareToken, token)
    if row is None or row.revoked:
        raise KeyError("invalid or revoked token")
    b = master_builder.brief(db, row.project_id)
    row.view_count = (row.view_count or 0) + 1
    row.last_viewed_at = _now()
    db.commit()
    return {
        "project": b.get("project"),
        "jurisdiction": b.get("jurisdiction"),
        "readiness_pct": b.get("readiness_pct"),
        "ready_steps": b.get("ready_steps"), "gap_steps": b.get("gap_steps"),
        "step_count": b.get("step_count"),
        "steps": [{"n": s["n"], "title": s["title"], "status": s["status"]} for s in b.get("steps", [])],
        "activity": _activity_for_token(db, token),
        **({"payment_schedule": _payment_schedule(db, row.project_id)} if row.show_payments else {}),
        "shared_label": row.label,
        "note": "Read-only shared project digest — high-level readiness only. No record-level data, "
                "GUIDs, financial detail, or personal information is exposed. Not a substitute for the "
                "project record of authority.",
    }


# PORTAL-TXN — the tokenized client-decision surface. Whitelists + hard caps because the endpoint is
# PUBLIC: an unauthenticated token holder must not grow the table unbounded or inject markup.
_ITEM_TYPES = ("estimate", "proposal", "change_order", "selection", "invoice", "document", "digest")
_ACTIONS = ("approved", "acknowledged", "declined")
_MAX_DECISIONS_PER_TOKEN = 200
_CAPS = {"item_ref": 120, "client_name": 80, "note": 500}


def record_decision(db: Session, token: str, item_type: str, item_ref: str, action: str,
                    client_name: str | None = None, note: str | None = None) -> dict[str, Any]:
    """Record a client decision through a live token. Raises KeyError (bad/revoked token → 404) or
    ValueError (bad input / decision cap → 422/409). Timestamped + token-stamped; NOT a payment or an
    e-signature of record."""
    from sqlalchemy import func, select

    from .models import ClientDecision, ShareToken

    row = db.get(ShareToken, token)
    if row is None or row.revoked:
        raise KeyError("invalid or revoked token")
    it, act = str(item_type or "").strip().lower(), str(action or "").strip().lower()
    ref = str(item_ref or "").strip()
    if it not in _ITEM_TYPES:
        raise ValueError(f"item_type must be one of {', '.join(_ITEM_TYPES)}")
    if act not in _ACTIONS:
        raise ValueError(f"action must be one of {', '.join(_ACTIONS)}")
    if not ref:
        raise ValueError("item_ref is required")
    n = db.execute(select(func.count()).select_from(ClientDecision)
                   .where(ClientDecision.token == token)).scalar() or 0
    if n >= _MAX_DECISIONS_PER_TOKEN:
        raise ValueError("decision limit reached for this share link — ask the project team for a fresh link")
    d = ClientDecision(token=token, project_id=row.project_id, item_type=it,
                       item_ref=ref[:_CAPS["item_ref"]], action=act,
                       client_name=(str(client_name).strip()[:_CAPS["client_name"]] or None) if client_name else None,
                       note=(str(note).strip()[:_CAPS["note"]] or None) if note else None,
                       created_at=_now())
    db.add(d)
    db.commit()
    return _decision_row(d)


def _decision_row(d) -> dict[str, Any]:
    return {"id": d.id, "item_type": d.item_type, "item_ref": d.item_ref, "action": d.action,
            "client_name": d.client_name, "note": d.note,
            "created_at": d.created_at.isoformat() if d.created_at else None}


def decisions_for_project(db: Session, pid: str, limit: int = 500) -> list[dict[str, Any]]:
    """The project's client-decision feed, newest first (desc-limit keeps the NEWEST when capped)."""
    from sqlalchemy import select

    from .models import ClientDecision

    rows = db.execute(select(ClientDecision).where(ClientDecision.project_id == pid)
                      .order_by(ClientDecision.created_at.desc(), ClientDecision.id.desc())
                      .limit(max(1, min(limit, 2000)))).scalars().all()
    return [{**_decision_row(d), "token": d.token} for d in rows]


def _activity_for_token(db: Session, token: str, limit: int = 20) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from .models import ClientDecision

    rows = db.execute(select(ClientDecision).where(ClientDecision.token == token)
                      .order_by(ClientDecision.created_at.desc(), ClientDecision.id.desc())
                      .limit(limit)).scalars().all()
    return [_decision_row(d) for d in rows]


def to_html(d: dict[str, Any]) -> str:
    """Render a digest() result as a self-contained, escaped read-only HTML page (the public share page).
    Every dynamic value is HTML-escaped — the page is served to unauthenticated visitors."""
    import html as _html

    def esc(v: Any) -> str:
        return _html.escape(str(v if v is not None else ""))

    _color = {"ready": "#1a7f37", "partial": "#9a6700", "gap": "#b3261e"}
    _dot = {"ready": "●", "partial": "●", "gap": "●"}
    pct = d.get("readiness_pct") or 0
    bar = f'<div style="height:10px;border-radius:6px;background:#e5e7eb;overflow:hidden">' \
          f'<div style="height:100%;width:{max(0, min(100, pct))}%;background:#2563eb"></div></div>'
    rows = "".join(
        f'<li style="display:flex;gap:8px;align-items:baseline;margin:6px 0">'
        f'<span style="color:{_color.get(s.get("status"), "#6b7280")};font-size:11px">{_dot.get(s.get("status"), "○")}</span>'
        f'<span style="min-width:1.4em;color:#6b7280">{esc(s.get("n"))}.</span>'
        f'<span style="flex:1">{esc(s.get("title"))}</span>'
        f'<span style="font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:{_color.get(s.get("status"), "#6b7280")}">{esc(s.get("status"))}</span>'
        f'</li>' for s in d.get("steps", []))
    juris = f' · {esc(d.get("jurisdiction"))}' if d.get("jurisdiction") else ""
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex,nofollow\">"
        f"<title>{esc(d.get('project') or 'Project')} — readiness</title>"
        "<style>body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
        "background:#f7f7f8;color:#111827}main{max-width:640px;margin:0 auto;padding:28px 20px}"
        ".card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin:14px 0}"
        "h1{font-size:20px;margin:0 0 2px}.muted{color:#6b7280;font-size:13px}"
        "ul{list-style:none;padding:0;margin:8px 0 0}</style></head><body><main>"
        f"<h1>{esc(d.get('project') or 'Project')}</h1>"
        f"<div class=\"muted\">Project readiness{juris} · read-only shared digest</div>"
        "<div class=\"card\">"
        f"<div style=\"display:flex;justify-content:space-between;align-items:baseline\"><b>Readiness</b>"
        f"<span style=\"font-size:26px;font-weight:800;color:#2563eb\">{esc(pct)}%</span></div>"
        f"{bar}"
        f"<div class=\"muted\" style=\"margin-top:6px\">{esc(d.get('ready_steps'))}/"
        f"{esc(d.get('step_count'))} steps ready · {esc(d.get('gap_steps'))} gap(s)</div></div>"
        f"<div class=\"card\"><b>Master Builder Protocol</b><ul>{rows}</ul></div>"
        + (
            "<div class=\"card\"><b>Your activity</b><ul>"
            + "".join(
                f'<li style="display:flex;gap:8px;align-items:baseline;margin:6px 0">'
                f'<span style="font-size:11px;text-transform:uppercase;letter-spacing:.03em;'
                f'color:{"#1a7f37" if a.get("action") == "approved" else "#b3261e" if a.get("action") == "declined" else "#6b7280"}">'
                f'{esc(a.get("action"))}</span>'
                f'<span style="flex:1">{esc(a.get("item_type"))} · {esc(a.get("item_ref"))}</span>'
                f'<span class="muted">{esc((a.get("created_at") or "")[:10])}</span></li>'
                for a in d.get("activity", []))
            + "</ul></div>" if d.get("activity") else "")
        + (_payments_html(d["payment_schedule"], esc) if d.get("payment_schedule") else "")
        + f"<div class=\"muted\">{esc(d.get('note'))}</div>"
        "</main></body></html>")


def _payments_html(ps: dict, esc) -> str:
    """The escaped payment-schedule card for the public share page (display only)."""
    rows = []
    for it in ps.get("items", []):
        amount = it.get("amount") or 0
        color = "#1a7f37" if it.get("status") == "paid" else "#9a6700"
        rows.append(
            '<li style="display:flex;gap:8px;align-items:baseline;margin:6px 0">'
            f'<span style="min-width:4em;color:#6b7280">{esc(it.get("number"))}</span>'
            f'<span style="flex:1">{esc(it.get("period") or "")}</span>'
            f'<span style="font-variant-numeric:tabular-nums">${esc(f"{amount:,.0f}")}</span>'
            '<span style="font-size:11px;text-transform:uppercase;letter-spacing:.03em;'
            f'color:{color}">{esc(it.get("status"))}</span></li>')
    outstanding = ps.get("outstanding") or 0
    return (
        '<div class="card"><b>Payment schedule</b><ul>' + "".join(rows)
        + '<li style="display:flex;justify-content:space-between;margin-top:8px;'
          'border-top:1px solid #e5e7eb;padding-top:8px"><b>Outstanding</b>'
        + f'<b style="font-variant-numeric:tabular-nums">${esc(f"{outstanding:,.0f}")}</b></li></ul>'
        + f'<div class="muted">{esc(ps.get("note"))}</div></div>')


def _public_row(r) -> dict[str, Any]:
    return {"token": r.token, "label": r.label, "revoked": bool(r.revoked),
            "show_payments": bool(getattr(r, "show_payments", False)),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "created_by": r.created_by, "view_count": r.view_count or 0,
            "last_viewed_at": r.last_viewed_at.isoformat() if r.last_viewed_at else None,
            "share_path": f"/shared/{r.token}/digest"}
