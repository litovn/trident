# TRIDENT

**Black-box, multi-agent AI red-teaming accelerator** for generative-AI systems.

TRIDENT takes a plain-English description of what you want to test ("jailbreak the
chatbot", "prove it leaks data", "just map the attack surface") and turns it into a
governed, auditable red-team campaign. It selects techniques from a curated, standards-
mapped catalog (**OWASP LLM Top 10 (2025)** × **MITRE ATLAS** v6), dispatches them across
three attack layers via fenced agents, scores each result with a mix of deterministic
oracles and LLM judges, and produces a self-contained HTML report plus an immutable trace.

Built on the **GitHub Copilot SDK** (agentic orchestration), **Microsoft Foundry** (all
model calls), and **PyRIT** (execution surface — converters, scorers, orchestrators).

> **Status — v0.3.** Production-grade, target-agnostic catalog (20 techniques + 12
> packages). Working orchestrator, vertical agents, conversational NL→scope advisor,
> 5-rule policy gate, success oracle + canary honeytoken, immutable trace, and target
> adapters. Scope selection is Foundry-backed and degrades gracefully to a deterministic
> default package when Foundry is absent.

---

## Table of contents

- [Why TRIDENT](#why-trident)
- [How it works](#how-it-works)
- [The catalog: 3 layers, 20 techniques](#the-catalog-3-layers-20-techniques)
- [Attack packages](#attack-packages)
- [Scoring: confirmed vs assessed](#scoring-confirmed-vs-assessed)
- [Install](#install)
- [Configure Microsoft Foundry](#configure-microsoft-foundry)
- [Run](#run)
  - [Web UI](#web-ui)
  - [CLI](#cli)
- [Onboarding a target](#onboarding-a-target)
- [Project structure](#project-structure)
- [Design invariants](#design-invariants)
- [Key schema decisions](#key-schema-decisions)
- [Roadmap](#roadmap)
- [License](#license)

---

## Why TRIDENT

Red-teaming a GenAI application is hard to do *consistently*. Findings depend on the
tester's creativity, coverage is uneven, results aren't reproducible, and it's easy to
stray outside the agreed rules of engagement. TRIDENT addresses this by making the whole
campaign **declarative and governed**:

- **Black-box.** It only needs an endpoint and a small target profile — no model weights,
  no source access.
- **Standards-mapped.** Every technique is tagged to OWASP LLM Top 10 and MITRE ATLAS, so
  coverage is measurable and reports speak the language auditors expect.
- **Agents select, never invent.** Agents choose from the fixed catalog; they cannot
  improvise novel attacks outside the authored, reviewed technique set.
- **Governed by code.** A manifest is your *Rules of Engagement as Code*: campaign mode,
  host allowlist, technique denylist, query budgets, and human-in-the-loop gates. Every
  action passes a policy gate before it touches the target.
- **Auditable.** A single immutable trace feeds the report — every prompt, response,
  verdict, and piece of evidence is recorded.

---

## How it works

```
NL prompt  ("prove it leaks the planted secret")
   │
   ▼  Phase 1 — Package advisor (conversational, Foundry-backed; or --package)
Chosen package  (e.g. PKG-EXFIL)
   │
   ▼  Phase 2 — scope_to_scan  (gating: capabilities, allow/denylist, mode, status)
ScanPlan(verticals = [VerticalConfig × 1 or 3], skipped = […])
   │
   ▼  Phase 3 — Coordinator (GitHub Copilot SDK, agents-as-tools)
    ├── dispatch_prompt_agent  ─►  fenced Prompt vertical session  ─►┐
    ├── dispatch_app_agent     ─►  fenced App vertical session     ─►├─► Scorecards
    └── dispatch_model_agent   ─►  fenced Model vertical session   ─►┘
                                          │
                                          ▼  each skill handler:
                                          1. PolicyGate.check(action)
                                          2. PyritRunner.execute(technique, params, target)
                                               ├─ resolve {planted_secret} / {target_name}
                                               ├─ target.send(prompt)
                                               ├─ deterministic scorer? → SuccessOracle.detect()
                                               └─ judged scorer?         → LLM judge (offline fallback)
                                          3. Trace.append_*
   │
   ▼  Phase 4 — reports.correlator + reports.html_report
output/<campaign>.html   +   output/<campaign>.trace.jsonl
```

Four collaborating roles:

1. **NL→scope advisor** (`src/nl/`) — a conversational package selector. It asks
   clarifying questions only when the prompt is vague, otherwise proposes the best-fit
   packages immediately.
2. **Coordinator** (`src/orchestrator/`) — the top-level agent. It opens one *fenced*
   vertical session per in-scope layer, exposing **only** that layer's permitted skills.
3. **Vertical agents** (`src/agents/`) — Prompt / Application / Model specialists. Each
   reasons over its layer's techniques and drives them through the runner.
4. **Runner + oracle + trace** (`src/skills/`, `src/targets/`, `src/core/`) — the
   deterministic spine: policy-gate every action, execute via PyRIT, score, and record.

A campaign targets **one layer or all three — never exactly two** (ADR-021): findings are
either layer-isolated or a full-stack sweep.

---

## The catalog: 3 layers, 20 techniques

The catalog is the single source of truth. Each technique is one file —
`catalog/skills_catalog/<ID>/SKILL.md` — whose **YAML frontmatter is the full machine
config** and whose **Markdown body is the agent-facing procedure**. The registry loads
techniques straight from these files and validates every one against
`catalog/schema/catalog.schema.json` at load time (fail-fast on bad enums, missing
fields, malformed IDs, or dangling package references).

| Layer | What it attacks | Techniques |
|---|---|---|
| **Prompt** (`TRD-PRM-*`) | the input / prompt surface | 5 — system-prompt extraction, direct injection, multi-turn jailbreak, obfuscated injection, guardrail-probing recon |
| **Application** (`TRD-APP-*`) | RAG, tools, orchestration | 9 — indirect/RAG injection, info disclosure, output-handling (XSS), tool abuse, memory poisoning, exfil-via-tool, credential harvesting, tool poisoning, surface-enumeration recon |
| **Model** (`TRD-MOD-*`) | the underlying model via its API | 6 — fingerprinting, data extraction, misinformation, plus membership inference / extraction / inversion (cumulative, post-MVP) |

**Coverage is honest:** the OWASP map declares what is *not* black-box targetable rather
than hiding it — LLM03 (Supply Chain) and LLM10 (Unbounded Consumption) are marked
⛔ not-targetable with a stated reason. The full coverage matrices, ATLAS technique IDs,
and per-technique cards live in [`catalog/CATALOG.md`](backend/catalog/CATALOG.md).

---

## Attack packages

A **package** is a curated bundle of technique IDs plus safe limits (`max_intensity`,
`query_budget`) and the modes it runs in. The advisor resolves a prompt to a package
("package-first"). 12 packages across three axes (`catalog/packages.yaml`):

- **Profiles (one-click):** `PKG-QUICK` (quick scan) · `PKG-OWASP` (OWASP LLM sweep) ·
  `PKG-ATLAS` (ATLAS kill-chain) · `PKG-360` (full coverage).
- **Per-layer (single-layer option):** `PKG-PROMPT` · `PKG-APP` · `PKG-MODEL`.
- **Per-focus (intent-themed):** `PKG-GUARDRAIL` (jailbreak) · `PKG-EXFIL` (data
  exfiltration) · `PKG-RAG` (retrieval security) · `PKG-AGENTIC` (tool abuse) ·
  `PKG-RECON` (recon-only, non-intrusive).

---

## Scoring: confirmed vs assessed

Every result carries a verdict *kind* so you always know how much to trust it:

| Verdict | Meaning | Produced by |
|---|---|---|
| **`confirmed`** | deterministic ground truth, with evidence in the trace | `exfil_canary` / `leak_detector` (planted honeytoken), `output_markup` (structural regex), `categorical_match` (model fingerprint) |
| **`assessed`** | an LLM judgement, not ground truth | `refusal_judge` / `judged_objective` (LLM judge, with an **offline refusal heuristic** fallback when Foundry is absent) |

The deterministic detectors are powered by a per-target **SuccessOracle** (`src/targets/
oracle.py`). The key mechanism is a **canary honeytoken**: generated per campaign, planted
into the target by its adapter via the configured `plant_surface`, and resolved into
technique objectives through the `{planted_secret}` placeholder. When the model later
emits that exact token, disclosure is *confirmed*, and the canary's `data_classification`
drives the **MSRC AI bug-bar** severity (e.g. `info` → `high`). See
[`catalog/severity.md`](backend/catalog/severity.md), [`catalog/oracle.md`](backend/catalog/oracle.md),
and [`catalog/scorers.md`](backend/catalog/scorers.md) for the full contracts.

---

## Install

> **Python 3.11+ required** (tested on 3.11.9). All commands run from inside `backend/`.

```powershell
cd backend

# Full install (all capabilities): Copilot SDK + ranker + PyRIT + dev tooling
pip install -e ".[sdk,ranker,real,dev]"
```

Extras compose as needed:

| Extra | Pulls in | Needed for |
|---|---|---|
| `sdk` | `github-copilot-sdk`, `azure-identity` | the agentic Coordinator + vertical sessions |
| `ranker` | `openai`, `azure-identity` | the Phase-1 NL→scope package advisor |
| `real` | `pyrit` | the PyRIT execution surface (converters, judged scorers, orchestrators) |
| `dev` | `pytest`, `build` | tests + packaging |

The **base install** (no extras) is enough to import the catalog/registry/oracle and run
the deterministic core + the offline web engine. `requirements.txt` is a pinned lockfile
of a known-good environment.

---

## Configure Microsoft Foundry

Both the Copilot SDK Coordinator and the NL→scope advisor route **every model call through
Microsoft Foundry** — costs bill against **Foundry credit, never GitHub Copilot tokens**.
`FOUNDRY_ENDPOINT` is required for the full agentic path; without it the advisor falls back
to a deterministic default package per mode and the LLM judge falls back to an offline
heuristic, so a run still works (just without conversational scope selection).

Copy `.env.example` to `.env` and fill it in, or set the variables directly:

```powershell
$env:FOUNDRY_ENDPOINT         = "https://<account>.cognitiveservices.azure.com/"
$env:FOUNDRY_MODEL_DEPLOYMENT = "gpt-4o-mini"     # Coordinator + advisor + judge chat

# Auth (preferred): DefaultAzureCredential — `az login` locally, Managed Identity in prod.
az login

# Optional BYOK shortcut (prod should use Key Vault + Managed Identity, not .env):
# $env:FOUNDRY_API_KEY = "..."
```

No code change is needed to switch on Foundry — `TridentClient` (`src/core/client.py`) and
the ranker both read `FoundrySettings` (`src/core/config.py`) from the environment. See
[`.env.example`](backend/.env.example) for the complete variable list (wire API, ranker
overrides, the optional `web_search` grounding project endpoint, and target credentials).

---

## Run

> All commands run from inside `backend/` (`cd backend` first).

### Web UI

The frontend (`frontend/frontend.html`) is a single-file console — planner, live terminal,
and report viewer. It's served by a tiny stdlib web bridge (`src/web/`) that exposes the
engine over a same-origin JSON API with **zero extra dependencies** beyond the base
install. This is the easiest way to drive TRIDENT and the headline of the demo:

```powershell
run_web.cmd                 # http://localhost:8765  (default port)
run_web.cmd --port 9000
```

`run_web.cmd` prefers the repo `.venv` and launches `python -m src.web.server`, which
serves the UI at `/` and exposes:

| Endpoint | Purpose |
|---|---|
| `GET  /api/health` | capability probe (engine, catalog counts, foundry/pyrit/sdk flags) |
| `GET  /api/packages`, `GET /api/techniques` | catalog data for the UI |
| `POST /api/plan` | one advisor turn — propose packages or ask to clarify |
| `POST /api/campaign` | run a recon/attack campaign; returns the trace + correlated report |
| `GET  /api/logstream` | Server-Sent Events: the engine's live logs (web terminal) |

The web engine runs the in-process **Echo** target out of the box, so you can exercise the
full plan → dispatch → score → report flow without configuring an external target.

### CLI

Every campaign goes through the SDK Coordinator. Point it at a manifest (Rules of
Engagement) and a natural-language prompt; the advisor (or `--package`) selects the scope.

```powershell
# Attack a real target. The manifest's `target_profile_id` resolves a profile
# from targets/ (here: targets/aigoat.yaml — the reference vulnerable app).
python -m src.cli `
  --manifest manifests/aigoat.yaml `
  --catalog  catalog `
  --targets-dir targets `
  --out      output `
  --prompt   "direct prompt injection: override the bot and exfiltrate the secret"

# Skip the conversational advisor and pin the package:
python -m src.cli --manifest manifests/aigoat.yaml --package PKG-GUARDRAIL `
  --prompt "bypass the guardrails"
```

Useful flags (`python -m src.cli --help`):

- `--package <ID>` — skip the advisor and use a specific package (e.g. `PKG-EXFIL`).
- `--confirm-chain` — human-in-the-loop: ask before dispatching each layer (interactive
  TTY only).
- `--targets-dir`, `--catalog`, `--out` — override the default directories.

A run writes two artifacts to `--out`: `output/<campaign_id>.html` (the report) and
`output/<campaign_id>.trace.jsonl` (the immutable trace).

> **AIGoat note:** the AIGoat adapter needs the target running locally and an
> `AIGOAT_PASSWORD` env var (see `.env.example`). The Echo target is in-process and needs
> nothing — it's the fastest end-to-end smoke and is what the web engine uses by default.

A manifest is small and declarative — `manifests/aigoat.yaml`:

```yaml
campaign_id: aigoat
mode: attack                 # recon | attack — gate-enforced (ADR-018)
target_profile_id: aigoat    # resolves targets/aigoat.yaml by its `id` field
technique_denylist: []
host_allowlist: [127.0.0.1]  # Rules of Engagement: attack traffic stays here
query_budget_per_vertical: 5
hitl_techniques: []
```

---

## Onboarding a target

TRIDENT's core is **target-agnostic** — only files under `src/targets/` may know endpoint
specifics. A target plugs in through a small YAML **profile** plus a `success_oracle`
block; **targetability is computed**: a technique runs only if the target's `capabilities`
satisfy its `needs_capabilities`. The minimum to get recon + canary + markup + LLM-judge
working:

```yaml
id: my-target                 # slug (the CLI maps this to an adapter)
name: "My GenAI app"
base_url: "https://my-target.invalid"

# Drives technique targetability. has_chat alone is enough for the recon leads.
capabilities: [has_chat]

# Abstract attack surface → concrete endpoint. The adapter resolves these.
surfaces:
  chat: { method: POST, path: /api/chat }

auth: { type: none }          # none | bearer | apikey | cookie

# The generic success-detection suite — each block unlocks one detector.
success_oracle:
  canary:                     # → exfil_canary / leak_detector (honeytoken)
    prefix: TRIDENT
    plant_surface: chat       # chat | retrieval_ingest | search | tool
    data_classification: Confidential   # feeds MSRC severity
  expected_model_set: [GPT, Llama, Mistral, Phi]   # → categorical_match (fingerprint)
# output_markup needs no config — generic regex over the response.
# refusal_judge / judged_objective need no config — LLM judge (offline fallback).
```

What each detector needs from the profile:

| Detector | Verdict | Needs in profile |
|---|---|---|
| `exfil_canary` / `leak_detector` | `confirmed` | `success_oracle.canary` + an adapter that plants it |
| `output_markup` | `confirmed` | nothing — generic regex on the output |
| `categorical_match` (fingerprint) | `confirmed` | `success_oracle.expected_model_set` |
| `refusal_judge` / `judged_objective` | `assessed` | nothing — LLM judge, offline fallback |

The CLI maps the profile `id` to an adapter. Two adapters ship today: **`echo`**
(in-process, no setup) and **`aigoat`** (HTTP, the reference vulnerable target). A
brand-new `id` needs a small adapter implementing `send()` (and, for a canary, `plant()`).
See [`targets/target_profile.example.yaml`](backend/targets/target_profile.example.yaml)
for the fully-annotated schema and [`targets/aigoat.yaml`](backend/targets/aigoat.yaml)
for a real one.

---

## Project structure

```
backend/                  # all Python: engine, API, catalog, profiles
├── src/
│   ├── core/             # client (Foundry), models, policy_gate (5 rules), trace, config
│   ├── nl/               # advisor (conversational package selector) + scope_to_scan
│   ├── skills/           # base, registry (JSON-Schema validated), pyrit_runner, judge
│   ├── agents/           # factory (build vertical sessions + PyRIT tools), briefs
│   ├── orchestrator/     # coordinator (Phase 0–4), dispatch (agents-as-tools), scope_tool
│   ├── targets/          # adapter Protocol, oracle (canary + detectors), echo, aigoat
│   ├── reports/          # correlator + html_report
│   ├── web/              # web bridge: server (stdlib HTTP) + engine + logbus (SSE)
│   └── cli.py            # python -m src.cli --manifest ... --prompt ...
├── catalog/              # 20 techniques + 12 packages + JSON Schema + reference docs
│   ├── skills_catalog/   # one SKILL.md per technique — the single source of truth
│   │   ├── trd-prm-*/SKILL.md   # 5 prompt techniques
│   │   ├── trd-app-*/SKILL.md   # 9 application techniques
│   │   └── trd-mod-*/SKILL.md   # 6 model techniques (-004/-005/-006 post-MVP)
│   ├── packages.yaml     # 12 packages: 4 profile + 3 layer + 5 focus
│   ├── schema/catalog.schema.json   # authoritative; validated at load time
│   └── CATALOG.md, severity.md, oracle.md, scorers.md, strategies.md   # design docs
├── targets/              # declarative target profiles
│   ├── aigoat.yaml                   # the reference vulnerable target
│   └── target_profile.example.yaml   # fully-annotated generic schema
├── manifests/            # Rules of Engagement as Code (ADR-008)
│   ├── aigoat.yaml               # attack-mode run against AIGoat
│   └── sample_attack.yaml        # attack-mode smoke
├── run_web.cmd           # launches the web bridge (serves ../frontend on :8765)
├── requirements.txt
├── pyproject.toml
└── .env.example

frontend/
└── frontend.html         # single-file TRIDENT console (planner, terminal, report)

output/                   # generated reports (.html) + traces (.trace.jsonl)
```

---

## Design invariants

These four rules keep the system auditable and target-agnostic — do not break them:

1. **Skills never call PyRIT directly** — they go through `skills.pyrit_runner.PyritRunner`.
2. **Every action passes `core.policy_gate.PolicyGate.check`** inside the skill handler.
3. **Only the immutable `core.trace.Trace`** feeds the report — there is no shared blackboard.
4. **Target-agnostic core** — only `src/targets/*.py` may know endpoint specifics. AIGoat
   is one implementation, never a dependency.

---

## Key schema decisions

| Concept | Type | Notes |
|---|---|---|
| `mode` | `recon` / `attack` | Campaign-level (manifest). Gate-enforced (ADR-018). |
| `phase` | `recon` / `exploit` / `both` | Technique-level (catalog). Recon-mode keeps `phase ∈ {recon, both}`. |
| `severity_base` | `critical` / `high` / `medium` / `low` / `info` | MSRC AI bug bar (string). |
| `severity_track` | `security` / `content` | Content track is *informational*, not blocking. |
| `scorer` | enum | Deterministic → SuccessOracle (`confirmed`); judged → LLM judge (`assessed`). |
| `success_oracle` | block on the target profile | Canary, plant surface, data classification, expected model set. |
| Layer cardinality | `1` OR `3`, never `2` | ADR-021: a campaign targets one layer or all three. |

---

## Roadmap

- **Automatic technique synthesis (v1).** Tooling that drafts new `SKILL.md` techniques
  (and recon → target-profile generation). Today every technique is hand-authored.
- **Re-wire the `pytest` suite** (policy gate, ranker, end-to-end dispatch).
- **Real PyRIT as the default judge** in `skills/pyrit_runner.py` (SelfAskRefusalScorer,
  SelfAskTrueFalseScorer) — today's default judge is the offline heuristic.
- **Cumulative-scope techniques** (`TRD-MOD-004/005/006`) once the campaign-level scorer lands.
- **Foundry hosted deployment** — one-click `azd up` with Key Vault + Managed Identity.
- **Richer HTML report** — attack-chain visualization and an ATLAS heatmap.

---

## License

MIT © Nikita Litovchenko. See [`pyproject.toml`](backend/pyproject.toml).

> **Use responsibly.** TRIDENT is an offensive-security tool. Only run it against systems
> you own or are explicitly authorized to test, and keep every campaign inside the
> `host_allowlist` and Rules of Engagement declared in its manifest.
