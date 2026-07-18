# AI over the model — MCP server + standards experts

Two ways an AI works *with* a project here, both offline-first and grounded in real data (never a
model guessing from memory):

## 1. Standards-compliance experts

`GET /projects/{id}/standards/check?standard=iso19650|cobie|ids|uniclass` runs the named standard
against the project's own records — the CDE, the requirements register, the asset data, the model
quality index — and returns findings, each with the **clause it references** and a recommendation,
plus a 0–100 readiness score. Reachable in the app under **Construction ▸ CDE / Standards ▸
Compliance check**. Fully deterministic; no API key needed.

## 2. MCP server (external agents drive the platform)

The [Model Context Protocol](https://modelcontextprotocol.io) lets an AI client — Claude Desktop,
Cursor, an agent — call this project's tools by name. The catalog is at `GET /mcp/tools`; the stdio
server is `services/api/mcp_server.py`. Tools available:

| Tool | What it does |
|------|--------------|
| `list_projects` | list projects |
| `project_snapshot` | cross-module status (RFIs, schedule, budget, risk) |
| `list_records` | records of any module (rfi, information_container, …) |
| `cde_status` | ISO 19650 CDE container discipline |
| `bim_kpi_scorecard` | the 10-category BIM KPI scorecard |
| `openbim_quality` | LOIN / IDS / export-health / bSDD (needs a loaded model) |
| `standards_check` | run a standards-compliance check |
| `list_recipes` | the authoring-coverage matrix — every recipe `run_recipe` can drive |
| `schedule_risk` | Monte Carlo P10/P50/P80/P90 completion + delay drivers |
| `carbon_report` | A1–A3 embodied carbon + Buy Clean + LEED inventory (needs a model) |
| `permit_readiness` | submission-readiness over egress + code + sheet coverage (needs a model) |
| `drawing_qa` | drawing-set QA — duplicate/gap numbers, titleblock, model cross-checks |
| `create_rfi` | create an RFI (a **write** tool) |
| `run_recipe` | drive a GUID-stable authoring recipe (add_wall, set_pset, …) (a **write** tool) |

The two write tools carry the same **editor**-role gate as their HTTP routes when `AEC_RBAC=1`, so an
agent can never author or create records the acting identity couldn't through the UI. `run_recipe` saves a
new audited, undoable IFC version but leaves reconvert/publish to the normal flow.

The MCP SDK is an **optional** dependency (the platform is offline-first and doesn't force it). To
enable the server:

```bash
pip install "mcp[cli]"
cd services/api
PYTHONPATH=src DATABASE_URL=postgresql://… python mcp_server.py     # stdio server
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "massing": {
      "command": "python",
      "args": ["/path/to/services/api/mcp_server.py"],
      "env": {
        "PYTHONPATH": "/path/to/services/api/src",
        "DATABASE_URL": "postgresql://user:pass@host/db"
      }
    }
  }
}
```

The tool logic lives in `aec_api.mcp_tools` and reuses the same engines the HTTP API does, so an
agent's reads and writes go through the exact same validation and workflow gates as the UI — nothing
is duplicated, and the MCP surface can never do something a normal API caller can't.

## 3. Skill pack (agent playbooks)

A drop-in Claude **skill pack** ships at [`docs/mcp-skills/`](mcp-skills/SKILL.md): a `SKILL.md` plus three
copy-ready workflow playbooks — [draft an RFI](mcp-skills/draft-rfi.md), [run a takeoff](mcp-skills/run-takeoff.md)
(quantities/cost/carbon), and [drive a recipe](mcp-skills/drive-a-recipe.md) (safe GUID-stable authoring:
discover → precheck → apply → publish → verify). Point a Claude environment at it so an agent knows *how* to
use the tools above, not just *that* they exist — read before writing, ground every action in the project's
real state, and respect the compliance boundary.
