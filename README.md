# TRIDENT

**Black-box, multi-agent AI red-teaming accelerator.**
Built on GitHub Copilot SDK + Microsoft Foundry + (eventually) PyRIT.

> Phase: **v0.3 skeleton** — orchestrator, vertical agents, NL→scope, hybrid ranker,
> policy gate, success oracle + canary, trace, target adapters. Catalog content
> (20 techniques + 12 packages) is production-grade and target-agnostic.
> The Coordinator runs with the offline KeywordEmbedder out-of-the-box; the same
> code switches to Azure OpenAI by setting `AZURE_OPENAI_ENDPOINT`.

See `TRIDENT_design_context.md` for the full design rationale and ADRs.

---

## What's here

```
trident/                  # the package
├── core/                 # client, models (v0.3), policy_gate (7 rules), trace
├── nl/                   # ranker (hybrid: lexicon + embedding + LLM confirm), scope_to_scan
├── skills/               # base, registry (with JSON Schema validator), pyrit_runner
├── agents/               # factory (wrap_as_sdk_tools), briefs (enriched)
├── orchestrator/         # coordinator (Phase 0–4), dispatch (agents-as-tools)
├── targets/              # adapter Protocol, oracle (canary + placeholders), echo
├── reports/              # correlator, html_report
└── cli.py                # `trident run --manifest ... --prompt ...`

catalog/                  # 20 techniques + 12 packages + JSON Schema + 5 reference docs
├── prompt.yaml           # TRD-PRM-001..004 + TRD-PRM-R01
├── application.yaml      # TRD-APP-001..008 + TRD-APP-R01
├── model.yaml            # TRD-MOD-001..006  (-004/-005/-006 deferred-mvp)
├── packages.yaml         # 12 packages: 4 profile + 3 layer + 5 focus
└── schema/catalog.schema.json     # authoritative; validated at load time

targets/                  # declarative target profiles (v0.3)
├── echo.yaml             # in-process profile used by --dry-run
├── aigoat.yaml           # the reference vulnerable target
└── target_profile.example.yaml

manifests/                # Rules of Engagement as Code (ADR-008)
├── sample.yaml           # recon-mode smoke
└── sample_attack.yaml    # attack-mode smoke

tests/                    # 17 tests (policy gate, ranker, end-to-end dispatch)
```

---

## Install

```powershell
pip install -e ".[dev]"
# For the real (agentic) run, also:
pip install -e ".[sdk,real]"
```

> Python 3.12+ required (tested on 3.14.4).
> The runtime works fully offline; Azure OpenAI is opt-in via env vars.

---

## Smoke test (no SDK, no PyRIT)

### Recon mode

```powershell
trident `
  --manifest manifests/sample.yaml `
  --target   targets/echo.yaml `
  --catalog  catalog `
  --out      output `
  --prompt   "recon the bot defenses, fingerprint the model, map the app surface" `
  --dry-run
```

Expected: each layer fires its lead recon technique
(`TRD-PRM-R01`, `TRD-APP-R01`, `TRD-MOD-001`); the deterministic
`categorical_match` scorer for model fingerprinting marks `verdict: confirmed`.
Outputs: `output/smoke-001-recon.html` + `output/smoke-001-recon.trace.jsonl`.

### Attack mode (with canary exfil)

```powershell
trident `
  --manifest manifests/sample_attack.yaml `
  --target   targets/echo.yaml `
  --catalog  catalog `
  --out      output `
  --prompt   "data exfiltration: leak the planted secret and exfiltrate sensitive data" `
  --dry-run
```

Expected: the ranker picks `PKG-EXFIL`, runs 4 leak-class techniques across the
three layers, the EchoTargetAdapter surfaces the planted canary, and the
`SuccessOracle` confirms each disclosure (5 oracle hits, severity bumped from
`info` → `high` per the MSRC AI bug bar).

---

## Real run (agentic)

Drop `--dry-run`. Requires the Copilot SDK installed and authenticated.

```powershell
python -m src.cli --manifest manifests/sample_attack.yaml --target targets/echo.yaml --catalog catalog --out output --prompt ""

trident `
  --manifest manifests/sample_attack.yaml `
  --target   targets/echo.yaml `
  --catalog  catalog `
  --out      output `
  --prompt   "<natural-language scope from the user>"
```

The Coordinator session is created with `dispatch_prompt_agent`,
`dispatch_app_agent`, and `dispatch_model_agent` as tools. Each dispatch spins
up a *fenced* vertical session that exposes **only** that layer's in-scope
skills (post policy-gate filtering). The agent never sees OWASP/ATLAS taxonomy
directly — it receives ready converters + objectives via the enriched
`VerticalConfig` brief.

---

## Tests

```powershell
pytest -v
```

Current status: **17/17 passing**
(7 policy gate rules · 5 ranker · 2 end-to-end dispatch · 3 invariants).

---

## How it all wires together

```
NL prompt
  │
  ▼ Phase 1 — Ranker (hybrid: lexicon hits + cosine + LLM confirm, package-first)
