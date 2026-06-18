from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class TargetResponse:
    text: str
    raw: dict[str, Any] | None = None


@runtime_checkable
class TargetAdapter(Protocol):
    """Minimal contract every target must satisfy.

    Required: ``id``, ``endpoint``, ``capabilities`` and async ``send()``.

    Optional lifecycle / capability methods (callers invoke them defensively via
    ``getattr`` — a target that can't provide one simply omits it):
      * ``async plant(surface, content) -> bool`` — write a honeytoken into the
        target's data store (so ``exfil_canary`` can fire on a real target).
        Targets with no ingestable surface don't implement it.
      * ``async aclose() -> None`` — release network resources (HTTP adapters).
    """
    id: str
    endpoint: str
    capabilities: list[str]

    async def send(self, prompt: str, **kw: Any) -> TargetResponse:  # pragma: no cover
        ...
