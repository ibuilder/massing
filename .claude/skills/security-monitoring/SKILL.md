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

## SEC-DATAFLOW — where to spend review effort (empirical, from vuln-localization research)
Difficulty follows **structure, not severity**: multi-file / cross-import data flows are the hardest class to
localize and the least covered by SAST pattern matching. Prioritize hand/agentic review on flows spanning
**router → dependency helper → model/engine → storage** (request data crossing module boundaries), not
single-file sinks CodeQL already patterns. SAST is coverage-limited by its rules; the search→verify→refine
agentic review (the security-review subagent + this checklist) is the complement, not a duplicate.

## Hand-audit checklist (HARDEN passes — beyond CodeQL's reach)
Run over a release range (`git diff vX..vY --stat`, then read the changed files). Every class below
produced a real finding in the v0.3.510 HARDEN-2 pass:

- **Privilege side doors:** a stricter endpoint (admin + audited) whose work is ALSO reachable through
  a generic gate — the job queue (`routers/jobs.py` `_KIND_MIN_ROLE`), bulk endpoints, MCP dispatch.
  New privileged operations must gate every path, not just the front door, and audit each.
- **Unbounded stored data → cheap-GET amplification:** anything an editor stores that a viewer-level
  GET later evaluates (rules, configs, lists) needs count/size caps at save (`rule_library.MAX_*` is
  the pattern; `schedule_baselines._MAX` too).
- **Payload caps must keep the NEWEST rows:** `order_by(asc).limit()` silently hides everything
  created after row N — cap with `desc().limit()` then re-sort ascending for stable display.
- **innerHTML interpolation:** any file/server/model-derived free-text must pass `esc()` (panels,
  from `ui/charts`) or `escapeHtml` (viewer). Numbers/`.toFixed`/server-constant labels are fine.
  CodeQL catches some (`js/xss-through-dom`) but not all sinks.
- **Hand-rolled parsers:** operator splitting must be leftmost + quote-aware (the QUERY-DSL `_find_op`
  fix); validate what stored selectors will DO, not just that they parse — a silently-never-matching
  rule is a false "pass" downstream.
- **Serializer/format parity on swaps:** replacing a serializer (orjson) or parser needs the FULL
  suite as the parity gate + explicit deltas checked: non-str keys, float subclasses (numpy.float64),
  NaN/Infinity, tuples/sets, str subclasses.
- **Live-UI teardown:** modal/panel tools with timers or visibility state need an `onClose` hook
  (`ui/result.ts showResult(title, render, onClose)`) — closing must stop timers + restore state.
- **External-format imports:** skip container/rollup rows (MSPDI `<Summary>1</Summary>`; XER non-TASK
  tables) — named+dated summary rows import as phantom records otherwise.

## SEC-SUPPLY — license / SBOM audit (run before a hardening release)
`aec_api.supply_chain` is a dependency-free (stdlib `importlib.metadata`) supply-chain tool:
```
cd services/api && PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe -m aec_api.supply_chain          # informational
cd services/api && PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe -m aec_api.supply_chain --gate    # exit 1 on STRONG copyleft
```
- Classifies every installed distribution's license: **permitted** (MIT/BSD/Apache/ISC/PSF/Unlicense/Zlib) · **copyleft** · **unknown**, splitting **STRONG** (GPL/AGPL — the disallowed hard line) from **weak** (LGPL/MPL — accepted for the ifcopenshell/certifi core deps, but surfaced). Word-boundary matched (naive substring makes "EXE**MPL**ARY" false-match `mpl`).
- `--gate` fails only on STRONG copyleft, so it never breaks CI over the known LGPL/MPL core deps. **Known strong hits are venv-incidental, NOT declared deps** (e.g. `pymupdf`/AGPL, `pyinstaller`/GPL build tool) — confirm a strong hit is absent from `services/*/requirements*` before acting; a declared strong-copyleft dep is a real violation to remove.
- `supply_chain.sbom()` emits a minimal CycloneDX 1.5 component list. `supply_chain.pdf_sanity(bytes)` is a lightweight pre-ingest PDF check (header/EOF/size + active-content flags: JavaScript/Launch/EmbeddedFile/OpenAction) — NOT a full parser (no AGPL PyMuPDF).

## Not a vulnerability (don't manufacture fixes)
Per the security-review exclusions: DoS/resource-exhaustion, secrets-on-disk (handled elsewhere), rate-limiting, SSRF that only controls the path, client-side authz, log-spoofing, outdated-dep advisories (handled separately). Fix concrete, exploitable HIGH/MED with a clear path.

See memory: `codeql-monitoring`, `perf-sec-p0-patterns`, `innerhtml-xss-esc`, `query-dsl-selector-spine`.
