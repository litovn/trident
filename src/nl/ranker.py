import math
import os
import re
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from ..core.models import Layer, Package, PackageCandidate, Scope, TechniqueConfig
from ..skills.registry import SkillRegistry


# ──────────────────────────────────────────────────────────────────────────
# Pluggable interfaces (Azure OpenAI in prod, stubs offline)
# ──────────────────────────────────────────────────────────────────────────
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class LLMConfirmer(Protocol):
    def confirm(self, query: str, candidates: list[TechniqueConfig]) -> list[str]:
        """Return the ids of techniques genuinely relevant to the query."""
        ...


# ──────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────
def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


# ──────────────────────────────────────────────────────────────────────────
# Result types
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class Scored:
    id: str
    score: float


@dataclass
class ScopeSelection:
    """What the ranker proposes to run."""
    mode: str                          # 'package' | 'techniques'
    query: str
    selected_package: Package | None
    techniques: list[TechniqueConfig]
    package_candidates: list[Scored] = field(default_factory=list)
    technique_candidates: list[Scored] = field(default_factory=list)

    def explain(self) -> str:
        head = (f"PACKAGE: {self.selected_package.name}"
                if self.mode == "package" and self.selected_package
                else "SPECIFIC TECHNIQUES")
        lines = [f"[{head}]  (query: \"{self.query}\")"]
        for t in self.techniques:
            conv = "/".join(t.converters) or "-"
            lines.append(
                f"  - {t.id}  {t.name}  "
                f"[{t.layer}/{t.phase}/{t.owasp_id}/{t.atlas_tactic} -> {conv}]"
            )
        return "\n".join(lines)

    def to_scope(self) -> Scope:
        """Project this selection into the Scope shape consumed by `scope_to_scan`."""
        by_layer: dict[Layer, list[str]] = {}
        for t in self.techniques:
            by_layer.setdefault(t.layer, []).append(t.id)
        if self.mode == "package" and self.package_candidates:
            confidence = self.package_candidates[0].score
        elif self.technique_candidates:
            confidence = self.technique_candidates[0].score
        else:
            confidence = 0.0
        return Scope(
            selection_mode="package" if self.mode == "package" else "techniques",
            selected_package=self.selected_package.id if self.selected_package else None,
            packages=[s.id for s in self.package_candidates[:3]],
            techniques_by_layer=by_layer,
            confidence=round(confidence, 3),
            rationale=(
                f"mode={self.mode}; "
                f"top_pkg={[(s.id, round(s.score, 2)) for s in self.package_candidates[:1]]}; "
                f"top_tech={[(s.id, round(s.score, 2)) for s in self.technique_candidates[:3]]}"
            ),
        )


