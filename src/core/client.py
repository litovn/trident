from typing import Any, Optional
from copilot import CopilotClient  
from copilot.session import PermissionHandler 

# Central model routing table — change here, not at call sites.
# Strong model on the Coordinator (correlation reasoning), cheaper models on verticals.
MODELS: dict[str, str] = {
    "coordinator": "gpt-5",
    "prompt": "gpt-4.1-mini",
    "application": "gpt-4.1",
    "model": "gpt-4.1",
    "ranker": "gpt-4.1-mini",
}
    

class TridentClient:
    def __init__(self) -> None:
        self._sdk_client: Any = None
        self._sdk_perm: Any = None
        self.started = False

    async def start(self) -> None:
        self._sdk_client = CopilotClient()
        self._sdk_perm = PermissionHandler
        await self._sdk_client.start()
        self.started = True

    async def stop(self) -> None:
        if self._sdk_client is not None:
            await self._sdk_client.stop()
            self.started = False

    async def new_session(
        self,
        *,
        role: str,
        tools: list,
        agent_prompt: Optional[str] = None,
        streaming: bool = True,
    ):
        """Create a Session pre-configured for `role` (coordinator/prompt/application/model)."""
        if not self.started:
            raise RuntimeError("TridentClient not started — call await client.start() first")

        model = MODELS.get(role)
        if not model:
            raise ValueError(f"Unknown role {role!r}; add it to MODELS")

        kwargs: dict[str, Any] = dict(
            model=model,
            tools=tools,
            streaming=streaming,
            on_permission_request=self._sdk_perm.approve_all,
        )
        if agent_prompt:
            kwargs["custom_agents"] = [
                {
                    "name": role,
                    "display_name": role.title(),
                    "description": f"TRIDENT {role} agent",
                    "prompt": agent_prompt,
                }
            ]
            kwargs["agent"] = role

        return await self._sdk_client.create_session(**kwargs)
