"""Bonsai-MCP bridge client — drives the safe authoring recipes against a live Blender + Bonsai
session over the add-on's socket, with the safety gates required by CLAUDE.md:
  - save the .ifc *before* executing (so any edit is recoverable),
  - chunk large selections to `max_elements_per_call`,
  - require an explicit confirm before any execute_blender_code (it runs arbitrary Python).

`plan()` is pure (no Blender, no socket) so the gating is testable offline; `execute()` sends the
plan to the Bonsai socket. Default is dry-run, so it's safe by default. The exact recipes live in
recipes.py / services/data/src/aec_data/edit.py and run inside Blender's Python.

REL-5: plan/execute return typed dataclasses (`Plan` / `ExecutionResult`), not loose dicts — the
step shapes are part of the safety contract, so they're spelled out.
"""
from __future__ import annotations

import dataclasses
import json
import math
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).with_name("bonsai-mcp.config.json")


@dataclass(frozen=True)
class PlanStep:
    """One gated step: a `save` (recoverability) or an `execute` (one recipe chunk)."""
    op: str
    why: str | None = None
    recipe: str | None = None
    chunk: int | None = None
    of: int | None = None
    code: str | None = None


@dataclass(frozen=True)
class Plan:
    """The ordered, gated step list for a recipe run — pure, never touches Blender."""
    recipe: str
    element_count: int
    chunks: int
    confirm_required: bool
    steps: list[PlanStep]


@dataclass(frozen=True)
class ExecutionResult:
    """What `execute` did: the plan it followed, whether it was a dry run, and (live only) the
    per-chunk socket responses."""
    dry_run: bool
    plan: Plan
    results: list[Any] = field(default_factory=list)


class BonsaiBridge:
    def __init__(self, config_path: str | Path = CONFIG):
        self.cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.safety = self.cfg.get("safety", {})
        self.sock = self.cfg.get("socket", {"host": "127.0.0.1", "port": 9876})

    # --- pure planning (testable without Blender) -----------------------------
    def _snippet(self, recipe: str, params: dict) -> str:
        """The Python the Bonsai add-on runs: call the named recipe on the active IFC model."""
        return (
            "import bonsai.tool as tool\n"
            "import recipes\n"
            "model = tool.Ifc.get()\n"
            f"recipes.{recipe}(model, **{params!r})\n"
            "tool.Ifc.save()\n"
        )

    def plan(self, recipe: str, params: dict, *, element_count: int = 1) -> Plan:
        """Build the ordered, gated step list for a recipe run. Never touches Blender."""
        cap = int(self.safety.get("max_elements_per_call", 200))
        chunks = max(1, math.ceil(element_count / cap)) if element_count > cap else 1
        steps: list[PlanStep] = []
        if self.safety.get("save_before_execute", True):
            steps.append(PlanStep(op="save", why="recoverable before edit"))
        for i in range(chunks):
            steps.append(PlanStep(
                op="execute", recipe=recipe, chunk=i + 1, of=chunks,
                code=self._snippet(recipe, {**params, "_chunk": i} if chunks > 1 else params)))
        return Plan(recipe=recipe, element_count=element_count, chunks=chunks,
                    confirm_required=bool(self.safety.get("confirm_execute_blender_code", True)),
                    steps=steps)

    # --- live execution over the Bonsai socket --------------------------------
    def execute(self, recipe: str, params: dict, *, element_count: int = 1,
                confirm: bool = False, dry_run: bool = True) -> ExecutionResult:
        plan = self.plan(recipe, params, element_count=element_count)
        if dry_run:
            return ExecutionResult(dry_run=True, plan=plan)
        if plan.confirm_required and not confirm:
            raise PermissionError("execute_blender_code is gated — pass confirm=True to run arbitrary Python in Blender")
        results = [self._send({"type": "execute_code", "code": s.code})
                   for s in plan.steps if s.op == "execute"]
        return ExecutionResult(dry_run=False, plan=plan, results=results)

    def _send(self, payload: dict, timeout: float = 15.0) -> Any:
        with socket.create_connection((self.sock["host"], self.sock["port"]), timeout=timeout) as s:
            s.sendall((json.dumps(payload) + "\n").encode())
            buf = b""
            s.settimeout(timeout)
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        return json.loads(buf.decode() or "{}")


if __name__ == "__main__":   # tiny CLI: python bridge.py set_pset '{"ifc_class":"IfcSlab",...}' [--run]
    import sys
    recipe = sys.argv[1] if len(sys.argv) > 1 else "set_pset"
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    live = "--run" in sys.argv
    out = BonsaiBridge().execute(recipe, params, confirm=live, dry_run=not live)
    print(json.dumps(dataclasses.asdict(out), indent=2))
