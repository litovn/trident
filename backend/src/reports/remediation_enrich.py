"""Web-search augmentation of the remediation section (additive, shape-preserving).

`correlate()` builds the deterministic remediation list — the Microsoft controls
declared in the catalog for each successful finding (see
``reports.correlator._remediation``). This module *expands* each of those items
with grounded prose: for every control it issues one focused Foundry web-search
(reusing ``skills.web_search.run_web_search``), and the model extrapolates a
concise remediation description from real-time public-web sources.

Design (mirrors the rest of the web_search posture):
  * **Deterministic driver, agentic content.** Python owns the loop and the
    schema; the catalog stays the source of truth for *which* controls appear.
    The model only authors the ``description`` text + returns its source URLs —
    it never rewrites the payload structure, so no control can be invented.
  * **Additive + shape-preserving.** Each remediation item keeps every existing
    key and only gains ``description`` (str) and ``sources`` (list[{url,title}]).
    Every other key in the report payload is untouched.
  * **Graceful degradation.** When web grounding is unconfigured or a call fails,
    the item gets ``description=""`` / ``sources=[]`` — the payload shape (and the
    rendered report) is then identical to today's. Never raises.
"""
import asyncio
import logging
from typing import Optional

from ..core.config import FoundrySettings
from ..skills.web_search import run_web_search

log = logging.getLogger(__name__)

# A campaign rarely surfaces many distinct controls; cap defensively so a noisy
# run can't fan out into dozens of slow grounded calls. Override via the caller.
_DEFAULT_MAX_ITEMS = 12


def _context_for_control(control: str, findings: list[dict]) -> dict:
    """Collect the OWASP / ATLAS context of the findings a control addresses, so
    the search query can ask for a remediation specific to what actually fell."""
    owasp: list[str] = []
    atlas: list[str] = []
    names: list[str] = []
    for f in findings:
        if control not in (f.get("controls") or []):
            continue
        for value, bucket in (
            (f.get("owasp_name") or f.get("owasp_id"), owasp),
            (f.get("atlas_technique") or f.get("atlas_tactic"), atlas),
            (f.get("name"), names),
        ):
            if value and value not in bucket:
                bucket.append(value)
    return {"owasp": owasp, "atlas": atlas, "names": names}


def _build_query(control: str, ctx: dict) -> str:
    """A focused prompt that makes the grounded answer *be* the remediation text."""
    owasp = ", ".join(ctx["owasp"]) or "the observed AI red-team findings"
    atlas = ", ".join(ctx["atlas"])
    atlas_clause = f" (MITRE ATLAS: {atlas})" if atlas else ""
    return (
        f"In Microsoft's AI security guidance, how does the control "
        f"'{control}' mitigate {owasp}{atlas_clause}? Give a concise, accurate "
        f"remediation description (2-4 sentences) an AI red-team report can hand "
        f"to an engineering team, citing official Microsoft documentation."
    )


async def _enrich_one(item: dict, findings: list[dict], *,
                      settings: Optional[FoundrySettings], context_size: str) -> dict:
    """Expand a single remediation item; always returns a shape-preserving dict."""
    control = item.get("control", "")
    enriched = {**item, "description": "", "sources": []}
    if not control:
        return enriched
    ctx = _context_for_control(control, findings)
    result = await run_web_search(
        _build_query(control, ctx), context_size=context_size, settings=settings)
    if result.get("status") == "ok":
        enriched["description"] = result.get("answer", "") or ""
        enriched["sources"] = result.get("citations", []) or []
    else:
        # Keep the reason on the item for debugging; harmless extra key, the
        # renderer ignores it. Shape (description/sources) is still preserved.
        log.info("remediation_enrich: '%s' not expanded (%s)",
                 control, result.get("reason", result.get("status")))
    return enriched


async def enrich_remediation(
    remediation: list[dict],
    findings: list[dict],
    *,
    settings: Optional[FoundrySettings] = None,
    max_items: int = _DEFAULT_MAX_ITEMS,
    context_size: str = "high",
) -> list[dict]:
    """Return the remediation list with each item augmented by a web-searched
    ``description`` + ``sources``. Additive and order-preserving; never raises.

    Items beyond ``max_items`` are returned shape-preserved (empty description)
    so the payload is uniform regardless of how many controls surfaced.
    """
    if not remediation:
        return remediation

    to_expand = remediation[:max_items]
    passthrough = [
        {**item, "description": "", "sources": []} for item in remediation[max_items:]
    ]
    expanded = await asyncio.gather(*(
        _enrich_one(item, findings, settings=settings, context_size=context_size)
        for item in to_expand
    ))
    return [*expanded, *passthrough]
