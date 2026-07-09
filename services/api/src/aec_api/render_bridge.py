"""AI concept-render bridge (Track V) — AIRI-style generative concept visuals, as a feature-flagged bridge.

Turning a concept (space program + massing + a text prompt) into **AI concept renders / variations**
needs an external image-generation model — its own GPUs, cost and data governance — so, exactly like the
computer-vision progress bridge and the RVT / payment bridges, the platform does **not** run or bundle the
model. An operator enables the flag (``AEC_RENDER_BRIDGE``) and connects an image service; the platform
builds a grounded **prompt** from the project's program/massing, hands it to the service, and ingests the
returned image references as ``concept_render`` records. When the flag is off (the default), the endpoints
report the bridge as unavailable and **nothing is fabricated** — no fake images, no placeholder URLs.
"""
from __future__ import annotations

import os
from typing import Any


def enabled() -> bool:
    return os.environ.get("AEC_RENDER_BRIDGE", "").lower() in ("1", "true", "yes", "on")


def status() -> dict[str, Any]:
    return {
        "feature": "concept_render_bridge", "enabled": enabled(),
        "note": "AI concept renders from a project's program + massing need an external image model. "
                "Enable AEC_RENDER_BRIDGE and connect a service that accepts a prompt and POSTs image "
                "references to /concept-render/ingest. The platform builds the prompt and stores results; "
                "it does not run or bundle a model, and fabricates nothing when off.",
        "request_contract": {"prompt": "optional extra text", "style": "e.g. photoreal / massing / sketch",
                             "variations": "1–8"},
        "ingest_contract": {"prompt": "the prompt used", "image_url": "the generated image reference",
                            "style": "optional", "source": "the external generator"},
        "reference_adapter": "docs/render-bridge.md — the HTTP contract + a runnable Python reference "
                             "client you point at any image-generation service.",
    }


def build_prompt(program: dict[str, Any] | None, massing: dict[str, Any] | None,
                 extra: str | None = None, style: str | None = None) -> str:
    """Compose a grounded concept-render prompt from the project's space program + massing metrics."""
    parts: list[str] = []
    style = (style or "photoreal architectural rendering").strip()
    parts.append(style)
    if massing:
        m = massing.get("metrics") or massing
        floors = m.get("floors") or m.get("stories")
        use = m.get("use_type") or m.get("use")
        gfa = m.get("gross_area_m2") or m.get("gross_area_sf") or m.get("gfa_sf")
        seg = []
        if use:
            seg.append(str(use))
        if floors:
            seg.append(f"{floors}-storey")
        if gfa:
            seg.append(f"~{gfa} gross")
        if seg:
            parts.append("a " + " ".join(seg) + " building")
    if program:
        uses = program.get("use_mix") or program.get("uses")
        if isinstance(uses, (list, dict)):
            names = list(uses.keys()) if isinstance(uses, dict) else [str(u) for u in uses]
            if names:
                parts.append("program: " + ", ".join(names[:6]))
    if extra:
        parts.append(extra.strip())
    parts.append("context-appropriate materials, human scale, daylight, professional composition")
    return ", ".join(p for p in parts if p)


def request(payload: dict[str, Any], program: dict[str, Any] | None = None,
            massing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepare a concept-render request. Returns the grounded prompt + variation count when enabled; a
    no-op (accepted=False) when the bridge is disabled."""
    if not enabled():
        return {"accepted": False, "reason": "bridge disabled (set AEC_RENDER_BRIDGE to enable)", **status()}
    try:
        variations = int(payload.get("variations") or 1)
    except (TypeError, ValueError):
        variations = 1
    variations = max(1, min(8, variations))
    prompt = build_prompt(program, massing, payload.get("prompt"), payload.get("style"))
    return {"accepted": True, "prompt": prompt, "style": payload.get("style") or "photoreal",
            "variations": variations,
            "note": "Send this prompt to your connected image service; POST each result to "
                    "/concept-render/ingest to store it as a concept_render."}


def validate_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an ingested render (the router stores accepted ones as concept_render records)."""
    if not enabled():
        return {"accepted": False, "reason": "bridge disabled (set AEC_RENDER_BRIDGE to enable)", **status()}
    url = (payload.get("image_url") or "").strip()
    if not url:
        return {"accepted": False, "reason": "image_url required"}
    return {"accepted": True, "image_url": url, "prompt": payload.get("prompt", ""),
            "style": payload.get("style", ""), "source": payload.get("source", "render-bridge")}
