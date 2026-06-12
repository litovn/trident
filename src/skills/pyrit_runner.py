from typing import Any

from ..core.models import DETERMINISTIC_SCORERS, ExecutionResult, Severity, TechniqueConfig, Verdict
from ..targets.adapter import TargetAdapter
from ..targets.oracle import NullOracle, SuccessOracle, resolve_placeholders


# Data classification → MSRC-style severity bump on confirmed leaks.
_SEVERITY_BY_CLASS: dict[str, Severity] = {
    "Highly Confidential": "critical",
    "Confidential":        "high",
    "General":             "medium",
    "Public":              "low",
}


class PyritRunner:
    """Centralized executor — every skill funnels through here."""

    def __init__(self, oracle: SuccessOracle | None = None) -> None:
        self.oracle: SuccessOracle = oracle or NullOracle()

    async def execute(
        self,
        tech: TechniqueConfig,
        params: dict[str, Any],
        target: TargetAdapter,
    ) -> ExecutionResult:
        # Pick the prompt: explicit override → first objective (canary-resolved) → desc
        objective = params.get("objective")
        if not objective and tech.objectives:
            objective = tech.objectives[0]
        resolved_objective = (
            resolve_placeholders(objective, self.oracle.context(target_name=target.id))
            if objective else None
        )
        prompt = params.get("prompt") or resolved_objective or tech.desc

        response = await target.send(prompt)
        verdict = self._score(tech, response.text)

        # Severity: baseline; bump on confirmed disclosure-class hits
        severity: Severity = tech.severity_base
        if verdict.success and verdict.data_classification:
            severity = _SEVERITY_BY_CLASS.get(verdict.data_classification, severity)

        return ExecutionResult(
            success=verdict.success,
            verdict=verdict.kind,
            response=response.text,
            evidence=verdict.evidence,
            score=verdict.score,
            severity=severity,
            data_classification=verdict.data_classification,
            metadata={
                "target": target.id,
                "converters": tech.converters,
                "scorer": tech.scorer,
                "objective_resolved": resolved_objective,
            },
        )

    # ---- scoring -------------------------------------------------------

    def _score(self, tech: TechniqueConfig, response_text: str) -> Verdict:
        """Route to the oracle for deterministic scorers; v0 fallback otherwise."""
        if tech.scorer in DETERMINISTIC_SCORERS:
            return self.oracle.detect(tech.scorer, response_text)
        # Judged/cumulative: v0 surrogate — response present = assessed success.
        # v1 wires PyRIT SelfAsk scorers here (see catalog/scorers.md).
        if response_text:
            return Verdict(
                success=True, kind="assessed",
                evidence=f"v0 surrogate for scorer={tech.scorer!r}: response present",
            )
        return Verdict(success=False, kind="assessed",
                       evidence=f"v0 surrogate for scorer={tech.scorer!r}: empty response")
