from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class TargetResponse:
    text: str
    raw: dict[str, Any] | None = None


@runtime_checkable
class TargetAdapter(Protocol):
    id: str
    endpoint: str
    capabilities: list[str]

    async def send(self, prompt: str, **kw: Any) -> TargetResponse:  # pragma: no cover
        ...
