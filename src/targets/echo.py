from .adapter import TargetResponse


_ECHO_CAPS = ["has_chat", "has_retrieval", "exposes_system_prompt"]


class EchoTargetAdapter:
    id = "echo"

    def __init__(self, canary: str | None = None) -> None:
        self.endpoint = "memory://echo"
        self.capabilities = list(_ECHO_CAPS)
        self.canary = canary
        self._planted: list[str] = []   # in-memory "knowledge base" (simulated RAG store)

    async def plant(self, surface: str, content: str) -> bool:
        """Ingest a honeytoken into the in-memory KB so a later retrieval/exfil
        attempt can surface it (simulates RAG ingestion). `surface` is informational."""
        self._planted.append(content)
        return True

    async def send(self, prompt: str, **kw: object) -> TargetResponse:
        p = prompt.lower()
        body = f"ECHO: {prompt}"
        # RAG / exfil simulation: a prompt that tries to read memory / documents or
        # leak / exfiltrate surfaces whatever was planted (canary fallback if nothing
        # was planted), so the oracle has a real honeytoken to detect.
        if any(k in p for k in ("leak", "exfil", "planted", "system prompt", "canary",
                                "document", "knowledge", "context", "retriev", "summar")):
            for item in self._planted:
                body += f"\n[retrieved] {item}"
            if not self._planted and self.canary:
                body += f"\n[planted] {self.canary}"
        # Markup-injection simulation -> lets `output_markup` fire.
        if any(k in p for k in ("xss", "<script", "markup", "markdown", "image")):
            body += "\n<script>alert(1)</script>"
        # Model-fingerprint simulation -> lets `categorical_match` fire.
        if any(k in p for k in ("which model", "model family", "fingerprint")):
            body += "\nEcho (TRIDENT in-process)"
        return TargetResponse(text=body, raw={"prompt": prompt, "canary": self.canary,
                                              "planted": list(self._planted)})
