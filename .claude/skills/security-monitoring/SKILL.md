---
name: security-monitoring
description: How to monitor and fix security issues in Massing — CodeQL alerts, dependency audits, secret scanning, and ReDoS/XXE fixes. Invoke after a push (standing directive) or when doing a hardening pass. Emphasises that a green CodeQL *run* != zero alerts.
---

# Security monitoring — Massing

Standing directive: **check CodeQL after every push and fix any HIGH that appears.**

## CodeQL — check ALERTS, not run status
A "CodeQL Advanced" workflow run showing `completed success` only means the scan executed — it does NOT mean zero alerts. Alerts live in the code-scanning API:
```
gh api repos/ibuilder/massing/code-scanning/alerts --jq '[.[] | select(.state=="open")] | length'
gh api "repos/ibuilder/massing/code-scanning/alerts?state=open&per_page=30" \
  --jq '.[] | "\(.rule.security_severity_level // .rule.severity) | \(.rule.id) | \(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line)"'
```
After pushing a fix, wait for the next CodeQL run to re-scan, then re-query — the count drops when alerts auto-close.

## Common fixes
- **`py/polynomial-redos` (ReDoS):** a free-text scanner using unbounded `\d+` / `[\d,]+` / `\s*` under `re.search` re-scans → polynomial on a crafted long string. Fix: **bound the quantifiers** (`{1,n}` not `+`/`*`) and **cap the input** (`text[:20_000]`) before the regex. Verify detection still works on real inputs + a 100k-char crafted input returns in <100 ms.
- **XXE:** parse untrusted XML with `defusedxml.ElementTree.fromstring` (catch `ET.ParseError` + `defusedxml.common.DefusedXmlException` → return empty). Never bare `xml.etree`.
- **Weak-hash flags** (`py/weak-sensitive-data-hashing`, bandit B324): SHA-1/MD5 used for non-crypto identity/cache keys → add `usedforsecurity=False`.

## Local audits (run before a hardening release)
```
cd apps/web && npm audit --omit=dev
cd services/api && ./.venv/Scripts/python.exe -m bandit -r src ../data/src -ll -ii     # HIGH+MED, high-confidence
cd services/api && ./.venv/Scripts/python.exe -m pip_audit --progress-spinner off       # pip install pip-audit first
# secret scan (no gitleaks): grep the source tree for high-signal patterns, exclude node_modules/venv/tests
```
Pin CVE'd transitive deps in `services/data/requirements.txt` (e.g. `pillow>=12.3.0`).

## Not a vulnerability (don't manufacture fixes)
Per the security-review exclusions: DoS/resource-exhaustion, secrets-on-disk (handled elsewhere), rate-limiting, SSRF that only controls the path, client-side authz, log-spoofing, outdated-dep advisories (handled separately). Fix concrete, exploitable HIGH/MED with a clear path.

See memory: `codeql-monitoring`, `perf-sec-p0-patterns`.
