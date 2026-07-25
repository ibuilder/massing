"""Fetch family packs onto the external shelf (`services/data/families/external/`).

Packs are IFC4 files of `IfcTypeProduct` content. Once on the shelf they are listed by
`GET /families/library` (with manifest metadata) and importable server-side via
`POST /projects/{pid}/families/import-pack` — no upload round trip.

    python scripts/fetch_families.py --list
    python scripts/fetch_families.py                       # every pack in the latest release
    python scripts/fetch_families.py --tag v0.1.0 --packs structural-steel-w mechanical-ductwork

This is a **build/ops-time** tool, never a runtime dependency: the platform runs fully offline and
reads whatever is already on the shelf. Nothing here is imported by the API.

Each pack's sha256 is checked against the release manifest before it lands. Note what that does and
does not buy you: it detects a corrupted or truncated download, not a compromised release — manifest
and asset come from the same place. Treat a pack like any third-party content you choose to trust.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "MassingCloud/massing-families"
API = f"https://api.github.com/repos/{REPO}/releases"
DEST = Path(__file__).resolve().parents[1] / "services" / "data" / "families" / "external"
TIMEOUT = 60


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "massing-fetch-families"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:   # noqa: S310 — fixed https host above
        return r.read()


def _release(tag: str | None) -> dict:
    url = f"{API}/tags/{tag}" if tag else f"{API}/latest"
    try:
        return json.loads(_get(url))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(
                f"no {'release ' + tag if tag else 'published release'} on {REPO}.\n"
                f"Packs are generated from that repo's YAML catalog; until a release is published, "
                f"build them from a checkout instead:\n"
                f"    git clone https://github.com/{REPO}\n"
                f"    cd massing-families && pip install -e . && python -m massing_families.cli build\n"
                f"then copy packs/*.ifc and packs/manifest.json into {DEST}") from None
        raise SystemExit(f"could not reach {REPO}: {e}") from None
    except (urllib.error.URLError, ValueError) as e:
        raise SystemExit(f"could not reach {REPO}: {e}") from None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", help="release tag (default: latest)")
    ap.add_argument("--packs", nargs="*", help="pack disciplines to fetch (default: all)")
    ap.add_argument("--dest", type=Path, default=DEST)
    ap.add_argument("--list", action="store_true", help="list packs in the release and exit")
    args = ap.parse_args(argv)

    rel = _release(args.tag)
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    if "manifest.json" not in assets:
        raise SystemExit(f"release {rel.get('tag_name')} has no manifest.json — cannot verify packs")
    manifest = json.loads(_get(assets["manifest.json"]))
    packs = manifest.get("packs") or []

    if args.list:
        t = manifest.get("totals", {})
        print(f"{REPO} {rel['tag_name']} — {t.get('families', '?')} families, {t.get('types', '?')} types")
        for p in sorted(packs, key=lambda x: x.get("discipline", "")):
            print(f"  {p.get('discipline', '?'):34} {p.get('families', 0):>3}f {p.get('types', 0):>5}t "
                  f"{p.get('size_bytes', 0) / 1e6:>6.1f} MB")
        return 0

    wanted = set(args.packs) if args.packs else None
    if wanted:
        missing = wanted - {p.get("discipline") for p in packs}
        if missing:
            raise SystemExit(f"no such pack(s): {sorted(missing)}. Use --list to see options.")
    selected = [p for p in packs if wanted is None or p.get("discipline") in wanted]

    args.dest.mkdir(parents=True, exist_ok=True)
    written = 0
    for pack in selected:
        name = pack.get("file")
        url = assets.get(name)
        if not url:
            print(f"  SKIP {name} — declared in the manifest but not published as a release asset")
            continue
        data = _get(url)
        want = pack.get("sha256")
        got = hashlib.sha256(data).hexdigest()
        if want and got != want:
            raise SystemExit(f"{name}: sha256 mismatch (manifest {want}, downloaded {got}) — refusing "
                             f"to write. Nothing already on the shelf was modified.")
        (args.dest / name).write_bytes(data)
        written += 1
        print(f"  {name}  {len(data) / 1e6:.1f} MB  {pack.get('types', '?')} types")

    # keep the manifest beside the packs — the shelf listing reads it for discipline/type counts
    (args.dest / "manifest.json").write_bytes(_get(assets["manifest.json"]))
    print(f"\n{written} pack(s) -> {args.dest}")
    if written < len(selected):
        print(f"NB {len(selected) - written} declared pack(s) had no published asset (listed above).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
