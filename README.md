# TRIDENT

**Black-box, multi-agent AI red-teaming accelerator for generative-AI systems.**

TRIDENT turns a plain-English goal — *"jailbreak the chatbot"*, *"prove it leaks data"*,
*"just map the attack surface"* — into a governed, auditable red-team campaign. It selects
techniques from a curated, standards-mapped catalog (**OWASP LLM Top 10 (2025)** ×
**MITRE ATLAS** v6), dispatches them across three attack layers via fenced agents, scores
each result with deterministic oracles and LLM judges, and emits a self-contained HTML
report plus an immutable trace.

Built on the **GitHub Copilot SDK** (agentic orchestration), **Microsoft Foundry** (all
model calls), and **PyRIT** (execution surface — converters, scorers, orchestrators).

> **Status — v0.3.** Target-agnostic catalog (20 techniques + 12 packages), working
> orchestrator, vertical agents, conversational NL→scope advisor, 5-rule policy gate,
> success oracle + canary honeytoken, immutable trace, and target adapters. Foundry-backed
> scope selection degrades gracefully to a deterministic default when Foundry is absent.

---

## Why TRIDENT

Red-teaming a GenAI app is hard to do *consistently* — findings depend on tester
creativity, coverage is uneven, results aren't reproducible, and it's easy to stray
outside the rules of engagement. TRIDENT makes the whole campaign **declarative and
governed**:

- **Black-box** — needs only an endpoint and a small target profile; no weights, no source.
- **Standards-mapped** — every technique is tagged to OWASP LLM Top 10 and MITRE ATLAS.
- **Agents select, never invent** — they choose from the fixed, reviewed catalog only.
- **Governed by code** — a manifest is your *Rules of Engagement as Code* (mode, host
  allowlist, technique denylist, query budgets, HITL gates). Every action passes a policy
  gate before touching the target.
- **Auditable** — one immutable trace records every prompt, response, verdict, and evidence.

---

## How it works

```
NL prompt ("prove it leaks the planted secret")
   │
   ▼  Phase 1 — Package advisor (conversational, Foundry-backed; or --package)
Chosen package (e.g. PKG-EXFIL)
   │
   ▼  Phase 2 — scope_to_scan (gating: capabilities, allow/denylist, mode, status)
ScanPlan(verticals = [1 or 3], skipped = [...])
   │
   ▼  Phase 3 — Coordinator (Copilot SDK, agents-as-tools)
    ├── dispatch_prompt_agent ─► fenced Prompt session ─►┐
    ├── dispatch_app_agent    ─► fenced App session    ─►├─► Scorecards
    └── dispatch_model_agent  ─► fenced Model session  ─►┘
                                       │  each skill handler:
                                       │  1. PolicyGate.check(action)
                                       │  2. PyritRunner.execute(technique, params, target)
                                       │  3. SuccessOracle / LLM judge → verdict
                                       │  4. Trace.append_*
   │
   ▼  Phase 4 — reports.correlator + reports.html_report
output/<campaign>.html  +  output/<campaign>.trace.jsonl
```

Four collaborating roles:

1. **NL→scope advisor** (`src/nl/`) — conversational package selector; asks to clarify only
   when the prompt is vague.
2. **Coordinator** (`src/orchestrator/`) — top-level agent; opens one *fenced* vertical
   session per in-scope layer, exposing only that layer's skills.
3. **Vertical agents** (`src/agents/`) — Prompt / Application / Model specialists.
4. **Runner + oracle + trace** (`src/skills/`, `src/targets/`, `src/core/`) — the
   deterministic spine: policy-gate, execute via PyRIT, score, record.

A campaign targets **one layer or all three — never exactly two** (ADR-021).

---

## The catalog: 3 layers, 20 techniques

