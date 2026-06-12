from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────
# Enums and vocabularies (kept in sync with catalog/schema/catalog.schema.json)
# ──────────────────────────────────────────────────────────────────────────
Layer = Literal["prompt", "application", "model"]
Mode = Literal["recon", "attack"]                       # campaign-level (manifest)
Phase = Literal["recon", "exploit", "both"]             # technique-level (catalog)
ModeIntent = Literal["recon", "exploit"]                # derived from Phase
Severity = Literal["critical", "high", "medium", "low", "info"]   # MSRC AI bug bar
SeverityTrack = Literal["security", "content"]
Surface = Literal["chat", "retrieval_ingest", "search", "tool"]
Intensity = Literal["easy", "moderate", "difficult"]
Interaction = Literal["single_turn", "multi_turn"]
Axis = Literal["profile", "layer", "focus"]
TechniqueScope = Literal["per_attempt", "cumulative"]
VerdictKind = Literal["confirmed", "assessed", "cumulative", "blocked", "failed"]

CAPABILITY_VOCAB: frozenset[str] = frozenset({
    "has_chat", "has_retrieval", "has_tools", "is_agentic",
    "multi_turn", "exposes_system_prompt", "auth", "streaming",
})

OWASP_VOCAB: frozenset[str] = frozenset({
    "LLM01", "LLM02", "LLM03", "LLM04", "LLM05",
    "LLM06", "LLM07", "LLM08", "LLM09", "LLM10", "N/A",
})

CONVERTER_VOCAB: frozenset[str] = frozenset({
    "Baseline", "Base64", "Flip", "Leetspeak", "Morse", "ROT13",
    "UnicodeConfusable", "Url", "Diacritic", "StringJoin", "SuffixAppend",
    "Tense", "IndirectAttack", "Jailbreak", "Crescendo", "Multiturn",
})

SCORER_VOCAB: frozenset[str] = frozenset({
    "exfil_canary", "leak_detector", "output_markup", "categorical_match",
    "refusal_judge", "judged_objective", "cumulative_metric",
})

DETERMINISTIC_SCORERS: frozenset[str] = frozenset({
    "exfil_canary", "leak_detector", "output_markup", "categorical_match",
})

# Phase → which campaign modes the gate lets through (ADR-018)
_PHASE_TO_MODES: dict[Phase, set[Mode]] = {
    "recon":   {"recon", "attack"},
    "exploit": {"attack"},
    "both":    {"recon", "attack"},
}


# ──────────────────────────────────────────────────────────────────────────
# Catalog types
# ──────────────────────────────────────────────────────────────────────────
class TechniqueConfig(BaseModel):
    """One catalog entry (schema v0.3). A PyRIT-backed skill, tagged OWASP × MITRE ATLAS."""
    id: str
    name: str
    desc: str = ""
    layer: Layer
    phase: Phase = "exploit"
    priority: int = 99
    owasp_id: str = "N/A"
    owasp_name: str = ""
    owasp_secondary: str = ""
    atlas_tactic: str = ""
    atlas_technique: str = ""
    surface: Surface = "chat"
    needs_capabilities: list[str] = Field(default_factory=list)
    interaction: Interaction = "single_turn"
    intensity: Intensity = "moderate"
    converters: list[str] = Field(default_factory=list)
    converters_alt: list[str] = Field(default_factory=list)
    scorer: str = "judged_objective"
    objectives: list[str] = Field(default_factory=list)
    severity_base: Severity = "medium"
    severity_track: SeverityTrack = "security"
    controls: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    intent_examples: list[str] = Field(default_factory=list)
    status: str = ""                              # "" or "deferred-mvp"
    scope: TechniqueScope = "per_attempt"
    version: str | float = "0.1"

    # ---- Derived (for back-compat callers and the gate) ----------------

    @property
    def mode_intent(self) -> ModeIntent:
        return "exploit" if self.phase == "exploit" else "recon"

    @property
    def supported_modes(self) -> list[Mode]:
        return sorted(_PHASE_TO_MODES[self.phase])

    @property
    def description(self) -> str:
        """Alias for `desc` (older callers use `description`)."""
        return self.desc

    def runs_in(self, mode: Mode) -> bool:
        return mode in _PHASE_TO_MODES[self.phase]

    # ---- Ranker hooks --------------------------------------------------

    def embedding_text(self) -> str:
        """Indexed text for the semantic lane. Excludes raw taxonomy IDs (noise)
        but includes the human OWASP name + intent_examples."""
        parts = [self.name, self.desc, self.owasp_name, *self.intent_examples]
        return " | ".join(p for p in parts if p)

    def alias_terms(self) -> list[str]:
        """Lexicon-lane terms: aliases + OWASP id (typed shortcut)."""
        terms = [str(a).lower() for a in self.aliases]
        if self.owasp_id and self.owasp_id != "N/A":
            terms.append(self.owasp_id.lower())
        return terms


