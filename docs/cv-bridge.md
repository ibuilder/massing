# Computer-vision site-progress bridge

Estimating **% complete** from site photos needs a computer-vision model. Massing does **not** ship or
run that model — training/serving a construction-progress vision model is an external concern with its
own data, GPUs and cost. Instead the platform exposes a **feature-flagged bridge**: you connect any
vision service (an in-house model, a vendor API, a hand-labelling tool) and it POSTs progress estimates
in. The platform resolves each estimate to a schedule activity and writes its `percent`. When the flag
is off — the default — the endpoints report the bridge as unavailable and **nothing is fabricated**.

This mirrors how the platform treats every other paid/external integration (RVT→IFC via Autodesk APS,
licensed payment processors): the capability surface is complete and tested; only the external engine is
brought by the operator.

## Enable it

Set the environment flag on the API service and restart:

```bash
export AEC_CV_BRIDGE=1        # 1 / true / yes / on
```

Check status (no flag → `enabled:false`, and the endpoints no-op):

```
GET /projects/{pid}/cv-progress/status
```

## HTTP contract

**Single estimate** — `POST /projects/{pid}/cv-progress/ingest`

```json
{ "activity": "Frame L2", "percent": 55, "source": "yard-cam-3", "image_ref": "s3://…/f.jpg" }
```

- `activity` — a `schedule_activity` **id or name**. Names are resolved case-insensitively, so a service
  that only knows human task labels still addresses the right activity.
- `percent` — clamped to `0–100`.
- `source`, `image_ref`, `observed_at` — optional provenance, echoed back.

Response: `{ "accepted": true, "percent": 55.0, "applied": true, "activity_id": "…" }`
(`applied:false` with `apply_error` if no activity matched — a bad reference never 500s the bridge.)

**Batch** — `POST /projects/{pid}/cv-progress/ingest-batch` (the shape a per-photo sweep produces):

```json
{ "estimates": [
    { "activity": "Frame L2", "percent": 55 },
    { "activity": "Slab L3",  "percent": 20, "source": "drone-a" }
] }
```

Response summarises `count` / `valid` / `applied` and returns per-item outcomes.

## Reference adapter

A minimal, dependency-free client you point at your own vision service. Swap `estimate_from_photo` for
your model call; everything else is the bridge contract.

```python
import os, requests   # stdlib urllib works too — requests is just for brevity

API   = os.environ["MASSING_API"]      # e.g. https://api.example.com
TOKEN = os.environ["MASSING_TOKEN"]    # an editor-role session/bearer token
PID   = os.environ["MASSING_PROJECT"]

def estimate_from_photo(path: str) -> list[dict]:
    """YOUR model: return [{'activity': <id or name>, 'percent': 0..100, 'image_ref': path}, …]."""
    ...

def push(estimates: list[dict]) -> dict:
    r = requests.post(f"{API}/projects/{PID}/cv-progress/ingest-batch",
                      json={"estimates": estimates},
                      headers={"Authorization": f"Bearer {TOKEN}"})
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    import sys
    all_estimates = [e for p in sys.argv[1:] for e in estimate_from_photo(p)]
    print(push(all_estimates))
```

The estimates flow straight into `schedule_activity.percent`, so earned-value, the S-curve, and the
schedule alerts reflect field reality as soon as your model reports it.