The catalog is the single source of truth. Each technique is one file —
`catalog/skills_catalog/<ID>/SKILL.md` — whose **YAML frontmatter is the machine config**
and whose **Markdown body is the agent-facing procedure**. The registry loads techniques
from these files and validates each against `catalog/schema/catalog.schema.json` at load
time (fail-fast).

| Layer | Attacks | Techniques |
|---|---|---|
| **Prompt** (`TRD-PRM-*`) | the input / prompt surface | 5 — system-prompt extraction, direct injection, multi-turn jailbreak, obfuscated injection, guardrail recon |
| **Application** (`TRD-APP-*`) | RAG, tools, orchestration | 9 — indirect/RAG injection, info disclosure, output-handling (XSS), tool abuse, memory poisoning, exfil-via-tool, credential harvesting, tool poisoning, surface enumeration |
| **Model** (`TRD-MOD-*`) | the model via its API | 6 — fingerprinting, data extraction, misinformation, + membership inference / extraction / inversion (post-MVP) |

Coverage is honest: LLM03 (Supply Chain) and LLM10 (Unbounded Consumption) are marked
⛔ not black-box targetable, with a stated reason. Full matrices and per-technique cards
live in [`catalog/CATALOG.md`](backend/catalog/CATALOG.md).

---

## Attack packages

A **package** bundles technique IDs with safe limits (`max_intensity`, `query_budget`) and
the modes it runs in. The advisor resolves a prompt to a package. 12 packages
(`catalog/packages.yaml`):

- **Profiles (one-click):** `PKG-QUICK` · `PKG-OWASP` · `PKG-ATLAS` · `PKG-360`.
- **Per-layer:** `PKG-PROMPT` · `PKG-APP` · `PKG-MODEL`.
- **Per-focus:** `PKG-GUARDRAIL` (jailbreak) · `PKG-EXFIL` (exfiltration) · `PKG-RAG`
  (retrieval) · `PKG-AGENTIC` (tool abuse) · `PKG-RECON` (non-intrusive).

---

## Scoring: confirmed vs assessed

Every result carries a verdict *kind* so you know how much to trust it:

| Verdict | Meaning | Produced by |
|---|---|---|
| **`confirmed`** | deterministic ground truth, with evidence in the trace | `exfil_canary` / `leak_detector` (honeytoken), `output_markup` (regex), `categorical_match` (fingerprint) |
| **`assessed`** | an LLM judgement, not ground truth | `refusal_judge` / `judged_objective` (LLM judge, offline heuristic fallback) |

Deterministic detectors are powered by a per-target **SuccessOracle** (`src/targets/oracle.py`).
The key mechanism is a **canary honeytoken**: generated per campaign, planted via the
adapter's `plant_surface`, and injected into objectives through `{planted_secret}`. When
the model emits that exact token, disclosure is *confirmed*, and the canary's
`data_classification` drives **MSRC AI bug-bar** severity. See
[`catalog/severity.md`](backend/catalog/severity.md),
[`catalog/oracle.md`](backend/catalog/oracle.md), and
[`catalog/scorers.md`](backend/catalog/scorers.md).

---

## Install

> **Python 3.11+** required. All commands run from inside `backend/`.

```powershell
cd backend
pip install -e ".[sdk,ranker,real,dev]"   # full install; extras compose as needed
```

| Extra | Pulls in | Needed for |
|---|---|---|
| `sdk` | `github-copilot-sdk`, `azure-identity` | agentic Coordinator + vertical sessions |
| `ranker` | `openai`, `azure-identity` | the Phase-1 NL→scope advisor |
| `real` | `pyrit` | PyRIT execution surface |
| `bridge` | `fastapi`, `uvicorn` | the optional `server.py` frontend bridge |
| `dev` | `pytest`, `build` | tests + packaging |

The **base install** (no extras) runs the deterministic core and the offline web engine.
`requirements.txt` is a pinned lockfile of a known-good environment.

---

## Configure Microsoft Foundry

