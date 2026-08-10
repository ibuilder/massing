"""Audit services/api/requirements.lock against OSV, by PINNED VERSION.

Why not pip-audit: it resolves and installs to learn the versions, so it needs an interpreter that
can satisfy the lock. The lock is compiled for py3.12/Linux (networkx 3.6.1 requires >=3.11) and the
local venv is 3.10 — pip-audit fails to install and reports nothing, which is a check that cannot
fail. The lock already states every version exactly; asking OSV about those strings audits the
artefact that ships, not whatever happens to be installed here.

NOT A CI GATE. This exits 1 on ANY advisory, including ones with no published fix — useful for a
human asking "what is in the lock right now", wrong for a build, which would then block forever on
something no version bump can answer. The gate is `scripts/audit_lock_gate.py`, and it blocks only
where a fix exists. Do not wire this one into a workflow.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request

LOCK = sys.argv[1] if len(sys.argv) > 1 else "services/api/requirements.lock"
PIN = re.compile(r"^([A-Za-z0-9._-]+)==([^\s\\;]+)")

pins: dict[str, str] = {}
with open(LOCK, encoding="utf-8") as fh:
    for line in fh:
        if line[:1].isspace() or line.startswith("#"):
            continue
        m = PIN.match(line.strip())
        if m:
            pins[m.group(1).lower()] = m.group(2)

print(f"{len(pins)} pinned distributions read from {LOCK}")

queries = [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in pins.items()]
req = urllib.request.Request(
    "https://api.osv.dev/v1/querybatch",
    data=json.dumps({"queries": queries}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=120) as r:
    results = json.load(r)["results"]

names = list(pins)
hits = []
for name, res in zip(names, results):
    for v in res.get("vulns", []) or []:
        hits.append((name, pins[name], v["id"]))

if not hits:
    print("\nNo advisories against the pinned versions.")
    sys.exit(0)

# fetch details for each id so the fixed version is stated, not guessed
print(f"\n{len(hits)} advisory hit(s):\n")
seen: dict[str, dict] = {}
# Advisory ids come back from OSV and are then put INTO a URL. The host is a constant so this is not
# SSRF, but interpolating a remote value into a path is the wrong habit to write down — a later edit
# that makes the host variable inherits it. Constrained to the shape every real id has.
_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
for name, ver, vid in hits:
    if not _ID.match(vid):
        print(f"  {name}=={ver}\n    {vid!r} is not a well-formed advisory id — skipped, not fetched")
        continue
    if vid not in seen:
        with urllib.request.urlopen(f"https://api.osv.dev/v1/vulns/{vid}", timeout=60) as r:
            seen[vid] = json.load(r)
    d = seen[vid]
    fixed = set()
    for a in d.get("affected", []):
        if a.get("package", {}).get("name", "").lower() != name:
            continue
        for rng in a.get("ranges", []):
            for ev in rng.get("events", []):
                if "fixed" in ev:
                    fixed.add(ev["fixed"])
    sev = d.get("database_specific", {}).get("severity") or ""
    for s in d.get("severity", []) or []:
        sev = sev or s.get("score", "")
    aliases = [a for a in d.get("aliases", []) if a.startswith("CVE")]
    print(f"  {name}=={ver}")
    print(f"    {vid}{'  (' + ', '.join(aliases) + ')' if aliases else ''}  {sev}")
    print(f"    fixed in: {', '.join(sorted(fixed)) if fixed else 'NO FIX PUBLISHED'}")
    print(f"    {d.get('summary', '').strip()[:150]}")
    print()
sys.exit(1)
