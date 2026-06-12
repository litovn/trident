from .adapter import TargetResponse


_ECHO_CAPS = ["has_chat", "has_retrieval", "exposes_system_prompt"]


class EchoTargetAdapter:
    id = "echo"

    def __init__(self, canary: str | None = None) -> None:
        self.endpoint = "memory://echo"
        self.capabilities = list(_ECHO_CAPS)
        self.canary = canary

    async def send(self, prompt: str, **kw: object) -> TargetResponse:
        body = f"ECHO: {prompt}"
        # Mimic exfil when the objective asks for a leak — gives the oracle something to detect.
        if self.canary and any(k in prompt.lower() for k in ("leak", "exfil", "planted", "system prompt", "canary")):
            body += f"\n[planted] {self.canary}"
        # Mimic markup output when the prompt asks for it — lets `output_markup` fire.
        if any(k in prompt.lower() for k in ("xss", "<script", "markup")):
            body += "\n<script>alert(1)</script>"
        # Mimic model fingerprinting answer.
        if any(k in prompt.lower() for k in ("which model", "model family", "fingerprint")):
            body += "\nEcho (TRIDENT in-process)"
        return TargetResponse(text=body, raw={"prompt": prompt, "canary": self.canary})
