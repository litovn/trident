from dataclasses import dataclass
from typing import Awaitable, Callable

from ..core.models import Action, ExecutionResult, TechniqueConfig
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


def make_skill_handler(tech: TechniqueConfig, ctx: SkillContext) -> SkillHandler:
    """Factory: TechniqueConfig + context → callable handler.

    The returned handler carries `.technique` so the SDK-wrapping layer
    (`agents.factory.wrap_as_sdk_tools`) can read metadata without re-lookups.
    """

    async def handler(params: dict) -> dict:
        params = params or {}
        action = Action(technique_id=tech.id, layer=tech.layer, params=params)

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
