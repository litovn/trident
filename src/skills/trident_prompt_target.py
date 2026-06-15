"""Minimal PyRIT ``PromptTarget`` wrapping a TRIDENT ``TargetAdapter``.

Needed by multi-turn attacks (``CrescendoAttack``, etc.) that drive the target
through PyRIT's orchestrator: PyRIT speaks ``PromptTarget``, our adapters speak
``async def send(prompt) -> TargetResponse``. This shim bridges the two.

Single-turn paths in ``PyritRunner.execute`` still use the adapter directly —
this wrapper is only on the orchestrator code path, to keep the adapter as the
single source of truth for HTTP / auth / canary plumbing.
"""
from typing import Any

from pyrit.models import construct_response_from_request
from pyrit.models.messages.message import Message
from pyrit.prompt_target import PromptTarget

from ..targets.adapter import TargetAdapter


class TridentPromptTarget(PromptTarget):
    """Adapt a TRIDENT ``TargetAdapter`` to PyRIT's ``PromptTarget`` API."""

    def __init__(self, adapter: TargetAdapter) -> None:
        super().__init__(endpoint=getattr(adapter, "endpoint", ""),
                         model_name=getattr(adapter, "id", "trident-target"))
        self._adapter = adapter

    async def _send_prompt_to_target_async(
        self, *, normalized_conversation: list[Message]
    ) -> list[Message]:
        last = normalized_conversation[-1]
        request_piece = last.message_pieces[-1]
        prompt_text = request_piece.converted_value

        reply = await self._adapter.send(prompt_text)
        return [construct_response_from_request(
            request=request_piece,
            response_text_pieces=[reply.text or ""],
        )]

    # Required by PromptTarget contract (text in, text out — no extra checks).
    def _validate_request(self, *, prompt_request: Any) -> None:
        return None
