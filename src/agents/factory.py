from ..core.client import TridentClient
from ..core.models import VerticalConfig
from ..skills.base import SkillContext
from ..skills.pyrit_tools import make_pyrit_tools
from ..skills.registry import SkillRegistry
from .briefs import VERTICAL_PERSONAS


async def build_vertical_session(
    client: TridentClient,
    vcfg: VerticalConfig,
    registry: SkillRegistry,
    ctx: SkillContext,
):
    """Create a Session for one vertical with the PyRIT tool surface.

    The agent loads the catalog techniques as *skills* (each a `SKILL.md`, the
    single source of truth) from ``ctx.skills_dir`` and composes them through the
    three technique-agnostic PyRIT tools (`pyrit_send_prompt`, `pyrit_run_scorer`,
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
