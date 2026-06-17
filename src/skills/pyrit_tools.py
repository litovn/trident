"""PyRIT primitives exposed as Copilot SDK tools.

Architecture (ADR-revisit, v0.4): catalog techniques are *skills* (each authored
as a ``SKILL.md`` — the single source of truth); PyRIT is the *tool* surface the
agent composes. Instead
of one ``@define_tool`` per technique we expose three technique-agnostic
primitives:

    pyrit_send_prompt      — single-turn send (catalog converters applied)
    pyrit_run_scorer       — evaluate a response (deterministic or judged)
    pyrit_run_orchestrator — multi-turn attack via real PyRIT ``CrescendoAttack``

Every primitive takes a ``technique_id`` so the gate still enforces the manifest
per technique and the trace still writes attributed ``gate``/``exec`` rows.

Implementation note: this module must NOT use ``from __future__ import
annotations``. The SDK's ``@define_tool`` calls ``typing.get_type_hints`` on the
decorated function, which cannot resolve the locally-defined Pydantic ``Params``
classes if their annotations are stored as strings.

Caveats (v0.4):
  * ``pyrit_run_orchestrator`` runs real ``CrescendoAttack`` only when a judge
    target is available (FOUNDRY_ENDPOINT set). Without Foundry it falls back
    to a single ``pyrit_send_prompt`` and the return marks ``kind: "no_judge_fallback"``.
  * The Crescendo path bypasses the per-turn ``PolicyGate``: each turn talks to
    the target through ``TridentPromptTarget``, not through the gated handler.
    The enclosing technique IS gated once. Tighten in v0.5 if needed.
"""
from typing import Any

from ..core.models import DETERMINISTIC_SCORERS, Verdict
from .base import SkillContext, make_skill_handler
from .judge_factory import score_judged_async
from .registry import SkillRegistry
from .scorer_factory import score_deterministic


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
        endpoint: str = Field("", description="Optional target endpoint (must satisfy host_allowlist).")

    @define_tool(
        name="pyrit_send_prompt",
        description=(
            "Send a single prompt to the target via PyRIT. The converters declared by "
            "the technique in the catalog are applied automatically; per-call overrides "
            "are not supported in v0. Records a gate decision and an execution result "
            "attributed to technique_id. Returns the target response plus the scorer "
            "verdict for the technique."
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
        })

    # ---- pyrit_run_scorer -------------------------------------------------

    class RunScorerParams(BaseModel):
        scorer: str = Field(description="Scorer name (e.g. leak_detector, exfil_canary, refusal_judge).")
        response: str = Field(description="Target response text to evaluate.")
        objective: str = Field("", description="For judged scorers: the objective to evaluate against.")
        technique_id: str = Field("", description="Optional technique id for context / logging.")

    @define_tool(
        name="pyrit_run_scorer",
        description=(
            "Evaluate a target response with a scorer. Deterministic scorers route "
            "through PyRIT SubStringScorer / MarkdownInjectionScorer (confirmed). "
            "Judged scorers route through PyRIT SelfAskRefusalScorer / "
            "SelfAskTrueFalseScorer (assessed) when Foundry is configured; otherwise "
            "fall back to the v0 refusal heuristic. Informational — does not itself "
            "fire a technique."
        ),
    )
    async def pyrit_run_scorer(params: RunScorerParams) -> dict:
        verdict: Verdict
        if params.scorer in DETERMINISTIC_SCORERS:
            verdict = await score_deterministic(params.scorer, params.response, ctx.runner.oracle)
        else:
            verdict = await score_judged_async(
                params.scorer, params.response,
                objective=params.objective or None,
                judge_target=ctx.runner._judge_target,
            )
        return {"status": "ok", "scorer": params.scorer, **verdict.model_dump()}

    # ---- pyrit_run_orchestrator ------------------------------------------

    class RunOrchestratorParams(BaseModel):
        technique_id: str = Field(description="Catalog technique id this orchestration belongs to.")
        strategy: str = Field("Crescendo", description="Multi-turn strategy. v0.4 supports 'Crescendo'.")
        objective: str = Field("", description="Objective. Empty → the technique's first objective is used.")
        max_turns: int = Field(10, description="Maximum attack turns before giving up.")

    @define_tool(
        name="pyrit_run_orchestrator",
        description=(
            "Run a real PyRIT multi-turn attack against the target. v0.4 supports "
            "'Crescendo' (gradual escalation with an adversarial LLM driving turn-by-turn "
            "prompts). Requires Foundry to be configured (the adversarial LLM). When "
            "Foundry is not configured, the call returns 'no_judge_fallback' and the "
            "agent should use pyrit_send_prompt instead."
        ),
    )
    async def pyrit_run_orchestrator(params: RunOrchestratorParams) -> dict:
        tech = _resolve(params.technique_id)
        if tech is None:
            return {"status": "error", "reason": f"unknown technique_id: {params.technique_id}"}

        judge_target = ctx.runner._judge_target
        if judge_target is None:
            handler = make_skill_handler(tech, ctx)
            out = await handler({"prompt": params.objective, "strategy": params.strategy})
            return {
                "status": "ok",
                "kind": "no_judge_fallback",
                "reason": "FOUNDRY_ENDPOINT not configured — Crescendo needs an adversarial LLM",
                "technique_id": params.technique_id,
                "single_turn_result": out,
            }

        from pyrit.executor.attack.multi_turn.crescendo import (
            AttackAdversarialConfig, CrescendoAttack,
        )
        from .trident_prompt_target import TridentPromptTarget

        objective = params.objective or (tech.objectives[0] if tech.objectives else tech.desc)

        target_wrapper = TridentPromptTarget(ctx.target)
        attack = CrescendoAttack(
            objective_target=target_wrapper,
            attack_adversarial_config=AttackAdversarialConfig(target=judge_target),
            max_turns=max(1, params.max_turns),
        )
        result = await attack.execute_async(objective=objective)

        outcome = getattr(result, "outcome", None)
        succeeded = str(outcome).lower().endswith("success") if outcome is not None else False
        return {
            "status": "ok",
            "kind": "crescendo",
            "technique_id": params.technique_id,
            "strategy": "Crescendo",
            "objective": objective,
            "turns_used": getattr(result, "executed_turns", None),
            "succeeded": succeeded,
            "outcome": str(outcome) if outcome is not None else None,
            "conversation_id": getattr(result, "conversation_id", None),
        }

    return [pyrit_send_prompt, pyrit_run_scorer, pyrit_run_orchestrator]
