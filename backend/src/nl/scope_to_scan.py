from typing import Any

from ..core.models import (
    Layer,
    Manifest,
    Mode,
    Package,
    ScanPlan,
    Scope,
    TargetProfile,
    TechniqueConfig,
    VerticalConfig,
)
from ..skills.registry import SkillRegistry


def _dedup(seq: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for x in seq:
        if x and x not in {"N/A", "—", "-"}:
            seen.setdefault(x, None)
    return list(seen)


def _resolve_layer_cardinality(layers: set[str]) -> str:
    n = len(layers)
    if n <= 1:
        return "single"
    if n == 2:
        return "invalid(2)"
    return "full"


def scope_to_scan(
    scope: Scope,
    manifest: Manifest,
    target: TargetProfile,
    registry: SkillRegistry,
) -> ScanPlan:
    included: list[TechniqueConfig] = []
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()

    # ADR-008: the manifest declares constraints, not the plan. Layer selection
    # is driven by the chosen package projected into scope.techniques_by_layer.
    active_layers: list[Layer] = [
        lyr for lyr in scope.techniques_by_layer if scope.techniques_by_layer[lyr]
    ]

    for layer in active_layers:
        for tid in scope.techniques_by_layer.get(layer, []):
            if tid in seen or tid not in registry.techniques:
                continue
            seen.add(tid)

            if tid in manifest.technique_denylist:
                skipped.append({"id": tid, "layer": layer, "reason": "denylist"})
                continue

            tech = registry.get(tid)

            if manifest.mode == "recon" and tech.phase not in {"recon", "both"}:
                skipped.append({"id": tid, "layer": layer, "reason": "mode_intent"})
                continue
            if not target.supports(tech.needs_capabilities):
                missing = sorted(set(tech.needs_capabilities) - set(target.capabilities))
                skipped.append({"id": tid, "layer": layer,
                                "reason": "missing_capabilities", "missing": missing})
                continue
            if tech.status == "deferred-mvp":
                skipped.append({"id": tid, "layer": layer, "reason": "deferred-mvp"})
                continue

            included.append(tech)

    by_layer: dict[Layer, list[TechniqueConfig]] = {}
    for t in included:
        by_layer.setdefault(t.layer, []).append(t)

    verticals: list[VerticalConfig] = []
    for layer in active_layers:
        techs = by_layer.get(layer)
        if not techs:
            continue
        verticals.append(VerticalConfig(
            layer=layer,
            technique_ids=[t.id for t in techs],
            target_profile=target,
            mode=manifest.mode,
            query_budget=manifest.query_budget_per_vertical,
            surfaces=_dedup([t.surface for t in techs]),
            converters=_dedup([c for t in techs for c in t.converters]),
            objectives=_dedup([o for t in techs for o in t.objectives]),
            scorers=_dedup([t.scorer for t in techs]),
            atlas_chain=[{"id": t.id, "owasp_id": t.owasp_id,
                          "atlas_tactic": t.atlas_tactic,
                          "atlas_technique": t.atlas_technique} for t in techs],
            multi_turn=any(t.interaction == "multi_turn" for t in techs),
        ))

    return ScanPlan(
        campaign_id=manifest.campaign_id,
        scope=scope,
        verticals=verticals,
        skipped=skipped,
        layer_cardinality=_resolve_layer_cardinality(set(by_layer)),
    )


def scope_from_package(package: Package, registry: SkillRegistry) -> Scope:
    """Project a chosen package into the Scope consumed by `scope_to_scan`: group
    the package's techniques by layer. Pure projection — deferred/untargetable
    filtering stays in `scope_to_scan` (the deterministic floor)."""
    by_layer: dict[Layer, list[str]] = {}
    for tid in package.techniques:
        t = registry.techniques.get(tid)
        if t is None:
            continue
        by_layer.setdefault(t.layer, []).append(tid)
    return Scope(
        selection_mode="package",
        selected_package=package.id,
        packages=[package.id],
        techniques_by_layer=by_layer,
        confidence=1.0,  # a human (or the deterministic default) authorized this package
        rationale=f"package {package.id} selected",
    )


def default_package(mode: Mode, registry: SkillRegistry) -> Package:
    """Deterministic non-interactive fallback when no package was chosen (no
    ``--package``, and no Foundry/TTY for the advisor): a sensible default per
    mode, so the coordinator's floor stays reproducible without an LLM."""
    preferred = "PKG-RECON" if mode == "recon" else "PKG-QUICK"
    pkg = registry.packages.get(preferred)
    if pkg is not None:
        return pkg
    for p in registry.packages.values():         # last resort: any mode-eligible package
        if mode in p.modes:
            return p
    raise RuntimeError(f"no package available for mode {mode!r}")
