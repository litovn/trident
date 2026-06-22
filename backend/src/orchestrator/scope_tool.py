"""The coordinator's `select_scope` tool — the agentic "analyze" surface over the
deterministic package-projection + gate floor (D-RANK b).

The Coordinator LLM calls `select_scope` once to turn the campaign's NL prompt
into a policy-GATED ScanPlan. The tool body projects the operator-chosen attack
package then runs the deterministic gate/config projection (`scope_to_scan`); the
gate is bundled INSIDE the tool so it always runs and is never separately skippable — the
coordinator never sees an un-gated scope. The gated plan is stashed in the
SkillContext so the dispatch tools can pull each layer's VerticalConfig without
round-tripping JSON through the LLM (G-CO-1), and a coverage-friendly summary
(in-scope verticals + skipped-with-reasons, C3) is returned to the coordinator.

NOTE: like ``skills/pyrit_tools.py`` this module must NOT use
``from __future__ import annotations`` — the SDK's ``@define_tool`` calls
``typing.get_type_hints`` on the decorated function and cannot resolve a locally
defined Pydantic params class if its annotations are stored as strings.
"""
from ..core.models import Manifest, Package, ScanPlan, TargetProfile
from ..nl.scope_to_scan import default_package, scope_from_package, scope_to_scan
from ..skills.base import SkillContext
from ..skills.registry import SkillRegistry

# Layer → dispatch-tool suffix (dispatch_<suffix>_agent), surfaced to the LLM so
# it knows exactly which tool to call for each in-scope layer.
_TOOL_SUFFIX = {"prompt": "prompt", "application": "app", "model": "model"}


def select_scope_plan(
    manifest: Manifest,
    target_profile: TargetProfile,
    registry: SkillRegistry,
    ctx: SkillContext,
    *,
    chosen_package: Package | None = None,
) -> ScanPlan:
    """Deterministic seam: project the chosen package → gate → gated ScanPlan,
    stashed in ``ctx``.

    The package is selected upstream (operator + conversational advisor in the
    CLI, or an explicit ``--package``); here we only project it and run the
    deterministic gate. When no package was chosen (non-interactive / no Foundry),
    fall back to a sensible ``default_package`` so the floor stays reproducible.
    Shared by the `select_scope` SDK tool and the coordinator's deterministic floor.
    """
    pkg = chosen_package or default_package(manifest.mode, registry)
    scope = scope_from_package(pkg, registry)
    plan = scope_to_scan(scope, manifest, target_profile, registry)
    ctx.scan_plan = plan
    return plan


def plan_summary(plan: ScanPlan) -> dict:
    """Compact, LLM-facing view of the gated plan + honest coverage (C3)."""
    return {
        "campaign_id": plan.campaign_id,
        "layer_cardinality": plan.layer_cardinality,
        "in_scope": [
            {
                "layer": v.layer,
                "dispatch_tool": f"dispatch_{_TOOL_SUFFIX.get(v.layer, v.layer)}_agent",
                "technique_ids": v.technique_ids,
                "query_budget": v.query_budget,
            }
            for v in plan.verticals
        ],
        # [{id, layer, reason, missing?}] — what was NOT tested and why (coverage).
        "skipped": plan.skipped,
    }


def make_select_scope_tool(
    manifest: Manifest,
    target_profile: TargetProfile,
    registry: SkillRegistry,
    ctx: SkillContext,
    *,
    chosen_package: Package | None = None,
):
    """Build the `select_scope` SDK tool. The attack package is chosen upstream
    (operator + advisor, or ``--package``) and bound here at build time, so the
    LLM decides WHEN to project/gate it, not WHAT to select — the gate stays
    deterministic and the coordinator never sees an un-gated scope."""
    from copilot.tools import define_tool  # type: ignore  (lazy: keep import SDK-free)
    from pydantic import BaseModel

    class SelectScopeParams(BaseModel):
        pass

    @define_tool(
        name="select_scope",
        description=(
            "Return the policy-gated red-team plan for the chosen attack package: "
            "the in-scope layers/techniques (each with the dispatch tool to call) and "
            "what was skipped and why. Call this FIRST, before any dispatch."
        ),
    )
    async def select_scope(params: SelectScopeParams) -> dict:
        plan = select_scope_plan(manifest, target_profile, registry, ctx,
                                 chosen_package=chosen_package)
        return plan_summary(plan)

    return select_scope
