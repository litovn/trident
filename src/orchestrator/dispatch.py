import logging
import os

from ..core.client import TridentClient
from ..core.models import Layer, Scorecard, VerticalConfig
from ..core.trace import Trace
from ..skills.base import SkillContext
from ..skills.registry import SkillRegistry

log = logging.getLogger(__name__)

# Per-vertical Copilot SDK session timeout (see coordinator.py for rationale).
_VERTICAL_TIMEOUT = float(os.environ.get("TRIDENT_VERTICAL_TIMEOUT", "1200"))


def _response_text(response) -> str:
    """Extract the agent's final narrative from an SDK response (G-CO-2)."""
    return getattr(getattr(response, "data", None), "content", "") if response else ""


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


async def run_layer(
    client: TridentClient,
    registry: SkillRegistry,
    ctx: SkillContext,
    layer: Layer,
    *,
    rationale: str = "",
) -> dict:
    """Run one vertical sub-agent against the GATED plan, returning its scorecard
    plus the agent's own narrative report (G-CO-2).

    Shared by the `dispatch_*` SDK tools and the coordinator's deterministic
    floor, so the guardrails below hold regardless of who calls it:
      * refuse if `select_scope` hasn't produced a plan yet;
      * refuse a layer that is not in the gated plan (R4 — out-of-scope dispatch);
      * skip a layer that already ran (R3 — per-layer idempotency).
    The VerticalConfig is pulled from the stashed plan, never relayed as JSON
    through the LLM (G-CO-1).
    """
    plan = ctx.scan_plan
    if plan is None:
        return {"status": "refused", "layer": layer,
                "reason": "no plan yet — call select_scope first"}
    vcfg = next((v for v in plan.verticals if v.layer == layer), None)
    if vcfg is None:  # R4: the LLM asked for a layer the gate did not allow
        in_scope = [v.layer for v in plan.verticals]
        return {"status": "refused", "layer": layer,
                "reason": f"layer not in gated plan (in scope: {in_scope})"}
    if layer in ctx.dispatched_layers:  # R3: idempotency (only COMPLETED layers)
        return {"status": "skipped", "layer": layer, "reason": "already dispatched"}
    # Claim the layer up-front so a concurrent re-dispatch is rejected (the
    # check+add is atomic — no await between them). The claim is RELEASED on
    # failure below so a transient error doesn't permanently drop the layer
    # (the floor can then retry it once).
    ctx.dispatched_layers.add(layer)

    # Lazy import: keeps this module loadable without the SDK / PyRIT installed
    # (build_vertical_session pulls in make_pyrit_tools → pyrit).
    from ..agents.briefs import build_brief
    from ..agents.factory import build_vertical_session

    log.info("dispatch layer=%s techniques=%s rationale=%r",
             layer, vcfg.technique_ids, rationale)
    ctx.trace.append_dispatch(layer, {"event": "begin",
                                      "techniques": vcfg.technique_ids,
                                      "rationale": rationale})
    try:
        session = await build_vertical_session(client, vcfg, registry, ctx)
        response = await session.send_and_wait(build_brief(vcfg), timeout=_VERTICAL_TIMEOUT)
    except Exception as exc:  # vertical session failed — release & surface
        ctx.dispatched_layers.discard(layer)
        log.exception("dispatch layer=%s failed", layer)
        ctx.trace.append_dispatch(layer, {"event": "error", "error": str(exc)})
        return {"status": "error", "layer": layer, "error": str(exc)}
    agent_report = _response_text(response)  # the vertical's OWN report (G-CO-2)

    scorecard = _collect_scorecard(ctx.trace, vcfg)
    ctx.trace.append_dispatch(layer, {"event": "end",
                                      "scorecard": scorecard.model_dump(),
                                      "agent_report": agent_report})
    return {**scorecard.model_dump(), "agent_report": agent_report}


def make_dispatch_tools(client: TridentClient, registry: SkillRegistry, ctx: SkillContext):
    """Build the 3 `dispatch_*` tools the Coordinator Session exposes.

    The tools take NO scan-plan argument — each pulls its VerticalConfig from the
    gated plan stashed in ``ctx`` by `select_scope` (G-CO-1). The coordinator just
    DECIDES which layers to dispatch; the config is never relayed through the LLM.
    """
    from copilot.tools import define_tool  # type: ignore
    from pydantic import BaseModel, Field

    class DispatchParams(BaseModel):
        rationale: str = Field("", description="Why dispatch this layer now (for the report).")

    @define_tool(description="Dispatch the Prompt-layer red team vertical (config from the gated plan).")
    async def dispatch_prompt_agent(params: DispatchParams) -> dict:
        return await run_layer(client, registry, ctx, "prompt", rationale=params.rationale)

    @define_tool(description="Dispatch the Application-layer red team vertical (config from the gated plan).")
    async def dispatch_app_agent(params: DispatchParams) -> dict:
        return await run_layer(client, registry, ctx, "application", rationale=params.rationale)

    @define_tool(description="Dispatch the Model-layer red team vertical (config from the gated plan).")
    async def dispatch_model_agent(params: DispatchParams) -> dict:
        return await run_layer(client, registry, ctx, "model", rationale=params.rationale)

    return [dispatch_prompt_agent, dispatch_app_agent, dispatch_model_agent]
