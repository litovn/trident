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

## Demo scope (hackathon)

For the hackathon the goal is a **working, legible recon demo** — not full automation.
We deliberately keep the surface small:

- ✅ **Recon works today** and is the headline of the demo. See **[Recon — what works
  and how](#recon--what-works-and-how)** below for the end-to-end flow.
- ✅ **A minimal target profile is enough.** You do *not* need the full profile schema to
  onboard a target — just the handful of fields in **[Minimal target profile](#minimal-target-profile)**.
  `targets/echo.yaml` is the canonical minimal *generic* profile and runs out-of-the-box.
- ✅ **canary / markup / LLM-judge are generic.** The success-detection suite is
  target-agnostic (deterministic checks in `targets/oracle.py`, the LLM-judge in
  `skills/judge_factory.py`) — AIGoat is just one config, never a dependency. The
  LLM-judge degrades gracefully to an offline heuristic when Foundry is not configured.
- ✅ **SKILL.md is the single source of truth.** Each technique is authored as a
  `catalog/skills_catalog/<ID>/SKILL.md` (YAML frontmatter = full machine config,
  Markdown body = agent-facing procedure). The registry loads techniques straight
  from these files — there is no separate catalog YAML to keep in sync.

---

## What's here

```
trident/                  # the package
├── core/                 # client, models (v0.3), policy_gate (5 rules), trace
├── nl/                   # ranker (hybrid: lexicon + embedding + LLM confirm), scope_to_scan
├── skills/               # base, registry (with JSON Schema validator), pyrit_runner
├── agents/               # factory (build_vertical_session + make_pyrit_tools), briefs (enriched)
├── orchestrator/         # coordinator (Phase 0–4), dispatch (agents-as-tools)
├── targets/              # adapter Protocol, oracle (canary + placeholders), echo
├── reports/              # correlator, html_report
└── cli.py                # `python -m src.cli --manifest ... --prompt ...`

catalog/                  # 20 techniques + 12 packages + JSON Schema + 5 reference docs
├── skills_catalog/       # one SKILL.md per technique — the single source of truth
│   ├── TRD-PRM-*/SKILL.md    # 5 prompt techniques (frontmatter = full TechniqueConfig)
│   ├── TRD-APP-*/SKILL.md    # 9 application techniques
│   └── TRD-MOD-*/SKILL.md    # 6 model techniques (-004/-005/-006 deferred-mvp)
├── packages.yaml         # 12 packages: 4 profile + 3 layer + 5 focus
└── schema/catalog.schema.json     # authoritative; validated at load time

targets/                  # declarative target profiles (v0.3)
├── echo.yaml             # in-process profile for smoke / unit tests
├── aigoat.yaml           # the reference vulnerable target
└── target_profile.example.yaml

manifests/                # Rules of Engagement as Code (ADR-008)
├── sample.yaml           # recon-mode smoke
└── sample_attack.yaml    # attack-mode smoke

                          # (tests/ suite is not wired on this demo branch — see "Tests" below)
```

---

## Install

```powershell
# Full install (all capabilities): Copilot SDK + ranker + PyRIT + dev tooling
pip install -e ".[sdk,ranker,real,dev]"
```

Extras (compose as needed):

| Extra | Pulls in | Needed for |
|---|---|---|
| `sdk` | `github-copilot-sdk`, `azure-identity` | the agentic Coordinator + vertical sessions |
| `ranker` | `openai`, `azure-identity` | Phase-1 NL→scope ranker (Azure OpenAI) |
| `real` | `pyrit` | the PyRIT execution surface (converters, judged scorers, orchestrators) |
| `dev` | `pytest`, `build` | tests + packaging |

The base install (no extras) is enough to import the catalog/registry/oracle and
the deterministic core. `requirements.txt` remains a pinned lockfile of a known-good
environment.

> Python 3.11+ required (tested on 3.11.9).
> Every run goes through the agentic Coordinator and **requires Microsoft
> Foundry** (`FOUNDRY_ENDPOINT` + `az login`, or `FOUNDRY_API_KEY`). See `.env.example`.


---

## Run

Every campaign goes through the SDK Coordinator and **requires Foundry**
(`FOUNDRY_ENDPOINT` + `az login`, or `FOUNDRY_API_KEY`). The Echo target is
in-process, so these examples are a cheap end-to-end smoke that still exercises
the real Coordinator → vertical → PyRIT path.

### Recon — what works and how

```powershell
python -m src.cli `
  --manifest manifests/sample.yaml `
  --catalog  catalog `
  --out      output `
  --prompt   "recon the bot defenses, fingerprint the model, map the app surface"
```

Expected: each layer fires its **lead recon technique** —

| Layer | Technique | Scorer | Verdict kind |
|---|---|---|---|
| prompt | `TRD-PRM-R01` Guardrail probing | `judged_objective` | `assessed` (LLM-judge, offline fallback) |
| application | `TRD-APP-R01` RAG/tool surface enumeration | `judged_objective` | `assessed` (LLM-judge, offline fallback) |
| model | `TRD-MOD-001` Model fingerprinting | `categorical_match` | `confirmed` (deterministic) |

Outputs: `output/smoke-001-recon.html` + `output/smoke-001-recon.trace.jsonl`.

**How recon works, end to end:**

1. **NL → scope.** The ranker maps the prompt to recon techniques; `mode: recon` on the
   manifest means the policy gate keeps only `phase ∈ {recon, both}` and blocks exploit-only
   techniques (`rule=mode_intent`).
2. **scope → scan.** `scope_to_scan` drops any technique whose `needs_capabilities` the target
   profile doesn't satisfy. Echo advertises `has_chat` → all three leads survive.
3. **Dispatch.** The Coordinator opens one *fenced* vertical session per layer, exposing only
   that layer's in-scope skills.
4. **Execute + score (per technique).** Every skill funnels through `PyritRunner`:
   `PolicyGate.check` → resolve `{planted_secret}`/`{target_name}` in the objective →
   `target.send(prompt)` → score. Deterministic scorers (`categorical_match` here) go through
   the **SuccessOracle** and yield `confirmed` ground truth; judged scorers (`judged_objective`)
   go through the **LLM-judge**, falling back to the offline refusal heuristic when Foundry is
   absent (verdict stays `assessed`).
5. **Report.** The immutable `Trace` feeds `correlator` + `html_report`.

So recon already exercises **both** halves of the generic scoring suite on a generic target:
the deterministic path (`categorical_match` → `confirmed` model fingerprint) and the
LLM-judge path (`judged_objective`). The same `SuccessOracle` powers `exfil_canary` /
`leak_detector` (canary honeytoken) and `output_markup` (executable-markup regex) used by the
attack flow below.

### Attack (with canary exfil)

```powershell
python -m src.cli `
  --manifest manifests/sample_attack.yaml `
  --catalog  catalog `
  --out      output `
  --prompt   "data exfiltration: leak the planted secret and exfiltrate sensitive data"
```

Expected: the ranker picks `PKG-EXFIL`, runs 4 leak-class techniques across the
three layers, the EchoTargetAdapter surfaces the planted canary, and the
`SuccessOracle` confirms each disclosure (5 oracle hits, severity bumped from
`info` → `high` per the MSRC AI bug bar).

---

## Against a real target

The manifest names its target via `target_profile_id`; TRIDENT resolves the
matching profile from the `targets/` directory (e.g. `targets/aigoat.yaml`).
Switch targets by changing that one field — no CLI flag. Requires the Copilot
SDK + Foundry, as above.

```powershell
python -m src.cli `
  --manifest manifests/aigoat_l0_prompt_injection.yaml `
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

## Minimal target profile

You do **not** need the full profile schema to onboard a target. A target plugs into the
**generic** core through a small YAML profile + a `SuccessOracle` block; everything else is
optional. `targets/echo.yaml` is the canonical *minimal generic* profile and is what the
recon/attack smokes above use.

The minimum to get **recon + canary + markup + LLM-judge** working:

```yaml
id: my-target                 # slug (the CLI maps this to an adapter)
name: "My GenAI app"
base_url: "https://my-target.invalid"

# Drives technique targetability: a technique runs only if the target's capabilities
# satisfy its needs_capabilities. has_chat alone is enough for the three recon leads.
capabilities: [has_chat]

# Abstract attack surface → concrete endpoint. Recon leads only need `chat`.
surfaces:
  chat: { method: POST, path: /api/chat }

auth: { type: none }          # none | bearer | apikey | cookie

# The generic success-detection suite. Everything here is optional, but each block
# unlocks one deterministic detector:
success_oracle:
  canary:                     # → exfil_canary / leak_detector (honeytoken planted by the adapter)
    prefix: TRIDENT
    plant_surface: chat       # chat | retrieval_ingest | search | tool
    data_classification: Confidential   # feeds MSRC severity
  expected_model_set: [GPT, Llama, Mistral, Phi]   # → categorical_match (model fingerprint)
# output_markup needs no config — it is a structural regex over the response.
# refusal_judge / judged_objective need no target config — they use the LLM-judge
# (or the offline heuristic when Foundry is absent).
```

What each detector needs from the profile:

| Detector | Verdict | Needs in profile |
|---|---|---|
| `exfil_canary` / `leak_detector` | `confirmed` | `success_oracle.canary` (and an adapter that plants it) |
| `output_markup` | `confirmed` | nothing — generic regex on the output |
| `categorical_match` (fingerprint) | `confirmed` | `success_oracle.expected_model_set` |
| `refusal_judge` / `judged_objective` | `assessed` | nothing — LLM-judge, offline fallback |

> Adapters: the CLI maps `id` → an adapter (`echo`, `aigoat`). A brand-new `id` needs a small
> adapter that knows how to `send()` (and, if you use a canary, how to plant it). For the demo,
> reuse `echo` (in-process) or `aigoat`. See `targets/target_profile.example.yaml` for the full
> annotated schema.

---

## Tests

> The automated `pytest` suite is **not part of this demo branch** — it will be
> re-wired in v1 alongside the real PyRIT/judge integration. For the hackathon the
> verification path is the **recon smoke** above (deterministic `categorical_match`
> → `confirmed`) plus the offline LLM-judge fallback, which run without Foundry.

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

- **Automatic *technique* synthesis — v1 (out of demo scope).** Grow tooling that
  drafts new `SKILL.md` techniques (and recon → target-profile generation). Today
  every technique is a hand-authored `SKILL.md` loaded directly by the registry.
- Re-wire the `pytest` suite (policy gate, ranker, end-to-end dispatch).
- Real PyRIT wiring as the default judge in `skills/pyrit_runner.py`
  (SelfAskRefusalScorer, SelfAskTrueFalseScorer) — today's default is the offline heuristic.
- HTTP target adapter for AIGoat (today's adapter is in-process Echo).
- Cumulative-scope techniques (`TRD-MOD-004/005/006`) once the campaign-level
  scorer infra lands.
- Foundry hosted deployment (one-click `azd up`) with Key Vault + Managed Identity.
- Richer HTML report (chain visualization, ATLAS heatmap).
