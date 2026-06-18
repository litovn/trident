import os

from ..core.client import TridentClient
from ..core.models import Layer, Scorecard, VerticalConfig
from ..core.trace import Trace
from ..skills.base import SkillContext
from ..skills.registry import SkillRegistry

# Per-vertical Copilot SDK session timeout (see coordinator.py for rationale).
_VERTICAL_TIMEOUT = float(os.environ.get("TRIDENT_VERTICAL_TIMEOUT", "1200"))


def _collect_scorecard(trace: Trace, vcfg: VerticalConfig) -> Scorecard:
    """Aggregate trace rows for this vertical into a Scorecard."""
    fired: set[str] = set()
    successes = blocked = failed = oracle_hits = 0
    findings: list[dict] = []

    for s in trace.for_layer(vcfg.layer):
        if s.kind == "gate":
            allow = s.payload.get("decision", {}).get("allow", False)
            if not allow:
                blocked += 1
        elif s.kind == "exec":
            if s.technique_id:
                fired.add(s.technique_id)
            result = s.payload.get("result", {})
            if result.get("success"):
                successes += 1
            else:
                failed += 1
            # An oracle hit = a SUCCESSFUL deterministic check. The oracle returns
            # verdict="confirmed" for confirmed-negatives too (e.g. "no canary found"),
            # so guard on success to avoid inflating the count.
            if result.get("verdict") == "confirmed" and result.get("success"):
                oracle_hits += 1
            findings.append({
                "technique_id": s.technique_id,
                "success": bool(result.get("success")),
                "verdict": result.get("verdict"),
                "severity": result.get("severity"),
                "response": result.get("response", "")[:200],
            })

    total = max(successes + failed, 1)
    return Scorecard(
        layer=vcfg.layer,
        techniques_fired=sorted(fired),
        successes=successes,
        blocked=blocked,
        failed=failed,
        asr=round(successes / total, 3),
        oracle_hits=oracle_hits,
        findings=findings,
    )


def make_dispatch_tools(client: TridentClient, registry: SkillRegistry, ctx: SkillContext):
    """Build the 3 `dispatch_*` tools that the Coordinator Session exposes."""
    from copilot.tools import define_tool  # type: ignore
    from pydantic import BaseModel, Field

    from ..agents.factory import build_vertical_session
    from ..agents.briefs import build_brief

    class DispatchParams(BaseModel):
        vertical_config_json: str = Field(description="JSON-serialized VerticalConfig for this layer")

    async def _run_layer(layer: Layer, vertical_config_json: str) -> dict:
        vcfg = VerticalConfig.model_validate_json(vertical_config_json)
        if vcfg.layer != layer:
            return {"error": f"config.layer mismatch: {vcfg.layer} != {layer}"}

        ctx.trace.append_dispatch(layer, {"event": "begin", "techniques": vcfg.technique_ids})
        session = await build_vertical_session(client, vcfg, registry, ctx)
        await session.send_and_wait(build_brief(vcfg), timeout=_VERTICAL_TIMEOUT)
        scorecard = _collect_scorecard(ctx.trace, vcfg)
        ctx.trace.append_dispatch(layer, {"event": "end", "scorecard": scorecard.model_dump()})
        return scorecard.model_dump()

    @define_tool(description="Dispatch the Prompt-layer red team vertical")
    async def dispatch_prompt_agent(params: DispatchParams) -> dict:
        return await _run_layer("prompt", params.vertical_config_json)

    @define_tool(description="Dispatch the Application-layer red team vertical")
    async def dispatch_app_agent(params: DispatchParams) -> dict:
        return await _run_layer("application", params.vertical_config_json)

    @define_tool(description="Dispatch the Model-layer red team vertical")
    async def dispatch_model_agent(params: DispatchParams) -> dict:
        return await _run_layer("model", params.vertical_config_json)

    return [dispatch_prompt_agent, dispatch_app_agent, dispatch_model_agent]
