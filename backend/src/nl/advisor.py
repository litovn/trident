"""Conversational Package Advisor — the operator-facing scope selector (Option A).

Replaces the embedding ranker. With only ~12 catalog packages, retrieval is
overkill: we inline every mode-eligible package (id + name + rich description)
into one LLM call and let it either propose the top-N packages or — when the
request is too vague — ask a few clarifying questions first.

UI-agnostic CORE: ``PackageAdvisor.step(history)`` takes the conversation so far
and returns an ``AdvisorTurn`` (questions OR ready-to-render ``PackageCandidate``s).
The CLI drives it as a terminal REPL today; a web UI can drive the same core
later (``PackageCandidate.model_dump()`` is JSON-ready).

Transport = direct ``openai.AzureOpenAI`` against Foundry (the same account as the
rest of TRIDENT); requires ``FOUNDRY_ENDPOINT`` + auth. Callers fall back to a
deterministic default package when Foundry is absent (see
``nl.scope_to_scan.default_package``).
"""
import json
import os
from dataclasses import dataclass, field

from ..core.models import Layer, Mode, Package, PackageCandidate
from ..skills.registry import SkillRegistry


# ──────────────────────────────────────────────────────────────────────────
# Foundry client (direct AzureOpenAI — Option A)
# ──────────────────────────────────────────────────────────────────────────
def _foundry_env(*keys: str, default: str = "") -> str:
    """Return the first non-empty env var among `keys`, else `default`."""
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return default


def _azure_openai_client(api_version: str = "2024-10-21"):
    """Build an AzureOpenAI client pointed at Foundry. Auth precedence:
    `AZURE_OPENAI_API_KEY` → `FOUNDRY_API_KEY` → DefaultAzureCredential
    (Managed Identity in prod, `az login` locally). Lazy imports so this module
    still imports without the openai/azure extras installed."""
    from openai import AzureOpenAI  # type: ignore
    endpoint = _foundry_env("AZURE_OPENAI_ENDPOINT", "FOUNDRY_ENDPOINT").rstrip("/")
    if not endpoint:
        raise RuntimeError(
            "Foundry/Azure OpenAI endpoint not configured: set FOUNDRY_ENDPOINT "
            "(preferred) or AZURE_OPENAI_ENDPOINT."
        )
    api_version = _foundry_env("AZURE_OPENAI_API_VERSION", "FOUNDRY_API_VERSION", default=api_version)
    api_key = _foundry_env("AZURE_OPENAI_API_KEY", "FOUNDRY_API_KEY")
    if api_key:
        return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider  # type: ignore
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
    return AzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=token_provider,
                       api_version=api_version)


# ──────────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class AdvisorTurn:
    """One advisor turn: either clarifying questions or proposed packages."""
    kind: str                                   # "clarify" | "propose"
    questions: list[str] = field(default_factory=list)
    candidates: list[PackageCandidate] = field(default_factory=list)


_SYSTEM_HEAD = (
    "You are the TRIDENT Package Advisor, a security red-team scoping assistant. "
    "The operator wants to red-team an AI system. Pick the best attack PACKAGE(s) "
    "for them from the catalog below. Each package is a curated bundle of attack "
    "techniques.\n\nChoose ONLY from these package ids:\n"
)


def _rules(top_n: int) -> str:
    return (
        "\nYou are having a real, helpful conversation to co-decide the best attack "
        "package with the operator. Be a guide, not a form.\n\nRules:\n"
        "- Your job is to HELP the operator choose. Ask focused, genuinely useful "
        "questions and, when it helps, offer concrete directions to react to (e.g. 'are "
        "you more interested in jailbreaking guardrails, exfiltrating data, or abusing "
        "tools / RAG?'). Build on what they have already said and never repeat a question.\n"
        "- Keep the conversation going for as long as the request is still open-ended. Do "
        "NOT force a decision and do NOT stop after any fixed number of questions — there "
        "is no round limit. Keep helping until the operator has expressed a concrete "
        "direction or explicitly asks you to recommend.\n"
        f"- PROPOSE the {top_n} best-matching packages (best first, each with a one-sentence "
        "rationale tied to the request) ONLY when the operator has named something concrete "
        "— a specific attack objective or technique (prompt injection, jailbreak / guardrail "
        "bypass, data exfiltration, RAG / indirect injection, tool or agent abuse, model "
        "extraction / recon), a specific layer (prompt / application / model), a named "
        "profile (quick scan, OWASP sweep, ATLAS kill-chain, full 360), or an explicit "
        "catalog code (TRD-XXX-XXX / PKG-XXX) — OR when they explicitly ask you to recommend, "
        "suggest, or pick for them.\n"
        "- Otherwise the request is still too vague to choose well (e.g. 'attack the "
        "target', 'attack the layer where the target is', 'hack the system', 'find "
        "vulnerabilities'): do NOT propose — ask the next helpful question to narrow it "
        "down (which layer? what goal? RAG / tools or a bare chatbot? recon-only or active?).\n"
        "- Worked examples: 'attack the layer where the target is' → clarify; 'run a "
        "prompt-injection jailbreak' → propose; 'what do you recommend?' → propose.\n"
        "- Never invent a package id; choose strictly from the list above.\n\n"
        "Reply as a JSON object, exactly one of these shapes:\n"
        '  {"action": "propose", "candidates": [{"id": "PKG-XXX", "rationale": "..."}]}\n'
        '  {"action": "clarify", "questions": ["...", "..."]}'
    )