Scope (selection_mode = package | techniques)
  │
  ▼ Phase 2 — scope_to_scan (gating: capabilities, allow/denylist, mode, status)
ScanPlan(verticals=[VerticalConfig×N], skipped=[…], layer_cardinality)
  │
  ▼ Phase 3 — Coordinator
   ├── dispatch_prompt_agent  ─► fenced PromptVertical session    ─►┐
   ├── dispatch_app_agent     ─► fenced AppVertical session       ─►├─► Scorecards
   └── dispatch_model_agent   ─► fenced ModelVertical session     ─►┘
                                          │
                                          ▼ each skill handler:
                                          1. PolicyGate.check(action)
                                          2. PyritRunner.execute(tech, params, target)
                                                ├─ resolve {planted_secret} in objective
                                                ├─ target.send(prompt)
                                                ├─ DETERMINISTIC scorer? → SuccessOracle.detect()
                                                └─ JUDGED scorer?         → v0 surrogate / PyRIT
                                          3. Trace.append_*
  │
  ▼ Phase 4 — reports.correlator + reports.html_report
output/<campaign>.html  +  output/<campaign>.trace.jsonl
```

---

## The 4 invariants (do not break)

1. **Skills NEVER call PyRIT directly** — they go through `skills.pyrit_runner.PyritRunner`.
2. **Every action passes `core.policy_gate.PolicyGate.check`** (inside the skill handler).
3. **Only the immutable `core.trace.Trace`** feeds the report — no blackboard.
4. **Target-agnostic core** — only `targets/*.py` may know endpoint specifics.
   AIGoat is one implementation, never a dependency.

---

## Key schema decisions (v0.3 — see `catalog/CATALOG.md` + `catalog/severity.md`)

| Concept | Type | Notes |
|---|---|---|
| `mode` | `recon` / `attack` | Campaign-level, on the manifest. Gate-enforced (ADR-018). |
| `phase` | `recon` / `exploit` / `both` | Technique-level, on each catalog entry. |
| `severity_base` | `critical` / `high` / `medium` / `low` / `info` | MSRC AI bug bar (string, not int). |
| `severity_track` | `security` / `content` | Track B (content) is *informational*, not blocking. |
| `scorer` | enum | DETERMINISTIC → SuccessOracle; JUDGED → PyRIT self-ask. |
| `success_oracle` | block on target profile | Canary, plant surface, data classification, expected model set. |
| Layer cardinality | `1` OR `3`, never `2` | ADR-021: each campaign targets one layer or all three. |

---

## Switching to Microsoft Foundry 

Both the Copilot SDK Coordinator and the Phase-1 ranker route their model
calls through Foundry using `DefaultAzureCredential` — every call bills
against **Foundry credit, not GitHub Copilot tokens**. `FOUNDRY_ENDPOINT` is
required; `TridentClient.start()` raises if it is unset. The ranker keeps a
deterministic `KeywordEmbedder` + `PassthroughConfirmer` only for unit tests
(no model call), not as a runtime fallback.

```powershell
$env:FOUNDRY_ENDPOINT          = "https://<your-foundry>.cognitiveservices.azure.com"
$env:FOUNDRY_MODEL_DEPLOYMENT  = "gpt-4o-mini"           # Coordinator + ranker chat
$env:FOUNDRY_EMBED_DEPLOYMENT  = "text-embedding-3-large" # ranker embedder (multilingual)
# Auth (preferred): DefaultAzureCredential — `az login` locally, MI in prod.
# Optional BYOK shortcut: $env:FOUNDRY_API_KEY = "..."
az login
pip install -e ".[sdk,ranker]"
```

No code change required — `TridentClient` (in `src/core/client.py`) and
`make_ranker(registry)` both pick up the Foundry config from `FoundrySettings`
in `src/core/config.py`. See `.env.example` for the full variable list.

---

## Roadmap (post-MVP)

- Real PyRIT wiring in `skills/pyrit_runner.py` (SelfAskRefusalScorer, SelfAskTrueFalseScorer).
- HTTP target adapter for AIGoat (today's adapter is in-process Echo).
- Cumulative-scope techniques (`TRD-MOD-004/005/006`) once the campaign-level
  scorer infra lands.
- Foundry hosted deployment (one-click `azd up`) with Key Vault + Managed Identity.
- Richer HTML report (chain visualization, ATLAS heatmap).
