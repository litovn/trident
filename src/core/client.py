import logging
from typing import Any, Optional

from .config import FoundrySettings, get_foundry_settings

logger = logging.getLogger(__name__)


class TridentClient:
    def __init__(self, settings: FoundrySettings | None = None) -> None:
        self._sdk_client: Any = None
        self._sdk_perm: Any = None
        self._credential: Any = None
        self._token_provider: Any = None
        self.settings: FoundrySettings = settings or get_foundry_settings()
        self.started = False

    async def start(self) -> None:
        # Fail loudly before importing the SDK so the error is unambiguous.
        self.settings.require_endpoint()

        # Lazy SDK import keeps the module loadable without the [sdk] extra.
        from copilot import CopilotClient  # type: ignore
        from copilot.session import PermissionHandler  # type: ignore

        self._sdk_perm = PermissionHandler
        self._token_provider = self._build_token_provider()
        logger.info(
            "TridentClient: Foundry endpoint=%s deployment=%s (Foundry credit)",
            self.settings.endpoint, self.settings.model_deployment,
        )

        self._sdk_client = CopilotClient()
        await self._sdk_client.start()
        self.started = True

    async def stop(self) -> None:
        if self._sdk_client is not None:
            await self._sdk_client.stop()
            self._sdk_client = None
        if self._credential is not None:
            try:
                await self._credential.close()
            except Exception:
                pass
            self._credential = None
        self.started = False

    # ---- internal helpers ------------------------------------------------

    def _build_token_provider(self):
        """Async bearer-token provider scoped to Cognitive Services.

        Prefers `ManagedIdentityCredential` (production) with `AzureCLICredential`
        fallback (`az login` locally); falls back to `DefaultAzureCredential` if
        the chained variant isn't available in the installed `azure-identity`."""
        try:
            from azure.identity.aio import (  # type: ignore
                AzureCLICredential,
                ChainedTokenCredential,
                ManagedIdentityCredential,
                get_bearer_token_provider,
            )
            self._credential = ChainedTokenCredential(
                ManagedIdentityCredential(),
                AzureCLICredential(),
            )
        except ImportError:
            from azure.identity.aio import (  # type: ignore
                DefaultAzureCredential,
                get_bearer_token_provider,
            )
            self._credential = DefaultAzureCredential()
        return get_bearer_token_provider(
            self._credential, "https://services.azure.com/.default"
        )

    def _build_provider_config(self) -> dict:
        """Azure provider dict consumed by `CopilotClient.create_session`."""
        s = self.settings
        return {
            "type": "azure",
            "base_url": f"{s.endpoint}/openai/deployments/{s.model_deployment}",
            "token_provider": self._token_provider,
            "wire_api": s.wire_api,
            "azure": {"api_version": s.api_version},
        }

    # ---- public API ------------------------------------------------------

    async def new_session(
        self,
        *,
        role: str,
        tools: list,
        agent_prompt: Optional[str] = None,
        streaming: bool = True,
        skill_directories: Optional[list[str]] = None,
        enable_skills: bool = False,
    ):
        """Create a Session for `role`, bound to the Foundry deployment named
        by `FOUNDRY_MODEL_DEPLOYMENT`.

        ``skill_directories`` lists folders the SDK scans for SKILL.md files.
        ``enable_skills`` toggles skill matching on (default off — caller wins;
        empty-mode clients require this to be True for the skills to actually be
        discoverable at runtime).
        """
        if not self.started:
            raise RuntimeError("TridentClient not started — call await client.start() first")

        kwargs: dict[str, Any] = dict(
            model=self.settings.model_deployment,
            tools=tools,
            streaming=streaming,
            on_permission_request=self._sdk_perm.approve_all,
            provider=self._build_provider_config(),
        )
        if skill_directories:
            kwargs["skill_directories"] = skill_directories
            kwargs["enable_skills"] = enable_skills or True  # any dir → enable
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
