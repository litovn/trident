from urllib.parse import urlsplit

from .models import Action, Decision, Manifest, Phase, TechniqueConfig


# Recon-mode policy: which technique phases survive (ADR-018)
_RECON_OK_PHASES: set[Phase] = {"recon", "both"}


def _host_of(s: str) -> str:
    """Extract a hostname from a URL, host:port, or bare host.

    Examples:
        http://127.0.0.1:8000  -> 127.0.0.1
        memory://echo          -> echo
        127.0.0.1              -> 127.0.0.1
        api.example.com:8443   -> api.example.com
    """
    if not s:
        return ""
    if "://" in s:
        return (urlsplit(s).hostname or "").lower()
    return s.split("/", 1)[0].split(":", 1)[0].lower()


class PolicyGate:
    def __init__(self, manifest: Manifest, registry=None):
        self.manifest = manifest
        self.registry = registry  # optional: enables phase-aware checks
        self._budget_used: dict[str, int] = {layer: 0 for layer in manifest.layers}

    def _tech(self, tid: str) -> TechniqueConfig | None:
        if not self.registry:
            return None
        try:
            return self.registry.get(tid)
        except KeyError:
            return None

    def check(self, action: Action) -> Decision:
        m = self.manifest

        # 1) Denylist
        if action.technique_id in m.technique_denylist:
            return Decision(allow=False, reason="technique in denylist", rule="denylist")

        # 2) Allowlist
        if m.technique_allowlist and action.technique_id not in m.technique_allowlist:
            return Decision(allow=False, reason="technique not in allowlist", rule="allowlist")

        # 3) Layer scope
        if action.layer not in m.layers:
            return Decision(allow=False, reason=f"layer {action.layer} not in scope",
                            rule="layer_scope")

        # 4) Mode / phase intent + status (only enforceable if registry present)
        tech = self._tech(action.technique_id)
        if tech is not None:
            if m.mode == "recon" and tech.phase not in _RECON_OK_PHASES:
                return Decision(allow=False,
                                reason=f"phase={tech.phase} blocked in recon mode",
                                rule="mode_intent")
            if tech.status == "deferred-mvp":
                return Decision(allow=False,
                                reason="technique marked deferred-mvp",
                                rule="status")

        # 5) Per-vertical budget
        used = self._budget_used.get(action.layer, 0)
        if used >= m.query_budget_per_vertical:
            return Decision(allow=False, reason="query budget exhausted", rule="budget")

        # 6) Host allowlist (only checked if endpoint param present).
        # Compares hostnames, not substrings, to prevent
        # `https://evil.com/proxy?to=127.0.0.1` from satisfying ["127.0.0.1"].
        endpoint = (action.params or {}).get("endpoint", "")
        if endpoint and m.host_allowlist:
            ep_host = _host_of(endpoint)
            allowed_hosts = {_host_of(a) for a in m.host_allowlist}
            if not ep_host or ep_host not in allowed_hosts:
                return Decision(allow=False,
                                reason=f"endpoint host {ep_host!r} (from {endpoint!r}) not in host_allowlist",
                                rule="host_allowlist")

        # 7) HITL — v0 stub: deny; v1 will prompt
        if action.technique_id in m.hitl_techniques:
            return Decision(allow=False, reason="HITL required (v0 stub denies)", rule="hitl")

        self._budget_used[action.layer] = used + 1
        return Decision(allow=True, reason="ok", rule="permitted")

    def budget_used(self, layer: str) -> int:
        return self._budget_used.get(layer, 0)
