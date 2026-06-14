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

v0 honesty caveats:
  * ``pyrit_run_orchestrator`` is a STUB — it loops ``pyrit_send_prompt`` with
    the same prompt N times. Real Crescendo/TAP/PAIR (turn-evolving attacker
    LLM, conversational memory) arrives with the actual PyRIT install. The tool
    response sets ``kind: "stub_v0"`` so the agent knows.
  * Converters declared in the catalog (``technique.converters``) ARE applied
    via ``PyritRunner``. Per-call converter overrides from the agent are NOT
    accepted yet, because the runner would silently ignore them — adding the
    field would lie to the agent. Re-introduce once PyRIT is wired for real.
"""
from typing import Any

from ..core.models import DETERMINISTIC_SCORERS, Verdict
from .base import SkillContext, make_skill_handler
from .pyrit_runner import judged_verdict_v0
from .registry import SkillRegistry


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
        technique_id: str = Field("", description="Optional technique id for context / logging.")

    @define_tool(
        name="pyrit_run_scorer",
        description=(
            "Evaluate a target response with a scorer. Deterministic scorers route "
            "through the SuccessOracle (confirmed verdicts); judged scorers use a v0 "
            "refusal heuristic (refusals → failure, otherwise → tentative success). "
            "Informational — does not itself fire a technique."
        ),
    )
    async def pyrit_run_scorer(params: RunScorerParams) -> dict:
        verdict: Verdict
        if params.scorer in DETERMINISTIC_SCORERS:
            verdict = ctx.runner.oracle.detect(params.scorer, params.response)
        else:
            verdict = judged_verdict_v0(params.scorer, params.response)
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
            "STUB (v0): does NOT yet run a real PyRIT orchestrator. Iterates "
            "pyrit_send_prompt up to max_turns with the same objective each turn, "
            "stopping on first success. Each turn is gated and traced under "
            "technique_id. The response includes kind='stub_v0' so callers know "
            "this is not real Crescendo/TAP/PAIR; turn-evolving attacker prompts "
            "arrive once PyRIT is wired for real."
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
            "kind": "stub_v0",
            "technique_id": params.technique_id,
            "strategy": params.strategy,
            "turns_used": len(turns),
            "succeeded": any(t.get("success") for t in turns),
            "turns": turns,
        }

    return [pyrit_send_prompt, pyrit_run_scorer, pyrit_run_orchestrator]
