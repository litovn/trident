# TRIDENT — Skeleton

Black-box multi-agent AI red-teaming accelerator. See `TRIDENT_design_context.md` for full design.

This is the **infrastructure skeleton** — orchestrator, vertical agents, NL→scope, skill→tool wiring,
policy gate, trace, target adapter. Catalog/manifest content is sample-only; replace with real
catalog when ready.

## What's here

```
trident/
├── core/           # client, models, policy_gate, trace  (the choke points)
├── nl/             # ranker, scope_to_scan                (NL → ScanPlan)
├── skills/         # base, registry, pyrit_runner         (technique → tool)
├── agents/         # factory, briefs                       (vertical sessions)
├── orchestrator/   # coordinator, dispatch                 (Phases 0-4 + agents-as-tools)
├── targets/        # adapter, oracle, echo                 (pluggable, ADR-013)
├── reports/        # correlator, html_report               (post-hoc cross-layer)
└── cli.py          # `trident run --manifest ... --prompt ...`
```

## Install

```powershell
pip install -e .[dev]
# For the real (agentic) run, also:
pip install -e .[sdk,real]
```

## Smoke test (no SDK, no PyRIT)

```powershell
python -m trident.cli `
  --manifest manifests/sample.yaml `
  --target manifests/echo_target.yaml `
  --catalog catalog `
  --prompt "Run a quick LLM01 jailbreak probe" `
  --dry-run
```

Expected: 3 scorecards (one per layer, those whose techniques are capability-applicable),
an `output/smoke-001.html` report, and a JSONL trace file.

## Real run (agentic)

Drop `--dry-run`. Requires the Copilot SDK installed and authenticated.
The Coordinator session will be created with `dispatch_prompt_agent` / `dispatch_app_agent` /
`dispatch_model_agent` as tools; each dispatch spins up a fenced vertical session with only that
layer's in-scope skills.

## The 4 invariants (do not break)

1. Skills NEVER call PyRIT directly — they go through `skills.pyrit_runner.PyritRunner`.
2. Every action passes `core.policy_gate.PolicyGate.check` (inside the skill handler).
3. Only the immutable `core.trace.Trace` feeds the report — no blackboard.
4. Target-agnostic core: only `targets/*.py` may know endpoint specifics. AIGoat is one impl, never a dep.
