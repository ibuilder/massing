---
name: massing-bim
description: >-
  Drive a Massing BIM/AEC project from an AI agent over MCP — read a project's status, records, CDE,
  KPI and model-quality checks; run standards-compliance, schedule-risk, embodied-carbon, permit-
  readiness and drawing-QA analyses; author the IFC model with GUID-stable recipes; and draft RFIs.
  Use when the user asks to inspect, analyse, or author a Massing project through Claude.
---

# Massing over MCP

Massing exposes an offline-first [MCP](https://modelcontextprotocol.io) server (`services/api/mcp_server.py`)
that lets you drive a real project through the **same engines the web UI and HTTP API use** — every read
is grounded in the project's own data and every write goes through the identical validation, guardrail,
and audit path. You never guess from memory; you call a tool and report what it returns.

## Connect

```bash
pip install "mcp[cli]"
cd services/api
PYTHONPATH=src DATABASE_URL=postgresql://… python mcp_server.py     # stdio server
```

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "massing": {
    "command": "python",
    "args": ["/path/to/services/api/mcp_server.py"],
    "env": { "PYTHONPATH": "/path/to/services/api/src",
             "DATABASE_URL": "postgresql://user:pass@host/db",
             "AEC_RBAC": "1", "AEC_MCP_USER": "you@firm.com" } } } }
```

Set `AEC_MCP_USER` to the acting identity when `AEC_RBAC=1`: reads are then scoped to that user's member
projects and write tools require **editor** role — the agent can never do what the person couldn't.

## Tools

| Tool | Kind | What it does |
|------|------|--------------|
| `list_projects` | read | projects you can see (id + name) |
| `project_snapshot` | read | cross-module status: RFIs, submittals, COs, punch, safety, schedule + budget KPIs, risk headline |
| `list_records` | read | records of any module (`rfi`, `submittal`, `information_container`, `schedule_activity`, …) |
| `cde_status` | read | ISO 19650 CDE container discipline |
| `bim_kpi_scorecard` | read | the 10-category BIM KPI scorecard |
| `openbim_quality` | read | LOIN / IDS / export-health / bSDD *(needs a loaded model)* |
| `standards_check` | read | run `iso19650` \| `cobie` \| `ids` \| `uniclass` — clause-referenced findings + a readiness score |
| `list_recipes` | read | the authoring-coverage matrix — every recipe `run_recipe` can drive, by category + IFC output |
| `schedule_risk` | read | Monte Carlo P10/P50/P80/P90 completion, criticality index, delay drivers |
| `carbon_report` | read | A1–A3 embodied carbon per element + Buy Clean limits + LEED inventory *(needs a model)* |
| `permit_readiness` | read | submission-readiness over egress + approvability + code analysis + sheet coverage *(needs a model)* |
| `drawing_qa` | read | drawing-set QA — duplicate/gap numbers, titleblock, issuance hygiene, model cross-checks |
| `create_rfi` | **write** | create an RFI |
| `run_recipe` | **write** | drive a GUID-stable authoring recipe (add_wall, add_column, set_pset, …), saving an audited version |

## Workflows

Detailed, copy-ready playbooks live alongside this file:

- [`draft-rfi.md`](draft-rfi.md) — turn a coordination question into a well-formed RFI grounded in the model.
- [`run-takeoff.md`](run-takeoff.md) — pull quantities, cost and carbon signals for an estimate or a check.
- [`drive-a-recipe.md`](drive-a-recipe.md) — author the model safely: discover recipes, precheck params, apply, then publish.

## Ground rules for the agent

1. **Read before you write.** Snapshot the project (or list the relevant records) before creating an RFI
   or editing the model, so your action references real GUIDs, sheet numbers, and current state.
2. **`run_recipe` saves a new IFC version but does not reconvert.** After a batch of edits, tell the user
   the model needs a **publish** (the normal reconvert flow) for the viewer/index to reflect them.
3. **Author with GUID-stable recipes only.** Never fabricate a GUID or hand-write IFC; call `list_recipes`
   to see what's available and `run_recipe` to apply it.
4. **Respect the compliance boundary.** Money movement, KYC, and paid third-party bridges are deliberately
   not exposed — don't try to route around them.
5. **Report the tool's own numbers.** If a model isn't loaded, the analysis tools return a clear
   `"no model loaded"` signal — surface that rather than inventing a result.
