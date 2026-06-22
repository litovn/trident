from pathlib import Path
from typing import Iterator, Optional

from .models import Action, Decision, ExecutionResult, Layer, TraceStep


class Trace:
    def __init__(self, jsonl_path: Optional[Path] = None) -> None:
        self._steps: list[TraceStep] = []
        self._sink = jsonl_path
        if self._sink:
            self._sink.parent.mkdir(parents=True, exist_ok=True)

    # ---- write ------------------------------------------------------------

    def append_gate(self, action: Action, decision: Decision) -> None:
        self._write(TraceStep(
            kind="gate",
            layer=action.layer,
            technique_id=action.technique_id,
            payload={"params": action.params, "decision": decision.model_dump()},
        ))

    def append_exec(self, action: Action, result: ExecutionResult) -> None:
        self._write(TraceStep(
            kind="exec",
            layer=action.layer,
            technique_id=action.technique_id,
            payload={"params": action.params, "result": result.model_dump()},
        ))

    def append_dispatch(self, layer: Layer, payload: dict) -> None:
        self._write(TraceStep(kind="dispatch", layer=layer, payload=payload))

    def _write(self, step: TraceStep) -> None:
        self._steps.append(step)
        if self._sink:
            with self._sink.open("a", encoding="utf-8") as f:
                f.write(step.model_dump_json() + "\n")

    # ---- read -------------------------------------------------------------

    def steps(self) -> Iterator[TraceStep]:
        return iter(list(self._steps))

    def for_layer(self, layer: Layer) -> list[TraceStep]:
        return [s for s in self._steps if s.layer == layer]

    def __len__(self) -> int:
        return len(self._steps)