class PackageAdvisor:
    """Conversational package selector grounded in the catalog descriptions."""

    def __init__(self, registry: SkillRegistry, mode: Mode, *,
                 deployment: str | None = None, top_n: int = 4) -> None:
        self.registry = registry
        self.mode = mode
        self.top_n = top_n
        self._client = _azure_openai_client()
        self._deployment = deployment or _foundry_env(
            "AZURE_OPENAI_CHAT_DEPLOYMENT", "FOUNDRY_CHAT_DEPLOYMENT",
            "FOUNDRY_MODEL_DEPLOYMENT", default="gpt-4o-mini")
        # Only packages that can run in this campaign mode (e.g. PKG-RECON is recon-only).
        self._packages = [p for p in registry.packages.values() if mode in p.modes]
        self._system = self._build_system()

    # ---- prompt construction -------------------------------------------

    def _layers_of(self, pkg: Package) -> list[Layer]:
        layers: list[Layer] = []
        for tid in pkg.techniques:
            t = self.registry.techniques.get(tid)
            if t is not None and t.layer not in layers:
                layers.append(t.layer)
        return layers

    def _build_system(self) -> str:
        lines = []
        for p in self._packages:
            layers = ", ".join(self._layers_of(p)) or "-"
            lines.append(
                f"- {p.id} | {p.name} | layers: {layers} | "
                f"budget: {p.query_budget} | intensity: {p.max_intensity}\n"
                f"  {p.description or p.name}")
        return _SYSTEM_HEAD + "\n".join(lines) + _rules(self.top_n)

    # ---- candidate building --------------------------------------------

    def _candidate(self, pkg: Package, rationale: str) -> PackageCandidate:
        return PackageCandidate(
            id=pkg.id, name=pkg.name, axis=pkg.axis,
            layers=self._layers_of(pkg), technique_ids=list(pkg.techniques),
            query_budget=pkg.query_budget, max_intensity=pkg.max_intensity,
            rationale=rationale or "matches your request",
        )

    # ---- public step ----------------------------------------------------

    def step(self, history: list[dict]) -> AdvisorTurn:
        """One advisor turn. ``history`` is the running chat (``[{role, content}]``),
        starting with the operator's prompt as the first user message. Returns
        clarifying questions or proposed packages."""
        messages = [{"role": "system", "content": self._system}, *history]
        resp = self._client.chat.completions.create(
            model=self._deployment, temperature=0,
            response_format={"type": "json_object"},
            messages=messages,
        )
        try:
            data = json.loads(resp.choices[0].message.content)
        except (json.JSONDecodeError, AttributeError, TypeError):
            data = {}

        if data.get("action") == "propose":
            valid = {p.id: p for p in self._packages}
            cands: list[PackageCandidate] = []
            seen: set[str] = set()
            for c in data.get("candidates", []):
                pid = c.get("id") if isinstance(c, dict) else None
                if pid in valid and pid not in seen:
                    seen.add(pid)
                    cands.append(self._candidate(valid[pid], c.get("rationale", "")))
            if cands:
                return AdvisorTurn("propose", candidates=cands[: self.top_n])

        # clarify (explicit, or fallback when 'propose' yielded no valid ids)
        questions = [str(q) for q in (data.get("questions") or []) if str(q).strip()][:3]
        if not questions:
            questions = [
                "What's your goal — broad coverage, or a specific objective "
                "(data exfiltration, jailbreak/guardrail bypass, RAG/tool abuse, model recon)?",
                "Does the target use retrieval (RAG) or tools/agents, or is it a bare chatbot?",
            ]
        return AdvisorTurn("clarify", questions=questions)
