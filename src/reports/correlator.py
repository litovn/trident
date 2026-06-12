from ..core.models import Scorecard


def correlate(scorecards: list[Scorecard]) -> dict:
    layers = [sc.layer for sc in scorecards]
    return {
        "layers_executed": layers,
        "total_techniques_fired": sum(len(sc.techniques_fired) for sc in scorecards),
        "total_successes": sum(sc.successes for sc in scorecards),
        "total_blocked": sum(sc.blocked for sc in scorecards),
        "total_failed": sum(sc.failed for sc in scorecards),
        "asr_per_layer": {sc.layer: sc.asr for sc in scorecards},
        "oracle_hits_per_layer": {sc.layer: sc.oracle_hits for sc in scorecards},
        "potential_chains": [],  # v1: ATLAS chain construction across verticals
        "coverage": {"in_scope": layers, "tested": layers},  # v1: real coverage metric
        "scorecards": [sc.model_dump() for sc in scorecards],
    }
