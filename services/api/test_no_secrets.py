"""No credential ever ships in a tracked file — and the dev constants stay where they are sanctioned.

WHY A SUITE TEST AND NOT A WORKFLOW
    A CI workflow that triggers on a paths filter runs only when the files it watches change — which
    is exactly how the lockfile gate sat red and unseen for three releases (it fired on the
    Dependabot PRs, was merged past, and no ordinary push ever re-ran it). This suite runs on every
    push through the API test gate, so a leaked key fails the NEXT build, whatever that build
    touches. The external security audit (2026-08-01) asked for this gate; it proposed a standalone
    workflow, and this is the same check moved to where checks in this repo actually get seen.

TWO TIERS, BECAUSE THE REPO LEGITIMATELY CONTAINS "SECRETS"
    `dev-insecure-secret` and `minioadmin` are not leaks — they are the documented dev defaults that
    `_production_guard()` exists to refuse in production, and the guard's own source must name them.
    A scanner that flags them everywhere would fail on day one and teach people to ignore it; one
    that ignores them everywhere would let them creep into new config files as REAL defaults.

      tier 1  HIGH-RISK PATTERNS — private key blocks, cloud/AWS access keys, GitHub and Slack
              token shapes, Anthropic keys. Zero tolerance, every tracked text file, no allowlist.
      tier 2  SANCTIONED DEV CONSTANTS — allowed ONLY in the named files below, and every allowlist
              entry is asserted to still match (a dead entry is dead weight pretending to protect
              something — the vendor-exclusion lesson, applied here on day one).

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_no_secrets.py
"""
import os
import re
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# ---- tier 1: high-risk, zero tolerance ----------------------------------------------------------
#: Each pattern names its subject so a hit reads as a finding, not a regex.
HIGH_RISK: list[tuple[str, re.Pattern]] = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
]

# ---- tier 2: sanctioned dev constants, allowed only where they are the SUBJECT ------------------
SANCTIONED: dict[str, set[str]] = {
    "dev-insecure-secret": {
        "services/api/src/aec_api/auth.py",          # the constant's single definition
    },
    "minioadmin": {
        "docker-compose.yml",                        # dev default, refused in prod by the guard
        "docker-compose.prod.yml",                   # the overlay that REQUIRES real values
        "scripts/validate_prod_config.py",           # the preflight that rejects it
        "services/api/src/aec_api/main.py",          # _production_guard names it to refuse it
        "services/api/src/aec_api/storage.py",       # the dev fallback the guard polices
        "CHANGELOG.md",                              # release notes describing the guard
        # the preflight smoke drives the validator off a known-good posture and flips one
        # setting at a time; the UNSAFE posture necessarily contains this constant, because
        # refusing it is the behaviour under test. Synthetic fixture value, never a default.
        "services/api/test_preflight_smoke.py",
    },
}

# This file IS the allowlist, so it necessarily names every sanctioned constant; it is skipped for
# tier 2 only. Tier 1 still scans it — a real key pasted here would be caught like anywhere else.
SELF = "services/api/test_no_secrets.py"

SKIP_EXT = (".png", ".jpg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".frag", ".glb", ".ifc",
            ".mass", ".zip", ".pdf", ".db", ".lock")

tracked = [p for p in subprocess.run(
    ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True,
).stdout.split("\0") if p and not p.lower().endswith(SKIP_EXT)]
check("the scan population is the tracked tree, and it is populated", len(tracked) > 800,
      f"{len(tracked)} files")

hits: list[str] = []
sanctioned_seen: dict[str, set[str]] = {k: set() for k in SANCTIONED}
for rel in tracked:
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="strict") as fh:
            body = fh.read()
    except (UnicodeDecodeError, OSError):
        continue                                     # binary or unreadable — not a text surface
    for name, pat in HIGH_RISK:
        m = pat.search(body)
        if m:
            hits.append(f"{rel}: {name} ({m.group()[:12]}…)")
    for const, allowed in SANCTIONED.items():
        if rel != SELF and const in body:
            sanctioned_seen[const].add(rel)
            if rel not in allowed:
                hits.append(f"{rel}: sanctioned dev constant {const!r} outside its allowlist — "
                            "if this is a new legitimate use, add it here WITH the reason; if it is "
                            "a new default, it is the exact creep this gate exists to stop")

check("no high-risk credential pattern and no unsanctioned dev constant in any tracked file",
      not hits, "\n        " + "\n        ".join(hits[:8]) if hits else "")

# every allowlist entry must still be live — asserted per entry, never in aggregate
for const, allowed in SANCTIONED.items():
    dead = sorted(allowed - sanctioned_seen[const])
    check(f"every allowlisted location for {const!r} still contains it",
          not dead, f"dead entries (remove them): {dead}")

# ---- the scanner itself must be able to see (mutation check, in-process) ------------------------
# A gate is proven by what it catches. Synthetic positives run through the same patterns the scan
# used — if a pattern regresses, this fails even though the repo is clean.
SYNTHETIC = {
    "AWS access key id": "AKIA" + "ABCDEFGHIJKLMNOP",
    "private key block": "-----BEGIN " + "PRIVATE KEY-----",
    "GitHub token": "ghp_" + "a" * 36,
    "Slack token": "xoxb-" + "123456789012",
    "Anthropic API key": "sk-ant-" + "a" * 24,
}
for name, sample in SYNTHETIC.items():
    pat = dict(HIGH_RISK)[name]
    check(f"the {name} pattern still detects a synthetic positive", bool(pat.search(sample)))

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"test_no_secrets OK - {len(tracked)} tracked files scanned: {len(HIGH_RISK)} high-risk "
      f"patterns at zero tolerance, {len(SANCTIONED)} sanctioned dev constants pinned to "
      "their allowlisted homes (each entry asserted live)")
