import os
from dataclasses import dataclass
from functools import lru_cache


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


@dataclass(frozen=True)
class FoundrySettings:
    # ── Microsoft Foundry (control plane + model endpoint) ──────────────
    endpoint: str = ""
    model_deployment: str = "gpt-4o-mini"
    project_name: str = "trident"
    api_key: str = ""              # local BYOK shortcut (prod uses MI)
    api_version: str = "2024-10-21"
    wire_api: str = "chat_completions"   # Copilot SDK wire_api: chat_completions | responses | completions

    # ── Ranker-only overrides (Phase 1 NL→scope) ───────────────────────
    embed_deployment: str = "text-embedding-3-large"
    chat_deployment: str = ""      # empty → falls back to model_deployment

    # ── Observability (optional) ────────────────────────────────────────
    appinsights_connection_string: str = ""
    otel_service_name: str = "trident"

    @classmethod
    def from_env(cls) -> "FoundrySettings":
        return cls(
            endpoint=_env("FOUNDRY_ENDPOINT"),
            model_deployment=_env("FOUNDRY_MODEL_DEPLOYMENT", "gpt-4o-mini"),
            project_name=_env("FOUNDRY_PROJECT_NAME", "trident"),
            api_key=_env("FOUNDRY_API_KEY"),
            api_version=_env("FOUNDRY_API_VERSION", "2024-10-21"),
            wire_api=_env("FOUNDRY_WIRE_API", "chat_completions"),
            embed_deployment=_env("FOUNDRY_EMBED_DEPLOYMENT", "text-embedding-3-large"),
            chat_deployment=_env("FOUNDRY_CHAT_DEPLOYMENT"),
            appinsights_connection_string=_env("APPLICATIONINSIGHTS_CONNECTION_STRING"),
            otel_service_name=_env("OTEL_SERVICE_NAME", "trident"),
        )

    def require_endpoint(self) -> None:
        """Fail loudly when FOUNDRY_ENDPOINT is missing."""
        if not self.endpoint:
            raise RuntimeError(
                "FOUNDRY_ENDPOINT is required. Set it to your Foundry account URL, "
                "e.g. https://<account>.services.azure.com — see .env.example."
            )

    @property
    def effective_chat_deployment(self) -> str:
        """Chat deployment for the ranker: explicit override or the agent's model."""
        return self.chat_deployment or self.model_deployment


@lru_cache(maxsize=1)
def get_foundry_settings() -> FoundrySettings:
    """Process-wide cached Foundry settings. Call `get_foundry_settings.cache_clear()`
    in tests if you need to reload after monkey-patching env vars."""
    return FoundrySettings.from_env()