# ──────────────────────────────────────────────────────────────────────────
# Ranker
# ──────────────────────────────────────────────────────────────────────────
class ScopeRanker:
    def __init__(
        self,
        registry: SkillRegistry,
        embedder: Embedder,
        confirmer: LLMConfirmer,
        *,
        retrieval_top_n: int = 6,
        package_accept_threshold: float = 0.55,
        alias_boost: float = 1.0,
    ) -> None:
        self.registry = registry
        self.embedder = embedder
        self.confirmer = confirmer
        self.retrieval_top_n = retrieval_top_n
        self.package_accept_threshold = package_accept_threshold
        self.alias_boost = alias_boost
        self._index()

    def _index(self) -> None:
        self._tech_ids = list(self.registry.techniques)
        self._pkg_ids = list(self.registry.packages)
        tech_vecs = self.embedder.embed(
            [self.registry.techniques[i].embedding_text() for i in self._tech_ids])
        pkg_vecs = self.embedder.embed(
            [self.registry.packages[i].embedding_text() for i in self._pkg_ids])
        self._tech_vecs = dict(zip(self._tech_ids, tech_vecs))
        self._pkg_vecs = dict(zip(self._pkg_ids, pkg_vecs))

    def _alias_hits(self, query: str) -> tuple[set[str], set[str]]:
        """Lexicon lane: which techniques / packages are hit by a jargon term or OWASP id."""
        ql = query.lower()
        qtok = _tokens(ql)
        hit_t, hit_p = set(), set()
        for tid in self._tech_ids:
            for term in self.registry.techniques[tid].alias_terms():
                matched = (term in ql) if (" " in term or "-" in term) else (term in qtok)
                if matched:
                    hit_t.add(tid)
                    break
        for pid in self._pkg_ids:
            for term in self.registry.packages[pid].alias_terms():
                matched = (term in ql) if (" " in term or "-" in term) else (term in qtok)
                if matched:
                    hit_p.add(pid)
                    break
        return hit_t, hit_p

    def rank(self, query: str) -> ScopeSelection:
        qvec = self.embedder.embed([query])[0]
        hit_t, hit_p = self._alias_hits(query)

        def tscore(i: str) -> float:
            s = _cosine(qvec, self._tech_vecs[i])
            return max(s, self.alias_boost) if i in hit_t else s

        def pscore(i: str) -> float:
            s = _cosine(qvec, self._pkg_vecs[i])
            return max(s, self.alias_boost) if i in hit_p else s

        pkg_scores = sorted((Scored(i, pscore(i)) for i in self._pkg_ids),
                            key=lambda s: s.score, reverse=True)
        tech_scores = sorted((Scored(i, tscore(i)) for i in self._tech_ids),
                             key=lambda s: s.score, reverse=True)

        # Stage 2: LLM confirmation on the top-N candidates (alias hits forced in)
        top_candidates = [self.registry.techniques[s.id]
                          for s in tech_scores[: self.retrieval_top_n]]
        confirmed_ids = set(self.confirmer.confirm(query, top_candidates)) | hit_t
        confirmed = [t for t in top_candidates if t.id in confirmed_ids]

        # PACKAGE-FIRST decision
        best_pkg = pkg_scores[0] if pkg_scores else None
        if best_pkg and best_pkg.score >= self.package_accept_threshold:
            pkg = self.registry.packages[best_pkg.id]
            techs = [self.registry.techniques[tid] for tid in pkg.techniques
                     if tid in self.registry.techniques]
            return ScopeSelection("package", query, pkg, techs,
                                  pkg_scores, tech_scores)

        # Specific query: return confirmed techniques (fallback to the best candidate)
        if not confirmed and top_candidates:
            confirmed = top_candidates[:1]
        return ScopeSelection("techniques", query, None, confirmed,
                              pkg_scores, tech_scores)

    def drilldown(self, selection: ScopeSelection) -> list[TechniqueConfig]:
        """Expand a package into its (user-editable) techniques."""
        if selection.selected_package is None:
            return selection.techniques
        return [self.registry.techniques[tid]
                for tid in selection.selected_package.techniques
                if tid in self.registry.techniques]
    # ---- package-only ranking (top-N for HITL selection) ----------------

    def _package_candidate(self, scored: Scored) -> PackageCandidate:
        """Resolve a scored package id into a display-ready PackageCandidate."""
        pkg = self.registry.packages[scored.id]
        layers: list[Layer] = []
        for tid in pkg.techniques:
            t = self.registry.techniques.get(tid)
            if t is not None and t.layer not in layers:
                layers.append(t.layer)
        pct = max(0, min(100, round(scored.score * 100)))
        return PackageCandidate(
            id=pkg.id, name=pkg.name, axis=pkg.axis,
            score=round(scored.score, 3), percent=pct,
            layers=layers, technique_ids=list(pkg.techniques),
            query_budget=pkg.query_budget, max_intensity=pkg.max_intensity,
            rationale=f"semantic match {pct}% on package intent",
        )

    def rank_packages(self, query: str, *, top_n: int = 4) -> list[PackageCandidate]:
        """Package-only ranking: score every catalog package against the prompt and
        return the top-N candidates (highest score first). The prompt is usually
        vague, so we surface N options for a human to choose from (HITL) rather
        than auto-committing to one. Uses the same two lanes as `rank`: cosine
        over package intent + a lexicon boost for jargon/aliases (e.g. a typed
        'jailbreak' forces PKG-GUARDRAIL up)."""
        qvec = self.embedder.embed([query])[0]
        _, hit_p = self._alias_hits(query)

        def pscore(i: str) -> float:
            s = _cosine(qvec, self._pkg_vecs[i])
            return max(s, self.alias_boost) if i in hit_p else s

        scored = sorted((Scored(i, pscore(i)) for i in self._pkg_ids),
                        key=lambda s: s.score, reverse=True)
        return [self._package_candidate(s) for s in scored[:top_n]]

# ──────────────────────────────────────────────────────────────────────────
# Azure OpenAI implementations
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
    (Managed Identity in prod, `az login` locally). Lazy imports so this
    module still runs offline."""
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


class AzureOpenAIEmbedder:
    """text-embedding-3-large is multilingual → Italian user input matches the English
    intent_examples. Catalog text is batched into 2 calls; per query it's 1 call."""

    def __init__(self, deployment: str | None = None) -> None:
        self._client = _azure_openai_client()
        self._deployment = deployment or _foundry_env(
            "AZURE_OPENAI_EMBED_DEPLOYMENT", "FOUNDRY_EMBED_DEPLOYMENT",
            default="text-embedding-3-large")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._deployment, input=list(texts))
        return [d.embedding for d in resp.data]


