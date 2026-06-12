from typing import Iterable

from ..core.client import TridentClient
from ..core.models import VerticalConfig
from ..skills.base import SkillContext, SkillHandler, make_skill_handler
from ..skills.registry import SkillRegistry
from .briefs import VERTICAL_PERSONAS


def _sanitize_tool_name(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")


def wrap_as_sdk_tools(handlers: Iterable[SkillHandler]) -> list:
    """Wrap plain skill handlers in `@define_tool` so the SDK can register them.

    Each tool exposes a tiny Params model (`prompt` + optional `endpoint`).
    The handler-internal gate already enforces the manifest, so callers can
    pass arbitrary prompts safely.
    """
    from copilot.tools import define_tool  # type: ignore
    from pydantic import BaseModel, Field

    tools = []
    for handler in handlers:
        tech = handler.technique  # type: ignore[attr-defined]

        class Params(BaseModel):
            prompt: str = Field("", description="Attack prompt or objective for this technique")
            endpoint: str = Field("", description="Optional target endpoint (must match host_allowlist)")

        Params.__name__ = f"{_sanitize_tool_name(tech.id)}Params"

        @define_tool(description=tech.description, name=_sanitize_tool_name(tech.id))
        async def _tool(params: Params, _h=handler):  # closure binds the handler
            return await _h(params.model_dump())

        tools.append(_tool)
    return tools


async def build_vertical_session(
    client: TridentClient,
    vcfg: VerticalConfig,
    registry: SkillRegistry,
    ctx: SkillContext,
):
    """Create a Session for one vertical with its fenced tool subset."""
    techs = registry.for_layer(vcfg.layer, vcfg.technique_ids)
    handlers = [make_skill_handler(t, ctx) for t in techs]
    tools = wrap_as_sdk_tools(handlers)
    return await client.new_session(
        role=vcfg.layer,
        tools=tools,
        agent_prompt=VERTICAL_PERSONAS[vcfg.layer],
    )
