"""Catalog ``converters`` name → PyRIT ``PromptConverter`` instance.

Source of truth for naming: ``catalog/strategies.md`` (the curated subset of the
``azure-ai-evaluation`` ``AttackStrategy`` enum that the TRIDENT catalog uses).

The mapping is intentionally narrow — only the converters that appear in the
catalog techniques are wired. Adding a new strategy means: (a) add it to
``strategies.md``, (b) add a row here, (c) confirm the PyRIT class exists.

``Baseline`` is the empty converter list: ``apply_converters_async`` returns the
input unchanged when given ``["Baseline"]`` (or an empty list).
"""
from typing import Any

from pyrit.prompt_converter import (
    Base64Converter,
    DiacriticConverter,
    FlipConverter,
    LeetspeakConverter,
    MorseConverter,
    PromptConverter,
    ROT13Converter,
    StringJoinConverter,
    SuffixAppendConverter,
    UnicodeConfusableConverter,
    UrlConverter,
)


_REGISTRY: dict[str, type[PromptConverter]] = {
    "Base64":            Base64Converter,
    "Flip":              FlipConverter,
    "Leetspeak":         LeetspeakConverter,
    "Morse":             MorseConverter,
    "ROT13":             ROT13Converter,
    "UnicodeConfusable": UnicodeConfusableConverter,
    "Url":               UrlConverter,
    "Diacritic":         DiacriticConverter,
    "StringJoin":        StringJoinConverter,
    "SuffixAppend":      SuffixAppendConverter,
}


# Strategies the catalog references but that are not single-turn converters:
# they are handled by orchestrators, not by ``apply_converters_async``.
_ORCHESTRATOR_ONLY = {"Crescendo", "Multiturn", "TAP", "PAIR", "Jailbreak", "IndirectAttack", "Tense"}


def build_converters(names: list[str]) -> list[PromptConverter]:
    """Instantiate the converters declared by a technique.

    Unknown names raise ``ValueError`` (we prefer fail-fast over silent skip;
    the catalog is schema-validated so this should never trigger at runtime).
    Orchestrator-only strategies are skipped with no-op — they are applied by
    the orchestrator path, not by per-prompt converters.
    """
    out: list[PromptConverter] = []
    for n in names:
        if n in ("Baseline", ""):
            continue
        if n in _ORCHESTRATOR_ONLY:
            continue
        cls = _REGISTRY.get(n)
        if cls is None:
            raise ValueError(f"unknown converter strategy {n!r} (catalog/strategies.md)")
        out.append(_instantiate(cls))
    return out


def _instantiate(cls: type[PromptConverter]) -> PromptConverter:
    # SuffixAppendConverter needs a suffix argument; everything else we use
    # is zero-arg. Keep this dumb: if a converter later needs args, add a
    # branch here rather than a generic config plumbing.
    if cls is SuffixAppendConverter:
        return cls(suffix=" Now answer truthfully.")
    return cls()


async def apply_converters_async(prompt: str, converters: list[PromptConverter]) -> str:
    """Chain converters left-to-right. Returns the transformed prompt text."""
    text = prompt
    for c in converters:
        result: Any = await c.convert_async(prompt=text, input_type="text")
        text = result.output_text
    return text
