# AI concept-render bridge

Turning a concept — the space **program** + **massing** + a text prompt — into **AI concept renders /
variations** needs an external image-generation model, with its own GPUs, cost and data governance.
Massing does **not** ship or run that model. Instead the platform exposes a **feature-flagged bridge**:
it builds a **grounded prompt** from the project's program/massing, hands it to any image service you
connect, and ingests the returned image references as reviewable `concept_render` records. When the flag
is off — the default — the endpoints report the bridge as unavailable and **nothing is fabricated**: no
fake images, no placeholder URLs.

This mirrors how the platform treats every other paid/external integration (the computer-vision
site-progress bridge, RVT→IFC via Autodesk APS, licensed payment processors): the capability surface is
complete and tested; only the external engine is brought by the operator.

## Enable it

Set the environment flag on the API service and restart:

```bash
export AEC_RENDER_BRIDGE=1        # 1 / true / yes / on
```

Check status (no flag → `enabled:false`, and the endpoints no-op):

```
GET /projects/{pid}/concept-render/status
```

## HTTP contract

**Build a grounded prompt** — `POST /projects/{pid}/concept-render/request`

```json
{ "style": "photoreal", "prompt": "golden hour, waterfront context", "variations": 4 }
```

- The platform composes the prompt from the project's **space program** (use mix) + **massing** (floors,
  use, gross area) and appends your `style` + extra `prompt`. Pass `program` / `massing` explicitly to
  override what's fetched.
- `variations` — clamped to `1–8`.

Response (bridge on): `{ "accepted": true, "prompt": "photoreal…, a 12-storey office building, …",
"style": "photoreal", "variations": 4 }` — send this prompt to your image service.
(Bridge off: `{ "accepted": false, "reason": "bridge disabled (set AEC_RENDER_BRIDGE to enable)", … }`.)

**Ingest a generated image** — `POST /projects/{pid}/concept-render/ingest`

```json
{ "title": "Street view — dusk", "prompt": "…the prompt used…",
  "image_url": "https://cdn.example.com/render-1.png", "style": "photoreal", "source": "your-generator" }
```

- `image_url` is **required** (a render with no image reference is rejected — it never 500s the bridge).
- Accepted renders are stored as `concept_render` records (workflow `draft → shortlisted / archived`),
  reviewable in the design workspace's 🖼 **Concept Renders** panel.

Response: `{ "accepted": true, "stored": true, "record_id": "…", "image_url": "…" }`.

## Reference adapter

A minimal, dependency-free client: ask the platform for a grounded prompt, call **your** image model,
then ingest each result. Swap `generate_images` for your model call; everything else is the bridge
contract.

```python
import os, requests   # stdlib urllib works too — requests is just for brevity

API   = os.environ["MASSING_API"]      # e.g. https://api.example.com
TOKEN = os.environ["MASSING_TOKEN"]    # an editor-role session/bearer token
PID   = os.environ["MASSING_PROJECT"]
HDR   = {"Authorization": f"Bearer {TOKEN}"}

def generate_images(prompt: str, n: int) -> list[str]:
    """YOUR image model: return a list of image URLs for the prompt."""
    ...

def build_prompt(style="photoreal", extra=None, variations=4) -> dict:
    r = requests.post(f"{API}/projects/{PID}/concept-render/request",
                      json={"style": style, "prompt": extra, "variations": variations}, headers=HDR)
    r.raise_for_status()
    return r.json()

def ingest(prompt: str, url: str, style="photoreal") -> dict:
    r = requests.post(f"{API}/projects/{PID}/concept-render/ingest",
                      json={"title": "Concept render", "prompt": prompt, "image_url": url,
                            "style": style, "source": "reference-adapter"}, headers=HDR)
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    req = build_prompt(style="photoreal", extra="golden hour", variations=4)
    if not req.get("accepted"):
        raise SystemExit(f"bridge off: {req.get('reason')}")
    for img in generate_images(req["prompt"], req["variations"]):
        print(ingest(req["prompt"], img))
```

The stored renders are just `concept_render` records, so they round-trip through the same list / board /
workflow views as every other module — shortlist the ones the design team likes, archive the rest.
