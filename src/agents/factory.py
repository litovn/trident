from typing import Iterable

from ..core.client import TridentClient
from ..core.models import VerticalConfig
from ..skills.base import SkillContext, SkillHandler, make_skill_handler
from ..skills.pyrit_tools import make_pyrit_tools
from ..skills.registry import SkillRegistry
from .briefs import VERTICAL_PERSONAS


def _sanitize_tool_name(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")


def wrap_as_sdk_tools(handlers: Iterable[SkillHandler]) -> list:
    """Wrap plain skill handlers in `@define_tool` so the SDK can register them.

    Each tool exposes a tiny Params model (`prompt` + optional `endpoint`).
    The handler-internal gate already enforces the manifest, so callers can
    pass arbitrary prompts safely.

    Legacy: kept for the fallback path (`fan_out_directly` builds these too if
    asked); the agentic path now uses `make_pyrit_tools` instead.
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


async def fan_out_directly(
    handlers: Iterable[SkillHandler],
    *,
    prompt: str = "",
) -> list[dict]:
    """Deterministic fallback: run every handler sequentially, no Session/LLM.

    Used when the agentic path is disabled (smoke tests, CI, or when the
    Coordinator LLM declines to drive the verticals). Each handler still goes
    through the gate and the trace via `make_skill_handler`, so policy and
    attribution are preserved end-to-end. Returns the raw handler results.
    """
    results: list[dict] = []
    for handler in handlers:
        results.append(await handler({"prompt": prompt}))
    return results


async def build_vertical_session(
    client: TridentClient,
    vcfg: VerticalConfig,
    registry: SkillRegistry,
    ctx: SkillContext,
):
    """Create a Session for one vertical with the PyRIT tool surface.

    The agent loads the catalog techniques as *skills* (SKILL.md, see
    `skillgen.py`) from ``ctx.skills_dir`` and composes them through the three
    technique-agnostic PyRIT tools (`pyrit_send_prompt`, `pyrit_run_scorer`,
    `pyrit_run_orchestrator`). Per-technique policy enforcement is preserved
    because every tool call routes through `make_skill_handler` which calls
    the gate under the supplied ``technique_id``.
    """
    tools = make_pyrit_tools(registry, ctx)
    return await client.new_session(
        role=vcfg.layer,
        tools=tools,
        agent_prompt=VERTICAL_PERSONAS[vcfg.layer],
        skill_directories=[ctx.skills_dir],
        enable_skills=True,
    )