class Package(BaseModel):
    """Curated bundle of techniques + safe limits + which modes it can run in."""
    id: str
    name: str
    axis: Axis = "profile"
    aliases: list[str] = Field(default_factory=list)
    intent_examples: list[str] = Field(default_factory=list)
    techniques: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    modes: list[Mode] = Field(default_factory=lambda: ["recon", "attack"])

    @property
    def technique_ids(self) -> list[str]:
        """Back-compat alias for older callers."""
        return self.techniques

    @property
    def query_budget(self) -> Optional[int]:
        v = self.limits.get("query_budget")
        return int(v) if v is not None else None

    @property
    def max_intensity(self) -> Optional[str]:
        return self.limits.get("max_intensity")

    def embedding_text(self) -> str:
        return " | ".join(p for p in [self.name, *self.intent_examples] if p)

    def alias_terms(self) -> list[str]:
        return [str(a).lower() for a in self.aliases]


# ──────────────────────────────────────────────────────────────────────────
# Target profile (schema v0.3 — declarative; the adapter implements I/O)
# ──────────────────────────────────────────────────────────────────────────
class TargetProfile(BaseModel):
    """Declarative target profile. Implementation lives in a TargetAdapter that consumes this."""
    id: str
    name: str = ""
    base_url: str = ""
    capabilities: list[str] = Field(default_factory=list)
    surfaces: dict[str, dict[str, Any]] = Field(default_factory=dict)
    auth: dict[str, Any] = Field(default_factory=dict)
    defense_levels: list[str] = Field(default_factory=list)
    success_oracle: dict[str, Any] = Field(default_factory=dict)
    egress: str = "local-only"
    ctf_challenge_mapping: str | bool = ""
    notes: str = ""

    @property
    def endpoint(self) -> str:
        """Back-compat alias used in older briefs/logging code paths."""
        return self.base_url

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def supports(self, needs: list[str]) -> bool:
        return set(needs).issubset(self.capabilities)


# ──────────────────────────────────────────────────────────────────────────
# Manifest (Rules of Engagement as Code — ADR-008)
# ──────────────────────────────────────────────────────────────────────────
class Manifest(BaseModel):
    campaign_id: str
    mode: Mode = "recon"
    target_profile_id: str
    layers: list[Layer]                                       # 1 or all 3, never exactly 2 (ADR-021)
    technique_allowlist: list[str] = Field(default_factory=list)
    technique_denylist: list[str] = Field(default_factory=list)
    host_allowlist: list[str] = Field(default_factory=list)
    query_budget_per_vertical: int = 100
    hitl_techniques: list[str] = Field(default_factory=list)
    egress_local_only: bool = True


# ──────────────────────────────────────────────────────────────────────────
# Scope / Plan
# ──────────────────────────────────────────────────────────────────────────
class Scope(BaseModel):
    """Output of the NL ranker — packages + per-layer techniques."""
    selection_mode: Literal["package", "techniques"] = "techniques"
    selected_package: Optional[str] = None
    packages: list[str] = Field(default_factory=list)          # candidate packages (top-scored)
    techniques_by_layer: dict[Layer, list[str]] = Field(default_factory=dict)
    confidence: float = 0.0
    rationale: str = ""


class VerticalConfig(BaseModel):
    """One config produced by scope_to_scan for one layer (Phase 2 → Phase 3 input)."""
    layer: Layer
    technique_ids: list[str]
    target_profile: TargetProfile
    mode: Mode
    query_budget: int = 100
    surfaces: list[str] = Field(default_factory=list)
    converters: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    scorers: list[str] = Field(default_factory=list)
    atlas_chain: list[dict[str, Any]] = Field(default_factory=list)
    multi_turn: bool = False


class ScanPlan(BaseModel):
    campaign_id: str
    scope: Scope
    verticals: list[VerticalConfig]
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    layer_cardinality: Literal["single", "full", "invalid(2)"] = "single"


# ──────────────────────────────────────────────────────────────────────────
# Action / Decision / Verdict / Result / Trace
# ──────────────────────────────────────────────────────────────────────────
class Action(BaseModel):
    technique_id: str
    layer: Layer
    params: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)


class Decision(BaseModel):
    allow: bool
    reason: str = ""
    rule: str = ""


class Verdict(BaseModel):
    """Result of a scorer evaluation. confirmed = deterministic; assessed = judged."""
    success: bool
    kind: VerdictKind = "assessed"
    evidence: str = ""
    data_classification: Optional[str] = None
    score: Optional[float] = None


class ExecutionResult(BaseModel):
    """Result of a single runner execution. Aggregated into a Scorecard."""
    success: bool
    verdict: VerdictKind = "assessed"
    response: str = ""
    evidence: str = ""
    score: Optional[float] = None
    severity: Severity = "medium"
    data_classification: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


class TraceStep(BaseModel):
    kind: Literal["gate", "exec", "dispatch"]
    timestamp: datetime = Field(default_factory=_utcnow)
    layer: Optional[Layer] = None
    technique_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class Scorecard(BaseModel):
    layer: Layer
    techniques_fired: list[str] = Field(default_factory=list)
    successes: int = 0
    blocked: int = 0
    failed: int = 0
    asr: float = 0.0
    oracle_hits: int = 0
    findings: list[dict[str, Any]] = Field(default_factory=list)
