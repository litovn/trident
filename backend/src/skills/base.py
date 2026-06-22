from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from ..core.models import Action, ExecutionResult, ScanPlan, TechniqueConfig
from ..core.policy_gate import PolicyGate
from ..core.trace import Trace
from ..targets.adapter import TargetAdapter
from .pyrit_runner import PyritRunner

SkillHandler = Callable[[dict], Awaitable[dict]]


@dataclass
class SkillContext:
    """Everything a skill needs at runtime. One per campaign."""
    gate: PolicyGate
    runner: PyritRunner
    trace: Trace
    target: TargetAdapter
    # Directory containing the SKILL.md trees (one subdir per technique, named
    # with the lowercase technique slug). Passed to
    # `client.create_session(skill_directories=[...])` by the SDK wiring so the
    # Copilot agent can match techniques as skills at runtime.
    skills_dir: str = "catalog/skills_catalog"
    # The policy-gated ScanPlan, stashed by the `select_scope` tool so the
    # dispatch tools can pull each layer's VerticalConfig WITHOUT round-tripping
    # JSON through the LLM (G-CO-1). None until select_scope (or the floor) runs.
    scan_plan: Optional[ScanPlan] = None
    # Layers already dispatched this campaign — the idempotency floor (R3): the
    # dispatch tools refuse to re-run a layer (no double budget / double trace).
    dispatched_layers: set[str] = field(default_factory=set)
    # HITL: when True, run_layer asks the operator to confirm each layer (one
    # attack-chain step) before dispatching it. Set by the CLI only on an
    # interactive TTY, so non-interactive runs never block.
    confirm_chain: bool = False


def make_skill_handler(tech: TechniqueConfig, ctx: SkillContext) -> SkillHandler:
    """Factory: TechniqueConfig + context → callable handler.

    The returned handler carries `.technique` so callers can read the technique
    metadata off the handler without a registry re-lookup.
    """

    async def handler(params: dict) -> dict:
        params = params or {}
        # Fail-closed for host_allowlist: the gate's rule 6 only fires when
        # `endpoint` is present in params. Tools default it to "" and the LLM
        # rarely passes it, so we bind the adapter's real endpoint here.
        gate_params = {**params, "endpoint": params.get("endpoint") or getattr(ctx.target, "endpoint", "")}
        action = Action(technique_id=tech.id, layer=tech.layer, params=gate_params)

        decision = ctx.gate.check(action)
        ctx.trace.append_gate(action, decision)
        if not decision.allow:
            return {
                "status": "refused",
                "technique_id": tech.id,
                "reason": decision.reason,
                "rule": decision.rule,
            }

        result: ExecutionResult = await ctx.runner.execute(tech, params, ctx.target)
        ctx.trace.append_exec(action, result)
        return {"status": "ok", "technique_id": tech.id, **result.as_dict()}

    handler.__name__ = tech.id.replace("-", "_").replace(".", "_")
    handler.__doc__ = tech.description
    handler.technique = tech  # type: ignore[attr-defined]
    return handler
