"""PyRIT runtime bootstrap.

v0.4 decision (A.b): we keep TRIDENT Trace JSONL as the primary trace and force
PyRIT to use an *in-memory* CentralMemory so it never writes to
``~/.pyrit/results.db`` or ``~/.pyrit/results.duckdb`` on the developer machine.
Scores produced by PyRIT scorers/attacks live for the lifetime of the process;
we copy what we need into Trace JSONL at the call site (PyritRunner).

Idempotent and thread-safe. Call ``ensure_pyrit_initialized()`` from anywhere
that is about to touch PyRIT; subsequent calls are no-ops.
"""
import threading

_lock = threading.Lock()
_done = False


def ensure_pyrit_initialized() -> None:
    global _done
    if _done:
        return
    with _lock:
        if _done:
            return
        from pyrit.memory import CentralMemory, SQLiteMemory
        CentralMemory.set_memory_instance(SQLiteMemory(db_path=":memory:", silent=True))
        _done = True
