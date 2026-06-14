"""HTTP target adapter for AIGoat (AISecurityConsortium/AIGoat).

Reads endpoints, auth and capabilities from the declarative target profile
(targets/aigoat.yaml). The TRIDENT generic core never imports this module
directly — it's selected by `target_profile.id == "aigoat"` in src/cli.py.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ..core.models import TargetProfile
from .adapter import TargetResponse


class AIGoatTargetAdapter:
    id = "aigoat"

    def __init__(
        self,
        profile: TargetProfile,
        password: str,
        canary: str | None = None,
        timeout: float = 360.0,   # > AIGoat's internal ollama.timeout (300s); Mistral 7B on CPU is slow
    ) -> None:
        if not profile.base_url:
            raise ValueError("AIGoat profile missing base_url")
        self.endpoint = profile.base_url
        self.capabilities = list(profile.capabilities)
        self.canary = canary

        chat_surface = profile.surfaces.get("chat", {})
        self._chat_path = chat_surface.get("path", "/api/chat")
        self._chat_method = chat_surface.get("method", "POST").upper()

        login_block = profile.auth.get("login", {})
        self._login_path = login_block.get("path", "/api/auth/login")
        self._login_method = login_block.get("method", "POST").upper()
        self._username = profile.auth.get("default_user", "alice")
        self._password = password

        self._client = httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=timeout,
            follow_redirects=True,        # AIGoat routes end in '/', tolerate both
        )
        self._token: str | None = None
        self._token_lock = asyncio.Lock()

    async def _ensure_token(self) -> str:
        if self._token:
            return self._token
        async with self._token_lock:
            if self._token:
                return self._token
            resp = await self._client.request(
                self._login_method,
                self._login_path,
                json={"username": self._username, "password": self._password},
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("token") or data.get("access_token")
            if not token:
                raise RuntimeError(f"AIGoat login returned no token: {data!r}")
            self._token = token
            return token

    async def send(self, prompt: str, **kw: Any) -> TargetResponse:
        token = await self._ensure_token()
        body: dict[str, Any] = {"message": prompt}
        if "use_kb" in kw:
            body["use_kb"] = bool(kw["use_kb"])
        if "lab_id" in kw and kw["lab_id"] is not None:
            body["lab_id"] = kw["lab_id"]
        if "challenge_id" in kw and kw["challenge_id"] is not None:
            body["challenge_id"] = kw["challenge_id"]
        resp = await self._client.request(
            self._chat_method,
            self._chat_path,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("reply", "")
        return TargetResponse(text=text, raw=data)

    async def aclose(self) -> None:
        await self._client.aclose()
