"""Correlation & coverage — turns per-vertical scorecards into the report payload.

Three real outputs (no longer stubs):
  * potential_chains — cross-layer ATLAS kill-chains, **correlated post-hoc**
    (TRIDENT identifies/correlates chains; it does NOT autonomously execute
    emergent exploits — keep that wording honest, see design §3).
  * coverage — honest: what was planned vs tested vs excluded (with reasons).
  * remediation — Microsoft controls that address the successful findings.
"""
from ..core.models import ScanPlan, Scorecard
from ..core.trace import Trace
from ..skills.registry import SkillRegistry

# MSRC severity rank (for blast-radius = the worst severity in a chain).
_SEV_RANK: dict[str, int] = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
_RANK_SEV: dict[int, str] = {v: k for k, v in _SEV_RANK.items()}

# MITRE ATLAS tactic order — used to sequence a cross-layer chain like a kill-chain.
_TACTIC_ORDER: dict[str, int] = {
    "Reconnaissance": 0, "Resource Development": 1, "Initial Access": 2,
    "ML Model Access": 3, "ML Attack Staging": 4, "Discovery": 5, "Execution": 6,
    "Persistence": 7, "Privilege Escalation": 8, "Defense Evasion": 9,
    "Credential Access": 10, "Collection": 11, "Exfiltration": 12, "Impact": 13,
}


def scorecards_from_trace(trace: Trace) -> list[Scorecard]:
    """Pull the per-vertical scorecards the dispatch tools wrote to the trace."""
    return [
        Scorecard.model_validate(step.payload["scorecard"])
        for step in trace.steps()
        if step.kind == "dispatch" and "scorecard" in step.payload
    ]


def _tactic_rank(tactic: str) -> int:
    return _TACTIC_ORDER.get((tactic or "").strip(), 99)


def _enrich_successes(scorecards: list[Scorecard], registry: SkillRegistry) -> list[dict]:
    """Successful findings, annotated with catalog OWASP/ATLAS/severity/controls."""
    out: list[dict] = []
    for sc in scorecards:
        for f in sc.findings:
            if not f.get("success"):
                continue
            tid = f.get("technique_id") or ""
            tech = registry.get(tid) if registry.has(tid) else None
            out.append({
                "technique_id": tid,
                "name": tech.name if tech else tid,
                "layer": sc.layer,
                "owasp_id": tech.owasp_id if tech else "",
                "owasp_name": tech.owasp_name if tech else "",
                "atlas_tactic": tech.atlas_tactic if tech else "",
                "atlas_technique": tech.atlas_technique if tech else "",
                "severity": f.get("severity") or (tech.severity_base if tech else "info"),
                "controls": list(tech.controls) if tech else [],
                "evidence": f.get("response", ""),
            })
    return out


def _build_chains(successes: list[dict]) -> list[dict]:
    """A cross-layer chain = successes spanning >= 2 distinct layers, sequenced by
    ATLAS tactic. v1 = one candidate chain (the design correlates post-hoc)."""
    layers_hit = {s["layer"] for s in successes}
    if len(layers_hit) < 2:
        return []  # single-layer findings are not a cross-layer chain
    seq = sorted(successes, key=lambda s: (_tactic_rank(s["atlas_tactic"]), s["layer"]))
    blast = max((_SEV_RANK.get(s["severity"], 1) for s in seq), default=1)
    return [{
        "id": "chain-1",
        "kind": "cross-layer",
        "label": "correlated post-hoc (not autonomously executed)",
        "layers": sorted(layers_hit),
        "blast_radius": _RANK_SEV.get(blast, "info"),
        "steps": [
            {"technique_id": s["technique_id"], "name": s["name"], "layer": s["layer"],
             "owasp_id": s["owasp_id"], "atlas_tactic": s["atlas_tactic"],
             "severity": s["severity"]}
            for s in seq
        ],
    }]


def _coverage(scorecards: list[Scorecard], scanplan: ScanPlan | None) -> dict:
    """Honest coverage: planned vs tested vs excluded (with reasons)."""
    planned = sorted({t for v in (scanplan.verticals if scanplan else []) for t in v.technique_ids})
    tested = sorted({t for sc in scorecards for t in sc.techniques_fired})
    not_tested = [t for t in planned if t not in tested]
    excluded = list(scanplan.skipped) if scanplan else []  # {id, layer, reason, missing?}
    return {
        "planned": planned,
        "tested": tested,
        "not_tested_in_scope": not_tested,
        "excluded_pre_scan": excluded,
        "coverage_pct": round(len(tested) / len(planned), 3) if planned else 0.0,
    }


def _remediation(successes: list[dict]) -> list[dict]:
    """Microsoft controls that address the successful findings, most-impactful first."""
    hits: dict[str, int] = {}
    for s in successes:
        for c in s["controls"]:
            hits[c] = hits.get(c, 0) + 1
    return [{"control": c, "addresses_findings": n}
            for c, n in sorted(hits.items(), key=lambda kv: kv[1], reverse=True)]


def correlate(
    scorecards: list[Scorecard],
    scanplan: ScanPlan | None = None,
    registry: SkillRegistry | None = None,
    *,
    summary: str = "",
) -> dict:
    """Join per-vertical scorecards into the report payload (chains + coverage +
    remediation). ``scanplan`` and ``registry`` enrich the analysis; when omitted
    the function still returns the aggregate totals."""
    successes = _enrich_successes(scorecards, registry) if registry else []
    return {
        "campaign_id": scanplan.campaign_id if scanplan else "",
        "coordinator_summary": summary,
        "layers_executed": [sc.layer for sc in scorecards],
        "total_techniques_fired": sum(len(sc.techniques_fired) for sc in scorecards),
        "total_successes": sum(sc.successes for sc in scorecards),
        "total_blocked": sum(sc.blocked for sc in scorecards),
        "total_failed": sum(sc.failed for sc in scorecards),
        "asr_per_layer": {sc.layer: sc.asr for sc in scorecards},
        "oracle_hits_per_layer": {sc.layer: sc.oracle_hits for sc in scorecards},
        "potential_chains": _build_chains(successes),
        "coverage": _coverage(scorecards, scanplan),
        "remediation": _remediation(successes),
        "findings": successes,
        "scorecards": [sc.model_dump() for sc in scorecards],
    }