Both the Coordinator and the advisor route **every model call through Microsoft Foundry**
(billed to Foundry credit, never Copilot tokens). `FOUNDRY_ENDPOINT` enables the full
agentic path; without it the advisor falls back to a deterministic package and the judge
to an offline heuristic — a run still works.

```powershell
$env:FOUNDRY_ENDPOINT         = "https://<account>.cognitiveservices.azure.com/"
$env:FOUNDRY_MODEL_DEPLOYMENT = "gpt-4o-mini"

az login   # DefaultAzureCredential (preferred); or set $env:FOUNDRY_API_KEY for BYOK
```

Copy `.env.example` to `.env` for the complete variable list. `TridentClient`
(`src/core/client.py`) and the ranker read `FoundrySettings` (`src/core/config.py`) from
the environment — no code change needed.

---

## Run

> All commands run from inside `backend/`.

### Web UI

`frontend/frontend.html` is a single-file console (planner, live terminal, report viewer)
served by a stdlib web bridge (`src/web/`) — zero extra deps beyond the base install. It
runs the in-process **Echo** target out of the box, so you can exercise the full
plan → dispatch → score → report flow with no external target.

```powershell
run_web.cmd                 # http://localhost:8765
run_web.cmd --port 9000
```

| Endpoint | Purpose |
|---|---|
| `GET  /api/health` | capability probe (catalog counts, foundry/pyrit/sdk flags) |
| `GET  /api/packages`, `/api/techniques` | catalog data for the UI |
| `POST /api/plan` | one advisor turn — propose packages or clarify |
| `POST /api/campaign` | run a recon/attack campaign; returns trace + report |
| `GET  /api/logstream` | Server-Sent Events: live engine logs |

### CLI

Point it at a manifest (Rules of Engagement) and a prompt; the advisor (or `--package`)
selects the scope.

```powershell
python -m src.cli `
  --manifest manifests/aigoat.yaml `
  --catalog  catalog --targets-dir targets --out output `
  --prompt   "direct prompt injection: override the bot and exfiltrate the secret"

# Skip the advisor and pin a package:
python -m src.cli --manifest manifests/aigoat.yaml --package PKG-GUARDRAIL `
  --prompt "bypass the guardrails"
```

Useful flags (`python -m src.cli --help`): `--package <ID>`, `--confirm-chain`
(human-in-the-loop per layer), `--targets-dir`, `--catalog`, `--out`. A run writes
`output/<campaign>.html` and `output/<campaign>.trace.jsonl`.

A manifest is small and declarative — `manifests/aigoat.yaml`:

```yaml
campaign_id: aigoat
mode: attack                 # recon | attack — gate-enforced (ADR-018)
target_profile_id: aigoat    # resolves targets/aigoat.yaml by its `id`
technique_denylist: []
host_allowlist: [127.0.0.1]  # attack traffic stays here
query_budget_per_vertical: 5
hitl_techniques: []
```

> **Echo** is in-process and needs nothing — the fastest end-to-end smoke. **AIGoat**
> needs the target running locally and `AIGOAT_PASSWORD` (see `.env.example`).

---

## Onboarding a target

The core is **target-agnostic** — only `src/targets/*.py` may know endpoint specifics. A
target plugs in via a YAML **profile** plus a `success_oracle` block; **targetability is
computed** (a technique runs only if the target's `capabilities` satisfy its
`needs_capabilities`).

```yaml
id: my-target
name: "My GenAI app"
base_url: "https://my-target.invalid"
capabilities: [has_chat]            # drives targetability
surfaces:
  chat: { method: POST, path: /api/chat }
auth: { type: none }                # none | bearer | apikey | cookie
success_oracle:
  canary:                           # → exfil_canary / leak_detector
    prefix: TRIDENT
    plant_surface: chat             # chat | retrieval_ingest | search | tool
    data_classification: Confidential
  expected_model_set: [GPT, Llama, Mistral, Phi]   # → categorical_match
```