class AzureOpenAIConfirmer:
    """JSON-mode LLM disambiguation. Separate scorer (not the acting agent): given
    the user text + candidate techniques, returns ONLY the genuinely relevant ids."""

    def __init__(self, deployment: str | None = None) -> None:
        self._client = _azure_openai_client()
        self._deployment = deployment or _foundry_env(
            "AZURE_OPENAI_CHAT_DEPLOYMENT", "FOUNDRY_CHAT_DEPLOYMENT", "FOUNDRY_MODEL_DEPLOYMENT",
            default="gpt-4o-mini")

    def confirm(self, query: str, candidates: list[TechniqueConfig]) -> list[str]:
        import json
        if not candidates:
            return []
        listing = "\n".join(f"- {t.id}: {t.name} — {t.desc}" for t in candidates)
        system = ("You are a security-testing scope router. Given the user's request and a "
                  "list of candidate attack techniques, return ONLY the ids that are genuinely "
                  "relevant to the request. Choose strictly from the provided ids; never invent "
                  "an id. Reply as JSON: {\"relevant_ids\": [\"...\"]}.")
        user = f"User request:\n{query}\n\nCandidate techniques:\n{listing}"
        resp = self._client.chat.completions.create(
            model=self._deployment, temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        try:
            ids = json.loads(resp.choices[0].message.content).get("relevant_ids", [])
        except (json.JSONDecodeError, AttributeError):
            ids = []
        valid = {t.id for t in candidates}
        return [i for i in ids if i in valid]


# ──────────────────────────────────────────────────────────────────────────
# Deterministic offline stubs
# ──────────────────────────────────────────────────────────────────────────
class KeywordEmbedder:
    """Bag-of-words embedding over a vocabulary built from the catalog. Not
    semantic (no synonyms); ONLY for the offline demo / tests. In production swap
    in AzureOpenAIEmbedder without touching the ranker."""

    def __init__(self, corpus: Sequence[str]) -> None:
        vocab: dict[str, int] = {}
        for text in corpus:
            for tok in _tokens(text):
                vocab.setdefault(tok, len(vocab))
        self._vocab = vocab

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * len(self._vocab)
            for tok in _tokens(text):
                if tok in self._vocab:
                    vec[self._vocab[tok]] += 1.0
            out.append(vec)
        return out


class PassthroughConfirmer:
    """Keeps candidates sharing at least one word with the query — crude
    surrogate for LLM disambiguation, only used offline."""

    def confirm(self, query: str, candidates: list[TechniqueConfig]) -> list[str]:
        qtok = _tokens(query)
        return [t.id for t in candidates if qtok & _tokens(t.embedding_text())]


# ──────────────────────────────────────────────────────────────────────────
# Factory + back-compat helper
# ──────────────────────────────────────────────────────────────────────────
def make_ranker(registry: SkillRegistry, *, offline: bool | None = None, **kwargs) -> ScopeRanker:
    """Build a ScopeRanker.
    - offline=False  → force Azure OpenAI (embedder + confirmer)
    - offline=True   → force the deterministic offline stubs
    - offline=None   → auto: Foundry/Azure if FOUNDRY_ENDPOINT or
                       AZURE_OPENAI_ENDPOINT is set, else stubs
    """
    use_azure = (offline is False) or (
        offline is None and bool(
            os.environ.get("AZURE_OPENAI_ENDPOINT") or os.environ.get("FOUNDRY_ENDPOINT")
        )
    )
    if use_azure:
        return ScopeRanker(registry, AzureOpenAIEmbedder(), AzureOpenAIConfirmer(), **kwargs)
    corpus = ([t.embedding_text() for t in registry.techniques.values()]
              + [p.embedding_text() for p in registry.packages.values()])
    return ScopeRanker(registry, KeywordEmbedder(corpus), PassthroughConfirmer(), **kwargs)


def rank(nl: str, registry: SkillRegistry, *, offline: bool | None = None) -> Scope:
    """Convenience: build a ranker and return a Scope (used by the Coordinator)."""
    return make_ranker(registry, offline=offline).rank(nl).to_scope()


def rank_packages(nl: str, registry: SkillRegistry, *, top_n: int = 4,
                  offline: bool | None = None) -> list[PackageCandidate]:
    """Convenience: build a ranker and return the top-N package candidates for the
    prompt. Package-only selection — the candidates come straight from
    ``packages.yaml`` (see `ScopeRanker.rank_packages`)."""
    return make_ranker(registry, offline=offline).rank_packages(nl, top_n=top_n)


def scope_from_package(package: Package, registry: SkillRegistry) -> Scope:
    """Project a chosen package into the Scope consumed by `scope_to_scan`: group
    the package's techniques by layer. This is a pure projection — deferred /
    untargetable filtering stays in `scope_to_scan` (the deterministic floor)."""
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
        confidence=1.0,  # a human authorized this exact package
        rationale=f"package {package.id} selected",
    )
