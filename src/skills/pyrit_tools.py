"""PyRIT primitives exposed as Copilot SDK tools (SCAFFOLD).

Architecture (ADR-revisit, v0.4): the catalog techniques become *skills*
(SKILL.md, see `skillgen.py`) and PyRIT becomes the *tool* surface the agent
composes as it sees fit. Instead of one `@define_tool` per technique, we expose
a small, technique-agnostic set of PyRIT primitives:

    pyrit_send_prompt     — send one prompt (optionally converted) to the target
    pyrit_run_scorer      — evaluate a response with a scorer / success oracle
    pyrit_run_orchestrator— v0 multi-turn loop (Crescendo/TAP placeholder)

Every primitive takes a ``technique_id`` so the gate still enforces the manifest
per-technique and the trace still writes *attributed* ``gate``/``exec`` rows —
which is exactly what keeps ``Scorecard.techniques_fired`` populated.

NOTE: this module is scaffold only. It is intentionally NOT wired into
``agents.factory.build_vertical_session`` yet — that step is left for review.

Implementation note: this module must NOT use ``from __future__ import
annotations``. The SDK's ``@define_tool`` calls ``typing.get_type_hints`` on the
decorated function, which cannot resolve the locally-defined Pydantic ``Params``
classes if their annotations are stored as strings.
"""
from typing import Any

from ..core.models import DETERMINISTIC_SCORERS, Verdict
from .base import SkillContext, make_skill_handler
from .registry import SkillRegistry


def _split_converters(raw: str) -> list[str]:
    return [c.strip() for c in (raw or "").split(",") if c.strip()]


def make_pyrit_tools(registry: SkillRegistry, ctx: SkillContext) -> list:
    """Build the technique-agnostic PyRIT tool surface.

    The returned tools are plain `@define_tool` callables ready to be passed to
    `client.new_session(tools=...)`. They resolve ``technique_id`` against the
    registry so manifest gating and trace attribution are preserved.
    """
    from copilot.tools import define_tool  # type: ignore  (lazy: keep module SDK-free to import)
    from pydantic import BaseModel, Field

    def _resolve(technique_id: str):
        if not registry.has(technique_id):
            return None
        return registry.get(technique_id)

    # ---- pyrit_send_prompt ------------------------------------------------

    class SendPromptParams(BaseModel):
        technique_id: str = Field(description="Catalog technique id this send belongs to (e.g. TRD-PRM-001)")
        prompt: str = Field("", description="Attack prompt. Empty → the technique's first objective is used.")
        converters: str = Field("", description="Comma-separated PyRIT converters to apply (e.g. 'Base64,Flip').")
        endpoint: str = Field("", description="Optional target endpoint (must satisfy host_allowlist).")

    @define_tool(
        name="pyrit_send_prompt",
        description=(
            "Send a single (optionally converted) prompt to the target via PyRIT. "
            "Records a gate decision and an execution result attributed to technique_id. "
            "Returns the target response plus the scorer verdict for the technique."
        ),
    )
    async def pyrit_send_prompt(params: SendPromptParams) -> dict:
        tech = _resolve(params.technique_id)
        if tech is None:
            return {"status": "error", "reason": f"unknown technique_id: {params.technique_id}"}
        handler = make_skill_handler(tech, ctx)
        return await handler({
            "prompt": params.prompt,
            "endpoint": params.endpoint,
            "converters": _split_converters(params.converters),
        })

    # ---- pyrit_run_scorer -------------------------------------------------

    class RunScorerParams(BaseModel):
        scorer: str = Field(description="Scorer name (e.g. leak_detector, exfil_canary, refusal_judge).")
        response: str = Field(description="Target response text to evaluate.")
        technique_id: str = Field("", description="Optional technique id for context / logging.")

    @define_tool(
        name="pyrit_run_scorer",
        description=(
            "Evaluate a target response with a scorer. Deterministic scorers route "
            "through the SuccessOracle (confirmed verdicts); judged scorers return a "
            "v0 surrogate assessment. Informational — does not itself fire a technique."
        ),
    )
    async def pyrit_run_scorer(params: RunScorerParams) -> dict:
        verdict: Verdict
        if params.scorer in DETERMINISTIC_SCORERS:
            verdict = ctx.runner.oracle.detect(params.scorer, params.response)
        elif params.response:
            verdict = Verdict(
                success=True, kind="assessed",
                evidence=f"v0 surrogate for scorer={params.scorer!r}: response present",
            )
        else:
            verdict = Verdict(
                success=False, kind="assessed",
                evidence=f"v0 surrogate for scorer={params.scorer!r}: empty response",
            )
        return {"status": "ok", "scorer": params.scorer, **verdict.model_dump()}

    # ---- pyrit_run_orchestrator ------------------------------------------

    class RunOrchestratorParams(BaseModel):
        technique_id: str = Field(description="Catalog technique id this orchestration belongs to.")
        strategy: str = Field("Crescendo", description="Multi-turn strategy (Crescendo, TAP, PAIR, ...).")
        objective: str = Field("", description="Objective. Empty → the technique's first objective is used.")
        max_turns: int = Field(3, description="Maximum attack turns before giving up.")

    @define_tool(
        name="pyrit_run_orchestrator",
        description=(
            "Run a multi-turn PyRIT orchestrator (Crescendo/TAP/PAIR) against the target. "
            "v0 scaffold: iterates pyrit_send_prompt up to max_turns, stopping on first "
            "success. Each turn is gated and traced under technique_id."
        ),
    )
    async def pyrit_run_orchestrator(params: RunOrchestratorParams) -> dict:
        tech = _resolve(params.technique_id)
        if tech is None:
            return {"status": "error", "reason": f"unknown technique_id: {params.technique_id}"}
        handler = make_skill_handler(tech, ctx)
        turns: list[dict[str, Any]] = []
        for turn in range(max(1, params.max_turns)):
            out = await handler({
                "prompt": params.objective,
                "strategy": params.strategy,
                "turn": turn,
            })
            turns.append(out)
            if out.get("success"):
                break
        return {
            "status": "ok",
            "technique_id": params.technique_id,
            "strategy": params.strategy,
            "turns_used": len(turns),
            "succeeded": any(t.get("success") for t in turns),
            "turns": turns,
        }

    return [pyrit_send_prompt, pyrit_run_scorer, pyrit_run_orchestrator]
