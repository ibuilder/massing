# Claude Code skills for Massing

Project-local skills that encode this repo's hard-won workflows. Skills are **inert markdown** loaded on
demand when you (or a teammate's Claude Code) invoke them by name — safe to commit and share. They pair
with the auto-recalled memories in `~/.claude/projects/.../memory/`.

## Shipped here (committed, ready to use)
| Skill | Use it when |
|---|---|
| **ship-release** | finishing any shippable change — the exact release flow (bump BOTH version files, CHANGELOG, roadmap, ruff-as-CI, tag, direct-to-main push, CI/CodeQL verify) |
| **backend-tests** | running/adding Python `test_*.py` — the `run_tests.py` runner, the manifest guard, DB-lock cleanup, the two test idioms |
| **verify-frontend** | you changed `apps/web` — typecheck/lint/vitest/build + the tools-panel force-build technique (the dev-preview geometry loader stalls), and honest flagging |
| **security-monitoring** | after a push (standing directive) or a hardening pass — CodeQL **alerts** (not run status), ReDoS/XXE fixes, bandit/pip-audit/npm-audit |

## Recommended external add-ons (opt-in — install/review yourself)
Researched 2026-07-17. **Skills are safe once read; plugins can bundle hooks/MCP — review before install;
hooks auto-execute code — the real supply-chain risk.** Prefer project-local reviewed skills over pulling
arbitrary executable hooks.

- **Superpowers** (obra/superpowers, MIT) — a strong dev methodology as composable skills (brainstorming ·
  git-worktrees · writing-plans · TDD RED-GREEN-REFACTOR · subagent-driven-development · requesting-code-review
  · finishing-a-branch). Matches how we already work. Install via the **official** marketplace for a better
  trust chain: `/plugin install superpowers@claude-plugins-official` — or, for **zero runtime surface**,
  cherry-pick its individual `SKILL.md` files into `.claude/skills/` instead of installing the plugin.
- **Cherry-picked security/testing skills** from the awesome lists (BehiSecc/awesome-claude-skills,
  hesreallyhim/awesome-claude-code) — copy the specific reviewed `SKILL.md` into `.claude/skills/<name>/`:
  Trail-of-Bits security, owasp-security, webapp-testing (Playwright), test-driven-development. Read each
  before committing.
- **Skill_Seekers** (yusufkaraaslan, MIT) — a build-time generator that turns docs (ifcopenshell / web-ifc /
  @thatopen / FastAPI) into local reference skills. Use as a one-off, **human-review every generated
  `SKILL.md`** before it lands. Not wired into runtime.

## Deliberately NOT added
- **No third-party executable hooks** (johnlindquist/claude-hooks and similar). Hooks run arbitrary code on
  every tool event and can make network calls / add a Bun dependency — the main supply-chain vector. If we
  want format/lint-on-edit, add a **self-authored** `PostToolUse` hook in `.claude/settings.json` that shells
  to our *existing* `ruff --fix` / `eslint --fix` — no third-party bodies, no network. (Opt-in: it would run
  automatically on every edit for anyone with the repo, so decide as a team before committing it.)
- **No wholesale `/plugin marketplace add` + install** of unreviewed marketplaces.
- **No PR-diff security-review Action** — `main` ships **direct-to-main (no PRs)**, so it wouldn't fire;
  CodeQL + `.github/workflows/security.yml` + the `security-monitoring` skill already cover it.

## Authoring more
Put a new skill at `.claude/skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`) + a concise
body. Keep it a *workflow* (how to do the thing here), not a fact dump — facts belong in memory.
