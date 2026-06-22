"""In-process log fan-out for the web terminal's live SSE stream.

A single logging handler on the root logger pushes interesting records to every
open ``/api/logstream`` subscriber, plus a small ring buffer so a freshly opened
terminal immediately shows recent activity. Stdlib only.
"""
from __future__ import annotations

import collections
import logging
import queue
import threading

# Loggers worth surfacing live (prefix match). Keeps the alembic / sqlite-migration
# / openai-internal spam out of the terminal while preserving the engine's story.
_INCLUDE_PREFIXES = (
    "trident",                 # trident.web, trident.judge
    "src.",                    # src.orchestrator.dispatch, src.core.client, ...
    "copilot",                 # Copilot CLI client
    "httpx",                   # outbound Foundry HTTP
    "pyrit.prompt_target",     # prompts sent to targets / judge
    "pyrit.prompt_converter",  # converter output (obfuscation, etc.)
    "pyrit.exceptions",        # content-filter / bad-request notices
)


class _IncludeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name or ""
        return any(name == p or name.startswith(p) for p in _INCLUDE_PREFIXES)


class LogBus:
    """Thread-safe broadcaster: one logging handler, many SSE subscribers."""

    def __init__(self, backlog: int = 200) -> None:
        self._subs: set[queue.Queue] = set()
        self._backlog: collections.deque = collections.deque(maxlen=backlog)
        self._lock = threading.Lock()
        self._installed = False

    def install(self) -> None:
        with self._lock:
            if self._installed:
                return
            self._installed = True
        handler = _BusHandler(self)
        handler.setLevel(logging.INFO)
        handler.addFilter(_IncludeFilter())
        logging.getLogger().addHandler(handler)

    def subscribe(self) -> "queue.Queue":
        q: queue.Queue = queue.Queue(maxsize=2000)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: "queue.Queue") -> None:
        with self._lock:
            self._subs.discard(q)

    def snapshot(self) -> list:
        with self._lock:
            return list(self._backlog)

    def publish(self, item: dict) -> None:
        with self._lock:
            self._backlog.append(item)
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(item)
            except queue.Full:
                pass


class _BusHandler(logging.Handler):
    def __init__(self, bus: LogBus) -> None:
        super().__init__()
        self._bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - logging must never raise
            return
        self._bus.publish({
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "msg": msg,
        })


BUS = LogBus()