| Detector | Verdict | Needs in profile |
|---|---|---|
| `exfil_canary` / `leak_detector` | `confirmed` | `success_oracle.canary` + adapter that plants it |
| `output_markup` | `confirmed` | nothing — generic regex |
| `categorical_match` | `confirmed` | `success_oracle.expected_model_set` |
| `refusal_judge` / `judged_objective` | `assessed` | nothing — LLM judge, offline fallback |

Two adapters ship today: **`echo`** (in-process) and **`aigoat`** (HTTP, the reference
vulnerable target). A new `id` needs a small adapter implementing `send()` (and `plant()`
for a canary). See
[`targets/target_profile.example.yaml`](backend/targets/target_profile.example.yaml) and
[`targets/aigoat.yaml`](backend/targets/aigoat.yaml).

---

## Project structure

```
backend/                  # all Python: engine, API, catalog, profiles
├── src/
│   ├── core/             # client (Foundry), models, policy_gate, trace, config
│   ├── nl/               # advisor + scope_to_scan
│   ├── skills/           # base, registry, pyrit_runner, judge
│   ├── agents/           # vertical-session factory + briefs
│   ├── orchestrator/     # coordinator, dispatch (agents-as-tools), scope_tool
│   ├── targets/          # adapter Protocol, oracle, echo, aigoat
│   ├── reports/          # correlator + html_report
│   ├── web/              # stdlib HTTP server + engine + SSE logbus
│   └── cli.py            # python -m src.cli
├── catalog/              # 20 techniques + 12 packages + JSON Schema + design docs
├── targets/              # declarative target profiles
├── manifests/            # Rules of Engagement as Code
├── run_web.cmd · requirements.txt · pyproject.toml · .env.example

frontend/frontend.html    # single-file TRIDENT console
server.py                 # optional FastAPI bridge (frontend/index.html ↔ campaign)
output/                   # generated reports (.html) + traces (.trace.jsonl)
```

---

## Design invariants & key schemas

Four rules keep the system auditable and target-agnostic:

1. **Skills never call PyRIT directly** — they go through `skills.pyrit_runner.PyritRunner`.
2. **Every action passes `core.policy_gate.PolicyGate.check`** inside the skill handler.
3. **Only the immutable `core.trace.Trace`** feeds the report — no shared blackboard.
4. **Target-agnostic core** — only `src/targets/*.py` may know endpoint specifics.

| Concept | Type | Notes |
|---|---|---|
| `mode` | `recon` / `attack` | Campaign-level (manifest). Gate-enforced (ADR-018). |
| `phase` | `recon` / `exploit` / `both` | Technique-level; recon mode keeps `phase ∈ {recon, both}`. |
| `severity_base` | `critical`…`info` | MSRC AI bug bar. |
| `scorer` | enum | Deterministic → SuccessOracle (`confirmed`); judged → LLM judge (`assessed`). |
| Layer cardinality | `1` OR `3`, never `2` | ADR-021: one layer or all three. |

---

## Roadmap

- Automatic technique synthesis — tooling that drafts new `SKILL.md` techniques.
- Re-wire the `pytest` suite (policy gate, ranker, end-to-end dispatch).
- Real PyRIT as the default judge (replacing today's offline heuristic).
- Cumulative-scope model techniques (`TRD-MOD-004/005/006`).
- Foundry hosted deployment (`azd up` with Key Vault + Managed Identity).
- Richer HTML report — attack-chain visualization and ATLAS heatmap.

---

## License

MIT © Nikita Litovchenko, Luca Medea, Lorenzo Albani, Riccardo Ponte, Changchen Yu, Alp Bayrak. See [`pyproject.toml`](backend/pyproject.toml).

> **Use responsibly.** TRIDENT is an offensive-security tool. Only run it against systems
> you own or are explicitly authorized to test, and keep every campaign inside the
> `host_allowlist` and Rules of Engagement declared in its manifest.
